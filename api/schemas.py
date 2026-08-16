from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str

class IngestRequest(BaseModel):
    title: str
    source_type: str # 'pdf', 'drive_doc', 'drive_video', 'raw_text'
    source_url: str  # For pdf/raw_text this might just be a local path or text block

class SourceResponse(BaseModel):
    id: int
    title: str
    source_type: str
    status: str
    error_message: Optional[str] = None
    chunk_count: int
    created_at: datetime

    class Config:
        from_attributes = True

class BulkIngestRequest(BaseModel):
    bulk_text: str

class UserCreate(BaseModel):
    username: str
    password: str
    role: str

class UserResponse(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        from_attributes = True

class QueryRequest(BaseModel):
    query: str

class SourceMetadata(BaseModel):
    id: int
    title: str

class QueryResponse(BaseModel):
    answer: str
    confidence: str
    sources: List[SourceMetadata]
    query_id: int

class FeedbackRequest(BaseModel):
    query_id: int
    feedback: str # 'up' or 'down'
