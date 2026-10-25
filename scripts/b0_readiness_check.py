"""
scripts/b0_readiness_check.py

Verifies readiness for Track B:
1. Checks that required Track A and Track F files exist.
2. Checks that data/audit/ is in .gitignore.
3. Computes the baseline counts in the test split within the 2023-2024 audit window.
"""

from pathlib import Path
import duckdb
from hsclf.data.io import get_connection

REQUIRED_FILES = [
    Path("data/processed/unique_descriptions.parquet"),
    Path("data/processed/transactions_grouped.parquet"),
    Path("data/processed/split_assignments.parquet"),
    Path("data/processed/description_status.parquet"),
    Path("data/processed/training_pool.parquet"),
    Path("data/reference/ahtn_2022_scope_reference.parquet"),
]

def check_gitignore():
    gitignore_path = Path(".gitignore")
    if not gitignore_path.exists():
        print("[FAIL] .gitignore does not exist!")
        return False
    content = gitignore_path.read_text(encoding="utf-8")
    patterns = [line.strip() for line in content.splitlines() if line.strip()]
    
    if "data/" in patterns or "data" in patterns or "data/audit/" in patterns or "data/audit" in patterns:
        print("[PASS] data/ is listed in .gitignore (data/audit/ is protected).")
        return True
    else:
        print("[WARNING] 'data/' was NOT found in .gitignore. Please protect audit data.")
        return False

def check_files():
    all_ok = True
    for f in REQUIRED_FILES:
        if f.exists():
            print(f"[PASS] Found: {f}")
        else:
            print(f"[FAIL] Missing required file: {f}")
            all_ok = False
    return all_ok

def audit_window_recount():
    res = get_connection()
    con = res[0] if isinstance(res, tuple) else res
    print("\n--- Auditing Test Split (Window: 2023-2024) ---")
    
    query = """
    WITH test_tx AS (
        SELECT 
            t.group_l1,
            t.group_l2,
            t.ch2,
            t.ahtn8,
            t.year
        FROM 'data/processed/transactions_grouped.parquet' t
        JOIN 'data/processed/split_assignments.parquet' s
            ON t.group_l2 = s.group_l2
        WHERE s.split = 'test'
          AND t.year IN (2023, 2024)
    ),
    desc_summary AS (
        SELECT 
            group_l1,
            group_l2,
            ch2,
            COUNT(*) AS n_tx,
            COUNT(DISTINCT ahtn8) AS n_codes_ahtn8
        FROM test_tx
        GROUP BY group_l1, group_l2, ch2
    )
    SELECT 
        COUNT(*) AS total_descriptions,
        COUNT(CASE WHEN n_tx = 1 THEN 1 END) AS singleton_descriptions,
        COUNT(CASE WHEN n_tx >= 2 THEN 1 END) AS repeated_descriptions,
        COUNT(CASE WHEN n_tx >= 2 AND n_codes_ahtn8 > 1 THEN 1 END) AS conflicting_repeated_descriptions,
        COUNT(CASE WHEN n_tx >= 2 AND n_codes_ahtn8 = 1 THEN 1 END) AS non_conflicting_repeated_descriptions,
        ROUND(100.0 * COUNT(CASE WHEN n_tx >= 2 AND n_codes_ahtn8 > 1 THEN 1 END) / NULLIF(COUNT(CASE WHEN n_tx >= 2 THEN 1 END), 0), 2) AS conflict_rate_on_repeated_pct
    FROM desc_summary;
    """
    
    result = con.execute(query).df()
    print(result.to_string(index=False))
    
    # Save log output
    out_dir = Path("docs")
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / "audit_log.md", "a", encoding="utf-8") as f:
        f.write("\n\n### B0 Readiness Recount (2023-2024 Window in Test Split)\n\n")
        headers = list(result.columns)
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
        for _, row in result.iterrows():
            f.write("| " + " | ".join(str(val) for val in row.values) + " |\n")
        f.write("\n")
    print(f"\n[INFO] Recount logged to docs/audit_log.md.")

def main():
    print("=== Step B0: Readiness Check ===")
    g_ok = check_gitignore()
    f_ok = check_files()
    if f_ok and g_ok:
        audit_window_recount()
        print("\n[SUCCESS] Step B0 verification complete. Ready for Step B1.")
    else:
        print("\n[STOP] Please resolve the missing prerequisites before proceeding.")

if __name__ == "__main__":
    main()