import sys
import os
from datetime import datetime, timedelta

# Ensure jasper is in path
sys.path.append(os.getcwd())

from jasper.mail.email_tools import find_emails

# Use fixed dates for consistency
date_from = datetime(2026, 1, 6)
date_to = datetime(2026, 1, 9)

def test_query(name):
    print(f"\n>>> TESTING: {name}")
    res = find_emails(sender_name=name, date_from=date_from, date_to=date_to)
    if isinstance(res, list):
        print(f"FOUND: {len(res)} items")
        for i, item in enumerate(res):
            print(f"  {i+1}. From: {item['sender']} | Subj: {item['subject']}")
    else:
        print(f"ERROR/RESULT: {res}")

test_query("sonja")
test_query("sumandl")
test_query("šumandl")
