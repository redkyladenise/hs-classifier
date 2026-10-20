"""Track A5: Goods Description Normalization Pipeline.

Processes pre-bucketed distinct raw descriptions in memory-safe chunks,
produces resumable normalized parts, combines them into raw_to_norm.parquet,
builds the deduplicated norm_descriptions.parquet table, and exports diagnostic counts.
"""

import sys
import time
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.io import get_connection, load_params
from src.hsclf.data.normalize import normalize_light


def stage_1_normalize_bucket_chunks(
    raw_desc_dir: Path,
    parts_dir: Path,
    chunk_size: int,
    norm_buckets: int,
    placeholders: set,
):
    """Normalize raw descriptions in chunks across all 16 A3 buckets."""
    print("\n--- Stage 1: Normalizing Distinct Descriptions in Chunks ---")
    parts_dir.mkdir(parents=True, exist_ok=True)

    bucket_files = sorted(raw_desc_dir.glob("part_*.parquet"))
    if not bucket_files:
        raise FileNotFoundError(f"No bucket files found in {raw_desc_dir}")

    total_chunks_processed = 0

    for b_idx, b_file in enumerate(bucket_files):
        print(f"\nProcessing Bucket {b_idx:02d} ({b_file.name})...")
        pq_file = pq.ParquetFile(b_file)
        
        chunk_idx = 0
        for batch in pq_file.iter_batches(batch_size=chunk_size, columns=["goods_description"]):
            part_path = parts_dir / f"b{b_idx:02d}_c{chunk_idx:03d}.parquet"
            if part_path.exists():
                print(f"  Chunk {part_path.name} already exists. Skipping.")
                chunk_idx += 1
                continue

            start_t = time.time()
            raw_descs = batch.column(0).to_pylist()
            
            records = {
                "desc_raw": [],
                "desc_norm": [],
                "desc_norm_id": [],
                "norm_bucket": [],
                "desc_status": [],
            }

            for text in raw_descs:
                res = normalize_light(text, placeholders=placeholders, norm_buckets=norm_buckets)
                records["desc_raw"].append(text)
                records["desc_norm"].append(res["desc_norm"])
                records["desc_norm_id"].append(res["desc_norm_id"])
                records["norm_bucket"].append(res["norm_bucket"])
                records["desc_status"].append(res["desc_status"])

            # Explicit schema definition to ensure stable types across all chunks
            schema = pa.schema([
                ("desc_raw", pa.string()),
                ("desc_norm", pa.string()),
                ("desc_norm_id", pa.int64()),
                ("norm_bucket", pa.int64()),
                ("desc_status", pa.string()),
            ])

            table = pa.Table.from_pydict(records, schema=schema)
            pq.write_table(table, part_path, compression="ZSTD")
            elapsed = time.time() - start_t
            print(f"  Wrote {part_path.name} ({len(table):,} rows) in {elapsed:.1f}s.")

            chunk_idx += 1
            total_chunks_processed += 1

    print(f"\nStage 1 complete. All chunks saved to {parts_dir.name}.")


def stage_2_combine_raw_to_norm(con, parts_dir: Path, output_file: Path):
    """Stream-combine all chunked parts into raw_to_norm.parquet."""
    print("\n--- Stage 2: Combining Parts into raw_to_norm.parquet ---")
    if output_file.exists():
        print(f"Target {output_file.name} already exists. Skipping.")
        return

    start_t = time.time()
    parts_glob = (parts_dir / "*.parquet").as_posix()
    print(f"Streaming from {parts_glob}...")
    
    con.execute(f"""
        COPY (
            SELECT 
                desc_raw,
                desc_norm,
                desc_norm_id,
                norm_bucket,
                desc_status
            FROM read_parquet('{parts_glob}')
        ) TO '{output_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
    """)
    print(f"Created {output_file.name} in {time.time() - start_t:.1f}s.")


