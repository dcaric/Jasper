import os
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path
import hashlib
from datetime import datetime

# CONFIGURATION
DB_PATH = "./chroma_db"
COLLECTION_NAME = "jasper_docs"
CHUNK_SIZE = 1000  # Characters
CHUNK_OVERLAP = 100

# EMBEDDING MODEL (Chroma Default: all-MiniLM-L6-v2 ONNX)
# This is fast and light on RAM
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
    with open(path, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

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
            
        # Strip HTML tags if it's an HTML file to improve semantic matching
        if ext == '.html':
            # Remove script and style tags completely
            content = re.sub(r'<(script|style).*?>.*?</\1>', '', content, flags=re.DOTALL | re.IGNORECASE)
            # Strip remaining tags but keep text
            content = re.sub(r'<.*?>', ' ', content)
            # Clean up whitespace
            content = re.sub(r'\s+', ' ', content).strip()
            
        if not content.strip(): return

        # 2. DELETE OLD CHUNKS (if any)
        collection.delete(where={"source": str(path_obj.absolute())})
        
        # 3. CHUNK AND ADD
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
        # Use a safe print for console to avoid encoding errors on special filenames
        safe_name = path_obj.name.encode('ascii', 'ignore').decode('ascii')
        print(f"Indexed {len(chunks)} chunks from: {safe_name}")
        
    except Exception as e:
        print(f"Error indexing {file_path}: {e}")

def update_status(progress_pct, status_text):
    """Writes progress to a local JSON file for the main app to read."""
    try:
        import json
        with open(".index_status", "w") as f:
            json.dump({
                "percent": progress_pct,
                "status": status_text,
                "updated_at": str(datetime.now())
            }, f)
    except:
        pass


def index_all(force=False):
    # Folders to skip (checked before entering)
    skip_folders = [
        'AppData', 'LocalLow', 'Local', 'Roaming', 
        'node_modules', '.git', '.venv', 'venv',   
        'Pictures', 'Music', 'Videos', 'Searches', 
        'Saved Games', 'Links', 'Contacts', 'OneDrive',
        'Cookies', 'Recent', 'SendTo', 'Start Menu', 'Templates'
    ]
    
    all_files = []
    
    # 1. Workspace
    workspace = os.getcwd()
    print(f"Indexing workspace: {workspace}")
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in skip_folders and not d.startswith('.')]
        for file in files:
            if file.endswith(('.txt', '.md', '.py', '.bat', '.html', '.js', '.css', '.json')) or file == 'Modelfile':
                all_files.append(os.path.join(root, file))

    # 2. Priority: WORKING directory (where projects are)
    working_dir = r"C:\Users\Dario\WORKING"
    if os.path.exists(working_dir):
        print(f"Indexing WORKING directory: {working_dir}")
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
        
        # If force is true, we delete the file from index first to ensure metadata update
        if force:
             collection.delete(where={"source": str(Path(file_path).absolute())})
             
        index_file(file_path)
    
    update_status(100, "Idle")
    print("Indexing complete.")
    
    update_status(100, "Idle")
    print("Indexing complete.")

if __name__ == "__main__":
    import sys
    force_reindex = "--force" in sys.argv
    index_all(force=force_reindex)
