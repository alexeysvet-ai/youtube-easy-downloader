import os
import asyncio
import uuid
import shutil
import random
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

# ===================== CONFIG =====================

TOKEN = os.getenv("TOKEN")
BASE_URL = os.getenv("BASE_URL")
PORT = int(os.getenv("PORT", 10000))

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}" if BASE_URL else None

MAX_FILE_SIZE = 50 * 1024 * 1024
DOWNLOAD_TIMEOUT = 60
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", 2))

PROXY_FILE = "proxies.txt"
BLACKLIST_FILE = "proxy_blacklist.txt"

WELCOME_TEXT = (
    "👋 Привет!\n\n"
    "Это простой бот для скачивания видео с YouTube.\n\n"
    "🚫 Без рекламы и лишних действий.\n\n"
    "⚠️ Бот сейчас тестируется, возможны задержки.\n\n"
    "Просто отправь ссылку 👇"
)

if not TOKEN:
    raise ValueError("TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

# временное хранилище
user_requests = {}

# ===================== LOG =====================

def log(msg):
    print(msg, flush=True)

# ===================== FILE HELPERS =====================

def ensure_file(path):
    if not os.path.exists(path):
        open(path, "w").close()
        log(f"[FILE CREATED] {path}")

def load_proxies():
    ensure_file(PROXY_FILE)
    with open(PROXY_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def load_blacklist():
    ensure_file(BLACKLIST_FILE)
    with open(BLACKLIST_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def add_to_blacklist(proxy):
    if not proxy:
        return

    blacklist = load_blacklist()
    if proxy in blacklist:
        return

    with open(BLACKLIST_FILE, "a") as f:
        f.write(proxy + "\n")

def get_active_proxies():
    proxies = load_proxies()
    blacklist = load_blacklist()

    active = [p for p in proxies if p not in blacklist]
    result = [None] + active
    random.shuffle(result)

    return result[:5]

# ===================== DOWNLOAD =====================

def should_blacklist(error_text: str) -> bool:
    error_text = error_text.lower()
    return any(x in error_text for x in [
        "sign in",
        "confirm you’re not a bot",
        "403",
        "forbidden"
    ])

def download_video(url: str, mode: str = "360") -> str:
    unique_id = uuid.uuid4().hex
    proxies = get_active_proxies()

    for proxy in proxies:
        try:
            if mode == "720":
                fmt = "best[ext=mp4][height<=720]/best"
            elif mode == "audio":
                fmt = "bestaudio/best"
            else:
                fmt = "best[ext=mp4][height<=480]/best"

            ydl_opts = {
                "format": fmt,
                "outtmpl": f"/tmp/{unique_id}_%(id)s.%(ext)s",
                "noplaylist": True,
                "retries": 1,
                "fragment_retries": 1,
                "socket_timeout": 20,
                "nocheckcertificate": True,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"
                },
            }

            if mode == "audio":
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]

            if proxy:
                ydl_opts["proxy"] = proxy

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        except Exception as e:
            if proxy and should_blacklist(str(e)):
                add_to_blacklist(proxy)
            continue

    raise Exception("All proxies failed")

async def safe_download(url: str, mode: str) -> str:
    async with semaphore:
        return await asyncio.wait_for(
            asyncio.to_thread(download_video, url, mode),
            timeout=DOWNLOAD_TIMEOUT
        )

# ===================== HANDLERS =====================

def quality_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎥 360p", callback_data="q_360"),
            InlineKeyboardButton(text="🎥 720p", callback_data="q_720"),
        ],
        [
            InlineKeyboardButton(text="🎵 Аудио (mp3)", callback_data="q_audio")
        ]
    ])

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(WELCOME_TEXT)

@dp.message()
async def handle_video(message: types.Message):
    if not message.text:
        return

    url = message.text.strip()

    if "youtube.com" not in url and "youtu.be" not in url:
        await message.answer("Это не ссылка на YouTube")
        return

    user_requests[message.from_user.id] = url

    await message.answer(
        "Выбери формат:",
        reply_markup=quality_keyboard()
    )

@dp.callback_query()
async def handle_quality(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    if user_id not in user_requests:
        await callback.answer("Ссылка устарела", show_alert=True)
        return

    url = user_requests[user_id]

    mode = callback.data.replace("q_", "")

    await callback.message.edit_text("Скачиваю... ⏳")

    file_path = None

    try:
        file_path = await safe_download(url, mode)

        if not os.path.exists(file_path):
            raise RuntimeError("Файл не создан")

        if os.path.getsize(file_path) > MAX_FILE_SIZE:
            await callback.message.answer("Файл слишком большой (>50MB)")
            return

        if mode == "audio":
            await callback.message.answer_audio(types.FSInputFile(file_path))
        else:
            await callback.message.answer_video(types.FSInputFile(file_path))

    except Exception as e:
        log(f"[ERROR] {e}")
        await callback.message.answer("Ошибка при загрузке ❌")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

# ===================== WEB =====================

async def handle_webhook(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return web.Response(text="OK")

async def on_startup(app):
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)

async def health(request):
    return web.Response(text="OK")

def create_app():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", health)
    app.on_startup.append(on_startup)
    return app

# ===================== MAIN =====================

if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=PORT)
