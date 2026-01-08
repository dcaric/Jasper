from .base_connector import SearchConnector
from .semantic_tools import search_semantic
from ..filemanager.file_tools import find_files, open_file

class SemanticConnector(SearchConnector):
    """Connector for Semantic Content Search via ChromaDB with Indexer fallback."""
    
    @property
    def name(self):
        return "Semantic"

    def search(self, query=None, limit=10, folder=None, **kwargs):
        # 1. Try ChromaDB
        results = search_semantic(query=query, limit=limit, folder=folder)
        
        # 2. Fallback to Windows Indexer Content Search if nothing found
        if not results:
             print("DEBUG: [SemanticConnector] ChromaDB empty, falling back to Windows Indexer Content Search")
             results = find_files(query=query, limit=limit, content_mode=True)
             
        return results

    def open(self, item_id):
        return open_file(item_id)
