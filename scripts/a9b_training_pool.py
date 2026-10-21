"""Track A9b: Measure and Set Training Cap & Pre-Training Leakage Probe.

Constructs the hierarchical training pool with deterministic nested ranks (main and y1),
evaluates temporal group additions across 2023-2024, and executes a TF-IDF cosine similarity
leakage probe across test, val, and train partitions.
"""

import sys
import time
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.group_split import hash_group_seed
from src.hsclf.data.io import get_connection, load_params


def stage_1_temporal_group_audit(con, tx_file: Path, split_file: Path):
    """Measure temporal group contributions and longevity across 2023-2025."""
    print("\n--- Stage 1: Temporal Group Contribution Audit ---")
    start_t = time.time()

    audit_query = f"""
        WITH train_groups AS (
            SELECT group_l2 
            FROM read_parquet('{split_file.as_posix()}')
            WHERE split = 'train'
        ),
        group_years AS (
            SELECT 
                t.group_l2,
                bool_or(t.year = 2023) AS in_2023,
                bool_or(t.year = 2024) AS in_2024,
                bool_or(t.year = 2025) AS in_2025
            FROM read_parquet('{tx_file.as_posix()}') t
            INNER JOIN train_groups tg ON t.group_l2 = tg.group_l2
            GROUP BY t.group_l2
        )
        SELECT 
            count(CASE WHEN in_2023 THEN 1 END) AS n_groups_2023,
            count(CASE WHEN in_2024 THEN 1 END) AS n_groups_2024,
            count(CASE WHEN in_2023 AND NOT in_2024 AND NOT in_2025 THEN 1 END) AS n_2023_only,
            round(count(CASE WHEN in_2023 AND NOT in_2024 AND NOT in_2025 THEN 1 END) * 100.0 / 
                  count(CASE WHEN in_2023 THEN 1 END), 4) AS pct_2023_dropped,
            count(CASE WHEN in_2024 AND NOT in_2023 THEN 1 END) AS n_2024_new,
            round(count(CASE WHEN in_2024 AND NOT in_2023 THEN 1 END) * 100.0 / 
                  count(CASE WHEN in_2024 THEN 1 END), 4) AS pct_2024_new
        FROM group_years;
    """
    df_temporal = con.execute(audit_query).df()
    print(df_temporal.to_string(index=False))
    print(f"Temporal group audit completed in {time.time() - start_t:.1f}s.")
    return df_temporal


