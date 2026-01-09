import requests
import time

try:
    print("Triggering Restart...")
    resp = requests.post("http://localhost:8000/restart")
    print(resp.json())
except Exception as e:
    print(f"Error triggering restart: {e}")
    
print("Waiting for 5 seconds...")
time.sleep(5)
