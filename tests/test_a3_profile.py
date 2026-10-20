"""Validation script for Track A3: Data Profiling."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.io import get_connection, load_params


def validate_a3():
    params = load_params()
    con, _ = get_connection(params)

    bucket_dir = ROOT / params["paths"]["interim_dir"] / "raw_desc_counts"
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"
    bucket_glob = (bucket_dir / "part_*.parquet").as_posix()

    print("========================================")
    print(" TRACK A3 VALIDATION AUDIT")
    print("========================================\n")

    # 1. Verify 16 bucket files exist
    parts = list(bucket_dir.glob("part_*.parquet"))
    print(f"1. Checking bucket parts: Found {len(parts)} files (Expected: 16)...")
    assert len(parts) == 16, f"Expected 16 bucket parts, found {len(parts)}"
    print("   -> Bucket count: [PASS]")

    # 2. Check total transactions sum across buckets equals 26,889,707
    total_tx_query = f"SELECT sum(n_transactions)::BIGINT FROM read_parquet('{bucket_glob}')"
    sum_tx = con.execute(total_tx_query).fetchone()[0]
    expected_tx = sum(params["expected_rows_by_year"].values())
    print(f"\n2. Total transactions across buckets: {sum_tx:,} (Expected: {expected_tx:,})")
    assert sum_tx == expected_tx, f"Transaction count mismatch: got {sum_tx}, expected {expected_tx}"
    print("   -> Transaction sum: [PASS]")

    # 3. Check distinct descriptions count sanity bounds
    total_distinct = con.execute(f"SELECT count(*) FROM read_parquet('{bucket_glob}')").fetchone()[0]
    print(f"\n3. Total distinct descriptions: {total_distinct:,}")
    assert total_distinct == 16757438, f"Unexpected distinct count: {total_distinct}"
    print("   -> Distinct count: [PASS]")

    # 4. Verify all expected CSV reports exist
    required_csvs = [
        "a3_rows_by_year_month.csv",
        "a3_null_zero_negative_audit.csv",
        "a3_code_digit_distribution.csv",
        "a3_description_length_quantiles.csv",
        "a3_distinct_descriptions.csv",
        "a3_placeholder_candidates.csv",
        "a3_top_descriptions.csv",
        "a3_top_words_weighted.csv",
    ]
    print("\n4. Checking required CSV tables in reports/tables/:")
    for csv_name in required_csvs:
        f = tables_dir / csv_name
        assert f.exists(), f"Missing CSV: {csv_name}"
        print(f"   - {csv_name}: Exists [PASS]")

    print("\n========================================")
    print(" ALL A3 VALIDATION CRITERIA PASSED")
    print("========================================")
    con.close()


if __name__ == "__main__":
    validate_a3()