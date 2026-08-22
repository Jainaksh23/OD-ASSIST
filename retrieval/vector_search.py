from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict

def search_vectors(query: str, db: Session, embedder, k: int = 20, query_embedding=None) -> List[Dict]:
    """
    Performs cosine similarity search using pgvector `<=>` operator.
    Accepts an optional pre-computed query_embedding to avoid redundant encoding.
    """
    if query_embedding is None:
        query_embedding = embedder.encode(query)
    
    # Raw SQL with pgvector for performance and direct operator usage
    sql = text("""
        SELECT c.id, c.source_id, c.chunk_text, c.chunk_summary, s.title,
               1 - (c.embedding <=> CAST(:emb AS vector)) AS similarity 
        FROM chunks c
        JOIN sources s ON c.source_id = s.id
        ORDER BY c.embedding <=> CAST(:emb AS vector) 
        LIMIT :k
    """)
    
    result = db.execute(sql, {"emb": str(query_embedding.tolist()), "k": k}).fetchall()
    
    return [
        {
            "id": row[0],
            "source_id": row[1],
            "chunk_text": row[2],
            "chunk_summary": row[3],
            "source_title": row[4],
            "score": row[5]
        }
        for row in result
    ]
