import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv("d:/OKIE DOKIE PORTAL/od-assist/.env")
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

models_to_try = [
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
    "allam-2-7b"
]

for model in models_to_try:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=10
        )
        print(f"Success: {model}")
    except Exception as e:
        print(f"Failed: {model} - {e}")
