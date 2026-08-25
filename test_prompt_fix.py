import requests, time

url = "http://127.0.0.1:7860/chat/query"
queries = [
    "How is payroll processed?",
    "Student admission process",  
    "How to configure GPS?",
    "Transport module setup",
    "Fee collection kaise hota hai?",
]

for q in queries:
    start = time.time()
    r = requests.post(url, json={"query": q}, timeout=60)
    elapsed = time.time() - start
    d = r.json()
    cached = d.get("cached")
    sources = [s["id"] for s in d.get("sources", [])]
    answer = d.get("answer", "")[:200]
    
    is_idk = "don't have enough" in answer.lower() or "kaafi jaankari nahi" in answer.lower() or "kaafi information nahi" in answer.lower()
    status = "IDK" if is_idk else "ANSWERED"
    
    print(f"[{status}] Q: {q}")
    print(f"  Time: {elapsed:.1f}s | Cached: {cached} | Sources: {sources}")
    print(f"  A: {answer}")
    print()
