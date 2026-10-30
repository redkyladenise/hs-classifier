import duckdb
import pandas as pd
from pathlib import Path

def generate_baseline_report(scenario='main'):
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='0.75GB'")
    
    # Make sure the reports folder exists
    report_dir = Path("reports/tables")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    print("Calculating Exact Match and Fallback Baselines...")
    
    # 1. Fallback A: The single most popular code overall
    query_fa = """
        SELECT ahtn8 FROM read_parquet('data/processed/desc_code_counts.parquet')
        GROUP BY ahtn8 ORDER BY sum(tx_count) DESC LIMIT 1
    """
    fallback_a_code = con.execute(query_fa).fetchone()[0]
    
    # 2. Get the true answers for the Validation Tuning set
    query_val = f"""
        WITH true_labels AS (
            SELECT group_l1, ahtn8, SUBSTRING(ahtn8, 1, 2) as true_ch2,
                   ROW_NUMBER() OVER (PARTITION BY group_l1 ORDER BY tx_count DESC) as rn
            FROM read_parquet('data/processed/desc_code_counts.parquet')
        )
        SELECT v.group_l1, t.ahtn8, t.true_ch2
        FROM read_parquet('data/processed/val_tune_{scenario}.parquet') v
        JOIN true_labels t ON v.group_l1 = t.group_l1
        WHERE t.rn = 1
    """
    val_data = con.execute(query_val).fetchdf()
    total_val = len(val_data)
    
    # 3. Exact Match: Does the exact text exist in training? What was its top code?
    query_exact = """
        SELECT group_l1, ahtn8 as exact_guess
        FROM (
            SELECT group_l1, ahtn8,
                   ROW_NUMBER() OVER (PARTITION BY group_l1 ORDER BY tx_count DESC) as rn
            FROM read_parquet('data/processed/desc_code_counts.parquet')
        ) WHERE rn = 1
    """
    exact_data = con.execute(query_exact).fetchdf()
    
    # 4. Fallback B: Most popular code per Chapter
    query_fb = """
        SELECT SUBSTRING(ahtn8, 1, 2) as ch2, ahtn8 as fb_guess
        FROM (
            SELECT SUBSTRING(ahtn8, 1, 2) as ch2, ahtn8,
                   ROW_NUMBER() OVER (PARTITION BY SUBSTRING(ahtn8, 1, 2) ORDER BY sum(tx_count) DESC) as rn
            FROM read_parquet('data/processed/desc_code_counts.parquet')
            GROUP BY ch2, ahtn8
        ) WHERE rn = 1
    """
    fb_data = con.execute(query_fb).fetchdf()
    
    # Combine and Grade
    merged = val_data.merge(exact_data, on='group_l1', how='left')
    merged = merged.merge(fb_data, left_on='true_ch2', right_on='ch2', how='left')
    
    # Grade Exact Match
    exact_correct = (merged['ahtn8'] == merged['exact_guess']).sum()
    exact_acc = (exact_correct / total_val) * 100
    
    # Grade Fallback A (Guess the same thing for everything)
    fa_correct = (merged['ahtn8'] == fallback_a_code).sum()
    fa_acc = (fa_correct / total_val) * 100
    
    # Grade Fallback B (Guess the most popular code in the true chapter)
    fb_correct = (merged['ahtn8'] == merged['fb_guess']).sum()
    fb_acc = (fb_correct / total_val) * 100
    
    # 5. Save the Report
    results = [
        {"Model": "Fallback A (Blind Guess)", "Accuracy_Percent": round(fa_acc, 2)},
        {"Model": "Fallback B (Cheat Chapter)", "Accuracy_Percent": round(fb_acc, 2)},
        {"Model": "Exact Match (Dictionary)", "Accuracy_Percent": round(exact_acc, 2)},
        {"Model": "Flat Logistic Regression", "Accuracy_Percent": 18.60} # Hardcoded from our previous run
    ]
    
    df_report = pd.DataFrame(results)
    out_path = report_dir / f"c3_baselines_{scenario}.csv"
    df_report.to_csv(out_path, index=False)
    
    print(f"Report successfully saved to {out_path}!")
    print(df_report)

if __name__ == "__main__":
    generate_baseline_report('main')