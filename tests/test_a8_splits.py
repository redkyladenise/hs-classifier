"""Track A8: Automated Validation Audit for Frozen Dataset Splits."""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

import pandas as pd
from src.hsclf.data.io import get_connection, load_params


def get_sha256(file_path: Path) -> str:
  hasher = hashlib.sha256()
  with open(file_path, "rb") as f:
    while chunk := f.read(1024 * 1024):
      hasher.update(chunk)
  return hasher.hexdigest()


def test_track_a8_integrity():
  params = load_params()
  con, _ = get_connection(params)

  processed_dir = ROOT / params["paths"]["processed_dir"]
  tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

  unique_desc_file = processed_dir / "unique_descriptions.parquet"
  tx_file = processed_dir / "transactions_grouped.parquet"
  split_file = processed_dir / "split_assignments.parquet"
  desc_status_file = processed_dir / "description_status.parquet"
  manifest_file = ROOT / "docs" / "split_manifest.md"
  summary_csv = tables_dir / "a8_split_summary.csv"

  print("\n========================================")
  print(" TRACK A8 VALIDATION AUDIT")
  print("========================================\n")

  # 1. Artifact existence check
  assert split_file.exists(), f"Missing {split_file}"
  assert desc_status_file.exists(), f"Missing {desc_status_file}"
  assert manifest_file.exists(), f"Missing {manifest_file}"
  assert summary_csv.exists(), f"Missing {summary_csv}"
  print("1. Artifact existence check: [PASS]")

  # 2. Every group appears exactly once in split_assignments
  n_total_l2 = con.execute(
      f"SELECT count(DISTINCT group_l2) FROM"
      f" read_parquet('{unique_desc_file.as_posix()}')"
  ).fetchone()[0]
  split_group_stats = con.execute(f"""
        SELECT 
            count(*), 
            count(DISTINCT group_l2),
            count(CASE WHEN split IS NULL THEN 1 END)
        FROM read_parquet('{split_file.as_posix()}')
    """).fetchone()

  assert (
      split_group_stats[0] == n_total_l2
  ), f"Split table rows ({split_group_stats[0]}) != unique L2 groups ({n_total_l2})"
  assert (
      split_group_stats[1] == n_total_l2
  ), "Duplicate group_l2 IDs detected in split table!"
  assert (
      split_group_stats[2] == 0
  ), f"Found {split_group_stats[2]} null split assignments"
  print(
      f"2. Group coverage and uniqueness ({split_group_stats[0]:,} groups,"
      " 0 nulls, 0 duplicates): [PASS]"
  )

  # 3. Every Level-1 description appears exactly once in description_status
  n_total_l1 = con.execute(
      f"SELECT count(*) FROM read_parquet('{unique_desc_file.as_posix()}')"
  ).fetchone()[0]
  desc_status_stats = con.execute(f"""
        SELECT 
            count(*), 
            count(DISTINCT group_l1),
            count(CASE WHEN seen_y1 IS NULL OR seen_y2 IS NULL THEN 1 END)
        FROM read_parquet('{desc_status_file.as_posix()}')
    """).fetchone()

  assert (
      desc_status_stats[0] == n_total_l1
  ), f"description_status rows ({desc_status_stats[0]}) != unique L1 descriptions ({n_total_l1})"
  assert (
      desc_status_stats[1] == n_total_l1
  ), "Duplicate group_l1 IDs detected in description_status table!"
  assert (
      desc_status_stats[2] == 0
  ), f"Found {desc_status_stats[2]} null seen statuses"
  print(
      f"3. Description coverage and status completeness"
      f" ({desc_status_stats[0]:,} descriptions, 0 nulls): [PASS]"
  )

  # 4. Proportions within split_tolerance_group_pct (0.5%)
  early_splits = con.execute(f"""
        SELECT split, count(*) * 100.0 / sum(count(*)) OVER () AS pct
        FROM read_parquet('{split_file.as_posix()}')
        WHERE split != 'only_2025'
        GROUP BY split
    """).df()

  pct_map = dict(zip(early_splits["split"], early_splits["pct"]))
  tol = params.get("split_tolerance_group_pct", 0.5)
  assert (
      abs(pct_map["train"] - 70.0) <= tol
  ), f"Train group pct out of bounds: {pct_map['train']}%"
  assert (
      abs(pct_map["val"] - 15.0) <= tol
  ), f"Val group pct out of bounds: {pct_map['val']}%"
  assert (
      abs(pct_map["test"] - 15.0) <= tol
  ), f"Test group pct out of bounds: {pct_map['test']}%"
  print(
      f"4. Early group proportions (Train: {pct_map['train']:.4f}%, Val:"
      f" {pct_map['val']:.4f}%, Test: {pct_map['test']:.4f}% | Tol: <={tol}%):"
      " [PASS]"
  )

  # 5. only_2025 integrity
  invalid_2025_early = con.execute(f"""
        SELECT count(*)
        FROM read_parquet('{split_file.as_posix()}')
        WHERE split = 'only_2025' AND first_year_l2 < 2025
    """).fetchone()[0]
  assert (
      invalid_2025_early == 0
  ), f"Found {invalid_2025_early} only_2025 groups with transactions before 2025"

  invalid_early_as_2025 = con.execute(f"""
        SELECT count(*)
        FROM read_parquet('{split_file.as_posix()}')
        WHERE split != 'only_2025' AND first_year_l2 = 2025
    """).fetchone()[0]
  assert (
      invalid_early_as_2025 == 0
  ), f"Found {invalid_early_as_2025} groups starting in 2025 assigned to early splits"
  print("5. only_2025 group boundary isolation: [PASS]")

  # 6. unseen scenario 100% new check
  unseen_leak = con.execute(f"""
        SELECT count(*)
        FROM read_parquet('{tx_file.as_posix()}') t
        INNER JOIN read_parquet('{desc_status_file.as_posix()}') s
            ON t.group_l1 = s.group_l1
        WHERE t.year IN (2023, 2024)
          AND s.split = 'test'
          AND s.seen_y2 != 'new'
    """).fetchone()[0]
  assert (
      unseen_leak == 0
  ), f"Found {unseen_leak} test transactions in unseen scenario that are not 'new'"
  print("6. unseen scenario strict zero-leakage check (100% new): [PASS]")

  # 7. Checksum recorded in manifest
  manifest_text = manifest_file.read_text(encoding="utf-8")
  actual_split_sha = get_sha256(split_file)
  actual_desc_sha = get_sha256(desc_status_file)
  assert (
      actual_split_sha in manifest_text
  ), "split_assignments SHA-256 not found in manifest!"
  assert (
      actual_desc_sha in manifest_text
  ), "description_status SHA-256 not found in manifest!"
  print("7. Manifest checksum verification: [PASS]")

  print("\n========================================")
  print(" ALL TRACK A8 AUDITS PASSED")
  print("========================================\n")
  con.close()


if __name__ == "__main__":
  test_track_a8_integrity()