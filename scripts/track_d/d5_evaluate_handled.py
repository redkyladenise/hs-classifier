import duckdb
import yaml
import numpy as np
import pandas as pd
from pathlib import Path
import sys
import gc
import shutil
import types

sys.path.append('.')
from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

def bootstrap_difference(acc_base, acc_variant, groups, n_resamples=200):
    df = pd.DataFrame({'base': acc_base, 'var': acc_variant, 'group': groups})
    diffs = []
    unique_groups = df['group'].unique()
    n_groups = len(unique_groups)
    
    np.random.seed(42)
    for _ in range(n_resamples):
        sampled_groups = np.random.choice(unique_groups, size=n_groups, replace=True)
        counts = pd.Series(sampled_groups).value_counts()
        sampled_df = df.set_index('group').loc[counts.index]
        sampled_df['weight'] = counts.values
        
        b_base = np.average(sampled_df['base'], weights=sampled_df['weight'])
        b_var = np.average(sampled_df['var'], weights=sampled_df['weight'])
        diffs.append(b_var - b_base)
        
    return np.percentile(diffs, [2.5, 97.5])

# --- THE PATCH ---
def patched_get_children(self, parent_code, parent_level):
    """Patched version that falls back to 'main' for class eligibility."""
    child_level = parent_level + 2
    scenario_elig = 'main' if self.scenario.startswith('main_h') else self.scenario
    
    query = f"""
        SELECT DISTINCT c.class as child_code
        FROM read_parquet('data/processed/train_pairs_{self.scenario}.parquet') t
        JOIN read_parquet('data/processed/class_eligibility.parquet') c
          ON c.scenario = '{scenario_elig}' AND c.level = {child_level}
        WHERE t.elig_ch2 = true 
    """
    if parent_level == 2:
        query += f"AND t.ch2 = '{parent_code}' AND c.class = t.hd4 AND t.elig_hd4 = true"
    elif parent_level == 4:
        query += f"AND t.hd4 = '{parent_code}' AND c.class = t.sh6 AND t.elig_sh6 = true"
    elif parent_level == 6:
        query += f"AND t.sh6 = '{parent_code}' AND c.class = t.ahtn8 AND t.elig_ahtn8 = true"
    elif parent_level == 0:
        query = f"""
            SELECT DISTINCT t.ch2 as child_code
            FROM read_parquet('data/processed/train_pairs_{self.scenario}.parquet') t
            WHERE t.elig_ch2 = true
        """
    result = self.con.execute(query).fetchall()
    return [row[0] for row in result]
# -----------------

def score_variant(variant_name, test_data, params):
    print(f"\n--- Scoring Variant: {variant_name.upper()} ---")
    
    extractor = FeatureExtractor(params['hash_bits_word'], params['hash_bits_char'])
    extractor.set_idf(np.load("data/processed/idf_main.npy"))
    
    engine = HSInferenceEngine(scenario=variant_name, cache_size=400)
    # Apply the monkey-patch to bypass the missing eligibility table entries
    engine.hierarchy.get_children = types.MethodType(patched_get_children, engine.hierarchy)
    
    predictions = []
    batch_size = 5000
    total_len = len(test_data)
    
    for i in range(0, total_len, batch_size):
        if i % (batch_size * 4) == 0:
            print(f"    Predicting batch {i}/{total_len}...")
            
        batch = test_data.iloc[i:i+batch_size]
        texts = batch['desc_norm'].tolist()
        
        X_batch = extractor.transform(texts)
        preds = engine.predict_beam_batch(X_batch, top_k=5)
        
        for item_beams in preds:
            if item_beams and len(item_beams[0]['code']) >= 8:
                top_1_code = item_beams[0]['code']
                top_1 = [top_1_code[:2], top_1_code[:4], top_1_code[:6], top_1_code]
                top_5_hd4 = [b['code'][:4] for b in item_beams if len(b['code']) >= 4]
                top_5_sh6 = [b['code'][:6] for b in item_beams if len(b['code']) >= 6]
                top_5_ahtn8 = [b['code'] for b in item_beams if len(b['code']) >= 8]
            else:
                top_1 = [None]*4
                top_5_hd4 = top_5_sh6 = top_5_ahtn8 = []
                
            predictions.append({
                'pred_ch2': top_1[0], 'pred_hd4': top_1[1],
                'pred_sh6': top_1[2], 'pred_ahtn8': top_1[3],
                'top5_hd4': top_5_hd4, 'top5_sh6': top_5_sh6, 'top5_ahtn8': top_5_ahtn8
            })
            
    engine.cache.cache.clear()
    gc.collect()
    
    pred_df = pd.DataFrame(predictions)
    res = pd.concat([test_data.reset_index(drop=True), pred_df], axis=1)
    
    metrics = {
        'group': res['group_l1'].values,
        'is_conflicting': res['is_conflicting'].values,
        'acc_ch2': np.array([p in t for p, t in zip(res['pred_ch2'], res['true_ch2'])]).astype(int),
        'acc_hd4': np.array([p in t for p, t in zip(res['pred_hd4'], res['true_hd4'])]).astype(int),
        'acc_sh6': np.array([p in t for p, t in zip(res['pred_sh6'], res['true_sh6'])]).astype(int),
        'acc_ahtn8': np.array([p in t for p, t in zip(res['pred_ahtn8'], res['true_ahtn8'])]).astype(int),
        't5_hd4': np.array([any(tgt in p5 for tgt in t) for t, p5 in zip(res['true_hd4'], res['top5_hd4'])]).astype(int),
        't5_sh6': np.array([any(tgt in p5 for tgt in t) for t, p5 in zip(res['true_sh6'], res['top5_sh6'])]).astype(int),
        't5_ahtn8': np.array([any(tgt in p5 for tgt in t) for t, p5 in zip(res['true_ahtn8'], res['top5_ahtn8'])]).astype(int)
    }
    return metrics

