"""Unit tests for Track A7 & Track A8: Description Grouping and Splitting logic."""

from src.hsclf.data.group_split import (
    assign_split_by_position,
    compute_group_l2_id,
    compute_skeleton_text,
    determine_seen_status,
    hash_group_seed,
)


def test_skeleton_token_sorting_and_deduplication():
    s1 = compute_skeleton_text("steel bolt 10mm steel")
    s2 = compute_skeleton_text("bolt 12mm steel")
    assert s1 == "bolt mm steel"
    assert s2 == "bolt mm steel"
    assert s1 == s2
    assert compute_group_l2_id(s1) == compute_group_l2_id(s2)

    s3 = compute_skeleton_text("bearing roller ball bearing")
    assert s3 == "ball bearing roller"


def test_skeleton_punctuation_and_digit_removal():
    raw_norm = "laptop (15.6 inch) *new*, 100% genuine!"
    skeleton = compute_skeleton_text(raw_norm)
    assert skeleton == "genuine inch laptop new"


def test_skeleton_empty_or_non_alpha():
    assert compute_skeleton_text("") == ""
    assert compute_skeleton_text(None) == ""
    assert compute_skeleton_text("12345 6789") == ""
    assert compute_skeleton_text("... --- /// +++") == ""


def test_group_l2_id_properties():
    sk = "bearing ball steel"
    id_1 = compute_group_l2_id(sk)
    id_2 = compute_group_l2_id(sk)
    assert id_1 == id_2
    assert 0 <= id_1 < (1 << 63)


def test_position_formula_10_groups():
    # Exactly 10 groups:
    # rank 1..7  -> pos 0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65 (< 0.70) -> train (7)
    # rank 8     -> pos 0.75 (< 0.85) -> val (1)
    # rank 9..10 -> pos 0.85, 0.95 (>= 0.85) -> test (2)
    splits = [assign_split_by_position(r, 10) for r in range(1, 11)]
    assert splits.count("train") == 7
    assert splits.count("val") == 1
    assert splits.count("test") == 2


def test_hash_group_seed_determinism():
    h1 = hash_group_seed(8298994855678238606, 42)
    h2 = hash_group_seed(8298994855678238606, 42)
    h3 = hash_group_seed(8298994855678238606, 99)
    assert h1 == h2
    assert h1 != h3


def test_determine_seen_status():
    # Group in train: exact match in 2023 for y1 (train: 2023)
    assert determine_seen_status("train", first_year_l1=2023, first_year_l2=2023, scenario_last_train_year=2023) == "seen_exact"

    # Group in train: near match (skeleton appeared in 2023, exact l1 appeared in 2024)
    assert determine_seen_status("train", first_year_l1=2024, first_year_l2=2023, scenario_last_train_year=2023) == "seen_near"

    # Group in train: both group and l1 appeared after train window
    assert determine_seen_status("train", first_year_l1=2025, first_year_l2=2025, scenario_last_train_year=2024) == "new"

    # Group in val, test, or only_2025 -> always 'new'
    assert determine_seen_status("val", first_year_l1=2023, first_year_l2=2023, scenario_last_train_year=2024) == "new"
    assert determine_seen_status("test", first_year_l1=2023, first_year_l2=2023, scenario_last_train_year=2024) == "new"
    assert determine_seen_status("only_2025", first_year_l1=2025, first_year_l2=2025, scenario_last_train_year=2024) == "new"