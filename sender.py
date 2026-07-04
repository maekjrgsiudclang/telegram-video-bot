import os
import subprocess
import asyncio
from pathlib import Path
from typing import List
from config import MAX_CHUNK_SIZE_MB, QUALITY_PRESETS


async def compress_video(input_path: str, output_path: str, height: int) -> str:
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"scale=-2:{height}",
        "-c:v", "libx264", "-crf", "28",
        "-preset", "ultrafast",
        "-c:a", "copy",
        output_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        raise Exception("Compression timed out (5 min limit)")

    if proc.returncode != 0:
        error_msg = stderr.decode(errors="ignore")[-500:]
        raise Exception(f"ffmpeg failed: {error_msg}")

    return output_path


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
        "-f", "segment",
        "-segment_bytes", str(max_bytes),
        "-reset_timestamps", "1",
        pattern,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    parts = sorted(out_dir.glob(f"{stem}_part*{ext}"))
    if not parts:
        return [input_path]
    return [str(p) for p in parts]


async def prepare_video(input_path: str, quality: str, progress_callback=None) -> List[str]:
    work_path = input_path

    height = QUALITY_PRESETS.get(quality)
    if height is not None:
        if progress_callback:
            await progress_callback("compressing")
        compressed = input_path + ".compressed.mp4"
        await compress_video(input_path, compressed, height)
        work_path = compressed

    if progress_callback:
        await progress_callback("splitting")
    parts = split_file(work_path)

    return parts
