import collections
import sys
from dotenv import load_dotenv
load_dotenv()

from db.db import SessionLocal
from db.models import Source

def main():
    db = SessionLocal()
    sources = db.query(Source).all()
    
    url_counts = collections.defaultdict(list)
    for s in sources:
        if s.source_url:
            url_counts[s.source_url].append(s)
            
    duplicates = {url: lst for url, lst in url_counts.items() if len(lst) > 1}
    print(f"Total Unique URLs with duplicates: {len(duplicates)}")
    
    for url, lst in duplicates.items():
        print(f"\nURL: {url}")
        for s in lst:
            print(f" - ID: {s.id} | Status: {s.status} | Title: {s.title}")
            
    db.close()

if __name__ == "__main__":
    main()
