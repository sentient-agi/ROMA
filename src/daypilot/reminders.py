from __future__ import annotations
from datetime import datetime, timedelta, date, time
from dateutil.tz import gettz
from dateutil.rrule import rrulestr
from apscheduler.schedulers.background import BackgroundScheduler

from .storage import get_session, TaskRow
from .messenger import send_telegram
from .calendar_sync import delete_google_event

_scheduler: BackgroundScheduler | None = None


_BALANCED_KEYS = {
    "wake up","light exercise","breakfast","deep work","short break","focus block",
    "lunch","10-minute walk","admin/emails","wrap-up","workout","dinner",
    "plan tomorrow","relax/reading","sleep"
}

def _is_balanced_title(title: str | None) -> bool:
    t = (title or "").lower()
    return any(k in t for k in _BALANCED_KEYS)

def scheduler() -> BackgroundScheduler:
    """Singleton APScheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.start()
    return _scheduler

def _as_aware(dt_obj: datetime | None, tz) -> datetime | None:
    if dt_obj is None:
        return None
    return dt_obj if dt_obj.tzinfo is not None else dt_obj.replace(tzinfo=tz)

def _next_occurrence(row: TaskRow) -> datetime | None:
    tz = gettz(row.timezone)
    now = datetime.now(tz)
    start = _as_aware(getattr(row, "start", None), tz)
    if row.rrule:
        rule = rrulestr(row.rrule, dtstart=start or now)
        return rule.after(now, inc=True)
    if start and start > now:
        return start
    return None

def _pretty_time(row: TaskRow) -> str:
    dt = _next_occurrence(row)
    return dt.strftime('%a %Y-%m-%d %H:%M') if dt else "(unscheduled)"

def _notify(task_id: int):
    """Send the primary Telegram reminder for a task and schedule a gentle follow-up."""
    s = get_session()
    t = s.query(TaskRow).get(task_id)
    if not t or t.status != "scheduled":
        return
    when = _pretty_time(t)
    send_telegram(t.user_id, f"⏰ *{t.title}*\n({when})")

   
    tz = gettz(t.timezone)
    scheduler().add_job(
        _escalate, "date",
        run_date=datetime.now(tz) + timedelta(minutes=2),
        args=[t.id],
        id=f"escalate-{t.id}", replace_existing=True
    )

def _escalate(task_id: int):
    s = get_session()
    t = s.query(TaskRow).get(task_id)
    if t and t.status == "scheduled":
        send_telegram(t.user_id, f"🔔 Still pending: *{t.title}*")

def schedule_row(row: TaskRow):
    """(Re)schedule a Telegram reminder for a single TaskRow."""
    nxt = _next_occurrence(row)
    if not nxt:
        return
    offset = int(getattr(row, "reminder_offset_minutes", 0) or 0)
    remind_at = nxt - timedelta(minutes=offset)
    if remind_at <= datetime.now(gettz(row.timezone)):
        return
    scheduler().add_job(
        _notify, "date",
        run_date=remind_at,
        args=[row.id],
        id=f"task-{row.id}",
        replace_existing=True
    )

def schedule_all():
    """Schedule reminders for all scheduled tasks (called on bot startup)."""
    s = get_session()
    for t in s.query(TaskRow).filter(TaskRow.status == "scheduled").all():
        schedule_row(t)



def _cleanup_dayplan_today(user_id: int, tz_name: str):
    """
    Cancel today's 'balanced' day-plan tasks (one-time variant) at 23:59
    and remove their Google Calendar events so they don't accumulate.
    """
    s = get_session()
    tz = gettz(tz_name)
    today = datetime.now(tz).date()

    rows = (
        s.query(TaskRow)
        .filter(TaskRow.user_id == user_id, TaskRow.status == "scheduled")
        .all()
    )

    changed = False
    for r in rows:
        if not r.start:
            continue
        start_local = _as_aware(r.start, gettz(r.timezone)).astimezone(tz)
        if start_local.date() != today:
            continue
        if not _is_balanced_title(r.title):
            continue
        # Cancel and clean up from Google
        r.status = "cancelled"
        try:
            delete_google_event(r)
        except Exception:
            pass
        changed = True

    if changed:
        s.commit()
        send_telegram(user_id, "🧹 Cleared today’s one-time day plan.")

def schedule_cleanup_dayplan_today(user_id: int, tz_name: str):
    """
    Public API: schedule a one-time cleanup job at 23:59 *today* in the user's timezone.
    Used when the user chooses 'One-time' for the day plan.
    """
    tz = gettz(tz_name)
    run_at = datetime.combine(date.today(), time(23, 59), tz)
    scheduler().add_job(
        _cleanup_dayplan_today, "date",
        run_date=run_at,
        args=[user_id, tz_name],
        id=f"cleanup-dayplan-{user_id}",
        replace_existing=True
    )
