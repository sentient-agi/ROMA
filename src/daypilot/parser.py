from __future__ import annotations
import re
from datetime import datetime
import dateparser
from dateutil.tz import gettz
from .models import DayPlan, Task

WEEKDAY_MAP = {
    'mon':'MO','monday':'MO','tue':'TU','tuesday':'TU','wed':'WE','wednesday':'WE',
    'thu':'TH','thursday':'TH','fri':'FR','friday':'FR','sat':'SA','saturday':'SA','sun':'SU','sunday':'SU'
}

def _minutes(text: str, default: int) -> int:
    m = re.search(r'(\d+)\s*(min|mins|minutes|m)\b', text, re.I)
    if m: return int(m.group(1))
    m = re.search(r'(\d+)\s*(h|hr|hrs|hour|hours)\b', text, re.I)
    if m: return int(m.group(1)) * 60
    return default

def _extract_rrule(text: str) -> str | None:
    t = text.lower()
    if re.search(r'\b(every\s+day|daily)\b', t): return "FREQ=DAILY"
    if re.search(r'\bevery\s+(weekday|weekdays)\b', t): return "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    if re.search(r'\bevery\s+weekend\b', t): return "FREQ=WEEKLY;BYDAY=SA,SU"
    days = re.findall(r'\b(mon|tue|wed|thu|fri|sat|sun)(?:day)?\b', t, re.I)
    if days and "every" in t:
        byday = ",".join(sorted({WEEKDAY_MAP[d.lower()] for d in days}))
        return f"FREQ=WEEKLY;BYDAY={byday}"
    m = re.search(r'\b(first|second|third|fourth)\s+(mon|tue|wed|thu|fri|sat|sun)\b.*\b(month|monthly)\b', t)
    if m:
        pos = {"first":1,"second":2,"third":3,"fourth":4}[m.group(1).lower()]
        byday = WEEKDAY_MAP[m.group(2).lower()]
        return f"FREQ=MONTHLY;BYDAY={byday};BYSETPOS={pos}"
    return None

def _parse_time(text: str) -> datetime | None:
    return dateparser.parse(text, settings={"PREFER_DATES_FROM":"future","RETURN_AS_TIMEZONE_AWARE":True}, languages=["en"])

def parse_narration(narration: str, tz_name: str = "Africa/Lagos") -> DayPlan:
    chunks = re.split(r'\s*(?:[,;]| and )\s*', narration.strip())
    tasks: list[Task] = []
    default_offset = _minutes(narration, 10)

    for chunk in chunks:
        if not chunk: continue
        duration = _minutes(re.search(r'\bfor\s+([^\b]+)', chunk, re.I).group(0) if re.search(r'\bfor\s+', chunk, re.I) else "", 60)
        m = re.search(r'remind\s+me\s+(\d+\s*(?:m|min|mins|minutes|h|hr|hrs|hour|hours))\s+before', chunk, re.I)
        remind = _minutes(m.group(1), default_offset) if m else default_offset
        rrule_txt = _extract_rrule(chunk)

   
        title = re.split(r'\b(for|remind|at|on|by|around)\b', chunk, flags=re.I)[0].strip().rstrip(",.") or chunk.strip()
      
        p = re.search(r'\b(at|on|by|around)\s+(.+)$', chunk, re.I)
        timestr = p.group(2) if p else chunk
        start_dt = _parse_time(timestr)

        tasks.append(Task(title=title, start=start_dt, duration_minutes=duration, reminder_offset_minutes=remind, rrule=rrule_txt))
    return DayPlan(timezone=tz_name, tasks=tasks)
