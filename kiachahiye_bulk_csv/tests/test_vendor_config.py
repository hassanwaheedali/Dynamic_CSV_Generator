"""Unit and integration tests for multi-store vendor configuration and isolation.

All assertions against registered vendors (``KIACHAHIYE``, ``AJMER``, etc.) are
strictly DRY and read expected values dynamically from ``vendor_config.py``, so
editing ``sku_prefix``, ``vendor_name``, ``title_formula``, ``brands``, or
``categories`` in ``vendor_config.py`` never requires touching test files.
"""

from __future__ import annotations

import copy
import csv
import dataclasses
from pathlib import Path
from typing import Any

import pytest

import audit
import main as pipeline_main
import sku_handle
from brands import BRANDS_ALFA, BRANDS_DIGI, resolve_brand
from categories import (
    CATEGORY_ALFA_IDS,
    CATEGORY_DIGI_PATHS,
    resolve_category,
    resolve_product_type,
)
from description_builder import (
    DESCRIPTION_TEMPLATES,
    SPEC_TABLE,
    DescriptionTemplate,
    SpecRow,
    template_for,
)
from series_corpus import analyze_row
from sku_handle import SKU_PREFIX, ModelExtraction, build_sku_token
from title_builder import build_title
from vendor_config import (
    AJMER,
    KIACHAHIYE,
    PLATFORM_DEFAULTS,
    VENDOR_REGISTRY,
    ConfigError,
    PlatformConfig,
    VendorConfig,
    get_vendor,
    resolve_cell,
    validate_vendor_cfg,
)
from writers import template_for_cell


def test_all_registered_vendors_pass_validation() -> None:
    """Every store registered in VENDOR_REGISTRY is structurally valid."""
    assert len(VENDOR_REGISTRY) >= 2
    for key, cfg in VENDOR_REGISTRY.items():
        assert get_vendor(key) is cfg
        validate_vendor_cfg(cfg)
        assert cfg.digi.vendor_name != cfg.alfa.vendor_name


def test_vendor_registry_dynamic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adding a new store to VENDOR_REGISTRY makes it immediately discoverable."""
    metro = VendorConfig(
        display_name="Metro Store",
        sku_prefix="MT",
        digi=PlatformConfig(
            vendor_name="Metro Digi",
            brands={"haier": 1},
            categories={"refrigerators": "1_2"},
        ),
        alfa=PlatformConfig(
            vendor_name="Metro Alfa",
            brands={"haier": 2},
            categories={"refrigerators": "99"},
        ),
    )
    monkeypatch.setitem(VENDOR_REGISTRY, "metro", metro)
    assert get_vendor("metro") is metro


def test_get_vendor_unknown_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_vendor("nonexistent_store")


def test_resolve_brand_vendor_isolation() -> None:
    """Each store resolves brands strictly from its own VendorConfig dicts."""
    for brand_key in ("orient", "pel", "tcl", "super asia", "haier", "dawlance"):
        for cfg in VENDOR_REGISTRY.values():
            res = resolve_brand(brand_key, vendor_cfg=cfg)
            assert res.digi_id == cfg.digi.brands.get(res.normalized)
            assert res.alfa_id == cfg.alfa.brands.get(res.normalized)


def test_resolve_category_vendor_isolation() -> None:
    """Each store resolves categories strictly from its own VendorConfig dicts."""
    # Deep Freezer
    for cfg in VENDOR_REGISTRY.values():
        df = resolve_category(
            "Electronics > Home appliances > Deep Freezer", "", "", vendor_cfg=cfg
        )
        assert df.digi_path == cfg.digi.categories.get("freezers")
        assert df.alfa_id == cfg.alfa.categories.get("deep freezer")

    # Iron & Garment steamer (un-narrowed umbrella vs narrowed Dry Iron)
    for cfg in VENDOR_REGISTRY.values():
        iron_umbrella = resolve_category(
            "Electronics > Home appliances > Iron & Garment steamer",
            "",
            "",
            vendor_cfg=cfg,
        )
        assert iron_umbrella.digi_path == cfg.digi.categories.get("irons")
        assert iron_umbrella.alfa_id == cfg.alfa.categories.get("iron & garment steamer")

        dry_iron = resolve_category(
            "Electronics > Home appliances > Iron & Garment steamer",
            "Philips Dry Iron HD1172",
            "Philips Dry Iron HD1172",
            vendor_cfg=cfg,
        )
        assert dry_iron.digi_path == (
            cfg.digi.categories.get("dry iron") or cfg.digi.categories.get("irons")
        )
        assert dry_iron.alfa_id == cfg.alfa.categories.get("iron & garment steamer")

    # AC (Inverter)
    for cfg in VENDOR_REGISTRY.values():
        ac = resolve_category(
            "Electronics > Home appliances > AC",
            "Haier 1.5 Ton DC Inverter AC",
            "",
            vendor_cfg=cfg,
        )
        expected_alfa_ac = (
            cfg.alfa.categories.get("air conditioners alfabnpl")
            or cfg.alfa.categories.get("air conditioner")
            or cfg.alfa.categories.get("ac")
        )
        assert ac.alfa_id == expected_alfa_ac
        assert ac.digi_path == (
            cfg.digi.categories.get("ac inverter")
            or cfg.digi.categories.get("inverters")
        )
        assert resolve_product_type(ac, "Haier", vendor_cfg=cfg) == (
            "Air Conditioner",
            False,
        )


def test_alfa_cells_never_leave_the_stores_own_lists() -> None:
    """Every Alfa Category and Brands id the generator can write is one this store's list has.

    Swept over the real sheets, so it covers the breadcrumbs and brand spellings no
    hand-written case would think to try.  A store with no entry for a product ships an
    empty cell plus a reason -- it never borrows another store's id, which is what put
    Ajmer's rows in KiaChahiye's categories and brands.
    """
    sheets = [
        Path(__file__).resolve().parent.parent / "data/input/Products.csv",
        Path(__file__).resolve().parent.parent / "data/input/Step 1.csv",
    ]
    for sheet in sheets:
        if not sheet.exists():  # unit run on a checkout without the shop's sheets
            continue
        rows = list(csv.DictReader(sheet.open(encoding="utf-8-sig", newline="")))
        for cfg in VENDOR_REGISTRY.values():
            own_cats = set(cfg.alfa.categories.values())
            own_brands = {str(b) for b in cfg.alfa.brands.values()}
            for r in rows:
                got = resolve_category(
                    r.get("Categories", ""), r.get("Title", ""), r.get("Description", ""), cfg
                )
                assert got.alfa_id in own_cats | {None}, (sheet, cfg.display_name, r["Title"], got.alfa_id)
                if got.alfa_id is None:
                    assert got.alfa_reason, f"{r['Title']} shipped empty with no reason"
                brand_id = resolve_brand(r.get("Brand", ""), r.get("Title", ""), cfg).alfa_id
                assert brand_id is None or str(brand_id) in own_brands, (
                    sheet, cfg.display_name, r["Title"], brand_id
                )


def test_sku_prefix_dynamic_for_all_vendors() -> None:
    """build_sku_token uses each vendor's configured sku_prefix dynamically."""
    for cfg in VENDOR_REGISTRY.values():
        assert (
            build_sku_token("WD-1051HC", prefix=cfg.sku_prefix)
            == f"{cfg.sku_prefix}-WD-1051HC"
        )


