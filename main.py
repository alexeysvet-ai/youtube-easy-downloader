import os
import asyncio
import logging
import uuid
import shutil
import random
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

MAX_FILE_SIZE = 50 * 1024 * 1024
DOWNLOAD_TIMEOUT = 180
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", 2))

PROXY_FILE = "proxies.txt"
BLACKLIST_FILE = "proxy_blacklist.txt"

# 🟡 режим тестирования
TEST_MODE = False

MAINTENANCE_TEXT = (
    "🚧 Бот скоро заработает\n\n"
    "Сейчас мы тестируем загрузку видео.\n"
    "Попробуйте чуть позже 🙏"
)

if not TOKEN:
    raise ValueError("TOKEN not set")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

# ===================== FILE HELPERS =====================

def ensure_file(path):
    if not os.path.exists(path):
        open(path, "w").close()
        logging.info(f"[FILE CREATED] {path}")

def load_proxies():
    ensure_file(PROXY_FILE)
    with open(PROXY_FILE, "r") as f:
        proxies = [line.strip() for line in f if line.strip()]
    logging.info(f"[PROXIES LOADED] count={len(proxies)}")
    return proxies

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

    logging.warning(f"[BLACKLIST ADDED] {proxy}")

def get_active_proxies():
    proxies = load_proxies()
    blacklist = load_blacklist()

    active = [p for p in proxies if p not in blacklist]

    result = [None] + active
    random.shuffle(result)

    logging.info(f"[ACTIVE PROXIES] total={len(result)}")
    return result

# ===================== HEALTH =====================

def self_check():
    logging.info("Running startup checks...")

    if not shutil.which("ffmpeg"):
        logging.warning("ffmpeg not found")

    test_path = f"/tmp/test_{uuid.uuid4().hex}.txt"
    with open(test_path, "w") as f:
        f.write("ok")
    os.remove(test_path)

    logging.info("Startup checks passed")

# ===================== DOWNLOAD =====================

def should_blacklist(error_text: str) -> bool:
    error_text = error_text.lower()
    return any(x in error_text for x in [
        "sign in",
        "confirm you’re not a bot",
        "403",
        "forbidden"
    ])

def download_video(url: str) -> str:
    unique_id = uuid.uuid4().hex
    proxies = get_active_proxies()

    logging.info(f"[DOWNLOAD START] url={url}")

    errors = []

    for idx, proxy in enumerate(proxies):
        try:
            logging.info(f"[TRY {idx+1}/{len(proxies)}] proxy={proxy}")

            ydl_opts = {
                "format": "best[ext=mp4][height<=480]/best[ext=mp4]/best",
                "outtmpl": f"/tmp/{unique_id}_%(id)s.%(ext)s",
                "noplaylist": True,
                "quiet": False,
                "retries": 2,
                "socket_timeout": 20,
                "nocheckcertificate": True,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"
                },
                "logger": logging.getLogger("yt_dlp"),
            }

            if proxy:
                ydl_opts["proxy"] = proxy

            logging.info(f"[YTDLP START] proxy={proxy}")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

                logging.info(f"[YTDLP SUCCESS] proxy={proxy}")

                filename = ydl.prepare_filename(info)
                logging.info(f"[FILE SAVED] {filename}")

                return filename

        except Exception as e:
            err = str(e)
            logging.error(f"[ERROR] proxy={proxy} error={err}")

            if proxy and should_blacklist(err):
                add_to_blacklist(proxy)

            errors.append(f"{proxy} -> {err}")
            continue

    logging.error("[ALL PROXIES FAILED]")
    raise Exception("All proxies failed:\n" + "\n".join(errors))

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
            logging.info(f"[FILE REMOVED] {path}")
    except Exception as e:
        logging.warning(f"Cleanup failed: {e}")

# ===================== HANDLERS =====================

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(MAINTENANCE_TEXT)

@dp.message(Command("startdownloadtest"))
async def enable_test_mode(message: types.Message):
    global TEST_MODE
    TEST_MODE = True
    logging.info("[TEST MODE ENABLED]")
    await message.answer("✅ Тестовый режим включён. Теперь можно отправлять ссылки.")

@dp.message()
async def handle_video(message: types.Message):
    if not TEST_MODE:
        await message.answer(MAINTENANCE_TEXT)
        return

    if not message.text:
        await message.answer("Нужна текстовая ссылка")
        return

    url = message.text.strip()
    user_id = message.from_user.id

    logging.info(f"[REQUEST] user={user_id} url={url}")

    if not is_youtube_url(url):
        await message.answer("Это не ссылка на YouTube")
        return

    await message.answer("Скачиваю... ⏳")

    file_path = None

    try:
        file_path = await safe_download(url)

        if not file_path or not os.path.exists(file_path):
            raise RuntimeError("Файл не создан")

        size = os.path.getsize(file_path)

        logging.info(f"[FILE SIZE] {size}")

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
        logging.warning("BASE_URL not set")

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
