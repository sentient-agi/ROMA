from __future__ import annotations
import os, re, io, csv, asyncio, logging, datetime as dt
from typing import List, Tuple
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ForceReply, BotCommand,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError, RetryAfter

from .agent import plan_and_schedule
from .storage import get_session, TaskRow
from .llm_parser import llm_parse
from .dobby_router import dobby_route
from .calendar_sync import (
    sync_all_tasks_for_user,
    delete_google_event,
    is_google_connected,
    revoke_tokens_for_user,
)

from .reminders import schedule_all, schedule_row, scheduler as _reminder_scheduler, schedule_cleanup_dayplan_today

BOT_TOKEN = os.getenv("BOT_TOKEN")
DAYPILOT_CHAT_MODEL = os.getenv(
    "DAYPILOT_CHAT_MODEL",
    os.getenv("DAYPILOT_LLM_MODEL", "openrouter/anthropic/claude-sonnet-4"),
)

log = logging.getLogger("daypilot.bot")
logging.basicConfig(level=logging.INFO)



_EN = {
    "welcome_title": "👋 **Welcome to DayPilot**",
    "welcome_body": (
        "Plan your day and get reminders right here on Telegram.\n\n"
        "What you can do:\n"
        "• Create one-off or recurring tasks (weekdays, Mon/Wed/Fri, first Friday monthly)\n"
        "• Use relative times like “in 30 minutes”, “tomorrow 9–11”\n"
        "• Add reminders like “remind me 15m before”\n"
        "• List & delete tasks\n"
        "• Optional: **/connect** Google Calendar, then **/sync** to see events everywhere"
    ),
    "commands": "Commands",
    "ready": "Ready when you are — just tell me your plan in one sentence",
    "help": (
        "🆘 **How I work**\n"
        "• Chat naturally: “tomorrow at 2 schedule dentist; remind me 10m before”.\n"
        "• I recognize time ranges, repetitions (weekdays / Mon-Wed-Fri / monthly), and offsets like “remind me 15m before”.\n"
        "• I can also understand general requests (e.g., “list my plans”, “move meeting to 4pm”, “plan my day”).\n\n"
        "Google Calendar: `/connect` to link your account, then `/sync`.\n"
        "Settings: `/settings` to change default reminder, language, timezone, or disconnect Google."
    ),
    "no_tasks": "You don’t have any scheduled items yet. Try `/examples` to get started.",
    "schedule_title": "📅 Your schedule",
    "unscheduled": "— Unscheduled —",
    "list_tip": "\nTip: delete an item with `/delete <id>` (you can pass many ids), `/delete all`, or `/delete past`.",
    "plan_created": "✅ Plan created:\n",
    "cant_parse": (
        "I didn’t spot a schedulable task in that message.\n\n"
        "Try including a time (or relative time), a duration, or “remind me … before”.\n"
        "To see what’s already booked, send `list my plans` or use `/list`."
    ),
    "set_tz_usage": "Reply with a timezone like `Europe/London`",
    "set_tz_ok": "Timezone set to `{tz}`",
    "del_usage": "Reply with the task id(s) you want to delete. Examples:\n`12 18 21`, `all`, or `past`",
    "del_id_num": "Task id must be a number, e.g. `42`",
    "not_found": "Not found.",
    "already_deleted": "That task is already deleted: {title} [id:{id}]",
    "deleted": "🗑️ Deleted: {title}",
    "deleted_many": "🗑️ Deleted {n} task(s).",
    "connect_btn": "🔗 Connect Google Calendar",
    "connect_msg_btn": "Tap the button below, then run `/sync` afterward.",
    "connect_msg_url": "Link your Google Calendar:\n{url}\n\nAfter connecting, run `/sync`.",
    "synced": "🔄 Synced to Google Calendar.\n• Updated/created: {ok}\n• Skipped: {skipped}",
    "sync_fail": "Couldn’t sync. Make sure you’ve used `/connect` and granted access.",
    "menu_title": "Here’s your menu. Pick an action or just type your plan:",
    "lang_pick": "Choose your language:",
    "export_ready": "📤 Export ready ({fmt}).",
    "settings_title": "⚙️ Settings",
    "settings_desc": "Default reminder, language, timezone, and calendar connection.",
    "settings_rem_current": "Default reminder: {mins}m",
    "settings_rem_set": "Default reminder set to {mins} minutes.",
    "settings_disc_ok": "Disconnected Google access for this bot.\n(You can also review access at https://myaccount.google.com/permissions)",
    "settings_disc_info": "To fully revoke access, visit https://myaccount.google.com/permissions",
    "settings_connected": "Google: **Connected**",
    "settings_disconnected": "Google: **Not connected**",
    "settings_change_lang": "Change language",
    "settings_change_tz": "Change timezone",
    "settings_disconnect": "Disconnect Google",
    "settings_connect": "Connect Google",
    "tz_pick": "Choose a timezone or tap **Other…** to type a specific one.",
    "tz_other": "Other…",
    "dayplan_exists": "A day plan for today is already set. What would you like to do?",
    "dayplan_edit": "✏️ Edit existing",
    "dayplan_replace": "🔁 Replace",
    "dayplan_cancel": "❌ Cancel",
    "dayplan_replaced": "Replaced today’s plan.",
    "dayplan_edit_hint": "Okay — tell me the changes (e.g., “move lunch to 13:00”, “set all reminders to 5m”), or use `/list` to tweak items.",
    "edit_ok": "Updated **{title}** to {time}. I’ve adjusted today’s schedule to fit.",
    "edit_not_found": "I couldn’t find a task matching “{q}” for today.",

    "rec_q": "Should I keep today’s plan as a daily routine or just for today?",
    "rec_daily": "🔁 Daily",
    "rec_once": "🗓️ One-time",
    "rec_saved": "Got it — saved as a daily routine.",
    "rec_once_note": "Okay — I’ll auto-clear this day plan at 23:59 so it won’t repeat.",
   
    "dups_header": "Possible duplicates in the last 7 days:",
    "dups_none": "No duplicate-looking tasks found in the last 7 days.",
}

