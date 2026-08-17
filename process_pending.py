import os
import sys
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

from sentence_transformers import SentenceTransformer
from groq import Groq
from db.db import SessionLocal
from db.models import Source
from ingestion.orchestrator import process_source

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

def process_single_source(source_id, source_title, embedder, groq_client):
    try:
        # process_source opens and closes its own DB session
        process_source(source_id, embedder, groq_client)
        
        # Verify status from DB
        db2 = SessionLocal()
        updated = db2.get(Source, source_id)
        status = updated.status
        error_msg = updated.error_message
        db2.close()
        
        if status == "completed":
            return {"id": source_id, "title": source_title, "success": True}
        else:
            return {"id": source_id, "title": source_title, "success": False, "error": error_msg}
    except Exception as e:
        return {"id": source_id, "title": source_title, "success": False, "error": str(e)}

def main():
    logger.info("Initializing models...")
    embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    db = SessionLocal()
    pending_sources = db.query(Source).filter(Source.status == "pending").all()
    db.close()

    if not pending_sources:
        logger.info("No pending sources found in the database.")
        return

    total = len(pending_sources)
    logger.info(f"Found {total} pending sources. Starting processing loop...")

    completed = 0
    failed_sources = []
    
    # Using 3 workers to speed up processing without hitting rate limits too fast
    max_workers = 3
    logger.info(f"Processing concurrently with {max_workers} workers...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_source = {
            executor.submit(process_single_source, source.id, source.title, embedder, groq_client): source
            for source in pending_sources
        }
        
        processed_count = 0
        for future in as_completed(future_to_source):
            processed_count += 1
            result = future.result()
            
            logger.info(f"\n--- Processed {processed_count}/{total}: {result['title']} (ID: {result['id']}) ---")
            if result["success"]:
                logger.info("-> completed!")
                completed += 1
            else:
                logger.error(f"-> failed: {result.get('error')}")
                failed_sources.append(result)

    logger.info("\n==============================================")
    logger.info("SUMMARY:")
    logger.info(f"Total Processed : {total}")
    logger.info(f"Completed       : {completed}")
    logger.info(f"Failed          : {len(failed_sources)}")
    
    if failed_sources:
        logger.info("\nFailure Details:")
        for f in failed_sources:
            logger.info(f"  - ID {f['id']} | {f['title']}\n    Error: {f['error']}")
    logger.info("==============================================\n")

if __name__ == "__main__":
    main()
