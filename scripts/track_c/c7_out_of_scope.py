import duckdb
import yaml
import numpy as np
import pandas as pd
import random
import string
import pickle
from pathlib import Path
import sys

sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor

def generate_gibberish(n=200):
    """Generates random keyboard-smash strings (e.g., 'asdfqwer')"""
    return [''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 15))) for _ in range(n)]

def generate_extreme(n=100):
    """Generates 50 extremely short strings and 50 massive walls of text"""
    shorts = ['a', 'x', '1', 'no', 'ok'] * 10
    longs = [''.join(random.choices(string.ascii_lowercase + ' ', k=500)) for _ in range(50)]
    return shorts[:50] + longs[:50]

def run_c7():
    print("--- Running C7: Out-of-Scope Check ---")
    
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    scenario = 'main'
    
    extractor = FeatureExtractor(params['hash_bits_word'], params['hash_bits_char'])
    extractor.set_idf(np.load(f"data/processed/idf_{scenario}.npy"))
    
    # Load just the Level 2 Root Model to get pure root-level confidence
    print("  -> Loading Level 2 Root Model...")
    with open(f"models/v1/{scenario}/root.pkl", "rb") as f:
        saved_data = pickle.load(f)
        
    # Extract the actual model from the dictionary
    if isinstance(saved_data, dict):
        root_model = next(v for v in saved_data.values() if hasattr(v, 'predict_proba'))
    else:
        root_model = saved_data
        
    # 1. Get In-Scope valid data to calculate the threshold
    print("  -> Evaluating In-Scope validation data...")
    query_in = f"""
        SELECT n.desc_norm
        FROM read_parquet('data/processed/val_cal_{scenario}.parquet') v
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n 
          ON v.group_l1 = n.desc_norm_id
    """
    df_in = con.execute(query_in).df()
    X_in = extractor.transform(df_in['desc_norm'].tolist())
    
    # Load the active indices bundle for the root model
    print("  -> Loading Level 2 Root bundle metadata...")
    with open(f"models/v1/{scenario}/root.pkl", "rb") as f:
        root_bundle = pickle.load(f)
    
    # Get the highest probability the model assigned to each in-scope item
    # We MUST slice X_in to match the active columns the model was trained on!
    active_cols = root_bundle['active_indices']
    in_probs = root_model.predict_proba(X_in[:, active_cols]).max(axis=1)
    
    # 2. Find t_oos threshold (Accepts >= 98% of in-scope)
    # The 2nd percentile means 98% of legitimate shipments score higher than this line.
    t_oos = float(np.percentile(in_probs, 2))
    print(f"  -> Calculated t_oos threshold: {t_oos:.4f}")
    
    # 3. Generate Out-of-Scope (OOS) Data
    print("  -> Gathering Out-of-Scope (OOS) data...")
    try:
        query_out = """
            WITH trained_chapters AS (
                SELECT DISTINCT SUBSTRING(ahtn8, 1, 2) as ch2
                FROM read_parquet('data/processed/desc_code_counts.parquet')
            )
            SELECT n.desc_norm 
            FROM read_parquet('data/interim/transactions_clean.parquet') t
            JOIN read_parquet('data/interim/norm_descriptions.parquet') n 
              ON t.desc_norm_id = n.desc_norm_id
            WHERE t.ch2 NOT IN (SELECT ch2 FROM trained_chapters)
            LIMIT 20000
        """
        df_unchosen = con.execute(query_out).df()
        unchosen_texts = df_unchosen['desc_norm'].tolist()
        
        # Fallback if transactions_clean doesn't have 20,000 OOS rows
        if len(unchosen_texts) < 20000:
            print(f"     (Note: Only found {len(unchosen_texts)} unchosen chapter rows in clean data.)")
            
    except Exception as e:
        print(f"     (Warning: Could not fetch from transactions_clean. Error: {e})")
        unchosen_texts = ["synthetic unchosen item " + str(i) for i in range(20000)]
        
    gibberish_texts = generate_gibberish(200)
    extreme_texts = generate_extreme(100)
    
    oos_records = []
    
    def evaluate_oos(texts, category):
        if not texts: return
        X_oos = extractor.transform(texts)
        # Slice X_oos using the same active_cols
        probs = root_model.predict_proba(X_oos[:, active_cols]).max(axis=1)
        
        # Count how many junk items snuck past the bouncer (prob >= t_oos)
        passed = sum(1 for p in probs if p >= t_oos)
        leakage_rate = passed / len(probs)
        
        oos_records.append({
            'Category': category,
            'Total Tested': len(probs),
            'Passed Threshold (Leaked)': passed,
            'Leakage Rate (%)': round(leakage_rate * 100, 2)
        })
        
    evaluate_oos(unchosen_texts, "Unchosen Chapters")
    evaluate_oos(gibberish_texts, "Gibberish")
    evaluate_oos(extreme_texts, "Extreme Length (Short/Long)")
    
    # 4. Save Results
    df_oos = pd.DataFrame(oos_records)
    out_dir = Path("reports/tables")
    df_oos.to_csv(out_dir / "c7_oos.csv", index=False)
    
    # 5. Safely update params.yaml
    params['t_oos'] = t_oos
    with open("config/params.yaml", "w") as f:
        yaml.dump(params, f, sort_keys=False)
        
    print("\n C7 Complete!")
    print(f"Updated config/params.yaml with t_oos = {t_oos:.4f}")
    print(f"Saved leakage report to: reports/tables/c7_oos.csv")
    print("\n--- OUT-OF-SCOPE LEAKAGE REPORT ---")
    print(df_oos.to_string(index=False))

if __name__ == "__main__":
    run_c7()