import aiohttp
from datetime import datetime, timezone
from utils import log

async def send_alert(bot_token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log(f"[ALERT ERROR] status={resp.status} body={body}")
    except Exception as e:
        log(f"[ALERT ERROR] {e}")


def build_download_fail_alert(user_id: int, url: str, mode: str, err: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        "🚨 Download failed\n"
        f"time: {ts}\n"
        f"user_id: {user_id}\n"
        f"mode: {mode}\n"
        f"url: {url}\n"
        f"error: {err}"
    )