from __future__ import annotations
import os, json, re
from typing import Tuple, Dict, Any
from openai import OpenAI
from .agent import plan_and_schedule
from .storage import get_session, TaskRow

FIREWORKS_BASE = "https://api.fireworks.ai/inference/v1"

def dobby_enabled() -> bool:
    if os.getenv("USE_DOBBY_ROUTER", "1").lower() in ("0","false","no"):
        return False
    return bool(os.getenv("FIREWORKS_API_KEY"))

_client: OpenAI | None = None
def _client_or_none() -> OpenAI | None:
    global _client
    if _client is None and dobby_enabled():
        _client = OpenAI(base_url=FIREWORKS_BASE, api_key=os.getenv("FIREWORKS_API_KEY"))
    return _client

DOBBY_MODEL = os.getenv(
    "DOBBY_MODEL",
    "accounts/fireworks/models/sentientfoundation/dobby-unhinged-llama-3-3-70b-new",
)

SYSTEM = (
    "You are DayPilot’s assistant brain inside a Telegram bot.\n"
    "If the user asks to plan/schedule/list/delete/reschedule/snooze/ "
    "timezone/connect/sync/export/help/language/menu, use TOOLS and then reply naturally.\n"
    "Never print raw tool JSON; wait for results and speak plainly."
)

TOOLS = [
    {"type":"function","function":{
        "name":"plan_schedule","description":"Create a plan from natural language",
        "parameters":{"type":"object","properties":{
            "narration":{"type":"string"},"timezone":{"type":"string"},
            "telegram_user_id":{"type":"integer"}},
            "required":["narration","timezone","telegram_user_id"],"additionalProperties":False}}},
    {"type":"function","function":{
        "name":"list_tasks","description":"List tasks for the user",
        "parameters":{"type":"object","properties":{
            "telegram_user_id":{"type":"integer"}},
            "required":["telegram_user_id"],"additionalProperties":False}}},
    {"type":"function","function":{
        "name":"delete_task","description":"Delete a task by id",
        "parameters":{"type":"object","properties":{
            "telegram_user_id":{"type":"integer"},"task_id":{"type":"integer"}},
            "required":["telegram_user_id","task_id"],"additionalProperties":False}}},
    {"type":"function","function":{
        "name":"set_timezone","description":"Set timezone string",
        "parameters":{"type":"object","properties":{
            "timezone":{"type":"string"}},
            "required":["timezone"],"additionalProperties":False}}},
    {"type":"function","function":{
        "name":"connect_calendar","description":"Return a connect URL",
        "parameters":{"type":"object","properties":{
            "telegram_user_id":{"type":"integer"}},
            "required":["telegram_user_id"],"additionalProperties":False}}},
    {"type":"function","function":{
        "name":"sync_calendar","description":"Sync tasks to Google Calendar",
        "parameters":{"type":"object","properties":{
            "telegram_user_id":{"type":"integer"},"timezone":{"type":"string"}},
            "required":["telegram_user_id","timezone"],"additionalProperties":False}}},
    {"type":"function","function":{
        "name":"export_tasks","description":"Export tasks as CSV or ICS",
        "parameters":{"type":"object","properties":{
            "telegram_user_id":{"type":"integer"},"format":{"type":"string","enum":["csv","ics"]}},
            "required":["telegram_user_id"],"additionalProperties":False}}},
]

_TIME_RE = re.compile(r"\b(\d{1,2}(:\d{2})?\s*(am|pm)?)\b", re.I)
_TOOL_WORDS = (
    "list","show","view","plans","schedule","agenda","delete","remove","timezone",
    "connect","sync","export","menu","language","lang","meeting","appointment",
    "remind","alarm","tomorrow","today","tonight","morning","evening","afternoon",
    "weekday","weekdays","every ","daily","weekly","monthly","monday","tuesday",
    "wednesday","thursday","friday","saturday","sunday",
)

def _wants_tools(text: str) -> bool:
    t = text.lower()
    return bool(_TIME_RE.search(t) or any(w in t for w in _TOOL_WORDS))

def _looks_like_tool_json(text: str) -> bool:
    if not text: return False
    t = text.strip()
    return ('"type": "function"' in t) or ('"parameters"' in t and t.startswith("{"))

