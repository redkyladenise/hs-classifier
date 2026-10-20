"""Track A5: Integrity, Collision, and Idempotency Audit."""

import sys
from pathlib import Path
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.io import get_connection, load_params
from src.hsclf.data.normalize import normalize_light


def test_track_a5_integrity():
    params = load_params()
    con, _ = get_connection(params)

    interim_dir = ROOT / params["paths"]["interim_dir"]
    raw_to_norm_file = interim_dir / "raw_to_norm.parquet"
    norm_desc_file = interim_dir / "norm_descriptions.parquet"
    parts_dir = interim_dir / "raw_to_norm_parts"

    print("\n========================================")
    print(" TRACK A5 VALIDATION AUDIT")
    print("========================================\n")

    # 1. Total raw-to-norm row count must equal 16,757,438
    print("1. Checking total rows in raw_to_norm.parquet...")
    total_raw = con.execute(f"SELECT count(*) FROM read_parquet('{raw_to_norm_file.as_posix()}')").fetchone()[0]
    expected_raw = 16757438
    print(f"   Found: {total_raw:,} | Expected: {expected_raw:,}")
    assert total_raw == expected_raw, f"Row count mismatch: got {total_raw}, expected {expected_raw}"
    print("   -> Total distinct raw rows: [PASS]")

    # 2. Collision Check: Each desc_norm_id must map to exactly one desc_norm
    print("\n2. Auditing for hash collisions across norm buckets...")
    norm_buckets = params.get("norm_buckets", 16)
    for b in range(norm_buckets):
        collisions = con.execute(f"""
            SELECT desc_norm_id, count(DISTINCT desc_norm) AS n_descs
            FROM read_parquet('{norm_desc_file.as_posix()}')
            WHERE norm_bucket = {b}
            GROUP BY desc_norm_id
            HAVING count(DISTINCT desc_norm) > 1
        """).fetchall()
        assert len(collisions) == 0, f"Collision detected in bucket {b}: {collisions}"
    print(f"   -> All {norm_buckets} buckets audited: 0 hash collisions found: [PASS]")

    # 3. Idempotency on Sample Chunk
    print("\n3. Testing part recreation idempotency...")
    sample_part = next(parts_dir.glob("*.parquet"))
    table_orig = pq.read_table(sample_part)
    
    # Re-normalize first 1,000 rows
    sample_raws = table_orig.column("desc_raw").slice(0, 1000).to_pylist()
    for i, raw_text in enumerate(sample_raws):
        res = normalize_light(raw_text, norm_buckets=norm_buckets)
        assert res["desc_norm"] == table_orig.column("desc_norm")[i].as_py()
        assert res["desc_norm_id"] == table_orig.column("desc_norm_id")[i].as_py()
        assert res["desc_status"] == table_orig.column("desc_status")[i].as_py()
    print("   -> Deterministic replay matches byte-for-byte: [PASS]")

    print("\n========================================")
    print(" ALL TRACK A5 AUDITS PASSED")
    print("========================================\n")
    con.close()


if __name__ == "__main__":
    test_track_a5_integrity()