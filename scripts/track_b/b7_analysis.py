import numpy as np
import pandas as pd
from scipy import stats

# 1. Stratum Population Counts
POP_SIZES = {
    'A': 16587,
    'B': 88387,
    'C': 685084
}
N_TOTAL = sum(POP_SIZES.values())
WEIGHTS = {k: v / N_TOTAL for k, v in POP_SIZES.items()}

# Wilson score interval helper
def wilson_ci(k, n, confidence=0.95):
    if n == 0:
        return 0.0, 0.0
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    p = k / n
    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    spread = z * np.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2))) / denominator
    return max(0.0, centre - spread), min(1.0, centre + spread)

# Stratified proportion & standard error helper
def stratified_estimate(counts_dict, n_dict, weights=WEIGHTS):
    # p_h = k_h / n_h
    p_h = {h: counts_dict[h] / n_dict[h] if n_dict[h] > 0 else 0.0 for h in counts_dict}
    p_weighted = sum(weights[h] * p_h[h] for h in weights)
    # Stratified variance with finite population correction (fpc)
    var_strat = sum(
        (weights[h]**2) * (p_h[h] * (1 - p_h[h]) / (n_dict[h] - 1 if n_dict[h] > 1 else 1)) *
        (1 - n_dict[h] / POP_SIZES[h])
        for h in weights
    )
    se_strat = np.sqrt(max(0.0, var_strat))
    z = 1.95996
    ci_lower = max(0.0, p_weighted - z * se_strat)
    ci_upper = min(1.0, p_weighted + z * se_strat)
    return p_weighted, ci_lower, ci_upper

# 2. Load Frozen Labels
df = pd.read_csv("data/audit/labels_frozen.csv")
df["sample_id"] = df["sample_id"].astype(str)

# Ensure stratum column exists
if "stratum" not in df.columns:
    def assign_stratum(sid):
        try:
            num = int(str(sid).replace("MAIN_", ""))
            if num <= 90:
                return "A"
            elif num <= 135:
                return "B"
            else:
                return "C"
        except:
            return "C"
    df["stratum"] = df["sample_id"].apply(assign_stratum)

# Standardize label columns
label_cols = [c for c in ["label_1", "label_2", "label_3"] if c in df.columns]
for c in label_cols:
    df[c] = df[c].fillna("").astype(str).str.strip()

# 3. Derive Description-Level Verdict for Stratum A
def classify_conflict(row):
    labels = [row[c] for c in label_cols if row[c] != "" and row[c] != "nan"]
    if not labels:
        return "Undecidable unusable"
    
    # Check kind_identified
    if str(row.get("kind_identified", "")).strip().lower() == "no" or all(l == "Cannot check" for l in labels):
        return "Undecidable unusable"
    
    match_count = labels.count("Match")
    mismatch_count = labels.count("Mismatch")
    ambig_count = labels.count("Ambiguous")
    
    if match_count > 1:
        return "Multiple plausible"
    elif match_count == 1 and mismatch_count >= 1:
        return "One plausible others wrong"
    elif match_count == 1 and mismatch_count == 0:
        return "One plausible"
    elif mismatch_count == len(labels):
        return "All implausible"
    elif match_count == 0 and ambig_count > 0:
        return "Ambiguous between codes"
    else:
        return "Undecidable unusable"

df_a = df[df["stratum"] == "A"].copy()
df_a["description_verdict"] = df_a.apply(classify_conflict, axis=1)

# Item 1: Conflicting descriptions verdict distribution
verdict_categories = [
    "Multiple plausible",
    "One plausible others wrong",
    "One plausible",
    "All implausible",
    "Ambiguous between codes",
    "Undecidable unusable"
]

n_a = len(df_a)
v_counts = df_a["description_verdict"].value_counts().to_dict()

b7_item1_rows = []
for cat in verdict_categories:
    k = v_counts.get(cat, 0)
    pct = (k / n_a) if n_a > 0 else 0
    ci_low, ci_high = wilson_ci(k, n_a)
    b7_item1_rows.append({
        "verdict_category": cat,
        "sample_count": k,
        "sample_share": pct,
        "ci_lower_95": ci_low,
        "ci_upper_95": ci_high
    })

b7_item1 = pd.DataFrame(b7_item1_rows)
b7_item1.to_csv("reports/tables/track_b/b7_item1_conflict_breakdown.csv", index=False)

# Item 2: Hidden error rate (Non-conflicting Strata B and C labeled Mismatch)
# A description has error if label_1 is Mismatch
df_bc = df[df["stratum"].isin(["B", "C"])].copy()
df_b = df[df["stratum"] == "B"]
df_c = df[df["stratum"] == "C"]

k_b = (df_b["label_1"] == "Mismatch").sum()
n_b = len(df_b)
k_c = (df_c["label_1"] == "Mismatch").sum()
n_c = len(df_c)

hidden_err_b = k_b / n_b if n_b > 0 else 0
hidden_err_c = k_c / n_c if n_c > 0 else 0
b_ci_l, b_ci_u = wilson_ci(k_b, n_b)
c_ci_l, c_ci_u = wilson_ci(k_c, n_c)

