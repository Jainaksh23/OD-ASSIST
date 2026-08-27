import re
# pyrefly: ignore [missing-import]
from groq import Groq
from generation.prompt_template import SYSTEM_PROMPT, build_prompt
from typing import List, Dict, Any

def strip_thinking(text: str) -> str:
    """
    Strips <think>...</think> and <thinking>...</thinking> blocks from the text.
    Handles unclosed tags as well.
    """
    if not text:
        return ""
    
    # Remove closed <think>...</think> or <thinking>...</thinking> blocks
    text = re.sub(r'<(think|thinking)>.*?</\1>', '', text, flags=re.DOTALL)
    
    # Remove unclosed <think> or <thinking> blocks (if cut off by max_tokens)
    text = re.sub(r'<(think|thinking)>.*', '', text, flags=re.DOTALL)
    
    # Clean up whitespace
    text = text.strip()
    
    return text

def generate_answer(query: str, retrieved_chunks: list[dict], client: Groq, system_paths: list[dict] = None, faqs: list[dict] = None) -> dict:
    """
    Calls Groq to generate an answer based on the context, system paths, and FAQs.
    Returns the answer text and the unique source IDs used.
    """

    prompt = build_prompt(query, retrieved_chunks, system_paths, faqs)
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=1024
        )
        raw_answer = response.choices[0].message.content.strip()
        answer = strip_thinking(raw_answer)
        
        if not answer:
            answer = "I don't have enough information to answer this confidently."
        
        # Extract unique source IDs from context chunks and faqs
        sources_used = [chunk["source_id"] for chunk in retrieved_chunks if "source_id" in chunk]
        if faqs:
            sources_used.extend([f["source_id"] for f in faqs if f.get("source_id")])
        
        sources_used = list(set(sources_used))
        
        return {
            "answer": answer,
            "sources_used": sources_used,
            "raw_response": response
        }
    except Exception as e:
        print(f"Error generating answer: {e}")
        return {
            "answer": "An error occurred while generating the answer.",
            "sources_used": [],
            "raw_response": None
        }
