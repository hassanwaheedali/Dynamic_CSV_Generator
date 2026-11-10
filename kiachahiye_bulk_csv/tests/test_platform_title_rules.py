"""Dynamic test suite for platform-driven Title and SEO Title generation rules.

Fully dynamic and config-driven:
- Iterates over all registered vendors dynamically from `VENDOR_REGISTRY`.
- Directly inspects each platform's `PlatformConfig` (`include_inverter`, `include_warranty`, `title_formula`).
- Tests custom dynamic configurations (e.g. flipping inverter or warranty on/off) without hardcoding expectations.
- Ensures cross-platform isolation and technical attributes (Attribute_INV/NON-INV) are preserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

import pytest

from vendor_config import VENDOR_REGISTRY, TitleFormula

Pipeline = Callable[..., dict[str, Any]]


@pytest.fixture()
def inverter_deep_freezer_row() -> dict[str, str]:
    return {
        "Title": (
            "Dawlance 15 Cu Ft Hybrid Inverter Double Door Deep Freezer (White) "
            "- DF-500DD - 12 Year Compressor Warranty"
        ),
        "Description": "5-Way Cooling. Energy Saving. Refrigerator and Freezer. 12 Year Compressor Warranty.",
        "Sell Price": "95,000",
        "Original Price": "105,000",
        "Categories": "Electronics / Home appliances / Deep Freezer",
        "Brand": "Dawlance",
        "Image": "https://example.com/df500dd.jpg",
    }


@pytest.fixture()
def non_inverter_ac_row() -> dict[str, str]:
    return {
        "Title": (
            "Haier 1.5 Ton Turbo Cool Non-Inverter Wall Mounted Split Air Conditioner "
            "- HSU-18CF - 05 Year Compressor Warranty"
        ),
        "Description": "Wall Mounted Split AC. 1.5 Ton capacity. High efficiency cooling. 05 Year Compressor Warranty.",
        "Sell Price": "120,000",
        "Original Price": "130,000",
        "Categories": "Electronics / Home appliances / Air Conditioner",
        "Brand": "Haier",
        "Image": "https://example.com/hsu18cf.jpg",
    }


def _assert_platform_title_compliance(
    title: str,
    seo_title: str,
    include_inverter: bool,
    include_warranty: bool,
    formula: str | TitleFormula | None,
    expected_inverter_word: str = "Inverter",
) -> None:
    """Dynamically assert that title and seo_title conform to the platform's configuration."""
    if not include_inverter:
        assert expected_inverter_word not in title, f"{expected_inverter_word!r} found in title: {title}"
        assert expected_inverter_word not in seo_title, f"{expected_inverter_word!r} found in seo_title: {seo_title}"
    else:
        assert expected_inverter_word in title, f"{expected_inverter_word!r} expected in title: {title}"

    if not include_warranty:
        assert "Warranty" not in title, f"'Warranty' found in title: {title}"
        assert "Warranty" not in seo_title, f"'Warranty' found in seo_title: {seo_title}"
    else:
        assert "Warranty" in title, f"'Warranty' expected in title: {title}"

    if formula == "standard":
        assert "|" not in title, f"Pipes found in standard formula title: {title}"
        assert " - " in title, f"Dashes expected in standard formula title: {title}"


@pytest.mark.parametrize("vendor_key", list(VENDOR_REGISTRY.keys()))
def test_all_registered_vendors_dynamically_adhere_to_platform_config(
    pipeline: Pipeline,
    inverter_deep_freezer_row: dict[str, str],
    vendor_key: str,
) -> None:
    """Dynamic test: inspects whatever each vendor's PlatformConfig defines and validates adherence."""
    vendor_cfg = VENDOR_REGISTRY[vendor_key]
    result = pipeline([inverter_deep_freezer_row], vendor_cfg=vendor_cfg)

    digi_row = result["digi"][0]
    alfa_row = result["alfa"][0]

    # Validate DigiMall platform dynamically against vendor_cfg.digi
    _assert_platform_title_compliance(
        title=digi_row["Title"],
        seo_title=digi_row["SEO Title"],
        include_inverter=vendor_cfg.digi.include_inverter,
        include_warranty=vendor_cfg.digi.include_warranty,
        formula=vendor_cfg.digi.title_formula or vendor_cfg.title_formula,
        expected_inverter_word="Inverter",
    )

    # Validate Alfa platform dynamically against vendor_cfg.alfa
    _assert_platform_title_compliance(
        title=alfa_row["Title"],
        seo_title=alfa_row["SEO Title"],
        include_inverter=vendor_cfg.alfa.include_inverter,
        include_warranty=vendor_cfg.alfa.include_warranty,
        formula=vendor_cfg.alfa.title_formula or vendor_cfg.title_formula,
        expected_inverter_word="Inverter",
    )


