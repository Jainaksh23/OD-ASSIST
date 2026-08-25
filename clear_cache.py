from sqlalchemy import text
from db.db import engine

def clear_cache():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM query_cache;"))
        conn.commit()
    print("Query cache cleared.")

if __name__ == "__main__":
    clear_cache()
