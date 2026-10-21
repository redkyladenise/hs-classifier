"""Automated validation audit for Track A9: Class Eligibility by Level."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from src.hsclf.data.io import get_connection, load_params


def test_track_a9_integrity():
    params = load_params()
    con, _ = get_connection(params)

    processed_dir = ROOT / params["paths"]["processed_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

    elig_file = processed_dir / "class_eligibility.parquet"
    summary_csv = tables_dir / "a9_eligibility_summary.csv"
    excluded_csv = tables_dir / "a9_top_excluded_codes.csv"

    print("\n========================================")
    print(" TRACK A9 VALIDATION AUDIT")
    print("========================================\n")

    # 1. Artifact existence check
    assert elig_file.exists(), f"Missing {elig_file}"
    assert summary_csv.exists(), f"Missing {summary_csv}"
    assert excluded_csv.exists(), f"Missing {excluded_csv}"
    print("1. Artifact existence check: [PASS]")

    # 2. Schema and scenario completeness
    scenarios = set(con.execute(f"SELECT DISTINCT scenario FROM read_parquet('{elig_file.as_posix()}')").fetchall())
    expected_scenarios = {("main",), ("y1",)}
    assert scenarios == expected_scenarios, f"Unexpected scenarios: {scenarios}"

    levels = set(con.execute(f"SELECT DISTINCT level FROM read_parquet('{elig_file.as_posix()}')").fetchall())
    expected_levels = {(2,), (4,), (6,), (8,)}
    assert levels == expected_levels, f"Unexpected levels: {levels}"
    print("2. Scenarios {'main', 'y1'} and Levels {2, 4, 6, 8} completeness: [PASS]")

    # 3. Mathematical inequality checks
    # majority distinct descriptions must be <= any distinct descriptions
    invalid_counts = con.execute(f"""
        SELECT count(*)
        FROM read_parquet('{elig_file.as_posix()}')
        WHERE n_train_desc_majority > n_train_desc_any
    """).fetchone()[0]
    assert invalid_counts == 0, f"Found {invalid_counts} rows where n_train_desc_majority > n_train_desc_any"
    print("3. n_train_desc_majority <= n_train_desc_any: [PASS]")

    # 4. Monotonic threshold check
    monotonic_violations = con.execute(f"""
        SELECT count(*)
        FROM read_parquet('{elig_file.as_posix()}')
        WHERE (eligible_at_50 AND NOT eligible_at_20)
           OR (eligible_at_20 AND NOT eligible_at_10)
    """).fetchone()[0]
    assert monotonic_violations == 0, f"Found {monotonic_violations} threshold monotonicity violations"
    print("4. Sensitivity threshold monotonicity (50 <= 20 <= 10): [PASS]")

    # 5. Summary metrics check
    summary_df = pd.read_csv(summary_csv)
    assert len(summary_df) == 8, f"Expected 8 summary rows (2 scenarios x 4 levels), got {len(summary_df)}"
    assert (summary_df["pct_tx_coverage"] >= 95.0).all(), "Transaction coverage on eligible classes unexpectedly low"
    print("5. Summary coverage sanity checks: [PASS]")

    print("\n========================================")
    print(" ALL TRACK A9 AUDITS PASSED")
    print("========================================\n")
    con.close()


if __name__ == "__main__":
    test_track_a9_integrity()