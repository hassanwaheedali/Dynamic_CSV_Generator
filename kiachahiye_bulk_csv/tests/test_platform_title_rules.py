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

import description_builder
import main as pipeline_main
import title_builder
from models import InputRow, ProductRecord
from qc_report import QCFlagCollector
from sku_handle import ModelExtraction, UniqueRegistry
from vendor_config import KIACHAHIYE, VENDOR_REGISTRY, TitleFormula, resolve_cell
from writers import build_alfa_row, build_digi_row

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
    include_inverter: bool | None,
    include_warranty: bool | None,
    formula: str | TitleFormula | None,
    expected_inverter_word: str = "Inverter",
) -> None:
    """Dynamically assert that title and seo_title conform to the platform's configuration."""
    assert isinstance(include_inverter, bool)
    assert isinstance(include_warranty, bool)
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

    # Even when BOTH platforms disable include_inverter, Attribute_INV/NON-INV still resolves "Inverter"
    base_cfg = next(iter(VENDOR_REGISTRY.values()))
    both_no_inv_cfg = dataclasses.replace(
        base_cfg,
        digi=dataclasses.replace(base_cfg.digi, include_inverter=False),
        alfa=dataclasses.replace(base_cfg.alfa, include_inverter=False),
    )
    res_both_off = pipeline([inverter_deep_freezer_row], vendor_cfg=both_no_inv_cfg)
    assert "Inverter" not in res_both_off["digi"][0]["Title"]
    assert "Inverter" not in res_both_off["alfa"][0]["Title"]
    assert res_both_off["digi"][0].get("Attribute_INV/NON-INV") == "Inverter"


# Captured from the pre-refactor implementation (M1.2 Step 0). These are literal
# output oracles, deliberately independent of the extraction/rendering helpers.
_LONG_SOURCE = (
    "TCL Cinema Experience Exceptional Entertainment Premium Ultra Clear Picture Smart Television "
    "For Every Home With Beautiful Screen And Advanced Features"
)
_TV_TITLE = "TCL 55 Inch LED TV - 55P735 Google"
_TV_SEO = "TCL 55P735 LED TV - 55 Inch Price in Pakistan"
_AC_TITLE = "Haier 1.5 Ton Inverter Air Conditioner - HSU-18CF"
_AC_SEO = "Haier HSU-18CF Air Conditioner - 1.5 Ton Price in Pakistan"
_LONG_SEO = "TCL Cinema Experience Exceptional Entertainment Premium Ultra Clear Price in Pakistan"
_WARRANTY_CASES = [
    ("tv_stated", "TCL 55P735 55 Inch Google LED TV Black",
     "Resolution: 4K UHD\nWarranty: 3 Year Panel Warranty", "LED TV", True,
     _TV_TITLE, _TV_SEO, "3 Year Panel Warranty", "3 Year Panel Warranty"),
    ("tv_missing", "TCL 55P735 55 Inch Google LED TV Black", "Resolution: 4K UHD", "LED TV", True,
     _TV_TITLE, _TV_SEO, "2 Year Panel Warranty", ""),
    ("non_tv", "Haier 1.5 Ton Inverter Air Conditioner HSU-18CF",
     "Capacity: 1.5 Ton\nCooling: Turbo Cool", "Air Conditioner", True,
     _AC_TITLE, _AC_SEO, "10 Year Compressor Warranty", "10 Year Compressor Warranty"),
    ("long_kept", _LONG_SOURCE, "Resolution: 4K UHD\nWarranty: 3 Year Panel Warranty", "LED TV", False,
     _LONG_SOURCE, _LONG_SEO, "3 Year Panel Warranty", "3 Year Panel Warranty"),
]


