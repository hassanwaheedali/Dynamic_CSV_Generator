"""Section 3 -- brand lookup behaviour."""

from __future__ import annotations

from brands import (
    BRANDS_ALFA,
    BRANDS_DIGI,
    canonical_brand_key,
    resolve_brand,
)


def test_lists_match_the_spec_exactly() -> None:
    assert BRANDS_DIGI["dawlance"] == 3755
    assert BRANDS_ALFA["dawlance"] == 3673
    assert BRANDS_DIGI["gree"] == 3790 and BRANDS_ALFA["gree"] == 3678
    assert len(BRANDS_DIGI) == 12
    assert len(BRANDS_ALFA) == 11


def test_dawlance_ids_differ_between_platforms() -> None:
    resolved = resolve_brand("Dawlance")
    assert resolved.digi_id == 3755
    assert resolved.alfa_id == 3673
    assert resolved.digi_id != resolved.alfa_id


def test_case_and_whitespace_are_normalised() -> None:
    for spelling in ("DAWLANCE", "dawlance", "  Dawlance  ", "Dawlance"):
        resolved = resolve_brand(spelling)
        assert resolved.digi_id == 3755, spelling
        assert resolved.alfa_id == 3673, spelling


def test_superasia_spacing_alias_is_needed_and_works() -> None:
    """45 rows in the real sheet spell it without the space."""
    assert "superasia" not in BRANDS_DIGI
    resolved = resolve_brand("Superasia")
    assert resolved.normalized == "super asia"
    assert resolved.digi_id == 3776
    assert resolved.alfa_id == 4395


def test_orient_is_missing_from_alfa_only() -> None:
    resolved = resolve_brand("Orient")
    assert resolved.digi_id == 3769
    assert resolved.alfa_id is None


def test_homage_and_hisense_are_missing_from_both() -> None:
    for brand in ("Homage", "Hisense"):
        resolved = resolve_brand(brand)
        assert resolved.digi_id is None, brand
        assert resolved.alfa_id is None, brand


def test_no_fuzzy_matching_ever() -> None:
    """A near-miss must NOT resolve -- 'closest sounding' is forbidden.

    ("Dawlanc" is deliberately excluded: spec section 3 names it as a known
    DigiMall export spelling and it lives in the explicit alias table.)
    """
    for near_miss in ("Dawlance Pak", "Haierr", "TCL Pakistan Ltd", "Greee"):
        resolved = resolve_brand(near_miss)
        assert resolved.digi_id is None, near_miss
        assert resolved.alfa_id is None, near_miss


def test_alias_table_is_explicit_not_computed() -> None:
    assert canonical_brand_key("Superasia") == "super asia"
    assert canonical_brand_key("xiaomi") == "xioami"  # Alfa's own spelling
    assert canonical_brand_key("Something New") == "something new"
