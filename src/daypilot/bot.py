from __future__ import annotations
import os, re, asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

from .agent import plan_and_schedule
from .storage import get_session, TaskRow
from .llm_parser import llm_parse
from .dobby_router import dobby_route, dobby_enabled 

BOT_TOKEN = os.getenv("BOT_TOKEN")
DAYPILOT_CHAT_MODEL = os.getenv("DAYPILOT_CHAT_MODEL", os.getenv("DAYPILOT_LLM_MODEL", "openrouter/anthropic/claude-sonnet-4"))

# helpers

def _llm_on() -> bool:
    use = os.getenv("DAYPILOT_USE_LLM", "1").lower() not in ("0", "false", "no")
    return bool(os.getenv("OPENROUTER_API_KEY")) and use

def _llm_chat_reply(prompt: str, tz: str) -> str:
    """Short helpful reply for general chat, powered by LiteLLM (OpenRouter)."""
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

def welcome_text(tz_hint: str = "Africa/Lagos") -> str:

    return (
        "👋 **Welcome to DayPilot**\n"
        "Plan your day and get reminders right here on Telegram.\n\n"
        "What you can do:\n"
        "• Create one-off or recurring tasks (weekdays, Mon/Wed/Fri, first Friday monthly)\n"
        "• Use relative times like “in 30 minutes”, “tomorrow 9–11”\n"
        "• Add reminders like “remind me 15m before”\n"
        "• List and delete tasks when needed\n\n"
        "Examples:\n"
        "• `Weekdays 7am gym for 1h, remind me 15m before`\n"
        "• `Tomorrow 9–11 deep work; lunch 1pm`\n"
        "• `In 30 minutes check the oven`\n"
        "• `Every weekend call mom at 6pm, remind me 10m before`\n\n"
        f"Timezone: default is `{tz_hint}`. Change anytime with `/tz Africa/Lagos` (or another IANA zone).\n"
        "Commands: `/tz <IANA>`, `/list`, `/delete <id>`, `/help`, `/examples`\n\n"
        "Ready when you are — just tell me your plan in one sentence"
    )

def help_text() -> str:
    return (
        "🆘 **Help**\n"
        "Send a sentence that mentions a time/relative time, optional duration, and (optionally) a reminder offset.\n\n"
        "Tips:\n"
        "• Time or relative time helps a lot (e.g., “tomorrow”, “in 20 minutes”).\n"
        "• Duration: “for 1h / 90m”.\n"
        "• Reminder: “remind me 15m before”.\n"
        "• Recurrence: “every weekday”, “Mon/Wed”, “first Friday monthly”."
    )

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

def _render_task_list_for_user(user_id: int, tz: str) -> str:
    s = get_session()
    items = (
        s.query(TaskRow)
        .filter(TaskRow.user_id == user_id, TaskRow.status == "scheduled")
        .order_by(TaskRow.start.is_(None), TaskRow.start.asc())
        .all()
    )
    if not items:
        return "You don’t have any scheduled items yet. Try `/examples` to get started."

    from collections import defaultdict
    groups = defaultdict(list)
    for t in items:
        key = t.start.date().isoformat() if t.start else "unscheduled"
        groups[key].append(t)

    lines = [f"📅 Your schedule ({tz})"]
    for key in sorted(groups.keys()):
        if key == "unscheduled":
            lines.append("\n— Unscheduled —")
        else:
            d = groups[key][0].start
            lines.append(f"\n{d.strftime('%a %b %d, %Y')}")
        for t in groups[key]:
            time_str = t.start.strftime('%H:%M') if t.start else "—"
            rec = " 🔁" if t.rrule else ""
            lines.append(f"• {time_str} — {t.title}{rec} (remind {t.reminder_offset_minutes}m) [id:{t.id}]")
    lines.append("\nTip: delete an item with `/delete <id>`.")
    return "\n".join(lines)