def test_sku_prefix_legacy_default() -> None:
    assert build_sku_token("WD-1051HC") == f"{SKU_PREFIX}-WD-1051HC"


def test_title_formula_strategies() -> None:
    """Both built-in title formula strategies and custom callables work cleanly."""
    for cfg in VENDOR_REGISTRY.values():
        assert resolve_cell(cfg, "digi").title_formula is not None
        assert resolve_cell(cfg, "alfa").title_formula is not None

    extraction = ModelExtraction(code="HWM 120-1708", source="title", confidence="high")
    std_res = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="Washing Machine",
        source_title="Haier 12kg Grey Top Load Washing Machine HWM 120-1708",
        source_description="10 Years Motor Warranty",
        warranty="10 Years Motor Warranty",
        strict_rebuild=True,
        capacity="12 Kg",
        title_formula="standard",
    )
    ext_res = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="Washing Machine",
        source_title="Haier 12kg Grey Top Load Washing Machine HWM 120-1708",
        source_description="10 Years Motor Warranty",
        warranty="10 Years Motor Warranty",
        strict_rebuild=True,
        capacity="12 Kg",
        title_formula="brand_first_extended",
    )
    assert std_res.title != ext_res.title
    assert std_res.title.startswith("Haier 12 Kg")
    assert ext_res.title.startswith("Haier HWM 120-1708 - 12 Kg")


def test_validate_rejects_matching_vendor_names() -> None:
    bad = VendorConfig(
        display_name="Bad",
        sku_prefix="BD",
        digi=PlatformConfig(vendor_name="Same", brands={}, categories={}),
        alfa=PlatformConfig(vendor_name="Same", brands={}, categories={}),
    )
    with pytest.raises(ConfigError):
        validate_vendor_cfg(bad)


def test_end_to_end_cli_and_audit_for_both_vendors(tmp_path: Path) -> None:
    """Every registered vendor passes main + audit and stamps its configured SKU prefix and Vendor name."""
    sheet = tmp_path / "mini.csv"
    with sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(
            [
                "Title",
                "Description",
                "Sell Price",
                "Original Price",
                "Categories",
                "Brand",
                "Image",
            ]
        )
        writer.writerow(
            [
                "Haier 12kg Top Load Washing Machine HWM 120-1708",
                "Haier 12kg Top Load Fully Automatic Washing Machine with 10 Years Motor Warranty. Weight: 42 kg.",
                "75000",
                "82000",
                "Electronics > Home appliances > Washing machine",
                "Haier",
                "https://example.com/hwm120.jpg",
            ]
        )

    for vendor_key, cfg in VENDOR_REGISTRY.items():
        # Run 'both' when digi has categories configured, otherwise 'alfa'
        platform = "both" if cfg.digi.categories else "alfa"
        v_dir = tmp_path / vendor_key
        v_digi = v_dir / "digi.csv"
        v_alfa = v_dir / "alfa.csv"
        v_qc = v_dir / "qc.csv"
        v_sample = v_dir / "sample.csv"

        assert (
            pipeline_main.main(
                [
                    "--input",
                    str(sheet),
                    "--vendor",
                    vendor_key,
                    "--platform",
                    platform,
                    "--digi",
                    str(v_digi),
                    "--alfa",
                    str(v_alfa),
                    "--qc",
                    str(v_qc),
                    "--sample-titles",
                    str(v_sample),
                ]
            )
            == 0
        )
        assert (
            audit.main(
                [
                    "--input",
                    str(sheet),
                    "--vendor",
                    vendor_key,
                    "--platform",
                    platform,
                    "--digi",
                    str(v_digi),
                    "--alfa",
                    str(v_alfa),
                    "--qc",
                    str(v_qc),
                ]
            )
            == 0
        )

        with v_alfa.open(encoding="utf-8-sig", newline="") as f:
            alfa_row = next(csv.DictReader(f))
        assert alfa_row["Variant SKU"].startswith(f"{cfg.sku_prefix}-")
        assert alfa_row["Vendor"] == cfg.alfa.vendor_name

        if platform == "both":
            with v_digi.open(encoding="utf-8-sig", newline="") as f:
                digi_row = next(csv.DictReader(f))
            assert digi_row["Variant SKU"].startswith(f"{cfg.sku_prefix}-")
            assert digi_row["Vendor"] == cfg.digi.vendor_name