LANGS = {
    "en": _EN,
    "es": {**_EN, "welcome_title": "👋 **Bienvenido a DayPilot**", "ready": "Listo — cuéntame tu plan en una frase", "lang_pick": "Elige idioma:"},
    "fr": {**_EN, "welcome_title": "👋 **Bienvenue sur DayPilot**", "ready": "Prêt ? Dites-moi votre plan en une phrase", "lang_pick": "Choisissez votre langue :"},
    "de": {**_EN, "welcome_title": "👋 **Willkommen bei DayPilot**", "ready": "Bereit – sag mir deinen Plan in einem Satz", "lang_pick": "Sprache auswählen:"},
    "pt": {**_EN, "welcome_title": "👋 **Bem-vindo ao DayPilot**", "ready": "Pronto — diga seu plano em uma frase", "lang_pick": "Escolha o idioma:"},
    "it": {**_EN, "welcome_title": "👋 **Benvenuto su DayPilot**", "ready": "Pronto — dimmi il tuo piano in una frase", "lang_pick": "Scegli la lingua:"},
}

POPULAR_TZ = [
    "Africa/Lagos", "Europe/London", "Europe/Paris", "Europe/Berlin",
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "Asia/Dubai", "Asia/Kolkata", "Asia/Shanghai", "Asia/Tokyo",
]

def _u(context: ContextTypes.DEFAULT_TYPE) -> dict:
    lang = context.user_data.get("lang", "en")
    return LANGS.get(lang, LANGS["en"])

# helpers

def _llm_on() -> bool:
    use = os.getenv("DAYPILOT_USE_LLM", "1").lower() not in ("0", "false", "no")
    return bool(os.getenv("OPENROUTER_API_KEY")) and use

def _llm_chat_reply(prompt: str, tz: str) -> str:
    if not _llm_on():
        return ("I can plan from plain English and set reminders.\n\n"
                "Try: `Tomorrow 9–11 deep work; lunch 1pm; remind me 10m before`")
    from litellm import completion
    SYSTEM = (
        "You are DayPilot, a friendly planning assistant on Telegram.\n"
        "Answer in a crisp tone (1–3 short paragraphs). "
        "End with one concrete example the user can copy (in backticks)."
    )
    resp = completion(
        model=DAYPILOT_CHAT_MODEL,
        messages=[{"role":"system","content":SYSTEM},
                  {"role":"user","content":f"Timezone: {tz}\nUser: {prompt}"}],
        temperature=0.4, max_tokens=350
    )
    return resp["choices"][0]["message"]["content"]

def _menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("➕ Plan my day"), KeyboardButton("📅 List")],
        [KeyboardButton("🔗 Connect"), KeyboardButton("🔄 Sync")],
        [KeyboardButton("🌐 Timezone"), KeyboardButton("🌍 Language")],
        [KeyboardButton("⚙️ Settings")],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def welcome_text(tz_hint: str, u: dict) -> str:
    return (
        f"{u['welcome_title']}\n{u['welcome_body']}\n\n"
        f"Timezone: default is `{tz_hint}`. Use `/tz` to change (picker provided).\n"
        f"{u['commands']}: `/menu`, `/settings`, `/tz`, `/list`, `/delete`, `/examples`, `/connect`, `/sync`, `/export csv|ics`, `/dedup`, `/dups`\n\n"
        f"{u['ready']}"
    )

def help_text(u: dict) -> str:
    return u["help"]

def examples_text() -> str:
    return (
        "📋 **Copy-paste examples**\n"
        "`Weekdays 7am gym for 1h, remind me 15m before`\n"
        "`Tomorrow 9–11 deep work; lunch 1pm`\n"
        "`First Friday monthly team brunch 10:00 for 90m`\n"
        "`In 30 minutes check the oven`\n"
        "`Every weekend call mom at 6pm, remind me 10m before`"
    )

def _looks_like_question(text: str) -> bool:
    t = text.strip().lower()
    return "?" in t or t.startswith(("can you", "what", "how", "help", "hi", "hello", "hey"))

def _pretty_preview(plan) -> str:
    rows=[]
    for i,task in enumerate(plan.tasks,1):
        when = task.start.strftime('%a %H:%M') if task.start else "unspecified"
        rec = " 🔁" if task.rrule else ""
        rows.append(f"{i}. {task.title}{rec} — {when} (remind {task.reminder_offset_minutes}m before)")
    return "\n".join(rows) if rows else "No tasks parsed."

def _render_task_list_for_user(user_id: int, tz: str, u: dict) -> str:
    s = get_session()
    items = (
        s.query(TaskRow)
        .filter(TaskRow.user_id == user_id, TaskRow.status == "scheduled")
        .order_by(TaskRow.start.is_(None), TaskRow.start.asc())
        .all()
    )
    if not items:
        return u["no_tasks"]

    from collections import defaultdict
    groups = defaultdict(list)
    for t in items:
        key = t.start.date().isoformat() if t.start else "unscheduled"
        groups[key].append(t)

    lines = [f"{u['schedule_title']} ({tz})"]
    for key in sorted(groups.keys()):
        if key == "unscheduled":
            lines.append(f"\n{u['unscheduled']}")
        else:
            d = groups[key][0].start
            lines.append(f"\n{d.strftime('%a %b %d, %Y')}")
        for t in groups[key]:
            time_str = t.start.strftime('%H:%M') if t.start else "—"
            rec = " 🔁" if t.rrule else ""
            lines.append(f"• {time_str} — {t.title}{rec} (remind {t.reminder_offset_minutes}m) [id:{t.id}]")
    lines.append(u["list_tip"])
    return "\n".join(lines)

def _is_valid_tz(name: str) -> bool:
    try:
        ZoneInfo(name); return True
    except Exception:
        return False

