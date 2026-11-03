import numpy as np
import scipy.sparse as sp
import pandas as pd
from src.hsclf.data.normalize import normalize_light

class RetrievalEngine:
    def __init__(self, idf_path, index_meta_path, retrieval_codes_path, feature_extractor):
        self.extractor = feature_extractor
        
        if self.extractor.idf_weights is None:
            self.extractor.set_idf(np.load(idf_path))
            
        self.meta_df = pd.read_parquet(index_meta_path)
        
        # ROOT CAUSE FIX 1: Set the index so merges become instant hash-lookups
        self.codes_df = pd.read_parquet(retrieval_codes_path).set_index('group_l1')
        
        self.matrix_cache = {}
        self.meta_cache = {ch: df.copy() for ch, df in self.meta_df.groupby('chapter')}

    def _load_matrix(self, chapter):
        if chapter not in self.matrix_cache:
            path = f'data/processed/retrieval/index_ch{chapter}.npz'
            self.matrix_cache[chapter] = sp.load_npz(path)
        return self.matrix_cache[chapter]

    def query(self, raw_text, routed_chapters, top_k=5, min_tx=0):
        norm_result = normalize_light(raw_text)
        normalized_text = norm_result['desc_norm']
        query_vector = self.extractor.transform([normalized_text])
        
        all_top_indices, all_top_sims, all_top_chapters = [], [], []
        
        for ch in routed_chapters:
            try:
                ch_matrix = self._load_matrix(ch)
            except FileNotFoundError:
                continue 
            
            similarities = ch_matrix.dot(query_vector.T).toarray().flatten()
            
            k = min(top_k, len(similarities))
            if k == 0:
                continue
                
            # ROOT CAUSE FIX 2: Pure NumPy extraction (blazing fast, bypasses Pandas sorting)
            idx = np.argpartition(similarities, -k)[-k:]
            idx = idx[np.argsort(similarities[idx])[::-1]] # sort just the top K
            
            ch_meta = self.meta_cache.get(ch)
            if ch_meta is None or ch_meta.empty:
                continue
                
            # Extract only the exact rows we need directly from RAM
            group_l1s = ch_meta['group_l1'].values[idx]
            window_txs = ch_meta['window_transactions'].values[idx]
            sims = similarities[idx]
            
            if min_tx > 0:
                valid_mask = window_txs >= min_tx
                group_l1s = group_l1s[valid_mask]
                sims = sims[valid_mask]
                
            all_top_indices.extend(group_l1s)
            all_top_sims.extend(sims)
            all_top_chapters.extend([ch] * len(group_l1s))
            
        if not all_top_indices:
            return pd.DataFrame()

        combo_df = pd.DataFrame({
            'group_l1': all_top_indices,
            'similarity': all_top_sims,
            'chapter': all_top_chapters
        })
        top_matches = combo_df.nlargest(top_k, 'similarity')
        
        # Instant hash-lookup instead of a table scan
        final_results = top_matches.join(self.codes_df, on='group_l1')
        
        return final_results.reset_index(drop=True)

    def summarize_distribution(self, final_results_df):
        if final_results_df.empty:
            return {"distribution": pd.DataFrame(), "invalid_dropped": 0, "total_declarations": 0, "total_descriptions": 0}
            
        valid_codes = final_results_df[final_results_df['is_valid'] == True]
        invalid_dropped = len(final_results_df) - len(valid_codes)
        total_desc = final_results_df['group_l1'].nunique()
        
        if valid_codes.empty:
             return {"distribution": pd.DataFrame(), "invalid_dropped": invalid_dropped, "total_declarations": 0, "total_descriptions": total_desc}
            
        dist = valid_codes.groupby('code')['declaration_count'].sum().reset_index()
        dist = dist.sort_values('declaration_count', ascending=False)
        
        total_tx = dist['declaration_count'].sum()
        dist['share'] = dist['declaration_count'] / total_tx
        
        if len(dist) > 3:
            top_3 = dist.head(3).copy()
            other_tx = dist.iloc[3:]['declaration_count'].sum()
            other_share = other_tx / total_tx
            
            other_row = pd.DataFrame([{'code': 'Other', 'declaration_count': other_tx, 'share': other_share}])
            final_dist = pd.concat([top_3, other_row], ignore_index=True)
        else:
            final_dist = dist
            
        return {
            "distribution": final_dist, 
            "invalid_dropped": invalid_dropped, 
            "total_declarations": total_tx,
            "total_descriptions": total_desc
        }