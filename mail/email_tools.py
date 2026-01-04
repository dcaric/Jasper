import imaplib
import email
from email.header import decode_header
import os
import json
import shlex
import sys
import datetime

# Windows Console Encoding Fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# IMAP Settings
IMAP_SERVERS = {
    "GMAIL": "imap.gmail.com",
    "OUTLOOK": "outlook.office365.com"
}
IMAP_PORT = 993

def normalize_text(text):
    """Replaces Croatian characters with ASCII equivalents for safe search."""
    if not text: return text
    
    # Map of special chars to ASCII
    mapping = {
        'ž': 'z', 'Ž': 'Z',
        'ć': 'c', 'Ć': 'C',
        'č': 'c', 'Č': 'C',
        'š': 's', 'Š': 'S',
        'đ': 'd', 'Đ': 'D'
    }
    
    res = text
    for char, replacement in mapping.items():
        res = res.replace(char, replacement)
    return res

def connect_imap(email_user, email_pass, provider="GMAIL"):
    try:
        server = IMAP_SERVERS.get(provider, "imap.gmail.com")
        print(f"DEBUG: Connecting to IMAP {server} for {provider}...")
        mail = imaplib.IMAP4_SSL(server, IMAP_PORT)
        mail.login(email_user, email_pass)
        return mail
    except Exception as e:
        return f"Error connecting to IMAP ({provider}): {str(e)}"

def get_credentials(provider="GMAIL"):
    try:
        with open("constants.json", "r") as f:
            config = json.load(f)
            
            if provider == "OUTLOOK":
                user = config.get("OUTLOOK_USER") or config.get("GMAIL_USER") # Fallback to GMAIL_USER if strictly using one email
                password = config.get("OUTLOOK_PASS", config.get("OUTLOOK_PASSWORD"))
            else:
                user = config.get("GMAIL_USER")
                password = config.get("GMAIL_PASS")
                
            if password:
                password = password.replace(" ", "")
            return user, password
    except Exception:
        return None, None

def decode_mime_header(raw_header):
    if not raw_header:
        return "No Subject"
    try:
        decoded = decode_header(raw_header)
        parts = []
        for text, encoding in decoded:
            if isinstance(text, bytes):
                try:
                    parts.append(text.decode(encoding if encoding else "utf-8", errors="ignore"))
                except LookupError:
                    parts.append(text.decode("utf-8", errors="ignore"))
            else:
                parts.append(str(text))
        return " ".join(parts)
    except Exception:
        return str(raw_header)

def search_emails(criteria_parts, limit=5, provider="GMAIL"):
    """
    Search emails with standard IMAP.
    criteria_parts: List of strings like ['FROM', 'Anja'] or ['X-GM-RAW', '"query"']
    """
    print(f"DEBUG: IMAP SEARCH CRITERIA ({provider}) -> {criteria_parts}")
    email_user, email_pass = get_credentials(provider=provider)
    
    if not email_user or not email_pass or "your-email" in email_user:
        return f"Error: Please set {provider}_USER and {provider}_PASS in constants.json."
        
    mail = connect_imap(email_user, email_pass, provider=provider)
    if isinstance(mail, str):
        return mail
        
    try:
        mail.select("inbox")
        
        # Helper to quote strings with spaces
        def quote_if_needed(s):
            if " " in s and not s.startswith('"') and not s.endswith('"'):
                return f'"{s}"'
            return s
            
        # Determine if we need UTF-8 and apply quoting
        needs_utf8 = False
        for i, p in enumerate(criteria_parts):
            # Always quote if it has a space
            criteria_parts[i] = quote_if_needed(p)
            
            # Check if this part (now potentially quoted) needs UTF-8
            try:
                criteria_parts[i].encode('ascii')
            except UnicodeEncodeError:
                needs_utf8 = True
        
        if needs_utf8:
            # For non-ASCII, we fallback to UTF-8
            # Note: X-GM-RAW usually handles UTF-8 literals if ENABLE UTF8=ACCEPT is supported,
            # otherwise sending straight UTF-8 bytes usually works with CHARSET UTF-8.
            encoded_parts = [p.encode('utf-8') for p in criteria_parts]
            status, messages = mail.search("UTF-8", *encoded_parts)
        else:
            # For ASCII, simple search is most compatible.
            status, messages = mail.search(None, *criteria_parts)
        
        if status != "OK":
            return f"Search failed: {status} {messages}"
            
        mail_ids = [m for m in messages[0].split() if m]
        # Apply limit - latest emails first
        mail_ids = mail_ids[::-1][:limit]
        
        results = []
        for m_id in mail_ids:
            res, msg_data = mail.fetch(m_id, "(RFC822)")
            if res != "OK":
                continue
                
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Safe Header Decoding
                    subject = decode_mime_header(msg.get("Subject"))
                    sender = decode_mime_header(msg.get("From"))
                    msg_id = msg.get("Message-ID", "").strip("<>")
                        
                    # Extract body snippet
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                try:
                                    body = part.get_payload(decode=True).decode(errors="ignore")
                                    break
                                except: pass
                    else:
                        try:
                            body = msg.get_payload(decode=True).decode(errors="ignore")
                        except: pass
                    
                    # Clean up body snippet
                    body_snippet = " ".join(body.split())[:1000]
                        
                    results.append({
                        "subject": subject,
                        "sender": sender,
                        "received": str(msg.get("Date", "Unknown date")),
                        "message_id": msg_id,
                        "body": body_snippet
                    })
                    
        mail.logout()
        return results
    except Exception as e:
        return f"Error during IMAP search: {str(e)}"

