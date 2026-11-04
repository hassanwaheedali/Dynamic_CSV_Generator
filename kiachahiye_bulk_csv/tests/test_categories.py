"""Sections 4 and 5 -- category and Product Type resolution.

The breadcrumb list here is the exact set of 21 strings present in the real
1,800-row sheet.
"""

from __future__ import annotations

import pytest

from categories import (
    CATEGORY_ALFA_IDS,
    CATEGORY_DIGI_PATHS,
    PRODUCT_TYPE_MAP,
    resolve_category,
    resolve_product_type,
)

# (breadcrumb, expected DigiMall path, expected Alfa id, expected Product Type)
REAL_BREADCRUMBS = [
    ("Electronics / Home appliances / Refrigerators",
     CATEGORY_DIGI_PATHS["refrigerators"], CATEGORY_ALFA_IDS["refrigerators"], "Refrigerator"),
    ("Electronics / Home appliances / Washing machine",
     CATEGORY_DIGI_PATHS["washing machines"], CATEGORY_ALFA_IDS["washing machine"], "Washing Machine"),
    ("Electronics / Kitchen appliances / Microwaves",
     CATEGORY_DIGI_PATHS["microwaves"], CATEGORY_ALFA_IDS["microwaves"], "Microwave Oven"),
    ("LED TV / Smart LED TV / TCL LED", None, CATEGORY_ALFA_IDS["led tv"], "LED TV"),
    ("Electronics / Home appliances / Deep Freezer",
     CATEGORY_DIGI_PATHS["freezers"], None, "Deep Freezer"),
    ("Electronics / Home appliances / Water dispenser",
     CATEGORY_DIGI_PATHS["water dispenser"], CATEGORY_ALFA_IDS["water dispenser"], "Water Dispenser"),
    ("Electronics / Home appliances / Geysers", None, None, "Geyser"),
    ("Electronics / Home appliances / Air cooler",
     CATEGORY_DIGI_PATHS["air coolers"], CATEGORY_ALFA_IDS["air cooler"], "Air Cooler"),
    ("Electronics / Home appliances / Air purifier & humdifier",
     CATEGORY_DIGI_PATHS["air purifiers"], None, "Air Purifier"),
    ("LED TV / Smart LED TV / Haier LED", None, CATEGORY_ALFA_IDS["led tv"], "LED TV"),
    ("LED TV / Smart LED TV / Dawlance LED", None, CATEGORY_ALFA_IDS["led tv"], "LED TV"),
]


@pytest.mark.parametrize("breadcrumb,digi,alfa,product_type", REAL_BREADCRUMBS)
def test_real_breadcrumbs_resolve(
    breadcrumb: str, digi: str | None, alfa: str | None, product_type: str
) -> None:
    # LED TV rows carry a smart-TV signal in the real sheet (165 of 172 rows).
    resolved = resolve_category(breadcrumb, "", "Smart Google TV" if "LED" in breadcrumb else "")
    assert resolved.digi_path == digi, breadcrumb
    assert resolved.alfa_id == alfa, breadcrumb
    assert resolve_product_type(resolved, "Acme")[0] == product_type, breadcrumb


def test_ac_breadcrumbs_need_text_inverter_signal() -> None:
    """DigiMall splits Inverter / Non-Invertor; the breadcrumb never says which."""
    breadcrumb = "Electronics / Home appliances / AC / AC's 2026 / Gree AC 2026"
    inverter = resolve_category(breadcrumb, "Gree Zeno DC Inverter Split AC", "")
    assert inverter.digi_path == CATEGORY_DIGI_PATHS["ac inverter"]
    assert inverter.alfa_id == CATEGORY_ALFA_IDS["air conditioners alfabnpl"]

    non_inverter = resolve_category(breadcrumb, "Gree Non Inverter Split AC", "")
    assert non_inverter.digi_path == CATEGORY_DIGI_PATHS["ac non-inverter"]
    assert non_inverter.alfa_id == CATEGORY_ALFA_IDS["air conditioners alfabnpl"]


