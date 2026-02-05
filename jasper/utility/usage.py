import json
import os
from .config import BASE_DIR

USAGE_FILE = os.path.join(BASE_DIR, ".usage_data")

def get_usage():
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"input_tokens": 0, "output_tokens": 0}

def save_usage(data):
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f)

def update_usage(input_tokens, output_tokens):
    usage = get_usage()
    usage["input_tokens"] += input_tokens
    usage["output_tokens"] += output_tokens
    save_usage(usage)

def calculate_cost():
    usage = get_usage()
    # Rates: $0.50 per 1M input, $3.00 per 1M output
    input_cost = (usage["input_tokens"] / 1000000) * 0.50
    output_cost = (usage["output_tokens"] / 1000000) * 3.00
    return input_cost + output_cost
