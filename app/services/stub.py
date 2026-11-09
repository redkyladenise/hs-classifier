import json
import os

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'fixtures')

def load_fixture(name):
    path = os.path.join(FIXTURES_DIR, f"{name}.json")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def classify(text):
    """Simulates the real pipeline by returning a fixture based on input."""
    if not text or len(text.strip()) == 0:
        return {"status": "error", "message": "Empty input"}
    
    text_lower = text.lower()
    
    if "mango" in text_lower:
        return load_fixture("out_of_scope")
    elif "parts" in text_lower:
        return load_fixture("vague")
    else:
        return load_fixture("normal_mixed")