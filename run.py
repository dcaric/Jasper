import sys
import os
import shutil
import subprocess
from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

VENV_DIR = BASE_DIR / "venv"

def is_venv():
    """Checks if the script is currently running inside a virtual environment."""
    return (
        hasattr(sys, 'real_prefix') or
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )

def ensure_venv():
    """
    Ensures that a virtual environment exists and has dependencies installed.
    If not running in venv, it restarts itself with the venv python.
    """
    if is_venv():
        return # Already in venv

    print("[BOOTSTRAP] Environment check: Not in a virtual environment.")
    
    # 1. Create venv if missing
    if not VENV_DIR.exists():
        print(f"[BOOTSTRAP] Creating virtual environment in {VENV_DIR}...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
        print("[BOOTSTRAP] Venv created.")

    # 2. Identify venv python
    if os.name == 'nt':
        venv_python = VENV_DIR / "Scripts" / "python.exe"
    else:
        venv_python = VENV_DIR / "bin" / "python"

    if not venv_python.exists():
        print(f"[ERROR] Could not find python in {venv_python}")
        sys.exit(1)

    # 3. Check/Install dependencies
    requirements = BASE_DIR / "requirements.txt"
    if requirements.exists():
        print("[BOOTSTRAP] Verifying dependencies (pip install)...")
        # We run pip install to ensure everything is there. 
        # Pip is smart enough to skip if already satisfied.
        subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(requirements)], check=True)

    # 4. Re-execute the script using the venv python
    print("[BOOTSTRAP] Restarting within virtual environment...\n")
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)

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
    # FIRST: Ensure we are in a proper environment
    ensure_venv()
    
    # SECOND: Run the functional bootstrap (models, index, config)
    bootstrap()
    
    # THIRD: Start the server
    import uvicorn
    # Use the string-based import for uvicorn to support hot-reloading if needed
    uvicorn.run("jasper.app:app", host="0.0.0.0", port=8000, reload=True)
