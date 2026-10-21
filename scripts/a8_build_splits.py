"""Track A8: Leakage-Free Stratified Group Splitting and Diagnostic Pipeline.

Partitions Level-2 skeleton groups deterministically into train, val, test, and only_2025.
Constructs split_assignments.parquet, description_status.parquet, and diagnostic summaries.
"""

import sys
import time
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.group_split import (
    assign_split_by_position,
    determine_seen_status,
    hash_group_seed,
)
from src.hsclf.data.io import get_connection, load_params


def stage_1_aggregate_l2_groups(con, unique_desc_file: Path, temp_dir: Path, norm_buckets: int):
    """Aggregate unique descriptions up to Level-2 groups partitioned by group_l2 bucket."""
    print("\n--- Stage 1: Aggregating Level-2 Skeleton Groups ---")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_parts = []

    for b in range(norm_buckets):
        part_path = temp_dir / f"l2_agg_b{b:02d}.parquet"
        temp_parts.append(part_path)
        if part_path.exists():
            print(f"  Bucket {b:02d} already aggregated. Skipping.")
            continue

        start_b = time.time()
        print(f"  Aggregating group_l2 for bucket {b:02d}...")

        query = f"""
            COPY (
                WITH bucket_items AS (
                    SELECT 
                        group_l2,
                        desc_norm_id,
                        n_transactions,
                        first_year,
                        last_year,
                        majority_ahtn8
                    FROM read_parquet('{unique_desc_file.as_posix()}')
                    WHERE abs(group_l2) % {norm_buckets} = {b}
                ),
                group_majorities AS (
                    SELECT 
                        group_l2,
                        arg_max(majority_ahtn8, total_tx) AS majority_ahtn8_l2
                    FROM (
                        SELECT 
                            group_l2,
                            majority_ahtn8,
                            sum(n_transactions) AS total_tx
                        FROM bucket_items
                        GROUP BY group_l2, majority_ahtn8
                    )
                    GROUP BY group_l2
                ),
                group_aggs AS (
                    SELECT 
                        group_l2,
                        count(DISTINCT desc_norm_id) AS n_descriptions,
                        sum(n_transactions)::BIGINT AS n_transactions,
                        min(first_year) AS first_year_l2,
                        max(last_year) AS last_year_l2
                    FROM bucket_items
                    GROUP BY group_l2
                )
                SELECT 
                    a.group_l2,
                    m.majority_ahtn8_l2,
                    a.n_descriptions,
                    a.n_transactions,
                    a.first_year_l2,
                    a.last_year_l2
                FROM group_aggs a
                INNER JOIN group_majorities m
                    ON a.group_l2 = m.group_l2
            ) TO '{part_path.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
        """
        con.execute(query)
        print(f"  Bucket {b:02d} saved in {time.time() - start_b:.1f}s.")

    return temp_parts


def stage_2_stratified_split(con, temp_dir: Path, output_file: Path, seed: int):
    """Execute deterministic stratification on Level-2 groups."""
    print("\n--- Stage 2: Performing Stratified Partitioning ---")
    if output_file.exists():
        print(f"  {output_file.name} already exists. Skipping.")
        return

    start_t = time.time()
    glob_pattern = (temp_dir / "l2_agg_b*.parquet").as_posix()

    print("Loading Level-2 aggregate pool into memory...")
    groups_df = con.execute(f"""
        SELECT 
            group_l2,
            majority_ahtn8_l2,
            n_descriptions,
            n_transactions,
            first_year_l2,
            last_year_l2
        FROM read_parquet('{glob_pattern}')
    """).df()

    print(f"Total Level-2 groups loaded: {len(groups_df):,}")

    # Mark only_2025 groups
    is_only_2025 = groups_df["first_year_l2"] == 2025
    early_df = groups_df[~is_only_2025].copy()
    only_2025_df = groups_df[is_only_2025].copy()

    only_2025_df["split"] = "only_2025"
    print(f"  early groups (2023-2024 active): {len(early_df):,}")
    print(f"  only_2025 groups (held out): {len(only_2025_df):,}")

    # Deterministic mixing hash
    print("Computing deterministic integer mixing hashes...")
    early_df["mix_hash"] = [hash_group_seed(gid, seed) for gid in early_df["group_l2"]]

    # Rank within majority_ahtn8_l2 stratum
    print("Ranking within majority code strata...")
    early_df["stratum_rank"] = (
        early_df.groupby("majority_ahtn8_l2")["mix_hash"]
        .rank(method="first", ascending=True)
        .astype(int)
    )
    early_df["stratum_size"] = early_df.groupby("majority_ahtn8_l2")["mix_hash"].transform("count")

    # Assign position-based splits
    print("Assigning position thresholds (<0.70, <0.85, test)...")
    positions = (early_df["stratum_rank"] - 0.5) / early_df["stratum_size"]
    splits = np.where(positions < 0.70, "train", np.where(positions < 0.85, "val", "test"))
    early_df["split"] = splits

    early_df = early_df.drop(columns=["mix_hash", "stratum_rank", "stratum_size"])

    # Combine early and only_2025
    final_splits_df = pd.concat([early_df, only_2025_df], ignore_index=True)
    
    # Save to Parquet
    schema = pa.schema([
        ("group_l2", pa.int64()),
        ("majority_ahtn8_l2", pa.string()),
        ("n_descriptions", pa.int64()),
        ("n_transactions", pa.int64()),
        ("first_year_l2", pa.int32()),
        ("last_year_l2", pa.int32()),
        ("split", pa.string()),
    ])
    table = pa.Table.from_pandas(final_splits_df, schema=schema, preserve_index=False)
    pq.write_table(table, output_file, compression="ZSTD")
    print(f"Saved {output_file.name} ({len(final_splits_df):,} rows) in {time.time() - start_t:.1f}s.")


