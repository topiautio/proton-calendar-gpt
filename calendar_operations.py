"""Calendar queries and deliberate mutations of existing events.

Keep the iCalendar object when editing: reconstructing only title/time would
silently discard reminders, recurrence exceptions and provider properties.
"""
import copy
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

import recurring_ical_events
from icalendar import Alarm, Calendar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CALENDAR_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9_+=-]{0,511}$'


class OperationError(Exception):
    """A safe error raised before an existing event is mutated."""


class MutationUncertain(Exception):
    pass


class Recurrence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    frequency: Literal['DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY']
    interval: int = Field(default=1, ge=1, le=52)
    count: int | None = Field(default=None, ge=1, le=1000)
    until: datetime | None = None
    weekdays: list[Literal['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']] = Field(default_factory=list, max_length=7)

    @model_validator(mode='after')
    def validate_rule(self):
        if self.count is not None and self.until is not None:
            raise ValueError('Choose count or until, not both')
        if self.until is not None and self.until.utcoffset() is None:
            raise ValueError('until requires a UTC offset')
        self.weekdays = sorted(set(self.weekdays))
        return self


def rule_value(recurrence):
    rule = {'freq': recurrence.frequency, 'interval': recurrence.interval}
    if recurrence.count is not None:
        rule['count'] = recurrence.count
    if recurrence.until is not None:
        rule['until'] = recurrence.until.astimezone(timezone.utc)
    if recurrence.weekdays:
        rule['byday'] = recurrence.weekdays
    return rule


def reminders(item, minutes):
    item.subcomponents = [c for c in item.subcomponents if c.name != 'VALARM']
    for value in sorted(set(minutes)):
        alarm = Alarm()
        alarm.add('action', 'DISPLAY')
        alarm.add('trigger', -timedelta(minutes=value))
        alarm.add('description', str(item.get('SUMMARY', 'Reminder')))
        item.add_component(alarm)


def moment(value):
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise OperationError('A calendar event has an unresolved timezone')
        return value.astimezone(timezone.utc)
    return datetime.combine(value, datetime.min.time(), timezone.utc)


def event_end(item):
    start = item.decoded('DTSTART')
    return item.decoded('DTEND', start + item.decoded('DURATION', timedelta(days=1) if not isinstance(start, datetime) else timedelta(0)))


def time_value(value):
    return value.isoformat()


def calendar_from_snapshot(snapshot):
    cal = Calendar()
    cal.add('version', '2.0')
    cal.add('prodid', '-//Private Proton Calendar//EN')
    for record in snapshot['events']:
        for item in Calendar.from_ical(record['ics']).walk('VEVENT'):
            cal.add_component(item)
    cal.subcomponents.sort(key=lambda item: (str(item.get('UID', '')), str(item.get('RECURRENCE-ID', ''))))
    return cal


def snapshot(bridge, calendar_id, uid=None):
    args = ['events-json', '-calendar', calendar_id]
    if uid:
        args += ['-uid', uid]
    try:
        value = json.loads(bridge(args))
        if value['calendar_id'] != calendar_id or not isinstance(value['events'], list):
            raise ValueError('Invalid snapshot')
        return value
    except Exception as exc:
        raise OperationError('Calendar could not be read. Check the NAS login and bridge configuration.') from exc


def revision(cal):
    return hashlib.sha256(cal.to_ical()).hexdigest()


def event_view(item, calendar_id, rev):
    start = item.decoded('DTSTART')
    end = event_end(item)
    trigger_values = []
    for alarm in item.walk('VALARM'):
        trigger = alarm.decoded('TRIGGER', None)
        if isinstance(trigger, timedelta):
            trigger_values.append({'action': str(alarm.get('ACTION', 'DISPLAY')), 'minutes_before': -int(trigger.total_seconds() / 60)})
    rid = item.decoded('RECURRENCE-ID', None)
    return {'calendar_id': calendar_id, 'uid': str(item['UID']), 'revision': rev,
            'title': str(item.get('SUMMARY', '')), 'start': time_value(start), 'end': time_value(end),
            'all_day': not isinstance(start, datetime), 'location': str(item.get('LOCATION', '')),
            'description': str(item.get('DESCRIPTION', '')), 'recurrence': item.get('RRULE').to_ical().decode() if item.get('RRULE') else None,
            'recurrence_id': time_value(rid) if rid is not None else None, 'reminders': trigger_values,
            'has_attendees': bool(item.get('ATTENDEE'))}


