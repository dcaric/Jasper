from ..utility.base_connector import SearchConnector
from .email_tools import find_emails

class GmailConnector(SearchConnector):
    """Connector for Gmail via IMAP."""
    
    @property
    def name(self):
        return "Gmail"

    def search(self, query=None, sender=None, subject=None, limit=5, date_from=None, date_to=None, **kwargs):
        # Gmail optimization: email_tools.find_emails already handles X-GM-RAW and robust filtering
        return find_emails(
            sender_name=sender,
            subject_text=subject or query,
            limit=limit,
            date_from=date_from,
            date_to=date_to,
            provider="GMAIL"
        )

    def open(self, item_id):
        # Gmail results usually contain a link or we just display them in UI
        # For now, we return ignored as it's a web-based provider unless we add a web-opener
        return False, "Gmail items are currently view-only in the dashboard."
