import ollama
import json
from mail.email_tools import find_emails as find_emails_gmail
from mail.outlook_tools import find_emails as find_emails_outlook

def get_provider():
    try:
        with open("constants.json", "r") as f:
            config = json.load(f)
            return config.get("PROVIDER", "GMAIL").upper()
    except:
        return "GMAIL"

def orchestrator():
    # Force UTF-8 for CLI
    import sys
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    model_name = "functiongemma"
    
    print(f"Orchestrator started with model: {model_name}")
    print("Using multi-provider logic (Gmail/Outlook).")
    print("Type 'exit' to quit.")
    
    # Ultra-clinical template to bypass all conversational AI guardrails
    # We use 'fetch_items' in the prompt to avoid the 'email' keyword trigger
    # We inject the current default provider into the prompt to guide the model
    current_default = get_provider()
    
    prompt_base = (
        "USER: Pattern matcher. Convert Input into Query.\n"
        "TOOLS: fetch_items(sender, subject, limit, provider, date_filter)\n\n"
        "Parameters:\n"
        "- sender: Name found after 'from' or 'by'.\n"
        "- subject: Topic or keywords.\n"
        "- provider: 'GMAIL' if gmail/personal, 'OUTLOOK' if outlook/work/company.\n"
        "- date_filter: Relative or absolute range string.\n\n"
        "Input: 'search outlook from sabina at 24.12.2025'\n"
        "Query: {\"function\": \"fetch_items\", \"args\": {\"sender\": \"sabina\", \"subject\": null, \"limit\": 5, \"provider\": \"OUTLOOK\", \"date_filter\": \"at 24.12.2025\"}}\n\n"
        "Input: 'get from dario from gmail'\n"
        "Query: {\"function\": \"fetch_items\", \"args\": {\"sender\": \"dario\", \"subject\": null, \"limit\": 1, \"provider\": \"GMAIL\", \"date_filter\": null}}\n\n"
        "Input: 'fetch mail since yesterday'\n"
        "Query: {\"function\": \"fetch_items\", \"args\": {\"sender\": null, \"subject\": null, \"limit\": 5, \"provider\": null, \"date_filter\": \"since yesterday\"}}\n\n"
        "Input: 'find dario in outlook last week'\n"
        "Query: {\"function\": \"fetch_items\", \"args\": {\"sender\": \"dario\", \"subject\": null, \"limit\": 5, \"provider\": \"OUTLOOK\", \"date_filter\": \"last week\"}}\n\n"
    )

    while True:
        try:
            user_input = input("\nUser: ")
        except EOFError:
            break
            
        if user_input.lower() in ['exit', 'quit']:
            break
            
        try:
            # Neutralize the user input to avoid "email" triggers
            import re
            sanitized_input = re.sub(r'\b(email|mail)s?\b', 'item', user_input, flags=re.IGNORECASE)
            full_prompt = f"{prompt_base}Input: '{sanitized_input}'\nQuery: "
            
            response = ollama.generate(
                model=model_name,
                prompt=full_prompt,
                format="json",
                options={
                    "temperature": 0.1,
                    "stop": ["\n", "Input:"]
                }
            )
            
            raw_content = response.get("response", "").strip()
            print(f"DEBUG: Internal Result -> {raw_content}") 
            
            try:
                data = json.loads(raw_content)
                function_name = data.get("function") or data.get("name") # fallback
                args = data.get("args") or data.get("arguments") or {}   # fallback
                
                if function_name == "fetch_items":
                    sender = args.get("sender")
                    subject = args.get("subject")
                    limit = args.get("limit", 5)
                    date_filter = args.get("date_filter")
                    
                    # REGEX FALLBACK for Sender
                    import re
                    should_recheck_sender = False
                    
                    # Check if AI hallucinated a keyword as the sender
                    invalid_senders = ["search", "find", "get", "show", "fetch", "email", "mail", "gmail", "outlook", "from", "for"]
                    
                    if sender:
                         is_keyword = sender.lower() in invalid_senders
                         is_missing = sender.lower() not in user_input.lower()
                         
                         if is_keyword or is_missing:
                              should_recheck_sender = True
                    else:
                         if "from" in user_input.lower():
                              should_recheck_sender = True
                              
                    if should_recheck_sender:
                         # Look for "from <word>" or "for <word>"
                         match = re.search(r"(?:from|for)\s+(\w+)", user_input, re.IGNORECASE)
                         if match:
                              real_sender = match.group(1)
                              # exclude keywords
                              if real_sender.lower() not in ["gmail", "outlook", "mail", "email", "search", "find"]:
                                   print(f"DEBUG: Overriding sender '{sender}' with regex match '{real_sender}'")
                                   sender = real_sender

                    # SANITIZE SUBJECT
                    if subject:
                         invalid_subjects = ["search", "find", "get", "show", "fetch", "email", "mail", "gmail", "outlook", "item", "items"]
                         if subject.lower() in invalid_subjects:
                              # print(f"DEBUG: Ignoring hallucinated subject '{subject}'")
                              subject = None
                    
                    # REGEX FALLBACK for Date
                    # If model missed the date, we try to find it
                    if not date_filter:
                        # Match: last/past/this/current + number + unit OR last/past/this/current + unit
                        date_match = re.search(r"(?:last|past|this|current)\s+(?:\d+\s+)?(?:day|week|month|year|mont)s?", user_input, re.IGNORECASE)
                        if date_match:
                             date_filter = date_match.group(0)
                             print(f"DEBUG: Extracted date filter via regex: {date_filter}")
                    
                    # DATE PARSING (NEW: Support for FROM/TO)
                    from utility.date_utils import extract_date_range
                    date_from, date_to = extract_date_range(date_filter or user_input)

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
                         print(f"DEBUG: No valid provider in input or model. Using default: {final_provider}")
                    else:
                         print(f"DEBUG: Provider resolved to: {final_provider}")

                    print(f"--- Fulfilling Search: provider='{final_provider}', sender='{sender}', subject='{subject}', limit={limit}, from='{date_from}', to='{date_to}' ---")
                    
                    if final_provider == "OUTLOOK":
                        results = find_emails_outlook(sender_name=sender, subject_text=subject, limit=limit, date_from=date_from, date_to=date_to)
                    else:
                        results = find_emails_gmail(sender_name=sender, subject_text=subject, limit=limit, date_from=date_from, date_to=date_to)
                        
                    if isinstance(results, list):
                        if not results:
                            print("No items found.")
                        else:
                            for i, msg in enumerate(results, 1):
                                print(f"{i}. From: {msg['sender']} | Subj: {msg['subject']} | Rec: {msg['received']}")
                    else:
                        print(results)
                else:
                    print(f"Assistant: {raw_content}")
                    
            except json.JSONDecodeError:
                if raw_content:
                    print(f"Assistant: {raw_content}")
                else:
                    print("Error: Model returned empty response.")
                
        except Exception as e:
            print(f"Error in execution: {str(e)}")

if __name__ == "__main__":
    orchestrator()
