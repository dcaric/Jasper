import os
import datetime
from jasper.mail.email_tools import find_emails
from jasper.utility.config import get_credentials

def check_booking_requests():
    # Calculate date range (last 15 days)
    today = datetime.datetime.now()
    date_from_obj = today - datetime.timedelta(days=15)
    
    print(f"Searching for 'booking request' since {date_from_obj.strftime('%d-%b-%Y')}...")
    
    try:
        # Using Gmail provider as requested and configured in .env
        emails = find_emails(
            subject_text="booking request",
            date_from=date_from_obj,
            limit=10,
            provider="GMAIL"
        )
        
        if not emails:
            print("No emails found with subject 'booking request' in the last 15 days.")
            return

        print(f"Found {len(emails)} emails:")
        for i, email_data in enumerate(emails, 1):
            print(f"\n[{i}] Subject: {email_data.get('subject', 'No Subject')}")
            print(f"    From: {email_data.get('from', 'Unknown')}")
            print(f"    Date: {email_data.get('date', 'Unknown')}")
            # Snippet if available
            snippet = email_data.get('body_snippet', '')
            if snippet:
                print(f"    Snippet: {snippet[:100]}...")
                
    except Exception as e:
        print(f"Error during search: {e}")

if __name__ == "__main__":
    check_booking_requests()
