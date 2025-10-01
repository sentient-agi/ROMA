from __future__ import annotations
import os, json
from datetime import timedelta
from typing import Optional, Tuple

from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import declarative_base

from .storage import get_session, TaskRow


FERNET = Fernet(os.getenv("FERNET_SECRET").encode())
Base = declarative_base()

class GoogleAuth(Base):
    __tablename__ = "google_auth"
    user_id = Column(Integer, primary_key=True)
    email = Column(String(255))
    token_encrypted = Column(Text, nullable=False)

def _ensure_table():
    s = get_session()
    Base.metadata.create_all(bind=s.get_bind())

def _load_creds(user_id: int) -> Optional[Credentials]:
    _ensure_table()
    s = get_session()
    row = s.get(GoogleAuth, user_id)
    if not row:
        return None
    try:
        info = json.loads(FERNET.decrypt(row.token_encrypted.encode()).decode())
        return Credentials.from_authorized_user_info(info)
    except Exception:
        return None

# public helper

def is_google_connected(user_id: int) -> bool:
    """True if we have stored OAuth credentials for this user."""
    _ensure_table()
    s = get_session()
    return s.get(GoogleAuth, user_id) is not None

def revoke_tokens_for_user(user_id: int) -> bool:
    """Delete stored Google tokens for this user. Returns True if removed."""
    _ensure_table()
    s = get_session()
    row = s.get(GoogleAuth, user_id)
    if not row:
        return False
    try:
        s.delete(row)
        s.commit()
        return True
    except Exception:
        s.rollback()
        return False


#calendar processes
def _duration_minutes(row: TaskRow) -> int:
    return getattr(row, "duration_minutes", None) or 60

def upsert_google_event(row: TaskRow, tz: str, calendar_id: str = "primary") -> Tuple[bool, Optional[str]]:
    """Create or update a Google event for this TaskRow. Returns (ok, htmlLink or None)."""
    creds = _load_creds(row.user_id)
    if not creds:
        return False, None

    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    if not row.start:
        return False, None

    start_dt = row.start
    end_dt = start_dt + timedelta(minutes=_duration_minutes(row))

    body = {
        "summary": row.title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": tz},
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": tz},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": int(row.reminder_offset_minutes or 0)}],
        },
    }
    if row.rrule:
        body["recurrence"] = [row.rrule]

    s = get_session()
    if getattr(row, "google_event_id", None):
        ev = service.events().update(calendarId=calendar_id, eventId=row.google_event_id, body=body).execute()
    else:
        ev = service.events().insert(calendarId=calendar_id, body=body).execute()
        try:
            row.google_event_id = ev["id"]
            s.add(row)
            s.commit()
        except Exception:
            s.rollback()

    return True, ev.get("htmlLink")

def delete_google_event(row: TaskRow, calendar_id: str = "primary") -> bool:
    creds = _load_creds(row.user_id)
    if not creds or not getattr(row, "google_event_id", None):
        return False
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    try:
        service.events().delete(calendarId=calendar_id, eventId=row.google_event_id).execute()
        return True
    except Exception:
        return False

def sync_all_tasks_for_user(user_id: int, tz: str, calendar_id: str = "primary") -> Tuple[int, int]:
    """Upsert all scheduled tasks for a user. Returns (synced, skipped)."""
    s = get_session()
    items = (
        s.query(TaskRow)
        .filter(TaskRow.user_id == user_id, TaskRow.status == "scheduled")
        .all()
    )
    ok = 0
    skipped = 0
    for row in items:
        done, _ = upsert_google_event(row, tz, calendar_id=calendar_id)
        if done:
            ok += 1
        else:
            skipped += 1
    return ok, skipped
