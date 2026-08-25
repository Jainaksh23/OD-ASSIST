import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from db.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=3, max_overflow=2)
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

    # Ensure ivfflat indexes on embeddings are dropped
    with engine.connect() as conn:
        conn.execute(text("DROP INDEX IF EXISTS chunks_embedding_idx;"))
        conn.execute(text("DROP INDEX IF EXISTS query_cache_embedding_idx;"))
        conn.commit()

    # Create HNSW indexes on embeddings (M=16, ef_construction=200 for robust exact-like search)
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx ON chunks "
            "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200);"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS query_cache_embedding_hnsw_idx ON query_cache "
            "USING hnsw (query_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200);"
        ))
        conn.commit()

    # Create GIN index on chunks for full-text keyword search
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = 'chunks_fts_idx' AND n.nspname = 'public';"
        )).fetchone()

        if not result:
            conn.execute(text(
                "CREATE INDEX chunks_fts_idx ON chunks USING GIN "
                "(to_tsvector('english', coalesce(chunk_summary, '') || ' ' || chunk_text));"
            ))
        conn.commit()

    # Seed default system paths
    db = SessionLocal()
    try:
        seed_default_system_paths(db)
    except Exception as e:
        print(f"Error seeding system paths: {e}")
        db.rollback()
    finally:
        db.close()

def seed_default_system_paths(db):
    from db.models import SystemPath, SystemPathStep, Source
    
    # Check if paths already exist to prevent duplicate seeding
    student_path = db.query(SystemPath).filter(SystemPath.title == "Student List Navigation").first()
    if not student_path:
        student_path = SystemPath(
            title="Student List Navigation",
            description="Navigation flow to view student details from the student list"
        )
        db.add(student_path)
        db.flush()
        
        # Add steps: Student List -> Select Student -> Detail
        labels = ["Student List", "Select Student", "Detail"]
        for idx, label in enumerate(labels):
            step = SystemPathStep(
                system_path_id=student_path.id,
                step_label=label,
                step_order=idx + 1
            )
            db.add(step)
            
        # Try to link to a relevant student/admission source
        admission_source = db.query(Source).filter(Source.title.ilike("%admission%")).first()
        if admission_source:
            student_path.sources.append(admission_source)
        db.commit()
        print("Seeded System Path: Student List Navigation")

    assign_route_path = db.query(SystemPath).filter(SystemPath.title == "Assign Route").first()
    if not assign_route_path:
        assign_route_path = SystemPath(
            title="Assign Route",
            description="Navigation flow to assign a transport route to a student"
        )
        db.add(assign_route_path)
        db.flush()
        
        # Add steps: Route List -> Assign Route -> Select Student -> Confirm
        labels = ["Route List", "Assign Route", "Select Student", "Confirm"]
        for idx, label in enumerate(labels):
            step = SystemPathStep(
                system_path_id=assign_route_path.id,
                step_label=label,
                step_order=idx + 1
            )
            db.add(step)
            
        # Link to Transport Setup source
        transport_source = db.query(Source).filter(Source.title.ilike("%transport%")).first()
        if transport_source:
            assign_route_path.sources.append(transport_source)
        db.commit()
        print("Seeded System Path: Assign Route")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
