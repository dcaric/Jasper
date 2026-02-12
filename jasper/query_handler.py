import os
import re
import ollama
import traceback
import json
import time
from datetime import datetime
from fastapi import Request
from fastapi.responses import JSONResponse

from .utility.config import get_setting, get_log_file, get_status_file, BASE_DIR, log_event
from .tools.filemanager.file_tools import read_file_content
from . import state
from . import chat

def get_help_message():
    """Constructs a Markdown help message based on current GEMINI_USAGE."""
    gemini_on = chat.is_gemini_enabled()
    g_on = "✅" if gemini_on else "❌ (Disabled)"
    
    msg = (
        "## 🦾 Jasper Help\n"
        "Here is what I can do for you:\n\n"
        
        "### 📧 Communication\n"
        "- **Email Search**: Search Gmail or Outlook via `search mail from [sender] subject [topic]`.\n\n"
        
        "### 📂 File Management\n"
        "- **File Search**: Find files in your project with `search for files named [name]`.\n"
        "- **Folder Search**: Locate directories with `search folders containing [name]`.\n\n"
        
        "### 🧠 Intelligence & Cloud\n"
        f"- **Web Search**: {g_on} Get real-time info with `check on the web what is [topic]`.\n"
        "- **Summarization**: ✅ Ask me to `summarize` your search results (uses local model if Gemini is off).\n"
        "- **Semantic Search**: Find data by meaning, even if exact words don't match.\n\n"
        
        "### 💻 Engineering\n"
        f"- **Coding Mode**: {g_on} Enable with `coding on` to let me write and run scripts to solve complex tasks.\n\n"
        
        "--- \n"
        "**Tip**: You can switch modes by saying `coding on` or `coding off`."
    )
    return msg

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
            model=state.MODEL_NAME, # Use Jasper
            prompt=prompt,
            system="You are a helpful assistant. Summarize the text in one short sentence.", # OVERRIDE JSON INSTRUCTION
            options={ "temperature": 0, "stop": ["\n", "TEXT:", "User:"] }
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

    if not chat.is_gemini_enabled():
        # LOCAL FALLBACK: Use Ollama (Gemma3 4B)
        try:
            log_event("OLLAMA", "Gemini disabled, using local fallback for multi-result summary...")
            response = ollama.generate(
                model=state.MODEL_NAME,
                prompt=prompt,
                options={ "temperature": 0.1 }
            )
            return {"content": response.get("response", "Local summarization failed.").strip(), "data_sent": False}
        except Exception as e:
            return {"content": f"I performed the search but local summarization failed: {str(e)}", "data_sent": False}

    try:
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
    
    overall_data_sent = False
    for i, item in enumerate(files):
        if i >= 3: break # STRICTOR LIMIT: Reduce prompt workload for 4B model
        if item.get("kind") == "folder":
            continue
            
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

        if not chat.is_gemini_enabled():
            # LOCAL FALLBACK: Summarize individual file using Ollama
            try:
                log_event("OLLAMA", f"Using local fallback for file summarization: {name}")
                response = ollama.generate(
                    model=state.MODEL_NAME,
                    prompt=prompt,
                    options={ "temperature": 0.1 }
                )
                summaries.append(f"**FILE: {name}**\nPath: `{path}`\nSummary: {response.get('response', '').strip()}")
            except Exception as e:
                summaries.append(f"**FILE: {name}**\nPath: `{path}`\nError: *Local summary failed: {str(e)}*")
            continue

        try:
            # Use Gemini cloud model for individual file content analysis
            file_summary, sent = chat.chat_with_gemini(prompt, data_sent_flag=True)
            if sent: overall_data_sent = True
            summaries.append(f"**FILE: {name}**\nPath: `{path}`\nSummary: {file_summary}")
        except Exception as e:
            summaries.append(f"**FILE: {name}**\nPath: `{path}`\nError: *Failed to summarize: {str(e)}*")

    return {"content": "\n\n".join(summaries), "data_sent": overall_data_sent}

