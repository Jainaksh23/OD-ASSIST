import requests
import time

url = "http://127.0.0.1:7860/chat/query"

queries = [
    "Transport module setup",
    "Fee collection",
    "Transport module kaise use karein?"
]

print("Starting tests...\n")
for q in queries:
    start = time.time()
    try:
        res = requests.post(url, json={"query": q}, timeout=60)
        elapsed = time.time() - start
        if res.status_code == 200:
            data = res.json()
            answer = data.get("answer", "")
            cached = data.get("cached", False)
            print(f"Q: {q}")
            print(f"Time: {elapsed:.2f}s | Cached: {cached}")
            print(f"A: {answer[:150]}...\n")
        else:
            print(f"Q: {q}\nError: {res.status_code} - {res.text}\n")
    except Exception as e:
        print(f"Q: {q}\nException: {e}\n")
