import copy
import json
from datetime import datetime, timezone

import pytest
from icalendar import Calendar
from pydantic import ValidationError

import app
import calendar_operations as ops
from test_app import client, HEADERS

CAL = 'selected-calendar'


class Bridge:
    def __init__(self, event):
        self.events = Calendar.from_ical(app.make_ics(event, 'fixture@calendar')).walk('VEVENT')
        self.calls = []
        self.fail_readback = False

    def __call__(self, args, content=None):
        self.calls.append((args, content))
        if args[0] == 'calendars-json':
            return json.dumps([{'ID': CAL, 'Name': 'Calendar'}])
        if args[0] == 'events-json':
            if self.fail_readback and any(c for a, c in self.calls):
                raise RuntimeError('simulated lost read-back')
            records = []
            for item in self.events:
                if '-uid' in args and str(item['UID']) != args[args.index('-uid') + 1]:
                    continue
                cal = Calendar(); cal.add('version', '2.0'); cal.add_component(item)
                records.append({'ics': cal.to_ical().decode(), 'unverified': False})
            return json.dumps({'calendar_id': CAL, 'events': records, 'unreadable_count': 0})
        if args[:2] == ['event', 'put']:
            for item in Calendar.from_ical(content).walk('VEVENT'):
                if item.get('RECURRENCE-ID') and isinstance(item.decoded('RECURRENCE-ID'), datetime):
                    master = next(e for e in self.events if not e.get('RECURRENCE-ID'))
                    assert item['RECURRENCE-ID'].params.get('TZID') == master['DTSTART'].params.get('TZID'), 'Exception must retain parent timezone'
                self.events = [e for e in self.events if not (e['UID'] == item['UID'] and e.get('RECURRENCE-ID') == item.get('RECURRENCE-ID'))]
                self.events.append(item)
            return 'saved'
        if args[:2] == ['event', 'delete']:
            self.events = []
            return 'deleted'
        if args[0] == 'delete-occurrence':
            rid = int(args[args.index('-recurrence-id') + 1])
            self.events = [e for e in self.events if not (e.get('RECURRENCE-ID') and int(ops.moment(e.decoded('RECURRENCE-ID')).timestamp()) == rid)]
            return '{"deleted":true}'
        raise AssertionError(args)


def sample(**kwargs):
    return app.EventRequest(title='Meeting', start='2026-10-19T09:00:00+03:00', end='2026-10-19T10:00:00+03:00', **kwargs)


def run(bridge, kind, **kwargs):
    return ops.execute(ops.CalendarOperation(kind=kind, **kwargs), bridge, CAL)


def read(bridge):
    return run(bridge, 'get_event', uid='fixture@calendar')


def change(bridge, changes, scope='event', **kwargs):
    return run(bridge, 'update_event', uid='fixture@calendar', expected_revision=read(bridge)['revision'], scope=scope, changes=changes, **kwargs)


def test_list_search_and_read_reminders():
    bridge = Bridge(sample(reminders_minutes=[0, 15]))
    assert run(bridge, 'list_calendars')['calendars'][0]['default']
    results = run(bridge, 'list_events', start='2026-10-19T00:00:00Z', end='2026-10-20T00:00:00Z', query='MEET')
    assert len(results['events']) == 1
    assert {r['minutes_before'] for r in results['events'][0]['reminders']} == {0, 15}
    assert len(read(bridge)['revision']) == 64


def test_edit_preserves_existing_alarm_and_unknown_property():
    bridge = Bridge(sample(reminders_minutes=[15]))
    bridge.events[0].add('x-private-property', 'keep')
    change(bridge, {'title': 'Changed', 'start': '2026-10-19T14:00:00+03:00'})
    item = bridge.events[0]
    assert str(item['X-PRIVATE-PROPERTY']) == 'keep'
    assert item.decoded('DTEND').astimezone(ops.ZoneInfo('Europe/Helsinki')).hour == 15
    assert read(bridge)['events'][0]['reminders'][0]['minutes_before'] == 15
    change(bridge, {'reminders_minutes': []})
    assert not bridge.events[0].walk('VALARM')


def test_stale_revision_and_attendee_never_write():
    bridge = Bridge(sample())
    revision = read(bridge)['revision']
    bridge.events[0]['SUMMARY'] = 'Externally changed'
    with pytest.raises(ops.OperationError, match='changed since'):
        run(bridge, 'delete_event', uid='fixture@calendar', expected_revision=revision)
    bridge.events[0].add('attendee', 'mailto:guest@example.test')
    with pytest.raises(ops.OperationError, match='Attendee'):
        change(bridge, {'title': 'Do not send'})
    assert not any(a[0] == 'event' for a, _ in bridge.calls)


