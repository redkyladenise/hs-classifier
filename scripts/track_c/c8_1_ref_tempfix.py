import pandas as pd

def calculate_level_baselines(truth_df, test_ids, name):
    # 1. Filter ground truth for the test set
    df = truth_df[truth_df['group_l1'].isin(test_ids)].copy()
    
    # Create columns for each hierarchical level
    df['L2'] = df['ahtn8'].astype(str).str[:2]
    df['L4'] = df['ahtn8'].astype(str).str[:4]
    df['L6'] = df['ahtn8'].astype(str).str[:6]
    df['L8'] = df['ahtn8'].astype(str)
    
    m1_total = df['tx_count'].sum()
    
    # --- Fallback A: Blind Guess (Max volume code at each level) ---
    fb_a_l2 = (df.groupby('L2')['tx_count'].sum().max() / m1_total) * 100
    fb_a_l4 = (df.groupby('L4')['tx_count'].sum().max() / m1_total) * 100
    fb_a_l6 = (df.groupby('L6')['tx_count'].sum().max() / m1_total) * 100
    fb_a_l8 = (df.groupby('L8')['tx_count'].sum().max() / m1_total) * 100
    
    # --- Fallback B: Cheat Parent (Max volume code within known parent) ---
    # L2 parent is root (same as Fallback A)
    fb_b_l2 = fb_a_l2
    # L4 parent is L2
    fb_b_l4 = (df.groupby(['L2', 'L4'])['tx_count'].sum().groupby('L2').max().sum() / m1_total) * 100
    # L6 parent is L4
    fb_b_l6 = (df.groupby(['L4', 'L6'])['tx_count'].sum().groupby('L4').max().sum() / m1_total) * 100
    # L8 parent is L6
    fb_b_l8 = (df.groupby(['L6', 'L8'])['tx_count'].sum().groupby('L6').max().sum() / m1_total) * 100
    
    print(f"=== {name} ===")
    print(f"Fallback A (Blind Guess):")
    print(f"  L2: {fb_a_l2:.2f}% | L4: {fb_a_l4:.2f}% | L6: {fb_a_l6:.2f}% | L8: {fb_a_l8:.2f}%")
    print(f"Fallback B (Cheat Parent):")
    print(f"  L2: {fb_b_l2:.2f}% | L4: {fb_b_l4:.2f}% | L6: {fb_b_l6:.2f}% | L8: {fb_b_l8:.2f}%\n")

# 2. Load master tables
truth = pd.read_parquet('data/processed/desc_code_counts.parquet')
unseen_ids = pd.read_parquet('data/processed/test_unseen.parquet')['group_l1']
y2_ids = pd.read_parquet('data/processed/test_y2.parquet')['group_l1']

# 3. Execute math
calculate_level_baselines(truth, unseen_ids, "UNSEEN")
calculate_level_baselines(truth, y2_ids, "Y2 (2025)")