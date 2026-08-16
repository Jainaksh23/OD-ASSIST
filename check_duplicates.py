import collections
import sys
from dotenv import load_dotenv
load_dotenv()

from db.db import SessionLocal
from db.models import Source, Chunk

def main():
    db = SessionLocal()
    sources = db.query(Source).all()
    
    url_counts = collections.defaultdict(list)
    for s in sources:
        if s.source_url:
            url_counts[s.source_url].append(s)
            
    duplicates = {url: lst for url, lst in url_counts.items() if len(lst) > 1}
    print(f"Total Unique URLs with duplicates: {len(duplicates)}")
    
    total_deleted = 0
    
    for url, lst in duplicates.items():
        print(f"\nURL: {url}")
        # Sort so we keep the newest one or the one that is pending/processing
        # Priority: completed > processing > pending > failed
        def status_weight(s):
            if s.status == "completed": return 4
            if s.status == "processing": return 3
            if s.status == "pending": return 2
            return 1 # failed
            
        lst.sort(key=lambda s: (status_weight(s), s.id), reverse=True)
        
        keep = lst[0]
        remove = lst[1:]
        
        print(f" -> KEEPING : ID {keep.id} | Status: {keep.status} | Title: {keep.title}")
        for r in remove:
            print(f" -> DELETING: ID {r.id} | Status: {r.status} | Title: {r.title}")
            db.query(Chunk).filter(Chunk.source_id == r.id).delete()
            db.delete(r)
            total_deleted += 1
            
    if total_deleted > 0:
        db.commit()
        print(f"\nSuccessfully deleted {total_deleted} duplicate sources from DB.")
    else:
        print("\nNo duplicates found to delete.")

if __name__ == "__main__":
    main()
