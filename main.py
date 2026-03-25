import logging
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher, types

from config import BOT_TOKEN, WEBHOOK_PATH, PORT, WEBHOOK_URL
from handlers import register

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
register(dp)

async def webhook(req):
    logging.debug("Received webhook request")
    data = await req.json()
    update = types.Update(**data)
    logging.debug(f"Processed update from webhook: {update}")
    await dp.feed_update(bot, update)
    return web.Response(text="ok")

async def health(req):
    logging.debug("Health check requested")
    return web.Response(text="OK")

async def on_startup(app):
    logging.debug("Bot starting up")
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)

app = web.Application()
app.router.add_post(WEBHOOK_PATH, webhook)
app.router.add_get('/health', health)

if __name__ == '__main__':
    logging.debug("Starting bot app")
    app.on_startup.append(on_startup)
    web.run_app(app, port=PORT)
