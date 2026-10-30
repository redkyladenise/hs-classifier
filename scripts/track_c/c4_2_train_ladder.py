import duckdb
import yaml
import numpy as np
from sklearn.linear_model import SGDClassifier
import json
from pathlib import Path
import psutil
import os
import time
import pickle
import pandas as pd
import gc

import sys
sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor
from src.hsclf.models.hierarchy import HSHierarchy

def get_dir_size_mb(path):
    total = 0
    for entry in os.scandir(path):
        if entry.is_file():
            total += entry.stat().st_size
    return total / (1024 * 1024)

def train_ladder(scenario='main'):
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{params['memory_ceiling_gb']}GB'")
    con.execute("PRAGMA threads=1")
    
    with open("config/best_c_grid.json", "r") as f:
        best_c_grid = {int(k): v for k, v in json.load(f).items()}
        
    hierarchy = HSHierarchy(scenario=scenario)
    extractor = FeatureExtractor(
        hash_bits_word=params['hash_bits_word'],
        hash_bits_char=params['hash_bits_char']
    )
    extractor.set_idf(np.load(f"data/processed/idf_{scenario}.npy"))
    
    n_caps = [50, 200]
    results = []
    process = psutil.Process(os.getpid())
    
    query_parents = f"""
        SELECT parent_level, parent_code 
        FROM read_parquet('data/processed/hierarchy_{scenario}.parquet')
        WHERE n_children > 1
        ORDER BY parent_level, parent_code
    """
    parents_to_train = con.execute(query_parents).fetchall()
    
    print(f"--- C4.2: Training Ladder with Active Columns (Caps: {n_caps}) ---")
    
    for n_cap in n_caps:
        print(f"\n🚀 Training Full Tree at N={n_cap}...")
        
        nodes_dir = Path(f"models/track_c/{scenario}/ladder_N{n_cap}")
        nodes_dir.mkdir(parents=True, exist_ok=True)
        
        start_time = time.time()
        peak_mem_mb = 0
        
        for count, (p_level, p_code) in enumerate(parents_to_train, 1):
            if count % 50 == 0 or count == 1:
                print(f"  -> Building Node {count}/{len(parents_to_train)} (Level {p_level})")
                
            current_mem = process.memory_info().rss / (1024 * 1024)
            if current_mem > peak_mem_mb:
                peak_mem_mb = current_mem
                
            if p_level == 0:
                target_col, filter_col = 'ch2', None
            elif p_level == 2:
                target_col, filter_col = 'hd4', 'ch2'
            elif p_level == 4:
                target_col, filter_col = 'sh6', 'hd4'
            elif p_level == 6:
                target_col, filter_col = 'ahtn8', 'sh6'
                
            filter_sql = f"AND t.{filter_col} = '{p_code}'" if filter_col else ""
            
            query_train = f"""
                SELECT n.desc_norm, t.{target_col}
                FROM read_parquet('data/processed/train_pairs_{scenario}.parquet') t
                JOIN read_parquet('data/interim/norm_descriptions.parquet') n
                  ON t.group_l1 = n.desc_norm_id
                JOIN read_parquet('data/processed/training_pool.parquet') p
                  ON t.group_l1 = p.group_l1
                WHERE t.elig_{target_col} = true 
                  AND p.rank_{scenario} <= {n_cap} {filter_sql}
            """
            
            train_data = con.execute(query_train).fetchall()
            if len(train_data) < 2: 
                continue
                
            X_train = extractor.transform([r[0] for r in train_data])
            y_train = [r[1] for r in train_data]
            
            # 1. FIX: Calculate alpha dynamically based on row count
            c_val = best_c_grid.get(p_level, 1.0)
            n_rows = X_train.shape[0]
            alpha_val = 1.0 / (c_val * n_rows)
            
            # Always use SGDClassifier now, since alpha is fixed
            model = SGDClassifier(loss='log_loss', alpha=alpha_val, random_state=42)
            model.fit(X_train, y_train)
            
            # 2. FIX: Active Columns Compression
            # Find columns that have at least one non-zero value
            active_cols = np.array((X_train != 0).sum(axis=0)).flatten() > 0
            active_indices = np.where(active_cols)[0]
            
            # Slice the coefficient matrix to only store the active columns
            model.coef_ = model.coef_[:, active_indices]
            
            # Save the active indices so we can rebuild the full matrix during prediction
            bundle = {
                'model': model,
                'active_indices': active_indices,
                'n_classes': len(model.classes_)
            }
            
            out_file = nodes_dir / f"{p_code}.pkl"
            with open(out_file, 'wb') as f:
                pickle.dump(bundle, f)
                
            del model, bundle, X_train, y_train, train_data, active_cols, active_indices
            if count % 20 == 0:
                gc.collect()

        end_time = time.time()
        train_mins = (end_time - start_time) / 60.0
        disk_mb = get_dir_size_mb(nodes_dir)
        
        print(f"N={n_cap} Finished! Peak RAM: {peak_mem_mb:.1f} MB | Time: {train_mins:.1f} mins | Disk: {disk_mb:.1f} MB")
        
        results.append({
            "N_Cap": n_cap,
            "Peak_Memory_MB": round(peak_mem_mb, 2),
            "Training_Time_Mins": round(train_mins, 2),
            "Disk_Size_MB": round(disk_mb, 2)
        })

    report_dir = Path("reports/tables")
    report_dir.mkdir(parents=True, exist_ok=True)
    df_results = pd.DataFrame(results)
    df_results.to_csv(report_dir / "c4_ladder_hardware_stats.csv", index=False)
    
    print("\nTraining complete! Hardware stats saved to reports/tables/c4_ladder_hardware_stats.csv")

if __name__ == "__main__":
    train_ladder('main')