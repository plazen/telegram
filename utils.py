import re
import logging
from datetime import datetime, timedelta, timezone
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import config 

logger = logging.getLogger(__name__)

KEY = bytes.fromhex(config.ENCRYPTION_KEY)
IV_LENGTH = 12
AUTH_TAG_LENGTH = 12

def encrypt(text: str) -> str:
    if not text:
        return text
    try:
        iv = get_random_bytes(IV_LENGTH)
        cipher = AES.new(KEY, AES.MODE_GCM, nonce=iv)
        encrypted_bytes, auth_tag = cipher.encrypt_and_digest(text.encode('utf-8'))
        
        iv_hex = iv.hex()
        auth_tag_hex = auth_tag.hex()
        encrypted_hex = encrypted_bytes.hex()
        
        return f"{iv_hex}:{auth_tag_hex}:{encrypted_hex}"
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return text  

def decrypt(hash_str: str) -> str:
    if not hash_str:
        return hash_str
    try:
        parts = hash_str.split(':')
        if len(parts) != 3:
            return hash_str
        
        iv = bytes.fromhex(parts[0])
        auth_tag = bytes.fromhex(parts[1])
        encrypted_text = bytes.fromhex(parts[2])
        
        cipher = AES.new(KEY, AES.MODE_GCM, nonce=iv)
        decrypted_bytes = cipher.decrypt_and_verify(encrypted_text, auth_tag)
        return decrypted_bytes.decode('utf-8')
    except (ValueError, TypeError) as e:
        logger.warning(f"Decryption failed for hash '{hash_str[:10]}...': {e}. Returning original text.")
        return hash_str
    except Exception as e:
        logger.error(f"An unexpected error occurred during decryption: {e}")
        return "[Decryption Error]"


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

def parse_duration_to_minutes(duration_str: str) -> int | None:
    duration_str = duration_str.lower().strip()
    logger.info(f"Parsing duration: {duration_str}")
    try:
        match = re.search(r"([\d\.]+)\s*(hour|hr|h)", duration_str)
        if match:
            return int(float(match.group(1)) * 60)
        
        match = re.search(r"([\d\.]+)\s*(minute|min|m)", duration_str)
        if match:
            return int(float(match.group(1)))
            
        match = re.search(r"^([\d\.]+)$", duration_str)
        if match:
            return int(float(match.group(1)))
            
        logger.warning(f"Could not parse duration: {duration_str}")
        return None
        
    except Exception as e:
        logger.error(f"Failed to parse duration '{duration_str}': {e}")
        return None

def parse_local_time_to_naive_datetime(time_str: str, user_timezone: timezone) -> datetime | None:
    time_str = time_str.strip().upper()
    logger.info(f"Parsing local time: {time_str} for timezone {user_timezone.tzname(None)}")
    
    time_formats_to_try = ["%H:%M", "%I:%M%p", "%I%p"] # e.g., "17:30", "5:30PM", "5PM"
    parsed_time = None
    
    for fmt in time_formats_to_try:
        try:
            parsed_time = datetime.strptime(time_str, fmt).time()
            break # Success
        except ValueError:
            continue
    
    if parsed_time is None:
        logger.warning(f"Could not parse time string: {time_str}")
        return None # Failed to parse

    now_local = datetime.now(user_timezone)
    
    task_dt_local = now_local.replace(
        hour=parsed_time.hour, 
        minute=parsed_time.minute, 
        second=0, 
        microsecond=0
    )

    if task_dt_local < now_local:
        logger.info("Parsed time is in the past, assuming tomorrow.")
        task_dt_local += timedelta(days=1)
        
    task_dt_naive = task_dt_local.replace(tzinfo=None)
    logger.info(f"Converted {time_str} to naive datetime {task_dt_naive.isoformat()} for DB storage")
    
    return task_dt_naive