"""Unit tests for HS code standardization (Track A4)."""

import pytest
from src.hsclf.data.codes import standardize_code


def test_standardize_11_digits():
    res = standardize_code("94042910123")
    assert res["ahtn8"] == "94042910"
    assert res["hs_extra"] == "123"
    assert res["code_fix"] == "trim_extra"
    assert res["code_flag"] == "valid"
    assert res["right_padded"] is False


def test_standardize_10_digits_dropped_zero():
    res = standardize_code("1012100001")
    assert res["ahtn8"] == "01012100"
    assert res["hs_extra"] == "001"
    assert res["ch2"] == "01"
    assert res["code_fix"] == "left_pad"
    assert res["code_flag"] == "valid"


def test_standardize_6_digits_right_padded():
    res = standardize_code("940429")
    assert res["ahtn8"] == "94042900"
    assert res["code_fix"] == "right_pad"
    assert res["code_flag"] == "valid"
    assert res["right_padded"] is True
    assert res["ends_00"] is True


def test_standardize_dots_and_dashes():
    res = standardize_code("9404.29.10")
    assert res["ahtn8"] == "94042910"
    assert res["code_fix"] == "none"
    assert res["code_flag"] == "valid"


def test_standardize_alphanumeric_bad_format():
    res = standardize_code("9404291A")
    assert res["code_flag"] == "bad_format"
    assert res["ahtn8"] is None


def test_standardize_zero_bad_format():
    res = standardize_code("0")
    assert res["code_flag"] == "bad_format"
    assert res["ahtn8"] is None


def test_standardize_null_bad_format():
    res = standardize_code(None)
    assert res["code_flag"] == "bad_format"
    assert res["ahtn8"] is None


def test_standardize_odd_length():
    res = standardize_code("940429101")  # 9 digits
    assert res["code_flag"] == "odd_length"
    assert res["ahtn8"] is None


def test_standardize_7_digits():
    res = standardize_code("4042910")  # Chapter 04
    assert res["ahtn8"] == "04042910"
    assert res["ch2"] == "04"
    assert res["code_fix"] == "left_pad"
    assert res["code_flag"] == "valid"


def test_standardize_5_digits():
    res = standardize_code("94042")  # Chapter 09, 5 digits -> 09404200
    assert res["ahtn8"] == "09404200"
    assert res["ch2"] == "09"
    assert res["code_fix"] == "left_pad+right_pad"
    assert res["code_flag"] == "valid"
    assert res["right_padded"] is True


def test_standardize_8_digits_exact():
    res = standardize_code("94042910")
    assert res["ahtn8"] == "94042910"
    assert res["code_fix"] == "none"
    assert res["code_flag"] == "valid"
    assert res["right_padded"] is False


def test_standardize_negative_bad_format():
    res = standardize_code("-9404291012")
    assert res["code_flag"] == "bad_format"
    assert res["ahtn8"] is None


def test_standardize_bad_chapters():
    # Chapter 77 is reserved
    res_77 = standardize_code("77012345")
    assert res_77["code_flag"] == "bad_chapter"
    assert res_77["ahtn8"] is None

    # Chapter 98 is out of scope (01-97)
    res_98 = standardize_code("98012345")
    assert res_98["code_flag"] == "bad_chapter"
    assert res_98["ahtn8"] is None


def test_right_padded_distinction():
    # 940429 right-pads to 94042900 -> right_padded = True
    res_6 = standardize_code("940429")
    assert res_6["ahtn8"] == "94042900"
    assert res_6["right_padded"] is True

    # 94042900 naturally ends in 00 -> right_padded = False
    res_8 = standardize_code("94042900")
    assert res_8["ahtn8"] == "94042900"
    assert res_8["right_padded"] is False