async def reply_text_safe(message, text: str, **kwargs):
    for attempt in range(3):
        try:
            return await message.reply_text(text, **kwargs)
        except RetryAfter as e:
            await asyncio.sleep(int(getattr(e, "retry_after", 1)))
        except (TimedOut, NetworkError):
            await asyncio.sleep(1 * (2**attempt))
    try:
        kwargs.pop("parse_mode", None)
        return await message.reply_text(text, **kwargs)
    except Exception as e:
        log.warning("Failed to send message after retries: %s", e)



_ACK_TOKENS = {
    "thanks","thank you","thx","ok","okay","k","cool","great","awesome","got it","roger",
    "yup","yep","sure","nice","perfect","sounds good","no problem","np","cheers",
    "hi","hello","hey","good morning","good afternoon","good evening","good night",
    "bye","goodbye","see you","ttyl","lol","haha","😂","👍","👌","🙏"
}

def _looks_like_smalltalk(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return True

    if any(tok in t for tok in _ACK_TOKENS):
       
        if re.search(r"\b(?:\d{1,2}(:\d{2})?\s?(am|pm)?)\b", t):
            return False
        if re.search(r"\b(today|tomorrow|next|mon|tue|wed|thu|fri|sat|sun)\b", t):
            return False
        return True
  
    if not any(ch.isalnum() for ch in text):
        return True
    return False

def _llm_smalltalk_reply(text: str, tz: str) -> str:
    """Short, warm response that never schedules anything."""
    if not _llm_on():
        return "😊 You're welcome! When you're ready, tell me what to schedule."
    from litellm import completion
    SYSTEM = (
        "You are DayPilot, a warm, brief assistant. "
        "The user message is casual small-talk (greetings/thanks). "
        "Reply in one short, friendly sentence. "
        "Do not ask questions and do not mention scheduling."
    )
    resp = completion(
        model=DAYPILOT_CHAT_MODEL,
        messages=[{"role":"system","content":SYSTEM},
                  {"role":"user","content":f"Timezone: {tz}\nMessage: {text}"}],
        temperature=0.5, max_tokens=50
    )
    return resp["choices"][0]["message"]["content"].strip()

async def _maybe_handle_smalltalk(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """If small-talk, send LLM reply, then a 'no task created' nudge."""
    tz = context.user_data.get("tz", "Africa/Lagos")
    if not _looks_like_smalltalk(text):
        return False
    try:
        reply = _llm_smalltalk_reply(text, tz)
        await reply_text_safe(update.message, reply, parse_mode="Markdown")
    except Exception:
        await reply_text_safe(update.message, "😊 You're welcome!", parse_mode="Markdown")
    await reply_text_safe(
        update.message,
        "No task created. When you want me to plan, try something like:\n`Tomorrow 9–11 deep work; lunch 1pm; remind me 10m before`",
        parse_mode="Markdown"
    )
    return True



_TIME_WORDS = r"(?:today|tomorrow|tonight|next|this|mon|tue|wed|thu|fri|sat|sun|weekend|weekday|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|in\s+\d+\s*(?:min|mins|minutes|hour|hours|day|days|week|weeks))"
_TIME_REGEX = re.compile(
    r"\b(\d{1,2}(:\d{2})?\s*(am|pm))\b|"
    r"\b\d{1,2}(:\d{2})\b|"
    rf"\b{_TIME_WORDS}\b",
    re.I,
)

_SCHEDULE_VERBS = re.compile(
    r"\b(remind|schedule|set|add|create|book|put|block|plan|calendar|alarm|timer)\b",
    re.I,
)

_META_COMM_PHRASES = re.compile(
    r"\b(i['’]ll\s+(let\s+you\s+know|ping|message|text|reach\s+out|hit\s+you\s+up)|"
    r"not\s+now|later|soon|when\s+i['’]m\s+ready|i\s+am\s+ready\s+to)\b",
    re.I,
)

def _has_time_signal(text: str) -> bool:
    return bool(_TIME_REGEX.search(text))

def _has_schedule_intent(text: str) -> bool:
    return bool(_SCHEDULE_VERBS.search(text))

def _is_meta_comm(text: str) -> bool:
    return bool(_META_COMM_PHRASES.search(text))


# Balanced plan helpers

_BALANCED_KEYS = {
    "wake up","light exercise","breakfast","deep work","short break","focus block",
    "lunch","10-minute walk","admin/emails","wrap-up","workout","dinner",
    "plan tomorrow","relax/reading","sleep"
}

def _is_balanced_title(title: str) -> bool:
    t = (title or "").lower()
    return any(k in t for k in _BALANCED_KEYS)

def _today_date(tz: str) -> dt.date:
    return dt.datetime.now(ZoneInfo(tz)).date()

def _balanced_tasks_for_today(user_id: int, tz: str) -> List[TaskRow]:
    s = get_session()
    zi = ZoneInfo(tz)
    rows = (
        s.query(TaskRow)
        .filter(TaskRow.user_id == user_id, TaskRow.status == "scheduled")
        .all()
    )
    today = _today_date(tz)
    out = []
    for r in rows:
        if r.start and r.start.astimezone(zi).date() == today and _is_balanced_title(r.title or ""):
            out.append(r)
    return out

def _has_day_plan(user_id: int, tz: str) -> bool:
    return len(_balanced_tasks_for_today(user_id, tz)) >= 5

def _cancel_today_day_plan(user_id: int, tz: str) -> int:
    s = get_session()
    zi = ZoneInfo(tz)
    today = _today_date(tz)
    rows = (
        s.query(TaskRow)
        .filter(TaskRow.user_id == user_id, TaskRow.status == "scheduled")
        .all()
    )
    cnt = 0
    for t in rows:
        if not t.start:
            continue
        if t.start.astimezone(zi).date() != today:
            continue
        if not _is_balanced_title(t.title or ""):
            continue
        t.status = "cancelled"
        try:
            delete_google_event(t)
        except Exception:
            pass
        cnt += 1
    if cnt:
        s.commit()
    return cnt

def _duration_minutes_row(t: TaskRow) -> int:
    return getattr(t, "duration_minutes", None) or 60

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

def _parse_time_token(s: str):
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", s, re.I)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2) or 0)
    ap = (m.group(3) or "").lower()
    if ap == "pm" and hh != 12: hh += 12
    if ap == "am" and hh == 12: hh = 0
    hh %= 24
    return hh, mm

def _parse_edit_change(text: str, context: ContextTypes.DEFAULT_TYPE):
    m = re.search(r"\b(change|move|set|reschedule)\s+(.+?)\s+(to|at)\s+(.+)$", text, re.I)
    if m:
        title = m.group(2).strip()
        tm = _parse_time_token(m.group(4))
        if tm:
            context.user_data["last_edit_title"] = title
            return title, tm[0], tm[1]
    tm_only = _parse_time_token(text)
    if tm_only and context.user_data.get("last_edit_title"):
        title = context.user_data["last_edit_title"]
        return title, tm_only[0], tm_only[1]
    return None

def _reflow_today(user_id: int, tz: str):
    s = get_session()
    zi = ZoneInfo(tz)
    today = _today_date(tz)
    rows = (
        s.query(TaskRow)
        .filter(TaskRow.user_id == user_id, TaskRow.status == "scheduled")
        .all()
    )
    todays = [r for r in rows if r.start and r.start.astimezone(zi).date() == today]
    todays.sort(key=lambda r: r.start)
    if not todays:
        return
    end_of_day = dt.datetime.combine(today, dt.time(23, 59), tzinfo=zi)
    prev_end = None
    for r in todays:
        dur = dt.timedelta(minutes=_duration_minutes_row(r))
        start = r.start.astimezone(zi)
        if prev_end and start < prev_end:
            start = prev_end
        if start + dur > end_of_day:
            start = max(start, end_of_day - dur)
        r.start = start.astimezone(r.start.tzinfo or zi)
        prev_end = r.start.astimezone(zi) + dur
        # ensure reminders follow edits
        schedule_row(r)
    s.commit()

def _delete_duplicates_by_title_today(user_id: int, tz: str, keep_id: int, title: str):
    s = get_session()
    zi = ZoneInfo(tz)
    today = _today_date(tz)
    rows = (
        s.query(TaskRow)
        .filter(TaskRow.user_id == user_id, TaskRow.status == "scheduled")
        .all()
    )
    title_n = _norm(title)
    for r in rows:
        if r.id == keep_id or not r.start:
            continue
        if r.start.astimezone(zi).date() != today:
            continue
        if _norm(r.title) == title_n:
            r.status = "cancelled"
            try: delete_google_event(r)
            except Exception: pass
    s.commit()

async def _apply_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, query_title: str, hh: int, mm: int):
    tz = context.user_data.get("tz", "Africa/Lagos")
    u = _u(context)
    zi = ZoneInfo(tz)
    today = _today_date(tz)
    candidates = _balanced_tasks_for_today(update.effective_user.id, tz)
    q = _norm(query_title)
    target = None
    best = -1
    for c in candidates:
        t = _norm(c.title)
        score = (5 if (q in t or t in q) else 0) + len(set(q.split()).intersection(set(t.split())))
        if score > best: best = score; target = c
    if not target:
        await reply_text_safe(update.message, u["edit_not_found"].format(q=query_title), parse_mode="Markdown")
        return
    new_dt = dt.datetime.combine(today, dt.time(hh, mm), tzinfo=zi)
    target.start = new_dt.astimezone(target.start.tzinfo or zi)
    s = get_session()
    s.merge(target); s.commit()
    schedule_row(target)
    _delete_duplicates_by_title_today(update.effective_user.id, tz, target.id, target.title or query_title)
    _reflow_today(update.effective_user.id, tz)
    try: sync_all_tasks_for_user(update.effective_user.id, tz)
    except Exception: pass
    await reply_text_safe(update.message, u["edit_ok"].format(title=target.title, time=new_dt.strftime("%H:%M")), parse_mode="Markdown")

# Google connect/sync 

async def connect_cmd_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = _u(context)
    base = os.getenv("OAUTH_BASE_URL", "http://localhost:8000")
    uid = update.effective_user.id
    url = f"{base}/connect?uid={uid}"
    p = urlparse(url)
    allow_button = (p.scheme == "https" and p.hostname not in ("localhost","127.0.0.1"))
    if allow_button:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(u["connect_btn"], url=url)]])
        await reply_text_safe(update.message, u["connect_msg_btn"], reply_markup=kb, disable_web_page_preview=True)
    else:
        await reply_text_safe(update.message, u["connect_msg_url"].format(url=url), disable_web_page_preview=True)

