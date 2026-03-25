import os, time, asyncio
from pathlib import Path
from aiogram import types, Dispatcher
from aiogram.filters import Command

import logger as log
from downloader import download_video
from texts import TEXTS

req = {}
lang = {}


def t(k, u):
    return TEXTS[k][lang.get(u, "ru")]


def title(info, fp):
    t = (info.get("title") or "").strip()
    return t or Path(fp).stem


async def run(c, u, url, mode):
    start = time.time()

    try:
        log.start(u, mode, url)
        res = await asyncio.to_thread(download_video, url, mode, u)

        fp, info = res if isinstance(res, tuple) else (res, {})

        size = os.path.getsize(fp) / (1024 * 1024)
        ext = info.get("ext", "mp4")

        log.file(u, ext, round(size, 2), info.get("abr"))

        if mode == "audio":
            await c.message.answer_audio(types.FSInputFile(fp), title=title(info, fp))
        else:
            await c.message.answer_video(types.FSInputFile(fp))

        log.time_log(u, time.time() - start)

    except Exception as e:
        log.final_error(u, url, str(e))
        await c.message.answer(t("error", u))

    finally:
        if 'fp' in locals() and os.path.exists(fp):
            os.remove(fp)
            log.cleanup(u)


def register(dp: Dispatcher):

    @dp.message(Command("start"))
    async def s(m: types.Message):
        await m.answer(t("welcome", m.from_user.id))

    @dp.message()
    async def h(m: types.Message):
        u = m.from_user.id
        url = (m.text or "").strip()
        log.request(u, url)
        req[u] = url
        await m.answer(t("choose_format", u))

    @dp.callback_query(lambda c: c.data.startswith("q_"))
    async def q(c):
        u = c.from_user.id
        url = req.get(u)
        mode = c.data.split("_")[1]
        await c.answer()
        asyncio.create_task(run(c, u, url, mode))
