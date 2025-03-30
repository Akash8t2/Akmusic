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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyASzHWkz__U3vfRtt-VyToX5vvzzYg7Ipg")  # Use environment variables
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://akashkashyap8t2:Akking8t2@cluster0.t3sbtoi.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
MAX_HISTORY = 15  # Increased context memory
GROUP_MEMORY_MINUTES = 3  # Group chat memory duration
RATE_LIMIT = 2  # More strict rate limiting
RATE_LIMIT_PERIOD = 15  # Seconds
OWNER_ID = 5397621246
ADMINS = [OWNER_ID, 7819525628]  # Owner + Akash

# ================= ENHANCED PERSONA =================
PERSONA = {
    "name": "Priya",
    "moods": {
        "happy": ["🌸", "💖", "✨"],
        "sassy": ["😏", "🤭", "🥀"],
        "neutral": ["💫", "🎵", "🤗"]
    },
    "vocabulary": {
        "hindi": ["Arrey!", "Waah!", "Arey yaar"],
        "english": ["Oh my!", "Seriously?", "Hmm interesting"],
        "hybrid": ["Ajeeb!", "Mast hai na", "Kya baat hai"]
    },
    "response_templates": {
        "greeting": [
            "{vocab} {greet_emoji} Kaise ho?",
            "{vocab} {greet_emoji} Aaj kaise?",
            "{vocab} {greet_emoji} Sunao zara!"
        ],
        "farewell": [
            "Chalo theek hai {bye_emoji}",
            "Accha chalo {bye_emoji}",
            "Phir baat karna {bye_emoji}"
        ],
        "casual": [
            "{vocab} {mood_emoji} {comment}",
            "{vocab} {mood_emoji} Aap bhi na...",
            "{vocab} {mood_emoji} Yeh sab toh..."
        ]
    },
    "fallbacks": [
        "Hmm...thoda time do {mood_emoji}",
        "Abhi busy hun...baad mein? {mood_emoji}",
        "Kal baat karte hain {mood_emoji}"
    ]
}

# ================= INITIALIZE SERVICES =================
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["gemini_bot_db"]
chat_history_collection = db["chat_histories"]
group_memory_collection = db["group_memory"]
user_last_requests = defaultdict(list)

# Gemini initialization with fallback
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        generation_config={
            "max_output_tokens": 300,
            "temperature": 0.7  # More creative responses
        }
    )
    gemini_available = True
except Exception as e:
    print(f"⚠️ Gemini init error: {e}")
    gemini_available = False

# ================= MEMORY FUNCTIONS =================
async def get_conversation_context(chat_id, user_id=None):
    """Get recent conversation context"""
    # Group context (last 3 minutes)
    if user_id is None:
        cutoff = datetime.now() - timedelta(minutes=GROUP_MEMORY_MINUTES)
        return list(group_memory_collection.find({
            "chat_id": chat_id,
            "timestamp": {"$gt": cutoff}
        }).sort("timestamp", -1).limit(5))
    
    # User context
    user_data = chat_history_collection.find_one({"user_id": user_id}) or {}
    return user_data.get("history", [])[-5:]  # Last 5 messages

async def store_message(chat_id, user_id, text, is_group=False):
    """Store message in appropriate memory"""
    if is_group:
        group_memory_collection.insert_one({
            "chat_id": chat_id,
            "user_id": user_id,
            "text": text,
            "timestamp": datetime.now()
        })
    else:
        chat_history_collection.update_one(
            {"user_id": user_id},
            {"$push": {"history": {
                "role": "user",
                "parts": [{"text": text}],
                "time": datetime.now()
            }}},
            upsert=True
        )

