import time
import yt_dlp

from proxy import get, mark_ok, mark_fail, ban
import logger as log

MAX = 10


def _formats(mode):
    if mode == "audio":
        return ["bestaudio/best", "bestaudio"]
    return ["bestvideo+bestaudio/best", "best"]


def _classify_error(e):
    s = str(e).lower()

    if "timeout" in s:
        return "TIMEOUT"
    if "proxy" in s:
        return "PROXY"
    if "network" in s:
        return "NETWORK"

    return "YOUTUBE"


def download_video(url, mode, user):
    proxies = get()

    # fallback — если прокси нет
    if not proxies:
        proxies = [None]

    for i, p in enumerate(proxies[:MAX], 1):
        for fmt in _formats(mode):
            try:
                log.try_p(user, i, MAX, p)

                opts = {
                    "format": fmt,
                    "proxy": p,
                    "quiet": True,
                    "socket_timeout": 10,
                    "outtmpl": "/tmp/%(title)s.%(ext)s",
                }

                t0 = time.time()

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)

                path = ydl.prepare_filename(info)

                dt = time.time() - t0
                size = round(info.get("filesize", 0) / (1024 * 1024), 2)

                if p:
                    mark_ok(p)
                    log.proxy_used(user, p)

                log.success(user, p, size, dt)

                return path, info

            except Exception as e:
                err = str(e)
                etype = _classify_error(e)

                if p:
                    mark_fail(p)
                    ban(p, err)

                log.error(user, p, etype, err)

    raise Exception("All attempts failed")
