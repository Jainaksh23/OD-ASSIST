import sys
import time
from fastapi.testclient import TestClient
from api.main import app

def test_faqs():
    print("Initializing test client...")
    
    # In api/main.py, the endpoint is:
    # @app.post("/admin/faqs/generate-from-sources", tags=["admin"])
    # async def generate_faqs_from_sources(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    
    # I will override the require_admin dependency to bypass auth
    from api.auth import require_admin
    app.dependency_overrides[require_admin] = lambda: {"id": 1, "username": "testadmin", "role": "admin"}
    
    with TestClient(app) as client:
        print("Triggering FAQ generation...")
        start = time.time()
        # This endpoint streams SSE
        with client.stream("POST", "/admin/faqs/generate-from-sources") as response:
            print(f"Status: {response.status_code}")
            for line in response.iter_lines():
                if line:
                    print(line)
        dur = time.time() - start
        print(f"\nTotal Duration: {dur:.2f}s")
        
    app.dependency_overrides.clear()
    print("Test finished.")

if __name__ == "__main__":
    test_faqs()
