import ollama
import traceback
from datetime import datetime
from .utility.config import get_setting, get_log_file, log_event
from .utility.usage import update_usage

def is_gemini_enabled():
    """Checks if Gemini usage is enabled in settings and API key is present."""
    usage = get_setting("GEMINI_USAGE", "1")
    key = get_setting("GEMINI_API_KEY")
    return usage == "1" and bool(key)

def chat_with_gemma(prompt, allow_fallback=True, model_name="gemma3", options=None):
    """
    Sends the user prompt to Gemini (formerly Gemma wrapper).
    Returns only the text for backward compatibility with most callers, 
    but we should ideally update all to handle tuples.
    """
    try:
        log_event("CHAT", f"Input: {prompt[:200]}...")
        
        # We now skip Gemma and go straight to Gemini
        # Heuristic for data: if it's very long or contains certain headers
        is_data = len(prompt) > 2000 or any(kw in prompt.lower() for kw in ["content:", "email body:", "file content:"])
        
        raw_content, data_sent = chat_with_gemini(prompt, data_sent_flag=is_data)
        return raw_content
    except Exception as e:
        log_event("ERROR", f"Chat Error: {e}")
        return f"I'm sorry, I'm having trouble thinking right now. ({str(e)})"

def call_gemini_cloud(query, system_instruction=None):
    """
    Calls Gemini Pro in the cloud for web data or deep analysis.
    Returns (response_text, data_sent_flag)
    """
    try:
        from google import genai
        from google.genai import types
        if not is_gemini_enabled():
            return "Gemini features are currently disabled via GEMINI_USAGE or missing API key.", False
            
        is_data = len(query) > 2000 or any(kw in query.lower() for kw in ["content:", "email body:", "file content:"])

        api_key = get_setting("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key)
        
        config_params = {
            "tools": [types.Tool(google_search=types.GoogleSearchRetrieval())]
        }
        if system_instruction:
            config_params['system_instruction'] = system_instruction
            
        config = types.GenerateContentConfig(**config_params)
        
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=query,
            config=config
        )
        
        # Extract tokens if available
        try:
            update_usage(response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
        except:
            pass
            
        text_resp = response.text
        log_event("GEMINI", f"Response: {text_resp[:200]}...")
        return text_resp, is_data
        
    except Exception as e:
        log_event("ERROR", f"Gemini Cloud failure: {str(e)}")
        return f"Gemini cloud error: {str(e)}", False

def chat_with_gemini(prompt, system_instruction=None, json_mode=False, data_sent_flag=False):
    """
    Sends the prompt to Gemini cloud model and returns (response_text, data_sent_flag).
    """
    try:
        from google import genai
        from google.genai import types
        if not is_gemini_enabled():
            return "Gemini features are currently disabled.", False
            
        api_key = get_setting("GEMINI_API_KEY")
            
        client = genai.Client(api_key=api_key)
        
        config_params = {}
        if system_instruction:
            config_params['system_instruction'] = system_instruction
        if json_mode:
            config_params['response_mime_type'] = 'application/json'
            
        config = types.GenerateContentConfig(**config_params) if config_params else None
            
        log_event("GEMINI", f"Input: {prompt[:200]}...")
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=config
        )
        
        # Extract tokens if available
        try:
            update_usage(response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count)
        except:
            pass

        raw_content = response.text
        log_event("GEMINI", f"Response: {raw_content[:200]}...")
        return raw_content, data_sent_flag
    except Exception as e:
        log_event("ERROR", f"Gemini Chat failure: {str(e)}")
        return f"Gemini connection failed: {str(e)}", False
