"""
tests/track_b/test_conflicts.py

Unit tests for conflict divergence typing and dominance calculations.
"""

from hsclf.audit.conflicts import (
    compute_code_distribution,
    get_divergence_type,
    get_dominance_band,
)


def test_divergence_types():
    # Single or empty
    assert get_divergence_type([]) is None
    assert get_divergence_type(["84713020"]) is None
    assert get_divergence_type(["84713020", "84713020"]) is None

    # D2: Differs at chapter
    assert get_divergence_type(["84713020", "85044090"]) == "D2"

    # D4: Same chapter (84), differs at heading (8471 vs 8473)
    assert get_divergence_type(["84713020", "84733010"]) == "D4"

    # D6: Same heading (8471), differs at subheading (847130 vs 847141)
    assert get_divergence_type(["84713020", "84714110"]) == "D6"

    # D8: Same subheading (847130), differs at leaf (84713020 vs 84713090)
    assert get_divergence_type(["84713020", "84713090"]) == "D8"


def test_dominance_bands():
    assert get_dominance_band(0.95) == "dominant"
    assert get_dominance_band(0.90) == "dominant"
    assert get_dominance_band(0.89) == "moderate"
    assert get_dominance_band(0.60) == "moderate"
    assert get_dominance_band(0.59) == "split"
    assert get_dominance_band(0.33) == "split"


def test_code_distribution_computation():
    # Single dominant
    codes = [("84713020", 95), ("84713090", 5)]
    top_code, share, band = compute_code_distribution(codes)
    assert top_code == "84713020"
    assert round(share, 2) == 0.95
    assert band == "dominant"

    # Deterministic tie-breaker (alphabetical)
    codes_tied = [("85044090", 50), ("84713020", 50)]
    top_code, share, band = compute_code_distribution(codes_tied)
    assert top_code == "84713020"
    assert share == 0.50
    assert band == "split"