@pytest.mark.parametrize("fallback", [True, False])
@pytest.mark.parametrize(
    "case,title,description,category,strict,expected_title,expected_seo,warranty_on,warranty_off",
    _WARRANTY_CASES,
    ids=[case[0] for case in _WARRANTY_CASES],
)
def test_warranty_title_and_seo_characterization(
    pipeline: Pipeline, fallback: bool, case: str, title: str, description: str, category: str,
    strict: bool, expected_title: str, expected_seo: str, warranty_on: str, warranty_off: str,
) -> None:
    cell = dataclasses.replace(KIACHAHIYE.digi, title_formula="standard", include_inverter=True)
    cfg = dataclasses.replace(
        KIACHAHIYE, strict_title_rebuild=strict, apply_tv_warranty_table=fallback,
        digi=dataclasses.replace(cell, include_warranty=False),
        alfa=dataclasses.replace(cell, vendor_name="Alfa", include_warranty=True),
    )
    row = {
        "Title": title, "Description": description, "Categories": category,
        "Brand": "TCL" if category == "LED TV" else "Haier",
        "Sell Price": "100", "Original Price": "120", "Image": "",
    }
    output = pipeline([row], vendor_cfg=cfg)
    warranty = warranty_on if fallback else warranty_off
    assert output["digi"][0]["Title"] == expected_title, case
    assert output["alfa"][0]["Title"] == expected_title + (f" - {warranty}" if warranty else ""), case
    assert output["digi"][0]["SEO Title"] == expected_seo, case
    assert output["alfa"][0]["SEO Title"] == expected_seo, case
    assert "Warranty" not in output["digi"][0]["SEO Title"]


def test_vendor_tv_warranty_policy_back_to_back(pipeline: Pipeline) -> None:
    row = {
        "Title": "TCL 55P735 55 Inch Google LED TV Black", "Description": "Resolution: 4K UHD",
        "Categories": "LED TV", "Brand": "TCL", "Sell Price": "100", "Original Price": "120", "Image": "",
    }
    for enabled in (False, True, False):
        cfg = dataclasses.replace(
            KIACHAHIYE, apply_tv_warranty_table=enabled,
            alfa=dataclasses.replace(KIACHAHIYE.alfa, title_formula="standard"),
        )
        output = pipeline([row], vendor_cfg=cfg)
        expected = _TV_TITLE + (" - 2 Year Panel Warranty" if enabled else "")
        assert output["alfa"][0]["Title"] == expected
        assert output["alfa"][0]["SEO Title"] == _TV_SEO


def test_title_formula_registry_is_authoritative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(title_builder.TITLE_FORMULAS, "probe", lambda slots: "Registered formula")
    result = title_builder.build_title(
        "TCL", ModelExtraction("55P735", "title", "medium"), "LED TV", "TCL 55P735 LED TV", "",
        title_formula="probe",
    )
    assert result.title == "Registered formula"
    assert title_builder.TITLE_FORMULAS["ajmer_variant"] is title_builder.TITLE_FORMULAS["brand_first_extended"]


def test_title_slots_and_standalone_cell_render() -> None:
    slots = title_builder.extract_title_slots(
        "TCL", ModelExtraction("55P735", "title", "medium"), "LED TV",
        "TCL 55P735 55 Inch LED TV Black", "Warranty: 3 Year Panel Warranty",
    )
    cell = resolve_cell(KIACHAHIYE, "digi")
    result, seo = title_builder.render_title_and_seo_from_slots(slots, cell)
    assert result.title == "TCL 55 Inch LED TV - 55P735"
    assert seo == _TV_SEO
    assert slots.warranty == "3 Year Panel Warranty"
    assert slots.color == "Black"
    with pytest.raises(dataclasses.FrozenInstanceError):
        slots.color = "White"  # type: ignore[misc]


