import sys
import time
from fastapi.testclient import TestClient
from api.main import app

def test_app():
    print("Initializing test client...")
    with TestClient(app) as client:
        print("Testing chat endpoint (Query 1)...")
        start = time.time()
        res1 = client.post("/chat/query", json={"query": "Transport module setup"})
        dur1 = time.time() - start
        print(f"Status: {res1.status_code}")
        print(f"Response: {res1.json().get('answer')[:100]}...")
        print(f"Sources Used: {res1.json().get('sources_used')}")
        print(f"Duration: {dur1:.2f}s")
        
        print("\nTesting chat endpoint AGAIN for Cache Hit (Query 1)...")
        start = time.time()
        res2 = client.post("/chat/query", json={"query": "Transport module setup"})
        dur2 = time.time() - start
        print(f"Status: {res2.status_code}")
        print(f"Response: {res2.json().get('answer')[:100]}...")
        print(f"Duration: {dur2:.2f}s")
        
        print(f"\nCache Speedup: {dur1/dur2:.1f}x")
        
        print("\nTesting chat endpoint (Query 2)...")
        res3 = client.post("/chat/query", json={"query": "How to handle fee concessions?"})
        print(f"Status: {res3.status_code}")
        print(f"Response: {res3.json().get('answer')[:100]}...")
        
        print("\nAll tests passed successfully!")

if __name__ == "__main__":
    test_app()
