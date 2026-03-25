import uuid
import yt_dlp

from proxy import get_active_proxies, record_success, record_fail, proxy_score, add_to_blacklist
from utils import log

def download_video(url, mode):
    unique_id = uuid.uuid4().hex
    proxies = get_active_proxies()

    if not proxies:
        raise Exception("No proxies available")

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
                "force_ipv4": True,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"
                },

                # 🔥 ВАЖНО: улучшение обхода YouTube
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

                return filename

        except Exception as e:
            err = str(e)

            record_fail(proxy)
            log(f"[ERROR] proxy={proxy} score={proxy_score(proxy)} error={err}")

            if proxy:
                add_to_blacklist(proxy, err)

            continue

    raise Exception("All attempts failed")
