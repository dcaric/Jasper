import subprocess
import os

print("--- Testing Ollama Commands ---")
try:
    print("Testing 'ollama --version'...")
    res1 = subprocess.run(["ollama", "--version"], capture_output=True, check=True)
    print(f"Result: {res1.stdout.decode().strip()}")
    
    print("Testing 'ollama list'...")
    res2 = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    print("Model list received.")
    print(res2.stdout)
    
except Exception as e:
    print(f"Error: {e}")
print("--- Test Complete ---")
