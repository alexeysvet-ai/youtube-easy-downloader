import os
import asyncio
import uuid
import shutil
import random
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

# ===================== CONFIG =====================

TOKEN = os.getenv("TOKEN")
BASE_URL = os.getenv("BASE_URL")
PORT = int(os.getenv("PORT", 10000))

BUILD_ID = os.getenv("BUILD_ID") or datetime.utcnow().strftime("%Y%m%d-%H%M")

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}" if BASE_URL else None

MAX_FILE_SIZE = 50 * 1024 * 1024
DOWNLOAD_TIMEOUT = 60
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", 2))

PROXY_FILE = "proxies.txt"
BLACKLIST_FILE = "proxy_blacklist.txt"

# ===================== INIT =====================

if not TOKEN:
    raise ValueError("TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

# ===================== STATE =====================

user_lang = {}
user_requests = {}

# ===================== TEXTS =====================

TEXTS = {
    "welcome": {
        "ru": "👋 Привет! Отправь ссылку 👇",
        "en": "👋 Hi! Send a link 👇"
    },
    "choose_lang": {
        "ru": "Выбери язык:",
        "en": "Choose language:"
    },
    "choose_format": {
        "ru": "Выбери формат:",
        "en": "Choose format:"
    },
    "downloading": {
        "ru": "Скачиваю... ⏳",
        "en": "Downloading... ⏳"
    },
    "too_big": {
        "ru": "⚠️ Видео слишком большое (>50MB)\n\nЭто ограничение Telegram\n\nСсылка:\n",
        "en": "⚠️ File too large (>50MB)\n\nTelegram limitation\n\nLink:\n"
    },
    "error": {
        "ru": "Ошибка ❌",
        "en": "Error ❌"
    }
}

def t(key, user_id):
    lang = user_lang.get(user_id, "ru")
    return TEXTS[key][lang]

# ===================== METRICS =====================

metrics = {"total": 0, "success": 0, "fail": 0, "timeouts": 0}

def success_rate():
    return round(metrics["success"] / metrics["total"] * 100, 2) if metrics["total"] else 0

# ===================== LOG =====================

def log(msg):
    print(msg, flush=True)

# ===================== HELPERS =====================

def get_service(url):
    if "youtube" in url or "youtu.be" in url:
        return "youtube"
    if "vk.com" in url:
        return "vk"
    if "mail.ru" in url:
        return "mail"
    return "other"

def normalize_url(url):
    return url.replace("m.my.mail.ru", "my.mail.ru")

def is_supported_url(url):
    return any(x in url for x in ["youtube", "youtu.be", "vk.com", "mail.ru"])

def cleanup_file(path):
    if path and os.path.exists(path):
        os.remove(path)

# ===================== DOWNLOAD =====================

def download_video(url, mode):
    unique_id = uuid.uuid4().hex

    fmt_map = {
        "720": "best[height<=720]",
        "360": "best[height<=360]",
        "240": "best[height<=240]",
        "144": "best[height<=144]",
        "audio": "bestaudio/best"
    }

    ydl_opts = {
        "format": fmt_map.get(mode, "best"),
        "outtmpl": f"/tmp/{unique_id}_%(id)s.%(ext)s",
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

async def safe_download(url, mode):
    return await asyncio.wait_for(
        asyncio.to_thread(download_video, url, mode),
        timeout=DOWNLOAD_TIMEOUT
    )

# ===================== UI =====================

def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺", callback_data="lang_ru"),
         InlineKeyboardButton(text="🇺🇸", callback_data="lang_en")]
    ])

def quality_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="720p", callback_data="q_720"),
         InlineKeyboardButton(text="360p", callback_data="q_360")],
        [InlineKeyboardButton(text="240p", callback_data="q_240"),
         InlineKeyboardButton(text="144p", callback_data="q_144")],
        [InlineKeyboardButton(text="Audio", callback_data="q_audio")]
    ])

# ===================== HANDLERS =====================

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        TEXTS["choose_lang"]["ru"] + " / " + TEXTS["choose_lang"]["en"],
        reply_markup=lang_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith("lang_"))
async def set_lang(callback: types.CallbackQuery):
    user_lang[callback.from_user.id] = callback.data.split("_")[1]
    await callback.message.edit_text(t("welcome", callback.from_user.id))

@dp.message()
async def handle_video(message: types.Message):
    user_id = message.from_user.id
    url = normalize_url(message.text.strip())

    if not is_supported_url(url):
        return

    user_requests[user_id] = url

    await message.answer(t("choose_format", user_id), reply_markup=quality_keyboard())

@dp.callback_query(lambda c: c.data.startswith("q_"))
async def handle_quality(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    url = user_requests.get(user_id)
    mode = callback.data.split("_")[1]

    metrics["total"] += 1

    await callback.message.edit_text(t("downloading", user_id))

    file_path = None

    try:
        file_path = await safe_download(url, mode)

        size = os.path.getsize(file_path)

        if size > MAX_FILE_SIZE:
            metrics["fail"] += 1
            await callback.message.answer(t("too_big", user_id) + url)
            return

        await callback.message.answer_video(types.FSInputFile(file_path))
        metrics["success"] += 1

    except:
        metrics["fail"] += 1
        await callback.message.answer(t("error", user_id))

    finally:
        cleanup_file(file_path)

        log(f"[METRICS][BUILD {BUILD_ID}] total={metrics['total']} success={metrics['success']} fail={metrics['fail']} rate={success_rate()}%")

# ===================== WEB =====================

async def handle_webhook(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return web.Response(text="OK")

async def on_startup(app):
    log(f"[START][BUILD {BUILD_ID}]")
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)

def create_app():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    app.on_startup.append(on_startup)
    return app

# ===================== MAIN =====================

if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
