from sqlalchemy.orm import Session
from rank_bm25 import BM25Okapi
from typing import List, Dict
from db.models import Chunk, Source

def search_keywords(query: str, db: Session, k: int = 20) -> List[Dict]:
    """
    Performs BM25 keyword search over all chunks (MVP implementation).
    """
    # For MVP, load all chunks. This can be optimized later (e.g. elasticsearch or pg_trgm)
    all_chunks = db.query(Chunk, Source.title).join(Source, Chunk.source_id == Source.id).all()
    
    if not all_chunks:
        return []
        
    corpus = []
    chunk_meta = []
    
    for chunk, source_title in all_chunks:
        # We index the concatenation of summary and text
        text_to_index = f"{chunk.chunk_summary or ''} {chunk.chunk_text}"
        corpus.append(text_to_index.lower().split())
        chunk_meta.append({
            "id": chunk.id,
            "source_id": chunk.source_id,
            "chunk_text": chunk.chunk_text,
            "chunk_summary": chunk.chunk_summary,
            "source_title": source_title
        })
        
    bm25 = BM25Okapi(corpus)
    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)
    
    # Get top k
    top_k_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    
    results = []
    for idx in top_k_indices:
        if scores[idx] > 0: # only return if there's some match
            meta = chunk_meta[idx]
            meta["score"] = scores[idx]
            results.append(meta)
            
    return results
