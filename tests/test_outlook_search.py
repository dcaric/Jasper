from jasper.mail.outlook_tools import find_emails
from datetime import datetime, timedelta

def test_outlook():
    print("Testing Outlook Search for 'Boris' in last 10 days...")
    date_from = datetime.now() - timedelta(days=10)
    
    try:
        results = find_emails(sender_name="Boris", date_from=date_from, limit=5)
        if isinstance(results, list):
            print(f"Success! Found {len(results)} emails.")
            for r in results:
                print(f"- {r['subject']} (from {r['sender']} on {r['received']})")
        else:
            print(f"Error from find_emails: {results}")
    except Exception as e:
        print(f"Exception during test: {e}")

if __name__ == "__main__":
    test_outlook()
