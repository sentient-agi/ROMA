from __future__ import annotations
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from .agent import plan_and_schedule
from .storage import get_session, TaskRow

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I’m DayPilot.\n"
        "Tell me your plan, e.g.\n"
        "“Weekdays 7am gym for 1h, remind me 15m before. Deep work 9–12. Lunch 1pm.”\n"
        "Set timezone with /tz Africa/Lagos"
    )

async def set_tz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /tz Africa/Lagos"); return
    context.user_data["tz"] = " ".join(context.args)
    await update.message.reply_text(f"Timezone set to {context.user_data['tz']}")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = get_session()
    items = s.query(TaskRow).filter(TaskRow.user_id==update.effective_user.id, TaskRow.status=="scheduled").all()
    if not items: await update.message.reply_text("No scheduled tasks."); return
    lines = [f"{i}. {t.title} — {(t.start.strftime('%a %H:%M') if t.start else 'from next recurrence')} [id:{t.id}]"
             for i,t in enumerate(items,1)]
    await update.message.reply_text("\n".join(lines))

async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: /delete <id>"); return
    s = get_session(); t = s.query(TaskRow).get(int(context.args[0]))
    if t and t.user_id == update.effective_user.id:
        t.status = "cancelled"; s.commit()
        await update.message.reply_text(f"🗑️ Deleted: {t.title}")
    else:
        await update.message.reply_text("Not found.")

async def handle_narration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = context.user_data.get("tz", "Africa/Lagos")
    out = plan_and_schedule(update.message.text, timezone=tz, telegram_user_id=update.effective_user.id)
    await update.message.reply_text("Plan created:\n"+out.pretty_plan)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tz", set_tz))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CommandHandler("delete", delete_task))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_narration))
    print("DayPilot bot running…"); app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
