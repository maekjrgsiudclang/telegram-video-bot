import os
from typing import Optional
import httpx
from config import TEMP_DIR


async def get_file_size(url: str) -> Optional[int]:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.head(url)
            if resp.status_code == 200:
                length = resp.headers.get("content-length")
                if length:
                    return int(length)

            resp = await client.get(url, headers={"Range": "bytes=0-0"})
            if resp.status_code in (200, 206):
                content_range = resp.headers.get("content-range", "")
                if "/" in content_range:
                    return int(content_range.split("/")[-1])
                length = resp.headers.get("content-length")
                if length:
                    return int(length)
    except Exception:
        pass
    return None


def get_filename_from_url(url: str) -> str:
    path = httpx.URL(url).path
    name = os.path.basename(path)
    if not name or "." not in name:
        name = "video.mp4"
    return name


async def download_file(url: str, dest: str, progress_callback=None, cancel_check=None) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                    if cancel_check and cancel_check():
                        raise Exception("Cancelled")
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total:
                        await progress_callback(downloaded, total)
    return dest
