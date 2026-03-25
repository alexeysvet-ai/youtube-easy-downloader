import time
import yt_dlp

from proxy import get, mark_ok, mark_fail, ban
import logger as log

MAX = 10


def download_video(url, mode, user):
    proxies = get()

    for i, p in enumerate(proxies[:MAX], 1):
        try:
            log.try_p(user, i, MAX, p)

            opts = {
                "format": "bestaudio/best" if mode == "audio" else "best",
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

            mark_ok(p)
            log.proxy_used(user, p)
            log.success(user, p, size, dt)

            return path, info

        except Exception as e:
            err = str(e)
            mark_fail(p)
            ban(p, err)
            log.error(user, p, "YOUTUBE", err)

    raise Exception("All attempts failed")