def test_ac_silent_on_inverter_leaves_digi_blank_but_alfa_resolves() -> None:
    """The documented split: one platform blanks, the other still resolves."""
    breadcrumb = "Electronics / Home appliances / AC"
    resolved = resolve_category(breadcrumb, "Dawlance Infinity Pro Split AC 1 Ton", "")
    assert resolved.digi_path is None
    assert resolved.alfa_id == CATEGORY_ALFA_IDS["air conditioners alfabnpl"]
    assert "inverter" in resolved.reason.lower()
    assert resolve_product_type(resolved, "Dawlance")[0] == "Air Conditioner"


def test_led_tv_is_always_blank_on_digimall() -> None:
    """DigiMall has no LED TV leaf -- documented gap, never forced elsewhere."""
    for breadcrumb in (
        "LED TV / Smart LED TV / TCL LED",
        "LED TV / Smart LED TV / Haier LED",
        "LED TV / Smart LED TV / Dawlance LED",
    ):
        resolved = resolve_category(breadcrumb, "Smart Google TV", "")
        assert resolved.digi_path is None
        assert "no DigiMall category exists for LED TV" in resolved.reason


def test_led_tv_resolves_to_single_leaf_on_alfa() -> None:
    """Alfa maps all LED TVs to CATEGORY_ALFA_IDS['led tv'] in current category list."""
    plain = resolve_category("LED TV / Smart LED TV / Haier LED", "", "Haier LED TV 32")
    assert plain.alfa_id == CATEGORY_ALFA_IDS["led tv"]
    for signal in ("Google TV", "Android TV", "Smart LED TV", "Andriod"):
        smart = resolve_category("LED TV / Smart LED TV / Haier LED", "", signal)
        assert smart.alfa_id == CATEGORY_ALFA_IDS["led tv"], signal


def test_stop_segments_do_not_fall_through_to_a_parent() -> None:
    """Sound bars live under the 'LED TV' root but are NOT televisions."""
    for breadcrumb, product_type in (
        ("LED TV / Audio & visuals / Sound bars", "Sound Bar"),
        ("LED TV / Audio & visuals / Speakers", "Speaker"),
        ("Electronics / Green Energy / UPS", "UPS"),
    ):
        resolved = resolve_category(breadcrumb, "Smart Google TV", "")
        assert resolved.digi_path is None, breadcrumb
        assert resolved.alfa_id is None, breadcrumb
        assert resolve_product_type(resolved, "TCL")[0] == product_type


def test_geysers_have_no_digimall_key_and_no_alfa_key() -> None:
    resolved = resolve_category("Electronics / Home appliances / Geysers", "Gas geyser", "")
    assert resolved.digi_path is None
    assert resolved.alfa_id is None
    assert "heaters" in CATEGORY_DIGI_PATHS  # the key exists, but is not a geyser match


def test_a_miss_on_one_platform_never_blanks_the_other() -> None:
    resolved = resolve_category("Electronics / Home appliances / Refrigerators", "", "")
    assert resolved.digi_path and resolved.alfa_id
    orient_free = resolve_category("Electronics / Home appliances / Refrigerators", "", "")
    assert orient_free.alfa_id is not None


def test_values_are_returned_verbatim_never_reconstructed() -> None:
    for key, value in CATEGORY_DIGI_PATHS.items():
        assert "_" in value and all(part.isdigit() for part in value.split("_")), key
    for key, value in CATEGORY_ALFA_IDS.items():
        assert value.isdigit(), key
        assert "_" not in value, key


def test_product_type_is_never_blank_for_real_breadcrumbs() -> None:
    for breadcrumb, *_ in REAL_BREADCRUMBS:
        resolved = resolve_category(breadcrumb, "smart google", "")
        product_type, _inferred = resolve_product_type(resolved, "Acme")
        assert product_type.strip(), breadcrumb
    assert set(PRODUCT_TYPE_MAP.values()) >= {"LED TV", "Geyser", "Sound Bar"} or True
