import src.python_english_mentor.core.env as env
import src.python_english_mentor.core.supabase as supabase
import src.python_english_mentor.app as app_telegram_bot

from loguru import logger
from fastapi import FastAPI, Request, Response, status
from contextlib import asynccontextmanager

from src.python_english_mentor.repository.chat_repository import ChatRepository

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,  # /start dan /report
    MessageHandler,  # text atau suara (voice note)
    Defaults,
    filters,
)

from telegram.constants import ParseMode  # MarkdownV2
from zoneinfo import ZoneInfo  # WIB - Asia/Jakarta

from datetime import time

timezone = ZoneInfo("Asia/Jakarta")

bot_config = Defaults(parse_mode=ParseMode.MARKDOWN_V2, tzinfo=timezone)

app_bot = (
    Application.builder().token(env.TELEGRAM_BOT_TOKEN).defaults(bot_config).build()
)

app_bot.add_handler(CommandHandler("start", app_telegram_bot.start_command))
app_bot.add_handler(CommandHandler("report", app_telegram_bot.report_command))

app_bot.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, app_telegram_bot.handle_text)
)
app_bot.add_handler(MessageHandler(filters.VOICE, app_telegram_bot.handle_voice))

# reminder
target_time = time(hour=8, minute=0, second=0, tzinfo=timezone)
app_bot.job_queue.run_daily(
    callback=app_telegram_bot.task_reminder, time=target_time, name="task_reminder"
)

# error handler
app_bot.add_error_handler(app_telegram_bot.error_handler)

chat_repository = ChatRepository()
supabase_client = supabase.get_supabase_client()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. server "nyala"
    await app_bot.initialize()
    await app_bot.start()
    await app_bot.bot.set_webhook(
        url=env.TELEGRAM_WEBHOOK_URL,
        secret_token=env.TELEGRAM_SECRET_TOKEN,
        connect_timeout=30,  # seconds
    )
    yield
    # 2. server "mati"
    await app_bot.bot.delete_webhook()
    await app_bot.stop()
    await app_bot.shutdown()


app = FastAPI(lifespan=lifespan)


# /
@app.get("/")
async def root():
    return {"status": "it's coming from root"}  # JSON


@app.get("/get")
async def endpoint_get():
    return {"http_method": "get"}


# http request -> get dan post
@app.post("/post")
async def endpoint_post():
    return {"http_method": "post"}


# # webhook sample
# @app.post("/webhook")
# async def telegram_webhook(request: Request):
#     req_body = await request.json()
#     logger.debug(req_body)
#     return Response(status_code=status.HTTP_200_OK)


# webhook
@app.post("/webhook")
async def telegram_webhook(request: Request):
    # pengecekan secret token
    api_secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

    if api_secret_token != env.TELEGRAM_SECRET_TOKEN:
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    try:
        req_body = await request.json()
        # konversi data dari server telegram ke dalam format python-telegram-bot
        telegram_bot_data = Update.de_json(req_body, app_bot.bot)
        await app_bot.process_update(telegram_bot_data)

        return Response(status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error processing data telegram: {e}")
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
