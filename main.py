import logging
import os
import asyncio
import re
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


def parse_timezone_offset(offset_str: str | None) -> timezone | None:
    if not offset_str:
        return None
    
    match = re.match(r"^([+-])(\d{1,2})(?::?(\d{2}))?$", offset_str)
    
    if not match:
        logger.warning(f"Invalid timezone format: {offset_str}")
        return None
        
    try:
        sign = -1 if match.group(1) == '-' else 1
        hours = int(match.group(2))
        minutes = int(match.group(3) or 0)
        
        if hours > 14 or minutes > 59:
             logger.warning(f"Invalid timezone range: {offset_str}")
             return None
             
        offset_delta = timedelta(hours=hours, minutes=minutes)
        return timezone(sign * offset_delta, name=f"UTC{offset_str}")
    except Exception as e:
        logger.error(f"Error parsing offset '{offset_str}': {e}")
        return None


async def get_user_settings_by_telegram_chat_id(chat_id: str):
    logger.info(f"Looking up user settings for chat_id: {chat_id}")
    try:
        response = (
            supabase.table("UserSettings")
            .select("user_id, timezone_offset")
            .eq("telegram_id", chat_id)
            .single()
            .execute()
        )
        
        if response.data:
            logger.info(f"Found user settings for chat_id {chat_id}")
            return response.data 
            
    except Exception as e:
        if "PostgrestAPIError" in str(e) and "JSON object requested, multiple (or no) rows returned" in str(e):
             logger.warning(f"No user found for chat_id: {chat_id}")
             return None
        logger.error(f"Error finding user by chat_id: {e}")
    
    logger.warning(f"No user found for chat_id: {chat_id}")
    return None


async def fetch_schedule_for_user_in_range(user_id: str, range_start: datetime, range_end: datetime):
    try:
        logger.info(f"Fetching tasks for user {user_id} between {range_start.isoformat()} and {range_end.isoformat()}")

        range_start_naive = range_start.replace(tzinfo=None)
        range_end_naive = range_end.replace(tzinfo=None)

        response = (
            supabase.table("tasks")
            .select("*")
            .eq("user_id", user_id)
            .gte("scheduled_time", range_start_naive.isoformat())
            .lt("scheduled_time", range_end_naive.isoformat())
            .order("scheduled_time", desc=False)
            .execute()
        )
        
        return response.data
    except Exception as e:
        logger.error(f"Error fetching tasks for user {user_id}: {e}")
        return []

