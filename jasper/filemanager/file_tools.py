import os
import win32com.client
from datetime import datetime
from ..utility.config import get_setting, get_log_file

# Detect system user
USER_NAME = get_setting("USER_NAME", os.environ.get("USERNAME", "Unknown"))

def find_files(query=None, name=None, date_from=None, date_to=None, limit=10, kind=None, content_mode=False):
    """
    Search Windows files using the native indexer.
    Returns a list of dictionaries with file metadata.
    """
    try:
        # LOGGING TO FILE FOR DEBUGGING
        with open(get_log_file(), "a") as f:
             f.write(f"[{datetime.now()}] find_files EXECUTION -> kind='{kind}', content_mode={content_mode}\n")

        conn = win32com.client.Dispatch("ADODB.Connection")
        conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
        
        rs = win32com.client.Dispatch("ADODB.Recordset")
        
        # Build SQL
        select_clause = "SELECT System.ItemName, System.ItemPathDisplay, System.DateModified, System.Size, System.FileExtension, System.Kind"
        from_clause = "FROM SystemIndex"
        where_parts = ["SCOPE='file:'"]
        
        if query:
            if content_mode:
                # Use FREETEXT for content search which is smarter for natural language matches
                where_parts.append(f"FREETEXT(System.Search.Contents, '{query}')")
            else:
                where_parts.append(f"(System.ItemName LIKE '%{query}%' OR System.ItemPathDisplay LIKE '%{query}%')")
        
        if name:
            where_parts.append(f"System.ItemName LIKE '%{name}%'")
            
        if kind:
            # System.Kind can be 'folder', 'document', 'picture', etc.
            # Windows Search Syntax: System.Kind = 'folder'
            if kind.lower() in ['folder', 'directory']:
                 # System.ItemType = 'Directory' is often more reliable than Kind
                 where_parts.append("(System.Kind = 'folder' OR System.ItemType = 'Directory')")
            else:
                 where_parts.append(f"System.Kind LIKE '%{kind}%'")
            
        if date_from:
            formatted_from = date_from.strftime("%Y-%m-%d %H:%M:%S")
            where_parts.append(f"System.DateModified >= '{formatted_from}'")
            
        if date_to:
            formatted_to = date_to.strftime("%Y-%m-%d 23:59:59")
            where_parts.append(f"System.DateModified <= '{formatted_to}'")
            
        where_clause = "WHERE " + " AND ".join(where_parts)
        order_clause = "ORDER BY System.DateModified DESC"
        
        sql = f"{select_clause} {from_clause} {where_clause} {order_clause}"
        
        print(f"DEBUG: find_files called with kind='{kind}'")
        print(f"DEBUG: File Search SQL -> {sql}")
        rs.Open(sql, conn)
        
        results = []
        count = 0
        if not rs.EOF:
            rs.MoveFirst()
            while not rs.EOF and count < limit:
                results.append({
                    "name": rs.Fields("System.ItemName").Value,
                    "path": rs.Fields("System.ItemPathDisplay").Value,
                    "date": str(rs.Fields("System.DateModified").Value),
                    "size": rs.Fields("System.Size").Value,
                    "extension": rs.Fields("System.FileExtension").Value,
                    "kind": rs.Fields("System.Kind").Value
                })
                count += 1
                rs.MoveNext()
        
        rs.Close()
        conn.Close()

        # STEP 1: Filter SQL results immediately if kind is specified
        # This ensures that if SQL returns filtered-out items, we still trigger fallback.
        if kind and kind.lower() in ['folder', 'directory']:
             filtered = []
             for r in results:
                 if os.path.exists(r['path']) and os.path.isdir(r['path']):
                     r['kind'] = 'folder'
                     filtered.append(r)
             results = filtered
        
        # LOCAL FALLBACK: Check workspace specifically
        # Now this will trigger if SQL returned nothing relevant (filtered list is empty)
        if query and (not results or len(query) <= 3):
            potential_paths = [
                f"C:\\Users\\{USER_NAME}\\ML",
                f"C:\\Users\\{USER_NAME}\\ML\\Jasper",
                f"C:\\Users\\{USER_NAME}\\WORKING",
                f"C:\\Users\\{USER_NAME}\\repos",
                f"C:\\Users\\{USER_NAME}",
                f"C:\\Users\\{USER_NAME}\\Downloads",
                f"C:\\Users\\{USER_NAME}\\Documents",
                os.getcwd(),
                os.path.dirname(os.getcwd())
            ]
            fallback_results = []
            for p in potential_paths:
                p = os.path.normpath(p)
                if not os.path.exists(p): 
                    continue
                
                # Check the folder itself
                bname = os.path.basename(p)
                if query.lower() in bname.lower():
                    exists = any(os.path.normpath(r["path"]).lower() == p.lower() for r in results)
                    if not exists:
                        fallback_results.append({
                            "name": bname,
                            "path": p,
                            "date": str(datetime.fromtimestamp(os.path.getmtime(p))),
                            "size": 0,
                            "extension": "",
                            "kind": "folder"
                        })
                
                # Check immediate children
                try:
                    for item in os.listdir(p):
                        if query.lower() in item.lower():
                            full_path = os.path.normpath(os.path.join(p, item))
                            if not any(os.path.normpath(r["path"]).lower() == full_path.lower() for r in results):
                                is_dir = os.path.isdir(full_path)
                                
                                # Apply kind filter if present
                                if kind and kind.lower() in ['folder', 'directory'] and not is_dir:
                                    continue
                                    
                                fallback_results.append({
                                    "name": item,
                                    "path": full_path,
                                    "date": str(datetime.fromtimestamp(os.path.getmtime(full_path))),
                                    "size": os.path.getsize(full_path) if not is_dir else 0,
                                    "extension": os.path.splitext(item)[1] if not is_dir else "",
                                    "kind": "folder" if is_dir else "document"
                                })
                except:
                    continue
                
                if len(results) + len(fallback_results) >= limit: break
            
            # Prepend fallback results
            results = fallback_results + results
        
        return results[:limit]
        
    except Exception as e:
        print(f"Error in file search: {e}")
        return f"Error: {str(e)}"

def open_file(path):
    """Opens a file or folder using the default system handler."""
    try:
        os.startfile(path)
        return True, "Opened successfully"
    except Exception as e:
        return False, str(e)

def read_file_content(path, max_chars=10000):
    """
    Reads text content from a file, supporting multiple encodings.
    """
    if not os.path.exists(path):
        return None
        
    try:
        # Try UTF-8 first
        with open(path, 'r', encoding='utf-8') as f:
            return f.read(max_chars)
    except UnicodeDecodeError:
        try:
            # Try Windows-1250 (Central European) or Latin-1
            with open(path, 'r', encoding='cp1250') as f:
                return f.read(max_chars)
        except UnicodeDecodeError:
            try:
                with open(path, 'r', encoding='latin-1') as f:
                    return f.read(max_chars)
            except:
                return None
    except Exception:
        return None

if __name__ == "__main__":
    # Test
    res = find_files(query="Hvar")
    print(f"Found {len(res)} files")
