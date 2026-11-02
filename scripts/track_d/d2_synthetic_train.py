import os
import sys
import yaml
import json
import duckdb
import numpy as np
import pickle
from pathlib import Path
from sklearn.linear_model import SGDClassifier
import gc

# Import custom feature extractor
sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor

def main():
    print("=" * 60)
    print("Track D - Step D2.3: Train Synthetic Variants on Chapter Nodes")
    print("=" * 60)

    # 1. Load C5 params and C-grid
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
    
    with open("config/best_c_grid.json", "r") as f:
        best_c_grid = {int(k): v for k, v in json.load(f).items()}
    c_val_level_2 = best_c_grid.get(2, 1.0) # C value for chapter nodes

    con = duckdb.connect()
    
    # 2. Setup Feature Extractor
    extractor = FeatureExtractor(
        hash_bits_word=params['hash_bits_word'],
        hash_bits_char=params['hash_bits_char']
    )
    extractor.set_idf(np.load("data/processed/idf_main.npy"))

    variants = [
        "syn_clean", 
        "syn_noisy_10", "syn_h1_10", "syn_h2_10", "syn_h3_10",
        "syn_noisy_20", "syn_h1_20", "syn_h2_20", "syn_h3_20"
    ]
    
    chapters_to_train = ['39', '73', '84', '85', '87']
    n_cap = 200

    for variant in variants:
        print(f"\n--- Training Variant: {variant} ---")
        out_dir = Path(f"models/v1/synthetic/{variant}")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        for ch2 in chapters_to_train:
            # Added joins to training_pool and train_pairs_main to enforce rank <= 200 and elig_hd4 = true
            query = f"""
                SELECT n.desc_norm, t.hd4, t.weight
                FROM read_parquet('data/audit/synthetic/{variant}.parquet') t
                JOIN read_parquet('data/interim/norm_descriptions.parquet') n 
                  ON t.group_l1 = n.desc_norm_id
                JOIN read_parquet('data/processed/training_pool.parquet') p 
                  ON t.group_l1 = p.group_l1
                JOIN read_parquet('data/processed/train_pairs_main.parquet') orig 
                  ON t.group_l1 = orig.group_l1 AND t.ahtn8 = orig.ahtn8
                WHERE t.ch2 = '{ch2}' 
                  AND p.rank_main <= {n_cap}
                  AND orig.elig_hd4 = true
            """
            
            data = con.execute(query).fetchall()
            if not data:
                print(f"Skipping Chapter {ch2} - no data found.")
                continue
                
            X_text = [r[0] for r in data]
            y_train = [r[1] for r in data]
            w_train = np.array([float(r[2]) for r in data])
            
            if len(set(y_train)) < 2:
                print(f"Skipping Chapter {ch2} - only 1 class.")
                continue
                
            X_train = extractor.transform(X_text)
            
            # Use exact SGD setup from C5_1
            n_rows = X_train.shape[0]
            alpha_val = 1.0 / (c_val_level_2 * n_rows)
            
            model = SGDClassifier(loss='log_loss', alpha=alpha_val, random_state=42)
            model.fit(X_train, y_train, sample_weight=w_train)
            
            # Sparse coefficient reduction (same as C5_1)
            active_cols = np.array((X_train != 0).sum(axis=0)).flatten() > 0
            active_indices = np.where(active_cols)[0]
            model.coef_ = model.coef_[:, active_indices].astype(np.float32)
            model.intercept_ = model.intercept_.astype(np.float32)
            model.n_features_in_ = len(active_indices)
            
            bundle = {
                'model': model,
                'active_indices': active_indices,
                'n_classes': len(model.classes_),
                'number_type': 'float32'
            }
            
            with open(out_dir / f"{ch2}.pkl", 'wb') as f:
                pickle.dump(bundle, f)
                
            print(f"  -> Built Node {ch2} (N={n_rows}, Classes={len(model.classes_)})")
            
            del model, bundle, X_train, y_train, w_train, data, active_cols, active_indices
            gc.collect()

    print("\nAll synthetic models built successfully.")

if __name__ == "__main__":
    main()