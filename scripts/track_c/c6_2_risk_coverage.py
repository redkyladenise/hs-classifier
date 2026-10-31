import duckdb
import yaml
import numpy as np
import pandas as pd
import json
import gc
from pathlib import Path
import sys

sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

def apply_calibration(raw_probs, cal_map):
    """Translates raw probabilities to calibrated real-world accuracy using the JSON map."""
    return np.interp(raw_probs, cal_map['x_raw_thresholds'], cal_map['y_calibrated_acc'])

def run_risk_coverage():
    print("--- Running C6.3-C6.5: Risk-Coverage & Target Accuracies ---")
    
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    con.execute("PRAGMA threads=1")
    
    scenarios = ['main', 'y1']
    coverage_records = []
    band_records = []
    target_records = []
    
    # C6.5: Defensible Target Accuracies. 
    # Root (Level 2) is easier, so we demand 95% accuracy. 
    # Level 8 is notoriously hard, so we demand 75% accuracy.
    target_accuracies = {
        'Level 2': 0.95,
        'Level 4': 0.85,
        'Level 6': 0.80,
        'Level 8': 0.75
    }
    
    for scenario in scenarios:
        print(f"\n=================================================")
        print(f"      CALCULATING BANDS: {scenario.upper()}")
        print(f"=================================================")
        
        engine = HSInferenceEngine(scenario=scenario)
        extractor = FeatureExtractor(params['hash_bits_word'], params['hash_bits_char'])
        extractor.set_idf(np.load(f"data/processed/idf_{scenario}.npy"))
        
        with open(f"models/v1/calibration_{scenario}.json", "r") as f:
            calibrator = json.load(f)
            
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
        
        print(f"  -> Predicting {len(df)} rows for {scenario}...")
        beams = engine.predict_beam_batch(X_val, top_k=5)
        
        levels = [
            ('Level 2', 'ch2', 2),
            ('Level 4', 'hd4', 4),
            ('Level 6', 'sh6', 6),
            ('Level 8', 'ahtn8', 8)
        ]
        
        for level_name, target_col, char_len in levels:
            # 1. Get predictions and apply calibration
            preds = [b[0]['code'][:char_len] for b in beams]
            raw_probs = [b[0]['prob'] for b in beams]
            cal_probs = apply_calibration(raw_probs, calibrator[level_name])
            
            df_lvl = pd.DataFrame({'true': df[target_col], 'pred': preds, 'cal_prob': cal_probs})
            df_lvl['correct'] = (df_lvl['true'] == df_lvl['pred']).astype(int)
            
            # 2. Build Risk-Coverage Curve
            df_lvl = df_lvl.sort_values(by='cal_prob', ascending=False).reset_index(drop=True)
            df_lvl['cumulative_correct'] = df_lvl['correct'].cumsum()
            df_lvl['coverage'] = (df_lvl.index + 1) / len(df_lvl)
            df_lvl['accuracy_at_coverage'] = df_lvl['cumulative_correct'] / (df_lvl.index + 1)
            
            # Sample points for the generic curve report
            for cov_target in np.arange(0.1, 1.1, 0.1):
                idx = int(cov_target * len(df_lvl)) - 1
                if idx >= 0:
                    coverage_records.append({
                        'Scenario': scenario,
                        'Level': level_name,
                        'Coverage (%)': round(cov_target * 100),
                        'Accuracy (%)': round(df_lvl.loc[idx, 'accuracy_at_coverage'] * 100, 2),
                        'Min Confidence Req.': round(df_lvl.loc[idx, 'cal_prob'], 4)
                    })
                    
            # 3. C6.5: Calculate coverage for our explicitly chosen Target Accuracies
            target_acc = target_accuracies[level_name]
            # Find the max coverage where accuracy stays above our target
            valid_rows = df_lvl[df_lvl['accuracy_at_coverage'] >= target_acc]
            if not valid_rows.empty:
                achieved_coverage = valid_rows['coverage'].iloc[-1]
            else:
                achieved_coverage = 0.0
                
            target_records.append({
                'Scenario': scenario,
                'Level': level_name,
                'Defended Target Acc (%)': round(target_acc * 100, 1),
                'Max Achieved Coverage (%)': round(achieved_coverage * 100, 2)
            })
            
            # 4. Dynamic Band Setting (Traffic Lights)
            band_high = 0.90 if level_name in ['Level 2', 'Level 4'] else 0.75
            band_low = 0.60 if level_name in ['Level 2', 'Level 4'] else 0.50
            
            high_mask = df_lvl['cal_prob'] >= band_high
            med_mask = (df_lvl['cal_prob'] >= band_low) & (df_lvl['cal_prob'] < band_high)
            low_mask = df_lvl['cal_prob'] < band_low
            
            band_records.append({
                'Scenario': scenario,
                'Level': level_name,
                'High Limit': band_high,
                'High (Auto) Coverage (%)': round(high_mask.mean() * 100, 2),
                'Med Limit': band_low,
                'Low (Manual) Coverage (%)': round(low_mask.mean() * 100, 2)
            })
            
        del engine, df, X_val, beams, df_lvl
        gc.collect()
        
    # Save Tables
    out_dir = Path("reports/tables")
    
    pd.DataFrame(coverage_records).to_csv(out_dir / "c6_risk_coverage.csv", index=False)
    pd.DataFrame(band_records).to_csv(out_dir / "c6_confidence_bands.csv", index=False)
    
    df_targets = pd.DataFrame(target_records)
    df_targets.to_csv(out_dir / "c6_target_accuracies.csv", index=False)
    
    print("\n C6.3 - C6.5 Complete!")
    print(f"Saved risk-coverage curve to: reports/tables/c6_risk_coverage.csv")
    print(f"Saved targets to: reports/tables/c6_target_accuracies.csv")
    print("\n--- DEFENSIBLE TARGET ACCURACIES & COVERAGE ---")
    print(df_targets.to_string(index=False))

if __name__ == "__main__":
    run_risk_coverage()