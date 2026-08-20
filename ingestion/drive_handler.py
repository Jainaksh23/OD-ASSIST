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
    import sys
    import re
    import importlib
    import time
    import requests

    # Eagerly ensure gdown.download is imported so the monkey-patch
    # always applies — even on the very first call in the process.
    if 'gdown.download' not in sys.modules:
        importlib.import_module('gdown.download')

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

    max_retries = 3
    backoff = 3
    
    for attempt in range(max_retries + 1):
        try:
            try:
                return gdown.download(**kwargs)
            except TypeError as e:
                if "fuzzy" in str(e):
                    kwargs_copy = dict(kwargs)
                    kwargs_copy.pop("fuzzy", None)
                    return gdown.download(**kwargs_copy)
                raise
        except Exception as e:
            error_msg = str(e).lower()
            
            # Identify if it's a transient network error
            is_network_error = (
                "ssleoferror" in error_msg 
                or "sslerror" in error_msg
                or "max retries exceeded" in error_msg
                or "connectionerror" in error_msg
                or "read timed out" in error_msg
                or "connection reset" in error_msg
                or getattr(requests.exceptions, "ConnectionError", None) and isinstance(e, (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.SSLError
                ))
            )
            
            # Permission/Access issues should fail immediately without retry.
            # Note: gdown often prefixes generic errors with "failed to retrieve", 
            # so we only treat it as an Access Denied if it isn't a network error.
            is_permission_error = any(err in error_msg for err in ["access denied", "permission", "403", "forbidden"])
            if is_permission_error or (not is_network_error and "failed to retrieve" in error_msg):
                raise Exception("Access Denied") from e
            
            if is_network_error:
                if attempt < max_retries:
                    print(f"Network error encountered. Retrying in {backoff} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                else:
                    raise Exception(f"Network issue after {max_retries} retries: {e}") from e
                    
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