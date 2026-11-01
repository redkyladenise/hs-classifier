import duckdb
import pandas as pd
from pathlib import Path

def run_c8_reference_points():
    print("--- Phase 1: Calculating Reference Points & Upper Bounds ---")
    con = duckdb.connect()
    records = []
    
    # 1. Load A9 Ceilings
    print("  -> Loading A9 Ceilings...")
    try:
        df_a9 = pd.read_csv("reports/tables/a9_eligibility_summary.csv")
        for _, row in df_a9.iterrows():
            if pd.notna(row['pct_tx_coverage']):
                records.append({
                    'scenario': row['scenario'],
                    'level': int(row['level']),
                    'metric': 'M1',
                    'reference': 'A9 Ceiling',
                    'value': float(row['pct_tx_coverage']) / 100.0,
                    'coverage': 1.0,
                    'definition': 'Theoretical maximum accuracy based on eligible classes'
                })
    except FileNotFoundError:
        print("     (Warning: a9_eligibility_summary.csv not found. Skipping.)")

    # 2. Define Scenarios with their specific year windows
    scenarios = {
        'unseen': {
            'test_file': 'data/processed/test_unseen.parquet',
            'train_label': 'main',
            'test_years': 'year IN (2023, 2024)',
            'train_years': 'year <= 2022'
        },
        'y1': {
            'test_file': 'data/processed/test_y1.parquet',
            'train_label': 'y1',
            'test_years': 'year = 2024',
            'train_years': 'year <= 2023'
        },
        'y2': {
            'test_file': 'data/processed/test_y2.parquet',
            'train_label': 'main',
            'test_years': 'year = 2025',
            'train_years': 'year <= 2022'
        }
    }

    levels = {2: 2, 4: 4, 6: 6, 8: 8}

    for sc_name, sc_info in scenarios.items():
        print(f"\n  -> Processing scenario: {sc_name}")
        
        for lvl, str_len in levels.items():
            # --- A. Majority-Label Upper Bound (Eligible Only) ---
            query_ub = f"""
                WITH test_ids AS (
                    SELECT group_l1 FROM read_parquet('{sc_info['test_file']}')
                ),
                eligible_codes AS (
                    SELECT DISTINCT SUBSTRING(ahtn8, 1, {str_len}) as code
                    FROM read_parquet('data/processed/train_pairs_{sc_info['train_label']}.parquet')
                    WHERE elig_ch2 = true -- Proxy to ensure it's in the training pool
                ),
                test_truth AS (
                    SELECT 
                        c.group_l1, 
                        SUBSTRING(c.ahtn8, 1, {str_len}) as true_code, 
                        SUM(c.tx_count) as tx_count
                    FROM read_parquet('data/processed/desc_code_counts.parquet') c
                    JOIN test_ids t ON c.group_l1 = t.group_l1
                    WHERE c.{sc_info['test_years']}
                    GROUP BY c.group_l1, true_code
                ),
                eligible_truth AS (
                    SELECT t.group_l1, t.true_code, t.tx_count
                    FROM test_truth t
                    JOIN eligible_codes e ON t.true_code = e.code
                ),
                max_per_desc AS (
                    SELECT group_l1, MAX(tx_count) as max_tx
                    FROM eligible_truth
                    GROUP BY group_l1
                )
                -- FIX: Sum independently instead of joining to avoid duplicating counts on multi-code items
                SELECT 
                    (SELECT SUM(max_tx) FROM max_per_desc) / 
                    (SELECT SUM(tx_count) FROM test_truth) as upper_bound_m1
            """
            
            try:
                ub_val = con.execute(query_ub).fetchone()[0]
                if ub_val is not None:
                    records.append({'scenario': sc_name, 'level': lvl, 'metric': 'M1', 'reference': 'Upper Bound (Eligible)', 'value': float(ub_val), 'coverage': 1.0, 'definition': 'Best possible M1 if predicting max eligible code per desc'})
                    records.append({'scenario': sc_name, 'level': lvl, 'metric': 'M2', 'reference': 'Upper Bound (Eligible)', 'value': 1.0, 'coverage': 1.0, 'definition': 'M2 UB is 100% by definition'})
                    records.append({'scenario': sc_name, 'level': lvl, 'metric': 'M3', 'reference': 'Upper Bound (Eligible)', 'value': 1.0, 'coverage': 1.0, 'definition': 'M3 UB is 100% by definition'})
            except Exception as e:
                print(f"     (Error on UB {sc_name} L{lvl}: {e})")

            # --- B. C3 Baselines (Majority, Exact Match, Fallback A) ---
            query_c3 = f"""
                WITH train_data AS (
                    SELECT 
                        group_l1, 
                        SUBSTRING(ahtn8, 1, {str_len}) as code, 
                        SUM(tx_count) as tx
                    FROM read_parquet('data/processed/desc_code_counts.parquet')
                    WHERE {sc_info['train_years']}
                    GROUP BY group_l1, code
                ),
                majority_overall AS (
                    SELECT code FROM train_data GROUP BY code ORDER BY SUM(tx) DESC LIMIT 1
                ),
                train_exact_maj AS (
                    SELECT group_l1, code FROM (
                        SELECT group_l1, code, ROW_NUMBER() OVER (PARTITION BY group_l1 ORDER BY tx DESC) as rn
                        FROM train_data
                    ) WHERE rn = 1
                ),
                test_ids AS (
                    SELECT group_l1 FROM read_parquet('{sc_info['test_file']}')
                ),
                test_truth AS (
                    SELECT 
                        c.group_l1, 
                        SUBSTRING(c.ahtn8, 1, {str_len}) as true_code, 
                        SUM(c.tx_count) as tx_count
                    FROM read_parquet('data/processed/desc_code_counts.parquet') c
                    JOIN test_ids t ON c.group_l1 = t.group_l1
                    WHERE c.{sc_info['test_years']}
                    GROUP BY c.group_l1, true_code
                ),
                eval AS (
                    SELECT 
                        t.tx_count,
                        t.true_code,
                        e.code as exact_pred,
                        m.code as maj_pred,
                        COALESCE(e.code, m.code) as fallback_a_pred
                    FROM test_truth t
                    CROSS JOIN majority_overall m
                    LEFT JOIN train_exact_maj e ON t.group_l1 = e.group_l1
                )
                SELECT
                    SUM(CASE WHEN true_code = maj_pred THEN tx_count ELSE 0 END) / SUM(tx_count) as maj_acc,
                    SUM(CASE WHEN exact_pred IS NOT NULL THEN tx_count ELSE 0 END) / SUM(tx_count) as exact_cov,
                    SUM(CASE WHEN exact_pred IS NOT NULL AND true_code = exact_pred THEN tx_count ELSE 0 END) / NULLIF(SUM(CASE WHEN exact_pred IS NOT NULL THEN tx_count ELSE 0 END), 0) as exact_acc,
                    SUM(CASE WHEN true_code = fallback_a_pred THEN tx_count ELSE 0 END) / SUM(tx_count) as fa_acc
                FROM eval
            """
            
            try:
                c3_vals = con.execute(query_c3).fetchone()
                if c3_vals:
                    maj_acc, exact_cov, exact_acc, fa_acc = c3_vals
                    
                    records.append({'scenario': sc_name, 'level': lvl, 'metric': 'M1', 'reference': 'Majority Baseline', 'value': float(maj_acc or 0), 'coverage': 1.0, 'definition': 'Always guess most frequent code overall'})

                    if exact_cov is not None:
                        records.append({'scenario': sc_name, 'level': lvl, 'metric': 'M1', 'reference': 'Exact Match', 'value': float(exact_acc or 0), 'coverage': float(exact_cov), 'definition': 'Guess most frequent code for exactly matched text'})

                    records.append({'scenario': sc_name, 'level': lvl, 'metric': 'M1', 'reference': 'Fallback A', 'value': float(fa_acc or 0), 'coverage': 1.0, 'definition': 'Exact Match, fallback to Majority'})
                    records.append({'scenario': sc_name, 'level': lvl, 'metric': 'M1', 'reference': 'Fallback B', 'value': float(fa_acc or 0), 'coverage': 1.0, 'definition': 'Proxy (Mirrors Fallback A)'})
            except Exception as e:
                print(f"     (Error on Baselines {sc_name} L{lvl}: {e})")

    # 3. Save Output
    df_refs = pd.DataFrame(records)
    out_path = Path("reports/tables/c8_reference_points.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_refs.to_csv(out_path, index=False)
    
    print(f"\n Phase 1 Complete! Reference points saved to {out_path}")

if __name__ == "__main__":
    run_c8_reference_points()