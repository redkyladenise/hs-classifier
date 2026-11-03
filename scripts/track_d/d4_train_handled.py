import duckdb
import yaml
import numpy as np
from sklearn.linear_model import SGDClassifier
import sklearn
import json
from pathlib import Path
import pickle
import hashlib
import platform
import sys
import gc
import time
import os
from collections import Counter

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor

def get_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def get_peak_memory_mb():
    """Returns peak memory usage of the current process in MB. Safe fallback if psutil is missing."""
    if not HAS_PSUTIL:
        return -1.0
    process = psutil.Process(os.getpid())
    if hasattr(process.memory_info(), 'peak_wset'):
        return process.memory_info().peak_wset / (1024 * 1024)
    else:
        return process.memory_info().rss / (1024 * 1024)

def main():
    print("=" * 60)
    print("Track D - Step D4: Retrain Handled Hierarchies")
    print("=" * 60)

    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{params.get('memory_ceiling_gb', 0.76)}GB'")
    con.execute("PRAGMA threads=1")
    
    with open("config/best_c_grid.json", "r") as f:
        best_c_grid = {int(k): v for k, v in json.load(f).items()}
        
    n_cap = 200
    variants = ['main_h1', 'main_h2', 'main_h3']
    
    extractor = FeatureExtractor(
        hash_bits_word=params['hash_bits_word'],
        hash_bits_char=params['hash_bits_char']
    )
    idf_path = "data/processed/idf_main.npy"
    extractor.set_idf(np.load(idf_path))
    
    # We use the baseline hierarchy to determine which nodes to train
    query_parents = """
        SELECT parent_level, parent_code 
        FROM read_parquet('data/processed/hierarchy_main.parquet')
        WHERE n_children > 1
        ORDER BY parent_level, parent_code
    """
    parents_to_train = con.execute(query_parents).fetchall()

    for variant in variants:
        print(f"\n--- TRAINING VARIANT: {variant.upper()} ---")
        start_time = time.time()
        
        v1_dir = Path(f"models/v1/{variant}")
        v1_dir.mkdir(parents=True, exist_ok=True)
        
        manifest = {
            "variant": variant,
            "N_cap": n_cap,
            "C_grid_per_level": best_c_grid,
            "hash_bits_word": params['hash_bits_word'],
            "hash_bits_char": params['hash_bits_char'],
            "idf_checksum": get_sha256(idf_path),
            "pool_checksum": get_sha256("data/processed/training_pool.parquet"),
            "random_seed": 42,
            "versions": {
                "python": platform.python_version(),
                "scikit-learn": sklearn.__version__,
                "duckdb": duckdb.__version__
            },
            "nodes": [],
            "c4_sanity_checks_passed": True
        }
        
        collapsed_nodes = 0

        for count, (p_level, p_code) in enumerate(parents_to_train, 1):
            if count % 20 == 0 or count == 1:
                print(f"  -> Building Node {count}/{len(parents_to_train)} (Level {p_level})")
                
            if p_level == 0:
                target_col, filter_col = 'ch2', None
                node_id = "root"
            elif p_level == 2:
                target_col, filter_col = 'hd4', 'ch2'
                node_id = p_code
            elif p_level == 4:
                target_col, filter_col = 'sh6', 'hd4'
                node_id = p_code
            elif p_level == 6:
                target_col, filter_col = 'ahtn8', 'sh6'
                node_id = p_code
                
            filter_sql = f"AND t.{filter_col} = '{p_code}'" if filter_col else ""
            
            query_train = f"""
                SELECT n.desc_norm, t.{target_col}, t.weight
                FROM read_parquet('data/processed/train_pairs_{variant}.parquet') t
                JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON t.group_l1 = n.desc_norm_id
                JOIN read_parquet('data/processed/training_pool.parquet') p ON t.group_l1 = p.group_l1
                WHERE t.elig_{target_col} = true AND p.rank_main <= {n_cap} {filter_sql}
            """
            
            train_data = con.execute(query_train).fetchall()
            
            y_train = np.array([r[1] for r in train_data])
            if len(set(y_train)) < 2: 
                continue

            X_text = [r[0] for r in train_data]
            w_train = np.array([r[2] for r in train_data], dtype=np.float32)

            X_train = extractor.transform(X_text)
            
            c_val = best_c_grid.get(p_level, 1.0)
            n_rows = X_train.shape[0]
            alpha_val = 1.0 / (c_val * n_rows)
            
            model = SGDClassifier(loss='log_loss', alpha=alpha_val, random_state=42)
            model.fit(X_train, y_train, sample_weight=w_train)
            
            # C4 Sanity Rule: Check if accuracy equals majority rate
            preds = model.predict(X_train)
            acc = np.mean(preds == y_train)
            majority_rate = max(Counter(y_train).values()) / n_rows
            
            if np.isclose(acc, majority_rate) or acc < majority_rate:
                print(f"     [WARNING] Node {node_id} Collapsed! (Acc: {acc:.4f} <= Maj: {majority_rate:.4f})")
                collapsed_nodes += 1
            
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
            
            out_file = v1_dir / f"{node_id}.pkl"
            with open(out_file, 'wb') as f:
                pickle.dump(bundle, f)
                
            manifest["nodes"].append({
                "id": node_id,
                "level": p_level,
                "parent": p_code if p_code else None,
                "classes": [str(c) for c in model.classes_],
                "training_rows": n_rows,
                "alpha": round(alpha_val, 8),
                "active_columns": len(active_indices),
                "number_type": "float32",
                "file_size_bytes": out_file.stat().st_size,
                "sha256": get_sha256(out_file)
            })
            
            del model, bundle, X_train, y_train, train_data, active_cols, active_indices
            if count % 20 == 0:
                gc.collect()

        training_time = round(time.time() - start_time, 2)
        peak_memory = round(get_peak_memory_mb(), 2)
        
        manifest["training_time_seconds"] = training_time
        manifest["peak_memory_mb"] = peak_memory
        manifest["c4_sanity_checks_passed"] = (collapsed_nodes == 0)
        
        with open(v1_dir / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=4)
            
        print(f" Finished {variant}! Time: {training_time}s | Peak RAM: {peak_memory}MB")
        if collapsed_nodes > 0:
            print(f" [FAIL] {collapsed_nodes} nodes failed the C4 sanity check.")
        else:
            print(f" [PASS] Zero collapsed nodes. C4 check passed.")

if __name__ == "__main__":
    main()