@pytest.mark.parametrize("vendor_key", list(VENDOR_REGISTRY))
@pytest.mark.parametrize("identical_policies", [False, True])
def test_resolve_row_extracts_once_and_renders_each_cell_once(
    monkeypatch: pytest.MonkeyPatch, vendor_key: str, identical_policies: bool,
) -> None:
    extracted: list[title_builder.TitleSlots] = []
    rendered: list[tuple[title_builder.TitleSlots, str]] = []
    seo_calls: list[str] = []
    real_extract = pipeline_main.extract_title_slots
    real_render = pipeline_main.render_title_and_seo_from_slots
    real_seo = description_builder.build_seo_title

    def extract(*args: Any, **kwargs: Any) -> title_builder.TitleSlots:
        facts = real_extract(*args, **kwargs)
        extracted.append(facts)
        return facts

    def render(facts: title_builder.TitleSlots, cell: Any) -> tuple[title_builder.TitleResult, str]:
        rendered.append((facts, cell.platform))
        return real_render(facts, cell)

    def seo(base: str, feature_tokens: list[str]) -> str:
        seo_calls.append(base)
        return real_seo(base, feature_tokens)

    monkeypatch.setattr(pipeline_main, "extract_title_slots", extract)
    monkeypatch.setattr(pipeline_main, "render_title_and_seo_from_slots", render)
    monkeypatch.setattr(description_builder, "build_seo_title", seo)
    row = InputRow(2, "TCL 55P735 55 Inch LED TV", "Warranty: 3 Year Panel Warranty",
                   "100", "120", "LED TV", "TCL", "", "")
    cfg = VENDOR_REGISTRY[vendor_key]
    if identical_policies:
        cfg = dataclasses.replace(cfg, alfa=dataclasses.replace(cfg.digi, vendor_name=cfg.alfa.vendor_name))
    record = pipeline_main.resolve_row(
        row, QCFlagCollector(), UniqueRegistry(str.upper), UniqueRegistry(str.lower), True, vendor_cfg=cfg,
    )
    assert len(extracted) == 1
    assert [platform for _, platform in rendered] == ["digi", "alfa"]
    assert all(facts is extracted[0] for facts, _ in rendered)
    assert isinstance(extracted[0].usps, tuple)
    assert not {"analysis", "corpus", "apply_tv_warranty_table"} & {
        field.name for field in dataclasses.fields(extracted[0])
    }
    assert len(seo_calls) == 2

    def forbidden_writer_render(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("writers must project resolved Title/SEO fields without extraction or rendering")

    monkeypatch.setattr(title_builder, "_render_title", forbidden_writer_render)
    monkeypatch.setattr(title_builder, "extract_title_slots", forbidden_writer_render)
    build_digi_row(record, cfg)
    build_alfa_row(record, cfg)
    assert len(extracted) == 1 and len(rendered) == 2 and len(seo_calls) == 2
    assert {field.name for field in dataclasses.fields(ProductRecord)} == {
        "row_number", "source", "title", "product_type", "product_type_inferred", "description", "brand", "category",
        "images", "option1_name", "option1_value", "option2_name", "option2_value", "option3_name", "option3_value",
        "sku", "barcode", "bin_number", "handle", "weight", "weight_unit", "variant_price", "variant_compare_at_price",
        "variant_quantity", "attributes", "title_digi", "title_alfa", "seo_title_digi", "seo_title_alfa", "model",
        "model_source", "model_confidence", "warranty_source", "variant_suffix", "handle_deduped", "series_token",
        "subtype_from", "title_strategy", "capacity_token", "color_token", "inverter_token", "dropped_words",
    }


_CELLS = [(key, platform) for key in VENDOR_REGISTRY for platform in ("digi", "alfa")]


@pytest.mark.parametrize("vendor_key,platform", _CELLS)
@pytest.mark.parametrize("field,value", [
    ("title_formula", "vip_pipe"), ("include_inverter", False), ("include_warranty", False),
    ("omit_title_color_categories", frozenset()), ("strict_title_rebuild", False),
])
def test_title_settings_are_isolated_and_never_stale(
    pipeline: Pipeline, vendor_key: str, platform: str, field: str, value: Any,
) -> None:
    if field == "strict_title_rebuild":
        title, description, category, brand = _LONG_SOURCE, "Warranty: 3 Year Panel Warranty", "LED TV", "TCL"
    elif field == "omit_title_color_categories":
        title, description, category, brand = (
            "TCL 55P735 55 Inch LED TV Black", "Warranty: 3 Year Panel Warranty", "LED TV", "TCL",
        )
    else:
        title, description, category, brand = (
            "Dawlance 15 Cu Ft Inverter Deep Freezer White DF-500DD", "Warranty: 12 Year Compressor Warranty",
            "Deep Freezer", "Dawlance",
        )
    row = {"Title": title, "Description": description, "Categories": category, "Brand": brand,
           "Sell Price": "100", "Original Price": "120", "Image": ""}
    configs = {
        key: dataclasses.replace(cfg, **{
            p: dataclasses.replace(
                getattr(cfg, p), title_formula="standard", include_inverter=True, include_warranty=True,
                strict_title_rebuild=True, omit_title_color_categories=frozenset({"LED TV"}),
            ) for p in ("digi", "alfa")
        }) for key, cfg in VENDOR_REGISTRY.items()
    }

    def capture(changed: bool) -> dict[tuple[str, str], tuple[str, str]]:
        results: dict[tuple[str, str], tuple[str, str]] = {}
        for key, original in configs.items():
            cfg = original
            if changed and key == vendor_key:
                cfg = dataclasses.replace(cfg, **{
                    platform: dataclasses.replace(getattr(cfg, platform), **{field: value}),
                })
            output = pipeline([row], vendor_cfg=cfg)
            for p in ("digi", "alfa"):
                results[key, p] = output[p][0]["Title"], output[p][0]["SEO Title"]
        return results

    before, after, restored = capture(False), capture(True), capture(False)
    assert restored == before
    for cell in _CELLS:
        if cell == (vendor_key, platform):
            assert after[cell] != before[cell]
        else:
            assert after[cell] == before[cell]
    changed_title = after[vendor_key, platform][0]
    if field == "include_inverter":
        assert "Inverter" not in changed_title
    elif field == "include_warranty":
        assert "Warranty" not in changed_title
    elif field == "omit_title_color_categories":
        assert "Black" in changed_title
    elif field == "strict_title_rebuild":
        assert changed_title.startswith(_LONG_SOURCE)
    else:
        assert " | " in changed_title


@pytest.mark.parametrize("vendor_key,platform", _CELLS)
@pytest.mark.parametrize("formula", list(title_builder.TITLE_FORMULAS))
def test_registered_formulas_render_independently_for_every_cell(
    pipeline: Pipeline, vendor_key: str, platform: str, formula: str,
) -> None:
    row = {
        "Title": "TCL 55P735 55 Inch LED TV", "Description": "Warranty: 3 Year Panel Warranty",
        "Categories": "LED TV", "Brand": "TCL", "Sell Price": "100", "Original Price": "120", "Image": "",
    }
    cfg = VENDOR_REGISTRY[vendor_key]
    cfg = dataclasses.replace(cfg, **{
        platform: dataclasses.replace(getattr(cfg, platform), title_formula=formula, include_warranty=False),
    })
    actual = pipeline([row], vendor_cfg=cfg)[platform][0]
    expected = {
        "standard": "TCL 55 Inch LED TV - 55P735",
        "brand_first_extended": "TCL 55P735 - 55 Inch LED TV",
        "ajmer_variant": "TCL 55P735 - 55 Inch LED TV",
        "vip_pipe": "TCL 55 Inch LED TV | 55P735",
    }
    if formula in expected:
        assert actual["Title"] == expected[formula]
    assert actual["Title"]
    assert actual["SEO Title"] == _TV_SEO


@pytest.mark.parametrize("usp", ["Voice Control|Dolby Audio", "Voice" + "|Audio" * 28])
def test_vip_source_pipes_preserve_text_and_reserved_warranty(usp: str) -> None:
    result = title_builder.build_title(
        "TCL", ModelExtraction("55P735", "title-code-token", "high"), "LED TV",
        "TCL 55P735 55 Inch LED TV", f"Features: {usp}",
        title_formula="vip_pipe", warranty="2 Year Panel Warranty",
    )
    assert result.title == f"TCL 55 Inch LED TV | 55P735 | {usp} | 2 Year Panel Warranty"
    assert result.usp_tokens == (usp,)

