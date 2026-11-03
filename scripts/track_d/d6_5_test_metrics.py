import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

def fast_cluster_bootstrap(base_acc, var_acc, groups, n_resamples=200):
    df = pd.DataFrame({'base': base_acc, 'var': var_acc, 'group': groups})
    agg = df.groupby('group').agg(
        base_sum=('base', 'sum'),
        var_sum=('var', 'sum'),
        n_rows=('base', 'count')
    )
    
    base_sums = agg['base_sum'].values
    var_sums = agg['var_sum'].values
    n_rows = agg['n_rows'].values
    n_groups = len(agg)
    
    diffs = np.zeros(n_resamples)
    np.random.seed(42)
    
    for i in range(n_resamples):
        idx = np.random.randint(0, n_groups, size=n_groups)
        total_rows = np.sum(n_rows[idx])
        b_base = np.sum(base_sums[idx]) / total_rows
        b_var = np.sum(var_sums[idx]) / total_rows
        diffs[i] = b_var - b_base
        
    return np.percentile(diffs, [2.5, 97.5])

def main():
    print("=" * 60)
    print("Track D - Step D6.5: Test Metrics (Baseline vs H3)")
    print("=" * 60)

    con = duckdb.connect()
    
    print("1. Joining test IDs, predictions, and ground truth...")
    query = """
    WITH true_codes AS (
        SELECT group_l1, list(ahtn8) as true_all_8, count(ahtn8) as n_codes
        FROM read_parquet('data/processed/desc_code_counts.parquet')
        GROUP BY group_l1
    )
    SELECT 
        s.group_l1, s.chapter, s.group_l2,
        p_raw.pred_1 as raw_p1, p_raw.pred_2 as raw_p2, p_raw.pred_3 as raw_p3, p_raw.pred_4 as raw_p4, p_raw.pred_5 as raw_p5,
        p_h3.pred_1 as h3_p1, p_h3.pred_2 as h3_p2, p_h3.pred_3 as h3_p3, p_h3.pred_4 as h3_p4, p_h3.pred_5 as h3_p5,
        u.majority_ahtn8 as true_majority_8,
        CASE WHEN u.n_transactions = 1 THEN 1 ELSE 0 END as is_singleton,
        CASE WHEN tc.n_codes > 1 THEN 1 ELSE 0 END as is_conflicting,
        tc.true_all_8
    FROM read_parquet('data/processed/d_test_sample_ids.parquet') s
    JOIN read_parquet('data/processed/predictions_unseen/part_*.parquet') p_raw ON s.group_l1 = p_raw.group_l1
    JOIN read_parquet('data/processed/predictions_test_h3.parquet') p_h3 ON s.group_l1 = p_h3.group_l1
    JOIN read_parquet('data/processed/unique_descriptions.parquet') u ON s.group_l1 = u.desc_norm_id
    JOIN true_codes tc ON s.group_l1 = tc.group_l1
    """
    
    df = con.execute(query).df()
    print(f"Total merged records: {len(df):,}")

    cols_to_clean = ['raw_p1', 'raw_p2', 'raw_p3', 'raw_p4', 'raw_p5', 
                     'h3_p1', 'h3_p2', 'h3_p3', 'h3_p4', 'h3_p5', 'true_majority_8']
    for col in cols_to_clean:
        df[col] = df[col].fillna('').astype(str)

    print("2. Pre-calculating global metric arrays (Fast Python Native)...")
    
    # Extract to native Python lists for extreme speed
    true_all = df['true_all_8'].tolist()
    raw_p = [df[f'raw_p{i}'].tolist() for i in range(1, 6)]
    h3_p = [df[f'h3_p{i}'].tolist() for i in range(1, 6)]
    
    # Pre-build lookup sets for O(1) speed
    true_sets = {}
    for lvl in [2, 4, 6, 8]:
        true_sets[lvl] = [{str(t)[:lvl] for t in codes if pd.notna(t)} for codes in true_all]

    levels = [2, 4, 6, 8]
    for prefix, preds in [('raw', raw_p), ('h3', h3_p)]:
        p1 = preds[0]
        for lvl in levels:
            # M1 is fast enough in Pandas
            df[f'{prefix}_m1_l{lvl}'] = (df[f'{prefix}_p1'].str[:lvl] == df['true_majority_8'].str[:lvl]).astype(int)
            
            # M2 Top-1 (Python Zip loop)
            t_sets = true_sets[lvl]
            m2_t1 = [1 if (p and p[:lvl] in ts) else 0 for p, ts in zip(p1, t_sets)]
            df[f'{prefix}_m2_top1_l{lvl}'] = m2_t1
            
            if lvl >= 4:
                # M2 Top-5 (Python Zip loop)
                m2_t5 = []
                for i in range(len(t_sets)):
                    ts = t_sets[i]
                    match = 0
                    for rank in range(5):
                        p_val = preds[rank][i]
                        if p_val and p_val[:lvl] in ts:
                            match = 1
                            break
                    m2_t5.append(match)
                df[f'{prefix}_m2_top5_l{lvl}'] = m2_t5

    splits = {
        'overall': df,
        'conflict_prone': df[df['is_conflicting'] == 1],
        'consistent': df[df['is_conflicting'] == 0],
        'singleton': df[df['is_singleton'] == 1],
        'repeated': df[df['is_singleton'] == 0]
    }
    for chap in df['chapter'].unique():
        splits[f'chapter_{chap}'] = df[df['chapter'] == chap]

    print("3. Executing split aggregations and fast bootstraps...")
    all_metrics = []
    
    for split_name, split_df in splits.items():
        if len(split_df) == 0: continue
        groups = split_df['group_l2'].values
        
        for lvl in levels:
            metric_keys = [('M1_top1', f'm1_l{lvl}'), ('M2_top1', f'm2_top1_l{lvl}')]
            if lvl >= 4:
                metric_keys.append(('M2_top5', f'm2_top5_l{lvl}'))
                
            for metric_label, col_suffix in metric_keys:
                raw_array = split_df[f'raw_{col_suffix}'].values
                h3_array = split_df[f'h3_{col_suffix}'].values
                
                raw_rate = raw_array.mean()
                h3_rate = h3_array.mean()
                ci_low, ci_high = fast_cluster_bootstrap(raw_array, h3_array, groups)
                
                all_metrics.append({
                    'metric': metric_label, 'set': split_name, 'scenario': 'test',
                    'model': 'main', 'level': lvl, 'rate': round(raw_rate, 4),
                    'ci2.5_diff': None, 'ci97.5_diff': None
                })
                all_metrics.append({
                    'metric': metric_label, 'set': split_name, 'scenario': 'test',
                    'model': 'main_h3', 'level': lvl, 'rate': round(h3_rate, 4),
                    'ci2.5_diff': round(ci_low, 4), 'ci97.5_diff': round(ci_high, 4)
                })

    out_df = pd.DataFrame(all_metrics)
    out_path = Path("reports/tables/d6_test.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    
    print(f"\nSaved test metrics to {out_path}")
    print("\n--- Level 8 Top-1 (M2) Summary ---")
    summary = out_df[(out_df['level'] == 8) & (out_df['metric'] == 'M2_top1') & (out_df['set'].isin(['overall', 'conflict_prone', 'consistent']))]
    print(summary[['set', 'model', 'rate', 'ci2.5_diff', 'ci97.5_diff']].to_string(index=False))

if __name__ == "__main__":
    main()