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

class SystemPathSimpleResponse(BaseModel):
    title: str
    description: Optional[str] = None
    steps: List[str]

class QueryResponse(BaseModel):
    answer: str
    confidence: str
    sources: List[SourceMetadata]
    query_id: int
    cached: bool = False
    response_time_ms: int = 0
    system_paths: Optional[List[SystemPathSimpleResponse]] = []

class FeedbackRequest(BaseModel):
    query_id: int
    feedback: str # 'up' or 'down'

class SystemPathStepResponse(BaseModel):
    id: int
    step_label: str
    step_order: int
    
    class Config:
        from_attributes = True

class SystemPathResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    steps: List[SystemPathStepResponse]
    sources: List[SourceMetadata]
    created_at: datetime

    class Config:
        from_attributes = True

class SystemPathCreate(BaseModel):
    title: str
    description: Optional[str] = None
    steps: List[str]
    source_ids: List[int]

class FAQCreate(BaseModel):
    question: str
    answer: str
    category: Optional[str] = None
    display_order: Optional[int] = 0
    linked_source_id: Optional[int] = None
    is_published: Optional[bool] = False

class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    display_order: Optional[int] = None
    linked_source_id: Optional[int] = None
    is_published: Optional[bool] = None

class FAQResponse(BaseModel):
    id: int
    question: str
    answer: str
    category: Optional[str] = None
    display_order: int
    linked_source_id: Optional[int] = None
    is_published: bool
    created_at: datetime

    class Config:
        from_attributes = True

class FAQReorderItem(BaseModel):
    id: int
    display_order: int

class FAQReorderRequest(BaseModel):
    items: List[FAQReorderItem]
