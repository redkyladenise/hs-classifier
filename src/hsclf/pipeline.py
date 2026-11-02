import re
import numpy as np
from pathlib import Path
import pandas as pd

# Import your C2 Extractor and C5 Engine
from src.hsclf.models.features import FeatureExtractor
from scripts.track_c.c5_2_inference_tests import HSInferenceEngine

class HSPipeline:
    def __init__(self, scenario='main', cache_size=150):
        self.scenario = scenario
        self.confidence_threshold = 0.50
        
        # 1. Load Track F valid codes
        self.valid_codes = self._load_valid_codes()
        
        # 2. Load the C5 Engine
        self.engine = HSInferenceEngine(scenario=self.scenario, cache_size=cache_size)
        
        # 3. Load the C2 Feature Extractor and set IDF weights
        self.extractor = FeatureExtractor()
        idf_path = f'data/processed/idf_{scenario}.npy'
        
        if Path(idf_path).exists():
            idf_array = np.load(idf_path)
            self.extractor.set_idf(idf_array)
        else:
            self.extractor = None

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
        
    def out_of_scope_rule(self, norm_text: str) -> bool:
        return len(norm_text) < 3

    def predict(self, raw_text: str):
        norm_text = self.normalize_text(raw_text)
        
        if self.out_of_scope_rule(norm_text):
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
        
        is_valid_track_f = predicted_code in self.valid_codes if self.valid_codes else True
        
        # 3. Routing Rule
        deepest_level = 8 # Always provide the 8-digit candidates to the screen
        
        if calibrated_prob >= self.confidence_threshold:
            # High or Medium at level 8
            routing = "NORMAL"
            ui_message = "Show normally with confidence"
        else:
            # Low at level 8
            routing = "HUMAN_REVIEW"
            ui_message = "Unverified, please check"
            
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
            "alternatives": item_beams[1:]
        }