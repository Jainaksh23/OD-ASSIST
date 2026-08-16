from pypdf import PdfReader
import pdfplumber

def extract_text_from_pdf(file_path: str) -> str:
    """
    Extracts text from a PDF file using pypdf, with pdfplumber fallback.
    """
    text_content = []
    
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text_content.append(extracted)
                
        if not "".join(text_content).strip():
            raise ValueError("pypdf extracted empty text")
            
    except Exception as e:
        # Fallback to pdfplumber
        text_content = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text_content.append(extracted)
                    
    return "\n".join(text_content)