class CalendarOperation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['list_calendars', 'list_events', 'get_event', 'update_event', 'delete_event']
    calendar_id: str | None = Field(default=None, pattern=CALENDAR_PATTERN)
    uid: str | None = Field(default=None, min_length=1, max_length=512)
    start: datetime | None = None
    end: datetime | None = None
    query: str = Field(default='', max_length=200)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=10000)
    expected_revision: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    scope: Literal['event', 'series', 'occurrence'] = 'event'
    recurrence_id: datetime | date | None = None
    changes: dict | None = None

    @field_validator('recurrence_id', mode='before')
    @classmethod
    def distinguish_dates(cls, value):
        if isinstance(value, str) and len(value) == 10:
            return date.fromisoformat(value)
        return value

    @model_validator(mode='after')
    def check_request(self):
        if self.uid and any(ord(c) < 32 for c in self.uid):
            raise ValueError('Invalid event UID')
        if self.kind != 'list_calendars' and self.kind != 'list_events' and not self.uid:
            raise ValueError('An event UID from a calendar read is required')
        if self.kind == 'list_events':
            if not self.start or not self.end or self.start.utcoffset() is None or self.end.utcoffset() is None:
                raise ValueError('Date range requires explicit offsets')
            if not timedelta(0) < self.end - self.start <= timedelta(days=366):
                raise ValueError('Read at most 366 days per request')
        if self.kind in ('update_event', 'delete_event'):
            if not self.expected_revision:
                raise ValueError('Read the event first and supply its revision')
            if self.scope == 'occurrence' and self.recurrence_id is None:
                raise ValueError('Specify which occurrence to change')
            if isinstance(self.recurrence_id, datetime) and self.recurrence_id.utcoffset() is None:
                raise ValueError('Occurrence time requires an offset')
        if self.kind == 'update_event':
            if not self.changes:
                raise ValueError('At least one change is required')
            allowed = {'title', 'start', 'end', 'location', 'description', 'recurrence', 'reminders_minutes', 'recurrence_timezone'}
            if set(self.changes) - allowed:
                raise ValueError('Unsupported event changes')
            for name, maximum in [('title', 200), ('location', 300), ('description', 2000)]:
                if name in self.changes:
                    value = self.changes[name]
                    if not isinstance(value, str) or len(value) > maximum or (name == 'title' and not value.strip()) or any(ord(c) < 32 and c not in '\n\t' for c in value):
                        raise ValueError('Invalid event text')
            if 'recurrence' in self.changes and self.changes['recurrence'] is not None:
                Recurrence.model_validate(self.changes['recurrence'])
            if 'recurrence_timezone' in self.changes:
                try:
                    ZoneInfo(self.changes['recurrence_timezone'])
                except (KeyError, ValueError, TypeError):
                    raise ValueError('Use a valid IANA recurrence timezone')
            if 'reminders_minutes' in self.changes:
                values = self.changes['reminders_minutes']
                if not isinstance(values, list) or len(values) > 5 or any(type(v) is not int or not 0 <= v <= 10080 for v in values):
                    raise ValueError('Use at most five device reminders within seven days')
        return self


def occurrences(cal, start, end):
    for item in cal.walk('VEVENT'):
        rule = item.get('RRULE')
        if rule and str(rule.get('FREQ', [''])[0]) not in ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'):
            raise OperationError('Sub-daily recurring events must be read in Proton')
    try:
        return [i for i in recurring_ical_events.of(cal).between(start, end) if str(i.get('STATUS', '')).upper() != 'CANCELLED']
    except Exception as exc:
        raise OperationError('This recurrence could not be interpreted safely') from exc


