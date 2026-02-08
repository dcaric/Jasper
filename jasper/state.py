import os
import ollama
from .utility.config import get_setting, BASE_DIR
from .tools.mail.gmail_connector import GmailConnector
from .tools.mail.outlook_connector import OutlookConnector
from .tools.filemanager.file_connector import FileConnector
from .utility.semantic_connector import SemanticConnector

MODEL_NAME = "jasper"

def get_coding_state():
    """Reads the current coding mode state from a persistent file."""
    state_file = os.path.join(BASE_DIR, ".coding_mode")
    if os.path.exists(state_file):
        with open(state_file, "r") as f:
            return f.read().strip() == "ON"
    return False

def set_coding_state(is_on):
    """Saves the current coding mode state to a persistent file."""
    state_file = os.path.join(BASE_DIR, ".coding_mode")
    with open(state_file, "w") as f:
        f.write("ON" if is_on else "OFF")

CODING_MODE = get_coding_state()
STOP_CODING_FLAG = False

# Connector Registry
connectors = {
    "mail_gmail": GmailConnector(),
    "mail_outlook": OutlookConnector(),
    "files": FileConnector(),
    "semantic": SemanticConnector()
}
