import duckdb
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import matplotlib.ticker as mtick

def run_tradeoff():
    print("--- Generating Risk-Coverage Tradeoff Curve ---")
    con = duckdb.connect()
    
    out_dir = Path("reports/tables/diagnostics")
    fig_dir = Path("reports/figures")
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    query = """
    WITH truth_base AS (
        SELECT group_l1, ahtn8, SUBSTRING(ahtn8, 1, 6) as sh6, SUBSTRING(ahtn8, 1, 4) as hd4, SUBSTRING(ahtn8, 1, 2) as ch2, SUM(tx_count) as tx_count
        FROM read_parquet('data/processed/desc_code_counts.parquet')
        WHERE year IN (2023, 2024)
        GROUP BY group_l1, ahtn8
    ),
    l8_maj AS (SELECT group_l1, ahtn8 as code FROM truth_base QUALIFY ROW_NUMBER() OVER(PARTITION BY group_l1 ORDER BY tx_count DESC, ahtn8 ASC) = 1)
    
    SELECT 
        p.prob_1 as conf_1,
        CASE WHEN p.pred_1 = l8.code THEN 1 ELSE 0 END as is_corr_l8
    FROM read_parquet('data/processed/predictions_unseen/*.parquet') p
    JOIN l8_maj l8 ON p.group_l1 = l8.group_l1
    WHERE l8.code IS NOT NULL
    """
    
    df = con.execute(query).df()
    total_items = len(df)
    
    thresholds = np.arange(0.10, 1.00, 0.05)
    results = []
    
    for t in thresholds:
        accepted = df[df['conf_1'] >= t]
        if len(accepted) > 0:
            coverage = len(accepted) / total_items
            accuracy = accepted['is_corr_l8'].mean()
            results.append({'Threshold': t, 'Coverage': coverage, 'Accuracy': accuracy})
            
    df_curve = pd.DataFrame(results)
    df_curve.to_csv(out_dir / "accuracy_coverage_tradeoff.csv", index=False)
    
    # Plotting the Curve
    sns.set_theme(style="whitegrid")
    fig, ax1 = plt.subplots(figsize=(8, 5))
    
    color1 = 'tab:blue'
    ax1.set_xlabel('Confidence Threshold')
    ax1.set_ylabel('Coverage (Automation %)', color=color1)
    ax1.plot(df_curve['Threshold'], df_curve['Coverage'], color=color1, marker='o', linewidth=2)
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    
    ax2 = ax1.twinx()
    color2 = 'tab:green'
    ax2.set_ylabel('Accuracy of Automated Items', color=color2)
    ax2.plot(df_curve['Threshold'], df_curve['Accuracy'], color=color2, marker='s', linewidth=2)
    ax2.tick_params(axis='y', labelcolor=color2)
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    
    plt.title('Accuracy vs. Coverage Tradeoff (Level 8)', fontsize=14)
    fig.tight_layout()
    plt.savefig(fig_dir / "fig4_risk_coverage_curve.png", dpi=300)
    plt.close()
    
    print(f" Tradeoff table saved to {out_dir}/accuracy_coverage_tradeoff.csv")
    print(f" Tradeoff chart saved to {fig_dir}/fig4_risk_coverage_curve.png")

if __name__ == "__main__":
    run_tradeoff()