# handlers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = context.user_data.get("tz", "Africa/Lagos")
    await update.message.reply_text(welcome_text(tz), parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(help_text(), parse_mode="Markdown")

async def examples_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(examples_text(), parse_mode="Markdown")

async def set_tz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/tz Africa/Lagos`", parse_mode="Markdown"); return
    tz = " ".join(context.args)
    context.user_data["tz"] = tz
    await update.message.reply_text(f"Timezone set to `{tz}`", parse_mode="Markdown")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = context.user_data.get("tz", "Africa/Lagos")
    msg = _render_task_list_for_user(update.effective_user.id, tz)
    await update.message.reply_text(msg)

async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/delete <task_id>`", parse_mode="Markdown"); return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Task id must be a number, e.g. `/delete 42`", parse_mode="Markdown"); return
    s = get_session()
    t = s.query(TaskRow).get(tid)
    if t and t.user_id==update.effective_user.id:
        t.status="cancelled"; s.commit()
        await update.message.reply_text(f"🗑️ Deleted: {t.title}")
    else:
        await update.message.reply_text("Not found.")

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action = q.data
    if action == "confirm_schedule":
        tz = context.user_data.get("tz", "Africa/Lagos")
        narration = context.user_data.pop("pending_narration", None)
        if not narration:
            await q.edit_message_text("Nothing to schedule. Send a message to create a plan.")
            return
        out = plan_and_schedule(narration, timezone=tz, telegram_user_id=update.effective_user.id)
        await q.edit_message_text("✅ Plan created:\n" + out.pretty_plan)
    else:
        context.user_data.pop("pending_narration", None)
        await q.edit_message_text("Okay, not scheduled. You can send a new message or type /examples.")

async def handle_narration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = context.user_data.get("tz", "Africa/Lagos")
    text = update.message.text.strip()
    uid = update.effective_user.id


    handled, reply = dobby_route(text, tz, uid)
    if handled and reply:
        await update.message.reply_text(reply, parse_mode="Markdown")
        return


    if re.search(r"\b(list|show|view)\b.*\b(tasks|plans|schedule|agenda)\b", text, re.I) \
       or text.strip().lower() in {"list", "my plans", "show schedule"}:
        msg = _render_task_list_for_user(uid, tz)
        await update.message.reply_text(msg)
        return

  
    if _looks_like_question(text):
        reply = _llm_chat_reply(text, tz)
        await update.message.reply_text(reply, parse_mode="Markdown")
        return

  
    out = plan_and_schedule(text, timezone=tz, telegram_user_id=uid)
    if out.scheduled_jobs > 0:
        await update.message.reply_text("✅ Plan created:\n" + out.pretty_plan)
        return

 
    if _llm_on():
        try:
            plan = llm_parse(text, tz)
            if plan.tasks:
                preview = _pretty_preview(plan)
                context.user_data["pending_narration"] = text
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Schedule", callback_data="confirm_schedule"),
                     InlineKeyboardButton("✏️ Cancel", callback_data="cancel_schedule")]
                ])
                await update.message.reply_text(
                    "Here’s a plan I can schedule from that:\n" + preview + "\n\nSchedule it?",
                    reply_markup=kb
                )
                return
        except Exception:
            pass

   
    msg = (
        "I didn’t spot a schedulable task in that message.\n\n"
        "Try including a time (or relative time), a duration, or “remind me … before”.\n\n"
        "To see what’s already booked, send `list my plans` or use `/list`.\n\n"
        + examples_text()
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Put it in .env and `source .env` before running.")

  
    from telegram import Bot
    async def _check():
        me = await Bot(BOT_TOKEN).get_me()
        print(f"Authenticated as @{me.username} ({me.id})")
    asyncio.run(_check())

    app = Application.builder().token(BOT_TOKEN).build()
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("examples", examples_cmd))
    app.add_handler(CommandHandler("tz", set_tz))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("delete", delete_task))
    # Callbacks
    app.add_handler(CallbackQueryHandler(on_callback))
    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_narration))
    print("DayPilot bot running…")
    app.run_polling()

if __name__ == "__main__":
    main()
