import imaplib
import email
from email.header import decode_header
import os
from ..utility.config import get_credentials
import shlex
import sys
import re
import datetime

# Windows Console Encoding Fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# IMAP Settings
from unidecode import unidecode

IMAP_SERVERS = {
    "GMAIL": "imap.gmail.com",
    "OUTLOOK": "outlook.office365.com"
}
IMAP_PORT = 993

def normalize_text(text):
    """
    Replaces special characters with ASCII equivalents using unidecode.
    Handles almost all languages (German, Croatian, Cyrillic, etc.) automatically.
    """
    if not text: return text
    
    # unidecode handles everything: 
    # ß -> ss, č -> c, đ -> d, ö -> o, etc.
    return unidecode(text)

def connect_imap(email_user, email_pass, provider="GMAIL"):
    try:
        server = IMAP_SERVERS.get(provider, "imap.gmail.com")
        print(f"DEBUG: Connecting to IMAP {server} for {provider}...")
        mail = imaplib.IMAP4_SSL(server, IMAP_PORT)
        mail.login(email_user, email_pass)
        return mail
    except Exception as e:
        return f"Error connecting to IMAP ({provider}): {str(e)}"

# Credentials are now managed by utility.config
pass

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

def search_emails(criteria_parts, limit=5, provider="GMAIL", headers_only=False, use_uid=False, fetch_specific_ids=None):
    """
    Search emails with standard IMAP.
    criteria_parts: List of strings like ['FROM', 'Anja'] or ['X-GM-RAW', '"query"']
    use_uid: If True, uses mail.uid('search', ...) and mail.uid('fetch', ...) (Recommended for consistency)
    fetch_specific_ids: list of IDs (UIDs if use_uid=True) to fetch directly, bypassing search.
    """
    # Debug info
    if fetch_specific_ids:
         print(f"DEBUG: IMAP MATCH FETCH ({provider}) -> IDs: {len(fetch_specific_ids)} items (UID={use_uid}, headers_only={headers_only})")
    else:
         print(f"DEBUG: IMAP SEARCH CRITERIA ({provider}) -> {criteria_parts} (UID={use_uid}, headers_only={headers_only})")
         
    email_user, email_pass = get_credentials(provider=provider)
    
    if not email_user or not email_pass or "your-email" in email_user:
        return f"Error: Please set {provider}_USER and {provider}_PASS in constants.json."
        
    mail = connect_imap(email_user, email_pass, provider=provider)
    if isinstance(mail, str):
        return mail
        
    try:
        mail.select("inbox")
        
        # 1. IDENTIFY IDs TO MEANINGFULLY FETCH
        mail_ids = []
        
        if fetch_specific_ids:
            # We already have the IDs we want to fetch
            mail_ids = fetch_specific_ids
        else:
            # We need to searching first
            
            # Helper to quote strings with spaces
            def quote_if_needed(s):
                keywords = ["FROM", "SUBJECT", "SINCE", "BEFORE", "OR", "UID", "X-GM-RAW"]
                if s.upper() in keywords:
                    return s
                if " " in s and not s.startswith('"') and not s.endswith('"'):
                    return f'"{s}"'
                return s
                
            # Determine if we need UTF-8 and apply quoting
            needs_utf8 = False
            for i, p in enumerate(criteria_parts):
                criteria_parts[i] = quote_if_needed(p)
                try:
                    criteria_parts[i].encode('ascii')
                except UnicodeEncodeError:
                    needs_utf8 = True
            
            # SEARCH EXECUTION
            if use_uid:
                # UID SEARCH
                if needs_utf8:
                    encoded_parts = [p.encode('utf-8') for p in criteria_parts]
                    status, messages = mail.uid("search", "UTF-8", *encoded_parts)
                else:
                    status, messages = mail.uid("search", None, *criteria_parts)
            else:
                # STANDARD SEARCH (Sequence Numbers)
                if needs_utf8:
                    encoded_parts = [p.encode('utf-8') for p in criteria_parts]
                    status, messages = mail.search("UTF-8", *encoded_parts)
                else:
                    status, messages = mail.search(None, *criteria_parts)
            
            if status != "OK":
                return f"Search failed: {status} {messages}"
                
            mail_ids = [m for m in messages[0].split() if m]
            # Apply limit - latest emails first
            mail_ids = mail_ids[::-1][:limit]
        
        if not mail_ids:
            mail.logout()
            return []
            
        # 2. FETCH DATA FOR THESE IDs
        # OPTIMIZATION: Batch fetch
        # Ensure ids are bytes
        encoded_ids = []
        for mid in mail_ids:
            if isinstance(mid, str):
                encoded_ids.append(mid.encode('ascii'))
            else:
                encoded_ids.append(mid)
                
        batch_ids = b",".join(encoded_ids)
        
        # Determine Fetch Command and Criteria
        # Ensure we request UID if we are using UIDs, so we can map results back accurately
        base_criteria = "RFC822.HEADER" if headers_only else "RFC822"
        fetch_criteria = f"(UID {base_criteria})"
        
        print(f"DEBUG: Batch fetching {len(mail_ids)} items using {'UID ' if use_uid else ''}FETCH...")
        
        if use_uid:
             status, msg_data = mail.uid("fetch", batch_ids, fetch_criteria)
        else:
             status, msg_data = mail.fetch(batch_ids, fetch_criteria)
        
        if status != "OK":
            mail.logout()
            # If fetch failed, it might be due to valid UIDs disappearing (deleted logic). Return empty.
            print(f"DEBUG: Fetch failed (status {status}), possibly due to invalid IDs.")
            return []
            
        results = []
        # msg_data is a list of (metadata, content) tuples followed by a closing string
        # Parsing is trickier with UID included in response
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                # response_part[0] is metadata e.g. b'1234 (UID 9999 RFC822.HEADER {size})'
                # response_part[1] is content
                
                meta = response_part[0].decode(errors="ignore")
                msg = email.message_from_bytes(response_part[1])
                
                # Extract ID (UID or Seq)
                s_id = "?"
                if use_uid:
                    # Parse proper UID from metadata: "123 (UID 5678 ...)"
                    uid_match = re.search(r"UID\s+(\d+)", meta)
                    if uid_match:
                        s_id = uid_match.group(1)
                    else:
                        print(f"DEBUG: Warning - Could not parse UID from '{meta}'")
                else:
                    # Sequence number is at the start
                    s_id = meta.split()[0]
                
                # Safe Header Decoding
                subject = decode_mime_header(msg.get("Subject"))
                sender = decode_mime_header(msg.get("From"))
                msg_id = msg.get("Message-ID", "").strip("<>")
                    
                # Extract body snippet (only if not headers_only)
                body_snippet = ""
                if not headers_only:
                    body_content = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                try:
                                    body_content = part.get_payload(decode=True).decode(errors="ignore")
                                    break
                                except: pass
                    else:
                        try:
                            body_content = msg.get_payload(decode=True).decode(errors="ignore")
                        except: pass
                    
                    # Clean up body snippet
                    body_snippet = " ".join(body_content.split())[:1000]
                    
                results.append({
                    "id": s_id, # This is now consistently the UID if use_uid=True
                    "subject": subject,
                    "sender": sender,
                    "received": str(msg.get("Date", "Unknown date")),
                    "message_id": msg_id,
                    "body": body_snippet
                })
        
        # Sort results based on original id order (latest first)
        # Note: mail_ids are bytes, s_id is string
        if fetch_specific_ids:
             # Convert fetch_specific_ids to strings for comparison
             target_order = [x.decode() if isinstance(x, bytes) else str(x) for x in fetch_specific_ids]
             id_map = {uid: i for i, uid in enumerate(target_order)}
             results.sort(key=lambda x: id_map.get(x['id'], 999))
        else:
             # Just reverse if not specific (implicit date order)
             pass 
                    
        mail.logout()
        return results
    except Exception as e:
        return f"Error during IMAP search: {str(e)}"