def test_adversarial_category_word_boundaries_and_aliases() -> None:
    """Unmapped 'ac' substrings, Microwave Oven vs Oven, Smart LED TV, and Iron & Garment Steamer."""
    # 1. Unmapped breadcrumbs containing 'ac' inside a word must NOT match Air Conditioner
    for unmapped in (
        "Electronics / Home appliances / Vacuums",
        "Electronics / Kitchen appliances / Coffee machine",
        "Electronics / Accessories",
    ):
        cat = resolve_category(unmapped, "", "", vendor_cfg=AJMER)
        assert cat.alfa_id is None, unmapped
        assert "Alfa category key" in cat.alfa_reason

    # 2. Microwave Oven / Microwave Ovens must resolve to the store's 'microwaves' leaf, never 'oven'
    for crumb in (
        "Electronics > Kitchen appliances > Microwave Oven",
        "Electronics > Kitchen appliances > Microwave Ovens",
    ):
        for cfg in VENDOR_REGISTRY.values():
            mw = resolve_category(crumb, "", "", vendor_cfg=cfg)
            assert mw.alfa_id == cfg.alfa.categories.get("microwaves")
            assert mw.digi_path == cfg.digi.categories.get("microwaves")
            assert resolve_product_type(mw, "Dawlance", vendor_cfg=cfg) == (
                "Microwave Oven",
                False,
            )

    # 3. Smart LED TV leaf segment resolves to 'smart led tv' when present in the store's Alfa map
    for cfg in VENDOR_REGISTRY.values():
        smart_leaf = resolve_category(
            "Electronics > Tv & entertainment > Smart LED TV", "", "", vendor_cfg=cfg
        )
        expected_smart = cfg.alfa.categories.get(
            "smart led tv", cfg.alfa.categories.get("led tv")
        )
        assert smart_leaf.alfa_id == expected_smart

        plain_tv = resolve_category(
            "LED TV / Smart LED TV / Haier LED", "", "Haier LED TV 32", vendor_cfg=cfg
        )
        assert plain_tv.alfa_id == cfg.alfa.categories.get("led tv")

    # 4. Dishwashing vs Dishwashing machine
    dw_clean = resolve_category("Cleaners > Dishwashing", "", "", vendor_cfg=AJMER)
    assert dw_clean.alfa_id == AJMER.alfa.categories.get("dishwashing")
    dw_appl = resolve_category(
        "Electronics > Home appliances > Dishwashing machine", "", "", vendor_cfg=AJMER
    )
    assert dw_appl.alfa_id == AJMER.alfa.categories.get("dish washer")


def test_adversarial_brand_display_and_no_title_brand_stutter() -> None:
    """Brand aliases normalize display names and brand_first_extended never stutters brand."""
    assert resolve_brand("pel", vendor_cfg=AJMER).raw == "PEL"
    assert resolve_brand("Pak Electron", vendor_cfg=AJMER).raw == "PEL"
    assert resolve_brand("Superasia", vendor_cfg=KIACHAHIYE).raw == "Super Asia"

    # Model code starting with brand name must not stutter 'Haier Haier' in brand_first_extended
    ext = ModelExtraction("Haier HSU-12HFM", "high", "description")
    res = build_title(
        brand="Haier",
        extraction=ext,
        product_type="Air Conditioner",
        source_title="Haier 1 Ton Inverter Split AC HSU-12HFM",
        source_description="Model: Haier HSU-12HFM. 10 Years Compressor Warranty.",
        capacity="1 Ton",
        title_formula="brand_first_extended",
    )
    assert res.title.startswith("Haier HSU-12HFM - ")
    assert not res.title.startswith("Haier Haier ")


# ---------------------------------------------------------------------------
# Per-(store x platform) Description template
# ---------------------------------------------------------------------------
def _cell(platform: str, **overrides: Any) -> PlatformConfig:
    """One store's platform block, with only the override changed."""
    base = getattr(KIACHAHIYE, platform)
    return dataclasses.replace(base, **overrides)


def _store(**overrides: Any) -> VendorConfig:
    return dataclasses.replace(KIACHAHIYE, **overrides)


def test_every_cell_defaults_to_todays_template() -> None:
    """A store that says nothing ships the table the shop uses today."""
    silent = PlatformConfig("Vendor", {}, {})
    assert silent.description_template is None
    assert resolve_cell(_store(digi=silent), "digi").description_template == "spec_table"
    for key, cfg in VENDOR_REGISTRY.items():
        for platform in ("digi", "alfa"):
            resolved = resolve_cell(cfg, platform)
            assert resolved.description_template in DESCRIPTION_TEMPLATES, (key, platform)
            assert (
                template_for(resolved.description_template)
                is DESCRIPTION_TEMPLATES[resolved.description_template]
            )


def test_a_template_may_be_shared_by_name_across_stores() -> None:
    """Requirement: the same named template on two stores is one object, not a copy."""
    ajmer_alfa = dataclasses.replace(
        AJMER.alfa, description_template="kiachahiye_alfa_card"
    )
    assert ajmer_alfa.description_template is not None
    assert KIACHAHIYE.alfa.description_template is not None
    assert template_for(ajmer_alfa.description_template) is template_for(
        KIACHAHIYE.alfa.description_template
    )
    validate_vendor_cfg(dataclasses.replace(AJMER, alfa=ajmer_alfa))


def test_a_bad_template_name_names_the_cell_that_has_it() -> None:
    broken = _store(alfa=_cell("alfa", description_template="spec_tabl"))
    with pytest.raises(ConfigError) as caught:
        validate_vendor_cfg(broken)
    message = str(caught.value)
    assert "alfa.description_template" in message
    assert "spec_tabl" in message
    assert "spec_table" in message  # names what is actually available


