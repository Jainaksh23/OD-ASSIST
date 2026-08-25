import sys, os
sys.path.insert(0, "d:/OKIE DOKIE PORTAL/od-assist")
from dotenv import load_dotenv
load_dotenv(dotenv_path="d:/OKIE DOKIE PORTAL/od-assist/.env")

from db.db import SessionLocal
from db.models import FAQ
from sqlalchemy import text
from sentence_transformers import SentenceTransformer

db = SessionLocal()

print("Adding embedding column to faqs table...")
try:
    db.execute(text("ALTER TABLE faqs ADD COLUMN embedding vector(384)"))
    db.commit()
    print("Column added successfully.")
except Exception as e:
    db.rollback()
    print(f"Column might already exist: {e}")

print("Loading embedder...")
embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")

print("Fetching FAQs without embeddings...")
faqs = db.query(FAQ).filter(FAQ.embedding == None).all()
print(f"Found {len(faqs)} FAQs to embed.")

for faq in faqs:
    # Embed the question and answer together
    text_to_embed = f"Q: {faq.question}\nA: {faq.answer}"
    emb = embedder.encode(text_to_embed).tolist()
    faq.embedding = emb

db.commit()
print("Backfill complete!")

db.close()
