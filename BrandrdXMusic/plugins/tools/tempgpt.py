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

# ================= CONFIGURATION =================
GEMINI_API_KEY = "AIzaSyASzHWkz__U3vfRtt-VyToX5vvzzYg7Ipg"
MONGO_URI = "mongodb+srv://akashkashyap8t2:Akking8t2@cluster0.t3sbtoi.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
MAX_HISTORY = 10
RATE_LIMIT = 3
RATE_LIMIT_PERIOD = 10
OWNER_ID = 5397621246
ADMINS = [OWNER_ID, 7819525628]  # Owner + Akash

# ================= FEMALE PERSONA CONFIG =================
PERSONA = {
    "name": "Priya",
    "mood": ["friendly", "sweet", "playful"],
    "emoji_style": ["🌸", "💖", "✨", "🥀"],
    "responses": {
        "greetings": [
            "Hello ji! Kaise ho aap? {}",
            "Hiiii~ Kya chal raha hai? {}",
            "Aapka din accha ja raha hai? {}"
        ],
        "farewell": [
            "Chalo, mai ja rahi hun! {}",
            "Baad mein baat karte hain {}",
            "Bye bye! Miss karo ge mujhe? {}"
        ],
        "random": [
            "Aaj mera mood bohot achha hai! {}",
            "Kuch interesting batao na... {}",
            "Mujhe music sunna bahut pasand hai! {}",
            "Aapke bare mein kuch batao? {}",
            "Kal movie dekhi thi, bohot achhi thi! {}"
        ]
    },
    "response_probability": 0.3  # 30% chance to respond randomly
}

# ================= INITIALIZE SERVICES =================
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["gemini_bot_db"]
chat_history_collection = db["chat_histories"]
user_last_requests = defaultdict(list)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-pro-latest")

# ================= HELPER FUNCTIONS =================
def clean_history_for_gemini(mongo_history):
    """Convert MongoDB history to Gemini-compatible format"""
    return [{
        "role": msg["role"],
        "parts": [{"text": part["text"]} for part in msg["parts"]]
    } for msg in mongo_history]

def should_respond(message, last_interaction_time):
    """Determine if bot should respond naturally"""
    # Always respond in private chats
    if message.chat.type == enums.ChatType.PRIVATE:
        return True
    
    # Check if mentioned
    if f"@{app.me.username}" in message.text:
        return True
    
    # Don't respond if last interaction was recent
    if datetime.now() - last_interaction_time < timedelta(minutes=5):
        return False
    
    # Random chance based on probability
    return random.random() < PERSONA["response_probability"]

# ================= RATE LIMITING =================
def rate_limit(func):
    async def wrapper(client, message):
        if message.from_user.id in ADMINS:
            return await func(client, message)
            
        user_id = message.from_user.id
        current_time = time.time()
        user_last_requests[user_id] = [t for t in user_last_requests[user_id] if current_time - t < RATE_LIMIT_PERIOD]
        
        if len(user_last_requests[user_id]) >= RATE_LIMIT:
            wait_time = int(RATE_LIMIT_PERIOD - (current_time - user_last_requests[user_id][0]))
            await message.reply_text(f"⏳ Please wait {wait_time} seconds")
            return
        
        user_last_requests[user_id].append(current_time)
        return await func(client, message)
    return wrapper

