# === handlers.py (FULL FILE) ===
# BUILD: 20260329-02-UX

import asyncio
from datetime import datetime, timezone
from bot_state import download_semaphore, user_requests, last_update_ts, process_start_ts
from aiogram import types, Dispatcher
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import STAGE_MODE, ALLOWED_USER_IDS, BOT_CODE
from downloader import download_video
from bot_core.utils import log
from texts import TEXTS
from bot_core.alerts import send_alert, build_download_fail_alert
from bot_core.events import insert_bot_entry, insert_bot_event
from bot_core.user_settings import set_user_lang
from bot_i18n import t, user_lang
from bot_core.bot_helpers import sanitize_filename, safe_title, extract_url
from download_flow import process_download
from bot_ui import quality_keyboard



def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺", callback_data="lang_ru"),
         InlineKeyboardButton(text="🇺🇸", callback_data="lang_en")]
    ])

# ===================== DOWNLOAD =====================

async def safe_download(url, mode, semaphore):
    async with semaphore:
        return await asyncio.to_thread(download_video, url, mode)

# ===================== HANDLERS =====================

def register_handlers(dp: Dispatcher):

    @dp.message(Command("start"))
    async def start(message: types.Message):
        import bot_state
        bot_state.last_update_ts = datetime.now(timezone.utc).timestamp()
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

        asyncio.create_task(process_download(callback, user_id, url, mode, t, safe_download, download_semaphore, user_requests))


