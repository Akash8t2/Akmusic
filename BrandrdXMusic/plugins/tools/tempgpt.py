import os
import google.generativeai as genai
from dotenv import load_dotenv

# ✅ Environment Variable Load Karein (Agar .env File Use Kar Rahe Hain)
load_dotenv()

# ✅ API Key Set Karein
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("❌ API key missing! Please set GEMINI_API_KEY in .env or environment variables.")

genai.configure(api_key=AIzaSyASzHWkz__U3vfRtt-VyToX5vvzzYg7Ipg)

# ✅ Correct Model Select Karein
model = genai.GenerativeModel("gemini-2.0-flash")  # Ya "gemini-2.5-pro-exp-03-25"

def ask_gemini(prompt):
    """Gemini AI se response lene ka function"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ✅ Test Query
if __name__ == "__main__":
    user_input = input("Enter your question: ")
    print("\n🤖 Gemini's Response:\n")
    print(ask_gemini(user_input))
