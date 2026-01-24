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
        source_type = "Email" if item.get("sender") else "File"
        content = item.get("body") or item.get("content") or item.get("summary") or "No content available."
        date = item.get("received") or item.get("date") or "Unknown date"
        
        context += f"ITEM {i+1} ({source_type}):\n"
        if source_type == "Email":
            context += f"From: {item.get('sender')}\nSubject: {item.get('subject')}\n"
        else:
            context += f"Name: {item.get('name')}\nPath: {item.get('path')}\n"
        context += f"Date: {date}\n"
        context += f"Content: {content[:750]}\n\n"

    prompt = (
        f"The user asked: '{original_query}'.\n"
        f"Based on the following {len(results)} search results, provide a CLEAR, LUXURY, and PROFESSIONAL summary.\n\n"
        "STRUCTURE RULES:\n"
        "1. Use Markdown headers (### [File Name] - [Short Description]) for each file discussed.\n"
        "2. Provide a descriptive paragraph for each file detailing what the code/content does.\n"
        "3. If the user asked for EXAMPLES, you MUST provide VERBATIM code snippets in triple backticks (e.g., ```python) for every file.\n\n"
        "STRICT GROUNDING RULES:\n"
        "1. Use ONLY the provided search results below.\n"
        "2. CITE the source files for every claim.\n"
        "3. If a web address or detail is not EXPLICITLY FOUND in the results, state: 'No web address found in the project files.'\n"
        "4. DO NOT guess URLs or phone numbers.\n"
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
        # Use custom gemma3 model (4B) for high-quality reasoning summary
        return chat.chat_with_gemma(prompt, allow_fallback=False, model_name="gemma3")
    except Exception as e:
        return f"I performed the search but failed to generate a summary: {str(e)}"

def summarize_files_iteratively(files, original_query):
    """
    Summarizes a list of files by reading their content and 
    summarizing them one by one.
    """
    if not files:
        return "I found no files to summarize."

    summaries = []
    actual_file_count = 0
    
    for i, item in enumerate(files):
        if i >= 5: break # SAFETY LIMIT: Never summarize more than 5 results iteratively
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
            f"Please summarize the following content from the file '{name}':\n\n"
            f"FILE CONTENT:\n{content}\n\n"
            "INSTRUCTION: Provide a CLEAR, LUXURY, and PROFESSIONAL summary.\n"
            "STRUCTURE RULES:\n"
            "1. Use Markdown headers (### [File Name]) for your response.\n"
            "2. If the user asked for EXAMPLES, you MUST provide VERBATIM code blocks in triple backticks.\n"
            "STRICT GROUNDING: Do not use external knowledge. Do not hallucinate URLs.\n"
            f"CITE this file ('{name}') in your response.\n"
        )

        # Detect example request
        is_example_req = any(k in original_query.lower() for k in ["example", "snippet", "how to", "code", "template", "context"])
        if is_example_req:
            prompt += (
                "\nIMPORTANT: The user explicitly asked for EXAMPLES. "
                "You MUST INCLUDE EXTENDED VERBATIM CODE BLOCKS from the file content above. "
                "SHOW the code clearly in triple backticks.\n"
            )

        try:
            from . import chat
            # Use custom gemma3 model (4B) for individual file content analysis
            file_summary = chat.chat_with_gemma(prompt, allow_fallback=False, model_name="gemma3")
            summaries.append(f"**FILE: {name}**\nPath: `{path}`\nSummary: {file_summary}")
        except Exception as e:
            summaries.append(f"**FILE: {name}**\nPath: `{path}`\nError: *Failed to summarize: {str(e)}*")

    if actual_file_count == 0:
        return "I found only folders, which cannot be summarized by content. Please specify a file name."

    return "\n\n---\n\n".join(summaries)

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
        return JSONResponse(content={"response": "Please enter a query."})

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
                 print(f"[{datetime.now()}] DEBUG: Fallback to Gemma3 (4B) triggered.")
                 from . import chat
                 # Run in executor to avoid blocking
                 loop = asyncio.get_event_loop()
                 resp = await loop.run_in_executor(None, lambda: chat.chat_with_gemma(user_input, model_name="gemma3"))
                 return {"type": "chat", "content": resp}

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
                    return {"type": "results", "content": "No items found.", "data": []}
                else:
                    if should_summarize:
                        summary_res = summarize_results_with_gemma(results, user_input)
                        return {"type": "chat", "content": summary_res}
                    
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
                    if should_summarize:
                        summary_res = summarize_files_iteratively(results, user_input)
                        return {"type": "chat", "content": summary_res}
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
                limit=5, 
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
                     return {"type": "results", "content": f"No matches found for '{args.get('query')}'.", "data": [], "category": "files"}
                
                if should_summarize:
                    summary_res = summarize_results_with_gemma(results, user_input)
                    return {"type": "chat", "content": summary_res}

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
        log_event("ERROR", f"Backend Error: {error_trace}")
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
