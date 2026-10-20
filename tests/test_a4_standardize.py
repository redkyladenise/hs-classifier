"""Automated validation audit for Track A4: Code Standardization."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.io import get_connection, load_params


def test_track_a4_integrity():
    params = load_params()
    con, _ = get_connection(params)

    interim_dir = ROOT / params["paths"]["interim_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

    code_map_file = interim_dir / "code_map.parquet"
    codes_std_file = interim_dir / "codes_standardized.parquet"
    report_csv = tables_dir / "a4_code_fix_counts.csv"

    print("\n========================================")
    print(" TRACK A4 VALIDATION AUDIT")
    print("========================================\n")

    # 1. Verify required files exist
    assert code_map_file.exists(), f"Missing {code_map_file}"
    assert codes_std_file.exists(), f"Missing {codes_std_file}"
    assert report_csv.exists(), f"Missing {report_csv}"
    print("1. Artifact existence check: [PASS]")

    # 2. Verify code_map has unique rows per raw hs_code
    distinct_raw = con.execute(f"SELECT count(DISTINCT hs_code), count(*) FROM read_parquet('{code_map_file.as_posix()}')").fetchone()
    assert distinct_raw[0] == distinct_raw[1], f"Duplicate hs_codes in code_map: {distinct_raw}"
    print(f"2. code_map.parquet: {distinct_raw[0]:,} unique codes mapped cleanly: [PASS]")

    # 3. Verify total row count is exactly 26,889,707
    total_rows = con.execute(f"SELECT count(*) FROM read_parquet('{codes_std_file.as_posix()}')").fetchone()[0]
    expected_total = sum(params["expected_rows_by_year"].values())
    print(f"3. Total row count: {total_rows:,} (Expected: {expected_total:,})")
    assert total_rows == expected_total, f"Row count mismatch: got {total_rows}, expected {expected_total}"
    print("   -> Total row count: [PASS]")

    # 4. Verify per-year row counts match A1 exactly
    yearly_counts = con.execute(f"""
        SELECT year, count(*) 
        FROM read_parquet('{codes_std_file.as_posix()}') 
        GROUP BY year 
        ORDER BY year
    """).fetchall()

    for year, cnt in yearly_counts:
        exp = params["expected_rows_by_year"][year]
        print(f"   - Year {year}: {cnt:,} (Expected: {exp:,})")
        assert cnt == exp, f"Year {year} count mismatch: got {cnt}, expected {exp}"
    print("   -> Yearly breakdown: [PASS]")

    # 5. Verify 100% of rows have a non-null 8-digit AHTN code and code_flag is 'valid'
    flag_audit = con.execute(f"""
        SELECT 
            count(CASE WHEN ahtn8 IS NULL THEN 1 END) AS null_ahtn8,
            count(CASE WHEN length(ahtn8) != 8 THEN 1 END) AS bad_len_ahtn8,
            count(CASE WHEN code_flag != 'valid' THEN 1 END) AS non_valid_flags
        FROM read_parquet('{codes_std_file.as_posix()}')
    """).fetchone()

    assert flag_audit[0] == 0, f"Found {flag_audit[0]} null ahtn8 codes"
    assert flag_audit[1] == 0, f"Found {flag_audit[1]} ahtn8 codes with length != 8"
    assert flag_audit[2] == 0, f"Found {flag_audit[2]} non-valid code_flag rows"
    print("4. Code standardization quality (0 nulls, 0 invalid flags, 100% 8-digit): [PASS]")

    print("\n========================================")
    print(" ALL TRACK A4 AUDITS PASSED")
    print("========================================\n")
    con.close()


if __name__ == "__main__":
    test_track_a4_integrity()