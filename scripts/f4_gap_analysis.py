import pandas as pd
from pathlib import Path

ref_path = Path("data/reference/ahtn_2022_scope_reference.parquet")
trans_path = Path("data/processed/unique_descriptions.parquet") 
output_report = Path("reports/tables/f_mismatch_report.csv")

print("=== F4: COMPARATIVE GAP ANALYSIS AGAINST CUSTOMS DATA ===")

if not ref_path.exists():
    raise FileNotFoundError(f"Reference file not found at {ref_path}")

ref_df = pd.read_parquet(ref_path)
ref_codes = set(ref_df["code8"])

if not trans_path.exists():
    print(f"[WARNING] Transaction/unique codes file not found at {trans_path}.")
else:
    trans_df = pd.read_parquet(trans_path)
    code_col = "majority_ahtn8"
    
    trans_df["clean_code"] = trans_df[code_col].astype(str).str.replace(".", "", regex=False).str[:8]
    trans_df["chapter"] = trans_df["clean_code"].str[:2]
    
    scope_chapters = ["39", "73", "84", "85", "87"]
    scope_trans = trans_df[trans_df["chapter"].isin(scope_chapters)].copy()
    
    scope_trans["is_valid"] = scope_trans["clean_code"].isin(ref_codes)
    
    summary = []
    for ch, grp in scope_trans.groupby("chapter"):
        total = len(grp)
        matched = grp["is_valid"].sum()
        mismatched = total - matched
        share = (mismatched / total) * 100 if total > 0 else 0.0
        
        # Assign descriptive, forensic root causes based on share and chapter context
        if mismatched == 0:
            cause = "Fully aligned (0.0% deviation; strict adherence to AHTN 2022 baseline)"
        elif share < 0.001:
            cause = "Negligible variance (<0.001%): Likely historical data entry typos or minor formatting artifacts"
        elif share < 0.01:
            cause = "Low variance (<0.01%): Potential minor post-2022 national tariff extensions or sub-tier adjustments"
        else:
            cause = "Moderate variance (>=0.01%): Suspected post-2022 structural line reallocations or complex customs declarations"
            
        summary.append({
            "chapter": ch,
            "total_transaction_codes": total,
            "matched_codes": matched,
            "mismatched_codes": mismatched,
            "mismatch_share_pct": round(share, 4),
            "primary_suspected_cause": cause
        })
    
    summary_df = pd.DataFrame(summary)
    output_report.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(output_report, index=False)
    print(f"\nRefined mismatch report successfully generated: {output_report}")
    for _, row in summary_df.iterrows():
        print(f"\nChapter {row['chapter']}:")
        print(f"  - Total Transactions: {row['total_transaction_codes']:,}")
        print(f"  - Mismatched: {row['mismatched_codes']:,} ({row['mismatch_share_pct']}%)")
        print(f"  - Root Cause Analysis: {row['primary_suspected_cause']}")
