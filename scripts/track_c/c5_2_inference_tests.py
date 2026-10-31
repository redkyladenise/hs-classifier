import duckdb
import yaml
import numpy as np
from sklearn.linear_model import SGDClassifier
import json
from pathlib import Path
import pickle
import sys
from collections import OrderedDict

sys.path.append('.') 
from src.hsclf.models.features import FeatureExtractor
from src.hsclf.models.hierarchy import HSHierarchy

class LRUCache:
    def __init__(self, capacity=100):
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key):
        if key not in self.cache: return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

class HSInferenceEngine:
    def __init__(self, scenario='main', cache_size=100):
        self.scenario = scenario
        self.v1_dir = Path(f"models/v1/{scenario}")
        self.cache = LRUCache(capacity=cache_size)
        self.hierarchy = HSHierarchy(scenario=scenario)
        self.skipped_1_child_count = 0
        
        with open(self.v1_dir / "manifest.json", "r") as f:
            self.manifest = json.load(f)

    def _load_node(self, node_id):
        node_id = "root" if node_id == "" else node_id
        cached = self.cache.get(node_id)
        if cached: return cached
        
        file_path = self.v1_dir / f"{node_id}.pkl"
        if not file_path.exists(): return None
        
        with open(file_path, 'rb') as f:
            bundle = pickle.load(f)
        
        self.cache.put(node_id, bundle)
        return bundle

    def predict_beam_batch(self, X_batch, top_k=5):
        n_samples = X_batch.shape[0]
        beams = [[{'code': '', 'prob': 1.0}] for _ in range(n_samples)]
        
        for lvl in [0, 2, 4, 6]:
            node_to_items = {}
            for item_idx, item_beams in enumerate(beams):
                for b in item_beams:
                    code = b['code']
                    if code not in node_to_items:
                        node_to_items[code] = []
                    node_to_items[code].append((item_idx, b))
                    
            new_beams = [[] for _ in range(n_samples)]
            
            for node_code, items in node_to_items.items():
                if lvl > 0 and node_code == '': continue
                
                children = self.hierarchy.get_children(node_code, lvl)
                
                if len(children) == 1:
                    self.skipped_1_child_count += 1
                    for i, b in items:
                        new_beams[i].append({'code': children[0], 'prob': b['prob']})
                    continue
                if len(children) == 0:
                    for i, b in items: new_beams[i].append(b)
                    continue

                bundle = self._load_node(node_code)
                if not bundle:
                    for i, b in items: new_beams[i].append({'code': children[0], 'prob': b['prob']})
                    continue

                unique_indices = list(set([idx for idx, _ in items]))
                idx_map = {orig_idx: mat_idx for mat_idx, orig_idx in enumerate(unique_indices)}
                
                X_node = X_batch[unique_indices][:, bundle['active_indices']]
                probs = bundle['model'].predict_proba(X_node)
                classes = bundle['model'].classes_

                for i, b in items:
                    mat_idx = idx_map[i]
                    item_probs = probs[mat_idx]
                    for cls_idx, cls_code in enumerate(classes):
                        new_prob = b['prob'] * item_probs[cls_idx]
                        new_beams[i].append({'code': cls_code, 'prob': new_prob})

            for i in range(n_samples):
                sorted_b = sorted(new_beams[i], key=lambda x: x['prob'], reverse=True)
                beams[i] = sorted_b[:top_k]
                
        return beams