def stage_3_build_norm_descriptions(con, raw_to_norm_file: Path, output_file: Path, norm_buckets: int):
    """Build deduplicated norm_descriptions.parquet one norm_bucket at a time."""
    print("\n--- Stage 3: Building Unique norm_descriptions.parquet ---")
    if output_file.exists():
        print(f"Target {output_file.name} already exists. Skipping.")
        return

    temp_norm_dir = output_file.parent / "temp_norm_buckets"
    temp_norm_dir.mkdir(parents=True, exist_ok=True)

    bucket_parts = []
    for b in range(norm_buckets):
        part_path = temp_norm_dir / f"norm_desc_bucket_{b:02d}.parquet"
        bucket_parts.append(part_path)
        if part_path.exists():
            print(f"  norm_bucket {b:02d} already exists. Skipping.")
            continue

        start_t = time.time()
        print(f"  Deduplicating norm_bucket {b:02d}...")
        con.execute(f"""
            COPY (
                SELECT DISTINCT 
                    desc_norm_id,
                    desc_norm,
                    norm_bucket
                FROM read_parquet('{raw_to_norm_file.as_posix()}')
                WHERE norm_bucket = {b}
            ) TO '{part_path.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
        """)
        print(f"  norm_bucket {b:02d} saved in {time.time() - start_t:.1f}s.")

    # Merge all bucket files into the final deduplicated table
    print(f"Merging {norm_buckets} buckets into {output_file.name}...")
    glob_pattern = (temp_norm_dir / "norm_desc_bucket_*.parquet").as_posix()
    con.execute(f"""
        COPY (
            SELECT * FROM read_parquet('{glob_pattern}')
        ) TO '{output_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
    """)
    print(f"Created {output_file.name} successfully.")


def stage_4_generate_counts(con, raw_to_norm_file: Path, norm_desc_file: Path, report_file: Path):
    """Generate diagnostic summary counts for Track A5."""
    print("\n--- Stage 4: Generating Normalization Counts Report ---")
    report_file.parent.mkdir(parents=True, exist_ok=True)

    if report_file.exists():
        print(f"Report {report_file.name} already exists. Skipping.")
        return

    print("Computing metrics...")
    stats_df = con.execute(f"""
        WITH raw_stats AS (
            SELECT 
                count(*) AS total_raw,
                count(CASE WHEN desc_status = 'ok' THEN 1 END) AS n_ok,
                count(CASE WHEN desc_status = 'placeholder' THEN 1 END) AS n_placeholder,
                count(CASE WHEN desc_status = 'blank' THEN 1 END) AS n_blank
            FROM read_parquet('{raw_to_norm_file.as_posix()}')
        ),
        norm_stats AS (
            SELECT 
                count(*) AS total_norm,
                count(DISTINCT desc_norm_id) AS distinct_ids
            FROM read_parquet('{norm_desc_file.as_posix()}')
        )
        SELECT 
            r.total_raw AS distinct_raw_descriptions,
            n.total_norm AS distinct_normalized_descriptions,
            n.distinct_ids AS distinct_norm_ids,
            r.n_ok AS count_status_ok,
            r.n_placeholder AS count_status_placeholder,
            r.n_blank AS count_status_blank,
            round(r.n_ok * 100.0 / r.total_raw, 4) AS pct_ok,
            round(r.n_placeholder * 100.0 / r.total_raw, 4) AS pct_placeholder,
            round(r.n_blank * 100.0 / r.total_raw, 4) AS pct_blank
        FROM raw_stats r, norm_stats n;
    """).df()

    stats_df.to_csv(report_file, index=False)
    print(f"Saved {report_file.name}:")
    print(stats_df.to_string(index=False))


def main():
    params = load_params()
    con, _ = get_connection(params)

    interim_dir = ROOT / params["paths"]["interim_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

    raw_desc_dir = interim_dir / "raw_desc_counts"
    parts_dir = interim_dir / "raw_to_norm_parts"
    raw_to_norm_file = interim_dir / "raw_to_norm.parquet"
    norm_desc_file = interim_dir / "norm_descriptions.parquet"
    report_file = tables_dir / "a5_normalization_counts.csv"

    chunk_size = params.get("chunk_size", 500000)
    norm_buckets = params.get("norm_buckets", 16)
    placeholders = set(params.get("placeholders", []))

    try:
        stage_1_normalize_bucket_chunks(raw_desc_dir, parts_dir, chunk_size, norm_buckets, placeholders)
        stage_2_combine_raw_to_norm(con, parts_dir, raw_to_norm_file)
        stage_3_build_norm_descriptions(con, raw_to_norm_file, norm_desc_file, norm_buckets)
        stage_4_generate_counts(con, raw_to_norm_file, norm_desc_file, report_file)
        print("\nTrack A5 normalization pipeline completed successfully.")
    finally:
        con.close()


if __name__ == "__main__":
    main()