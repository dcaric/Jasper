import os
import time
from pathlib import Path
from jasper.utility.indexer import index_all, get_collection

def test_incremental_indexing():
    # 1. Clean build or ensure index exists
    print("\n--- Step 1: Initial Indexing (Incremental Mode) ---")
    index_all(force=False)
    
    # 2. Run again immediately
    print("\n--- Step 2: Immediate Re-run (Expected: 0 processed) ---")
    index_all(force=False)
    
    # 3. Modify a file
    print("\n--- Step 3: Modifying a file ---")
    test_file = os.path.join(os.getcwd(), "test_file.txt")
    with open(test_file, "w") as f:
        f.write(f"Test content at {time.time()}")
    
    try:
        index_all(force=False)
        
        # 4. Force re-index
        print("\n--- Step 4: Forced Re-index (Expected: All processed) ---")
        index_all(force=True)
        
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

if __name__ == "__main__":
    test_incremental_indexing()
