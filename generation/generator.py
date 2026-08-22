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

def generate_answer(query: str, context_chunks: List[Dict], client: Groq) -> Dict[str, Any]:
    """
    Calls Groq to generate an answer based on the context.
    Returns the answer text and the unique source IDs used.
    """
    if not context_chunks:
        return {
            "answer": "I don't have enough information to answer this confidently.",
            "sources_used": [],
            "raw_response": None
        }
        
    prompt = build_prompt(query, context_chunks)
    
    try:
        response = client.chat.completions.create(
            model="qwen/qwen3.6-27b",
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
        
        # Extract unique source IDs from context chunks
        sources_used = list(set([chunk["source_id"] for chunk in context_chunks]))
        
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
