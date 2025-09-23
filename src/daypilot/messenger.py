from __future__ import annotations
import os, asyncio
from telegram import Bot

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def _send(user_id: int, text: str):
    bot = Bot(BOT_TOKEN)
    await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown", disable_notification=False)

def send_telegram(user_id: int, text: str):
    if not BOT_TOKEN or not user_id:
        return
    asyncio.run(_send(user_id, text))
