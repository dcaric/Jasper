import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project (one level up from jasper/utility/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env file from the base directory
load_dotenv(BASE_DIR / ".env")

def get_config_path():
    """Returns the absolute path to constants.json in the project root."""
    return BASE_DIR / "constants.json"

def get_db_path():
    """Returns the absolute path to the ChromaDB directory."""
    return str(BASE_DIR / "chroma_db")

def get_status_file():
    """Returns the absolute path to .index_status."""
    return str(BASE_DIR / ".index_status")

def get_log_file():
    """Returns the absolute path to debug.log."""
    return str(BASE_DIR / "debug.log")

def get_setting(name, default=None):
    """
    Retrieves a setting with the following priority:
    1. Environment Variable (highest)
    2. constants.json
    3. Default value (lowest)
    """
    # 1. Check ENV
    val = os.getenv(name)
    
    # Ignore placeholders starting with 'your-'
    if val and not val.lower().startswith(("your-", "your_")):
        return val
    
    # 2. Check constants.json
    try:
        with open(get_config_path(), "r") as f:
            config = json.load(f)
            # Filter constants.json values too, just in case
            v = config.get(name, default)
            if isinstance(v, str) and v.lower().startswith(("your-", "your_")):
                return default
            return v
    except:
        return default

def get_credentials(provider="GMAIL"):
    """
    Retrieves credentials for the specified provider.
    Priority: ENV vars, then constants.json.
    """
    if provider == "OUTLOOK":
        user = get_setting("OUTLOOK_USER") or get_setting("GMAIL_USER")
        password = get_setting("OUTLOOK_PASS") or get_setting("OUTLOOK_PASSWORD")
    else:
        user = get_setting("GMAIL_USER")
        password = get_setting("GMAIL_PASS")
    
    if password:
        password = password.replace(" ", "")
    return user, password
