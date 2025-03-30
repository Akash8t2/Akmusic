import os
import time
import random
import asyncio
from pyrogram import filters, enums
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.types import Message
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

# Connection lock for thread safety
connection_lock = asyncio.Lock()
user_last_requests = defaultdict(list)

# Initialize Gemini
if GEMINI_API_KEY != "your_api_key_here":
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            generation_config={"max_output_tokens": 500}
        )
        gemini_available = True
    except Exception as e:
        print(f"⚠️ Gemini init error: {e}")
        gemini_available = False
else:
    gemini_available = False

# ================= ENHANCED PERSONA =================
PERSONA = {
    "name": "Priya",
    "mood": random.choice(["friendly", "sweet", "playful"]),
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
    },
    "fallbacks": [
        "Hmm...thoda time do {}",
        "Abhi busy hun...baad mein? {}"
    ]
}

# ================= DATABASE SETUP =================
mongo_client = MongoClient(
    MONGO_URI,
    maxPoolSize=50,
    connectTimeoutMS=30000,
    socketTimeoutMS=30000
)
db = mongo_client["music_ai_bot"]
chat_history = db["chat_history"]
group_memory = db["group_memory"]

# ================= SAFE OPERATIONS =================
async def safe_send_message(chat_id, text, reply_to=None):
    """Thread-safe message sending with retry"""
    async with connection_lock:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if reply_to:
                    return await app.send_message(
                        chat_id,
                        text,
                        reply_to_message_id=reply_to
                    )
                return await app.send_message(chat_id, text)
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Failed to send after {max_retries} attempts: {e}")
                await asyncio.sleep(1)

async def safe_store_message(chat_id, user_id, text, is_group=False):
    """Safe message storage"""
    async with connection_lock:
        try:
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
        except Exception as e:
            print(f"Database error: {e}")

# ================= MESSAGE HANDLERS =================
@app.on_message(filters.group & filters.text & ~filters.command(["start", "help", "ai"]))
async def handle_group_message(bot: app, message: Message):
    """Handle group messages safely"""
    try:
        await safe_store_message(
            message.chat.id,
            message.from_user.id,
            message.text,
            is_group=True
        )

        # 30% response chance with cooldown
        last_msg = group_memory.find_one(
            {"user_id": message.from_user.id},
            sort=[("timestamp", -1)]
        )
        if last_msg and (datetime.now() - last_msg["timestamp"]).seconds < 120:
            return
        if random.random() > 0.3:
            return

        # Generate and send response
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        await asyncio.sleep(random.uniform(0.5, 1.5))
        response = generate_response(message.text)
        await safe_send_message(message.chat.id, response, reply_to=message.id)

    except Exception as e:
        print(f"Group chat error: {e}")

@app.on_message(filters.command(["ai", "ask"]))
async def handle_ai_command(bot: app, message: Message):
    """Handle AI queries safely"""
    try:
        if not gemini_available:
            fallback = random.choice(PERSONA["fallbacks"]).format(PERSONA["emoji"])
            return await safe_send_message(message.chat.id, fallback)

        query = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
        if not query:
            return await safe_send_message(message.chat.id, "Kuch to pucho ji? 🥀")

        # Rate limiting
        async with connection_lock:
            user_id = message.from_user.id
            now = time.time()
            user_requests = [t for t in user_last_requests.get(user_id, []) if now - t < RATE_LIMIT_PERIOD]
            
            if len(user_requests) >= RATE_LIMIT:
                wait_time = RATE_LIMIT_PERIOD - (now - user_requests[0])
                return await safe_send_message(
                    message.chat.id,
                    f"Please wait {int(wait_time)} seconds"
                )
            user_last_requests[user_id] = user_requests + [now]

        # Process query
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        response = model.generate_content(query)
        await safe_send_message(
            message.chat.id,
            response.text[:1000],
            reply_to=message.id
        )

    except Exception as e:
        error_msg = random.choice(PERSONA["fallbacks"]).format(PERSONA["emoji"])
        if "429" in str(e):
            error_msg = "Thoda rest kar leti hun...baad mein puchna 🌸"
        await safe_send_message(message.chat.id, error_msg)

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
