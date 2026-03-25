# [BUILD 20260326-PROD-07] STABLE MAIN (Render + aiogram webhook)

import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types

from config import BOT_TOKEN, WEBHOOK_PATH
from handlers import register

# --- logging ---
logging.basicConfig(level=logging.INFO)

# --- bot / dispatcher ---
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- register handlers ---
register(dp)


# --- webhook handler ---
async def webhook(request: web.Request):
    try:
        data = await request.json()
        update = types.Update(**data)

        logging.info("Received update")

        await dp.feed_update(bot, update)

        return web.Response(text="ok")

    except Exception as e:
        logging.exception(f"Webhook error: {e}")
        return web.Response(text="error", status=500)


# --- health check ---
async def health(request: web.Request):
    return web.Response(text="OK")


# --- app setup ---
app = web.Application()
app.router.add_post(WEBHOOK_PATH, webhook)
app.router.add_get("/health", health)


# --- startup ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    logging.info(f"Starting app on port {port}")

    web.run_app(app, port=port)