def find_emails(sender_name=None, subject_text=None, limit=5, date_from=None, date_to=None, provider="GMAIL"):
    """
    Search emails by sender or subject.
    Uses X-GM-RAW for Gmail to handle robust queries (unicode/phrases).
    Falls back to STANDARD IMAP for others.
    """
    # Normalize special characters to ASCII to avoid IMAP parsing errors
    # as per user request (č -> c, etc.)
    sender_name = normalize_text(sender_name)
    subject_text = normalize_text(subject_text)
    
    # SAFETY: Strip quotes from inputs to prevent X-GM-RAW syntax errors (BAD command)
    if sender_name:
        sender_name = sender_name.replace('"', '').replace("'", "").strip()
    if subject_text:
        subject_text = subject_text.replace('"', '').replace("'", "").strip()
    
    # Check if we are aiming for Gmail
    is_gmail = (provider == "GMAIL")
    
    # GMAIL OPTIMIZATION: Use X-GM-RAW for robust phrase search (e.g. "ljeto zavala")
    # This avoids slicing phrases into separate SUBJECT keywords which fails in standard IMAP.
    if is_gmail and (sender_name or subject_text):
        # Construct X-GM-RAW query string
        xq = []
        if sender_name:
            xq.append(f'from:{sender_name}')
        if subject_text:
             cleaned_subj = subject_text.replace('"', '').replace("'", "")
             xq.append(f'subject:({cleaned_subj})')
            
        # Handle dates in X-GM-RAW format (YYYY/MM/DD)
        # Note: Gmail 'after' and 'before' are usually exclusive boundaries depending on granularity.
        # To be safe and inclusive for "from 05.01", we use "after:04.01".
        # To be safe for "to 06.01", we use "before:07.01".
        from datetime import timedelta
        
        if date_from:
            # Gmail 'after' is inclusive (>=), so we use the date as is.
            xq.append(f'after:{date_from.strftime("%Y/%m/%d")}')
            
        if date_to:
            # Gmail 'before' is exclusive (<), so we add 1 day to make it inclusive of the end date.
            inclusive_end = date_to + timedelta(days=1)
            xq.append(f'before:{inclusive_end.strftime("%Y/%m/%d")}')
            
        full_query = " ".join(xq)
        # We must wrap the entire query in double quotes for the X-GM-RAW argument
        quoted_query = f'"{full_query}"'
        
        print(f"DEBUG: Using X-GM-RAW Criteria -> {quoted_query}")
        return search_emails(["X-GM-RAW", quoted_query], limit=limit, provider=provider)

    # STANDARD IMAP FALLBACK (Outlook, etc.) or if no text search
    criteria = []

    # Split keywords with spaces into multiple criteria to avoid quoting/literal issues
    if sender_name:
        for part in sender_name.split():
             criteria.extend(["FROM", part])
    
    if subject_text:
        # Strip potential quotes first
        clean_subj = subject_text.strip('"').strip("'")
        for part in clean_subj.split():
             criteria.extend(["SUBJECT", part])
        
    if date_from:
        # IMAP SINCE format: DD-Mon-YYYY
        imap_date_from = date_from.strftime("%d-%b-%Y")
        criteria.extend(["SINCE", imap_date_from])
        print(f"DEBUG: Applied date_from -> SINCE {imap_date_from}")

    if date_to:
        # IMAP BEFORE format: DD-Mon-YYYY
        # VERY IMPORTANT: IMAP BEFORE is exclusive. To make it inclusive of the 'date_to' 
        # day, we must add one day to the criteria.
        from datetime import timedelta
        inclusive_to = date_to + timedelta(days=1)
        imap_date_to = inclusive_to.strftime("%d-%b-%Y")
        criteria.extend(["BEFORE", imap_date_to])
        print(f"DEBUG: Applied inclusive date_to -> BEFORE {imap_date_to} (original was {date_to.strftime('%d-%b-%Y')})")
        
    if not criteria:
        return "Error: No search criteria provided."
    
    return search_emails(criteria, limit=limit, provider=provider)

def find_emails_from_sender(sender_name):
    return find_emails(sender_name=sender_name)

def find_emails_by_subject(subject_text):
    return find_emails(subject_text=subject_text)

if __name__ == "__main__":
    pass
