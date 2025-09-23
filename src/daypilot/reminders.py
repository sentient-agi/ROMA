from __future__ import annotations
from datetime import datetime, timedelta
from dateutil.tz import gettz
from dateutil.rrule import rrulestr
from apscheduler.schedulers.background import BackgroundScheduler
from .storage import get_session, TaskRow
from .messenger import send_telegram

_scheduler: BackgroundScheduler | None = None

def scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.start()
    return _scheduler

def _next_occurrence(row: TaskRow) -> datetime | None:
    tz = gettz(row.timezone)
    now = datetime.now(tz)
    if row.rrule:
        rule = rrulestr(row.rrule, dtstart=row.start or now)
        nxt = rule.after(now, inc=True)
        return nxt
    if row.start and row.start > now:
        return row.start
    return None

def _pretty_time(row: TaskRow) -> str:
    dt = _next_occurrence(row)
    return dt.strftime('%a %Y-%m-%d %H:%M') if dt else "(unscheduled)"

def _notify(task_id: int):
    s = get_session()
    t = s.query(TaskRow).get(task_id)
    if not t or t.status != "scheduled":
        return
    when = _pretty_time(t)
    send_telegram(t.user_id, f"⏰ *{t.title}*\n({when})")

    # Escalate after 2 minutes if still not marked done
    sch = scheduler()
    tz = gettz(t.timezone)
    sch.add_job(_escalate, "date",
                run_date=datetime.now(tz)+timedelta(minutes=2),
                args=[t.id],
                id=f"escalate-{t.id}", replace_existing=True)

def _escalate(task_id: int):
    s = get_session()
    t = s.query(TaskRow).get(task_id)
    if t and t.status == "scheduled":
        send_telegram(t.user_id, f"🔔 Still pending: *{t.title}*")

def schedule_row(row: TaskRow):
    nxt = _next_occurrence(row)
    if not nxt: return
    remind_at = nxt - timedelta(minutes=row.reminder_offset_minutes)
    if remind_at <= datetime.now(gettz(row.timezone)): return
    scheduler().add_job(_notify, "date", run_date=remind_at, args=[row.id], id=f"task-{row.id}", replace_existing=True)

def schedule_all():
    s = get_session()
    for t in s.query(TaskRow).filter(TaskRow.status=="scheduled").all():
        schedule_row(t)
