import ollama
import traceback
from datetime import datetime
from .utility.config import get_setting, get_log_file

def chat_with_gemma(prompt, allow_fallback=True):
    """
    Sends the user prompt to gemma3:4b (or compatible model) 
    and returns the text response.
    """
    try:
        log_msg = f"[{datetime.now()}] [CHAT] Input: {prompt}\n"
        with open(get_log_file(), "a", encoding="utf-8") as f:
            f.write(log_msg)
        # Get model from settings (consistent with app.py)
        model_name = get_setting("MODEL_NAME", "jasper")
        print(f"DEBUG: asking {model_name} (Jasper) -> '{prompt}'")
        
        response = ollama.chat(model=model_name, messages=[
            {'role': 'user', 'content': prompt},
        ])
        raw_content = response['message']['content']
        
        with open(get_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] [CHAT] Response: {raw_content}\n")

        # Check for Fallback Signal FIRST (on raw content)
        if allow_fallback:
            import json
            import re
            try:
                # 1. Try to find JSON block in the raw content
                json_match = re.search(r'\{.*"action":\s*"google_search".*\}', raw_content, re.DOTALL)
                
                # 2. Extract and parse data if found
                data = None
                if json_match:
                    data = json.loads(json_match.group(0))
                elif raw_content.strip().startswith("{") and raw_content.strip().endswith("}"):
                    # Maybe it's ONLY JSON
                    data = json.loads(raw_content)

                if isinstance(data, dict) and data.get("action") == "google_search":
                    query = data.get("query")
                    log_msg = f"[{datetime.now()}] [CHAT] Fallback Triggered -> Query: {query}\n"
                    with open(get_log_file(), "a", encoding="utf-8") as f:
                        f.write(log_msg)
                    print(f"DEBUG: Cloud Fallback Triggered -> Query: {query}")
                    return call_gemini_cloud(query)
            except Exception as e:
                print(f"DEBUG: JSON parse failed (likely just normal text): {e}")

        # If no fallback or not allowed, CLEAN the content and return it
        import re
        # 1. Strip trailing action/intent JSON blocks
        clean_content = re.sub(r'\s*\{.*"(action|intent)":\s*".*"\s*\}\s*$', '', raw_content, flags=re.DOTALL)
        
        # 2. If the entire response is JUST a JSON block (e.g. from an over-eager model),
        # explaining the search instead of doing it, we should provide a natural message.
        if clean_content.strip().startswith("{") and clean_content.strip().endswith("}"):
            try:
                import json
                data = json.loads(clean_content)
                if "intent" in data or "action" in data:
                    return f"I'm sorry, I encountered a temporary delay in processing that search request. Could you please try again in a moment?"
            except:
                pass
            
        return clean_content.strip()
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
        with open(get_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] [GEMINI] Response: {text_resp}\n")
        return text_resp
        
    except Exception as e:
        traceback.print_exc()
        return f"I tried to check the web, but the cloud connection failed: {str(e)}"
