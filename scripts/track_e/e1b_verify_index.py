import pandas as pd
import numpy as np
import scipy.sparse as sp

def main():
    print("--- E1b: Verifying the Retrieval Index ---")

    print("-> Loading index and reference files...")
    index_meta = pd.read_parquet('data/processed/retrieval/index_meta.parquet')
    unique_desc = pd.read_parquet('data/processed/unique_descriptions.parquet')
    splits = pd.read_parquet('data/processed/split_assignments.parquet')
    train_pairs = pd.read_parquet('data/processed/train_pairs_main.parquet')
    eval_sample = pd.read_parquet('data/processed/d_test_sample_ids.parquet')

    # 1. Leakage Check: Join index to splits
    # We use desc_norm_id to bridge to unique_descriptions, then group_l2 to bridge to splits
    merged = index_meta.merge(unique_desc[['desc_norm_id', 'group_l2']], on='desc_norm_id', how='left')
    merged = merged.merge(splits[['group_l2', 'split']], on='group_l2', how='left')

    val_test_leaks = merged[merged['split'].isin(['val', 'test'])]
    print(f"\n1. Split Leakage Check:")
    print(f"   -> Total items in index: {len(index_meta)}")
    print(f"   -> Items illegally in 'val' or 'test' split: {len(val_test_leaks)}")
    if len(val_test_leaks) == 0:
        print("    PASS: No test/val leakage into the index.")
    else:
        print("    FAIL: Index contains leaked items. Must rebuild E1.")

    # 2. Extra Descriptions Check
    index_ids = set(index_meta['group_l1'])
    train_ids = set(train_pairs['group_l1'])
    extras = index_ids - train_ids
    print(f"\n2. Extra Descriptions Check:")
    print(f"   -> Extra items in index not in train_pairs_main: {len(extras)}")

    # 3. Evaluation Sample Leakage Check
    eval_ids = set(eval_sample['group_l1'])
    eval_leaks = index_ids.intersection(eval_ids)
    print(f"\n3. Evaluation Sample Leakage Check:")
    print(f"   -> Items from evaluation sample leaking into index: {len(eval_leaks)}")
    if len(eval_leaks) == 0:
        print("    PASS: Evaluation sample is completely unseen by the index.")
    else:
        print("    FAIL: Evaluation sample leaked into the index.")

    # 4. Self-Match Test
    print("\n4. Self-Match Math Test (Chapter 85):")
    try:
        # Load the math matrix for Chapter 85
        ch85_matrix = sp.load_npz('data/processed/retrieval/index_ch85.npz')
        
        # Take the very first item (row 0) as our test query
        query_vector = ch85_matrix.getrow(0)
        
        # Compare it against the entire chapter
        similarities = ch85_matrix.dot(query_vector.T).toarray().flatten()
        
        best_match_idx = np.argmax(similarities)
        best_sim = similarities[best_match_idx]
        
        if best_match_idx == 0 and np.isclose(best_sim, 1.0, atol=1e-5):
            print(f"    PASS: Item 0 successfully matched itself with a similarity of {best_sim:.4f}")
        else:
            print(f"    FAIL: Self-match failed.")
            
    except FileNotFoundError:
        print("    Chapter 85 matrix not found. Skipping self-match test.")

if __name__ == "__main__":
    main()