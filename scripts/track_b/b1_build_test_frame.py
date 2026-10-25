"""
scripts/track_b/b1_build_test_frame.py

Constructs the Track B sampling frame (frame_test.parquet):
1. Scope: test split, 2023-2024 transactions.
2. Whitelist filter: Excludes descriptions declaring codes absent from Track F.
3. Classifies strata:
   - Stratum A: Conflicting (>= 2 distinct AHTN8 codes in window)
   - Stratum B: Repeated Clean (>= 2 tx in window, exactly 1 AHTN8 code)
   - Stratum C: Singleton (exactly 1 tx in window)
4. Assigns divergence type (D2, D4, D6, D8) and dominance bands for Stratum A.
5. Emits cell diagnostics for Gate B1 review.
"""

from pathlib import Path
import pandas as pd
from hsclf.data.io import get_connection

OUTPUT_DIR = Path("reports/tables/track_b")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR = Path("data/audit")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def build_test_frame():
    res = get_connection()
    con = res[0] if isinstance(res, tuple) else res

    print("\n--- Building Track B Sampling Frame (Test Split, 2023-2024) ---")

    query = """
    -- 1. Identify valid AHTN codes from Track F reference
    WITH valid_codes AS (
        SELECT DISTINCT code8
        FROM 'data/reference/ahtn_2022_scope_reference.parquet'
    ),
    -- 2. Filter test transactions within the 2023-2024 window
    test_tx AS (
        SELECT 
            t.group_l1,
            t.group_l2,
            t.norm_bucket,
            t.ch2,
            t.hd4,
            t.sh6,
            t.ahtn8,
            CASE WHEN v.code8 IS NOT NULL THEN 1 ELSE 0 END AS is_valid_code
        FROM 'data/processed/transactions_grouped.parquet' t
        JOIN 'data/processed/split_assignments.parquet' s
            ON t.group_l2 = s.group_l2
        LEFT JOIN valid_codes v
            ON t.ahtn8 = v.code8
        WHERE s.split = 'test'
          AND t.year IN (2023, 2024)
    ),
    -- 3. Check code validity at description level
    desc_validity AS (
        SELECT 
            group_l1,
            MIN(is_valid_code) AS all_codes_valid
        FROM test_tx
        GROUP BY group_l1
    ),
    -- 4. Aggregate code distributions for valid descriptions
    desc_code_counts AS (
        SELECT 
            t.group_l1,
            t.group_l2,
            t.norm_bucket,
            t.ch2,
            t.hd4,
            t.sh6,
            t.ahtn8,
            COUNT(*) AS tx_count
        FROM test_tx t
        JOIN desc_validity v ON t.group_l1 = v.group_l1
        WHERE v.all_codes_valid = 1
        GROUP BY t.group_l1, t.group_l2, t.norm_bucket, t.ch2, t.hd4, t.sh6, t.ahtn8
    ),
    desc_summary AS (
        SELECT 
            group_l1,
            FIRST(group_l2) AS group_l2,
            FIRST(norm_bucket) AS norm_bucket,
            FIRST(ch2) AS ch2,
            COUNT(DISTINCT ahtn8) AS n_codes_ahtn8,
            COUNT(DISTINCT ch2) AS n_codes_ch2,
            COUNT(DISTINCT hd4) AS n_codes_hd4,
            COUNT(DISTINCT sh6) AS n_codes_sh6,
            SUM(tx_count) AS n_transactions_window,
            MAX(tx_count) AS max_tx,
            CASE 
                WHEN COUNT(DISTINCT ch2) > 1 THEN 'D2'
                WHEN COUNT(DISTINCT hd4) > 1 THEN 'D4'
                WHEN COUNT(DISTINCT sh6) > 1 THEN 'D6'
                WHEN COUNT(DISTINCT ahtn8) > 1 THEN 'D8'
                ELSE NULL
            END AS divergence_type
        FROM desc_code_counts
        GROUP BY group_l1
    ),
    frame_tagged AS (
        SELECT 
            group_l1,
            group_l2,
            norm_bucket,
            ch2,
            n_transactions_window,
            n_codes_ch2,
            n_codes_hd4,
            n_codes_sh6,
            n_codes_ahtn8,
            divergence_type,
            CASE 
                WHEN n_codes_ahtn8 > 1 THEN
                    CASE 
                        WHEN (1.0 * max_tx / n_transactions_window) >= 0.90 THEN 'dominant'
                        WHEN (1.0 * max_tx / n_transactions_window) >= 0.60 THEN 'moderate'
                        ELSE 'split'
                    END
                ELSE NULL
            END AS dominance_band,
            CASE 
                WHEN n_codes_ahtn8 > 1 THEN 'A'
                WHEN n_transactions_window >= 2 THEN 'B'
                ELSE 'C'
            END AS stratum
        FROM desc_summary
    )
    SELECT * FROM frame_tagged
    """

    frame_path = AUDIT_DIR / "frame_test.parquet"
    con.execute(f"COPY ({query}) TO '{frame_path.as_posix()}' (FORMAT PARQUET);")
    print(f"[SUCCESS] Test frame built and saved to: {frame_path}")

    # Gate B1 Evaluation Queries
    print("\n--- Gate B1 Cell Analysis ---")
    
    # 1. Stratum distribution
    strat_query = f"""
    SELECT 
        stratum,
        COUNT(*) AS n_descriptions,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) AS share_pct
    FROM '{frame_path.as_posix()}'
    GROUP BY stratum
    ORDER BY stratum;
    """
    df_strat = con.execute(strat_query).df()
    print(df_strat.to_string(index=False))

    # 2. Stratum A cell matrix: divergence_type x chapter
    cell_query = f"""
    SELECT 
        divergence_type,
        ch2 AS chapter,
        COUNT(*) AS n_descriptions
    FROM '{frame_path.as_posix()}'
    WHERE stratum = 'A'
    GROUP BY divergence_type, ch2
    ORDER BY divergence_type, ch2;
    """
    df_cells = con.execute(cell_query).df()
    df_cells.to_csv(OUTPUT_DIR / "b1_frame_cells.csv", index=False)

    pivot_cells = df_cells.pivot(index="divergence_type", columns="chapter", values="n_descriptions").fillna(0).astype(int)
    print("\n--- Stratum A Sampling Matrix (Divergence Type x Chapter) ---")
    print(pivot_cells.to_string())

    # Summary table
    df_strat.to_csv(OUTPUT_DIR / "b1_gate_b1_summary.csv", index=False)


if __name__ == "__main__":
    build_test_frame()