"""
fix_stuck_and_process.py -- One-time fix for stuck "processing" sources.

Steps:
  1. Find ALL sources with status="processing" and reset them to "pending"
  2. Process the 5 specific stuck/failed sources one-by-one with live progress
  3. Report final status for each
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

from db.db import SessionLocal
from db.models import Source, Chunk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# The 3 specific source IDs that are genuinely stuck
TARGET_IDS = [35]
# 103 = Admission Token Money (failed - timeout)
# 104 = Admission Advance (stuck processing)
#  96 = Fee Module Handover Video (stuck processing)
#  94 = ERP Transport Video (stuck processing)
#  35 = GPS Config Video (failed - connection aborted)


def step1_reset_all_stuck():
    """Find ALL 'processing' sources and reset to 'pending'."""
    print("\n" + "=" * 70)
    print("STEP 1: Resetting ALL stuck 'processing' sources to 'pending'")
    print("=" * 70)
    
    db = SessionLocal()
    try:
        stuck = db.query(Source).filter(Source.status == "processing").all()
        
        if not stuck:
            print("  [OK] No stuck 'processing' sources found.")
            return
        
        print(f"\n  Found {len(stuck)} stuck 'processing' source(s):\n")
        for s in stuck:
            print(f"  ID:{s.id:3d} | {s.source_type:12s} | {s.title}")
            # Clear any partial chunks
            chunk_count = db.query(Chunk).filter(Chunk.source_id == s.id).count()
            if chunk_count > 0:
                db.query(Chunk).filter(Chunk.source_id == s.id).delete()
                print(f"          -> Cleared {chunk_count} partial chunks")
            
            s.status = "pending"
            s.error_message = None
            s.chunk_count = 0
        
        db.commit()
        print(f"\n  [OK] Reset {len(stuck)} sources: 'processing' -> 'pending'")
    finally:
        db.close()


def step2_reset_targets_for_retry():
    """Reset the 5 target sources (both stuck and failed) to 'pending'."""
    print("\n" + "=" * 70)
    print("STEP 2: Resetting 5 target sources for processing")
    print("=" * 70)
    
    db = SessionLocal()
    try:
        for sid in TARGET_IDS:
            source = db.get(Source, sid)
            if not source:
                print(f"  [SKIP] ID:{sid} not found in DB")
                continue
            
            # Clear old chunks
            old_chunks = db.query(Chunk).filter(Chunk.source_id == sid).count()
            if old_chunks > 0:
                db.query(Chunk).filter(Chunk.source_id == sid).delete()
            
            old_status = source.status
            source.status = "pending"
            source.error_message = None
            source.chunk_count = 0
            
            print(f"  ID:{sid:3d} | '{old_status}' -> 'pending' | {source.title}")
        
        db.commit()
        print(f"\n  [OK] All targets reset to 'pending'")
    finally:
        db.close()


def step3_process_targets():
    """Process the 5 target sources one-by-one with live progress."""
    print("\n" + "=" * 70)
    print("STEP 3: Loading models (one-time)...")
    print("=" * 70)
    
    from sentence_transformers import SentenceTransformer
    from groq import Groq
    
    print("  Loading SentenceTransformer (BAAI/bge-small-en-v1.5)...")
    embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")
    print("  [OK] Embedder loaded")
    
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    print("  [OK] Groq client initialized")
    
    print("\n" + "=" * 70)
    print("STEP 4: Processing 5 sources ONE-BY-ONE")
    print("=" * 70)
    
    from ingestion.orchestrator import process_source
    
    results = {}
    
    for idx, sid in enumerate(TARGET_IDS, 1):
        db = SessionLocal()
        source = db.get(Source, sid)
        if not source:
            print(f"\n[{idx}/5] SKIPPED - Source ID:{sid} not found")
            results[sid] = {"title": f"ID:{sid}", "status": "not_found", "error": "Not in DB"}
            db.close()
            continue
        
        title = source.title
        stype = source.source_type
        url = source.source_url[:80] if source.source_url else "?"
        db.close()
        
        print(f"\n{'=' * 60}")
        print(f"[{idx}/5] {title}")
        print(f"  ID: {sid} | Type: {stype}")
        print(f"  URL: {url}...")
        print(f"{'=' * 60}")
        
        start_time = time.time()
        
        try:
            print(f"  -> Starting ingestion pipeline...")
            process_source(sid, embedder, groq_client)
            
            # Check result
            db2 = SessionLocal()
            updated = db2.get(Source, sid)
            elapsed = time.time() - start_time
            
            if updated.status == "completed":
                print(f"  [COMPLETED] {updated.chunk_count} chunks ingested in {elapsed:.1f}s")
                results[sid] = {
                    "title": title,
                    "status": "completed",
                    "chunks": updated.chunk_count,
                    "time": f"{elapsed:.1f}s"
                }
            elif updated.status == "failed":
                err = updated.error_message or "unknown"
                print(f"  [FAILED] {err} (in {elapsed:.1f}s)")
                results[sid] = {
                    "title": title,
                    "status": "failed",
                    "error": err,
                    "time": f"{elapsed:.1f}s"
                }
            else:
                print(f"  [WARNING] Status still '{updated.status}' after {elapsed:.1f}s - marking failed")
                updated.status = "failed"
                updated.error_message = f"Silent failure - status was '{updated.status}' after processing"
                db2.commit()
                results[sid] = {
                    "title": title,
                    "status": "failed",
                    "error": updated.error_message,
                    "time": f"{elapsed:.1f}s"
                }
            
            db2.close()
            
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)[:500]
            print(f"  [EXCEPTION] {error_msg} (in {elapsed:.1f}s)")
            
            # Force-update DB status to "failed"
            try:
                db3 = SessionLocal()
                s = db3.get(Source, sid)
                if s and s.status != "failed":
                    s.status = "failed"
                    s.error_message = f"Script crash: {error_msg}"
                    db3.commit()
                db3.close()
            except Exception:
                pass
            
            results[sid] = {
                "title": title,
                "status": "failed",
                "error": error_msg,
                "time": f"{elapsed:.1f}s"
            }
    
    return results


def print_final_report(results):
    """Print final status report."""
    print("\n" + "=" * 70)
    print("FINAL REPORT - 5 Target Sources")
    print("=" * 70)
    
    completed = 0
    failed = 0
    
    for sid, r in results.items():
        if r["status"] == "completed":
            completed += 1
            print(f"  [OK]   ID:{sid:3d} | {r['title']}")
            print(f"         {r.get('chunks', 0)} chunks | {r.get('time', '?')}")
        else:
            failed += 1
            print(f"  [FAIL] ID:{sid:3d} | {r['title']}")
            print(f"         Error: {r.get('error', 'unknown')[:100]}")
            print(f"         Time: {r.get('time', '?')}")
    
    print(f"\n  Completed: {completed}/5 | Failed: {failed}/5")
    print("=" * 70)


if __name__ == "__main__":
    print("\n=== OD Assist -- Fix Stuck Sources & Process Targets ===")
    print(f"    Time: {datetime.now()}")
    print("=" * 70)
    
    # Step 1: Reset all stuck processing sources
    step1_reset_all_stuck()
    
    # Step 2: Reset targets specifically (including failed ones)
    step2_reset_targets_for_retry()
    
    # Step 3+4: Process targets one by one
    results = step3_process_targets()
    
    # Final report
    print_final_report(results)
    
    print("\nDone!")
