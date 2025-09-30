from __future__ import annotations
import os, json, re
from typing import Tuple, Dict, Any
from openai import OpenAI

from .agent import plan_and_schedule
from .storage import get_session, TaskRow

FIREWORKS_BASE = "https://api.fireworks.ai/inference/v1"

def dobby_enabled() -> bool:
    """True if router should run (env flag + API key present)."""
    if os.getenv("USE_DOBBY_ROUTER", "1").lower() in ("0", "false", "no"):
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
    "• If the user asks for planning/scheduling/reminders/listing/deleting/timezone, use TOOLS via function calling.\n"
    "• Otherwise, reply conversationally in 1–3 short paragraphs.\n"
    "• NEVER print tool schemas or raw JSON to the user. If you call tools, return no natural-language text until you see tool results.\n"
)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "plan_schedule",
            "description": "Create a day plan and reminders from natural language",
            "parameters": {
                "type": "object",
                "properties": {
                    "narration": {"type": "string"},
                    "timezone": {"type": "string"},
                    "telegram_user_id": {"type": "integer"},
                },
                "required": ["narration", "timezone", "telegram_user_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List scheduled tasks for the user",
            "parameters": {
                "type": "object",
                "properties": {"telegram_user_id": {"type": "integer"}},
                "required": ["telegram_user_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Delete a task by id (use id from /list)",
            "parameters": {
                "type": "object",
                "properties": {
                    "telegram_user_id": {"type": "integer"},
                    "task_id": {"type": "integer"},
                },
                "required": ["telegram_user_id", "task_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_timezone",
            "description": "Set the user's timezone preference",
            "parameters": {
                "type": "object",
                "properties": {"timezone": {"type": "string"}},
                "required": ["timezone"],
                "additionalProperties": False,
            },
        },
    },
]


_TIME_RE = re.compile(r"\b(\d{1,2}(:\d{2})?\s*(am|pm)?)\b", re.I)

_TOOL_INTENT_WORDS = (
    "list", "show", "view", "plans", "schedule", "agenda", "what's on", "whats on",
    "delete", "remove", "cancel task", "cancel reminder", "timezone", "/list", "/tz",
    "meeting", "appointment", "remind", "alarm", "tomorrow", "today", "tonight",
    "morning", "evening", "afternoon", "weekday", "weekdays", "every ", "daily",
    "weekly", "monthly", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday",
)

def _wants_tools(text: str) -> bool:
    t = text.lower()
    return bool(_TIME_RE.search(t) or any(w in t for w in _TOOL_INTENT_WORDS))

def _looks_like_tool_json(text: str) -> bool:
    if not text:
        return False
    t = text.strip()

    return ('"type": "function"' in t) or ('"parameters"' in t and t.startswith("{"))


def _exec_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "plan_schedule":
        out = plan_and_schedule(
            narration=args.get("narration", ""),
            timezone=args.get("timezone", "Africa/Lagos"),
            telegram_user_id=args["telegram_user_id"],
        )
        return {"ok": True, "kind": "plan_schedule", "pretty": out.pretty_plan, "scheduled_jobs": out.scheduled_jobs}

    if name == "list_tasks":
        s = get_session()
        items = s.query(TaskRow).filter(
            TaskRow.user_id == args["telegram_user_id"], TaskRow.status == "scheduled"
        ).all()
        return {
            "ok": True,
            "kind": "list_tasks",
            "items": [
                {
                    "id": t.id,
                    "title": t.title,
                    "start": t.start.isoformat() if t.start else None,
                    "rrule": t.rrule,
                    "reminder": t.reminder_offset_minutes,
                }
                for t in items
            ],
        }

    if name == "delete_task":
        s = get_session()
        t = s.query(TaskRow).get(args["task_id"])
        if t and t.user_id == args["telegram_user_id"]:
            t.status = "cancelled"
            s.commit()
            return {"ok": True, "kind": "delete_task", "deleted_id": t.id, "title": t.title}
        return {"ok": False, "kind": "delete_task", "error": "not_found_or_not_owner"}

    if name == "set_timezone":
        return {"ok": True, "kind": "set_timezone", "tz": args["timezone"]}

    return {"ok": False, "error": f"unknown_tool:{name}"}


def dobby_route(user_text: str, tz: str, telegram_user_id: int) -> Tuple[bool, str]:
    """
    Ask Dobby to handle the message (with tool calling).
    Returns (handled, reply_text). If handled==False, caller should fallback.
    """
    cli = _client_or_none()
    if not cli:
        return False, ""

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"TZ={tz}\nUSER_ID={telegram_user_id}\nMESSAGE:\n{user_text}"},
    ]

    try:
        for _ in range(3):
            resp = cli.chat.completions.create(
                model=DOBBY_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
            )
            msg = resp.choices[0].message


            if getattr(msg, "tool_calls", None) and not _wants_tools(user_text):
                messages.append({
                    "role": "system",
                    "content": "User did not ask for planning/listing/deleting/timezone. Reply conversationally without tools."
                })
                continue

            tcs = getattr(msg, "tool_calls", None)
            if tcs:
                for tc in tcs:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        args = {}
                    if name in ("plan_schedule", "list_tasks", "delete_task"):
                        args = {"telegram_user_id": telegram_user_id, **args}
                    result = _exec_tool(name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": json.dumps(result),
                    })
                    if result.get("kind") == "plan_schedule":
                        return True, "✅ Plan created:\n" + result.get("pretty", "Plan created.")
             
                continue

           
            text = (msg.content or "").strip()
            if _looks_like_tool_json(text):
            
                return False, ""
            if text:
                return True, text

        return False, ""
    except Exception:
    
        return False, ""
