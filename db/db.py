import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from db.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    # Enable pgvector extension
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    
    # Create tables (includes new query_cache table)
    Base.metadata.create_all(bind=engine)
    
    # Add new columns to query_logs if they don't exist
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS confidence VARCHAR(20);"))
        conn.execute(text("ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS normalized_query TEXT;"))
        conn.execute(text("ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS cached BOOLEAN DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS response_time_ms INTEGER DEFAULT 0;"))
        conn.commit()

    # Create ivfflat index on chunks.embedding
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = 'chunks_embedding_idx' AND n.nspname = 'public';"
        )).fetchone()
        
        if not result:
             conn.execute(text(
                 "CREATE INDEX chunks_embedding_idx ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
             ))
        conn.commit()

    # Create ivfflat index on query_cache.query_embedding
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = 'query_cache_embedding_idx' AND n.nspname = 'public';"
        )).fetchone()

        if not result:
            # Use a smaller lists value since query_cache will have far fewer rows than chunks
            conn.execute(text(
                "CREATE INDEX query_cache_embedding_idx ON query_cache "
                "USING ivfflat (query_embedding vector_cosine_ops) WITH (lists = 10);"
            ))
        conn.commit()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
