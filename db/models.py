"""
models.py — SQLAlchemy ORM models for OD Assist.
Tables: users, sources, chunks (pgvector), query_logs
"""

from sqlalchemy import Column, ForeignKey, Integer, String, Text, TIMESTAMP
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

    ingester = relationship("User", back_populates="sources_ingested")
    chunks = relationship(
        "Chunk", back_populates="source",
        cascade="all, delete-orphan", lazy="select"
    )


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
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="query_logs")
