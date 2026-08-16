"""
Orchestrates the full ingestion pipeline for a single source.
Called as a FastAPI BackgroundTask — creates its OWN DB session internally
(the request-scoped session is already closed by the time this runs).

Flow:
  extract raw text  →  preprocess  →  chunk  →  enrich  →  embed+store  →  update status
"""

import logging
import os

from db.db import SessionLocal
from db.models import Chunk, Source
from ingestion.chunker import get_chunks
from ingestion.drive_handler import fetch_from_drive
from ingestion.embedder import embed_chunks
from ingestion.enricher import enrich_chunk
from ingestion.pdf_handler import extract_text_from_pdf
from ingestion.preprocessor import clean_text
from ingestion.transcriber import extract_and_transcribe_video

logger = logging.getLogger(__name__)

TEMP_DIR = "temp_files"


def process_source(
    source_id: int,
    embedder,
    groq_client,
):
    """
    Background-safe ingestion runner.
    Opens and closes its own DB session — never shares the request session.
    """
    db = SessionLocal()
    temp_file_to_clean = None

    try:
        source = db.get(Source, source_id)
        if not source:
            logger.error("process_source: source_id=%d not found", source_id)
            return

        source.status = "processing"
        db.commit()

        extracted_text = _extract_text(source, groq_client)
        if not extracted_text or not extracted_text.strip():
            raise ValueError("No readable text extracted from source.")

        cleaned = clean_text(extracted_text)
        chunks_text = get_chunks(cleaned)

        if not chunks_text:
            raise ValueError("Chunking produced zero chunks — document may be empty.")

        logger.info(
            "source_id=%d: %d chunks generated, starting enrich+embed",
            source_id, len(chunks_text)
        )

        embeddings = embed_chunks(chunks_text, embedder)

        db_chunks = []
        for i, text_chunk in enumerate(chunks_text):
            summary = enrich_chunk(text_chunk, groq_client)
            db_chunks.append(
                Chunk(
                    source_id=source.id,
                    chunk_text=text_chunk,
                    chunk_summary=summary,
                    embedding=embeddings[i],
                )
            )

        db.add_all(db_chunks)
        source.chunk_count = len(db_chunks)
        source.status = "completed"
        source.error_message = None
        db.commit()
        logger.info("source_id=%d ingestion completed (%d chunks)", source_id, len(db_chunks))

    except Exception as exc:
        logger.exception("process_source failed for source_id=%d", source_id)
        try:
            source = db.get(Source, source_id)
            if source:
                source.status = "failed"
                source.error_message = str(exc)[:500]
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
        _cleanup(temp_file_to_clean)


def _extract_text(source: Source, groq_client) -> str:
    """Route extraction based on source_type."""
    if source.source_type == "raw_text":
        # raw_text sources: text was stored in source_url field at ingest time
        return source.source_url or ""

    if source.source_type == "pdf":
        return extract_text_from_pdf(source.source_url)

    if source.source_type in ("drive_doc", "drive_video"):
        os.makedirs(TEMP_DIR, exist_ok=True)
        local_path, detected_type = fetch_from_drive(source.source_url, TEMP_DIR)
        try:
            # Respect user-specified type; fall back to auto-detected
            resolved_type = source.source_type if source.source_type != "drive_doc" else detected_type
            if resolved_type == "drive_video":
                return extract_and_transcribe_video(local_path, groq_client)
            else:
                # drive_doc: try PDF extraction, fallback to plain text read
                try:
                    return extract_text_from_pdf(local_path)
                except Exception:
                    with open(local_path, "r", encoding="utf-8", errors="replace") as f:
                        return f.read()
        finally:
            if local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass

    raise ValueError(f"Unknown source_type: {source.source_type!r}")


def _cleanup(path):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
