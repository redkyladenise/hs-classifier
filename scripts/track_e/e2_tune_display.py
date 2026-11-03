import os
import sys
import pandas as pd
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.hsclf.retrieval.search import RetrievalEngine
from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

def get_model_predictions(val_df, text_df, extractor):
    """Uses your custom Track C Engine to safely predict chapters in batches."""
    print("-> Bridging IDs to text...")
    val_text_df = val_df.merge(text_df, left_on='group_l1', right_on='desc_norm_id', how='left')
    raw_texts = val_text_df['desc_norm'].tolist()
    
    print("-> Calculating features for validation set...")
    val_vectors = extractor.transform(raw_texts)
    
    print("-> Loading HSInferenceEngine...")
    engine = HSInferenceEngine(scenario='main', cache_size=150)
    
    print("-> Predicting Chapters (Batching to save RAM)...")
    predictions = []
    batch_size = 5000
    
    for i in range(0, val_vectors.shape[0], batch_size):
        batch_vectors = val_vectors[i : i + batch_size]
        
        # Get the top 5 paths for this batch
        beam_results = engine.predict_beam_batch(batch_vectors, top_k=5)
        
        for item_beams in beam_results:
            seen_chs = set()
            top_chs = []
            # The engine returns 8-digit codes. The first 2 digits are the Chapter!
            for b in item_beams:
                ch = b['code'][:2]
                if ch not in seen_chs:
                    seen_chs.add(ch)
                    top_chs.append(ch)
            
            # Ensure we always have 3 chapters to test scoping (pad with the best if needed)
            while len(top_chs) < 3:
                top_chs.append(top_chs[0] if top_chs else '85')
                
            predictions.append(top_chs[:3])
            
    val_text_df['predicted_chapters'] = predictions
    return val_text_df

def run_evaluation_queries(val_data, engine):
    print(f"-> Running queries for {len(val_data)} items (this may take a few minutes)...")
    results_list = []
    
    for idx, row in val_data.iterrows():
        if idx > 0 and idx % 1000 == 0:
            print(f"   ...processed {idx} / {len(val_data)}")
            
        search_results = engine.query(
            raw_text=row['desc_norm'], 
            routed_chapters=row['predicted_chapters'][:3], 
            top_k=15
        )
        
        codes_s1, codes_s2, codes_s3 = [], [], []
        best_sim = 0.0
        
        if not search_results.empty:
            valid_res = search_results[search_results['is_valid'] == True]
            if not valid_res.empty:
                pred_chs = row['predicted_chapters']
                
                # Scope 1: Matches from just the #1 predicted chapter
                res_s1 = valid_res[valid_res['chapter'] == pred_chs[0]].nlargest(5, 'similarity')
                codes_s1 = res_s1['code'].tolist()
                
                # Scope 2: Matches from the #1 and #2 predicted chapters
                res_s2 = valid_res[valid_res['chapter'].isin(pred_chs[:2])].nlargest(5, 'similarity')
                codes_s2 = res_s2['code'].tolist()
                
                # Scope 3 (All): Matches across all 3 predicted chapters
                res_s3 = valid_res.nlargest(5, 'similarity')
                codes_s3 = res_s3['code'].tolist()
                
                best_sim = res_s3['similarity'].max() if not res_s3.empty else 0.0
        
        results_list.append({
            'group_l1': row['group_l1'],
            'best_similarity': best_sim,
            'codes_s1': codes_s1,
            'codes_s2': codes_s2,
            'codes_s3': codes_s3
        })
        
    return pd.DataFrame(results_list)

def _check_hit(true_code, retrieved_codes_list, level):
    if not true_code or not retrieved_codes_list:
        return False
    true_prefix = true_code[:level]
    for c in retrieved_codes_list:
        if c and c[:level] == true_prefix:
            return True
    return False

