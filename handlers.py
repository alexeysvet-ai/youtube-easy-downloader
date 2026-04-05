# === handlers.py (FULL FILE) ===
# BUILD: 20260329-02-UX

import os
import asyncio
import re
from pathlib import Path
from datetime import datetime, timezone
from aiogram import types, Dispatcher
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import MAX_FILE_SIZE, STAGE_MODE, ALLOWED_USER_IDS, BOT_CODE
from downloader import download_video
from utils import log
from texts import TEXTS
from alerts import send_alert, build_download_fail_alert
from bot_core.db import insert_bot_entry, get_user_lang, set_user_lang, insert_bot_event

semaphore = asyncio.Semaphore(1)

user_lang = {}
user_requests = {}
last_update_ts = None
process_start_ts = datetime.now(timezone.utc).timestamp()

# ===================== HELPERS =====================
# --- LAG DETECTION HELPER (20260326 UX SAFE) ---
def detect_sleep(now_ts: float, process_start_ts: float) -> bool:
    # === CHANGE START ===
    # больше не используется — логика перенесена в message.date
    return False
    # === CHANGE END ===

def t(key, user_id):
    lang = user_lang.get(user_id)

    if not lang:
        try:
            lang = get_user_lang(BOT_CODE, user_id)
            if lang:
                user_lang[user_id] = lang
                log(f"[DB LANG LOAD OK] bot_code={BOT_CODE} user_id={user_id} lang={lang}")
        except Exception as e:
            log(f"[DB LANG LOAD ERROR] bot_code={BOT_CODE} user_id={user_id} error={e}")

    return TEXTS[key][lang or "ru"]

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name)

def safe_title(info, file_path):
    title = (info.get("title") or "").strip()

    if not title or title.lower() in ["unknown", "na", "none"]:
        title = Path(file_path).stem

    return sanitize_filename(title)

# --- URL EXTRACTION (20260326-02 SAFE) ---
def extract_url(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r'(https?://[^\s]+)', text)
    return match.group(1) if match else None

# ===================== UI =====================

def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺", callback_data="lang_ru"),
         InlineKeyboardButton(text="🇺🇸", callback_data="lang_en")]
    ])

def quality_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="720p", callback_data="q_720"),
         InlineKeyboardButton(text="360p", callback_data="q_360")],
        [InlineKeyboardButton(text="240p", callback_data="q_240"),
         InlineKeyboardButton(text="144p", callback_data="q_144")],
        [InlineKeyboardButton(text="Audio", callback_data="q_audio")]
    ])

# ===================== DOWNLOAD =====================

async def safe_download(url, mode):
    async with semaphore:
        return await asyncio.to_thread(download_video, url, mode)

# ===================== HANDLERS =====================

def register_handlers(dp: Dispatcher):

    @dp.message(Command("start"))
    async def start(message: types.Message):
        global last_update_ts
        last_update_ts = datetime.now(timezone.utc).timestamp()
        log(f"[USER START] id={message.from_user.id}")

        try:
            insert_bot_entry(BOT_CODE, message.from_user.id)
            print(f"DB INSERT OK: bot_code={BOT_CODE}, user_id={message.from_user.id}")
        except Exception as e:
            log(f"[DB INSERT ERROR] {e}")

        if STAGE_MODE and message.from_user.id not in ALLOWED_USER_IDS:
            await message.answer(
                TEXTS["stage_restricted"]["ru"] + " / " + TEXTS["stage_restricted"]["en"]
            )
            return

        await message.answer(
            TEXTS["choose_lang"]["ru"] + " / " + TEXTS["choose_lang"]["en"],
            reply_markup=lang_keyboard()
        )

    @dp.callback_query(lambda c: c.data.startswith("lang_"))
    async def set_lang(callback: types.CallbackQuery):
        lang = callback.data.split("_")[1]
        user_lang[callback.from_user.id] = lang
        
        try:
            set_user_lang(BOT_CODE, callback.from_user.id, lang)
            log(f"[DB LANG SAVE OK] bot_code={BOT_CODE} user_id={callback.from_user.id} lang={lang}")
        except Exception as e:
            log(f"[DB LANG SAVE ERROR] bot_code={BOT_CODE} user_id={callback.from_user.id} lang={lang} error={e}")

        await callback.message.edit_text(t("welcome", callback.from_user.id))

    @dp.message(lambda message: message.text and not message.text.startswith("/"))
    async def handle_video(message: types.Message):
        user_id = message.from_user.id
        if STAGE_MODE and message.from_user.id not in ALLOWED_USER_IDS:
            await message.answer(
                TEXTS["stage_restricted"]["ru"] + " / " + TEXTS["stage_restricted"]["en"]
            )
            return
        raw_text = (message.text or "").strip()
        url = extract_url(raw_text)

        if not url:
            try:
                insert_bot_event(
                    BOT_CODE,
                    user_id,
                    "url_received_invalid",
                    status="fail"
                )
            except Exception as e:
                log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=url_received_invalid error={e}")

            await message.answer(t("invalid_url", user_id))
            return

        # === CHANGE START ===
        now = datetime.now(timezone.utc)
        msg_time = message.date

        lag_sec = (now - msg_time).total_seconds()

        if lag_sec > 10:
            await message.answer(t("lag_long", user_id))
        # === CHANGE END ===

        try:
            insert_bot_event(
                BOT_CODE,
                user_id,
                "url_received_valid",
                status="success"
            )
        except Exception as e:
            log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=url_received_valid error={e}")

        user_requests[user_id] = url

        await message.answer(
            t("choose_format", user_id),
            reply_markup=quality_keyboard()
        )

    @dp.callback_query(lambda c: c.data.startswith("q_"))
    async def handle_quality(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        url = user_requests.get(user_id)
        mode = callback.data.split("_")[1]

        if not url:
            await callback.message.answer(t("expired_request", user_id))
            return

        await callback.answer()

        try:
            insert_bot_event(
                BOT_CODE,
                user_id,
                "download_mode_selected",
                status="success",
                mode=mode
            )
        except Exception as e:
            log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=download_mode_selected mode={mode} error={e}")

        # === CHANGE START ===
        now = datetime.now(timezone.utc)
        msg_time = callback.message.date if callback.message else now

        lag_sec = (now - msg_time).total_seconds()

        if lag_sec > 10:
            await callback.message.answer(t("lag_long", user_id))
        # === CHANGE END ===

        asyncio.create_task(process_download(callback, user_id, url, mode))


# ===================== PROCESS =====================

async def process_download(callback, user_id, url, mode):
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
        result = await safe_download(url, mode)

        if isinstance(result, tuple):
            file_path, info = result
        else:
            file_path = result
            info = {}

        if not file_path or not os.path.exists(file_path):
            raise RuntimeError("File not created")

        size = os.path.getsize(file_path)
        size_mb = round(size / (1024 * 1024), 2)

        if size > MAX_FILE_SIZE:
            try:
                insert_bot_event(
                    BOT_CODE,
                    user_id,
                    "download_rejected_too_big",
                    status="rejected",
                    mode=mode,
                    file_size_bytes=size
                )
            except Exception as e:
                log(f"[DB EVENT ERROR] bot_code={BOT_CODE} user_id={user_id} event_type=download_rejected_too_big mode={mode} error={e}")

            await callback.message.answer(t("too_big", user_id) + url)
            return

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
