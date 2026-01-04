import requests
import os
import json

BASE_URL = "http://127.0.0.1:8000"

def test_summarize():
    print("--- Testing /summarize Endpoint ---")
    
    # Use README.md as the target
    target_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "README.md"))
    if not os.path.exists(target_file):
        print(f"Error: Target file {target_file} not found.")
        return

    print(f"Target File: {target_file}")
    
    payload = {"path": target_file}
    
    try:
        response = requests.post(f"{BASE_URL}/summarize", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                print("\nSUCCESS! Summary received:")
                print("-" * 40)
                print(data.get("summary"))
                print("-" * 40)
            else:
                print(f"\nFAILED: API returned error status: {data}")
        else:
            print(f"\nFAILED: HTTP {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"\nEXCEPTION: {e}")

if __name__ == "__main__":
    test_summarize()
