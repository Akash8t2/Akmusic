import os
import time
from pyrogram import filters, enums
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from BrandrdXMusic import app
import google.generativeai as genai
from pymongo import MongoClient
from datetime import datetime
from collections import defaultdict

# ================= Configuration =================
GEMINI_API_KEY = "AIzaSyASzHWkz__U3vfRtt-VyToX5vvzzYg7Ipg"
MONGO_URI = "mongodb+srv://akashkashyap8t2:Akking8t2@cluster0.t3sbtoi.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
MAX_HISTORY = 10
RATE_LIMIT = 3  # Messages per 10 seconds
RATE_LIMIT_PERIOD = 10  # Seconds

# ================= Initialize Services =================
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["gemini_bot_db"]
chat_history_collection = db["chat_histories"]
user_last_requests = defaultdict(list)  # For rate limiting

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

# ================= Rate Limiting Decorator =================
def rate_limit(func):
    async def wrapper(client, message):
        user_id = message.from_user.id
        current_time = time.time()
        
        # Remove old requests
        user_last_requests[user_id] = [
            t for t in user_last_requests[user_id] 
            if current_time - t < RATE_LIMIT_PERIOD
        ]
        
        if len(user_last_requests[user_id]) >= RATE_LIMIT:
            wait_time = int(RATE_LIMIT_PERIOD - (current_time - user_last_requests[user_id][0]))
            await message.reply_text(
                f"⏳ Please wait {wait_time} seconds before making another request. "
                f"(Limit: {RATE_LIMIT} requests per {RATE_LIMIT_PERIOD} seconds)",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        user_last_requests[user_id].append(current_time)
        return await func(client, message)
    return wrapper

# ================= Clean History for Gemini =================
def clean_history_for_gemini(mongo_history):
    """Remove custom fields (like 'time') before sending to Gemini"""
    return [{
        "role": msg["role"],
        "parts": msg["parts"]
    } for msg in mongo_history]

# ================= Bot Commands =================
@app.on_message(filters.command(["ai", "ask", "gemini"], prefixes=["/", "!", "."]))
@rate_limit
async def ai_chat(bot: app, message: Message):
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        user_id = message.from_user.id
        
        if not message.text or len(message.text.split()) < 2:
            return await message.reply_text("💡 Please ask me something after the command!")

        query = message.text.split(maxsplit=1)[1]
        
        # Get/Initialize user history
        user_data = chat_history_collection.find_one({"user_id": user_id}) or {
            "user_id": user_id,
            "history": [],
            "updated_at": datetime.now()
        }
        
        # Add user message (with timestamp stored separately)
        user_data["history"].append({
            "role": "user",
            "parts": [{"text": query}],
            # Note: 'time' is stored in MongoDB but removed before sending to Gemini
            "timestamp": datetime.now().isoformat()  
        })

        try:
            # Generate response with cleaned history
            chat = model.start_chat(history=clean_history_for_gemini(user_data["history"][-MAX_HISTORY:]))
            response = chat.send_message(query)
            
            if not response.text:
                return await message.reply_text("🔴 Gemini didn't return a valid response")

            # Add bot response
            user_data["history"].append({
                "role": "model",
                "parts": [{"text": response.text}],
                "timestamp": datetime.now().isoformat()
            })
            user_data["updated_at"] = datetime.now()

            # Update database
            chat_history_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "history": user_data["history"][-MAX_HISTORY:],
                    "updated_at": user_data["updated_at"]
                }},
                upsert=True
            )

            await message.reply_text(response.text[:4000], parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            if "blocked" in str(e).lower():
                await message.reply_text("🚫 This query violates safety guidelines")
            else:
                await message.reply_text(f"⚠️ Gemini Error: {str(e)}")

    except FloodWait as e:
        await message.reply_text(f"⏳ Please wait {e.value} seconds (flood control)")
    except Exception as e:
        await message.reply_text(f"⚠️ Bot Error: {str(e)}")

# ================= Other Commands =================
@app.on_message(filters.command(["clearchat", "resetai"]))
async def clear_history(bot: app, message: Message):
    user_id = message.from_user.id
    chat_history_collection.delete_one({"user_id": user_id})
    await message.reply_text("🧹 Chat history cleared!")

@app.on_message(filters.command("history"))
async def show_history(bot: app, message: Message):
    user_id = message.from_user.id
    user_data = chat_history_collection.find_one({"user_id": user_id})
    
    if not user_data or not user_data.get("history"):
        return await message.reply_text("📭 No chat history found")
    
    history_text = "📜 Your Last 10 Chats:\n\n"
    for msg in user_data["history"][-MAX_HISTORY:]:
        prefix = "👤 You: " if msg["role"] == "user" else "🤖 Bot: "
        history_text += f"{prefix}{msg['parts'][0]['text'][:50]}...\n"
    
    await message.reply_text(history_text)

# ================= TTL Index for Auto-Cleanup =================
chat_history_collection.create_index(
    "updated_at", 
    expireAfterSeconds=30*24*60*60  # Auto-delete after 30 days
            )
