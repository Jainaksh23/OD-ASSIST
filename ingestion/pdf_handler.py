"""
ingestion/pdf_handler.py — with vision fallback for graphic-heavy PDFs
(Canva exports, infographic-style step guides, scanned documents).
"""

import base64
from pypdf import PdfReader
import pdfplumber
import fitz  # PyMuPDF
import gc
import time
import re

MIN_CHARS_PER_PAGE = 40
VISION_MODEL = "qwen/qwen3.6-27b"


def extract_text_from_pdf(file_path: str, groq_client=None) -> str:
    text_content = []
    num_pages = 0

    try:
        reader = PdfReader(file_path)
        num_pages = len(reader.pages)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text_content.append(extracted)
        if not "".join(text_content).strip():
            raise ValueError("pypdf extracted empty text")
    except Exception:
        text_content = []
        with pdfplumber.open(file_path) as pdf:
            num_pages = len(pdf.pages)
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text_content.append(extracted)
                page.flush_cache()
            gc.collect()

    combined = "\n".join(text_content)
    too_sparse = num_pages > 0 and len(combined.strip()) < MIN_CHARS_PER_PAGE * num_pages

    if too_sparse and groq_client is not None:
        vision_text = _extract_via_vision(file_path, groq_client)
        if vision_text and len(vision_text.strip()) > len(combined.strip()):
            return vision_text

    return combined


def _extract_via_vision(file_path: str, groq_client) -> str:
    doc = fitz.open(file_path)
    page_texts = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=100)
        img_bytes = pix.tobytes("png")
        b64_img = base64.b64encode(img_bytes).decode("utf-8")
        
        del pix

        try_count = 0
        while try_count < 3:
            try:
                response = groq_client.chat.completions.create(
                    model=VISION_MODEL,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": (
                                "Transcribe all visible text on this document page, in reading order. "
                                "If it's a step-by-step guide, list every numbered step with its full label. "
                                "Include text inside icons, callout boxes, and diagrams. "
                                "Output only the transcribed content — no commentary, no markdown."
                            )},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}},
                        ],
                    }],
                    temperature=0.0,
                    max_tokens=1024,
                )
                text = response.choices[0].message.content.strip()
                # Remove <think> tags often returned by Qwen
                text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
                page_texts.append(text)
                break
            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "rate" in error_msg:
                    try_count += 1
                    time.sleep(5 * try_count)
                else:
                    print(f"Vision extraction failed for page {page_num}: {e}")
                    break
            
        del img_bytes
        del b64_img
        gc.collect()
        time.sleep(1.0)

    doc.close()
    return "\n\n".join(page_texts)