def stage_3_build_description_status(con, unique_desc_file: Path, split_file: Path, output_file: Path):
    """Build description_status.parquet with seen_y1 and seen_y2 statuses."""
    print("\n--- Stage 3: Resolving Description Seen Statuses ---")
    if output_file.exists():
        print(f"  {output_file.name} already exists. Skipping.")
        return

    start_t = time.time()
    print("Computing seen statuses for all Level-1 descriptions...")

    query = f"""
        COPY (
            WITH desc_splits AS (
                SELECT 
                    u.desc_norm_id AS group_l1,
                    u.group_l2,
                    u.first_year AS first_year_l1,
                    s.first_year_l2,
                    s.split
                FROM read_parquet('{unique_desc_file.as_posix()}') u
                INNER JOIN read_parquet('{split_file.as_posix()}') s
                    ON u.group_l2 = s.group_l2
            )
            SELECT 
                group_l1,
                group_l2,
                split,
                CASE 
                    WHEN split = 'train' AND first_year_l1 <= 2023 THEN 'seen_exact'
                    WHEN split = 'train' AND first_year_l2 <= 2023 THEN 'seen_near'
                    ELSE 'new'
                END AS seen_y1,
                CASE 
                    WHEN split = 'train' AND first_year_l1 <= 2024 THEN 'seen_exact'
                    WHEN split = 'train' AND first_year_l2 <= 2024 THEN 'seen_near'
                    ELSE 'new'
                END AS seen_y2
            FROM desc_splits
        ) TO '{output_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
    """
    con.execute(query)
    print(f"Saved {output_file.name} in {time.time() - start_t:.1f}s.")


