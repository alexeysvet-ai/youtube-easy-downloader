import uuid
import yt_dlp
import asyncio  # [ADD] требуется для create_task, если используется в проекте

from proxy import get_active_proxies, record_success, record_fail, proxy_score, add_to_blacklist
from utils import log

def download_video(url, mode):
    unique_id = uuid.uuid4().hex
    proxies = get_active_proxies()

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

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

                record_success(proxy)
                log(f"[SUCCESS] proxy={proxy} score={proxy_score(proxy)}")

                return filename, info

        except Exception as e:
            err = str(e)

            record_fail(proxy)
            log(f"[ERROR] proxy={proxy} score={proxy_score(proxy)} error={err}")

            # [CHANGE] blacklist только для реальных proxy-ошибок
            if proxy and (
                "402" in err or
                "Payment Required" in err or
                "403" in err or
                "ProxyError" in err or
                "tunnel connection failed" in err.lower()
            ):
                add_to_blacklist(proxy, err)

            # [CHANGE] явный лог перехода к следующей попытке
            log(f"[RETRY NEXT] after proxy={proxy}")

            continue

    raise Exception("All attempts failed")
