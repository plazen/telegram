import logging
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import db
import utils

logger = logging.getLogger(__name__)

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
    
    user_settings = await db.get_user_settings_by_telegram_chat_id(chat_id)
    
    if not user_settings or not user_settings.get('user_id'):
        await update.message.reply_text(
            "I don't recognize you. 😢\n"
            "Please send /start to get your Chat ID, then add it to your Plazen app settings."
        )
        return

    user_id = user_settings['user_id']
    user_timezone_str = user_settings.get('timezone_offset')
    user_timezone = utils.parse_timezone_offset(user_timezone_str)

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
    
    tasks = await db.fetch_schedule_for_user_in_range(user_id, range_start, range_end)
    
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
    user_timezone = utils.parse_timezone_offset(offset_str)
    
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
        response_data = await db.update_user_timezone(chat_id, offset_str)
        
        if not response_data:
             logger.warning(f"No UserSettings row found for chat_id {chat_id} during timezone update.")
             await update.message.reply_text(
                "I couldn't find your user account. 😢\n"
                "Please make sure you have linked your account in the Plazen app using /start first."
             )
             return

        await update.message.reply_html(f"Success! Your timezone is set to <b>UTC{offset_str}</b>. 🎉")
        
    except Exception as e:
        logger.error(f"Error during timezone_command for chat_id {chat_id}: {e}")
        await update.message.reply_text("An error occurred while trying to save your timezone. Please try again.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Get your Telegram Chat ID to link your account.\n"
        "/schedule - Get your schedule for today.\n"
        "/timezone - Set your local timezone (e.g., /timezone -7)"
    )

async def handle_ai_task_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.message.chat_id)
    text = update.message.text
    
    match = re.match(r"i want to (.*) for (.*) at (.*)", text, re.IGNORECASE)
    
    if not match:
        logger.info(f"Ignoring non-task message from {chat_id}")
        return

    logger.info(f"Matched task creation syntax from {chat_id}")
    
    user_settings = await db.get_user_settings_by_telegram_chat_id(chat_id)
    
    if not user_settings or not user_settings.get('user_id'):
        await update.message.reply_text(
            "I can't schedule this for you until I know who you are. 😢\n"
            "Please send /start to get your Chat ID, then add it to your Plazen app settings."
        )
        return

    user_id = user_settings['user_id']
    user_timezone_str = user_settings.get('timezone_offset')
    user_timezone = utils.parse_timezone_offset(user_timezone_str)

    if not user_timezone:
        await update.message.reply_html(
            "I can't schedule this for you until I know your timezone!\n"
            "Please set your timezone first using <code>/timezone +5:30</code> or <code>/timezone -7</code>."
        )
        return
        
    try:
        title = match.group(1).strip()
        duration_str = match.group(2).strip()
        time_str = match.group(3).strip()
        
        if not title:
             await update.message.reply_text("Please provide a title for the task.")
             return

        duration_minutes = utils.parse_duration_to_minutes(duration_str)
        if duration_minutes is None:
            await update.message.reply_html(
                f"I didn't understand the duration <b>'{duration_str}'</b>.\n"
                "Please try '30 min' or '1 hour' or just '30'."
            )
            return
            
        task_dt_naive = utils.parse_local_time_to_naive_datetime(time_str, user_timezone)
        if task_dt_naive is None:
            await update.message.reply_html(
                f"I didn't understand the time <b>'{time_str}'</b>.\n"
                "Please try '17:30' or '5:30PM'."
            )
            return
            
        new_task = {
            "user_id": user_id,
            "title": title,
            "scheduled_time": task_dt_naive.isoformat(), 
            "duration_minutes": duration_minutes,
            "is_completed": False
        }
        
        await db.create_task(new_task)
        
        local_time_str = task_dt_naive.strftime('%H:%M on %b %d')
        
        await update.message.reply_html(
            f"<b>Task Scheduled!</b> 👍\n\n"
            f"<b>Task:</b> {title.replace('<', '&lt;').replace('>', '&gt;')}\n"
            f"<b>When:</b> {local_time_str} ({user_timezone.tzname(None)})\n"
            f"<b>Duration:</b> {duration_minutes} minutes"
        )
        
    except Exception as e:
        logger.error(f"Error in handle_ai_task_creation for chat {chat_id}: {e}")
        await update.message.reply_text("Oops! Something went wrong while trying to schedule that. Please try again.")