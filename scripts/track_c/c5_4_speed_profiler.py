import duckdb
import yaml
import numpy as np
import pandas as pd
import time
import tracemalloc
import gc
from pathlib import Path
import sys

sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

def run_speed_profile():
    tracemalloc.start()
    print("--- Running C5.4 Speed & Memory Profiler ---")
    
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{params.get('memory_ceiling_gb', 0.76)}GB'")
    con.execute("PRAGMA threads=1")
    
    # 1. Setup Engine and Data
    engine = HSInferenceEngine(scenario='main')
    extractor = FeatureExtractor(params['hash_bits_word'], params['hash_bits_char'])
    extractor.set_idf(np.load("data/processed/idf_main.npy"))
    
    print("\nLoading 10,000 descriptions for profiling...")
    query = """
        SELECT n.desc_norm
        FROM read_parquet('data/processed/val_cal_main.parquet') v
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON v.group_l1 = n.desc_norm_id
        LIMIT 10000
    """
    sample_texts = con.execute(query).df()['desc_norm'].tolist()
    X_sample = extractor.transform(sample_texts)
    n_samples = len(sample_texts)
    
    # 2. Cold Cache Profiling (Loading from disk)
    print("Running Cold Cache Inference...")
    engine.cache.cache.clear()
    gc.collect() # FIX 1: Force true memory wipe for a genuine cold start
    
    start_time = time.time()
    engine.predict_beam_batch(X_sample, top_k=5)
    cold_time = time.time() - start_time
    
    cold_speed = n_samples / cold_time
    
    # 3. Warm Cache Profiling (Models already in RAM)
    print("Running Warm Cache Inference...")
    start_time = time.time()
    engine.predict_beam_batch(X_sample, top_k=5)
    warm_time = time.time() - start_time
    
    warm_speed = n_samples / warm_time
    
    # Capture absolute peak memory for the entire process
    _, peak_mem_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_mem_mb = peak_mem_bytes / (1024 * 1024)
    
    # 4. Projections (Using the slower Cold Speed for a safe worst-case estimate)
    unseen_size = 1173618
    test_2024_size = 296093
    test_2025_size = 300000  # Estimate based on y1 size
    
    unseen_hours = (unseen_size / cold_speed) / 3600
    y1_hours = (test_2024_size / cold_speed) / 3600
    y2_hours = (test_2025_size / cold_speed) / 3600
    
    # 5. Save Report
    results = [{
        'Metric': 'Cold Cache Speed (rows/sec)', 'Value': round(cold_speed, 2)
    }, {
        'Metric': 'Warm Cache Speed (rows/sec)', 'Value': round(warm_speed, 2)
    }, {
        'Metric': 'Absolute Peak RAM (MB)', 'Value': round(peak_mem_mb, 2)
    }, {
        'Metric': 'Projected Unseen Test (Hours)', 'Value': round(unseen_hours, 2)
    }, {
        'Metric': 'Projected 2024 Test (Hours)', 'Value': round(y1_hours, 2)
    }, {
        'Metric': 'Projected 2025 Test (Hours)', 'Value': round(y2_hours, 2)
    }, {
        'Metric': 'Max Eval Hours Ceiling', 'Value': 12.0
    }, {
        'Metric': 'Fits in Time Limit?', 'Value': "YES" if unseen_hours < 12 else "NO - Fallback Required"
    }]
    
    out_dir = Path("reports/tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    df_results = pd.DataFrame(results)
    df_results.to_csv(out_dir / "c5_speed.csv", index=False)
    
    print("\n Speed Profiling Complete! Saved to reports/tables/c5_speed.csv")
    print("\n--- PERFORMANCE PROJECTIONS ---")
    print(df_results.to_string(index=False))

if __name__ == "__main__":
    run_speed_profile()