from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict

def search_faqs(query: str, db: Session, embedder, k: int = 5, query_embedding=None) -> List[Dict]:
    """
    Performs cosine similarity search over published FAQs using pgvector `<=>` operator.
    """
    if query_embedding is None:
        query_embedding = embedder.encode(query)
        
    sql = text("""
        SELECT f.id, f.question, f.answer, f.category, f.linked_source_id,
               1 - (f.embedding <=> CAST(:emb AS vector)) AS similarity 
        FROM faqs f
        WHERE f.is_published = true AND f.embedding IS NOT NULL
        ORDER BY f.embedding <=> CAST(:emb AS vector) 
        LIMIT :k
    """)
    
    result = db.execute(sql, {"emb": str(query_embedding.tolist()), "k": k}).fetchall()
    
    # We only return FAQs that are reasonably relevant (sim > 0.65 roughly, though we can just return top_k and let the LLM decide)
    return [
        {
            "id": row[0],
            "question": row[1],
            "answer": row[2],
            "category": row[3],
            "source_id": row[4],
            "score": row[5]
        }
        for row in result if row[5] > 0.60
    ]
