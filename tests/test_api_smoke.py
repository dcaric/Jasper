import requests
import json

BASE_URL = "http://localhost:8000"

def test_api_health():
    print("--- API Health Check ---")
    try:
        # Just check if server is up
        response = requests.get(BASE_URL, timeout=5)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("SUCCESS: Jasper Backend is online.")
    except Exception as e:
        print(f"FAILED: Could not reach backend at {BASE_URL}. Error: {e}")

def test_basic_query():
    print("\n--- Basic Intent Extraction Test ---")
    url = f"{BASE_URL}/query"
    # Use generic queries that don't depend on user data
    queries = [
        "hi",
        "search for content 'Jasper'"
    ]
    
    for q in queries:
        try:
            print(f"Testing Query: '{q}'")
            resp = requests.post(url, json={"query": q}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                print(f"SUCCESS: Received response type '{data.get('type')}'")
            else:
                print(f"FAILED: Status {resp.status_code}")
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    test_api_health()
    test_basic_query()