def calculate_summary(metrics_dict, variant, base_metrics=None, split="overall"):
    if split == "overall":
        m, b = metrics_dict, base_metrics
    elif split == "conflicting":
        mask = metrics_dict['is_conflicting'] == 1
        m = {k: v[mask] for k, v in metrics_dict.items()}
        b = {k: v[mask] for k, v in base_metrics.items()} if base_metrics else None
    else: 
        mask = metrics_dict['is_conflicting'] == 0
        m = {k: v[mask] for k, v in metrics_dict.items()}
        b = {k: v[mask] for k, v in base_metrics.items()} if base_metrics else None
            
    row = {
        'variant': variant,
        'split': split,
        'm2_l2': np.mean(m['acc_ch2']),
        'm2_l4': np.mean(m['acc_hd4']),
        'm2_l6': np.mean(m['acc_sh6']),
        'm2_l8': np.mean(m['acc_ahtn8']),
        'm2_t5_l4': np.mean(m['t5_hd4']),
        'm2_t5_l6': np.mean(m['t5_sh6']),
        'm2_t5_l8': np.mean(m['t5_ahtn8']),
        'ci2.5_diff_l8': None,
        'ci97.5_diff_l8': None
    }
    
    if base_metrics:
        ci = bootstrap_difference(b['acc_ahtn8'], m['acc_ahtn8'], m['group'], n_resamples=200)
        row['ci2.5_diff_l8'] = round(ci[0], 4)
        row['ci97.5_diff_l8'] = round(ci[1], 4)
        
    for k, v in row.items():
        if isinstance(v, float) and k not in ['ci2.5_diff_l8', 'ci97.5_diff_l8']:
            row[k] = round(v, 4)
            
    return row

def main():
    print("=" * 60)
    print("Track D - Step D5: Evaluate Handling Impact & Gate D2")
    print("=" * 60)

    for v in ['main_h1', 'main_h2', 'main_h3']:
        dst = Path(f"data/processed/hierarchy_{v}.parquet")
        if not dst.exists():
            shutil.copy("data/processed/hierarchy_main.parquet", dst)

    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)

    con = duckdb.connect()
    
    print("Preparing validation data...")
    query = """
        SELECT v.group_l1, 
               MAX(n.desc_norm) as desc_norm,
               list(substring(t.ahtn8, 1, 2)) as true_ch2,
               list(substring(t.ahtn8, 1, 4)) as true_hd4,
               list(substring(t.ahtn8, 1, 6)) as true_sh6,
               list(t.ahtn8) as true_ahtn8,
               CASE WHEN count(t.ahtn8) > 1 THEN 1 ELSE 0 END as is_conflicting
        FROM read_parquet('data/processed/val_cal_main.parquet') v
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON v.group_l1 = n.desc_norm_id
        JOIN read_parquet('data/processed/desc_code_counts.parquet') t ON v.group_l1 = t.group_l1
        GROUP BY v.group_l1
        ORDER BY v.group_l1
    """
    eval_df = con.execute(query).df()
    print(f"Validation records: {len(eval_df):,}")

    variants = ['main', 'main_h1', 'main_h2', 'main_h3']
    all_metrics = {}
    
    for v in variants:
        all_metrics[v] = score_variant(v, eval_df, params)

    print("\nCalculating metrics and bootstrap intervals...")
    summary_rows = []
    base = all_metrics['main']
    
    for v in variants:
        b_metrics = None if v == 'main' else base
        for split in ['overall', 'conflicting', 'consistent']:
            summary_rows.append(calculate_summary(all_metrics[v], v, b_metrics, split))
            
    res_df = pd.DataFrame(summary_rows)
    
    out_path = Path("reports/tables/d5_validation.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    res_df.to_csv(out_path, index=False)
    
    print("\n--- Gate D2 Pre-Committed Rule Check ---")
    l8_overall = res_df[res_df['split'] == 'overall'][['variant', 'm2_l8', 'ci2.5_diff_l8', 'ci97.5_diff_l8']]
    print(l8_overall.to_string(index=False))
    
    print("\nDecision Execution:")
    success_variants = []
    for _, row in l8_overall.iterrows():
        if row['variant'] == 'main': continue
        if row['ci2.5_diff_l8'] > 0:
            success_variants.append(row['variant'])
            
    if not success_variants:
        print("\nGATE RESULT: All handled methods degraded or failed to statistically improve upon the raw baseline.")
        print("ACTION: The raw, unhandled data REMAINS the official headline model. Freeze the 'main' model.")
    else:
        print(f"\nGATE RESULT: Handled method(s) {success_variants} passed the pre-committed rule (paired interval above zero).")
        print(f"ACTION: Change headline model to {success_variants[0]}.")

if __name__ == "__main__":
    main()