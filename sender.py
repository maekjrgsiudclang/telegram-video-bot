import os
import subprocess
from pathlib import Path
from typing import List
from config import MAX_CHUNK_SIZE_MB


TELEGRAM_MAX_SIZE = 50 * 1024 * 1024  # 50MB Telegram limit


def split_file(input_path: str) -> List[str]:
    max_bytes = MAX_CHUNK_SIZE_MB * 1024 * 1024
    file_size = os.path.getsize(input_path)

    if file_size <= max_bytes:
        return [input_path]

    ext = Path(input_path).suffix
    stem = Path(input_path).stem
    out_dir = Path(input_path).parent
    pattern = str(out_dir / f"{stem}_part%03d{ext}")

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-c", "copy",
        "-movflags", "+faststart",
        "-f", "segment",
        "-segment_bytes", str(max_bytes),
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

    # If a part is still > 50MB, it won't upload to Telegram
    # Check and warn
    for p in parts:
        if os.path.getsize(p) > TELEGRAM_MAX_SIZE:
            raise Exception(f"File too large for Telegram: {os.path.getsize(p) / 1024 / 1024:.0f}MB (max 50MB)")

    return parts
