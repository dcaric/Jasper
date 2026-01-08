from ..utility.base_connector import SearchConnector
from .file_tools import find_files, open_file

class FileConnector(SearchConnector):
    """Connector for local files via Windows Indexer."""
    
    @property
    def name(self):
        return "Files"

    def search(self, query=None, limit=10, kind=None, date_from=None, date_to=None, content_mode=False, **kwargs):
        return find_files(
            query=query,
            limit=limit,
            kind=kind,
            date_from=date_from,
            date_to=date_to,
            content_mode=content_mode
        )

    def open(self, item_id):
        # item_id is the file path for this connector
        return open_file(item_id)
