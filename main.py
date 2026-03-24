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

# ===================== LANG =====================

user_lang = {}

TEXTS = {
    "welcome": {
        "ru": "👋 Привет!\n\nЯ бот для скачивания видео и аудио.\n\n"
              "• YouTube — стабильно\n"
              "• VK — иногда работает\n"
              "• Mail.ru — иногда работает\n\n"
              "⚠️ VK и Mail.ru — дополнительные функции.\n\n"
              "Отправь ссылку 👇",

        "en": "👋 Hi!\n\nI download videos and audio.\n\n"
              "• YouTube — stable\n"
              "• VK — sometimes works\n"
              "• Mail.ru — sometimes works\n\n"
              "⚠️ VK and Mail.ru are experimental.\n\n"
              "Send a link 👇"
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
        "ru": "⚠️ Файл слишком большой (>50MB).\n\nЭто ограничение Telegram, а не бота.\nПопробуй выбрать более низкое качество или аудио 🙏",
        "en": "⚠️ File is too large (>50MB).\n\nThis is a Telegram limitation, not the bot.\nTry lower quality or audio 🙏"
    },
    "timeout": {
        "ru": "Слишком долго скачивается ⏱",
        "en": "Download timeout ⏱"
    },
    "error": {
        "ru": "Ошибка при загрузке ❌",
        "en": "Download error ❌"
    },
    "vk_error": {
        "ru": "⚠️ VK видео нестабильны\nПопробуй другое",
        "en": "⚠️ VK downloads unstable\nTry another video"
    },
    "mail_error": {
        "ru": "⚠️ Не удалось скачать с Mail.ru\nПопробуй другое или YouTube",
        "en": "⚠️ Failed to download from Mail.ru\nTry another or YouTube"
    }
}

def t(key, user_id):
    lang = user_lang.get(user_id, "ru")
    return TEXTS[key][lang]

# ===================== INIT =====================

if not TOKEN:
    raise ValueError("TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

user_requests = {}

# ===================== METRICS =====================

metrics = {
    "total": 0,
    "success": 0,
    "fail": 0,
    "timeouts": 0,
}

def success_rate():
    if metrics["total"] == 0:
        return 0
    return round(metrics["success"] / metrics["total"] * 100, 2)

# ===================== LOG =====================

def log(msg):
    print(msg, flush=True)

# ===================== FILE HELPERS =====================

def ensure_file(path):
    if not os.path.exists(path):
        open(path, "w").close()

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
    random.shuffle(active)

    return [None] + active[:5]

# ===================== HELPERS =====================

def get_service(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    elif "vk.com" in url:
        return "vk"
    elif "mail.ru" in url:
        return "mail"
    else:
        return "other"

def normalize_url(url: str) -> str:
    if "m.my.mail.ru" in url:
        return url.replace("m.my.mail.ru", "my.mail.ru")
    return url

def is_supported_url(url: str) -> bool:
    return any(x in url for x in [
        "youtube.com",
        "youtu.be",
        "vk.com",
        "mail.ru"
    ])

def cleanup_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except:
        pass

# ===================== DOWNLOAD =====================

def should_blacklist(error_text: str) -> bool:
    error_text = error_text.lower()
    return any(x in error_text for x in [
        "sign in",
        "confirm you’re not a bot",
        "403",
        "forbidden"
    ])

def download_video(url: str, mode: str):
    unique_id = uuid.uuid4().hex
    service = get_service(url)

    proxies = get_active_proxies() if service == "youtube" else [None]

    for proxy in proxies:
        try:
            if mode == "720":
                fmt = "best[ext=mp4][height<=720]/best"
            elif mode == "360":
                fmt = "best[ext=mp4][height<=360]/best"
            elif mode == "240":
                fmt = "best[ext=mp4][height<=240]/best"
            elif mode == "144":
                fmt = "best[ext=mp4][height<=144]/best"
            elif mode == "audio":
                fmt = "bestaudio/best"
            else:
                fmt = "best"

            ydl_opts = {
                "format": fmt,
                "outtmpl": f"/tmp/{unique_id}_%(id)s.%(ext)s",
                "noplaylist": True,
                "retries": 1,
                "socket_timeout": 20,
                "nocheckcertificate": True,
            }

            if proxy:
                ydl_opts["proxy"] = proxy

            if mode == "audio":
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        except Exception as e:
            if proxy and should_blacklist(str(e)):
                add_to_blacklist(proxy)
            continue

    raise Exception("fail")

async def safe_download(url, mode):
    async with semaphore:
        return await asyncio.wait_for(
            asyncio.to_thread(download_video, url, mode),
            timeout=DOWNLOAD_TIMEOUT
        )

# ===================== UI =====================

def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en"),
        ]
    ])

def quality_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎥 720p", callback_data="q_720"),
            InlineKeyboardButton(text="🎥 360p", callback_data="q_360"),
        ],
        [
            InlineKeyboardButton(text="🎥 240p", callback_data="q_240"),
            InlineKeyboardButton(text="🎥 144p", callback_data="q_144"),
        ],
        [
            InlineKeyboardButton(text="🎵 Audio", callback_data="q_audio")
        ]
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
    lang = callback.data.split("_")[1]
    user_lang[callback.from_user.id] = lang

    await callback.message.edit_text(t("welcome", callback.from_user.id))

@dp.message()
async def handle_video(message: types.Message):
    if not message.text:
        return

    user_id = message.from_user.id
    url = normalize_url(message.text.strip())

    if not is_supported_url(url):
        return

    user_requests[user_id] = url

    await message.answer(
        t("choose_format", user_id),
        reply_markup=quality_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith("q_"))
async def handle_quality(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    url = user_requests.get(user_id)
    if not url:
        return

    mode = callback.data.replace("q_", "")

    metrics["total"] += 1

    await callback.message.edit_text(t("downloading", user_id))

    file_path = None

    try:
        file_path = await safe_download(url, mode)

        if os.path.getsize(file_path) > MAX_FILE_SIZE:
            metrics["fail"] += 1
            await callback.message.answer(t("too_big", user_id))
            return

        if mode == "audio":
            await callback.message.answer_audio(types.FSInputFile(file_path))
        else:
            await callback.message.answer_video(types.FSInputFile(file_path))

        metrics["success"] += 1

    except asyncio.TimeoutError:
        metrics["timeouts"] += 1
        await callback.message.answer(t("timeout", user_id))
    except Exception:
        metrics["fail"] += 1

        service = get_service(url)

        if service == "vk":
            await callback.message.answer(t("vk_error", user_id))
        elif service == "mail":
            await callback.message.answer(t("mail_error", user_id))
        else:
            await callback.message.answer(t("error", user_id))

    finally:
        if file_path:
            cleanup_file(file_path)

        log(f"[METRICS][BUILD {BUILD_ID}] total={metrics['total']} success={metrics['success']} fail={metrics['fail']} timeouts={metrics['timeouts']} rate={success_rate()}%")

# ===================== WEB =====================

async def handle_webhook(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return web.Response(text="OK")

async def on_startup(app):
    log(f"[STARTUP][BUILD {BUILD_ID}]")
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
