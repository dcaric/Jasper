import ollama
import traceback

def chat_with_gemma(prompt):
    """
    Sends the user prompt to gemma3:4b (or compatible model) 
    and returns the text response.
    """
    try:
        print(f"DEBUG: asking gemma3 (Jasper) -> '{prompt}'")
        response = ollama.chat(model='gemma3', messages=[
            {'role': 'user', 'content': prompt},
        ])
        content = response['message']['content']
        
        # Check for Fallback Signal
        import json
        try:
            # Look for JSON block if embedded in text
            import re
            json_match = re.search(r'\{.*"action":\s*"google_search".*\}', content, re.DOTALL)
            if json_match:
                 data = json.loads(json_match.group(0))
            else:
                 data = json.loads(content)

            if isinstance(data, dict) and data.get("action") == "google_search":
                query = data.get("query")
                print(f"DEBUG: Cloud Fallback Triggered -> Query: {query}")
                return call_gemini_cloud(query)
        except:
            pass # Not JSON, just normal chat
            
        return content
    except Exception as e:
        print(f"Chat Error: {e}")
        traceback.print_exc()
        return f"I'm sorry, I'm having trouble thinking right now. ({str(e)})"

def call_gemini_cloud(query):
    try:
        from google import genai
        from google.genai import types
        import json
        
        # Load API Key
        with open("constants.json", "r") as f:
            config = json.load(f)
            api_key = config.get("GEMINI_API_KEY")
            
        if not api_key:
            return "I need to check the web, but I don't have a GEMINI_API_KEY in constants.json."
            
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
        return response.text
        
    except Exception as e:
        traceback.print_exc()
        return f"I tried to check the web, but the cloud connection failed: {str(e)}"
