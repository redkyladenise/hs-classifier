"""Automated validation audit for Track A6: Chapter Scope Selection & Dataset Cleaning."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from src.hsclf.data.io import get_connection, load_params


def test_track_a6_integrity():
  params = load_params()
  con, _ = get_connection(params)

  interim_dir = ROOT / params["paths"]["interim_dir"]
  tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

  clean_file = interim_dir / "transactions_clean.parquet"
  scope_file = interim_dir / "transactions_scope.parquet"
  attrition_csv = tables_dir / "a6_attrition.csv"
  ranking_csv = tables_dir / "a6_chapter_ranking.csv"

  print("\n========================================")
  print(" TRACK A6 VALIDATION AUDIT")
  print("========================================\n")

  # 1. Artifact existence check
  assert clean_file.exists(), f"Missing {clean_file}"
  assert scope_file.exists(), f"Missing {scope_file}"
  assert attrition_csv.exists(), f"Missing {attrition_csv}"
  assert ranking_csv.exists(), f"Missing {ranking_csv}"
  print("1. Artifact existence check: [PASS]")

  # 2. Total clean rows check (26,889,707)
  total_clean = con.execute(
      f"SELECT count(*) FROM read_parquet('{clean_file.as_posix()}')"
  ).fetchone()[0]
  expected_total = sum(params["expected_rows_by_year"].values())
  print(f"2. Total clean row count: {total_clean:,} (Expected: {expected_total:,})")
  assert total_clean == expected_total, (
      f"Row count mismatch in clean file: {total_clean} vs {expected_total}"
  )
  print("   -> Total clean count: [PASS]")

  # 3. Yearly counts match A1
  yearly_counts = con.execute(f"""
        SELECT year, count(*) 
        FROM read_parquet('{clean_file.as_posix()}') 
        GROUP BY year 
        ORDER BY year
    """).fetchall()

  print("3. Checking per-year clean row distribution:")
  for y, cnt in yearly_counts:
    exp = params["expected_rows_by_year"][y]
    print(f"   - Year {y}: {cnt:,} (Expected: {exp:,})")
    assert cnt == exp, f"Year {y} row count mismatch: {cnt} vs {exp}"
  print("   -> Per-year clean distribution: [PASS]")

  # 4. No missing desc_norm_id
  null_ids = con.execute(f"""
        SELECT count(*) 
        FROM read_parquet('{clean_file.as_posix()}') 
        WHERE desc_norm_id IS NULL
    """).fetchone()[0]
  assert null_ids == 0, (
      f"Found {null_ids} rows with missing/null desc_norm_id"
  )
  print("4. desc_norm_id completeness (0 nulls): [PASS]")

  # 5. Attrition waterfall full reconciliation
  attr_df = pd.read_csv(attrition_csv)
  reconciled_sum = attr_df["n_transactions"].sum()
  print(
      f"5. Attrition waterfall total: {reconciled_sum:,} (Expected:"
      f" {expected_total:,})"
  )
  assert reconciled_sum == expected_total, (
      f"Attrition does not reconcile! Sum = {reconciled_sum}"
  )

  # Check that bad_format, odd_length, and bad_chapter rows do not appear or have 0 counts
  invalid_flags = (
      attr_df[
          attr_df["category"].isin(["bad_format", "odd_length", "bad_chapter"])
      ]["n_transactions"].sum()
      if any(
          attr_df["category"].isin(["bad_format", "odd_length", "bad_chapter"])
      )
      else 0
  )
  assert invalid_flags == 0, (
      f"Unexpected invalid code flags in attrition: {invalid_flags}"
  )
  print("   -> Attrition waterfall perfect reconciliation: [PASS]")

  # 6. Scope dataset audit
  scope_audit = con.execute(f"""
        SELECT 
            count(*),
            count(DISTINCT ch2),
            count(CASE WHEN norm_bucket IS NULL THEN 1 END) AS null_buckets,
            count(CASE WHEN code_flag != 'valid' THEN 1 END) AS invalid_codes,
            count(CASE WHEN desc_status != 'ok' THEN 1 END) AS invalid_status
        FROM read_parquet('{scope_file.as_posix()}')
    """).fetchone()

  in_scope_tx = attr_df[attr_df["category"] == "valid_in_scope"][
      "n_transactions"
  ].iloc[0]
  assert scope_audit[0] == in_scope_tx, (
      f"Scope rows mismatch: {scope_audit[0]:,} vs attrition {in_scope_tx:,}"
  )
  assert scope_audit[1] == len(params["chapters"]), (
      f"Expected {len(params['chapters'])} distinct chapters in scope, got"
      f" {scope_audit[1]}"
  )
  assert scope_audit[2] == 0, f"Found {scope_audit[2]} null norm_bucket values"
  assert scope_audit[3] == 0, f"Found {scope_audit[3]} non-valid code_flags"
  assert scope_audit[4] == 0, f"Found {scope_audit[4]} non-ok desc_statuses"
  print(
      f"6. transactions_scope.parquet ({scope_audit[0]:,} rows, exactly"
      " Chapters [84, 85, 39, 73, 87], norm_bucket populated): [PASS]"
  )

  print("\n========================================")
  print(" ALL TRACK A6 AUDITS PASSED")
  print("========================================\n")
  con.close()


if __name__ == "__main__":
  test_track_a6_integrity()