from aiohttp import web
from aiogram import Bot, Dispatcher, types
import asyncio
from config import TOKEN, WEBHOOK_PATH, WEBHOOK_URL, PORT
from handlers import register_handlers
from bot_core.utils import log
from proxy_cron import run_proxy_refresh
from bot_core.db import test_connection

if not TOKEN:
    raise ValueError("TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

register_handlers(dp)

is_refresh_running = False

async def refresh_proxies(req):
    global is_refresh_running

    if is_refresh_running:
        return web.Response(text="ALREADY RUNNING")

    is_refresh_running = True

    async def wrapper():
        global is_refresh_running
        try:
            await asyncio.to_thread(run_proxy_refresh)
        finally:
            is_refresh_running = False

    asyncio.create_task(wrapper())

    return web.Response(text="REFRESH STARTED")


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
        asyncio.create_task(bot.set_webhook(WEBHOOK_URL))
    # TEST DB CONNECTION
    try:
        ok = test_connection()
        print("DB CONNECTION:", ok)
    except Exception as e:
        print("DB CONNECTION ERROR:", e)

        
async def health(req):
    return web.Response(text="OK")
def create_app():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", health)
    app.router.add_get("/health", health) 
    app.router.add_get("/refresh-proxies", refresh_proxies)
    app.on_startup.append(on_startup)
    return app

if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
