# [BUILD 20260326-PROD-03] FULL STABLE V2 RESTORE

from aiogram import types, Dispatcher
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from downloader import download_video
import logger as log

req = {}

# --- keyboards ---
def format_kb():
    return ReplyKeyboardMarkup(
        resize_keyboard=True
    ).add(
        KeyboardButton("Аудио"),
        KeyboardButton("Видео")
    )


def register(dp: Dispatcher):

    # START
    @dp.message_handler(commands=["start"])
    async def start(message: types.Message):
        await message.answer("Отправь ссылку на видео")


    # URL
    @dp.message_handler(lambda m: m.text and "http" in m.text)
    async def handle_url(message: types.Message):
        user_id = message.from_user.id
        url = message.text.strip()

        req[user_id] = url

        log.info(f"[REQUEST] user={user_id} url={url}")

        await message.answer(
            "Выбери формат",
            reply_markup=format_kb()
        )


    # FORMAT
    @dp.message_handler(lambda m: m.text in ["Аудио", "Видео"])
    async def handle_format(message: types.Message):
        user_id = message.from_user.id

        if user_id not in req:
            await message.answer("Сначала пришли ссылку")
            return

        url = req[user_id]
        fmt = "audio" if message.text == "Аудио" else "video"

        log.info(f"[FORMAT] user={user_id} format={fmt}")

        await message.answer("Скачиваю...")

        try:
            await download_video(url, fmt, message)
            log.info(f"[SUCCESS] user={user_id}")

        except Exception as e:
            log.error(f"[ERROR] user={user_id} err={e}")
            await message.answer("Ошибка при скачивании")
