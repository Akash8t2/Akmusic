import google.generativeai as genai
from BrandrdXMusic import app
from pyrogram.enums import ChatAction, ParseMode
from pyrogram import filters

# Google Gemini API Key
GEMINI_API_KEY = "AIzaSyASzHWkz__U3vfRtt-VyToX5vvzzYg7Ipg"

# API Key Set karein
genai.configure(api_key=GEMINI_API_KEY)

@app.on_message(filters.command(["gemini", "ai", "ask"], prefixes=[".", "/", "!"]))
async def chat_gemini(bot, message):
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

        if len(message.command) < 2:
            await message.reply_text("❌ **Please provide a question!**")
            return

        query = message.text.split(' ', 1)[1]

        # Gemini API se response lena
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(query)

        # Response send karein
        if response and hasattr(response, "text"):
            result_text = response.text
        else:
            result_text = "⚠️ API ne koi valid response nahi diya."

        await message.reply_text(result_text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await message.reply_text(f"❌ **Error:** `{e}`")
