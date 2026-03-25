from aiohttp import web
from aiogram import Bot, Dispatcher, types

from config import TOKEN, WEBHOOK_PATH, WEBHOOK_URL, PORT
from handlers import register_handlers
from utils import log

if not TOKEN:
    raise ValueError("TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

register_handlers(dp)

async def handle_webhook(request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.feed_update(bot, update)
    except Exception as e:
        log(f"[WEBHOOK ERROR] {e}")
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
