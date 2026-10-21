"""Track A7: Description Grouping and Conflict Preview Pipeline.

Builds Level-1 and Level-2 description groupings, aggregates unique description
cardinalities and majority targets, creates the final integer-only grouped transactions dataset,
and compiles conflict preview metrics.
"""

import sys
import time
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.group_split import compute_group_l2_id, compute_skeleton_text
from src.hsclf.data.io import get_connection, load_params


def stage_1_build_skeleton_parts(con, norm_desc_file: Path, scope_file: Path, parts_dir: Path, norm_buckets: int, chunk_size: int):
    """Generate mapping of desc_norm_id to group_l2 bucket-by-bucket."""
    print("\n--- Stage 1: Generating Level-2 (Skeleton) Group IDs ---")
    parts_dir.mkdir(parents=True, exist_ok=True)

    for b in range(norm_buckets):
        part_path = parts_dir / f"b{b:02d}.parquet"
        if part_path.exists():
            print(f"  Bucket {b:02d} already exists: {part_path.name}. Skipping.")
            continue

        start_b = time.time()
        print(f"  Extracting in-scope distinct descriptions for Bucket {b:02d}...")

        # Select only desc_norm_id present in transactions_scope for bucket b
        distinct_df = con.execute(f"""
            SELECT DISTINCT s.desc_norm_id, n.desc_norm
            FROM (
                SELECT DISTINCT desc_norm_id 
                FROM read_parquet('{scope_file.as_posix()}')
                WHERE norm_bucket = {b}
            ) s
            INNER JOIN read_parquet('{norm_desc_file.as_posix()}') n
                ON s.desc_norm_id = n.desc_norm_id
            WHERE n.norm_bucket = {b}
        """).df()

        print(f"    Bucket {b:02d}: {len(distinct_df):,} unique descriptions. Computing skeletons...")
        
        group_l2_ids = []
        for text in distinct_df["desc_norm"]:
            sk = compute_skeleton_text(text)
            group_l2_ids.append(compute_group_l2_id(sk))

        distinct_df["group_l2"] = group_l2_ids
        distinct_df = distinct_df.drop(columns=["desc_norm"])

        # Write out as compact Parquet
        table = pa.Table.from_pandas(distinct_df, preserve_index=False)
        pq.write_table(table, part_path, compression="ZSTD")
        print(f"  Saved {part_path.name} in {time.time() - start_b:.1f}s.")


