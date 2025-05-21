import sys
import os
import re
import json
import requests
import praw
import shutil
import asyncio
import aiohttp
import aiofiles
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from pathlib import Path
from tqdm.asyncio import tqdm_asyncio, tqdm
from dotenv import load_dotenv
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QLineEdit, QTextEdit, QSpinBox, QMessageBox, QCheckBox, QListWidget, QComboBox, QFileDialog
)

# Constants for Erome
USER_AGENT = "Mozilla/5.0"
HOST = "www.erome.com"
CHUNK_SIZE = 1024

# Load environment variables
load_dotenv()

# Initialize Reddit client
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent=os.getenv("REDDIT_USER_AGENT"),
    username=os.getenv("REDDIT_USERNAME"),
    password=os.getenv("REDDIT_PASSWORD")
)

class RedditDownloaderGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Reddit + Erome Image Downloader")
        self.setMinimumWidth(600)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        search_layout = QHBoxLayout()
        self.search_type_combo = QComboBox()
        self.search_type_combo.addItems(["Search by keyword", "Search by subreddit name", "Erome gallery URL"])
        self.keyword_input = QLineEdit()
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_subreddits)
        search_layout.addWidget(self.search_type_combo)
        search_layout.addWidget(self.keyword_input)
        search_layout.addWidget(self.search_button)

        self.subreddit_list = QListWidget()

        count_layout = QHBoxLayout()
        self.count_label = QLabel("Number of images:")
        self.count_input = QSpinBox()
        self.count_input.setRange(1, 100)
        self.count_input.setValue(5)
        count_layout.addWidget(self.count_label)
        count_layout.addWidget(self.count_input)

        filter_layout = QHBoxLayout()
        self.sfw_checkbox = QCheckBox("SFW")
        self.sfw_checkbox.setChecked(True)
        self.nsfw_checkbox = QCheckBox("NSFW")
        self.nsfw_checkbox.setChecked(True)
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.sfw_checkbox)
        filter_layout.addWidget(self.nsfw_checkbox)

        self.download_button = QPushButton("Download Images")
        self.download_button.clicked.connect(self.download_images)

        manage_layout = QHBoxLayout()
        self.clear_cache_button = QPushButton("Clear All Caches")
        self.clear_cache_button.clicked.connect(self.clear_all_caches)
        self.clear_selected_cache_button = QPushButton("Clear Selected Cache")
        self.clear_selected_cache_button.clicked.connect(self.clear_selected_cache)
        self.clear_downloads_button = QPushButton("Clear Downloads")
        self.clear_downloads_button.clicked.connect(self.clear_master_folder)
        self.copy_downloads_button = QPushButton("Copy Master Folder")
        self.copy_downloads_button.clicked.connect(self.copy_master_folder)
        manage_layout.addWidget(self.clear_cache_button)
        manage_layout.addWidget(self.clear_selected_cache_button)
        manage_layout.addWidget(self.clear_downloads_button)
        manage_layout.addWidget(self.copy_downloads_button)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        layout.addLayout(search_layout)
        layout.addWidget(self.subreddit_list)
        layout.addLayout(count_layout)
        layout.addLayout(filter_layout)
        layout.addWidget(self.download_button)
        layout.addLayout(manage_layout)
        layout.addWidget(QLabel("Log Output:"))
        layout.addWidget(self.log_output)

        self.setLayout(layout)

    def log(self, message):
        self.log_output.append(message)

    def clear_all_caches(self):
        cache_folder = "cache"
        if not os.path.exists(cache_folder):
            self.log("Cache folder does not exist.")
            return
        try:
            for item in os.listdir(cache_folder):
                path = os.path.join(cache_folder, item)
                if os.path.isfile(path):
                    os.unlink(path)
            self.log("✅ All cache files deleted.")
        except Exception as e:
            self.log(f"❌ Failed to clear caches: {e}")

    def clear_selected_cache(self):
        selected = self.subreddit_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Input Error", "Please select a subreddit to clear its cache.")
            return

        try:
            subreddit_name = selected.text().split()[1].replace("r/", "")
        except IndexError:
            self.log("❌ Could not determine subreddit name from selection.")
            return

        safe_name = re.sub(r'[^\w\-]', '_', subreddit_name.lower())
        cache_file = os.path.join("cache", f"r_{safe_name}.txt")

        try:
            if os.path.exists(cache_file):
                os.remove(cache_file)
                self.log(f"✅ Cache cleared for r/{subreddit_name}.")
            else:
                self.log(f"ℹ️ No cache file found for r/{subreddit_name}.")
        except Exception as e:
            self.log(f"❌ Failed to clear cache for r/{subreddit_name}: {e}")

    def clear_master_folder(self):
        master_folder = "downloader"
        if not os.path.exists(master_folder):
            self.log("Master folder does not exist.")
            return

        try:
            for item in os.listdir(master_folder):
                path = os.path.join(master_folder, item)
                if os.path.isfile(path) or os.path.islink(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            self.log("✅ All download contents deleted.")
        except Exception as e:
            self.log(f"❌ Failed to clear downloads: {e}")

    def copy_master_folder(self):
        master_folder = "downloader"
        if not os.path.exists(master_folder):
            self.log("Master folder does not exist.")
            return

        target_dir = QFileDialog.getExistingDirectory(self, "Select Target Directory")
        if not target_dir:
            self.log("No target directory selected.")
            return

        try:
            dest_path = os.path.join(target_dir, os.path.basename(master_folder))
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.copytree(master_folder, dest_path)
            self.log(f"✅ Master folder copied to {dest_path}")
        except Exception as e:
            self.log(f"❌ Failed to copy master folder: {e}")

    async def download_erome_gallery(self, url):
        try:
            await dump(url=url, max_connections=5, skip_videos=False, skip_images=False)
            self.log("✅ Erome gallery downloaded.")
        except Exception as e:
            self.log(f"❌ Erome download error: {e}")

    def search_subreddits(self):
        keyword = self.keyword_input.text().strip().lower()
        allow_sfw = self.sfw_checkbox.isChecked()
        allow_nsfw = self.nsfw_checkbox.isChecked()
        search_type = self.search_type_combo.currentText()

        self.subreddit_list.clear()

        if not keyword:
            QMessageBox.warning(self, "Input Error", "Please enter a keyword or subreddit name to search.")
            return

        if "erome.com" in keyword or search_type == "Erome gallery URL":
            self.subreddit_list.addItem(keyword)
            self.log("Erome gallery ready for download.")
            return

        try:
            results = []
            if search_type in ("Search by keyword", "Search by subreddit name"):
                for subreddit in reddit.subreddits.search(keyword, limit=100):
                    if subreddit.subscribers is not None:
                        if subreddit.over18 and not allow_nsfw:
                            continue
                        if not subreddit.over18 and not allow_sfw:
                            continue
                        if search_type == "Search by subreddit name" and keyword not in subreddit.display_name.lower():
                            continue
                        results.append((subreddit.display_name, subreddit.title, subreddit.subscribers, subreddit.over18))

            results.sort(key=lambda x: x[2], reverse=True)

            for name, title, subs, over18 in results:
                tag = "🔞" if over18 else "✅"
                self.subreddit_list.addItem(f"{tag} r/{name} ({subs:,} members) - {title}")

            if not results:
                self.log("No subreddits found matching your filters.")

        except Exception as e:
            self.log(f"Error searching subreddits: {e}")

    def download_images(self):
        selected = self.subreddit_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Input Error", "Please select a subreddit or Erome URL from the list.")
            return

        text = selected.text().strip()
        if "erome.com" in text:
            asyncio.run(self.download_erome_gallery(text))
            return

        self.log("Subreddit downloading logic is not shown here.")

# --- Utility Functions ---
def _clean_album_title(title: str, default_title="temp") -> str:
    illegal_chars = r'[\\/:*?"<>|]'
    title = re.sub(illegal_chars, "_", title).strip(". ")
    return title if title else default_title

def _get_final_download_path(album_title: str) -> Path:
    final_path = Path("downloader") / album_title
    final_path.mkdir(parents=True, exist_ok=True)
    return final_path

async def dump(url: str, max_connections: int, skip_videos: bool, skip_images: bool):
    if urlparse(url).hostname != HOST:
        raise ValueError(f"Host must be {HOST}")
    title, urls = await _collect_album_data(url, skip_videos, skip_images)
    download_path = _get_final_download_path(title)
    await _download(url, urls, max_connections, download_path)

async def _download(album: str, urls: list[str], max_connections: int, download_path: Path):
    semaphore = asyncio.Semaphore(max_connections)
    async with aiohttp.ClientSession(headers={"Referer": album, "User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=None)) as session:
        tasks = [
            _download_file(session, url, semaphore, download_path)
            for url in urls
        ]
        await tqdm_asyncio.gather(*tasks, colour="MAGENTA", desc="Album Progress", unit="file", leave=True)

async def _download_file(session: aiohttp.ClientSession, url: str, semaphore: asyncio.Semaphore, download_path: Path):
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

async def _collect_album_data(url: str, skip_videos: bool, skip_images: bool) -> tuple[str, list[str]]:
    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")
            title = _clean_album_title(soup.find("meta", property="og:title")["content"])
            videos = [v["src"] for v in soup.find_all("source")] if not skip_videos else []
            images = [i["data-src"] for i in soup.find_all("img", class_="img-back")] if not skip_images else []
            return title, list(set(videos + images))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RedditDownloaderGUI()
    window.show()
    sys.exit(app.exec_())
# Use this link to test https://www.erome.com/a/X9CLe8fX