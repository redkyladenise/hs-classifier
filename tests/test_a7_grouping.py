"""Automated validation audit for Track A7: Description Grouping and Conflict Preview."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from src.hsclf.data.io import get_connection, load_params


def test_track_a7_integrity():
    params = load_params()
    con, _ = get_connection(params)

    interim_dir = ROOT / params["paths"]["interim_dir"]
    processed_dir = ROOT / params["paths"]["processed_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

    scope_file = interim_dir / "transactions_scope.parquet"
    unique_desc_file = processed_dir / "unique_descriptions.parquet"
    tx_grouped_file = processed_dir / "transactions_grouped.parquet"
    conflict_csv = tables_dir / "a7_conflict_preview.csv"
    top_groups_csv = tables_dir / "a7_top_skeleton_groups.csv"

    print("\n========================================")
    print(" TRACK A7 VALIDATION AUDIT")
    print("========================================\n")

    # 1. Artifact existence check
    assert unique_desc_file.exists(), f"Missing {unique_desc_file}"
    assert tx_grouped_file.exists(), f"Missing {tx_grouped_file}"
    assert conflict_csv.exists(), f"Missing {conflict_csv}"
    assert top_groups_csv.exists(), f"Missing {top_groups_csv}"
    print("1. Artifact existence check: [PASS]")

    # Baseline: In-scope transaction count
    expected_scope_tx = con.execute(
        f"SELECT count(*) FROM read_parquet('{scope_file.as_posix()}')"
    ).fetchone()[0]
    print(f"Baseline in-scope transactions: {expected_scope_tx:,}")

    # 2. Reconcile transactions_grouped.parquet row count
    total_grouped_tx = con.execute(
        f"SELECT count(*) FROM read_parquet('{tx_grouped_file.as_posix()}')"
    ).fetchone()[0]
    print(f"2. Total grouped transactions: {total_grouped_tx:,} (Expected: {expected_scope_tx:,})")
    assert total_grouped_tx == expected_scope_tx, (
        f"Grouped tx count mismatch: {total_grouped_tx} vs {expected_scope_tx}"
    )
    print("   -> transactions_grouped.parquet row balance: [PASS]")

    # 3. Completeness of group IDs in transactions_grouped.parquet
    null_audit = con.execute(f"""
        SELECT 
            count(CASE WHEN group_l1 IS NULL THEN 1 END) AS null_l1,
            count(CASE WHEN group_l2 IS NULL THEN 1 END) AS null_l2
        FROM read_parquet('{tx_grouped_file.as_posix()}')
    """).fetchone()
    assert null_audit[0] == 0, f"Found {null_audit[0]} null group_l1 values"
    assert null_audit[1] == 0, f"Found {null_audit[1]} null group_l2 values"
    print("3. Group ID completeness (0 nulls in group_l1 & group_l2): [PASS]")

    # 4. Reconcile unique_descriptions.parquet transaction sum
    desc_tx_sum = con.execute(
        f"SELECT sum(n_transactions)::BIGINT FROM read_parquet('{unique_desc_file.as_posix()}')"
    ).fetchone()[0]
    print(f"4. Sum of n_transactions in unique_descriptions: {desc_tx_sum:,} (Expected: {expected_scope_tx:,})")
    assert desc_tx_sum == expected_scope_tx, (
        f"unique_descriptions transaction sum mismatch: {desc_tx_sum} vs {expected_scope_tx}"
    )
    print("   -> unique_descriptions.parquet transaction reconciliation: [PASS]")

    # 5. Cardinality inequality: count(distinct group_l2) <= count(distinct group_l1)
    cardinalities = con.execute(f"""
        SELECT 
            count(DISTINCT desc_norm_id) AS distinct_l1,
            count(DISTINCT group_l2) AS distinct_l2
        FROM read_parquet('{unique_desc_file.as_posix()}')
    """).fetchone()
    distinct_l1, distinct_l2 = cardinalities
    print(f"5. Cardinality: L1={distinct_l1:,} | L2={distinct_l2:,}")
    assert distinct_l2 <= distinct_l1, (
        f"L2 cardinality ({distinct_l2}) exceeds L1 ({distinct_l1})"
    )
    print("   -> Skeleton cardinality reduction inequality (L2 <= L1): [PASS]")

    # 6. Largest group size safety threshold (< 1.0% of in-scope transactions)
    top_df = pd.read_csv(top_groups_csv)
    max_share = top_df["pct_in_scope_tx"].max()
    print(f"6. Largest L2 group share: {max_share:.4f}% (Threshold limit: < 1.0%)")
    assert max_share < 1.0, f"Largest group exceeds 1.0% limit: {max_share}%"
    print("   -> Largest group balance check: [PASS]")

    print("\n========================================")
    print(" ALL TRACK A7 AUDITS PASSED")
    print("========================================\n")
    con.close()


if __name__ == "__main__":
    test_track_a7_integrity()