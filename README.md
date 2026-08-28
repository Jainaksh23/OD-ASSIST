# ⚡ OD Assist (Okie Dokie Knowledge Portal)

**OD Assist** is an enterprise-grade, AI-powered Retrieval-Augmented Generation (RAG) system tailored for organizational knowledge management. It serves as a centralized "brain" that instantly answers staff and student questions by securely searching through internal documents, policies, and training materials.

---

## 🎯 The Problem It Solves

Organizations often face fragmented knowledge scattered across policy PDFs, Google Drive Docs, Town Hall recordings, and HR memos. When employees or students have a question, they either spend hours searching through folders or interrupt colleagues. 

**OD Assist solves this by:**
1. **Unifying Data**: Providing a simple Admin Portal to ingest PDFs, Google Drive links, Video Recordings, and Raw Text into a single database.
2. **Instant, Accurate Answers**: Users can ask questions in natural language and get immediate, context-aware answers.
3. **Eliminating AI Hallucinations**: By strictly using the RAG architecture, the AI is constrained to answer *only* using the provided organizational documents.
4. **Transparent Citations & Workflows**: Every answer comes with exact source citations, and when a step-by-step process is detected, it renders interactive workflow diagrams (System Paths).

---

## 🏗️ System Architecture

OD Assist uses a modern, serverless-ready architecture optimized for speed, precision, and low operational costs.

```mermaid
graph TD
    subgraph Frontend
        U[User Chat Interface]
        A[Admin Dashboard]
    end

    subgraph Backend - FastAPI
        API[FastAPI Router]
        Auth[JWT Authentication]
        Cache[Semantic Query Cache]
        Ingest[Ingestion Pipeline]
        Search[Hybrid Search Engine]
    end

    subgraph Database - Neon Serverless
        PG[(PostgreSQL)]
        VEC[pgvector Extension]
    end

    subgraph AI Services
        Emb[Sentence Transformers<br>BAAI/bge-small-en-v1.5]
        Groq[Groq Cloud API]
        LLM[Qwen 3.6 27B Reasoning]
        Whisper[Whisper Large V3]
    end

    U --> API
    A --> Auth --> API
    API --> Cache
    Cache -- Miss --> Search
    Search --> PG
    Search --> VEC
    Search --> Groq
    Groq --> LLM
    API --> Ingest
    Ingest --> Emb
    Ingest --> Whisper
    Emb --> VEC
```

---

## ⚙️ Core Data Pipelines

### 1. The Ingestion Pipeline
When an administrator uploads a document, the system processes it intelligently to extract and index the maximum amount of contextual information.

```mermaid
flowchart TD
    Start[Admin Uploads File] --> Router{File Type?}
    
    Router -- Google Drive / Text --> TextExtractor[Extract Raw Text]
    Router -- Video / Audio --> AudioExt[Extract Audio] --> Whisper[Groq Whisper Transcription]
    Router -- PDF Document --> PDFReader{Is Scanned / Image-heavy?}
    
    PDFReader -- No --> PyPDF[Standard Text Extraction]
    PDFReader -- Yes --> VisionAPI[Groq Vision API Fallback]
    
    TextExtractor --> Chunker
    Whisper --> Chunker
    PyPDF --> Chunker
    VisionAPI --> Chunker
    
    Chunker[LangChain Recursive Splitter<br>600 chars, 90 overlap] --> Enricher
    
    Enricher[AI Semantic Summarizer<br>Generates 1-sentence summary per chunk] --> Embedder
    
    Embedder[Local Embedding Model<br>BAAI/bge-small-en] --> DB[(PostgreSQL + pgvector)]
```

### 2. The Retrieval & Generation Pipeline
When a user asks a question, OD Assist ensures low-latency and highly relevant answers using Semantic Caching and Hybrid Search.

```mermaid
sequenceDiagram
    participant User
    participant System as OD Assist Backend
    participant DB as PostgreSQL
    participant Groq as Groq AI (Qwen)
    
    User->>System: "How to add alumni?"
    System->>System: Encode query to Vector
    
    System->>DB: Check Semantic Cache (Similarity > 0.95)
    alt Cache Hit
        DB-->>System: Return cached answer
        System-->>User: Sub-100ms Response
    else Cache Miss
        System->>Groq: Translate query if non-English
        Groq-->>System: English Query
        
        System->>DB: 1. Vector Search (pgvector)
        System->>DB: 2. Keyword Search (BM25)
        System->>DB: 3. FAQ Exact Match Search
        
        DB-->>System: Top relevant chunks
        
        System->>Groq: Prompt LLM with Chunks + Query
        Groq-->>System: Generated Answer (with filtered reasoning)
        
        System->>DB: Save to Semantic Cache
        System-->>User: Return Answer & Citations
    end
```

