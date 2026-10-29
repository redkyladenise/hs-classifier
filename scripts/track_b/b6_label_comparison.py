import pandas as pd
from sklearn.metrics import cohen_kappa_score

# 1. Load both rounds
df_main = pd.read_csv("data/audit/labels_main.csv")
df_relabel = pd.read_csv("data/audit/labels_relabel.csv")

# Ensure sample_id is string
df_main["sample_id"] = df_main["sample_id"].astype(str)
df_relabel["sample_id"] = df_relabel["sample_id"].astype(str)

# 2. Reshape to code-level pairs (sample_id, code_idx, label)
def melt_labels(df, round_name):
    records = []
    for _, row in df.iterrows():
        sid = row["sample_id"]
        for idx in [1, 2, 3]:
            col_code = f"code_{idx}"
            col_label = f"label_{idx}"
            if col_code in row and pd.notna(row[col_code]) and str(row[col_code]).strip() != "":
                records.append({
                    "sample_id": sid,
                    "code_idx": idx,
                    "code": str(row[col_code]).strip(),
                    f"label_{round_name}": str(row[col_label]).strip() if pd.notna(row[col_label]) else "MISSING"
                })
    return pd.DataFrame(records)

pairs_main = melt_labels(df_main, "round1")
pairs_relabel = melt_labels(df_relabel, "round2")

# 3. Inner join on sample_id, code_idx, and code
paired = pd.merge(pairs_relabel, pairs_main, on=["sample_id", "code_idx", "code"], how="inner")

# Infer stratum based on sample_id if not present
# Stratum A: MAIN_001 to MAIN_090
def get_stratum(sid):
    try:
        num = int(sid.replace("MAIN_", ""))
        return "Stratum A" if num <= 90 else "Strata B/C"
    except:
        return "Unknown"

paired["stratum"] = paired["sample_id"].apply(get_stratum)

# 4. Metrics function
def calc_metrics(df_sub):
    total = len(df_sub)
    if total == 0:
        return 0, 0, 0
    agreed = (df_sub["label_round1"] == df_sub["label_round2"]).sum()
    raw_agreement = agreed / total
    kappa = cohen_kappa_score(df_sub["label_round1"], df_sub["label_round2"])
    return total, raw_agreement, kappa

tot, po, kappa = calc_metrics(paired)
tot_a, po_a, kappa_a = calc_metrics(paired[paired["stratum"] == "Stratum A"])
tot_bc, po_bc, kappa_bc = calc_metrics(paired[paired["stratum"] == "Strata B/C"])

print(f"\n{'='*45}")
print(f"GATE B3 RELIABILITY RESULTS (Pre-adjudication)")
print(f"{'='*45}")
print(f"Total Code-Level Pairs Evaluated: {tot}")
print(f"  - Stratum A Pairs: {tot_a}")
print(f"  - Strata B/C Pairs: {tot_bc}\n")

print(f"OVERALL:")
print(f"  Raw Agreement (Po): {po:.2%} (Threshold: >= 80%) -> {'PASS' if po >= 0.8 else 'FAIL'}")
print(f"  Cohen's Kappa (k):  {kappa:.4f} (Threshold: >= 0.60) -> {'PASS' if kappa >= 0.6 else 'FAIL'}\n")

print(f"DISAGGREGATED:")
print(f"  Stratum A:   Po = {po_a:.2%}, Kappa = {kappa_a:.4f}")
print(f"  Strata B/C:  Po = {po_bc:.2%}, Kappa = {kappa_bc:.4f}")
print(f"{'='*45}\n")

# 5. Extract disagreements
disagreements = paired[paired["label_round1"] != paired["label_round2"]]
print(f"Disagreements Found: {len(disagreements)}")
if len(disagreements) > 0:
    print(disagreements[["sample_id", "code", "label_round1", "label_round2"]].to_string(index=False))
    disagreements.to_csv("data/audit/disagreements_b6.csv", index=False)
    print("\nSaved disagreement table to: data/audit/disagreements_b6.csv")