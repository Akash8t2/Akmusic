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

# ================= CONFIGURATION =================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_api_key_here")
MONGO_URI = os.getenv("MONGO_URI", "your_mongodb_uri_here")
MAX_HISTORY = 15
RATE_LIMIT = 5
RATE_LIMIT_PERIOD = 15
OWNER_ID = 5397621246
ADMINS = [OWNER_ID, 7819525628]
TIMEZONE = pytz.timezone('Asia/Kolkata')

# ================= ENHANCED PERSONA CONFIG =================
PERSONA = {
    "name": "Priya",
    "mood": ["friendly", "sweet", "playful", "emotional", "supportive"],
    "emoji_style": ["🌸", "💖", "✨", "🥀", "🎶", "🤗", "💫"],
    "active_hours": {
        "morning": (8, 11),
        "afternoon": (13, 16),
        "evening": (18, 22)
    },
    "group_activity": {
        "min_interval": timedelta(minutes=20),
        "max_interval": timedelta(minutes=30),
        "break_duration": timedelta(hours=1.5)
    },
    "responses": {
        "greetings": [
            "Hello ji! Kaise ho aap? {}",
            "Hiiii~ Kya chal raha hai? {}",
            "Aapka din accha ja raha hai? {}",
            "Namaste! Main aa gayi {}",
            "Sabko mera pyar bhara pyaar! {}"
        ],
        "farewell": [
            "Chalo, mai ja rahi hun! {}",
            "Baad mein baat karte hain {}",
            "Bye bye! Miss karo ge mujhe? {}",
            "Thoda kaam hai, jaldi wapas aungi {}",
            "Mujhe jaana padega, par main wapas aungi {}"
        ],
        "random": [
            "Aaj mera mood bohot achha hai! {}",
            "Kuch interesting batao na... {}",
            "Mujhe music sunna bahut pasand hai! {}",
            "Aapke bare mein kuch batao? {}",
            "Kal movie dekhi thi, bohot achhi thi! {}",
            "Tum log kya kar rahe ho? {}",
            "Mujhe lagta hai aaj kuch special hone wala hai {}",
            "Kya aapko lagta hai AI dosto ki tarah baat kar sakti hai? {}"
        ],
        "follow_up": [
            "Aapne pichle baar {} ke bare mein kaha tha, uska kya hua? {}",
            "Yaad hai tumne {} ke bare mein bataya tha? {}",
            "Mujhe yaad aaya, tum {} ki baat kar rahe the {}",
            "Aaj phir se {} ki baat chali hai {}"
        ]
    },
    "response_probability": 0.25
}

# ================= INITIALIZE SERVICES =================
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["gemini_bot_db"]
chat_history_collection = db["chat_histories"]
group_activity_collection = db["group_activity"]
user_last_requests = defaultdict(list)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-pro-latest")

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
    return [{
        "role": msg["role"],
        "parts": [{"text": part["text"]} for part in msg["parts"]]
    } for msg in mongo_history]

def get_last_group_activity(chat_id):
    activity = group_activity_collection.find_one({"chat_id": chat_id})
    return activity.get("last_active") if activity else None

def update_group_activity(chat_id):
    group_activity_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"last_active": datetime.now(), "next_available": datetime.now() + PERSONA["group_activity"]["break_duration"]}},
        upsert=True
    )

def extract_topics(text):
    topics = []
    for word in text.lower().split():
        if word in ["movie", "music", "song", "dance", "food", "travel", "work", "study"]:
            topics.append(word)
    return topics if topics else ["general"]

# ================= FIXED TOPICS UPDATE FUNCTION =================
def update_user_topics(user_data, query):
    try:
        existing_topics = user_data.get("topics", [])
        new_topics = extract_topics(query)
        combined_topics = list(set(existing_topics + new_topics))
        user_data["topics"] = combined_topics[-10:]  # Keep last 10 topics
    except Exception as e:
        print(f"Error updating topics: {e}")
        user_data["topics"] = user_data.get("topics", [])[-10:]  # Fallback
    return user_data