def stage_2_build_unique_descriptions(con, scope_file: Path, skeleton_parts_dir: Path, output_file: Path, norm_buckets: int):
    """Build data/processed/unique_descriptions.parquet partitioned strictly by norm_bucket."""
    print("\n--- Stage 2: Building unique_descriptions.parquet ---")
    if output_file.exists():
        print(f"  {output_file.name} already exists. Skipping.")
        return

    temp_dir = output_file.parent / "temp_unique_desc_buckets"
    temp_dir.mkdir(parents=True, exist_ok=True)

    for b in range(norm_buckets):
        part_path = temp_dir / f"unique_desc_b{b:02d}.parquet"
        if part_path.exists():
            print(f"  Bucket {b:02d} part already exists. Skipping.")
            continue

        start_b = time.time()
        print(f"  Aggregating unique descriptions for Bucket {b:02d}...")

        sk_part = skeleton_parts_dir / f"b{b:02d}.parquet"

        # Note: Using arg_max to pick majority_ahtn8 deterministically
        query = f"""
            COPY (
                WITH base AS (
                    SELECT 
                        desc_norm_id,
                        norm_bucket,
                        year,
                        ch2,
                        hd4,
                        sh6,
                        ahtn8
                    FROM read_parquet('{scope_file.as_posix()}')
                    WHERE norm_bucket = {b}
                ),
                code_counts AS (
                    SELECT 
                        desc_norm_id,
                        ahtn8,
                        count(*) AS cnt
                    FROM base
                    GROUP BY desc_norm_id, ahtn8
                ),
                majorities AS (
                    SELECT 
                        desc_norm_id,
                        arg_max(ahtn8, cnt) AS majority_ahtn8
                    FROM code_counts
                    GROUP BY desc_norm_id
                ),
                desc_aggs AS (
                    SELECT 
                        b.desc_norm_id,
                        b.norm_bucket,
                        count(*) AS n_transactions,
                        min(b.year) AS first_year,
                        max(b.year) AS last_year,
                        count(DISTINCT b.ch2) AS n_codes_ch2,
                        count(DISTINCT b.hd4) AS n_codes_hd4,
                        count(DISTINCT b.sh6) AS n_codes_sh6,
                        count(DISTINCT b.ahtn8) AS n_codes_ahtn8
                    FROM base b
                    GROUP BY b.desc_norm_id, b.norm_bucket
                )
                SELECT 
                    a.desc_norm_id,
                    a.norm_bucket,
                    a.n_transactions,
                    a.first_year,
                    a.last_year,
                    a.n_codes_ch2,
                    a.n_codes_hd4,
                    a.n_codes_sh6,
                    a.n_codes_ahtn8,
                    m.majority_ahtn8,
                    sk.group_l2
                FROM desc_aggs a
                INNER JOIN majorities m
                    ON a.desc_norm_id = m.desc_norm_id
                INNER JOIN read_parquet('{sk_part.as_posix()}') sk
                    ON a.desc_norm_id = sk.desc_norm_id
            ) TO '{part_path.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
        """
        con.execute(query)
        print(f"  Saved {part_path.name} in {time.time() - start_b:.1f}s.")

    print(f"Merging unique description bucket parts into {output_file.name}...")
    glob_pattern = (temp_dir / "unique_desc_b*.parquet").as_posix()
    con.execute(f"""
        COPY (
            SELECT * FROM read_parquet('{glob_pattern}')
        ) TO '{output_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
    """)
    print(f"Created {output_file.name} successfully.")


def stage_3_build_transactions_grouped(con, scope_file: Path, skeleton_parts_dir: Path, output_file: Path, norm_buckets: int):
    """Build data/processed/transactions_grouped.parquet holding integer IDs only."""
    print("\n--- Stage 3: Building transactions_grouped.parquet ---")
    if output_file.exists():
        print(f"  {output_file.name} already exists. Skipping.")
        return

    temp_dir = output_file.parent / "temp_tx_grouped_buckets"
    temp_dir.mkdir(parents=True, exist_ok=True)

    for b in range(norm_buckets):
        part_path = temp_dir / f"tx_grouped_b{b:02d}.parquet"
        if part_path.exists():
            print(f"  Bucket {b:02d} already exists. Skipping.")
            continue

        start_b = time.time()
        print(f"  Joining group IDs for Bucket {b:02d} transactions...")
        sk_part = skeleton_parts_dir / f"b{b:02d}.parquet"

        query = f"""
            COPY (
                SELECT 
                    s.row_id,
                    s.year,
                    s.month,
                    s.desc_norm_id AS group_l1,
                    sk.group_l2,
                    s.norm_bucket,
                    s.ch2,
                    s.hd4,
                    s.sh6,
                    s.ahtn8,
                    s.ends_00
                FROM read_parquet('{scope_file.as_posix()}') s
                INNER JOIN read_parquet('{sk_part.as_posix()}') sk
                    ON s.desc_norm_id = sk.desc_norm_id
                WHERE s.norm_bucket = {b}
            ) TO '{part_path.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
        """
        con.execute(query)
        print(f"  Saved {part_path.name} in {time.time() - start_b:.1f}s.")

    print(f"Merging grouped transaction parts into {output_file.name}...")
    glob_pattern = (temp_dir / "tx_grouped_b*.parquet").as_posix()
    con.execute(f"""
        COPY (
            SELECT * FROM read_parquet('{glob_pattern}')
        ) TO '{output_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
    """)
    print(f"Created {output_file.name} successfully.")


