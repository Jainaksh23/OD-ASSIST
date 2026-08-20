"""Check updated_at column and show stuck sources."""
import os
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

with engine.connect() as conn:
    # Check if column exists
    result = conn.execute(text("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'sources' AND column_name = 'updated_at';
    """)).fetchone()
    
    if result:
        print("[OK] 'updated_at' column exists in sources table.")
    else:
        print("[MISSING] 'updated_at' column NOT found - adding it now...")
        conn.execute(text("""
            ALTER TABLE sources 
            ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
        """))
        conn.execute(text("""
            UPDATE sources SET updated_at = created_at WHERE updated_at IS NULL;
        """))
        conn.commit()
        print("[OK] Column added and backfilled.")
    
    # Backfill any nulls
    conn.execute(text("""
        UPDATE sources SET updated_at = created_at WHERE updated_at IS NULL;
    """))
    conn.commit()
    print("[OK] Any null updated_at values backfilled from created_at.")
    
    # Show current stuck sources
    print("\n--- Current 'processing' sources ---")
    rows = conn.execute(text("""
        SELECT id, title, source_type, status, created_at, updated_at, error_message
        FROM sources 
        WHERE status = 'processing'
        ORDER BY id;
    """)).fetchall()
    
    if not rows:
        print("  (none found)")
    else:
        for r in rows:
            print(f"  ID:{r[0]:3d} | {r[2]:12s} | status={r[3]} | created={r[4]} | updated={r[5]} | {r[1]}")
    
    print(f"\nTotal stuck 'processing': {len(rows)}")
    
    # Also show all sources summary
    print("\n--- All sources summary ---")
    all_rows = conn.execute(text("""
        SELECT status, count(*) FROM sources GROUP BY status ORDER BY status;
    """)).fetchall()
    for r in all_rows:
        print(f"  {r[0]:12s}: {r[1]}")
