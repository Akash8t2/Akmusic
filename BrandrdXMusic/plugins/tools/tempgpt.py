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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyASzHWkz__U3vfRtt-VyToX5vvzzYg7Ipg")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://akashkashyap8t2:Akking8t2@cluster0.t3sbtoi.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
MAX_HISTORY = 15  # Increased context window
RATE_LIMIT = 5
RATE_LIMIT_PERIOD = 15
OWNER_ID = 5397621246
ADMINS = [OWNER_ID, 7819525628]  # Owner + Akash
TIMEZONE = pytz.timezone('Asia/Kolkata')

# ================= ENHANCED FEMALE PERSONA CONFIG =================
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
    "response_probability": 0.25  # Reduced random response chance
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
    """Get current hour in Indian timezone"""
    return datetime.now(TIMEZONE).hour

def is_active_time():
    """Check if it's within persona's active hours"""
    current_hour = get_current_hour()
    for period_name, (start, end) in PERSONA["active_hours"].items():
        if start <= current_hour <= end:
            return True
    return False

def clean_history_for_gemini(mongo_history):
    """Convert MongoDB history to Gemini-compatible format"""
    return [{
        "role": msg["role"],
        "parts": [{"text": part["text"]} for part in msg["parts"]]
    } for msg in mongo_history]

def get_last_group_activity(chat_id):
    """Get last activity time in group"""
    activity = group_activity_collection.find_one({"chat_id": chat_id})
    return activity.get("last_active") if activity else None

def update_group_activity(chat_id):
    """Update last activity time for group"""
    group_activity_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"last_active": datetime.now(), "next_available": datetime.now() + PERSONA["group_activity"]["break_duration"]}},
        upsert=True
    )

def should_respond_in_group(chat_id, message=None):
    """Determine if bot should respond in group"""
    # Never respond if not active hours
    if not is_active_time():
        return False
    
    last_activity = get_last_group_activity(chat_id)
    
    # If never active in this group, 50% chance to start
    if not last_activity:
        return random.random() > 0.5
    
    time_since_last = datetime.now() - last_activity
    
    # If within min interval, don't respond
    if time_since_last < PERSONA["group_activity"]["min_interval"]:
        return False
    
    # If past max interval, definitely respond
    if time_since_last > PERSONA["group_activity"]["max_interval"]:
        return True
    
    # Otherwise increasing probability based on time passed
    progress = (time_since_last - PERSONA["group_activity"]["min_interval"]) / \
               (PERSONA["group_activity"]["max_interval"] - PERSONA["group_activity"]["min_interval"])
    return random.random() < progress

def extract_topics(text):
    """Extract potential conversation topics"""
    # This is simplified - you might want to use NLP here
    topics = []
    for word in text.lower().split():
        if word in ["movie", "music", "song", "dance", "food", "travel", "work", "study"]:
            topics.append(word)
    return topics if topics else ["general"]

# ================= ENHANCED RATE LIMITING =================
def rate_limit(func):
    async def wrapper(client, message):
        if message.from_user.id in ADMINS:
            return await func(client, message)
            
        user_id = message.from_user.id
        current_time = time.time()
        
        # Clear old requests
        user_last_requests[user_id] = [t for t in user_last_requests[user_id] 
                                     if current_time - t < RATE_LIMIT_PERIOD]
        
        if len(user_last_requests[user_id]) >= RATE_LIMIT:
            wait_time = int(RATE_LIMIT_PERIOD - (current_time - user_last_requests[user_id][0]))
            if random.random() > 0.7:  # 30% chance to show wait message
                await message.reply_text(
                    f"⏳ Thoda intezaar karo {random.choice(PERSONA['emoji_style'])}\n"
                    f"{wait_time} seconds baad try karna"
                )
            return
        
        user_last_requests[user_id].append(current_time)
        return await func(client, message)
    return wrapper

# ================= SMART GROUP INTERACTION HANDLER =================
@app.on_message(filters.group & filters.text & ~filters.command(["ai", "ask", "broadcast", "play", "song"]))
async def smart_group_interaction(bot: app, message: Message):
    try:
        chat_id = message.chat.id
        
        # Check if we should respond in this group
        if not should_respond_in_group(chat_id, message):
            return

        # Get last few messages for context
        last_messages = []
        async for msg in bot.get_chat_history(chat_id, limit=5):
            if msg.text and not msg.text.startswith(('/', '!', '.')):
                last_messages.append(msg.text)
        
        # Analyze conversation topics
        topics = set()
        for msg in last_messages:
            topics.update(extract_topics(msg))
        
        emoji = random.choice(PERSONA["emoji_style"])
        
        # Check if we're continuing a previous topic
        user_data = chat_history_collection.find_one(
            {"user_id": message.from_user.id},
            {"history": 1}
        )
        
        response = None
        if user_data and random.random() > 0.6:  # 40% chance to follow up
            # Find recent topics from history
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
        
        # If no follow-up, choose random response
        if not response:
            if any(word in message.text.lower() for word in ["hi", "hello", "hey", "namaste"]):
                response = random.choice(PERSONA["responses"]["greetings"]).format(emoji)
            elif any(word in message.text.lower() for word in ["bye", "goodbye", "alvida"]):
                response = random.choice(PERSONA["responses"]["farewell"]).format(emoji)
            elif random.random() < PERSONA["response_probability"]:
                response = random.choice(PERSONA["responses"]["random"]).format(emoji)
            else:
                return

        # Add typing action with variable duration
        typing_duration = min(1.5, max(0.5, len(response) / 40))  # 0.5-1.5 seconds based on response length
        await bot.send_chat_action(chat_id, ChatAction.TYPING)
        await asyncio.sleep(typing_duration)
        
        # Sometimes reply, sometimes send new message
        if random.random() > 0.7:
            await message.reply_text(response)
        else:
            await bot.send_message(chat_id, response)

        # Update group activity
        update_group_activity(chat_id)

    except Exception as e:
        print(f"Group interaction error: {e}")

