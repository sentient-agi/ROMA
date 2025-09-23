from __future__ import annotations
import os, json
from datetime import datetime
import dateparser
from dateutil.tz import gettz
from litellm import completion
from .models import DayPlan, Task

MODEL = os.getenv("DAYPILOT_LLM_MODEL", "openrouter/anthropic/claude-sonnet-4")

SYSTEM = """You are a scheduling parser.
Output ONLY JSON:
{
  "tasks":[
    {"title":"string","start":"YYYY-MM-DDTHH:MM","duration_minutes":60,"reminder_offset_minutes":10,"rrule":null,"notes":null}
  ]
}
Resolve relative times using NOW and TIMEZONE. Default duration 60, reminder 10. Include RRULE for recurrences. No prose, JSON only.
"""

def _extract_json(text: str) -> str:
    s = text.find("{"); e = text.rfind("}")
    if s == -1 or e == -1 or e <= s: raise ValueError("No JSON object")
    return text[s:e+1]

def llm_parse(narration: str, tz_name: str) -> DayPlan:
    now = datetime.now(gettz(tz_name)).strftime("%Y-%m-%d %H:%M")
    user_msg = f"NOW: {now}\nTIMEZONE: {tz_name}\nNARRATION: {narration}"
    resp = completion(
        model=MODEL,
        messages=[{"role":"system","content":SYSTEM},{"role":"user","content":user_msg}],
        temperature=0.2, max_tokens=1200,
    )
    text = resp["choices"][0]["message"]["content"]
    data = json.loads(_extract_json(text))
    tasks = []
    for item in data.get("tasks", []):
        start = dateparser.parse(item.get("start") or "", settings={"RETURN_AS_TIMEZONE_AWARE":True})
        tasks.append(Task(
            title=item.get("title") or "Task",
            start=start,
            duration_minutes=item.get("duration_minutes"),
            reminder_offset_minutes=item.get("reminder_offset_minutes", 10),
            rrule=item.get("rrule"),
            notes=item.get("notes"),
        ))
    return DayPlan(timezone=tz_name, tasks=tasks)
