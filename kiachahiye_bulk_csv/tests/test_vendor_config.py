"""Unit and integration tests for multi-store vendor configuration and isolation.

All assertions against registered vendors (``KIACHAHIYE``, ``AJMER``, etc.) are
strictly DRY and read expected values dynamically from ``vendor_config.py``, so
editing ``sku_prefix``, ``vendor_name``, ``title_formula``, ``brands``, or
``categories`` in ``vendor_config.py`` never requires touching test files.
"""

from __future__ import annotations

import csv
import dataclasses
from pathlib import Path

import pytest

import audit
import main as pipeline_main
from brands import resolve_brand
from categories import resolve_category, resolve_product_type
from description_builder import (
    DESCRIPTION_TEMPLATES,
    SPEC_TABLE,
    DescriptionTemplate,
    template_for,
)
from sku_handle import SKU_PREFIX, ModelExtraction, build_sku_token
from title_builder import build_title
from vendor_config import (
    AJMER,
    KIACHAHIYE,
    VENDOR_REGISTRY,
    ConfigError,
    PlatformConfig,
    VendorConfig,
    get_vendor,
    validate_vendor_cfg,
)


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

    # Iron & Garment steamer
    for cfg in VENDOR_REGISTRY.values():
        iron = resolve_category(
            "Electronics > Home appliances > Iron & Garment steamer",
            "",
            "",
            vendor_cfg=cfg,
        )
        assert iron.digi_path == cfg.digi.categories.get("irons")
        assert iron.alfa_id == cfg.alfa.categories.get("iron & garment steamer")

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
        assert ac.digi_path == cfg.digi.categories.get("ac inverter")
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
        Path("data/input/Products.csv"),
        Path("data/input/Step 1.csv"),
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
    assert KIACHAHIYE.title_formula == "vip_pipe"
    assert AJMER.title_formula == "standard"

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
def _cell(platform: str, **overrides: object) -> PlatformConfig:
    """One store's platform block, with only the override changed."""
    base = getattr(KIACHAHIYE, platform)
    return dataclasses.replace(base, **overrides)


def _store(**overrides: object) -> VendorConfig:
    return dataclasses.replace(KIACHAHIYE, **overrides)


def test_every_cell_defaults_to_todays_template() -> None:
    """A store that says nothing ships the table the shop uses today."""
    for key, cfg in VENDOR_REGISTRY.items():
        for platform in ("digi", "alfa"):
            cell = getattr(cfg, platform)
            assert cell.description_template == "spec_table", (key, platform)
            assert template_for(cell.description_template) is SPEC_TABLE


def test_a_template_may_be_shared_by_name_across_stores() -> None:
    """Requirement: the same named template on two stores is one object, not a copy."""
    ajmer_alfa = dataclasses.replace(AJMER.alfa, description_template="spec_table")
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


def test_a_digi_template_problem_is_named_as_digi() -> None:
    broken = _store(digi=_cell("digi", description_template="pretty_table"))
    with pytest.raises(ConfigError) as caught:
        validate_vendor_cfg(broken)
    assert "digi.description_template" in str(caught.value)


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
