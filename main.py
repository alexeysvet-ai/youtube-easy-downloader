from aiohttp import web
from aiogram import Bot, Dispatcher, types

from config import BOT_TOKEN, WEBHOOK_PATH, PORT, WEBHOOK_URL
from handlers import register

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
register(dp)

async def webhook(req):
    data = await req.json()
    update = types.Update(**data)  # Преобразуем данные в объект Update
    await dp.feed_update(bot, update)
    return web.Response(text="ok")

async def health(req):
    return web.Response(text="OK")

async def on_startup(app):
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)

app = web.Application()
app.router.add_post(WEBHOOK_PATH, webhook)
app.router.add_get('/health', health)

if __name__ == '__main__':
    app.on_startup.append(on_startup)
    web.run_app(app, port=PORT)
