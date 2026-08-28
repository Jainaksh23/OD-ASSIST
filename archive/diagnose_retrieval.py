"""Deep diagnostic: what does retrieval actually return for failing queries?"""
import sys, os, codecs
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from db.db import SessionLocal
from sentence_transformers import SentenceTransformer
from sqlalchemy import text

db = SessionLocal()
embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")

test_queries = [
    "How do I add a new bus",
    "How do I add a new bus and set its seating capacity?",
    "Transport set up k baare m btao",
    "How is payroll processed?",
    "Fee collection kaise hota hai?",
    "Tell me about transport setup",
    "new vehicle add karna hai",
]

for q in test_queries:
    print(f"\n{'='*60}")
    print(f"QUERY: {q}")
    print(f"{'='*60}")
    
    emb = embedder.encode(q)
    
    # Vector search - top 5 with similarity scores
    sql = text("""
        SELECT c.id, c.source_id, s.title,
               1 - (c.embedding <=> CAST(:emb AS vector)) AS similarity,
               LEFT(c.chunk_text, 100) AS snippet
        FROM chunks c
        JOIN sources s ON c.source_id = s.id
        ORDER BY c.embedding <=> CAST(:emb AS vector) 
        LIMIT 5
    """)
    rows = db.execute(sql, {"emb": str(emb.tolist())}).fetchall()
    
    print(f"\n  Vector Search Results:")
    for r in rows:
        print(f"    sim={r.similarity:.4f} | src={r.source_id} ({r.title[:40]}) | {r.snippet[:80]}...")
    
    # Keyword search
    kw_sql = text("""
        SELECT c.id, c.source_id, s.title,
               ts_rank_cd(c.search_vector, websearch_to_tsquery('english', :query)) AS score,
               LEFT(c.chunk_text, 100) AS snippet
        FROM chunks c
        JOIN sources s ON c.source_id = s.id
        WHERE c.search_vector @@ websearch_to_tsquery('english', :query)
        ORDER BY score DESC
        LIMIT 5
    """)
    kw_rows = db.execute(kw_sql, {"query": q}).fetchall()
    
    print(f"\n  Keyword Search Results ({len(kw_rows)} hits):")
    for r in kw_rows:
        print(f"    score={r.score:.4f} | src={r.source_id} ({r.title[:40]}) | {r.snippet[:80]}...")
    
    if not kw_rows:
        print(f"    (no keyword matches)")

db.close()
print("\n\nDone.")
