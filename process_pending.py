import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

from sentence_transformers import SentenceTransformer
from groq import Groq
from db.db import SessionLocal
from db.models import Source
from ingestion.orchestrator import process_source

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

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

    for i, source in enumerate(pending_sources, 1):
        logger.info(f"\n--- Processing {i}/{total}: {source.title} (ID: {source.id}) ---")
        try:
            # process_source opens and closes its own DB session
            process_source(source.id, embedder, groq_client)
            
            # Verify status from DB
            db2 = SessionLocal()
            updated = db2.get(Source, source.id)
            if updated.status == "completed":
                logger.info(f"-> completed!")
                completed += 1
            else:
                logger.error(f"-> failed: {updated.error_message}")
                failed_sources.append({"id": source.id, "title": source.title, "error": updated.error_message})
            db2.close()
        except Exception as e:
            logger.error(f"-> crashed: {e}")
            failed_sources.append({"id": source.id, "title": source.title, "error": str(e)})

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
