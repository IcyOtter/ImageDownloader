import os
from dotenv import load_dotenv
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox

ENV_PATH = ".env"

class EnvSetupDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Reddit API Setup")
        self.inputs = {}
        layout = QVBoxLayout()

        fields = [
            ("REDDIT_CLIENT_ID", "Client ID"),
            ("REDDIT_CLIENT_SECRET", "Client Secret"),
            ("REDDIT_USER_AGENT", "User Agent"),
            ("REDDIT_USERNAME", "Username"),
            ("REDDIT_PASSWORD", "Password")
        ]

        for key, label in fields:
            layout.addWidget(QLabel(label))
            input_field = QLineEdit()
            if "PASSWORD" in key:
                input_field.setEchoMode(QLineEdit.Password)
            layout.addWidget(input_field)
            self.inputs[key] = input_field

        save_button = QPushButton("Save and Continue")
        save_button.clicked.connect(self.save_env)
        layout.addWidget(save_button)

        self.setLayout(layout)

    def save_env(self):
        try:
            with open(ENV_PATH, "w") as f:
                for key, field in self.inputs.items():
                    value = field.text().strip()
                    if not value:
                        QMessageBox.warning(self, "Input Error", f"{key} cannot be empty.")
                        return
                    f.write(f"{key}={value}\n")
            QMessageBox.information(self, "Success", ".env file created successfully!")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save .env file: {e}")

def get_reddit_client(parent=None):
    if not os.path.exists(ENV_PATH):
        dialog = EnvSetupDialog()
        if parent:
            dialog.setParent(parent)
        if dialog.exec_() != QDialog.Accepted:
            raise Exception("Setup canceled by user")

    load_dotenv(ENV_PATH)

    import praw
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD")
    )
