import duckdb
import pandas as pd
from pathlib import Path

def run_c8_3b():
    print("--- Phase 3B: Hierarchical First-Errors & Line Types ---")
    con = duckdb.connect()
    
    scenarios = {
        'unseen': {'test_years': 'year IN (2023, 2024)'},
        'y1': {'test_years': 'year = 2024'},
        'y2': {'test_years': 'year = 2025'}
    }
    
    error_reports = []
    line_reports = []
    
    for sc_name, sc_info in scenarios.items():
        print(f"\nProcessing Scenario: {sc_name.upper()}")
        
        # ---------------------------------------------------------
        # 1. HIERARCHICAL FIRST-ERROR ANALYSIS
        # ---------------------------------------------------------
        query_errors = f"""
        WITH truth_base AS (
            SELECT group_l1, ahtn8, SUBSTRING(ahtn8, 1, 6) as sh6, SUBSTRING(ahtn8, 1, 4) as hd4, SUBSTRING(ahtn8, 1, 2) as ch2, SUM(tx_count) as tx_count
            FROM read_parquet('data/processed/desc_code_counts.parquet')
            WHERE {sc_info['test_years']}
            GROUP BY group_l1, ahtn8
        ),
        l8_maj AS (SELECT group_l1, ahtn8 as code FROM truth_base QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx_count DESC) = 1),
        l6_maj AS (SELECT group_l1, sh6 as code, SUM(tx_count) as tx FROM truth_base GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC) = 1),
        l4_maj AS (SELECT group_l1, hd4 as code, SUM(tx_count) as tx FROM truth_base GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC) = 1),
        l2_maj AS (SELECT group_l1, ch2 as code, SUM(tx_count) as tx FROM truth_base GROUP BY 1, 2 QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx DESC) = 1),
        
        scored AS (
            SELECT 
                CASE 
                    WHEN SUBSTRING(p.pred_1, 1, 2) != l2.code THEN '1_L2_Chapter_Error'
                    WHEN SUBSTRING(p.pred_1, 1, 4) != l4.code THEN '2_L4_Heading_Error'
                    WHEN SUBSTRING(p.pred_1, 1, 6) != l6.code THEN '3_L6_Subheading_Error'
                    WHEN p.pred_1 != l8.code THEN '4_L8_Line_Error'
                    ELSE '5_Correct'
                END as first_error_level
            FROM read_parquet('data/processed/predictions_{sc_name}/*.parquet') p
            JOIN l8_maj l8 ON p.group_l1 = l8.group_l1
            JOIN l6_maj l6 ON p.group_l1 = l6.group_l1
            JOIN l4_maj l4 ON p.group_l1 = l4.group_l1
            JOIN l2_maj l2 ON p.group_l1 = l2.group_l1
        )
        SELECT 
            first_error_level, 
            COUNT(*) as desc_count
        FROM scored
        GROUP BY first_error_level
        ORDER BY first_error_level
        """
        
        df_err = con.execute(query_errors).df()
        df_err['scenario'] = sc_name
        df_err['share_of_total'] = df_err['desc_count'] / df_err['desc_count'].sum()
        error_reports.append(df_err)
        
        # Calculate specific roadmap metric: "Correct at L6 but wrong at L8" share
        total_errors = df_err[df_err['first_error_level'] != '5_Correct']['desc_count'].sum()
        l8_only_errors = df_err[df_err['first_error_level'] == '4_L8_Line_Error']['desc_count'].sum()
        l8_error_share = l8_only_errors / total_errors if total_errors > 0 else 0
        print(f"  -> Share of errors where L6 was correct but L8 failed: {l8_error_share:.1%}")

        # ---------------------------------------------------------
        # 2. LINE TYPES (Single vs Split Subheadings)
        # ---------------------------------------------------------
        query_lines = f"""
        WITH global_sh6_counts AS (
            -- Determine if a 6-digit code has 1 or multiple 8-digit codes historically
            SELECT SUBSTRING(ahtn8, 1, 6) as sh6, COUNT(DISTINCT ahtn8) as l8_count
            FROM read_parquet('data/processed/desc_code_counts.parquet')
            GROUP BY 1
        ),
        truth_base AS (
            SELECT group_l1, ahtn8, SUBSTRING(ahtn8, 1, 6) as sh6, SUM(tx_count) as tx_count
            FROM read_parquet('data/processed/desc_code_counts.parquet')
            WHERE {sc_info['test_years']}
            GROUP BY group_l1, ahtn8
        ),
        l8_maj AS (SELECT group_l1, ahtn8 as code, sh6 FROM truth_base QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx_count DESC) = 1),
        
        scored AS (
            SELECT 
                CASE WHEN g.l8_count = 1 THEN 'Single_Line' ELSE 'Split_Subheading' END as line_type,
                CASE WHEN p.pred_1 = l8.code THEN 1 ELSE 0 END as is_correct
            FROM read_parquet('data/processed/predictions_{sc_name}/*.parquet') p
            JOIN l8_maj l8 ON p.group_l1 = l8.group_l1
            JOIN global_sh6_counts g ON l8.sh6 = g.sh6
        )
        SELECT 
            line_type, 
            COUNT(*) as desc_count, 
            SUM(is_correct) as correct_count, 
            SUM(is_correct)*1.0 / COUNT(*) as accuracy_m2
        FROM scored
        GROUP BY line_type
        ORDER BY line_type
        """
        
        df_lines = con.execute(query_lines).df()
        df_lines['scenario'] = sc_name
        line_reports.append(df_lines)
        
        single_acc = df_lines[df_lines['line_type'] == 'Single_Line']['accuracy_m2'].values[0]
        split_acc = df_lines[df_lines['line_type'] == 'Split_Subheading']['accuracy_m2'].values[0]
        print(f"  -> Single-Line Accuracy: {single_acc:.1%} | Split Accuracy: {split_acc:.1%}")

    # Combine and save reports
    out_dir = Path("reports/tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    pd.concat(error_reports).to_csv(out_dir / "c8_hierarchical_errors.csv", index=False)
    pd.concat(line_reports).to_csv(out_dir / "c8_line_types.csv", index=False)
    print(f"\n Phase 3B Complete! Breakdowns saved to reports/tables/")

if __name__ == "__main__":
    run_c8_3b()