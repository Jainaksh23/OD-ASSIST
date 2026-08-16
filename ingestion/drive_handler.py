import os
# pyrefly: ignore [missing-import]
import gdown
from ingestion.input_router import detect_source_type

def _gdown_download(**kwargs):
    """
    Version-proof wrapper around gdown.download().

    gdown <6.0 required fuzzy=True to extract the file ID from
    '/view?usp=sharing' style URLs. gdown >=6.0 removed the `fuzzy`
    kwarg entirely and always does fuzzy ID extraction, so passing
    fuzzy=True there raises:
        TypeError: download() got an unexpected keyword argument 'fuzzy'
    This tries the modern call first and falls back for older installs,
    so it works regardless of which gdown version is installed.

    gdown >=6.0 also raises gdown.exceptions.FileURLRetrievalError /
    DownloadError instead of returning None on failure — normalize both
    behaviors to a single raised Exception.
    """
    try:
        import sys
        import re
        
        # Monkey patch osp.join inside gdown.download module to sanitize destination filenames
        # This prevents WinError 87 on Windows when Drive filenames contain colons or other invalid chars.
        download_mod = sys.modules.get('gdown.download')
        if download_mod and not hasattr(download_mod, '_original_osp_join'):
            download_mod._original_osp_join = download_mod.osp.join
            
            def safe_join(path, *paths):
                sanitized_paths = []
                for p in paths:
                    if isinstance(p, str):
                        p = re.sub(r'[<>:"/\\|?*]', '_', p).replace('\ufffd', '_')
                    sanitized_paths.append(p)
                return download_mod._original_osp_join(path, *sanitized_paths)
                
            download_mod.osp.join = safe_join

        try:
            return gdown.download(**kwargs)
        except TypeError as e:
            if "fuzzy" in str(e):
                kwargs.pop("fuzzy", None)
                return gdown.download(**kwargs)
            raise
    except Exception as e:
        # covers gdown.exceptions.DownloadError / FileURLRetrievalError (6.x)
        raise Exception(f"gdown download failed: {e}") from e


def fetch_from_drive(url: str, output_dir: str) -> tuple[str, str]:
    """
    Downloads file from Google Drive and returns (file_path, detected_type).
    """
    os.makedirs(output_dir, exist_ok=True)

    # format="pdf" is only meaningful for native Google Docs/Sheets/Slides URLs
    # (docs.google.com/document/... etc.) — it tells Drive to export them as PDF.
    # It has no effect on regular uploaded files (like .mp4 videos), so it's safe
    # to pass conditionally based on URL shape.
    is_native_gdoc = "docs.google.com" in url
    if is_native_gdoc:
        output_path = _gdown_download(url=url, output=output_dir + os.sep, quiet=True, fuzzy=True, format="pdf")
    else:
        output_path = _gdown_download(url=url, output=output_dir + os.sep, quiet=True, fuzzy=True)

    if not output_path:
        raise Exception(f"Failed to download from Drive URL: {url}")
        
    detected_type = detect_source_type(file_path=output_path)
    
    # Some docs might not have extensions, default to pdf if unknown
    if detected_type == "raw_text" and not output_path.endswith(".txt"):
        detected_type = "pdf"
        
    return output_path, detected_type