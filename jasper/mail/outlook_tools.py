import win32com.client
import os

def find_emails(sender_name=None, subject_text=None, body_text=None, limit=5, date_from=None, date_to=None, has_attachment=False):
    """
    Search Outlook emails by sender, subject, or body.
    Matches the signature of email_tools.py find_emails.
    Supports optional date_from and date_to (datetime objects).
    Supports filtering by attachment presence.
    """
    try:
        # Initialize Outlook COM
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        inbox = outlook.GetDefaultFolder(6) # 6 corresponds to olFolderInbox
        
        messages = inbox.Items
        # messages.Sort("[ReceivedTime]", True) # Moved after Restrict
        
        # Build filter
        # We use DASL for robust 'LIKE' searches
        query_parts = []
        if sender_name:
            # From property
            query_parts.append(f"\"http://schemas.microsoft.com/mapi/proptag/0x0042001f\" LIKE '%{sender_name}%'")
        if subject_text:
            # Subject property
            query_parts.append(f"\"http://schemas.microsoft.com/mapi/proptag/0x0037001f\" LIKE '%{subject_text}%'")
        if body_text:
            # Body property (urn:schemas:httpmail:textdescription)
            query_parts.append(f"\"urn:schemas:httpmail:textdescription\" LIKE '%{body_text}%'")
            print(f"DEBUG: Applied Body Filter -> LIKE '%{body_text}%'")
        
        if date_from:
            dasl_date_from = date_from.strftime("%Y-%m-%d %H:%M:%S")
            query_parts.append(f"\"http://schemas.microsoft.com/mapi/proptag/0x0E060040\" >= '{dasl_date_from}'")
            print(f"DEBUG: Applied date_from -> >= '{dasl_date_from}'")

        if date_to:
            # We add 23:59:59 to make end_date inclusive if it's just a date
            dasl_date_to = date_to.strftime("%Y-%m-%d 23:59:59")
            query_parts.append(f"\"http://schemas.microsoft.com/mapi/proptag/0x0E060040\" <= '{dasl_date_to}'")
            print(f"DEBUG: Applied date_to -> <= '{dasl_date_to}'")
            
        if has_attachment:
            # urn:schemas:httpmail:hasattachment is the DASL property for attachments
            # It maps to a boolean (1 for True)
            query_parts.append("\"urn:schemas:httpmail:hasattachment\" = 1")
            print("DEBUG: Applied Attachment Filter -> HAS ATTACHMENT")
            
        if not query_parts:
            return "Error: No search criteria provided."
            
        dasl_query = "@SQL=" + " AND ".join(query_parts)
        print(f"DEBUG: Outlook Search -> {dasl_query}")
        
        filtered_messages = messages.Restrict(dasl_query)
        filtered_messages.Sort("[ReceivedTime]", True)
        
        results = []
        count = 0
        for msg in filtered_messages:
            if count >= limit:
                break
            if msg.Class != 43: # 43 is olMail
                continue
            try:
                # We normalize the output to match email_tools.py format
                results.append({
                    "subject": msg.Subject,
                    "sender": msg.SenderName,
                    "received": str(msg.ReceivedTime),
                    "body": msg.Body[:1000] if msg.Body else "", # Snippet for AI
                    "message_id": getattr(msg, "EntryID", "NoID") # EntryID is unique in Outlook
                })
                count += 1
            except Exception:
                continue
                
        return results
    except Exception as e:
        return f"Error accessing Outlook: {str(e)}"

def find_emails_from_sender(sender_name):
    return find_emails(sender_name=sender_name)

def find_emails_by_subject(subject_text):
    return find_emails(subject_text=subject_text)

def open_email_by_id(entry_id):
    """
    Open the Outlook email window for the given EntryID.
    """
    try:
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        item = outlook.GetItemFromID(entry_id)
        item.Display()
        return True, "Opened successfully"
    except Exception as e:
        return False, str(e)

if __name__ == "__main__":
    print("Testing Outlook Search...")
    # res = find_emails(sender_name="Dario")
    # print(res)
