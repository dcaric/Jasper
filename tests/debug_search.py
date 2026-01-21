import os
import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from jasper.filemanager.file_tools import find_files

print("--- Testing Folder Search ---")
print("Searching for folder 'ML'...")
res_folder = find_files(query="ML", kind="folder")
print(f"Results for 'ML' (folder): {res_folder}")

print("\nSearching for folder 'Jasper'...")
res_jasper = find_files(query="Jasper", kind="folder")
print(f"Results for 'Jasper' (folder): {res_jasper}")

print("\nSearching for file 'Modelfile'...")
res_file = find_files(query="Modelfile")
print(f"Results for 'Modelfile': {len(res_file)} items found.")
for r in res_file[:3]:
    print(f" - {r['name']} at {r['path']}")
