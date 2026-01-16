import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project (one level up from jasper/utility/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env file from the base directory
load_dotenv(BASE_DIR / ".env")

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
    Retrieves a setting with the highest priority:
    Environment Variable (highest) -> Default value (lowest)
    """
    # Check ENV
    val = os.getenv(name)
    
    # Ignore placeholders starting with 'your-'
    if val and not val.lower().startswith(("your-", "your_")):
        return val
    
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

def get_index_paths():
    """
    Returns a list of absolute paths to index.
    Priority: INDEX_PATHS env/const (comma-separated), then current workspace.
    """
    paths_str = get_setting("INDEX_PATHS")
    if paths_str:
        return [str(Path(p.strip()).absolute()) for p in paths_str.split(",") if p.strip()]
    
    # Default: the project root
    return [str(BASE_DIR)]
