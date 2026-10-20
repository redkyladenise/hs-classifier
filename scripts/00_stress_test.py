
from pathlib import Path
import argparse
import ctypes
import platform
import sys
import threading
import time

import duckdb
import yaml
import psutil

ROOT = Path(__file__).resolve().parents[1]
PARAMS_PATH = ROOT / "config" / "params.yaml"


def get_free_ram_gb():
    """Return currently available physical RAM in decimal GB."""
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

    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024 / 1_000_000_000

    import os

    pages = os.sysconf("SC_AVPHYS_PAGES")
    page_size = os.sysconf("SC_PAGE_SIZE")
    return pages * page_size / 1_000_000_000


def get_connection(params):
    """Open DuckDB with the memory and thread limits from params.yaml."""
    temp_dir = ROOT / params["duckdb_temp_dir"]
    temp_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(":memory:")
    con.execute(
        f"SET memory_limit = '{params['duckdb_memory_limit_gb']}GB'"
    )
    con.execute(f"SET threads = {int(params['duckdb_threads'])}")
    con.execute("SET preserve_insertion_order = false")

    safe_temp_dir = str(temp_dir.resolve()).replace("'", "''")
    con.execute(f"SET temp_directory = '{safe_temp_dir}'")

    return con, temp_dir


def directory_size_bytes(directory):
    """Calculate the current total size of files in a directory."""
    return sum(
        file.stat().st_size
        for file in directory.rglob("*")
        if file.is_file()
    )


def sql_string(value):
    """Safely quote a path as a SQL string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def monitor_ram(stop_event, ram_readings, process_memory_readings):
    """Monitor available system RAM and this Python process's memory."""
    process = psutil.Process()

    while not stop_event.is_set():
        try:
            ram_readings.append(get_free_ram_gb())
            process_memory_readings.append(
                process.memory_info().rss / 1_000_000
            )
        except (OSError, psutil.Error):
            pass

        stop_event.wait(0.1)

def get_process_memory_mb():
    """Return this Python process's current memory usage in MB."""
    process = psutil.Process()
    return process.memory_info().rss / 1_000_000

def run_query(con, label, query, temp_dir):
    """Run a query and report elapsed time, RAM, and temp-disk usage."""
    print(f"\n--- {label} ---")
    temp_before = directory_size_bytes(temp_dir)
    readings = [get_free_ram_gb()]
    process_memory_readings = [get_process_memory_mb()]
    stop_event = threading.Event()

    monitor = threading.Thread(
        target=monitor_ram,
        args=(stop_event, readings, process_memory_readings),
        daemon=True,
    )
    monitor.start()

    start = time.perf_counter()

    try:
        result = con.execute(query).fetchall()
    finally:
        elapsed = time.perf_counter() - start
        stop_event.set()
        monitor.join()

    temp_after = directory_size_bytes(temp_dir)

    print(f"Elapsed time: {elapsed / 60:.2f} minutes")
    print(f"Lowest available RAM during query: {min(readings):.2f} GB")
    print(
        "Peak Python-process memory: "
        f"{max(process_memory_readings):.1f} MB"
    )
    print(f"Temporary directory before: {temp_before / 1_000_000:.2f} MB")
    print(f"Temporary directory after:  {temp_after / 1_000_000:.2f} MB")
    print(f"Temporary directory change: {(temp_after - temp_before) / 1_000_000:.2f} MB")
    print("Result:")
    for row in result:
        print(row)

    return elapsed, min(readings)


def main():
    parser = argparse.ArgumentParser(
        description="Stress-test DuckDB queries against selected Parquet years."
    )
    parser.add_argument(
        "target",
        choices=["2023", "2024", "2025", "all"],
        help="Test 2023, 2024, 2025, or all three years together.",
    )
    args = parser.parse_args()

    with PARAMS_PATH.open("r", encoding="utf-8") as file:
        params = yaml.safe_load(file)

    years = (
        [2023, 2024, 2025]
        if args.target == "all"
        else [int(args.target)]
    )

    raw_dir = ROOT / params["paths"]["raw_dir"]
    paths = []

    for year in years:
        path = raw_dir / f"{year}.parquet"
        if not path.is_file():
            raise SystemExit(f"STOP: Missing Parquet file: {path}")
        paths.append(path)

    print("=== DuckDB Memory Stress Test ===")
    print(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {platform.python_version()}")
    print(f"Target years: {', '.join(map(str, years))}")
    print(f"Free RAM before run: {get_free_ram_gb():.2f} GB")
    print(f"DuckDB memory limit: {params['duckdb_memory_limit_gb']} GB")
    print(f"DuckDB threads: {params['duckdb_threads']}")
    print(f"Chunk size in config: {params['chunk_size']}")
    print("Peak Python-process memory will be sampled automatically.")

    con, temp_dir = get_connection(params)

    try:
        settings = con.execute("""
            SELECT
                current_setting('memory_limit'),
                current_setting('threads'),
                current_setting('temp_directory')
        """).fetchone()

        print(f"Applied DuckDB memory limit: {settings[0]}")
        print(f"Applied DuckDB threads: {settings[1]}")
        print(f"Applied temp directory: {settings[2]}")

        # Use a UNION ALL so the all-years test scans each selected file.
        description_queries = []
        digit_length_queries = []

        for path in paths:
            parquet = sql_string(path.resolve())
            description_queries.append(
                "SELECT GOODSDESCRIPTION "
                f"FROM read_parquet({parquet})"
            )
            digit_length_queries.append(
                "SELECT length(CAST(HSCODE AS VARCHAR)) AS digit_length "
                f"FROM read_parquet({parquet})"
            )

        description_union = " UNION ALL ".join(description_queries)
        digit_union = " UNION ALL ".join(digit_length_queries)

        distinct_query = (
            "SELECT COUNT(DISTINCT GOODSDESCRIPTION) "
            f"FROM ({description_union}) AS descriptions"
        )

        digit_length_query = (
            "SELECT digit_length, COUNT(*) AS row_count "
            f"FROM ({digit_union}) AS codes "
            "GROUP BY digit_length ORDER BY digit_length"
        )

        run_query(
            con,
            "Query A: Count distinct goods descriptions",
            distinct_query,
            temp_dir,
        )

        run_query(
            con,
            "Query B: Count rows by HSCODE digit length",
            digit_length_query,
            temp_dir,
        )

    finally:
        con.close()

    print("\nStress-test queries completed.")
    print("Use Task Manager readings and the pass rule in decisions.md")
    print("to decide whether to proceed to the next test.")


if __name__ == "__main__":
    main()
