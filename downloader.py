# === FILE: downloader.py ===
# === BUILD: 20260329-03-P0-FIX ===

import uuid
import yt_dlp
import asyncio  # [KEEP]
import multiprocessing
from config import YOUTUBE_TEST_VIDEO_URL  # [ADD]
from config import DOWNLOAD_TIMEOUT

from proxy import get_active_proxies, record_success, record_fail, proxy_score, add_to_blacklist
from utils import log
from queue import Empty


# === NEW: proxy block detection (P0 FIX) ===
def is_proxy_block_error(err: str) -> bool:
    err = err.lower()
    return (
        "429" in err or
        "too many requests" in err or
        "confirm you’re not a bot" in err or
        "confirm you're not a bot" in err or
        "sign in to confirm" in err
    )


# === NEW FUNCTION: multiprocessing worker (KEEP) ===
def ytdlp_worker(q, url, ydl_opts):
    try:
        print("[WORKER] before YoutubeDL")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("[WORKER] before extract_info")
            info = ydl.extract_info(url, download=True)
            print("[WORKER] after extract_info")

            filename = ydl.prepare_filename(info)
            print(f"[WORKER] prepared filename={filename}")

            print("[WORKER] before q.put success")
            q.put((filename, info, None))
            print("[WORKER] after q.put success")
    except Exception as e:
        print(f"[WORKER] exception before error q.put: {e}")
        q.put((None, None, str(e)))
        print("[WORKER] after q.put error")

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
            log("[PARENT] after p.start")

            p.join(DOWNLOAD_TIMEOUT)
            log("[PARENT] after p.join")

            alive = p.is_alive()
            log(f"[PARENT] p.is_alive={alive}")

            if alive:
                try:
                    log("[PARENT] before get_nowait timeout-branch")
                    filename, info, err = result_queue.get_nowait()
                    log("[PARENT] after get_nowait timeout-branch")
                except Empty:
                    log("[PARENT] queue empty in timeout-branch")

                    log("[PARENT] before p.terminate")
                    p.terminate()
                    log("[PARENT] after p.terminate")

                    p.join()
                    log("[PARENT] after p.join post-terminate")

                    raise TimeoutError("Proxy attempt timeout")
                else:
                    log("[PARENT] got result before terminate")

                    log("[PARENT] before p.terminate")
                    p.terminate()
                    log("[PARENT] after p.terminate")

                    p.join()
                    log("[PARENT] after p.join post-terminate")
            else:
                try:
                    log("[PARENT] before get_nowait normal-branch")
                    filename, info, err = result_queue.get_nowait()
                    log("[PARENT] after get_nowait normal-branch")
                except Empty:
                    log("[PARENT] queue empty in normal-branch")
                    raise Exception("Worker finished without result")
            log(f"[PARENT] err is {'set' if err else 'empty'}")

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

            # === CHANGE: extended blacklist (P0 FIX) ===
            if proxy and (
                "402" in err or
                "payment required" in err.lower() or
                "403" in err or
                "proxyerror" in err.lower() or
                "tunnel connection failed" in err.lower() or
                is_proxy_block_error(err)
            ):
                add_to_blacklist(proxy, err)

            log(f"[RETRY NEXT] after proxy={proxy}")

            continue

    # === CHANGE: fallback without proxy (P0 FIX) ===
    try:
        log("[FALLBACK] trying without proxy")

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

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        log("[FALLBACK SUCCESS] no proxy used")

        return filename, info

    except Exception as e:
        log(f"[FALLBACK ERROR] {e}")

    raise Exception("All attempts failed")
