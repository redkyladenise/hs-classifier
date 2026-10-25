"""
scripts/track_b/b2_create_template.py

Creates the blank evaluation sheet template (label_sheet_template.csv).
Defines all standard column headers required for human labeling.
"""

from pathlib import Path
import pandas as pd

AUDIT_DIR = Path("data/audit")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATE_COLUMNS = [
    "sample_id",
    "goods_description_raw",
    "goods_description_norm",
    "kind_identified",
    "code_1",
    "official_chain_1",
    "label_1",
    "code_2",
    "official_chain_2",
    "label_2",
    "code_3",
    "official_chain_3",
    "label_3",
    "confidence_rating",
    "duration_minutes",
    "notes",
]


def create_template():
    df_template = pd.DataFrame(columns=TEMPLATE_COLUMNS)
    template_path = AUDIT_DIR / "label_sheet_template.csv"
    df_template.to_csv(template_path, index=False)
    print(f"[SUCCESS] Blank audit sheet template created at: {template_path}")
    print(f"Columns ({len(TEMPLATE_COLUMNS)}):")
    for col in TEMPLATE_COLUMNS:
        print(f" - {col}")


if __name__ == "__main__":
    create_template()