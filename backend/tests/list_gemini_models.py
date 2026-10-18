
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY is missing from backend/.env")

client = genai.Client(api_key=api_key)

print("Models supporting generateContent:\n")

for model in client.models.list():
    if "generateContent" in (model.supported_actions or []):
        print(model.name)