# ================= NATURAL CHAT HANDLER =================
@app.on_message(filters.text & ~filters.command(["ai", "ask", "broadcast", "play", "song"]))
async def natural_chat_response(bot: app, message: Message):
    try:
        # Get last interaction time
        last_interaction = chat_history_collection.find_one(
            {"user_id": message.from_user.id},
            {"last_active": 1}
        )
        last_time = last_interaction.get("last_active", datetime.min) if last_interaction else datetime.min
        
        # Check if should respond
        if not should_respond(message, last_time):
            return

        emoji = random.choice(PERSONA["emoji_style"])
        
        # Select response type based on context
        if any(word in message.text.lower() for word in ["hi", "hello", "hey", "namaste"]):
            response = random.choice(PERSONA["responses"]["greetings"]).format(emoji)
        elif any(word in message.text.lower() for word in ["bye", "goodbye", "alvida"]):
            response = random.choice(PERSONA["responses"]["farewell"]).format(emoji)
        else:
            # 50% chance to respond to random messages
            if random.random() > 0.5:
                response = random.choice(PERSONA["responses"]["random"]).format(emoji)
            else:
                return

        # Add typing action and slight delay
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        await asyncio.sleep(random.uniform(0.5, 1.5))  # Natural typing speed
        
        # Sometimes reply, sometimes send new message
        if random.random() > 0.7:
            await message.reply_text(response)
        else:
            await bot.send_message(message.chat.id, response)

        # Update last interaction time
        chat_history_collection.update_one(
            {"user_id": message.from_user.id},
            {"$set": {"last_active": datetime.now()}},
            upsert=True
        )

    except Exception as e:
        print(f"Natural chat error: {e}")

# ================= AI COMMAND HANDLER =================
@app.on_message(filters.command(["ai", "ask"], prefixes=["/", "!", "."]))
@rate_limit
async def ai_chat(bot: app, message: Message):
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        if not message.text or len(message.text.split()) < 2:
            return await message.reply_text("💡 Please ask me something!")
            
        query = message.text.split(maxsplit=1)[1]
        user_id = message.from_user.id
        
        # Get/update history
        user_data = chat_history_collection.find_one({"user_id": user_id}) or {
            "user_id": user_id,
            "history": [],
            "first_seen": datetime.now(),
            "last_active": datetime.now()
        }

        # Add user message
        user_data["history"].append({
            "role": "user",
            "parts": [{"text": query}],
            "time": datetime.now()
        })

        # Generate response
        chat = model.start_chat(history=clean_history_for_gemini(user_data["history"][-MAX_HISTORY:]))
        response = chat.send_message(query)
        
        # Add bot response
        user_data["history"].append({
            "role": "model",
            "parts": [{"text": response.text}],
            "time": datetime.now()
        })
        user_data["last_active"] = datetime.now()
        
        # Update DB
        chat_history_collection.update_one(
            {"user_id": user_id},
            {"$set": user_data},
            upsert=True
        )
        
        await message.reply_text(response.text[:4000])

    except Exception as e:
        error_msg = f"⚠️ Error: {str(e)[:200]}"
        if "blocked" in str(e).lower():
            error_msg = "🚫 This query violates safety guidelines"
        await message.reply_text(error_msg)

# ================= MUSIC BOT HANDLERS =================
@app.on_message(filters.command(["play", "song"]))
async def play_music(bot: app, message: Message):
    try:
        # Your existing music bot code here
        # ...
        
        # Add personality touch (20% chance)
        if random.random() > 0.8:
            emoji = random.choice(PERSONA["emoji_style"])
            await message.reply_text(f"Song ready! Enjoy karo {emoji}")
            
    except Exception as e:
        await message.reply_text(f"⚠️ Music Error: {str(e)[:200]}")

# ================= OWNER COMMANDS =================
@app.on_message(filters.command("botstats") & filters.user(ADMINS))
async def bot_stats(bot: app, message: Message):
    stats = {
        "total_users": chat_history_collection.count_documents({}),
        "active_users": chat_history_collection.count_documents({
            "last_active": {"$gt": datetime.now() - timedelta(days=1)}
        }),
        "total_requests": sum(len(v) for v in user_last_requests.values())
    }
    await message.reply_text(
        f"🤖 <b>Bot Statistics</b>\n"
        f"• 👥 Total Users: {stats['total_users']}\n"
        f"• 🎯 Active (24h): {stats['active_users']}\n"
        f"• 📊 Today's Requests: {stats['total_requests']}",
        parse_mode=ParseMode.HTML
    )

# ================= STARTUP =================
chat_history_collection.create_index("last_active", expireAfterSeconds=30*24*60*60)
print("🎵 Music Bot + 🤖 AI Assistant Started Successfully!")