# Weighted across Strata B & C frame
bc_total_pop = POP_SIZES['B'] + POP_SIZES['C']
w_b_norm = POP_SIZES['B'] / bc_total_pop
w_c_norm = POP_SIZES['C'] / bc_total_pop
weighted_hidden_err = (w_b_norm * hidden_err_b) + (w_c_norm * hidden_err_c)

b7_item2 = pd.DataFrame([
    {"stratum": "Stratum B (Repeated Clean)", "mismatch_count": k_b, "n": n_b, "share": hidden_err_b, "ci_lower": b_ci_l, "ci_upper": b_ci_u},
    {"stratum": "Stratum C (Singletons)", "mismatch_count": k_c, "n": n_c, "share": hidden_err_c, "ci_lower": c_ci_l, "ci_upper": c_ci_u},
    {"stratum": "Strata B+C Weighted", "mismatch_count": k_b + k_c, "n": n_b + n_c, "share": weighted_hidden_err, "ci_lower": None, "ci_upper": None}
])
b7_item2.to_csv("reports/tables/track_b/b7_item2_hidden_error.csv", index=False)

# Item 3: Declared codes flagged invalid_code
invalid_count = 0
total_codes_checked = 0
for _, row in df.iterrows():
    for c in label_cols:
        if row[c] != "" and row[c] != "nan":
            total_codes_checked += 1
            if str(row.get("invalid_code", "")).strip().lower() in ["yes", "true", "1"] or row[c] == "invalid_code":
                invalid_count += 1

inv_pct = invalid_count / total_codes_checked if total_codes_checked > 0 else 0
inv_low, inv_high = wilson_ci(invalid_count, total_codes_checked)
b7_item3 = pd.DataFrame([{
    "total_codes_checked": total_codes_checked,
    "invalid_code_count": invalid_count,
    "invalid_code_share": inv_pct,
    "ci_lower_95": inv_low,
    "ci_upper_95": inv_high
}])
b7_item3.to_csv("reports/tables/track_b/b7_item3_invalid_codes.csv", index=False)

# Item 4: Theoretical Ceiling (Share of conflicts where >=1 declared code is Match)
# P(at least one plausible)
at_least_one_plausible = sum(v_counts.get(c, 0) for c in ["Multiple plausible", "One plausible others wrong", "One plausible"])
ceiling_pct = at_least_one_plausible / n_a if n_a > 0 else 0
ceil_low, ceil_high = wilson_ci(at_least_one_plausible, n_a)

b7_item4 = pd.DataFrame([{
    "stratum_a_n": n_a,
    "at_least_one_plausible_count": at_least_one_plausible,
    "plausible_ceiling": ceiling_pct,
    "ci_lower_95": ceil_low,
    "ci_upper_95": ceil_high
}])
b7_item4.to_csv("reports/tables/track_b/b7_item4_ceiling.csv", index=False)

# Item 6: Construct Verified Set for Track D
# Criteria: Exactly one declared code is 'Match'
verified_records = []

for _, row in df.iterrows():
    labels = [row[c] for c in label_cols if row[c] != "" and row[c] != "nan"]
    match_indices = [i for i, c in enumerate(label_cols, 1) if row[c] == "Match"]
    
    if len(match_indices) == 1:
        match_idx = match_indices[0]
        code_raw = str(row[f"code_{match_idx}"]).strip().replace(".", "")
        if len(code_raw) >= 8:
            code_8 = code_raw[:8]
            code_6 = code_8[:6]
            code_4 = code_8[:4]
            code_2 = code_8[:2]
            
            verified_records.append({
                "sample_id": row["sample_id"],
                "stratum": row["stratum"],
                "goods_description_raw": row.get("goods_description_raw", ""),
                "goods_description_norm": row.get("goods_description_norm", ""),
                "verified_label_8": code_8,
                "verified_label_6": code_6,
                "verified_label_4": code_4,
                "verified_label_2": code_2,
                "source_code_index": match_idx
            })

df_verified = pd.DataFrame(verified_records)
df_verified.to_parquet("data/audit/verified_set.parquet", index=False)

# Log verified set sizes by stratum
ver_counts = df_verified["stratum"].value_counts().to_dict()
b7_item6 = pd.DataFrame([
    {"stratum": h, "sample_evaluated": len(df[df["stratum"]==h]), "verified_retained": ver_counts.get(h, 0), "retention_rate": ver_counts.get(h, 0)/len(df[df["stratum"]==h])}
    for h in ["A", "B", "C"]
])
b7_item6.to_csv("reports/tables/track_b/b7_item6_verified_set_sizes.csv", index=False)


print("\n" + "="*50)
print("B7 ANALYSIS PIPELINE COMPLETE")
print("="*50)
print(f"Item 1: Stratum A Conflicts Classified (n={n_a})")
print(b7_item1.to_string(index=False))
print(f"\nItem 2: Hidden Error Rate (Mismatch in Clean/Singleton):")
print(b7_item2.to_string(index=False))
print(f"\nItem 4: Conflict Plausibility Ceiling: {ceiling_pct:.2%} [{ceil_low:.2%}, {ceil_high:.2%}]")
print(f"\nItem 6: Verified Gold Set Retained: {len(df_verified)} of {len(df)} descriptions")
print(f"Saved: data/audit/verified_set.parquet")
print(f"Saved tables: reports/tables/track_b/b7_*.csv")
print("="*50)