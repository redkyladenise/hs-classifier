"""Unit tests for description normalization (Track A5)."""

import pytest
from src.hsclf.data.normalize import compute_desc_norm_id, normalize_light


def test_example_1_foam_mattress():
    res = normalize_light("FOAM Mattress")
    assert res["desc_norm"] == "foam mattress"
    assert res["desc_status"] == "ok"


def test_example_2_laptop():
    res = normalize_light("LAPTOP (15.6 INCH) *NEW*")
    assert res["desc_norm"] == "laptop 15.6 inch new"
    assert res["desc_status"] == "ok"


def test_example_3_cotton_tshirt():
    res = normalize_light("Cotton T-Shirt, 100% Cotton")
    assert res["desc_norm"] == "cotton t-shirt, 100% cotton"
    assert res["desc_status"] == "ok"


def test_example_4_placeholder_na():
    res = normalize_light("N/A")
    assert res["desc_norm"] == "n/a"
    assert res["desc_status"] == "placeholder"

    res_none = normalize_light("None")
    assert res_none["desc_norm"] == "none"
    assert res_none["desc_status"] == "placeholder"


def test_blank_and_symbols_only():
    # Empty string
    assert normalize_light("")["desc_status"] == "blank"
    assert normalize_light(None)["desc_status"] == "blank"

    # Only symbols and numbers (no letters)
    res_digits = normalize_light("12345 6789")
    assert res_digits["desc_status"] == "blank"

    res_symbols = normalize_light("... --- /// +++")
    assert res_symbols["desc_status"] == "blank"


def test_id_determinism_and_bounds():
    id_1 = compute_desc_norm_id("laptop 15.6 inch new")
    id_2 = compute_desc_norm_id("laptop 15.6 inch new")
    assert id_1 == id_2
    assert 0 <= id_1 < (1 << 63)  # Valid positive 63-bit integer


def test_idempotency():
    raw = "  ELECTRONIC INTEGRATED CIRCUITS: 2.5V, (MODULE) #123! "
    step_1 = normalize_light(raw)
    step_2 = normalize_light(step_1["desc_norm"])

    assert step_1["desc_norm"] == step_2["desc_norm"]
    assert step_1["desc_norm_id"] == step_2["desc_norm_id"]
    assert step_1["desc_status"] == step_2["desc_status"]