import os

def is_folder_link(url: str) -> bool:
    """Check if a Google Drive URL is a folder link rather than a file link."""
    return url and "drive.google.com/drive/folders/" in url

def detect_source_type(file_path: str = None, url: str = None) -> str:
    """
    Detects if the source is a pdf, drive_doc, drive_video, or raw_text.
    """
    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            return "pdf"
        elif ext in [".mp4", ".mov", ".mkv", ".avi", ".webm", ".mp3", ".wav"]:
            return "drive_video"
        elif ext in [".txt", ".docx", ".doc"]:
            return "drive_doc"
        else:
            return "raw_text"
    
    if url:
        if "drive.google.com" in url:
            # We will refine this after downloading, default to doc for now
            return "drive_doc"
    
    return "raw_text"
