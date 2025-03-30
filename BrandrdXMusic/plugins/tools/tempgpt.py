import google.generativeai as genai
import time
from BrandrdXMusic import app
from pyrogram.enums import ChatAction, ParseMode
from pyrogram import filters

# ✅ Google Gemini API Key
GEMINI_API_KEY = "AIzaSyASzHWkz__U3vfRtt-VyToX5vvzzYg7Ipg"

# ✅ API Key Configure Karein
genai.configure(api_key=GEMINI_API_KEY)

# ✅ Sahi Model Select Karein
model = genai.GenerativeModel("gemini-2.0-flash")  # Ya "gemini-2.5-pro-exp-03-25"

@app.on_message(filters.command(["chatgpt", "ai", "ask", "", "iri"], prefixes=[".", "J", "j", "s", "", "/"]))
async def chat_gpt(bot, message):
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

        # User ka naam check karein
        name = message.from_user.first_name if message.from_user else "User"

        if len(message.command) < 2:
            await message.reply_text(f"**Hello {name}, How can I help you today?**")
        else:
            query = message.text.split(' ', 1)[1]
            response = model.generate_content(query).text
            await message.reply_text(f"{response}", parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await message.reply_text(f"**❌ Error:** {e}")
