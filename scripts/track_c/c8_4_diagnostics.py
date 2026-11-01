import duckdb
import pandas as pd
import numpy as np
from sklearn.metrics import classification_report
from pathlib import Path
import os

def run_c8_4():
    print("--- Phase 4: Workload, Confidence & Error Forensics ---")
    con = duckdb.connect()
    
    out_dir = Path("reports/tables/diagnostics")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    scenarios = {
        'unseen': {'test_years': 'year IN (2023, 2024)', 'band_scenario': 'main'},
        'y1': {'test_years': 'year = 2024', 'band_scenario': 'y1'}
    }
    
    # Load auxiliary data
    bands_path = Path("reports/tables/c6_confidence_bands.csv")
    df_bands = pd.read_csv(bands_path) if bands_path.exists() else pd.DataFrame()
    
    a9b_path = Path("reports/tables/a9b_leakage_probe.csv")
    df_a9b = pd.read_csv(a9b_path) if a9b_path.exists() else pd.DataFrame()

    for sc_name, sc_info in scenarios.items():
        print(f"\n========================================")
        print(f"  SCENARIO: {sc_name.upper()}")
        
        # 1. CORE SCORED DATA (With deterministic ties and missing pred_l8)
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
            p.group_l1, p.pred_1, p.prob_1 as conf_1,
            p.pred_1 as pred_l8,
            l8.code as true_l8, 
            l6.code as true_l6, SUBSTRING(p.pred_1, 1, 6) as pred_l6,
            l4.code as true_l4, SUBSTRING(p.pred_1, 1, 4) as pred_l4,
            l2.code as true_l2, SUBSTRING(p.pred_1, 1, 2) as pred_l2,
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
        
        if df_scored.empty:
            print(f"⚠️ No data found for scenario {sc_name}. Skipping.")
            continue
        
        # ---------------------------------------------------------
        # A. WORKLOAD & CONFIDENCE
        # ---------------------------------------------------------
        if not df_bands.empty:
            print("  -> Generating Workload Tables...")
            workload_rows = []
            band_sc = sc_info['band_scenario']
            df_b = df_bands[df_bands['Scenario'].str.lower() == band_sc.lower()]
            
            for lvl in [2, 4, 6, 8]:
                try:
                    thresh = df_b[df_b['Level'] == lvl]['Med Limit'].values[0]
                    col_corr = f'is_corr_l{lvl}'
                    
                    accepted = df_scored[df_scored['conf_1'] >= thresh]
                    rejected = df_scored[df_scored['conf_1'] < thresh]
                    
                    workload_rows.append({
                        'Scenario': sc_name, 'Level': lvl, 'Med_Threshold': thresh,
                        'Total_Items': len(df_scored),
                        'Accepted_Auto': len(accepted),
                        'Accepted_Coverage_Pct': len(accepted) / len(df_scored) if len(df_scored) > 0 else 0,
                        'Accepted_Accuracy': accepted[col_corr].mean() if len(accepted)>0 else 0,
                        'Routed_to_Human': len(rejected),
                        'Human_Routing_Pct': len(rejected) / len(df_scored) if len(df_scored) > 0 else 0
                    })
                except IndexError:
                    pass
                    
            if workload_rows:
                pd.DataFrame(workload_rows).to_csv(out_dir / f"workload_{sc_name}.csv", index=False)

        # ---------------------------------------------------------
        # B. ERROR FORENSICS (Confusion Matrices & Tables)
        # ---------------------------------------------------------
        print("  -> Generating Confusion Matrices...")
        # B1: Chapter 5x5 Matrix (Leakage-Proof)
        top_5_chaps = df_scored['true_l2'].value_counts().nlargest(5).index
        df_top5 = df_scored[df_scored['true_l2'].isin(top_5_chaps)].copy()
        
        # Map any predicted chapters outside the top 5 to 'Other' to preserve row totals
        df_top5['pred_l2_mapped'] = df_top5['pred_l2'].apply(lambda x: x if x in top_5_chaps else 'Other')
        
        cm_ch2 = pd.crosstab(df_top5['true_l2'], df_top5['pred_l2_mapped'])
        cm_ch2_norm = pd.crosstab(df_top5['true_l2'], df_top5['pred_l2_mapped'], normalize='index')
        cm_ch2.to_csv(out_dir / f"cm_chapter_counts_{sc_name}.csv")
        cm_ch2_norm.to_csv(out_dir / f"cm_chapter_norm_{sc_name}.csv")
        
        # B2: Top 15 Headings Matrices (Per Top-5 Chapter)
        for ch in top_5_chaps:
            df_ch = df_scored[df_scored['true_l2'] == ch].copy()
            top_15_hd = df_ch['true_l4'].value_counts().nlargest(15).index
            df_ch['pred_l4_mapped'] = df_ch['pred_l4'].apply(lambda x: x if x in top_15_hd else 'Other')
            
            df_hd_filtered = df_ch[df_ch['true_l4'].isin(top_15_hd)]
            cm_hd = pd.crosstab(df_hd_filtered['true_l4'], df_hd_filtered['pred_l4_mapped'])
            cm_hd.to_csv(out_dir / f"cm_headings_ch{ch}_{sc_name}.csv")
            
        # B3: Top 20 Confusion Tables for L6 and L8
        for lvl in [6, 8]:
            err_df = df_scored[df_scored[f'true_l{lvl}'] != df_scored[f'pred_l{lvl}']]
            top_errors = err_df.groupby([f'true_l{lvl}', f'pred_l{lvl}']).size().reset_index(name='count')
            top_errors = top_errors.sort_values('count', ascending=False).head(20)
            top_errors.to_csv(out_dir / f"top20_confusions_l{lvl}_{sc_name}.csv", index=False)

        # ---------------------------------------------------------
        # C. SIBLING ERRORS
        # ---------------------------------------------------------
        print("  -> Calculating Sibling Errors...")
        l8_errors = df_scored[df_scored['is_corr_l8'] == 0]
        if len(l8_errors) > 0:
            sibling_errors = l8_errors[l8_errors['is_corr_l6'] == 1]
            sib_share = len(sibling_errors) / len(l8_errors)
            pd.DataFrame([{'Scenario': sc_name, 'L8_Errors': len(l8_errors), 'Sibling_Errors': len(sibling_errors), 'Sibling_Share': sib_share}]).to_csv(out_dir / f"sibling_errors_{sc_name}.csv", index=False)

        # ---------------------------------------------------------
        # D. PER-CLASS F1 & WEAKEST 20
        # ---------------------------------------------------------
        print("  -> Generating Per-Class Performance...")
        cls_report = classification_report(df_scored['true_l8'], df_scored['pred_l8'], output_dict=True, zero_division=0)
        df_cls = pd.DataFrame(cls_report).T
        df_cls = df_cls[~df_cls.index.isin(['accuracy', 'macro avg', 'weighted avg'])]
        df_cls.index.name = 'HS_Code'
        df_cls.reset_index(inplace=True)
        
        df_cls.sort_values('support', ascending=False).to_csv(out_dir / f"per_class_all_{sc_name}.csv", index=False)
        
        weakest_20 = df_cls[df_cls['support'] >= 50].sort_values('f1-score', ascending=True).head(20)
        weakest_20.to_csv(out_dir / f"weakest_20_classes_{sc_name}.csv", index=False)

        # ---------------------------------------------------------
        # E. ROBUSTNESS (A9b Near-Twin Sensitivity)
        # ---------------------------------------------------------
        if not df_a9b.empty and sc_name == 'unseen':
            print("  -> Evaluating A9b Leakage Probe Sensitivity...")
            try:
                # Deduplicate A9b on group_l1 to prevent row explosion
                df_a9b_unique = df_a9b.drop_duplicates(subset=['group_l1'])
                
                sim_col = [c for c in df_a9b_unique.columns if 'sim' in c.lower() or 'leak' in c.lower()][0]
                df_merged = df_scored.merge(df_a9b_unique[['group_l1', sim_col]], on='group_l1', how='inner')
                
                is_twin = df_merged[sim_col] >= 0.95 if df_merged[sim_col].dtype in [np.float64, np.float32] else df_merged[sim_col] == 1
                
                df_twins = df_merged[is_twin]
                df_clean = df_merged[~is_twin]
                
                rob_report = [{
                    'Category': 'Clean (< 0.95 Sim)',
                    'Desc_Count': len(df_clean),
                    'Accuracy': df_clean['is_corr_l8'].mean() if len(df_clean) > 0 else 0
                }, {
                    'Category': 'Near-Twin (>= 0.95 Sim)',
                    'Desc_Count': len(df_twins),
                    'Accuracy': df_twins['is_corr_l8'].mean() if len(df_twins) > 0 else 0
                }]
                pd.DataFrame(rob_report).to_csv(out_dir / f"a9b_twin_sensitivity_{sc_name}.csv", index=False)
            except Exception as e:
                print(f" A9b Sensitivity processing skipped. Column matching error: {e}")

    print(f"\n Phase 4 Complete! All forensic files saved to {out_dir}/")

if __name__ == "__main__":
    run_c8_4()