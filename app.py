"""Private GPT Action adapter for the experimental Carbonate Proton bridge."""
import hashlib
import hmac
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from icalendar import Calendar, Event
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
import calendar_operations as operations

DATA = Path(os.getenv("DATA_DIR", "/data"))
TZ = os.getenv("CALENDAR_TIMEZONE", "Europe/Helsinki")
DEFAULT_DURATION = int(os.getenv("DEFAULT_DURATION_MINUTES", "60"))
CALENDAR_ID = os.getenv("PROTON_CALENDAR_ID", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://calendar.example.com").rstrip("/")
STOP = threading.Event()
WAKE = threading.Event()


def secret(name):
    path = os.getenv(name + "_FILE")
    return Path(path).read_text().strip() if path else os.getenv(name, "")


def db():
    conn = sqlite3.connect(DATA / "jobs.sqlite", timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


class EventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    start: datetime | date = Field(description="Absolute ISO 8601 date/time with UTC offset.")
    end: datetime | date | None = Field(default=None, description="End with UTC offset; omit to use the configured default duration.")
    calendar_id: str | None = Field(default=None, pattern=operations.CALENDAR_PATTERN)
    recurrence: operations.Recurrence | None = None
    recurrence_timezone: str | None = None
    reminders_minutes: list[StrictInt] = Field(default_factory=list, max_length=5)
    location: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=2000)

    @field_validator('start', 'end', mode='before')
    @classmethod
    def distinguish_dates(cls, value):
        if isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return date.fromisoformat(value)
        return value

    @field_validator("title", "location", "description")
    @classmethod
    def clean_text(cls, value):
        if any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("Control characters are not allowed")
        return value.strip()

    @model_validator(mode="after")
    def check_times(self):
        if not self.title:
            raise ValueError("Title must not be blank")
        timed = isinstance(self.start, datetime)
        if self.end is not None and isinstance(self.end, datetime) != timed:
            raise ValueError("Start and end must both be dates or both be date-times")
        if timed:
            if self.start.utcoffset() is None or (self.end and self.end.utcoffset() is None):
                raise ValueError("Dates require an explicit UTC offset")
            self.start = self.start.astimezone(timezone.utc)
            self.end = (self.end or (self.start + timedelta(minutes=DEFAULT_DURATION))).astimezone(timezone.utc)
            if self.start.microsecond or self.end.microsecond:
                raise ValueError("Use whole seconds")
        else:
            self.end = self.end or self.start + timedelta(days=1)
        if self.end <= self.start or self.end - self.start > timedelta(days=7):
            raise ValueError("End must follow start and duration must not exceed seven days")
        if any(type(v) is not int or not 0 <= v <= 10080 for v in self.reminders_minutes):
            raise ValueError("Device reminders must be zero to 10080 minutes before the event")
        self.reminders_minutes = sorted(set(self.reminders_minutes))
        if self.recurrence_timezone:
            try:
                ZoneInfo(self.recurrence_timezone)
            except (KeyError, ValueError, TypeError):
                raise ValueError("Use a valid IANA recurrence timezone")
        if self.recurrence:
            if timed and not self.recurrence_timezone:
                raise ValueError("Recurring timed events require an IANA recurrence timezone")
            if self.recurrence.until:
                if not timed or self.recurrence.until < self.start:
                    raise ValueError("until must follow a timed series start; use count for all-day series")
        return self


def identity(event):
    payload = event.model_dump(mode="json")
    # Keep existing individual-event request identities stable after upgrades.
    for key in ('calendar_id', 'recurrence', 'recurrence_timezone', 'reminders_minutes'):
        if not payload[key]:
            del payload[key]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest(), raw


def make_ics(event, uid):
    cal = Calendar()
    cal.add("prodid", "-//Private Proton Calendar GPT//EN")
    cal.add("version", "2.0")
    item = Event()
    item.add("uid", uid)
    item.add("dtstamp", datetime.now(timezone.utc))
    zone = ZoneInfo(event.recurrence_timezone) if event.recurrence and isinstance(event.start, datetime) else None
    item.add("dtstart", event.start.astimezone(zone) if zone else event.start)
    item.add("dtend", event.end.astimezone(zone) if zone else event.end)
    if event.recurrence:
        item.add("rrule", operations.rule_value(event.recurrence))
    operations.reminders(item, event.reminders_minutes)
    item.add("summary", event.title)
    if event.location:
        item.add("location", event.location)
    if event.description:
        item.add("description", event.description)
    cal.add_component(item)
    return cal.to_ical()


class BridgeError(Exception):
    def __init__(self, message, safe_diagnostic=''):
        super().__init__(message)
        self.safe_diagnostic = safe_diagnostic


class CalendarContext(BaseModel):
    now: str
    timezone: str
    default_duration_minutes: int
    provider: str
    login_configured: bool
    api_version: int = 2
    adapter_version: str = "0.2.3"
    selected_calendar_id: str
    capabilities: list[str]


class EventStatus(BaseModel):
    job_id: str
    state: str = Field(description="pending, writing, verified, or unknown. Only verified confirms a saved event.")
    event: dict
    error: str
    calendar_url: str
    poll_after_seconds: int


def run_bridge(args, content=None):
    env = os.environ.copy()
    env["CARBONATE_BRIDGE_PASSWORD"] = secret("CARBONATE_BRIDGE_PASSWORD")
    env["CARBONATE_NO_INVITATIONS"] = "1"
    try:
        result = subprocess.run(
            ["carbonate", *args, "-session", str(DATA / "auth.json")],
            input=content, capture_output=True, timeout=90, env=env,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise BridgeError("Bridge unavailable or timed out", 'bridge unavailable or timed out') from exc
    if result.returncode:
        # Never send upstream errors, tokens, or account data to the API client.
        # Retain only the numeric code in Carbonate's known rejection format.
        # Never expose the accompanying upstream text, tokens or calendar data.
        match = re.search(rb'Proton rejected (?:the event|the request)[^\r\n]*\(code ([0-9]{3,6})\)', result.stderr)
        diagnostic = 'bridge command failed'
        if match:
            diagnostic = 'Proton rejected the write, code ' + match[1].decode('ascii')
            lowered = result.stderr.lower()
            for category, words in (
                ('signature', (b'signed', b'signature')),
                ('timezone', (b'tzid', b'timezone', b'time zone')),
                ('recurrence', (b'recurr', b'parent')),
                ('duplicate', (b'already exists', b'duplicate')),
                ('sequence', (b'sequence',)),
                ('properties', (b'properties', b'property')),
            ):
                if any(word in lowered for word in words):
                    diagnostic += ', category ' + category
                    break
        raise BridgeError("Bridge command failed; check login and calendar configuration", diagnostic)
    return result.stdout.decode("utf-8", errors="strict")


def verified_in_output(output, event, uid):
    # Carbonate's calendars --ics indents each iCalendar line with '    | '.
    lines = [line[6:] for line in output.splitlines() if line.startswith("    | ")]
    text = "\r\n".join(lines) + "\r\n"
    # Each event is a separate VCALENDAR; parse independently.
    blocks = re.findall(r"BEGIN:VCALENDAR\r\n.*?END:VCALENDAR", text, re.S)
    for block in blocks:
        for item in Calendar.from_ical(block).walk("VEVENT"):
            if str(item.get("UID", "")) != uid:
                continue
            return (
                str(item.get("SUMMARY", "")) == event.title
                and item.decoded("DTSTART") == event.start
                and item.decoded("DTEND") == event.end
                and str(item.get("LOCATION", "")) == event.location
                and str(item.get("DESCRIPTION", "")) == event.description
            )
    return False


def update_job(job_id, state, error=""):
    with db() as conn:
        conn.execute("UPDATE jobs SET state=?, error=? WHERE id=?", (state, error, job_id))


def creation_calendar(event):
    selected = event.calendar_id or CALENDAR_ID
    if not selected:
        calendars = json.loads(run_bridge(['calendars-json']))
        if len(calendars) != 1:
            raise operations.OperationError('Select a calendar ID; this account has multiple calendars')
        selected = calendars[0]['ID']
    return selected


def verify_creation(event, uid, selected):
    data = operations.snapshot(run_bridge, selected, uid)
    expected = Calendar.from_ical(make_ics(event, uid)).walk('VEVENT')[0]
    items = operations.calendar_from_snapshot(data).walk('VEVENT')
    return not data['unreadable_count'] and any(
        not i.get('RECURRENCE-ID') and operations.verification_signature(i) == operations.verification_signature(expected)
        for i in items
    )


def process_job(row):
    event = EventRequest.model_validate_json(row['payload'])
    uid = row['id'] + '@private-proton-gpt'
    try:
        selected = creation_calendar(event)
        run_bridge(['event', 'put', '-calendar', selected], make_ics(event, uid))
        if not verify_creation(event, uid, selected):
            raise BridgeError('Write was not verified')
    except Exception:
        update_job(row['id'], 'unknown', 'Could not verify the write. Check Proton Calendar before trying again; the event may already exist.')
    else:
        update_job(row['id'], 'verified')


def process_operation(row):
    payload = json.loads(row['payload'])
    try:
        if payload.get('kind') == 'verify_creation':
            with db() as conn:
                job = conn.execute('SELECT * FROM jobs WHERE id=?', (payload['job_id'],)).fetchone()
            event = EventRequest.model_validate_json(job['payload'])
            verified = verify_creation(event, job['id'] + '@private-proton-gpt', creation_calendar(event))
            if verified:
                update_job(job['id'], 'verified')
            result = {'verified': verified, 'job_id': job['id'], 'message': 'Read-only reconciliation; no event was written or retried.'}
        else:
            result = operations.execute(operations.CalendarOperation.model_validate(payload), run_bridge, CALENDAR_ID)
        state, error = 'ready', ''
    except operations.MutationUncertain as exc:
        result, state, error = {}, 'unknown', str(exc)
    except operations.OperationError as exc:
        result, state, error = {}, 'failed', str(exc)
    except Exception:
        result, state, error = {}, 'failed', 'Calendar operation failed before a verified result was available. Check the NAS configuration.'
    with db() as conn:
        conn.execute('UPDATE operations SET state=?, result=?, error=? WHERE id=?', (state, json.dumps(result), error, row['id']))


def worker():
    while not STOP.is_set():
        with db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE state='pending' ORDER BY created LIMIT 1").fetchone()
            if row:
                conn.execute("UPDATE jobs SET state='writing' WHERE id=?", (row["id"],))
        if row:
            process_job(row)
        else:
            with db() as conn:
                operation = conn.execute("SELECT * FROM operations WHERE state='pending' ORDER BY created LIMIT 1").fetchone()
                if operation:
                    conn.execute("UPDATE operations SET state='running' WHERE id=?", (operation['id'],))
            if operation:
                process_operation(operation)
                continue
            WAKE.wait(1)
            WAKE.clear()


@asynccontextmanager
async def lifespan(app):
    if len(secret("ACTION_API_KEY")) < 32:
        raise RuntimeError("Set ACTION_API_KEY_FILE to a secret containing at least 32 characters")
    if not secret("CARBONATE_BRIDGE_PASSWORD"):
        raise RuntimeError("Configure CARBONATE_BRIDGE_PASSWORD_FILE after Proton login")
    ZoneInfo(TZ)
    if not 1 <= DEFAULT_DURATION <= 10080:
        raise RuntimeError("Invalid default duration")
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', created REAL NOT NULL)")
        conn.execute("UPDATE jobs SET state='unknown', error='Server restarted during the write. Check Proton Calendar; no automatic retry was made.' WHERE state='writing'")
        conn.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '', created REAL NOT NULL)")
        conn.execute("UPDATE operations SET state='unknown', error='Server restarted during an operation. Read Proton before retrying; no mutation was retried.' WHERE state='running'")
    os.chmod(DATA / "jobs.sqlite", 0o600)
    STOP.clear()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    yield
    STOP.set()
    WAKE.set()
    thread.join(timeout=2)


app = FastAPI(title="Private Proton Calendar", version="0.2.3", lifespan=lifespan,
              servers=[{"url": PUBLIC_URL}], docs_url=None, redoc_url=None)
bearer = HTTPBearer(auto_error=False)


def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    key = secret("ACTION_API_KEY")
    if not key or not credentials or not hmac.compare_digest(credentials.credentials.encode(), key.encode()):
        raise HTTPException(401, "Invalid API key", headers={"WWW-Authenticate": "Bearer"})


@app.get("/healthz", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.get("/context", dependencies=[Depends(authorize)], operation_id="getCalendarContext", response_model=CalendarContext)
def context():
    """Get current local date, timezone and default event duration."""
    return {"now": datetime.now(ZoneInfo(TZ)).isoformat(), "timezone": TZ,
            "default_duration_minutes": DEFAULT_DURATION,
            "provider": "proton", "login_configured": (DATA / "auth.json").exists(),
            "api_version": 2, "selected_calendar_id": CALENDAR_ID,
            "capabilities": ['read', 'search', 'create', 'update', 'delete', 'recurrence', 'device_reminders']}


@app.post("/events", status_code=202, dependencies=[Depends(authorize)],
          operation_id="createCalendarEvent", response_model=EventStatus, openapi_extra={"x-openai-isConsequential": False})
def create_event(event: EventRequest):
    """Queue one event. Poll getEventStatus; only verified means saved. Identical requests reuse the same job."""
    if not (DATA / "auth.json").exists():
        raise HTTPException(503, "Proton login is required on the server")
    job_id, payload = identity(event)
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not existing:
            count = conn.execute("SELECT count(*) FROM jobs WHERE state IN ('pending','writing')").fetchone()[0]
            if count >= 20:
                raise HTTPException(429, "Queue is full; try later")
            conn.execute("INSERT OR IGNORE INTO jobs(id,payload,state,created) VALUES(?,?,'pending',?)", (job_id, payload, time.time()))
    WAKE.set()
    return get_status(job_id)


@app.get("/events/{job_id}", dependencies=[Depends(authorize)], operation_id="getEventStatus", response_model=EventStatus)
def get_status(job_id: str):
    """Get event status. pending/writing are unfinished; unknown requires checking Proton; verified confirms read-back."""
    with db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Unknown job")
    return {"job_id": row["id"], "state": row["state"], "event": json.loads(row["payload"]),
            "error": row["error"], "calendar_url": "https://calendar.proton.me",
            "poll_after_seconds": 3 if row["state"] in ("pending", "writing") else 0}


class OperationStatus(BaseModel):
    operation_id: str
    state: str
    result: dict
    error: str
    poll_after_seconds: int


def queue_operation(payload, mutation=False):
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    operation_id = hashlib.sha256(raw.encode()).hexdigest() if mutation else uuid.uuid4().hex
    with db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute('SELECT id FROM operations WHERE id=?', (operation_id,)).fetchone():
            count = conn.execute("SELECT count(*) FROM operations WHERE state IN ('pending','running')").fetchone()[0]
            if count >= 20:
                raise HTTPException(429, 'Calendar operation queue is full')
            conn.execute("INSERT INTO operations(id,payload,state,created) VALUES(?,?,'pending',?)", (operation_id, raw, time.time()))
    WAKE.set()
    return operation_status(operation_id)


@app.post('/operations', status_code=202, dependencies=[Depends(authorize)], response_model=OperationStatus)
def start_operation(operation: operations.CalendarOperation):
    if not (DATA / 'auth.json').exists():
        raise HTTPException(503, 'Proton login is required on the server')
    return queue_operation(operation.model_dump(mode='json'), operation.kind in ('update_event', 'delete_event'))


@app.get('/operations/{operation_id}', dependencies=[Depends(authorize)], response_model=OperationStatus)
def operation_status(operation_id: str):
    with db() as conn:
        row = conn.execute('SELECT * FROM operations WHERE id=?', (operation_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Unknown calendar operation')
    return {'operation_id': row['id'], 'state': row['state'], 'result': json.loads(row['result']),
            'error': row['error'], 'poll_after_seconds': 3 if row['state'] in ('pending', 'running') else 0}


@app.post('/events/{job_id}/verify', status_code=202, dependencies=[Depends(authorize)], response_model=OperationStatus)
def reconcile_creation(job_id: str):
    get_status(job_id)
    return queue_operation({'kind': 'verify_creation', 'job_id': job_id})
