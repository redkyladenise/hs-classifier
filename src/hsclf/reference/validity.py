from pathlib import Path
from typing import Optional, Tuple
import pandas as pd

_REF_PATH = Path("data/reference/ahtn_2022_scope_reference.parquet")
_REF_DICT: Optional[dict[str, str]] = None


def _load_reference() -> dict[str, str]:
    """Lazy-loads the AHTN 2022 scope reference into an in-memory dictionary for O(1) lookups."""
    global _REF_DICT
    if _REF_DICT is None:
        if not _REF_PATH.exists():
            raise FileNotFoundError(
                f"Reference dataset not found at {_REF_PATH.resolve()}. "
                "Ensure Track F Phase 2 extraction has been executed."
            )
        df = pd.read_parquet(_REF_PATH)
        _REF_DICT = dict(zip(df["code8"].astype(str), df["description"].astype(str)))
    return _REF_DICT


def check_code_validity(code: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Validates whether an 8-digit tariff code exists within the authoritative AHTN 2022 reference.

    Rules:
    - Accepts clean 8-digit strings (e.g., '39140000') or dotted formats (e.g., '3914.00.00').
    - Performs strict exact matching. No synthetic right-padding is applied.
    - A code ending in '00' is valid if and only if that exact line exists as a legal leaf code.

    Returns:
        Tuple[bool, Optional[str]]: (is_valid, official_description)
    """
    if not code or not isinstance(code, str):
        return False, None

    clean_code = code.strip().replace(".", "")

    if len(clean_code) != 8 or not clean_code.isdigit():
        return False, None

    ref_map = _load_reference()
    if clean_code in ref_map:
        return True, ref_map[clean_code]

    return False, None
