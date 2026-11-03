import sys
import os
import time
from pathlib import Path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pandas as pd
import numpy as np
import duckdb
import yaml

from src.hsclf.retrieval.search import RetrievalEngine
from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

def score_validation_set():
    print("\n--- Mini-step 1a: Scoring Validation Set ---")
    out_dir = Path("data/processed/predictions_val")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    con.execute("PRAGMA threads=1")
    
    # 1. Load Engine and Extractor
    print(" -> Loading C5 Engine (scenario: main)...")
    engine = HSInferenceEngine(scenario='main')
    extractor = FeatureExtractor(params['hash_bits_word'], params['hash_bits_char'])
    extractor.set_idf(np.load("data/processed/idf_main.npy"))
    
    # 2. Fetch Data
    print(" -> Fetching validation descriptions...")
    query = """
        SELECT t.group_l1, n.desc_norm
        FROM read_parquet('data/processed/val_cal_main.parquet') t
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n 
          ON t.group_l1 = n.desc_norm_id
        ORDER BY t.group_l1
    """
    df_val = con.execute(query).df()
    total_items = len(df_val)
    print(f" -> Found {total_items} items to score.")
    
    # 3. Process in Chunks
    batch_size = 5000
    chunks = [df_val[i:i + batch_size] for i in range(0, total_items, batch_size)]
    
    for i, chunk in enumerate(chunks):
        part_file = out_dir / f"part_{i:03d}.parquet"
        if part_file.exists():
            print(f" -> [Chunk {i+1}/{len(chunks)}] Already exists. Skipping.")
            continue
            
        print(f" -> [Chunk {i+1}/{len(chunks)}] Processing {len(chunk)} descriptions...")
        start_time = time.time()
        
        texts = chunk['desc_norm'].tolist()
        X_batch = extractor.transform(texts)
        beams = engine.predict_beam_batch(X_batch, top_k=5)
        
        records = []
        for idx, item_beams in zip(chunk['group_l1'], beams):
            row = {'group_l1': idx}
            for rank, b in enumerate(item_beams, start=1):
                row[f'pred_{rank}'] = b['code']
                row[f'prob_{rank}'] = b['prob']
            for rank in range(len(item_beams) + 1, 6):
                row[f'pred_{rank}'] = None
                row[f'prob_{rank}'] = 0.0
            records.append(row)
            
        df_out = pd.DataFrame(records)
        df_out.to_parquet(part_file, index=False)
        elapsed = time.time() - start_time
        print(f"    Done in {elapsed:.1f}s.")
        
    print(" -> Validation Scoring Complete!")

def run_e3_search():
    print("\n--- E3: Validation Batch Search (Mini-step 1b) ---")
    
    val_cal = pd.read_parquet('data/processed/val_cal_main.parquet')
    preds = pd.read_parquet('data/processed/predictions_val')
    unique_desc = pd.read_parquet('data/processed/unique_descriptions.parquet')
    norm_desc = pd.read_parquet('data/interim/norm_descriptions.parquet')
    
    df = val_cal.merge(preds, on='group_l1', how='inner')
    df['pred_chapter'] = df['pred_1'].str[:2]
    
    if len(df) > 20000:
        df = df.groupby('pred_chapter', group_keys=False).apply(
            lambda x: x.sample(int(np.round(20000 * len(x) / len(df))), random_state=42)
        )
        
    df = df.merge(unique_desc[['desc_norm_id', 'majority_ahtn8']], left_on='group_l1', right_on='desc_norm_id', how='left')
    df = df.merge(norm_desc[['desc_norm_id', 'desc_norm']], left_on='group_l1', right_on='desc_norm_id', how='left')
    
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

    df['routed_chapters'] = df.apply(get_routed_chapters, axis=1)
    
    print(f"-> Starting Batch Search for {len(df)} queries...")
    engine = RetrievalEngine()
    engine.batch_search(
        df=df, 
        text_col='desc_norm', 
        chapter_col='routed_chapters', 
        out_dir='data/processed/retrieval_eval_e3', 
        chunk_size=2000
    )
    print(" E3 Search Complete! Results saved to data/processed/retrieval_eval_e3")

def main():
    score_validation_set()
    run_e3_search()

if __name__ == "__main__":
    main()