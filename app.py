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
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from icalendar import Calendar, Event
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    start: datetime = Field(description="Absolute ISO 8601 date/time with UTC offset.")
    end: datetime | None = Field(default=None, description="End with UTC offset; omit to use the configured default duration.")
    location: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=2000)

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
        if self.start.utcoffset() is None or (self.end and self.end.utcoffset() is None):
            raise ValueError("Dates require an explicit UTC offset")
        self.start = self.start.astimezone(timezone.utc)
        self.end = (self.end or (self.start + timedelta(minutes=DEFAULT_DURATION))).astimezone(timezone.utc)
        if self.end <= self.start or self.end - self.start > timedelta(days=7):
            raise ValueError("End must follow start and duration must not exceed seven days")
        if self.start.microsecond or self.end.microsecond:
            raise ValueError("Use whole seconds")
        return self


def identity(event):
    payload = event.model_dump(mode="json")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest(), raw


def make_ics(event, uid):
    cal = Calendar()
    cal.add("prodid", "-//Private Proton Calendar GPT//EN")
    cal.add("version", "2.0")
    item = Event()
    item.add("uid", uid)
    item.add("dtstamp", datetime.now(timezone.utc))
    item.add("dtstart", event.start)
    item.add("dtend", event.end)
    item.add("summary", event.title)
    if event.location:
        item.add("location", event.location)
    if event.description:
        item.add("description", event.description)
    cal.add_component(item)
    return cal.to_ical()


class BridgeError(Exception):
    pass


class CalendarContext(BaseModel):
    now: str
    timezone: str
    default_duration_minutes: int
    provider: str
    login_configured: bool


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
        raise BridgeError("Bridge unavailable or timed out") from exc
    if result.returncode:
        # Never send upstream errors, tokens, or account data to the API client.
        raise BridgeError("Bridge command failed; check login and calendar configuration")
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


def process_job(row):
    event = EventRequest.model_validate_json(row["payload"])
    uid = row["id"] + "@private-proton-gpt"
    args = ["event", "put"]
    if CALENDAR_ID:
        args += ["-calendar", CALENDAR_ID]
    try:
        run_bridge(args, make_ics(event, uid))
        output = run_bridge(["calendars", "--ics"])
        if not verified_in_output(output, event, uid):
            raise BridgeError("Write was not verified")
    except Exception:
        update_job(row["id"], "unknown", "Could not verify the write. Check Proton Calendar before trying again; the event may already exist.")
    else:
        update_job(row["id"], "verified")


def worker():
    while not STOP.is_set():
        with db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE state='pending' ORDER BY created LIMIT 1").fetchone()
            if row:
                conn.execute("UPDATE jobs SET state='writing' WHERE id=?", (row["id"],))
        if row:
            process_job(row)
        else:
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
    os.chmod(DATA / "jobs.sqlite", 0o600)
    STOP.clear()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    yield
    STOP.set()
    WAKE.set()
    thread.join(timeout=2)


app = FastAPI(title="Private Proton Calendar", version="0.1.0", lifespan=lifespan,
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
            "provider": "proton", "login_configured": (DATA / "auth.json").exists()}


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
