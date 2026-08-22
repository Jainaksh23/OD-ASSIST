import os
from dotenv import load_dotenv

# Load env variables from .env
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

print("--- ENV VARIABLE CHECK ---")
print(f"Raw API Key string representation: {repr(api_key)}")
if api_key:
    print(f"Length of API Key: {len(api_key)}")
else:
    print("API Key is None!")

print("\n--- GROQ API TEST ---")
if api_key == "PASTE_YOUR_GROQ_KEY_HERE" or not api_key:
    print("ERROR: API key is clearly a placeholder or missing. Aborting test.")
else:
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        
        # Test Chat Completion
        print("Testing Chat Completion...")
        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print("Chat Completion SUCCESS:", completion.choices[0].message.content)
        
        # Audio Transcription requires an audio file, skipping to avoid complexity unless chat also fails.
        print("Groq API Key is valid and working!")
    except Exception as e:
        print(f"Groq API Call FAILED: {e}")