# ================= ENHANCED AI COMMAND HANDLER =================
@app.on_message(filters.command(["ai", "ask"], prefixes=["/", "!", "."]))
@rate_limit
async def enhanced_ai_chat(bot: app, message: Message):
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        
        if not message.text or len(message.text.split()) < 2:
            return await message.reply_text("💡 Please ask me something with /ai your_question")
            
        query = message.text.split(maxsplit=1)[1]
        user_id = message.from_user.id
        
        # Get user history with context from last 5 messages
        context_messages = []
        if message.chat.type != enums.ChatType.PRIVATE:
            async for msg in bot.get_chat_history(message.chat.id, limit=5):
                if msg.text and not msg.text.startswith(('/', '!', '.')):
                    context_messages.append(f"{msg.from_user.first_name}: {msg.text}")
        
        # Add context to query if available
        if context_messages:
            context = "\n".join(reversed(context_messages))
            enhanced_query = f"Context from group chat:\n{context}\n\nUser question: {query}"
        else:
            enhanced_query = query

        # Get/update history
        user_data = chat_history_collection.find_one({"user_id": user_id}) or {
            "user_id": user_id,
            "history": [],
            "first_seen": datetime.now(),
            "last_active": datetime.now(),
            "topics": []
        }

        # Add user message
        user_data["history"].append({
            "role": "user",
            "parts": [{"text": enhanced_query}],
            "time": datetime.now()
        })

        # Update topics
        user_data["topics"] = list(set(user_data.get("topics", []) + extract_topics(query))[-10:]  # Keep last 10 topics

        # Generate response
        chat = model.start_chat(history=clean_history_for_gemini(user_data["history"][-MAX_HISTORY:]))
        response = await asyncio.to_thread(chat.send_message, enhanced_query)
        
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
        
        # Format response with persona touch
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

# ================= IMPROVED MUSIC BOT INTEGRATION =================
@app.on_message(filters.command(["play", "song"]))
async def play_music_with_persona(bot: app, message: Message):
    try:
        # Your existing music bot code here
        # ...
        
        # Add personality touch (30% chance)
        if random.random() > 0.7:
            emoji = random.choice(PERSONA["emoji_style"])
            responses = [
                f"Song ready! Enjoy karo {emoji}",
                f"Gaana play ho raha hai {emoji}",
                f"Tumhare liye ye special song {emoji}",
                f"Mujhe ye song bahut pasand hai {emoji}"
            ]
            await message.reply_text(random.choice(responses))
            
    except Exception as e:
        await message.reply_text(f"⚠️ Music Error: {str(e)[:200]}")

# ================= IMPROVED BOT STATS COMMAND =================
@app.on_message(filters.command("botstats") & filters.user(ADMINS))
async def detailed_bot_stats(bot: app, message: Message):
    try:
        # User statistics
        total_users = chat_history_collection.count_documents({})
        active_users = chat_history_collection.count_documents({
            "last_active": {"$gt": datetime.now() - timedelta(days=1)}
        })
        
        # Group statistics
        total_groups = group_activity_collection.count_documents({})
        active_groups = group_activity_collection.count_documents({
            "last_active": {"$gt": datetime.now() - timedelta(days=1)}
        })
        
        # Request statistics
        total_requests = sum(len(v) for v in user_last_requests.values())
        
        # Most active hours
        hour_counts = {str(h): 0 for h in range(24)}
        for doc in chat_history_collection.find({}, {"last_active": 1}):
            hour = doc["last_active"].astimezone(TIMEZONE).hour
            hour_counts[str(hour)] += 1
        
        peak_hour = max(hour_counts.items(), key=lambda x: x[1])[0]
        
        await message.reply_text(
            f"🤖 <b>Enhanced Bot Statistics</b>\n"
            f"• 👥 Total Users: {total_users}\n"
            f"• 🎯 Active (24h): {active_users}\n"
            f"• 🏙️ Active Groups: {active_groups}/{total_groups}\n"
            f"• 📊 Today's Requests: {total_requests}\n"
            f"• 🕒 Peak Hour: {peak_hour}:00-{int(peak_hour)+1}:00\n\n"
            f"<i>Last updated: {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}</i>",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        await message.reply_text(f"⚠️ Stats Error: {str(e)}")

# ================= STARTUP =================
async def initialize_bot():
    # Create indexes
    chat_history_collection.create_index("last_active", expireAfterSeconds=30*24*60*60)
    group_activity_collection.create_index("last_active")
    group_activity_collection.create_index("next_available")
    
    # Initialize group activity records
    # (This would be more comprehensive in a real implementation)
    
    print("🎵 Music Bot + 🤖 AI Assistant Started Successfully!")
    print(f"Persona: {PERSONA['name']}")
    print(f"Active hours: {PERSONA['active_hours']}")

# Schedule the initialize function to run when bot starts
app.run(initialize_bot())
