"""
src/hsclf/audit/conflicts.py

Core audit functions for conflict categorization and dominance calculation.
"""

from typing import Iterable, List, Optional, Tuple


def get_divergence_type(codes: Iterable[str]) -> Optional[str]:
    """
    Determines the shallowest hierarchical level at which a set of 8-digit
    AHTN codes diverge.

    Returns:
        'D2': Diverges at 2-digit chapter (digits 0..2)
        'D4': Same chapter, diverges at 4-digit heading (digits 2..4)
        'D6': Same heading, diverges at 6-digit subheading (digits 4..6)
        'D8': Same subheading, diverges at 8-digit tariff line (digits 6..8)
        None: No divergence (0 or 1 distinct 8-digit code)
    """
    cleaned_codes = sorted({str(c).strip().zfill(8)[:8] for c in codes if c})
    if len(cleaned_codes) <= 1:
        return None

    # Check 2-digit Chapter
    ch2_set = {c[:2] for c in cleaned_codes}
    if len(ch2_set) > 1:
        return "D2"

    # Check 4-digit Heading
    hd4_set = {c[:4] for c in cleaned_codes}
    if len(hd4_set) > 1:
        return "D4"

    # Check 6-digit Subheading
    sh6_set = {c[:6] for c in cleaned_codes}
    if len(sh6_set) > 1:
        return "D6"

    # Check 8-digit Tariff Line
    return "D8"


def get_dominance_band(top_share: float) -> str:
    """
    Categorizes the transaction dominance of the most declared code:
        'dominant': >= 90%
        'moderate': 60% <= share < 90%
        'split': < 60%
    """
    if top_share >= 0.90:
        return "dominant"
    elif top_share >= 0.60:
        return "moderate"
    return "split"


def compute_code_distribution(code_counts: List[Tuple[str, int]]) -> Tuple[str, float, str]:
    """
    Given a list of (ahtn8_code, transaction_count), returns:
        (top_code, top_share, dominance_band)
    """
    if not code_counts:
        return "", 0.0, "none"

    total_tx = sum(count for _, count in code_counts)
    if total_tx == 0:
        return "", 0.0, "none"

    # Sort descending by count, ascending by code for deterministic tie-breaking
    sorted_codes = sorted(code_counts, key=lambda x: (-x[1], x[0]))
    top_code, top_count = sorted_codes[0]
    top_share = top_count / total_tx
    band = get_dominance_band(top_share)

    return top_code, top_share, band