async def sync_cmd_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = _u(context)
    tz = context.user_data.get("tz", "Africa/Lagos")
    try:
        ok, skipped = sync_all_tasks_for_user(update.effective_user.id, tz)
        await reply_text_safe(update.message, u["synced"].format(ok=ok, skipped=skipped))
    except Exception:
        await reply_text_safe(update.message, u["sync_fail"])

# Export 

def _export_csv_bytes(rows: List[TaskRow]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id","title","start_iso","rrule","reminder_minutes","status"])
    for t in rows:
        w.writerow([t.id, t.title, t.start.isoformat() if t.start else "", t.rrule or "", t.reminder_offset_minutes, t.status])
    return buf.getvalue().encode("utf-8")

def _export_ics_bytes(rows: List[TaskRow]) -> bytes:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//DayPilot//EN"]
    for t in rows:
        if not t.start:
            continue
        dtstart = t.start.strftime("%Y%m%dT%H%M%S")
        uid = f"daypilot-{t.id}@local"
        summary = t.title.replace("\n"," ")
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}", f"DTSTART:{dtstart}", f"SUMMARY:{summary}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines)).encode("utf-8")

async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = _u(context)
    fmt = (context.args[0].lower() if context.args else "csv")
    s = get_session()
    rows = (
        s.query(TaskRow)
        .filter(TaskRow.user_id == update.effective_user.id)
        .order_by(TaskRow.start.is_(None), TaskRow.start.asc())
        .all()
    )
    if fmt == "ics":
        data = _export_ics_bytes(rows)
        await update.message.reply_document(document=data, filename="daypilot_export.ics", caption=u["export_ready"].format(fmt="ICS"))
    else:
        data = _export_csv_bytes(rows)
        await update.message.reply_document(document=data, filename="daypilot_export.csv", caption=u["export_ready"].format(fmt="CSV"))

