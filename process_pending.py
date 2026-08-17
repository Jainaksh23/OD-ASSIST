"""
process_pending.py — Robust processor for pending & stuck sources.

Features:
  - Auto-detects stuck "processing" sources (> 1 hour old) and resets them
  - Processes all "pending" sources with max 2 concurrent workers (rate-limit safe)
  - Each source wrapped in try/except — one failure doesn't kill the script
  - Clears old chunks before retry to prevent duplicates
  - Reports detailed summary at the end

Usage:
  python process_pending.py
"""

import os
import sys
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

from sentence_transformers import SentenceTransformer
from groq import Groq
from db.db import SessionLocal
from db.models import Source, Chunk
from ingestion.orchestrator import process_source

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
MAX_WORKERS = 2           # max concurrent source processing (rate-limit safe)
STUCK_THRESHOLD_HOURS = 1  # sources in "processing" longer than this → reset


def reset_stuck_sources(db):
    """
    Find sources stuck in 'processing' status for too long and reset to 'pending'.
    Returns list of reset source IDs.
    """
    threshold = datetime.now(timezone.utc) - timedelta(hours=STUCK_THRESHOLD_HOURS)
    stuck = db.query(Source).filter(
        Source.status == "processing",
        Source.created_at < threshold,
    ).all()

    reset_ids = []
    for s in stuck:
        db.query(Chunk).filter(Chunk.source_id == s.id).delete()
        s.status = "pending"
        s.error_message = None
        s.chunk_count = 0
        reset_ids.append(s.id)
        logger.info("Reset stuck source ID:%d (%s) -> pending", s.id, s.title)

    if reset_ids:
        db.commit()
        logger.info("Reset %d stuck sources", len(reset_ids))
    return reset_ids


def process_single_source(source_id, source_title, embedder, groq_client):
    """Process one source with full error isolation."""
    try:
        # Clear any old chunks before processing to prevent duplicates
        db = SessionLocal()
        source = db.get(Source, source_id)
        if source:
            db.query(Chunk).filter(Chunk.source_id == source_id).delete()
            source.error_message = None
            source.chunk_count = 0
            db.commit()
        db.close()

        # process_source opens and closes its own DB session
        process_source(source_id, embedder, groq_client)

        # Verify final status
        db2 = SessionLocal()
        updated = db2.get(Source, source_id)
        status = updated.status if updated else "not_found"
        error_msg = updated.error_message if updated else None
        chunk_count = updated.chunk_count if updated else 0
        db2.close()

        if status == "completed":
            return {"id": source_id, "title": source_title, "success": True, "chunks": chunk_count}
        else:
            return {"id": source_id, "title": source_title, "success": False, "error": error_msg, "status": status}
    except Exception as e:
        # Ensure source is marked as failed, not left stuck in "processing"
        try:
            db3 = SessionLocal()
            src = db3.get(Source, source_id)
            if src and src.status == "processing":
                src.status = "failed"
                src.error_message = f"process_pending crash: {str(e)[:400]}"
                db3.commit()
            db3.close()
        except Exception:
            pass
        return {"id": source_id, "title": source_title, "success": False, "error": str(e)}


def main():
    logger.info("=" * 60)
    logger.info("OD Assist — Process Pending Sources")
    logger.info("=" * 60)

    # Phase 1: Reset stuck sources
    logger.info("\nPhase 1: Checking for stuck 'processing' sources...")
    db = SessionLocal()
    reset_ids = reset_stuck_sources(db)

    # Phase 2: Gather all pending sources
    pending_sources = db.query(Source).filter(Source.status == "pending").all()
    db.close()

    if not pending_sources:
        logger.info("No pending sources found. Nothing to do.")
        return

    total = len(pending_sources)
    logger.info("\nPhase 2: Found %d pending sources. Initializing models...", total)
    for s in pending_sources:
        logger.info("  -> ID:%d | %s (%s)", s.id, s.title, s.source_type)

    # Initialize models (heavy — do once)
    embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    logger.info("\nPhase 3: Processing with %d concurrent workers...\n", MAX_WORKERS)

    completed = 0
    failed_results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_source = {
            executor.submit(
                process_single_source, s.id, s.title, embedder, groq_client
            ): s
            for s in pending_sources
        }

        processed_count = 0
        for future in as_completed(future_to_source):
            processed_count += 1
            try:
                result = future.result()
            except Exception as e:
                src = future_to_source[future]
                result = {"id": src.id, "title": src.title, "success": False, "error": str(e)}

            status_icon = "OK" if result["success"] else "FAIL"
            logger.info(
                "[%d/%d] %s | ID:%d | %s",
                processed_count, total, status_icon,
                result["id"], result["title"],
            )
            if result["success"]:
                logger.info("         -> %d chunks ingested", result.get("chunks", 0))
                completed += 1
            else:
                logger.error("         -> %s", result.get("error", "unknown error"))
                failed_results.append(result)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info("Total Processed : %d", total)
    logger.info("Completed       : %d", completed)
    logger.info("Failed          : %d", len(failed_results))

    if failed_results:
        logger.info("\nFailure Details:")
        for f in failed_results:
            logger.info("  ID:%d | %s", f["id"], f["title"])
            logger.info("    Error: %s", f.get("error", "?"))

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
