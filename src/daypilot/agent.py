from __future__ import annotations
import os
from pathlib import Path
from datetime import timedelta
from .models import DayPlan, PlanResult
from .parser import parse_narration
from .llm_parser import llm_parse
from .storage import get_session, TaskRow
from .reminders import schedule_row

USE_LLM = os.getenv("DAYPILOT_USE_LLM", "1").lower() not in ("0","false","no")

def _pretty(created: list[TaskRow]) -> str:
    rows = []
    for i, r in enumerate(created, 1):
        when = r.start.strftime('%a %H:%M') if r.start else "from next recurrence"
        rec = " 🔁" if r.rrule else ""
        rows.append(f"{i}. {r.title}{rec} — {when} (remind {r.reminder_offset_minutes}m before)")
    return "\n".join(rows) if rows else "No tasks parsed."

def to_ics(plan: DayPlan, out_path="dayplan.ics") -> str:
    from uuid import uuid4
    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//DayPilot//EN"]
    for t in plan.tasks:
        if not t.start: continue
        end = t.start + timedelta(minutes=t.duration_minutes or 60)
        fmt = lambda dt: dt.strftime("%Y%m%dT%H%M%S")
        lines += ["BEGIN:VEVENT", f"UID:{uuid4()}",
                  f"DTSTART:{fmt(t.start)}", f"DTEND:{fmt(end)}",
                  f"SUMMARY:{t.title}", "END:VEVENT"]
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return str(Path(out_path).resolve())

def _plan_from_text(narration: str, timezone: str) -> DayPlan:
    if USE_LLM and os.getenv("OPENROUTER_API_KEY"):
        try:
            return llm_parse(narration, timezone)
        except Exception:
            pass
    return parse_narration(narration, tz_name=timezone)

def plan_and_schedule(narration: str, timezone: str="Africa/Lagos", telegram_user_id: int|None=None) -> PlanResult:
    dp: DayPlan = _plan_from_text(narration, timezone)
    dp.user_id = telegram_user_id or 0
    s = get_session()
    created = []
    for t in dp.tasks:
        row = TaskRow(
            user_id=dp.user_id, title=t.title, start=t.start,
            duration_minutes=t.duration_minutes or 60,
            reminder_offset_minutes=t.reminder_offset_minutes,
            ring_call=t.ring_call, timezone=dp.timezone, rrule=t.rrule, notes=t.notes
        )
        s.add(row); s.commit()
        if dp.user_id:
            schedule_row(row)
        created.append(row)
    ics_path = to_ics(dp, "dayplan.ics")
    return PlanResult(pretty_plan=_pretty(created), scheduled_jobs=len(created), ics_path=ics_path)
