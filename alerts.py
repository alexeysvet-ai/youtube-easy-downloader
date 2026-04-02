from aiogram import Bot
from datetime import datetime, timezone
from config import TOKEN, ALERT_CHANNEL_ID, STAGE_MODE
from utils import log

def build_download_fail_alert(user_id: int, url: str, mode: str, err: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    env_name = "stage" if STAGE_MODE else "prod"

    return (
        f"🚨 Download failed\n"
        f"env: {env_name}\n"
        f"time: {now}\n"
        f"user_id: {user_id}\n"
        f"mode: {mode}\n"
        f"url: {url}\n"
        f"error: {err}"
    )

async def send_alert(text: str):
    log(f"[ALERT DEBUG] chat_id={ALERT_CHANNEL_ID}")
    log(f"[ALERT DEBUG] token={TOKEN[:10]}")
    async with Bot(token=TOKEN) as bot_alert:
        await bot_alert.send_message(chat_id=ALERT_CHANNEL_ID, text=text)