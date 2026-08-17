"""
api/main.py — OD Assist FastAPI application.

Startup (lifespan):
  - init_db(): creates tables + pgvector extension
  - SentenceTransformer loaded once → app.state.embedder
  - Groq client initialized once → app.state.groq_client

Routes:
  POST /auth/login
  POST /admin/ingest          (JSON: drive/raw_text)
  POST /admin/upload_pdf      (multipart)
  GET  /admin/sources
  DELETE /admin/sources/{id}
  POST /chat/query
  POST /chat/feedback
  GET  /          → redirect to user panel
  GET  /admin     → redirect to admin panel
  /static/*       → static HTML/CSS/JS files
"""

import json
import logging
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import (BackgroundTasks, Depends, FastAPI, File, Form,
                     HTTPException, Request, UploadFile, status)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from groq import Groq
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.auth import (create_access_token, get_current_user, require_admin,
                      verify_password, get_password_hash)
from api.schemas import (FeedbackRequest, IngestRequest, LoginRequest,
                          QueryRequest, QueryResponse, SourceMetadata,
                          SourceResponse, TokenResponse, BulkIngestRequest, UserCreate, UserResponse)
from db.db import SessionLocal, get_db, init_db
from db.models import QueryLog, Source, User, Chunk
from generation.confidence_check import determine_confidence
from generation.generator import generate_answer
from ingestion.orchestrator import process_source
from ingestion.input_router import is_folder_link
from retrieval.hybrid_merge import merge_results
from retrieval.keyword_search import search_keywords
from retrieval.vector_search import search_vectors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMP_DIR = "temp_files"
AUTO_PROCESS_INTERVAL = 60   # seconds between auto-process checks
STUCK_THRESHOLD_HOURS = 1    # sources in "processing" longer than this → reset


# ── Auto-processor: picks up pending/stuck sources automatically ─────────────

def _auto_process_pending(embedder, groq_client, stop_event: threading.Event):
    """
    Background daemon that periodically checks for pending or stuck sources
    and processes them. Runs until stop_event is set (server shutdown).
    """
    logger.info("Auto-processor started (interval=%ds)", AUTO_PROCESS_INTERVAL)

    while not stop_event.is_set():
        try:
            db = SessionLocal()

            # Reset stuck "processing" sources (> threshold hours old)
            threshold = datetime.now(timezone.utc) - timedelta(hours=STUCK_THRESHOLD_HOURS)
            stuck = db.query(Source).filter(
                Source.status == "processing",
                Source.created_at < threshold,
            ).all()
            for s in stuck:
                db.query(Chunk).filter(Chunk.source_id == s.id).delete()
                s.status = "pending"
                s.error_message = None
                s.chunk_count = 0
                logger.info("Auto-processor: reset stuck source ID:%d (%s)", s.id, s.title)
            if stuck:
                db.commit()

            # Find pending sources
            pending = db.query(Source).filter(Source.status == "pending").all()
            pending_ids = [(s.id, s.title) for s in pending]
            db.close()

            if pending_ids:
                logger.info("Auto-processor: found %d pending sources, processing...", len(pending_ids))
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = {
                        pool.submit(process_source, sid, embedder, groq_client): title
                        for sid, title in pending_ids
                    }
                    for f in futures:
                        try:
                            f.result()
                        except Exception:
                            logger.exception(
                                "Auto-processor: failed processing '%s'", futures[f]
                            )

        except Exception:
            logger.exception("Auto-processor: cycle error")

        # Sleep in small increments so we can respond to stop_event quickly
        for _ in range(AUTO_PROCESS_INTERVAL):
            if stop_event.is_set():
                break
            time.sleep(1)

    logger.info("Auto-processor stopped")


# ── Lifespan: all singletons initialized once at startup ─────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("OD Assist starting up...")

    init_db()
    logger.info("Database ready")

    # Embedding model — weights already baked into Docker image
    app.state.embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")
    logger.info("Embedding model loaded")

    # Groq client — single instance shared across all requests
    app.state.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    logger.info("Groq client initialized")

    os.makedirs(TEMP_DIR, exist_ok=True)

    # Start auto-processor daemon thread
    stop_event = threading.Event()
    auto_thread = threading.Thread(
        target=_auto_process_pending,
        args=(app.state.embedder, app.state.groq_client, stop_event),
        daemon=True,
        name="auto-processor",
    )
    auto_thread.start()
    logger.info("Auto-processor thread started")

    yield  # ── server is running ─────────────────────────────────────────────

    # Graceful shutdown: signal the auto-processor to stop
    logger.info("OD Assist shutting down — stopping auto-processor...")
    stop_event.set()
    auto_thread.join(timeout=5)
    logger.info("OD Assist shutdown complete")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OD Assist",
    description="RAG chatbot for Okie Dokie organizational knowledge",
    version="2.0.0",
    lifespan=lifespan,
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers to pull singletons from app.state ─────────────────────────────────

