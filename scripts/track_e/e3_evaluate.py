import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np

def calculate_hit_at_5(df, level):
    hits = []
    for _, row in df.iterrows():
        # True code string truncated to the target level
        true_code = str(row['majority_ahtn8'])[:level] if pd.notna(row['majority_ahtn8']) else ""
        
        # Extracted retrieved codes (ignoring 'Other' which was handled in search.py)
        retrieved = row.get('retrieved_codes', [])
        if retrieved is None:
            retrieved = []
            
        ret_codes = [str(c)[:level] for c in retrieved[:5] if pd.notna(c)]
        
        if true_code != "" and true_code in ret_codes:
            hits.append(1)
        else:
            hits.append(0)
    
    return np.mean(hits) if hits else 0.0

def main():
    print("--- E3: Calculating Hit@5 and Setting Rules ---")
    
    print("-> Loading search results...")
    df = pd.read_parquet('data/processed/retrieval_eval_e3')
    
    print("-> Calculating Overall Hit@5 at Levels 2, 4, 6, and 8...")
    hit_2 = calculate_hit_at_5(df, 2)
    hit_4 = calculate_hit_at_5(df, 4)
    hit_6 = calculate_hit_at_5(df, 6)
    hit_8 = calculate_hit_at_5(df, 8)
    
    # File 6 Rule 1: display_level is deepest level >= 60%
    display_level = 4 # File 6 default
    if hit_8 >= 0.60: display_level = 8
    elif hit_6 >= 0.60: display_level = 6
    elif hit_4 >= 0.60: display_level = 4
    elif hit_2 >= 0.60: display_level = 2
    
    print("\n[Overall Accuracy]")
    print(f"Level 2 (Chapter):    {hit_2:.2%}")
    print(f"Level 4 (Heading):    {hit_4:.2%}")
    print(f"Level 6 (Subheading): {hit_6:.2%}")
    print(f"Level 8 (AHTN8):      {hit_8:.2%}")
    print(f"=> RULE APPLIED: display_level frozen at {display_level}")
    
    print("\n-> Calculating Level 6 Hit@5 by Similarity Bands...")
    bins = [-np.inf, 0.3, 0.5, 0.7, 0.9, np.inf]
    labels = ['<0.3', '0.3-0.5', '0.5-0.7', '0.7-0.9', '>=0.9']
    df['sim_band'] = pd.cut(df['max_similarity'], bins=bins, labels=labels, right=False)
    
    band_results = []
    min_similarity = 0.5 # File 6 default
    found_min_sim = False
    
    threshold_map = {'<0.3': 0.0, '0.3-0.5': 0.3, '0.5-0.7': 0.5, '0.7-0.9': 0.7, '>=0.9': 0.9}
    
    for label in labels:
        band_df = df[df['sim_band'] == label]
        count = len(band_df)
        if count == 0:
            band_hit_6 = 0.0
        else:
            band_hit_6 = calculate_hit_at_5(band_df, 6)
            
        band_results.append({
            'Similarity_Band': label,
            'Query_Count': count,
            'Hit_at_5_Level_6': band_hit_6
        })
        
        # File 6 Rule 2: min_similarity is lowest band where L6 Hit@5 >= 50%
        if not found_min_sim and band_hit_6 >= 0.50:
            min_similarity = threshold_map[label]
            found_min_sim = True

    print("\n[Similarity Band Analysis (Level 6)]")
    band_df_out = pd.DataFrame(band_results)
    for _, row in band_df_out.iterrows():
        print(f"Band {row['Similarity_Band']:>8}: {row['Hit_at_5_Level_6']:>7.2%} (Count: {row['Query_Count']})")
    
    print(f"=> RULE APPLIED: min_similarity frozen at {min_similarity}")
    
    # Save Report
    Path("reports/tables").mkdir(parents=True, exist_ok=True)
    report_df = pd.DataFrame({
        'Metric': ['Hit@5_L2', 'Hit@5_L4', 'Hit@5_L6', 'Hit@5_L8', 'Frozen_Display_Level', 'Frozen_Min_Similarity'],
        'Value': [hit_2, hit_4, hit_6, hit_8, display_level, min_similarity]
    })
    
    # Combine with bands for CSV export
    final_export = pd.concat([report_df, band_df_out], ignore_index=True)
    final_export.to_csv('reports/tables/e3_validation.csv', index=False)
    print("\n E3 Complete! Saved to reports/tables/track_e/e3_validation.csv")

if __name__ == "__main__":
    main()