def evaluate_and_save_metrics(results_df):
    print("-> Evaluating metrics to find optimal rules...")
    
    unique_df = pd.read_parquet('data/processed/unique_descriptions.parquet')
    
    # ROOT CAUSE FIX: Handle the ID column mismatch between files
    id_col = 'desc_norm_id' if 'desc_norm_id' in unique_df.columns else 'group_l1'
    target_col = 'majority_ahtn8' if 'majority_ahtn8' in unique_df.columns else 'ahtn8'
    
    eval_df = results_df.merge(unique_df[[id_col, target_col]], left_on='group_l1', right_on=id_col, how='left')
    eval_df = eval_df.dropna(subset=[target_col]).copy()
    
    eval_df['hit_2'] = eval_df.apply(lambda r: _check_hit(r[target_col], r['codes_s3'], 2), axis=1)
    eval_df['hit_4'] = eval_df.apply(lambda r: _check_hit(r[target_col], r['codes_s3'], 4), axis=1)
    eval_df['hit_6'] = eval_df.apply(lambda r: _check_hit(r[target_col], r['codes_s3'], 6), axis=1)
    eval_df['hit_8'] = eval_df.apply(lambda r: _check_hit(r[target_col], r['codes_s3'], 8), axis=1)
    
    eval_df['hit_6_s1'] = eval_df.apply(lambda r: _check_hit(r[target_col], r['codes_s1'], 6), axis=1)
    eval_df['hit_6_s2'] = eval_df.apply(lambda r: _check_hit(r[target_col], r['codes_s2'], 6), axis=1)
    
    # --- RULE 1: Determine Display Level ---
    level_hits = []
    chosen_display_level = 2
    for lvl in [2, 4, 6, 8]:
        acc = eval_df[f'hit_{lvl}'].mean()
        level_hits.append({'level': lvl, 'hit_rate': acc})
        if acc >= 0.60:
            chosen_display_level = lvl
            
    pd.DataFrame(level_hits).to_csv('reports/tables/e2_level_hit.csv', index=False)
    
    # --- RULE 2: Determine Minimum Similarity ---
    bins = [0.0, 0.3, 0.5, 0.7, 0.9, 1.0]
    labels = ['<0.3', '0.3-0.5', '0.5-0.7', '0.7-0.9', '>=0.9']
    eval_df['sim_band'] = pd.cut(eval_df['best_similarity'], bins=bins, labels=labels, right=False)
    
    band_hits = eval_df.groupby('sim_band', observed=False)['hit_6'].mean().reset_index()
    band_hits.to_csv('reports/tables/e2_similarity_bands.csv', index=False)
    
    chosen_min_sim = 0.5
    for index, row in band_hits.iterrows():
        if row['hit_6'] >= 0.50:
            band_str = str(row['sim_band'])
            if band_str.startswith('>='):
                chosen_min_sim = 0.9
            elif band_str.startswith('<'):
                chosen_min_sim = 0.0
            else:
                chosen_min_sim = float(band_str.split('-')[0])
            break
            
    # --- RULE 3: Determine Chapter Scope ---
    hit_s1 = eval_df['hit_6_s1'].mean()
    hit_s2 = eval_df['hit_6_s2'].mean()
    hit_s3 = eval_df['hit_6'].mean()
    
    scope_data = [
        {'scope': 1, 'hit_rate_6': hit_s1},
        {'scope': 2, 'hit_rate_6': hit_s2},
        {'scope': 'all', 'hit_rate_6': hit_s3}
    ]
    pd.DataFrame(scope_data).to_csv('reports/tables/e2_scope_choice.csv', index=False)
    
    if (hit_s3 - hit_s1) <= 0.01:
        chosen_scope = 1
    elif (hit_s3 - hit_s2) <= 0.01:
        chosen_scope = 2
    else:
        chosen_scope = 3
        
    print("\n Tuning Complete! Here are your mathematically proven display rules:")
    print(f"   -> display_level: {chosen_display_level} digits")
    print(f"   -> min_similarity: {chosen_min_sim}")
    print(f"   -> retrieval_chapters: {chosen_scope}")
    print("\nPlease tell me these 3 numbers so we can update params.yaml!")

def main():
    print("--- Track E: Tuning Display Rules ---")
    
    extractor = FeatureExtractor()
    engine = RetrievalEngine(
        idf_path='data/processed/idf_main.npy',
        index_meta_path='data/processed/retrieval/index_meta.parquet',
        retrieval_codes_path='data/processed/retrieval/retrieval_codes.parquet',
        feature_extractor=extractor
    )
    
    print("-> Loading Validation Set...")
    val_df = pd.read_parquet('data/processed/val_cal_main.parquet')
    text_df = pd.read_parquet('data/interim/norm_descriptions.parquet')
    
    print("-> Sampling 10,000 items for hyper-parameter tuning...")
    val_df = val_df.sample(n=10000, random_state=42).reset_index(drop=True)
    
    val_data_with_preds = get_model_predictions(val_df, text_df, extractor)
    results_df = run_evaluation_queries(val_data_with_preds, engine)
    
    evaluate_and_save_metrics(results_df)

if __name__ == "__main__":
    main()