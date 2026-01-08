from ..utility.base_connector import SearchConnector
from .outlook_tools import find_emails, open_email_by_id
from .email_tools import find_emails as find_emails_imap
from ..utility.config import get_setting

class OutlookConnector(SearchConnector):
    """Connector for Outlook (COM for Classic, IMAP for New)."""
    
    @property
    def name(self):
        return "Outlook"

    def search(self, query=None, sender=None, subject=None, body=None, limit=5, date_from=None, date_to=None, has_attachment=False, **kwargs):
        # Determine if we should use IMAP or COM
        # (Already handled in app.py previously, but let's centralize it here)
        use_imap = bool(get_setting("OUTLOOK_PASS") or get_setting("OUTLOOK_PASSWORD"))
        
        if use_imap:
            return find_emails_imap(
                sender_name=sender,
                subject_text=subject or query,
                limit=limit,
                date_from=date_from,
                date_to=date_to,
                provider="OUTLOOK"
            )
        else:
            return find_emails(
                sender_name=sender,
                subject_text=subject or query,
                body_text=body,
                limit=limit,
                date_from=date_from,
                date_to=date_to,
                has_attachment=has_attachment
            )

    def open(self, item_id):
        # Outlook items can be opened via COM EntryID
        return open_email_by_id(item_id)
