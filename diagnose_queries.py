import ollama
import json

MODEL_NAME = "jasper"

def test_query(query):
    print(f"Testing local intent extraction for: {query}")
    try:
        response = ollama.generate(
            model=MODEL_NAME,
            prompt=f"User: \"{query}\"",
            format="json",
            options={ "temperature": 0.0, "num_predict": 128 }
        )
        raw = response.get("response", "").strip()
        print(f"Raw Output: {raw}")
        try:
            parsed = json.loads(raw)
            print("Parsed JSON:")
            print(json.dumps(parsed, indent=2))
        except:
            print("Failed to parse JSON")
    except Exception as e:
        print(f"Ollama error: {e}")

if __name__ == "__main__":
    test_query("search outlook for mails form Boris last 15d")
    test_query("search outlook for mails form Boris last month")
