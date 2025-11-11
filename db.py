import logging
from datetime import datetime
from config import supabase

logger = logging.getLogger(__name__)

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

async def update_user_timezone(chat_id: str, offset_str: str):
    logger.info(f"Updating timezone for chat_id {chat_id} to {offset_str}")
    try:
        response = (
            supabase.table("UserSettings")
            .update({"timezone_offset": offset_str})
            .eq("telegram_id", chat_id)
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"Error updating timezone for chat_id {chat_id}: {e}")
        return None

async def create_task(new_task: dict):
    try:
        response = supabase.table("tasks").insert(new_task).execute()
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
            .select("*")
            .eq("user_id", user_id)
            .eq("is_completed", False)
            .gte("scheduled_time", start_naive.isoformat())
            .lt("scheduled_time", end_naive.isoformat())
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"Error fetching tasks for reminder for user {user_id}: {e}")
        return []