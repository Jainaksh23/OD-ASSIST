import os
import subprocess
from groq import Groq
import imageio_ffmpeg

# 25 MB in bytes (Groq whisper limit)
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
# Split slightly smaller to be safe (e.g. 20 MB chunks)
SPLIT_SIZE_BYTES = 20 * 1024 * 1024

def extract_and_transcribe_video(file_path: str, client: Groq) -> str:
    """
    Extracts audio using ffmpeg, splits if > 25MB, and transcribes via Groq Whisper.
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
    transcripts = []
    
    try:
        # 2. Check size and split if needed
        if file_size > MAX_FILE_SIZE_BYTES:
            # We approximate split by time or just let ffmpeg segment it
            # A simple way to segment by size is difficult, segmenting by time (e.g. 10 min) is easier
            # Let's use ffmpeg segmenter: 10 mins chunks (usually < 15MB for mp3)
            segment_pattern = file_path + "_part%03d.mp3"
            split_cmd = [
                ffmpeg_exe, "-i", output_audio,
                "-f", "segment",
                "-segment_time", "600",
                "-c", "copy",
                segment_pattern
            ]
            subprocess.run(split_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Transcribe all segments
            part_idx = 0
            while True:
                part_file = file_path + f"_part{part_idx:03d}.mp3"
                if not os.path.exists(part_file):
                    break
                    
                with open(part_file, "rb") as audio_file:
                    res = client.audio.transcriptions.create(
                        file=(os.path.basename(part_file), audio_file.read()),
                        model="whisper-large-v3",
                        response_format="text"
                    )
                    transcripts.append(res)
                
                # Cleanup part
                os.remove(part_file)
                part_idx += 1
                
        else:
            # Single file transcription
            with open(output_audio, "rb") as audio_file:
                res = client.audio.transcriptions.create(
                    file=(os.path.basename(output_audio), audio_file.read()),
                    model="whisper-large-v3",
                    response_format="text"
                )
                transcripts.append(res)
                
    finally:
        # Cleanup extracted audio
        if os.path.exists(output_audio):
            os.remove(output_audio)
            
    return " ".join(transcripts)
