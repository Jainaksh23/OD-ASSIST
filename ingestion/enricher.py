from groq import Groq

def enrich_chunk(chunk_text: str, client: Groq) -> str:
    """
    Uses Groq llama-3.3-70b-versatile to generate a one-line summary 
    of the chunk for BM25 keyword search enhancement.
    """
    prompt = f"Summarize the following text in exactly one short sentence. Do not add any introductory or concluding remarks, just output the summary:\n\n{chunk_text}"
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.0
        )
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        print(f"Error enriching chunk: {e}")
        return ""