---

## ✨ Key Features & Technical Highlights

* **Reasoning AI Model**: Powered by Groq's blazing-fast inference using `qwen/qwen3.6-27b`. The system parses and filters the model's complex `<think>` reasoning blocks to provide users with direct, highly-intelligent answers.
* **Hybrid Search (Dense + Sparse)**: Combines standard vector similarity search with BM25 keyword search to ensure both contextual meaning and exact technical terms are retrieved accurately.
* **Intelligent Vision Fallback**: Standard PDF extractors fail on scanned documents and infographics. OD Assist automatically detects sparse text and routes image-heavy pages through a Vision LLM for perfect OCR and structural transcription.
* **Semantic Query Caching**: To save API costs and reduce latency, queries are matched against a vector cache. Semantically identical questions (e.g., "What is the fee?" vs "How much is the fee?") instantly return cached results in <100ms.
* **Multilingual Translation Routing**: Hindi and Hinglish queries are instantly translated to English under-the-hood before searching the database, drastically improving retrieval recall for non-English users.
* **Auto-FAQ Generation**: Admins can automatically parse ingested documents to generate interactive Frequently Asked Questions using AI.
* **System Paths**: Dynamic visual navigation flows (rounded boxes and arrows) linked to specific knowledge sources, which automatically render in the user's chatbot interface when relevant topics are queried.

---

## 🛠️ Tech Stack

* **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Python)
* **Database**: [PostgreSQL (Neon Serverless)](https://neon.tech/) with `pgvector`
* **AI Engine**: [Groq API](https://groq.com/)
    * *Reasoning/Generation*: `qwen/qwen3.6-27b`
    * *Audio Transcription*: `whisper-large-v3`
* **Embeddings**: `sentence-transformers` (`BAAI/bge-small-en-v1.5`)
* **Chunking**: LangChain `RecursiveCharacterTextSplitter`
* **Document Parsers**: `pypdf`, `pdfplumber`, `PyMuPDF` (fitz)
* **Frontend**: Vanilla HTML, CSS (Glassmorphism, Dark/Light modes), JavaScript

---

## 🚀 Setup & Deployment Guide

### 1. Database Setup
1. Create a free project on [Neon](https://neon.tech/).
2. Copy the **pooled** connection string.
3. Open the Neon SQL Editor and run `CREATE EXTENSION IF NOT EXISTS vector;` to enable the pgvector extension.

### 2. API Keys
1. Create a free account at [Groq Console](https://console.groq.com/).
2. Generate an API key. This single key handles all generation, summarization, and transcription tasks.

### 3. Environment Variables
Create a `.env` file in the root directory (use `.env.example` as a template):
```env
DATABASE_URL=postgresql://user:pass@ep-cool-db.neon.tech/neondb?sslmode=require
GROQ_API_KEY=gsk_your_api_key_here
JWT_SECRET=generate_a_random_secure_string
ADMIN_PASSWORD=YourSecurePassword123
ADMIN_BASIC_AUTH_USER=admin
ADMIN_BASIC_AUTH_PASS=YourSecureAdminAuthPass

# Optional Cache Configuration
CACHE_SIMILARITY_THRESHOLD=0.95
CACHE_TTL_HOURS=48
```

### 4. Install Dependencies
**System Dependencies:**
Install `ffmpeg` (required for video audio extraction):
- Windows: `choco install ffmpeg` or `winget install ffmpeg`.
- Linux: `sudo apt install ffmpeg`
- Verify with `ffmpeg -version`.

**Python Dependencies:**
```bash
pip install -r requirements.txt
```

### 5. Initialize the System
Run the admin seeder to create your initial admin account:
```bash
python scripts/seed_admin.py
```

### 6. Run Locally
Start the FastAPI server:
```bash
uvicorn api.main:app --reload --port 7860
```
- Navigate to `http://localhost:7860/` for the User Panel.
- Navigate to `http://localhost:7860/admin` for the Admin Dashboard.

### 7. Deployment (Render Free Tier)
This app is fully compatible with Render's Docker environment.
1. Push this repository to GitHub.
2. Go to [Render](https://render.com/) and create a new **Web Service**.
3. Connect your GitHub repo, set Environment to **Docker**, and choose the Free tier.
4. Add all environment variables from your `.env` file into Render's dashboard.
5. Deploy!
