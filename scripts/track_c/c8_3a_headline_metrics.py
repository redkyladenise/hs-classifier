import duckdb
import pandas as pd
import numpy as np
from sklearn.metrics import f1_score, precision_score, recall_score, cohen_kappa_score
from pathlib import Path

def run_c8_3a_headline_metrics():
    print("--- Phase 3A: Headline Metrics & Bootstrapping ---")
    
    con = duckdb.connect()
    
    # Load baselines for Attainment and Lift calculations
    df_refs = pd.read_csv("reports/tables/c8_reference_points.csv")
    
    scenarios = {
        'unseen': {'test_years': 'year IN (2023, 2024)'},
        'y1': {'test_years': 'year = 2024'},
        'y2': {'test_years': 'year = 2025'}
    }
    
    reports = []
    
    for sc_name, sc_info in scenarios.items():
        print(f"\n========================================")
        print(f"  SCENARIO: {sc_name.upper()}")
        
# 1. BUILD THE SCORECARD
        query_scorecard = f"""
        WITH truth_base AS (
            SELECT 
                group_l1,
                ahtn8,
                SUBSTRING(ahtn8, 1, 6) as sh6,
                SUBSTRING(ahtn8, 1, 4) as hd4,
                SUBSTRING(ahtn8, 1, 2) as ch2,
                SUM(tx_count) as tx_count
            FROM read_parquet('data/processed/desc_code_counts.parquet')
            WHERE {sc_info['test_years']}
            GROUP BY group_l1, ahtn8
        ),
        -- Hierarchically Correct Majority Calculations
        l8_maj AS (SELECT group_l1, ahtn8 as code FROM truth_base QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx_count DESC) = 1),
        l6_maj AS (SELECT group_l1, sh6 as code, SUM(tx_count) as tx FROM truth_base GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC) = 1),
        l4_maj AS (SELECT group_l1, hd4 as code, SUM(tx_count) as tx FROM truth_base GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC) = 1),
        l2_maj AS (SELECT group_l1, ch2 as code, SUM(tx_count) as tx FROM truth_base GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC) = 1),
        
        valid_lists AS (
            SELECT 
                group_l1,
                SUM(tx_count) as total_tx,
                LIST(DISTINCT ahtn8) as valid_l8,
                LIST(DISTINCT sh6) as valid_l6,
                LIST(DISTINCT hd4) as valid_l4,
                LIST(DISTINCT ch2) as valid_l2
            FROM truth_base
            GROUP BY group_l1
        ),
        
        predictions AS (
            SELECT * FROM read_parquet('data/processed/predictions_{sc_name}/*.parquet')
        ),
        
        scored AS (
            SELECT 
                ds.group_l2,
                COALESCE(vl.total_tx, 0) as total_tx,
                
                -- M1 Logic (Transaction Weighted)
                (SELECT COALESCE(SUM(tb.tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1 AND tb.ahtn8 = p.pred_1) as m1_l8_tx,
                (SELECT COALESCE(SUM(tb.tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1 AND tb.sh6 = SUBSTRING(p.pred_1, 1, 6)) as m1_l6_tx,
                (SELECT COALESCE(SUM(tb.tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1 AND tb.hd4 = SUBSTRING(p.pred_1, 1, 4)) as m1_l4_tx,
                (SELECT COALESCE(SUM(tb.tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1 AND tb.ch2 = SUBSTRING(p.pred_1, 1, 2)) as m1_l2_tx,
                
                -- M1 Logic Top-5 (Transaction Weighted)
                (SELECT COALESCE(SUM(tb.tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1 AND tb.ahtn8 IN (p.pred_1, p.pred_2, p.pred_3, p.pred_4, p.pred_5)) as m1_top5_l8_tx,
                (SELECT COALESCE(SUM(tb.tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1 AND tb.sh6 IN (SUBSTRING(p.pred_1,1,6), SUBSTRING(p.pred_2,1,6), SUBSTRING(p.pred_3,1,6), SUBSTRING(p.pred_4,1,6), SUBSTRING(p.pred_5,1,6))) as m1_top5_l6_tx,
                (SELECT COALESCE(SUM(tb.tx_count), 0) FROM truth_base tb WHERE tb.group_l1 = p.group_l1 AND tb.hd4 IN (SUBSTRING(p.pred_1,1,4), SUBSTRING(p.pred_2,1,4), SUBSTRING(p.pred_3,1,4), SUBSTRING(p.pred_4,1,4), SUBSTRING(p.pred_5,1,4))) as m1_top5_l4_tx,

                -- M2 Logic (Description Weighted Majority)
                CASE WHEN p.pred_1 = l8.code THEN 1 ELSE 0 END as m2_l8,
                CASE WHEN SUBSTRING(p.pred_1, 1, 6) = l6.code THEN 1 ELSE 0 END as m2_l6,
                CASE WHEN SUBSTRING(p.pred_1, 1, 4) = l4.code THEN 1 ELSE 0 END as m2_l4,
                CASE WHEN SUBSTRING(p.pred_1, 1, 2) = l2.code THEN 1 ELSE 0 END as m2_l2,
                
                -- M3 Logic (Description Weighted Any Valid)
                CASE WHEN list_contains(vl.valid_l8, p.pred_1) THEN 1 ELSE 0 END as m3_l8,
                CASE WHEN list_contains(vl.valid_l6, SUBSTRING(p.pred_1, 1, 6)) THEN 1 ELSE 0 END as m3_l6,
                CASE WHEN list_contains(vl.valid_l4, SUBSTRING(p.pred_1, 1, 4)) THEN 1 ELSE 0 END as m3_l4,
                CASE WHEN list_contains(vl.valid_l2, SUBSTRING(p.pred_1, 1, 2)) THEN 1 ELSE 0 END as m3_l2,
                
                l8.code as true_l8, p.pred_1 as pred_l8,
                l4.code as true_l4, SUBSTRING(p.pred_1, 1, 4) as pred_l4,
                l2.code as true_l2, SUBSTRING(p.pred_1, 1, 2) as pred_l2
                
            FROM predictions p
            LEFT JOIN read_parquet('data/processed/description_status.parquet') ds ON p.group_l1 = ds.group_l1
            LEFT JOIN valid_lists vl ON p.group_l1 = vl.group_l1
            LEFT JOIN l8_maj l8 ON p.group_l1 = l8.group_l1
            LEFT JOIN l6_maj l6 ON p.group_l1 = l6.group_l1
            LEFT JOIN l4_maj l4 ON p.group_l1 = l4.group_l1
            LEFT JOIN l2_maj l2 ON p.group_l1 = l2.group_l1
        )
        SELECT 
            group_l2,
            COUNT(*) as desc_count,
            SUM(total_tx) as total_tx,
            
            SUM(m1_l8_tx) as m1_l8_sum, SUM(m1_l6_tx) as m1_l6_sum, SUM(m1_l4_tx) as m1_l4_sum, SUM(m1_l2_tx) as m1_l2_sum,
            SUM(m2_l8) as m2_l8_sum, SUM(m2_l6) as m2_l6_sum, SUM(m2_l4) as m2_l4_sum, SUM(m2_l2) as m2_l2_sum,
            SUM(m3_l8) as m3_l8_sum, SUM(m3_l6) as m3_l6_sum, SUM(m3_l4) as m3_l4_sum, SUM(m3_l2) as m3_l2_sum,
            
            SUM(m1_top5_l8_tx) as m1_top5_l8_sum, SUM(m1_top5_l6_tx) as m1_top5_l6_sum, SUM(m1_top5_l4_tx) as m1_top5_l4_sum
        FROM scored
        GROUP BY group_l2
        """
        
        df_scorecard = con.execute(query_scorecard).df()
        
        # 2. 200-RESAMPLE CLUSTER BOOTSTRAP
        n_resamples = 200
        n_clusters = len(df_scorecard)
        
        metrics = [
            'm1_l8', 'm1_l6', 'm1_l4', 'm1_l2',
            'm2_l8', 'm2_l6', 'm2_l4', 'm2_l2',
            'm3_l8', 'm3_l6', 'm3_l4', 'm3_l2',
            'm1_top5_l8', 'm1_top5_l6', 'm1_top5_l4'
        ]
        boot_results = {m: [] for m in metrics}
        
        arr_totals = df_scorecard['total_tx'].values
        arr_desc = df_scorecard['desc_count'].values
        sum_arrays = {m: df_scorecard[f'{m}_sum'].values for m in metrics}

        np.random.seed(42)
        for _ in range(n_resamples):
            idx = np.random.randint(0, n_clusters, size=n_clusters)
            sum_tx = np.sum(arr_totals[idx])
            sum_d = np.sum(arr_desc[idx])
            
            for m in metrics:
                denom = sum_tx if m.startswith('m1') else sum_d
                num = np.sum(sum_arrays[m][idx])
                boot_results[m].append(num / denom if denom > 0 else 0)
                
        # Calculate CIs
        for m in metrics:
            reports.append({
                'scenario': sc_name, 'metric': m,
                'mean': np.mean(boot_results[m]),
                'ci_lower': np.percentile(boot_results[m], 2.5),
                'ci_upper': np.percentile(boot_results[m], 97.5)
            })

        # 3. SKLEARN METRICS (Macro-F1, Kappa)
        print("  -> Calculating Scikit-Learn Metrics (No Bootstrap)...")
        query_raw = f"""
        WITH truth_base AS (
            SELECT group_l1, ahtn8, SUBSTRING(ahtn8, 1, 4) as hd4, SUBSTRING(ahtn8, 1, 2) as ch2, SUM(tx_count) as tx_count
            FROM read_parquet('data/processed/desc_code_counts.parquet')
            WHERE {sc_info['test_years']}
            GROUP BY group_l1, ahtn8
        ),
        l8_maj AS (SELECT group_l1, ahtn8 as code FROM truth_base QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx_count DESC) = 1),
        l4_maj AS (SELECT group_l1, hd4 as code, SUM(tx_count) as tx FROM truth_base GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC) = 1),
        l2_maj AS (SELECT group_l1, ch2 as code, SUM(tx_count) as tx FROM truth_base GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC) = 1)
        
        SELECT 
            l8.code as true_l8, p.pred_1 as pred_l8,
            l4.code as true_l4, SUBSTRING(p.pred_1, 1, 4) as pred_l4,
            l2.code as true_l2, SUBSTRING(p.pred_1, 1, 2) as pred_l2
        FROM read_parquet('data/processed/predictions_{sc_name}/*.parquet') p
        JOIN l8_maj l8 ON p.group_l1 = l8.group_l1
        JOIN l4_maj l4 ON p.group_l1 = l4.group_l1
        JOIN l2_maj l2 ON p.group_l1 = l2.group_l1
        WHERE l8.code IS NOT NULL
        """
        df_raw = con.execute(query_raw).df()
        
        reports.append({'scenario': sc_name, 'metric': 'macro_f1', 'mean': f1_score(df_raw['true_l8'], df_raw['pred_l8'], average='macro', zero_division=0), 'ci_lower': None, 'ci_upper': None})
        reports.append({'scenario': sc_name, 'metric': 'kappa_l2', 'mean': cohen_kappa_score(df_raw['true_l2'], df_raw['pred_l2']), 'ci_lower': None, 'ci_upper': None})
        reports.append({'scenario': sc_name, 'metric': 'kappa_l4', 'mean': cohen_kappa_score(df_raw['true_l4'], df_raw['pred_l4']), 'ci_lower': None, 'ci_upper': None})

        # 4. ATTAINMENT & LIFT
        m1_l8_mean = np.mean(boot_results['m1_l8'])
        refs_sc = df_refs[(df_refs['scenario'] == sc_name) & (df_refs['level'] == 8) & (df_refs['metric'] == 'M1')]
        
        ub = refs_sc[refs_sc['reference'] == 'Upper Bound (Eligible)']['value'].values
        maj = refs_sc[refs_sc['reference'] == 'Majority Baseline']['value'].values
        
        if len(ub) > 0 and ub[0] > 0:
            reports.append({'scenario': sc_name, 'metric': 'attainment_m1_l8', 'mean': m1_l8_mean / ub[0], 'ci_lower': None, 'ci_upper': None})
        if len(maj) > 0:
            reports.append({'scenario': sc_name, 'metric': 'lift_vs_majority_m1_l8', 'mean': m1_l8_mean - maj[0], 'ci_lower': None, 'ci_upper': None})

    df_report = pd.DataFrame(reports)
    out_path = Path("reports/tables/c8_headline_metrics.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_report.to_csv(out_path, index=False)
    print(f"\n Phase 3A Complete! Core metrics saved to {out_path}")

if __name__ == "__main__":
    run_c8_3a_headline_metrics()