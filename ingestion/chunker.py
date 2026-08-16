from langchain_text_splitters import RecursiveCharacterTextSplitter

def get_chunks(text: str) -> list[str]:
    """
    Splits text into chunks using LangChain's RecursiveCharacterTextSplitter.
    Uses chunk_size=600 and overlap=90 tokens/chars approx.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=90,
        length_function=len,
        is_separator_regex=False,
    )
    
    return splitter.split_text(text)
