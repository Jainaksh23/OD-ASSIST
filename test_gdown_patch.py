import sys
import gdown.download
import os.path
import re

download_mod = sys.modules['gdown.download']
original_join = download_mod.osp.join

def safe_join(path, *paths):
    sanitized_paths = []
    for p in paths:
        if isinstance(p, str):
            p = re.sub(r'[<>:"|?*]', '_', p).replace('\ufffd', '_')
        sanitized_paths.append(p)
    return original_join(path, *sanitized_paths)

download_mod.osp.join = safe_join

print("Testing osp.join patch...")
try:
    download_mod.download('https://drive.google.com/file/d/1ujvpst5OMS2VOP3-QahmoUzyIPXls80V/view', 'temp_files' + os.sep, quiet=True, fuzzy=True)
    print("SUCCESS!")
except Exception as e:
    import traceback
    traceback.print_exc()
