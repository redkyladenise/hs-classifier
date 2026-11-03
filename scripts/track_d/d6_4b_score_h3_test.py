import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
import sys
import yaml
import gc

sys.path.append('.')
from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

def main():
    print("=" * 60)
    print("Track D - Step D6.4b: Score H3 on Test Sample")
    print("=" * 60)

    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)

    con = duckdb.connect()
    
    print("Loading test sample descriptions...")
    query = """
        SELECT s.group_l1, n.desc_norm 
        FROM read_parquet('data/processed/d_test_sample_ids.parquet') s
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n
          ON s.group_l1 = n.desc_norm_id
    """
    test_df = con.execute(query).df()
    total_len = len(test_df)
    print(f"Loaded {total_len:,} records for H3 inference.")
    
    # Initialize feature extractor
    extractor = FeatureExtractor(params['hash_bits_word'], params['hash_bits_char'])
    extractor.set_idf(np.load("data/processed/idf_main.npy"))
    
    print("Initializing H3 Engine...")
    engine = HSInferenceEngine(scenario='main_h3', cache_size=400)
    engine.hierarchy.scenario = 'main' # Force baseline structure alignment
    
    batch_size = 5000
    all_preds = []
    
    for i in range(0, total_len, batch_size):
        if i % (batch_size * 2) == 0:
            print(f"  Predicting batch {i:,}/{total_len:,}...")
            
        batch = test_df.iloc[i:i+batch_size]
        texts = batch['desc_norm'].tolist()
        
        # Transform and Predict
        X_batch = extractor.transform(texts)
        preds = engine.predict_beam_batch(X_batch, top_k=5)
        
        # Parse output into strict schema matching the unseen_predictions
        for j, item_beams in enumerate(preds):
            row = {'group_l1': batch['group_l1'].iloc[j]}
            for rank in range(5):
                if rank < len(item_beams):
                    row[f'pred_{rank+1}'] = item_beams[rank]['code']
                    row[f'prob_{rank+1}'] = float(item_beams[rank]['prob'])
                else:
                    row[f'pred_{rank+1}'] = None
                    row[f'prob_{rank+1}'] = None
            all_preds.append(row)
            
        engine.cache.cache.clear()
        gc.collect()
    
    print("Saving predictions...")
    out_df = pd.DataFrame(all_preds)
    out_path = Path("data/processed/predictions_test_h3.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out_path, index=False)
    
    print(f"Saved {len(out_df):,} H3 predictions to {out_path}")

if __name__ == "__main__":
    main()