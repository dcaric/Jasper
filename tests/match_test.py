def normalize_text(text):
    """Replaces Croatian characters with ASCII equivalents for safe search."""
    if not text: return text
    mapping = {
        'ž': 'z', 'Ž': 'Z',
        'ć': 'c', 'Ć': 'C',
        'č': 'c', 'Č': 'C',
        'š': 's', 'Š': 'S',
        'đ': 'd', 'Đ': 'D'
    }
    res = text
    for char, replacement in mapping.items():
        res = res.replace(char, replacement)
    return res

def check_match(query, target):
    query_norm = normalize_text(query).lower()
    target_norm = normalize_text(target).lower()
    
    # Match keywords in any order
    for word in query_norm.split():
        if word not in target_norm:
            return False
    return True

# Test cases
tests = [
    ("ljeto zavala", "Planovi za ljeto u Zavala", True),
    ("ljeto zavala", "Zavala - ljeto 2024", True),
    ("ljeto zavala", "Ljeto u gradu", False),
    ("šumandl", "sonja šumandl", True),
    ("sumandl", "sonja šumandl", True),
    ("sonja", "sonja.sumandl123@gmail.com", True),
    ("sumandl", "sonja.sumandl123@gmail.com", True),
]

for q, t, expected in tests:
    res = check_match(q, t)
    print(f"Query: '{q}' | Target: '{t}' | Result: {res} | Expected: {expected} | {'PASS' if res == expected else 'FAIL'}")
