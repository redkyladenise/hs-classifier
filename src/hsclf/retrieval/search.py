import os
import numpy as np
import scipy.sparse as sp
import pandas as pd
from pathlib import Path
from src.hsclf.data.normalize import normalize_light
from src.hsclf.models.features import FeatureExtractor
from src.hsclf.retrieval.mask import mask_description

class RetrievalEngine:
    def __init__(self, idf_path='data/processed/idf_main.npy', 
                 index_meta_path='data/processed/retrieval/index_meta.parquet', 
                 retrieval_codes_path='data/processed/retrieval/retrieval_codes.parquet'):
        
        self.extractor = FeatureExtractor()
        if os.path.exists(idf_path):
            self.extractor.set_idf(np.load(idf_path))
            
        # Load meta and slice by chapter for instant access
        self.meta_df = pd.read_parquet(index_meta_path)
        self.meta_cache = {ch: df.copy() for ch, df in self.meta_df.groupby('chapter')}
        
        # Hash-map optimization: Set group_l1 as index for instant code lookups
        self.codes_df = pd.read_parquet(retrieval_codes_path).set_index('group_l1')
        self.matrix_cache = {}
        
        # Load text dictionary for E7 examples
        self.texts_df = pd.read_parquet(
            'data/interim/norm_descriptions.parquet',
            columns=['desc_norm_id', 'desc_norm']
        ).set_index('desc_norm_id')

    def _load_matrix(self, chapter):
        if chapter not in self.matrix_cache:
            if len(self.matrix_cache) >= 2:
                oldest_chapter = next(iter(self.matrix_cache))
                del self.matrix_cache[oldest_chapter]
                
            path = f'data/processed/retrieval/index_ch{chapter}.npz'
            if os.path.exists(path):
                self.matrix_cache[chapter] = sp.load_npz(path).tocsr()
            else:
                self.matrix_cache[chapter] = None
                
        return self.matrix_cache[chapter]
    
    def query(self, raw_text, routed_chapters, top_k=5, min_similarity=0.5, split_share=0.60, show_examples=True):
        # 1. Normalize and Extract Math Features
        norm_result = normalize_light(raw_text)
        normalized_text = norm_result['desc_norm']
        query_vector = self.extractor.transform([normalized_text])
        
        all_top_indices, all_top_desc_ids, all_top_sims, all_top_chapters = [], [], [], []
        
        # 2. Search only the routed chapters (Fast NumPy Math)
        for ch in routed_chapters:
            ch_matrix = self._load_matrix(ch)
            if ch_matrix is None:
                continue 
            
            similarities = ch_matrix.dot(query_vector.T).toarray().flatten()
            k = min(top_k, len(similarities))
            if k == 0:
                continue
                
            idx = np.argpartition(similarities, -k)[-k:]
            idx = idx[np.argsort(similarities[idx])[::-1]]
            
            # FIX 1: Robust lookup (handles int 39, string '39', and string '039'/'01')
            ch_meta = self.meta_cache.get(ch)
            if ch_meta is None: ch_meta = self.meta_cache.get(str(ch))
            if ch_meta is None: ch_meta = self.meta_cache.get(str(ch).zfill(2))
                
            if ch_meta is None or ch_meta.empty:
                continue
                
            group_l1s = ch_meta['group_l1'].values[idx]
            desc_norm_ids = ch_meta['desc_norm_id'].values[idx] # Fetched for texts!
            sims = similarities[idx]
            
            all_top_indices.extend(group_l1s)
            all_top_desc_ids.extend(desc_norm_ids)
            all_top_sims.extend(sims)
            all_top_chapters.extend([ch] * len(group_l1s))
            
        if not all_top_indices:
            return self._empty_result()

        # 3. Combine and pick the absolute top_k across the searched chapters
        combo_df = pd.DataFrame({
            'group_l1': all_top_indices,
            'desc_norm_id': all_top_desc_ids, # Added to dataframe
            'similarity': all_top_sims,
            'chapter': all_top_chapters
        })
        top_matches = combo_df.nlargest(top_k, 'similarity')
        
        # 4. Instant hash-lookup to get the historical codes
        final_results = top_matches.join(self.codes_df, on='group_l1').reset_index(drop=True)
        
        # 5. Generate Masked Examples (E7)
        examples = []
        if show_examples and not final_results.empty:
            max_sim = final_results['similarity'].max()
            if max_sim >= min_similarity:
                final_with_text = final_results.copy()
                
                # FIX 2: Look up text using desc_norm_id instead of group_l1
                final_with_text['desc_norm'] = (
                    self.texts_df['desc_norm']
                    .reindex(final_with_text['desc_norm_id'].values)
                    .values
                )
                final_with_text = (
                    final_with_text
                    .dropna(subset=['desc_norm'])
                    .drop_duplicates(subset=['group_l1'])
                )

                # Process top 3 valid examples
                for _, row in final_with_text.iterrows():
                    if len(examples) >= 3:
                        break
                    if row['similarity'] < min_similarity:
                        continue
                        
                    raw_text = row['desc_norm']
                    masked = mask_description(raw_text)
                    if masked is None:
                        continue # Dropped due to over-masking
                        
                    examples.append({
                        "example_id": row['group_l1'],
                        "original_text": raw_text,
                        "text": masked,
                        "similarity": round(row['similarity'], 2),
                        "label": "very similar" if row['similarity'] >= 0.90 else "similar",
                        "codes": {row['code']: row['declaration_count']}
                    })

        # 6. Build Distribution and Flags based on File 6 rules
        result_dict = self._build_distribution(final_results, min_similarity, split_share)
        result_dict['examples'] = examples
        return result_dict

    def _build_distribution(self, df, min_sim, split_share):
        if df.empty:
            return self._empty_result()
            
        max_similarity = df['similarity'].max()
        no_close_match = bool(max_similarity < min_sim)
        
        valid_codes = df[df['is_valid'] == True]
        invalid_dropped = len(df) - len(valid_codes)
        total_desc = df['group_l1'].nunique()
        
        if valid_codes.empty:
             return {
                 "neighbors_df": df, "distribution": pd.DataFrame(), "invalid_dropped": invalid_dropped, 
                 "total_declarations": 0, "total_descriptions": total_desc,
                 "max_similarity": max_similarity, "no_close_match": no_close_match, "split_notice": False
             }
            
        dist = valid_codes.groupby('code')['declaration_count'].sum().reset_index()
        dist = dist.sort_values('declaration_count', ascending=False)
        
        total_tx = dist['declaration_count'].sum()
        dist['share'] = dist['declaration_count'] / total_tx
        
        split_notice = bool(dist.iloc[0]['share'] < split_share)

        # Top 3 + Other logic
        if len(dist) > 3:
            top_3 = dist.head(3).copy()
            other_tx = dist.iloc[3:]['declaration_count'].sum()
            other_share = other_tx / total_tx
            other_row = pd.DataFrame([{'code': 'Other', 'declaration_count': other_tx, 'share': other_share}])
            final_dist = pd.concat([top_3, other_row], ignore_index=True)
        else:
            final_dist = dist
            
        return {
            "neighbors_df": df,
            "distribution": final_dist, 
            "invalid_dropped": invalid_dropped, 
            "total_declarations": total_tx,
            "total_descriptions": total_desc,
            "max_similarity": max_similarity,
            "no_close_match": no_close_match,
            "split_notice": split_notice
        }

    def _empty_result(self):
        return {
            "neighbors_df": pd.DataFrame(), "distribution": pd.DataFrame(), "invalid_dropped": 0, 
            "total_declarations": 0, "total_descriptions": 0,
            "max_similarity": 0.0, "no_close_match": True, "split_notice": False, "examples": []
        }

    def batch_search(self, df, text_col='desc_norm', chapter_col='routed_chapters', 
                     out_dir='data/processed/retrieval_eval', chunk_size=2000,
                     min_similarity=0.5, split_share=0.60):
        """Processes a dataframe in chunks and saves to part_*.parquet to prevent data loss."""
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        
        num_chunks = (len(df) // chunk_size) + (1 if len(df) % chunk_size != 0 else 0)
        
        for i in range(num_chunks):
            part_path = f"{out_dir}/part_{i:04d}.parquet"
            if os.path.exists(part_path):
                print(f"Skipping chunk {i+1}/{num_chunks} (already exists)")
                continue
                
            print(f"Processing chunk {i+1}/{num_chunks}...")
            chunk = df.iloc[i*chunk_size : (i+1)*chunk_size].copy()
            
            results = []
            for _, row in chunk.iterrows():
                text = row[text_col]
                chaps = row[chapter_col]
                
                res = self.query(text, chaps, top_k=5, min_similarity=min_similarity, split_share=split_share)
                
                # Extract top 3 codes for hit@5 evaluation later
                dist = res['distribution']
                top_codes = dist['code'].tolist() if not dist.empty else []
                # Remove 'Other' from codes if present
                top_codes = [c for c in top_codes if c != 'Other']
                
                results.append({
                    'max_similarity': res['max_similarity'],
                    'no_close_match': res['no_close_match'],
                    'split_notice': res['split_notice'],
                    'retrieved_codes': top_codes
                })
                
            res_df = pd.DataFrame(results, index=chunk.index)
            final_chunk = pd.concat([chunk, res_df], axis=1)
            final_chunk.to_parquet(part_path)
            
        print("Batch processing complete.")