import os
import sys
import math
from pathlib import Path
import duckdb
import pandas as pd


def wilson_ci(k: int, n: int, confidence: float = 0.95):
    """Computes the Wilson score interval for a proportion k/n."""
    if n == 0:
        return 0.0, 0.0
    z = 1.959963984540054  # 95% confidence
    p = k / n
    denom = 1 + (z ** 2) / n
    center = (p + (z ** 2) / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) / n) + ((z ** 2) / (4 * (n ** 2))))) / denom
    ci_low = max(0.0, center - margin)
    ci_high = min(1.0, center + margin)
    return round(ci_low * 100, 2), round(ci_high * 100, 2)


def main():
    print("=" * 60)
    print("Track D - Step D1.2: Majority Rule vs. Verified Set (Stratum A)")
    print("=" * 60)

    con = duckdb.connect()

    # Join verified_set -> norm_descriptions -> unique_descriptions
    query = """
    SELECT 
        v.sample_id,
        v.stratum,
        v.goods_description_norm,
        v.verified_label_8,
        v.verified_label_6,
        v.verified_label_4,
        v.verified_label_2,
        u.majority_ahtn8,
        SUBSTRING(u.majority_ahtn8, 1, 6) AS majority_sh6,
        SUBSTRING(u.majority_ahtn8, 1, 4) AS majority_hd4,
        SUBSTRING(u.majority_ahtn8, 1, 2) AS majority_ch2
    FROM 'data/audit/verified_set.parquet' v
    INNER JOIN 'data/interim/norm_descriptions.parquet' nd 
        ON v.goods_description_norm = nd.desc_norm
    INNER JOIN 'data/processed/unique_descriptions.parquet' u 
        ON nd.desc_norm_id = u.desc_norm_id
    WHERE v.stratum = 'A'
    """

    df = con.execute(query).df()
    n_a = len(df)
    print(f"Total Stratum A records found: {n_a}")

    if n_a != 34:
        print(f"WARNING: Expected 34 Stratum A records, found {n_a}!")

    levels = [
        ("Level 2 (Chapter)", "majority_ch2", "verified_label_2"),
        ("Level 4 (Heading)", "majority_hd4", "verified_label_4"),
        ("Level 6 (Subheading)", "majority_sh6", "verified_label_6"),
        ("Level 8 (AHTN Line)", "majority_ahtn8", "verified_label_8"),
    ]

    results = []
    print("\n--- Agreement: Historical Broker Majority vs. Legally Verified Code ---")
    for level_name, maj_col, ver_col in levels:
        matches = int((df[maj_col] == df[ver_col]).sum())
        acc_pct = round((matches / n_a) * 100, 2)
        ci_low, ci_high = wilson_ci(matches, n_a)

        results.append({
            "level": level_name,
            "n_evaluated": n_a,
            "n_matches": matches,
            "accuracy_pct": acc_pct,
            "ci_low_95": ci_low,
            "ci_high_95": ci_high
        })
        print(f"{level_name:22}: {matches}/{n_a} ({acc_pct}%) [95% CI: {ci_low}% - {ci_high}%]")

    res_df = pd.DataFrame(results)

    out_dir = Path("reports/tables")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "d1_majority_vs_verified.csv"
    res_df.to_csv(out_path, index=False)
    print(f"\nSaved results table to: {out_path}")


if __name__ == "__main__":
    main()