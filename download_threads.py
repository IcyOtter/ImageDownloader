import os
import re
import asyncio
import aiohttp
import aiofiles
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal
import requests
from praw import Reddit
from utils import create_download_path, download_file, scrape_erome_album
from utils import parse_4chan_thread_url, fetch_4chan_thread_data, get_4chan_media_url

class DownloaderThread(QThread):
    progress_updated = pyqtSignal(int, int)
    log_message = pyqtSignal(str)

    def __init__(self, subreddit_name, limit, allow_sfw, allow_nsfw, master_folder, cache_folder, reddit_client: Reddit):
        super().__init__()
        self.subreddit_name = subreddit_name
        self.limit = limit
        self.allow_sfw = allow_sfw
        self.allow_nsfw = allow_nsfw
        self.master_folder = master_folder
        self.cache_folder = cache_folder
        self.reddit = reddit_client

    def run(self):
        try:
            subreddit = self.reddit.subreddit(self.subreddit_name)
            self.log(f"Downloading up to {self.limit if self.limit else 'All'} images from r/{subreddit.display_name}...")

            if (subreddit.over18 and not self.allow_nsfw) or (not subreddit.over18 and not self.allow_sfw):
                self.log("Subreddit does not match selected filter (SFW/NSFW). Skipping download.")
                return

            os.makedirs(self.master_folder, exist_ok=True)
            os.makedirs(self.cache_folder, exist_ok=True)

            safe_name = re.sub(r'[^\w-]', '_', self.subreddit_name.lower().replace("r/", ""))
            subfolder_name = f"r_{safe_name}"
            download_folder = os.path.join(self.master_folder, subfolder_name)
            os.makedirs(download_folder, exist_ok=True)

            cache_file = os.path.join(self.cache_folder, f"{subfolder_name}.txt")
            if os.path.exists(cache_file):
                with open(cache_file, "r") as f:
                    cached_urls = set(line.strip() for line in f if line.strip())
            else:
                cached_urls = set()

            posts = list(subreddit.hot(limit=1000))
            count = 0
            new_urls = []
            total_target = len(posts) if not self.limit else self.limit
            self.progress_updated.emit(0, total_target)

            for post in posts:
                url = post.url.strip()
                if url.lower().endswith((".jpg", ".jpeg", ".png", ".gif")) and url not in cached_urls:
                    try:
                        image_data = requests.get(url).content
                        extension = os.path.splitext(url)[1]
                        filename = os.path.join(download_folder, f"{subfolder_name}_{count}_{post.id}{extension}")
                        with open(filename, "wb") as f:
                            f.write(image_data)
                        self.log(f"Saved: {filename}")
                        count += 1
                        new_urls.append(url)
                        self.progress_updated.emit(count, total_target)
                        if self.limit and count >= self.limit:
                            break
                    except Exception as e:
                        self.log(f"Failed to download {url}: {e}")

            if new_urls:
                with open(cache_file, "a") as f:
                    for url in new_urls:
                        f.write(url + "\n")

            if count == 0:
                self.log("No new images found (all duplicates).")
            else:
                self.log(f"{count} new images downloaded to '{os.path.abspath(download_folder)}'")

        except Exception as e:
            self.log(f"Error: {e}")

    def log(self, message):
        self.log_message.emit(message)

class Download4chanThread(QThread):
    progress_updated = pyqtSignal(int, int)
    log_message = pyqtSignal(str)

    def __init__(self, url, master_folder, log_link_callback=None):
        super().__init__()
        self.url = url
        self.master_folder = master_folder
        self.log_link_callback = log_link_callback

    def run(self):
        asyncio.run(self.download_4chan_thread())

    async def download_4chan_thread(self):
        try:
            board, thread_id = parse_4chan_thread_url(self.url)
            data = await fetch_4chan_thread_data(board, thread_id)

            save_path = Path(self.master_folder) / f"4chan_{board}_{thread_id}"
            save_path.mkdir(parents=True, exist_ok=True)

            images = [post for post in data.get("posts", []) if "tim" in post and "ext" in post]
            total = len(images)

            async with aiohttp.ClientSession() as session:
                for i, post in enumerate(images):
                    file_url = get_4chan_media_url(board, post["tim"], post["ext"])
                    file_path = save_path / f"{post['tim']}{post['ext']}"
                    async with session.get(file_url) as resp:
                        if resp.status == 200:
                            with open(file_path, "wb") as out:
                                out.write(await resp.read())
                            self.log_message.emit(f"Saved: {file_path}")
                            if self.log_link_callback:
                                self.log_link_callback("4chan", self.url)  # Thread URL only
                        else:
                            self.log_message.emit(f"Failed to download: {file_url}")

                    self.progress_updated.emit(i + 1, total)

            self.log_message.emit(f"Downloaded {total} images to {save_path}")

        except Exception as e:
            self.log_message.emit(f"4chan download error: {e}")
            
class DownloadEromeThread(QThread):
    progress_updated = pyqtSignal(int, int)
    log_message = pyqtSignal(str)

    def __init__(self, url, master_folder, collect_album_data_fn, download_fn):
        super().__init__()
        self.url = url
        self.master_folder = master_folder
        self.collect_album_data_fn = collect_album_data_fn
        self.download_fn = download_fn

    def run(self):
        asyncio.run(self.download_erome())

    async def download_erome(self):
        try:
            title, urls = await scrape_erome_album(self.url, skip_videos=False, skip_images=False)
            download_path = create_download_path(self.master_folder, title)

            total = len(urls)
            semaphore = asyncio.Semaphore(1)

            async with aiohttp.ClientSession(headers={"Referer": self.url}) as session:
                for i, url in enumerate(urls):
                    await download_file(session, url, semaphore, download_path)
                    self.progress_updated.emit(i + 1, total)

            self.log_message.emit(f"Erome gallery downloaded to {download_path}")

        except Exception as e:
            self.log_message.emit(f"Erome download error: {e}")
