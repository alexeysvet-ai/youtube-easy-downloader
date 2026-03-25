# [BUILD 20260325-PROD-01] RESTORE stable UX (no new logic)

from aiogram import types, Dispatcher
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from downloader import download_video
import logger as log

req = {}

# --- keyboards ---
def format_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Аудио"), KeyboardButton(text="Видео")]
        ],
        resize_keyboard=True
    )


def register(dp: Dispatcher):

    # START
    @dp.message_handler(commands=["start"])
    async def start(message: types.Message):
        await message.answer("Отправь ссылку на видео")


    # URL
    @dp.message_handler(lambda m: m.text and "http" in m.text)
    async def handle_url(message: types.Message):
        u = message.from_user.id
        url = message.text.strip()

        req[u] = url

        log.info(f"[REQUEST] user={u} url={url}")

        await message.answer(
            "Выбери формат",
            reply_markup=format_kb()
        )


    # FORMAT
    @dp.message_handler(lambda m: m.text in ["Аудио", "Видео"])
    async def handle_format(message: types.Message):
        u = message.from_user.id

        if u not in req:
            await message.answer("Сначала пришли ссылку")
            return

        url = req[u]
        fmt = "audio" if message.text == "Аудио" else "video"

        log.info(f"[FORMAT] user={u} format={fmt}")

        await message.answer("Скачиваю...")

        try:
            await download_video(url, fmt, message)
            log.info(f"[SUCCESS] user={u}")

        except Exception as e:
            log.error(f"[ERROR] user={u} err={e}")
            await message.answer("Ошибка при скачивании")
