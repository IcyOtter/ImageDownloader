import sys, os, re, requests, praw, shutil, asyncio, aiohttp, aiofiles, webbrowser
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from pathlib import Path
from tqdm.asyncio import tqdm_asyncio, tqdm
from dotenv import load_dotenv
from PyQt5.QtCore import QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QLineEdit, QTextEdit, QSpinBox, QMessageBox, QCheckBox, QListWidget, QComboBox, QFileDialog,
    QMenuBar, QMenu, QAction, QMainWindow, QProgressBar
)

# Constants for Erome
USER_AGENT = "Mozilla/5.0"
EROME_HOST = "www.erome.com"
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

class DownloaderThread(QThread):
    progress_updated = pyqtSignal(int, int)  # current, total
    log_message = pyqtSignal(str)

    def __init__(self, subreddit_name, limit, allow_sfw, allow_nsfw, master_folder, cache_folder):
        super().__init__()
        self.subreddit_name = subreddit_name
        self.limit = limit
        self.allow_sfw = allow_sfw
        self.allow_nsfw = allow_nsfw
        self.master_folder = master_folder
        self.cache_folder = cache_folder

    def run(self):
        try:
            subreddit = reddit.subreddit(self.subreddit_name)
            self.log(f"Downloading up to {self.limit if self.limit else 'All'} images from r/{subreddit.display_name}...")

            if (subreddit.over18 and not self.allow_nsfw) or (not subreddit.over18 and not self.allow_sfw):
                self.log("Subreddit does not match selected filter (SFW/NSFW). Skipping download.")
                return

            os.makedirs(self.master_folder, exist_ok=True)
            os.makedirs(self.cache_folder, exist_ok=True)

            safe_name = re.sub(r'[^\w\-]', '_', self.subreddit_name.lower())
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
            board = re.search(r"boards\.4chan\.org/([^/]+)/thread/", self.url)
            thread_id = re.search(r"thread/(\d+)", self.url)
            if not board or not thread_id:
                self.log_message.emit("Invalid 4chan thread URL format.")
                return

            board, thread_id = board.group(1), thread_id.group(1)
            api_url = f"https://a.4cdn.org/{board}/thread/{thread_id}.json"
            media_url_base = f"https://i.4cdn.org/{board}/"
            save_path = Path(self.master_folder) / f"4chan_{board}_{thread_id}"
            save_path.mkdir(parents=True, exist_ok=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        self.log_message.emit("Failed to fetch thread data.")
                        return
                    data = await resp.json()
                    images = [post for post in data.get("posts", []) if "tim" in post and "ext" in post]

                    total = len(images)
                    for i, post in enumerate(images):
                        file_url = f"{media_url_base}{post['tim']}{post['ext']}"
                        file_path = save_path / f"{post['tim']}{post['ext']}"
                        async with session.get(file_url) as f:
                            if f.status == 200:
                                with open(file_path, "wb") as out:
                                    out.write(await f.read())
                                self.log_message.emit(f"Saved: {file_path}")
                                if self.log_link_callback:
                                    self.log_link_callback("4chan", file_url)
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
        try:
            title, urls = asyncio.run(self.collect_album_data_fn(self.url, skip_videos=False, skip_images=False))
            download_path = Path(self.master_folder) / title
            download_path.mkdir(parents=True, exist_ok=True)

            total = len(urls)
            for i, url in enumerate(urls):
                asyncio.run(self.download_fn(self.url, [url], max_connections=1, download_path=download_path))
                self.progress_updated.emit(i + 1, total)

            self.log_message.emit(f"Erome gallery downloaded to {download_path}")
        except Exception as e:
            self.log_message.emit(f"Erome download error: {e}")

class RedditDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Downloader")
        self.setMinimumWidth(800)
        self.master_folder = "downloader"
        self.setup_menu()
        self.setup_ui()
        self.link_log_file = "downloaded_links.log"

    def setup_menu(self):
        menu_bar = self.menuBar()
        # Links menu
        links_menu = QMenu("Links", self)
        # Log menu
        log_menu = QMenu("Log", self)

        # Place links to websites here
        websites = {
            "Reddit": "https://www.reddit.com",
            "Erome": "https://www.erome.com",
            "4chan": "https://boards.4chan.org",
        }

        for name, url in websites.items():
            action = QAction(name, self)
            action.triggered.connect(lambda checked, link=url: webbrowser.open(link))
            links_menu.addAction(action)

        menu_bar.addMenu(links_menu)

        # Log menu actions
        view_log_action = QAction("View Downloaded Log", self)
        view_log_action.triggered.connect(self.view_link_log)
        log_menu.addAction(view_log_action)
        menu_bar.addMenu(log_menu)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)  # Attach central widget to QMainWindow

        layout = QVBoxLayout()

        # UI setup
        search_layout = QHBoxLayout()
        self.search_type_combo = QComboBox()
        self.search_type_combo.addItems(["Search by keyword", "Search by subreddit name"])
        self.keyword_input = QLineEdit()
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_subreddits)
        search_layout.addWidget(self.search_type_combo)
        search_layout.addWidget(self.keyword_input)
        search_layout.addWidget(self.search_button)

        # Website detection
        self.detected_type_label = QLabel("Detected Type: None")
        layout.addWidget(self.detected_type_label)


        self.subreddit_list = QListWidget()

        # Number of images GUI
        self.count_container = QWidget()
        count_layout = QHBoxLayout()
        self.count_container.setLayout(count_layout)

        self.count_label = QLabel("Number of Images:")
        self.count_input = QComboBox()
        self.count_input.addItems(["5", "10", "20", "50", "100", "200", "All"])
        count_layout.addWidget(self.count_label)
        count_layout.addWidget(self.count_input)

        layout.addWidget(self.count_container)
        self.count_container.hide()

        # Filtering GUI
        self.filter_container = QWidget()
        filter_layout = QHBoxLayout()
        self.filter_container.setLayout(filter_layout)

        self.sfw_checkbox = QCheckBox("SFW")
        self.sfw_checkbox.setChecked(True)
        self.nsfw_checkbox = QCheckBox("NSFW")
        self.nsfw_checkbox.setChecked(True)
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.sfw_checkbox)
        filter_layout.addWidget(self.nsfw_checkbox)

        layout.addWidget(self.filter_container)
        self.filter_container.hide()  # Hide the filter container initially

        # Download button GUI
        self.download_button = QPushButton("Download Images")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.download_button.clicked.connect(self.download_images)

        # Mangement GUI
        manage_layout = QHBoxLayout()
        self.clear_cache_button = QPushButton("Clear All Caches")
        self.clear_cache_button.clicked.connect(self.clear_all_caches)
        self.clear_selected_cache_button = QPushButton("Clear Selected Cache")
        self.clear_selected_cache_button.clicked.connect(self.clear_selected_cache)
        self.clear_downloads_button = QPushButton("Clear Downloads")
        self.clear_downloads_button.clicked.connect(self.clear_master_folder)
        self.copy_downloads_button = QPushButton("Backup Master Folder")
        self.copy_downloads_button.clicked.connect(self.copy_master_folder)
        self.change_location_button = QPushButton("Change Download Location")
        self.change_location_button.clicked.connect(self.change_master_folder)
        manage_layout.addWidget(self.clear_cache_button)
        manage_layout.addWidget(self.clear_selected_cache_button)
        manage_layout.addWidget(self.clear_downloads_button)
        manage_layout.addWidget(self.copy_downloads_button)
        manage_layout.addWidget(self.change_location_button)


        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        layout.addLayout(search_layout)
        layout.addWidget(self.subreddit_list)
        layout.addWidget(self.download_button)
        layout.addLayout(manage_layout)
        layout.addWidget(QLabel("Log Output:"))
        layout.addWidget(self.log_output)

        central_widget.setLayout(layout)  # Set layout on central widget
    
    def change_master_folder(self):
        target_dir = QFileDialog.getExistingDirectory(self, "Select New Master Folder Location")
        if target_dir:
            self.master_folder = target_dir
            self.log(f"Master folder location changed to: {self.master_folder}")
        else:
            self.log("Master folder location not changed.")
    # --- Logging ---
    def log_downloaded_link(self, source: str, url: str):
        try:
            if os.path.exists(self.link_log_file):
                with open(self.link_log_file, "r") as f:
                    if any(url in line for line in f):
                        return  # URL already logged

            with open(self.link_log_file, "a") as f:
                f.write(f"[{source.upper()}] {url}\n")
        except Exception as e:
            self.log(f"Failed to log link: {e}")

    def view_link_log(self):
        try:
            if not os.path.exists(self.link_log_file):
                QMessageBox.information(self, "Link Log", "No log file found yet.")
                return

            with open(self.link_log_file, "r") as f:
                content = f.read()

            log_window = QMessageBox(self)
            log_window.setWindowTitle("Downloaded Links Log")
            log_window.setText("Here are your downloaded links:")
            log_window.setDetailedText(content)
            log_window.setStandardButtons(QMessageBox.Ok)
            log_window.exec_()
        except Exception as e:
            self.log(f"❌ Failed to open link log: {e}")

    def log(self, message):
        self.log_output.append(message)

    # Progress bar update
    def update_progress(self, current, total):
        if total == 0:
            self.progress_bar.setValue(0)
        else:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)


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
            self.log("All cache files deleted.")
        except Exception as e:
            self.log(f"Failed to clear caches: {e}")

    def clear_selected_cache(self):
        selected = self.subreddit_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Input Error", "Please select a subreddit to clear its cache.")
            return

        try:
            subreddit_name = selected.text().split()[1].replace("r/", "")
        except IndexError:
            self.log("Could not determine subreddit name from selection.")
            return

        safe_name = re.sub(r'[^\w\-]', '_', subreddit_name.lower())
        cache_file = os.path.join("cache", f"r_{safe_name}.txt")

        try:
            if os.path.exists(cache_file):
                os.remove(cache_file)
                self.log(f"Cache cleared for r/{subreddit_name}.")
            else:
                self.log(f"No cache file found for r/{subreddit_name}.")
        except Exception as e:
            self.log(f"Failed to clear cache for r/{subreddit_name}: {e}")

    def clear_master_folder(self):
        if not os.path.exists(self.master_folder):
            self.log("Master folder does not exist.")
            return

        try:
            for item in os.listdir(self.master_folder):
                path = os.path.join(self.master_folder, item)
                if os.path.isfile(path) or os.path.islink(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            self.log("All download contents deleted.")
        except Exception as e:
            self.log(f"Failed to clear downloads: {e}")

    def copy_master_folder(self):
        if not os.path.exists(self.master_folder):
            self.log("Master folder does not exist.")
            return

        target_dir = QFileDialog.getExistingDirectory(self, "Select Target Directory")
        if not target_dir:
            self.log("No target directory selected.")
            return

        try:
            dest_path = os.path.join(target_dir, os.path.basename(self.master_folder))
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.copytree(self.master_folder, dest_path)
            self.log(f"Master folder copied to {dest_path}")
        except Exception as e:
            self.log(f"Failed to copy master folder: {e}")

    async def download_erome_gallery(self, url):
        try:
            await self.dump(url=url, max_connections=5, skip_videos=False, skip_images=False)
            self.log_downloaded_link("EROME", url)
            self.log("Erome gallery downloaded.")
        except Exception as e:
            self.log(f"Erome download error: {e}")


    def download_images(self):
        selected = self.subreddit_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Input Error", "Please select a source from the list.")
            return

        text = selected.text().strip()

        if "erome.com" in text:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Progress: %p%")
            self.download_thread = DownloadEromeThread(
                text,
                self.master_folder,
                self._collect_album_data,
                self._download
            )
            self.download_thread.progress_updated.connect(self.update_progress)
            self.download_thread.log_message.connect(self.log)
            self.download_thread.start()
            self.log_downloaded_link("EROME", text)
            return


        if "boards.4chan.org" in text:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Progress: %p%")
            self.download_thread = Download4chanThread(text, self.master_folder)
            self.download_thread.progress_updated.connect(self.update_progress)
            self.download_thread.log_message.connect(self.log)
            self.download_thread.start()

            self.log_downloaded_link("4chan", text)
            return

        try:
            subreddit_name = text.split()[1].replace("r/", "")
        except IndexError:
            self.log("Could not determine subreddit name from selection.")
            return

        selected_limit = self.count_input.currentText()
        limit = None if selected_limit == "All" else int(selected_limit)
        allow_sfw = self.sfw_checkbox.isChecked()
        allow_nsfw = self.nsfw_checkbox.isChecked()

        self.progress_bar.setValue(0)
        self.thread = DownloaderThread(subreddit_name, limit, allow_sfw, allow_nsfw, self.master_folder, "cache")
        self.thread.progress_updated.connect(self.update_progress)
        self.thread.log_message.connect(self.log)
        self.thread.start()


    def download_images_blocking(self, text):
        try:
            subreddit_name = text.split()[1].replace("r/", "")
        except IndexError:
            self.log("Could not determine subreddit name from selection.")
            return

        selected_limit = self.count_input.currentText()
        limit = None if selected_limit == "All" else int(selected_limit)
        allow_sfw = self.sfw_checkbox.isChecked()
        allow_nsfw = self.nsfw_checkbox.isChecked()

        try:
            subreddit = reddit.subreddit(subreddit_name)
            self._log_threadsafe(f"Downloading up to {limit if limit else 'All'} images from r/{subreddit.display_name}...")

            subreddit_is_nsfw = subreddit.over18
            if (subreddit_is_nsfw and not allow_nsfw) or (not subreddit_is_nsfw and not allow_sfw):
                self._log_threadsafe("Subreddit does not match selected filter (SFW/NSFW). Skipping download.")
                return

            cache_folder = "cache"
            os.makedirs(self.master_folder, exist_ok=True)
            os.makedirs(cache_folder, exist_ok=True)

            safe_name = re.sub(r'[^\w\-]', '_', subreddit_name.lower())
            subfolder_name = f"r_{safe_name}"
            download_folder = os.path.join(self.master_folder, subfolder_name)
            os.makedirs(download_folder, exist_ok=True)

            cache_file = os.path.join(cache_folder, f"{subfolder_name}.txt")
            if os.path.exists(cache_file):
                with open(cache_file, "r") as f:
                    cached_urls = set(line.strip() for line in f if line.strip())
            else:
                cached_urls = set()

            posts = list(subreddit.hot(limit=1000))
            count = 0
            new_urls = []
            total_target = len(posts) if not limit else limit

            self._update_progress_safe(0, total_target)

            for i, post in enumerate(posts):
                url = post.url.strip()
                if url.lower().endswith((".jpg", ".jpeg", ".png", ".gif")) and url not in cached_urls:
                    try:
                        image_data = requests.get(url).content
                        extension = os.path.splitext(url)[1]
                        filename = os.path.join(download_folder, f"{subfolder_name}_{count}_{post.id}{extension}")
                        with open(filename, "wb") as f:
                            f.write(image_data)
                        self._log_threadsafe(f"Saved: {filename}")
                        count += 1
                        new_urls.append(url)
                        self._update_progress_safe(count, total_target)
                        if limit and count >= limit:
                            break
                    except Exception as e:
                        self._log_threadsafe(f"Failed to download {url}: {e}")

            if new_urls:
                with open(cache_file, "a") as f:
                    for url in new_urls:
                        f.write(url + "\n")

            if count == 0:
                self._log_threadsafe("No new images found (all duplicates).")
            else:
                self._log_threadsafe(f"{count} new images downloaded to '{os.path.abspath(download_folder)}'")

        except Exception as e:
            self._log_threadsafe(f"Error: {e}")


    async def download_4chan_thread(self, url):
        try:
            board = re.search(r"boards\.4chan\.org/([^/]+)/thread/", url)
            thread_id = re.search(r"thread/(\d+)", url)
            if not board or not thread_id:
                self.log("Invalid 4chan thread URL format.")
                return
            board, thread_id = board.group(1), thread_id.group(1)
            api_url = f"https://a.4cdn.org/{board}/thread/{thread_id}.json"
            media_url_base = f"https://i.4cdn.org/{board}/"
            save_path = Path(self.master_folder) / f"4chan_{board}_{thread_id}"
            save_path.mkdir(parents=True, exist_ok=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        self.log("Failed to fetch thread data.")
                        return
                    data = await resp.json()
                    images = [post for post in data.get("posts", []) if "tim" in post and "ext" in post]

                    for i, post in enumerate(images):
                        file_url = f"{media_url_base}{post['tim']}{post['ext']}"
                        file_path = save_path / f"{post['tim']}{post['ext']}"
                        async with session.get(file_url) as f:
                            if f.status == 200:
                                with open(file_path, "wb") as out:
                                    out.write(await f.read())
                                self.log(f"Saved: {file_path}")
                                self.log_downloaded_link("4chan", file_url)
                            else:
                                self.log(f"Failed to download: {file_url}")

            self.log(f"Downloaded {len(images)} images to {save_path}")

        except Exception as e:
            self.log(f"4chan download error: {e}")

    def search_subreddits(self):
        keyword = self.keyword_input.text().strip().lower()
        self.detected_type_label.setText("Detected Type: None")
        allow_sfw = self.sfw_checkbox.isChecked()
        allow_nsfw = self.nsfw_checkbox.isChecked()
        search_type = self.search_type_combo.currentText()
        self.filter_container.hide()
        self.count_container.show()

        self.subreddit_list.clear()

        if not keyword:
            QMessageBox.warning(self, "Input Error", "Please enter a keyword or subreddit name to search.")
            return

        # Auto-detect what website the user is trying to download from
        if "erome.com" in keyword:
            self.subreddit_list.clear()
            self.subreddit_list.addItem(keyword)
            self.detected_type_label.setText("Detected Type: Erome Gallery")
            self.count_container.hide()
            self.log("Erome gallery ready for download.")
            return

        elif "4chan.org" in keyword:
            self.subreddit_list.clear()
            self.subreddit_list.addItem(keyword)
            self.detected_type_label.setText("Detected Type: 4chan Thread")
            self.count_container.hide()
            self.log("4chan thread ready for download.")
            return


        try:
            results = []
            if search_type in ("Search by keyword", "Search by subreddit name"):
                search_type = self.search_type_combo.currentText()
                for subreddit in reddit.subreddits.search(keyword, limit=100):
                    if subreddit.subscribers is not None:
                        if subreddit.over18 and not allow_nsfw:
                            continue
                        if not subreddit.over18 and not allow_sfw:
                            continue
                        if search_type == "Search by subreddit name" and keyword not in subreddit.display_name.lower():
                            continue
                        results.append((subreddit.display_name, subreddit.title, subreddit.subscribers, subreddit.over18))
                        self.filter_container.show()
                        self.detected_type_label.setText("Detected Type: Reddit Subreddit Search")

            results.sort(key=lambda x: x[2], reverse=True)

            for name, title, subs, over18 in results:
                tag = "🔞" if over18 else "✅"
                self.subreddit_list.addItem(f"{tag} r/{name} ({subs:,} members) - {title}")

            if not results:
                self.log("No subreddits found matching your filters.")

        except Exception as e:
            self.log(f"Error searching subreddits: {e}")

# --- Utility Functions ---
    def _clean_album_title(self, title: str, default_title="temp") -> str:
        illegal_chars = r'[\\/:*?"<>|]'
        title = re.sub(illegal_chars, "_", title).strip(". ")
        return title if title else default_title


    def _get_final_download_path(self, album_title: str) -> Path:
        final_path = Path(self.master_folder) / album_title
        final_path.mkdir(parents=True, exist_ok=True)
        return final_path

    async def dump(self, url: str, max_connections: int, skip_videos: bool, skip_images: bool):
        if urlparse(url).hostname != EROME_HOST:
            raise ValueError(f"Host must be {EROME_HOST}")
        title, urls = await self._collect_album_data(url, skip_videos, skip_images)
        download_path = self._get_final_download_path(title)
        await self._download(url, urls, max_connections, download_path)

    async def _download(self, album: str, urls: list[str], max_connections: int, download_path: Path):
        semaphore = asyncio.Semaphore(max_connections)
        async with aiohttp.ClientSession(headers={"Referer": album, "User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=None)) as session:
            tasks = [
                self._download_file(session, url, semaphore, download_path)
                for url in urls
            ]
            await tqdm_asyncio.gather(*tasks, colour="MAGENTA", desc="Album Progress", unit="file", leave=True)

    async def _download_file(self, session: aiohttp.ClientSession, url: str, semaphore: asyncio.Semaphore, download_path: Path):
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

    async def _collect_album_data(self, url: str, skip_videos: bool, skip_images: bool) -> tuple[str, list[str]]:
        headers = {"User-Agent": USER_AGENT}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as response:
                soup = BeautifulSoup(await response.text(), "html.parser")
                title = self._clean_album_title(soup.find("meta", property="og:title")["content"])
                videos = [v["src"] for v in soup.find_all("source")] if not skip_videos else []
                images = [i["data-src"] for i in soup.find_all("img", class_="img-back")] if not skip_images else []
            return title, list(set(videos + images))
        
    def _log_threadsafe(self, message):
        QTimer.singleShot(0, lambda: self.log(message))

    def update_progress(self, current, total):
        if total == 0:
            self.progress_bar.setValue(0)
        else:
            percent = int((current / total) * 100)
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(percent)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RedditDownloaderGUI()
    window.show()
    sys.exit(app.exec_())
