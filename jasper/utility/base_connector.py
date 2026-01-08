from abc import ABC, abstractmethod

class SearchConnector(ABC):
    """
    Abstract Base Class for all Jasper search providers (Gmail, Outlook, Files, etc.)
    This ensures a consistent interface across different data silos.
    """
    
    @abstractmethod
    def search(self, query=None, **kwargs):
        """
        Executes a search query and returns results.
        :param query: Natural language search string or primary keyword.
        :param kwargs: Additional filters (sender, subject, date_from, date_to, etc.)
        :return: List of dictionaries representing search results.
        """
        pass

    @abstractmethod
    def open(self, item_id):
        """
        Opens a specific search result.
        :param item_id: Unique identifier for the item (e.g. EntryID, Path, or MessageID).
        :return: Tuple (success: bool, message: str)
        """
        pass

    @property
    @abstractmethod
    def name(self):
        """Returns the human-readable name of the connector."""
        pass
