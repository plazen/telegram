# Plazen Telegram Bot 🤖

This is a simple Telegram bot designed to integrate with the Plazen application. It allows users to retrieve their daily schedule from their Plazen account directly within Telegram by linking their Telegram Chat ID.

## Features

* **/start**: Get a welcome message and your unique Telegram Chat ID to link to your Plazen account.
* **/schedule**: Fetch and display your task schedule for the current day (UTC), including completion status, time, title, and duration.
* **/help**: Show a list of available commands.

## Setup and Installation

### 1. Prerequisites

* Python 3.x (the code uses `asyncio` features)
* A Telegram Bot. You will need the **Bot Token**.
* A Supabase project. You will need the project **URL** and the **Service Role Key**.

### 2. Install Dependencies

Install the required Python packages using the `requirements.txt` file:

pip install -r requirements.txt

### 3. Configure Environment Variables

This project uses a `.env` file to manage secret keys. Create a file named `.env` in the root directory.

Add the following environment variables to your `.env` file:

# .env
```
TELEGRAM_TOKEN=your_telegram_bot_token_here
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_KEY=your_supabase_service_role_key
```
### 4. Supabase Database Setup

This bot expects a specific Supabase database structure to function:

* A table named `UserSettings` with (at least):
    * `user_id` (e.g., UUID, Text)
    * `telegram_id` (Text) - *This stores the Chat ID from the /start command*.
* A table named `tasks` with (at least):
    * `user_id` (links to `UserSettings`)
    * `scheduled_time` (TimestampTz)
    * `title` (Text)
    * `is_completed` (Boolean)
    * `duration_minutes` (Number, optional)

## How to Run

Once your `.env` file is configured and dependencies are installed, run the bot:

```python main.py ```

The bot will start polling for messages.

## License

This project is licensed under the MIT License.
Copyright (c) 2025 Plazen