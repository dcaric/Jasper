from pathlib import Path
import subprocess
import os
import shutil
import sys

BASE_DIR = Path(os.getcwd())

def bootstrap():
    print("--- Jasper Smart Bootstrap Test ---")
    
    # 1. Ensure .env exists
    print("[BOOTSTRAP] Step 1: Checking environment configuration (.env)...")
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        print("[BOOTSTRAP] .env missing.")
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
        print("Checking ollama version...")
        subprocess.run(["ollama", "--version"], capture_output=True, check=True)
        print("Ollama version check passed.")
        
        # Check existing models
        print("Listing ollama models...")
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        installed_models = result.stdout.lower()
        print("Model list length:", len(installed_models))
        
        # 1. Pull Base Models
        for model in required_base_models:
            if model.lower() not in installed_models:
                print(f"[BOOTSTRAP] Base model '{model}' not found. (Skipping pull in test)")
            else:
                print(f"[BOOTSTRAP] Base model '{model}' verified.")
        
        # 2. Create Custom Models
        for model_name, modelfile_path in custom_models.items():
            if model_name.lower() not in installed_models:
                print(f"[BOOTSTRAP] Custom model '{model_name}' missing. (Skipping create in test)")
            else:
                print(f"[BOOTSTRAP] Custom model '{model_name}' verified.")

    except Exception as e:
        print(f"[WARNING] Could not verify Ollama models: {e}")

    # 3. Ensure Semantic Index exists
    print("[BOOTSTRAP] Step 3: Verifying semantic index (ChromaDB)...")
    db_path = BASE_DIR / "chroma_db"
    if not db_path.exists():
        print("[BOOTSTRAP] Semantic Index not found.")
    else:
        print("[BOOTSTRAP] Semantic index verified.")

    print("--- Bootstrap Test Complete ---\n")

if __name__ == "__main__":
    bootstrap()
