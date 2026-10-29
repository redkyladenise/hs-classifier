import pandas as pd

# Load your labeled main sample
df = pd.read_csv("data/audit/labels_main.csv")

# 1. Stratify by Stratum
# MAIN_001 to MAIN_090 are Stratum A (conflicts)
# MAIN_091 to MAIN_135 are Stratum B (clean repeated)
# MAIN_136 to MAIN_180 are Stratum C (singletons)

# If your CSV already has a 'stratum' column, filter directly.
# Otherwise, slice by sample_id index:
stratum_a = df.iloc[:90].copy()
stratum_bc = df.iloc[90:].copy()

# 2. Sample: 10 from Stratum A, 30 from Stratum B/C (seed ensures reproducibility)
sample_a = stratum_a.sample(n=10, random_state=42)
sample_bc = stratum_bc.sample(n=30, random_state=42)

# 3. Combine and shuffle the 40 items
b6_sample = (
    pd.concat([sample_a, sample_bc])
    .sample(frac=1.0, random_state=42)
    .reset_index(drop=True)
)

# 4. Strip existing labels, confidence, and notes (create the blind sheet)
keep_cols = [
    "sample_id",
    "goods_description_raw",
    "goods_description_norm",
    "kind_identified",
    "code_1",
    "official_chain_1",
    "code_2",
    "official_chain_2",
    "code_3",
    "official_chain_3",
]
available_cols = [c for c in keep_cols if c in b6_sample.columns]
blind_sheet = b6_sample[available_cols].copy()

# Add blank adjudication columns to fill out during B6
blind_sheet["kind_identified"] = ""
blind_sheet["label_1"] = ""
blind_sheet["label_2"] = ""
blind_sheet["label_3"] = ""
blind_sheet["confidence_rating"] = ""
blind_sheet["notes"] = ""

# 5. Export blind template
blind_sheet.to_csv("data/audit/labels_relabel_blank.csv", index=False)
print(f"Sample drawn: {len(blind_sheet)} rows saved to data/audit/labels_relabel_blank.csv")