async def handle_coding_task(user_input):
    """
    Handles request for script creation using Gemma3.
    Iteratively tries to solve the problem by feeding back errors to the model.
    """
    state.STOP_CODING_FLAG = False
    
    import subprocess
    import asyncio
    
    iteration = 1
    max_iterations = 20
    conversation_history = []
    
    # Scripts directory absolute path
    scripts_dir = os.path.join(BASE_DIR, "JaspersScripts")
    if not os.path.exists(scripts_dir):
        os.makedirs(scripts_dir)

    while iteration <= max_iterations:
        if state.STOP_CODING_FLAG:
            log_event("SYSTEM", "Coding task cancelled by user.")
            return {"type": "chat", "content": "Execution stopped by user.", "coding_mode": True}

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
                prompt += f"--- Iteration {i+1} ---\nScript content was:\n{entry['script']}\n\nError output was:\n{entry['error']}\n\n"

        try:
            log_event("CODING", f"Iteration {iteration}: Sending prompt to Gemini...")
            # Pass both system instruction and prompt to Gemini, enabling JSON mode for reliability
            loop = asyncio.get_event_loop()
            raw_resp, sent = await loop.run_in_executor(None, lambda: chat.chat_with_gemini(prompt, system_instruction=system_instr, json_mode=True, data_sent_flag=False))
            
            # Clean JSON Response
            if raw_resp.startswith("```"):
                match = re.search(r"```(?:json)?\s*(\{.*?\})", raw_resp, re.DOTALL)
                if match: raw_resp = match.group(1).strip()
            
            # Parse logic
            try:
                resp_json = json.loads(raw_resp)
            except:
                # Fallback extraction if JSON parsing fails
                script_match = re.search(r'"script":\s*"(.*?)"', raw_resp, re.DOTALL)
                filename_match = re.search(r'"filename":\s*"(.*?)"', raw_resp)
                description_match = re.search(r'"description":\s*"(.*?)"', raw_resp)
                command_match = re.search(r'"command":\s*"(.*?)"', raw_resp)
                
                resp_json = {
                    "script": script_match.group(1).encode().decode('unicode_escape') if script_match else "",
                    "filename": filename_match.group(1) if filename_match else "script.py",
                    "description": description_match.group(1) if description_match else "No description",
                    "command": command_match.group(1) if command_match else ""
                }

            script_content = resp_json.get("script", "")
            filename = resp_json.get("filename", "generated_script.py")
            description = resp_json.get("description", "Solving task...")
            command = resp_json.get("command", "")
            
            log_event("CODING", f"Script generated: {filename}")
            
            # Save the script
            script_path = os.path.join(scripts_dir, filename)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script_content)
                
            # Execute the command
            log_event("CODING", f"Executing command: {command}")
            
            def sync_execute(cmd):
                import subprocess
                res = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                return res.returncode, res.stdout, res.stderr

            loop = asyncio.get_event_loop()
            ret_code, stdout_str, stderr_str = await loop.run_in_executor(None, sync_execute, command)
            
            log_event("CODING", f"Result (code {ret_code}): {stdout_str[:200]}...")
            
            if ret_code == 0:
                log_event("SYSTEM", f"Success on Iteration {iteration}")
                return {
                    "type": "chat",
                    "content": f"**Success on Iteration {iteration}**\n\n{stdout_str}\n\n{description}",
                    "coding_mode": True
                }
            else:
                # Store error and retry
                log_event("CODING", f"Iteration {iteration} failed: {stderr_str or stdout_str}")
                conversation_history.append({
                    "script": script_content,
                    "error": stderr_str or stdout_str or "Unknown error"
                })
                iteration += 1
                
        except Exception as e:
            import traceback
            error_detail = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            log_event("ERROR", f"Coding Mode Failure context:\n{error_detail}")
            return {"type": "chat", "content": f"Coding loop failed: {str(e)}", "coding_mode": True}

    return {"type": "chat", "content": f"Failed to complete task after {max_iterations} iterations. Check individual errors in logs.", "coding_mode": True}

def read_index():
    from .utility.config import get_index_paths
    return get_index_paths()

