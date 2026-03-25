import os
import asyncio
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

def t(key, user_id):
    return TEXTS[key][user_lang.get(user_id, "ru")]

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

async def safe_download(url, mode):
    async with semaphore:
        return await asyncio.wait_for(
            asyncio.to_thread(download_video, url, mode),
            timeout=DOWNLOAD_TIMEOUT
        )

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
        url = (message.text or "").strip()

        if not url:
            return

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

        await callback.answer()

        asyncio.create_task(process_download(callback, user_id, url, mode))


async def process_download(callback, user_id, url, mode):
    await callback.message.answer(t("start", user_id))

    await callback.message.answer(t("status_1", user_id))
    await asyncio.sleep(1)
    await callback.message.answer(t("status_2", user_id))
    await asyncio.sleep(1)
    await callback.message.answer(t("status_3", user_id))

    file_path = None

    try:
       result = await safe_download(url, mode)

       # 🔥 поддержка старого и нового формата
       if isinstance(result, tuple):
         file_path, info = result
       else:
         file_path = result
         info = {}

        if not file_path or not os.path.exists(file_path):
            raise RuntimeError("File not created")

        size = os.path.getsize(file_path)

        if size > MAX_FILE_SIZE:
            await callback.message.answer(t("too_big", user_id) + url)
            return

        # 🔥 Формируем инфо
        title = info.get("title", "Unknown")
        ext = info.get("ext", "")
        abr = info.get("abr")  # bitrate audio

        size_mb = round(size / (1024 * 1024), 2)

        info_text = f"📄 {title}\n"
        info_text += f"📦 {ext.upper()} | {size_mb} MB"

        if mode == "audio" and abr:
            info_text += f" | {int(abr)} kbps"

        # Финальное сообщение
        await callback.message.answer(t("success", user_id) + "\n\n" + info_text)

        if mode == "audio":
            await callback.message.answer_audio(types.FSInputFile(file_path))
        else:
            await callback.message.answer_video(types.FSInputFile(file_path))

    except Exception as e:
        log(f"[FINAL ERROR] {e}")
        await callback.message.answer(t("error", user_id))

    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                log(f"[CLEANUP ERROR] {e}")
