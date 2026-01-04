import re
from datetime import datetime, timedelta

def parse_relative_date(text):
    """
    Parses strings like "last 3 months", "last 2 weeks", "past 5 days".
    Returns a datetime object representing the start date (cutoff), or None.
    """
    if not text:
        return None
        
    text = text.lower()
    
    # Matches: "last <number> <unit>" ...
    # Units: day, week, month, year, mont (typo)
    match = re.search(r"(?:last|past|this|current|lat|pst)\s+(\d+)\s+(day|week|month|year|mont)s?", text)
    
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        
        today = datetime.now()
        
        if unit == "day":
            delta = timedelta(days=amount)
        elif unit == "week":
            delta = timedelta(weeks=amount)
        elif unit in ["month", "mont"]:
            # Approximation: 30 days per month
            delta = timedelta(days=amount * 30)
        elif unit == "year":
            # Approximation: 365 days per year
            delta = timedelta(days=amount * 365)
        else:
            return None
            
        return today - delta
        
    # Handle singular/this/current
    match_singular = re.search(r"(?:last|past|this|current|lat|pst)\s+(day|week|month|year|mont)", text)
    if not match_singular and "yesterday" in text:
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        
    if match_singular:
         unit = match_singular.group(1)
         today = datetime.now()
         
         if unit == "day": 
             delta = timedelta(days=1)
             if "this" in text or "current" in text: return today.replace(hour=0, minute=0, second=0, microsecond=0)
         elif unit == "week":
             delta = timedelta(weeks=1)
             if "this" in text or "current" in text: 
                 start_of_week = today - timedelta(days=today.weekday())
                 return start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
         elif unit in ["month", "mont"]:
             delta = timedelta(days=30)
             if "this" in text or "current" in text: return today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
         elif unit == "year":
             delta = timedelta(days=365)
             if "this" in text or "current" in text: return today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
         else:
             return None
             
         return today - delta

    return None

def parse_absolute_date(text):
    """
    Parses DD.MM.YYYY or YYYY-MM-DD strings.
    Returns a datetime object or None.
    """
    if not text:
        return None
    
    # Try DD.MM.YYYY
    match_dots = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if match_dots:
        try:
            return datetime(int(match_dots.group(3)), int(match_dots.group(2)), int(match_dots.group(1)))
        except ValueError:
            pass
            
    # Try YYYY-MM-DD
    match_dash = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match_dash:
        try:
            return datetime(int(match_dash.group(1)), int(match_dash.group(2)), int(match_dash.group(3)))
        except ValueError:
            pass
            
    return None

def extract_date_range(text):
    """
    Extracts a (start_date, end_date) tuple from text.
    Handles 'from X to Y', 'since X', 'before Y', 'at X', and relative dates.
    Uses specific patterns to avoid stealing sender names.
    """
    if not text:
        return None, None
        
    text = text.lower()
    start_date = None
    end_date = None
    
    # Date pattern: Absolute (DD.MM.YYYY or YYYY-MM-DD) or Relative (last 3 months)
    date_pattern = r"((?:\d{1,2}\.\d{1,2}\.\d{4})|(?:\d{4}-\d{1,2}-\d{1,2})|(?:last|past|this|current|lat|pst)\s+(?:\d+\s+)?(?:day|week|month|year|mont)s?)"
    
    # 1. Check for "at <DATE>" or "on <DATE>" (Exact day)
    exact_match = re.search(fr"(?:at|on)\s+{date_pattern}", text)
    if exact_match:
        dt = parse_absolute_date(exact_match.group(1)) or parse_relative_date(exact_match.group(1))
        if dt:
            # For exact day, start and end are the same
            return dt, dt

    # 2. Range check "from <DATE> to <DATE>"
    range_match = re.search(fr"(?:from|since)\s+{date_pattern}\s+(?:to|until|before)\s+{date_pattern}", text)
    if range_match:
        start_date = parse_absolute_date(range_match.group(1)) or parse_relative_date(range_match.group(1))
        end_date = parse_absolute_date(range_match.group(2)) or parse_relative_date(range_match.group(2))
        return start_date, end_date

    # 3. Singular checks
    since_match = re.search(fr"(?:since|from)\s+{date_pattern}", text)
    if since_match:
        start_date = parse_absolute_date(since_match.group(1)) or parse_relative_date(since_match.group(1))
            
    before_match = re.search(fr"(?:to|until|before)\s+{date_pattern}", text)
    if before_match:
        end_date = parse_absolute_date(before_match.group(1)) or parse_relative_date(before_match.group(1))
            
    # Fallback to pure relative if no keyword was found
    if not start_date and not end_date:
        # Check if an absolute date is hidden in the text despite other words
        abs_date = parse_absolute_date(text)
        if abs_date:
            return abs_date, abs_date
        start_date = parse_relative_date(text)
        
    return start_date, end_date

    return start_date, end_date

def clean_date_string(text):
    """
    Removes the detected date substring from the text.
    Returns the cleaned text.
    """
    if not text: return text
    
    # Use the same detection logic to find and replace with empty string
    # We prioritize longest matches first
    
    date_pattern = r"((?:\d{1,2}\.\d{1,2}\.\d{4})|(?:\d{4}-\d{1,2}-\d{1,2})|(?:last|past|this|current|lat|pst)\s+(?:\d+\s+)?(?:day|week|month|year|mont)s?)"
    
    # Range check "from <DATE> to <DATE>"
    text = re.sub(fr"(?:from|since)\s+{date_pattern}\s+(?:to|until|before)\s+{date_pattern}", "", text, flags=re.IGNORECASE)
    
    # Check for "at <DATE>" or "on <DATE>"
    text = re.sub(fr"(?:at|on)\s+{date_pattern}", "", text, flags=re.IGNORECASE)

    # Singular checks (since/from/before/until)
    # Note: 'from' might collide with sender 'from', so be careful. 
    # Use stricter spacing or only remove if date follows specific format.
    # But for "search for boris from 2025", we want to remove "from 2025".
    # Logic: If it matches date pattern, remove it.
    text = re.sub(fr"(?:since|from)\s+{date_pattern}", "", text, flags=re.IGNORECASE)
    text = re.sub(fr"(?:to|until|before)\s+{date_pattern}", "", text, flags=re.IGNORECASE)
    
    # Pure relative fallback (last X days)
    # Only remove if it's the specific relative pattern at end or start, or isolated
    # But our pattern creates 'last ... days', so we can just remove it
    text = re.sub(fr"{date_pattern}", "", text, flags=re.IGNORECASE)
    
    return " ".join(text.split())

if __name__ == "__main__":
    # Test cases
    print(f"last 3 months -> {parse_relative_date('last 3 months')}")
    print(f"from 02.12.2025 to 02.02.2026 -> {extract_date_range('from 02.12.2025 to 02.02.2026')}")
    print(f"since yesterday -> {extract_date_range('since yesterday')}")
    print(f"clean: search for boris at 10.12.2025 -> {clean_date_string('search for boris at 10.12.2025')}")
