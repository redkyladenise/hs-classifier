import duckdb
import yaml
import numpy as np
import pickle
from pathlib import Path
from sklearn.linear_model import SGDClassifier

import sys
sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor

def train_baseline(scenario='main'):
    # 1. Setup and Rules
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{params['memory_ceiling_gb']}GB'")
    con.execute("PRAGMA threads=1")
    
    # Folders to save our baseline model
    model_dir = Path(f"models/track_c/baselines/{scenario}")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"--- Starting Baseline Training for {scenario.upper()} ---")
    
    # 2. Get all valid 8-digit codes
    # The baseline ignores the tree and just predicts the final 8-digit code directly
    query_classes = f"""
        SELECT DISTINCT ahtn8 
        FROM read_parquet('data/processed/train_pairs_{scenario}.parquet')
        WHERE elig_ahtn8 = true
        ORDER BY ahtn8
    """
    all_classes = np.array([row[0] for row in con.execute(query_classes).fetchall()])
    print(f"Baseline will predict {len(all_classes)} distinct codes.")
    
    # 3. Setup the tools
    extractor = FeatureExtractor(
        hash_bits_word=params['hash_bits_word'],
        hash_bits_char=params['hash_bits_char']
    )
    extractor.set_idf(np.load(f"data/processed/idf_{scenario}.npy"))
    
    # The single, giant "Flat" model
    baseline_model = SGDClassifier(
        loss='log_loss',
        penalty='l2',
        alpha=0.0001,
        random_state=42,
        max_iter=1,
        tol=None
    )
    
    # 4. Train in memory-safe batches
    print("Training baseline in batches...")
    
    # We join our training pairs with the actual text
    query_data = f"""
        SELECT n.desc_norm, t.ahtn8, t.weight
        FROM read_parquet('data/processed/train_pairs_{scenario}.parquet') t
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n
          ON t.group_l1 = n.desc_norm_id
        WHERE t.elig_ahtn8 = true
    """
    
    batch_size = params['batch_size']
    db_result = con.execute(query_data)
    total_processed = 0
    
    while True:
        batch = db_result.fetchmany(batch_size)
        if not batch:
            break
            
        texts = [row[0] for row in batch]
        y_codes = [row[1] for row in batch]
        weights = [row[2] for row in batch]
        
        # Convert text to math
        X_batch = extractor.transform(texts)
        
        # Teach the baseline model
        baseline_model.partial_fit(
            X_batch, 
            y_codes, 
            classes=all_classes, 
            sample_weight=weights
        )
        
        total_processed += len(texts)
        print(f"Trained on {total_processed} descriptions...")
        
    # 5. Save the finished brain to disk
    out_file = model_dir / "flat_logistic.pkl"
    with open(out_file, 'wb') as f:
        pickle.dump(baseline_model, f)
        
    print(f"Done! Baseline saved to {out_file}")

if __name__ == "__main__":
    train_baseline('main')
    # train_baseline('y1') # We can run y1 later if needed