# Settings 

def _settings_kb(default_minutes: int, connected: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("Rem: None", callback_data="settings:reminder:0"),
            InlineKeyboardButton("5m", callback_data="settings:reminder:5"),
            InlineKeyboardButton("10m", callback_data="settings:reminder:10"),
            InlineKeyboardButton("15m", callback_data="settings:reminder:15"),
            InlineKeyboardButton("30m", callback_data="settings:reminder:30"),
        ],
        [InlineKeyboardButton("🌍 Change language", callback_data="settings:lang")],
        [InlineKeyboardButton("🌐 Change timezone", callback_data="settings:tz")],
    ]
    if connected:
        rows.append([InlineKeyboardButton("Disconnect Google", callback_data="settings:disconnect")])
    else:
        rows.append([InlineKeyboardButton("Connect Google", callback_data="settings:connect")])
    rows.append([InlineKeyboardButton("Close", callback_data="settings:close")])
    return InlineKeyboardMarkup(rows)

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = _u(context)
    mins = int(context.user_data.get("default_reminder", 10))
    connected = is_google_connected(update.effective_user.id)
    gline = u["settings_connected"] if connected else u["settings_disconnected"]
    txt = (
        f"{u['settings_title']}\n{u['settings_desc']}\n\n"
        f"{gline}\n{u['settings_rem_current'].format(mins=mins)}"
    )
    await update.message.reply_text(txt, reply_markup=_settings_kb(mins, connected), parse_mode="Markdown")

# Timezone picker 

def _tz_keyboard(u: dict) -> InlineKeyboardMarkup:
    rows = []
    chunk = []
    for z in POPULAR_TZ:
        chunk.append(InlineKeyboardButton(z, callback_data=f"settz:{z}"))
        if len(chunk) == 2:
            rows.append(chunk); chunk = []
    if chunk: rows.append(chunk)
    rows.append([InlineKeyboardButton(u["tz_other"], callback_data="settz:other")])
    return InlineKeyboardMarkup(rows)

async def tz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = _u(context)
    await reply_text_safe(update.message, u["tz_pick"], reply_markup=_tz_keyboard(u))

# Balanced template 

def _balanced_day_narration() -> str:
    return (
        "Today 07:00 wake up; "
        "07:30 light exercise for 20m; "
        "08:00 breakfast; "
        "09:00 deep work for 90m; "
        "10:30 short break for 10m; "
        "10:40 focus block for 90m; "
        "12:30 lunch for 45m; "
        "13:30 10-minute walk; "
        "14:00 admin/emails for 60m; "
        "15:30 short break for 10m; "
        "15:40 deep work for 80m; "
        "17:00 wrap-up for 30m; "
        "18:00 workout for 30m; "
        "19:00 dinner for 45m; "
        "20:30 plan tomorrow for 15m; "
        "21:00 relax/reading for 60m; "
        "22:30 sleep; "
        "remind me 10m before"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = context.user_data.get("tz", "Africa/Lagos")
    u = _u(context)
    await update.message.reply_text(welcome_text(tz, u), parse_mode="Markdown", reply_markup=_menu_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(help_text(_u(context)), parse_mode="Markdown")

async def examples_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply_text_safe(update.message, examples_text(), parse_mode="Markdown")

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply_text_safe(update.message, _u(context)["menu_title"], reply_markup=_menu_keyboard())

async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("English", callback_data="setlang:en"),
         InlineKeyboardButton("Español", callback_data="setlang:es")],
        [InlineKeyboardButton("Français", callback_data="setlang:fr"),
         InlineKeyboardButton("Deutsch", callback_data="setlang:de")],
        [InlineKeyboardButton("Português", callback_data="setlang:pt"),
         InlineKeyboardButton("Italiano", callback_data="setlang:it")],
    ])
    await reply_text_safe(update.message, _u(context)["lang_pick"], reply_markup=kb)

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = context.user_data.get("tz", "Africa/Lagos")
    msg = _render_task_list_for_user(update.effective_user.id, tz, _u(context))
    await reply_text_safe(update.message, msg)

def _parse_delete_args(tokens: List[str]) -> Tuple[str, List[int]]:
    """Returns ('all'|'past'|'ids', ids[])"""
    if not tokens: return ("ids", [])
    t0 = tokens[0].lower()
    if t0 in {"all", "past"} and len(tokens) == 1:
        return (t0, [])
    ids: List[int] = []
    for tok in tokens:
        for m in re.findall(r"\d+", tok):
            try: ids.append(int(m))
            except Exception: pass
    return ("ids", sorted(set(ids)))

def _cancel_ids(user_id: int, ids: List[int]) -> int:
    s = get_session()
    n = 0
    for tid in ids:
        t = s.query(TaskRow).get(tid)
        if not t or t.user_id != user_id: continue
        if t.status == "cancelled": continue
        t.status = "cancelled"; n += 1
        try: delete_google_event(t)
        except Exception: pass
    if n: s.commit()
    return n

def _cancel_all(user_id: int) -> int:
    s = get_session()
    rows = s.query(TaskRow).filter(TaskRow.user_id==user_id, TaskRow.status=="scheduled").all()
    ids = [r.id for r in rows]
    return _cancel_ids(user_id, ids)

