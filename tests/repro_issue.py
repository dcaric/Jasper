from jasper.mail.email_tools import find_emails
from datetime import datetime, timedelta

# Mocking the date logic used by the agent
date_from = datetime.now() - timedelta(days=3)
date_to = datetime.now()

print("--- Testing 'sonja' ---")
res_sonja = find_emails(sender_name="sonja", date_from=date_from, date_to=date_to)
print(f"Results for 'sonja': {len(res_sonja) if isinstance(res_sonja, list) else res_sonja}")

print("\n--- Testing 'sumandl' ---")
res_sumandl = find_emails(sender_name="sumandl", date_from=date_from, date_to=date_to)
print(f"Results for 'sumandl': {len(res_sumandl) if isinstance(res_sumandl, list) else res_sumandl}")

print("\n--- Testing 'šumandl' ---")
res_unicode = find_emails(sender_name="šumandl", date_from=date_from, date_to=date_to)
print(f"Results for 'šumandl': {len(res_unicode) if isinstance(res_unicode, list) else res_unicode}")
