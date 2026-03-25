import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import *
from downloader import download_video
from utils import log

bot = Bot(token=TOKEN)
dp = Dispatcher()
semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

user_lang = {}
user_requests = {}
async def safe_download(url, mode):
    async with semaphore:
        return await asyncio.wait_for(
            asyncio.to_thread(download_video, url, mode),
            timeout=DOWNLOAD_TIMEOUT
        )


@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("👋 Send a link")


@dp.message()
async def handle_video(message: types.Message):
    user_requests[message.from_user.id] = message.text
    await message.answer("Choose quality")


@dp.callback_query()
async def handle_quality(callback: types.CallbackQuery):
    url = user_requests.get(callback.from_user.id)

    try:
        file_path = await safe_download(url, "720")
        await callback.message.answer_video(types.FSInputFile(file_path))
    except Exception as e:
        log(f"[FINAL ERROR] {e}")
        await callback.message.answer("Error")


async def handle_webhook(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return web.Response(text="OK")


async def on_startup(app):
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)


def create_app():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    app.on_startup.append(on_startup)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
