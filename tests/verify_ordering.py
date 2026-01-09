import sys
import os
from datetime import datetime, timedelta

# Ensure jasper is in path
sys.path.append(os.getcwd())

from jasper.mail.email_tools import find_emails

# Use a date range likely to have emails
date_from = datetime.now() - timedelta(days=60)
date_to = datetime.now()

def test_query(subject_query):
    print(f"\n>>> TESTING SUBJECT: '{subject_query}'")
    res = find_emails(subject_text=subject_query, date_from=date_from, date_to=date_to)
    if isinstance(res, list):
        print(f"FOUND: {len(res)} items")
        for i, item in enumerate(res):
            print(f"  {i+1}. From: {item['sender']} | Subj: {item['subject']}")
    else:
        print(f"ERROR/RESULT: {res}")

# Test normal order
test_query("ljeto zavala")

# Test reversed order
test_query("zavala ljeto")
