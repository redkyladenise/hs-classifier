import duckdb
import yaml
import numpy as np
import pickle
import pandas as pd
from pathlib import Path
import sys

sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor
from src.hsclf.models.hierarchy import HSHierarchy

def evaluate_ladders(scenario='main'):
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{params['memory_ceiling_gb']}GB'")
    
    print("1. Loading Validation Set and Features...")
    hierarchy = HSHierarchy(scenario=scenario)
    extractor = FeatureExtractor(
        hash_bits_word=params['hash_bits_word'],
        hash_bits_char=params['hash_bits_char']
    )
    extractor.set_idf(np.load(f"data/processed/idf_{scenario}.npy"))
    
    # Get ground truth
    query_val = f"""
        WITH true_labels AS (
            SELECT group_l1, ahtn8,
                   SUBSTRING(ahtn8, 1, 2) as true_ch2,
                   SUBSTRING(ahtn8, 1, 4) as true_hd4,
                   SUBSTRING(ahtn8, 1, 6) as true_sh6,
                   ROW_NUMBER() OVER (PARTITION BY group_l1 ORDER BY tx_count DESC) as rn
            FROM read_parquet('data/processed/desc_code_counts.parquet')
        )
        SELECT n.desc_norm, t.true_ch2, t.true_hd4, t.true_sh6, t.ahtn8 as true_ahtn8
        FROM read_parquet('data/processed/val_tune_{scenario}.parquet') v
        JOIN true_labels t ON v.group_l1 = t.group_l1
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON v.group_l1 = n.desc_norm_id
        WHERE t.rn = 1
    """
    val_df = con.execute(query_val).fetchdf()
    
    X_val = extractor.transform(val_df['desc_norm'].tolist())
    total_features = X_val.shape[1]
    
    print("\n--- Calculating Baselines ---")
    majority_rates = {
        'ch2': val_df['true_ch2'].value_counts(normalize=True).max() * 100,
        'hd4': val_df['true_hd4'].value_counts(normalize=True).max() * 100,
        'sh6': val_df['true_sh6'].value_counts(normalize=True).max() * 100,
        'ahtn8': val_df['true_ahtn8'].value_counts(normalize=True).max() * 100
    }
    
    n_caps = [50, 200]
    
    for n_cap in n_caps:
        print(f"\n==================================================================")
        print(f"                 EVALUATING LADDER: N={n_cap}                     ")
        print(f"==================================================================")
        
        nodes_dir = Path(f"models/track_c/{scenario}/ladder_N{n_cap}")
        
        preds_df = val_df.copy()
        preds_df['pred_ch2'] = ''
        preds_df['pred_hd4'] = ''
        preds_df['pred_sh6'] = ''
        preds_df['pred_ahtn8'] = ''
        
        levels = [
            ('', 'pred_ch2', 0),
            ('pred_ch2', 'pred_hd4', 2),
            ('pred_hd4', 'pred_sh6', 4),
            ('pred_sh6', 'pred_ahtn8', 6)
        ]
        
        root_probs = None
        root_classes = None
        
        for parent_col, child_col, p_level in levels:
            unique_parents = [None] if p_level == 0 else preds_df[parent_col].unique()
            
            for p_code in unique_parents:
                if p_level > 0 and not p_code: continue
                
                idx = preds_df.index if p_level == 0 else preds_df[preds_df[parent_col] == p_code].index
                if len(idx) == 0: continue
                
                children = hierarchy.get_children(p_code, p_level)
                
                if len(children) == 1:
                    preds_df.loc[idx, child_col] = children[0]
                elif len(children) > 1:
                    
                    # FIX: Handle multiple possible file names for the Root node
                    possible_names = [f"{p_code}.pkl", "None.pkl", "root.pkl", ".pkl"]
                    model_path = None
                    for name in possible_names:
                        if (nodes_dir / name).exists():
                            model_path = nodes_dir / name
                            break
                            
                    if not model_path:
                        preds_df.loc[idx, child_col] = children[0]
                        continue
                        
                    with open(model_path, 'rb') as f:
                        bundle = pickle.load(f)
                        
                    model = bundle['model']
                    
                    # Temporarily rebuild full coefficient matrix for Scikit-Learn compatibility
                    orig_shape = (1 if bundle['n_classes'] <= 2 else bundle['n_classes'], total_features)
                    full_coef = np.zeros(orig_shape)
                    full_coef[:, bundle['active_indices']] = model.coef_
                    model.coef_ = full_coef
                    
                    preds = model.predict(X_val[idx])
                    preds_df.loc[idx, child_col] = preds
                    
                    if p_level == 0:
                        root_probs = model.predict_proba(X_val[idx])
                        root_classes = model.classes_
                        
        # --- Root Top-K Calculation ---
        top2_correct = 0
        top3_correct = 0
        for i, true_l in enumerate(val_df['true_ch2']):
            top_indices = np.argsort(root_probs[i])[-3:][::-1]
            top_classes = [root_classes[idx] for idx in top_indices]
            if true_l in top_classes[:2]: top2_correct += 1
            if true_l in top_classes[:3]: top3_correct += 1
            
        print(f"\n-> Root (Level 2) Top-1 Accuracy: {(preds_df['pred_ch2'] == val_df['true_ch2']).mean()*100:.2f}%")
        print(f"-> Root (Level 2) Top-2 Accuracy: {(top2_correct / len(val_df)) * 100:.2f}%")
        print(f"-> Root (Level 2) Top-3 Accuracy: {(top3_correct / len(val_df)) * 100:.2f}%")
        
        print(f"\n[Metric: val_tune | Scenario: {scenario}]")
        print(f"{'Level':<10} | {'Majority Rate':<15} | {'Greedy Acc':<12} | {'Conditional Acc (If Parent Right)'}")
        print("-" * 80)
        
        # Level 2 (Chapters)
        acc2 = (preds_df['pred_ch2'] == val_df['true_ch2']).mean() * 100
        print(f"{'2 (Ch)':<10} | {majority_rates['ch2']:>14.2f}% | {acc2:>11.2f}% | {'N/A':>20}")
        
        # Level 4 (Headings)
        acc4 = (preds_df['pred_hd4'] == val_df['true_hd4']).mean() * 100
        cond4_mask = preds_df['pred_ch2'] == val_df['true_ch2']
        cond4 = (preds_df.loc[cond4_mask, 'pred_hd4'] == val_df.loc[cond4_mask, 'true_hd4']).mean() * 100
        print(f"{'4 (Hd)':<10} | {majority_rates['hd4']:>14.2f}% | {acc4:>11.2f}% | {cond4:>20.2f}%")

        # Level 6 (Subheadings)
        acc6 = (preds_df['pred_sh6'] == val_df['true_sh6']).mean() * 100
        cond6_mask = preds_df['pred_hd4'] == val_df['true_hd4']
        cond6 = (preds_df.loc[cond6_mask, 'pred_sh6'] == val_df.loc[cond6_mask, 'true_sh6']).mean() * 100
        print(f"{'6 (Sh)':<10} | {majority_rates['sh6']:>14.2f}% | {acc6:>11.2f}% | {cond6:>20.2f}%")

        # Level 8 (Final Code)
        acc8 = (preds_df['pred_ahtn8'] == val_df['true_ahtn8']).mean() * 100
        cond8_mask = preds_df['pred_sh6'] == val_df['true_sh6']
        cond8 = (preds_df.loc[cond8_mask, 'pred_ahtn8'] == val_df.loc[cond8_mask, 'true_ahtn8']).mean() * 100
        print(f"{'8 (Code)':<10} | {majority_rates['ahtn8']:>14.2f}% | {acc8:>11.2f}% | {cond8:>20.2f}%")
        
        # Fallback B context at Level 8
        print("-" * 80)
        print(f"Fallback B (Level 8 overall comparison): 13.88%")

if __name__ == "__main__":
    evaluate_ladders('main')