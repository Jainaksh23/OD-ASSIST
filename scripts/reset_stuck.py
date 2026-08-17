"""Reset stuck processing sources and clear stale error messages from pending ones."""
import sys, os
sys.path.insert(0, r"d:\OKIE DOKIE PORTAL\od-assist")
from dotenv import load_dotenv
load_dotenv(os.path.join(r"d:\OKIE DOKIE PORTAL\od-assist", ".env"))

from datetime import datetime, timedelta, timezone
from db.db import SessionLocal
from db.models import Source, Chunk

db = SessionLocal()

# 1. Reset stuck "processing" sources (> 1 hour old) to "pending"
stuck_threshold = datetime.now(timezone.utc) - timedelta(hours=1)
stuck = db.query(Source).filter(
    Source.status == "processing",
    Source.created_at < stuck_threshold
).all()

print(f"Found {len(stuck)} stuck processing sources:")
for s in stuck:
    # Clear any old chunks to prevent duplicates on retry
    old_chunks = db.query(Chunk).filter(Chunk.source_id == s.id).delete()
    s.status = "pending"
    s.error_message = None
    s.chunk_count = 0
    print(f"  ID:{s.id} | {s.title} | cleared {old_chunks} old chunks -> pending")

# 2. Clear stale error messages from pending sources (leftover from previous attempts)
pending_with_errors = db.query(Source).filter(
    Source.status == "pending",
    Source.error_message != None
).all()

print(f"\nFound {len(pending_with_errors)} pending sources with stale error messages:")
for s in pending_with_errors:
    # Clear old chunks too
    old_chunks = db.query(Chunk).filter(Chunk.source_id == s.id).delete()
    s.error_message = None
    s.chunk_count = 0
    print(f"  ID:{s.id} | {s.title} | cleared error msg + {old_chunks} old chunks")

db.commit()

# 3. Show final state
all_sources = db.query(Source).order_by(Source.created_at.desc()).all()
counts = {}
for s in all_sources:
    counts[s.status] = counts.get(s.status, 0) + 1

print(f"\nFinal status summary:")
for k, v in sorted(counts.items()):
    print(f"  {k}: {v}")

db.close()
print("\nDone!")
