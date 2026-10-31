import duckdb
import yaml
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
import json
import gc
from pathlib import Path
import sys

sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

def run_calibration():
    print("--- Running C6.1: Calibration & Reliability ---")
    
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{params.get('memory_ceiling_gb', 0.76)}GB'")
    con.execute("PRAGMA threads=1")
    
    scenarios = ['main', 'y1']
    reliability_records = []
    ece_records = []
    freq_records = [] # FIX 1: Tracker for Class Frequencies
    
    for scenario in scenarios:
        print(f"\n=================================================")
        print(f"      CALIBRATING SCENARIO: {scenario.upper()}")
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
        
        print(f"  -> Predicting {len(df)} rows to gather raw confidences...")
        beams = engine.predict_beam_batch(X_val, top_k=5)
        
        levels = [
            ('Level 2', 'ch2', 2),
            ('Level 4', 'hd4', 4),
            ('Level 6', 'sh6', 6),
            ('Level 8', 'ahtn8', 8)
        ]
        
        calibration_map = {}
        
        for level_name, target_col, char_len in levels:
            preds = [b[0]['code'][:char_len] for b in beams]
            probs = [b[0]['prob'] for b in beams]
            
            df_lvl = pd.DataFrame({
                'true': df[target_col],
                'pred': preds,
                'prob': probs
            })
            df_lvl['correct'] = (df_lvl['true'] == df_lvl['pred']).astype(int)
            
            # FIX 1: Calculate True vs Predicted Class Frequencies
            true_freq = df_lvl['true'].value_counts(normalize=True).rename('True Frequency')
            pred_freq = df_lvl['pred'].value_counts(normalize=True).rename('Predicted Frequency')
            df_freq = pd.concat([true_freq, pred_freq], axis=1).fillna(0.0)
            df_freq.index.name = 'Code'
            df_freq.reset_index(inplace=True)
            df_freq['Scenario'] = scenario
            df_freq['Level'] = level_name
            freq_records.append(df_freq)
            
            # Fit Isotonic Regression
            iso_reg = IsotonicRegression(out_of_bounds='clip')
            iso_reg.fit(df_lvl['prob'], df_lvl['correct'])
            
            calibration_map[level_name] = {
                'x_raw_thresholds': iso_reg.X_thresholds_.tolist(),
                'y_calibrated_acc': iso_reg.y_thresholds_.tolist()
            }
            
            # Create 20 Equal-Frequency Bins
            df_lvl['bin'] = pd.qcut(df_lvl['prob'], q=20, duplicates='drop')
            bin_stats = df_lvl.groupby('bin', observed=True).agg(
                count=('prob', 'count'),
                mean_raw_prob=('prob', 'mean'),
                actual_accuracy=('correct', 'mean')
            ).reset_index()
            
            # Calculate Expected Calibration Error (ECE)
            total_items = bin_stats['count'].sum()
            bin_stats['abs_error'] = abs(bin_stats['mean_raw_prob'] - bin_stats['actual_accuracy'])
            ece = (bin_stats['abs_error'] * bin_stats['count']).sum() / total_items
            
            ece_records.append({
                'Scenario': scenario,
                'Level': level_name,
                'ECE (%)': round(ece * 100, 2)
            })
            
            for _, row in bin_stats.iterrows():
                reliability_records.append({
                    'Scenario': scenario,
                    'Level': level_name,
                    'Bin Range': str(row['bin']),
                    'Count': row['count'],
                    'Mean Raw Prob': round(row['mean_raw_prob'], 4),
                    'Actual Accuracy': round(row['actual_accuracy'], 4),
                    'Error': round(row['abs_error'], 4)
                })
                
            print(f"     [{level_name}] ECE: {ece*100:.2f}%")
            
        # Save Calibration JSON
        v1_dir = Path(f"models/v1")
        with open(v1_dir / f"calibration_{scenario}.json", "w") as f:
            json.dump(calibration_map, f, indent=4)
            
        # FIX 2: Aggressive Garbage Collection before loading the next scenario
        del engine, df, X_val, beams, df_lvl
        gc.collect()
            
    # Save Tables
    out_dir = Path("reports/tables")
    pd.DataFrame(reliability_records).to_csv(out_dir / "c6_reliability.csv", index=False)
    
    df_ece = pd.DataFrame(ece_records)
    df_ece.to_csv(out_dir / "c6_ece.csv", index=False)
    
    df_freq_all = pd.concat(freq_records, ignore_index=True)
    df_freq_all = df_freq_all[['Scenario', 'Level', 'Code', 'True Frequency', 'Predicted Frequency']]
    df_freq_all.to_csv(out_dir / "c6_class_frequencies.csv", index=False)
    
    print("\n C6.1 Complete!")
    print(f"Saved calibrators to: models/v1/calibration_*.json")
    print(f"Saved tables to: reports/tables/c6_*.csv")
    print("\n--- EXPECTED CALIBRATION ERROR (ECE) ---")
    print(df_ece.to_string(index=False))

if __name__ == "__main__":
    run_calibration()