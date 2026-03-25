# Youtube Easy Downloader — main.py (Canvas version)
# UX: separate status messages (no edit), no duplicate error messages

import os
import asyncio
import uuid
import random
import time
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

BUILD_ID = datetime.utcnow().strftime("%Y%m%d-%H%M")

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}" if BASE_URL else None

MAX_FILE_SIZE = 50 * 1024 * 1024
DOWNLOAD_TIMEOUT = 60
MAX_CONCURRENT_DOWNLOADS = 1

PROXY_FILE = "proxies.txt"
BLACKLIST_FILE = "proxy_blacklist.txt"

TTL_SHORT = 300
TTL_MEDIUM = 1800
TTL_LONG = 3600

# ===================== INIT =====================

if not TOKEN:
    raise ValueError("TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

user_lang = {}
user_requests = {}

# ===================== TEXTS =====================

TEXTS = {
    "welcome": {"ru": "👋 Привет! Отправь ссылку 👇", "en": "👋 Hi! Send a link 👇"},
    "choose_lang": {"ru": "Выбери язык:", "en": "Choose language:"},
    "choose_format": {"ru": "Выбери формат:", "en": "Choose format:"},

    "start": {
        "ru": "🔍 Начинаю обработку...",
        "en": "🔍 Starting..."
    },

    "status_1": {
        "ru": "🌐 Подбираю рабочий прокси...",
        "en": "🌐 Selecting proxy..."
    },
    "status_2": {
        "ru": "🛡 Обхожу ограничения YouTube...",
        "en": "🛡 Bypassing restrictions..."
    },
    "status_3": {
        "ru": "⬇️ Загружаю видео...",
        "en": "⬇️ Downloading..."
    },

    "success": {
        "ru": "✅ Готово!",
        "en": "✅ Done!"
    },

    "too_big": {
        "ru": "⚠️ Видео слишком большое (>50MB)\n\nЭто ограничение Telegram\n\nСсылка:\n",
        "en": "⚠️ File too large (>50MB)\n\nTelegram limitation\n\nLink:\n"
    },

    "error": {
        "ru": "😔 К сожалению, сейчас не удалось скачать видео.\n\n"
              "Я попробовал несколько способов, но сервис временно блокирует загрузку.\n\n"
              "Попробуй чуть позже 🙏",
        "en": "😔 Failed to download.\n\nTry again later 🙏"
    }
}

def t(key, user_id):
    return TEXTS[key][user_lang.get(user_id, "ru")]

# ===================== LOG =====================

def log(msg):
    print(msg, flush=True)

# ===================== FILE =====================

def ensure_file(path):
    if not os.path.exists(path):
        open(path, "w").close()

# ===================== PROXY =====================

def load_blacklist():
    ensure_file(BLACKLIST_FILE)
    result = {}

    with open(BLACKLIST_FILE, "r") as f:
        for line in f:
            if "|" in line:
                proxy, ts = line.strip().split("|")
                result[proxy] = float(ts)

    return result


def save_blacklist(data):
    with open(BLACKLIST_FILE, "w") as f:
        for proxy, ts in data.items():
            f.write(f"{proxy}|{ts}\n")


def get_ttl(error_text: str) -> int:
    error_text = error_text.lower()

    if "sign in" in error_text:
        return TTL_LONG
    if "403" in error_text or "forbidden" in error_text:
        return TTL_MEDIUM
    return TTL_SHORT


def add_to_blacklist(proxy, error_text):
    if not proxy:
        return

    bl = load_blacklist()
    ttl = get_ttl(error_text)
    bl[proxy] = time.time() + ttl
    save_blacklist(bl)


def load_proxies():
    ensure_file(PROXY_FILE)
    with open(PROXY_FILE) as f:
        return [x.strip() for x in f if x.strip()]


def get_active_proxies():
    proxies = load_proxies()
    bl = load_blacklist()
    now = time.time()

    active = [p for p in proxies if p not in bl or bl[p] < now]
    random.shuffle(active)

    # try direct first
    return [None] + active[:5]

# ===================== DOWNLOAD =====================

def download_video(url, mode):
    unique_id = uuid.uuid4().hex
    proxies = get_active_proxies()

    fmt_map = {
        "720": "best[height<=720]",
        "360": "best[height<=360]",
        "240": "best[height<=240]",
        "144": "best[height<=144]",
        "audio": "bestaudio/best"
    }

    for idx, proxy in enumerate(proxies):
        try:
            log(f"[TRY {idx+1}/{len(proxies)}] proxy={proxy}")

            ydl_opts = {
                "format": fmt_map.get(mode, "best"),
                "outtmpl": f"/tmp/{unique_id}_%(id)s.%(ext)s",
                "noplaylist": True,
                "retries": 2,
                "socket_timeout": 20,
                "nocheckcertificate": True,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"
                },
            }

            if proxy:
                ydl_opts["proxy"] = proxy

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                return filename

        except Exception as e:
            err = str(e)
            log(f"[ERROR] proxy={proxy} error={err}")
            if proxy:
                add_to_blacklist(proxy, err)
            continue

    raise Exception("All attempts failed")


async def safe_download(url, mode):
    async with semaphore:
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
    url = (message.text or "").strip()

    user_requests[user_id] = url
    await message.answer(t("choose_format", user_id), reply_markup=quality_keyboard())


@dp.callback_query(lambda c: c.data.startswith("q_"))
async def handle_quality(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    url = user_requests.get(user_id)
    mode = callback.data.split("_")[1]

    # Start message
    await callback.message.answer(t("start", user_id))

    # Progress messages (no edit, separate messages)
    await callback.message.answer(t("status_1", user_id))
    await asyncio.sleep(1)
    await callback.message.answer(t("status_2", user_id))
    await asyncio.sleep(1)
    await callback.message.answer(t("status_3", user_id))

    file_path = None

    try:
        file_path = await safe_download(url, mode)

        if not file_path or not os.path.exists(file_path):
            raise RuntimeError("File not created")

        size = os.path.getsize(file_path)
        log(f"[FILE SIZE] {size}")

        if size > MAX_FILE_SIZE:
            await callback.message.answer(t("too_big", user_id) + url)
            return

        # Final success message (single, no duplicates)
        await callback.message.answer(t("success", user_id))

        if mode == "audio":
            await callback.message.answer_audio(types.FSInputFile(file_path))
        else:
            await callback.message.answer_video(types.FSInputFile(file_path))

    except asyncio.TimeoutError:
        await callback.message.answer(t("error", user_id))
    except Exception as e:
        log(f"[FINAL ERROR] {e}")
        await callback.message.answer(t("error", user_id))
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                log(f"[CLEANUP ERROR] {e}")

# ===================== WEB =====================

async def handle_webhook(request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.feed_update(bot, update)
    except Exception as e:
        log(f"[WEBHOOK ERROR] {e}")
    return web.Response(text="OK")


async def on_startup(app):
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)


def create_app():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    app.on_startup.append(on_startup)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
