from __future__ import annotations
import os, re, io, csv, asyncio, logging, datetime as dt
from typing import List
from urllib.parse import urlparse

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

BOT_TOKEN = os.getenv("BOT_TOKEN")
DAYPILOT_CHAT_MODEL = os.getenv(
    "DAYPILOT_CHAT_MODEL",
    os.getenv("DAYPILOT_LLM_MODEL", "openrouter/anthropic/claude-sonnet-4"),
)

log = logging.getLogger("daypilot.bot")
logging.basicConfig(level=logging.INFO)

# i18n

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
    "list_tip": "\nTip: delete an item with `/delete <id>`.",
    "plan_created": "✅ Plan created:\n",
    "cant_parse": (
        "I didn’t spot a schedulable task in that message.\n\n"
        "Try including a time (or relative time), a duration, or “remind me … before”.\n"
        "To see what’s already booked, send `list my plans` or use `/list`."
    ),
    "set_tz_usage": "Reply with a timezone like `Europe/London`",
    "set_tz_ok": "Timezone set to `{tz}`",
    "del_usage": "Reply with the task id (number) you want to delete.",
    "del_id_num": "Task id must be a number, e.g. `42`",
    "not_found": "Not found.",
    "already_deleted": "That task is already deleted: {title} [id:{id}]",
    "deleted": "🗑️ Deleted: {title}",
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

#helpers

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
        f"{u['commands']}: `/menu`, `/settings`, `/tz`, `/list`, `/delete`, `/examples`, `/connect`, `/sync`, `/export csv|ics`\n\n"
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

async def settings_cmd_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = _u(context)
    mins = int(context.user_data.get("default_reminder", 10))
    connected = is_google_connected(update.effective_user.id)
    gline = u["settings_connected"] if connected else u["settings_disconnected"]
    txt = (
        f"{u['settings_title']}\n{u['settings_desc']}\n\n"
        f"{gline}\n{u['settings_rem_current'].format(mins=mins)}"
    )
    await update.message.reply_text(txt, reply_markup=_settings_kb(mins, connected), parse_mode="Markdown")

#Timezone picker & prompts

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
    await update.message.reply_text(u["tz_pick"], reply_markup=_tz_keyboard(u))

# “Plan my day” (balanced template)

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

# Handlers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = context.user_data.get("tz", "Africa/Lagos")
    u = _u(context)
    await update.message.reply_text(welcome_text(tz, u), parse_mode="Markdown", reply_markup=_menu_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(help_text(_u(context)), parse_mode="Markdown")

async def examples_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(examples_text(), parse_mode="Markdown")

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(_u(context)["menu_title"], reply_markup=_menu_keyboard())

async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("English", callback_data="setlang:en"),
         InlineKeyboardButton("Español", callback_data="setlang:es")],
        [InlineKeyboardButton("Français", callback_data="setlang:fr"),
         InlineKeyboardButton("Deutsch", callback_data="setlang:de")],
        [InlineKeyboardButton("Português", callback_data="setlang:pt"),
         InlineKeyboardButton("Italiano", callback_data="setlang:it")],
    ])
    await update.message.reply_text(_u(context)["lang_pick"], reply_markup=kb)

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = context.user_data.get("tz", "Africa/Lagos")
    msg = _render_task_list_for_user(update.effective_user.id, tz, _u(context))
    await update.message.reply_text(msg)

async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = _u(context)
    if not context.args:
        context.user_data["awaiting_delete"] = True
        await update.message.reply_text(u["del_usage"], reply_markup=ForceReply(selective=True))
        return

async def connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await connect_cmd_impl(update, context)

async def sync_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await sync_cmd_impl(update, context)

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await settings_cmd_impl(update, context)

async def tz_entry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # `/tz` without args → open picker
    await tz_cmd(update, context)

# Callback & text routing

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

    context.user_data.pop("pending_narration", None)
    await q.edit_message_text("Okay, not scheduled. You can send a new message or type /examples.")

