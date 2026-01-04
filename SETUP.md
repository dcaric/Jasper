# Jasper Project Setup Guide

Follow these steps to set up Jasper on a new machine.

## 1. Prerequisites
- **Python 3.13+** (ensure it's in your PATH).
- **Outlook Classic** (signed in) for "OUTLOOK" provider mode.
- **Ollama** installed (from [ollama.com](https://ollama.com)).

## 2. Repository Setup
1. Clone the repository.
2. Open a terminal in the project folder and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## 3. Ollama Models Setup
Jasper uses a custom alias for the model to remain compatible across different versions.
1. Download the base model:
   ```bash
   ollama pull functiongemma:270m
   ```
2. Create the `functiongemma` alias:
   ```bash
   ollama create functiongemma -f utility/Modelfile
   ```
   *(Note: Ensure you have a `Modelfile` in the `utility` folder that points to `FROM functiongemma:270m`)*

## 4. Configuration
1. Copy `constants.json.example` to `constants.json`.
2. Edit `constants.json` with your details:
   - `PROVIDER`: Set to `"GMAIL"` or `"OUTLOOK"`.
   - `GMAIL_USER` / `GMAIL_PASS`: Your Gmail address and App Password (if using Gmail).
   - `OUTLOOK_USER` / `OUTLOOK_PASS`: Your Outlook/Hotmail credentials (if using IMAP mode).
   - `GEMINI_API_KEY`: Required for Jasper to check the web/news.
   - `USER_NAME`: Your Windows login name (used for file search fallbacks).

## 5. Automation & Indexing Setup
To set up the automatic indexing at 9 AM and 1 PM:
1. Navigate to the `startup` folder.
2. Right-click `setup_automation.bat` and **Run as Administrator**.
   - This script will detect your Python path and create the necessary Windows Scheduled Tasks.
3. Run an initial index manually to build the search database:
   ```bash
   python utility/indexer.py
   ```

## 6. How to Run
- **Start the Server**: Run `python app.py`.
- **Open the UI**: Navigate to `http://localhost:8000` in your browser.

## Project Structure
- `app.py`: Main FastAPI server and AI logic.
- `mail/`: Gmail and Outlook search logic.
- `utility/`: Indexer, semantic search tools, and config models.
- `filemanager/`: Local file search and management.
- `startup/`: Service runners and automation scripts.
- `/static`: The web dashboard files.
- `/chroma_db`: Local persistent memory (created after first index).
