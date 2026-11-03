import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.hsclf.retrieval.search import RetrievalEngine

def main():
    print("--- E4: Test Sample Batch Search (Phase 1) ---")
    
    print("-> 1/5: Loading 183 unseen prediction files...")
    pred_dir = Path('data/processed/predictions_unseen')
    pred_files = list(pred_dir.glob('*.parquet'))
    
    if not pred_files:
        raise FileNotFoundError("Could not find parquet files in data/processed/predictions_unseen")
        
    preds = pd.concat([pd.read_parquet(f) for f in pred_files], ignore_index=True)
    
    print("-> 2/5: Loading dictionaries and audit key...")
    unique_desc = pd.read_parquet('data/processed/unique_descriptions.parquet')
    norm_desc = pd.read_parquet('data/interim/norm_descriptions.parquet')
    sample_key = pd.read_csv('data/audit/sample_key.csv')
    
    print("-> 3/5: Isolating 180 audit items and forming 50,000 batch...")
    main_audit = sample_key[sample_key['sample_type'] == 'main']
    audit_ids = main_audit['group_l1'].unique()
    
    audit_df = preds[preds['group_l1'].isin(audit_ids)].copy()
    rest_df = preds[~preds['group_l1'].isin(audit_ids)].copy()
    
    target_size = 50000
    n_needed = target_size - len(audit_df)
    
    if len(rest_df) > n_needed:
        rest_df = rest_df.sample(n=n_needed, random_state=42)
        
    df_eval = pd.concat([audit_df, rest_df]).reset_index(drop=True)
    
    print("-> 4/5: Attaching text, routing chapters, and SORTING to prevent memory thrashing...")
    df_eval = df_eval.merge(unique_desc[['desc_norm_id', 'majority_ahtn8']], left_on='group_l1', right_on='desc_norm_id', how='left')
    df_eval = df_eval.merge(norm_desc[['desc_norm_id', 'desc_norm']], left_on='group_l1', right_on='desc_norm_id', how='left')
    
    def get_routed_chapters(row):
        chaps = []
        for p in ['pred_1', 'pred_2', 'pred_3', 'pred_4', 'pred_5']:
            if pd.notna(row[p]):
                ch = str(row[p])[:2]
                if ch not in chaps:
                    chaps.append(ch)
                if len(chaps) == 2:
                    break
        return chaps

    df_eval['routed_chapters'] = df_eval.apply(get_routed_chapters, axis=1)
    
    df_eval['chapter_sort_key'] = df_eval['routed_chapters'].apply(lambda x: '-'.join(x))
    df_eval = df_eval.sort_values('chapter_sort_key').reset_index(drop=True)
    df_eval = df_eval.drop(columns=['chapter_sort_key'])
    
    out_dir = Path('data/processed/retrieval_eval_e4')
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n-> 5/5: Starting Batch Search on {len(df_eval)} queries...")
    print(f"   (Using chunk_size=1000. You should see 50 chunks. They will process much faster.)")
    engine = RetrievalEngine()
    engine.batch_search(
        df=df_eval, 
        text_col='desc_norm', 
        chapter_col='routed_chapters', 
        out_dir=str(out_dir), 
        chunk_size=1000
    )
    print("\n E4 Search Complete! Results saved to data/processed/retrieval_eval_e4")

if __name__ == "__main__":
    main()