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
os.environ["OMP_NUM_THREADS"] = "1"  # Limit PyTorch memory/CPU usage
import shutil
import threading
import time
import re
from typing import List, Dict, Optional, Any, Union, Tuple
from sqlalchemy import func, text
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import (BackgroundTasks, Depends, FastAPI, File, Form,
                     HTTPException, Request, UploadFile, status)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, StreamingResponse
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
                          SourceResponse, TokenResponse, BulkIngestRequest, UserCreate, UserResponse,
                          SystemPathResponse, SystemPathCreate, SystemPathSimpleResponse,
                          FAQCreate, FAQUpdate, FAQResponse, FAQReorderRequest)
from db.db import SessionLocal, get_db, init_db
from db.models import QueryLog, QueryCache, Source, User, Chunk, SystemPath, SystemPathStep, FAQ
from generation.confidence_check import determine_confidence
from generation.generator import generate_answer
from ingestion.orchestrator import process_source
from ingestion.input_router import is_folder_link
from retrieval.hybrid_merge import merge_results
from retrieval.keyword_search import search_keywords
from retrieval.vector_search import search_vectors

import tempfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMP_DIR = os.path.join(tempfile.gettempdir(), "od_assist_temp")
AUTO_PROCESS_INTERVAL = 60   # seconds between auto-process checks
STUCK_THRESHOLD_MINUTES = 15 # sources in "processing" longer than this → mark failed
CACHE_SIMILARITY_THRESHOLD = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.90"))
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "48"))


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

            # Safety-net: detect and fail stuck "processing" sources
            # (crash recovery — sources abandoned by dead workers)
            threshold = datetime.now(timezone.utc) - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
            stuck = db.query(Source).filter(
                Source.status == "processing",
                Source.updated_at < threshold,
            ).all()
            if stuck:
                for s in stuck:
                    s.status = "failed"
                    s.error_message = (
                        f"Safety-net: source stuck in 'processing' for >{STUCK_THRESHOLD_MINUTES} min "
                        f"(last updated: {s.updated_at}). Marked as failed for manual retry."
                    )
                    logger.warning(
                        "Safety-net: marked stuck source ID:%d (%s) as 'failed'",
                        s.id, s.title,
                    )
                db.commit()
                logger.info("Safety-net: marked %d stuck sources as 'failed'", len(stuck))

            # Find pending sources
            pending = db.query(Source).filter(Source.status == "pending").all()
            pending_ids = [(s.id, s.title) for s in pending]
            db.close()

            if pending_ids:
                logger.info("Auto-processor: found %d pending sources, processing...", len(pending_ids))
                with ThreadPoolExecutor(max_workers=1) as pool:
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

    # Reset any stuck processing sources to failed
    from db.db import SessionLocal
    from db.models import Source
    db = SessionLocal()
    stuck = db.query(Source).filter(Source.status == "processing").all()
    if stuck:
        for s in stuck:
            s.status = "failed"
            s.error_message = "Processing interrupted by server shutdown/restart."
        db.commit()
        logger.info(f"Marked {len(stuck)} stuck 'processing' sources as 'failed'.")
    db.close()

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


def get_system_paths_for_sources(db: Session, source_ids: List[int]) -> List[dict]:
    if not source_ids:
        return []
    from db.models import system_path_sources
    paths = (
        db.query(SystemPath)
        .join(system_path_sources, SystemPath.id == system_path_sources.c.system_path_id)
        .filter(system_path_sources.c.source_id.in_(source_ids))
        .distinct()
        .all()
    )
    result = []
    for p in paths:
        steps_sorted = sorted(p.steps, key=lambda s: s.step_order)
        step_labels = [s.step_label for s in steps_sorted]
        result.append({
            "title": p.title,
            "description": p.description,
            "steps": step_labels
        })
    return result


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
        with ThreadPoolExecutor(max_workers=1) as pool:
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


# ── Admin System Paths ────────────────────────────────────────────────────────

