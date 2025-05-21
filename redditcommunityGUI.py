import sys
import os
import re
import requests
import praw
import shutil
from dotenv import load_dotenv
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QLineEdit, QTextEdit, QSpinBox, QMessageBox, QCheckBox, QListWidget, QComboBox, QFileDialog
)

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
        self.setWindowTitle("Reddit Image Downloader")
        self.setMinimumWidth(600)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Search type and keyword input
        search_layout = QHBoxLayout()
        self.search_type_combo = QComboBox()
        self.search_type_combo.addItems(["Search by keyword", "Search by subreddit name"])
        self.keyword_input = QLineEdit()
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_subreddits)
        search_layout.addWidget(self.search_type_combo)
        search_layout.addWidget(self.keyword_input)
        search_layout.addWidget(self.search_button)

        # Subreddit selection list
        self.subreddit_list = QListWidget()

        # Image count input
        count_layout = QHBoxLayout()
        self.count_label = QLabel("Number of images:")
        self.count_input = QSpinBox()
        self.count_input.setRange(1, 100)
        self.count_input.setValue(5)
        count_layout.addWidget(self.count_label)
        count_layout.addWidget(self.count_input)

        # NSFW/SFW filter checkboxes
        filter_layout = QHBoxLayout()
        self.sfw_checkbox = QCheckBox("SFW")
        self.sfw_checkbox.setChecked(True)
        self.nsfw_checkbox = QCheckBox("NSFW")
        self.nsfw_checkbox.setChecked(True)
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.sfw_checkbox)
        filter_layout.addWidget(self.nsfw_checkbox)

        # Download button
        self.download_button = QPushButton("Download Images")
        self.download_button.clicked.connect(self.download_images)

        # Cache and folder management buttons
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

        # Log output area
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        # Assemble layout
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

    def search_subreddits(self):
        keyword = self.keyword_input.text().strip().lower()
        allow_sfw = self.sfw_checkbox.isChecked()
        allow_nsfw = self.nsfw_checkbox.isChecked()
        search_type = self.search_type_combo.currentText()

        if not keyword:
            QMessageBox.warning(self, "Input Error", "Please enter a keyword or subreddit name to search.")
            return

        self.subreddit_list.clear()
        try:
            results = []
            if search_type == "Search by keyword" or search_type == "Search by subreddit name":
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

    def copy_master_folder(self):
        src = "communitydownloader"
        if not os.path.exists(src):
            self.log("Master folder does not exist.")
            return

        dest = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if not dest:
            self.log("Copy cancelled.")
            return

        dest_path = os.path.join(dest, os.path.basename(src))
        try:
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.copytree(src, dest_path)
            self.log(f"✅ Master folder copied to: {dest_path}")
        except Exception as e:
            self.log(f"❌ Failed to copy master folder: {e}")

    def download_images(self):
        selected = self.subreddit_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Input Error", "Please select a subreddit from the list.")
            return

        subreddit_name = selected.text().split()[1].replace("r/", "")
        limit = self.count_input.value()

        allow_sfw = self.sfw_checkbox.isChecked()
        allow_nsfw = self.nsfw_checkbox.isChecked()

        try:
            subreddit = reddit.subreddit(subreddit_name)
            self.log(f"\nDownloading up to {limit} new images from r/{subreddit.display_name}...")

            subreddit_is_nsfw = subreddit.over18
            if (subreddit_is_nsfw and not allow_nsfw) or (not subreddit_is_nsfw and not allow_sfw):
                self.log("❌ Subreddit does not match selected filter (SFW/NSFW). Skipping download.")
                return

            master_folder = "communitydownloader"
            cache_folder = "cache"
            os.makedirs(master_folder, exist_ok=True)
            os.makedirs(cache_folder, exist_ok=True)

            safe_name = re.sub(r'[^\w\-]', '_', subreddit_name.lower())
            subfolder_name = f"r_{safe_name}"
            download_folder = os.path.join(master_folder, subfolder_name)
            os.makedirs(download_folder, exist_ok=True)

            cache_file = os.path.join(cache_folder, f"{subfolder_name}.txt")
            if os.path.exists(cache_file):
                with open(cache_file, "r") as f:
                    cached_urls = set(line.strip() for line in f if line.strip())
            else:
                cached_urls = set()

            count = 0
            new_urls = []
            for post in subreddit.hot(limit=100):
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
                        if count >= limit:
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
                self.log(f"\n{count} new images downloaded to '{os.path.abspath(download_folder)}'")

        except Exception as e:
            self.log(f"❌ Error: {e}")

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

        subreddit_name = selected.text().split()[1].replace("r/", "")
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
        master_folder = "communitydownloader"
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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RedditDownloaderGUI()
    window.show()
    sys.exit(app.exec_())