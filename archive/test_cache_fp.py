import requests
import time

url = "http://127.0.0.1:7860/chat/query"

queries = [
    "Fee collection kaise hota hai?",
    "Fee refund kaise hota hai?"
]

for q in queries:
    start = time.time()
    res = requests.post(url, json={"query": q}, timeout=60)
    elapsed = time.time() - start
    if res.status_code == 200:
        data = res.json()
        print(f"Q: {q}")
        print(f"Time: {elapsed:.2f}s | Cached: {data.get('cached')}")
        print(f"A: {data.get('answer')[:100]}...\n")
    else:
        print(f"Error: {res.status_code}")
