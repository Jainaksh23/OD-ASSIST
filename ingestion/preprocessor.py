import re

def clean_text(text: str) -> str:
    """
    Normalizes whitespace, removes common header/footer artifacts,
    and preserves multi-lingual content (Devanagari/Hinglish).
    """
    # Remove multiple spaces/newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    
    # Strip leading/trailing whitespaces
    text = text.strip()
    
    return text
