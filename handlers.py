    # === handlers.py (FULL FILE) ===
# BUILD: 20260326-02

import os
import asyncio
import re
from pathlib import Path
from datetime import datetime, timezone
from aiogram import types, Dispatcher
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import DOWNLOAD_TIMEOUT, MAX_FILE_SIZE
from downloader import download_video
from utils import log
from texts import TEXTS

semaphore = asyncio.Semaphore(1)

user_lang = {}
user_requests = {}
last_update_ts = None
process_start_ts = datetime.now(timezone.utc).timestamp()

# ===================== HELPERS =====================
# --- LAG DETECTION HELPER (20260326 UX SAFE) ---
def detect_sleep(now_ts: float, process_start_ts: float) -> bool:
    global last_update_ts

    sleep_detected = False

    if last_update_ts is None:
        # первый запрос после старта процесса
        uptime = now_ts - process_start_ts
        if uptime > 5:
            sleep_detected = True
    else:
        delta = now_ts - last_update_ts
        if delta > 30:
            sleep_detected = True

    # обновляем timestamp ПОСЛЕ проверки
    last_update_ts = now_ts

    return sleep_detected
def t(key, user_id):
    return TEXTS[key][user_lang.get(user_id, "ru")]

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
        return await asyncio.wait_for(
            asyncio.to_thread(download_video, url, mode),
            timeout=DOWNLOAD_TIMEOUT
        )

# ===================== HANDLERS =====================

def register_handlers(dp: Dispatcher):

    @dp.message(Command("start"))
    async def start(message: types.Message):
        await message.answer(
            TEXTS["choose_lang"]["ru"] + " / " + TEXTS["choose_lang"]["en"],
            reply_markup=lang_keyboard()
        )

    @dp.callback_query(lambda c: c.data.startswith("lang_"))
    async def set_lang(callback: types.CallbackQuery):
        user_lang[callback.from_user.id] = callback.data.split("_")[1]
        await callback.message.edit_text(t("welcome", callback.from_user.id))

    @dp.message(lambda message: message.text and not message.text.startswith("/"))
    async def handle_video(message: types.Message):
        user_id = message.from_user.id

        # --- INPUT VALIDATION (20260326-02 SAFE) ---
        raw_text = (message.text or "").strip()
        url = extract_url(raw_text)

        if not url:
            await message.answer(t("invalid_url", user_id))
            return

        # --- V2 LAG DETECTION (20260326-02 SAFE, LOCALIZED) ---
        now = datetime.now(timezone.utc)
        msg_time = message.date
        # --- COLD START + LAG (20260326-04 SAFE) ---
        global last_update_ts

        now = datetime.now(timezone.utc)
        # --- LAG DETECTION ---
        now_ts = datetime.now(timezone.utc).timestamp()
        sleep_detected = detect_sleep(now_ts, process_start_ts)

        lag_sec = (datetime.now(timezone.utc) - message.date).total_seconds()

        if sleep_detected:
            await message.answer(t("lag_long", user_id))
        elif lag_sec > 25:
            await message.answer(t("lag_long", user_id))
        elif lag_sec > 10:
            await message.answer(t("lag_short", user_id))


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

        # --- STATE EXPIRATION CHECK (20260326-04 SAFE) ---
        if not url:
            await callback.message.answer(t("expired_request", user_id))
            return

        await callback.answer()
        # --- LAG FOR CALLBACK (20260326-05 SAFE) ---
        now = datetime.now(timezone.utc)

        # используем message.date как fallback
        msg_time = callback.message.date if callback.message else now

        # --- LAG DETECTION ---
        now_ts = datetime.now(timezone.utc).timestamp()
        sleep_detected = detect_sleep(now_ts, process_start_ts)

        lag_sec = (datetime.now(timezone.utc) - message.date).total_seconds()

        if sleep_detected:
            await message.answer(t("lag_long", user_id))
        elif lag_sec > 25:
            await message.answer(t("lag_long", user_id))
        elif lag_sec > 10:
            await message.answer(t("lag_short", user_id))

        asyncio.create_task(process_download(callback, user_id, url, mode))


# ===================== PROCESS =====================

async def process_download(callback, user_id, url, mode):
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
            else:
                result_text += " | ~192 kbps"

        await callback.message.answer(
            t("success", user_id) + "\n\n" + result_text
        )

        if mode == "audio":
            await callback.message.answer_audio(
                types.FSInputFile(file_path),
                title=title,
                performer=uploader or ""
            )
        else:
            await callback.message.answer_video(
                types.FSInputFile(file_path)
            )

    except Exception as e:
        log(f"[FINAL ERROR] {e}")
        await callback.message.answer(t("error", user_id))

    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                log(f"[CLEANUP ERROR] {e}")
