SYSTEM_PROMPT = """You are OD Assist, a helpful assistant for OD (Okie Dokie) organizational knowledge.
Answer ONLY from the provided context. Cite source titles inline using square brackets like [Source Title].
If the context is insufficient to answer the question, say exactly: "I don't have enough information to answer this confidently."
Do not make up any information.
"""

def build_prompt(query: str, context_chunks: list[dict]) -> str:
    """
    Builds the user prompt containing the query and retrieved context.
    """
    context_str = ""
    for chunk in context_chunks:
        title = chunk.get("source_title", "Unknown Source")
        text = chunk.get("chunk_text", "")
        context_str += f"Source Title: {title}\nContent: {text}\n\n"
        
    prompt = f"Context information is below.\n---------------------\n{context_str}\n---------------------\n"
    prompt += f"Given the context information and no prior knowledge, answer the query.\nQuery: {query}\nAnswer: "
    
    return prompt
