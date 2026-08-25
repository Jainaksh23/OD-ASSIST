import time
import asyncio
from db.db import init_db, SessionLocal
from db.models import Chunk, Source

from api.main import get_embedder, search_vectors
from contextlib import contextmanager
from sentence_transformers import SentenceTransformer

def test_retrieval():
    print("Initializing Database (will create HNSW indexes)...")
    init_db()
    
    embedder = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
    db = SessionLocal()
    
    queries = [
        "Transport module setup",
        "What is the employee onboarding process?",
        "How to manage fleet maintenance?",
        "Can you explain fee concession logic?"
    ]
    
    print("\n===========================================")
    print("REGRESSION TEST: CHUNK RETRIEVAL COUNT")
    print("===========================================")
    
    for q in queries:
        print(f"\nQuery: '{q}'")
        emb = embedder.encode(q)
        
        t0 = time.perf_counter()
        results = search_vectors(q, db, embedder, k=20, query_embedding=emb)
        t1 = time.perf_counter()
        
        print(f"Retrieved {len(results)} chunks.")
        print(f"Retrieval Time (DB only): {(t1-t0)*1000:.2f} ms")
        
        if len(results) > 0:
            print(f"Top result score: {results[0]['score']}")
        if len(results) < 5:
            print("WARNING: Retrieved too few chunks! Possible HNSW bug.")

if __name__ == "__main__":
    test_retrieval()
