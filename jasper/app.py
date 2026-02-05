import os
import re
import ollama
import traceback
import json
import time
from datetime import datetime
print(f"[{datetime.now()}] [BOOT] Jasper App is loading... FINGERPRINT: 4433221100")
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .utility.config import get_setting, get_log_file, get_status_file, BASE_DIR, log_event
from .mail.gmail_connector import GmailConnector
from .mail.outlook_connector import OutlookConnector
from .filemanager.file_connector import FileConnector
from .filemanager.file_tools import read_file_content
from .utility.semantic_connector import SemanticConnector
from .utility.usage import calculate_cost

# Connector Registry
connectors = {
    "mail_gmail": GmailConnector(),
    "mail_outlook": OutlookConnector(),
    "files": FileConnector(),
    "semantic": SemanticConnector()
}

app = FastAPI()

# Mount static files
static_path = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_path):
    os.makedirs(static_path)
app.mount("/static", StaticFiles(directory=static_path), name="static")

MODEL_NAME = "jasper"

def get_coding_state():
    """Reads the current coding mode state from a persistent file."""
    state_file = os.path.join(BASE_DIR, ".coding_mode")
    if os.path.exists(state_file):
        with open(state_file, "r") as f:
            return f.read().strip() == "ON"
    return False

def set_coding_state(is_on):
    """Saves the current coding mode state to a persistent file."""
    state_file = os.path.join(BASE_DIR, ".coding_mode")
    with open(state_file, "w") as f:
        f.write("ON" if is_on else "OFF")

CODING_MODE = get_coding_state() # Initialize from persistent storage

def get_provider():
    return get_setting("PROVIDER", "GMAIL").upper()

def summarize_text(text):
    if not text or len(text.strip()) < 10:
        return "No content to summarize."
    try:
        # Clinical completion prompt for the 270M model (or Jasper)
        prompt = (
            "TASK: Summarize the following email text into one very short sentence.\n"
            "TEXT: " + text[:800] + "\n"
            "SUMMARY: "
        )
        response = ollama.generate(
            model=MODEL_NAME, # Use Jasper
            prompt=prompt,
            system="You are a helpful assistant. Summarize the text in one short sentence.", # OVERRIDE JSON INSTRUCTION
            options={ "temperature": 0, "stop": ["\n", "TEXT:", "USER:"] }
        )
        summary = response.get("response", "").strip()
        if not summary or len(summary) > 150: return text[:500] + "..."
        return summary
    except:
        return text[:500] + "..."

def summarize_results_with_gemma(results, original_query):
    """
    Summarizes a list of search results using Gemma3 4B for a professional, 
    cohesive overview.
    """
    if not results:
        return "I found no results to summarize."

    # Aggregate content
    context = ""
    for i, item in enumerate(results):
        if i >= 3: break # STRICTOR LIMIT: Reduce prompt workload for 4B model
        source_type = "Email" if item.get("sender") else "File"
        content = item.get("body") or item.get("content") or item.get("summary") or "No content available."
        date = item.get("received") or item.get("date") or "Unknown date"
        
        context += f"ITEM {i+1} ({source_type}):\n"
        if source_type == "Email":
            context += f"From: {item.get('sender')}\nSubject: {item.get('subject')}\n"
        else:
            context += f"Name: {item.get('name')}\nPath: {item.get('path')}\n"
        context += f"Date: {date}\n"
        context += f"Content: {content[:500]}\n\n"

    prompt = (
        f"The user asked: '{original_query}'.\n"
        f"Based on the following {len(results)} search results, provide a clean, professional summary.\n\n"
        "FORMATTING:\n"
        "1. Start each section with '### [File Name]'.\n"
        "2. Provide a brief explanation of how it answers the user's query.\n"
        "3. You MUST provide VERBATIM code snippets in triple backticks for examples.\n\n"
        "STRICT GROUNDING:\n"
        "1. Answer ONLY using these results. Do not guess web addresses.\n"
    )

    # 5. Add specific instruction if user asked for examples
    is_example_req = any(k in original_query.lower() for k in ["example", "snippet", "how to", "code", "template", "context"])
    if is_example_req:
        prompt += (
            "\nIMPORTANT: The user explicitly asked for EXAMPLES. "
            "You MUST INCLUDE EXTENDED VERBATIM CODE BLOCKS from the source files. "
            "Do not just summarize; SHOW the code clearly in triple backticks.\n"
        )

    prompt += f"\nRESULTS:\n{context}\nSUMMARY:"

    try:
        from . import chat
        # Use Gemini cloud model for high-quality reasoning summary
        resp, sent = chat.chat_with_gemini(prompt, data_sent_flag=True)
        return {"content": resp, "data_sent": sent}
    except Exception as e:
        return {"content": f"I performed the search but failed to generate a summary: {str(e)}", "data_sent": False}

