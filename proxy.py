import time
from config import PROXY_FILE, BLACKLIST_FILE, TTL_SHORT, TTL_MEDIUM, TTL_LONG
from utils import ensure_file

state = {}
blacklist = {}


def load_proxies():
    ensure_file(PROXY_FILE)
    with open(PROXY_FILE) as f:
        return [l.strip() for l in f if l.strip()]


def load_blacklist():
    ensure_file(BLACKLIST_FILE)
    with open(BLACKLIST_FILE) as f:
        for line in f:
            try:
                p, ts = line.strip().split("|")
                blacklist[p] = float(ts)
            except:
                continue


def save_blacklist():
    with open(BLACKLIST_FILE, "w") as f:
        for p, ts in blacklist.items():
            f.write(f"{p}|{ts}\n")


def score(p):
    s = state.get(p, {"s": 0, "f": 0})
    return s["s"] - s["f"]


def is_bad(p):
    return p in blacklist and time.time() < blacklist[p]


def mark_ok(p):
    s = state.setdefault(p, {"s": 0, "f": 0})
    s["s"] += 1


def mark_fail(p):
    s = state.setdefault(p, {"s": 0, "f": 0})
    s["f"] += 1


def ban(p, err):
    e = err.lower()
    ttl = TTL_SHORT
    if "403" in e:
        ttl = TTL_MEDIUM
    if "sign" in e:
        ttl = TTL_LONG

    blacklist[p] = time.time() + ttl
    save_blacklist()


def get():
    load_blacklist()
    proxies = load_proxies()
    proxies = sorted(proxies, key=score, reverse=True)
    return [p for p in proxies if not is_bad(p)]
