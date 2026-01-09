import requests
import json

url = "http://localhost:8000/query"
payload = {
    "query": "search gmail for sonja for last 3 days"
}
headers = {
    "Content-Type": "application/json; charset=utf-8"
}

print(f"Sending search for 'sonja' to {url}...")
try:
    response = requests.post(url, json=payload, headers=headers)
    print(f"Status: {response.status_code}")
    
    data = response.json()
    items = data.get("data", [])
    if items:
        print(f"SUCCESS: Found {len(items)} items!")
        for item in items:
            print(f"- {item.get('sender')}: {item.get('subject')}")
    else:
        print("RESULT: No items found.")
        
except Exception as e:
    print(f"ERROR: {e}")
