from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict

def search_keywords(query: str, db: Session, k: int = 20) -> List[Dict]:
    """
    Performs fast keyword search using PostgreSQL Full-Text Search.
    """
    sql = text("""
        SELECT c.id, c.source_id, c.chunk_text, c.chunk_summary, s.title,
               ts_rank_cd(c.search_vector, websearch_to_tsquery('english', :query)) AS score
        FROM chunks c
        JOIN sources s ON c.source_id = s.id
        WHERE c.search_vector @@ websearch_to_tsquery('english', :query)
        ORDER BY score DESC
        LIMIT :k
    """)
    
    result = db.execute(sql, {"query": query, "k": k}).fetchall()
    
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
