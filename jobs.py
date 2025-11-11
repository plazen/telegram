import logging
from datetime import datetime, timedelta
from telegram.ext import Application
from telegram.constants import ParseMode
import db
import utils

logger = logging.getLogger(__name__)

async def check_and_send_reminders(application: Application) -> None:
    logger.info("Checking for task reminders...")
    
    try:
        users = await db.get_users_for_reminders()
        
        if not users:
            logger.info("No users have notifications enabled. Skipping reminder check.")
            return

        for user in users:
            user_id = user.get('user_id')
            chat_id = user.get('telegram_id')
            user_timezone = utils.parse_timezone_offset(user.get('timezone_offset'))

            if not (user_id and chat_id and user_timezone):
                logger.warning(f"Skipping reminders for user {user_id}: missing chat_id or timezone.")
                continue

            try:
                now_local = datetime.now(user_timezone)
                now_rounded = now_local.replace(second=0, microsecond=0)
                
                reminder_start_time = now_rounded + timedelta(minutes=30)
                reminder_end_time = reminder_start_time + timedelta(minutes=1)

                reminder_start_naive = reminder_start_time.replace(tzinfo=None)
                reminder_end_naive = reminder_end_time.replace(tzinfo=None)

                tasks = await db.get_tasks_for_reminder(user_id, reminder_start_naive, reminder_end_naive)

                if not tasks:
                    continue 

                logger.info(f"Found {len(tasks)} tasks for user {user_id} needing reminders.")

                for task in tasks:
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