from groq import Groq
from generation.generator import strip_thinking

def enrich_chunk(chunk_text: str, client: Groq) -> str:
    """
    Uses Groq openai/gpt-oss-20b to generate a one-line summary 
    of the chunk for BM25 keyword search enhancement.
    """
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes technical text. Respond ONLY with the summary, no other text."},
                {"role": "user", "content": f"Summarize the following text in one short sentence (max 15 words):\n\n{chunk_text}"}
            ],
            temperature=0.0,
            max_tokens=50
        )
        raw_summary = response.choices[0].message.content.strip()
        summary = strip_thinking(raw_summary)
        return summary
    except Exception as e:
        print(f"Error enriching chunk: {e}")
        return ""
