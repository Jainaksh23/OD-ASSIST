import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv("d:/OKIE DOKIE PORTAL/od-assist/.env")

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

try:
    models = client.models.list()
    for m in models.data:
        print(m.id)
except Exception as e:
    print(e)
