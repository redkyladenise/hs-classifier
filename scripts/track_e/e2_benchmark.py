import sys
import os
import gc
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import time
import tracemalloc
import pandas as pd
from src.hsclf.retrieval.search import RetrievalEngine

def main():
    print("--- E2: Benchmarking Search Engine ---")
    
    print("-> Preparing 200 sample queries (Outside of RAM tracker)...")
    meta = pd.read_parquet('data/processed/retrieval/index_meta.parquet').head(200)
    norm = pd.read_parquet('data/interim/norm_descriptions.parquet')
    samples = meta.merge(norm, on='desc_norm_id', how='left')
    
    del norm
    gc.collect()
    
    print("-> Starting RAM tracker...")
    tracemalloc.start()
    
    print("-> Loading Engine (Cold Start)...")
    engine = RetrievalEngine()
    
    print("-> Running 200 queries...")
    start_time = time.time()
    
    for _, row in samples.iterrows():
        engine.query(row['desc_norm'], routed_chapters=[row['chapter']])
        
    end_time = time.time()
    
    # Stop tracking RAM
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    total_time = end_time - start_time
    time_per_query = total_time / 200
    peak_mb = peak / (1024 * 1024)
    
    print("\n Benchmark Complete!")
    print(f"   -> Peak RAM used: {peak_mb:.2f} MB")
    print(f"   -> Time per query: {time_per_query:.4f} seconds")

if __name__ == "__main__":
    main()