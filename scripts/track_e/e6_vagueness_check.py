import os
from pathlib import Path

def load_generic_words():
    """Fetches generic words from the external reference file."""
    file_path = Path('data/reference/generic_words.txt')
    
    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        default_words = [
            "parts", "spare", "goods", "accessories", "items", 
            "equipment", "assorted", "various", "machine", "for",
            "and", "with", "other", "general", "components"
        ]
        with open(file_path, 'w') as f:
            f.write('\n'.join(default_words))
            
    # FETCH the words from the text file
    with open(file_path, 'r') as f:
        words = [line.strip().lower() for line in f if line.strip()]
        
    return set(words)

def is_vague(description, generic_words):
    """
    Rule: Flag if 2 words or fewer, OR if ALL words are in the generic list.
    """
    words = str(description).lower().split()
    
    if len(words) <= 2:
        return True
        
    meaningful_words = [w for w in words if w not in generic_words]
    if len(meaningful_words) == 0:
        return True
        
    return False

def main():
    print("--- E6: Minimal Vagueness Flag (File-Fetched) ---")
    
    # 1. Fetch from file
    generic_words = load_generic_words()
    print(f" Loaded {len(generic_words)} words from data/reference/generic_words.txt")
    
    # 2. Run tests
    test_cases = [
        "parts", 
        "spare parts for machine", 
        "stainless steel kitchen sink 60x45 cm"
    ]
    
    print("\n--- Running Tests ---")
    message = " This description is vague. Add the material, function, type, and any sizes or ratings."
    
    for test in test_cases:
        flagged = is_vague(test, generic_words)
        result_text = "FLAGGED" if flagged else "PASSED "
        print(f"[{result_text}] '{test}'")
        if flagged:
            print(f"          -> {message}")

if __name__ == "__main__":
    main()