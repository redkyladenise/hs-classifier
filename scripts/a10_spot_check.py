"""Track A10: Pipeline Spot-Checks, Checksum Verification, and Manifest Generator."""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb
import pyarrow.parquet as pq
from src.hsclf.data.io import get_connection, load_params


def get_file_checksum(filepath: Path) -> str:
    """Compute SHA-256 checksum of a file in chunks."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def count_parquet_rows(filepath: Path) -> int:
    """Return exact row count from parquet metadata without full scan."""
    if filepath.is_dir():
        total = 0
        for p in filepath.glob("*.parquet"):
            total += pq.read_metadata(p).num_rows
        return total
    return pq.read_metadata(filepath).num_rows


def audit_system_environment():
    """Print system environment specs and pinned DuckDB version."""
    params = load_params()
    duckdb_ver = duckdb.__version__
    norm_buckets = params.get("norm_buckets", 16)
    print("=" * 60)
    print(" TRACK A10: ENVIRONMENT SPECIFICATION")
    print("=" * 60)
    print(f"DuckDB Version : {duckdb_ver}")
    print(f"Norm Buckets   : {norm_buckets}")
    print(f"Python Version : {sys.version.split()[0]}")
    print("=" * 60 + "\n")


def generate_artifact_manifest():
    """Generate row count, size, and SHA-256 checksum manifest for Track A."""
    print("=" * 60)
    print(" TRACK A DATA ARTIFACT MANIFEST (A1 - A9b)")
    print("=" * 60)

    artifacts = [
        Path("data/interim/transactions_slim.parquet"),
        Path("data/interim/raw_desc_counts"),
        Path("data/interim/code_map.parquet"),
        Path("data/interim/codes_standardized.parquet"),
        Path("data/interim/raw_to_norm.parquet"),
        Path("data/interim/norm_descriptions.parquet"),
        Path("data/processed/transactions_clean.parquet"),
        Path("data/processed/transactions_scope.parquet"),
        Path("data/processed/unique_descriptions.parquet"),
        Path("data/processed/transactions_grouped.parquet"),
        Path("data/processed/split_assignments.parquet"),
        Path("data/processed/description_status.parquet"),
        Path("data/processed/class_eligibility.parquet"),
        Path("data/processed/training_pool.parquet"),
    ]

    manifest = []
    for rel_path in artifacts:
        full_path = ROOT / rel_path
        if not full_path.exists():
            print(f"WARNING: Missing artifact {rel_path.as_posix()}")
            continue

        rows = count_parquet_rows(full_path)
        if full_path.is_file():
            checksum = get_file_checksum(full_path)
            size_mb = full_path.stat().st_size / (1024 * 1024)
        else:
            # Multi-file directory
            part_hashes = []
            size_bytes = 0
            for p in sorted(full_path.glob("*.parquet")):
                part_hashes.append(get_file_checksum(p))
                size_bytes += p.stat().st_size
            checksum = hashlib.sha256("".join(part_hashes).encode()).hexdigest()
            size_mb = size_bytes / (1024 * 1024)

        manifest.append({
            "artifact": rel_path.as_posix(),
            "rows": rows,
            "size_mb": round(size_mb, 2),
            "sha256": checksum,
        })
        print(f"-> {rel_path.as_posix():<45} | Rows: {rows:>10,} | Size: {size_mb:>8.2f} MB | SHA-256: {checksum[:12]}...")

    manifest_json = ROOT / "reports" / "tables" / "a10_track_a_manifest.json"
    manifest_json.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_json, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nSaved manifest to {manifest_json.relative_to(ROOT).as_posix()}\n")
    return manifest


def spot_check_bucketed_stages():
    """Spot-check bucketed processing partitions for A3, A5, A6, and A7."""
    print("=" * 60)
    print(" BUCKETED REPRODUCIBILITY SPOT-CHECKS (A3, A5, A6, A7)")
    print("=" * 60)
    params = load_params()
    con, _ = get_connection(params)

    # 1. Spot-check A3 bucket 00
    a3_b0 = ROOT / "data" / "interim" / "raw_desc_counts" / "raw_desc_b00.parquet"
    if a3_b0.exists():
        r = con.execute(f"SELECT count(*), sum(n_transactions) FROM read_parquet('{a3_b0.as_posix()}')").fetchone()
        print(f"A3 Bucket 00: {r[0]:,} unique raw descriptions, {r[1]:,} transactions [OK]")

    # 2. Spot-check A5 bucket 00
    a5_b0 = ROOT / "data" / "interim" / "temp_norm_buckets" / "norm_desc_bucket_00.parquet"
    if a5_b0.exists():
        r = con.execute(f"SELECT count(*) FROM read_parquet('{a5_b0.as_posix()}')").fetchone()
        print(f"A5 Bucket 00: {r[0]:,} normalized descriptions [OK]")

    # 3. Spot-check A6 bucket 00
    a6_b0 = ROOT / "data" / "processed" / "temp_unique_desc_buckets" / "unique_desc_b00.parquet"
    if a6_b0.exists():
        r = con.execute(f"SELECT count(*) FROM read_parquet('{a6_b0.as_posix()}')").fetchone()
        print(f"A6 Bucket 00: {r[0]:,} unique descriptions [OK]")

    # 4. Spot-check A7 bucket 00
    a7_b0 = ROOT / "data" / "processed" / "temp_a7_buckets" / "grouped_tx_b00.parquet"
    if a7_b0.exists():
        r = con.execute(f"SELECT count(*) FROM read_parquet('{a7_b0.as_posix()}')").fetchone()
        print(f"A7 Bucket 00: {r[0]:,} grouped transactions [OK]")

    print("Spot-checks complete.\n")
    con.close()


def main():
    audit_system_environment()
    spot_check_bucketed_stages()
    generate_artifact_manifest()


if __name__ == "__main__":
    main()