@pytest.mark.parametrize("vendor_key", list(VENDOR_REGISTRY.keys()))
def test_non_inverter_exclusion_dynamic(
    pipeline: Pipeline,
    non_inverter_ac_row: dict[str, str],
    vendor_key: str,
) -> None:
    """Dynamic test for Non-Inverter products across all registered vendors."""
    vendor_cfg = VENDOR_REGISTRY[vendor_key]
    result = pipeline([non_inverter_ac_row], vendor_cfg=vendor_cfg)

    digi_row = result["digi"][0]
    alfa_row = result["alfa"][0]

    _assert_platform_title_compliance(
        title=digi_row["Title"],
        seo_title=digi_row["SEO Title"],
        include_inverter=vendor_cfg.digi.include_inverter,
        include_warranty=vendor_cfg.digi.include_warranty,
        formula=vendor_cfg.digi.title_formula or vendor_cfg.title_formula,
        expected_inverter_word="Non-Inverter",
    )

    _assert_platform_title_compliance(
        title=alfa_row["Title"],
        seo_title=alfa_row["SEO Title"],
        include_inverter=vendor_cfg.alfa.include_inverter,
        include_warranty=vendor_cfg.alfa.include_warranty,
        formula=vendor_cfg.alfa.title_formula or vendor_cfg.title_formula,
        expected_inverter_word="Non-Inverter",
    )


def test_dynamic_configuration_reversibility(
    pipeline: Pipeline, inverter_deep_freezer_row: dict[str, str]
) -> None:
    """Proves the solution is fully dynamic: flipping config flags on the fly changes outputs accordingly.

    If in the future someone enables warranty on DigiMall or disables inverter on Alfa,
    the pipeline adapts dynamically without code changes.
    """
    base_cfg = VENDOR_REGISTRY["kiachahiye"]

    # Dynamically reconfigure: Digi includes inverter & warranty; Alfa excludes them
    reconfigured_digi = dataclasses.replace(
        base_cfg.digi,
        include_inverter=True,
        include_warranty=True,
    )
    reconfigured_alfa = dataclasses.replace(
        base_cfg.alfa,
        include_inverter=False,
        include_warranty=False,
    )
    dynamic_cfg = dataclasses.replace(
        base_cfg,
        digi=reconfigured_digi,
        alfa=reconfigured_alfa,
    )

    result = pipeline([inverter_deep_freezer_row], vendor_cfg=dynamic_cfg)
    digi_row = result["digi"][0]
    alfa_row = result["alfa"][0]

    # DigiMall dynamically now HAS inverter & warranty because config enabled them:
    _assert_platform_title_compliance(
        title=digi_row["Title"],
        seo_title=digi_row["SEO Title"],
        include_inverter=True,
        include_warranty=True,
        formula=reconfigured_digi.title_formula or dynamic_cfg.title_formula,
    )

    # Alfa dynamically now EXCLUDES inverter & warranty because config disabled them:
    _assert_platform_title_compliance(
        title=alfa_row["Title"],
        seo_title=alfa_row["SEO Title"],
        include_inverter=False,
        include_warranty=False,
        formula=reconfigured_alfa.title_formula or dynamic_cfg.title_formula,
    )


def test_digimall_titles_match_across_vendors_with_same_platform_config(
    pipeline: Pipeline, inverter_deep_freezer_row: dict[str, str]
) -> None:
    """When multiple vendors share platform configs, their generated DigiMall titles are identical."""
    vendors = list(VENDOR_REGISTRY.values())
    if len(vendors) < 2:
        pytest.skip("Requires at least two registered vendors")

    v1, v2 = vendors[0], vendors[1]
    res1 = pipeline([inverter_deep_freezer_row], vendor_cfg=v1)
    res2 = pipeline([inverter_deep_freezer_row], vendor_cfg=v2)

    # Both vendors have identical digi platform settings:
    assert v1.digi.include_inverter == v2.digi.include_inverter
    assert v1.digi.include_warranty == v2.digi.include_warranty
    assert (v1.digi.title_formula or v1.title_formula) == (v2.digi.title_formula or v2.title_formula)

    # Generated titles match identically
    assert res1["digi"][0]["Title"] == res2["digi"][0]["Title"]
    assert res1["digi"][0]["SEO Title"] == res2["digi"][0]["SEO Title"]


def test_digimall_technical_attributes_unaffected_by_title_exclusion(
    pipeline: Pipeline, inverter_deep_freezer_row: dict[str, str]
) -> None:
    """Verifies that excluding Inverter from the display title does NOT break Attribute_* matching."""
    for vendor_cfg in VENDOR_REGISTRY.values():
        res = pipeline([inverter_deep_freezer_row], vendor_cfg=vendor_cfg)
        digi_row = res["digi"][0]
        # Title must omit inverter, but attribute column must retain 'Inverter'
        assert "Inverter" not in digi_row["Title"]
        assert digi_row.get("Attribute_INV/NON-INV") == "Inverter"
