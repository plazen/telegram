import logging
import os
import asyncio
from datetime import datetime, timedelta, timezone
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.constants import ParseMode
from supabase import create_client, AsyncClient
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable is not set.")
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL environment variable is not set.")
if not SUPABASE_SERVICE_KEY:
    raise ValueError("SUPABASE_SERVICE_KEY environment variable is not set. (This must be your Service Role key)")

supabase: AsyncClient = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


async def get_user_id_by_telegram_chat_id(chat_id: str):
    logger.info(f"Looking up user for chat_id: {chat_id}")
    try:
        response = supabase.table("UserSettings").select("user_id").eq("telegram_id", chat_id).single().execute()
        
        if response.data:
            logger.info(f"Found user: {response.data['user_id']}")
            return response.data['user_id']
    except Exception as e:
        if "PostgrestAPIError" in str(e) and "JSON object requested, multiple (or no) rows returned" in str(e):
             logger.warning(f"No user found for chat_id: {chat_id}")
             return None
        logger.error(f"Error finding user by chat_id: {e}")
    
    logger.warning(f"No user found for chat_id: {chat_id}")
    return None

async def fetch_schedule_for_user(user_id: str):
    try:
        today_utc = datetime.now(timezone.utc)
        
        range_start = today_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        range_end = range_start + timedelta(days=1)
        
        logger.info(f"Fetching tasks for user {user_id} between {range_start.isoformat()} and {range_end.isoformat()}")

        response = supabase.table("tasks").select("*").eq("user_id", user_id).gte("scheduled_time", range_start.isoformat()).lt("scheduled_time", range_end.isoformat()).order("scheduled_time", desc=False).execute()
        
        return response.data
    except Exception as e:
        logger.error(f"Error fetching tasks for user {user_id}: {e}")
        return []

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat_id = str(update.message.chat_id)
    
    logger.info(f"User {user.first_name} (ID: {chat_id}) started the bot.")
    
    await update.message.reply_html(
        rf"Hi {user.mention_html()}! Welcome to the Plazen Bot. 🤖"
        "\n\n"
        "To link this bot to your Plazen account, copy your Chat ID below and paste it into the 'Telegram Chat ID' field in your Plazen app's settings."
        "\n\n"
        "Your Telegram Chat ID is:"
        "\n"
        f"<code>{chat_id}</code>"
        "\n\n"
        "Once linked, you can type /schedule to see your tasks for today."
    )

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.message.chat_id)
    logger.info(f"Received /schedule command from {chat_id}")
    
    user_id = await get_user_id_by_telegram_chat_id(chat_id)
    
    if not user_id:
        await update.message.reply_text(
            "I don't recognize you. 😢\n"
            "Please send /start to get your Chat ID, then add it to your Plazen app settings."
        )
        return

    await update.message.reply_text("Checking your schedule for today (UTC)...")
    
    tasks = await fetch_schedule_for_user(user_id)
    
    if not tasks:
        await update.message.reply_text("You have no tasks scheduled for today. ✨")
        return

    schedule_message = "<b>Here is your schedule for today (UTC):</b>\n\n"
    for task in tasks:
        if task.get("scheduled_time"):
            task_time_utc = datetime.fromisoformat(task["scheduled_time"]).replace(tzinfo=timezone.utc)
            
            time_str = task_time_utc.strftime('%H:%M')
        else:
            time_str = "No time"
            
        status = '✅' if task.get("is_completed") else '🔲'
        title = task.get("title", "No Title").replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
        duration = f"({task.get('duration_minutes')} min)" if task.get("duration_minutes") else ""
        
        schedule_message += f"{status} <b>{time_str}</b> - {title} {duration}\n"

    await update.message.reply_html(schedule_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Get your Telegram Chat ID to link your account.\n"
        "/schedule - Get your schedule for today."
    )

async def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("help", help_command))
    try:
        logger.info("Initializing application...")
        await application.initialize() 
        
        logger.info("Starting bot polling...")
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        while True:
            await asyncio.sleep(60)
            
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Bot polling failed unexpectedly: {e}")
    finally:
        if application.updater and application.updater.is_running:
            logger.info("Stopping updater...")
            await application.updater.stop()
        if application.running:
            logger.info("Stopping application...")
            await application.stop()
        logger.info("Shutting down application...")
        await application.shutdown() 
        logger.info("Bot shut down successfully.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down (main entry).")
    except Exception as e:
        logger.error(f"Application failed to run: {e}")