import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
import sys
import math
import yaml

sys.path.append('.')
from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

def wilson_interval(count, n, z=1.96):
    if n == 0: return 0.0, 0.0
    p = count / n
    denominator = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return (center - margin) / denominator, (center + margin) / denominator

def main():
    print("=" * 60)
    print("Track D - Steps 1-3: Audit Scoring & Mismatch Reproduction")
    print("=" * 60)

    # 1. Load actual hash bits from params instead of hardcoding
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)

    con = duckdb.connect()
    
    print("Loading audit records...")
    audit_keys = con.execute("SELECT sample_id, group_l1, stratum FROM read_csv_auto('data/audit/sample_key.csv')").df()
    norms = con.execute("SELECT desc_norm_id, desc_norm FROM read_parquet('data/interim/norm_descriptions.parquet')").df()
    
    # Merge and ensure no duplicates
    audit_df = audit_keys.merge(norms, left_on='group_l1', right_on='desc_norm_id', how='inner').drop_duplicates('sample_id')
    
    verified_df = con.execute("SELECT * FROM read_parquet('data/audit/verified_set.parquet')").df()
    frozen_df = con.execute("SELECT * FROM read_csv_auto('data/audit/labels_frozen.csv')").df()

    models = ['main', 'main_h1', 'main_h2', 'main_h3']
    
    # Use proper parameters
    extractor = FeatureExtractor(params['hash_bits_word'], params['hash_bits_char'])
    extractor.set_idf(np.load("data/processed/idf_main.npy"))
    
    X_audit = extractor.transform(audit_df['desc_norm'].tolist())
    all_preds = []

    # Step 1: Audit Scoring
    for model in models:
        print(f"Scoring {model}...")
        engine = HSInferenceEngine(scenario=model, cache_size=400)
        engine.hierarchy.scenario = 'main' # Force structural alignment
        
        preds = engine.predict_beam_batch(X_batch=X_audit, top_k=1)
        
        for i, item_beams in enumerate(preds):
            pred_8 = item_beams[0]['code'] if item_beams else ""
            all_preds.append({
                'model': model,
                'sample_id': audit_df['sample_id'].iloc[i],
                'group_l1': audit_df['group_l1'].iloc[i],
                'stratum': audit_df['stratum'].iloc[i],
                'pred_2': pred_8[:2] if len(pred_8) >= 2 else "",
                'pred_4': pred_8[:4] if len(pred_8) >= 4 else "",
                'pred_6': pred_8[:6] if len(pred_8) >= 6 else "",
                'pred_8': pred_8
            })
            
    preds_df = pd.DataFrame(all_preds)
    results = []

    # Step 2: Verified Set (66) Metrics
    print("Calculating Verified Set (66) metrics...")
    ver_merged = preds_df.merge(verified_df, on='sample_id')
    base_preds = ver_merged[ver_merged['model'] == 'main'].set_index('sample_id')
    
    for model in models:
        m_df = ver_merged[ver_merged['model'] == model].set_index('sample_id')
        for lvl in [2, 4, 6, 8]:
            correct = (m_df[f'pred_{lvl}'] == m_df[f'verified_label_{lvl}']).sum()
            n_total = len(m_df)
            ci_low, ci_high = wilson_interval(correct, n_total)
            
            w2r = r2w = 0
            if model != 'main':
                base_correct = (base_preds[f'pred_{lvl}'] == base_preds[f'verified_label_{lvl}'])
                mod_correct = (m_df[f'pred_{lvl}'] == m_df[f'verified_label_{lvl}'])
                w2r = ((~base_correct) & mod_correct).sum()
                r2w = (base_correct & (~mod_correct)).sum()
                
            results.append({
                'metric': f'verified_acc_l{lvl}', 'set': 'verified_66', 
                'scenario': 'audit', 'model': model, 'level': lvl,
                'count': correct, 'total': n_total, 'rate': round(correct/n_total, 4),
                'ci_low': round(ci_low, 4), 'ci_high': round(ci_high, 4),
                'wrong_to_right': w2r, 'right_to_wrong': r2w
            })

    # Step 3: Mismatch Reproduction (Level 8)
    print("Calculating Mismatch Reproduction...")
    frozen_melt = pd.wide_to_long(frozen_df, stubnames=['code_', 'label_'], i='sample_id', j='rank').reset_index()
    frozen_melt['code_'] = frozen_melt['code_'].astype(str).str.replace(r'\.0$', '', regex=True)
    
    mismatch_ids = frozen_melt[frozen_melt['label_'] == 'Mismatch']['sample_id'].unique()
    
    for model in models:
        m_preds = preds_df[(preds_df['model'] == model) & (preds_df['sample_id'].isin(mismatch_ids))]
        
        match_count = mismatch_count = 0
        total_mismatch_items = len(m_preds)
        
        for _, row in m_preds.iterrows():
            item_labels = frozen_melt[frozen_melt['sample_id'] == row['sample_id']]
            pred_code = row['pred_8']
            
            if pred_code in item_labels[item_labels['label_'] == 'Mismatch']['code_'].values:
                mismatch_count += 1
            if pred_code in item_labels[item_labels['label_'] == 'Match']['code_'].values:
                match_count += 1
                
        results.append({
            'metric': 'mismatch_reproduction', 'set': 'audit_mismatch',
            'scenario': 'audit', 'model': model, 'level': 8,
            'count': mismatch_count, 'total': total_mismatch_items, 'rate': round(mismatch_count/total_mismatch_items, 4)
        })
        results.append({
            'metric': 'match_alignment', 'set': 'audit_mismatch',
            'scenario': 'audit', 'model': model, 'level': 8,
            'count': match_count, 'total': total_mismatch_items, 'rate': round(match_count/total_mismatch_items, 4)
        })

    out_df = pd.DataFrame(results)
    out_path = Path("reports/tables/d6_audit.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    
    print(f"\nSaved audit evaluation to {out_path}")
    print(out_df[['metric', 'model', 'level', 'rate', 'wrong_to_right', 'right_to_wrong']].head(15))

if __name__ == "__main__":
    main()