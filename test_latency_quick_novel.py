import requests
import time

url = "http://127.0.0.1:7860/chat/query"

queries = [
    "What is the exact process of applying for a student leave in the portal?",
    "Explain the detailed steps for configuring the library management books.",
    "How does the software handle late fee calculations and penalties?"
]

print("Starting tests...\n")
for q in queries:
    start = time.time()
    try:
        res = requests.post(url, json={"query": q}, timeout=60)
        elapsed = time.time() - start
        if res.status_code == 200:
            print(f"Q: {q}")
            print(f"Time: {elapsed:.2f}s")
        else:
            print(f"Q: {q}\nError: {res.status_code} - {res.text}\n")
    except Exception as e:
        print(f"Q: {q}\nException: {e}\n")