async def process_query(request: Request):
    body = await request.json()
    user_input = body.get("query", "")
    
    if not user_input:
        return JSONResponse(content={"response": "Please enter a query.", "data_sent_to_gemini": False})

    low_input = user_input.lower().strip().strip(".")
    
    # 0. Help Command Guard
    help_keywords = ["help", "what you can do", "what can you do", "pomoć", "informacije"]
    if any(k == low_input or low_input.startswith(k + " ") for k in help_keywords):
        return {"type": "chat", "content": get_help_message(), "coding_mode": state.CODING_MODE, "data_sent_to_gemini": False}

    # PRIVACY INDICATOR TRACKER
    data_sent_to_gemini = False

    # Handle Coding Mode Toggles
    if low_input == "coding on":
        if not chat.is_gemini_enabled():
            return {"type": "chat", "content": "Coding mode cannot be enabled because Gemini features are disabled (GEMINI_USAGE=0 or missing API key).", "coding_mode": False, "data_sent_to_gemini": False}
        state.CODING_MODE = True
        state.set_coding_state(True)
        log_event("SYSTEM", "Coding Mode: ON")
        return {"type": "chat", "content": "Coding mode is now **ON**. I'm ready to help you write scripts!", "coding_mode": True, "data_sent_to_gemini": False}
    
    if low_input == "coding off":
        state.CODING_MODE = False
        state.set_coding_state(False)
        log_event("SYSTEM", "Coding Mode: OFF")
        return {"type": "chat", "content": "Coding mode is now **OFF**. Returning to standard operation.", "coding_mode": False, "data_sent_to_gemini": False}

    # HYBRID CODING MODE GUARD
    chat_keywords = [
        'hi', 'hello', 'hey', 'who are you', 'how are you', 'howdy', 'greetings',
        'weather', 'stock', 'price', 'news', 'who is', 'what is', 'joke', 'tell me', 
        'market', 'online', 'check the web', 'web search', 'nyse', 'nasdaq', 'forecast',
        'bitcoin', 'crypto', 'how to', 'who was'
    ]
    
    is_chat_query = any(low_input == k or low_input.startswith(k + " ") for k in ['hi', 'hello', 'hey']) or any(k in low_input for k in chat_keywords)
    is_explicit_code_request = any(kw in low_input for kw in ["script", "code", "automate", "program", "write a", "create a", "fix the"])

    if state.CODING_MODE:
        if is_chat_query and not is_explicit_code_request:
            log_event("SYSTEM", "Bypassing Coding Mode for standard chat query.")
        else:
            res = await handle_coding_task(user_input)
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
        
        # OLLAMA CALL
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: ollama.generate(
                    model=state.MODEL_NAME,
                    prompt=f"User: \"{user_input}\"", 
                    format="json",
                    options={ "temperature": 0.0, "stop": ["\n", "User:", "Input:"], "num_predict": 128 }
                )),
                timeout=90.0
            )
            raw_content = response.get("response", "").strip()
        except asyncio.TimeoutError:
            raw_content = ""

        # FALLBACK HELPER
        async def fallback_to_chat():
             log_event("SYSTEM", "Fallback to Gemini triggered.")
             loop = asyncio.get_event_loop()
             resp, sent = await loop.run_in_executor(None, lambda: chat.chat_with_gemini(user_input))
             return {"type": "chat", "content": resp, "data_sent_to_gemini": sent}

        if not raw_content:
            return await fallback_to_chat()

        # CLEANUP JSON
        if raw_content.startswith("```"):
            match = re.search(r"```(?:\w+)?\s*(.*?)```", raw_content, re.DOTALL)
            if match: raw_content = match.group(1).strip()
        
        raw_content = raw_content.replace("\\_", "_")
        intent_data = json.loads(raw_content)

        # Restores original accents
        def recover_accents(fuzzy_text, raw_input):
            if not fuzzy_text: return fuzzy_text
            def snorm(t): return re.sub(r'[^\w\s]', '', t.lower())
            norm_fuzzy = snorm(fuzzy_text)
            words = raw_input.split()
            for w in words:
                if snorm(w) == norm_fuzzy: return w
            return fuzzy_text

        # BROAD NOISE STRIPPING
        def clean_noise(text):
            if not text: return None
            noise_words = ["search", "find", "get", "show", "fetch", "email", "mail", "gmail", "outlook", "item", "items", "for", "from", "in", "about"]
            parts = text.split()
            cleaned = [p for p in parts if p.lower() not in noise_words]
            res = " ".join(cleaned).strip()
            res = re.sub(r'^[?.,!]+|[?.,!]+$', '', res).strip()
            return res if res else None

        intent = intent_data.get("intent")
        action = intent_data.get("action")
        args = intent_data.get("parameters", {})
        should_summarize = intent_data.get("should_summarize", False)

        if intent == "email":
            function_name = "fetch_items"
        elif intent == "file":
            if action == "semantic_search":
                function_name = "semantic_search"
            else:
                function_name = "search_files"

        sender = args.get("sender")
        subject = args.get("subject")
        date_filter = args.get("date_filter")
        limit = args.get("limit", 15)
        has_attachment = args.get("has_attachment", False)

        from .utility.date_utils import extract_date_range
        date_from, date_to = extract_date_range(date_filter or user_input)

        sender = recover_accents(sender, user_input)
        subject = recover_accents(subject, user_input)
        
        sender = clean_noise(sender)
        subject = clean_noise(subject)
        
        # FINAL PROVIDER LOGIC
        final_provider = None
        lower_input = user_input.lower()
        if any(k in lower_input for k in ["gmail", "google"]): final_provider = "GMAIL"
        elif any(k in lower_input for k in ["outlook", "exchange"]): final_provider = "OUTLOOK"
        if not final_provider: final_provider = get_provider()

        body_text = clean_noise(args.get("body") or args.get("content"))

        # EXECUTION
        if function_name == "fetch_items":
            connector = state.connectors.get(f"mail_{final_provider.lower()}", state.connectors["mail_gmail"])
            results = connector.search(sender=sender, subject=subject, body=body_text, limit=limit, date_from=date_from, date_to=date_to, has_attachment=has_attachment)
            if isinstance(results, list):
                if not results: return {"type": "results", "content": "No items found.", "data": [], "data_sent_to_gemini": False}
                if should_summarize:
                    res_dict = summarize_results_with_gemma(results, user_input)
                    return {"type": "chat", "content": res_dict["content"], "data_sent_to_gemini": res_dict["data_sent"]}
                for item in results:
                    item["summary"] = summarize_text(item.get("body", ""))
                    item["provider"] = final_provider
                return {"type": "results", "content": f"Found {len(results)} items.", "data": results, "data_sent_to_gemini": False}

        elif function_name == "search_files":
            query = clean_noise(args.get("query") or args.get("name"))
            results = state.connectors["files"].search(query=query, limit=args.get("limit", 5), kind=args.get("kind"), date_from=date_from, date_to=date_to)
            if isinstance(results, list):
                if not results: return {"type": "results", "content": "No files found.", "data": [], "category": "files", "data_sent_to_gemini": False}
                if should_summarize:
                    res_dict = summarize_files_iteratively(results, user_input)
                    return {"type": "chat", "content": res_dict["content"], "data_sent_to_gemini": res_dict["data_sent"]}
                return {"type": "results", "content": f"Found {len(results)} files.", "data": results, "category": "files", "data_sent_to_gemini": False}

        elif function_name == "semantic_search":
            results = state.connectors["semantic"].search(query=args.get("query"), limit=args.get("limit", 3), folder=args.get("folder"))
            if isinstance(results, list):
                if not results: return {"type": "results", "content": f"No matches found.", "data": [], "category": "files", "data_sent_to_gemini": False}
                if should_summarize:
                    res_dict = summarize_results_with_gemma(results, user_input)
                    return {"type": "chat", "content": res_dict["content"], "data_sent_to_gemini": res_dict["data_sent"]}
                return {"type": "results", "content": "Matches found.", "data": results, "category": "files", "data_sent_to_gemini": False}

        return await fallback_to_chat()
                
    except Exception as e:
        log_event("ERROR", f"Query Error: {traceback.format_exc()}")
        return JSONResponse(content={"type": "error", "content": str(e)}, status_code=500)
