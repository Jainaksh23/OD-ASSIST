def determine_confidence(answer: str) -> str:
    """
    Heuristic to determine confidence of the generated answer.
    """
    lower_answer = answer.lower()
    
    # Low confidence indicators
    if "don't have enough information" in lower_answer or \
       "do not have enough information" in lower_answer or \
       "insufficient information" in lower_answer:
        return "low"
        
    # Medium confidence: Very short answer without strong context, 
    # but for now we just use length as a simple proxy
    if len(answer.split()) < 10:
        return "medium"
        
    return "high"
