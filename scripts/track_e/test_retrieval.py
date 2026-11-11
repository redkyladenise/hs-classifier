import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.hsclf.retrieval.search import RetrievalEngine

def main():
    print("Loading Retrieval Engine...")
    engine = RetrievalEngine()
    
    test_text = "polybutylene terephthalate 25kgs"
    test_chapters = [39]
    
    print(f"\nQuery: '{test_text}'")
    print(f"Routing to chapters: {test_chapters}")
    
    # We call query() to test our newly fixed method
    results = engine.query(
        raw_text=test_text, 
        routed_chapters=test_chapters, 
        min_similarity=0.0, 
        show_examples=True
    )
    
    print("\n--- RESULTS ---")
    print(f"Max Similarity Found: {results.get('max_similarity', 0.0):.4f}")
    
    print("\nDistribution:")
    if not results.get('distribution').empty:
        print(results['distribution'].to_string(index=False))
    else:
        print("No distribution returned.")
        
    print("\nExamples:")
    for ex in results.get('examples', []):
        print(f"  [{ex['similarity']:.2f}] {ex['text']}")

if __name__ == "__main__":
    main()