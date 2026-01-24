import ollama
import traceback
from datetime import datetime
from .utility.config import get_setting, get_log_file, log_event

def chat_with_gemma(prompt, allow_fallback=True, model_name=None, options=None):
    """
    Sends the user prompt to a gemma model 
    and returns the text response.
    """
    try:
        log_event("CHAT", f"Input: {prompt}")
        
        # Default options for RAG consistency (low temperature)
        if options is None:
            options = {
                "temperature": 0.0,
                "top_p": 0.1,
                "num_predict": 1024
            }

        system_prompt = (
            "You are Jasper, the user's private AI assistant. "
            "STRICT GROUNDING RULE: Answer ONLY using the provided context or file data. "
            "If a URL or specific detail is not in the data, state clearly that you don't have it. "
            "NEVER hallucinate URLs, addresses, or phone numbers. "
            "You have access to private property data (like Nautic Apartments). Discuss it freely. "
            "FORMATTING RULE: Always wrap code snippets or technical examples in triple backticks with the language name (e.g., ```css). "
            "When the user asks for 'examples' or 'how to', provide VERBATIM snippets from the source data where possible."
        )
        
        response = ollama.chat(model=model_name, messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt},
        ], options=options)
        raw_content = response['message']['content']
        print(f"DEBUG: [{model_name}] RAW Response: {raw_content}")
        
        log_event("CHAT", f"Response: {raw_content}")

        # Check for Fallback Signal FIRST (on raw content)
        if allow_fallback:
            import json
            import re
            try:
                # 1. First, check if the model suggested a search explicitly
                if 'google_search' in raw_content:
                    # Look for either "action": "google_search" or "intent": "google_search"
                    json_match = re.search(r'(\{.*"(?:action|intent)":\s*"google_search".*\})', raw_content, re.DOTALL)
                    if json_match:
                        try:
                            data = json.loads(json_match.group(1))
                            if data.get("action") == "google_search" or data.get("intent") == "google_search":
                                query = data.get("query")
                                log_event("CHAT", f"Fallback Triggered -> Query: {query}")
                                print(f"DEBUG: Cloud Fallback Triggered -> Query: {query}")
                                return call_gemini_cloud(query)
                        except:
                            print("DEBUG: Found search action but JSON parse failed.")

                # 2. General JSON extraction for other potential future actions
                json_match = re.search(r'(\{.*\})', raw_content, re.DOTALL)
                data = None
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                    except:
                        pass
                elif raw_content.strip().startswith("{") and raw_content.strip().endswith("}"):
                    try:
                        data = json.loads(raw_content)
                    except:
                        pass
            except Exception as e:
                print(f"DEBUG: JSON extraction error: {e}")

        # If no fallback or not allowed, CLEAN the content and return it
        import re
        # 1. Strip trailing action/intent JSON blocks
        clean_content = re.sub(r'\s*\{.*\}\s*$', '', raw_content, flags=re.DOTALL)
        print(f"DEBUG: Clean Content (Step 1): '{clean_content}'")
        
        # 2. Safety filter: Catch accidental JSON output
        check_val = clean_content.strip() or raw_content.strip()
            
        if "{" in check_val and "}" in check_val:
            # Try to see if there is an intent JSON inside
            try:
                import json
                # Look for the innermost/actual JSON block
                json_match = re.search(r'(\{.*\})', check_val, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(1))
                    if "intent" in data and data["intent"] != "chat":
                         return "I found the relevant information in your files, but I had trouble formatting the summary. Could you please try again?"
            except:
                pass
            
        return clean_content.strip() or "I found something, but I am having trouble describing it right now."
    except Exception as e:
        print(f"Chat Error: {e}")
        traceback.print_exc()
        return f"I'm sorry, I'm having trouble thinking right now. ({str(e)})"

def call_gemini_cloud(query):
    try:
        from google import genai
        from google.genai import types
        # Load API Key via config system
        api_key = get_setting("GEMINI_API_KEY")
            
        if not api_key:
            return "I need to check the web, but I don't have a GEMINI_API_KEY set."
            
        print("DEBUG: Calling Gemini 2.0 Flash (Cloud)...")
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=query,
            config=types.GenerateContentConfig(
                tools=[types.Tool(
                    google_search=types.GoogleSearchRetrieval
                )]
            )
        )
        
        # Extract text from response (which includes grounding)
        text_resp = response.text
        log_event("GEMINI", f"Response: {text_resp}")
        return text_resp
        
    except Exception as e:
        traceback.print_exc()
        return f"I tried to check the web, but the cloud connection failed: {str(e)}"