async def handle_narration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = context.user_data.get("tz", "Africa/Lagos")
    text = update.message.text.strip()
    uid = update.effective_user.id
    u = _u(context)

    # Reply-prompt follow-ups
    if context.user_data.pop("awaiting_tz", False):
        context.user_data["tz"] = text
        await update.message.reply_text(u["set_tz_ok"].format(tz=text), parse_mode="Markdown")
        return
    if context.user_data.get("awaiting_delete", False):
        context.user_data["awaiting_delete"] = False
        try:
            tid = int(re.findall(r"\d+", text)[0])
        except Exception:
            await update.message.reply_text(u["del_id_num"], parse_mode="Markdown"); return
        s = get_session()
        t = s.query(TaskRow).get(tid)
        if not t or t.user_id != uid:
            await update.message.reply_text(u["not_found"]); return
        if t.status == "cancelled":
            await update.message.reply_text(u["already_deleted"].format(title=t.title, id=t.id)); return
        t.status = "cancelled"; s.commit()
        try: delete_google_event(t)
        except Exception: pass
        await update.message.reply_text(u["deleted"].format(title=t.title)); return

    # Quick menu shortcuts
    t = text.lower()
    if t in {"menu","/menu"}:
        await menu_cmd(update, context); return
    if t in {"settings","/settings","⚙️ settings"}:
        await settings_cmd_impl(update, context); return
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
    if t in {"➕ plan my day","/plan"}:
        narration = _balanced_day_narration()

        # Apply default reminder if user has one and they didn't specify explicitly
        default_rem = int(context.user_data.get("default_reminder", 10))
        if default_rem > 0 and "remind me" not in narration.lower():
            narration = narration.rstrip("; ") + f"; remind me {default_rem}m before"
        out = plan_and_schedule(narration, timezone=tz, telegram_user_id=uid)
        if out.scheduled_jobs > 0:
            try: sync_all_tasks_for_user(uid, tz)
            except Exception: pass
            await update.message.reply_text(u["plan_created"] + out.pretty_plan)
        else:
            await update.message.reply_text(u["cant_parse"] + "\n\n" + examples_text(), parse_mode="Markdown")
        return

    # Default reminder injection for free-form text
    default_rem = int(context.user_data.get("default_reminder", 10))
    if default_rem > 0 and re.search(r"\bremind me\b", text, re.I) is None:
        text = f"{text}, remind me {default_rem}m before"

    # Try Dobby tool routing first
    handled, reply = dobby_route(text, tz, uid)
    if handled and reply:
        await update.message.reply_text(reply, parse_mode="Markdown"); return

    # Plain chat?
    if _looks_like_question(text):
        reply = _llm_chat_reply(text, tz)
        await update.message.reply_text(reply, parse_mode="Markdown"); return

    # Direct schedule
    out = plan_and_schedule(text, timezone=tz, telegram_user_id=uid)
    if out.scheduled_jobs > 0:
        try: sync_all_tasks_for_user(uid, tz)
        except Exception: pass
        await update.message.reply_text(u["plan_created"] + out.pretty_plan); return

    # LLM fallback
    if _llm_on():
        try:
            plan = llm_parse(text, tz)
            if plan.tasks:
                preview = _pretty_preview(plan)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Schedule", callback_data="confirm_schedule"),
                     InlineKeyboardButton("✏️ Cancel", callback_data="cancel_schedule")]
                ])
                await update.message.reply_text("Here’s a plan I can schedule from that:\n" + preview + "\n\nSchedule it?", reply_markup=kb)
                return
        except Exception:
            pass

    await update.message.reply_text(u["cant_parse"] + "\n\n" + examples_text(), parse_mode="Markdown")

# Errors & app 

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled exception while processing update", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("Sorry, I hit a connection hiccup. Please try again.")
    except Exception:
        pass

def _build_application() -> Application:
    request = HTTPXRequest(connect_timeout=15.0, read_timeout=30.0, write_timeout=30.0, pool_timeout=5.0)
    return Application.builder().token(BOT_TOKEN).request(request).build()

async def _post_init(app: Application):
    cmds = [
        BotCommand("start","welcome"),
        BotCommand("menu","show quick menu"),
        BotCommand("settings","change reminder/language/timezone, connect Google"),
        BotCommand("help","how to use"),
        BotCommand("examples","copy-paste samples"),
        BotCommand("tz","pick a timezone"),
        BotCommand("list","list tasks"),
        BotCommand("delete","delete a task (ForceReply)"),
        BotCommand("connect","link Google Calendar"),
        BotCommand("sync","sync to Google Calendar"),
        BotCommand("export","export tasks (csv|ics)"),
        BotCommand("lang","language"),
        BotCommand("plan","balanced day plan"),
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
    app.add_handler(CommandHandler("plan", handle_narration))  # /plan triggers “Plan my day”
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_narration))
    app.add_error_handler(error_handler)
    app.post_init = _post_init

    print("DayPilot bot running…")
    app.run_polling()

if __name__ == "__main__":
    main()
