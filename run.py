import sys
import os
import shutil
import subprocess
import hashlib
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
    # 0. Identify venv directory (support both .venv and venv)
    target_venv = VENV_DIR
    if not target_venv.exists() and (BASE_DIR / ".venv").exists():
        target_venv = BASE_DIR / ".venv"

    if is_venv():
        # Even if we are in a venv, we should verify dependencies
        print("[BOOTSTRAP] Environment check: Already in virtual environment. Verifying dependencies...")
        check_dependencies(sys.executable)
        return

    print("[BOOTSTRAP] Environment check: Using virtual environment...")
    
    # 1. Create venv if missing or broken
    is_broken = target_venv.exists() and not (target_venv / "pyvenv.cfg").exists()
    
    if not target_venv.exists() or is_broken:
        if is_broken:
            print(f"[BOOTSTRAP] Virtual environment directory '{target_venv.name}' exists but is corrupted.")
            print("[BOOTSTRAP] Attempting to repair/recreate...")
        else:
            print(f"[BOOTSTRAP] Creating virtual environment in {target_venv}...")
            
        try:
            subprocess.run([sys.executable, "-m", "venv", str(target_venv)], check=True)
            print("[BOOTSTRAP] Venv created/repaired.")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to create virtual environment: {e}")
            print("[TIP] Try deleting the 'venv' or '.venv' folder manually and running the script again.")
            sys.exit(1)

    # 2. Identify venv python
    if os.name == 'nt':
        venv_python = target_venv / "Scripts" / "python.exe"
    else:
        venv_python = target_venv / "bin" / "python"

    if not venv_python.exists():
        print(f"[ERROR] Could not find python in {venv_python}")
        sys.exit(1)

    # 3. Check/Install dependencies
    check_dependencies(venv_python, target_venv)

    # 4. Re-execute the script using the venv python
    print(f"[BOOTSTRAP] Switching to virtual environment python: {venv_python}")
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)

def check_dependencies(python_exe, venv_dir=None):
    """Verifies and installs dependencies if requirements.txt has changed."""
    requirements = BASE_DIR / "requirements.txt"
    
    # If venv_dir is not provided, try to find it from the python_exe path
    if venv_dir is None:
        # python_exe is usually venv/Scripts/python.exe or venv/bin/python
        python_path = Path(python_exe)
        if os.name == 'nt':
            venv_dir = python_path.parent.parent
        else:
            venv_dir = python_path.parent.parent
            
    hash_file = venv_dir / ".requirements_hash"
    
    if requirements.exists():
        # Calculate current hash
        with open(requirements, "rb") as f:
            current_hash = hashlib.md5(f.read()).hexdigest()
        
        # Check against stored hash
        stored_hash = ""
        if hash_file.exists():
            stored_hash = hash_file.read_text().strip()
            
        if current_hash != stored_hash:
            print("[BOOTSTRAP] Dependencies changed or not verified. Running pip install...")
            try:
                subprocess.run([str(python_exe), "-m", "pip", "install", "-r", str(requirements)], check=True)
                # Store the new hash only if pip succeeded
                hash_file.write_text(current_hash)
                print("[BOOTSTRAP] Dependencies updated and verified.")
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Pip install failed: {e}")
                # We don't exit here if we are already in the venv, but we might want to
                if not is_venv():
                    sys.exit(1)
        else:
            print("[BOOTSTRAP] Dependencies verified (cached).")

def bootstrap():
    print("--- Jasper Smart Bootstrap ---")
    
    # 1. Ensure .env exists
    print("[BOOTSTRAP] Step 1: Checking environment configuration (.env)...")
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        example_env = BASE_DIR / ".env.example"
        if example_env.exists():
            print("[BOOTSTRAP] .env missing. Creating from .env.example...")
            shutil.copy(example_env, env_file)
            print("[BOOTSTRAP] .env created.")
        else:
            print("[WARNING] .env.example not found. Please create .env manually.")
    else:
        print("[BOOTSTRAP] .env file verified.")

    # 2. Check Ollama Models
    print("[BOOTSTRAP] Step 2: Verifying Ollama models...")
    required_base_models = ["functiongemma:270m", "gemma3:4b"]
    custom_models = {
        "jasper": BASE_DIR / "jasper" / "utility" / "Modelfile",
        "gemma3": BASE_DIR / "jasper" / "utility" / "ModelfileGemma3"
    }
    
    try:
        # Check if ollama is available
        subprocess.run(["ollama", "--version"], capture_output=True, check=True)
        
        # Check existing models
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        installed_models = result.stdout.lower()
        
        # 1. Pull Base Models
        for model in required_base_models:
            if model.lower() not in installed_models:
                print(f"[BOOTSTRAP] Base model '{model}' not found. Pulling now (this may take a while)...")
                subprocess.run(["ollama", "pull", model], check=True)
            else:
                print(f"[BOOTSTRAP] Base model '{model}' verified.")
        
        # 2. Create Custom Models
        for model_name, modelfile_path in custom_models.items():
            if model_name.lower() not in installed_models:
                if modelfile_path.exists():
                    print(f"[BOOTSTRAP] Custom model '{model_name}' missing. Creating from {modelfile_path.name}...")
                    subprocess.run(["ollama", "create", model_name, "-f", str(modelfile_path)], check=True)
                    print(f"[BOOTSTRAP] Custom model '{model_name}' created successfully.")
                else:
                    print(f"[WARNING] Modelfile for '{model_name}' not found at {modelfile_path}")
            else:
                print(f"[BOOTSTRAP] Custom model '{model_name}' verified.")

    except Exception as e:
        print(f"[WARNING] Could not verify Ollama models: {e}")
        print("Please ensure Ollama is installed and running.")

    # 3. Ensure Semantic Index exists
    print("[BOOTSTRAP] Step 3: Verifying semantic index (ChromaDB)...")
    db_path = BASE_DIR / "chroma_db"
    if not db_path.exists():
        print("[BOOTSTRAP] Semantic Index not found. Building initial index (this may take a minute)...")
        try:
            from jasper.utility.indexer import main as run_indexer
            # Pass build command to the indexer's main
            sys.argv = ["indexer.py", "build"]
            run_indexer()
            print("[BOOTSTRAP] Initial index build complete.")
        except Exception as e:
            print(f"[ERROR] Failed to build initial index: {e}")
    else:
        print("[BOOTSTRAP] Semantic index verified.")

    print("--- Bootstrap Complete ---\n")

if __name__ == "__main__":
    import uvicorn
    import time
    
    # supervisor loop
    while True:
        try:
            # FIRST: Ensure we are in a proper environment (this might restart the script itself)
            ensure_venv()
            
            # SECOND: Run the functional bootstrap (models, index, config)
            bootstrap()
            
            # THIRD: Start the server
            print("[SERVER] Starting Jasper on http://localhost:8000")
            # We run uvicorn in a way that allows us to catch exits if possible, 
            # though uvicorn.run blocks.
            # If the user clicks "Restart" in the UI, our app will exit with code 0 or 3.
            # On Windows, os._exit(0) from a thread often terminates the whole process.
            uvicorn.run("jasper.app:app", host="0.0.0.0", port=8000, reload=True)
            
            # If we reach here, uvicorn finished normally (e.g. CTRL+C)
            break
            
        except SystemExit as e:
            # Catch os._exit or sys.exit
            if e.code == 0:
                print("[SUPERVISOR] Server requested restart. Re-bootstrapping...")
                time.sleep(1)
                continue
            else:
                raise
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[ERROR] Supervisor caught exception: {e}")
            time.sleep(2)
            continue
