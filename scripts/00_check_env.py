from pathlib import Path
import ctypes
import platform
import re
import struct
import sys
from importlib.metadata import PackageNotFoundError, version

import duckdb
import yaml


ROOT = Path(__file__).resolve().parents[1]
PARAMS_PATH = ROOT / "config" / "params.yaml"

LIBRARIES = [
    "duckdb",
    "pandas",
    "pyarrow",
    "PyYAML",
    "ipykernel",
    "jupyter",
    "matplotlib",
    "pytest",
]

INTEGER_TYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT",
}


def get_free_ram_gb():
    """Return available physical RAM in decimal GB."""
    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)

        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(
            ctypes.byref(status)
        ):
            raise OSError("Could not retrieve available RAM.")

        return status.ullAvailPhys / 1_000_000_000

    # Linux
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024 / 1_000_000_000

    # macOS or another Unix-like system
    import os

    available_pages = os.sysconf("SC_AVPHYS_PAGES")
    page_size = os.sysconf("SC_PAGE_SIZE")
    return available_pages * page_size / 1_000_000_000


def get_connection(params):
    """Open DuckDB and apply the configured resource limits."""
    paths = params["paths"]

    temp_dir = ROOT / paths["interim_dir"] / "duckdb_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(":memory:")

    memory_limit = params["duckdb_memory_limit_gb"]
    threads = int(params["duckdb_threads"])

    con.execute(f"SET memory_limit = '{memory_limit}GB'")
    con.execute(f"SET threads = {threads}")

    escaped_temp_dir = str(temp_dir.resolve()).replace("'", "''")
    con.execute(f"SET temp_directory = '{escaped_temp_dir}'")

    return con


def quote_identifier(name):
    """Safely quote a column name for SQL."""
    return '"' + name.replace('"', '""') + '"'


def quote_string(value):
    """Safely quote a string value for SQL."""
    return "'" + str(value).replace("'", "''") + "'"


def is_integer_type(data_type):
    """Check whether a DuckDB type is an integer type."""
    return data_type.upper().strip() in INTEGER_TYPES


