"""Track A9: Class Eligibility by Hierarchical Level.

Evaluates training description diversity per class at 2-, 4-, 6-, and 8-digit levels
under 'main' and 'y1' scenarios. Computes both 'any' and 'majority' distinct description
counts and derives theoretical test-set accuracy ceilings.
"""

import sys
import time
from pathlib import Path
import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.io import get_connection, load_params


def stage_1_compute_eligibility(con, tx_file: Path, split_file: Path, output_file: Path, norm_buckets: int):
    """Compute distinct training descriptions per class and scenario across 16 buckets."""
    print("\n--- Stage 1: Computing Distinct Description Counts per Class ---")
    if output_file.exists():
        print(f"  {output_file.name} already exists. Skipping.")
        return

    start_t = time.time()
    temp_dir = output_file.parent / "temp_a9_buckets"
    temp_dir.mkdir(parents=True, exist_ok=True)

    levels = [
        ("ch2", 2),
        ("hd4", 4),
        ("sh6", 6),
        ("ahtn8", 8)
    ]

    scenarios = [
        ("main", "t.year IN (2023, 2024)"),
        ("y1", "t.year = 2023")
    ]

    bucket_parts = []

    for b in range(norm_buckets):
        part_path = temp_dir / f"eligibility_b{b:02d}.parquet"
        bucket_parts.append(part_path)
        if part_path.exists():
            continue

        start_b = time.time()
        print(f"  Processing bucket {b:02d}...")

        subqueries = []
        for sc_name, sc_filter in scenarios:
            for col_name, lvl in levels:
                # 1. Any count: distinct group_l1 appearing with the class
                # 2. Majority count: distinct group_l1 whose arg_max majority code is this class
                subqueries.append(f"""
                    SELECT 
                        '{sc_name}' AS scenario,
                        {lvl} AS level,
                        {col_name} AS class,
                        group_l1,
                        is_majority
                    FROM (
                        WITH tx_train AS (
                            SELECT 
                                t.group_l1,
                                t.{col_name}
                            FROM read_parquet('{tx_file.as_posix()}') t
                            INNER JOIN read_parquet('{split_file.as_posix()}') s
                                ON t.group_l2 = s.group_l2
                            WHERE t.norm_bucket = {b}
                              AND s.split = 'train'
                              AND {sc_filter}
                        ),
                        class_counts AS (
                            SELECT 
                                group_l1,
                                {col_name},
                                count(*) AS cnt
                            FROM tx_train
                            GROUP BY group_l1, {col_name}
                        ),
                        majorities AS (
                            SELECT 
                                group_l1,
                                arg_max({col_name}, cnt) AS maj_class
                            FROM class_counts
                            GROUP BY group_l1
                        )
                        SELECT 
                            c.group_l1,
                            c.{col_name},
                            (c.{col_name} = m.maj_class) AS is_majority
                        FROM class_counts c
                        INNER JOIN majorities m
                            ON c.group_l1 = m.group_l1
                    )
                """)

        union_query = " UNION ALL ".join(subqueries)
        bucket_query = f"""
            COPY (
                SELECT 
                    scenario,
                    level,
                    class,
                    count(DISTINCT group_l1) AS n_train_desc_any,
                    count(DISTINCT CASE WHEN is_majority THEN group_l1 END) AS n_train_desc_majority
                FROM ({union_query})
                GROUP BY scenario, level, class
            ) TO '{part_path.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
        """
        con.execute(bucket_query)
        print(f"    Saved bucket {b:02d} in {time.time() - start_b:.1f}s.")

    # Sum across buckets (exact addition since each description belongs to strictly one bucket)
    print("Combining bucket partitions into class_eligibility.parquet...")
    glob_pattern = (temp_dir / "eligibility_b*.parquet").as_posix()
    con.execute(f"""
        COPY (
            SELECT 
                scenario,
                level,
                class,
                sum(n_train_desc_any)::BIGINT AS n_train_desc_any,
                sum(n_train_desc_majority)::BIGINT AS n_train_desc_majority,
                (sum(n_train_desc_any) >= 10) AS eligible_at_10,
                (sum(n_train_desc_any) >= 20) AS eligible_at_20,
                (sum(n_train_desc_any) >= 50) AS eligible_at_50,
                (sum(n_train_desc_majority) >= 20) AS eligible_majority_at_20
            FROM read_parquet('{glob_pattern}')
            GROUP BY scenario, level, class
            ORDER BY scenario, level, class
        ) TO '{output_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
    """)
    print(f"Saved {output_file.name} in {time.time() - start_t:.1f}s.")


