import os
import time
import asyncio
import random
from pyrogram import filters, enums
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from BrandrdXMusic import app
import google.generativeai as genai
from pymongo import MongoClient
from datetime import datetime, timedelta
from collections import defaultdict
import pytz
import logging

# ================= LOGGING SETUP =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= CONFIGURATION =================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_api_key_here")
MONGO_URI = os.getenv("MONGO_URI", "your_mongodb_uri_here")
MAX_HISTORY = 15
RATE_LIMIT = 5
RATE_LIMIT_PERIOD = 15
OWNER_ID = 5397621246
ADMINS = [OWNER_ID, 7819525628]
TIMEZONE = pytz.timezone('Asia/Kolkata')

# ================= PERSONA CONFIG =================
PERSONA = {
    "name": "Priya",
    "emoji_style": ["🌸", "💖", "✨", "🥀", "🎶", "🤗", "💫"],
    "active_hours": {
        "morning": (8, 11),
        "afternoon": (13, 16), 
        "evening": (18, 22)
    }
}

# ================= INITIALIZE SERVICES =================
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["gemini_bot_db"]
    chat_history_collection = db["chat_histories"]
    group_activity_collection = db["group_activity"]
    logger.info("Database connection established successfully")
except Exception as e:
    logger.error(f"Database connection failed: {e}")
    raise

try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-pro-latest")
    logger.info("Gemini AI initialized successfully")
except Exception as e:
    logger.error(f"Gemini initialization failed: {e}")
    raise

# ================= HELPER FUNCTIONS =================
def get_current_hour():
    return datetime.now(TIMEZONE).hour

def is_active_time():
    current_hour = get_current_hour()
    for period_name, (start, end) in PERSONA["active_hours"].items():
        if start <= current_hour <= end:
            return True
    return False

def clean_history_for_gemini(mongo_history):
    try:
        return [{
            "role": msg["role"],
            "parts": [{"text": part["text"]} for part in msg["parts"]]
        } for msg in mongo_history]
    except Exception as e:
        logger.error(f"Error cleaning history: {e}")
        return []

def update_group_activity(chat_id):
    try:
        group_activity_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {
                "last_active": datetime.now(),
                "next_available": datetime.now() + timedelta(hours=1.5)
            }},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error updating group activity: {e}")

def create_enhanced_query(context_messages, query):
    try:
        if context_messages:
            nl = '\n'  # Define newline separately
            return f"Context:{nl.join(reversed(context_messages))}{nl}{nl}Question: {query}"
        return query
    except Exception as e:
        logger.error(f"Error creating enhanced query: {e}")
        return query

# ================= MESSAGE HANDLERS =================
@app.on_message(filters.command(["ai", "ask"], prefixes=["/", "!", "."]))
async def ai_chat_handler(bot: app, message: Message):
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        if not message.text or len(message.text.split()) < 2:
            return await message.reply_text("💡 Please ask me something with /ai your_question")

        query = message.text.split(maxsplit=1)[1]
        user_id = message.from_user.id
        
        # Get context from last 5 messages
        context_messages = []
        if message.chat.type != enums.ChatType.PRIVATE:
            async for msg in bot.get_chat_history(message.chat.id, limit=5):
                if msg.text and not msg.text.startswith(('/', '!', '.')):
                    context_messages.append(f"{msg.from_user.first_name}: {msg.text}")

        enhanced_query = create_enhanced_query(context_messages, query)

        # Get/update user data
        user_data = chat_history_collection.find_one({"user_id": user_id}) or {
            "user_id": user_id,
            "history": [],
            "first_seen": datetime.now(),
            "last_active": datetime.now()
        }

        # Add user message to history
        user_data["history"].append({
            "role": "user",
            "parts": [{"text": enhanced_query}],
            "time": datetime.now()
        })

        # Generate response
        chat = model.start_chat(history=clean_history_for_gemini(user_data["history"][-MAX_HISTORY:]))
        response = await asyncio.to_thread(chat.send_message, enhanced_query)
        
        # Add bot response to history
        user_data["history"].append({
            "role": "model",
            "parts": [{"text": response.text}],
            "time": datetime.now()
        })
        user_data["last_active"] = datetime.now()
        
        # Update database
        chat_history_collection.update_one(
            {"user_id": user_id},
            {"$set": user_data},
            upsert=True
        )
        
        # Send response
        emoji = random.choice(PERSONA["emoji_style"])
        formatted_response = f"{response.text[:4000]}\n\n{emoji}"
        await message.reply_text(formatted_response)

    except Exception as e:
        error_msg = f"⚠️ Error: {str(e)[:200]}"
        logger.error(f"AI chat error: {error_msg}")
        await message.reply_text(error_msg)

# ================= STARTUP =================
async def initialize_bot():
    try:
        # Create indexes
        chat_history_collection.create_index("last_active", expireAfterSeconds=30*24*60*60)
        group_activity_collection.create_index("last_active")
        group_activity_collection.create_index("next_available")
        
        logger.info("🎵 Music Bot + 🤖 AI Assistant Started Successfully!")
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise

app.run(initialize_bot())
