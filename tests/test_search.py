import pytest
import pandas as pd
from src.hsclf.retrieval.search import RetrievalEngine

# --- Test Fixtures ---
@pytest.fixture(scope="module")
def engine():
    # Initialize the engine once for all tests to save time
    return RetrievalEngine()

@pytest.fixture(scope="module")
def sample_training_item():
    # Grab the very first item from the known training index to test "self-match"
    meta = pd.read_parquet('data/processed/retrieval/index_meta.parquet')
    unique_df = pd.read_parquet('data/processed/unique_descriptions.parquet')
    first_item = meta.iloc[0]
    
    # Bridge to get the actual text
    target_id = first_item['desc_norm_id']
    target_text = unique_df[unique_df['desc_norm_id'] == target_id]['desc_norm'].iloc[0] if 'desc_norm' in unique_df.columns else "stainless steel pipe" # Fallback if text is in interim
    
    # If the text is actually in the interim folder
    if 'desc_norm' not in unique_df.columns:
         norm_df = pd.read_parquet('data/interim/norm_descriptions.parquet')
         target_text = norm_df[norm_df['desc_norm_id'] == target_id]['desc_norm'].iloc[0]
         
    return {
        'text': target_text,
        'chapter': first_item['chapter'],
        'group_l1': first_item['group_l1']
    }

# --- Tests ---
def test_self_match(engine, sample_training_item):
    """Rule: A training description finds itself at similarity ~1.0"""
    result = engine.query(sample_training_item['text'], routed_chapters=[sample_training_item['chapter']])
    
    assert not result['neighbors_df'].empty, "Search returned empty results"
    top_match = result['neighbors_df'].iloc[0]
    
    assert top_match['group_l1'] == sample_training_item['group_l1'], "Did not find itself as the top match"
    assert top_match['similarity'] > 0.99, "Similarity for self-match is not ~1.0"

def test_ordering(engine, sample_training_item):
    """Rule: Results come back in order of similarity"""
    result = engine.query(sample_training_item['text'], routed_chapters=[sample_training_item['chapter']], top_k=5)
    
    sims = result['neighbors_df']['similarity'].tolist()
    # Check if the list is sorted in descending order
    assert sims == sorted(sims, reverse=True), "Results are not ordered by similarity"

def test_invalid_code_handling(engine):
    """Rule: An invalid code is left out of the distribution but kept for the hit-rate check (neighbors_df)"""
    # We will simulate a query that we know returns results, and manually inject an invalid code to test the logic
    # Since we can't guarantee an invalid code naturally appears in top 5, we test the internal _build_distribution directly
    
    mock_df = pd.DataFrame({
        'group_l1': ['A', 'B'],
        'similarity': [0.9, 0.8],
        'code': ['12345678', '99999999'], # 99999999 is our fake invalid
        'declaration_count': [100, 50],
        'is_valid': [True, False]
    })
    
    result = engine._build_distribution(mock_df, min_sim=0.5, split_share=0.6)
    
    assert result['invalid_dropped'] == 1, "Failed to count the dropped invalid code"
    assert '99999999' not in result['distribution']['code'].values, "Invalid code leaked into the final distribution"
    assert '99999999' in result['neighbors_df']['code'].values, "Invalid code was deleted from the neighbors list (needed for hit-rate check)"

def test_gibberish_no_match(engine):
    """Rule: A nonsense string such as 'qwzx plmk' returns no_close_match"""
    result = engine.query("qwzx plmk", routed_chapters=[39, 73, 84, 85, 87])
    
    assert result['no_close_match'] is True, "Gibberish did not trigger the no_close_match flag"