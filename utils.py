# utils.py

import os
import re
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import aiohttp
import aiofiles
import asyncio
from tqdm.asyncio import tqdm, tqdm_asyncio

# Constants
USER_AGENT = "Mozilla/5.0"
EROME_HOST = "www.erome.com"
CHUNK_SIZE = 1024

USER_AGENT = "Mozilla/5.0"
CHUNK_SIZE = 1024

def clean_album_title(title: str, default_title="temp") -> str:
    illegal_chars = r'[\\/:*?"<>|]'
    title = re.sub(illegal_chars, "_", title).strip(". ")
    return title if title else default_title

def create_download_path(master_folder: str, album_title: str) -> Path:
    path = Path(master_folder) / album_title
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_final_download_path(master_folder: str, album_title: str) -> Path:
    final_path = Path(master_folder) / album_title
    final_path.mkdir(parents=True, exist_ok=True)
    return final_path

async def download_file(session: aiohttp.ClientSession, url: str, semaphore: asyncio.Semaphore, download_path: Path):
    async with semaphore:
        async with session.get(url) as r:
            if r.ok:
                file_name = Path(urlparse(url).path).name
                file_path = download_path / file_name
                total_size = int(r.headers.get("content-length", 0))
                if file_path.exists() and abs(file_path.stat().st_size - total_size) <= 50:
                    tqdm.write(f"[#] Skipping {url} [already downloaded]")
                    return
                progress = tqdm(desc=f"[+] Downloading {url}", total=total_size, unit="B", unit_scale=True, unit_divisor=CHUNK_SIZE, colour="MAGENTA", leave=False)
                async with aiofiles.open(file_path, "wb") as f:
                    async for chunk in r.content.iter_chunked(CHUNK_SIZE):
                        written = await f.write(chunk)
                        progress.update(written)
                progress.close()
            else:
                tqdm.write(f"[ERROR] Failed to download {url}")

async def dump_album(url: str, max_connections: int, skip_videos: bool, skip_images: bool, master_folder: str):
    if urlparse(url).hostname != EROME_HOST:
        raise ValueError(f"Host must be {EROME_HOST}")
    title, urls = await collect_album_data(url, skip_videos, skip_images)
    download_path = get_final_download_path(master_folder, title)
    await download_album_files(url, urls, max_connections, download_path)

async def collect_album_data(url: str, skip_videos: bool, skip_images: bool) -> tuple[str, list[str]]:
    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")
            title = clean_album_title(soup.find("meta", property="og:title")["content"])
            videos = [v["src"] for v in soup.find_all("source")] if not skip_videos else []
            images = [i["data-src"] for i in soup.find_all("img", class_="img-back")] if not skip_images else []
        return title, list(set(videos + images))

async def download_album_files(album: str, urls: list[str], max_connections: int, download_path: Path):
    semaphore = asyncio.Semaphore(max_connections)
    async with aiohttp.ClientSession(headers={"Referer": album, "User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=None)) as session:
        tasks = [
            download_file(session, url, semaphore, download_path)
            for url in urls
        ]
        await tqdm_asyncio.gather(*tasks, colour="MAGENTA", desc="Album Progress", unit="file", leave=True)


async def scrape_erome_album(url: str, skip_videos: bool, skip_images: bool) -> tuple[str, list[str]]:
    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")
            title = clean_album_title(soup.find("meta", property="og:title")["content"])
            videos = [v["src"] for v in soup.find_all("source")] if not skip_videos else []
            images = [i["data-src"] for i in soup.find_all("img", class_="img-back")] if not skip_images else []
        return title, list(set(videos + images))

async def fetch_4chan_thread_data(board: str, thread_id: str) -> dict:
    api_url = f"https://a.4cdn.org/{board}/thread/{thread_id}.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as resp:
            if resp.status != 200:
                raise ValueError("Failed to fetch thread data.")
            return await resp.json()

async def download_file(session: aiohttp.ClientSession, url: str, semaphore: asyncio.Semaphore, download_path: Path):
    async with semaphore:
        async with session.get(url) as r:
            if r.ok:
                file_name = Path(urlparse(url).path).name
                file_path = download_path / file_name
                total_size = int(r.headers.get("content-length", 0))
                if file_path.exists() and abs(file_path.stat().st_size - total_size) <= 50:
                    tqdm.write(f"[#] Skipping {url} [already downloaded]")
                    return
                progress = tqdm(desc=f"[+] Downloading {url}", total=total_size, unit="B", unit_scale=True, unit_divisor=CHUNK_SIZE, colour="MAGENTA", leave=False)
                async with aiofiles.open(file_path, "wb") as f:
                    async for chunk in r.content.iter_chunked(CHUNK_SIZE):
                        written = await f.write(chunk)
                        progress.update(written)
                progress.close()
            else:
                tqdm.write(f"[ERROR] Failed to download {url}")

def parse_4chan_thread_url(url: str) -> tuple[str, str]:
    board = re.search(r"boards\.4chan\.org/([^/]+)/thread/", url)
    thread_id = re.search(r"thread/(\d+)", url)
    if not board or not thread_id:
        raise ValueError("Invalid 4chan thread URL format.")
    return board.group(1), thread_id.group(1)

def get_4chan_media_url(board: str, tim: int, ext: str) -> str:
    return f"https://i.4cdn.org/{board}/{tim}{ext}"