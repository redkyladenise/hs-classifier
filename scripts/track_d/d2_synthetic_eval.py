import os
import sys
import yaml
import json
import duckdb
import numpy as np
import pandas as pd
import pickle
from pathlib import Path

sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor

def bootstrap_acc(y_true, y_pred, n_boot=1000, seed=42):
    """Standard bootstrap over descriptions (which act as the clusters of transactions)."""
    np.random.seed(seed)
    n = len(y_true)
    accs = []
    for _ in range(n_boot):
        idx = np.random.randint(0, n, size=n)
        accs.append(np.mean(y_true[idx] == y_pred[idx]))
    return np.percentile(accs, 2.5), np.percentile(accs, 97.5)

def bootstrap_diff(y_true, y_pred_var, y_pred_base, n_boot=1000, seed=42):
    """Paired bootstrap differences between a handled variant and the noisy baseline."""
    np.random.seed(seed)
    n = len(y_true)
    diffs = []
    for _ in range(n_boot):
        idx = np.random.randint(0, n, size=n)
        acc_var = np.mean(y_true[idx] == y_pred_var[idx])
        acc_base = np.mean(y_true[idx] == y_pred_base[idx])
        diffs.append(acc_var - acc_base)
    return np.percentile(diffs, 2.5), np.percentile(diffs, 97.5)

def main():
    print("=" * 60)
    print("Track D - Step D2.4: Evaluate Synthetic Variants")
    print("=" * 60)

    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    extractor = FeatureExtractor(
        hash_bits_word=params['hash_bits_word'],
        hash_bits_char=params['hash_bits_char']
    )
    extractor.set_idf(np.load("data/processed/idf_main.npy"))

    con = duckdb.connect()
    print("Fetching conflict-free test items from val_tune_main...")
    
    # Conflict-free at the heading level means COUNT(DISTINCT hd4) = 1
    query = """
    WITH val_groups AS (
        SELECT group_l1 FROM 'data/processed/val_tune_main.parquet'
    ),
    pool_counts AS (
        SELECT 
            c.group_l1,
            SUBSTRING(c.ahtn8, 1, 2) AS ch2,
            SUBSTRING(c.ahtn8, 1, 4) AS hd4
        FROM 'data/processed/desc_code_counts.parquet' c
        INNER JOIN val_groups v ON c.group_l1 = v.group_l1
        GROUP BY c.group_l1, c.ahtn8
    ),
    conflict_free AS (
        SELECT 
            group_l1,
            MIN(ch2) AS ch2,
            MIN(hd4) AS hd4
        FROM pool_counts
        GROUP BY group_l1
        HAVING COUNT(DISTINCT hd4) = 1
    )
    SELECT c.group_l1, c.ch2, c.hd4, n.desc_norm
    FROM conflict_free c
    JOIN 'data/interim/norm_descriptions.parquet' n ON c.group_l1 = n.desc_norm_id
    WHERE c.ch2 IN ('39', '73', '84', '85', '87')
    """
    
    test_df = con.execute(query).df()
    print(f"Loaded {len(test_df)} validation descriptions for evaluation.\n")

    variants = [
        "syn_clean", 
        "syn_noisy_10", "syn_h1_10", "syn_h2_10", "syn_h3_10",
        "syn_noisy_20", "syn_h1_20", "syn_h2_20", "syn_h3_20"
    ]
    
    results = {}
    chapters = ['39', '73', '84', '85', '87']

    for variant in variants:
        preds = []
        for ch2 in chapters:
            df_ch = test_df[test_df['ch2'] == ch2].copy()
            if len(df_ch) == 0: continue
            
            model_path = Path(f"models/v1/synthetic/{variant}/{ch2}.pkl")
            if not model_path.exists(): continue
                
            with open(model_path, 'rb') as f:
                bundle = pickle.load(f)
                
            model = bundle['model']
            active_indices = bundle['active_indices']
            
            X_test = extractor.transform(df_ch['desc_norm'].tolist())
            X_test_active = X_test[:, active_indices]
            
            df_ch['pred'] = model.predict(X_test_active)
            preds.append(df_ch[['group_l1', 'hd4', 'pred']])
            
        # Concat and explicitly sort by group_l1 to guarantee paired alignment across all variants
        df_res = pd.concat(preds, ignore_index=True)
        df_res = df_res.sort_values('group_l1').reset_index(drop=True)
        results[variant] = df_res
        print(f"Scored {variant}")

    rows = []
    
    df_clean = results['syn_clean']
    y_true = df_clean['hd4'].values
    y_pred_clean = df_clean['pred'].values
    acc_clean = np.mean(y_true == y_pred_clean)
    
    ci_l, ci_h = bootstrap_acc(y_true, y_pred_clean)
    rows.append({
        'noise_f': 0.0, 'variant': 'clean', 'n_eval': len(y_true),
        'acc': round(acc_clean*100, 2), 'ci_low': round(ci_l*100, 2), 'ci_high': round(ci_h*100, 2),
        'diff_vs_noisy': 0.0, 'diff_ci_low': 0.0, 'diff_ci_high': 0.0, 'recovery': 1.0
    })

    for noise in ['10', '20']:
        noisy_var = f'syn_noisy_{noise}'
        y_pred_noisy = results[noisy_var]['pred'].values
        acc_noisy = np.mean(y_true == y_pred_noisy)
        
        for h_var in [f'syn_noisy_{noise}', f'syn_h1_{noise}', f'syn_h2_{noise}', f'syn_h3_{noise}']:
            var_name = 'noisy' if h_var == noisy_var else h_var.split('_')[1]
            
            y_pred_curr = results[h_var]['pred'].values
            acc_curr = np.mean(y_true == y_pred_curr)
            
            ci_l, ci_h = bootstrap_acc(y_true, y_pred_curr)
            diff_l, diff_h = bootstrap_diff(y_true, y_pred_curr, y_pred_noisy)
            
            # Recovery bounded by clean baseline
            diff = acc_curr - acc_noisy
            recovery = diff / (acc_clean - acc_noisy) if (acc_clean - acc_noisy) != 0 else 0.0
            
            rows.append({
                'noise_f': float(noise)/100, 'variant': var_name, 'n_eval': len(y_true),
                'acc': round(acc_curr*100, 2), 'ci_low': round(ci_l*100, 2), 'ci_high': round(ci_h*100, 2),
                'diff_vs_noisy': round(diff*100, 2), 'diff_ci_low': round(diff_l*100, 2), 'diff_ci_high': round(diff_h*100, 2),
                'recovery': round(recovery, 4)
            })

    res_df = pd.DataFrame(rows)
    out_dir = Path("reports/tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "d2_synthetic.csv"
    res_df.to_csv(out_path, index=False)
    
    print("\n--- Synthetic Evaluation Results ---")
    print(res_df.to_string(index=False))
    print(f"\nSaved synthetic results table to: {out_path}")

if __name__ == "__main__":
    main()