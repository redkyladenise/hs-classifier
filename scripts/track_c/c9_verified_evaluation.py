import duckdb
import pandas as pd
import numpy as np
from pathlib import Path

def wilson_ci(correct, n, z=1.96):
    """Calculates the Wilson Score Interval for small samples."""
    if n == 0: return 0.0, 0.0
    p = correct / n
    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    spread = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
    return max(0.0, center - spread), min(1.0, center + spread)

def run_c9():
    print("--- C9: Verified Set Evaluation ---")
    out_dir = Path("reports/tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    con = duckdb.connect()
    
    # 1. Join Verified Set with Predictions
    query = """
    WITH verified AS (
        SELECT sample_id, stratum, goods_description_norm, 
               verified_label_8 as v8, verified_label_6 as v6, 
               verified_label_4 as v4, verified_label_2 as v2
        FROM read_parquet('data/audit/verified_set.parquet')
    ),
    text_bridge AS (
        SELECT desc_norm_id, desc_norm 
        FROM read_parquet('data/interim/norm_descriptions.parquet')
    ),
    mapping AS (
        SELECT desc_norm_id, majority_ahtn8
        FROM read_parquet('data/processed/unique_descriptions.parquet')
    ),
    preds AS (
        SELECT group_l1 as desc_norm_id, 
               pred_1, pred_2, pred_3, pred_4, pred_5
        FROM read_parquet('data/processed/predictions_unseen/*.parquet')
    )
    SELECT v.*, m.majority_ahtn8 as decl8, 
           p.pred_1, p.pred_2, p.pred_3, p.pred_4, p.pred_5
    FROM verified v
    JOIN text_bridge b ON v.goods_description_norm = b.desc_norm
    JOIN mapping m ON b.desc_norm_id = m.desc_norm_id
    JOIN preds p ON b.desc_norm_id = p.desc_norm_id
    """
    
    try:
        df = con.execute(query).df()
    except Exception as e:
        print(f" SQL Join Error (might need to adjust mapping path): {e}")
        return

    if len(df) != 66:
        print(f" WARNING: Expected 66 records, but joined {len(df)}. Check IDs.")
    
    # Stratum Weights
    weights = {'A': 0.0210, 'B': 0.1119, 'C': 0.8671}
    levels = [2, 4, 6, 8]
    metrics = ['top1', 'top5']
    results = []

    # 2. Evaluation Logic
    for lvl in levels:
        v_col = f'v{lvl}'
        
        # Calculate Top-1 and Top-5 matches
        df[f'top1_match_{lvl}'] = df['pred_1'].str[:lvl] == df[v_col]
        
        if lvl > 2:
            df[f'top5_match_{lvl}'] = df.apply(lambda r: r[v_col] in [
                str(r['pred_1'])[:lvl], str(r['pred_2'])[:lvl], str(r['pred_3'])[:lvl], 
                str(r['pred_4'])[:lvl], str(r['pred_5'])[:lvl]], axis=1)
            
        # Stratum A Declarations (Majority vs Verified)
        if lvl == 8:
            df['decl_match_8'] = df['decl8'] == df['v8']
            
    # 3. Aggregation and Wilson Intervals
    def append_stats(stratum, lvl, metric_name, is_match_series, basis='verified'):
        n = len(is_match_series)
        n_corr = is_match_series.sum()
        acc = n_corr / n if n > 0 else 0
        ci_low, ci_high = wilson_ci(n_corr, n)
        results.append({
            'scenario': 'unseen', 'level': lvl, 'metric': metric_name, 
            'label_basis': basis, 'stratum': stratum, 'n': n, 
            'n_correct': n_corr, 'accuracy': acc, 'ci_low': ci_low, 'ci_high': ci_high
        })
        return acc

    for lvl in levels:
        for metric in (['top1', 'top5'] if lvl > 2 else ['top1']):
            col = f'{metric}_match_{lvl}'
            
            # All 66
            append_stats('all', lvl, metric, df[col])
            
            # Per Stratum
            acc_A = append_stats('A', lvl, metric, df[df['stratum'] == 'A'][col])
            acc_B = append_stats('B', lvl, metric, df[df['stratum'] == 'B'][col])
            acc_C = append_stats('C', lvl, metric, df[df['stratum'] == 'C'][col])
            
            # Weighted Estimate
            w_acc = (weights['A']*acc_A) + (weights['B']*acc_B) + (weights['C']*acc_C)
            results.append({
                'scenario': 'unseen', 'level': lvl, 'metric': metric, 
                'label_basis': 'verified', 'stratum': 'weighted', 'n': 790058, 
                'n_correct': None, 'accuracy': w_acc, 'ci_low': None, 'ci_high': None
            })

    # Compare Stratum A vs Declared Majority
    append_stats('A', 8, 'top1', df[df['stratum'] == 'A']['decl_match_8'], basis='declared_majority')

    df_res = pd.DataFrame(results)
    df_res.to_csv(out_dir / "c9_verified.csv", index=False)
    
    print(" C9 Verified evaluation complete! Saved to reports/tables/c9_verified.csv")
    print(f"Sanity Check: Unweighted Level 2 Accuracy is {df['top1_match_2'].mean()*100:.1f}%")

if __name__ == "__main__":
    run_c9()