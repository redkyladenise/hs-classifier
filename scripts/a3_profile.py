"""Track A3: Data Profiling Pipeline.

Measures characteristics of transactions_slim.parquet without dropping data.
Uses 16 hash buckets to compute distinct description counts, top-N items,
and weighted words within the 0.6 GB RAM ceiling.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.io import get_connection, load_params

NUM_BUCKETS = 16


def stage_0_build_buckets(con, slim_file: Path, bucket_dir: Path) -> int:
    """Group descriptions into 16 hash buckets and count null descriptions."""
    bucket_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n--- Stage 0: Building Description Counts in {NUM_BUCKETS} Buckets ---")

    null_count_query = f"""
        SELECT count(*) 
        FROM read_parquet('{slim_file.as_posix()}') 
        WHERE goods_description IS NULL
    """
    null_count = con.execute(null_count_query).fetchone()[0]
    print(f"Null goods descriptions count: {null_count:,}")

    for b in range(NUM_BUCKETS):
        part_file = bucket_dir / f"part_{b:02d}.parquet"
        if part_file.exists():
            print(f"[Bucket {b:02d}/{NUM_BUCKETS-1}] Already exists: {part_file.name}. Skipping.")
            continue

        print(f"[Bucket {b:02d}/{NUM_BUCKETS-1}] Aggregating into {part_file.name}...")
        start_t = time.time()
        query = f"""
            COPY (
                SELECT 
                    goods_description,
                    count(*)::BIGINT AS n_transactions
                FROM read_parquet('{slim_file.as_posix()}')
                WHERE goods_description IS NOT NULL
                  AND abs(hash(goods_description)) % {NUM_BUCKETS} = {b}
                GROUP BY goods_description
            ) TO '{part_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
        """
        con.execute(query)
        elapsed = time.time() - start_t
        print(f"[Bucket {b:02d}] Finished in {elapsed:.1f}s.")

    return null_count


def stage_1_single_pass_profiling(con, slim_file: Path, tables_dir: Path):
    """Compute transaction volumes, null/code checks, digit lengths, and text quantiles."""
    tables_dir.mkdir(parents=True, exist_ok=True)
    print("\n--- Stage 1: Single-Pass Profiling Queries ---")

    # 1. Rows per year and month
    out_ym = tables_dir / "a3_rows_by_year_month.csv"
    if not out_ym.exists():
        print("Generating a3_rows_by_year_month.csv...")
        con.execute(f"""
            COPY (
                SELECT 
                    year, 
                    month, 
                    count(*) AS n_transactions
                FROM read_parquet('{slim_file.as_posix()}')
                GROUP BY year, month
                ORDER BY year, month
            ) TO '{out_ym.as_posix()}' (HEADER, DELIMITER ',');
        """)

    # 2. Null, zero, and negative checks
    out_audit = tables_dir / "a3_null_zero_negative_audit.csv"
    if not out_audit.exists():
        print("Generating a3_null_zero_negative_audit.csv...")
        con.execute(f"""
            COPY (
                SELECT 
                    year,
                    count(*) AS total_rows,
                    count(CASE WHEN goods_description IS NULL THEN 1 END) AS null_descriptions,
                    count(CASE WHEN hs_code IS NULL THEN 1 END) AS null_hs_codes,
                    count(CASE WHEN TRY_CAST(hs_code AS BIGINT) = 0 THEN 1 END) AS zero_codes,
                    count(CASE WHEN TRY_CAST(hs_code AS BIGINT) < 0 THEN 1 END) AS negative_codes
                FROM read_parquet('{slim_file.as_posix()}')
                GROUP BY year
                ORDER BY year
            ) TO '{out_audit.as_posix()}' (HEADER, DELIMITER ',');
        """)

    # 3. Code digit-length distribution
    out_digits = tables_dir / "a3_code_digit_distribution.csv"
    if not out_digits.exists():
        print("Generating a3_code_digit_distribution.csv...")
        con.execute(f"""
            COPY (
                SELECT 
                    year,
                    length(hs_code) AS digit_length,
                    count(*) AS n_transactions,
                    round(count(*) * 100.0 / sum(count(*)) OVER (PARTITION BY year), 4) AS pct_of_year
                FROM read_parquet('{slim_file.as_posix()}')
                GROUP BY year, length(hs_code)
                ORDER BY year, digit_length
            ) TO '{out_digits.as_posix()}' (HEADER, DELIMITER ',');
        """)

    # 4. Description length quantiles per year
    out_quantiles = tables_dir / "a3_description_length_quantiles.csv"
    if not out_quantiles.exists():
        print("Generating a3_description_length_quantiles.csv...")
        con.execute(f"""
            COPY (
                WITH text_metrics AS (
                    SELECT 
                        year,
                        length(goods_description) AS char_len,
                        array_length(str_split_regex(trim(goods_description), '\\s+')) AS word_count
                    FROM read_parquet('{slim_file.as_posix()}')
                    WHERE goods_description IS NOT NULL
                )
                SELECT 
                    year,
                    min(char_len) AS min_chars,
                    approx_quantile(char_len, 0.5) AS approx_median_chars,
                    approx_quantile(char_len, 0.95) AS approx_p95_chars,
                    max(char_len) AS max_chars,
                    min(word_count) AS min_words,
                    approx_quantile(word_count, 0.5) AS approx_median_words,
                    approx_quantile(word_count, 0.95) AS approx_p95_words,
                    max(word_count) AS max_words,
                    round(count(CASE WHEN word_count <= 2 THEN 1 END) * 100.0 / count(*), 4) AS pct_two_words_or_fewer
                FROM text_metrics
                GROUP BY year
                ORDER BY year
            ) TO '{out_quantiles.as_posix()}' (HEADER, DELIMITER ',');
        """)


def stage_2_bucket_profiling(con, slim_file: Path, bucket_dir: Path, tables_dir: Path, params: dict):
    """Aggregate over bucket files to compute distinct counts, top descriptions, placeholders, and words."""
    print("\n--- Stage 2: Bucket Aggregation Profiling ---")
    bucket_glob = (bucket_dir / "part_*.parquet").as_posix()

    # 1. Distinct raw descriptions: per year (separate query per year) + overall from buckets
    out_distinct = tables_dir / "a3_distinct_descriptions.csv"
    if not out_distinct.exists():
        print("Calculating distinct descriptions (per year and overall)...")
        years = params.get("train_years", [2023, 2024]) + [params.get("final_test_year", 2025)]
        yearly_counts = {}
        for y in years:
            print(f"Counting distinct descriptions for {y}...")
            cnt = con.execute(f"""
                SELECT count(DISTINCT goods_description)
                FROM read_parquet('{slim_file.as_posix()}')
                WHERE year = {y} AND goods_description IS NOT NULL
            """).fetchone()[0]
            yearly_counts[y] = cnt

        # Total distinct across buckets
        print("Summing distinct counts across buckets...")
        total_distinct = con.execute(f"""
            SELECT count(*) FROM read_parquet('{bucket_glob}')
        """).fetchone()[0]

        max_yearly = max(yearly_counts.values())
        sum_yearly = sum(yearly_counts.values())

        # Perform Sanity Check: max_yearly <= total_distinct <= sum_yearly
        print(f"Sanity check: {max_yearly:,} <= {total_distinct:,} <= {sum_yearly:,}")
        assert max_yearly <= total_distinct <= sum_yearly, "Sanity check on distinct counts failed!"

        # Write distinct counts to CSV
        with open(out_distinct, "w", encoding="utf-8") as f:
            f.write("metric,count\n")
            for y, c in yearly_counts.items():
                f.write(f"distinct_{y},{c}\n")
            f.write(f"distinct_overall,{total_distinct}\n")
            f.write(f"max_yearly,{max_yearly}\n")
            f.write(f"sum_yearly,{sum_yearly}\n")
            f.write("sanity_check_passed,True\n")
        print(f"Written to {out_distinct.name}.")

    # 2. Placeholder descriptions: 50 most common <= 3 chars
    out_placeholders = tables_dir / "a3_placeholder_candidates.csv"
    if not out_placeholders.exists():
        print("Generating a3_placeholder_candidates.csv...")
        con.execute(f"""
            COPY (
                SELECT 
                    goods_description,
                    sum(n_transactions)::BIGINT AS total_transactions
                FROM read_parquet('{bucket_glob}')
                WHERE length(goods_description) <= 3
                GROUP BY goods_description
                ORDER BY total_transactions DESC
                LIMIT 50
            ) TO '{out_placeholders.as_posix()}' (HEADER, DELIMITER ',');
        """)

    # 3. Top 50 frequent descriptions & Top 1000 coverage
    out_top_desc = tables_dir / "a3_top_descriptions.csv"
    if not out_top_desc.exists():
        print("Generating a3_top_descriptions.csv...")
        # Step A: extract top 1,000 from each bucket, combine, and take global top 1,000
        con.execute(f"""
            CREATE TEMPORARY TABLE top_1000_candidates AS
            SELECT goods_description, n_transactions
            FROM (
                SELECT 
                    goods_description, 
                    n_transactions,
                    row_number() OVER (PARTITION BY abs(hash(goods_description)) % {NUM_BUCKETS} ORDER BY n_transactions DESC) AS rank
                FROM read_parquet('{bucket_glob}')
            )
            WHERE rank <= 1000;
        """)

        con.execute(f"""
            CREATE TEMPORARY TABLE global_top_1000 AS
            SELECT goods_description, n_transactions
            FROM top_1000_candidates
            ORDER BY n_transactions DESC
            LIMIT 1000;
        """)

        # Total transaction count for percentages
        total_tx = 26889707

        con.execute(f"""
            COPY (
                WITH ranked AS (
                    SELECT 
                        row_number() OVER (ORDER BY n_transactions DESC) AS rank,
                        goods_description,
                        n_transactions,
                        round(n_transactions * 100.0 / {total_tx}, 4) AS pct_of_all_transactions,
                        round(sum(n_transactions) OVER (ORDER BY n_transactions DESC) * 100.0 / {total_tx}, 4) AS cumulative_pct
                    FROM global_top_1000
                )
                SELECT * FROM ranked WHERE rank <= 50
            ) TO '{out_top_desc.as_posix()}' (HEADER, DELIMITER ',');
        """)

        top_1000_sum = con.execute("SELECT sum(n_transactions) FROM global_top_1000").fetchone()[0]
        top_1000_pct = (top_1000_sum * 100.0) / total_tx
        print(f"Top 1,000 descriptions account for {top_1000_sum:,} transactions ({top_1000_pct:.2f}% of all transactions).")

    # 4. Top 100 most frequent words (weighted by n_transactions over distinct descriptions)
    out_words = tables_dir / "a3_top_words_weighted.csv"
    if not out_words.exists():
        print("Extracting top 100 words weighted by description frequency...")
        # Unnest words from distinct descriptions, group with weight n_transactions, take top 100
        con.execute(f"""
            COPY (
                WITH unnested_words AS (
                    SELECT 
                        lower(unnest(str_split_regex(trim(goods_description), '[\\s,.-]+'))) AS word,
                        n_transactions
                    FROM read_parquet('{bucket_glob}')
                    WHERE goods_description IS NOT NULL
                )
                SELECT 
                    word,
                    sum(n_transactions)::BIGINT AS total_occurrences
                FROM unnested_words
                WHERE length(word) >= 2
                GROUP BY word
                ORDER BY total_occurrences DESC
                LIMIT 100
            ) TO '{out_words.as_posix()}' (HEADER, DELIMITER ',');
        """)
        print(f"Written to {out_words.name}.")


def main():
    params = load_params()
    con, _ = get_connection(params)

    interim_dir = ROOT / params["paths"]["interim_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"
    slim_file = interim_dir / "transactions_slim.parquet"
    bucket_dir = interim_dir / "raw_desc_counts"

    if not slim_file.exists():
        raise FileNotFoundError(f"transactions_slim.parquet not found at {slim_file}")

    try:
        null_count = stage_0_build_buckets(con, slim_file, bucket_dir)
        stage_1_single_pass_profiling(con, slim_file, tables_dir)
        stage_2_bucket_profiling(con, slim_file, bucket_dir, tables_dir, params)
        print("\nAll Track A3 Profiling Tables Generated Successfully.")
    finally:
        con.close()


if __name__ == "__main__":
    main()