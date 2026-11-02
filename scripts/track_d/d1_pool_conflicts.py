import os
import sys
from pathlib import Path
import duckdb
import pandas as pd

def main():
    print("=" * 60)
    print("Track D - Step D1.1: Training Pool Conflict Analysis")
    print("=" * 60)

    con = duckdb.connect()

    print("Analyzing training pool descriptions for 2023-2024 window...")
    
    query = """
    WITH train_pool AS (
        SELECT DISTINCT group_l1 
        FROM 'data/processed/train_pairs_main.parquet'
    ),
    pool_counts AS (
        SELECT 
            c.group_l1,
            c.ahtn8,
            SUBSTRING(c.ahtn8, 1, 2) AS ch2,
            SUBSTRING(c.ahtn8, 1, 4) AS hd4,
            SUBSTRING(c.ahtn8, 1, 6) AS sh6,
            SUM(c.tx_count) AS tx_count
        FROM 'data/processed/desc_code_counts.parquet' c
        INNER JOIN train_pool p ON c.group_l1 = p.group_l1
        WHERE c.year IN (2023, 2024)
        GROUP BY c.group_l1, c.ahtn8
    ),
    desc_aggregates AS (
        SELECT 
            group_l1,
            SUBSTRING(MIN(ahtn8), 1, 2) AS primary_ch2,
            COUNT(DISTINCT ch2) AS n_ch2,
            COUNT(DISTINCT hd4) AS n_hd4,
            COUNT(DISTINCT sh6) AS n_sh6,
            COUNT(DISTINCT ahtn8) AS n_ahtn8,
            SUM(tx_count) AS total_tx,
            MAX(tx_count) AS top_tx
        FROM pool_counts
        GROUP BY group_l1
    ),
    classified_desc AS (
        SELECT 
            group_l1,
            primary_ch2,
            n_ch2,
            n_hd4,
            n_sh6,
            n_ahtn8,
            total_tx,
            top_tx,
            (top_tx * 1.0 / total_tx) AS top_share,
            CASE 
                WHEN n_ahtn8 = 1 THEN 'Consistent'
                WHEN (top_tx * 1.0 / total_tx) >= 0.90 THEN 'Dominant (>=90%)'
                WHEN (top_tx * 1.0 / total_tx) >= 0.60 THEN 'Moderate (60-89%)'
                ELSE 'Split (<60%)'
            END AS dominance_band
        FROM desc_aggregates
    )
    SELECT * FROM classified_desc
    """

    df = con.execute(query).df()
    total_desc = len(df)
    total_tx = df["total_tx"].sum()

    print(f"Total training pool descriptions: {total_desc:,}")
    print(f"Total training pool transactions  : {total_tx:,}")

    # 1. Level-by-level conflict summary
    levels = [
        ("Level 2 (Chapter)", "n_ch2"),
        ("Level 4 (Heading)", "n_hd4"),
        ("Level 6 (Subheading)", "n_sh6"),
        ("Level 8 (AHTN Line)", "n_ahtn8")
    ]

    summary_rows = []
    for level_name, col in levels:
        conf_mask = df[col] > 1
        conf_desc = int(conf_mask.sum())
        conf_tx = int(df.loc[conf_mask, "total_tx"].sum())
        summary_rows.append({
            "level": level_name,
            "conflicting_desc": conf_desc,
            "desc_pct": round((conf_desc / total_desc) * 100, 2),
            "conflicting_tx": conf_tx,
            "tx_pct": round((conf_tx / total_tx) * 100, 2)
        })

    summary_df = pd.DataFrame(summary_rows)
    print("\n--- Conflict Rate by Level ---")
    print(summary_df.to_string(index=False))

    # 2. Dominance breakdown for 8-digit level
    print("\n--- 8-Digit Dominance Bands ---")
    dom_summary = df.groupby("dominance_band").agg(
        desc_count=("group_l1", "count"),
        total_tx=("total_tx", "sum")
    ).reset_index()
    dom_summary["desc_pct"] = (dom_summary["desc_count"] / total_desc * 100).round(2)
    dom_summary["tx_pct"] = (dom_summary["total_tx"] / total_tx * 100).round(2)
    print(dom_summary.to_string(index=False))

    # 3. Save combined metrics to reports/tables/d1_pool_conflicts.csv
    out_dir = Path("reports/tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "d1_pool_conflicts.csv"
    
    # Save level summary and dominance together
    dom_summary.to_csv(out_path, index=False)
    print(f"\nSaved pool conflicts summary to: {out_path}")

if __name__ == "__main__":
    main()