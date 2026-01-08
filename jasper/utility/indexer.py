import os
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path
import hashlib
import json
from datetime import datetime
import argparse
from .config import get_db_path, get_status_file

# CONFIGURATION
DB_PATH = get_db_path()
COLLECTION_NAME = "jasper_docs"
CHUNK_SIZE = 1000  # Characters
CHUNK_OVERLAP = 100

# EMBEDDING MODEL (Chroma Default: all-MiniLM-L6-v2 ONNX)
embedding_func = embedding_functions.DefaultEmbeddingFunction()

# INITIALIZE CHROMA
client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_or_create_collection(
    name=COLLECTION_NAME, 
    embedding_function=embedding_func
)

def get_file_hash(path):
    """Generate a hash for a file to check for content changes."""
    hasher = hashlib.md5()
    try:
        with open(path, 'rb') as f:
            buf = f.read(65536)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
        return hasher.hexdigest()
    except:
        return ""

def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks."""
    chunks = []
    if not text: return chunks
    
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += (size - overlap)
    return chunks

def index_file(file_path):
    """Reads, chunks, and adds a file to ChromaDB."""
    try:
        path_obj = Path(file_path)
        if not path_obj.exists(): return
        
        mtime = os.path.getmtime(file_path)
        f_hash = get_file_hash(file_path)
        
        # Supports web dev files and project source
        ext = path_obj.suffix.lower()
        allowed_exts = ['.txt', '.md', '.py', '.bat', '.html', '.css', '.js', '.json', '.c', '.cpp', '.h']
        if ext not in allowed_exts and path_obj.name != 'Modelfile': 
            return
            
        import re
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        if ext == '.html':
            content = re.sub(r'<(script|style).*?>.*?</\1>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<.*?>', ' ', content)
            content = re.sub(r'\s+', ' ', content).strip()
            
        if not content.strip(): return

        # Delete old chunks
        collection.delete(where={"source": str(path_obj.absolute())})
        
        # Chunk and Add
        chunks = chunk_text(content)
        ids = [f"{str(path_obj.absolute())}_{i}" for i in range(len(chunks))]
        metadatas = [{
            "source": str(path_obj.absolute()),
            "filename": path_obj.name,
            "directory": str(path_obj.parent.absolute()),
            "parent": path_obj.parent.name,
            "mtime": mtime,
            "hash": f_hash
        } for _ in range(len(chunks))]
        
        collection.add(
            ids=ids,
            documents=chunks,
            metadatas=metadatas
        )
        safe_name = path_obj.name.encode('ascii', 'ignore').decode('ascii')
        print(f"Indexed {len(chunks)} chunks from: {safe_name}")
        
    except Exception as e:
        print(f"Error indexing {file_path}: {e}")

def update_status(progress_pct, status_text):
    """Writes progress to a local JSON file for the main app to read."""
    try:
        with open(get_status_file(), "w") as f:
            json.dump({
                "percent": progress_pct,
                "status": status_text,
                "updated_at": str(datetime.now())
            }, f)
    except:
        pass

def prune_index():
    """Removes entries from the index if the source file no longer exists."""
    print("Pruning stale entries from index...")
    results = collection.get()
    if not results or not results['metadatas']:
        print("Index is empty.")
        return

    seen_sources = set()
    to_delete = []

    for meta in results['metadatas']:
        source = meta.get('source')
        if source and source not in seen_sources:
            seen_sources.add(source)
            if not os.path.exists(source):
                to_delete.append(source)

    if to_delete:
        print(f"Removing {len(to_delete)} stale files from index.")
        for source in to_delete:
            collection.delete(where={"source": source})
            print(f"Deleted: {source}")
    else:
        print("No stale entries found.")

def show_status():
    """Displays stats about the current index."""
    count = collection.count()
    print(f"--- Jasper Index Status ---")
    print(f"Total Chunks: {count}")
    
    results = collection.get()
    if results and results['metadatas']:
        unique_files = len(set(m.get('source') for m in results['metadatas']))
        print(f"Unique Files: {unique_files}")
    
    status_file = get_status_file()
    if os.path.exists(status_file):
        with open(status_file, "r") as f:
            data = json.load(f)
            print(f"Last UI Status: {data.get('status')} ({data.get('percent')}%)")
            print(f"Last Updated: {data.get('updated_at')}")
    print(f"---------------------------")

def index_all(force=False):
    skip_folders = [
        'AppData', 'LocalLow', 'Local', 'Roaming', 
        'node_modules', '.git', '.venv', 'venv',   
        'Pictures', 'Music', 'Videos', 'Searches', 
        'Saved Games', 'Links', 'Contacts', 'OneDrive'
    ]
    
    all_files = []
    workspace = os.getcwd()
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in skip_folders and not d.startswith('.')]
        for file in files:
            if file.endswith(('.txt', '.md', '.py', '.bat', '.html', '.js', '.css', '.json')) or file == 'Modelfile':
                all_files.append(os.path.join(root, file))

    working_dir = r"C:\Users\Dario\WORKING"
    if os.path.exists(working_dir) and working_dir not in workspace:
        for root, dirs, files in os.walk(working_dir):
            dirs[:] = [d for d in dirs if d not in skip_folders and not d.startswith('.')]
            for file in files:
                f_path = os.path.join(root, file)
                if f_path.endswith(('.txt', '.md', '.py', '.bat', '.html', '.js', '.css', '.json')) or Path(f_path).name == 'Modelfile':
                    if f_path not in all_files:
                        all_files.append(f_path)

    total = len(all_files)
    print(f"Found {total} files to index")
    
    for i, file_path in enumerate(all_files):
        pct = int(((i + 1) / total) * 100) if total > 0 else 100
        update_status(pct, f"Indexing {Path(file_path).name}")
        index_file(file_path)
    
    update_status(100, "Idle")
    print("Indexing complete.")

def main():
    parser = argparse.ArgumentParser(description="Jasper Semantic Indexer CLI")
    parser.add_argument("command", choices=["build", "refresh", "status", "prune"], help="Command to run")
    parser.add_argument("--force", action="store_true", help="Force re-indexing of all files")
    
    args = parser.parse_args()

    if args.command == "build":
        print("Building index from scratch...")
        client.delete_collection(COLLECTION_NAME)
        collection = client.create_collection(name=COLLECTION_NAME, embedding_function=embedding_func)
        index_all()
    elif args.command == "refresh":
        index_all(force=args.force)
    elif args.command == "status":
        show_status()
    elif args.command == "prune":
        prune_index()

if __name__ == "__main__":
    main()
