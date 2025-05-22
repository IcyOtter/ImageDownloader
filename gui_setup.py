# gui_setup.py
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QLineEdit,
    QTextEdit, QMessageBox, QCheckBox, QListWidget, QComboBox, QFileDialog,
    QMenu, QAction, QProgressBar
)
import webbrowser

def setup_gui(main_window):
    # Central widget setup
    central_widget = QWidget()
    main_window.setCentralWidget(central_widget)
    layout = QVBoxLayout()

    # Store widgets on main_window instance
    main_window.detected_type_label = QLabel("Detected Type: None")
    layout.addWidget(main_window.detected_type_label)

    # Subreddit list
    main_window.subreddit_list = QListWidget()

    # Count selection
    main_window.count_container = QWidget()
    count_layout = QHBoxLayout()
    main_window.count_container.setLayout(count_layout)
    main_window.count_label = QLabel("Number of Images:")
    main_window.count_input = QComboBox()
    main_window.count_input.addItems(["5", "10", "20", "50", "100", "200", "All"])
    count_layout.addWidget(main_window.count_label)
    count_layout.addWidget(main_window.count_input)
    main_window.count_container.hide()

    # Filter checkboxes
    main_window.filter_container = QWidget()
    filter_layout = QHBoxLayout()
    main_window.filter_container.setLayout(filter_layout)
    main_window.sfw_checkbox = QCheckBox("SFW")
    main_window.nsfw_checkbox = QCheckBox("NSFW")
    main_window.sfw_checkbox.setChecked(True)
    main_window.nsfw_checkbox.setChecked(True)
    filter_layout.addWidget(QLabel("Filter:"))
    filter_layout.addWidget(main_window.sfw_checkbox)
    filter_layout.addWidget(main_window.nsfw_checkbox)
    main_window.filter_container.hide()

    # Search bar
    search_layout = QHBoxLayout()
    main_window.search_type_combo = QComboBox()
    main_window.search_type_combo.addItems(["Search by keyword", "Search by subreddit name"])
    main_window.keyword_input = QLineEdit()
    main_window.search_button = QPushButton("Search")
    search_layout.addWidget(main_window.search_type_combo)
    search_layout.addWidget(main_window.keyword_input)
    search_layout.addWidget(main_window.search_button)

    # Download and progress
    main_window.download_button = QPushButton("Download Images")
    main_window.progress_bar = QProgressBar()
    main_window.progress_bar.setValue(0)

    # Log display
    main_window.log_output = QTextEdit()
    main_window.log_output.setReadOnly(True)

    # Management buttons
    manage_layout = QHBoxLayout()
    main_window.clear_cache_button = QPushButton("Clear All Caches")
    main_window.clear_selected_cache_button = QPushButton("Clear Selected Cache")
    main_window.clear_downloads_button = QPushButton("Clear Downloads")
    main_window.copy_downloads_button = QPushButton("Backup Master Folder")
    main_window.change_location_button = QPushButton("Change Download Location")
    for btn in [
        main_window.clear_cache_button,
        main_window.clear_selected_cache_button,
        main_window.clear_downloads_button,
        main_window.copy_downloads_button,
        main_window.change_location_button
    ]:
        manage_layout.addWidget(btn)

    # Final layout
    layout.addLayout(search_layout)
    layout.addWidget(main_window.subreddit_list)
    layout.addWidget(main_window.count_container)
    layout.addWidget(main_window.filter_container)
    layout.addWidget(main_window.download_button)
    layout.addWidget(main_window.progress_bar)
    layout.addLayout(manage_layout)
    layout.addWidget(QLabel("Log Output:"))
    layout.addWidget(main_window.log_output)

    central_widget.setLayout(layout)

def setup_menu(main_window):
    menu_bar = main_window.menuBar()

    # --- Links Menu ---
    links_menu = menu_bar.addMenu("Links")
    websites = {
        "Reddit": "https://www.reddit.com",
        "Erome": "https://www.erome.com",
        "4chan": "https://boards.4chan.org",
    }

    for name, url in websites.items():
        action = QAction(name, main_window)
        action.triggered.connect(lambda checked, link=url: webbrowser.open(link))
        links_menu.addAction(action)

    # --- Log Menu ---
    log_menu = menu_bar.addMenu("Log")
    view_log_action = QAction("View Downloaded Log", main_window)
    view_log_action.triggered.connect(main_window.view_link_log)
    log_menu.addAction(view_log_action)