def summarize_files_iteratively(files, original_query):
    """
    Summarizes a list of files by reading their content and 
    summarizing them one by one.
    """
    if not files:
        return "I found no files to summarize."

    summaries = []
    actual_file_count = 0
    
    overall_data_sent = False
    for i, item in enumerate(files):
        if i >= 3: break # STRICTOR LIMIT: Reduce prompt workload for 4B model
        if item.get("kind") == "folder":
            continue
            
        actual_file_count += 1
        path = item.get("path")
        name = item.get("name")
        
        content = read_file_content(path, max_chars=8000)
        if not content:
            summaries.append(f"**FILE: {name}**\nPath: `{path}`\nStatus: *Could not read file content (binary or inaccessible).*")
            continue

        prompt = (
            f"The user is searching for: '{original_query}'.\n"
            f"Summarize this content from '{name}':\n\n"
            f"FILE CONTENT:\n{content[:5000]}\n\n"
            "INSTRUCTION: Provide a professional summary with ### [File Name] header.\n"
            "CODE: Wrap all examples in triple backticks.\n"
            f"CITE: {name}\n"
        )

        try:
            from . import chat
            # Use Gemini cloud model for individual file content analysis
            file_summary, sent = chat.chat_with_gemini(prompt, data_sent_flag=True)
            if sent: overall_data_sent = True
            summaries.append(f"**FILE: {name}**\nPath: `{path}`\nSummary: {file_summary}")
        except Exception as e:
            summaries.append(f"**FILE: {name}**\nPath: `{path}`\nError: *Failed to summarize: {str(e)}*")

    if actual_file_count == 0:
        return {"content": "I found only folders, which cannot be summarized by content. Please specify a file name.", "data_sent": False}

    return {"content": "\n\n---\n\n".join(summaries), "data_sent": overall_data_sent}

