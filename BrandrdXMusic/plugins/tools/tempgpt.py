import os
from pyrogram import filters, enums
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.types import Message
from BrandrdXMusic import app
import google.generativeai as genai
from pymongo import MongoClient
from datetime import datetime

# ================= Configuration =================
GEMINI_API_KEY = "AIzaSyASzHWkz__U3vfRtt-VyToX5vvzzYg7Ipg"  # Your Gemini API Key
MONGO_URI = "mongodb+srv://akashkashyap8t2:Akking8t2@cluster0.t3sbtoi.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
MAX_HISTORY = 10  # 10 messages per user

# ================= Initialize Services =================
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["gemini_bot_db"]
chat_history_collection = db["chat_histories"]

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

# ================= Bot Commands =================
@app.on_message(filters.command(["ai", "ask", "gemini"], prefixes=["/", "!", "."]))
async def ai_chat(bot: app, message: Message):
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        user_id = message.from_user.id
        
        if not message.text or len(message.text.split()) < 2:
            return await message.reply_text("💡 Please ask me something after the command!")

        query = message.text.split(maxsplit=1)[1]
        
        # Get/Initialize user history
        user_data = chat_history_collection.find_one({"user_id": user_id}) or {"user_id": user_id, "history": []}
        
        # Add user message
        user_data["history"].append({
            "role": "user",
            "parts": [query],
            "time": datetime.now()
        })

        # Generate response (last 10 messages as context)
        response = model.generate_content({"contents": user_data["history"][-MAX_HISTORY:]})
        
        if not response.text:
            return await message.reply_text("🔴 Gemini didn't return a valid response")

        # Add bot response
        user_data["history"].append({
            "role": "model",
            "parts": [response.text],
            "time": datetime.now()
        })

        # Update database (keep only last 10)
        chat_history_collection.update_one(
            {"user_id": user_id},
            {"$set": {"history": user_data["history"][-MAX_HISTORY:]}},
            upsert=True
        )

        await message.reply_text(response.text[:4000], parse_mode=ParseMode.MARKDOWN)

    except genai.types.BlockedPromptError:
        await message.reply_text("🚫 This query violates safety guidelines")
    except Exception as e:
        await message.reply_text(f"⚠️ Error: {str(e)}")

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
        history_text += f"{prefix}{msg['parts'][0][:50]}...\n"
    
    await message.reply_text(history_text)

# ================= Auto-Cleanup Setup =================
# Run this once to enable auto-deletion after 30 days
chat_history_collection.create_index(
    "time", 
    expireAfterSeconds=30*24*60*60  # 30 days TTL
    )