def stage_2_build_training_pool(con, tx_file: Path, split_file: Path, desc_file: Path, elig_file: Path, output_file: Path, seed: int):
    """Assign hierarchical cap keys and compute nested deterministic ranks for main and y1."""
    print("\n--- Stage 2: Constructing Hierarchical Training Pool ---")
    start_t = time.time()

    print("Querying training descriptions and mapping hierarchical cap keys...")
    query = f"""
        WITH train_groups AS (
            SELECT group_l2 
            FROM read_parquet('{split_file.as_posix()}')
            WHERE split = 'train'
        ),
        -- Filter unique descriptions belonging to train groups
        train_descs AS (
            SELECT 
                u.desc_norm_id AS group_l1,
                u.group_l2,
                u.majority_ahtn8,
                SUBSTRING(u.majority_ahtn8, 1, 6) AS majority_sh6,
                SUBSTRING(u.majority_ahtn8, 1, 4) AS majority_hd4,
                SUBSTRING(u.majority_ahtn8, 1, 2) AS majority_ch2,
                u.first_year,
                u.last_year
            FROM read_parquet('{desc_file.as_posix()}') u
            INNER JOIN train_groups tg ON u.group_l2 = tg.group_l2
        ),
        -- Load eligibility lookup tables for main scenario
        elig_main AS (
            SELECT level, class
            FROM read_parquet('{elig_file.as_posix()}')
            WHERE scenario = 'main' AND eligible_at_20
        ),
        -- Descriptions active in y1 training (2023 tx in train groups)
        y1_active_descs AS (
            SELECT DISTINCT t.group_l1
            FROM read_parquet('{tx_file.as_posix()}') t
            INNER JOIN train_groups tg ON t.group_l2 = tg.group_l2
            WHERE t.year = 2023
        ),
        -- Descriptions active in main training (2023-2024 tx in train groups)
        main_active_descs AS (
            SELECT DISTINCT t.group_l1
            FROM read_parquet('{tx_file.as_posix()}') t
            INNER JOIN train_groups tg ON t.group_l2 = tg.group_l2
            WHERE t.year IN (2023, 2024)
        )
        SELECT 
            td.group_l1,
            td.group_l2,
            CASE 
                WHEN e8.class IS NOT NULL THEN td.majority_ahtn8
                WHEN e6.class IS NOT NULL THEN td.majority_sh6
                WHEN e4.class IS NOT NULL THEN td.majority_hd4
                WHEN e2.class IS NOT NULL THEN td.majority_ch2
                ELSE 'excluded'
            END AS cap_key,
            (mad.group_l1 IS NOT NULL) AS in_main,
            (yad.group_l1 IS NOT NULL) AS in_y1
        FROM train_descs td
        LEFT JOIN elig_main e8 ON e8.level = 8 AND e8.class = td.majority_ahtn8
        LEFT JOIN elig_main e6 ON e6.level = 6 AND e6.class = td.majority_sh6
        LEFT JOIN elig_main e4 ON e4.level = 4 AND e4.class = td.majority_hd4
        LEFT JOIN elig_main e2 ON e2.level = 2 AND e2.class = td.majority_ch2
        LEFT JOIN main_active_descs mad ON td.group_l1 = mad.group_l1
        LEFT JOIN y1_active_descs yad ON td.group_l1 = yad.group_l1
        WHERE (mad.group_l1 IS NOT NULL) OR (yad.group_l1 IS NOT NULL);
    """
    df_pool = con.execute(query).df()
    print(f"Total active candidate training descriptions: {len(df_pool):,}")

    # Compute deterministic integer mix hash for ranking
    print("Computing deterministic integer mixing hashes for ranking...")
    df_pool["mix_hash"] = [hash_group_seed(gid, seed) for gid in df_pool["group_l1"]]

    # Rank within cap_key for main scenario
    print("Computing ranks for 'main' scenario...")
    df_main = df_pool[df_pool["in_main"]].copy()
    df_main["rank_main"] = (
        df_main.groupby("cap_key")["mix_hash"]
        .rank(method="first", ascending=True)
        .astype(int)
    )

    # Rank within cap_key for y1 scenario
    print("Computing ranks for 'y1' scenario...")
    df_y1 = df_pool[df_pool["in_y1"]].copy()
    df_y1["rank_y1"] = (
        df_y1.groupby("cap_key")["mix_hash"]
        .rank(method="first", ascending=True)
        .astype(int)
    )

    # Merge ranks back
    df_pool = df_pool.merge(df_main[["group_l1", "rank_main"]], on="group_l1", how="left")
    df_pool = df_pool.merge(df_y1[["group_l1", "rank_y1"]], on="group_l1", how="left")

    df_pool["rank_main"] = df_pool["rank_main"].fillna(-1).astype(int)
    df_pool["rank_y1"] = df_y1_ranks = df_pool["rank_y1"].fillna(-1).astype(int)

    final_pool = df_pool[["group_l1", "cap_key", "rank_main", "rank_y1"]].copy()

    # Save to Parquet
    schema = pa.schema([
        ("group_l1", pa.int64()),
        ("cap_key", pa.string()),
        ("rank_main", pa.int32()),
        ("rank_y1", pa.int32()),
    ])
    table = pa.Table.from_pandas(final_pool, schema=schema, preserve_index=False)
    pq.write_table(table, output_file, compression="ZSTD")
    print(f"Saved {output_file.name} ({len(final_pool):,} descriptions) in {time.time() - start_t:.1f}s.")
    return final_pool


def stage_3_cap_summary_report(pool_df: pd.DataFrame, tables_dir: Path):
    """Compute and export pool sizes across cap thresholds N = [10, 20, 50, 100, 200, 500]."""
    print("\n--- Stage 3: Compiling Cap Summary Ladder Report ---")
    tables_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = tables_dir / "a9b_cap_summary.csv"

    thresholds = [10, 20, 50, 100, 200, 500]
    records = []

    for n in thresholds:
        main_size = (pool_df["rank_main"] > 0) & (pool_df["rank_main"] <= n)
        y1_size = (pool_df["rank_y1"] > 0) & (pool_df["rank_y1"] <= n)
        records.append({
            "cap_per_code_N": n,
            "main_pool_size": int(main_size.sum()),
            "y1_pool_size": int(y1_size.sum()),
        })

    records.append({
        "cap_per_code_N": "Full (Uncapped)",
        "main_pool_size": int((pool_df["rank_main"] > 0).sum()),
        "y1_pool_size": int((pool_df["rank_y1"] > 0).sum()),
    })

    summary_df = pd.DataFrame(records)
    summary_df.to_csv(summary_csv, index=False)
    print(summary_df.to_string(index=False))
    print(f"Saved {summary_csv.name}.")
    return summary_df