def run_c5_tests():
    print("--- Running C5 Unit Tests ---")
    
    with open("config/params.yaml", "r") as f:
        params = yaml.safe_load(f)
    con = duckdb.connect()
    con.execute("PRAGMA threads=1")
    
    # Load C grid to calculate exact alpha
    with open("config/best_c_grid.json", "r") as f:
        best_c_grid = {int(k): v for k, v in json.load(f).items()}
        
    engine = HSInferenceEngine(scenario='main')
    extractor = FeatureExtractor(params['hash_bits_word'], params['hash_bits_char'])
    extractor.set_idf(np.load("data/processed/idf_main.npy"))

    print("\n[Test 1] 20 Examples Per Chapter (Batch Execution)")
    query_20 = """
        WITH true_labels AS (
            SELECT group_l1, SUBSTRING(ahtn8, 1, 2) as ch2,
                   ROW_NUMBER() OVER (PARTITION BY group_l1 ORDER BY tx_count DESC) as rn_group
            FROM read_parquet('data/processed/desc_code_counts.parquet')
        ),
        val_data AS (
            SELECT v.group_l1, n.desc_norm, t.ch2
            FROM read_parquet('data/processed/val_tune_main.parquet') v
            JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON v.group_l1 = n.desc_norm_id
            JOIN true_labels t ON v.group_l1 = t.group_l1
            WHERE t.rn_group = 1
        ),
        ranked AS (
            SELECT desc_norm, ch2, ROW_NUMBER() OVER (PARTITION BY ch2 ORDER BY group_l1) as rn
            FROM val_data
        )
        SELECT desc_norm FROM ranked WHERE rn <= 20
    """
    sample_texts = con.execute(query_20).df()['desc_norm'].tolist()
    X_sample = extractor.transform(sample_texts)
    
    beams = engine.predict_beam_batch(X_sample, top_k=5)
    print(f"Successfully processed {len(sample_texts)} descriptions through Beam Search.")
    
    print("\n[Test 2] Disk vs Memory Equality")
    bundle_disk = engine._load_node("root")
    engine.cache.cache.clear()
    bundle_mem = engine._load_node("root")
    
    p1 = bundle_disk['model'].predict_proba(X_sample[0:1][:, bundle_disk['active_indices']])
    p2 = bundle_mem['model'].predict_proba(X_sample[0:1][:, bundle_mem['active_indices']])
    assert np.allclose(p1, p2), "Disk and Memory predictions diverged!"
    print("Disk model predictions exactly match Memory model predictions.")
    
    print("\n[Test 3] Beam Probabilities <= 1.0")
    max_prob = max([b['prob'] for item in beams for b in item])
    assert max_prob <= 1.000001, f"Found probability > 1.0! ({max_prob})"
    print(f"Maximum combined probability is {max_prob:.4f} (<= 1.0).")

    print("\n[Test 4] Skipped 1-Child Nodes")
    assert engine.skipped_1_child_count > 0, "No 1-child nodes were skipped. Hierarchy mapping failed."
    print(f"Bypassed single-child nodes {engine.skipped_1_child_count} times to save inference time.")
    
    print("\n[Test 5] Retraining Identity (Same Seed = Same Output)")
    small_nodes = [n for n in engine.manifest['nodes'] if 10 < n['training_rows'] < 100][:3]
    
    for small_node in small_nodes:
        node_id = small_node['id']
        lvl = small_node['level']
        
        if lvl == 2: tgt, flt = 'hd4', 'ch2'
        elif lvl == 4: tgt, flt = 'sh6', 'hd4'
        elif lvl == 6: tgt, flt = 'ahtn8', 'sh6'
        
        query_train = f"""
            SELECT n.desc_norm, t.{tgt}
            FROM read_parquet('data/processed/train_pairs_main.parquet') t
            JOIN read_parquet('data/interim/norm_descriptions.parquet') n ON t.group_l1 = n.desc_norm_id
            JOIN read_parquet('data/processed/training_pool.parquet') p ON t.group_l1 = p.group_l1
            WHERE t.elig_{tgt} = true AND p.rank_main <= 200 AND t.{flt} = '{node_id}'
        """
        retrain_data = con.execute(query_train).fetchall()
        X_rt = extractor.transform([r[0] for r in retrain_data])
        y_rt = [r[1] for r in retrain_data]
        
        # FIX: Calculate EXACT alpha just like training did, overriding the rounded manifest
        c_val = best_c_grid.get(lvl, 1.0)
        exact_alpha = 1.0 / (c_val * len(y_rt))
        
        model_rt = SGDClassifier(loss='log_loss', alpha=exact_alpha, random_state=42)
        model_rt.fit(X_rt, y_rt)
        
        active_cols = np.array((X_rt != 0).sum(axis=0)).flatten() > 0
        active_indices = np.where(active_cols)[0]
        rt_coef = model_rt.coef_[:, active_indices].astype(np.float32)
        
        orig_bundle = engine._load_node(node_id)
        orig_model = orig_bundle['model']
        orig_coef = orig_model.coef_
        
        # Test 1: Check if Predictions are identical (Peer requirement)
        X_rt_sliced = X_rt[:, orig_bundle['active_indices']]
        rt_preds = model_rt.predict(X_rt)
        orig_preds = orig_model.predict(X_rt_sliced)
        assert np.array_equal(rt_preds, orig_preds), f"Predictions diverged for {node_id}!"
        
        # Test 2: Check Coefficients match
        assert np.array_equal(active_indices, orig_bundle['active_indices']), f"Active columns diverged for {node_id}!"
        assert np.allclose(rt_coef, orig_coef), f"Coefficients diverged for {node_id}!"
        
        print(f" Retraining node '{node_id}' produced identical predictions and coefficients.")

    print("\n ALL C5 UNIT TESTS PASSED!")

if __name__ == "__main__":
    run_c5_tests()