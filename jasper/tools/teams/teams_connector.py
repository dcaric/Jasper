from ...utility.base_connector import SearchConnector
from .teams_tools import find_messages


class TeamsConnector(SearchConnector):
    """Read-only Microsoft Teams connector backed by Microsoft Graph."""

    @property
    def name(self):
        return "Teams"

    def search(self, query=None, sender=None, subject=None, body=None, limit=5, date_from=None, date_to=None, **kwargs):
        return find_messages(
            sender_name=sender,
            subject_text=subject or query,
            body_text=body,
            limit=limit,
            date_from=date_from,
            date_to=date_to,
        )

    def open(self, item_id):
        return False, "Teams items are currently view-only in the dashboard."
