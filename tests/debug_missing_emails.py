import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.getcwd())

from jasper.mail.email_tools import search_emails, normalize_text

print(">>> DEBUGGING MISSING EMAILS")

# 1. Setup Date Range (Last 45 days to be safe)
date_from = datetime.now() - timedelta(days=45)
xq = f'after:{date_from.strftime("%Y/%m/%d")}'
quoted_query = f'"{xq}"'

print(f"Querying Gmail: {quoted_query}")

# 2. Fetch Headers (Limit 3000)
results = search_emails(["X-GM-RAW", quoted_query], limit=3000, provider="GMAIL", headers_only=True)

if isinstance(results, str):
    print(f"Error fetching: {results}")
    sys.exit(1)

print(f"Fetched {len(results)} candidate emails.")

# 3. MOCK FILTERING LOGIC
target_keywords = ["ljeto", "zavala"]
print(f"Looking for keywords: {target_keywords} (Order Independent)")

found_count = 0
partial_match_count = 0

for item in results:
    s_norm = normalize_text(item['subject']).lower()
    
    # Check if ANY keyword is present (for debug)
    has_partial = False
    for k in target_keywords:
        if k in s_norm:
            has_partial = True
            break
            
    # Check if ALL keywords are present (The actual logic)
    all_match = True
    missing_words = []
    for k in target_keywords:
        if k not in s_norm:
            all_match = False
            missing_words.append(k)
            
    if all_match:
        found_count += 1
        print(f"\n[MATCH] ID: {item['id']}")
        print(f"  Subject: {item['subject']}")
        print(f"  Norm:    {s_norm}")
        
    elif has_partial:
        partial_match_count += 1
        print(f"\n[PARTIAL/FAIL] ID: {item['id']}")
        print(f"  Subject: {item['subject']}")
        print(f"  Norm:    {s_norm}")
        print(f"  Missing: {missing_words}")

print(f"\nSummary: Found {found_count} exact matches. {partial_match_count} partial matches rejected.")
