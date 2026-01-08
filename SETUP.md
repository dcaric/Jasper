# Jasper Project Setup Guide (V1.1)

Jasper V1.1 features a **Smart Bootstrapper** that handles most of the configuration and data initialization for you.

## 1. Prerequisites
- **Python 3.13+** (ensure it's in your PATH).
- **Ollama** installed and running (from [ollama.com](https://ollama.com)).
- **Outlook Classic** (signed in) if you plan to use the "OUTLOOK" provider mode via COM.

## 2. Quick Start (Process for New Users)
1.  **Clone the Repository**.
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run Jasper**:
    ```bash
    python run.py
    ```
    - **What happens next?** Jasper will automatically:
        - Create your `.env` file from the example template.
        - Verify and pull the required AI models (`functiongemma` and `gemma3:4b`).
        - Build your initial semantic search index if it doesn't exist.
        - Start the web dashboard at `http://localhost:8000`.

## 3. Configuration (Optional Tweaks)
While Jasper bootstraps automatically, you may want to customize your setup:

### Secrets (.env)
Edit the newly created `.env` file to add:
- `GEMINI_API_KEY`: Get one at [Google AI Studio](https://aistudio.google.com/).
- `GMAIL_PASS`: Your Google App Password.

### Settings (constants.json)
Edit `constants.json` for:
- `"PROVIDER"`: Change between `"GMAIL"` and `"OUTLOOK"`.
- `"USER_NAME"`: Your Windows profile name for file path resolution.

## 4. Automation & Background Service
To ensure Jasper stays updated and runs in the background:
1.  **Configure Automation**: 
    - Open a terminal in the `startup` folder.
    - Run `setup_automation.bat` as Administrator.
    - This schedules indexing to run periodically in the background.

## 5. Manual Index Management
You can also manage the index manually via the CLI:
```bash
python -m jasper.utility.indexer status   # View index stats
python -m jasper.utility.indexer refresh  # Incremental update
python -m jasper.utility.indexer build    # Full rebuild
```