def stage_2_compile_summary(con, elig_file: Path, tx_file: Path, desc_file: Path, desc_status_file: Path, tables_dir: Path):
    """Generate reports/tables/a9_eligibility_summary.csv and theoretical test ceilings."""
    print("\n--- Stage 2: Compiling Summary Reports and Theoretical Ceilings ---")
    tables_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = tables_dir / "a9_eligibility_summary.csv"

    # Overall in-scope denominators
    total_in_scope_tx = con.execute(f"SELECT count(*) FROM read_parquet('{tx_file.as_posix()}')").fetchone()[0]
    total_unique_descs = con.execute(f"SELECT count(*) FROM read_parquet('{desc_file.as_posix()}')").fetchone()[0]

    summary_records = []
    levels = [("ch2", 2), ("hd4", 4), ("sh6", 6), ("ahtn8", 8)]
    scenarios = ["main", "y1"]

    for sc in scenarios:
        for col_name, lvl in levels:
            # 1. Total codes and eligible counts
            stats = con.execute(f"""
                SELECT 
                    count(*) AS n_codes,
                    count(CASE WHEN eligible_at_20 THEN 1 END) AS n_eligible_20,
                    count(CASE WHEN eligible_at_10 THEN 1 END) AS n_eligible_10,
                    count(CASE WHEN eligible_at_50 THEN 1 END) AS n_eligible_50,
                    count(CASE WHEN eligible_majority_at_20 THEN 1 END) AS n_eligible_maj_20,
                    count(CASE WHEN eligible_at_20 != eligible_majority_at_20 THEN 1 END) AS n_shifted_codes
                FROM read_parquet('{elig_file.as_posix()}')
                WHERE scenario = '{sc}' AND level = {lvl}
            """).df().iloc[0]

            # 2. Coverage of in-scope transactions (using majority_ahtn8 mapped to class)
            tx_cov = con.execute(f"""
                WITH elig_classes AS (
                    SELECT class 
                    FROM read_parquet('{elig_file.as_posix()}')
                    WHERE scenario = '{sc}' AND level = {lvl} AND eligible_at_20
                )
                SELECT 
                    round(count(CASE WHEN t.{col_name} IN (SELECT class FROM elig_classes) THEN 1 END) * 100.0 / {total_in_scope_tx}, 4) AS pct_tx_cov
                FROM read_parquet('{tx_file.as_posix()}') t
            """).fetchone()[0]

            # 3. Coverage of unique descriptions
            # Determine description's majority class at this level
            desc_cov = con.execute(f"""
                WITH elig_classes AS (
                    SELECT class 
                    FROM read_parquet('{elig_file.as_posix()}')
                    WHERE scenario = '{sc}' AND level = {lvl} AND eligible_at_20
                ),
                desc_maj AS (
                    SELECT 
                        desc_norm_id,
                        SUBSTRING(majority_ahtn8, 1, {lvl}) AS maj_class
                    FROM read_parquet('{desc_file.as_posix()}')
                )
                SELECT 
                    round(count(CASE WHEN maj_class IN (SELECT class FROM elig_classes) THEN 1 END) * 100.0 / {total_unique_descs}, 4) AS pct_desc_cov
                FROM desc_maj
            """).fetchone()[0]

            # 4. Theoretical Accuracy Ceiling on Test Sets
            # - unseen: 2023-2024 test split
            # - y1: 2024 all transactions
            # - y2: 2025 all transactions
            if sc == "main":
                ceiling_unseen = con.execute(f"""
                    WITH elig_classes AS (
                        SELECT class 
                        FROM read_parquet('{elig_file.as_posix()}')
                        WHERE scenario = 'main' AND level = {lvl} AND eligible_at_20
                    ),
                    test_tx AS (
                        SELECT t.{col_name}
                        FROM read_parquet('{tx_file.as_posix()}') t
                        INNER JOIN read_parquet('{desc_status_file.as_posix()}') s
                            ON t.group_l1 = s.group_l1
                        WHERE t.year IN (2023, 2024) AND s.split = 'test'
                    )
                    SELECT round(count(CASE WHEN {col_name} IN (SELECT class FROM elig_classes) THEN 1 END) * 100.0 / count(*), 4)
                    FROM test_tx
                """).fetchone()[0]

                ceiling_y2 = con.execute(f"""
                    WITH elig_classes AS (
                        SELECT class 
                        FROM read_parquet('{elig_file.as_posix()}')
                        WHERE scenario = 'main' AND level = {lvl} AND eligible_at_20
                    ),
                    test_tx AS (
                        SELECT t.{col_name}
                        FROM read_parquet('{tx_file.as_posix()}') t
                        WHERE t.year = 2025
                    )
                    SELECT round(count(CASE WHEN {col_name} IN (SELECT class FROM elig_classes) THEN 1 END) * 100.0 / count(*), 4)
                    FROM test_tx
                """).fetchone()[0]
                ceiling_val = f"unseen: {ceiling_unseen}%, y2: {ceiling_y2}%"
            else:
                ceiling_y1 = con.execute(f"""
                    WITH elig_classes AS (
                        SELECT class 
                        FROM read_parquet('{elig_file.as_posix()}')
                        WHERE scenario = 'y1' AND level = {lvl} AND eligible_at_20
                    ),
                    test_tx AS (
                        SELECT t.{col_name}
                        FROM read_parquet('{tx_file.as_posix()}') t
                        WHERE t.year = 2024
                    )
                    SELECT round(count(CASE WHEN {col_name} IN (SELECT class FROM elig_classes) THEN 1 END) * 100.0 / count(*), 4)
                    FROM test_tx
                """).fetchone()[0]
                ceiling_val = f"y1: {ceiling_y1}%"

            summary_records.append({
                "scenario": sc,
                "level": lvl,
                "n_codes": int(stats["n_codes"]),
                "eligible_at_20": int(stats["n_eligible_20"]),
                "eligible_at_10": int(stats["n_eligible_10"]),
                "eligible_at_50": int(stats["n_eligible_50"]),
                "eligible_maj_20": int(stats["n_eligible_maj_20"]),
                "codes_shifted": int(stats["n_shifted_codes"]),
                "pct_tx_coverage": tx_cov,
                "pct_desc_coverage": desc_cov,
                "test_accuracy_ceiling": ceiling_val
            })

    summary_df = pd.DataFrame(summary_records)
    summary_df.to_csv(summary_csv, index=False)
    print(f"Saved {summary_csv.name}:")
    print(summary_df.to_string(index=False))

    # Audit the 20 largest excluded 8-digit codes in main scenario
    print("\nAuditing top 20 largest excluded 8-digit codes (main scenario at threshold 20)...")
    top_excluded = con.execute(f"""
        WITH inelig_codes AS (
            SELECT class 
            FROM read_parquet('{elig_file.as_posix()}')
            WHERE scenario = 'main' AND level = 8 AND NOT eligible_at_20
        )
        SELECT 
            t.ahtn8 AS excluded_code,
            count(*) AS n_transactions,
            round(count(*) * 100.0 / {total_in_scope_tx}, 4) AS pct_in_scope_tx,
            count(DISTINCT t.group_l1) AS n_unique_descriptions
        FROM read_parquet('{tx_file.as_posix()}') t
        WHERE t.ahtn8 IN (SELECT class FROM inelig_codes)
        GROUP BY t.ahtn8
        ORDER BY n_transactions DESC
        LIMIT 20
    """).df()

    excluded_csv = tables_dir / "a9_top_excluded_codes.csv"
    top_excluded.to_csv(excluded_csv, index=False)
    print(f"Saved {excluded_csv.name}:")
    print(top_excluded.head(10).to_string(index=False))


def main():
    params = load_params()
    con, _ = get_connection(params)

    processed_dir = ROOT / params["paths"]["processed_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

    tx_file = processed_dir / "transactions_grouped.parquet"
    split_file = processed_dir / "split_assignments.parquet"
    desc_file = processed_dir / "unique_descriptions.parquet"
    desc_status_file = processed_dir / "description_status.parquet"
    elig_file = processed_dir / "class_eligibility.parquet"

    norm_buckets = params.get("norm_buckets", 16)

    try:
        stage_1_compute_eligibility(con, tx_file, split_file, elig_file, norm_buckets)
        stage_2_compile_summary(con, elig_file, tx_file, desc_file, desc_status_file, tables_dir)
        print("\nTrack A9 pipeline completed successfully.")
    finally:
        con.close()


if __name__ == "__main__":
    main()