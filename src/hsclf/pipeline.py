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
        
        project_root = Path(__file__).resolve().parent.parent.parent
        params_path = project_root / 'config' / 'params.yaml'
        
        with open(params_path, 'r') as f:
            self.params = yaml.safe_load(f)
            
        self.bands = self.params.get('confidence_bands', {
            8: {'high': 0.75, 'med': 0.50},
            6: {'high': 0.75, 'med': 0.50},
            4: {'high': 0.90, 'med': 0.60},
            2: {'high': 0.90, 'med': 0.60}
        })
        self.t_oos = self.params.get('t_oos', 0.3788)
        self.show_examples = self.params.get('track_e', {}).get('show_examples', True)
        
        self.valid_codes = self._load_valid_codes()
        self.engine = HSInferenceEngine(scenario=self.scenario, cache_size=cache_size)
        
        self.extractor = FeatureExtractor()
        idf_path = project_root / f'data/processed/idf_{scenario}.npy'
        
        if idf_path.exists():
            idf_array = np.load(idf_path)   
            self.extractor.set_idf(idf_array)
        else:
            self.extractor = None

        self.retrieval_engine = RetrievalEngine()

        self.messages = {
            8: "Confident down to the tariff line (8-digit). Please still verify before declaring.",
            6: "For Human Verification: Confident down to the subheading (6-digit). Please verify the tariff line.",
            4: "For Human Verification: Confident down to the heading (4-digit). Please verify the rest.",
            2: "For Human Verification: Confident down to the chapter (2-digit). Please verify the rest.",
            None: "Needs human verification at every level."
        }

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
        
        if self.fast_length_check(norm_text):
            return {"status": "out_of_scope", "reason": "Text is too short"}
            
        if self.extractor and self.extractor.idf_weights is not None:
            features = self.extractor.transform([norm_text])
        else:
            return {"status": "error", "reason": "Feature Extractor/IDF not loaded"}
            
        beam_results = self.engine.predict_beam_batch(features, top_k=5)
        item_beams = beam_results[0]
        top_result = item_beams[0]
        predicted_code = top_result['code']
        
        # Calculate level confidences by summing beam probabilities
        confidences = {}
        for lvl in (8, 6, 4, 2):
            prefix = predicted_code[:lvl]
            # Assuming raw beam probabilities serve as the calibrated proxy based on previous logic
            confidences[lvl] = sum(b['prob'] for b in item_beams if b['code'][:lvl] == prefix)

        # 1. Scope check on Chapter (Level 2) confidence
        if confidences[2] < self.t_oos:
            return {
                "status": "out_of_scope", 
                "reason": f"Chapter confidence ({round(confidences[2], 3)}) is below the safety threshold ({round(self.t_oos, 3)}). May be outside supported chapters, or too vague."
            }
            
        is_valid_track_f = predicted_code in self.valid_codes if self.valid_codes else True
        
        deepest = None
        bands_out = {}
        
        for lvl in (8, 6, 4, 2):
            p = confidences[lvl]
            if p >= self.bands[lvl]["high"]:
                band = "High"
            elif p >= self.bands[lvl]["med"]:
                band = "Medium"
            else:
                band = "Low"
                
            bands_out[lvl] = band
            if deepest is None and band != "Low":
                deepest = lvl
                
        verification_required = (deepest != 8)
        ui_message = self.messages[deepest]

        routed_chapters = list(set([int(beam['code'][:2]) for beam in item_beams]))
        
        retrieval_results = self.retrieval_engine.query(
            raw_text=raw_text, 
            routed_chapters=routed_chapters, 
            show_examples=self.show_examples
        )
        
        for key, value in list(retrieval_results.items()):
            if isinstance(value, pd.DataFrame):
                new_key = key.replace('_df', '_list') if key.endswith('_df') else key
                retrieval_results[new_key] = value.to_dict(orient="records")
                if new_key != key:
                    del retrieval_results[key]
            
        return {
            "status": "success",
            "raw_text": raw_text,
            "normalized_text": norm_text,
            "predicted_code": predicted_code,
            "deepest_confident_level": deepest,
            "verification_required": verification_required,
            "ui_flag": ui_message,
            "bands_out": bands_out,
            "track_f_valid": is_valid_track_f,
            "alternatives": item_beams[1:],
            "retrieval": retrieval_results
        }
    
if __name__ == "__main__":
    import json
    
    print("Loading HSPipeline (this may take a few seconds to load the models)...")
    pipeline = HSPipeline(scenario='main')
    
    # Let's test 4 different types of inputs to trigger your different routing rules

    test_cases = [
        # In-Scope (Should Pass)
        "apple macbook pro laptop computer",  
        "steel pipes",                        
        "machine parts", 
        "PART OF 1 CASE  - YAMAHA - CAP, CLEANER CASE 1 - 10 PCS",
        "2PCE OIL PUMP ASSY",
        
        # Pure Garbage (Should Fail)
        "asdfghjkl",                          
        "as per invoice",
        
        # True Out-of-Scope (Should Fail - Not in Chapters 39, 73, 84, 85, 87)
        "fresh mangoes",
        "men's cotton t-shirts",
        "wooden dining chair"
    ]
    
    for text in test_cases:
        print(f"\n" + "="*50)
        print(f"USER INPUT: '{text}'")
        print("="*50)
        
        result = pipeline.predict(text)
        
        # Print the dictionary in a clean, readable JSON format
        print(json.dumps(result, indent=2))