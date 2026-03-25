import time
import os

PROXY_FILE = "proxies.txt"

state = {}
blacklist = {}

SHORT, MEDIUM, LONG = 10, 60, 300


def load_proxies():
    if not os.path.exists(PROXY_FILE):
        return []

    with open(PROXY_FILE, "r") as f:
        lines = [l.strip() for l in f.readlines()]

    return [l for l in lines if l]


def score(p):
    s = state.get(p, {"s": 0, "f": 0})
    return s["s"] - s["f"]


def sorted_proxies(proxies):
    return sorted(proxies, key=score, reverse=True)


def is_bad(p):
    return p in blacklist and time.time() < blacklist[p]


def mark_ok(p):
    s = state.setdefault(p, {"s": 0, "f": 0})
    s["s"] += 1


def mark_fail(p):
    s = state.setdefault(p, {"s": 0, "f": 0})
    s["f"] += 1


def ban(p, err):
    ttl = SHORT
    e = err.lower()

    if "403" in e:
        ttl = MEDIUM
    if "sign" in e:
        ttl = LONG

    blacklist[p] = time.time() + ttl


def get():
    proxies = load_proxies()
    proxies = sorted_proxies(proxies)
    return [p for p in proxies if not is_bad(p)]