def handle_coding_task(user_input):
    """
    Handles request for script creation using Gemma3.
    Iteratively tries to solve the problem by feeding back errors to the model.
    """
    from . import chat
    import json
    import re
    import subprocess
    
    iteration = 1
    max_iterations = 20
    conversation_history = []
    
    # Scripts directory absolute path
    scripts_dir = os.path.join(BASE_DIR, "JaspersScripts")
    if not os.path.exists(scripts_dir):
        os.makedirs(scripts_dir)

    while iteration <= max_iterations:
        # Construct the system instruction and feedback
        system_instr = (
            "You are an expert software engineer. The user has requested a script or a command to solve a problem.\n"
            "GUIDELINES:\n"
            "1. Choose the most appropriate tool: Python, PowerShell (.ps1), or Bash (.sh).\n"
            "2. If the task is system-level or better suited for shell commands, prioritize PowerShell or Bash.\n"
            "3. You MUST provide a 'command' that the orchestrator can run in the project root to achieve the goal OR run the script.\n"
            f"4. SCRIPT LOCATION: Any script you write MUST be referenced as 'JaspersScripts/{ '{filename}' }' in your command.\n"
            "5. ENCODING RULE: Always use UTF-8. For Python, you MUST include `import sys; sys.stdout.reconfigure(encoding='utf-8')` at the top of your script to prevent Windows encoding errors.\n"
            "6. BROWSER READING TIP: If asked to 'see' or 'read' an open browser tab, UI Automation alone might fail due to sandboxing. "
            "Instead, use PowerShell to find the window, bring it to the foreground (`SwitchToThisWindow`), "
            "then simulate `Ctrl+A` and `Ctrl+C` to copy the page text and read it from the clipboard.\n"
            "7. Ensure the script is functional and follows best practices.\n"
            "8. ITEM LINKING: If your script or command finds emails or files, you MUST output a special marker for the orchestrator to create a link.\n"
            "   - For Outlook Emails: `ITEM_LINK: outlook:{EntryID}:{Subject}`\n"
            "   - For Files/Folders: `ITEM_LINK: file:{AbsolutePath}:{FileName}`\n"
            "   - Output these markers on their own lines in the script's output (stdout).\n\n"
            "FORMATTING RULE:\n"
            "You MUST return your response in the following JSON format ONLY:\n"
            "{\n"
            "  \"script\": \"content of the script\",\n"
            "  \"filename\": \"suggested_filename.ext\",\n"
            "  \"description\": \"simple description for the user\",\n"
            "  \"command\": \"shell command to run\"\n"
            "}\n"
            "IMPORTANT: Output ONLY the JSON block."
        )

        prompt = f"USER REQUEST: {user_input}\n\n"
        if conversation_history:
            prompt += "PREVIOUS ATTEMPTS AND ERRORS:\n"
            for i, entry in enumerate(conversation_history):
                prompt += f"Attempt {i+1}:\n- Command: {entry['command']}\n- Error: {entry['error']}\n\n"
            prompt += "Please fix the issue and try again."

        try:
            log_event("CODING", f"Iteration {iteration}: Sending prompt to Gemini...")
            # Pass both system instruction and prompt to Gemini, enabling JSON mode for reliability
            # NOTE: handle_coding_task typically DOES NOT send local data content, just instructions.
            raw_resp, sent = chat.chat_with_gemini(prompt, system_instruction=system_instr, json_mode=True, data_sent_flag=False)
            
            # Check for API failure strings returned from chat functions
            if "connection failed" in raw_resp.lower() or "not set" in raw_resp.lower():
                log_event("ERROR", f"Abort: LLM API error: {raw_resp}")
                return {"type": "chat", "content": f"I had to stop because of an API error: {raw_resp}", "coding_mode": True}

            # Parse JSON from response
            json_match = re.search(r'(\{.*\})', raw_resp, re.DOTALL)
            if not json_match:
                iteration += 1
                conversation_history.append({"command": "N/A", "error": f"Invalid JSON response from model: {raw_resp[:100]}..."})
                continue
                
            data = json.loads(json_match.group(1))
            script_content = data.get("script")
            filename = data.get("filename", "script.py")
            description = data.get("description", "I've created a script for you.")
            command = data.get("command")
            
            if not command:
                return {"type": "chat", "content": f"I generated a script but no command was provided to run it.\n\n**Description:** {description}", "coding_mode": True}

            # Save the script
            file_path = os.path.join(scripts_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(script_content)
            
            log_event("CODING", f"Saved script to {file_path}")
            
            # Execute command
            log_event("CODING", f"Executing command: {command}")
            # Ensure environment is set for UTF-8 and capture output correctly
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, cwd=BASE_DIR, encoding="utf-8", env=env)
            
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            
            if result.returncode == 0:
                log_event("CODING", "Command succeeded!")
                
                # PARSE FOR ITEM LINKS
                found_items = []
                # Regex to find ITEM_LINK: outlook:ID:Subject or ITEM_LINK: file:Path:Name
                link_matches = re.findall(r'ITEM_LINK:\s*(outlook|file):([^:\n]+):([^\n]+)', stdout, re.IGNORECASE)
                for provider_type, item_id, item_name in link_matches:
                    item_id = item_id.strip()
                    item_name = item_name.strip()
                    if provider_type.lower() == "outlook":
                        found_items.append({
                            "sender": "Found via Script",
                            "subject": item_name,
                            "message_id": item_id,
                            "provider": "OUTLOOK",
                            "received": "Discovered",
                            "is_compact": True
                        })
                    else:
                        found_items.append({
                            "name": item_name,
                            "path": item_id,
                            "kind": "document", # Default to document
                            "provider": "FILES",
                            "is_compact": True
                        })
                
                # Clean links from stdout to keep it pretty
                clean_stdout = re.sub(r'ITEM_LINK:.*?\n', '', stdout, flags=re.IGNORECASE).strip()
                if not clean_stdout: clean_stdout = stdout # Fallback if regex was too aggressive
                
                output_msg = f"### Success on Iteration {iteration}\n\n**Task:** {user_input}\n**Script:** `JaspersScripts/{filename}`\n**Description:** {description}\n\n**Output:**\n```\n{clean_stdout}\n```"
                return {"type": "results", "content": output_msg, "data": found_items, "coding_mode": True}
            else:
                log_event("CODING", f"Command failed with code {result.returncode}")
                # PRIVACY SANITIZATION: Only send STDERR to LLM, omit STDOUT to keep data local
                error_info = f"Exit Code: {result.returncode}\nSTDERR: {stderr}"
                conversation_history.append({"command": command, "error": error_info})
                iteration += 1
                
        except Exception as e:
            log_event("ERROR", f"Iteration {iteration} failed: {str(e)}")
            conversation_history.append({"command": "Internal Error", "error": str(e)})
            iteration += 1

    # If we reached here, we failed 20 times
    log_event("SYSTEM", f"Coding task failed after {max_iterations} iterations.")
    fail_summary = f"I'm sorry, I tried {max_iterations} times to solve this but kept encountering errors.\n\n**Last Error:**\n```\n{conversation_history[-1]['error'] if conversation_history else 'Unknown error'}\n```"
    return {"type": "chat", "content": fail_summary, "coding_mode": True}

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(static_path, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_json():
    return {}

@app.post("/query")
async def process_query(request: Request):
    body = await request.json()
    user_input = body.get("query", "")
    
    if not user_input:
        return JSONResponse(content={"response": "Please enter a query.", "data_sent_to_gemini": False})

    global CODING_MODE
    low_input = user_input.lower().strip().strip(".")
    
    # PRIVACY INDICATOR TRACKER
    data_sent_to_gemini = False

    # Handle Coding Mode Toggles
    if low_input == "coding on":
        CODING_MODE = True
        set_coding_state(True)
        log_event("SYSTEM", "Coding Mode: ON")
        return {"type": "chat", "content": "Coding mode is now **ON**. I'm ready to help you write scripts!", "coding_mode": True, "data_sent_to_gemini": False}
    
    if low_input == "coding off":
        CODING_MODE = False
        set_coding_state(False)
        log_event("SYSTEM", "Coding Mode: OFF")
        return {"type": "chat", "content": "Coding mode is now **OFF**. Returning to standard operation.", "coding_mode": False, "data_sent_to_gemini": False}

    # If in coding mode, route to handle_coding_task
    if CODING_MODE:
        res = handle_coding_task(user_input)
        # handle_coding_task usually returns a dict. We'll ensure it has the flag.
        if isinstance(res, dict):
            res["data_sent_to_gemini"] = res.get("data_sent_to_gemini", False)
        return res

    function_name = None
    args = {}
    intent = None
    action = None
    params = {}
    should_summarize = False

    try:
        # LOGGING
        log_event("INTENT", f"Input: {user_input}")
        
        # OLLAMA CALL (Using Jasper - built-in system prompt)
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: ollama.generate(
                    model=MODEL_NAME,
                    prompt=f"User: \"{user_input}\"", 
                    format="json",
                    options={ "temperature": 0.0, "stop": ["\n", "User:", "Input:"], "num_predict": 128 }
                )),
                timeout=90.0 # Increased timeout for slow system
            )
            raw_content = response.get("response", "").strip()
        except asyncio.TimeoutError:
            print(f"[{datetime.now()}] [BOOT] Jasper App is loading... FINGERPRINT: 9988776655")
            raw_content = "" # Will trigger fallback
            
        log_event("INTENT", f"Raw AI Response: {raw_content}")
        print(f"DEBUG: Jasper Raw Logic -> {raw_content}")

        try:
             # CLEANUP JSON
            if raw_content.startswith("```"):
                match = re.search(r"```(?:\w+)?\s*(.*?)```", raw_content, re.DOTALL)
                if match: raw_content = match.group(1).strip()
            
            raw_content = raw_content.replace("\\_", "_")
            
            # FALLBACK HELPER
            async def fallback_to_chat():
                 print(f"[{datetime.now()}] DEBUG: Fallback to Gemini triggered.")
                 # Run in executor to avoid blocking
                 loop = asyncio.get_event_loop()
                 from . import chat
                 resp, sent = await loop.run_in_executor(None, lambda: chat.chat_with_gemini(user_input))
                 return {"type": "chat", "content": resp, "data_sent_to_gemini": sent}

            if not raw_content:
                # Fallback if AI timed out or returned empty
                return await fallback_to_chat()
            
            try:
                # 1. Direct JSON parse
                data = json.loads(raw_content)
            except:
                # 2. Try to extract JSON from text (in case model didn't use format=json or wrapped it)
                json_match = re.search(r"({.*})", raw_content, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                    except:
                        print("DEBUG: Extracted JSON but failed to parse, retrying with Gemma3")
                        return await fallback_to_chat()
                else:
                    # If it's not JSON, it might be a valid chat response (or garbage)
                    print("DEBUG: Invalid JSON, retrying with Gemma3")
                    return await fallback_to_chat()
            
            # 1. Start with AI's raw intent
            intent = data.get("intent")
            action = data.get("action")
            params = data.get("params", {})
            if not params:
                params = {k: v for k, v in data.items() if k not in ['intent', 'action']}
            
            should_summarize = params.get("summarize", False)
            low_input = user_input.lower()

            # DETERMINISTIC CHAT GUARD: Force chat for greetings and known external topics
            chat_keywords = [
                'hi', 'hello', 'hey', 'who are you', 'how are you', 'howdy', 'greetings',
                'weather', 'stock', 'price', 'news', 'who is', 'what is', 'joke', 'tell me', 
                'market', 'online', 'check the web', 'web search', 'nyse', 'nasdaq', 'forecast',
                'bitcoin', 'crypto', 'how to', 'who was'
            ]
            
            # If it's a simple greeting or matches a chat keyword, and doesn't explicitly mention search targets
            if any(low_input == k or low_input.startswith(k + " ") for k in ['hi', 'hello', 'hey']) or any(k in low_input for k in chat_keywords):
                # Ensure we don't block semantics like "what is in the file"
                weak_targets = ["mail", "email", "gmail", "outlook", "sender", "file", "folder", "search", "find", "get"]
                if not any(wk in low_input for wk in weak_targets) or intent == "chat":
                    print(f"DEBUG: Keyword Guard triggered. Forcing intent 'chat'.")
                    intent = "chat"

            # DETERMINISTIC SUMMARIZATION GUARD (Safety Net)
            summarize_kws = ['summarize', 'summary', 'overview', 'briefly', 'explain', 'sažmi', 'pregled']
            if not should_summarize and any(k in low_input for k in summarize_kws):
                should_summarize = True

            # FINAL ROUTING LOG
            print(f"DEBUG: ROUTING -> intent='{intent}', summarize={should_summarize}, query='{params.get('query')}'")
            log_event("INTENT", f"Final Decision: intent='{intent}', params={params}, summarize={should_summarize}")
            
            # MAP INTENTS TO FUNCTIONS
            if intent == "mail":
                function_name = "fetch_items"
                args = params
                if not args.get("provider"):
                    args["provider"] = get_provider()
            
            elif intent == "files":
                function_name = "search_files"
                args = params
                kind = None
                lower_raw = user_input.lower()
                if "folder" in lower_raw or "directory" in lower_raw:
                    kind = "folder"
                if kind:
                    args["kind"] = kind
                if not args.get("query"):
                    args["query"] = args.get("subject") or args.get("sender") or args.get("message") or args.get("name")
            
            elif intent == "semantic":
                function_name = "semantic_search"
                args = params
                
            elif intent == "chat" or intent == "google_search":
                return await fallback_to_chat()
            
            if not function_name:
                return await fallback_to_chat()

        except Exception as e:
            print(f"Error parsing model output: {e}")
            return JSONResponse(content={"response": f"Error: {str(e)}", "data_sent_to_gemini": False})
        if function_name == "fetch_items":
            sender = args.get("sender")
            subject = args.get("subject")
            limit = args.get("limit", 5)
            date_filter = args.get("date_filter")
            has_attachment = args.get("has_attachment", False) # Added this line
                
            # Fallback: if model put everything in 'query'
            q_arg = args.get("query")
            if q_arg and not (sender or subject):
                # If there's a date in it, date_utils will catch it later.
                # For now, we take the whole string as a potential sender/subject base
                # but we'll prioritize sender extraction below.
                sender = q_arg
                
            # REGEX FALLBACK for Sender
            # FALLBACK: Explicit 'subject' extraction (Priority over sender hallucination)
            if not subject:
                # Regex for "subject" followed by specific quotes
                # We try to match paired quotes exactly: subject 'foo' OR subject "foo"
                subj_match_sq = re.search(r"subject\s+'(.+?)'", user_input, re.IGNORECASE)
                subj_match_dq = re.search(r"subject\s+\"(.+?)\"", user_input, re.IGNORECASE)
                    
                found_subj = None
                if subj_match_sq:
                    found_subj = subj_match_sq.group(1).strip()
                elif subj_match_dq:
                    found_subj = subj_match_dq.group(1).strip()
                else:
                     # Unquoted: subject foo bar (until 'last' or 'past' or end)
                     subj_match_raw = re.search(r"subject\s+(.+?)(?:\s+(?:last|past|since|before)|$)", user_input, re.IGNORECASE)
                     if subj_match_raw:
                         found_subj = subj_match_raw.group(1).strip()
                    
                if found_subj:
                    # Verify extracted subject isn't just a keyword
                    # Also strip any leading/trailing quote residuals just in case
                    found_subj = found_subj.strip("'\"")
                    if found_subj.lower() not in ["gmail", "outlook", "mail", "email"]:
                         print(f"DEBUG: Extracted subject via robust regex: '{found_subj}'")
                         subject = found_subj

            # Sender Logic
            should_recheck_sender = False
                
            # Check if AI hallucinated a keyword as the sender
            invalid_senders = ["search", "find", "get", "show", "fetch", "email", "mail", "gmail", "outlook", "from", "for"]
                
            # If we extracted a subject manually, and the sender looks like "subject ...", clear it immediately
            # ALSO: Even if we didn't extract a subject, if the sender literally contains "subject ", it's definitively a parsing error.
            if sender and "subject " in sender.lower():
                print(f"DEBUG: Clearing sender '{sender}' because it contains 'subject ' keyword.")
                # Attempt to recover subject from this falied sender string if extracting failed earlier
                if not subject:
                     clean_s = re.sub(r"subject\s+['\"]?(.+?)['\"]?", r"\1", sender, flags=re.IGNORECASE).strip()
                     if clean_s:
                         subject = clean_s
                         print(f"DEBUG: Recovered subject '{subject}' from malformed sender.")
                sender = None
                
            if subject and sender and "subject" in sender.lower():
                 sender = None
                
            # COLLISION FIX: If we found an explicit subject, but the sender seems to be just a fallback/hallucination
            # and the user did NOT explicitly say "from" or "sender", then clear the sender.
            # This fixes "search subject foo" becoming sender="foo" subject="foo".
            if subject and sender:
                 has_from = "from" in user_input.lower() or "sender" in user_input.lower()
                 if not has_from:
                     # Additional check: if sender is basically same as subject
                     if sender.lower() in subject.lower() or subject.lower() in sender.lower():
                         print(f"DEBUG: Clearing collision sender '{sender}' because matches subject '{subject}' and no explicit 'from'")
                         sender = None
                
            def recover_accents(fuzzy_text, raw_input):
                """Restores original accents if AI normalized them (e.g. sumandl -> šumandl)."""
                if not fuzzy_text or not raw_input: return fuzzy_text
                if fuzzy_text.lower() in raw_input.lower(): return fuzzy_text
                import unicodedata
                def snorm(t): return "".join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn').lower()
                target = snorm(fuzzy_text)
                for w in raw_input.split():
                    if snorm(w) == target: return w
                return fuzzy_text

            if sender:
                    sender = recover_accents(sender, user_input)
                    is_keyword = sender.lower() in invalid_senders
                    is_missing = sender.lower() not in user_input.lower()
                        
                    if is_keyword or is_missing:
                        should_recheck_sender = True
            else:
                    # If sender is missing but keywords are in input
                    if any(k in user_input.lower() for k in ["from", "for ", "search for "]):
                        should_recheck_sender = True
                            
            if should_recheck_sender:
                # Look for "from <word>" or "for <word>" - but prioritize 'from'
                matches = re.findall(r"(?:from|for)\s+(\S+)", user_input, re.IGNORECASE)
                found_valid = False
                if matches:
                    for m in matches:
                        m_clean = re.sub(r'[?.,!:]+$', '', m)
                        if m_clean.lower() not in ["gmail", "outlook", "mail", "email", "search", "find", "for", "subject"]:
                            sender = m_clean
                            found_valid = True
                            break
                    
                if not found_valid:
                    sender = None
                
            # SANITIZE SUBJECT
            # The AI often puts "search", "gmail", "find" in the subject. We must strip this.
            if subject:
                # LIST OF KNOWN HALLUCINATIONS FROM EXAMPLES
                # Removed "ljeto zavala" etc. as they are valid search terms for this user
                hallucinations = []
                invalid_keywords = ["search", "find", "get", "show", "fetch", "email", "mail", "gmail", "outlook", "item", "items", "none", "null"] + hallucinations
                
                subject_lower = subject.lower().strip()
                # If subject is or contains only invalid keywords, clear it
                subject_words = subject_lower.split()
                
                # Check if subject is in hallucinations
                if subject_lower in hallucinations:
                    print(f"DEBUG: Clearing hallucinated subject from examples: '{subject}'")
                    subject = None
                elif all(word in invalid_keywords for word in subject_words):
                    print(f"DEBUG: Ignoring hallucinated/empty subject '{subject}'")
                    subject = None
                elif any(word in ["search", "outlook", "gmail", "fetch"] for word in subject_words) and len(subject_words) <= 2:
                    # Extra check for common 2-word hallucinations like "search outlook"
                    if all(word in invalid_keywords for word in subject_words):
                         print(f"DEBUG: Ignoring hallucinated subject '{subject}'")
                         subject = None
                
                # FINAL VALIDATION: If subject was extracted by AI but is NOT in the user input (unquoted or quoted)
                # clear it to prevent hallucinations.
                print(f"DEBUG: Before final validation, subject='{subject}'")
                if subject and subject.lower() not in user_input.lower():
                    print(f"DEBUG: Clearing subject '{subject}' because it is NOT present in user input '{user_input}'")
                    subject = None
                
            # REGEX FALLBACK for Date
            # If model missed the date, we try to find it
            if not date_filter:
                # Match: last/past/this/current + number + unit OR last/past/this/current + unit
                date_match = re.search(r"(?:last|past|this|current)\s+(?:\d+\s+)?(?:day|week|month|year|mont)s?", user_input, re.IGNORECASE)
                if date_match:
                     date_filter = date_match.group(0)
                     print(f"DEBUG: Extracted date filter via regex: {date_filter}")
                
            # DATE PARSING
            from .utility.date_utils import extract_date_range, clean_date_string
            date_from, date_to = extract_date_range(date_filter or user_input)
                
            if date_from or date_to:
                print(f"DEBUG: Date Range Resolved -> From: {date_from}, To: {date_to}")
                    
                # CLEANUP: If we found a date in the user input, but 'sender' was set to the full string (fallback),
                # we must strip the date part from the sender.
                if sender:
                    cleaned_sender = clean_date_string(sender)
                    if cleaned_sender and cleaned_sender != sender:
                        print(f"DEBUG: Stripped date from sender: '{sender}' -> '{cleaned_sender}'")
                        sender = cleaned_sender

            # DATE/SUBJECT/SENDER CONFLICT Cleanup
            if date_filter:
                d_clean = date_filter.strip().lower()
                    
                if subject:
                    s_clean = subject.strip().lower()
                    if s_clean in d_clean or d_clean in s_clean:
                        print(f"DEBUG: Removing subject '{subject}' because it overlaps with date '{date_filter}'")
                        subject = None
            
            # ATTACHMENT REGEX FALLBACK
            # If model didn't catch it (args.get("has_attachment", False) is False)
            if not has_attachment:
                 if re.search(r"(with|has)\s+(an\s+)?attachment|attached|file", user_input, re.IGNORECASE):
                     print("DEBUG: Regex found attachment request")
                     has_attachment = True
            
            if has_attachment and subject:
                 # Check if the subject is just "attachment" or "with attachment"
                 # Strip out "with", "attachment", "file", "attached"
                 s_clean_att = re.sub(r'\b(with|has|attachment|attached|file|files)\b', '', subject, flags=re.IGNORECASE).strip()
                 # Remove punct
                 s_clean_att = re.sub(r'^[?.,!]+|[?.,!]+$', '', s_clean_att).strip()
                 
                 # Optimization: Update subject with the cleaned version so downstream cleaners don't see the attachment words
                 subject = s_clean_att
                 
                 if not subject or len(subject) < 2:
                     print(f"DEBUG: Clearing subject because it overlaps with attachment request.")
                     subject = None

            # BROAD NOISE STRIPPING
            # Remove common command verbs and provider names from sender/subject
            noise_words = ["search", "find", "get", "show", "fetch", "email", "mail", "gmail", "outlook", "item", "items", "for", "from", "in", "about"]
                
            def clean_noise(text):
                if not text: return None
                parts = text.split()
                cleaned = [p for p in parts if p.lower() not in noise_words]
                res = " ".join(cleaned).strip()
                # Also strip common punctuation that AI might leave
                res = re.sub(r'^[?.,!]+|[?.,!]+$', '', res).strip()
                return res if res else None

            sender = clean_noise(sender)
            subject = clean_noise(subject)
                
            if date_filter:
                d_clean = date_filter.strip().lower()
                if sender:
                    send_clean = sender.strip().lower()
                    if d_clean in send_clean:
                        print(f"DEBUG: Cleaning date '{date_filter}' out of sender '{sender}'")
                        sender = re.sub(re.escape(date_filter), '', sender, flags=re.IGNORECASE).strip()
                if subject:
                     s_clean = subject.strip().lower()
                     if d_clean in s_clean:
                         subject = re.sub(re.escape(date_filter), '', subject, flags=re.IGNORECASE).strip()
                
            # Final pass on prepositions
            if sender:
                 sender = re.sub(r'^(from|for|search|get)\s+', '', sender, flags=re.IGNORECASE).strip()
            if subject:
                 subject = re.sub(r'^(about|for|subject)\s+', '', subject, flags=re.IGNORECASE).strip()

            # Fix for model hallucination where sender is repeated as subject
            if sender and subject and sender.lower() == subject.lower():
                print(f"DEBUG: Dropping subject '{subject}' because it duplicates sender.")
                subject = None

            if not sender and not subject:
                 # This usually happens if the input was "search outlook"
                 # We can't do much, so we let it fall through
                 pass
                
            # RAW MODEL OUTPUT
            predicted_provider = args.get("provider")
                
            # DETERMINISTIC OVERRIDE
            final_provider = None
            lower_input = user_input.lower()
                
            # Priority 1: Explicit Keywords in Input
            if any(k in lower_input for k in ["gmail", "google", "personal"]):
                final_provider = "GMAIL"
            elif any(k in lower_input for k in ["outlook", "exchange", "office", "work", "company"]):
                final_provider = "OUTLOOK"
                
            # Priority 2: Model Prediction (if input didn't specify)
            if not final_provider and predicted_provider:
                pred_upper = predicted_provider.upper()
                if pred_upper in ["GMAIL", "OUTLOOK"]:
                    final_provider = pred_upper
                
            # Priority 3: Default Config
            if not final_provider:
                    final_provider = get_provider()


            # Extract body/content
            body_text = args.get("body") or args.get("content")
            
            # Clean body text
            body_text = clean_noise(body_text)
            
            # If subject starts with "about", maybe it should be body? 
            # For now, we trust the model's extraction of 'body' vs 'subject'.
            
            # LOGGING PARAMETERS
            log_event("INTENT", f"Final Params: provider={final_provider}, sender={sender}, subject={subject}, body={body_text}, date_filter={date_filter}, has_attachment={has_attachment}, from={date_from}, to={date_to}")
                
            print(f"DEBUG: Executing find_items(provider='{final_provider}', sender='{sender}', subject='{subject}', body='{body_text}', limit={limit}, from='{date_from}', to='{date_to}')")
                
        # ROUTE TO CONNECTOR
        if function_name == "fetch_items":
            provider = final_provider or get_provider()
            connector_key = f"mail_{provider.lower()}"
            connector = connectors.get(connector_key, connectors["mail_gmail"])
            
            # Use clarified params
            results = connector.search(
                sender=sender, 
                subject=subject, 
                body=body_text, 
                limit=limit, 
                date_from=date_from, 
                date_to=date_to,
                has_attachment=has_attachment
            )
            
            if isinstance(results, list):
                if not results:
                    return {"type": "results", "content": "No items found.", "data": [], "data_sent_to_gemini": False}
                else:
                    if should_summarize:
                        res_dict = summarize_results_with_gemma(results, user_input)
                        return {"type": "chat", "content": res_dict["content"], "data_sent_to_gemini": res_dict["data_sent"]}
                    
                    for item in results:
                        item["summary"] = summarize_text(item.get("body", ""))
                        item["provider"] = provider
                    return {"type": "results", "content": f"Found {len(results)} items.", "data": results, "data_sent_to_gemini": False}
            else:
                return {"type": "error", "content": str(results)}

        elif function_name == "search_files":
            # Clean up query
            query = args.get("query") or args.get("name")
            if query:
                for pref in [r'^search\s+for\s+', r'^find\s+files?\s+about\s+', r'^find\s+files?\s+', r'^find\s+folders?\s+', r'^search\s+files?\s+for\s+', r'^search\s+', r'^get\s+', r'^folder\s+', r'^file\s+']:
                    query = re.sub(pref, '', query, flags=re.IGNORECASE).strip()
            
            from .utility.date_utils import extract_date_range
            date_from, date_to = extract_date_range(args.get("date_filter") or user_input)
            
            results = connectors["files"].search(
                query=query, 
                limit=args.get("limit", 5), 
                kind=args.get("kind"), 
                date_from=date_from, 
                date_to=date_to
            )
            
            if isinstance(results, list):
                if not results:
                    return {"type": "results", "content": "No files found.", "data": [], "category": "files", "data_sent_to_gemini": False}
                else:
                    if should_summarize:
                        res_dict = summarize_files_iteratively(results, user_input)
                        return {"type": "chat", "content": res_dict["content"], "data_sent_to_gemini": res_dict["data_sent"]}
                    return {"type": "results", "content": f"Found {len(results)} files.", "data": results, "category": "files", "data_sent_to_gemini": False}
            else:
                return {"type": "error", "content": str(results)}

        elif function_name == "semantic_search":
            # Robust folder extraction
            folder = args.get("folder")
            folder_match = re.search(r"(?:in the|folder)\s+['\"]?(\w+)['\"]?\s+folder", user_input, re.IGNORECASE) or re.search(r"folder\s+['\"]?(\w+)['\"]?", user_input, re.IGNORECASE)
            if folder_match:
                f_test = folder_match.group(1).strip()
                if f_test.lower() not in ["the", "my"]:
                    folder = f_test

            results = connectors["semantic"].search(
                query=args.get("query"), 
                limit=args.get("limit", 3), 
                folder=folder
            )
            
            # DIAGNOSTIC: See what ChromaDB found
            log_diag = f"[{datetime.now()}] [RETRIEVAL] Found {len(results)} items.\n"
            for i, r in enumerate(results):
                log_diag += f"  [{i+1}] Source: {r.get('path')} | Score: {r.get('score', 'N/A')}\n"
            
            log_event("RETRIEVAL", log_diag)
            print(f"DEBUG: Retrieval diagnostic written to log.")

            if isinstance(results, list):
                if not results:
                     return {"type": "results", "content": f"No matches found for '{args.get('query')}'.", "data": [], "category": "files", "data_sent_to_gemini": False}
                
                if should_summarize:
                    res_dict = summarize_results_with_gemma(results, user_input)
                    return {"type": "chat", "content": res_dict["content"], "data_sent_to_gemini": res_dict["data_sent"]}

                msg = f"Found {len(results)} relevant semantic matches in your files."
                return {"type": "results", "content": msg, "data": results, "category": "files", "data_sent_to_gemini": False}
            else:
                return {"type": "error", "content": str(results)}

        else:
            # Fallback for chat or unknown intents
            return await fallback_to_chat()
                
    except json.JSONDecodeError:
        return {"type": "text", "content": raw_content, "data_sent_to_gemini": False}
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Backend Error: {error_trace}")
        log_event("ERROR", f"Backend Error: {error_trace}")
        return JSONResponse(content={"type": "error", "content": f"Backend Error: {str(e)}", "trace": error_trace, "data_sent_to_gemini": False}, status_code=500)

@app.post("/open")
async def open_email(request: Request):
    try:
        body = await request.json()
        idx = body.get("id")
        provider = body.get("provider", "GMAIL")
        
        if provider == "OUTLOOK" and idx:
            success, msg = connectors["mail_outlook"].open(idx)
            if success:
                return {"status": "ok", "message": "Opened in Outlook"}
            else:
                return JSONResponse(content={"status": "error", "message": msg}, status_code=500)
        elif provider == "FILES" and idx:
            success, msg = connectors["files"].open(idx)
            if success:
                return {"status": "ok", "message": "File opened"}
            else:
                return JSONResponse(content={"status": "error", "message": msg}, status_code=500)
        else:
            return {"status": "ignored", "message": "Not an Outlook item or file, or no ID"}
            
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

@app.post("/restart")
async def restart_service():
    try:
        import os
        import signal
        import threading
        
        def kill_self():
            import sys
            time.sleep(1)
            print("RESTART TRIGGERED: Exiting process for auto-restart...")
            sys.exit(0) # Signal supervisor to restart
            
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
            
        # Use errors="replace" to avoid crashing on non-UTF8 characters
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            # Return last 500 lines, reversed (newest first)
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
            # Default or first run
            return {"percent": 100, "status": "Idle"}
    except Exception as e:
        return {"percent": 0, "status": "Error", "error": str(e)}

@app.get("/coding-status")
async def get_coding_status():
    """Returns the current persistent coding mode status."""
    return {"coding_mode": get_coding_state()}

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
        
        # Run indexing in background to avoid blocking and database locks
        background_tasks.add_task(index_all, force=True)
        
        with open(get_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] [INDEXER] Background indexing task queued.\n")
            
        return {"status": "ok", "message": "Indexing started in background..."}
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
