# ⚡ OD Assist (Okie Dokie Knowledge Portal)

**OD Assist** is an advanced, AI-powered Retrieval-Augmented Generation (RAG) chatbot tailored for organizational knowledge management. It serves as a centralized "brain" that instantly answers staff and student questions by searching through your organization's internal documents, policies, and training materials.

---

## 🎯 The Problem It Solves

Organizations often face fragmented knowledge scattered across policy PDFs, Google Drive Docs, Town Hall recordings, and HR memos. When employees or students have a question (e.g., *"What is the student promotion process?"* or *"How is payroll processed?"*), they either spend hours searching through folders or interrupt colleagues. 

**OD Assist solves this by:**
1. **Unifying Data**: Providing a simple Admin Portal to ingest PDFs, Google Drive links, Video Recordings, and Raw Text into a single database.
2. **Instant, Accurate Answers**: Users can ask questions in natural language and get immediate answers.
3. **Eliminating AI Hallucinations**: By strictly using the RAG architecture, the AI is constrained to answer *only* using the provided organizational documents.
4. **Transparent Citations**: Every answer comes with exact source citations, allowing users to verify the information.

---

## 🛠️ Tech Stack & Architecture

OD Assist is built for speed, accuracy, and ease of deployment. 

### Backend & Core Logic
* **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python) — Ensures high performance and asynchronous request handling.
* **Database**: [PostgreSQL (Neon Serverless)](https://neon.tech/) — Cloud-native Postgres.
* **Vector Store**: `pgvector` extension for efficient cosine-similarity search.
* **ORM**: SQLAlchemy.

### AI & Machine Learning
* **Embeddings**: `sentence-transformers` (`BAAI/bge-small-en-v1.5`) — Runs locally for fast, cost-effective document chunk vectorization.
* **LLM Engine**: [Groq API](https://groq.com/) (`llama-3.3-70b-versatile`) — Provides blazing-fast inference for answer generation.
* **Audio Transcription**: Groq Whisper API (`whisper-large-v3`) — Automatically extracts and transcribes audio from Google Drive video links.
* **Search Engine**: **Hybrid Search** — Combines dense Vector Search with sparse Keyword Search (BM25) to ensure the highest retrieval accuracy.

### Frontend
* **UI**: Vanilla HTML, CSS (Design Tokens, CSS Variables), and JavaScript.
* **Design**: Fully responsive, glassmorphism aesthetics, integrated Dark/Light modes, and separate, secure portals for Users and Admins.

---

## ⚙️ How It Works (Implementation Flow)

1. **Ingestion (Admin Portal)**:
   - An authorized Admin securely logs in and uploads a knowledge source (PDF, Google Drive Document, Drive Video, or Raw Text).
2. **Background Processing**:
   - The app fetches and parses the file (extracting text from PDFs, downloading and transcribing Drive Videos via Whisper).
   - The text is chunked into manageable pieces (with overlap to preserve context).
   - The embedding model converts these chunks into dense vector representations.
   - Vectors and metadata are stored in the Neon PostgreSQL database.
3. **Retrieval & Generation (User Portal)**:
   - A user asks a question in the chat interface.
   - The query is vectorized. The system performs a hybrid search to find the top most relevant chunks from the database.
   - The LLM (Llama 3 via Groq) receives the user's question alongside the retrieved context chunks and generates a precise answer.
   - The UI displays the answer, a confidence score, and clickable source citations.

---

## 🚀 Setup & Deployment Guide

### 1. Database Setup
1. Create a free project on [Neon](https://neon.tech/).
2. Copy the **pooled** connection string.
3. **Crucial**: Open the Neon SQL Editor and run `CREATE EXTENSION IF NOT EXISTS vector;` to enable the pgvector extension.

### 2. API Keys
1. Create a free account at [Groq Console](https://console.groq.com/).
2. Generate an API key. This single key handles both the Llama 3 generation and Whisper transcription.

### 3. Environment Variables
Create a `.env` file in the root directory (use `.env.example` as a template):
```env
DATABASE_URL=postgresql://user:pass@ep-cool-db.neon.tech/neondb?sslmode=require
GROQ_API_KEY=gsk_your_api_key_here
JWT_SECRET=generate_a_random_secure_string
ADMIN_PASSWORD=YourSecurePassword123
ADMIN_BASIC_AUTH_USER=admin
ADMIN_BASIC_AUTH_PASS=YourSecureAdminAuthPass
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
Run the admin seeder to create your initial admin account (using credentials from `.env`):
```bash
python seed_admin.py
```

### 6. Run Locally
Start the FastAPI server:
```bash
uvicorn api.main:app --reload --port 7860
```
- Navigate to `http://localhost:7860/` to see the Landing Page.
- Choose **Admin Portal**, log in, and ingest your first PDF.
- Choose **User Portal** to test asking questions against the uploaded PDF.

### 7. Deployment (Render Free Tier)
This app is fully compatible with Render's Docker environment.
1. Push this repository to GitHub.
2. Go to [Render](https://render.com/) and create a new **Web Service**.
3. Connect your GitHub repo, set Environment to **Docker**, and choose the Free tier.
4. Add all environment variables from your `.env` file into Render's dashboard.
5. Deploy!
