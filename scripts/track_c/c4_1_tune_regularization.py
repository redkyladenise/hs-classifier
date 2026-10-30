import duckdb
import yaml
import numpy as np
from sklearn.linear_model import SGDClassifier, LogisticRegression
from sklearn.metrics import accuracy_score
import json
from pathlib import Path
from sklearn.datasets import make_classification
import sys

sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor

def prove_alpha_conversion():
    print("--- Check: Toy Data Alpha Conversion Test ---")
    X_toy, y_toy = make_classification(n_samples=1000, n_features=100, random_state=42)
    
    C_toy = 3.0
    lr_toy = LogisticRegression(C=C_toy, random_state=42, max_iter=1000)
    lr_toy.fit(X_toy, y_toy)
    
    # Using shape[0] for safety
    alpha_toy = 1.0 / (C_toy * X_toy.shape[0])
    sgd_toy = SGDClassifier(loss='log_loss', alpha=alpha_toy, random_state=42)
    sgd_toy.fit(X_toy, y_toy)
    
    lr_preds = lr_toy.predict(X_toy)
    sgd_preds = sgd_toy.predict(X_toy)
    match_rate = np.mean(lr_preds == sgd_preds) * 100
    print(f"Prediction Match Rate between LR(C={C_toy}) and SGD(alpha={alpha_toy:.7f}): {match_rate:.2f}%\n")


def tune_regularization(scenario='main'):
    prove_alpha_conversion()
    
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    
    extractor = FeatureExtractor(
        hash_bits_word=params['hash_bits_word'],
        hash_bits_char=params['hash_bits_char']
    )
    extractor.set_idf(np.load(f"data/processed/idf_{scenario}.npy"))
    
    c_grid = params.get('c_grid', [0.3, 1.0, 3.0, 10.0]) + [30.0, 100.0]
    n_cap = 50 
    
    targets = [
        (0, 'ch2', None, None),              
        (2, 'hd4', 'ch2', '84'),            
        (4, 'sh6', 'hd4', '8708'),          
        (6, 'ahtn8', 'sh6', '870829')       
    ]
    
    best_params = {}
    print(f"--- C4.1: Fast SGD Tuning on N={n_cap} with C-Grid {c_grid} ---")
    
    for level, target_col, filter_col, filter_val in targets:
        print(f"\nEvaluating Level {level} (Targeting {target_col})...")
        
        filter_sql_train = f"AND t.{filter_col} = '{filter_val}'" if filter_col else ""
        
        query_train = f"""
            SELECT n.desc_norm, t.{target_col}
            FROM read_parquet('data/processed/train_pairs_{scenario}.parquet') t
            JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON t.group_l1 = n.desc_norm_id
            JOIN read_parquet('data/processed/training_pool.parquet') p ON t.group_l1 = p.group_l1
            WHERE t.elig_{target_col} = true AND p.rank_{scenario} <= {n_cap} {filter_sql_train}
        """
        train_data = con.execute(query_train).fetchdf()
        
        if len(train_data) < 2:
            print("Not enough data to tune this node. Defaulting to C=1.0")
            best_params[level] = 1.0
            continue
            
        X_train = extractor.transform(train_data['desc_norm'].tolist())
        y_train = train_data[target_col].tolist()
        
        query_val = f"""
            WITH true_labels AS (
                SELECT group_l1, SUBSTRING(ahtn8, 1, 2) as true_ch2,
                       SUBSTRING(ahtn8, 1, 4) as true_hd4,
                       SUBSTRING(ahtn8, 1, 6) as true_sh6,
                       ahtn8 as true_ahtn8,
                       ROW_NUMBER() OVER (PARTITION BY group_l1 ORDER BY tx_count DESC) as rn
                FROM read_parquet('data/processed/desc_code_counts.parquet')
            )
            SELECT n.desc_norm, t.true_{target_col} as target
            FROM read_parquet('data/processed/val_tune_{scenario}.parquet') v
            JOIN true_labels t ON v.group_l1 = t.group_l1
            JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON v.group_l1 = n.desc_norm_id
            WHERE t.rn = 1 {f"AND t.true_{filter_col} = '{filter_val}'" if filter_col else ""}
        """
        val_data = con.execute(query_val).fetchdf()
        X_val = extractor.transform(val_data['desc_norm'].tolist())
        y_val = val_data['target'].tolist()
        
        best_c = None
        best_acc = 0
        
        for c in c_grid:
            # FIX: Using X_train.shape[0] to get the row count from the sparse matrix
            alpha_val = 1.0 / (c * X_train.shape[0])
            model = SGDClassifier(loss='log_loss', alpha=alpha_val, random_state=42)
            model.fit(X_train, y_train)
            preds = model.predict(X_val)
            acc = accuracy_score(y_val, preds) * 100
            
            print(f"  C={c} (alpha={alpha_val:.2e}) -> Accuracy: {acc:.2f}%")
            
            if acc > best_acc:
                best_acc = acc
                best_c = c
                
        print(f"-> Winner for Level {level}: C={best_c}")
        best_params[level] = best_c

    Path("config").mkdir(exist_ok=True)
    with open("config/best_c_grid.json", "w") as f:
        json.dump(best_params, f, indent=4)
        
    print("\nDone! Tuned parameters saved to config/best_c_grid.json")

if __name__ == "__main__":
    tune_regularization('main')