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

# Load environment variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

# Validate environment variables
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable is not set.")
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL environment variable is not set.")
if not SUPABASE_SERVICE_KEY:
    raise ValueError("SUPABASE_SERVICE_KEY environment variable is not set. (This must be your Service Role key)")

# Initialize Supabase client
try:
    supabase: AsyncClient = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
except Exception as e:
    logging.getLogger(__name__).error(f"Failed to initialize Supabase client: {e}")
    raise