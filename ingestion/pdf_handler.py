import base64
import logging
import gc
import time

from pypdf import PdfReader
import pdfplumber

logger = logging.getLogger(__name__)

# Max pages to OCR (prevents memory/cost blow-up on huge PDFs)
MAX_OCR_PAGES = 25


def extract_text_from_pdf(file_path: str, groq_client=None) -> str:
    """
    Extracts text from a PDF file using a 3-tier strategy:
      1. pypdf  (fast, text-layer PDFs)
      2. pdfplumber (fallback for complex layouts)
      3. Groq Vision OCR (for image-based / Canva PDFs)

    If tiers 1 & 2 return empty text and a groq_client is provided,
    converts each page to an image and sends it to Groq's vision
    model for OCR.
    """
    text_content = _try_pypdf(file_path)

    if not text_content.strip():
        text_content = _try_pdfplumber(file_path)

    if not text_content.strip() and groq_client:
        logger.info("pypdf and pdfplumber returned empty — trying Groq Vision OCR for: %s", file_path)
        text_content = _try_vision_ocr(file_path, groq_client)

    return text_content


def _try_pypdf(file_path: str) -> str:
    """Tier 1: Extract text using pypdf."""
    try:
        reader = PdfReader(file_path)
        pages = []
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                pages.append(extracted)
        return "\n".join(pages)
    except Exception as e:
        logger.warning("pypdf extraction failed: %s", e)
        return ""


def _try_pdfplumber(file_path: str) -> str:
    """Tier 2: Extract text using pdfplumber (better for tables)."""
    try:
        pages = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    pages.append(extracted)
                page.flush_cache()
                gc.collect()
        return "\n".join(pages)
    except Exception as e:
        logger.warning("pdfplumber extraction failed: %s", e)
        return ""


def _try_vision_ocr(file_path: str, groq_client) -> str:
    """
    Tier 3: Convert PDF pages to images via PyMuPDF, then use Groq
    Vision model to extract text from each page image.

    Handles rate limits with exponential backoff.
    """
    try:
        import pymupdf as fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF not installed — cannot do Vision OCR. pip install PyMuPDF")
        return ""

    pages_text = []

    try:
        doc = fitz.open(file_path)
        total_pages = min(len(doc), MAX_OCR_PAGES)

        if len(doc) > MAX_OCR_PAGES:
            logger.warning(
                "PDF has %d pages, only OCR-ing first %d to prevent cost/memory issues",
                len(doc), MAX_OCR_PAGES,
            )

        for page_num in range(total_pages):
            try:
                page = doc[page_num]
                # Render at 150 DPI — good balance of quality vs size
                # (Canva PDFs are usually simple layouts)
                mat = fitz.Matrix(150 / 72, 150 / 72)
                pix = page.get_pixmap(matrix=mat)

                # Convert to PNG bytes
                img_bytes = pix.tobytes("png")

                # Base64 encode for Groq Vision API
                b64_image = base64.b64encode(img_bytes).decode("utf-8")

                # Free pixmap memory immediately
                del pix
                
                # Send to Groq Vision for OCR
                extracted = _ocr_single_page(groq_client, b64_image, page_num + 1, total_pages)
                if extracted:
                    pages_text.append(extracted)

                # Free heavy string buffers
                del img_bytes
                del b64_image
                gc.collect()

                # Small delay between pages to respect rate limits
                if page_num < total_pages - 1:
                    time.sleep(1.0)

            except Exception as e:
                logger.warning("Vision OCR failed for page %d: %s", page_num + 1, e)
                continue

        doc.close()

    except Exception as e:
        logger.error("Failed to open PDF for Vision OCR: %s", e)
        return ""

    result = "\n\n".join(pages_text)
    if result.strip():
        logger.info("Vision OCR extracted %d characters from %d pages", len(result), len(pages_text))
    return result


def _ocr_single_page(groq_client, b64_image: str, page_num: int, total_pages: int) -> str:
    """
    Sends a single page image to Groq Vision for text extraction.
    Retries up to 3 times with exponential backoff on rate-limit errors.
    """
    max_retries = 3
    backoff_delays = [5, 10, 20]

    prompt = (
        "Extract ALL text visible in this image. This is a page from a PDF document. "
        "Preserve the original structure — headings, bullet points, numbered lists, tables. "
        "If text is in Hindi or Hinglish, keep it as-is. "
        "Output ONLY the extracted text, nothing else. No commentary."
    )

    for attempt in range(max_retries):
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.2-11b-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64_image}",
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                temperature=0.1,
                max_tokens=2048,
            )
            text = response.choices[0].message.content.strip()
            logger.info("  OCR page %d/%d: %d chars extracted", page_num, total_pages, len(text))
            return text

        except Exception as e:
            error_msg = str(e).lower()
            if ("429" in error_msg or "too many requests" in error_msg) and attempt < max_retries - 1:
                delay = backoff_delays[attempt]
                logger.warning(
                    "  Rate-limited on page %d, retrying in %ds (attempt %d/%d)...",
                    page_num, delay, attempt + 1, max_retries,
                )
                time.sleep(delay)
            else:
                logger.error("  Vision OCR failed for page %d: %s", page_num, e)
                return ""

    return ""

