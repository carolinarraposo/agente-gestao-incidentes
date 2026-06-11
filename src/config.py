from dotenv import load_dotenv
import os

load_dotenv()

#GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
#MODEL_NAME = "gemini-2.5-flash"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = "llama-3.3-70b-versatile"