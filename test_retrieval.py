import sys
import os
from db.db import SessionLocal
from db.models import Source, Chunk
from retrieval.vector_search import get_semantic_search_results
from retrieval.keyword_search import get_keyword_search_results
from sentence_transformers import SentenceTransformer
import warnings
warnings.filterwarnings('ignore')

db = SessionLocal()
embedder = SentenceTransformer('all-MiniLM-L6-v2')
query = "New student admission process"

print("--- Keyword Search ---")
k_res = get_keyword_search_results(query, limit=5)
for r in k_res:
    print(r['title'], r['score'])

print("\n--- Semantic Search ---")
emb = embedder.encode([query])[0]
s_res = get_semantic_search_results(emb, limit=5)
for r in s_res:
    print(r['title'], r['score'])
