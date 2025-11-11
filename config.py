import os
import logging
from dotenv import load_dotenv
from supabase import create_client, AsyncClient

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY") 
print(ENCRYPTION_KEY)

# Validate environment variables
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable is not set.")
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL environment variable is not set.")
if not SUPABASE_SERVICE_KEY:
    raise ValueError("SUPABASE_SERVICE_KEY environment variable is not set. (This must be your Service Role key)")
if not ENCRYPTION_KEY or len(ENCRYPTION_KEY) != 64:
    logger.error("ENCRYPTION_KEY environment variable is not set or is not a 64-character hex string.")
    raise ValueError("ENCRYPTION_KEY environment variable is not set or is not a 64-character hex string.")

# Initialize Supabase client
try:
    supabase: AsyncClient = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    raise