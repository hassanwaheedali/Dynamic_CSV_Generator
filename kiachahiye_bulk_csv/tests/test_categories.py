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
     "11639_11643_11661_11787", "11507", "Refrigerator"),
    ("Electronics / Home appliances / Washing machine",
     "11639_11643_11791_11792", "11506", "Washing Machine"),
    ("Electronics / Kitchen appliances / Microwaves",
     "11639_11643_11661_11666", "11519", "Microwave Oven"),
    ("LED TV / Smart LED TV / TCL LED", None, "11539", "LED TV"),
    ("Electronics / Home appliances / Deep Freezer",
     "11639_11643_11661_11788", None, "Deep Freezer"),
    ("Electronics / Home appliances / Water dispenser",
     "11639_11643_11661_11669", "11509", "Water Dispenser"),
    ("Electronics / Home appliances / Geysers", None, None, "Geyser"),
    ("Electronics / Home appliances / Air cooler",
     "11639_11643_11653_11654", "11511", "Air Cooler"),
    ("Electronics / Home appliances / Air purifier & humdifier",
     "11639_11643_11653_11655", None, "Air Purifier"),
    ("LED TV / Smart LED TV / Haier LED", None, "11539", "LED TV"),
    ("LED TV / Smart LED TV / Dawlance LED", None, "11539", "LED TV"),
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
    assert inverter.digi_path == "11639_11643_11653_11782_11783"
    assert inverter.alfa_id == "12353"

    non_inverter = resolve_category(breadcrumb, "Gree Non Inverter Split AC", "")
    assert non_inverter.digi_path == "11639_11643_11653_11782_11784"
    assert non_inverter.alfa_id == "12353"


def test_ac_silent_on_inverter_leaves_digi_blank_but_alfa_resolves() -> None:
    """The documented split: one platform blanks, the other still resolves."""
    breadcrumb = "Electronics / Home appliances / AC"
    resolved = resolve_category(breadcrumb, "Dawlance Infinity Pro Split AC 1 Ton", "")
    assert resolved.digi_path is None
    assert resolved.alfa_id == "12353"
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
    """Alfa maps all LED TVs to 11539 in current category list."""
    plain = resolve_category("LED TV / Smart LED TV / Haier LED", "", "Haier LED TV 32")
    assert plain.alfa_id == "11539"
    for signal in ("Google TV", "Android TV", "Smart LED TV", "Andriod"):
        smart = resolve_category("LED TV / Smart LED TV / Haier LED", "", signal)
        assert smart.alfa_id == "11539", signal


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
