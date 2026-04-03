import os
from datetime import datetime

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
YOUTUBE_TEST_VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
STAGE_MODE = os.getenv("STAGE_MODE", "false").lower() == "true"

ALLOWED_USER_IDS = set(
    int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x
)
ALERT_CHANNEL_ID = int(os.getenv("ALERT_CHANNEL_ID")) if os.getenv("ALERT_CHANNEL_ID") else None
