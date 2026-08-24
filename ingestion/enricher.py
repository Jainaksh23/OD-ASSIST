from groq import Groq
from generation.generator import strip_thinking

def enrich_chunk(chunk_text: str, client: Groq) -> str:
    """
    Uses Groq llama3-8b-8192 to generate a one-line summary 
    of the chunk for BM25 keyword search enhancement.
    """
    try:
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes technical text. Respond ONLY with the summary, no other text."},
                {"role": "user", "content": f"Summarize the following text in one short sentence (max 15 words):\n\n{chunk_text}"}
            ],
            temperature=0.0,
            max_tokens=512,
            reasoning_effort="low",
            reasoning_format="hidden"
        )
        raw_summary = response.choices[0].message.content.strip()
        summary = strip_thinking(raw_summary)
        return summary
    except Exception as e:
        print(f"Error enriching chunk: {e}")
        return ""
