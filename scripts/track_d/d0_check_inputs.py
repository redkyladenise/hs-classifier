import os
import sys
import hashlib
from pathlib import Path
import psutil

try:
    import duckdb
except ImportError:
    print("ERROR: duckdb is not installed.")
    sys.exit(1)

try:
    import sklearn
except ImportError:
    print("ERROR: scikit-learn is not installed.")
    sys.exit(1)


def compute_sha256(filepath: Path) -> str:
    """Computes the SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def check_file(path_str: str) -> dict:
    """Checks file existence, size in MB, and SHA-256."""
    p = Path(path_str)
    if not p.exists():
        return {"path": path_str, "exists": False, "size_mb": 0.0, "sha256": "MISSING"}
    size_mb = p.stat().st_size / (1024 * 1024)
    return {"path": path_str, "exists": True, "size_mb": round(size_mb, 2), "sha256": compute_sha256(p)}


def main():
    print("=" * 60)
    print("Track D - Step D0: Resource & Input Verification")
    print("=" * 60)

    # 1. System specs check
    free_ram_gb = psutil.virtual_memory().available / (1024 ** 3)
    free_disk_gb = psutil.disk_usage(".").free / (1024 ** 3)
    print(f"Python version : {sys.version.split()[0]}")
    print(f"scikit-learn   : {sklearn.__version__}")
    print(f"DuckDB version : {duckdb.__version__}")
    print(f"Available RAM  : {free_ram_gb:.2f} GB")
    print(f"Free Disk      : {free_disk_gb:.2f} GB")

    if free_disk_gb < 6.0:
        print("WARNING: Less than 6 GB of disk space free. Track D requires ~6 GB for models.")

    # 2. Key files to inspect
    files_to_check = [
        "data/processed/train_pairs_main.parquet",
        "data/processed/desc_code_counts.parquet",
        "data/processed/unique_descriptions.parquet",
        "data/processed/hierarchy_main.parquet",
        "models/v1/main/manifest.json",
        "data/audit/verified_set.parquet",
        "data/audit/labels_frozen.csv",
        "data/audit/sample_key.csv",
    ]

    results = []
    missing_files = []

    for f in files_to_check:
        res = check_file(f)
        results.append(res)
        status = "OK" if res["exists"] else "MISSING"
        print(f"[{status}] {f} ({res['size_mb']} MB)")
        if not res["exists"]:
            missing_files.append(f)

    # 3. Inspect table row counts using DuckDB for confirmed files
    con = duckdb.connect()
    row_counts = {}

    if Path("data/processed/train_pairs_main.parquet").exists():
        row_counts["train_pairs_main"] = con.execute(
            "SELECT count(*), count(distinct group_l1) FROM 'data/processed/train_pairs_main.parquet'"
        ).fetchone()

    if Path("data/audit/verified_set.parquet").exists():
        row_counts["verified_set"] = con.execute(
            "SELECT count(*) FROM 'data/audit/verified_set.parquet'"
        ).fetchone()[0]

    if Path("data/audit/labels_frozen.csv").exists():
        row_counts["labels_frozen"] = con.execute(
            "SELECT count(*) FROM 'data/audit/labels_frozen.csv'"
        ).fetchone()[0]

    # 4. Write findings to docs/noise_log.md
    Path("docs").mkdir(parents=True, exist_ok=True)
    noise_log_path = Path("docs/noise_log.md")

    with open(noise_log_path, "w", encoding="utf-8") as f:
        f.write("# Track D: Noise Log & Resource Verification\n\n")
        f.write("## Environment\n")
        f.write(f"- Python: {sys.version.split()[0]}\n")
        f.write(f"- scikit-learn: {sklearn.__version__}\n")
        f.write(f"- DuckDB: {duckdb.__version__}\n")
        f.write(f"- Available RAM at start: {free_ram_gb:.2f} GB\n")
        f.write(f"- Free Disk space: {free_disk_gb:.2f} GB\n")
        f.write(f"- Locked test sample size (`d_test_sample_size`): 300,000\n\n")

        f.write("## File Verification Table\n\n")
        f.write("| File Path | Status | Size (MB) | SHA-256 |\n")
        f.write("|:---|:---:|:---:|:---|\n")
        for r in results:
            stat = "Verified" if r["exists"] else "MISSING"
            f.write(f"| `{r['path']}` | {stat} | {r['size_mb']} | `{r['sha256']}` |\n")

        f.write("\n## Table Row Counts\n\n")
        for name, cnt in row_counts.items():
            f.write(f"- **{name}**: {cnt}\n")

    print("\nVerification log written to docs/noise_log.md")

    if missing_files:
        print("\nERROR: One or more critical files are missing! Check the list above.")
        sys.exit(1)
    else:
        print("\nGate D0 Status: PASS. All required resources are verified.")


if __name__ == "__main__":
    main()