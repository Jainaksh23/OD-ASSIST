import os
import glob
import hashlib
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from groq import Groq

# Load environment variables (DATABASE_URL, GROQ_API_KEY)
load_dotenv()

# Import from project
from db.db import SessionLocal
from db.models import Source, User
from ingestion.orchestrator import process_source

PDF_DIR = r"D:\D\PDF2"

def bulk_ingest():
    print("Loading embedder and Groq client...")
    embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")
    groq_client = Groq()
    
    print(f"Scanning {PDF_DIR} for PDFs...")
    pdf_files = glob.glob(os.path.join(PDF_DIR, "*.pdf"))
    
    if not pdf_files:
        print(f"No PDFs found in {PDF_DIR}.")
        return

    print(f"Found {len(pdf_files)} PDFs.")
    
    with SessionLocal() as temp_db:
        admin = temp_db.query(User).filter(User.username == "odadmin").first()
        admin_id = admin.id if admin else None

    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        print(f"\n--- Processing: {filename} ---")
        
        db = SessionLocal()
        try:
            hasher = hashlib.sha256()
            try:
                with open(pdf_path, "rb") as f:
                    hasher.update(f.read())
                file_hash = hasher.hexdigest()
            except Exception as e:
                print(f"Error reading file {filename}: {e}")
                continue

            existing = db.query(Source).filter(Source.file_hash == file_hash).first()
            if existing:
                if existing.status == "completed":
                    print(f"Skipped: Duplicate already exists in DB as '{existing.title}'.")
                    continue
                else:
                    print(f"Found existing source '{existing.title}' with status '{existing.status}'. Retrying...")
                    source = existing
                    source.source_url = pdf_path
            else:
                source = Source(
                    title=filename.replace(".pdf", ""),
                    source_type="pdf",
                    source_url=pdf_path,
                    status="processing",
                    file_hash=file_hash,
                    ingested_by=admin_id,
                )
                db.add(source)
                db.commit()
                db.refresh(source)

            source.status = "processing"
            db.commit()

            try:
                print(f"Starting extraction & embedding for {filename}...")
                process_source(source.id, embedder, groq_client)
                
                db.refresh(source)
                if source.status == "completed":
                    print(f"SUCCESS: Ingested {source.chunk_count} chunks.")
                else:
                    print(f"FAILED: {source.error_message}")
            except Exception as e:
                db.rollback()
                print(f"CRITICAL ERROR processing {filename}: {e}")
        finally:
            db.close()

if __name__ == "__main__":
    bulk_ingest()