def find_emails(sender_name=None, subject_text=None, limit=5, date_from=None, date_to=None, provider="GMAIL"):
    """
    Search emails by sender or subject.
    Uses X-GM-RAW for Gmail to handle robust queries (unicode/phrases).
    """
    # Normalize special characters to ASCII
    sender_name_norm = normalize_text(sender_name).lower() if sender_name else None
    subject_text_norm = normalize_text(subject_text).lower() if subject_text else None
    
    # Strip quotes for clean local keyword matching
    if subject_text_norm:
        subject_text_norm = subject_text_norm.strip().strip("'").strip('"')
    
    is_gmail = (provider == "GMAIL")
    
    # GMAIL OPTIMIZATION (Option C): Use broad date search + UID fetch + local filtering
    if is_gmail and (sender_name or subject_text):
        xq = []
        from datetime import timedelta
        if date_from:
            xq.append(f'after:{date_from.strftime("%Y/%m/%d")}')
        if date_to:
            inclusive_end = date_to + timedelta(days=1)
            xq.append(f'before:{inclusive_end.strftime("%Y/%m/%d")}')
        
        # Construct query - strictly date range
        full_query = " ".join(xq)
        quoted_query = f'"{full_query}"' if full_query else '""'
        
        print(f"DEBUG: Robust Gmail Search (Option C) - Fetching UIDs for: {quoted_query}")
        
        # STEP 1 & 2: Get UIDs and Headers (Batch)
        # We increase valid fetch limit to ensure we cover the user's window
        fetch_limit = 3000
        
        # CRITICAL CHANGE: use_uid=True
        raw_results = search_emails(["X-GM-RAW", quoted_query], limit=fetch_limit, provider=provider, headers_only=True, use_uid=True)
        
        if isinstance(raw_results, str): # Error string
            return raw_results
            
        print(f"DEBUG: Processing {len(raw_results)} candidates for filtering...")
        
        # STEP 3: Local Python Filtering
        matched_uids = []
        for item in raw_results:
            match = True
            
            # Local Debug
            s_norm_debug = normalize_text(item['subject']).lower()
            if "ljeto" in s_norm_debug or "zavala" in s_norm_debug:
                 print(f"DEBUG: Candidate found: {item['subject']} (UID: {item['id']})")
            
            if sender_name_norm:
                sender_val = normalize_text(item['sender']).lower()
                for word in sender_name_norm.split():
                    if word not in sender_val:
                        match = False
                        break
            
            if subject_text_norm and match:
                subj_val = normalize_text(item['subject']).lower()
                for word in subject_text_norm.split():
                    if word not in subj_val:
                        match = False
                        break
                    
            if match:
                print(f"DEBUG: MATCHED UID {item['id']}")
                matched_uids.append(item['id'])
        
        if not matched_uids:
            return []
            
        # STEP 4: Fetch bodies ONLY for the actual matched UIDs through explicit UID fetch
        print(f"DEBUG: Gmail Match! Fetching full bodies for {len(matched_uids)} items via UID...")
        real_limit = limit if len(matched_uids) > limit else len(matched_uids)
        final_uids = matched_uids[:real_limit]
        
        # Call search_emails with explicit fetch_specific_ids (UIDs)
        return search_emails([], limit=limit, provider=provider, headers_only=False, use_uid=True, fetch_specific_ids=final_uids)


    # STANDARD IMAP FALLBACK (Outlook, etc.)
    # Note: For non-Gmail, we still normalize for safety
    sender_name = normalize_text(sender_name)
    subject_text = normalize_text(subject_text)
    
    criteria = []
    if sender_name:
        for part in sender_name.split():
             criteria.extend(["FROM", part])
    
    if subject_text:
        clean_subj = subject_text.strip('"').strip("'")
        for part in clean_subj.split():
             criteria.extend(["SUBJECT", part])
        
    if date_from:
        imap_date_from = date_from.strftime("%d-%b-%Y")
        criteria.extend(["SINCE", imap_date_from])

    if date_to:
        from datetime import timedelta
        inclusive_to = date_to + timedelta(days=1)
        imap_date_to = inclusive_to.strftime("%d-%b-%Y")
        criteria.extend(["BEFORE", imap_date_to])
        
    if not criteria:
        return "Error: No search criteria provided."
    
    return search_emails(criteria, limit=limit, provider=provider)

def find_emails_from_sender(sender_name):
    return find_emails(sender_name=sender_name)

def find_emails_by_subject(subject_text):
    return find_emails(subject_text=subject_text)

if __name__ == "__main__":
    pass
