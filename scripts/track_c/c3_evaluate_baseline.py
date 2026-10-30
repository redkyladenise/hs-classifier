import duckdb
import yaml
import numpy as np
import pickle
from pathlib import Path

import sys
sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor

def evaluate_flat_baseline(scenario='main'):
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{params['memory_ceiling_gb']}GB'")
    
    print("1. Loading the trained Flat Baseline model...")
    model_path = f"models/track_c/baselines/{scenario}/flat_logistic.pkl"
    with open(model_path, 'rb') as f:
        baseline_model = pickle.load(f)
        
    extractor = FeatureExtractor(
        hash_bits_word=params['hash_bits_word'],
        hash_bits_char=params['hash_bits_char']
    )
    extractor.set_idf(np.load(f"data/processed/idf_{scenario}.npy"))
    
    print("2. Fetching the Validation 'Practice Test'...")
    # We join our validation IDs with the text, and find the true #1 most common code for that item
    query = f"""
        WITH true_labels AS (
            SELECT group_l1, ahtn8,
                   ROW_NUMBER() OVER (PARTITION BY group_l1 ORDER BY tx_count DESC) as rn
            FROM read_parquet('data/processed/desc_code_counts.parquet')
        )
        SELECT n.desc_norm, t.ahtn8
        FROM read_parquet('data/processed/val_tune_{scenario}.parquet') v
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n
          ON v.group_l1 = n.desc_norm_id
        JOIN true_labels t
          ON v.group_l1 = t.group_l1
        WHERE t.rn = 1
    """
    
    batch_size = 10000
    db_result = con.execute(query)
    
    correct_guesses = 0
    total_questions = 0
    
    print("3. Grading the model...")
    while True:
        batch = db_result.fetchmany(batch_size)
        if not batch:
            break
            
        texts = [row[0] for row in batch]
        true_codes = [row[1] for row in batch]
        
        # Turn text into math
        X_batch = extractor.transform(texts)
        
        # Ask the model to guess
        predictions = baseline_model.predict(X_batch)
        
        # Check how many it got right
        for guess, truth in zip(predictions, true_codes):
            if guess == truth:
                correct_guesses += 1
        total_questions += len(texts)
        
    accuracy = (correct_guesses / total_questions) * 100 if total_questions > 0 else 0
    
    print("\n" + "="*30)
    print("=== FLAT BASELINE RESULTS === ")
    print("="*30)
    print(f"Total Items Tested : {total_questions:,}")
    print(f"Correct Guesses    : {correct_guesses:,}")
    print(f"Accuracy Score     : {accuracy:.2f}%")
    print("="*30)

if __name__ == "__main__":
    evaluate_flat_baseline('main')