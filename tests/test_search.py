import os
import sys
import pytest
import numpy as np
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.hsclf.retrieval.search import RetrievalEngine
from src.hsclf.models.features import FeatureExtractor

# We use a fixture to build the engine once for all tests
@pytest.fixture(scope="module")
def engine():
    # Paths must point to the files we just built in E1
    idf_path = 'data/processed/idf_main.npy'
    index_meta_path = 'data/processed/retrieval/index_meta.parquet'
    retrieval_codes_path = 'data/processed/retrieval/retrieval_codes.parquet'
    
    # Quick safety check so tests skip nicely if files aren't built
    if not os.path.exists(index_meta_path):
        pytest.skip("E1 index files not found. Run E1 first.")
        
    extractor = FeatureExtractor()
    return RetrievalEngine(idf_path, index_meta_path, retrieval_codes_path, extractor)

def test_self_match(engine):
    """
    If we query the exact text of a description already in the index,
    it must return itself as the #1 match with a similarity score of ~1.0.
    """
    # 1. Grab a real description that is guaranteed to be in the index
    meta_df = engine.meta_df
    sample_row = meta_df.iloc[0]
    sample_chapter = sample_row['chapter']
    
    # We need the raw text to test the full pipeline (normalization -> math -> search)
    # The meta_df only has IDs, so we load the text from norm_descriptions
    text_df = pd.read_parquet('data/interim/norm_descriptions.parquet')
    sample_text = text_df[text_df['desc_norm_id'] == sample_row['desc_norm_id']]['desc_norm'].iloc[0]

    # 2. Run the query
    results = engine.query(raw_text=sample_text, routed_chapters=[sample_chapter], top_k=5)
    
    # 3. Assertions (The Test Rules)
    assert not results.empty, "Query returned no results."
    
    top_match = results.iloc[0]
    
    # The #1 match must be the exact same ID
    assert top_match['group_l1'] == sample_row['desc_norm_id'], "Did not retrieve itself."
    
    # The similarity math must equal 1.0 (with a tiny margin for float rounding)
    assert np.isclose(top_match['similarity'], 1.0, atol=1e-5), f"Similarity is {top_match['similarity']}, expected 1.0"
    
def test_distribution_formatting(engine):
    """
    Tests that the 'Top 3 + Other' formatting rule works correctly.
    """
    # Create fake results with 5 valid codes and 1 invalid code
    fake_results = pd.DataFrame({
        'group_l1': [1, 2, 3, 4, 5, 6],
        'code': ['A', 'B', 'C', 'D', 'E', 'INVALID'],
        'declaration_count': [1000, 500, 250, 100, 50, 10000],
        'is_valid': [True, True, True, True, True, False]
    })
    
    summary = engine.summarize_distribution(fake_results)
    dist = summary['distribution']
    
    # 1. Invalid codes must be dropped
    assert summary['invalid_dropped'] == 1, "Failed to drop invalid code."
    assert 'INVALID' not in dist['code'].values, "Invalid code leaked into distribution."
    
    # 2. Must be exactly 4 rows (Top 3 + 'Other')
    assert len(dist) == 4, "Did not format to exactly Top 3 + Other."
    
    # 3. The 4th row must be named 'Other'
    assert dist.iloc[3]['code'] == 'Other', "Last row is not named 'Other'."
    
    # 4. 'Other' must correctly sum the counts of D (100) and E (50)
    assert dist.iloc[3]['declaration_count'] == 150, "'Other' math is wrong."