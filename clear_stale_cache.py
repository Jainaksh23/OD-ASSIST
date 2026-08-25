"""Clear cached 'I don't know' answers so fresh generation uses updated prompt."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db.db import SessionLocal
from db.models import QueryCache
from sqlalchemy import text

db = SessionLocal()
# Delete cache entries where the answer is the "I don't know" response
result = db.execute(text("""
    DELETE FROM query_cache 
    WHERE answer_text LIKE '%I don''t have enough information%'
    OR answer_text LIKE '%Mere paas iska%'
    OR answer_text LIKE '%Mere paas isse%'
    OR answer_text LIKE '%kaafi jaankari nahi%'
    OR answer_text LIKE '%kaafi information nahi%'
"""))
db.commit()
print(f"Deleted {result.rowcount} stale 'I don't know' cache entries.")
db.close()
