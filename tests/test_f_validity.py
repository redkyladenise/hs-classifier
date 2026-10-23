import pytest
from hsclf.reference.validity import check_code_validity


def test_valid_leaf_code_plain():
    """Verify clean 8-digit leaf code returns valid with correct description."""
    valid, desc = check_code_validity("39140000")
    assert valid is True
    assert desc is not None
    assert "Ion-exchangers" in desc


def test_valid_leaf_code_dotted():
    """Verify dotted format normalizes correctly."""
    valid, desc = check_code_validity("8467.29.00")
    assert valid is True
    assert desc is not None


def test_valid_trailing_double_zero_leaf():
    """Verify a code ending in 00 is valid because the exact line exists."""
    valid, desc = check_code_validity("73130000")
    assert valid is True
    assert desc is not None
    assert "Barbed wire" in desc


def test_invalid_arbitrary_code():
    """Verify a non-existent 8-digit number returns False."""
    valid, desc = check_code_validity("99999999")
    assert valid is False
    assert desc is None


def test_reject_short_code_no_padding():
    """Verify strict exact matching does NOT synthesize right-padding on 4/6-digit codes."""
    valid_4, desc_4 = check_code_validity("8471")
    assert valid_4 is False
    assert desc_4 is None

    valid_6, desc_6 = check_code_validity("847130")
    assert valid_6 is False
    assert desc_6 is None


def test_reject_non_numeric_and_malformed():
    """Verify malformed strings and edge cases fail cleanly."""
    for malformed in ["", "ABCD1234", "8471.30", "   ", "8471-30-20"]:
        valid, desc = check_code_validity(malformed)
        assert valid is False
        assert desc is None


def test_none_input():
    """Verify None input is safely handled."""
    valid, desc = check_code_validity(None)
    assert valid is False
    assert desc is None
