FROM python:3.11-slim

# System dependencies: ffmpeg for audio extraction/splitting
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only torch first — HF Spaces free tier has no GPU,
# so the default CUDA-enabled torch build would waste ~2-3GB of
# unnecessary downloads and slow down every build.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake embedding model into the image at build time.
# This downloads ~130MB of model weights during docker build,
# so the first request never waits for a model download.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

# Copy application code
COPY . .

# Create temp directory for ingestion files
RUN mkdir -p temp_files

# Hugging Face Spaces runs on port 7860
EXPOSE 7860

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]
