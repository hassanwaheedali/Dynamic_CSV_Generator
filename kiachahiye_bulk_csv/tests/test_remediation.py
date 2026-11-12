"""Independent contracts for the pre-Phase-2 adversarial findings."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

import attributes
import main
from attributes import build_attributes
from categories import (
    extract_product_concept,
    load_raw_taxonomy_leaf_map,
    load_raw_taxonomy_nodes,
    resolve_category,
    resolve_product_type,
)
from models import CategoryStatus
from qc_report import CAT_ATTRIBUTE_EMPTY, CAT_SIBLING_AMBIGUOUS, QCFlagCollector
from series_corpus import analyze_row
from tests.conftest import Pipeline
from vendor_config import AJMER, KIACHAHIYE, VENDOR_REGISTRY, ConfigError
from warranty import resolve_warranty


@pytest.mark.parametrize(
    "duration", ["0.5 Years", ".5 Years", "3.5 Years", "1-3 Years", "1.5-3.5 Years", "1 to 3 Years"]
)
def test_warranty_preserves_the_complete_duration(duration: str) -> None:
    rows, headline, source = resolve_warranty(f"Warranty: {duration}", "unknown", "Iron")
    assert source == "stated"
    assert headline == duration
    assert [(r.label, r.value) for r in rows] == [("Warranty", duration)]


def test_every_alias_result_must_belong_to_the_current_allowed_list(monkeypatch: pytest.MonkeyPatch) -> None:
    column = "Attribute_INV/NON-INV"
    monkeypatch.setitem(attributes.ALLOWED, column, [v for v in attributes.ALLOWED[column] if v != "Inverter"])
    values, gaps = build_attributes(
        title="Gree Inverter Air Conditioner",
        description="",
        product_type="Air Conditioner",
        warranty_headline=None,
    )
    assert column not in values
    assert (column, "inverter") in gaps


def test_title_presentation_cannot_change_source_attributes(pipeline: Pipeline) -> None:
    row = {
        "Title": "Philips HD1000 Dry Iron 1000W",
        "Description": "Voltage: 220V",
        "Categories": "Iron",
        "Brand": "Philips",
        "Sell Price": "10000",
        "Original Price": "11000",
    }
    baseline = pipeline([row], KIACHAHIYE)
    changed = pipeline(
        [row],
        replace(
            KIACHAHIYE,
            digi=replace(
                KIACHAHIYE.digi,
                title_formula=lambda slots: "Philips Iron 2000W",
            ),
        ),
    )
    assert baseline["digi"][0]["Title"] != changed["digi"][0]["Title"]
    for result in (baseline, changed):
        assert result["digi"][0]["Attribute_Watts"] == "1000W"
    assert baseline["records"][0].attributes == changed["records"][0].attributes


def test_canonical_identity_is_independent_of_combined_marketplace_ids() -> None:
    text = "Philips Garment Steamer"
    for cfg in (
        AJMER,
        replace(AJMER, digi=replace(AJMER.digi, categories={}), alfa=replace(AJMER.alfa, categories={})),
    ):
        category = resolve_category("Garment Steamers", text, text, cfg)
        assert resolve_product_type(category, "Philips", cfg, title=text) == ("Garment Steamer", False)


@pytest.mark.parametrize(
    ("breadcrumb", "title", "description", "forbidden"),
    [
        ("Air Conditioners", "Gree Air Conditioner", "Inverter: No", "ac_type:inverter"),
        ("LED TV", "Haier LED TV", "Smart TV: No", "tv_type:smart"),
        ("Iron", "Philips Iron", "Steam Function: No", "iron_type:steam"),
        ("LED TV", "Haier LED TV with Smart Remote", "", "tv_type:smart"),
    ],
)
def test_negative_and_secondary_features_do_not_establish_positive_traits(
    breadcrumb: str,
    title: str,
    description: str,
    forbidden: str,
) -> None:
    concept = extract_product_concept(breadcrumb, title, description)
    assert forbidden not in concept.traits


def test_structured_identity_narrows_an_umbrella_without_a_title_noun() -> None:
    concept = extract_product_concept("Iron & Garment Steamer", "Philips HD1000", "Product Type: Garment Steamer")
    assert concept.primary_concepts == ("garment_steamer",)


def test_display_feature_does_not_become_product_identity() -> None:
    assert extract_product_concept("", "LED Display Water Dispenser").canonical_product_type == "Water Dispenser"


def test_taxonomy_declaration_factories_are_independent() -> None:
    first = load_raw_taxonomy_leaf_map("data/digimall_taxonomy.json")
    second = load_raw_taxonomy_leaf_map("data/digimall_taxonomy.json")
    assert first == second and first is not second


@pytest.mark.parametrize("destination", ["11639_11644_11677", "11639_99999", "11639_11643"])
def test_raw_taxonomy_cannot_launder_an_invalid_override(destination: str) -> None:
    cfg = replace(AJMER, digi=replace(AJMER.digi, categories={"refrigerators": destination}))
    result = resolve_category("Refrigerators", "Haier Refrigerator", "Haier Refrigerator", cfg)
    assert result.digi_path is None
    assert result.digi_status != CategoryStatus.MAPPED


def test_duplicate_leaf_names_keep_identity_and_ancestor_traits(tmp_path: Path) -> None:
    path = tmp_path / "tree.json"
    path.write_text(
        json.dumps(
            [
                {"category_id": "1", "category_name": "Air Conditioners", "parent": None},
                {"category_id": "2", "category_name": "Inverters", "parent": "1"},
                {"category_id": "3", "category_name": "Non-Invertors", "parent": "1"},
                {"category_id": "4", "category_name": "Floor Standing", "parent": "2"},
                {"category_id": "5", "category_name": "Floor Standing", "parent": "3"},
            ]
        ),
        encoding="utf-8",
    )
    declarations = load_raw_taxonomy_leaf_map(str(path))
    assert set(declarations.values()) == {"1_2_4", "1_3_5"}
    nodes = {n.category_id: n for n in load_raw_taxonomy_nodes(str(path))}
    assert "ac_type:inverter" in nodes["4"].required_traits
    assert "ac_type:non_inverter" in nodes["5"].required_traits
    cfg = replace(AJMER, digi=replace(AJMER.digi, categories=declarations, raw_taxonomy_path=str(path)))
    for trait, expected in [("Inverter", "1_2_4"), ("Non-Inverter", "1_3_5")]:
        title = f"Gree {trait} Floor Standing Air Conditioner"
        assert resolve_category("Air Conditioners", title, title, cfg).digi_path == expected


def test_equal_dynamic_matches_are_ambiguous_in_every_configuration_order() -> None:
    for items in [(("wine chillers", "1"), ("beer chillers", "2")), (("beer chillers", "2"), ("wine chillers", "1"))]:
        cfg = replace(KIACHAHIYE, digi=replace(KIACHAHIYE.digi, categories=dict(items)))
        result = resolve_category("Chillers", "Chiller", "Chiller", cfg)
        assert result.digi_path is None
        assert result.digi_status == CategoryStatus.SIBLING_AMBIGUOUS


def test_alias_cannot_override_a_contradictory_product_concept() -> None:
    cfg = replace(KIACHAHIYE, digi=replace(KIACHAHIYE.digi, category_segment_aliases={"refrigerators": "microwaves"}))
    result = resolve_category("Refrigerators", "Haier Refrigerator", "Haier Refrigerator", cfg)
    assert result.digi_path == cfg.digi.categories["refrigerators"]


def test_canonical_extraction_is_reused_by_preparation_and_rendering(pipeline: Pipeline) -> None:
    row = {"Title": "Philips HD1000 Dry Iron", "Brand": "Philips", "Categories": "Iron", "Sell Price": "1000"}
    with (
        patch.object(main, "resolve_brand", wraps=main.resolve_brand) as brand,
        patch.object(
            main,
            "resolve_category",
            wraps=main.resolve_category,
        ) as category,
        patch.object(main, "resolve_product_type", wraps=main.resolve_product_type) as product_type,
    ):
        pipeline([row], KIACHAHIYE)
    assert (brand.call_count, category.call_count, product_type.call_count) == (1, 1, 1)


def test_sibling_ambiguity_produces_a_structured_qc_flag(pipeline: Pipeline) -> None:
    result = pipeline(
        [{"Title": "Philips HD1000 Iron", "Brand": "Philips", "Categories": "Iron", "Sell Price": "1000"}], AJMER
    )
    assert any(f.category == CAT_SIBLING_AMBIGUOUS and f.platform == "digi" for f in result["flags"].flags)


def test_qc_gap_summary_keeps_multiword_attribute_names() -> None:
    flags = QCFlagCollector()
    flags.flag(
        2, "Title", CAT_ATTRIBUTE_EMPTY, "Attribute_LED Type: raw signal 'qled' did not exactly match any allowed value"
    )
    assert flags.attribute_gaps()[("Attribute_LED Type", "qled")] == 1


@pytest.mark.parametrize("vendor_key", list(VENDOR_REGISTRY))
def test_positive_category_contracts_for_every_registered_vendor(vendor_key: str) -> None:
    cfg = VENDOR_REGISTRY[vendor_key]
    controlled = replace(
        cfg,
        digi=replace(cfg.digi, categories={"refrigerators": "10_20", "microwaves": "10_21"}, raw_taxonomy_path=None),
        alfa=replace(cfg.alfa, categories={"refrigerators": "30", "microwaves": "31"}, raw_taxonomy_path=None),
    )
    for breadcrumb, title, digi_id, alfa_id in [
        ("Refrigerators", "Haier Refrigerator", "10_20", "30"),
        ("Microwaves", "Haier Microwave Oven", "10_21", "31"),
    ]:
        category = resolve_category(breadcrumb, title, title, controlled)
        assert (category.digi_path, category.alfa_id) == (digi_id, alfa_id)
        assert (category.digi_status, category.alfa_status) == (CategoryStatus.MAPPED, CategoryStatus.MAPPED)


def test_alfa_product_type_override_is_shared_and_conflicts_are_explicit() -> None:
    cfg = replace(KIACHAHIYE, alfa=replace(KIACHAHIYE.alfa, product_type_map={"wine chillers": "Wine Chiller"}))
    category = resolve_category("Wine Chillers", "Wine Chiller", "Wine Chiller", cfg)
    assert resolve_product_type(category, "Acme", cfg) == ("Wine Chiller", False)
    conflicting = replace(cfg, digi=replace(cfg.digi, product_type_map={"wine chillers": "Beer Chiller"}))
    with pytest.raises(ConfigError, match="conflicting"):
        resolve_product_type(category, "Acme", conflicting)


def test_corpus_reads_resolved_cell_aliases_and_type_maps() -> None:
    cfg = replace(
        KIACHAHIYE,
        alfa=replace(
            KIACHAHIYE.alfa,
            category_segment_aliases={"aurora cabinets": "wine chillers"},
            product_type_map={"wine chillers": "Wine Chiller"},
        ),
    )
    reading = analyze_row("Haier Aurora Cabinets Wine Chillers (WC-10)", brand="Haier", vendor_cfg=cfg)
    assert all(reading.claimed.get(word) == "category" for word in ("aurora", "cabinets", "wine", "chillers"))


def test_negative_specification_overrides_a_breadcrumb_trait() -> None:
    concept = extract_product_concept("Air Conditioners > Inverters", "Gree Air Conditioner", "Inverter: No")
    assert "ac_type:non_inverter" in concept.traits
    assert "ac_type:inverter" not in concept.traits


def test_smart_remote_specification_does_not_establish_smart_tv() -> None:
    concept = extract_product_concept("LED TV", "Haier LED TV", "Smart Remote: Yes")
    assert "tv_type:smart" not in concept.traits


def test_direct_raw_alias_cannot_bypass_required_traits() -> None:
    cfg = replace(
        AJMER,
        digi=replace(
            AJMER.digi,
            categories={
                "cooling appliances": "11639_11643_11653_11782_11783",
            },
        ),
    )
    result = resolve_category("Cooling Appliances", "Gree XYZ-100", "Gree XYZ-100", cfg)
    assert result.digi_path is None
    assert result.digi_status == CategoryStatus.SIBLING_AMBIGUOUS


def test_mixed_warranty_terms_preserve_each_components_answer() -> None:
    rows, headline, _source = resolve_warranty("Motor Warranty: 2 Years\nGeneral Warranty: N/A", "unknown", "Iron")
    assert headline == "2 Years"
    assert [(r.label, r.value) for r in rows] == [("Motor Warranty", "2 Years"), ("General Warranty", "N/A")]


@pytest.mark.parametrize("term", ["N/A", "No Warranty", "Not Applicable"])
def test_nonnumeric_warranty_answers_are_not_component_names(term: str) -> None:
    rows, headline, _source = resolve_warranty(f"Warranty: {term}", "unknown", "Iron")
    assert headline is None
    assert [(r.label, r.value) for r in rows] == [("Warranty", term)]


def test_negative_attribute_specification_cannot_emit_the_positive_alias() -> None:
    values, _gaps = build_attributes(
        title="Gree Air Conditioner",
        description="Inverter: No",
        product_type="Air Conditioner",
        warranty_headline=None,
    )
    assert values["Attribute_INV/NON-INV"] == "Non-Inverter"


def test_secondary_remote_does_not_publish_a_smart_display_attribute() -> None:
    values, _gaps = build_attributes(
        title="Haier 55 Inch Television",
        description="Smart Remote: Yes",
        product_type="LED TV",
        warranty_headline=None,
    )
    assert "Attribute_LED Type" not in values


@pytest.mark.parametrize(
    "description", ["Smart TV Support: Not Supported", "Remote: Smart TV Remote Control", "Smart TV: Unknown"]
)
def test_specification_labels_do_not_supply_missing_positive_answers(description: str) -> None:
    assert "tv_type:smart" not in extract_product_concept("LED TV", "Haier LED TV", description).traits
    values, _gaps = build_attributes(
        title="Haier 55 Inch Television",
        description=description,
        product_type="LED TV",
        warranty_headline=None,
    )
    assert values.get("Attribute_LED Type") != "Smart LED TV"


def test_decimal_duration_inside_a_label_survives_other_answering_clauses() -> None:
    rows, headline, _source = resolve_warranty(
        ".5 Years Compressor Warranty: Yes\nMotor Warranty: 2 Years",
        "unknown",
        "Iron",
    )
    assert headline == ".5 Years"
    assert [(r.label, r.value) for r in rows] == [("Compressor Warranty", ".5 Years"), ("Motor Warranty", "2 Years")]


def test_active_combined_leaf_is_not_suppressed_by_an_inactive_atomic_leaf(tmp_path: Path) -> None:
    path = tmp_path / "tree.json"
    path.write_text(
        json.dumps(
            [
                {"category_id": "1", "category_name": "Root", "parent": None},
                {"category_id": "2", "category_name": "Water Dispenser", "parent": "1", "is_active": False},
                {"category_id": "3", "category_name": "Water Dispensers & Purifiers", "parent": "1"},
            ]
        ),
        encoding="utf-8",
    )
    cfg = replace(
        AJMER,
        digi=replace(
            AJMER.digi,
            raw_taxonomy_path=str(path),
            categories=load_raw_taxonomy_leaf_map(str(path)),
        ),
    )
    assert resolve_category("Water Dispenser", "Haier Water Dispenser", "Haier Water Dispenser", cfg).digi_path == "1_3"


def test_source_qled_evidence_outranks_a_4k_resolution_token() -> None:
    values, _gaps = build_attributes(
        title="TCL 55 Inch QLED 4K TV",
        description="",
        product_type="LED TV",
        warranty_headline=None,
    )
    assert values["Attribute_LED Type"] == "QLED"


def test_presentation_cannot_repair_an_unlisted_source_capacity_spelling(pipeline: Pipeline) -> None:
    result = pipeline(
        [
            {
                "Title": "Haier HRF-100 Refrigerator 16 Cu.Ft",
                "Categories": "Refrigerators",
                "Brand": "Haier",
                "Sell Price": "1000",
            }
        ],
        KIACHAHIYE,
    )
    assert result["digi"][0]["Attribute_Capacity"] == ""
    assert any(f.category == CAT_ATTRIBUTE_EMPTY and "Attribute_Capacity:" in f.message for f in result["flags"].flags)


def test_html_source_specifications_retain_their_label_value_boundary(pipeline: Pipeline) -> None:
    steamer = pipeline(
        [
            {
                "Title": "Philips HD1000",
                "Categories": "Iron & Garment Steamer",
                "Brand": "Philips",
                "Sell Price": "1000",
                "Description": "<table><tr><td>Product Type</td><td>Garment Steamer</td></tr></table>",
            }
        ],
        AJMER,
    )
    assert steamer["records"][0].product_type == "Garment Steamer"
    ac = pipeline(
        [
            {
                "Title": "Gree Air Conditioner GS-100",
                "Categories": "Air Conditioners",
                "Brand": "Gree",
                "Sell Price": "1000",
                "Description": (
                    "<table><tr><td>Inverter</td><td>No</td></tr>"
                    "<tr><td>Warranty</td><td>.5 Years</td></tr></table>"
                ),
            }
        ],
        AJMER,
    )
    assert ac["records"][0].attributes["Attribute_INV/NON-INV"] == "Non-Inverter"
    assert ".5 Years" in ac["records"][0].description.warranty_rows[0].value