@app.get("/admin/system-paths", response_model=list[SystemPathResponse], tags=["admin"])
def list_system_paths(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(SystemPath).order_by(SystemPath.created_at.desc()).all()


@app.post("/admin/system-paths", response_model=SystemPathResponse, tags=["admin"])
def create_system_path(
    body: SystemPathCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    path = SystemPath(
        title=body.title,
        description=body.description
    )
    db.add(path)
    db.flush()

    # Create steps
    for idx, label in enumerate(body.steps):
        step = SystemPathStep(
            system_path_id=path.id,
            step_label=label,
            step_order=idx + 1
        )
        db.add(step)

    # Link sources
    if body.source_ids:
        sources = db.query(Source).filter(Source.id.in_(body.source_ids)).all()
        path.sources.extend(sources)

    db.commit()
    db.refresh(path)
    return path


@app.put("/admin/system-paths/{path_id}", response_model=SystemPathResponse, tags=["admin"])
def update_system_path(
    path_id: int,
    body: SystemPathCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    path = db.get(SystemPath, path_id)
    if not path:
        raise HTTPException(status_code=404, detail="System path not found")

    path.title = body.title
    path.description = body.description

    # Delete old steps
    db.query(SystemPathStep).filter(SystemPathStep.system_path_id == path_id).delete()

    # Re-create steps
    for idx, label in enumerate(body.steps):
        step = SystemPathStep(
            system_path_id=path.id,
            step_label=label,
            step_order=idx + 1
        )
        db.add(step)

    # Update sources
    path.sources.clear()
    if body.source_ids:
        sources = db.query(Source).filter(Source.id.in_(body.source_ids)).all()
        path.sources.extend(sources)

    db.commit()
    db.refresh(path)
    return path


@app.delete("/admin/system-paths/{path_id}", tags=["admin"])
def delete_system_path(
    path_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    path = db.get(SystemPath, path_id)
    if not path:
        raise HTTPException(status_code=404, detail="System path not found")
    db.delete(path)
    db.commit()
    return {"message": f"System path {path_id} deleted successfully"}

# ── FAQs ──────────────────────────────────────────────────────────────────────

@app.get("/faqs", response_model=list[FAQResponse], tags=["chat"])
def get_public_faqs(db: Session = Depends(get_db)):
    return db.query(FAQ).filter(FAQ.is_published == True).order_by(FAQ.display_order.asc()).all()

@app.get("/admin/faqs", response_model=list[FAQResponse], tags=["admin"])
def get_admin_faqs(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(FAQ).order_by(FAQ.display_order.asc()).all()

@app.post("/admin/faqs", response_model=FAQResponse, tags=["admin"])
def create_faq(body: FAQCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    faq = FAQ(**body.model_dump())
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq

@app.put("/admin/faqs/{faq_id}", response_model=FAQResponse, tags=["admin"])
def update_faq(faq_id: int, body: FAQUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    faq = db.get(FAQ, faq_id)
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(faq, key, value)
        
    db.commit()
    db.refresh(faq)
    return faq

@app.delete("/admin/faqs/{faq_id}", tags=["admin"])
def delete_faq(faq_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    faq = db.get(FAQ, faq_id)
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    db.delete(faq)
    db.commit()
    return {"message": "FAQ deleted successfully"}

@app.post("/admin/faqs/reorder", tags=["admin"])
def reorder_faqs(body: FAQReorderRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    for item in body.items:
        db.execute(text("UPDATE faqs SET display_order = :order WHERE id = :id"), {"order": item.display_order, "id": item.id})
    db.commit()
    return {"message": "FAQs reordered successfully"}

@app.get("/admin/faqs/suggested", tags=["admin"])
def get_suggested_faqs(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    # Find top queries with high confidence that are not already in FAQs (simple check)
    suggested = (
        db.query(
            QueryLog.normalized_query,
            func.count(QueryLog.id).label("count"),
            func.max(QueryLog.query).label("example_query"),
            func.max(QueryLog.answer).label("example_answer")
        )
        .filter(QueryLog.confidence == "high")
        .group_by(QueryLog.normalized_query)
        .having(func.count(QueryLog.id) >= 2)
        .order_by(func.count(QueryLog.id).desc())
        .limit(10)
        .all()
    )
    
    # Filter out ones that match existing FAQs
    existing_questions = [f.question.lower() for f in db.query(FAQ).all()]
    
    results = []
    for row in suggested:
        if row.example_query.lower() not in existing_questions:
            results.append({
                "query": row.example_query,
                "answer": row.example_answer,
                "count": row.count
            })
            
    return results

@app.post("/admin/faqs/generate-from-sources", tags=["admin"])
async def generate_faqs_from_sources(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """
    Bulk auto-generates FAQs from all 'completed' sources using Groq.
    Yields progress as SSE.
    """
    groq_client = request.app.state.groq_client
    
    # Get all completed sources
    sources = db.query(Source).filter(Source.status == "completed").all()
    
    if not sources:
        async def empty_stream():
            yield f"data: {json.dumps({'status': 'error', 'message': 'No completed sources found'})}\n\n"
        return StreamingResponse(empty_stream(), media_type="text/event-stream")
        
    async def event_stream():
        total = len(sources)
        yield f"data: {json.dumps({'status': 'starting', 'total': total, 'progress': 0})}\n\n"
        
        with SessionLocal() as session:
            for i, source in enumerate(sources):
                yield f"data: {json.dumps({'status': 'generating', 'progress': i, 'total': total, 'source_title': source.title})}\n\n"
                
                # Get top chunks
                chunks = session.query(Chunk).filter(Chunk.source_id == source.id).limit(10).all()
                if not chunks:
                    continue
                    
                combined_text = "\n\n".join([c.chunk_text for c in chunks])
                combined_text = combined_text[:12000] # Fit in context window
                
                prompt = (
                    "Given this ERP documentation content, generate 2-3 frequently-asked-question style Q&A pairs "
                    "that a real user of this software would naturally ask. Questions should be short and practical. "
                    "Answers should be concise (2-4 sentences), based ONLY on the given content. "
                    "Return EXACTLY as a JSON array of objects with 'question' and 'answer' keys. "
                    "Do not include any markdown formatting like ```json or any other text.\n\n"
                    f"CONTENT:\n{combined_text}"
                )
                
                try:
                    response = groq_client.chat.completions.create(
                        model="qwen/qwen3.6-27b",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2,
                        max_tokens=1024
                    )
                    
                    raw_text = response.choices[0].message.content.strip()
                    # Strip markdown if present
                    if raw_text.startswith("```json"):
                        raw_text = raw_text[7:]
                    if raw_text.startswith("```"):
                        raw_text = raw_text[3:]
                    if raw_text.endswith("```"):
                        raw_text = raw_text[:-3]
                    
                    qa_pairs = json.loads(raw_text.strip())
                    
                    # Guess category
                    cat = "General"
                    title_lower = source.title.lower() if source.title else ""
                    if "fee" in title_lower or "pay" in title_lower: cat = "Fees"
                    elif "transport" in title_lower or "bus" in title_lower: cat = "Transport"
                    elif "admission" in title_lower or "enroll" in title_lower: cat = "Admissions"
                    elif "payroll" in title_lower or "salary" in title_lower: cat = "Payroll"
                    
                    for pair in qa_pairs:
                        if "question" in pair and "answer" in pair:
                            new_faq = FAQ(
                                question=pair["question"],
                                answer=pair["answer"],
                                category=cat,
                                linked_source_id=source.id,
                                is_published=False,
                                display_order=999 # Append to end
                            )
                            session.add(new_faq)
                    session.commit()
                except Exception as e:
                    logger.error(f"Error generating FAQ for source {source.id}: {e}")
                    session.rollback()
                    continue
                    
        yield f"data: {json.dumps({'status': 'completed', 'total': total, 'progress': total})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/admin/faqs/publish-all", tags=["admin"])
def publish_all_faqs(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """
    Sets is_published=True for all draft FAQs.
    """
    drafts = db.query(FAQ).filter(FAQ.is_published == False).all()
    count = len(drafts)
    for draft in drafts:
        draft.is_published = True
    db.commit()
    return {"status": "success", "published_count": count}

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
    t_start = time.perf_counter()

    # 1. Encode query once — reused for both cache lookup and vector search
    query_embedding = embedder.encode(body.query)

    # 2. Semantic cache lookup (pgvector cosine similarity, TTL-filtered)
    cache_cutoff = datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)
    cache_sql = text("""
        SELECT id, query_text, answer_text, sources_json, confidence,
               1 - (query_embedding <=> CAST(:emb AS vector)) AS similarity
        FROM query_cache
        WHERE created_at >= :cutoff
        ORDER BY query_embedding <=> CAST(:emb AS vector)
        LIMIT 1
    """)
    cache_row = db.execute(cache_sql, {
        "emb": str(query_embedding.tolist()),
        "cutoff": cache_cutoff,
    }).fetchone()

    is_cache_hit = False
    if cache_row and cache_row.similarity >= CACHE_SIMILARITY_THRESHOLD:
        # ── CACHE HIT ─────────────────────────────────────────────────────
        is_cache_hit = True
        answer = cache_row.answer_text
        confidence = cache_row.confidence or "medium"
        source_metas = []
        if cache_row.sources_json:
            try:
                source_metas = [SourceMetadata(**s) for s in json.loads(cache_row.sources_json)]
            except Exception:
                pass

        # Update hit_count and last_hit_at
        db.execute(
            text("UPDATE query_cache SET hit_count = hit_count + 1, last_hit_at = NOW() WHERE id = :cid"),
            {"cid": cache_row.id}
        )

        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        logger.info(
            "CACHE HIT (sim=%.4f) for query: '%s' — %dms",
            cache_row.similarity, body.query[:80], elapsed_ms
        )

        # Log to QueryLog
        normalized = re.sub(r'\s+', ' ', body.query.lower().strip())
        log_entry = QueryLog(
            user_id=None,
            query=body.query,
            answer=answer,
            sources_used=cache_row.sources_json if cache_row.sources_json else "[]",
            confidence=confidence,
            normalized_query=normalized,
            cached=True,
            response_time_ms=elapsed_ms,
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)

        source_ids = [s.id for s in source_metas]
        # Only show system paths when the answer is relevant (not low confidence)
        system_paths = get_system_paths_for_sources(db, source_ids) if confidence != "low" else []

        return QueryResponse(
            answer=answer,
            confidence=confidence,
            sources=source_metas,
            query_id=log_entry.id,
            cached=True,
            response_time_ms=elapsed_ms,
            system_paths=system_paths,
        )

    # ── CACHE MISS — full RAG pipeline ────────────────────────────────────
    vec_results = search_vectors(body.query, db, embedder, k=20, query_embedding=query_embedding)
    kw_results = search_keywords(body.query, db, k=20)
    merged = merge_results(vec_results, kw_results, top_k=5)

    merged_source_ids = list(set([chunk["source_id"] for chunk in merged]))
    system_paths = get_system_paths_for_sources(db, merged_source_ids)

    gen = generate_answer(body.query, merged, groq_client, system_paths=system_paths)
    confidence = determine_confidence(gen["answer"])

    # Resolve source metadata for display
    source_metas = []
    if gen["sources_used"]:
        sources = db.query(Source).filter(Source.id.in_(gen["sources_used"])).all()
        source_metas = [SourceMetadata(id=s.id, title=s.title or f"Source {s.id}") for s in sources]

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)

    # Validate answer before caching to prevent cache poisoning
    answer_text = gen.get("answer", "").strip()
    is_valid_answer = (
        bool(answer_text) and
        answer_text != "An error occurred while generating the answer." and
        not answer_text.startswith("An error occurred")
    )

    if is_valid_answer:
        # Store in cache for future queries
        sources_json_str = json.dumps([{"id": s.id, "title": s.title} for s in source_metas])
        cache_entry = QueryCache(
            query_text=body.query,
            query_embedding=query_embedding.tolist(),
            answer_text=gen["answer"],
            sources_json=sources_json_str,
            confidence=confidence,
            hit_count=0,
        )
        db.add(cache_entry)

    normalized = re.sub(r'\s+', ' ', body.query.lower().strip())

    log_entry = QueryLog(
        user_id=None,
        query=body.query,
        answer=gen["answer"],
        sources_used=json.dumps(gen["sources_used"]),
        confidence=confidence,
        normalized_query=normalized,
        cached=False,
        response_time_ms=elapsed_ms,
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)

    logger.info(
        "CACHE MISS for query: '%s' — %dms (stored in cache)",
        body.query[:80], elapsed_ms
    )

    source_ids = [s.id for s in source_metas]
    # Only show system paths when the answer is relevant (not low confidence)
    system_paths = get_system_paths_for_sources(db, source_ids) if confidence != "low" else []

    return QueryResponse(
        answer=gen["answer"],
        confidence=confidence,
        sources=source_metas,
        query_id=log_entry.id,
        cached=False,
        response_time_ms=elapsed_ms,
        system_paths=system_paths,
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


@app.get("/admin/insights", tags=["admin"])
def get_insights(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    frequent_gaps_query = (
        db.query(
            QueryLog.normalized_query,
            func.count(QueryLog.id).label("count"),
            func.max(QueryLog.created_at).label("last_asked"),
            func.max(QueryLog.query).label("example_query")
        )
        .filter(QueryLog.confidence == "low")
        .group_by(QueryLog.normalized_query)
        .having(func.count(QueryLog.id) >= 2)
        .order_by(func.count(QueryLog.id).desc())
        .limit(20)
        .all()
    )

    frequent_gaps = [
        {
            "query": row.example_query,
            "count": row.count,
            "last_asked": row.last_asked,
            "confidence": "low"
        }
        for row in frequent_gaps_query
    ]

    rare_questions_query = (
        db.query(
            QueryLog.normalized_query,
            func.count(QueryLog.id).label("count"),
            func.max(QueryLog.created_at).label("last_asked"),
            func.max(QueryLog.query).label("example_query"),
            func.max(QueryLog.confidence).label("confidence")
        )
        .group_by(QueryLog.normalized_query)
        .having(func.count(QueryLog.id) == 1)
        .order_by(func.max(QueryLog.created_at).desc())
        .limit(30)
        .all()
    )

    rare_questions = [
        {
            "query": row.example_query,
            "count": row.count,
            "last_asked": row.last_asked,
            "confidence": row.confidence
        }
        for row in rare_questions_query
    ]

    return {
        "frequent_gaps": frequent_gaps,
        "rare_questions": rare_questions
    }


@app.get("/admin/analytics", tags=["admin"])
def get_analytics(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from sqlalchemy import text, desc
    from collections import Counter
    import datetime

    now = datetime.datetime.now(timezone.utc)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = start_of_today - datetime.timedelta(days=start_of_today.weekday())
    last_14_days = start_of_today - datetime.timedelta(days=14)

    # 1. Top Stat Cards
    total_queries = db.query(QueryLog).count()
    queries_today = db.query(QueryLog).filter(QueryLog.created_at >= start_of_today).count()
    queries_this_week = db.query(QueryLog).filter(QueryLog.created_at >= start_of_week).count()
    
    high_conf = db.query(QueryLog).filter(QueryLog.confidence == "high").count()
    avg_confidence_rate = (high_conf / total_queries * 100) if total_queries > 0 else 0

    # 2. Usage Trend (last 14 days)
    # Using PostgreSQL cast to DATE
    usage_trend_raw = db.query(
        func.date(QueryLog.created_at).label("d"), 
        func.count(QueryLog.id)
    ).filter(QueryLog.created_at >= last_14_days).group_by(func.date(QueryLog.created_at)).all()
    
    usage_trend = [{"date": str(row[0]), "count": row[1]} for row in usage_trend_raw]

    # 3. Top Questions
    top_questions_raw = db.query(
        QueryLog.normalized_query, 
        func.count(QueryLog.id).label("c"),
        func.max(QueryLog.query).label("q")
    ).group_by(QueryLog.normalized_query).order_by(desc("c")).limit(10).all()
    
    top_questions = [{"query": r.q, "count": r.c} for r in top_questions_raw]

    # 4. Feedback Stats
    feedback_total = db.query(QueryLog).filter(QueryLog.feedback.isnot(None)).count()
    feedback_up = db.query(QueryLog).filter(QueryLog.feedback == "up").count()
    feedback_down = db.query(QueryLog).filter(QueryLog.feedback == "down").count()
    
    most_disliked_raw = db.query(
        QueryLog.normalized_query,
        func.count(QueryLog.id).label("c"),
        func.max(QueryLog.query).label("q")
    ).filter(QueryLog.feedback == "down").group_by(QueryLog.normalized_query).order_by(desc("c")).limit(5).all()
    
    most_disliked = [{"query": r.q, "count": r.c} for r in most_disliked_raw]

    # 5. Confidence Distribution
    conf_dist_raw = db.query(QueryLog.confidence, func.count(QueryLog.id)).group_by(QueryLog.confidence).all()
    conf_dist = {row[0]: row[1] for row in conf_dist_raw}

    # 6. Peak Usage Time (Hour of day)
    peak_usage_raw = db.query(
        func.extract('hour', QueryLog.created_at).label("h"), 
        func.count(QueryLog.id)
    ).group_by(func.extract('hour', QueryLog.created_at)).all()
    
    peak_usage = [{"hour": int(r[0]), "count": r[1]} for r in peak_usage_raw if r[0] is not None]

    # 7. Most-Cited Sources
    # Read all sources_used (JSON string of arrays) and aggregate in Python
    all_sources = db.query(QueryLog.sources_used).filter(QueryLog.sources_used.isnot(None)).all()
    source_counter = Counter()
    for (su,) in all_sources:
        try:
            ids = json.loads(su)
            if isinstance(ids, list):
                source_counter.update(ids)
        except Exception:
            pass
            
    top_source_ids = [s_id for s_id, _ in source_counter.most_common(10)]
    source_titles = {}
    if top_source_ids:
        sources = db.query(Source.id, Source.title).filter(Source.id.in_(top_source_ids)).all()
        source_titles = {s.id: s.title for s in sources}
        
    most_cited_sources = [
        {"id": s_id, "title": source_titles.get(s_id, f"Unknown Source {s_id}"), "count": count}
        for s_id, count in source_counter.most_common(10)
    ]

    # 8. Semantic Cache Stats
    cached_queries = db.query(QueryLog).filter(QueryLog.cached == True).count()
    fresh_queries = total_queries - cached_queries
    cache_hit_rate = round((cached_queries / total_queries * 100), 1) if total_queries > 0 else 0

    avg_cached_time = db.query(func.avg(QueryLog.response_time_ms)).filter(
        QueryLog.cached == True, QueryLog.response_time_ms > 0
    ).scalar() or 0
    avg_fresh_time = db.query(func.avg(QueryLog.response_time_ms)).filter(
        QueryLog.cached == False, QueryLog.response_time_ms > 0
    ).scalar() or 0

    return {
        "top_stats": {
            "total_queries": total_queries,
            "queries_today": queries_today,
            "queries_this_week": queries_this_week,
            "avg_confidence_rate": round(avg_confidence_rate, 1)
        },
        "usage_trend": usage_trend,
        "top_questions": top_questions,
        "feedback_stats": {
            "total": feedback_total,
            "up": feedback_up,
            "down": feedback_down,
            "most_disliked": most_disliked
        },
        "confidence_distribution": conf_dist,
        "peak_usage_time": peak_usage,
        "most_cited_sources": most_cited_sources,
        "cache_stats": {
            "hit_rate": cache_hit_rate,
            "cached_queries": cached_queries,
            "fresh_queries": fresh_queries,
            "avg_cached_time_ms": round(float(avg_cached_time)),
            "avg_fresh_time_ms": round(float(avg_fresh_time)),
        }
    }


@app.get("/admin/cache", tags=["admin"])
def get_cached_queries(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from db.models import QueryCache
    cached = db.query(QueryCache).order_by(QueryCache.hit_count.desc(), QueryCache.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "query_text": c.query_text,
            "answer_text": c.answer_text,
            "confidence": c.confidence,
            "hit_count": c.hit_count,
            "created_at": c.created_at,
            "last_hit_at": c.last_hit_at,
        }
        for c in cached
    ]


@app.post("/admin/cache/clear", tags=["admin"])
def clear_semantic_cache(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from db.models import QueryCache
    flushed = db.query(QueryCache).delete()
    db.commit()
    logger.info("Admin manually flushed %d semantic cache entries", flushed)
    return {"message": "Semantic cache cleared successfully", "count": flushed}


# ── Page routing ──────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return RedirectResponse(url="/static/admin.html")


# Mount static LAST so API routes always take priority
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