def test_a_digi_template_problem_is_named_as_digi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real conformance failure on the digi cell, reached through its registry name.

    The name has to resolve, or this proves only the unknown-name branch again -- and
    the failure has to come from the harness, because digi is the file the untouched
    gate reads its Description rules from.
    """
    monkeypatch.setitem(DESCRIPTION_TEMPLATES, _LOSSY.name, _LOSSY)
    broken = _store(digi=_cell("digi", description_template=_LOSSY.name))
    with pytest.raises(ConfigError) as caught:
        validate_vendor_cfg(broken)
    message = str(caught.value)
    assert "unknown DescriptionTemplate" not in message, message
    assert "digi.description_template" in message, message
    assert "lossy" in message, message
    assert "extract" in message, message
    assert "alfa.description_template" not in message, message


def test_both_platforms_are_reported_in_one_raise() -> None:
    """One run must show every config hole, not the first one and then silence."""
    broken = _store(
        digi=_cell("digi", description_template="nope_digi"),
        alfa=_cell("alfa", description_template="nope_alfa"),
    )
    with pytest.raises(ConfigError) as caught:
        validate_vendor_cfg(broken)
    message = str(caught.value)
    assert "digi.description_template" in message
    assert "alfa.description_template" in message


def test_a_template_the_gates_cannot_read_fails_at_startup() -> None:
    """A pasted shape is judged before a single row is written."""
    lossy = DescriptionTemplate(
        name="lossy",
        render=SPEC_TABLE.render,
        extract=lambda _text: [],
        starts_with="<table",
        ends_with="</table>",
    )
    broken = _store(alfa=_cell("alfa", description_template=lossy))
    with pytest.raises(ConfigError) as caught:
        validate_vendor_cfg(broken)
    message = str(caught.value)
    assert "lossy" in message
    assert "alfa.description_template" in message


def _crashing_render(rows: list[SpecRow]) -> str:
    """A pasted skeleton that writes fixed positions of the table it is handed.

    Real enough to matter: the shop's own table has more rows than one, and a shape
    built by hand from a live listing often assumes it.
    """
    return SPEC_TABLE.render([rows[0], rows[3], rows[1], rows[2]])


#: A shape whose reader cannot state its own rows.
_LOSSY = DescriptionTemplate(
    name="lossy",
    render=SPEC_TABLE.render,
    extract=lambda _text: [],
    starts_with="<table",
    ends_with="</table>",
)

#: A shape whose writer dies on the rows the harness probes with.
_CRASHING = DescriptionTemplate(
    name="crashing",
    render=_crashing_render,
    extract=SPEC_TABLE.extract,
    starts_with="<table",
    ends_with="</table>",
)

#: A shape whose closing tags cross: every tag count matches the well-formed table and
#: the browser cannot build the row, so the harness refuses it by structure.
_CROSSED = DescriptionTemplate(
    name="crossed",
    render=lambda rows: SPEC_TABLE.render(rows).replace("</td></tr>", "</tr></td>", 1),
    extract=SPEC_TABLE.extract,
    starts_with="<table",
    ends_with="</table>",
)

REFUSALS = [pytest.param(_LOSSY, id="reads-nothing-back"),
            pytest.param(_CRASHING, id="raises-while-rendering"),
            pytest.param(_CROSSED, id="crossed-nesting")]


@pytest.mark.parametrize("template", REFUSALS)
def test_a_refused_template_writes_no_file_and_claims_no_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, template: DescriptionTemplate
) -> None:
    """The startup check is the gate: a refused shape stops the run before it writes.

    ``main`` resolves the vendor before it reads the sheet, so a cell whose template
    the gates cannot follow raises with no CSV, no QC report and no title sample in
    the output folder -- and no line saying a file was written.
    """
    sheet = tmp_path / "Products.csv"
    with sheet.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["Title", "Description", "Sell Price", "Original Price", "Categories",
             "Brand", "Image"]
        )
        writer.writerow(
            ["Haier 12kg Top Load Washing Machine HWM 120-1708",
             "Weight: 42 kg.\nWarranty: 1 Year", "75000", "82000",
             "Electronics > Home appliances > Washing machine", "Haier",
             "https://example.com/hwm120.jpg"]
        )

    broken = _store(alfa=_cell("alfa", description_template=template))
    outputs = [tmp_path / name for name in ("digi.csv", "alfa.csv", "qc.csv", "titles.csv")]
    monkeypatch.setitem(VENDOR_REGISTRY, "kiachahiye", broken)
    with pytest.raises(ConfigError):
        pipeline_main.main(
            ["--input", str(sheet), "--vendor", "kiachahiye", "--platform", "both",
             "--digi", str(outputs[0]), "--alfa", str(outputs[1]),
             "--qc", str(outputs[2]), "--sample-titles", str(outputs[3])]
        )
    assert not any(path.exists() for path in outputs), [p for p in outputs if p.exists()]


def test_a_template_that_crashes_is_named_instead_of_thrown() -> None:
    """A render that dies on the probe rows is a config defect, not a stack trace.

    The harness has to call the shape's own ``render`` to judge it, so a hand-pasted
    skeleton is free to raise -- and the operator's terminal must still show the same
    refusal as every other defect: the store, the exact cell and the template, in one
    ``ConfigError``.
    """
    broken = _store(alfa=_cell("alfa", description_template=_CRASHING))
    with pytest.raises(ConfigError) as caught:
        validate_vendor_cfg(broken)
    message = str(caught.value)
    assert "Kiachahiye.alfa.description_template" in message, message
    assert "crashing" in message, message
    assert "IndexError" in message, message


def test_an_inline_template_object_is_valid_on_its_own() -> None:
    """A cell may hold the template itself, not only a registry name."""
    inline = dataclasses.replace(
        _cell("alfa"), description_template=DESCRIPTION_TEMPLATES["spec_table"]
    )
    validate_vendor_cfg(_store(alfa=inline))


def test_a_description_template_is_not_enough_without_a_vendor_name() -> None:
    """The new knob must not silence the checks that were here before it."""
    broken = _store(alfa=dataclasses.replace(_cell("alfa"), vendor_name=""))
    with pytest.raises(ConfigError) as caught:
        validate_vendor_cfg(broken)
    assert "alfa.vendor_name is empty" in str(caught.value)


# ---------------------------------------------------------------------------
# Phase 0 Stabilization: Dead Knobs, Corpus Isolation, Missing-Mapping Contract, CLI & UI
# ---------------------------------------------------------------------------
def test_omit_title_color_categories_wired_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """vendor_cfg.omit_title_color_categories controls Title color inclusion per store."""
    tv_row = pipeline_main.InputRow(
        row_number=2,
        title="Haier 43 Inch Black Smart LED TV (H43K85FX)",
        description="Haier 43 inch smart LED TV in Black.\n• Model: H43K85FX\n• Color: Black",
        sell_price="85000",
        original_price="90000",
        categories="Electronics / TV & Video / LED TV",
        brand="Haier",
        image="https://example.com/tv.jpg",
        vendor="",
    )
    cfg_omit = dataclasses.replace(
        KIACHAHIYE, omit_title_color_categories=frozenset({"LED TV"})
    )
    cfg_keep = dataclasses.replace(
        KIACHAHIYE,
        omit_title_color_categories=frozenset(),
        digi=dataclasses.replace(KIACHAHIYE.digi, include_color=True),
    )

    flags_omit = pipeline_main.QCFlagCollector()
    rec_omit = pipeline_main.run([tv_row], flags_omit, vendor_cfg=cfg_omit)[0]
    assert "Black" not in rec_omit.title_digi
    assert "Black" not in rec_omit.title_alfa
    assert rec_omit.option1_value == "Black"

    flags_keep = pipeline_main.QCFlagCollector()
    rec_keep = pipeline_main.run([tv_row], flags_keep, vendor_cfg=cfg_keep)[0]
    assert "Black" in rec_keep.title_digi
    assert "Black" in rec_keep.title_alfa
    assert rec_keep.option1_value == "Black"


def test_apply_tv_warranty_table_wired_end_to_end_and_in_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """vendor_cfg.apply_tv_warranty_table controls LED TV fallback warranty in pipeline and audit."""
    sheet = tmp_path / "tv.csv"
    with sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(
            ["Title", "Description", "Sell Price", "Original Price", "Categories", "Brand", "Image"]
        )
        writer.writerow(
            [
                "Dawlance 43 Inch Smart LED TV (43G3A)",
                "The Dawlance 43G3A is a 43 inch smart LED TV with vibrant 4K display and Dolby Audio.",
                "89000",
                "95000",
                "Electronics / TV & Video / LED TV",
                "Dawlance",
                "https://example.com/43g3a.jpg",
            ]
        )

    for apply_flag in (False, True):
        custom_key = f"tv_{str(apply_flag).lower()}"
        custom_cfg = dataclasses.replace(
            KIACHAHIYE, apply_tv_warranty_table=apply_flag
        )
        monkeypatch.setitem(VENDOR_REGISTRY, custom_key, custom_cfg)
        out_dir = tmp_path / custom_key
        digi_p = out_dir / "digi.csv"
        alfa_p = out_dir / "alfa.csv"
        qc_p = out_dir / "qc.csv"
        sample_p = out_dir / "sample.csv"

        assert (
            pipeline_main.main(
                [
                    "--input", str(sheet),
                    "--vendor", custom_key,
                    "--platform", "both",
                    "--digi", str(digi_p),
                    "--alfa", str(alfa_p),
                    "--qc", str(qc_p),
                    "--sample-titles", str(sample_p),
                ]
            )
            == 0
        )
        assert (
            audit.main(
                [
                    "--input", str(sheet),
                    "--vendor", custom_key,
                    "--platform", "both",
                    "--digi", str(digi_p),
                    "--alfa", str(alfa_p),
                    "--qc", str(qc_p),
                ]
            )
            == 0
        )
        with digi_p.open(encoding="utf-8-sig", newline="") as f:
            digi_row = next(csv.DictReader(f))
        with alfa_p.open(encoding="utf-8-sig", newline="") as f:
            alfa_row = next(csv.DictReader(f))
        if apply_flag:
            assert digi_row["Attribute_Warranty"] != ""
            assert "Warranty" in alfa_row["Title"]
        else:
            assert digi_row["Attribute_Warranty"] == ""
            assert "Warranty" not in alfa_row["Title"]


def test_series_corpus_respects_active_vendor_vocabulary_without_cross_store_leakage() -> None:
    """series_corpus claims vendor-specific brand and category words without leaking across vendors."""
    custom_store = dataclasses.replace(
        KIACHAHIYE,
        brand_display_map={**KIACHAHIYE.brand_display_map, "auroracorp": "AuroraCorp", "aurora prime": "Aurora Prime"},
        brand_aliases={**KIACHAHIYE.brand_aliases, "aurora prime": "auroracorp"},
        product_type_map={**KIACHAHIYE.product_type_map, "wine chillers": "Wine Chiller"},
        digi=dataclasses.replace(
            KIACHAHIYE.digi,
            brands={**KIACHAHIYE.digi.brands, "auroracorp": 7777},
            categories={**KIACHAHIYE.digi.categories, "wine chillers": "10_20"},
        ),
    )
    analysis_custom = analyze_row(
        "Aurora Prime Lumina Wine Chillers 50L (AP-50W)",
        brand="aurora prime",
        product_type="Wine Chiller",
        breadcrumb="Appliances / Wine Chillers",
        vendor_cfg=custom_store,
    )
    # Under custom_store, 'aurora' and 'prime' are claimed as brand, 'wine' and 'chillers' as category,
    # leaving only 'lumina' as the series candidate.
    assert analysis_custom.claimed.get("aurora") == "brand"
    assert analysis_custom.claimed.get("prime") == "brand"
    assert analysis_custom.claimed.get("wine") == "category"
    assert analysis_custom.claimed.get("chillers") == "category"
    assert [c.key for c in analysis_custom.candidates] == ["lumina"]

    # Analyzing under AJMER (which does not have 'auroracorp' or 'wine chillers' in its config)
    # must NOT inherit custom_store's vocabulary when given an unrelated row.
    analysis_ajmer = analyze_row(
        "Dawlance Aurora Prime Refrigerator (REF-99)",
        brand="Dawlance",
        product_type="Refrigerator",
        breadcrumb="Appliances / Refrigerators",
        vendor_cfg=AJMER,
    )
    assert "aurora" not in analysis_ajmer.claimed


def test_strict_negative_brand_and_category_isolation_and_missing_mapping_workflow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing mappings never borrow IDs across stores/platforms/globals, leave CSV blank, and keep QC/UI."""
    # 1. Every store x platform cell resolves ONLY its own configured IDs, never another store's or global tables.
    all_brand_keys = set(BRANDS_DIGI) | set(BRANDS_ALFA)
    all_cat_keys = set(CATEGORY_DIGI_PATHS) | set(CATEGORY_ALFA_IDS)
    for cfg in VENDOR_REGISTRY.values():
        all_brand_keys |= set(cfg.digi.brands) | set(cfg.alfa.brands)
        all_cat_keys |= set(cfg.digi.categories) | set(cfg.alfa.categories)

    for vendor_key, cfg in VENDOR_REGISTRY.items():
        for b_key in all_brand_keys:
            res = resolve_brand(b_key, vendor_cfg=cfg)
            if res.normalized not in cfg.digi.brands:
                assert res.digi_id is None, f"{vendor_key}.digi leaked brand ID for {b_key!r}"
            if res.normalized not in cfg.alfa.brands:
                assert res.alfa_id is None, f"{vendor_key}.alfa leaked brand ID for {b_key!r}"

        for c_key in all_cat_keys:
            cat_res = resolve_category(c_key, "", "", vendor_cfg=cfg)
            if cat_res.digi_path is not None:
                assert cat_res.digi_path in set(cfg.digi.categories.values()), (
                    f"{vendor_key}.digi leaked category path {cat_res.digi_path!r} for {c_key!r}"
                )
            if cat_res.alfa_id is not None:
                assert cat_res.alfa_id in set(cfg.alfa.categories.values()), (
                    f"{vendor_key}.alfa leaked category ID {cat_res.alfa_id!r} for {c_key!r}"
                )

    # 2. End-to-end verification of missing mappings (e.g. Ajmer.digi and unmapped brand/category on any vendor):
    # CSV fields stay blank (""), CSV generation succeeds, QC flags and UI summary table are emitted, and audit passes.
    sheet = tmp_path / "unmapped.csv"
    with sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(
            ["Title", "Description", "Sell Price", "Original Price", "Categories", "Brand", "Image"]
        )
        writer.writerow(
            [
                "Gree 1.5 Ton Inverter Split AC (GS-18PITH11W)",
                "Gree 1.5 Ton DC Inverter Split Air Conditioner with 10 Years Compressor Warranty.",
                "145000",
                "155000",
                "Electronics > Home appliances > Air Conditioner",
                "Gree",
                "https://example.com/gree.jpg",
            ]
        )
        writer.writerow(
            [
                "Gree Baking & Flavours Starter Pack (GBF-100)",
                "Gree Baking & Flavours Starter Pack for Home Kitchen.",
                "5000",
                "6000",
                "Electronics > Kitchen > Baking & Flavours",
                "Gree",
                "https://example.com/gree-baking.jpg",
            ]
        )

    # Row 1: Gree is missing from AJMER.digi.brands, while Inverter AC resolves from AJMER.digi's raw taxonomy.
    # Row 2: Baking & Flavours exists in AJMER.alfa ("11856"), but NOT in AJMER.digi (leaves Category blank).
    digi_out = tmp_path / "ajmer_digi.csv"
    alfa_out = tmp_path / "ajmer_alfa.csv"
    qc_out = tmp_path / "ajmer_qc.csv"
    sample_out = tmp_path / "ajmer_sample.csv"

    rc = pipeline_main.main(
        [
            "--input", str(sheet),
            "--vendor", "ajmer",
            "--platform", "both",
            "--digi", str(digi_out),
            "--alfa", str(alfa_out),
            "--qc", str(qc_out),
            "--sample-titles", str(sample_out),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "BRAND NOT FOUND IN LOOKUP TABLE" in captured
    assert "CATEGORY NOT FOUND IN LOOKUP TABLE" in captured

    with digi_out.open(encoding="utf-8-sig", newline="") as f:
        ajmer_digi_rows = list(csv.DictReader(f))
    with alfa_out.open(encoding="utf-8-sig", newline="") as f:
        ajmer_alfa_rows = list(csv.DictReader(f))

    # Row 1: Ajmer.digi and Ajmer.alfa resolve strictly from their own configured maps.
    assert ajmer_digi_rows[0]["Brands"] == str(AJMER.digi.brands.get("gree", ""))
    assert ajmer_digi_rows[0]["Category"] == (
        AJMER.digi.categories.get("ac inverter")
        or AJMER.digi.categories.get("inverters")
        or ""
    )
    expected_alfa_ac = (
        AJMER.alfa.categories.get("air conditioners alfabnpl")
        or AJMER.alfa.categories.get("air conditioner")
        or AJMER.alfa.categories.get("ac")
        or ""
    )
    assert ajmer_alfa_rows[0]["Brands"] == str(AJMER.alfa.brands.get("gree", ""))
    assert ajmer_alfa_rows[0]["Category"] == expected_alfa_ac

    # Row 2: Ajmer.digi leaves Category blank when unmapped (never borrowing from Ajmer.alfa);
    #        Ajmer.alfa resolves its own configured IDs.
    assert ajmer_digi_rows[1]["Brands"] == str(AJMER.digi.brands.get("gree", ""))
    assert ajmer_digi_rows[1]["Category"] == AJMER.digi.categories.get("baking & flavours", "")
    assert ajmer_alfa_rows[1]["Brands"] == str(AJMER.alfa.brands.get("gree", ""))
    assert ajmer_alfa_rows[1]["Category"] == AJMER.alfa.categories.get("baking & flavours", "")

    # QC report records the missing DigiMall mappings and audit passes without blocking upload
    with qc_out.open(encoding="utf-8-sig", newline="") as f:
        qc_flags = {row["Flag Type"] for row in csv.DictReader(f)}
    assert "brand_missing_digi" in qc_flags
    assert "category_missing_digi" in qc_flags

    audit_rc = audit.main(
        [
            "--input", str(sheet),
            "--vendor", "ajmer",
            "--platform", "both",
            "--digi", str(digi_out),
            "--alfa", str(alfa_out),
            "--qc", str(qc_out),
        ]
    )
    assert audit_rc == 0


def test_cli_requires_explicit_vendor_when_argv_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User-facing CLI execution (argv=None) requires explicit --vendor in main.py and audit.py."""
    monkeypatch.setattr("sys.argv", ["main.py"])
    with pytest.raises(SystemExit) as exc_main:
        pipeline_main.main(None)
    assert exc_main.value.code == 2

    monkeypatch.setattr("sys.argv", ["audit.py"])
    with pytest.raises(SystemExit) as exc_audit:
        audit.main(None)
    assert exc_audit.value.code == 2


INHERITABLE_FIELDS = (
    "title_formula", "description_template", "include_inverter", "include_warranty",
    "include_color", "omit_title_color_categories", "strict_title_rebuild",
)


def _silent_vendor() -> VendorConfig:
    return VendorConfig("Silent", "S", PlatformConfig("Digi", {}, {}), PlatformConfig("Alfa", {}, {}))


def test_silent_declarations_and_engine_defaults() -> None:
    cfg = _silent_vendor()
    for name in INHERITABLE_FIELDS:
        assert getattr(cfg, name) is None
        assert getattr(cfg.digi, name) is None
    resolved = resolve_cell(cfg, "digi")
    assert resolved.title_formula == "standard"
    assert resolved.description_template == "spec_table"
    assert resolved.include_inverter is True
    assert resolved.include_warranty is True
    assert resolved.include_color is True
    assert resolved.strict_title_rebuild is True
    assert resolved.omit_title_color_categories == frozenset({"LED TV"})
    assert all(set(defaults) <= set(INHERITABLE_FIELDS) for defaults in PLATFORM_DEFAULTS.values())


@pytest.mark.parametrize("name,platform_value,vendor_value,cell_value", [
    ("title_formula", "vip_pipe", "brand_first_extended", "standard"),
    ("description_template", "kiachahiye_alfa_card", "spec_table", ""),
    ("include_inverter", False, True, False),
    ("include_warranty", False, True, False),
    ("include_color", False, True, False),
    ("strict_title_rebuild", False, True, False),
    ("omit_title_color_categories", frozenset({"Refrigerator"}), frozenset({"LED TV"}), frozenset()),
])
def test_all_four_levels_and_explicit_falsy_values(
    monkeypatch: pytest.MonkeyPatch, name: str, platform_value: Any, vendor_value: Any, cell_value: Any,
) -> None:
    cfg = _silent_vendor()
    monkeypatch.setitem(PLATFORM_DEFAULTS, "digi", {name: platform_value})
    assert getattr(resolve_cell(cfg, "digi"), name) == platform_value
    assert getattr(resolve_cell(cfg, "alfa"), name) == getattr(resolve_cell(None, "alfa"), name)
    cfg = dataclasses.replace(cfg, **{name: vendor_value})
    assert getattr(resolve_cell(cfg, "digi"), name) == vendor_value
    cfg = dataclasses.replace(cfg, digi=dataclasses.replace(cfg.digi, **{name: cell_value}))
    assert getattr(resolve_cell(cfg, "digi"), name) == cell_value
    assert type(getattr(resolve_cell(cfg, "digi"), name)) is type(cell_value)
    assert resolve_cell(dataclasses.replace(cfg), "digi") == resolve_cell(cfg, "digi")
    copy_replace = getattr(copy, "replace", dataclasses.replace)
    assert resolve_cell(copy_replace(cfg), "digi") == resolve_cell(cfg, "digi")
    reset: dict[str, Any] = {name: None}
    cfg = dataclasses.replace(cfg, digi=dataclasses.replace(cfg.digi, **reset))
    assert getattr(resolve_cell(cfg, "digi"), name) == vendor_value
    cfg = dataclasses.replace(cfg, **reset)
    assert getattr(resolve_cell(cfg, "digi"), name) == platform_value


def test_explicit_engine_formula_beats_platform_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(PLATFORM_DEFAULTS, "digi", {"title_formula": "vip_pipe"})
    cfg = dataclasses.replace(_silent_vendor(), title_formula="standard")
    assert resolve_cell(cfg, "digi").title_formula == "standard"
    assert resolve_cell(dataclasses.replace(cfg, title_formula=None), "digi").title_formula == "vip_pipe"


@pytest.mark.parametrize("vendor_key,platform", [
    (key, platform) for key in VENDOR_REGISTRY for platform in ("digi", "alfa")
])
def test_resolved_maps_are_cell_owned_read_only_snapshots(vendor_key: str, platform: str) -> None:
    original = VENDOR_REGISTRY[vendor_key]
    cell = dataclasses.replace(getattr(original, platform), brands={"probe": 123}, categories={"probe": "456"})
    aliases = {"alias": "probe"}
    cfg = dataclasses.replace(original, **{platform: cell}, brand_aliases=aliases)
    resolved = resolve_cell(cfg, platform)
    assert dict(resolved.brands) == {"probe": 123}
    assert dict(resolved.categories) == {"probe": "456"}
    cell.brands["late"] = 789
    cell.categories.clear()
    aliases.clear()
    assert dict(resolved.brands) == {"probe": 123}
    assert dict(resolved.categories) == {"probe": "456"}
    assert dict(resolved.brand_aliases) == {"alias": "probe"}
    with pytest.raises(TypeError):
        resolved.brands["late"] = 789  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        resolved.include_warranty = False  # type: ignore[misc]
    empty = dataclasses.replace(cfg, **{platform: dataclasses.replace(cell, brands={}, categories={})})
    assert dict(resolve_cell(empty, platform).brands) == {}
    assert dict(resolve_cell(empty, platform).categories) == {}
    other = "alfa" if platform == "digi" else "digi"
    assert getattr(empty, other) is getattr(original, other)


@pytest.mark.parametrize("forbidden", ["brands", "categories"])
def test_platform_defaults_cannot_own_marketplace_ids(monkeypatch: pytest.MonkeyPatch, forbidden: str) -> None:
    monkeypatch.setitem(PLATFORM_DEFAULTS, "digi", {forbidden: {"probe": 999}})
    with pytest.raises(ConfigError, match=forbidden):
        resolve_cell(_silent_vendor(), "digi")


def test_legacy_sku_prefix_is_read_at_resolution_time(monkeypatch: pytest.MonkeyPatch, pipeline: Any) -> None:
    monkeypatch.setattr(sku_handle, "SKU_PREFIX", "LEGACY")
    result = pipeline([{
        "Title": "Haier HSU-18CF Air Conditioner", "Description": "Capacity: 1.5 Ton",
        "Brand": "Haier", "Categories": "Air Conditioner", "Sell Price": "100", "Original Price": "120", "Image": "",
    }])
    assert resolve_cell(None, "digi").sku_prefix == "LEGACY"
    assert result["digi"][0]["Variant SKU"].startswith("LEGACY-")


@pytest.mark.parametrize("platform", ["digi", "alfa"])
def test_invalid_resolved_formula_names_the_cell(platform: str) -> None:
    cfg = _silent_vendor()
    cfg = dataclasses.replace(cfg, **{platform: dataclasses.replace(getattr(cfg, platform), title_formula="missing")})
    with pytest.raises(ConfigError, match=rf"Silent\.{platform}\.title_formula"):
        validate_vendor_cfg(cfg)


def test_platform_formula_default_reaches_pipeline(monkeypatch: pytest.MonkeyPatch, pipeline: Any) -> None:
    monkeypatch.setitem(PLATFORM_DEFAULTS, "digi", {"title_formula": "vip_pipe"})
    row = {
        "Title": "TCL 55P735 55 Inch LED TV", "Description": "Warranty: 3 Year Panel Warranty",
        "Categories": "LED TV", "Brand": "TCL", "Sell Price": "100", "Original Price": "120", "Image": "",
    }
    cfg = _silent_vendor()
    output = pipeline([row], vendor_cfg=cfg)
    assert output["digi"][0]["Title"] == "TCL 55 Inch LED TV | 55P735 | 3 Year Panel Warranty"
    assert output["alfa"][0]["Title"] == "TCL 55 Inch LED TV - 55P735 - 3 Year Panel Warranty"
    explicit = pipeline([row], vendor_cfg=dataclasses.replace(cfg, title_formula="standard"))
    assert explicit["digi"][0]["Title"] == "TCL 55 Inch LED TV - 55P735 - 3 Year Panel Warranty"


def test_explicit_zero_quantity_and_empty_vendor_defaults() -> None:
    cfg = dataclasses.replace(_silent_vendor(), default_variant_quantity=0, default_product_type_colors={})
    cell = resolve_cell(cfg, "digi")
    assert cell.default_variant_quantity == 0
    assert dict(cell.default_product_type_colors) == {}


@pytest.mark.parametrize("vendor_key,platform", [
    (key, platform) for key in VENDOR_REGISTRY for platform in ("digi", "alfa")
])
def test_description_inheritance_reaches_validation_and_projection(
    monkeypatch: pytest.MonkeyPatch, vendor_key: str, platform: str,
) -> None:
    original = VENDOR_REGISTRY[vendor_key]
    cfg = dataclasses.replace(original, **{
        platform: dataclasses.replace(getattr(original, platform), description_template=None),
    })
    monkeypatch.setitem(PLATFORM_DEFAULTS, platform, {"description_template": "kiachahiye_alfa_card"})
    assert template_for_cell(cfg, platform) is DESCRIPTION_TEMPLATES["kiachahiye_alfa_card"]
    validate_vendor_cfg(cfg)
    cfg = dataclasses.replace(cfg, description_template="spec_table")
    assert template_for_cell(cfg, platform) is SPEC_TABLE
    validate_vendor_cfg(cfg)
    explicit = dataclasses.replace(cfg, **{
        platform: dataclasses.replace(getattr(cfg, platform), description_template="kiachahiye_alfa_card"),
    })
    assert template_for_cell(explicit, platform) is DESCRIPTION_TEMPLATES["kiachahiye_alfa_card"]
    validate_vendor_cfg(explicit)


def test_explicit_empty_aliases_and_product_type_map_do_not_fallback_via_truthiness() -> None:
    """M1.5a: Explicit empty dicts on vendor or cell must never fall back via truthiness to KCC globals."""
    cfg = dataclasses.replace(
        KIACHAHIYE,
        digi_segment_aliases={},
        alfa_segment_aliases={},
        product_type_map={},
    )
    digi_cell = resolve_cell(cfg, "digi")
    alfa_cell = resolve_cell(cfg, "alfa")
    assert dict(digi_cell.category_segment_aliases) == {}
    assert dict(alfa_cell.category_segment_aliases) == {}
    assert dict(digi_cell.product_type_map) == {}
    assert dict(alfa_cell.product_type_map) == {}
    assert digi_cell.category_id_format == "ancestor_chain"
    assert alfa_cell.category_id_format == "leaf_only"

    # Cell-level empty override also beats non-empty vendor-level map
    cell_empty = dataclasses.replace(
        KIACHAHIYE,
        digi=dataclasses.replace(
            KIACHAHIYE.digi,
            category_segment_aliases={},
            product_type_map={},
        ),
    )
    assert dict(resolve_cell(cell_empty, "digi").category_segment_aliases) == {}
    assert dict(resolve_cell(cell_empty, "digi").product_type_map) == {}
    assert dict(resolve_cell(cell_empty, "alfa").category_segment_aliases) == dict(
        KIACHAHIYE.alfa_segment_aliases
    )


def test_customizing_config_values_dynamically_updates_pipeline_outputs(
    pipeline: Any,
) -> None:
    """Proves maintenance edits (SKU prefix, brand/category IDs, title/description flags) work without code edits."""
    row = {
        "Title": "Gree 1.5 Ton White DC Inverter Split Air Conditioner GS-18PITH11W",
        "Description": "Gree 1.5 Ton DC Inverter Split AC. Color: White. Warranty: 10 Years Compressor Warranty.",
        "Sell Price": "145000",
        "Original Price": "155000",
        "Categories": "Electronics > Home appliances > AC",
        "Brand": "Gree",
        "Image": "https://example.com/gree.jpg",
    }

    customized = dataclasses.replace(
        AJMER,
        sku_prefix="ZZ",
        digi=dataclasses.replace(
            AJMER.digi,
            vendor_name="Custom Digi Store",
            brands={"gree": 7771},
            categories={"ac inverter": "999_888_777"},
            raw_taxonomy_path=None,
            include_inverter=True,
            include_warranty=True,
            include_color=True,
            title_formula="vip_pipe",
        ),
        alfa=dataclasses.replace(
            AJMER.alfa,
            vendor_name="Custom Alfa Store",
            brands={"gree": 8882},
            categories={**AJMER.alfa.categories, "air conditioners alfabnpl": "55555"},
            include_inverter=False,
            include_warranty=False,
            include_color=False,
            title_formula="standard",
        ),
    )

    out = pipeline([row], vendor_cfg=customized)
    digi = out["digi"][0]
    alfa = out["alfa"][0]

    assert digi["Variant SKU"].startswith("ZZ-")
    assert alfa["Variant SKU"].startswith("ZZ-")
    assert digi["Vendor"] == "Custom Digi Store"
    assert alfa["Vendor"] == "Custom Alfa Store"
    assert digi["Brands"] == "7771"
    assert alfa["Brands"] == "8882"
    assert digi["Category"] == "999_888_777"
    assert alfa["Category"] == "55555"
    assert "Inverter" in digi["Title"] and "Warranty" in digi["Title"] and "White" in digi["Title"]
    assert "|" in digi["Title"]
    assert "Inverter" not in alfa["Title"] and "Warranty" not in alfa["Title"] and "White" not in alfa["Title"]
    assert " - " in alfa["Title"]
