from typing import List, Dict

def merge_results(vector_results: List[Dict], keyword_results: List[Dict], top_k: int = 5, k_rrf: int = 60) -> List[Dict]:
    """
    Merges vector and keyword search results using Reciprocal Rank Fusion (RRF).
    """
    rrf_scores = {}
    docs = {}
    
    # Process vector results
    for rank, doc in enumerate(vector_results):
        doc_id = doc["id"]
        docs[doc_id] = doc
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k_rrf + rank + 1)
        
    # Process keyword results
    for rank, doc in enumerate(keyword_results):
        doc_id = doc["id"]
        docs[doc_id] = doc
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k_rrf + rank + 1)
        
    # Sort by RRF score
    sorted_docs = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
    
    # Return top_k docs
    merged = []
    for doc_id, score in sorted_docs[:top_k]:
        doc = docs[doc_id]
        doc["rrf_score"] = score
        merged.append(doc)
        
    return merged