def stage_4_leakage_probe(con, pool_file: Path, desc_status_file: Path, norm_file: Path, tx_file: Path, tables_dir: Path, sample_size: int, seed: int):
    """Execute chapter-stratified TF-IDF cosine similarity leakage probe."""
    print(f"\n--- Stage 4: Executing Pre-Training Leakage Probe (Sample Size = {sample_size}) ---")
    start_t = time.time()
    probe_csv = tables_dir / "a9b_leakage_probe.csv"

    # Query distinct normalized texts with chapter and split
    # 'largest pool' uses the training pool (main scenario)
    print("Loading normalized text sample and training corpus...")
    corpus_query = f"""
        WITH sample_descs AS (
            SELECT 
                n.desc_norm_id,
                n.desc_norm,
                s.split,
                t.ch2 AS chapter,
                COALESCE(p.rank_main, -1) AS rank_main
            FROM read_parquet('{norm_file.as_posix()}') n
            INNER JOIN read_parquet('{desc_status_file.as_posix()}') s
                ON n.desc_norm_id = s.group_l1
            LEFT JOIN read_parquet('{pool_file.as_posix()}') p
                ON n.desc_norm_id = p.group_l1
            INNER JOIN (
                SELECT group_l1, min(ch2) AS ch2
                FROM read_parquet('{tx_file.as_posix()}')
                GROUP BY group_l1
            ) t ON n.desc_norm_id = t.group_l1
        )
        SELECT * FROM sample_descs;
    """
    corpus_df = con.execute(corpus_query).df()
    print(f"Total corpus loaded: {len(corpus_df):,} descriptions.")

    np.random.seed(seed)
    chapters = sorted(corpus_df["chapter"].unique())
    per_ch_sample = sample_size // len(chapters)

    probe_results = []
    comparisons = ["test_vs_train", "val_vs_train", "train_vs_train"]

    for comp in comparisons:
        all_max_sims = []
        print(f"  Evaluating comparison: {comp}...")

        for ch in chapters:
            ch_df = corpus_df[corpus_df["chapter"] == ch]
            # Largest pool for training: active main training pool (rank_main > 0)
            train_pool_ch = ch_df[ch_df["rank_main"] > 0]

            if comp == "test_vs_train":
                query_pool = ch_df[ch_df["split"] == "test"]
            elif comp == "val_vs_train":
                query_pool = ch_df[ch_df["split"] == "val"]
            else:  # train_vs_train
                query_pool = train_pool_ch

            if len(query_pool) == 0 or len(train_pool_ch) == 0:
                continue

            # Stratified sample
            n_sample = min(per_ch_sample, len(query_pool))
            sampled_query = query_pool.sample(n=n_sample, random_state=seed)

            # Fit TF-IDF on chapter training pool
            vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b", max_features=50000)
            X_train = vectorizer.fit_transform(train_pool_ch["desc_norm"].astype(str))
            X_query = vectorizer.transform(sampled_query["desc_norm"].astype(str))

            sim_matrix = cosine_similarity(X_query, X_train)

            if comp == "train_vs_train":
                np.fill_diagonal(sim_matrix, 0.0)

            max_sims = np.max(sim_matrix, axis=1)
            all_max_sims.extend(max_sims)

        all_max_sims = np.array(all_max_sims)
        total_eval = len(all_max_sims)
        pct_80 = (all_max_sims >= 0.80).sum() * 100.0 / total_eval
        pct_90 = (all_max_sims >= 0.90).sum() * 100.0 / total_eval
        pct_95 = (all_max_sims >= 0.95).sum() * 100.0 / total_eval

        probe_results.append({
            "comparison": comp,
            "sample_size": total_eval,
            "mean_max_similarity": round(float(np.mean(all_max_sims)), 4),
            "pct_ge_0_80": round(float(pct_80), 4),
            "pct_ge_0_90": round(float(pct_90), 4),
            "pct_ge_0_95": round(float(pct_95), 4),
        })

    probe_df = pd.DataFrame(probe_results)
    probe_df.to_csv(probe_csv, index=False)
    print("\nLeakage Probe Results:")
    print(probe_df.to_string(index=False))
    print(f"Saved {probe_csv.name} in {time.time() - start_t:.1f}s.")
    return probe_df

def main():
    params = load_params()
    con, _ = get_connection(params)

    processed_dir = ROOT / params["paths"]["processed_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

    tx_file = processed_dir / "transactions_grouped.parquet"
    split_file = processed_dir / "split_assignments.parquet"
    desc_file = processed_dir / "unique_descriptions.parquet"
    norm_file = ROOT / "data" / "interim" / "norm_descriptions.parquet"
    desc_status_file = processed_dir / "description_status.parquet"
    elig_file = processed_dir / "class_eligibility.parquet"
    pool_file = processed_dir / "training_pool.parquet"

    seed = params.get("random_seed", 42)
    sample_size = params.get("leakage_probe_sample", 2000)

    try:
        stage_1_temporal_group_audit(con, tx_file, split_file)
        pool_df = stage_2_build_training_pool(con, tx_file, split_file, desc_file, elig_file, pool_file, seed)
        stage_3_cap_summary_report(pool_df, tables_dir)
        stage_4_leakage_probe(con, pool_file, desc_status_file, norm_file, tx_file, tables_dir, sample_size, seed)
        print("\nTrack A9b pipeline completed successfully.")
    finally:
        con.close()


if __name__ == "__main__":
    main()