import numpy as np

def embed_chunks(chunks: list[str], embedder) -> list[list[float]]:
    """
    Embeds a list of text chunks using the provided sentence-transformers model.
    """
    # model.encode returns a numpy array, we convert to list of floats for pgvector
    embeddings = embedder.encode(chunks)
    return [embedding.tolist() for embedding in embeddings]