def get_embedder(request: Request):
    return request.app.state.embedder


def get_groq(request: Request):
    return request.app.state.groq_client


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    token = create_access_token(data={"sub": user.username, "role": user.role})
    return TokenResponse(access_token=token, token_type="bearer", role=user.role)


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.post("/admin/upload_pdf", response_model=SourceResponse, tags=["admin"])
async def upload_pdf(
    background_tasks: BackgroundTasks,
    title: str = Form(default=""),
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    embedder=Depends(get_embedder),
    groq_client=Depends(get_groq),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    safe_name = f"pdf_{os.urandom(8).hex()}.pdf"
    temp_path = os.path.join(TEMP_DIR, safe_name)
    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    effective_title = title.strip() or file.filename or "Uploaded PDF"
    source = Source(
        title=effective_title,
        source_type="pdf",
        source_url=temp_path,   # orchestrator reads from this path
        status="processing",
        ingested_by=admin.id,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    # process_source creates its own DB session — safe as a background task
    background_tasks.add_task(
        process_source,
        source.id,
        embedder,
        groq_client,
    )
    return source


@app.post("/admin/ingest", response_model=SourceResponse, tags=["admin"])
def ingest_source(
    background_tasks: BackgroundTasks,
    body: IngestRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    embedder=Depends(get_embedder),
    groq_client=Depends(get_groq),
):
    """
    Ingest a Drive link or raw text.
    For raw_text: source_url stores the actual text content.
    For drive_doc/drive_video: source_url stores the Drive share link.
    """
    if body.source_type in ("drive_doc", "drive_video") and is_folder_link(body.source_url):
        raise HTTPException(
            status_code=400, 
            detail="Folder links are not supported — please paste the individual file link (right-click the file → Share → Copy link)"
        )

    effective_title = (body.title or "").strip() or body.source_url[:60]
    source = Source(
        title=effective_title,
        source_type=body.source_type,
        source_url=body.source_url,
        status="processing",
        ingested_by=admin.id,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    background_tasks.add_task(
        process_source,
        source.id,
        embedder,
        groq_client,
    )
    return source


@app.get("/admin/sources", response_model=list[SourceResponse], tags=["admin"])
def list_sources(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(Source).order_by(Source.created_at.desc()).all()


@app.delete("/admin/sources/{source_id}", tags=["admin"])
def delete_source(
    source_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(source)
    db.commit()
    return {"message": f"Source {source_id} and all its chunks deleted"}


@app.post("/admin/sources/{source_id}/retry", response_model=SourceResponse, tags=["admin"])
def retry_source(
    source_id: int,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    embedder=Depends(get_embedder),
    groq_client=Depends(get_groq),
):
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.status != "failed":
        raise HTTPException(status_code=400, detail="Only failed sources can be retried")

    db.query(Chunk).filter(Chunk.source_id == source_id).delete()
    
    source.status = "processing"
    source.error_message = None
    source.chunk_count = 0
    db.commit()
    db.refresh(source)

    background_tasks.add_task(
        process_source,
        source.id,
        embedder,
        groq_client,
    )
    return source


@app.post("/admin/sources/retry-all", tags=["admin"])
def retry_all_failed(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    embedder=Depends(get_embedder),
    groq_client=Depends(get_groq),
):
    """
    Bulk-retry ALL failed sources.
    Resets status → processing, clears stale chunks, then processes
    sequentially (max 2 concurrent) in a background thread to avoid
    Groq/HF rate-limit hits.
    """
    failed_sources = db.query(Source).filter(Source.status == "failed").all()
    if not failed_sources:
        return {"message": "No failed sources to retry", "queued_count": 0}

    source_ids = []
    for src in failed_sources:
        # Clear old chunks to prevent duplicates
        db.query(Chunk).filter(Chunk.source_id == src.id).delete()
        src.status = "processing"
        src.error_message = None
        src.chunk_count = 0
        source_ids.append(src.id)
    db.commit()

    # Process in a background thread — max 2 concurrent to respect rate limits
    def _bulk_retry_worker(ids, emb, groq):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(process_source, sid, emb, groq) for sid in ids]
            for f in futures:
                try:
                    f.result()
                except Exception:
                    logger.exception("retry-all: one source failed during reprocessing")

    thread = threading.Thread(
        target=_bulk_retry_worker,
        args=(source_ids, embedder, groq_client),
        daemon=True,
    )
    thread.start()

    return {
        "message": f"Queued {len(source_ids)} failed sources for retry",
        "queued_count": len(source_ids),
        "source_ids": source_ids,
    }


@app.post("/admin/bulk_ingest", tags=["admin"])
def bulk_ingest(
    body: BulkIngestRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    embedder=Depends(get_embedder),
    groq_client=Depends(get_groq),
):
    lines = body.bulk_text.strip().splitlines()
    created_sources = []
    skipped_sources = []
    for line in lines:
        parts = line.split("|", 1)
        if len(parts) == 2:
            title = parts[0].strip()
            url = parts[1].strip()
            
            if is_folder_link(url):
                skipped_sources.append({
                    "title": title,
                    "url": url,
                    "reason": "Folder link — not supported"
                })
                continue
            
            # All bulk-import sources are Drive links (YouTube not supported).
            # Default to drive_doc — orchestrator auto-detects the real type
            # (doc vs video) from the downloaded file's extension.
            source_type = "drive_doc"
                
            source = Source(
                title=title or url[:60],
                source_type=source_type,
                source_url=url,
                status="processing",
                ingested_by=admin.id,
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            
            background_tasks.add_task(
                process_source,
                source.id,
                embedder,
                groq_client,
            )
            created_sources.append(source.id)
            
    return {
        "message": f"Queued {len(created_sources)} sources for processing", 
        "source_ids": created_sources,
        "skipped": skipped_sources
    }


@app.post("/admin/users", response_model=UserResponse, tags=["admin"])
def create_user(
    body: UserCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role must be admin or user")
        
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
        
    new_user = User(
        username=body.username,
        password_hash=get_password_hash(body.password),
        role=body.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.get("/admin/users", response_model=list[UserResponse], tags=["admin"])
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(User).order_by(User.id.desc()).all()


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/chat/query", response_model=QueryResponse, tags=["chat"])
@limiter.limit("15/minute")
def query_bot(
    request: Request,
    body: QueryRequest,
    db: Session = Depends(get_db),
    embedder=Depends(get_embedder),
    groq_client=Depends(get_groq),
):
    vec_results = search_vectors(body.query, db, embedder, k=20)
    kw_results = search_keywords(body.query, db, k=20)
    merged = merge_results(vec_results, kw_results, top_k=5)

    gen = generate_answer(body.query, merged, groq_client)
    confidence = determine_confidence(gen["answer"])

    # Resolve source metadata for display
    source_metas = []
    if gen["sources_used"]:
        sources = db.query(Source).filter(Source.id.in_(gen["sources_used"])).all()
        source_metas = [SourceMetadata(id=s.id, title=s.title or f"Source {s.id}") for s in sources]

    log_entry = QueryLog(
        user_id=None,
        query=body.query,
        answer=gen["answer"],
        sources_used=json.dumps(gen["sources_used"]),
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)

    return QueryResponse(
        answer=gen["answer"],
        confidence=confidence,
        sources=source_metas,
        query_id=log_entry.id,
    )


@app.post("/chat/feedback", tags=["chat"])
@limiter.limit("15/minute")
def submit_feedback(
    request: Request,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
):
    if body.feedback not in ("up", "down"):
        raise HTTPException(status_code=400, detail="feedback must be 'up' or 'down'")
    log = db.get(QueryLog, body.query_id)
    if not log:
        raise HTTPException(status_code=404, detail="Query log not found")
    log.feedback = body.feedback
    db.commit()
    return {"message": "Feedback recorded"}


# ── Page routing ──────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/static/user.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return RedirectResponse(url="/static/admin.html")


# Mount static LAST so API routes always take priority
app.mount("/static", StaticFiles(directory="static"), name="static")
