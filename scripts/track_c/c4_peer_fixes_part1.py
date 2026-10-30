import duckdb
import yaml
import numpy as np
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, confusion_matrix
import os
from pathlib import Path
import sys

sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor

def peer_fixes_part1():
    con = duckdb.connect()
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    print("--- 1. Exact-Match / Leakage Check ---")
    leak_query = """
        SELECT COUNT(DISTINCT v.group_l1) as leak_count
        FROM read_parquet('data/processed/val_tune_main.parquet') v
        JOIN read_parquet('data/processed/train_pairs_main.parquet') t
          ON v.group_l1 = t.group_l1
    """
    leak_count = con.execute(leak_query).fetchone()[0]
    print(f"Descriptions shared between Train and Val (Leakage): {leak_count}")
    print("(If 0, the firewall held and Exact Match coverage is exactly 0%.)")
    
    print("\n--- 2. Flat Model File Size Check ---")
    features_count = (1 << params['hash_bits_word']) + (1 << params['hash_bits_char']) 
    classes = 2522
    mem_mb = (classes * features_count * 8) / (1024 * 1024)
    print(f"Theoretical Flat Model RAM required to load coefficients:")
    print(f"{classes} classes x {features_count} features x 8 bytes = {mem_mb:.2f} MB")
        
    print("\n--- 3. Alpha Grid Tuning for Root (N=50) ---")
    extractor = FeatureExtractor(
        hash_bits_word=params['hash_bits_word'],
        hash_bits_char=params['hash_bits_char']
    )
    extractor.set_idf(np.load("data/processed/idf_main.npy"))
    
    query_train = """
        SELECT n.desc_norm, t.ch2
        FROM read_parquet('data/processed/train_pairs_main.parquet') t
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON t.group_l1 = n.desc_norm_id
        JOIN read_parquet('data/processed/training_pool.parquet') p ON t.group_l1 = p.group_l1
        WHERE t.elig_ch2 = true AND p.rank_main <= 50
    """
    train_df = con.execute(query_train).fetchdf()
    X_train = extractor.transform(train_df['desc_norm'].tolist())
    y_train = train_df['ch2'].tolist()
    
    query_val = """
        WITH true_labels AS (
            SELECT group_l1, SUBSTRING(ahtn8, 1, 2) as true_ch2,
                   ROW_NUMBER() OVER (PARTITION BY group_l1 ORDER BY tx_count DESC) as rn
            FROM read_parquet('data/processed/desc_code_counts.parquet')
        )
        SELECT n.desc_norm, t.true_ch2
        FROM read_parquet('data/processed/val_tune_main.parquet') v
        JOIN true_labels t ON v.group_l1 = t.group_l1
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON v.group_l1 = n.desc_norm_id
        WHERE t.rn = 1
    """
    val_df = con.execute(query_val).fetchdf()
    X_val = extractor.transform(val_df['desc_norm'].tolist())
    y_val = val_df['true_ch2'].tolist()
    
    alphas = [1e-7, 1e-6, 1e-5, 1e-4, 1e-3]
    best_alpha = None
    best_acc = 0
    best_preds = None
    
    for a in alphas:
        model = SGDClassifier(loss='log_loss', alpha=a, random_state=42)
        model.fit(X_train, y_train)
        preds = model.predict(X_val)
        acc = accuracy_score(y_val, preds) * 100
        print(f"  alpha={a} -> Accuracy: {acc:.2f}%")
        
        if acc > best_acc:
            best_acc = acc
            best_alpha = a
            best_preds = preds
            
    print(f"\nWinner: alpha = {best_alpha}")
    
    print("\n--- 4. Confusion Matrix (Root, best alpha) ---")
    labels = sorted(list(set(y_val)))
    cm = confusion_matrix(y_val, best_preds, labels=labels)
    
    header = f"{'True \\ Pred':>12} | " + " | ".join([f"{l:>6}" for l in labels])
    print(header)
    print("-" * len(header))
    for i, true_l in enumerate(labels):
        row = [f"{v:>6}" for v in cm[i]]
        print(f"{true_l:>12} | " + " | ".join(row))

if __name__ == "__main__":
    peer_fixes_part1()