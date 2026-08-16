---
title: OD Assist
emoji: ⚡
colorFrom: yellow
colorTo: orange
sdk: docker
pinned: false
app_port: 7860
---

# OD Assist

A RAG (Retrieval-Augmented Generation) chatbot for Okie Dokie organizational knowledge.

## Features
- Ingest PDFs, Google Drive docs/videos, and raw text
- Hybrid retrieval: pgvector cosine search + BM25 keyword search
- Groq LLM (llama-3.3-70b-versatile) for answer generation
- Groq Whisper (whisper-large-v3) for video transcription
- Admin panel for source management
- User chat interface with cited answers and feedback

## Stack
- **Backend**: FastAPI + SQLAlchemy
- **Vectors**: pgvector in Neon Postgres
- **Embeddings**: sentence-transformers (bge-small-en-v1.5)
- **LLM**: Groq

## Setup & Deployment Checklist

### 1. Database Setup
Create a free project on Neon Postgres (neon.tech). Use the **pooled** connection string.
**Important:** Ensure the vector extension is enabled by running `CREATE EXTENSION IF NOT EXISTS vector;` in the Neon SQL Editor to verify it works safely before starting the app.

### 2. API Keys
Create a free account at console.groq.com. Generate an API key. This single key is used for both Whisper transcription and LLM generation.

### 3. Environment Variables
Copy `.env.example` to `.env` and fill it out:
- `DATABASE_URL` (Neon Postgres connection string)
- `GROQ_API_KEY`
- `JWT_SECRET` (generate a random 32+ character string)
- `ADMIN_PASSWORD` (default is OkieDokie@123)
*Make sure `.env` is listed in your `.gitignore` so secrets are never committed.*

### 4. Install System Dependencies
Install `ffmpeg` (required for video audio extraction):
- Windows: `choco install ffmpeg` or `winget install ffmpeg` or download manually.
- Verify installation by opening a new terminal and running `ffmpeg -version`.

### 5. Install Python Dependencies
Run `pip install -r requirements.txt`.
*(Note: If version conflict errors arise regarding `bcrypt` or `passlib`, ensure `bcrypt==4.0.1` is pinned.)*

### 6. Seed Admin User
Run `python seed_admin.py`. This securely creates the `odadmin` user using the password defined in the `.env` file. This script is idempotent and safe to re-run.

### 7. Local Testing (Crucial Step)
Start the local server:
```bash
uvicorn api.main:app --reload --port 7860
```
- Go to `http://localhost:7860/admin`, log in, upload a short PDF, and wait for the status to show "completed".
- Go to `http://localhost:7860/`, ask a question as a user, and verify you get an answer with citations.
**Do not deploy to Hugging Face Spaces until this local end-to-end test passes.**

### 8. Deploy to Hugging Face Spaces
Push the repository to an HF Space using the Docker SDK.
- Navigate to your Space **Settings > Secrets**.
- Add the following secrets: `DATABASE_URL`, `GROQ_API_KEY`, `JWT_SECRET`, `ADMIN_PASSWORD`. (Never hardcode these in code).
- Allow the initial build time to complete (it bakes the embedding weights into the image to avoid cold starts).
- Finally, test the live URL to ensure admin ingestion and user chat function normally.
