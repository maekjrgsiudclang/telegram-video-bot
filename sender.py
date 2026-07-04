import os
import subprocess
import math
from pathlib import Path
from typing import List
from config import MAX_CHUNK_SIZE_MB


TELEGRAM_MAX_SIZE = 50 * 1024 * 1024


def get_duration(input_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def split_file(input_path: str) -> List[str]:
    max_bytes = MAX_CHUNK_SIZE_MB * 1024 * 1024
    file_size = os.path.getsize(input_path)

    if file_size <= max_bytes:
        return [input_path]

    ext = Path(input_path).suffix
    stem = Path(input_path).stem
    out_dir = Path(input_path).parent
    num_parts = math.ceil(file_size / max_bytes)

    duration = get_duration(input_path)
    segment_time = duration / num_parts + 1

    pattern = str(out_dir / f"{stem}_part%03d{ext}")

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-c", "copy",
        "-movflags", "+faststart",
        "-f", "segment",
        "-segment_time", str(segment_time),
        "-reset_timestamps", "1",
        pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"Split failed: {result.stderr[-300:]}")

    parts = sorted(out_dir.glob(f"{stem}_part*{ext}"))

    if not parts:
        raise Exception("Split failed: no output files created")

    return [str(p) for p in parts]


def prepare_video(input_path: str) -> List[str]:
    parts = split_file(input_path)

    for p in parts:
        if os.path.getsize(p) > TELEGRAM_MAX_SIZE:
            raise Exception(f"File too large for Telegram: {os.path.getsize(p) / 1024 / 1024:.0f}MB (max 50MB)")

    return parts
