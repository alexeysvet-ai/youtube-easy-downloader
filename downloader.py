# === FILE: downloader.py ===
# === BUILD: 20260329-02-PROXY-CLEAN ===

import uuid
import yt_dlp
import asyncio  # [KEEP]
import multiprocessing

# === CHANGE: requests больше не нужен (удалён) ===

from proxy import get_active_proxies, record_success, record_fail, proxy_score, add_to_blacklist
from utils import log


# === NEW FUNCTION: multiprocessing worker (KEEP) ===
def ytdlp_worker(q, url, ydl_opts):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            q.put((filename, info, None))
    except Exception as e:
        q.put((None, None, str(e)))


# === CHANGE START: удалены healthcheck и shortlist полностью ===
# удалено:
# - is_proxy_alive
# - pick_candidate_proxies
# === CHANGE END ===


# === MAIN DOWNLOAD FUNCTION ===
def download_video(url, mode):
    unique_id = uuid.uuid4().hex

    # === CHANGE START: используем все прокси как есть ===
    proxies = get_active_proxies()
    log(f"[PROXIES] loaded={len(proxies)}")
    # === CHANGE END ===

    if not proxies:
        raise Exception("No proxies available")

    fmt_map = {
        "720": "bestvideo[height<=720]+bestaudio/best",
        "360": "bestvideo[height<=360]+bestaudio/best",
        "240": "bestvideo[height<=240]+bestaudio/best",
        "144": "bestvideo[height<=144]+bestaudio/best",
        "audio": "bestaudio/best"
    }

    for idx, proxy in enumerate(proxies):
        try:
            log(f"[TRY {idx+1}/{len(proxies)}] proxy={proxy}")

            format_string = fmt_map.get(mode, "best")
            format_with_fallback = f"{format_string}/best"

            ydl_opts = {
                "format": format_with_fallback,
                "outtmpl": f"/tmp/{unique_id}_%(id)s.%(ext)s",
                "noplaylist": True,
                "retries": 0,
                "socket_timeout": 10,
                "nocheckcertificate": True,
                "force_ipv4": True,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"
                },
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "web"]
                    }
                },
            }

            if proxy:
                ydl_opts["proxy"] = proxy

            log(f"[PROXY USED] {proxy}")

            # === CHANGE START: multiprocessing timeout (KEEP) ===
            result_queue = multiprocessing.Queue()

            p = multiprocessing.Process(
                target=ytdlp_worker,
                args=(result_queue, url, ydl_opts)
            )

            p.start()
            p.join(15)

            if p.is_alive():
                p.terminate()
                p.join()
                raise TimeoutError("Proxy attempt timeout")

            filename, info, err = result_queue.get()

            if err:
                raise Exception(err)
            # === CHANGE END ===

            record_success(proxy)
            log(f"[SUCCESS] proxy={proxy} score={proxy_score(proxy)}")

            return filename, info

        except Exception as e:
            err = str(e)

            record_fail(proxy)
            log(f"[ERROR] proxy={proxy} score={proxy_score(proxy)} error={err}")

            # === KEEP: blacklist логика без изменений ===
            if proxy and (
                "402" in err or
                "Payment Required" in err or
                "403" in err or
                "ProxyError" in err or
                "tunnel connection failed" in err.lower()
            ):
                add_to_blacklist(proxy, err)

            log(f"[RETRY NEXT] after proxy={proxy}")

            continue

    raise Exception("All attempts failed")
