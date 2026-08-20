import os
import subprocess
import time
import glob
import re
from groq import Groq
import imageio_ffmpeg

# 25 MB in bytes (Groq whisper limit)
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
# Split threshold time: 8 minutes = 480 seconds
SPLIT_THRESHOLD_SECONDS = 480

def get_audio_duration(file_path: str, ffmpeg_exe: str) -> float:
    cmd = [ffmpeg_exe, "-i", file_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if match:
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return 0.0

def _transcribe_with_retry(client: Groq, file_path: str, max_retries=2) -> str:
    """Transcribes a single audio file sequentially with retries on failure."""
    for attempt in range(max_retries + 1):
        try:
            with open(file_path, "rb") as audio_file:
                res = client.audio.transcriptions.create(
                    file=(os.path.basename(file_path), audio_file.read()),
                    model="whisper-large-v3",
                    response_format="text",
                    timeout=180.0
                )
                return res
        except Exception as e:
            if attempt < max_retries:
                print(f"    [!] Transcription failed for chunk {os.path.basename(file_path)} (Attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying in 5 seconds...")
                time.sleep(5)
            else:
                raise RuntimeError(f"Failed to transcribe chunk {os.path.basename(file_path)} after {max_retries + 1} attempts: {e}")

def extract_and_transcribe_video(file_path: str, client: Groq) -> str:
    """
    Extracts audio using ffmpeg, splits if duration > 8 min or size > 25MB, 
    and transcribes sequentially via Groq Whisper with retries and timeout.
    """
    output_audio = file_path + ".mp3"
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    # 1. Extract audio
    cmd = [
        ffmpeg_exe, "-i", file_path,
        "-q:a", "0",
        "-map", "a",
        output_audio,
        "-y"
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if not os.path.exists(output_audio):
        raise RuntimeError("Failed to extract audio using ffmpeg.")
        
    file_size = os.path.getsize(output_audio)
    duration = get_audio_duration(output_audio, ffmpeg_exe)
    
    transcripts = []
    
    try:
        # 2. Check duration/size and split if needed
        # We split if > 8 minutes or > 25MB
        if duration > SPLIT_THRESHOLD_SECONDS or file_size > MAX_FILE_SIZE_BYTES:
            segment_pattern = file_path + "_part%03d.mp3"
            # Split into 8 minute chunks
            split_cmd = [
                ffmpeg_exe, "-i", output_audio,
                "-f", "segment",
                "-segment_time", "480",
                "-c", "copy",
                segment_pattern
            ]
            subprocess.run(split_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            part_files = sorted(glob.glob(file_path + "_part*.mp3"))
            
            for p_file in part_files:
                # Transcribe sequentially with retries
                text = _transcribe_with_retry(client, p_file, max_retries=2)
                transcripts.append(text)
                # Small delay between chunks to avoid rate limit
                time.sleep(2)
                
            # Cleanup part files
            for pf in part_files:
                if os.path.exists(pf):
                    try:
                        os.remove(pf)
                    except:
                        pass
                
        else:
            # Single file transcription
            text = _transcribe_with_retry(client, output_audio, max_retries=2)
            transcripts.append(text)
                
    finally:
        # Cleanup extracted full audio
        if os.path.exists(output_audio):
            try:
                os.remove(output_audio)
            except:
                pass
            
        # Ensure part files are cleaned up even if exception occurs
        part_files_remaining = glob.glob(file_path + "_part*.mp3")
        for pf in part_files_remaining:
            if os.path.exists(pf):
                try:
                    os.remove(pf)
                except:
                    pass
            
    return " ".join(transcripts)