def _exec_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "plan_schedule":
        out = plan_and_schedule(
            narration=args.get("narration",""),
            timezone=args.get("timezone","Africa/Lagos"),
            telegram_user_id=args["telegram_user_id"],
        )
        return {"ok":True,"kind":"plan_schedule","pretty":out.pretty_plan,"scheduled_jobs":out.scheduled_jobs}

    if name == "list_tasks":
        s = get_session()
        items = s.query(TaskRow).filter(
            TaskRow.user_id==args["telegram_user_id"],
            TaskRow.status=="scheduled"
        ).all()
        return {"ok":True,"kind":"list_tasks","items":[{
            "id":t.id,"title":t.title,"start":t.start.isoformat() if t.start else None,
            "rrule":t.rrule,"reminder":t.reminder_offset_minutes
        } for t in items]}

    if name == "delete_task":
        s = get_session()
        t = s.query(TaskRow).get(args["task_id"])
        if t and t.user_id==args["telegram_user_id"]:
            t.status="cancelled"; s.commit()
            return {"ok":True,"kind":"delete_task","deleted_id":t.id,"title":t.title}
        return {"ok":False,"kind":"delete_task","error":"not_found_or_not_owner"}

    if name == "set_timezone":
        return {"ok":True,"kind":"set_timezone","tz":args["timezone"]}

    if name == "connect_calendar":
        base = os.getenv("OAUTH_BASE_URL","http://localhost:8000")
        url = f"{base}/connect?uid={args['telegram_user_id']}"
        return {"ok":True,"kind":"connect_calendar","url":url}

    if name == "sync_calendar":
        # The bot will actually call /sync; here we just confirm intent.
        return {"ok":True,"kind":"sync_calendar","note":"tell user to run /sync"}

    if name == "export_tasks":
        fmt = args.get("format","csv")
        return {"ok":True,"kind":"export_tasks","format":fmt}

    return {"ok":False,"error":f"unknown_tool:{name}"}

def dobby_route(user_text: str, tz: str, telegram_user_id: int) -> Tuple[bool, str]:
    cli = _client_or_none()
    if not cli:
        return False, ""

    messages = [
        {"role":"system","content":SYSTEM},
        {"role":"user","content":f"TZ={tz}\nUSER_ID={telegram_user_id}\nMESSAGE:\n{user_text}"},
    ]
    try:
        for _ in range(3):
            resp = cli.chat.completions.create(
                model=DOBBY_MODEL, messages=messages, tools=TOOLS,
                tool_choice="auto", temperature=0.3
            )
            msg = resp.choices[0].message

            if getattr(msg,"tool_calls",None) and not _wants_tools(user_text):
                messages.append({"role":"system","content":"User didn't request scheduling tools. Answer conversationally."})
                continue

            tcs = getattr(msg,"tool_calls",None)
            if tcs:
                last_reply = ""
                for tc in tcs:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        args = {}
                    if name in ("plan_schedule","list_tasks","delete_task","connect_calendar","sync_calendar","export_tasks"):
                        args = {"telegram_user_id": telegram_user_id, **args}
                    result = _exec_tool(name, args)
                    messages.append({"role":"tool","tool_call_id":tc.id,"name":name,"content":json.dumps(result)})

                    if result.get("kind") == "plan_schedule":
                        return True, "✅ Plan created:\n" + result.get("pretty","Plan created.")
                    if result.get("kind") == "list_tasks":
                        items = result.get("items",[])
                        if not items:
                            last_reply = "You have no scheduled items yet. Try `/examples`."
                        else:
                            lines = ["📅 Your schedule:"]
                            for i,t in enumerate(items,1):
                                when = (t["start"] or "unscheduled").replace("T"," ").split(".")[0]
                                rec = " 🔁" if t.get("rrule") else ""
                                lines.append(f"{i}. {t['title']}{rec} — {when} (remind {t.get('reminder',0)}m) [id:{t['id']}]")
                            last_reply = "\n".join(lines)
                    if result.get("kind") == "connect_calendar":
                        last_reply = f"Use `/connect` or open:\n{result['url']}\nThen run `/sync`."
                    if result.get("kind") == "sync_calendar":
                        last_reply = "Okay. Run `/sync` to push your tasks to Google Calendar."
                    if result.get("kind") == "export_tasks":
                        last_reply = f"To export, run `/export {result.get('format','csv')}`."
                if last_reply:
                    return True, last_reply
                continue

            text = (msg.content or "").strip()
            if _looks_like_tool_json(text):
                return False, ""
            if text:
                return True, text

        return False, ""
    except Exception:
        return False, ""
