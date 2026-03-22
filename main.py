import os
import asyncio
import logging
import uuid
import shutil
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import yt_dlp

# ===================== CONFIG =====================

TOKEN = os.getenv("TOKEN")
BASE_URL = os.getenv("BASE_URL")
PORT = int(os.getenv("PORT", 10000))

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}" if BASE_URL else None

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB Telegram limit
DOWNLOAD_TIMEOUT = 180  # seconds
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", 2))

if not TOKEN:
    raise ValueError("TOKEN not set")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ограничение параллельных загрузок
semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

# ===================== HEALTH / SELF-CHECK =====================

def self_check():
    logging.info("Running startup checks...")

    # ffmpeg check
    if not shutil.which("ffmpeg"):
        logging.warning("ffmpeg not found — some formats may fail")

    # tmp writable check
    test_path = f"/tmp/test_{uuid.uuid4().hex}.txt"
    try:
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
    except Exception:
        raise RuntimeError("/tmp is not writable")

    logging.info("Startup checks passed")


# ===================== DOWNLOAD =====================

def download_video(url: str) -> str:
    unique_id = uuid.uuid4().hex

    ydl_opts = {
    "format": "best[ext=mp4][height<=480]/best[ext=mp4]/best",
    "outtmpl": f"/tmp/{unique_id}_%(id)s.%(ext)s",
    "noplaylist": True,
    "quiet": True,
    "retries": 5,
    "socket_timeout": 30,
    "nocheckcertificate": True,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    }
}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    return filename


async def safe_download(url: str) -> str:
    async with semaphore:
        return await asyncio.wait_for(
            asyncio.to_thread(download_video, url),
            timeout=DOWNLOAD_TIMEOUT
        )


# ===================== HELPERS =====================

def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def cleanup_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        logging.warning(f"Failed to remove file {path}: {e}")


# ===================== HANDLERS =====================

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Пришли ссылку на YouTube 🎬")


@dp.message()
async def handle_video(message: types.Message):
    if not message.text:
        await message.answer("Нужна текстовая ссылка")
        return

    url = message.text.strip()
    user_id = message.from_user.id

    logging.info(f"{user_id} -> {url}")

    if not is_youtube_url(url):
        await message.answer("Это не ссылка на YouTube")
        return

    await message.answer("Скачиваю... ⏳")

    file_path = None

    try:
        file_path = await safe_download(url)

        if not file_path or not os.path.exists(file_path):
            raise RuntimeError("Файл не был создан")

        size = os.path.getsize(file_path)

        if size > MAX_FILE_SIZE:
            await message.answer("Файл слишком большой (>50MB)")
            return

        await message.answer_video(types.FSInputFile(file_path))

    except asyncio.TimeoutError:
        await message.answer("Слишком долго скачивается ⏱")
    except Exception as e:
        logging.exception(e)
        await message.answer("Ошибка при загрузке ❌")
    finally:
        if file_path:
            cleanup_file(file_path)


# ===================== WEBHOOK =====================

async def handle_webhook(request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.exception(f"Webhook error: {e}")
    return web.Response(text="OK")


# ===================== STARTUP =====================

async def on_startup(app):
    self_check()

    if WEBHOOK_URL:
        logging.info(f"Setting webhook: {WEBHOOK_URL}")
        await bot.set_webhook(WEBHOOK_URL)
    else:
        logging.warning("BASE_URL not set — webhook not configured")


# ===================== HEALTH =====================

async def health(request):
    return web.Response(text="OK")


# ===================== APP =====================

def create_app():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", health)
    app.on_startup.append(on_startup)
    return app


# ===================== MAIN =====================

if __name__ == "__main__":
    app = create_app()
    logging.info(f"Starting server on port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)