def test_recurring_local_time_survives_dst_and_scope_required():
    bridge = Bridge(sample(recurrence={'frequency': 'WEEKLY', 'count': 3}, recurrence_timezone='Europe/Helsinki', reminders_minutes=[30]))
    results = run(bridge, 'list_events', start='2026-10-18T00:00:00Z', end='2026-11-03T00:00:00Z')['events']
    assert [e['start'] for e in results] == ['2026-10-19T09:00:00+03:00', '2026-10-26T09:00:00+02:00', '2026-11-02T09:00:00+02:00']
    with pytest.raises(ops.OperationError, match='Choose series'):
        change(bridge, {'title': 'no'})
    change(bridge, {'title': 'Weekly changed'}, scope='series')
    assert str(bridge.events[0]['SUMMARY']) == 'Weekly changed'
    assert bridge.events[0].get('RRULE')


def test_occurrence_move_reedit_cancel_keeps_series():
    bridge = Bridge(sample(recurrence={'frequency': 'WEEKLY', 'count': 3}, recurrence_timezone='Europe/Helsinki'))
    rid = '2026-10-26T09:00:00+02:00'
    change(bridge, {'start': '2026-10-26T14:00:00+02:00'}, scope='occurrence', recurrence_id=rid)
    assert len(bridge.events) == 2
    change(bridge, {'title': 'Moved twice'}, scope='occurrence', recurrence_id=rid)
    with pytest.raises(ops.OperationError, match='existing exceptions'):
        change(bridge, {'start': '2026-10-19T10:00:00+03:00'}, scope='series')
    result = run(bridge, 'delete_event', uid='fixture@calendar', expected_revision=read(bridge)['revision'], scope='occurrence', recurrence_id=rid)
    assert result['verified']
    results = run(bridge, 'list_events', start='2026-10-18T00:00:00Z', end='2026-11-03T00:00:00Z')['events']
    assert len(results) == 2
    assert bridge.events[0].get('RRULE')


def test_new_occurrence_advances_parent_sequence():
    bridge = Bridge(sample(recurrence={'frequency': 'WEEKLY', 'count': 3}, recurrence_timezone='Europe/Helsinki'))
    bridge.events[0].add('sequence', 7)
    change(bridge, {'start': '2026-10-26T14:00:00+02:00'}, scope='occurrence', recurrence_id='2026-10-26T09:00:00+02:00')
    master = next(e for e in bridge.events if not e.get('RECURRENCE-ID'))
    exception = next(e for e in bridge.events if e.get('RECURRENCE-ID'))
    assert int(master['SEQUENCE']) == 7
    assert int(exception['SEQUENCE']) == 8


def test_provider_failure_retains_safe_code_without_upstream_text():
    bridge = Bridge(sample())
    def rejected(args, content=None):
        if args[:2] == ['event', 'put']:
            raise app.BridgeError('secret upstream error', 'Proton rejected the write, code 2011')
        return bridge(args, content)
    with pytest.raises(ops.MutationUncertain) as error:
        change(rejected, {'title': 'Changed'})
    assert 'code 2011' in str(error.value)
    assert 'secret' not in str(error.value)


def test_series_reminder_changes_apply_to_exceptions():
    bridge = Bridge(sample(recurrence={'frequency':'WEEKLY', 'count':3}, recurrence_timezone='Europe/Helsinki', reminders_minutes=[15]))
    change(bridge, {'title':'Exception'}, scope='occurrence', recurrence_id='2026-10-26T09:00:00+02:00')
    change(bridge, {'reminders_minutes':[30]}, scope='series')
    assert all(ops.event_view(e, CAL, '')['reminders'][0]['minutes_before'] == 30 for e in bridge.events)


def test_occurrence_cancel_excludes_parent_and_preserves_other_exception():
    bridge = Bridge(sample(recurrence={'frequency': 'WEEKLY', 'count': 3}, recurrence_timezone='Europe/Helsinki'))
    change(bridge, {'title': 'Keep this exception'}, scope='occurrence', recurrence_id='2026-11-02T09:00:00+02:00')
    change(bridge, {'title': 'Cancel this exception'}, scope='occurrence', recurrence_id='2026-10-26T09:00:00+02:00')
    run(bridge, 'delete_event', uid='fixture@calendar', expected_revision=read(bridge)['revision'], scope='occurrence', recurrence_id='2026-10-26T09:00:00+02:00')
    master = next(e for e in bridge.events if not e.get('RECURRENCE-ID'))
    assert master.get('RRULE') and master.get('EXDATE')
    assert any(str(e['SUMMARY']) == 'Keep this exception' for e in bridge.events)
    assert not any(a[:2] == ['event', 'delete'] for a, _ in bridge.calls)
    results = run(bridge, 'list_events', start='2026-10-18T00:00:00Z', end='2026-11-03T00:00:00Z')['events']
    assert len(results) == 2 and results[1]['title'] == 'Keep this exception'


