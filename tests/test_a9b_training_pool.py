"""Automated validation audit for Track A9b: Training Pool and Cap Rule."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from src.hsclf.data.io import get_connection, load_params


def test_track_a9b_integrity():
    params = load_params()
    con, _ = get_connection(params)

    processed_dir = ROOT / params["paths"]["processed_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

    pool_file = processed_dir / "training_pool.parquet"
    cap_csv = tables_dir / "a9b_cap_summary.csv"
    probe_csv = tables_dir / "a9b_leakage_probe.csv"

    print("\n========================================")
    print(" TRACK A9b VALIDATION AUDIT")
    print("========================================\n")

    # 1. Artifact existence check
    assert pool_file.exists(), f"Missing {pool_file}"
    assert cap_csv.exists(), f"Missing {cap_csv}"
    assert probe_csv.exists(), f"Missing {probe_csv}"
    print("1. Artifact existence check: [PASS]")

    # 2. Schema check
    schema_cols = set(con.execute(f"DESCRIBE SELECT * FROM read_parquet('{pool_file.as_posix()}')").df()["column_name"])
    expected_cols = {"group_l1", "cap_key", "rank_main", "rank_y1"}
    assert expected_cols.issubset(schema_cols), f"Missing required columns: {expected_cols - schema_cols}"
    print("2. Schema validation [group_l1, cap_key, rank_main, rank_y1]: [PASS]")

    # 3. Validity of cap_key
    null_keys = con.execute(f"""
        SELECT count(*)
        FROM read_parquet('{pool_file.as_posix()}')
        WHERE cap_key IS NULL OR cap_key = ''
    """).fetchone()[0]
    assert null_keys == 0, f"Found {null_keys} records with null or empty cap_key"
    print("3. Cap key completeness: [PASS]")

    # 4. Strict subset nesting check
    pool_50 = set(con.execute(f"""
        SELECT group_l1 FROM read_parquet('{pool_file.as_posix()}')
        WHERE rank_main > 0 AND rank_main <= 50
    """).df()["group_l1"])

    pool_100 = set(con.execute(f"""
        SELECT group_l1 FROM read_parquet('{pool_file.as_posix()}')
        WHERE rank_main > 0 AND rank_main <= 100
    """).df()["group_l1"])

    assert pool_50.issubset(pool_100), "N = 50 pool is not a strict subset of N = 100 pool!"
    print(f"4. Monotonic nesting verified (N=50: {len(pool_50):,} is subset of N=100: {len(pool_100):,}): [PASS]")

    # 5. Leakage probe values check
    probe_df = pd.read_csv(probe_csv)
    assert len(probe_df) == 3, f"Expected 3 probe comparison rows, got {len(probe_df)}"
    
    # Ensure probe percentages are well-formed percentages
    assert (probe_df["pct_ge_0_95"] >= 0.0).all() and (probe_df["pct_ge_0_95"] <= 100.0).all()
    
    # Train-vs-train must show higher baseline similarity than test-vs-train
    test_sim = probe_df.loc[probe_df["comparison"] == "test_vs_train", "mean_max_similarity"].iloc[0]
    train_sim = probe_df.loc[probe_df["comparison"] == "train_vs_train", "mean_max_similarity"].iloc[0]
    assert test_sim < train_sim, f"Test similarity ({test_sim}) unexpectedly exceeds train similarity ({train_sim})"
    print(f"5. Leakage probe metrics verified (test_vs_train: {test_sim:.4f} < train_vs_train: {train_sim:.4f}): [PASS]")

    print("\n========================================")
    print(" ALL TRACK A9b AUDITS PASSED")
    print("========================================\n")
    con.close()


if __name__ == "__main__":
    test_track_a9b_integrity()