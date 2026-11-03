import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

def wilson_ci(count, nobs, z=1.96):
    """Calculates the 95% Wilson confidence interval for proportions."""
    if nobs == 0: return 0.0, 0.0
    p = count / nobs
    denominator = 1 + z**2 / nobs
    centre_adjusted_prob = p + z**2 / (2 * nobs)
    adjusted_sd = np.sqrt((p * (1 - p) + z**2 / (4 * nobs)) / nobs)
    lower_bound = (centre_adjusted_prob - z * adjusted_sd) / denominator
    upper_bound = (centre_adjusted_prob + z * adjusted_sd) / denominator
    return max(0.0, lower_bound), min(1.0, upper_bound)

def clean_code(code, level):
    """Safely cast code to string, remove float decimals, and truncate."""
    if pd.isna(code): return ""
    c_str = str(code).split('.')[0]
    if c_str == 'nan' or c_str == 'None': return ""
    return c_str[:level]

def main():
    print("--- E4: Test Sample Evaluation (Phase 2) ---")
    
    # 1. Load Data
    print("-> Loading search results and historical baseline data...")
    res_dir = Path('data/processed/retrieval_eval_e4')
    df = pd.concat([pd.read_parquet(f) for f in res_dir.glob('*.parquet')], ignore_index=True)
    
    codes_df = pd.read_parquet('data/processed/retrieval/retrieval_codes.parquet')
    
    sample_key = pd.read_csv('data/audit/sample_key.csv')
    verified_set = pd.read_parquet('data/audit/verified_set.parquet')
    
    # 2. Build Frequency Baselines
    print("-> Computing frequency baselines...")
    def get_baseline_top5(level):
        # Clean the historical codes to target level
        codes_df['level_code'] = codes_df['code'].apply(lambda x: clean_code(x, level))
        codes_df_filtered = codes_df[codes_df['level_code'] != ""]
        
        grouped = codes_df_filtered.groupby(['level_code'])['declaration_count'].sum().reset_index()
        grouped['ch2'] = grouped['level_code'].str.slice(0, 2)
        
        top5 = grouped.sort_values(['ch2', 'declaration_count'], ascending=[True, False])
        top5 = top5.groupby('ch2').head(5)
        return top5.groupby('ch2')['level_code'].apply(list).to_dict()

    baselines = {L: get_baseline_top5(L) for L in [2, 4, 6, 8]}
    
    # 3. Calculate Core Metrics
    print("-> Calculating Hit@5, Baselines, and Intervals...")
    results = []
    
    def evaluate_slice(df_slice, band_name):
        n = len(df_slice)
        if n == 0: return
        
        for level in [2, 4, 6, 8]:
            hits_at_5 = 0
            dist_tops = 0
            top_1s = 0
            freq_hits = 0
            paired_diffs = []
            
            for _, row in df_slice.iterrows():
                true_code = clean_code(row.get('majority_ahtn8', ''), level)
                if not true_code:
                    continue
                    
                # Engine retrieved codes
                retrieved = row.get('retrieved_codes', [])
                if retrieved is None: retrieved = []
                ret_levels = [clean_code(c, level) for c in retrieved[:5] if pd.notna(c)]
                
                # Baseline codes (combine from routed chapters)
                chaps = row.get('routed_chapters', [])
                base_codes = []
                for ch in chaps:
                    base_codes.extend(baselines[level].get(ch, []))
                base_codes = base_codes[:5]
                
                # Math checks
                r_hit = 1 if true_code in ret_levels else 0
                f_hit = 1 if true_code in base_codes else 0
                
                hits_at_5 += r_hit
                freq_hits += f_hit
                paired_diffs.append(r_hit - f_hit)
                
                if ret_levels and true_code == ret_levels[0]: top_1s += 1
                
                if ret_levels:
                    mode_val = pd.Series(ret_levels).mode()
                    if not mode_val.empty and true_code == mode_val[0]:
                        dist_tops += 1
            
            # Compute Wilson CI for proportions
            for metric, count in [('Hit@5', hits_at_5), ('Distribution-Top', dist_tops), 
                                  ('Top-1', top_1s), ('Freq_Baseline', freq_hits)]:
                low, high = wilson_ci(count, n)
                results.append({
                    'level': level, 'metric': metric, 'band': band_name,
                    'n': n, 'value': count/n if n>0 else 0, 'ci_low': low, 'ci_high': high
                })
                
            # Compute paired difference CI (Standard Error of Mean)
            if n > 0:
                diff_mean = np.mean(paired_diffs)
                diff_se = np.std(paired_diffs, ddof=1) / np.sqrt(n) if n > 1 else 0
                results.append({
                    'level': level, 'metric': 'Paired_Diff(Retrieval-Freq)', 'band': band_name,
                    'n': n, 'value': diff_mean, 'ci_low': diff_mean - 1.96 * diff_se, 'ci_high': diff_mean + 1.96 * diff_se
                })
                
    # Evaluate segments
    evaluate_slice(df, 'All')
    
    # 4. Similarity Bands & Near-Twins
    print("-> Slicing by similarity bands and near-twins...")
    bins = [-np.inf, 0.3, 0.5, 0.7, 0.9, np.inf]
    labels = ['<0.3', '0.3-0.5', '0.5-0.7', '0.7-0.9', '>=0.9']
    df['sim_band'] = pd.cut(df['max_similarity'], bins=bins, labels=labels, right=False)
    
    for label in labels:
        evaluate_slice(df[df['sim_band'] == label], label)
        
    near_twins = df[df['max_similarity'] >= 0.95]
    not_twins = df[df['max_similarity'] < 0.95]
    evaluate_slice(near_twins, 'Near-Twin (>=0.95)')
    evaluate_slice(not_twins, 'Not-Twin (<0.95)')
    
    twin_share = len(near_twins) / len(df)
    print(f"   [INFO] Near-twins make up {twin_share:.2%} of the test set.")
    
    out_df = pd.DataFrame(results)
    Path("reports/tables").mkdir(parents=True, exist_ok=True)
    out_df.to_csv('reports/tables/track_e/e4_hit_rate.csv', index=False)
    
    # 5. Verified Set Evaluation
    print("-> Grading against 66 manual Verified items...")
    ver_ids = sample_key[['group_l1', 'sample_id']].merge(verified_set, on='sample_id', how='inner')
    ver_df = df.merge(ver_ids, on='group_l1', how='inner')
    
    ver_results = []
    for level in [2, 4, 6, 8]:
        label_col = f'verified_label_{level}'
        hits, dist_tops, n = 0, 0, len(ver_df)
        
        for _, row in ver_df.iterrows():
            true_code = clean_code(row.get(label_col, ''), level)
            if not true_code: continue
            
            retrieved = row.get('retrieved_codes', [])
            if retrieved is None: retrieved = []
            ret_levels = [clean_code(c, level) for c in retrieved[:5] if pd.notna(c)]
            
            if true_code in ret_levels: hits += 1
            if ret_levels:
                mode_val = pd.Series(ret_levels).mode()
                if not mode_val.empty and true_code == mode_val[0]: dist_tops += 1
                
        h_low, h_high = wilson_ci(hits, n)
        d_low, d_high = wilson_ci(dist_tops, n)
        ver_results.extend([
            {'level': level, 'metric': 'Hit@5_Verified', 'band': 'Verified', 'n': n, 'value': hits/n if n>0 else 0, 'ci_low': h_low, 'ci_high': h_high},
            {'level': level, 'metric': 'DistTop_Verified', 'band': 'Verified', 'n': n, 'value': dist_tops/n if n>0 else 0, 'ci_low': d_low, 'ci_high': d_high}
        ])
    
    pd.DataFrame(ver_results).to_csv('reports/tables/track_e/e4_verified.csv', index=False)
    
    # 6. Plotting
    print("-> Generating Figures...")
    Path("reports/figures").mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid")
    
    # Fig 1: Hit rate by level (Retrieval vs Baseline)
    plt.figure(figsize=(8, 6))
    overall = out_df[out_df['band'] == 'All']
    hit5 = overall[overall['metric'] == 'Hit@5']
    freq = overall[overall['metric'] == 'Freq_Baseline']
    
    plt.errorbar(hit5['level'], hit5['value'], yerr=[hit5['value'] - hit5['ci_low'], hit5['ci_high'] - hit5['value']], 
                 fmt='-o', label='Retrieval Engine', capsize=5, linewidth=2)
    plt.errorbar(freq['level'], freq['value'], yerr=[freq['value'] - freq['ci_low'], freq['ci_high'] - freq['value']], 
                 fmt='--s', label='Blind Guess (Most Common Codes)', capsize=5, color='gray')
    
    plt.title('Retrieval Engine Accuracy vs. Popularity Guessing Baseline')
    plt.xlabel('AHTN Level (Digits)')
    plt.ylabel('Accuracy (Top 5 Suggestions)')
    plt.xticks([2, 4, 6, 8])
    plt.ylim(0, 1.0)
    plt.legend()
    plt.savefig('reports/figures/e4_hit_by_level.png', bbox_inches='tight', dpi=300)
    plt.close()
    
    # Fig 2: Hit rate by Band (Levels 6 and 8)
    plt.figure(figsize=(8, 6))
    bands_list = ['<0.3', '0.3-0.5', '0.5-0.7', '0.7-0.9', '>=0.9']
    band_df = out_df[(out_df['band'].isin(bands_list)) & (out_df['metric'] == 'Hit@5')]
    
    # Sort bands logically instead of alphabetically
    band_df['band'] = pd.Categorical(band_df['band'], categories=bands_list, ordered=True)
    band_df = band_df.sort_values('band')
    
    l6_bands = band_df[band_df['level'] == 6]
    l8_bands = band_df[band_df['level'] == 8]
    
    plt.plot(l6_bands['band'], l6_bands['value'], marker='o', label='6-Digit (Subheading)', linewidth=2)
    plt.plot(l8_bands['band'], l8_bands['value'], marker='s', label='8-Digit (AHTN)', linewidth=2)
    plt.title('Retrieval Engine Accuracy Based on Confidence Score')
    plt.xlabel('Engine Confidence Match Score')
    plt.ylabel('Accuracy (Top 5 Suggestions)')
    plt.ylim(0, 1.0)
    plt.legend()
    plt.savefig('reports/figures/e4_hit_by_band.png', bbox_inches='tight', dpi=300)
    plt.close()

    print(" E4 Complete! All tables and figures generated in reports/tables/track_e/ and reports/figures/")

if __name__ == "__main__":
    main()