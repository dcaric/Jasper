import os
import time
import json
from datetime import datetime
print(f"[{datetime.now()}] [BOOT] Jasper App is loading... FINGERPRINT: 4433221100")
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .utility.config import get_log_file, get_status_file, BASE_DIR, log_event
from .utility.usage import calculate_cost
from . import state
from . import query_handler

app = FastAPI()

# Mount static files
static_path = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_path):
    os.makedirs(static_path)
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open(os.path.join(static_path, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_json():
    return {}

@app.post("/query")
async def process_query(request: Request):
    return await query_handler.process_query(request)

@app.post("/stop")
async def stop_execution():
    state.STOP_CODING_FLAG = True
    log_event("SYSTEM", "Stop signal received.")
    return {"status": "ok", "message": "Stop signal sent."}

@app.post("/open")
async def open_email(request: Request):
    try:
        body = await request.json()
        idx = body.get("id")
        provider = body.get("provider", "GMAIL")
        
        if provider == "OUTLOOK" and idx:
            success, msg = state.connectors["mail_outlook"].open(idx)
            if success:
                return {"status": "ok", "message": "Opened in Outlook"}
            else:
                return JSONResponse(content={"status": "error", "message": msg}, status_code=500)
        elif provider == "FILES" and idx:
            success, msg = state.connectors["files"].open(idx)
            if success:
                return {"status": "ok", "message": "File opened"}
            else:
                return JSONResponse(content={"status": "error", "message": msg}, status_code=500)
        else:
            return {"status": "ignored", "message": "Not an Outlook item or file, or no ID"}
            
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

@app.post("/restart")
async def restart_service():
    try:
        import threading
        def kill_self():
            import sys
            time.sleep(1)
            print("RESTART TRIGGERED: Exiting process for auto-restart...")
            sys.exit(0)
            
        threading.Thread(target=kill_self).start()
        return {"status": "ok", "message": "Restarting Jasper..."}
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

@app.get("/api/logs")
async def get_logs():
    """Returns the last 100 lines of the debug log."""
    try:
        log_file = get_log_file()
        if not os.path.exists(log_file):
            return {"logs": []}
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            last_lines = lines[-500:]
            last_lines.reverse()
            return {"logs": [line.strip() for line in last_lines if line.strip()]}
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

@app.get("/index-status")
async def get_index_status():
    """Provides the current indexing percentage for the UI."""
    try:
        status_file = get_status_file()
        if os.path.exists(status_file):
            with open(status_file, "r") as f:
                return json.load(f)
        else:
            return {"percent": 100, "status": "Idle"}
    except Exception as e:
        return {"percent": 0, "status": "Error", "error": str(e)}

@app.get("/coding-status")
async def get_coding_status():
    """Returns the current persistent coding mode status."""
    return {"coding_mode": state.CODING_MODE}

@app.get("/gemini-cost")
async def get_gemini_cost():
    """Returns the current total cost of Gemini usage."""
    cost = calculate_cost()
    return {"cost": round(cost, 4)}

@app.post("/refresh-index")
async def refresh_index_endpoint(background_tasks: BackgroundTasks):
    """Triggers an indexing process in a background task."""
    try:
        from .utility.indexer import index_all
        background_tasks.add_task(index_all, force=True)
        with open(get_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] [INDEXER] Background indexing task queued.\n")
        return {"status": "ok", "message": "Indexing started in background..."}
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