def _cancel_past(user_id: int, tz: str) -> int:
    s = get_session()
    zi = ZoneInfo(tz)
    now = dt.datetime.now(zi)
    rows = s.query(TaskRow).filter(TaskRow.user_id==user_id, TaskRow.status=="scheduled").all()
    ids = [r.id for r in rows if r.start and r.start.astimezone(zi) < now]
    return _cancel_ids(user_id, ids)

async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = _u(context)

    if context.args:
        kind, ids = _parse_delete_args(context.args)
        uid = update.effective_user.id
        tz = context.user_data.get("tz", "Africa/Lagos")
        if kind == "all":
            n = _cancel_all(uid)
            await reply_text_safe(update.message, u["deleted_many"].format(n=n)); return
        if kind == "past":
            n = _cancel_past(uid, tz)
            await reply_text_safe(update.message, u["deleted_many"].format(n=n)); return
        if ids:
            n = _cancel_ids(uid, ids)
            await reply_text_safe(update.message, u["deleted_many"].format(n=n)); return
   
    context.user_data["awaiting_delete"] = True
    await reply_text_safe(update.message, u["del_usage"], reply_markup=ForceReply(selective=True))

async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await connect_cmd_impl(update, context)

async def sync_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await sync_cmd_impl(update, context)

async def tz_entry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await tz_cmd(update, context)



def _dedup_tasks_today(user_id: int, tz: str) -> int:
    from collections import defaultdict
    s = get_session()
    zi = ZoneInfo(tz)
    today = _today_date(tz)
    items = s.query(TaskRow).filter(TaskRow.user_id==user_id, TaskRow.status=="scheduled").all()
    groups = defaultdict(list)
    for t in items:
        if not t.start: continue
        if t.start.astimezone(zi).date() != today: continue
        key = _norm(t.title)
        if key: groups[key].append(t)
    removed = 0
    for key, rows in groups.items():
        if len(rows) <= 1: continue
        rows.sort(key=lambda r: r.start)
        keep = rows[0]
        for r in rows[1:]:
            r.status = "cancelled"; removed += 1
            try: delete_google_event(r)
            except Exception: pass
    if removed: s.commit()
    try: 
        if removed: sync_all_tasks_for_user(user_id, tz)
    except Exception: pass
    return removed

def _duplicate_titles_last_days(user_id: int, days: int = 7) -> List[Tuple[str, List[TaskRow]]]:
    """Crude scan: same normalized title appearing 2+ times in last N days (any status)."""
    s = get_session()
    now = dt.datetime.utcnow()
    since = now - dt.timedelta(days=days)
    rows = s.query(TaskRow).filter(TaskRow.user_id==user_id).all()
    from collections import defaultdict
    bucket = defaultdict(list)
    for r in rows:
        if not (r.title and r.start): continue
        if r.start.replace(tzinfo=None) < since: continue
        bucket[_norm(r.title)].append(r)
    out = []
    for key, arr in bucket.items():
        if len(arr) >= 2:

            out.append((arr[0].title, sorted(arr, key=lambda x: (x.start or dt.datetime.min))))
    return out

async def dedup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = context.user_data.get("tz", "Africa/Lagos")
    n = _dedup_tasks_today(update.effective_user.id, tz)
    if n:
        await reply_text_safe(update.message, f"Removed {n} duplicate task(s) for today (kept earliest per title).")
    else:
        await reply_text_safe(update.message, "No duplicates found for today.")

async def dups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = _u(context)
    dup_sets = _duplicate_titles_last_days(update.effective_user.id, days=7)
    if not dup_sets:
        await reply_text_safe(update.message, u["dups_none"]); return
    lines = [u["dups_header"]]
    for title, arr in dup_sets:
        ids = ", ".join(str(r.id) for r in arr[:6])
        when = ", ".join((r.start.strftime("%m-%d") if r.start else "—") for r in arr[:6])
        lines.append(f"• {title} — {len(arr)} times (ids: {ids}; dates: {when})")
    lines.append("\nTip: reply with `/delete <id> <id> …` to remove the extras.")
    await reply_text_safe(update.message, "\n".join(lines))

