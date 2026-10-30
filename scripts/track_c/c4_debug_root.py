import duckdb
import yaml
import numpy as np
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import accuracy_score
import time

import sys
sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor

def debug_root():
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    
    extractor = FeatureExtractor(
        hash_bits_word=params['hash_bits_word'],
        hash_bits_char=params['hash_bits_char']
    )
    extractor.set_idf(np.load("data/processed/idf_main.npy"))
    
    print("--- Running Peer Debug Checks for Root (Level 2) ---")
    
    # Check 1: Majority-class rate on validation
    query_val = """
        WITH true_labels AS (
            SELECT group_l1, SUBSTRING(ahtn8, 1, 2) as true_ch2,
                   ROW_NUMBER() OVER (PARTITION BY group_l1 ORDER BY tx_count DESC) as rn
            FROM read_parquet('data/processed/desc_code_counts.parquet')
        )
        SELECT t.true_ch2, count(*) as cnt
        FROM read_parquet('data/processed/val_tune_main.parquet') v
        JOIN true_labels t ON v.group_l1 = t.group_l1
        WHERE t.rn = 1
        GROUP BY t.true_ch2
        ORDER BY cnt DESC
    """
    val_counts = con.execute(query_val).fetchdf()
    total_val = val_counts['cnt'].sum()
    top_class = val_counts.iloc[0]
    majority_rate = (top_class['cnt'] / total_val) * 100
    print(f"\nCheck 1: Validation Majority Class is Chapter {top_class['true_ch2']} at {majority_rate:.2f}%")
    
    # Prepare 5,000 rows for Checks 2 & 7
    print("\nFetching 5,000 Training descriptions and Validation descriptions...")
    query_train = """
        SELECT n.desc_norm, t.ch2
        FROM read_parquet('data/processed/train_pairs_main.parquet') t
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON t.group_l1 = n.desc_norm_id
        WHERE t.elig_ch2 = true 
        LIMIT 5000
    """
    train_data = con.execute(query_train).fetchdf()
    X_train = extractor.transform(train_data['desc_norm'].tolist())
    y_train = train_data['ch2'].tolist()
    
    query_val_desc = """
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
    val_data = con.execute(query_val_desc).fetchdf()
    X_val = extractor.transform(val_data['desc_norm'].tolist())
    y_val = val_data['true_ch2'].tolist()

    # Check 7 & 2: Plain Logistic Regression on 5k
    print("\nCheck 7 & 2: Training Plain Logistic Regression on 5k items (C=1.0)...")
    log_reg = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    
    t0 = time.time()
    log_reg.fit(X_train, y_train)
    print(f"  Training time: {time.time()-t0:.2f} seconds")
    
    train_preds = log_reg.predict(X_train)
    val_preds = log_reg.predict(X_val)
    
    print(f"  -> Plain LR Training Accuracy: {accuracy_score(y_train, train_preds)*100:.2f}%")
    print(f"  -> Plain LR Validation Accuracy: {accuracy_score(y_val, val_preds)*100:.2f}%")
    
    # Re-testing SGD with the "Bugged" alpha vs a "Sane" alpha
    print("\nCheck 6: Testing the SGD Alpha Bug...")
    sgd_bad = SGDClassifier(loss='log_loss', alpha=10.0, random_state=42)
    sgd_bad.fit(X_train, y_train)
    bad_val_preds = sgd_bad.predict(X_val)
    print(f"  -> SGD with BUGGED alpha=10.0 Validation Accuracy: {accuracy_score(y_val, bad_val_preds)*100:.2f}%")

    sgd_good = SGDClassifier(loss='log_loss', alpha=0.0001, random_state=42)
    sgd_good.fit(X_train, y_train)
    good_val_preds = sgd_good.predict(X_val)
    print(f"  -> SGD with SANE alpha=0.0001 Validation Accuracy: {accuracy_score(y_val, good_val_preds)*100:.2f}%")

if __name__ == "__main__":
    debug_root()