import os
import asyncio
from aiogram import types

from config import BOT_CODE
from utils import log
from alerts import send_alert, build_download_fail_alert
from bot_core.db import insert_bot_event
from bot_helpers import safe_title

# ===================== PROCESS =====================

async def process_download(callback, user_id, url, mode, t, safe_download, semaphore, user_requests):

    try:
        insert_bot_event(
            BOT_CODE,
            user_id,
            "download_started",
            status="success",
            mode=mode
        )
    except Exception as e:
        log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=download_started mode={mode} error={e}")

    await callback.message.answer(t("start", user_id))

    await callback.message.answer(t("status_1", user_id))
    await asyncio.sleep(1)
    await callback.message.answer(t("status_2", user_id))
    await asyncio.sleep(1)

    if mode == "audio":
        await callback.message.answer(t("status_audio", user_id))
    else:
        await callback.message.answer(t("status_video", user_id))

    file_path = None

    try:
        result = await safe_download(url, mode, semaphore)

        if isinstance(result, tuple):
            file_path, info = result
        else:
            file_path = result
            info = {}

        if not file_path or not os.path.exists(file_path):
            raise RuntimeError("File not created")

        size = os.path.getsize(file_path)
        size_mb = round(size / (1024 * 1024), 2)
        # size check moved to downloader (pre-download)
        title = safe_title(info, file_path)

        ext = info.get("ext", "mp4")
        abr = info.get("abr")
        uploader = info.get("uploader", "")

        display_ext = ext
        if mode == "audio":
            display_ext = "mp3"

        new_path = f"/tmp/{title}.{ext}"

        try:
            os.rename(file_path, new_path)
            file_path = new_path
        except Exception as e:
            log(f"[RENAME ERROR] {e}")

        result_text = t("file_info", user_id).format(
            ext=display_ext.upper(),
            size=size_mb
        )

        if mode == "audio":
            if abr:
                result_text += f" | {int(abr)} kbps"

        final_caption = t("success", user_id) + "\n\n" + result_text

        if mode == "audio":
            await callback.message.answer_audio(
                types.FSInputFile(file_path),
                title=title,
                performer=uploader or "",
                caption=final_caption
            )
        else:
            await callback.message.answer_video(
                types.FSInputFile(file_path),
                caption=final_caption
            )

        try:
            insert_bot_event(
                BOT_CODE,
                user_id,
                "download_success",
                status="success",
                mode=mode,
                file_size_bytes=size
            )
        except Exception as e:
            log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=download_success mode={mode} error={e}")

    except Exception as e:
        log(f"[FINAL ERROR] {e}")

        if "File too big" in str(e):
            try:
                insert_bot_event(
                    BOT_CODE,
                    user_id,
                    "download_rejected_too_big",
                    status="rejected",
                    mode=mode
                )
            except Exception as db_error:
                log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=download_rejected_too_big mode={mode} error={db_error}")

            await callback.message.answer(t("too_big", user_id))
            return

        try:
            insert_bot_event(
                BOT_CODE,
                user_id,
                "download_failed",
                status="fail",
                mode=mode,
                error_text_short=str(e)[:500]
            )
        except Exception as db_error:
            log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=download_failed mode={mode} error={db_error}")

        await callback.message.answer(t("error", user_id))
        alert_text = build_download_fail_alert(user_id, url, mode, str(e))
        await send_alert(alert_text)


    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                log(f"[CLEANUP ERROR] {e}")
