import logging
from datetime import datetime
from config import supabase
from utils import encrypt, decrypt 

logger = logging.getLogger(__name__)

async def get_user_settings_by_telegram_chat_id(chat_id: str):
    logger.info(f"Looking up user settings for chat_id: {chat_id}")
    try:
        response = (
            supabase.table("UserSettings")
            .select("user_id, timezone_offset, timetable_start, timetable_end")
            .eq("telegram_id", chat_id)
            .limit(1)
            .single()
            .execute()
        )
        if response.data:
            logger.info(f"Found settings for chat_id: {chat_id}")
            return response.data
        else:
            logger.warning(f"No user settings found for chat_id: {chat_id}")
            return None
    except Exception as e:
        logger.error(f"Error fetching user settings for chat_id {chat_id}: {e}")
        return None

async def fetch_schedule_for_user_in_range(user_id: str, range_start: datetime, range_end: datetime):
    try:
        logger.info(f"Fetching tasks for user {user_id} between {range_start.isoformat()} and {range_end.isoformat()}")
        response = (
            supabase.table("tasks")
            .select("*")
            .eq("user_id", user_id)
            .gte("scheduled_time", range_start.isoformat())
            .lt("scheduled_time", range_end.isoformat())
            .order("scheduled_time", desc=False)
            .execute()
        )
        
        if response.data:
            for task in response.data:
                if 'title' in task:
                    task['title'] = decrypt(task['title'])
        
        return response.data
    except Exception as e:
        logger.error(f"Error fetching tasks for user {user_id}: {e}")
        return []

async def update_user_timezone(chat_id: str, offset_str: str):
    try:
        response = (
            supabase.table("UserSettings")
            .update({"timezone_offset": offset_str})
            .eq("telegram_id", chat_id)
            .execute()
        )
        logger.info(f"Updated timezone for chat_id {chat_id}: {response.data}")
        return response.data
    except Exception as e:
        logger.error(f"Error updating timezone for chat_id {chat_id}: {e}")
        return None

async def create_task(new_task: dict):
    try:
        if 'title' in new_task:
            new_task['title'] = encrypt(new_task['title'])

        response = supabase.table("tasks").insert(new_task).execute()

        if response.data:
            for task in response.data:
                if 'title' in task:
                    task['title'] = decrypt(task['title'])
                    
        return response.data
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        return None

async def get_users_for_reminders():
    try:
        response = (
            supabase.table("UserSettings")
            .select("user_id, telegram_id, timezone_offset")
            .eq("notifications", True)
            .not_.is_("telegram_id", "null")
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"Error fetching users for reminders: {e}")
        return []

async def get_tasks_for_reminder(user_id: str, start_naive: datetime, end_naive: datetime):
    try:
        response = (
            supabase.table("tasks")
            .select("title, scheduled_time")
            .eq("user_id", user_id)
            .eq("is_completed", False)
            .gte("scheduled_time", start_naive.isoformat())
            .lt("scheduled_time", end_naive.isoformat())
            .execute()
        )
        if response.data:
            for task in response.data:
                if 'title' in task:
                    task['title'] = decrypt(task['title'])
                    
        return response.data
    except Exception as e:
        logger.error(f"Error fetching tasks for reminder: {e}")
        return []