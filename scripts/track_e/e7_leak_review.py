import sys
import os
import time  # Added this missing import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import pandas as pd
from src.hsclf.retrieval.search import RetrievalEngine

def main():
    print("--- E7: Generating Leak Review Sample ---")
    
    print("Loading Retrieval Engine...")
    engine = RetrievalEngine()
    
    df_eval = pd.read_parquet('data/processed/retrieval_eval_e4/part_0000.parquet')
    df_eval = df_eval[df_eval['routed_chapters'].apply(len) == 1]
    
    sample_size = min(100, len(df_eval))
    df_eval = df_eval.sample(sample_size, random_state=42)
    df_eval['chap_str'] = df_eval['routed_chapters'].astype(str)
    df_eval = df_eval.sort_values('chap_str')

    review_data = []
    query_times = []
    
    print(f"Running {sample_size} queries and masking examples...")
    for i, (_, row) in enumerate(df_eval.iterrows(), 1):
        query_text = row['desc_norm']
        chapters = row['routed_chapters']
        
        query_start = time.perf_counter()
        
        result = engine.query(raw_text=query_text, routed_chapters=chapters, show_examples=True)
        
        query_times.append(time.perf_counter() - query_start)
        
        examples = result.get('examples', [])
        
        for ex in examples:
            review_data.append({
                'example_id': ex.get('example_id', ''),
                'original_text': ex.get('original_text', ''),
                'masked_text': ex['text'],
                'similarity': ex['similarity'],
                'leak_found': '',
                'note': ''
            })
            
        if i % 20 == 0:
            avg_time = sum(query_times) / len(query_times)
            print(f"  ...processed {i}/{sample_size} | Avg query time: {avg_time:.4f}s")

    df_review = pd.DataFrame(review_data)
    
    cols = ['example_id', 'original_text', 'masked_text', 'similarity', 'leak_found', 'note']
    if not df_review.empty:
        df_review = df_review[cols]
    
    out_path = 'reports/tables/track_e/e7_mask_review.csv'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df_review.to_csv(out_path, index=False)
    
    if query_times:
        print(f" Average query time: {sum(query_times)/len(query_times):.4f}s")
        print(f" Total query time: {sum(query_times):.2f}s")
    print(f"Generated {len(df_review)} masked examples for review at {out_path}")
    print("Next: Open the CSV, verify the masked texts, and ensure zero leaks.")

if __name__ == "__main__":
    main()