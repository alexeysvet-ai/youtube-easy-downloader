import time
import random

from config import PROXY_FILE, BLACKLIST_FILE, TTL_SHORT, TTL_MEDIUM, TTL_LONG
from bot_core.utils import ensure_file

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

    active.sort(key=lambda p: proxy_score(p), reverse=True)

    return active
