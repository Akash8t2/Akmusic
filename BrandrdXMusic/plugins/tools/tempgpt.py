import os
import time
import asyncio
import random
import logging
from datetime import datetime, timedelta
from collections import defaultdict
import pytz
import nest_asyncio
from pyrogram import Client, filters, enums
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
import google.generativeai as genai
from pymongo import MongoClient

# Fix event loop issues
nest_asyncio.apply()

# ================= LOGGING CONFIG =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= CONFIGURATION =================
CONFIG = {
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", "your_api_key_here"),
    "MONGO_URI": os.getenv("MONGO_URI", "your_mongodb_uri_here"),
    "MAX_HISTORY": 15,
    "RATE_LIMIT": 5,
    "RATE_LIMIT_PERIOD": 15,
    "OWNER_ID": 5397621246,
    "ADMINS": [5397621246, 7819525628],
    "TIMEZONE": pytz.timezone('Asia/Kolkata'),
    "API_ID": os.getenv("API_ID"),
    "API_HASH": os.getenv("API_HASH"),
    "BOT_TOKEN": os.getenv("BOT_TOKEN")
}

# ================= PERSONA CONFIG =================
PERSONA = {
    "name": "Priya",
    "emoji_style": ["🌸", "💖", "✨", "🥀", "🎶", "🤗", "💫"],
    "active_hours": {
        "morning": (8, 11),
        "afternoon": (13, 16), 
        "evening": (18, 22)
    },
    "responses": {
        "greetings": [
            "Hello ji! Kaise ho aap? {}",
            "Hiiii~ Kya chal raha hai? {}"
        ],
        "error": "⚠️ Oops! Kuch to gadbad hai. Thoda wait karo, phir try karo {}"
    }
}



# ================= DATABASE & AI SETUP =================
class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.chat_history = None
        self.group_activity = None
        
    async def initialize(self):
        try:
            self.client = MongoClient(CONFIG["MONGO_URI"])
            self.db = self.client["gemini_bot_db"]
            self.chat_history = self.db["chat_histories"]
            self.group_activity = self.db["group_activity"]
            
            # Create indexes
            self.chat_history.create_index("last_active", expireAfterSeconds=30*24*60*6t_active")
            self.group_activity.create_index("next_available")
            
            logger.info("Database initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Database error: {e}")
            return False

class AIService:
    def __init__(self):
        self.model = None
        
    async def initialize(self):
        try:
            genai.configure(api_key=CONFIG["GEMINI_API_KEY"])
            self.model = genai.GenerativeModel("gemini-1.5-pro-latest")
            logger.info("Gemini AI initialized successfully")
            return True
        except Exception as e:
            logger.error(f"AI initialization error: {e}")
            return False

# ================= HELPER FUNCTIONS =================
def get_current_hour():
    return datetime.now(CONFIG["TIMEZONE"]).hour

def is_active_time():
    current_hour = get_current_hour()
    for period_name, (start, end) in PERSONA["active_hours"].items():
        if start <= current_hour <= end:
            return True
    return False

async def create_enhanced_query(context_messages, query):
    try:
        if context_messages:
            nl = '\n'
            return f"Context:{nl.join(reversed(context_messages))}{nl}{nl}Question: {query}"
        return query
    except Exception as e:
        logger.error(f"Query creation error: {e}")
        return query

# ================= MESSAGE HANDLERS =================
@app.on_message(filters.command(["ai", "ask"]))
async def handle_ai_query(client, message):
    try:
        await client.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        if not message.text or len(message.text.split()) < 2:
            return await message.reply_text("💡 Please ask me something with /ai your_question")

        query = message.text.split(maxsplit=1)[1]
        user_id = message.from_user.id
        
        # Get context
        context_messages = []
        if message.chat.type != enums.ChatType.PRIVATE:
            async for msg in client.get_chat_history(message.chat.id, limit=5):
                if msg.text and not msg.text.startswith(('/', '!', '.')):
                    context_messages.append(f"{msg.from_user.first_name}: {msg.text}")

        enhanced_query = await create_enhanced_query(context_messages, query)
        
        # Generate response
        response = await asyncio.to_thread(
            ai_service.model.generate_content,
            enhanced_query
        )
        
        # Send response
        emoji = random.choice(PERSONA["emoji_style"])
        await message.reply_text(f"{response.text[:4000]}\n\n{emoji}")
        
    except Exception as e:
        emoji = random.choice(PERSONA["emoji_style"])
        await message.reply_text(PERSONA["responses"]["error"].format(emoji))
        logger.error(f"AI query error: {e}")

@app.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply_text("Namaste! Main BrandrdXMusic bot hoon. Kaise madad kar sakta hoon?")

# ================= MAIN FUNCTION =================
async def main():
    # Initialize services
    db = Database()
    ai = AIService()
    
    if not await db.initialize():
        logger.error("Failed to initialize database")
        return
        
    if not await ai.initialize():
        logger.error("Failed to initialize AI service")
        return
        
    # Store globally
    global db_service, ai_service
    db_service = db
    ai_service = ai
    
    # Start bot
    await app.start()
    logger.info("Bot started successfully!")
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        if 'app' in globals():
            asyncio.run(app.stop())
        logger.info("Bot shutdown complete")