# Callback handler

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data.startswith("setlang:"):
        lang = data.split(":",1)[1]
        context.user_data["lang"] = lang
        await q.edit_message_text(f"Language set to {lang.upper()}.")
        return

    if data.startswith("settings:"):
        u = _u(context)
        action = data.split(":")[1]
        if action == "reminder":
            mins = int(data.split(":")[2])
            context.user_data["default_reminder"] = mins
            connected = is_google_connected(q.from_user.id)
            await q.edit_message_text(u["settings_rem_set"].format(mins=mins), reply_markup=_settings_kb(mins, connected))
            return
        if action == "disconnect":
            ok = revoke_tokens_for_user(q.from_user.id)
            mins = int(context.user_data.get("default_reminder", 10))
            txt = u["settings_disc_ok"] if ok else u["settings_disc_info"]
            await q.edit_message_text(txt, reply_markup=_settings_kb(mins, False))
            return
        if action == "connect":
            await q.edit_message_text("Use /connect to link your Google Calendar.")
            return
        if action == "lang":
            await lang_cmd(update, context); return
        if action == "tz":
            await tz_cmd(update, context); return
        if action == "close":
            try: await q.delete_message()
            except Exception: await q.edit_message_text("Closed.")
            return

    if data.startswith("settz:"):
        z = data.split(":",1)[1]
        if z == "other":
            context.user_data["awaiting_tz"] = True
            await q.edit_message_text(_u(context)["set_tz_usage"])
            return
        context.user_data["tz"] = z
        await q.edit_message_text(_u(context)["set_tz_ok"].format(tz=z))
        return

    if data == "confirm_schedule":
        tz = context.user_data.get("tz", "Africa/Lagos")
        narration = context.user_data.pop("pending_narration", None)
        if not narration:
            await q.edit_message_text("Nothing to schedule. Send a message to create a plan.")
            return
        out = plan_and_schedule(narration, timezone=tz, telegram_user_id=update.effective_user.id)
        try: sync_all_tasks_for_user(update.effective_user.id, tz)
        except Exception: pass
        await q.edit_message_text(_u(context)["plan_created"] + out.pretty_plan)
        return

    # Dayplan replace/edit/cancel
    if data.startswith("dayplan:"):
        action = data.split(":",1)[1]
        tz = context.user_data.get("tz", "Africa/Lagos")
        u = _u(context)
        if action == "replace":
            _cancel_today_day_plan(q.from_user.id, tz)
            narration = _balanced_day_narration()
            default_rem = int(context.user_data.get("default_reminder", 10))
            if default_rem > 0 and "remind me" not in narration.lower():
                narration = narration.rstrip("; ") + f"; remind me {default_rem}m before"
            out = plan_and_schedule(narration, timezone=tz, telegram_user_id=q.from_user.id)
            try: sync_all_tasks_for_user(q.from_user.id, tz)
            except Exception: pass
            await q.edit_message_text(u["dayplan_replaced"] + "\n\n" + (_u(context)["plan_created"] + out.pretty_plan))
       
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(_u(context)["rec_daily"], callback_data="rec:daily"),
                                        InlineKeyboardButton(_u(context)["rec_once"], callback_data="rec:once")]])
            await reply_text_safe(update.effective_message, _u(context)["rec_q"], reply_markup=kb)
            return
        if action == "edit":
            context.user_data["editing_dayplan"] = True
            await q.edit_message_text(u["dayplan_edit_hint"])
            return
        if action == "cancel":
            try: await q.delete_message()
            except Exception: await q.edit_message_text("Cancelled.")
            return

   
    if data.startswith("rec:"):
        choice = data.split(":",1)[1]
        tz = context.user_data.get("tz", "Africa/Lagos")
        zi = ZoneInfo(tz)
        today = _today_date(tz)
        rows = _balanced_tasks_for_today(update.effective_user.id, tz)
        s = get_session()
        if choice == "daily":
            for r in rows:
 
                r.rrule = "FREQ=DAILY"
                s.add(r); schedule_row(r)
            s.commit()
            try: sync_all_tasks_for_user(update.effective_user.id, tz)
            except Exception: pass
            await q.edit_message_text(_u(context)["rec_saved"]); return
        if choice == "once":
            schedule_cleanup_dayplan_today(update.effective_user.id, tz)
            await q.edit_message_text(_u(context)["rec_once_note"]); return

    context.user_data.pop("pending_narration", None)
    await q.edit_message_text("Okay, not scheduled. You can send a new message or type /examples.")

# Main text router