def selected_occurrence(cal, value):
    point = moment(value)
    # Moved exceptions are found by original recurrence ID, even when their
    # current start falls outside the original occurrence window.
    for item in cal.walk('VEVENT'):
        rid = item.decoded('RECURRENCE-ID', None)
        if rid is not None and moment(rid) == point:
            return copy.deepcopy(item)
    items = occurrences(cal, point, point + timedelta(seconds=1))
    for item in items:
        rid = item.decoded('RECURRENCE-ID', item.decoded('DTSTART'))
        if moment(rid) == point:
            return copy.deepcopy(item)
    raise OperationError('The selected recurrence occurrence was not found')


def update_component(item, changes):
    old_start = item.decoded('DTSTART')
    old_end = event_end(item)
    full_day = not isinstance(old_start, datetime)
    for name in ('start', 'end'):
        if name in changes:
            try:
                value = date.fromisoformat(changes[name]) if full_day else datetime.fromisoformat(changes[name])
                if isinstance(value, datetime) and value.utcoffset() is None:
                    raise ValueError('Offset required')
            except (ValueError, TypeError) as exc:
                raise OperationError('Use dates for all-day events and explicit offsets for timed events') from exc
            item['DTSTART' if name == 'start' else 'DTEND'] = value
    # Assign via add(), rather than a raw datetime, to retain typed iCalendar values.
    for name in ('DTSTART', 'DTEND'):
        value = item.get(name)
        if isinstance(value, (datetime, date)):
            del item[name]
            item.add(name, value.astimezone(timezone.utc) if isinstance(value, datetime) and not getattr(value.tzinfo, 'key', None) else value)
    if 'start' in changes and 'end' not in changes:
        if 'DTEND' in item:
            del item['DTEND']
        item.add('dtend', item.decoded('DTSTART') + (old_end - old_start))
    if any(k in changes for k in ('start', 'end')) and 'DURATION' in item:
        del item['DURATION']
    start, end = item.decoded('DTSTART'), item.decoded('DTEND', old_end)
    if moment(end) <= moment(start) or moment(end) - moment(start) > timedelta(days=7):
        raise OperationError('End must follow start within seven days')
    if item.get('RRULE') and isinstance(start, datetime):
        zone = changes.get('recurrence_timezone') or getattr(old_start.tzinfo, 'key', None)
        if not zone and any(name in changes for name in ('start', 'end')):
            raise OperationError('Set recurrence_timezone when rescheduling a recurring series')
        if zone:
            for name in ('DTSTART', 'DTEND'):
                value = item.decoded(name).astimezone(ZoneInfo(zone))
                del item[name]
                item.add(name, value)
    for field, prop in [('title', 'SUMMARY'), ('location', 'LOCATION'), ('description', 'DESCRIPTION')]:
        if field in changes:
            if prop in item:
                del item[prop]
            item.add(prop, changes[field].strip())
    if 'recurrence' in changes:
        if 'RRULE' in item:
            del item['RRULE']
        if changes['recurrence'] is not None:
            if not full_day and 'recurrence_timezone' not in changes and not getattr(old_start.tzinfo, 'key', None):
                raise OperationError('Set recurrence_timezone for a new recurring series')
            rule = Recurrence.model_validate(changes['recurrence'])
            if full_day and rule.until is not None:
                raise OperationError('For all-day recurrences use count instead of until')
            if rule.until is not None and rule.until < moment(start):
                raise OperationError('Recurrence until must follow the series start')
            item.add('rrule', rule_value(rule))
            if not full_day:
                zone = changes.get('recurrence_timezone') or old_start.tzinfo.key
                for name in ('DTSTART', 'DTEND'):
                    value = item.decoded(name).astimezone(ZoneInfo(zone))
                    del item[name]
                    item.add(name, value)
    if 'reminders_minutes' in changes:
        reminders(item, changes['reminders_minutes'])
    if 'DTSTAMP' in item:
        del item['DTSTAMP']
    item.add('dtstamp', datetime.now(timezone.utc))
    return item


