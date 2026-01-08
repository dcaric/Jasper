import re
import ollama
import traceback
import json
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .utility.config import get_setting, get_log_file, get_status_file
from .mail.gmail_connector import GmailConnector
from .mail.outlook_connector import OutlookConnector
from .filemanager.file_connector import FileConnector
from .utility.semantic_connector import SemanticConnector

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

MODEL_NAME = "functiongemma"

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

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(static_path, "index.html"), "r") as f:
        return f.read()

@app.post("/query")
async def process_query(request: Request):
    body = await request.json()
    user_input = body.get("query", "")
    
    if not user_input:
        return JSONResponse(content={"response": "Please enter a query."})

    try:
        # LOGGING
        with open(get_log_file(), "a") as f:
            f.write(f"[{datetime.now()}] Input: {user_input}\n")
        
        # OLLAMA CALL (Using Jasper - built-in system prompt)
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: ollama.generate(
                    model=MODEL_NAME,
                    prompt=f"User: \"{user_input}\"", 
                    format="json",
                    options={ "temperature": 0.0, "stop": ["\n", "User:"] }
                )),
                timeout=20.0 # 20 seconds timeout for AI
            )
            raw_content = response.get("response", "").strip()
        except asyncio.TimeoutError:
            print(f"[{datetime.now()}] AI Timeout for input: {user_input}")
            raw_content = "" # Will trigger fallback
            
        with open(get_log_file(), "a") as f:
            f.write(f"[{datetime.now()}] AI Response: {raw_content}\n")
        print(f"Jasper Logic -> {raw_content}")

        try:
             # CLEANUP JSON
            if raw_content.startswith("```"):
                match = re.search(r"```(?:\w+)?\s*(.*?)```", raw_content, re.DOTALL)
                if match: raw_content = match.group(1).strip()
            
            raw_content = raw_content.replace("\\_", "_")
            
            # FALLBACK HELPER
            async def fallback_to_chat():
                 print(f"[{datetime.now()}] DEBUG: Fallback to Gemma3 triggered.")
                 from . import chat
                 # Run in executor to avoid blocking
                 loop = asyncio.get_event_loop()
                 resp = await loop.run_in_executor(None, lambda: chat.chat_with_gemma(user_input))
                 return {"type": "chat", "content": resp}

            if not raw_content:
                # Fallback if AI timed out or returned empty
                return await fallback_to_chat()
            
            try:
                data = json.loads(raw_content)
            except:
                # If it's not JSON, it might be a valid chat response (or garbage)
                # But since FunctionGemma sucks at chat, we retry with Gemma3
                print("DEBUG: Invalid JSON, retrying with Gemma3")
                return await fallback_to_chat()
            
            # PARSE INTENT
            intent = data.get("intent")
            params = data.get("params", {})
            folder = None
            
            # DETERMINISTIC INTENT OVERRIDE (Safety Net)
            low_input = user_input.lower()
            
            # Chat Keyword Guard
            chat_keywords = ['weather', 'stock', 'price', 'news', 'who is', 'what is', 'joke', 'tell me', 'market']
            
            # Content Search Guard: Force semantic search if explicit content keywords are used
            content_keywords = ['search for content', 'find in file', 'search inside', 'find file containing']
            
            # Check for content keywords first
            is_content_request = any(k in low_input for k in content_keywords)
            
            if is_content_request:
                intent = "semantic"
                # Extract query: everything after the keyword
                for k in content_keywords:
                    if k in low_input:
                        query_part = low_input.split(k)[-1].strip().strip("'").strip('"')
                        params = {"query": query_part}
                        break
                print(f"DEBUG: Content Search Shield triggered for: {low_input}")
            
            # GLOBAL CHAT GUARD: Force chat for known external topics
            # This prevents "check weather" from becoming "search email"
            elif any(k in low_input for k in chat_keywords):
                # Ensure we don't block semantics like "what is in the file"
                # If it has specific file/mail keywords, we rely on the model.
                # But for generic "what is X", we prefer chat.
                weak_mail_keywords = ["mail", "email", "gmail", "outlook", "sender", "file", "folder"]
                if not any(wk in low_input for wk in weak_mail_keywords):
                    print(f"DEBUG: Keyword Guard triggered. Forcing intent 'chat' due to keyword match.")
                    intent = "chat"
                    
            if "file" in low_input or "folder" in low_input or "path" in low_input:
                # If it mentions "in the files" or "content", it should be semantic, not filename-based
                if any(k in low_input for k in ["content", "in the", "inside", "about", "contain"]):
                    if intent != "semantic":
                        print(f"DEBUG: Overriding intent '{intent}' -> 'semantic' for content search.")
                        intent = "semantic"
                # Check if it's actually an email request (e.g. "email with file", "outlook file")
                elif any(k in low_input for k in ["mail", "email", "gmail", "outlook", "sender", "subject", "from"]):
                     # PROBABLY MAIL
                     if intent != "mail":
                         print(f"DEBUG: Overriding intent '{intent}' -> 'mail' because email keywords present with 'file'.")
                         intent = "mail"
                elif intent != "files":
                    print(f"DEBUG: Overriding intent '{intent}' -> 'files' due to keyword.")
                    intent = "files"
            elif any(k in low_input for k in ["mail", "email", "gmail", "outlook", "from", "subject"]):
                if intent == "files" or intent is None:
                    # Only override if it's very likely mail (e.g. contains 'subject' or 'sender' or 'from')
                     if any(k in low_input for k in ["from", "subject", "gmail", "outlook"]) or (intent is None and any(k in low_input for k in ["mail", "email"])):
                         print(f"DEBUG: Overriding intent '{intent}' -> 'mail' due to keyword.")
                         intent = "mail"
            
            function_name = None
            args = {}
            
            # MAP INTENTS TO FUNCTIONS
            if intent == "mail":
                function_name = "fetch_items"
                args = params
                # Default provider if missing
                if not args.get("provider"):
                    args["provider"] = get_provider()
            
            elif intent == "files":
                function_name = "search_files"
                args = params
                
                 # Detect 'kind' explicitly from user input if not extracted by AI
                kind = None
                q_text = args.get("query", "") or user_input
                
                # BUGFIX: Check raw user_input for 'folder' keyword, because q_text might already satisfy the AI extraction
                lower_raw = user_input.lower()
                
                if "folder" in lower_raw or "directory" in lower_raw:
                    kind = "folder"
                    # Do NOT strip keyword here; let the prefix stripper downstream handle it.
                    # q_text = re.sub(r'\b(folder|directory)\b', '', q_text, flags=re.IGNORECASE).strip()
                elif "file" in lower_raw or "document" in lower_raw:
                     # Only set kind=document if it's explicitly strictly documents, but usually we just default to None (all)
                     pass 
                
                args["query"] = q_text
                if kind:
                    args["kind"] = kind

                # Robust extraction: if AI put file name in 'subject' or 'sender' or 'message'
                if not args.get("query"):
                    args["query"] = args.get("subject") or args.get("sender") or args.get("message") or args.get("name")
            
            elif intent == "semantic":
                function_name = "semantic_search"
                args = params
                
            elif intent == "chat":
                # Utilize Gemma3 for chat responses instead of echoing
                return await fallback_to_chat()
            
            # Fallback/Safety: If intent is missing or invalid
            if not function_name:
                print("DEBUG: No valid intent found. Defaulting to Semantic Search.")
                function_name = "semantic_search"
                args = {"query": user_input}

        except Exception as e:
            print(f"Error parsing model output: {e}")
            return JSONResponse(content={"response": f"Error: {str(e)}"})
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
                
            if sender:
                    is_keyword = sender.lower() in invalid_senders
                    is_missing = sender.lower() not in user_input.lower()
                        
                    if is_keyword or is_missing:
                        should_recheck_sender = True
                        with open("debug.log", "a") as f: f.write(f"[{datetime.now()}] Sender '{sender}' rejected (Keyword={is_keyword}, Missing={is_missing}). Rechecking.\n")
            else:
                    # If sender is missing but keywords are in input
                    if any(k in user_input.lower() for k in ["from", "for ", "search for "]):
                        should_recheck_sender = True
                            
            if should_recheck_sender:
                # Look for "from <word>" or "for <word>" - but prioritize 'from'
                # and find ALL matches to filter out keywords correctly.
                matches = re.findall(r"(?:from|for)\s+(\w+)", user_input, re.IGNORECASE)
                found_valid = False
                if matches:
                    for m in matches:
                        if m.lower() not in ["gmail", "outlook", "mail", "email", "search", "find", "for", "subject"]:
                            print(f"DEBUG: Overriding sender '{sender}' with regex match '{m}'")
                            sender = m
                            found_valid = True
                            break
                    
                if not found_valid:
                    # If the original was a keyword/missing and fallback failed, we MUST clear it.
                    print(f"DEBUG: Clearing invalid/untraceable sender '{sender}'")
                    sender = None
                
            # SANITIZE SUBJECT
            # The AI often puts "search", "gmail", "find" in the subject. We must strip this.
            if subject:
                # LIST OF KNOWN HALLUCINATIONS FROM EXAMPLES
                hallucinations = ["ljeto zavala", "ljeto", "zavala"]
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
                if subject and subject.lower() not in user_input.lower():
                    print(f"DEBUG: Clearing subject '{subject}' because it is NOT present in user input.")
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
            with open(get_log_file(), "a") as f:
                f.write(f"[{datetime.now()}] Final Params: provider={final_provider}, sender={sender}, subject={subject}, body={body_text}, date_filter={date_filter}, has_attachment={has_attachment}, from={date_from}, to={date_to}\n")
                
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
                    return {"type": "results", "content": "No items found.", "data": []}
                else:
                    for item in results:
                        item["summary"] = summarize_text(item.get("body", ""))
                        item["provider"] = provider
                    return {"type": "results", "content": f"Found {len(results)} items.", "data": results}
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
                limit=args.get("limit", 10), 
                kind=args.get("kind"), 
                date_from=date_from, 
                date_to=date_to
            )
            
            if isinstance(results, list):
                if not results:
                    return {"type": "results", "content": "No files found.", "data": [], "category": "files"}
                else:
                    return {"type": "results", "content": f"Found {len(results)} files.", "data": results, "category": "files"}
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
                limit=args.get("limit", 10), 
                folder=folder
            )
            
            if isinstance(results, list):
                if not results:
                     return {"type": "results", "content": f"No matches found for '{args.get('query')}'.", "data": [], "category": "files"}
                
                msg = f"Found {len(results)} relevant semantic matches in your files."
                return {"type": "results", "content": msg, "data": results, "category": "files"}
            else:
                return {"type": "error", "content": str(results)}

        else:
            # Fallback for chat or unknown intents
            return await fallback_to_chat()
                
    except json.JSONDecodeError:
        return {"type": "text", "content": raw_content}
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Backend Error: {error_trace}")
        with open(get_log_file(), "a") as f:
            f.write(f"[{datetime.now()}] Backend Error: {error_trace}\n")
        return JSONResponse(content={"type": "error", "content": f"Backend Error: {str(e)}", "trace": error_trace}, status_code=500)

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
            import time
            import sys
            time.sleep(1)
            print("RESTART TRIGGERED: Exiting process for auto-restart...")
            os._exit(0) # Force exit to ensure loop catches it
            
        threading.Thread(target=kill_self).start()
        return {"status": "ok", "message": "Restarting Jasper..."}
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