# ================= PERSONA RESPONSE GENERATOR =================
def generate_persona_response(message_text, context=None):
    """Generate human-like response with personality"""
    # Mood selection
    current_mood = random.choice(["happy", "sassy", "neutral"])
    mood_emoji = random.choice(PERSONA["moods"][current_mood])
    
    # Language style selection
    lang_style = random.choice(["hindi", "english", "hybrid"])
    vocab = random.choice(PERSONA["vocabulary"][lang_style])
    
    # Context analysis
    is_greeting = any(word in message_text.lower() for word in ["hi", "hello", "namaste"])
    is_farewell = any(word in message_text.lower() for word in ["bye", "goodbye", "alvida"])
    
    # Response template selection
    if is_greeting:
        template = random.choice(PERSONA["response_templates"]["greeting"])
        return template.format(
            vocab=vocab,
            greet_emoji=mood_emoji
        )
    elif is_farewell:
        template = random.choice(PERSONA["response_templates"]["farewell"])
        return template.format(bye_emoji=mood_emoji)
    else:
        template = random.choice(PERSONA["response_templates"]["casual"])
        return template.format(
            vocab=vocab,
            mood_emoji=mood_emoji,
            comment=random.choice(["Maza aa raha hai", "Interesting", "Achha laga"])
        )

# ================= MESSAGE HANDLERS =================
@app.on_message(filters.group & filters.text & ~filters.command())
async def handle_group_chat(bot: app, message: Message):
    """Enhanced group chat handler"""
    try:
        # Store message
        await store_message(
            message.chat.id,
            message.from_user.id,
            message.text,
            is_group=True
        )
        
        # Check last interaction
        last_interaction = chat_history_collection.find_one(
            {"user_id": message.from_user.id},
            {"last_active": 1}
        )
        last_time = last_interaction.get("last_active", datetime.min) if last_interaction else datetime.min
        
        # 30% response chance with 2-minute cooldown
        if (datetime.now() - last_time < timedelta(minutes=2)) or (random.random() > 0.3):
            return
            
        # Generate response
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        await asyncio.sleep(random.uniform(0.8, 1.8))  # Human-like delay
        
        context = await get_conversation_context(message.chat.id)
        response = generate_persona_response(message.text, context)
        
        # 70% reply, 30% new message
        if random.random() > 0.3:
            await message.reply_text(response)
        else:
            await bot.send_message(message.chat.id, response)
            
        # Update interaction time
        chat_history_collection.update_one(
            {"user_id": message.from_user.id},
            {"$set": {"last_active": datetime.now()}},
            upsert=True
        )
        
    except Exception as e:
        print(f"Group chat error: {e}")

# ================= AI COMMAND HANDLER =================
@app.on_message(filters.command(["ai", "ask"]))
async def handle_ai_query(bot: app, message: Message):
    try:
        if not gemini_available:
            fallback = random.choice(PERSONA["fallbacks"]).format("✨")
            return await message.reply_text(fallback)
            
        query = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
        if not query:
            return await message.reply_text("Kuch to pucho ji? 🥀")
            
        # Get context
        context = await get_conversation_context(message.chat.id, message.from_user.id)
        
        # Generate response
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        chat = model.start_chat(history=clean_history_for_gemini(context))
        response = chat.send_message(query)
        
        # Store interaction
        await store_message(message.chat.id, message.from_user.id, query)
        chat_history_collection.update_one(
            {"user_id": message.from_user.id},
            {"$push": {"history": {
                "role": "model",
                "parts": [{"text": response.text}],
                "time": datetime.now()
            }}},
            upsert=True
        )
        
        await message.reply_text(response.text[:1000])
        
    except Exception as e:
        error_msg = random.choice(PERSONA["fallbacks"]).format("💖")
        if "429" in str(e):  # Rate limit error
            error_msg = "Thoda rest kar leti hun...baad mein puchna 🌸"
        await message.reply_text(error_msg)

# ================= STARTUP =================
# Create TTL indexes
chat_history_collection.create_index("last_active", expireAfterSeconds=30*24*60*60)  # 30 days
group_memory_collection.create_index("timestamp", expireAfterSeconds=GROUP_MEMORY_MINUTES*60)

print("""
🎵🤖 Hybrid Bot Started!
• Group Memory: {} minutes
• Persona: {}
• Gemini: {}
""".format(GROUP_MEMORY_MINUTES, PERSONA["name"], "Enabled" if gemini_available else "Disabled"))
