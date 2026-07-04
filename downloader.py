import os
import httpx
from config import TEMP_DIR


async def get_file_size(url: str) -> int | None:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.head(url)
        if resp.status_code != 200:
            return None
        length = resp.headers.get("content-length")
        return int(length) if length else None


def get_filename_from_url(url: str) -> str:
    path = httpx.URL(url).path
    name = os.path.basename(path)
    if not name or "." not in name:
        name = "video.mp4"
    return name


async def download_file(url: str, dest: str, progress_callback=None) -> str:
    async with httpx.AsyncClient(follow_redirects=True, timeout=None) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total:
                        await progress_callback(downloaded, total)
    return dest
