import os

# --- Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 8000))

BASE_URL = os.getenv("BASE_URL", "")
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}" if BASE_URL else None

# --- Download ---
DOWNLOAD_TIMEOUT = 60
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# --- Proxy ---
PROXY_FILE = "proxies.txt"
BLACKLIST_FILE = "blacklist.txt"

TTL_SHORT = 10
TTL_MEDIUM = 60
TTL_LONG = 300
