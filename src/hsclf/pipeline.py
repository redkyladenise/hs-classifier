import re
import yaml
import numpy as np
from pathlib import Path
import pandas as pd

# Import your C2 Extractor and C5 Engine
from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

# Import the Track E Retrieval Engine
from src.hsclf.retrieval.search import RetrievalEngine

class HSPipeline:
    def __init__(self, scenario='main', cache_size=150):
        self.scenario = scenario
        
        # 1. NEW: Load params.yaml configurations
        with open('params.yaml', 'r') as f:
            self.params = yaml.safe_load(f)
            
        self.bands = self.params.get('confidence_bands', {
            'level_8': {'high': 0.75, 'med': 0.50},
            'level_2': {'high': 0.90, 'med': 0.60}
        })
        self.t_oos = self.params.get('t_oos', 0.3788)
        self.show_examples = self.params.get('track_e', {}).get('show_examples', True)
        
        # 2. Load Track F valid codes
        self.valid_codes = self._load_valid_codes()
        
        # 3. Load the C5 Engine
        self.engine = HSInferenceEngine(scenario=self.scenario, cache_size=cache_size)
        
        # 4. Load the C2 Feature Extractor and set IDF weights
        self.extractor = FeatureExtractor()
        idf_path = f'data/processed/idf_{scenario}.npy'
        
        if Path(idf_path).exists():
            idf_array = np.load(idf_path)   
            self.extractor.set_idf(idf_array)
        else:
            self.extractor = None

        # 5. Initialize the Track E Engine
        self.retrieval_engine = RetrievalEngine()

    def _load_valid_codes(self):
        try:
            df = pd.read_parquet('data/processed/desc_code_counts.parquet')
            return set(df['ahtn8'].unique())
        except Exception:
            return set()

    def normalize_text(self, raw_text: str) -> str:
        if not isinstance(raw_text, str): return ""
        t = raw_text.lower()
        t = re.sub(r'[^a-z0-9\s]', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t
        
    def fast_length_check(self, norm_text: str) -> bool:
        return len(norm_text) < 3

    def predict(self, raw_text: str):
        norm_text = self.normalize_text(raw_text)
        
        # Fast filter for empty/1-letter strings
        if self.fast_length_check(norm_text):
            return {"status": "out_of_scope", "reason": "Text too short"}
            
        # 1. Extract features
        if self.extractor and self.extractor.idf_weights is not None:
            features = self.extractor.transform([norm_text])
        else:
            return {"status": "error", "reason": "Feature Extractor/IDF not loaded"}
            
        # 2. Beam Search Prediction (using predict_beam_batch)
        beam_results = self.engine.predict_beam_batch(features, top_k=5)
        
        item_beams = beam_results[0]
        top_result = item_beams[0]
        
        predicted_code = top_result['code']
        calibrated_prob = top_result['prob']
        
        # 3. NEW: Statistical Out-of-Scope Filter (t_oos)
        if calibrated_prob < self.t_oos:
            return {
                "status": "out_of_scope", 
                "reason": f"Confidence ({round(calibrated_prob, 3)}) is below the safety threshold ({round(self.t_oos, 3)}). Vague or non-customs text."
            }
            
        is_valid_track_f = predicted_code in self.valid_codes if self.valid_codes else True
        
        # 4. NEW: Hierarchical Fallback & 3-Tier Routing
        # Check Level 8 First
        if calibrated_prob >= self.bands['level_8']['high']:
            deepest_level = 8
            routing = "NORMAL"
            ui_message = "High Confidence - Auto Approve"
        elif calibrated_prob >= self.bands['level_8']['med']:
            deepest_level = 8
            routing = "HUMAN_VERIFICATION"
            ui_message = "Medium Confidence - Please Verify"
        else:
            # Fallback to Level 2 (Sum probabilities of beams sharing the same Chapter)
            top_chapter = predicted_code[:2]
            l2_prob = sum(b['prob'] for b in item_beams if b['code'][:2] == top_chapter)
            
            if l2_prob >= self.bands['level_2']['high']:
                deepest_level = 2
                routing = "NORMAL"
                ui_message = f"High Confidence at Chapter {top_chapter} - Select remaining digits"
            elif l2_prob >= self.bands['level_2']['med']:
                deepest_level = 2
                routing = "HUMAN_VERIFICATION"
                ui_message = f"Medium Confidence at Chapter {top_chapter} - Please Verify"
            else:
                # Fails both L8 and L2 med limits, but is above t_oos
                deepest_level = 2
                routing = "MANUAL_REVIEW"
                ui_message = "Low Confidence - Manual Review Required"

        # 5. NEW: Run the Track E Retrieval using YAML rules
        # Extract unique 2-digit chapters from the ML's top 5 predictions for search routing
        routed_chapters = list(set([int(beam['code'][:2]) for beam in item_beams]))
        
        retrieval_results = self.retrieval_engine.query(
            raw_text=raw_text, 
            routed_chapters=routed_chapters, 
            show_examples=self.show_examples
        )
            
        return {
            "status": "success",
            "raw_text": raw_text,
            "normalized_text": norm_text,
            "predicted_code": predicted_code,
            "calibrated_confidence": round(calibrated_prob, 4),
            "deepest_confident_level": deepest_level,
            "routing": routing,
            "ui_flag": ui_message,
            "track_f_valid": is_valid_track_f,
            "alternatives": item_beams[1:],
            "retrieval": retrieval_results
        }