import duckdb
import pandas as pd
from pathlib import Path

def patch_workload():
    print("--- Patching Workload Tables ---")
    con = duckdb.connect()
    out_dir = Path("reports/tables/diagnostics")
    
    bands_path = Path("reports/tables/c6_confidence_bands.csv")
    df_bands = pd.read_csv(bands_path)
    
    scenarios = {
        'unseen': {'test_years': 'year IN (2023, 2024)', 'band_scenario': 'main'},
        'y1': {'test_years': 'year = 2024', 'band_scenario': 'y1'}
    }
    
    for sc_name, sc_info in scenarios.items():
        print(f"Processing Workload for {sc_name.upper()}...")
        
        query_core = f"""
        WITH truth_base AS (
            SELECT group_l1, ahtn8, SUBSTRING(ahtn8, 1, 6) as sh6, SUBSTRING(ahtn8, 1, 4) as hd4, SUBSTRING(ahtn8, 1, 2) as ch2, SUM(tx_count) as tx_count
            FROM read_parquet('data/processed/desc_code_counts.parquet')
            WHERE {sc_info['test_years']}
            GROUP BY group_l1, ahtn8
        ),
        l8_maj AS (SELECT group_l1, ahtn8 as code FROM truth_base QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx_count DESC, ahtn8 ASC) = 1),
        l6_maj AS (SELECT group_l1, sh6 as code, SUM(tx_count) as tx FROM truth_base GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC, sh6 ASC) = 1),
        l4_maj AS (SELECT group_l1, hd4 as code, SUM(tx_count) as tx FROM truth_base GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC, hd4 ASC) = 1),
        l2_maj AS (SELECT group_l1, ch2 as code, SUM(tx_count) as tx FROM truth_base GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC, ch2 ASC) = 1)
        
        SELECT 
            p.prob_1 as conf_1,
            CASE WHEN p.pred_1 = l8.code THEN 1 ELSE 0 END as is_corr_l8,
            CASE WHEN SUBSTRING(p.pred_1, 1, 6) = l6.code THEN 1 ELSE 0 END as is_corr_l6,
            CASE WHEN SUBSTRING(p.pred_1, 1, 4) = l4.code THEN 1 ELSE 0 END as is_corr_l4,
            CASE WHEN SUBSTRING(p.pred_1, 1, 2) = l2.code THEN 1 ELSE 0 END as is_corr_l2
        FROM read_parquet('data/processed/predictions_{sc_name}/*.parquet') p
        JOIN l8_maj l8 ON p.group_l1 = l8.group_l1
        JOIN l6_maj l6 ON p.group_l1 = l6.group_l1
        JOIN l4_maj l4 ON p.group_l1 = l4.group_l1
        JOIN l2_maj l2 ON p.group_l1 = l2.group_l1
        WHERE l8.code IS NOT NULL
        """
        df_scored = con.execute(query_core).df()
        
        workload_rows = []
        band_sc = sc_info['band_scenario']
        df_b = df_bands[df_bands['Scenario'].str.lower() == band_sc.lower()]
        
        for lvl in [2, 4, 6, 8]:
            # The Fix: Look for exactly "Level X" to match your CSV
            level_string = f"Level {lvl}"
            
            try:
                thresh = df_b[df_b['Level'] == level_string]['Med Limit'].values[0]
                col_corr = f'is_corr_l{lvl}'
                
                accepted = df_scored[df_scored['conf_1'] >= thresh]
                rejected = df_scored[df_scored['conf_1'] < thresh]
                
                workload_rows.append({
                    'Scenario': sc_name, 
                    'Level': lvl, 
                    'Med_Threshold': thresh,
                    'Total_Items': len(df_scored),
                    'Accepted_Auto': len(accepted),
                    'Accepted_Coverage_Pct': len(accepted) / len(df_scored) if len(df_scored) > 0 else 0,
                    'Accepted_Accuracy': accepted[col_corr].mean() if len(accepted)>0 else 0,
                    'Routed_to_Human': len(rejected),
                    'Human_Routing_Pct': len(rejected) / len(df_scored) if len(df_scored) > 0 else 0
                })
            except IndexError:
                print(f" Could not find Med Limit for {level_string} in scenario {band_sc}")
                
        if workload_rows:
            pd.DataFrame(workload_rows).to_csv(out_dir / f"workload_{sc_name}.csv", index=False)
            print(f" Saved workload_{sc_name}.csv")

if __name__ == "__main__":
    patch_workload()