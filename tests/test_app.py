import json
import sqlite3
import subprocess
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from icalendar import Calendar

import app as module

HEADERS = {"Authorization": "Bearer " + "a" * 40}
PAYLOAD = {"title": "School", "start": "2026-10-07T09:45:00+03:00"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "DATA", tmp_path)
    monkeypatch.setenv("ACTION_API_KEY", "a" * 40)
    monkeypatch.setenv("CARBONATE_BRIDGE_PASSWORD", "test-secret")
    monkeypatch.delenv("ACTION_API_KEY_FILE", raising=False)
    monkeypatch.delenv("CARBONATE_BRIDGE_PASSWORD_FILE", raising=False)
    monkeypatch.setattr(module, "worker", lambda: None)
    (tmp_path / "auth.json").write_text("fake session")
    with TestClient(module.app) as client:
        yield client


def test_auth_and_missing_login(client):
    assert client.get("/context").status_code == 401
    assert client.post("/events", json=PAYLOAD).status_code == 401
    assert client.get("/context", headers=HEADERS).status_code == 200
    (module.DATA / "auth.json").unlink()
    assert client.post("/events", json=PAYLOAD, headers=HEADERS).status_code == 503


def test_offsets_and_idempotence(client):
    result = client.post("/events", json=PAYLOAD, headers=HEADERS).json()
    assert result["state"] == "pending"
    assert result["event"]["start"] == "2026-10-07T06:45:00Z"
    assert result["event"]["end"] == "2026-10-07T07:45:00Z"
    other = dict(PAYLOAD, start="2026-10-07T06:45:00Z", end="2026-10-07T07:45:00Z")
    assert client.post("/events", json=other, headers=HEADERS).json()["job_id"] == result["job_id"]
    with module.db() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


@pytest.mark.parametrize("changes", [
    {"start": "2026-10-07T09:45:00"}, {"end": "2026-10-07T08:00:00+03:00"},
    {"title": "   "}, {"title": "bad\x00title"}, {"attendees": ["someone@example.com"]},
])
def test_invalid_event_never_queued(client, changes):
    assert client.post("/events", json=dict(PAYLOAD, **changes), headers=HEADERS).status_code == 422


def test_ics_text_cannot_inject_properties():
    event = module.EventRequest(**dict(PAYLOAD, title="School\nATTENDEE:someone@example.com; test, \\"))
    item = Calendar.from_ical(module.make_ics(event, "test")).walk("VEVENT")[0]
    assert str(item["SUMMARY"]) == event.title
    assert "ATTENDEE" not in item


def test_readback_requires_matching_values():
    event = module.EventRequest(**PAYLOAD)
    raw = module.make_ics(event, "test").decode()
    output = "\n".join("    | " + line for line in raw.split("\r\n"))
    assert module.verified_in_output(output, event, "test")
    assert not module.verified_in_output(output.replace("SUMMARY:School", "SUMMARY:Wrong"), event, "test")
    assert not module.verified_in_output(output, event, "other")


def row_for(client):
    job_id = client.post("/events", json=PAYLOAD, headers=HEADERS).json()["job_id"]
    with module.db() as conn:
        return conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()


def test_success_only_after_readback(client, monkeypatch):
    row = row_for(client)
    calls = []
    monkeypatch.setattr(module, "CALENDAR_ID", "test-calendar")
    def bridge(args, content=None):
        calls.append(args)
        if content:
            bridge.content = content
            return "Created event upstream-id\n"
        return json.dumps({"calendar_id":"test-calendar", "events":[{"ics":bridge.content.decode(),"unverified":False}],"unreadable_count":0})
    monkeypatch.setattr(module, "run_bridge", bridge)
    module.process_job(row)
    assert module.get_status(row["id"])["state"] == "verified"
    assert calls[1] == ["events-json", "-calendar", "test-calendar", "-uid", row["id"] + "@private-proton-gpt"]


def test_uncertain_write_not_retried(client, monkeypatch):
    row = row_for(client)
    calls = []
    monkeypatch.setattr(module, "CALENDAR_ID", "test-calendar")
    def fail(args, content=None):
        calls.append(args)
        raise module.BridgeError("Simulate write succeeded but reply timed out")
    monkeypatch.setattr(module, "run_bridge", fail)
    module.process_job(row)
    assert module.get_status(row["id"])["state"] == "unknown"
    retry = client.post("/events", json=PAYLOAD, headers=HEADERS).json()
    assert retry["state"] == "unknown"
    assert len(calls) == 1


def test_queue_limit(client):
    for i in range(20):
        assert client.post("/events", json=dict(PAYLOAD, title=f"Event {i}"), headers=HEADERS).status_code == 202
    assert client.post("/events", json=PAYLOAD, headers=HEADERS).status_code == 429


def test_bridge_no_shell_and_no_error_leak(monkeypatch):
    def run(args, **kwargs):
        assert isinstance(args, list)
        assert "shell" not in kwargs
        assert kwargs["env"]["CARBONATE_NO_INVITATIONS"] == "1"
        return subprocess.CompletedProcess(args, 1, b"", b"secret token")
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(module.BridgeError) as exc:
        module.run_bridge(["event", "put"], b"data")
    assert "secret" not in str(exc.value)


def test_openapi_has_bearer_and_write_annotation(client):
    spec = client.get("/openapi.json").json()
    post = spec["paths"]["/events"]["post"]
    assert post["security"] == [{"HTTPBearer": []}]
    assert post["x-openai-isConsequential"] is False


def test_restart_marks_interrupted_write_unknown(client):
    row = row_for(client)
    module.update_job(row["id"], "writing")
    with TestClient(module.app) as restarted:
        result = restarted.get(f'/events/{row["id"]}', headers=HEADERS).json()
        assert result["state"] == "unknown"
        assert "restarted" in result["error"]


def test_unicode_folding_and_winter_offset():
    event = module.EventRequest(title="Koulu äöü ☃ " * 12, start="2026-12-07T09:45:00+02:00")
    assert event.start.hour == 7
    raw = module.make_ics(event, "test").decode()
    output = "\n".join("    | " + line for line in raw.split("\r\n"))
    assert module.verified_in_output(output, event, "test")
