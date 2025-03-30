import os
import time
import random
import asyncio
from pyrogram import filters, enums
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.types import Message
from BrandrdXMusic import app
from pymongo import MongoClient
from datetime import datetime, timedelta
from collections import defaultdict

# ================= CONFIGURATION =================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_api_key_here")
MONGO_URI = os.getenv("MONGO_URI", "your_mongodb_uri_here")
MAX_HISTORY = 10
GROUP_MEMORY_MINUTES = 3
RATE_LIMIT = 2
RATE_LIMIT_PERIOD = 15
OWNER_ID = 5397621246
ADMINS = [OWNER_ID, 7819525628]

# Initialize Gemini only if API key exists
if GEMINI_API_KEY != "your_api_key_here":
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        gemini_available = True
    except Exception as e:
        print(f"⚠️ Gemini init error: {e}")
        gemini_available = False
else:
    gemini_available = False

# ================= PERSONA CONFIG =================
PERSONA = {
    "name": "Priya",
    "emoji": random.choice(["🌸", "💖", "✨", "🥀"]),
    "responses": {
        "greeting": [
            "Hello ji! Kaise ho? {}",
            "Hiiii~ Aaj kya plan hai? {}"
        ],
        "farewell": [
            "Chalo, baad mein baat karte hain {}",
            "Bye bye! {}"
        ],
        "casual": [
            "Aaj mera mood achha hai! {}",
            "Kuch interesting batao na... {}"
        ]
    }
}

# ================= DATABASE SETUP =================
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["gemini_bot_db"]
chat_history = db["chat_history"]
group_memory = db["group_memory"]

# ================= HELPER FUNCTIONS =================
async def get_group_context(chat_id):
    """Get last 3 minutes of group chat"""
    cutoff = datetime.now() - timedelta(minutes=GROUP_MEMORY_MINUTES)
    return list(group_memory.find({
        "chat_id": chat_id,
        "timestamp": {"$gt": cutoff}
    }).sort("timestamp", -1).limit(5))

async def store_message(chat_id, user_id, text, is_group=False):
    """Store message in database"""
    if is_group:
        group_memory.insert_one({
            "chat_id": chat_id,
            "user_id": user_id,
            "text": text,
            "timestamp": datetime.now()
        })
    else:
        chat_history.update_one(
            {"user_id": user_id},
            {"$push": {"messages": text}},
            upsert=True
        )

def generate_response(message_text):
    """Generate persona-based response"""
    if any(word in message_text.lower() for word in ["hi", "hello", "hey"]):
        return random.choice(PERSONA["responses"]["greeting"]).format(PERSONA["emoji"])
    elif any(word in message_text.lower() for word in ["bye", "goodbye"]):
        return random.choice(PERSONA["responses"]["farewell"]).format(PERSONA["emoji"])
    else:
        return random.choice(PERSONA["responses"]["casual"]).format(PERSONA["emoji"])

# ================= MESSAGE HANDLERS =================
@app.on_message(filters.group & filters.text & ~filters.command(["start", "help", "ai"]))
async def handle_group_message(bot: app, message: Message):
    """Handle group messages with 30% response chance"""
    try:
        # Store message
        await store_message(
            message.chat.id,
            message.from_user.id,
            message.text,
            is_group=True
        )

        # 30% response chance with 2-minute cooldown
        last_msg = group_memory.find_one(
            {"user_id": message.from_user.id},
            sort=[("timestamp", -1)]
        )
        if last_msg and (datetime.now() - last_msg["timestamp"]).seconds < 120:
            return
        if random.random() > 0.3:
            return

        # Generate response
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        await asyncio.sleep(random.uniform(0.5, 1.5))
        response = generate_response(message.text)
        await message.reply_text(response)

    except Exception as e:
        print(f"Group chat error: {e}")

@app.on_message(filters.command(["ai", "ask"]))
async def handle_ai_command(bot: app, message: Message):
    """Handle AI queries with rate limiting"""
    try:
        if not gemini_available:
            return await message.reply_text("AI service temporarily unavailable 🌸")

        query = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
        if not query:
            return await message.reply_text("Please ask something after /ai")

        # Rate limiting
        user_id = message.from_user.id
        now = time.time()
        user_requests = [t for t in user_last_requests.get(user_id, []) if now - t < RATE_LIMIT_PERIOD]
        
        if len(user_requests) >= RATE_LIMIT:
            wait_time = RATE_LIMIT_PERIOD - (now - user_requests[0])
            return await message.reply_text(f"Please wait {int(wait_time)} seconds")

        user_last_requests[user_id] = user_requests + [now]

        # Process query
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        response = model.generate_content(query)
        await message.reply_text(response.text[:1000])

    except Exception as e:
        await message.reply_text(f"Error: {str(e)[:200]}")

# ================= STARTUP =================
print("""
🎵 Music Bot + 💬 AI Assistant Started!
• Group Memory: {} minutes
• Persona: {}
• Gemini: {}
""".format(
    GROUP_MEMORY_MINUTES,
    PERSONA["name"],
    "Enabled" if gemini_available else "Disabled"
))
