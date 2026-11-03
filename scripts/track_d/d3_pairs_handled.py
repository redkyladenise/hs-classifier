import os
import sys
import yaml
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

# 1. Create handling.py exactly as specified for Track D
def generate_handling_py():
    handling_path = Path("src/hsclf/models/handling.py")
    handling_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not handling_path.exists():
        code = '''import pandas as pd

def apply_h1(df):
    """Majority Rule: highest weight, tie-break with smaller code."""
    res = df.sort_values(by=['group_l1', 'weight', 'ahtn8'], ascending=[True, False, True])
    res = res.drop_duplicates(subset=['group_l1'], keep='first').copy()
    res['weight'] = 1.0
    return res

def apply_h2(df):
    """Drop Conflicted: keep only items with exactly 1 code."""
    counts = df.groupby('group_l1').size()
    valid = counts[counts == 1].index
    return df[df['group_l1'].isin(valid)].copy()

def apply_h3(df):
    """Down-weight: halve the weights of conflicting items."""
    counts = df.groupby('group_l1').size()
    conflicted = set(counts[counts > 1].index)
    res = df.copy()
    mask = res['group_l1'].isin(conflicted)
    res.loc[mask, 'weight'] = res.loc[mask, 'weight'] * 0.5
    return res
'''
        with open(handling_path, "w") as f:
            f.write(code)
        print(f"Created {handling_path}")

def reapply_eligibility(df, min_desc):
    """Re-applies the C1 eligibility flags for codes that still meet the threshold."""
    for lvl in ['ch2', 'hd4', 'sh6', 'ahtn8']:
        counts = df.groupby(lvl)['group_l1'].nunique()
        valid = set(counts[counts >= min_desc].index)
        df[f'elig_{lvl}'] = df[lvl].isin(valid)
    return df

def main():
    print("=" * 60)
    print("Track D - Step D3: Build Handled Real Training Pairs")
    print("=" * 60)

    generate_handling_py()
    
    # Import the newly created handlers
    sys.path.append('.')
    from src.hsclf.models.handling import apply_h1, apply_h2, apply_h3

    # Load threshold from params
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
    min_desc = params['min_unique_descriptions']

    con = duckdb.connect()
    print("Loading raw training pairs...")
    raw_df = con.execute("SELECT * FROM 'data/processed/train_pairs_main.parquet'").df()
    status_df = con.execute("SELECT group_l1, split FROM 'data/processed/description_status.parquet'").df()
    
    # Identify non-train splits to test for leakage
    val_test_groups = set(status_df[status_df['split'] != 'train']['group_l1'])

    code_counts = raw_df.groupby('group_l1').size()
    n_desc_raw = raw_df['group_l1'].nunique()
    conflicting_groups = set(code_counts[code_counts > 1].index)
    n_conflicting = len(conflicting_groups)

    print(f"Raw pairs loaded: {len(raw_df):,} pairs across {n_desc_raw:,} descriptions.")
    print(f"Found {n_conflicting:,} conflicting descriptions.")

    print("\nApplying H1 (Majority Rule)...")
    h1_df = apply_h1(raw_df)

    print("Applying H2 (Drop Conflicted)...")
    h2_df = apply_h2(raw_df)

    print("Applying H3 (Down-weight)...")
    h3_df = apply_h3(raw_df)

    # Compliance Checks per File 6
    print("\nRunning roadmap compliance checks...")
    
    # Check 1: H1 has one pair per desc and same desc count as raw
    assert len(h1_df) == n_desc_raw, "H1 Pair count mismatch!"
    assert h1_df['group_l1'].nunique() == n_desc_raw, "H1 Description count mismatch!"
    
    # Check 2: H2 desc count equals raw minus conflicting
    assert h2_df['group_l1'].nunique() == (n_desc_raw - n_conflicting), "H2 Description count mismatch!"
    
    # Check 3: H3 keeps all pairs, conflicting sum to 0.5
    assert len(h3_df) == len(raw_df), "H3 Pair count mismatch!"
    conf_sum = h3_df[h3_df['group_l1'].isin(conflicting_groups)].groupby('group_l1')['weight'].sum()
    if not conf_sum.empty:
        assert np.allclose(conf_sum, 0.5), "H3 conflicting weights do not sum to 0.5!"
        
    # Check 4: No val or test group appears in any file
    for df, name in zip([h1_df, h2_df, h3_df], ['H1', 'H2', 'H3']):
        leakage = set(df['group_l1']).intersection(val_test_groups)
        assert len(leakage) == 0, f"{name} contains val/test data!"
        
    print(" [PASS] All checks passed successfully.")

    # Save Handled Pairs
    out_dir = Path("data/processed")
    h1_df.to_parquet(out_dir / "train_pairs_main_h1.parquet", index=False)
    h2_df.to_parquet(out_dir / "train_pairs_main_h2.parquet", index=False)
    h3_df.to_parquet(out_dir / "train_pairs_main_h3.parquet", index=False)

    # Generate Summary CSV
    summary = []
    for name, df in zip(['raw', 'h1', 'h2', 'h3'], [raw_df, h1_df, h2_df, h3_df]):
        summary.append({
            'variant': name,
            'descriptions': df['group_l1'].nunique(),
            'pairs': len(df),
            'total_weight': round(df['weight'].sum(), 2)
        })
        
    sum_df = pd.DataFrame(summary)
    sum_path = Path("reports/tables/d3_pairs_summary.csv")
    sum_path.parent.mkdir(parents=True, exist_ok=True)
    sum_df.to_csv(sum_path, index=False)
    
    print("\n--- Handled Pairs Summary ---")
    print(sum_df.to_string(index=False))
    print(f"\nSaved summary to: {sum_path}")

if __name__ == "__main__":
    main()