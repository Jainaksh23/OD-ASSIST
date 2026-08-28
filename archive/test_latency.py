import time
import requests

url = "http://localhost:7860/chat/query"

queries = [
    "What is the employee onboarding process?",
    "How to manage fleet maintenance?",
    "Can you explain fee concession logic?",
    "Transport module setup" # Likely a cache hit
]

print("Starting latency tests...")
for q in queries:
    print(f"\nSending query: {q}")
    start = time.time()
    try:
        res = requests.post(url, json={"query": q}, timeout=60)
        dur = time.time() - start
        print(f"Status: {res.status_code}")
        print(f"Duration: {dur:.2f}s")
    except Exception as e:
        print(f"Error: {e}")
