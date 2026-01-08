import sys
import os
import shutil
import subprocess
from pathlib import Path

# Add the current directory to sys.path to ensure 'jasper' is importable
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

def bootstrap():
    print("--- Jasper Smart Bootstrap ---")
    
    # 1. Ensure .env exists
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        example_env = BASE_DIR / ".env.example"
        if example_env.exists():
            print("[BOOTSTRAP] .env missing. Creating from .env.example...")
            shutil.copy(example_env, env_file)
        else:
            print("[WARNING] .env.example not found. Please create .env manually.")

    # 2. Check Ollama Models
    required_models = ["functiongemma", "gemma3:4b"]
    try:
        # Check if ollama is available
        subprocess.run(["ollama", "--version"], capture_output=True, check=True)
        
        # Check existing models
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        installed_models = result.stdout.lower()
        
        for model in required_models:
            if model.lower() not in installed_models:
                print(f"[BOOTSTRAP] Model '{model}' not found. Pulling now (this may take a while)...")
                subprocess.run(["ollama", "pull", model], check=True)
            else:
                print(f"[BOOTSTRAP] Model '{model}' verified.")
    except Exception as e:
        print(f"[WARNING] Could not verify Ollama models: {e}")
        print("Please ensure Ollama is installed and running.")

    # 3. Ensure Semantic Index exists
    db_path = BASE_DIR / "chroma_db"
    if not db_path.exists():
        print("[BOOTSTRAP] Semantic Index not found. Building initial index...")
        try:
            from jasper.utility.indexer import main as run_indexer
            # Pass build command to the indexer's main
            sys.argv = ["indexer.py", "build"]
            run_indexer()
        except Exception as e:
            print(f"[ERROR] Failed to build initial index: {e}")

    print("--- Bootstrap Complete ---\n")

if __name__ == "__main__":
    bootstrap()
    
    import uvicorn
    # Use the string-based import for uvicorn to support hot-reloading if needed
    uvicorn.run("jasper.app:app", host="0.0.0.0", port=8000, reload=True)