def stage_4_conflict_preview(con, unique_desc_file: Path, tx_grouped_file: Path, norm_desc_file: Path, tables_dir: Path, norm_buckets: int):
    """Compute conflict rates at each level, group sizes, and top 20 largest groups."""
    print("\n--- Stage 4: Compiling Conflict Preview Diagnostics ---")
    tables_dir.mkdir(parents=True, exist_ok=True)
    report_csv = tables_dir / "a7_conflict_preview.csv"
    top_groups_csv = tables_dir / "a7_top_skeleton_groups.csv"

    # 1. Reduction Ratio and Group Sizes
    print("Computing Level-1 vs Level-2 reduction ratios...")
    group_stats = con.execute(f"""
        SELECT 
            count(*) AS n_l1_descs,
            count(DISTINCT group_l2) AS n_l2_groups,
            round(count(*) * 1.0 / count(DISTINCT group_l2), 4) AS reduction_ratio,
            sum(CASE WHEN group_size > 1 THEN 1 ELSE 0 END) AS n_l1_in_multi_groups,
            round(sum(CASE WHEN group_size > 1 THEN 1.0 ELSE 0.0 END) * 100.0 / count(*), 4) AS pct_l1_in_multi_groups
        FROM (
            SELECT 
                desc_norm_id,
                group_l2,
                count(*) OVER (PARTITION BY group_l2) AS group_size
            FROM read_parquet('{unique_desc_file.as_posix()}')
        )
    """).df()

    print("\nGroup Cardinality Overview:")
    print(group_stats.to_string(index=False))

    # 2. Level-1 Conflicts per Hierarchy Level (Overall and by Chapter)
    print("\nComputing Level-1 conflict rates across hierarchy levels...")
    levels = [("ch2", "n_codes_ch2"), ("hd4", "n_codes_hd4"), ("sh6", "n_codes_sh6"), ("ahtn8", "n_codes_ahtn8")]
    
    conflict_records = []
    total_tx = con.execute(f"SELECT count(*) FROM read_parquet('{tx_grouped_file.as_posix()}')").fetchone()[0]
    total_descs = len(con.execute(f"SELECT desc_norm_id FROM read_parquet('{unique_desc_file.as_posix()}')").fetchall())

    for lvl_name, col_name in levels:
        row = con.execute(f"""
            WITH conflict_summary AS (
                SELECT 
                    desc_norm_id,
                    n_transactions,
                    ({col_name} > 1) AS is_conflict
                FROM read_parquet('{unique_desc_file.as_posix()}')
            )
            SELECT 
                '{lvl_name}' AS hierarchy_level,
                count(*) AS total_descriptions,
                sum(CASE WHEN is_conflict THEN 1 ELSE 0 END) AS n_conflicting_descs,
                round(sum(CASE WHEN is_conflict THEN 1.0 ELSE 0.0 END) * 100.0 / count(*), 4) AS pct_conflict_all_descs,
                sum(CASE WHEN is_conflict AND n_transactions >= 2 THEN 1 ELSE 0 END) AS n_conflict_ge_2,
                round(sum(CASE WHEN is_conflict AND n_transactions >= 2 THEN 1.0 ELSE 0.0 END) * 100.0 / 
                      nullif(sum(CASE WHEN n_transactions >= 2 THEN 1 ELSE 0 END), 0), 4) AS pct_conflict_ge_2_descs,
                sum(CASE WHEN is_conflict THEN n_transactions ELSE 0 END) AS n_conflicting_transactions,
                round(sum(CASE WHEN is_conflict THEN n_transactions * 1.0 ELSE 0.0 END) * 100.0 / {total_tx}, 4) AS pct_conflicting_transactions
            FROM conflict_summary
        """).df()
        conflict_records.append(row)

    conflict_df = pd.concat(conflict_records, ignore_index=True)
    conflict_df.to_csv(report_csv, index=False)
    print(f"Saved {report_csv.name}:")
    print(conflict_df.to_string(index=False))

    # 3. Frequency Distribution of n_transactions (1, 2-5, 6+)
    print("\nTransaction Frequency Distribution:")
    freq_df = con.execute(f"""
        SELECT 
            freq_bucket,
            count(*) AS n_descriptions,
            round(count(*) * 100.0 / sum(count(*)) OVER (), 4) AS pct_descriptions,
            sum(n_transactions) AS n_transactions,
            round(sum(n_transactions) * 100.0 / sum(sum(n_transactions)) OVER (), 4) AS pct_transactions
        FROM (
            SELECT 
                desc_norm_id,
                n_transactions,
                CASE 
                    WHEN n_transactions = 1 THEN '1 tx'
                    WHEN n_transactions BETWEEN 2 AND 5 THEN '2-5 tx'
                    ELSE '6+ tx'
                END AS freq_bucket
            FROM read_parquet('{unique_desc_file.as_posix()}')
        )
        GROUP BY freq_bucket
        ORDER BY min(n_transactions)
    """).df()
    print(freq_df.to_string(index=False))

    # 4. Top 20 Largest Level-2 Groups
    print("\nAuditing top 20 largest Level-2 groups...")
    top_groups = con.execute(f"""
        WITH l2_sizes AS (
            SELECT 
                group_l2,
                count(*) AS n_l1_descriptions,
                sum(n_transactions) AS total_transactions
            FROM read_parquet('{unique_desc_file.as_posix()}')
            GROUP BY group_l2
            ORDER BY total_transactions DESC
            LIMIT 20
        ),
        top_descs AS (
            SELECT 
                u.group_l2,
                n.desc_norm,
                u.n_transactions,
                row_number() OVER (PARTITION BY u.group_l2 ORDER BY u.n_transactions DESC) as rnk
            FROM read_parquet('{unique_desc_file.as_posix()}') u
            INNER JOIN read_parquet('{norm_desc_file.as_posix()}') n
                ON u.desc_norm_id = n.desc_norm_id
            WHERE u.group_l2 IN (SELECT group_l2 FROM l2_sizes)
        )
        SELECT 
            s.group_l2,
            s.n_l1_descriptions,
            s.total_transactions,
            round(s.total_transactions * 100.0 / {total_tx}, 4) AS pct_in_scope_tx,
            string_agg(CASE WHEN d.rnk <= 3 THEN d.desc_norm || ' (' || d.n_transactions || ')' END, ' | ') AS top_3_descriptions
        FROM l2_sizes s
        LEFT JOIN top_descs d ON s.group_l2 = d.group_l2
        GROUP BY s.group_l2, s.n_l1_descriptions, s.total_transactions
        ORDER BY s.total_transactions DESC
    """).df()

    top_groups.to_csv(top_groups_csv, index=False)
    print(f"Saved {top_groups_csv.name}:")
    print(top_groups[["group_l2", "n_l1_descriptions", "total_transactions", "pct_in_scope_tx"]].head(10).to_string(index=False))

    largest_share = top_groups["pct_in_scope_tx"].max()
    print(f"\nLargest group share of in-scope transactions: {largest_share:.4f}%")


