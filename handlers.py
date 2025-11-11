import logging
import re
import asyncio
import random 
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
            # --- FIX: Convert DB time to local for display ---
            task_time_db = datetime.fromisoformat(task["scheduled_time"])
            task_time_naive = task_time_db.replace(tzinfo=None)
            task_time_local = task_time_naive.replace(tzinfo=user_timezone)
            # --- END FIX ---
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
    
    if "task_lock" not in context.user_data:
        context.user_data["task_lock"] = asyncio.Lock()
    lock = context.user_data["task_lock"]

    async with lock:
        logger.info(f"Acquired task lock for chat_id {chat_id}")
        
        match = re.match(r"i want to (.*) for (.*)(?: at (.*))?", text, re.IGNORECASE)
        
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
            title = match.group(1).strip().capitalize()
            duration_str = match.group(2).strip()
            time_str = match.group(3).strip() if match.group(3) else None
            
            if not title:
                 await update.message.reply_text("Please provide a title for the task.")
                 return 

            duration_minutes = utils.parse_duration_to_minutes(duration_str)
            if duration_minutes is None:
                await update.message.reply_html(
                    f"I didn't understand the duration <b>'{duration_str}'</b>.\n"
                    "Please try '30 min', '1 hour', '120m', or '2 hours'."
                )
                return 
                
            task_dt_naive = None
            local_time_str = ""

            if time_str:
                logger.info(f"User provided specific time: {time_str}")
                task_dt_naive = utils.parse_local_time_to_naive_datetime(time_str, user_timezone)
                if task_dt_naive is None:
                    await update.message.reply_html(
                        f"I didn't understand the time <b>'{time_str}'</b>.\n"
                        "Please try '17:30' or '5:30PM'."
                    )
                    return 
                local_time_str = task_dt_naive.strftime('%H:%M on %b %d')
            
            else:
                logger.info(f"User did not provide time for '{title}', finding random slot for today.")
                
                user_start_hour_int = user_settings.get('timetable_start')
                user_end_hour_int = user_settings.get('timetable_end')

                if user_start_hour_int is None or user_end_hour_int is None:
                    await update.message.reply_html(
                        "To auto-schedule, please set your <b>start and end times</b> in the Plazen app's settings first."
                    )
                    return 

                now_local = datetime.now(user_timezone)
                
                today_start_dt = now_local.replace(hour=user_start_hour_int, minute=0, second=0, microsecond=0)
                today_end_dt = now_local.replace(hour=user_end_hour_int, minute=0, second=0, microsecond=0)

                range_start_naive = today_start_dt.replace(tzinfo=None)
                range_end_naive = today_end_dt.replace(tzinfo=None)

                # This DB query MUST use naive datetimes to match the DB column
                existing_tasks_raw = await db.fetch_schedule_for_user_in_range(user_id, range_start_naive, range_end_naive)

                parsed_tasks_list = []
                for task in existing_tasks_raw:
                    try:
                        # 1. Parse the UTC datetime string from Supabase (e.g., 18:45+00:00)
                        task_start_db_time = datetime.fromisoformat(task['scheduled_time'])
                        
                        # 2. Get the naive time (e.g., 18:45)
                        task_start_naive = task_start_db_time.replace(tzinfo=None)

                        # 3. Apply the user's local timezone (e.g., 18:45 UTC+4)
                        task_start_local = task_start_naive.replace(tzinfo=user_timezone)

                        task_duration = task.get('duration_minutes') or 30
                        
                        # 4. Calculate end time in the same local timezone
                        task_end_local = task_start_local + timedelta(minutes=task_duration)
                        
                        parsed_tasks_list.append((task_start_local, task_end_local))
                        
                        logger.info(f"Existing task parsed (local): {task_start_local} to {task_end_local}")

                    except Exception as e:
                        logger.warning(f"Could not parse existing task {task.get('id')}: {e}")

                valid_slots = []
                
                search_start_time = max(now_local, today_start_dt)

                current_slot_start = search_start_time.replace(second=0, microsecond=0)
                if search_start_time.second > 0 or search_start_time.microsecond > 0:
                    current_slot_start += timedelta(minutes=1)
                
                minutes_past_interval = current_slot_start.minute % 15
                if minutes_past_interval > 0:
                    current_slot_start += timedelta(minutes=(15 - minutes_past_interval))

                while current_slot_start < today_end_dt:
                    slot_start = current_slot_start
                    slot_end = slot_start + timedelta(minutes=duration_minutes)

                    if slot_end > today_end_dt:
                        break # Slot finishes after end of day

                    is_conflict = False
                    for task_start, task_end in parsed_tasks_list:
                        # This comparison will now work (local vs local)
                        if (slot_start < task_end) and (slot_end > task_start):
                            is_conflict = True
                            break 
                    
                    if not is_conflict:
                        valid_slots.append(slot_start)
                    
                    current_slot_start += timedelta(minutes=15)
                
                if valid_slots:
                    logger.info(f"Found {len(valid_slots)} valid random slots for today.")
                    found_slot_dt = random.choice(valid_slots)
                    # We store the *naive* version, as the DB expects this
                    task_dt_naive = found_slot_dt.replace(tzinfo=None)
                    local_time_str = found_slot_dt.strftime('%H:%M on %b %d')
                else:
                    logger.warning(f"Could not find any free slots for user {user_id} today.")
                    await update.message.reply_html(
                        f"I couldn't find any free slots for <b>{duration_minutes} minutes</b> today. 😥\n"
                        "Please try a shorter duration or schedule it manually (e.g., '...at 7pm')."
                    )
                    return 

            
            new_task = {
                "user_id": user_id,
                "title": title, 
                "scheduled_time": task_dt_naive.isoformat(), 
                "duration_minutes": duration_minutes,
                "is_completed": False
            }
            
            created_task_data = await db.create_task(new_task)
            
            if not created_task_data:
                 await update.message.reply_text("Oops! Something went wrong and I couldn't save the task. Please try again.")
                 return 

            await update.message.reply_html(
                f"<b>Task Scheduled!</b> 👍\n\n"
                f"<b>Task:</b> {title.replace('<', '&lt;').replace('>', '&gt;')}\n"
                f"<b>When:</b> {local_time_str} ({user_timezone.tzname(None)})\n"
                f"<b>Duration:</b> {duration_minutes} minutes"
            )
            
        except Exception as e:
            logger.error(f"Error in handle_ai_task_creation for chat {chat_id}: {e}")
            await update.message.reply_text("Oops! Something went wrong while trying to schedule that. Please try again.")
        
        finally:
            logger.info(f"Released task lock for chat_id {chat_id}")