"""Track A4: HS Code Standardization Pipeline.

Extracts distinct codes, applies standardize_code to create code_map.parquet,
and joins the map back to transactions_slim.parquet year-by-year into
codes_standardized.parquet.
"""

import sys
import time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hsclf.data.codes import standardize_code
from src.hsclf.data.io import get_connection, load_params


def stage_1_build_code_map(con, slim_file: Path, code_map_file: Path) -> pd.DataFrame:
    """Extract distinct HS codes, standardize them, and export code_map.parquet."""
    print("\n--- Stage 1: Building Code Map ---")
    if code_map_file.exists():
        print(f"Loading existing code map: {code_map_file.name}")
        return pd.read_parquet(code_map_file)

    print("Querying distinct hs_code values from transactions_slim...")
    start_t = time.time()
    distinct_df = con.execute(f"""
        SELECT DISTINCT hs_code 
        FROM read_parquet('{slim_file.as_posix()}')
        WHERE hs_code IS NOT NULL
        ORDER BY hs_code
    """).df()
    print(f"Extracted {len(distinct_df):,} distinct codes in {time.time() - start_t:.2f}s.")

    print("Applying standardize_code to distinct values...")
    records = []
    for raw_code in distinct_df["hs_code"]:
        std = standardize_code(raw_code)
        records.append({
            "hs_code": str(raw_code),
            "ahtn8": std["ahtn8"],
            "sh6": std["sh6"],
            "hd4": std["hd4"],
            "ch2": std["ch2"],
            "hs_extra": std["hs_extra"],
            "code_len_orig": std["code_len_orig"],
            "code_fix": std["code_fix"],
            "code_flag": std["code_flag"],
            "ends_00": std["ends_00"],
            "right_padded": std["right_padded"]
        })

    code_map_df = pd.DataFrame(records)
    code_map_df.to_parquet(code_map_file, index=False, compression="ZSTD")
    print(f"Saved {len(code_map_df):,} standardized distinct codes to {code_map_file.name}.")
    return code_map_df


def stage_2_join_standardized_codes(con, slim_file: Path, code_map_file: Path, output_file: Path, params: dict):
    """Stream-join code_map with transactions_slim year-by-year into codes_standardized.parquet."""
    print("\n--- Stage 2: Streaming Join into codes_standardized.parquet ---")
    if output_file.exists():
        print(f"Target file {output_file.name} already exists. Skipping recreation.")
        return

    years = params.get("train_years", [2023, 2024]) + [params.get("final_test_year", 2025)]
    temp_dir = output_file.parent / "temp_standardized_years"
    temp_dir.mkdir(parents=True, exist_ok=True)

    part_files = []
    for y in years:
        part_out = temp_dir / f"codes_std_{y}.parquet"
        part_files.append(part_out)
        if part_out.exists():
            print(f"Year {y} part already exists: {part_out.name}. Skipping.")
            continue

        print(f"Joining code map for Year {y}...")
        start_y = time.time()
        query = f"""
            COPY (
                SELECT 
                    t.row_id,
                    t.year,
                    t.month,
                    t.hs_code,
                    t.goods_description,
                    m.ahtn8,
                    m.sh6,
                    m.hd4,
                    m.ch2,
                    m.hs_extra,
                    m.code_len_orig,
                    m.code_fix,
                    m.code_flag,
                    m.ends_00,
                    m.right_padded
                FROM read_parquet('{slim_file.as_posix()}') t
                LEFT JOIN read_parquet('{code_map_file.as_posix()}') m
                  ON t.hs_code = m.hs_code
                WHERE t.year = {y}
            ) TO '{part_out.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
        """
        con.execute(query)
        print(f"Year {y} completed in {time.time() - start_y:.1f}s.")

    # Combine the yearly files into a single unified Parquet dataset
    print(f"Merging yearly parts into {output_file.name}...")
    parts_glob = (temp_dir / "codes_std_*.parquet").as_posix()
    merge_query = f"""
        COPY (
            SELECT * FROM read_parquet('{parts_glob}')
        ) TO '{output_file.as_posix()}' (FORMAT PARQUET, COMPRESSION 'ZSTD');
    """
    con.execute(merge_query)
    print(f"Final file {output_file.name} created successfully.")


def stage_3_generate_reports(con, output_file: Path, tables_dir: Path):
    """Generate diagnostic summary tables for code fixes and flags."""
    print("\n--- Stage 3: Generating Diagnostic Tables ---")
    tables_dir.mkdir(parents=True, exist_ok=True)

    out_csv = tables_dir / "a4_code_fix_counts.csv"
    if not out_csv.exists():
        print(f"Generating {out_csv.name}...")
        con.execute(f"""
            COPY (
                SELECT 
                    year,
                    code_fix,
                    code_flag,
                    count(*) AS n_transactions,
                    round(count(*) * 100.0 / sum(count(*)) OVER (PARTITION BY year), 4) AS pct_of_year
                FROM read_parquet('{output_file.as_posix()}')
                GROUP BY year, code_fix, code_flag
                ORDER BY year, n_transactions DESC
            ) TO '{out_csv.as_posix()}' (HEADER, DELIMITER ',');
        """)
        print(f"Saved {out_csv.name}.")
    else:
        print(f"{out_csv.name} already exists. Skipping.")


def main():
    params = load_params()
    con, _ = get_connection(params)

    interim_dir = ROOT / params["paths"]["interim_dir"]
    tables_dir = ROOT / params["paths"]["reports_dir"] / "tables"

    slim_file = interim_dir / "transactions_slim.parquet"
    code_map_file = interim_dir / "code_map.parquet"
    output_file = interim_dir / "codes_standardized.parquet"

    if not slim_file.exists():
        raise FileNotFoundError(f"transactions_slim.parquet not found at {slim_file}")

    try:
        stage_1_build_code_map(con, slim_file, code_map_file)
        stage_2_join_standardized_codes(con, slim_file, code_map_file, output_file, params)
        stage_3_generate_reports(con, output_file, tables_dir)
        print("\nTrack A4 pipeline execution complete.")
    finally:
        con.close()


if __name__ == "__main__":
    main()