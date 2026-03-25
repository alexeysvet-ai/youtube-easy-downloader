import os
import asyncio
from aiogram import types, Dispatcher
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import DOWNLOAD_TIMEOUT, MAX_FILE_SIZE
from downloader import download_video
from utils import log

semaphore = asyncio.Semaphore(1)

user_lang = {}
user_requests = {}

TEXTS = {
    "welcome": {
        "ru": "👋 Привет! Отправь ссылку 👇",
        "en": "👋 Hi! Send a link 👇"
    },
    "choose_format": {
        "ru": "Выбери формат:",
        "en": "Choose format:"
    },
    "start": {
        "ru": "🔍 Начинаю обработку...",
        "en": "🔍 Starting..."
    },
    "status_1": {
        "ru": "🌐 Подбираю прокси...",
        "en": "🌐 Selecting proxy..."
    },
    "status_2": {
        "ru": "🛡 Обхожу ограничения...",
        "en": "🛡 Bypassing..."
    },
    "status_3": {
        "ru": "⬇️ Загружаю...",
        "en": "⬇️ Downloading..."
    },
    "success": {
        "ru": "✅ Готово!",
        "en": "✅ Done!"
    },
    "error": {
        "ru": "😔 Не удалось скачать",
        "en": "😔 Failed"
    }
}

def t(key, user_id):
    return TEXTS[key][user_lang.get(user_id, "ru")]

async def safe_download(url, mode):
    async with semaphore:
        return await asyncio.wait_for(
            asyncio.to_thread(download_video, url, mode),
            timeout=DOWNLOAD_TIMEOUT
        )

def quality_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="720p", callback_data="q_720"),
         InlineKeyboardButton(text="360p", callback_data="q_360")],
        [InlineKeyboardButton(text="240p", callback_data="q_240"),
         InlineKeyboardButton(text="144p", callback_data="q_144")],
        [InlineKeyboardButton(text="Audio", callback_data="q_audio")]
    ])

def register_handlers(dp: Dispatcher):

    @dp.message(Command("start"))
    async def start(message: types.Message):
        await message.answer(t("welcome", message.from_user.id))

    @dp.message()
    async def handle_video(message: types.Message):
        user_id = message.from_user.id
        url = (message.text or "").strip()

        user_requests[user_id] = url
        await message.answer(t("choose_format", user_id), reply_markup=quality_keyboard())

    @dp.callback_query(lambda c: c.data.startswith("q_"))
    async def handle_quality(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        url = user_requests.get(user_id)
        mode = callback.data.split("_")[1]

        await callback.message.answer(t("start", user_id))
        await callback.message.answer(t("status_1", user_id))
        await asyncio.sleep(1)
        await callback.message.answer(t("status_2", user_id))
        await asyncio.sleep(1)
        await callback.message.answer(t("status_3", user_id))

        try:
            file_path = await safe_download(url, mode)

            if not file_path or not os.path.exists(file_path):
                raise RuntimeError("File not created")

            size = os.path.getsize(file_path)

            if size > MAX_FILE_SIZE:
                await callback.message.answer("⚠️ File too large (>50MB)")
                return

            await callback.message.answer(t("success", user_id))

            if mode == "audio":
                await callback.message.answer_audio(types.FSInputFile(file_path))
            else:
                await callback.message.answer_video(types.FSInputFile(file_path))

        except Exception as e:
            log(f"[FINAL ERROR] {e}")
            await callback.message.answer(t("error", user_id))

        finally:
            if 'file_path' in locals() and file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    log(f"[CLEANUP ERROR] {e}")
