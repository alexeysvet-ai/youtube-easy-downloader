import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode

from handlers import register

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
register(dp)


async def webhook(req):
    data = await req.json()
    await dp.feed_update(bot, data)
    return web.Response(text="ok")


async def health(req):
    return web.Response(text="OK")


async def start(request):
    return web.Response(text="Bot is running")


app = web.Application()
app.router.add_post("/webhook", webhook)
app.router.add_get("/health", health)
app.router.add_get("/", start)

if __name__ == "__main__":
    web.run_app(app, port=8000)
