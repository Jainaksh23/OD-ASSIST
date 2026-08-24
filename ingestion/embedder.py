import numpy as np
import gc

def embed_chunks(chunks: list[str], embedder) -> list[list[float]]:
    """
    Embeds a list of text chunks using the provided sentence-transformers model.
    """
    # Use a small batch_size to prevent PyTorch from allocating large intermediate tensors
    embeddings = embedder.encode(chunks, batch_size=4)
    res = [embedding.tolist() for embedding in embeddings]
    
    # Force memory release for 512MB RAM limits
    del embeddings
    gc.collect()
    
    return res
