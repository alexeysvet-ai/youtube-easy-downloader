# === FILE: proxy_cron.py ===
# === BUILD: 20260329-04-CRON-LOGS ===

import requests
import os
import time

from utils import log  # [ADD] единый логгер

INPUT_FILE = "proxies.txt"
TEMP_FILE = "proxies.tmp"

MAX_GOOD_PROXIES = 5
TIMEOUT = 3


# === LOG PREFIX ===
CRON = "[CRON]"


def is_proxy_alive(proxy, idx, total):
    start = time.time()

    try:
        log(f"{CRON} [CHECK {idx}/{total}] proxy={proxy}")

        proxies = {
            "http": proxy,
            "https": proxy,
        }

        r = requests.get(
            "https://www.youtube.com/generate_204",
            proxies=proxies,
            timeout=TIMEOUT
        )

        elapsed = round(time.time() - start, 2)

        log(f"{CRON} [OK {idx}/{total}] proxy={proxy} status={r.status_code} time={elapsed}s")

        return r.status_code in (200, 204)

    except Exception as e:
        elapsed = round(time.time() - start, 2)

        log(f"{CRON} [FAIL {idx}/{total}] proxy={proxy} time={elapsed}s error={e}")

        return False


def load_proxies():
    try:
        with open(INPUT_FILE, "r") as f:
            proxies = [line.strip() for line in f if line.strip()]

        log(f"{CRON} [LOAD] loaded={len(proxies)} from {INPUT_FILE}")

        return proxies

    except Exception as e:
        log(f"{CRON} [LOAD ERROR] error={e}")
        return []


def save_proxies(proxies):
    try:
        with open(TEMP_FILE, "w") as f:
            for p in proxies:
                f.write(p + "\n")

        os.replace(TEMP_FILE, INPUT_FILE)

        log(f"{CRON} [SAVE] saved={len(proxies)} → {INPUT_FILE}")

    except Exception as e:
        log(f"{CRON} [SAVE ERROR] error={e}")


def run_proxy_refresh():
    start_total = time.time()

    log(f"{CRON} ===== START =====")

    proxies = load_proxies()
    alive = []

    total = len(proxies)

    if total == 0:
        log(f"{CRON} [EMPTY] no proxies to process")
        return

    for idx, proxy in enumerate(proxies, start=1):
        ok = is_proxy_alive(proxy, idx, total)

        if ok:
            alive.append(proxy)

        if len(alive) >= MAX_GOOD_PROXIES:
            log(f"{CRON} [STOP] collected={len(alive)} (limit reached)")
            break

    elapsed_total = round(time.time() - start_total, 2)

    log(f"{CRON} [RESULT] alive={len(alive)} checked={idx}/{total} time={elapsed_total}s")

    if alive:
        save_proxies(alive)
    else:
        log(f"{CRON} [SKIP] no alive proxies → keep old file")

    log(f"{CRON} ===== END =====")
