# Youtube Easy Downloader — main.py (PROXY SCORING VERSION)

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

# ===================== LOG =====================

def log(msg):
    print(msg, flush=True)

# ===================== PROXY SCORING =====================

proxy_stats = {}

def record_success(proxy):
    if not proxy:
        return
    stat = proxy_stats.setdefault(proxy, {"ok": 0, "fail": 0})
    stat["ok"] += 1

def record_fail(proxy):
    if not proxy:
        return
    stat = proxy_stats.setdefault(proxy, {"ok": 0, "fail": 0})
    stat["fail"] += 1

def proxy_score(proxy):
    stat = proxy_stats.get(proxy)
    if not stat:
        return 0
    return stat["ok"] - stat["fail"]
    def ensure_file(path):
    if not os.path.exists(path):
        open(path, "w").close()


def normalize_proxy(proxy: str) -> str:
    if not proxy:
        return None

    proxy = proxy.strip()

    if proxy.startswith("http://") or proxy.startswith("https://"):
        return proxy

    return f"http://{proxy}"


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

    proxies = []
    with open(PROXY_FILE) as f:
        for line in f:
            p = line.strip()
            if not p:
                continue
            proxies.append(normalize_proxy(p))

    return proxies


def get_active_proxies():
    proxies = load_proxies()
    bl = load_blacklist()
    now = time.time()

    active = [p for p in proxies if p not in bl or bl[p] < now]

    # 🔥 СОРТИРОВКА ВМЕСТО RANDOM
    active.sort(key=lambda p: proxy_score(p), reverse=True)

    return active[:5]  # ❗ убрали direct
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
                "proxy": proxy,
                "force_ipv4": True,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"
                },
            }

            # 🔥 КЛЮЧЕВАЯ ПРОВЕРКА
            log(f"[PROXY USED] {proxy}")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

                record_success(proxy)
                log(f"[SUCCESS] proxy={proxy} score={proxy_score(proxy)}")

                return filename

        except Exception as e:
            err = str(e)

            record_fail(proxy)
            log(f"[ERROR] proxy={proxy} score={proxy_score(proxy)} error={err}")

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
