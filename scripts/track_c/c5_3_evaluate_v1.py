import duckdb
import yaml
import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

def calculate_majority_metrics(df, level_col, parent_col=None):
    maj_rate = df[level_col].value_counts(normalize=True).max()
    
    if parent_col:
        majority_children = df.groupby(parent_col)[level_col].agg(lambda x: x.mode()[0] if not x.mode().empty else None)
        df['maj_guess'] = df[parent_col].map(majority_children)
        maj_upper_bound = (df['maj_guess'] == df[level_col]).mean()
    else:
        maj_upper_bound = maj_rate 
        
    return maj_rate, maj_upper_bound

def run_evaluation():
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{params.get('memory_ceiling_gb', 0.76)}GB'")
    con.execute("PRAGMA threads=1")
    
    scenarios = ['main', 'y1']
    results = []
    
    for scenario in scenarios:
        print(f"\n=================================================")
        print(f"      EVALUATING V1 MODELS: {scenario.upper()}")
        print(f"=================================================")
        
        engine = HSInferenceEngine(scenario=scenario)
        extractor = FeatureExtractor(params['hash_bits_word'], params['hash_bits_char'])
        extractor.set_idf(np.load(f"data/processed/idf_{scenario}.npy"))
        
        query = f"""
            WITH true_labels AS (
                SELECT group_l1, 
                       SUBSTRING(ahtn8, 1, 2) as ch2,
                       SUBSTRING(ahtn8, 1, 4) as hd4,
                       SUBSTRING(ahtn8, 1, 6) as sh6,
                       ahtn8,
                       ROW_NUMBER() OVER (PARTITION BY group_l1 ORDER BY tx_count DESC) as rn
                FROM read_parquet('data/processed/desc_code_counts.parquet')
            )
            SELECT v.group_l1, n.desc_norm, t.ch2, t.hd4, t.sh6, t.ahtn8
            FROM read_parquet('data/processed/val_cal_{scenario}.parquet') v
            JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON v.group_l1 = n.desc_norm_id
            JOIN true_labels t ON v.group_l1 = t.group_l1
            WHERE t.rn = 1
        """
        df = con.execute(query).df()
        X_val = extractor.transform(df['desc_norm'].tolist())
        
        print(f"  -> Predicting {len(df)} rows (Greedy / top_k=1)...")
        greedy_beams = engine.predict_beam_batch(X_val, top_k=1)
        
        print(f"  -> Predicting {len(df)} rows (Beam-5 / top_k=5)...")
        beam5_beams = engine.predict_beam_batch(X_val, top_k=5)
        
        levels = [
            ('Level 2 (Chapter)', 'ch2', None, 2),
            ('Level 4 (Heading)', 'hd4', 'ch2', 4),
            ('Level 6 (Subheading)', 'sh6', 'hd4', 6),
            ('Level 8 (Final)', 'ahtn8', 'sh6', 8)
        ]
        
        for level_name, target_col, parent_col, char_len in levels:
            print(f"  -> Calculating metrics for {level_name}...")
            
            df[f'greedy_{target_col}'] = [b[0]['code'][:char_len] for b in greedy_beams]
            df[f'beam_top1_{target_col}'] = [b[0]['code'][:char_len] for b in beam5_beams]
            df[f'beam_top5_{target_col}'] = [[path['code'][:char_len] for path in b] for b in beam5_beams]
            
            # 1. Greedy Accuracy
            greedy_acc = (df[f'greedy_{target_col}'] == df[target_col]).mean()
            
            # 2. Beam-5 Top-1 Accuracy
            beam_top1_acc = (df[f'beam_top1_{target_col}'] == df[target_col]).mean()
            
            # 3. Beam-5 Top-5 Accuracy
            beam_top5_acc = df.apply(lambda row: row[target_col] in row[f'beam_top5_{target_col}'], axis=1).mean()
            
            # 4. Conditional Accuracy (Using Greedy path)
            if parent_col:
                parent_correct_mask = df[f'greedy_{parent_col}'] == df[parent_col]
                if parent_correct_mask.sum() > 0:
                    cond_acc = (df.loc[parent_correct_mask, f'greedy_{target_col}'] == df.loc[parent_correct_mask, target_col]).mean()
                else:
                    cond_acc = 0.0
            else:
                cond_acc = greedy_acc
                
            # 5. Majority Baselines
            maj_rate, maj_upper = calculate_majority_metrics(df, target_col, parent_col)
            
            results.append({
                'Scenario': scenario,
                'Set': 'val_cal',
                'Metric': level_name,
                'Majority Rate': round(maj_rate * 100, 2),
                'Majority Upper Bound': round(maj_upper * 100, 2),
                'Greedy Acc': round(greedy_acc * 100, 2),
                'Beam-5 Top-1': round(beam_top1_acc * 100, 2),
                'Beam-5 Top-5': round(beam_top5_acc * 100, 2),
                'Cond. Acc (Parent Right)': round(cond_acc * 100, 2)
            })

    out_dir = Path("reports/tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    results_df = pd.DataFrame(results)
    results_df.to_csv(out_dir / "c5_val_cal.csv", index=False)
    
    print("\n Evaluation Complete! Saved to reports/tables/c5_val_cal.csv")
    print("\n--- FINAL MOCK EXAM SCORES ---")
    print(results_df.to_string(index=False))

if __name__ == "__main__":
    run_evaluation()