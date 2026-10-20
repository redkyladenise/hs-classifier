"""Track A1: Build slim transactions dataset.

Processes raw Parquet files by year:
  - Generates surrogate row_id ({year}-{row_position:08d})
  - Standardizes column names (row_id, year, month, goods_description, hs_code)
  - Casts hs_code safely to text (eliminating numerical artifacts)
  - Writes yearly slim files to data/interim/slim_by_year/
  - Merges yearly files into data/interim/transactions_slim.parquet using DuckDB
"""

import sys
import time
from pathlib import Path

# Add project root to path so we can import src.hsclf
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.io import get_connection, load_params


def stage_1_build_yearly_slim(con, params: dict) -> list[Path]:
    """Extract, transform, and write slim Parquet files per year."""
    raw_dir = ROOT / params["paths"]["raw_dir"]
    interim_dir = ROOT / params["paths"]["interim_dir"]
    slim_by_year_dir = interim_dir / "slim_by_year"
    slim_by_year_dir.mkdir(parents=True, exist_ok=True)

    source_cols = params["source_columns"]
    yearly_files = []

    # Combined years from train_years and final_test_year
    years = params.get("train_years", []) + [params.get("final_test_year")]

    print("\n--- Stage 1: Per-Year Slim Extraction ---")
    for year in years:
        raw_file = raw_dir / f"{year}.parquet"
        out_file = slim_by_year_dir / f"slim_{year}.parquet"
        yearly_files.append(out_file)

        if out_file.exists():
            print(f"[{year}] Output already exists: {out_file.name}. Skipping.")
            continue

        if not raw_file.exists():
            raise FileNotFoundError(f"Raw file missing: {raw_file}")

        print(f"[{year}] Processing {raw_file.name}...")
        start_t = time.time()

        # DuckDB query:
        # 1. row_number() over () gives 1-based row index (0-padded to 8 digits)
        # 2. cast(HSCODE as BIGINT) as VARCHAR ensures clean integer-to-string without scientific notation or floats
        # 3. Prune all unneeded columns (DUTY, VAT, etc.)
        query = f"""
            COPY (
                SELECT
                    printf('{year}-%08d', row_number() OVER ()) AS row_id,
                    CAST({source_cols['year']} AS INTEGER) AS year,
                    CAST({source_cols['month']} AS INTEGER) AS month,
                    {source_cols['goods_description']} AS goods_description,
                    CAST(CAST({source_cols['hs_code']} AS BIGINT) AS VARCHAR) AS hs_code
                FROM read_parquet('{raw_file.as_posix()}')
            ) TO '{out_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
        """
        con.execute(query)
        elapsed = time.time() - start_t
        print(f"[{year}] Written to {out_file.name} in {elapsed:.1f}s.")

    return yearly_files


def stage_2_merge_slim(con, params: dict, yearly_files: list[Path]) -> Path:
    """Stream-merge yearly slim Parquet files into a single transactions_slim.parquet."""
    interim_dir = ROOT / params["paths"]["interim_dir"]
    combined_file = interim_dir / "transactions_slim.parquet"

    print("\n--- Stage 2: Merging Yearly Slim Files ---")
    if combined_file.exists():
        print(f"Combined file already exists: {combined_file.name}. Skipping merge.")
        return combined_file

    file_paths_str = ", ".join([f"'{f.as_posix()}'" for f in yearly_files])

    print(f"Merging {len(yearly_files)} files into {combined_file.name}...")
    start_t = time.time()

    # Streaming merge using read_parquet list
    # preserve_insertion_order is false (set in get_connection) to minimize memory
    query = f"""
        COPY (
            SELECT * FROM read_parquet([{file_paths_str}])
        ) TO '{combined_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
    """
    con.execute(query)
    elapsed = time.time() - start_t
    print(f"Combined file created in {elapsed:.1f}s: {combined_file.name}")

    return combined_file


def main():
    params = load_params()
    con, _ = get_connection(params)

    try:
        yearly_files = stage_1_build_yearly_slim(con, params)
        stage_2_merge_slim(con, params, yearly_files)
        print("\nA1 Slim generation complete.")
    finally:
        con.close()


if __name__ == "__main__":
    main()