def main():
    params = load_params()
    con, _ = get_connection(params)

    interim_dir = ROOT / params["paths"]["interim_dir"]
    processed_dir = ROOT / params["paths"]["processed_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

    processed_dir.mkdir(parents=True, exist_ok=True)

    scope_file = interim_dir / "transactions_scope.parquet"
    norm_desc_file = interim_dir / "norm_descriptions.parquet"
    skeleton_parts_dir = interim_dir / "skeleton_parts"

    unique_desc_file = processed_dir / "unique_descriptions.parquet"
    tx_grouped_file = processed_dir / "transactions_grouped.parquet"

    norm_buckets = params.get("norm_buckets", 16)
    chunk_size = params.get("chunk_size", 500000)

    try:
        stage_1_build_skeleton_parts(con, norm_desc_file, scope_file, skeleton_parts_dir, norm_buckets, chunk_size)
        stage_2_build_unique_descriptions(con, scope_file, skeleton_parts_dir, unique_desc_file, norm_buckets)
        stage_3_build_transactions_grouped(con, scope_file, skeleton_parts_dir, tx_grouped_file, norm_buckets)
        stage_4_conflict_preview(con, unique_desc_file, tx_grouped_file, norm_desc_file, tables_dir, norm_buckets)
        print("\nTrack A7 pipeline execution completed successfully.")
    finally:
        con.close()


if __name__ == "__main__":
    main()