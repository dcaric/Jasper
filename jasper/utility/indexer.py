import os
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path
import hashlib
import json
from datetime import datetime
import argparse
from .config import get_db_path, get_status_file, get_index_paths, get_log_file

# CONFIGURATION
DB_PATH = get_db_path()
COLLECTION_NAME = "jasper_docs"
CHUNK_SIZE = 1000  # Characters
CHUNK_OVERLAP = 100

# INITIALIZE CHROMA (Use shared from semantic_tools to avoid locking)
from .semantic_tools import client, collection, embedding_func

def get_collection():
    """Safety wrapper to ensure collection is available."""
    return collection


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

def get_indexed_metadata():
    """Fetches metadata for all indexed files to support incremental indexing."""
    coll = get_collection()
    if not coll: return {}
    
    results = coll.get(include=['metadatas'])
    metadata_map = {}
    if results and results['metadatas']:
        for meta in results['metadatas']:
            source = meta.get('source')
            if source:
                # Store the most recent mtime/hash seen for this file
                mtime = meta.get('mtime', 0)
                f_hash = meta.get('hash', "")
                if source not in metadata_map or mtime > metadata_map[source]['mtime']:
                    metadata_map[source] = {'mtime': mtime, 'hash': f_hash}
    return metadata_map

def index_file(file_path, existing_metadata=None, force=False):
    """Reads, chunks, and adds a file to ChromaDB if it has changed."""
    try:
        path_obj = Path(file_path)
        if not path_obj.exists(): return
        
        # Supports web dev files and project source
        ext = path_obj.suffix.lower()
        allowed_exts = ['.txt', '.md', '.py', '.bat', '.html', '.css', '.js', '.json', '.c', '.cpp', '.h']
        if ext not in allowed_exts and path_obj.name != 'Modelfile': 
            return

        # Skip extremely large files (> 5MB)
        if path_obj.stat().st_size > 5 * 1024 * 1024:
            print(f"Skipping large file: {path_obj.name} ({path_obj.stat().st_size / 1024 / 1024:.2f} MB)")
            return

        mtime = os.path.getmtime(file_path)
        f_hash = get_file_hash(file_path)
        
        # Check if file has changed
        if not force and existing_metadata and str(path_obj.absolute()) in existing_metadata:
            stored = existing_metadata[str(path_obj.absolute())]
            if stored['mtime'] == mtime and stored['hash'] == f_hash:
                # print(f"Skipping unchanged file: {path_obj.name}")
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
        coll = get_collection()
        if coll:
            coll.delete(where={"source": str(path_obj.absolute())})
        else:
            print(f"Skipping {file_path} - Collection not available")
            return
        
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
        
        coll.add(
            ids=ids,
            documents=chunks,
            metadatas=metadatas
        )
        safe_name = path_obj.name.encode('ascii', 'ignore').decode('ascii')
        msg = f"Indexed {len(chunks)} chunks from: {safe_name}"
        # print(msg)
        with open(get_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] [INDEXER] {msg}\n")
        
    except Exception as e:
        msg = f"Error indexing {file_path}: {e}"
        print(msg)
        with open(get_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] [INDEXER] {msg}\n")

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
    coll = get_collection()
    if not coll: return
    
    results = coll.get()
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
        coll = get_collection()
        for source in to_delete:
            if coll:
                coll.delete(where={"source": source})
            print(f"Deleted: {source}")
    else:
        print("No stale entries found.")

def show_status():
    """Displays stats about the current index."""
    coll = get_collection()
    if not coll:
        print("Index currently unavailable.")
        return
        
    count = coll.count()
    print(f"--- Jasper Index Status ---")
    print(f"Total Chunks: {count}")
    
    results = coll.get()
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
    index_roots = get_index_paths()
    print(f"Indexing paths: {index_roots}")
    
    for workspace in index_roots:
        if not os.path.exists(workspace):
            print(f"Warning: Index path does not exist: {workspace}")
            continue
            
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if d not in skip_folders and not d.startswith('.')]
            for file in files:
                if file.endswith(('.txt', '.md', '.py', '.bat', '.html', '.js', '.css', '.json')) or file == 'Modelfile':
                    all_files.append(os.path.join(root, file))

    total = len(all_files)
    msg = f"[INDEXER] Found {total} files in workspace"
    print(msg)
    with open(get_log_file(), "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {msg}\n")
    
    # Pre-fetch metadata for incremental indexing
    existing_metadata = {}
    if not force:
        msg = "Fetching existing index metadata for incremental update..."
        print(msg)
        existing_metadata = get_indexed_metadata()
        msg = f"Found {len(existing_metadata)} files already in index."
        print(msg)
        with open(get_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] [INDEXER] {msg}\n")

    indexed_count = 0
    skipped_count = 0
    
    for i, file_path in enumerate(all_files):
        pct = int(((i + 1) / total) * 100) if total > 0 else 100
        
        # Check if we should skip before calling index_file to avoid overhead
        path_abs = str(Path(file_path).absolute())
        should_index = True
        if not force and path_abs in existing_metadata:
            try:
                mtime = os.path.getmtime(file_path)
                stored = existing_metadata[path_abs]
                if stored['mtime'] == mtime:
                    # mtime matches, quick skip
                    should_index = False
            except:
                pass

        if should_index:
            update_status(pct, f"Processing {Path(file_path).name}")
            # index_file handles force and deep hash check
            index_file(file_path, existing_metadata=existing_metadata, force=force)
            indexed_count += 1
        else:
            skipped_count += 1
    
    update_status(100, "Idle")
    msg = f"Indexing complete. Processed {indexed_count} files, skipped {skipped_count} unchanged files."
    print(msg)
    with open(get_log_file(), "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] [INDEXER] {msg}\n")

def repair_index():
    """Destroys and recreates the index directory to fix corruption."""
    import shutil
    print(f"[REPAIR] Deleting corrupted index at {DB_PATH}...")
    try:
        if os.path.exists(DB_PATH):
            shutil.rmtree(DB_PATH)
        print("[REPAIR] Index deleted. Rebuilding...")
        # Force re-index
        global collection, client
        client = chromadb.PersistentClient(path=DB_PATH)
        collection = client.create_collection(
            name=COLLECTION_NAME, 
            embedding_function=embedding_func
        )
        index_all()
        print("[REPAIR] Index successfully rebuilt.")
    except Exception as e:
        print(f"[ERROR] Failed to repair index: {e}")

def main():
    parser = argparse.ArgumentParser(description="Jasper Semantic Indexer CLI")
    parser.add_argument("command", choices=["build", "refresh", "status", "prune", "repair"], help="Command to run")
    parser.add_argument("--force", action="store_true", help="Force re-indexing of all files")
    
    args = parser.parse_args()
    
    global collection, client

    if args.command == "build":
        print("Building index from scratch...")
        coll = get_collection()
        if coll:
            client.delete_collection(COLLECTION_NAME)
        collection = client.create_collection(name=COLLECTION_NAME, embedding_function=embedding_func)
        index_all()
    elif args.command == "refresh":
        index_all(force=args.force)
    elif args.command == "status":
        show_status()
    elif args.command == "prune":
        prune_index()
    elif args.command == "repair":
        repair_index()

if __name__ == "__main__":
    main()