async def handle_narration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = context.user_data.get("tz", "Africa/Lagos")
    text = update.message.text.strip()
    uid = update.effective_user.id
    u = _u(context)

    # Timezone entry flow
    if context.user_data.pop("awaiting_tz", False):
        if _is_valid_tz(text):
            context.user_data["tz"] = text
            await reply_text_safe(update.message, u["set_tz_ok"].format(tz=text), parse_mode="Markdown")
        else:
            context.user_data["awaiting_tz"] = True
            await reply_text_safe(update.message, u["set_tz_usage"], parse_mode="Markdown")
        return

    # Deletion flow
    if context.user_data.get("awaiting_delete", False):
        context.user_data["awaiting_delete"] = False
        tokens = text.split()
        kind, ids = _parse_delete_args(tokens)
        if kind == "all":
            n = _cancel_all(uid); await reply_text_safe(update.message, u["deleted_many"].format(n=n)); return
        if kind == "past":
            n = _cancel_past(uid, tz); await reply_text_safe(update.message, u["deleted_many"].format(n=n)); return
        if ids:
            n = _cancel_ids(uid, ids); await reply_text_safe(update.message, u["deleted_many"].format(n=n)); return
        await reply_text_safe(update.message, u["del_usage"], parse_mode="Markdown"); return

    # Edit/move command
    edit = _parse_edit_change(text, context)
    if edit:
        title, hh, mm = edit
        await _apply_edit(update, context, title, hh, mm)
        return

    t = text.lower()

    # Dedup triggers
    if "delete duplicate" in t or "remove duplicate" in t or t == "dedup":
        n = _dedup_tasks_today(uid, tz)
        if n:
            await reply_text_safe(update.message, f"Removed {n} duplicate task(s) for today (kept earliest per title).")
        else:
            await reply_text_safe(update.message, "No duplicates found for today.")
        return
    if t in {"/dups", "dups", "duplicates"}:
        await dups_cmd(update, context); return

    # Simple commands
    if t in {"menu","/menu"}:
        await menu_cmd(update, context); return
    if t in {"settings","/settings","⚙️ settings"}:
        await settings_cmd(update, context); return
    if t in {"📅 list","list","my plans","show schedule"}:
        await list_tasks(update, context); return
    if t in {"🔗 connect","connect"}:
        await connect_cmd_impl(update, context); return
    if t in {"🔄 sync","sync"}:
        await sync_cmd_impl(update, context); return
    if t in {"🌐 timezone","timezone","/tz"}:
        await tz_cmd(update, context); return
    if t in {"🌍 language","language","/lang"}:
        await lang_cmd(update, context); return


    if _is_meta_comm(text) and not _has_time_signal(text):
        await reply_text_safe(
            update.message,
            _llm_smalltalk_reply(text, tz) or "👍 Sounds good!",
            parse_mode="Markdown",
        )
        await reply_text_safe(
            update.message,
            "No task created. When you want me to plan, say something like:\n`Tomorrow 9–11 deep work; lunch 1pm; remind me 10m before`",
            parse_mode="Markdown",
        )
        return

  
    if await _maybe_handle_smalltalk(update, context, text):
        return

 
    if t in {"➕ plan my day","/plan"}:
        if _has_day_plan(uid, tz):
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(_u(context)["dayplan_edit"], callback_data="dayplan:edit"),
                 InlineKeyboardButton(_u(context)["dayplan_replace"], callback_data="dayplan:replace")],
                [InlineKeyboardButton(_u(context)["dayplan_cancel"], callback_data="dayplan:cancel")]
            ])
            await reply_text_safe(update.message, _u(context)["dayplan_exists"], reply_markup=kb)
            return
        narration = _balanced_day_narration()
        default_rem = int(context.user_data.get("default_reminder", 10))
        if default_rem > 0 and "remind me" not in narration.lower():
            narration = narration.rstrip("; ") + f"; remind me {default_rem}m before"
        out = plan_and_schedule(narration, timezone=tz, telegram_user_id=uid)
        if out.scheduled_jobs > 0:
            try: sync_all_tasks_for_user(uid, tz)
            except Exception: pass
            await reply_text_safe(update.message, u["plan_created"] + out.pretty_plan)
        

            kb = InlineKeyboardMarkup([[InlineKeyboardButton(_u(context)["rec_daily"], callback_data="rec:daily"),
                                        InlineKeyboardButton(_u(context)["rec_once"], callback_data="rec:once")]])
            await reply_text_safe(update.message, _u(context)["rec_q"], reply_markup=kb)
        else:
            await reply_text_safe(update.message, u["cant_parse"] + "\n\n" + examples_text(), parse_mode="Markdown")
        return


    if not (_has_time_signal(text) or _has_schedule_intent(text)):

        if _looks_like_question(text):
            reply = _llm_chat_reply(text, tz)
            await reply_text_safe(update.message, reply, parse_mode="Markdown")
        else:
            await reply_text_safe(
                update.message,
                _llm_smalltalk_reply(text, tz) or "👋 Got it.",
                parse_mode="Markdown",
            )
            await reply_text_safe(
                update.message,
                "No task created. If you want me to schedule something, include a time/date or say `remind me …`.",
                parse_mode="Markdown",
            )
        return
   


    default_rem = int(context.user_data.get("default_reminder", 10))
    if default_rem > 0 and re.search(r"\bremind me\b", text, re.I) is None:
        text = f"{text}, remind me {default_rem}m before"

    handled, reply = dobby_route(text, tz, uid)
    if handled and reply:
        await reply_text_safe(update.message, reply, parse_mode="Markdown"); return


    if _looks_like_question(text):
        reply = _llm_chat_reply(text, tz)
        await reply_text_safe(update.message, reply, parse_mode="Markdown"); return

   
    out = plan_and_schedule(text, timezone=tz, telegram_user_id=uid)
    if out.scheduled_jobs > 0:
        try: sync_all_tasks_for_user(uid, tz)
        except Exception: pass
        await reply_text_safe(update.message, u["plan_created"] + out.pretty_plan); return

  
    if _llm_on() and (_has_time_signal(text) or _has_schedule_intent(text)):
        try:
            plan = llm_parse(text, tz)
            if plan.tasks:
                preview = _pretty_preview(plan)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Schedule", callback_data="confirm_schedule"),
                     InlineKeyboardButton("✏️ Cancel", callback_data="cancel_schedule")]
                ])
                context.user_data["pending_narration"] = text
                await reply_text_safe(update.message, "Here’s a plan I can schedule from that:\n" + preview + "\n\nSchedule it?", reply_markup=kb)
                return
        except Exception:
            pass

    await reply_text_safe(update.message, u["cant_parse"] + "\n\n" + examples_text(), parse_mode="Markdown")

# Errors & app

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled exception while processing update", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("Sorry, I hit a connection hiccup. Please try again.")
    except Exception:
        pass

def _build_application() -> Application:
    request = HTTPXRequest(connect_timeout=25.0, read_timeout=60.0, write_timeout=60.0, pool_timeout=10.0)
    return (
        Application
        .builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(_post_init)
        .build()
    )

async def _post_init(app: Application):
    try:
        schedule_all()
    except Exception as e:
        log.warning("schedule_all failed at startup: %s", e)

    cmds = [
        BotCommand("start","welcome"),
        BotCommand("menu","show quick menu"),
        BotCommand("settings","change reminder/language/timezone, connect Google"),
        BotCommand("help","how to use"),
        BotCommand("examples","copy-paste samples"),
        BotCommand("tz","pick a timezone"),
        BotCommand("list","list tasks"),
        BotCommand("delete","delete tasks (ids|all|past)"),
        BotCommand("connect","link Google Calendar"),
        BotCommand("sync","sync to Google Calendar"),
        BotCommand("export","export tasks (csv|ics)"),
        BotCommand("lang","language"),
        BotCommand("plan","balanced day plan"),
        BotCommand("dedup","remove duplicate tasks for today"),
        BotCommand("dups","scan last 7 days for duplicates"),
    ]
    try:
        await app.bot.set_my_commands(cmds)
    except Exception as e:
        log.warning("Could not set bot commands: %s", e)

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Put it in .env and `source .env` before running.")
    from telegram import Bot
    async def _check():
        try:
            me = await Bot(BOT_TOKEN).get_me()
            print(f"Authenticated as @{me.username} ({me.id})")
        except Exception as e:
            print("Warning: could not verify BOT token now:", e)
   
    asyncio.run(_check())

 
    app = _build_application()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("examples", examples_cmd))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CommandHandler("tz", tz_entry_cmd))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("delete", delete_task))
    app.add_handler(CommandHandler("connect", connect_cmd))
    app.add_handler(CommandHandler("sync", sync_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("plan", handle_narration))
    app.add_handler(CommandHandler("dedup", dedup_cmd))
    app.add_handler(CommandHandler("dups", dups_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_narration))
    app.add_error_handler(error_handler)


    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)


    print("DayPilot bot running…")
 
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
