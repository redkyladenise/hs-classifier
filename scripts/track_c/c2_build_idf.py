import duckdb
import numpy as np
import scipy.sparse as sp
import yaml
from pathlib import Path
import hashlib

# Import the feature extractor we just made
import sys
sys.path.append('.') # Ensure Python can find the src folder
from src.hsclf.models.features import FeatureExtractor

def build_idf():
    # Load our config
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
        
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{params['memory_ceiling_gb']}GB'")
    con.execute("PRAGMA threads=1")
    
    # We will build weights for both main and y1 scenarios
    scenarios = {
        'main': 'rank_main',
        'y1': 'rank_y1'
    }
    
    # Calculate the total number of features (buckets) we created in C2.1
    # 2^16 (words) + 2^17 (chars) = 65,536 + 131,072 = 196,608
    n_features = (2 ** params['hash_bits_word']) + (2 ** params['hash_bits_char'])
    
    for scenario, rank_col in scenarios.items():
        print(f"Calculating IDF weights for {scenario}...")
        
        # FIXED: Pointing to data/interim/norm_descriptions.parquet
        query = f"""
            SELECT n.desc_norm 
            FROM read_parquet('data/processed/training_pool.parquet') p
            JOIN read_parquet('data/interim/norm_descriptions.parquet') n
              ON p.group_l1 = n.desc_norm_id
            WHERE p.{rank_col} <= {params['training_cap_per_code']}
              AND p.{rank_col} IS NOT NULL
        """
        
        # To save memory, we pull the text in batches
        batch_size = params['batch_size']
        db_result = con.execute(query)
        
        # This will hold the count of how many descriptions contain each bucket
        doc_frequencies = np.zeros(n_features, dtype=np.float64)
        total_docs = 0
        
        # Initialize our extractor (without IDF weights yet)
        extractor = FeatureExtractor(
            hash_bits_word=params['hash_bits_word'], 
            hash_bits_char=params['hash_bits_char']
        )
        
        while True:
            batch = db_result.fetchmany(batch_size)
            if not batch:
                break # We ran out of data
                
            # Extract just the text strings from the DuckDB output
            texts = [row[0] for row in batch]
            total_docs += len(texts)
            
            # 1. Transform text into our math buckets
            X_batch = extractor.transform(texts)
            
            # 2. Convert to binary (1 if the word is present, 0 if not)
            X_binary = X_batch.copy()
            X_binary.data = np.ones_like(X_binary.data)
            
            # 3. Add to our running tally
            doc_frequencies += np.array(X_binary.sum(axis=0)).flatten()
            
            print(f"Processed {total_docs} descriptions...")

        # 4. The official IDF math formula (Smooth IDF): ln((1 + N) / (1 + df)) + 1
        print("Applying math formula to finalize weights...")
        idf = np.log((1.0 + total_docs) / (1.0 + doc_frequencies)) + 1.0
        
        # 5. Save the array to disk so our model can load it instantly later
        out_path = Path(f"data/processed/idf_{scenario}.npy")
        np.save(out_path, idf)
        
        # 6. Create a quick SHA-256 checksum
        checksum = hashlib.sha256(idf.tobytes()).hexdigest()
        print(f"Done! Saved to {out_path} (Checksum: {checksum[:8]}...)")

if __name__ == "__main__":
    build_idf()