def stage_4_audits_and_diagnostics(con, split_file: Path, desc_status_file: Path, unique_desc_file: Path, tx_file: Path, tables_dir: Path):
    """Run all balance, conflict, repetition, and scenario diagnostic checks."""
    print("\n--- Stage 4: Compiling Split Diagnostics ---")
    tables_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = tables_dir / "a8_split_summary.csv"

    # 1. Group Cardinality & Share Balance among early groups
    print("\n[Audit 1: Early Group Proportions]")
    early_groups_summary = con.execute(f"""
        WITH early AS (
            SELECT split, count(*) AS n_groups, sum(n_transactions)::BIGINT AS n_tx
            FROM read_parquet('{split_file.as_posix()}')
            WHERE split != 'only_2025'
            GROUP BY split
        )
        SELECT 
            split,
            n_groups,
            round(n_groups * 100.0 / sum(n_groups) OVER (), 4) AS pct_groups,
            n_tx,
            round(n_tx * 100.0 / sum(n_tx) OVER (), 4) AS pct_tx
        FROM early
        ORDER BY split DESC;
    """).df()
    print(early_groups_summary.to_string(index=False))

    # 2. Strata Coverage Check
    print("\n[Audit 2: Code Strata Representation]")
    strata_check = con.execute(f"""
        SELECT 
            count(DISTINCT majority_ahtn8_l2) AS total_strata,
            count(CASE WHEN n_splits = 3 THEN 1 END) AS strata_in_all_3_splits
        FROM (
            SELECT 
                majority_ahtn8_l2,
                count(DISTINCT split) AS n_splits
            FROM read_parquet('{split_file.as_posix()}')
            WHERE split IN ('train', 'val', 'test')
            GROUP BY majority_ahtn8_l2
            HAVING count(*) >= 5
        )
    """).df()
    print(strata_check.to_string(index=False))

    # 3. Conflict Parity Balance across splits
    print("\n[Audit 3: Conflict Balance Across Splits]")
    conflict_balance = con.execute(f"""
        WITH tx_conflicts AS (
            SELECT 
                s.split,
                t.group_l1,
                (u.n_codes_ahtn8 > 1) AS is_conflict_desc
            FROM read_parquet('{tx_file.as_posix()}') t
            INNER JOIN read_parquet('{desc_status_file.as_posix()}') s
                ON t.group_l1 = s.group_l1
            INNER JOIN read_parquet('{unique_desc_file.as_posix()}') u
                ON t.group_l1 = u.desc_norm_id
        )
        SELECT 
            split,
            count(*) AS total_transactions,
            round(sum(CASE WHEN is_conflict_desc THEN 1.0 ELSE 0.0 END) * 100.0 / count(*), 4) AS pct_conflicting_tx,
            count(DISTINCT group_l1) AS total_descriptions,
            round(count(DISTINCT CASE WHEN is_conflict_desc THEN group_l1 END) * 100.0 / count(DISTINCT group_l1), 4) AS pct_conflicting_descs
        FROM tx_conflicts
        GROUP BY split
        ORDER BY split;
    """).df()
    print(conflict_balance.to_string(index=False))

    # 4. Evaluation Scenarios Matrix
    print("\n[Audit 4: Scenario Summary Matrix]")
    scenario_matrix = con.execute(f"""
        WITH tx_context AS (
            SELECT 
                t.row_id,
                t.year,
                s.split,
                s.seen_y1,
                s.seen_y2,
                t.group_l1
            FROM read_parquet('{tx_file.as_posix()}') t
            INNER JOIN read_parquet('{desc_status_file.as_posix()}') s
                ON t.group_l1 = s.group_l1
        )
        SELECT 
            'unseen' AS scenario,
            count(CASE WHEN year IN (2023, 2024) AND split = 'train' THEN 1 END) AS n_train_tx,
            count(CASE WHEN year IN (2023, 2024) AND split = 'val' THEN 1 END) AS n_val_tx,
            count(CASE WHEN year IN (2023, 2024) AND split = 'test' THEN 1 END) AS n_test_tx,
            round(count(CASE WHEN year IN (2023, 2024) AND split = 'test' THEN 1 END) * 100.0 / 
                  nullif(count(CASE WHEN year IN (2023, 2024) AND split = 'test' THEN 1 END), 0), 2) AS pct_new_test
        FROM tx_context
        UNION ALL
        SELECT 
            'y1' AS scenario,
            count(CASE WHEN year = 2023 AND split = 'train' THEN 1 END) AS n_train_tx,
            count(CASE WHEN year = 2023 AND split = 'val' THEN 1 END) AS n_val_tx,
            count(CASE WHEN year = 2024 THEN 1 END) AS n_test_tx,
            round(count(CASE WHEN year = 2024 AND seen_y1 = 'new' THEN 1 END) * 100.0 / 
                  count(CASE WHEN year = 2024 THEN 1 END), 2) AS pct_new_test
        FROM tx_context
        UNION ALL
        SELECT 
            'y2' AS scenario,
            count(CASE WHEN year IN (2023, 2024) AND split = 'train' THEN 1 END) AS n_train_tx,
            count(CASE WHEN year IN (2023, 2024) AND split = 'val' THEN 1 END) AS n_val_tx,
            count(CASE WHEN year = 2025 THEN 1 END) AS n_test_tx,
            round(count(CASE WHEN year = 2025 AND seen_y2 = 'new' THEN 1 END) * 100.0 / 
                  count(CASE WHEN year = 2025 THEN 1 END), 2) AS pct_new_test
        FROM tx_context;
    """).df()
    print(scenario_matrix.to_string(index=False))

    # 5. Track B Conflicting Feasibility Pool in Test Split
    print("\n[Audit 5: Track B Test Conflict Sampling Pool]")
    track_b_pool = con.execute(f"""
        SELECT 
            t.ch2 AS chapter,
            count(DISTINCT u.desc_norm_id) AS n_conflicting_test_descs
        FROM read_parquet('{unique_desc_file.as_posix()}') u
        INNER JOIN read_parquet('{desc_status_file.as_posix()}') s
            ON u.desc_norm_id = s.group_l1
        INNER JOIN read_parquet('{tx_file.as_posix()}') t
            ON u.desc_norm_id = t.group_l1
        WHERE s.split = 'test'
          AND u.n_codes_ahtn8 > 1
          AND u.n_transactions >= 2
        GROUP BY t.ch2
        ORDER BY t.ch2;
    """).df()
    print(track_b_pool.to_string(index=False))

    # Save summary
    early_groups_summary.to_csv(summary_csv, index=False)
    print(f"\nSaved {summary_csv.name}.")


def main():
    params = load_params()
    con, _ = get_connection(params)

    processed_dir = ROOT / params["paths"]["processed_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

    unique_desc_file = processed_dir / "unique_descriptions.parquet"
    tx_file = processed_dir / "transactions_grouped.parquet"
    temp_dir = processed_dir / "temp_l2_aggregates"

    split_file = processed_dir / "split_assignments.parquet"
    desc_status_file = processed_dir / "description_status.parquet"

    norm_buckets = params.get("norm_buckets", 16)
    seed = params.get("random_seed", 42)

    try:
        stage_1_aggregate_l2_groups(con, unique_desc_file, temp_dir, norm_buckets)
        stage_2_stratified_split(con, temp_dir, split_file, seed)
        stage_3_build_description_status(con, unique_desc_file, split_file, desc_status_file)
        stage_4_audits_and_diagnostics(con, split_file, desc_status_file, unique_desc_file, tx_file, tables_dir)
        print("\nTrack A8 split pipeline completed successfully.")
    finally:
        con.close()


if __name__ == "__main__":
    main()