def main():
    with PARAMS_PATH.open("r", encoding="utf-8") as file:
        params = yaml.safe_load(file)

    # 1. Python environment
    print("=== Python Environment ===")
    print(f"Python version: {platform.python_version()}")

    is_64_bit = struct.calcsize("P") * 8 == 64
    print(f"64-bit Python: {is_64_bit}")
    print(f"Python executable: {sys.executable}")

    if not is_64_bit:
        raise SystemExit("STOP: A 64-bit Python installation is required.")

    # 2. Installed library versions
    print("\n=== Installed Library Versions ===")
    for package in LIBRARIES:
        try:
            print(f"{package}: {version(package)}")
        except PackageNotFoundError:
            print(f"{package}: NOT INSTALLED")

    # 3. Available RAM and configured memory limit
    print("\n=== Available RAM ===")
    free_ram_gb = get_free_ram_gb()
    memory_limit_gb = float(params["duckdb_memory_limit_gb"])

    print(f"Available RAM: {free_ram_gb:.2f} GB")
    print(f"Configured DuckDB memory limit: {memory_limit_gb} GB")

    if memory_limit_gb > free_ram_gb:
        print(
            "WARNING: DuckDB's configured memory limit is larger "
            "than the currently available RAM."
        )
    else:
        print("RAM check: PASS")

    # 4. Open DuckDB and report applied settings
    print("\n=== DuckDB Configuration ===")
    con = get_connection(params)

    settings = con.execute("""
        SELECT
            current_setting('memory_limit'),
            current_setting('threads'),
            current_setting('temp_directory')
    """).fetchone()

    expected_temp_dir = (
        ROOT / params["paths"]["interim_dir"] / "duckdb_tmp"
    ).resolve()

    print(f"Configured memory limit: {memory_limit_gb} GB")
    print(f"Applied memory limit: {settings[0]}")
    print(f"Configured threads: {params['duckdb_threads']}")
    print(f"Applied threads: {settings[1]}")
    print(f"Configured temp directory: {expected_temp_dir}")
    print(f"Applied temp directory: {settings[2]}")

    if int(settings[1]) != int(params["duckdb_threads"]):
        con.close()
        raise SystemExit("STOP: DuckDB thread limit does not match params.yaml.")

    if Path(settings[2]).resolve() != expected_temp_dir:
        con.close()
        raise SystemExit("STOP: DuckDB temp directory does not match params.yaml.")

    # 5. Check row counts first. Stop immediately on any mismatch.
    print("\n=== Parquet Row Counts ===")
    raw_dir = ROOT / params["paths"]["raw_dir"]
    counts = {}

    for year, expected_count in params["expected_rows_by_year"].items():
        filename = f"{year}.parquet"
        path = raw_dir / filename

        if not path.is_file():
            con.close()
            raise SystemExit(f"STOP: Missing Parquet file: {path}")

        parquet_path = quote_string(path.resolve())
        actual_count = con.execute(
            f"SELECT COUNT(*) FROM read_parquet({parquet_path})"
        ).fetchone()[0]

        counts[int(year)] = actual_count
        status = "PASS" if actual_count == expected_count else "FAIL"

        print(
            f"{filename}: {actual_count:,} rows "
            f"(expected {expected_count:,}) — {status}"
        )

    mismatches = [
        year
        for year, expected in params["expected_rows_by_year"].items()
        if counts[int(year)] != expected
    ]

    if mismatches:
        con.close()
        raise SystemExit(
            f"STOP: Row counts differ for {mismatches}. "
            "Check that the correct, complete files were copied."
        )

    # 6. Inspect schemas, HSCODE types, ID-like columns, and samples
    source_columns = params["source_columns"]
    required_keys = ["hs_code", "goods_description", "year", "month"]
    stored_hscode_types = {}

    for year in params["expected_rows_by_year"]:
        filename = f"{year}.parquet"
        path = raw_dir / filename
        parquet_path = quote_string(path.resolve())

        print(f"\n=== {filename}: Schema ===")
        schema = con.execute(
            f"DESCRIBE SELECT * FROM read_parquet({parquet_path})"
        ).fetchall()

        # Match source column names case-insensitively.
        actual_columns = {row[0].lower(): row for row in schema}

        for column_name, data_type, *_ in schema:
            print(f"{column_name}: {data_type}")

        missing = [
            source_columns[key]
            for key in required_keys
            if source_columns[key].lower() not in actual_columns
        ]

        if missing:
            con.close()
            raise SystemExit(
                f"STOP: {filename} is missing required columns: {missing}"
            )

        # Report the stored HSCODE type for each year.
        hscode_column = source_columns["hs_code"].lower()
        hscode_type = actual_columns[hscode_column][1]
        stored_hscode_types[int(year)] = hscode_type

        if is_integer_type(hscode_type):
            print(f"HSCODE stored type: {hscode_type} — PASS (integer)")
        else:
            print(
                f"WARNING: HSCODE stored type is {hscode_type}, "
                "not an integer type."
            )

        # ID-like columns are informational only.
        id_like_columns = [
            row[0]
            for row in schema
            if re.search(r"(^id$|_id$|id$|identifier|transaction)", row[0], re.I)
        ]

        print(
            "ID-like columns: "
            + (", ".join(id_like_columns) if id_like_columns else "None found")
        )

        # Show only the four required columns.
        selected_columns = []
        for key in required_keys:
            actual_name = actual_columns[source_columns[key].lower()][0]
            expression = quote_identifier(actual_name)

            if key == "goods_description":
                expression = (
                    f"LEFT(CAST({expression} AS VARCHAR), 80)"
                )

            selected_columns.append(
                f"{expression} AS {quote_identifier(key)}"
            )

        sample_query = (
            f"SELECT {', '.join(selected_columns)} "
            f"FROM read_parquet({parquet_path}) LIMIT 5"
        )

        sample_rows = con.execute(sample_query).fetchall()
        sample_columns = required_keys

        print(f"\n=== {filename}: Five Sample Rows ===")
        print(" | ".join(sample_columns))

        for row in sample_rows:
            print(" | ".join(
                str(value) if value is not None else "NULL"
                for value in row
            ))

    con.close()

    # 7. Summary for data_log.md
    print("\n=== HSCODE Stored Types for data_log.md ===")
    for year, data_type in sorted(stored_hscode_types.items()):
        print(f"- {year}: HSCODE = {data_type}")

    print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    main()