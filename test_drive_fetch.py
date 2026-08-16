import sys
import traceback
import gdown

print(f"Python Executable: {sys.executable}")
print(f"gdown version: {gdown.__version__}")

try:
    from ingestion.drive_handler import fetch_from_drive
    res = fetch_from_drive('https://drive.google.com/file/d/1ujvpst5OMS2VOP3-QahmoUzyIPXls80V/view', 'temp_files')
    print("SUCCESS:", res)
except Exception as e:
    print("FAILED WITH EXCEPTION:")
    traceback.print_exc()
