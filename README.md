# Jasper - AI Assistant

Jasper is a high-performance AI agent that helps you search and summarize your emails using the `FunctionGemma:270M` model.

## Features
- **WhatsApp-style Web UI**: Modern, responsive, and legible design.
- **Multi-Provider Support**: Works with **Gmail (IMAP)** and **Outlook Classic (COM)**.
- **Semantic Content Search**: Search *inside* files (HTML, JS, CSS, TXT) using AI-powered meaning matching (ChromaDB).
- **Deep Linking**: Open emails or files directly with one click.
- **Background Service**: Runs silently in the background and starts automatically with Windows.

## Installation & Setup
For a complete step-by-step setup on a new machine, please see [SETUP.md](./SETUP.md).

Quick start:
1. Clone the repo.
2. `pip install -r requirements.txt`
3. Copy `constants.json.example` to `constants.json`.
4. Run `setup_automation.bat` as Administrator.

## Configuration
Jasper detects your email provider automatically based on your `constants.json` settings:

### Option A: Gmail (Personal)
Set `"PROVIDER": "GMAIL"` in `constants.json`.
- Enable IMAP in Gmail.
- Use a Google "App Password" for the `GMAIL_PASS` field.

### Option B: Outlook Classic (Company)
Set `"PROVIDER": "OUTLOOK"` in `constants.json`.
- Requires **Outlook Classic** (not the "New Outlook" web-app version).
- Ensure Outlook is signed in on your laptop.

## Usage
- **Start Jasper**: Run `run_web.ps1`.
- **Open Dashboard**: Go to [http://localhost:8000](http://localhost:8000).
- **Auto-Startup**: Set Jasper to start at login by running this in an Administrator PowerShell window:
  ```powershell
  Set-Location "path\to\Jasper"
  & .\install_as_startup.ps1
  ```
  *(Jasper will automatically use its current location for the startup task)*

## UI Scaling
Jasper uses a **Comfortable 18px Scale** for maximum readability on all screens.


## benefits
1. Unified Intelligence (The "One Brain" Effect)
In a standard setup, your Files, Gmail, and Outlook are three separate silos.

Without Jasper: You search for "Hvar project" in File Explorer, find nothing, then switch to Outlook, search there, then switch to Gmail.
With Jasper: You ask once. Jasper is cross-platform. It can search across your local drive AND your cloud services (Gmail/Outlook) simultaneously. Windows Search natively cannot "reach into" your Gmail inbox.
2. Natural Language Date Filtering
Standard search bars are actually quite bad at dates. Try searching for "Friday before last" in File Explorer; it won't work. Jasper uses the date_utils.py logic we built to turn human phrases into precise SQL timestamps. It makes finding "that file from a few weeks ago" much less of a chore.

3. "Dumb" to "Smart" Fallback
As we saw with the ML folder, the native Windows Search Indexer is a bit of a "black box"—if it decides not to index a folder, you're out of luck. Because we wrote the code, we inserted that Surgical Fallback. Jasper is "smart" enough to say: "The database says it's not there, but I know where the user works, let me go manually check the ML folder just in case."

4. Preparation for the "Action Layer"
This is the most important part for the future. Native search is a Dead End: you find the file, and that's it. Jasper's search is an Entry Point:

Native Search: "Find the invoice." -> You find it.
Jasper: "Find the last invoice from Dario and tell me the total amount." Because the search results are in Python code, we can pipe that file content directly into a summarizer or an action (like drafting a reply email).
5. Semantic Search (The Next Step)
By having this infrastructure, we are 90% of the way to True Semantic Search. Once we add a Vector DB (ChromaDB/FAISS), you'll be able to search for "budget stuff" and it will find a spreadsheet named 2024_projections.xlsx because it understands the meaning of the content, not just the filename.

In short: Outlook and File Explorer are "Search Tools." Jasper is a "Knowledge Hub" that connects the dots between your different worlds.