def verification_signature(item):
    # Proton can add organizer/status/sequence metadata. Verify the fields under
    # our control, including alarms and recurrence/exclusions, rather than bytes.
    names = ['UID', 'SUMMARY', 'DTSTART', 'DTEND', 'LOCATION', 'DESCRIPTION', 'RRULE', 'RECURRENCE-ID', 'EXDATE', 'RDATE']
    result = {}
    for name in names:
        value = item.get(name)
        if name in ('DTSTART', 'DTEND', 'RECURRENCE-ID') and value is not None:
            decoded = item.decoded(name)
            result[name] = moment(decoded).isoformat() if isinstance(decoded, datetime) else decoded.isoformat()
        elif value is not None and not (name in ('LOCATION', 'DESCRIPTION') and not str(value)):
            values = value if isinstance(value, list) else [value]
            result[name] = sorted(v.to_ical().decode() for v in values)
    result['alarms'] = sorted((str(a.get('ACTION', 'DISPLAY')), a.get('TRIGGER').to_ical().decode()) for a in item.walk('VALARM') if a.get('TRIGGER'))
    return result


def execute(operation, bridge, default_calendar):
    if operation.kind == 'list_calendars':
        try:
            values = json.loads(bridge(['calendars-json']))
            return {'calendars': [{'calendar_id': c['ID'], 'name': c['Name'], 'default': c['ID'] == default_calendar} for c in values]}
        except Exception as exc:
            raise OperationError('Calendar list could not be read') from exc
    calendar_id = operation.calendar_id or default_calendar
    if not calendar_id:
        raise OperationError('Select a calendar ID before reading or writing')
    data = snapshot(bridge, calendar_id, operation.uid)
    cal = calendar_from_snapshot(data)
    rev = revision(cal)
    items = cal.walk('VEVENT')
    if operation.kind == 'list_events':
        results = occurrences(cal, operation.start, operation.end)
        results = [i for i in results if operation.query.casefold() in '\n'.join(str(i.get(k, '')) for k in ('SUMMARY', 'LOCATION', 'DESCRIPTION')).casefold()]
        results.sort(key=lambda i: (moment(i.decoded('DTSTART')), str(i['UID'])))
        views = [event_view(i, calendar_id, '') for i in results[operation.offset:operation.offset + operation.limit]]
        return {'events': views, 'next_offset': operation.offset + len(views) if operation.offset + len(views) < len(results) else None,
                'unreadable_count': data['unreadable_count'], 'message': 'Read getCalendarEvent before editing; listings do not carry a mutation revision.'}
    if data['unreadable_count']:
        raise OperationError('This event could not be decrypted; no mutation was attempted')
    if not items:
        raise OperationError('Event not found in the selected calendar')
    if operation.kind == 'get_event':
        return {'events': [event_view(i, calendar_id, rev) for i in items], 'revision': rev,
                'unverified_signature': any(r['unverified'] for r in data['events'])}
    if any(r['unverified'] for r in data['events']):
        raise OperationError('Event signature could not be verified; inspect it in Proton before changing it')
    if operation.expected_revision != rev:
        raise OperationError('Event changed since it was read. Read it again before editing or deleting')
    if any(i.get('ATTENDEE') for i in items):
        raise OperationError('Attendee events are read-only in this version; invitations are not enabled')
    master = next((i for i in items if not i.get('RECURRENCE-ID')), None)
    recurring = master is not None and bool(master.get('RRULE') or master.get('RDATE'))
    if recurring and operation.scope == 'event':
        raise OperationError('Choose series or occurrence for a recurring event')
    if not recurring and operation.scope != 'event':
        raise OperationError('This is an individual event, not a recurring series')
    if operation.scope == 'series' and operation.kind == 'update_event' and len(items) > 1 and any(k in operation.changes for k in ('start', 'end', 'recurrence')):
        raise OperationError('Rescheduling a series with existing exceptions requires manual review in Proton')
    original_master_signature = verification_signature(master) if master is not None else None
    expected = None
    if operation.scope == 'occurrence':
        target = selected_occurrence(cal, operation.recurrence_id)
        for key in ('RRULE', 'RDATE', 'EXDATE'):
            if key in target:
                del target[key]
        if operation.kind == 'delete_event':
            # Cancel this instance as an exception; do not delete the master UID.
            if 'STATUS' in target:
                del target['STATUS']
            target.add('status', 'CANCELLED')
        else:
            if 'recurrence' in operation.changes:
                raise OperationError('An occurrence cannot change the series recurrence')
            target = update_component(target, operation.changes)
        # Carbonate increments existing rows, but a new exception has no row
        # yet. Its sequence must advance beyond the parent, as Proton's client
        # does when changing an occurrence's schedule.
        sequence = max(int(master.get('SEQUENCE', 0)), int(target.get('SEQUENCE', 0))) + 1
        if 'SEQUENCE' in target:
            del target['SEQUENCE']
        target.add('sequence', sequence)
        if not target.get('RECURRENCE-ID'):
            target.add('recurrence-id', target.decoded('DTSTART'))
        write_cal = Calendar()
        write_cal.add('version', '2.0')
        write_cal.add('prodid', '-//Private Proton Calendar//EN')
        write_cal.add_component(target)
        expected = target
    elif operation.kind == 'update_event':
        target = master or items[0]
        update_component(target, operation.changes)
        if operation.scope == 'series':
            shared_changes = {k:v for k,v in operation.changes.items() if k in ('title', 'location', 'description', 'reminders_minutes')}
            for item in items:
                if item is not target and shared_changes:
                    update_component(item, shared_changes)
        write_cal = cal
        expected = target
    if operation.kind == 'update_event' or operation.scope == 'occurrence':
        # Carbonate identifies an exception only from a UTC or date-only
        # RECURRENCE-ID. A TZID value would otherwise select the master UID.
        for item in write_cal.walk('VEVENT'):
            rid = item.decoded('RECURRENCE-ID', None)
            if isinstance(rid, datetime):
                del item['RECURRENCE-ID']
                item.add('recurrence-id', rid.astimezone(timezone.utc))
    expected_items = [expected] if operation.scope == 'occurrence' else (write_cal.walk('VEVENT') if operation.kind == 'update_event' else [])
    try:
        if operation.kind == 'delete_event' and operation.scope != 'occurrence':
            bridge(['event', 'delete', '-calendar', calendar_id, '-uid', operation.uid])
        else:
            bridge(['event', 'put', '-calendar', calendar_id], write_cal.to_ical())
        after = snapshot(bridge, calendar_id, operation.uid)
        if after['unreadable_count']:
            raise ValueError('Unreadable verification')
        remaining = calendar_from_snapshot(after).walk('VEVENT')
        if operation.kind == 'delete_event' and operation.scope != 'occurrence':
            verified = not remaining
        else:
            rid = expected.decoded('RECURRENCE-ID', None)
            actual = next((i for i in remaining if i.decoded('RECURRENCE-ID', None) == rid), None)
            verified = all(any(i.decoded('RECURRENCE-ID', None) == expected_item.decoded('RECURRENCE-ID', None) and verification_signature(i) == verification_signature(expected_item) for i in remaining) for expected_item in expected_items)
            if operation.scope == 'occurrence':
                saved_master = next((i for i in remaining if not i.get('RECURRENCE-ID')), None)
                verified = verified and saved_master is not None and verification_signature(saved_master) == original_master_signature
            if operation.kind == 'delete_event':
                verified = verified and str(actual.get('STATUS', '')) == 'CANCELLED'
        if not verified:
            raise ValueError('Verification mismatch')
    except Exception as exc:
        diagnostic = getattr(exc, 'safe_diagnostic', '')
        # Bridge diagnostics consist solely of fixed labels or a numeric code.
        if diagnostic and not (diagnostic in ('bridge command failed', 'bridge unavailable or timed out') or re.fullmatch(r'Proton rejected the write, code [0-9]{3,6}', diagnostic)):
            diagnostic = ''
        if not diagnostic and isinstance(exc, ValueError) and str(exc) in ('Verification mismatch', 'Unreadable verification'):
            diagnostic = str(exc)
        suffix = f' ({diagnostic})' if diagnostic else ''
        raise MutationUncertain('Mutation could not be verified' + suffix + '. Check Proton before attempting another mutation.') from exc
    return {'verified': True, 'calendar_id': calendar_id, 'uid': operation.uid, 'scope': operation.scope, 'operation': operation.kind}
