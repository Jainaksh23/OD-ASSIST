import os
import time
import requests
import urllib.request
import csv
from dotenv import load_dotenv

load_dotenv()

ADMIN_USER = "odadmin"
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "OkieDokie@123")
API_URL = "http://127.0.0.1:7860"

def run_bulk_ingest():
    print("Logging in to OD Assist...")
    login_res = requests.post(f"{API_URL}/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    if not login_res.ok:
        print("Login failed:", login_res.text)
        return
    
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Login successful. Fetching Google Sheet CSV...")
    
    csv_url = "https://docs.google.com/spreadsheets/d/15qtuLue8dyDwMXN_F9B5-vQ_Pz_RUDkTLVMLKjkh9ys/export?format=csv&gid=0"
    response = urllib.request.urlopen(csv_url)
    lines = [l.decode('utf-8') for l in response.readlines()]
    reader = csv.DictReader(lines)
    
    for row in reader:
        title = row.get("Meeting", "").strip()
        video_link = row.get("Link", "").strip()
        notes_link = row.get("Gemini Notes", "").strip()
        
        if not title:
            continue
            
        print(f"Queueing: {title}")
        
        if video_link:
            res = requests.post(
                f"{API_URL}/admin/ingest",
                headers=headers,
                json={"title": f"{title} (Video)", "source_type": "drive_video", "source_url": video_link}
            )
            print(f"  Video ingest status: {res.status_code}")
            
        if notes_link:
            res = requests.post(
                f"{API_URL}/admin/ingest",
                headers=headers,
                json={"title": f"{title} (Notes)", "source_type": "drive_doc", "source_url": notes_link}
            )
            print(f"  Notes ingest status: {res.status_code}")
            
        time.sleep(0.5)

    print("Finished queueing all sources!")

if __name__ == "__main__":
    run_bulk_ingest()
