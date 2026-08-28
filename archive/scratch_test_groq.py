import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv("d:/OKIE DOKIE PORTAL/od-assist/.env")

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

try:
    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Transport module setup"}
        ],
        temperature=0.0,
        max_tokens=2048,
        reasoning_effort="low",
        reasoning_format="hidden"
    )
    print("Success:", response)
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"\nExact Error message: {e}")
