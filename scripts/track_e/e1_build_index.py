import os
import sys
import json
import hashlib
import duckdb
import numpy as np
import pandas as pd
import scipy.sparse as sp

# Add the src folder to Python's path so we can import your FeatureExtractor
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.hsclf.models.features import FeatureExtractor

def compute_sha256(filepath):
    """Computes a secure hash to prove files haven't been tampered with."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def main():
    print("--- Track E: Building Retrieval Index ---")
    
    os.makedirs('data/processed/retrieval', exist_ok=True)
    os.makedirs('reports/tables', exist_ok=True)
    
    print("1/5 Loading Feature Extractor and IDF weights...")
    extractor = FeatureExtractor()
    idf_weights = np.load('data/processed/idf_main.npy')
    extractor.set_idf(idf_weights)
    
    print("2/5 Running safe database queries to filter N=200 pool...")
    conn = duckdb.connect(':memory:')
    
    # Load Track F valid codes
    conn.execute("""
        CREATE TEMP TABLE valid_codes AS 
        SELECT code8 FROM read_parquet('data/reference/ahtn_2022_scope_reference.parquet')
    """)
    
    # Get just the N=200 capped pool IDs AND their chapters directly from train_pairs!
    conn.execute("""
        CREATE TEMP TABLE pool_ids AS 
        SELECT DISTINCT group_l1, ch2 as chapter 
        FROM read_parquet('data/processed/train_pairs_main.parquet')
    """)
    
    # Join with the text using the exact correct column names
    conn.execute("""
        CREATE TEMP TABLE pool_text AS
        SELECT 
            p.group_l1, 
            p.chapter, 
            n.desc_norm
        FROM pool_ids p
        JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON p.group_l1 = n.desc_norm_id
    """)
    
    conn.execute("""
        CREATE TEMP TABLE window_counts AS
        SELECT 
            d.group_l1, 
            d.ahtn8, 
            SUM(d.tx_count) as window_tx
        FROM read_parquet('data/processed/desc_code_counts.parquet') d
        JOIN pool_ids p ON d.group_l1 = p.group_l1
        WHERE d.year IN (2023, 2024)
        GROUP BY d.group_l1, d.ahtn8
    """)
    
    print("3/5 Saving historical declaration distributions...")
    conn.execute("""
        COPY (
            SELECT 
                w.group_l1, 
                w.ahtn8 as code, 
                w.window_tx as declaration_count, 
                CASE WHEN v.code8 IS NOT NULL THEN true ELSE false END as is_valid
            FROM window_counts w
            LEFT JOIN valid_codes v ON w.ahtn8 = v.code8
        ) TO 'data/processed/retrieval/retrieval_codes.parquet' (FORMAT PARQUET)
    """)
    
    chapters = ['39', '73', '84', '85', '87']
    all_meta_dfs = []
    summary_stats = []
    
    print("4/5 Calculating Sparse Math Matrices by Chapter...")
    for ch in chapters:
        print(f"   -> Processing Chapter {ch}...")
        
        query = f"""
            SELECT 
                pt.group_l1, 
                pt.desc_norm, 
                pt.chapter, 
                COALESCE(sum_tx.total_tx, 0) as window_transactions
            FROM pool_text pt
            LEFT JOIN (
                SELECT group_l1, sum(window_tx) as total_tx 
                FROM window_counts GROUP BY group_l1
            ) sum_tx ON pt.group_l1 = sum_tx.group_l1
            WHERE pt.chapter = '{ch}'
            ORDER BY pt.group_l1
        """
        df_ch = conn.execute(query).df()
        
        if len(df_ch) == 0:
            print(f"      No descriptions found for Chapter {ch}")
            continue
            
        raw_texts = df_ch['desc_norm'].tolist()
        sparse_matrix = extractor.transform(raw_texts)
        
        matrix_path = f'data/processed/retrieval/index_ch{ch}.npz'
        sp.save_npz(matrix_path, sparse_matrix)
        
        df_ch['row_index'] = range(len(df_ch))
        df_ch['desc_norm_id'] = df_ch['group_l1']
        
        df_ch = df_ch.drop(columns=['desc_norm'])
        all_meta_dfs.append(df_ch)
        
        mb_size = os.path.getsize(matrix_path) / (1024 * 1024)
        summary_stats.append({
            'chapter': ch,
            'rows': sparse_matrix.shape[0],
            'non_zero_entries': sparse_matrix.nnz,
            'size_mb': round(mb_size, 2)
        })
    
    print("5/5 Saving Meta table and Security Manifest...")
    meta_full = pd.concat(all_meta_dfs, ignore_index=True)
    meta_full.to_parquet('data/processed/retrieval/index_meta.parquet')
    
    summary_df = pd.DataFrame(summary_stats)
    summary_df.to_csv('reports/tables/track_e/e1_index_summary.csv', index=False)
    
    manifest = {
        "pool_count": len(meta_full),
        "idf_checksum": compute_sha256('data/processed/idf_main.npy'),
        "files": {
            "index_meta.parquet": compute_sha256('data/processed/retrieval/index_meta.parquet'),
            "retrieval_codes.parquet": compute_sha256('data/processed/retrieval/retrieval_codes.parquet')
        }
    }
    
    for stat in summary_stats:
        ch = stat['chapter']
        manifest["files"][f"index_ch{ch}.npz"] = compute_sha256(f'data/processed/retrieval/index_ch{ch}.npz')
        
    with open('data/processed/retrieval/manifest.json', 'w') as f:
        json.dump(manifest, f, indent=4)
        
    print(f"\n Index successfully built for {len(meta_full):,} items!")

if __name__ == "__main__":
    main()