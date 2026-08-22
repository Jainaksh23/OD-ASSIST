"""
models.py — SQLAlchemy ORM models for OD Assist.
Tables: users, sources, chunks (pgvector), query_logs, query_cache
"""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, TIMESTAMP, Table
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    role = Column(String(20), nullable=False)  # 'admin' | 'user'

    sources_ingested = relationship("Source", back_populates="ingester")
    query_logs = relationship("QueryLog", back_populates="user")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(Text)
    source_type = Column(String(30))  # 'pdf' | 'drive_doc' | 'drive_video' | 'raw_text'
    source_url = Column(Text)         # file path for pdf; drive URL; raw text content for raw_text
    status = Column(String(20), default="processing")  # 'processing' | 'completed' | 'failed'
    error_message = Column(Text)      # populated on failure, null on success
    chunk_count = Column(Integer, default=0)
    ingested_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    ingester = relationship("User", back_populates="sources_ingested")
    chunks = relationship(
        "Chunk", back_populates="source",
        cascade="all, delete-orphan", lazy="select"
    )
    system_paths = relationship("SystemPath", secondary="system_path_sources", back_populates="sources")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(
        Integer,
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_text = Column(Text, nullable=False)
    # Hidden Groq-generated one-liner used only for BM25 enrichment — never shown to users
    chunk_summary = Column(Text)
    # bge-small-en-v1.5 output dimension = 384
    embedding = Column(Vector(384), nullable=False)

    source = relationship("Source", back_populates="chunks")


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    query = Column(Text)
    answer = Column(Text)
    sources_used = Column(Text)   # JSON array of source_ids
    feedback = Column(String(10)) # 'up' | 'down' | None
    confidence = Column(String(20)) # 'high' | 'medium' | 'low'
    normalized_query = Column(Text) # For grouping similar queries
    cached = Column(Boolean, default=False)        # Was this served from semantic cache?
    response_time_ms = Column(Integer, default=0)  # Wall-clock ms for this request
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="query_logs")


class QueryCache(Base):
    """Semantic cache: stores recent query→answer pairs with embeddings
    for fast cosine-similarity lookups via pgvector."""
    __tablename__ = "query_cache"

    id = Column(Integer, primary_key=True, index=True)
    query_text = Column(Text, nullable=False)
    query_embedding = Column(Vector(384), nullable=False)
    answer_text = Column(Text, nullable=False)
    sources_json = Column(Text)        # JSON: [{id, title}, ...]
    confidence = Column(String(20))    # 'high' | 'medium' | 'low'
    hit_count = Column(Integer, default=0)
    last_hit_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


# Association table for many-to-many relationship between SystemPath and Source
system_path_sources = Table(
    "system_path_sources",
    Base.metadata,
    Column("system_path_id", Integer, ForeignKey("system_paths.id", ondelete="CASCADE"), primary_key=True),
    Column("source_id", Integer, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True),
)


class SystemPath(Base):
    __tablename__ = "system_paths"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(Text, nullable=False)
    description = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    steps = relationship("SystemPathStep", back_populates="system_path", cascade="all, delete-orphan")
    sources = relationship("Source", secondary=system_path_sources, back_populates="system_paths")


class SystemPathStep(Base):
    __tablename__ = "system_path_steps"

    id = Column(Integer, primary_key=True, index=True)
    system_path_id = Column(Integer, ForeignKey("system_paths.id", ondelete="CASCADE"), nullable=False)
    step_label = Column(Text, nullable=False)
    step_order = Column(Integer, nullable=False)

    system_path = relationship("SystemPath", back_populates="steps")