def test_delete_series_verified_and_readback_failure_is_uncertain():
    bridge = Bridge(sample(recurrence={'frequency':'DAILY', 'count':3}, recurrence_timezone='Europe/Helsinki'))
    result = run(bridge, 'delete_event', uid='fixture@calendar', expected_revision=read(bridge)['revision'], scope='series')
    assert result['verified'] and not bridge.events
    bridge = Bridge(sample())
    bridge.fail_readback = True
    with pytest.raises(ops.MutationUncertain):
        change(bridge, {'title':'Actually saved'})
    assert str(bridge.events[0]['SUMMARY']) == 'Actually saved'
    assert sum(a[0] == 'event' for a, _ in bridge.calls) == 1


def test_all_day_recurrence_and_exclusive_end():
    event = app.EventRequest(title='Holiday', start='2026-10-20', recurrence={'frequency':'YEARLY', 'count':2}, reminders_minutes=[60])
    assert event.end.isoformat() == '2026-10-21'
    bridge = Bridge(event)
    results = run(bridge, 'list_events', start='2026-10-19T00:00:00Z', end='2026-10-22T00:00:00Z')['events']
    assert results[0]['all_day'] and results[0]['start'] == '2026-10-20'


@pytest.mark.parametrize('changes', [
    {'recurrence_timezone':'Not/AZone'}, {'reminders_minutes':[True]}, {'reminders_minutes':[-1]},
    {'recurrence':{'frequency':'WEEKLY','count':2,'until':'2026-12-01T00:00:00Z'}},
])
def test_invalid_changes_rejected_before_queue(changes):
    with pytest.raises(ValidationError):
        ops.CalendarOperation(kind='update_event', uid='uid', expected_revision='a'*64, changes=changes)


def test_mutations_durable_reads_fresh_and_auth(client):
    payload = {'kind':'delete_event','uid':'fixture@calendar','expected_revision':'a'*64}
    assert client.post('/operations', json=payload).status_code == 401
    first = client.post('/operations', json=payload, headers=HEADERS).json()
    assert client.post('/operations', json=payload, headers=HEADERS).json()['operation_id'] == first['operation_id']
    a = client.post('/operations', json={'kind':'list_calendars'}, headers=HEADERS).json()
    b = client.post('/operations', json={'kind':'list_calendars'}, headers=HEADERS).json()
    assert a['operation_id'] != b['operation_id']
    with app.db() as conn:
        conn.execute("UPDATE operations SET state='running' WHERE id=?", (first['operation_id'],))
    from fastapi.testclient import TestClient
    with TestClient(app.app) as restarted:
        assert restarted.get('/operations/'+first['operation_id'], headers=HEADERS).json()['state'] == 'unknown'


def test_readonly_reconciliation_does_not_rewrite(client, monkeypatch):
    job = client.post('/events', json={'title':'Meeting','start':'2026-10-19T09:00:00+03:00','end':'2026-10-19T10:00:00+03:00'}, headers=HEADERS).json()
    app.update_job(job['job_id'], 'unknown')
    bridge = Bridge(sample())
    bridge.events[0]['UID'] = job['job_id'] + '@private-proton-gpt'
    monkeypatch.setattr(app, 'run_bridge', bridge)
    monkeypatch.setattr(app, 'CALENDAR_ID', CAL)
    task = client.post('/events/'+job['job_id']+'/verify', json={}, headers=HEADERS).json()
    with app.db() as conn:
        row = conn.execute('SELECT * FROM operations WHERE id=?',(task['operation_id'],)).fetchone()
    app.process_operation(row)
    assert app.operation_status(task['operation_id'])['result']['verified']
    assert app.get_status(job['job_id'])['state'] == 'verified'
    assert not any(a[0] == 'event' for a, _ in bridge.calls)


def test_occurrence_verification_rejects_missing_master():
    bridge = Bridge(sample(recurrence={'frequency':'WEEKLY', 'count':3}, recurrence_timezone='Europe/Helsinki'))
    def lossy(args, content=None):
        result = bridge(args, content)
        if content:
            bridge.events = [i for i in bridge.events if i.get('RECURRENCE-ID')]
        return result
    revision = read(bridge)['revision']
    with pytest.raises(ops.MutationUncertain):
        ops.execute(ops.CalendarOperation(kind='update_event', uid='fixture@calendar', expected_revision=revision, scope='occurrence', recurrence_id='2026-10-26T09:00:00+02:00', changes={'title':'Moved'}), lossy, CAL)


def test_exclusion_verification_compares_instants_and_ignores_duplicate_cards():
    from zoneinfo import ZoneInfo
    original = Bridge(sample()).events[0]
    expected = copy.deepcopy(original)
    point = datetime(2026, 10, 26, 9, tzinfo=ZoneInfo('Europe/Helsinki'))
    expected.add('exdate', point)
    actual = copy.deepcopy(original)
    actual.add('exdate', point.astimezone(timezone.utc))
    actual.add('exdate', point.astimezone(timezone.utc))
    assert ops.verification_signature(actual) == ops.verification_signature(expected)
    actual.add('exdate', datetime(2026, 11, 2, 7, tzinfo=timezone.utc))
    assert ops.verification_signature(actual) != ops.verification_signature(expected)
