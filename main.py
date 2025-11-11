import asyncio
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Import config, handlers, and jobs
import config
import handlers
import jobs

logger = logging.getLogger(__name__)

async def main() -> None:
    # Use the token from the config file
    application = Application.builder().token(config.TELEGRAM_TOKEN).build()
    
    # Add handlers from the handlers.py file
    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(CommandHandler("schedule", handlers.schedule_command))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("timezone", handlers.timezone_command))
    
    # Add the message handler for AI task creation
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_ai_task_creation))
    
    try:
        logger.info("Initializing application...")
        await application.initialize() 
        
        logger.info("Starting bot polling...")
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        # Main loop for running background jobs
        while True:
            # Run the reminder check from jobs.py
            await jobs.check_and_send_reminders(application)
            # Wait 60 seconds before checking again
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