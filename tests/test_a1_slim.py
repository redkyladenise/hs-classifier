"""Validation script for Track A1: Slim transactions file."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.io import get_connection, load_params


def validate_a1():
    params = load_params()
    con, _ = get_connection(params)

    expected_rows = params["expected_rows_by_year"]
    total_expected = sum(expected_rows.values())

    slim_dir = ROOT / params["paths"]["interim_dir"] / "slim_by_year"
    combined_file = ROOT / params["paths"]["interim_dir"] / "transactions_slim.parquet"

    print("========================================")
    print(" TRACK A1 VALIDATION AUDIT")
    print("========================================\n")

    # 1. Validate Yearly Files
    print("1. Checking yearly slim files...")
    for year, exp_count in expected_rows.items():
        year_file = slim_dir / f"slim_{year}.parquet"
        assert year_file.exists(), f"Missing yearly file: {year_file}"
        
        count = con.execute(f"SELECT count(*) FROM read_parquet('{year_file.as_posix()}')").fetchone()[0]
        status = "PASS" if count == exp_count else "FAIL"
        print(f"   - Year {year}: {count:,} rows (Expected: {exp_count:,}) -> [{status}]")
        assert count == exp_count, f"Row count mismatch for {year}: got {count}, expected {exp_count}"

    # 2. Check Combined File Existence and Schema
    print("\n2. Checking combined transactions_slim.parquet schema...")
    assert combined_file.exists(), f"Missing combined file: {combined_file}"

    schema_info = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{combined_file.as_posix()}')").fetchall()
    columns_found = {row[0]: row[1] for row in schema_info}
    expected_cols = ["row_id", "year", "month", "goods_description", "hs_code"]

    print(f"   Columns found: {list(columns_found.keys())}")
    for col in expected_cols:
        assert col in columns_found, f"Missing expected column: {col}"
    assert len(columns_found) == 5, f"Expected 5 columns, found {len(columns_found)}: {columns_found}"

    # Verify hs_code is VARCHAR
    hs_type = columns_found["hs_code"]
    print(f"   hs_code data type: {hs_type}")
    assert hs_type.upper() in ["VARCHAR", "TEXT", "STRING"], f"hs_code is not text! Got {hs_type}"
    print("   -> Schema check: [PASS]")

    # 3. Check Combined Total and Row ID Uniqueness
    print("\n3. Checking total row count and row_id uniqueness...")
    query = f"""
        SELECT 
            count(*) AS total_rows,
            count(DISTINCT row_id) AS unique_ids,
            count(CASE WHEN hs_code IS NULL THEN 1 END) AS null_codes,
            count(CASE WHEN goods_description IS NULL THEN 1 END) AS null_descriptions
        FROM read_parquet('{combined_file.as_posix()}')
    """
    stats = con.execute(query).fetchone()
    total_rows, unique_ids, null_codes, null_desc = stats

    print(f"   Total rows: {total_rows:,} (Expected: {total_expected:,})")
    print(f"   Unique row_id count: {unique_ids:,}")
    print(f"   Null HS codes: {null_codes:,}")
    print(f"   Null goods descriptions: {null_desc:,}")

    assert total_rows == total_expected, f"Total rows mismatch: got {total_rows}, expected {total_expected}"
    assert unique_ids == total_rows, f"Duplicate row_ids found! Unique: {unique_ids}, Total: {total_rows}"
    print("   -> Uniqueness & Count check: [PASS]")

    # Sample rows display
    print("\n4. Sample records (first 3 rows):")
    sample = con.execute(
        f"SELECT row_id, year, month, hs_code, substring(goods_description, 1, 40) AS desc "
        f"FROM read_parquet('{combined_file.as_posix()}') LIMIT 3"
    ).fetchall()
    for s in sample:
        print(f"   {s}")

    print("\n========================================")
    print(" ALL A1 VALIDATION CRITERIA PASSED")
    print("========================================")
    con.close()


if __name__ == "__main__":
    validate_a1()