import sys
import os
from datetime import datetime, timedelta

# Ensure jasper is in path
sys.path.append(os.getcwd())

from jasper.mail.email_tools import find_emails, normalize_text

print(">>> INSPECTING RECENT EMAILS (Last 40 days)")

# 1. Fetch ALL metadata for last 40 days (limit 50)
# We use a trick: search for something broad or just by date
# find_emails uses date range if provided. If we provide NO query, it might fail or default.
# Let's use a broad subject search that won't filter much, or just call search_emails directly.

from jasper.mail.email_tools import search_emails

date_from = datetime.now() - timedelta(days=40)
xq = f'after:{date_from.strftime("%Y/%m/%d")}'
quoted_query = f'"{xq}"'

print(f"Query: {quoted_query}")
results = search_emails(["X-GM-RAW", quoted_query], limit=50, provider="GMAIL", headers_only=False)

if isinstance(results, str):
    print(f"Error: {results}")
else:
    print(f"Fetched {len(results)} emails. Listing ALL subject lines...")
    for i, item in enumerate(results):
        print(f"[{i+1}] {item['received']} | {item['sender']} | {item['subject']}")
