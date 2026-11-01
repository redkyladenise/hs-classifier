import yaml
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
import time

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

def run_c8_inference():
    print("--- Phase 2: Inference Heavy Lift ---")
    
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    # Lock to single thread to prevent interference with NumPy parallel processing
    con.execute("PRAGMA threads=1") 
    
    scenarios = {
        'unseen': {
            'test_file': 'data/processed/test_unseen.parquet',
            'model_scenario': 'main'
        },
        'y1': {
            'test_file': 'data/processed/test_y1.parquet',
            'model_scenario': 'y1'
        },
        'y2': {
            'test_file': 'data/processed/test_y2.parquet',
            'model_scenario': 'main'
        }
    }
    
    batch_size = 5000
    
    for sc_name, sc_info in scenarios.items():
        print(f"\n========================================")
        print(f"  SCENARIO: {sc_name.upper()}")
        print(f"========================================")
        
        out_dir = Path(f"data/processed/predictions_{sc_name}")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Load Engine and Extractor
        model_sc = sc_info['model_scenario']
        print(f"  -> Loading C5 Engine (scenario: {model_sc})...")
        engine = HSInferenceEngine(scenario=model_sc)
        extractor = FeatureExtractor(params['hash_bits_word'], params['hash_bits_char'])
        extractor.set_idf(np.load(f"data/processed/idf_{model_sc}.npy"))
        
        # 2. Fetch Data
        print("  -> Fetching test descriptions...")
        query = f"""
            SELECT t.group_l1, n.desc_norm
            FROM read_parquet('{sc_info['test_file']}') t
            JOIN read_parquet('data/interim/norm_descriptions.parquet') n 
              ON t.group_l1 = n.desc_norm_id
            ORDER BY t.group_l1
        """
        df_test = con.execute(query).df()
        total_items = len(df_test)
        print(f"  -> Found {total_items} items to score.")
        
        # 3. Process in Chunks
        chunks = [df_test[i:i + batch_size] for i in range(0, total_items, batch_size)]
        
        for i, chunk in enumerate(chunks):
            part_file = out_dir / f"part_{i:03d}.parquet"
            
            # Checkpoint: Skip if already done
            if part_file.exists():
                print(f"  -> [Chunk {i+1}/{len(chunks)}] Already exists. Skipping.")
                continue
                
            print(f"  -> [Chunk {i+1}/{len(chunks)}] Processing {len(chunk)} descriptions...")
            start_time = time.time()
            
            # Extract features
            texts = chunk['desc_norm'].tolist()
            X_batch = extractor.transform(texts)
            
            # Predict using C5 Beam Search
            beams = engine.predict_beam_batch(X_batch, top_k=5)
            
            # Format output (Top 5 codes and probabilities)
            records = []
            for idx, item_beams in zip(chunk['group_l1'], beams):
                row = {'group_l1': idx}
                for rank, b in enumerate(item_beams, start=1):
                    row[f'pred_{rank}'] = b['code']
                    row[f'prob_{rank}'] = b['prob']
                
                # Pad with None if the beam search returned fewer than 5 paths
                for rank in range(len(item_beams) + 1, 6):
                    row[f'pred_{rank}'] = None
                    row[f'prob_{rank}'] = 0.0
                
                records.append(row)
            
            # Save chunk
            df_out = pd.DataFrame(records)
            df_out.to_parquet(part_file, index=False)
            
            elapsed = time.time() - start_time
            print(f"     Done in {elapsed:.1f}s. Saved to {part_file.name}")
            
        print(f"  Finished scenario: {sc_name}")

if __name__ == "__main__":
    run_c8_inference()