# ================= MESSAGE HANDLERS =================
@app.on_message(filters.group & filters.text & ~filters.command(["ai", "ask", "broadcast", "play", "song"]))
async def smart_group_interaction(bot: app, message: Message):
    try:
        chat_id = message.chat.id
        
        if not should_respond_in_group(chat_id, message):
            return

        last_messages = []
        async for msg in bot.get_chat_history(chat_id, limit=5):
            if msg.text and not msg.text.startswith(('/', '!', '.')):
                last_messages.append(msg.text)
        
        topics = set()
        for msg in last_messages:
            topics.update(extract_topics(msg))
        
        emoji = random.choice(PERSONA["emoji_style"])
        
        user_data = chat_history_collection.find_one(
            {"user_id": message.from_user.id},
            {"history": 1, "topics": 1}
        ) or {"history": [], "topics": []}
        
        response = None
        if user_data and random.random() > 0.6:
            for msg in reversed(user_data.get("history", [])):
                if msg["role"] == "user":
                    msg_topics = extract_topics(msg["parts"][0]["text"])
                    common_topics = topics.intersection(msg_topics)
                    if common_topics:
                        topic = random.choice(list(common_topics))
                        response = random.choice(PERSONA["responses"]["follow_up"]).format(
                            topic, emoji
                        )
                        break
        
        if not response:
            if any(word in message.text.lower() for word in ["hi", "hello", "hey", "namaste"]):
                response = random.choice(PERSONA["responses"]["greetings"]).format(emoji)
            elif any(word in message.text.lower() for word in ["bye", "goodbye", "alvida"]):
                response = random.choice(PERSONA["responses"]["farewell"]).format(emoji)
            elif random.random() < PERSONA["response_probability"]:
                response = random.choice(PERSONA["responses"]["random"]).format(emoji)
            else:
                return

        typing_duration = min(1.5, max(0.5, len(response) / 40))
        await bot.send_chat_action(chat_id, ChatAction.TYPING)
        await asyncio.sleep(typing_duration)
        
        if random.random() > 0.7:
            await message.reply_text(response)
        else:
            await bot.send_message(chat_id, response)

        update_group_activity(chat_id)

    except Exception as e:
        print(f"Group interaction error: {e}")

@app.on_message(filters.command(["ai", "ask"], prefixes=["/", "!", "."]))
@rate_limit
async def enhanced_ai_chat(bot: app, message: Message):
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        if not message.text or len(message.text.split()) < 2:
            return await message.reply_text("💡 Please ask me something with /ai your_question")
            
        query = message.text.split(maxsplit=1)[1]
        user_id = message.from_user.id
        
        context_messages = []
        if message.chat.type != enums.ChatType.PRIVATE:
            async for msg in bot.get_chat_history(message.chat.id, limit=5):
                if msg.text and not msg.text.startswith(('/', '!', '.')):
                    context_messages.append(f"{msg.from_user.first_name}: {msg.text}")
        
        enhanced_query = f"Context:\n{'\n'.join(reversed(context_messages))}\n\nQuestion: {query}" if context_messages else query

        user_data = chat_history_collection.find_one({"user_id": user_id}) or {
            "user_id": user_id,
            "history": [],
            "first_seen": datetime.now(),
            "last_active": datetime.now(),
            "topics": []
        }

        user_data["history"].append({
            "role": "user",
            "parts": [{"text": enhanced_query}],
            "time": datetime.now()
        })

        user_data = update_user_topics(user_data, query)

        chat = model.start_chat(history=clean_history_for_gemini(user_data["history"][-MAX_HISTORY:]))
        response = await asyncio.to_thread(chat.send_message, enhanced_query)
        
        user_data["history"].append({
            "role": "model",
            "parts": [{"text": response.text}],
            "time": datetime.now()
        })
        user_data["last_active"] = datetime.now()
        
        chat_history_collection.update_one(
            {"user_id": user_id},
            {"$set": user_data},
            upsert=True
        )
        
        emoji = random.choice(PERSONA["emoji_style"])
        formatted_response = f"{response.text[:4000]}\n\n{emoji}"
        await message.reply_text(formatted_response)

    except Exception as e:
        error_msg = f"⚠️ Error: {str(e)[:200]}"
        if "blocked" in str(e).lower():
            error_msg = "🚫 Yeh sawal safety guidelines ke khilaf hai"
        elif "timeout" in str(e).lower():
            error_msg = "⏳ Server busy hai, thoda wait karke phir try karo"
        await message.reply_text(error_msg)

# ================= STARTUP =================
async def initialize_bot():
    chat_history_collection.create_index("last_active", expireAfterSeconds=30*24*60*60)
    group_activity_collection.create_index("last_active")
    group_activity_collection.create_index("next_available")
    print("🎵 Music Bot + 🤖 AI Assistant Started Successfully!")

app.run(initialize_bot())
