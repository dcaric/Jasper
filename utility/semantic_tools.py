import chromadb
from chromadb.utils import embedding_functions
import os

# CONFIGURATION
DB_PATH = "./chroma_db"
COLLECTION_NAME = "jasper_docs"

# EMBEDDING MODEL (Must match indexer.py)
embedding_func = embedding_functions.DefaultEmbeddingFunction()

# INITIALIZE CHROMA
client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_or_create_collection(
    name=COLLECTION_NAME, 
    embedding_function=embedding_func
)

def search_semantic(query, limit=5, folder=None):
    """
    Performs a semantic search in the ChromaDB collection.
    Returns a list of matching code/text chunks.
    Optional: filter by folder name.
    """
    try:
        where_filter = None
        if folder:
            # Match both provided case and lowercase for robustness
            where_filter = {"parent": {"$in": [folder, folder.lower(), folder.capitalize()]}}
            print(f"DEBUG: Applying Folder Filter -> {folder} (Check cases: {folder}, {folder.lower()}, {folder.capitalize()})")

        results = collection.query(
            query_texts=[query],
            n_results=limit * 4, # Fetch more to allow for file-level deduplication
            where=where_filter
        )
        
        formatted_results = []
        seen_filenames = set()
        
        if results['documents']:
            for i in range(len(results['documents'][0])):
                doc = results['documents'][0][i]
                meta = results['metadatas'][0][i]
                path = meta.get("source", "")
                fname = meta.get("filename", "Unknown")
                dist = results['distances'][0][i] if 'distances' in results else 0
                
                # Deduplication: only take the first (best) match per filename
                # This ensures variety (e.g. not seeing CODE_OF_CONDUCT 10 times)
                if fname in seen_filenames:
                    continue
                seen_filenames.add(fname)
                
                formatted_results.append({
                    "name": fname,
                    "path": path,
                    "parent": meta.get("parent", ""),
                    "directory": meta.get("directory", ""),
                    "content": doc,
                    "score": round(1 - dist, 4), 
                    "kind": "semantic_match"
                })
                
                # Stop if we hit the requested unique file limit
                if len(formatted_results) >= limit:
                    break
                    
        return formatted_results
    except Exception as e:
        print(f"Error in semantic search: {e}")
        return []

if __name__ == "__main__":
    test_query = "how to setup outlook search"
    print(f"Searching for: {test_query}")
    res = search_semantic(test_query)
    for r in res:
        print(f"[{r['score']}] {r['name']} - {r['content'][:100]}...")
