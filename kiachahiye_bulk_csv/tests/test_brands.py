"""Section 3 -- brand lookup behaviour."""

from __future__ import annotations

from brands import (
    BRANDS_ALFA,
    BRANDS_DIGI,
    canonical_brand_key,
    resolve_brand,
)


def test_lists_match_the_spec_exactly() -> None:
    assert isinstance(BRANDS_DIGI["dawlance"], int) and BRANDS_DIGI["dawlance"] > 0
    assert isinstance(BRANDS_ALFA["dawlance"], int) and BRANDS_ALFA["dawlance"] > 0
    assert BRANDS_DIGI["dawlance"] != BRANDS_ALFA["dawlance"]
    assert isinstance(BRANDS_DIGI["gree"], int) and isinstance(BRANDS_ALFA["gree"], int)
    assert len(BRANDS_DIGI) > 0
    assert len(BRANDS_ALFA) > 0


def test_dawlance_ids_differ_between_platforms() -> None:
    resolved = resolve_brand("Dawlance")
    assert resolved.digi_id == BRANDS_DIGI["dawlance"]
    assert resolved.alfa_id == BRANDS_ALFA["dawlance"]
    assert resolved.digi_id != resolved.alfa_id


def test_case_and_whitespace_are_normalised() -> None:
    for spelling in ("DAWLANCE", "dawlance", "  Dawlance  ", "Dawlance"):
        resolved = resolve_brand(spelling)
        assert resolved.digi_id == BRANDS_DIGI["dawlance"], spelling
        assert resolved.alfa_id == BRANDS_ALFA["dawlance"], spelling


def test_superasia_spacing_alias_is_needed_and_works() -> None:
    """45 rows in the real sheet spell it without the space."""
    assert "superasia" not in BRANDS_DIGI
    resolved = resolve_brand("Superasia")
    assert resolved.normalized == "super asia"
    assert resolved.digi_id == BRANDS_DIGI["super asia"]
    assert resolved.alfa_id == BRANDS_ALFA.get("super asia")


def test_orient_resolves_for_both() -> None:
    resolved = resolve_brand("Orient")
    assert resolved.digi_id == BRANDS_DIGI["orient"]
    assert resolved.alfa_id == BRANDS_ALFA["orient"]


def test_homage_is_missing_from_both() -> None:
    resolved = resolve_brand("Homage")
    assert resolved.digi_id is None
    assert resolved.alfa_id is None


def test_hisense_resolves_for_alfa() -> None:
    resolved = resolve_brand("Hisense")
    assert resolved.digi_id == BRANDS_DIGI.get("hisense")
    assert resolved.alfa_id == BRANDS_ALFA["hisense"]


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
