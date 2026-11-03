import duckdb
import pandas as pd
import numpy as np
import hashlib
from pathlib import Path
import sys

def get_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def main():
    print("=" * 60)
    print("Track D - Step D6.4A: Build 300k Test Sample")
    print("=" * 60)

    con = duckdb.connect()

    # 1. Pool & 2. Features
    print("Loading pool and joining features...")
    query_pool = """
        SELECT DISTINCT p.group_l1,
               substring(u.majority_ahtn8, 1, 2) as chapter,
               u.group_l2
        FROM read_parquet('data/processed/predictions_unseen/part_*.parquet') p
        JOIN read_parquet('data/processed/unique_descriptions.parquet') u
          ON p.group_l1 = u.desc_norm_id
    """
    pool_df = con.execute(query_pool).df()
    pool_size = len(pool_df)
    print(f"Pool size: {pool_size:,} distinct descriptions")

    # 3. Audit Descriptions
    query_audit = "SELECT DISTINCT group_l1 FROM read_csv_auto('data/audit/sample_key.csv')"
    audit_ids = set(con.execute(query_audit).df()['group_l1'])
    print(f"Audit IDs loaded: {len(audit_ids)}")
    
    # Verify all audit IDs are in pool
    pool_ids = set(pool_df['group_l1'])
    missing = audit_ids - pool_ids
    assert len(missing) == 0, f"Missing {len(missing)} audit IDs from pool!"
    
    # 4. Draw Sample (Stratified)
    audit_mask = pool_df['group_l1'].isin(audit_ids)
    audit_df = pool_df[audit_mask].copy()
    rem_df = pool_df[~audit_mask].copy()
    
    target_total = 300_000
    target_rem = target_total - len(audit_df)
    
    # Proportional allocation based on remaining pool
    chapter_counts = rem_df['chapter'].value_counts(normalize=True)
    sample_alloc = (chapter_counts * target_rem).round().astype(int)
    
    # Adjust rounding errors to hit exactly target_rem
    diff = target_rem - sample_alloc.sum()
    if diff != 0:
        sample_alloc.iloc[0] += diff
        
    print(f"Drawing {target_rem:,} additional samples stratified by chapter...")
    np.random.seed(42)
    
    sampled_dfs = []
    for chap, n_draw in sample_alloc.items():
        chap_df = rem_df[rem_df['chapter'] == chap]
        sampled_dfs.append(chap_df.sample(n=n_draw, random_state=42))
        
    final_sample = pd.concat([audit_df] + sampled_dfs).reset_index(drop=True)
    
    # Shuffle to mix audit IDs
    final_sample = final_sample.sample(frac=1, random_state=42).reset_index(drop=True)
    
    assert len(final_sample) == target_total, f"Sample size mismatch: {len(final_sample)}"
    assert final_sample['group_l1'].nunique() == target_total, "Duplicate IDs found!"
    
    # 5. Save
    out_path = Path("data/processed/d_test_sample_ids.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final_sample.to_parquet(out_path, index=False)
    
    checksum = get_sha256(out_path)
    print(f"\nSaved {target_total:,} records to {out_path}")
    print(f"SHA-256: {checksum}")
    print("Checklist passed: All audit IDs included, deduplicated, stratified by chapter.")

if __name__ == "__main__":
    main()