async def check_and_send_reminders(application: Application) -> None:
    logger.info("Checking for task reminders...")
    
    try:
        user_response = (
            supabase.table("UserSettings")
            .select("user_id, telegram_id, timezone_offset")
            .eq("notifications", True)
            .execute()
        )
        
        if not user_response.data:
            logger.info("No users have notifications enabled. Skipping reminder check.")
            return

        for user in user_response.data:
            user_id = user.get('user_id')
            chat_id = user.get('telegram_id')
            user_timezone = parse_timezone_offset(user.get('timezone_offset'))

            if not (user_id and chat_id and user_timezone):
                logger.warning(f"Skipping reminders for user {user_id}: missing chat_id or timezone.")
                continue

            try:
                now_local = datetime.now(user_timezone)
                
                # --- FIX: Snap time to the current minute to avoid drift ---
                now_rounded = now_local.replace(second=0, microsecond=0)
                
                # Check for tasks starting exactly 30 minutes from this rounded time
                reminder_start_time = now_rounded + timedelta(minutes=30)
                reminder_end_time = reminder_start_time + timedelta(minutes=1) # 1-minute window
                # --- End of FIX ---

                # (This is the fix from last time, which is still needed)
                # Convert aware datetimes to naive datetimes for the query
                reminder_start_naive = reminder_start_time.replace(tzinfo=None)
                reminder_end_naive = reminder_end_time.replace(tzinfo=None)

                task_response = (
                    supabase.table("tasks")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("is_completed", False)
                    # Query using naive ISO strings
                    .gte("scheduled_time", reminder_start_naive.isoformat())
                    .lt("scheduled_time", reminder_end_naive.isoformat())
                    .execute()
                )

                if not task_response.data:
                    continue 

                logger.info(f"Found {len(task_response.data)} tasks for user {user_id} needing reminders.")

                for task in task_response.data:
                    title = task.get("title", "No Title").replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
                    
                    task_time_local = datetime.fromisoformat(task["scheduled_time"])
                    time_str = task_time_local.strftime('%H:%M')

                    message = (
                        f"🔔 <b>Reminder!</b>\n\n"
                        f"Your task is starting in 30 minutes (at {time_str}):\n"
                        f"<b>{title}</b>"
                    )
                    
                    await application.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode=ParseMode.HTML
                    )
                    logger.info(f"Sent reminder for task '{title}' to chat_id {chat_id}")

            except Exception as e:
                logger.error(f"Error processing reminders for user {user_id}: {e}")

    except Exception as e:
        logger.error(f"Error during reminder check cycle: {e}")

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
        "Once linked, please use /timezone to set your local timezone, then /schedule to see your tasks."
    )

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.message.chat_id)
    logger.info(f"Received /schedule command from {chat_id}")
    
    user_settings = await get_user_settings_by_telegram_chat_id(chat_id)
    
    if not user_settings or not user_settings.get('user_id'):
        await update.message.reply_text(
            "I don't recognize you. 😢\n"
            "Please send /start to get your Chat ID, then add it to your Plazen app settings."
        )
        return

    user_id = user_settings['user_id']
    user_timezone_str = user_settings.get('timezone_offset')
    user_timezone = parse_timezone_offset(user_timezone_str)

    if not user_timezone:
        await update.message.reply_html(
            "Please set your timezone first!\n"
            "I need to know your timezone to find your schedule for 'today'.\n\n"
            "Use <code>/timezone +5:30</code> or <code>/timezone -7</code>."
        )
        return

    await update.message.reply_text("Checking your schedule for today...")
    now_local = datetime.now(user_timezone)
    range_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    range_end = range_start + timedelta(days=1)
    
    tasks = await fetch_schedule_for_user_in_range(user_id, range_start, range_end)
    
    if not tasks:
        await update.message.reply_text("You have no tasks scheduled for today. ✨")
        return

    tz_label = user_timezone.tzname(None) 
    schedule_message = f"<b>Here is your schedule for today ({tz_label}):</b>\n\n"
    
    for task in tasks:
        if task.get("scheduled_time"):
            task_time_local = datetime.fromisoformat(task["scheduled_time"])
            time_str = task_time_local.strftime('%H:%M')
        else:
            time_str = "No time"
            
        status = '✅' if task.get("is_completed") else '🔲'
        title = task.get("title", "No Title").replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
        duration = f"({task.get('duration_minutes')} min)" if task.get("duration_minutes") else ""
        
        schedule_message += f"{status} <b>{time_str}</b> - {title} {duration}\n"

    await update.message.reply_html(schedule_message)


async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.message.chat_id)
    args = context.args
    
    if not args:
        await update.message.reply_html(
            "Please provide your timezone offset from UTC.\n\n"
            "<b>Examples:</b>\n"
            "<code>/timezone +5:30</code> (for India)\n"
            "<code>/timezone -7</code> (for Mountain Time)\n"
            "<code>/timezone +10</code> (for Sydney)\n"
            "<code>/timezone 0</code> (for UTC/GMT)\n\n"
            "You can google \"my timezone offset\" to find yours."
        )
        return

    offset_str = args[0]
    user_timezone = parse_timezone_offset(offset_str)
    
    if user_timezone is None:
        await update.message.reply_html(
            "<b>Invalid format.</b> 😕\n"
            "Please use one of these formats:\n"
            "<code>+5:30</code>\n"
            "<code>-7</code>\n"
            "<code>+09:00</code>\n"
        )
        return
        
    try:
        response = (
            supabase.table("UserSettings")
            .update({"timezone_offset": offset_str})
            .eq("telegram_id", chat_id)
            .execute()
        )
        
        if not response.data:
             logger.warning(f"No UserSettings row found for chat_id {chat_id} during timezone update.")
             await update.message.reply_text(
                "I couldn't find your user account. 😢\n"
                "Please make sure you have linked your account in the Plazen app using /start first."
             )
             return

        logger.info(f"Updated timezone for chat_id {chat_id} to {offset_str}")
        await update.message.reply_html(f"Success! Your timezone is set to <b>UTC{offset_str}</b>. 🎉")
        
    except Exception as e:
        logger.error(f"Error updating timezone for chat_id {chat_id}: {e}")
        await update.message.reply_text("An error occurred while trying to save your timezone. Please try again.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Get your Telegram Chat ID to link your account.\n"
        "/schedule - Get your schedule for today.\n"
        "/timezone - Set your local timezone (e.g., /timezone -7)"
    )

async def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("timezone", timezone_command))
    
    try:
        logger.info("Initializing application...")
        await application.initialize() 
        
        logger.info("Starting bot polling...")
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        while True:
            await check_and_send_reminders(application)
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