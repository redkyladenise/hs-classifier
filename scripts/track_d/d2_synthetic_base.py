import os
import sys
from pathlib import Path
import duckdb
import pandas as pd


def main():
    print("=" * 60)
    print("Track D - Step D2.1: Build Synthetic Base (Corrected)")
    print("=" * 60)

    con = duckdb.connect()

    # Join desc_code_counts with train_pairs_main to enforce the N=200 pool rule,
    # use the correct column 'tx_count', and apply the synthetic rules.
    query_base = """
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
            SUM(c.tx_count) AS tx_count
        FROM 'data/processed/desc_code_counts.parquet' c
        INNER JOIN train_pool p ON c.group_l1 = p.group_l1
        WHERE c.year IN (2023, 2024)
        GROUP BY c.group_l1, c.ahtn8
    ),
    conflict_free AS (
        SELECT 
            group_l1,
            MIN(ahtn8) AS ahtn8,
            MIN(ch2) AS ch2,
            MIN(hd4) AS hd4,
            SUM(tx_count) AS total_tx,
            COUNT(DISTINCT ahtn8) AS n_codes
        FROM pool_counts
        GROUP BY group_l1
        HAVING COUNT(DISTINCT ahtn8) = 1
    ),
    filtered_tx AS (
        SELECT *
        FROM conflict_free
        WHERE total_tx >= 2
    ),
    heading_counts AS (
        SELECT 
            hd4, 
            COUNT(group_l1) as n_desc_in_hd4
        FROM filtered_tx
        GROUP BY hd4
    ),
    final_base AS (
        SELECT 
            f.group_l1,
            f.ahtn8,
            f.ch2,
            f.hd4,
            f.total_tx
        FROM filtered_tx f
        INNER JOIN heading_counts h ON f.hd4 = h.hd4
        WHERE h.n_desc_in_hd4 >= 20
    )
    SELECT * FROM final_base
    """

    df = con.execute(query_base).df()
    n_base = len(df)
    print(f"Constructed synthetic base with {n_base:,} conflict-free descriptions.")

    if n_base == 0:
        print("ERROR: Synthetic base is empty! Try relaxing syn_min_tx to 1.")
        sys.exit(1)

    # Report sizes by Chapter and Heading
    print("\n--- Synthetic Base Size by Chapter ---")
    ch_summary = df.groupby('ch2').size().reset_index(name='n_descriptions')
    print(ch_summary.to_string(index=False))

    print("\n--- Summary of Headings ---")
    hd_summary = df.groupby('hd4').size()
    print(f"Total eligible 4-digit headings: {len(hd_summary)}")
    print(f"Smallest heading has: {hd_summary.min()} descriptions")
    print(f"Largest heading has : {hd_summary.max()} descriptions")

    # Save the base table
    out_dir = Path("data/audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "synthetic_base.parquet"
    
    # Save using DuckDB
    con.execute(f"CREATE TABLE syn_base AS SELECT * FROM df")
    con.execute(f"COPY syn_base TO '{out_path}' (FORMAT PARQUET)")
    
    print(f"\nSaved synthetic base to: {out_path}")


if __name__ == "__main__":
    main()