"""Sections 2, 7 and 9 -- projections, Vendor constants, SKU uniqueness, prices."""

from __future__ import annotations

from typing import Any

import pytest

from models import InputRow
from pricing import DEFAULT_VARIANT_QUANTITY, parse_price, resolve_prices, resolve_quantity
from qc_report import CAT_PRICE_INVERSION, CAT_QTY_DEFAULTED, QCFlagCollector
from sku_handle import (
    UniqueRegistry,
    build_handle_token,
    build_sku_token,
    extract_model,
    extract_variant_tokens,
    format_variant,
    join_base_variant,
)
from tests.conftest import Pipeline
from warranty import lookup_terms
from writers import VENDOR_ALFA, VENDOR_DIGI


def _row(**overrides: str) -> InputRow:
    base: dict[str, Any] = {
        "row_number": 1,
        "title": "Dawlance Freezer (9193-WB)-Meadow Green",
        "description": "",
        "sell_price": "1,000",
        "original_price": "1,100",
        "categories": "Electronics / Home appliances / Deep Freezer",
        "brand": "Dawlance",
        "image": "https://example.com/a.jpg",
        "vendor": "ignored",
    }
    base.update(overrides)
    return InputRow(**base)


# --------------------------------------------------------------------------
# Vendor constants
# --------------------------------------------------------------------------
def test_vendor_constants_are_distinct_and_never_cross_used() -> None:
    assert VENDOR_DIGI == "KiaChahiye PVT LTD"
    assert VENDOR_ALFA == "Kia Chahiye Pvt Ltd"
    assert VENDOR_DIGI != VENDOR_ALFA


def test_input_vendor_column_is_ignored(pipeline: Pipeline) -> None:
    result = pipeline(
        [
            {
                "Title": "Dawlance Deep Freezer (DF-500)",
                "Description": "Brand: Dawlance\nModel: DF-500\nType: Inverter",
                "Sell Price": "1,000",
                "Original Price": "1,100",
                "Categories": "Electronics / Home appliances / Deep Freezer",
                "Brand": "Dawlance",
                "Image": "https://example.com/a.jpg",
                "Vendor": "NOT THE RIGHT VENDOR",
            }
        ]
    )
    assert result["digi"][0]["Vendor"] == VENDOR_DIGI
    assert result["alfa"][0]["Vendor"] == VENDOR_ALFA


# --------------------------------------------------------------------------
# SKU / handle
# --------------------------------------------------------------------------
def test_model_extraction_hierarchy_prefers_the_model_line() -> None:
    extraction = extract_model(
        "Dawlance 2 Taps Water Dispenser White - (WD-1051 HC)",
        "Model: WD-1051 HC White\nCooling Capacity: 2.5 L/Hour",
    )
    assert extraction.code == "WD-1051 HC"
    assert extraction.source == "description-model-line"
    assert extraction.confidence == "high"


def test_colour_is_stripped_from_the_model_but_kept_in_the_title() -> None:
    extraction = extract_model("Dawlance X (DW-100)", "Model: DW-100 White")
    assert extraction.code == "DW-100"
    assert build_sku_token(extraction.code) == "KIA-DW-100"


def test_parenthetical_group_with_no_digit_is_rejected() -> None:
    extraction = extract_model("Haier Air Conditioner Cool Only (Cool Only)", "")
    assert extraction.source != "title-parenthetical"


def test_sku_and_handle_are_built_from_the_compact_model() -> None:
    assert build_sku_token("WD-1051 HC") == "KIA-WD-1051HC"
    assert build_handle_token("WD-1051 HC", "Water Dispenser") == "wd-1051hc-water-dispenser"


def test_handle_is_capped_but_keeps_the_model() -> None:
    handle = build_handle_token("A-VERY-LONG-MODEL-CODE-1234567890", "Air Conditioner")
    assert len(handle) <= 65
    assert handle.startswith("a-very-long-model")


def test_unique_registry_leaves_a_uniquely_modelled_row_untouched() -> None:
    registry = UniqueRegistry()
    registry.register_base("KIA-WD-1051HC")
    value, numeric = registry.assign("KIA-WD-1051HC", "WHITE")
    assert value == "KIA-WD-1051HC"  # no suffix when it is already unique
    assert numeric is False


def test_variant_suffix_disambiguates_real_variants() -> None:
    registry = UniqueRegistry()
    for _ in range(3):
        registry.register_base("KIA-9193-WB")
    first, _ = registry.assign("KIA-9193-WB", "16CUFT-WHITE")
    second, _ = registry.assign("KIA-9193-WB", "16CUFT-MEADOWGREEN")
    third, numeric = registry.assign("KIA-9193-WB", "16CUFT-WHITE")
    assert first == "KIA-9193-WB-16CUFT-WHITE"
    assert second == "KIA-9193-WB-16CUFT-MEADOWGREEN"
    assert third == "KIA-9193-WB-16CUFT-WHITE-2"  # numeric fallback, reported
    assert numeric is True
    assert len({first, second, third}) == 3


def test_variant_tokens_cover_capacity_colour_taps_and_generation() -> None:
    tokens = extract_variant_tokens(
        "Dawlance 3 Taps Water Dispenser White 1.5 Ton T3 Inverter", "1.5 Ton", "Dawlance"
    )
    joined = format_variant(tokens)
    assert joined == "1.5TON-WHITE-3TAPS"
    assert joined == joined.upper()


def test_join_base_variant_collapses_stuttered_numeric_tokens() -> None:
    assert join_base_variant("KIA-DAWLANCE-KORE-32", "32INCH") == "KIA-DAWLANCE-KORE-32-INCH"
    assert join_base_variant("KIA-DAWLANCE-ECONO-1", "1TON-WHITE") == "KIA-DAWLANCE-ECONO-1-TON-WHITE"
    assert join_base_variant("KIA-ORIENT-TWISTER-10", "10KG-SILVER") == "KIA-ORIENT-TWISTER-10-KG-SILVER"
    assert (
        join_base_variant("KIA-DAWLANCE-FREEZERONTOP-12", "12CUFT-BLACK")
        == "KIA-DAWLANCE-FREEZERONTOP-12-CUFT-BLACK"
    )
    assert join_base_variant("KIA-DAWLANCE-ECONO-15", "1.5TON-WHITE") == "KIA-DAWLANCE-ECONO-1.5-TON-WHITE"
    assert join_base_variant("KIA-DAWLANCE-KORE-32", "32") == "KIA-DAWLANCE-KORE-32"
    assert join_base_variant("KIA-DAWLANCE-KORE-32", "32-RED") == "KIA-DAWLANCE-KORE-32-RED"
    assert join_base_variant("KIA-DAWLANCE-KORE-32", "RED") == "KIA-DAWLANCE-KORE-32-RED"
    assert join_base_variant("KIA-DAWLANCE-KORE", "RED") == "KIA-DAWLANCE-KORE-RED"
    assert join_base_variant("", "RED") == "RED"
    assert join_base_variant("KIA-DAWLANCE", "") == "KIA-DAWLANCE"

    registry = UniqueRegistry()
    registry.register_base("KIA-DAWLANCE-KORE-32")
    registry.register_base("KIA-DAWLANCE-KORE-32")
    first, _ = registry.assign("KIA-DAWLANCE-KORE-32", "32INCH")
    second, _ = registry.assign("KIA-DAWLANCE-KORE-32", "32INCH")
    assert first == "KIA-DAWLANCE-KORE-32-INCH"
    assert second == "KIA-DAWLANCE-KORE-32-INCH-2"


# --------------------------------------------------------------------------
# Pricing
# --------------------------------------------------------------------------
def test_prices_strip_commas() -> None:
    assert parse_price("36,375") == 36375
    assert parse_price(" 1,234,567 ") == 1234567
    assert parse_price("") is None


def test_price_inversion_is_flagged_and_never_silently_reordered() -> None:
    flags = QCFlagCollector()
    row = _row(sell_price="36,475", original_price="36,375")
    price, compare_at = resolve_prices(row, flags)
    assert (price, compare_at) == (36475, 36375)
    assert flags.count(CAT_PRICE_INVERSION) == 1


def test_quantity_defaults_to_20_and_is_always_flagged() -> None:
    flags = QCFlagCollector()
    assert resolve_quantity(_row(), flags) == DEFAULT_VARIANT_QUANTITY == 20
    assert flags.count(CAT_QTY_DEFAULTED) == 1


def test_unparseable_price_is_flagged_and_never_invented() -> None:
    flags = QCFlagCollector()
    price, compare_at = resolve_prices(_row(sell_price="ask", original_price="ask"), flags)
    assert price == 0 and compare_at == 0
    assert flags.count("input_error") == 1


# --------------------------------------------------------------------------
# Projection
# --------------------------------------------------------------------------
def test_alfa_projection_excludes_every_digi_only_column(pipeline: Pipeline) -> None:
    result = pipeline(
        [
            {
                "Title": "Dawlance 2 Taps Water Dispenser White - (WD-1051 HC)",
                "Description": "Model: WD-1051 HC White\nCooling Capacity: 2.5 L/Hour\n"
                "Special Feature: Refrigerator Compartment\nVoltage: 220-240V",
                "Sell Price": "36,375",
                "Original Price": "36,475",
                "Categories": "Electronics / Home appliances / Water dispenser",
                "Brand": "Dawlance",
                "Image": "https://example.com/a.jpg",
                "Vendor": "ignored",
            }
        ]
    )
    alfa = result["alfa"][0]
    assert set(alfa) == set(
        {
            "Product ID", "Title", "Description", "Vendor", "Brands", "Product Type",
            "Category", "Tags", "SEO Title", "SEO Description", "Product Images",
            "Option1 Name", "Option1 Value", "Option2 Name", "Option2 Value",
            "Option3 Name", "Option3 Value", "Variant SKU", "Variant Barcode",
            "Variant Weight", "Variant Weight Unit", "Variant Price",
            "Variant Compare At Price", "Variant Bin Number", "Variant Quantity",
            "Handle", "Size Chart", "Collection",
        }
    )
    # The DigiMall-only facts exist in the DigiMall file and nowhere in Alfa.
    digi = result["digi"][0]
    assert digi["Attribute_Water Dispenser Type"] == "With refrigerator"
    assert digi["Short Description"]


def test_categories_are_different_shapes_per_file(pipeline: Pipeline) -> None:
    result = pipeline(
        [
            {
                "Title": "Dawlance Water Dispenser (WD-1051)",
                "Description": "Brand: Dawlance",
                "Sell Price": "1,000",
                "Original Price": "1,100",
                "Categories": "Electronics / Home appliances / Water dispenser",
                "Brand": "Dawlance",
                "Image": "https://example.com/a.jpg",
                "Vendor": "ignored",
            }
        ]
    )
    digi_category = result["digi"][0]["Category"]
    alfa_category = result["alfa"][0]["Category"]
    assert digi_category == "11639_11643_11661_11669"
    assert alfa_category == "11509"
    assert "_" not in alfa_category
    assert digi_category != alfa_category


def test_barcode_and_bin_equal_the_sku(pipeline: Pipeline) -> None:
    result = pipeline([_weight_row()])
    for row in result["digi"] + result["alfa"]:
        assert row["Variant Barcode"] == row["Variant SKU"]
        assert row["Variant Bin Number"] == row["Variant SKU"]


# --------------------------------------------------------------------------
# Warranty terms file (data/warranty/WARRANTY_TERMS.csv)
# --------------------------------------------------------------------------
def test_warranty_split_rows_beat_the_category_default() -> None:
    """A variant line wins over the default for the same brand + category."""
    semi = lookup_terms(
        "dawlance", "Washing Machine", "Dawlance Twin Tub Washing Machine (DW-6550C)"
    )
    plain = lookup_terms(
        "dawlance", "Washing Machine", "Dawlance Spinner Dryer Top Load 6kg (DS-6080)"
    )
    assert semi == [("Motor", "10 Years"), ("Parts", "1 Year")]
    assert plain == [("Motor", "12 Years"), ("PCB", "4 Years"), ("Parts", "1 Year")]


def test_non_inverter_title_never_matches_the_inverter_row() -> None:
    non_inverter = lookup_terms(
        "gree", "Air Conditioner", "Gree Non Inverter Split Air Conditioner 1.5 Ton"
    )
    inverter = lookup_terms(
        "gree", "Air Conditioner", "Gree Inverter Split Air Conditioner 1.5 Ton"
    )
    assert non_inverter is not None and non_inverter[0] == ("Compressor", "3 Years")
    assert inverter is not None and inverter[0] == ("Compressor", "10 Years")


def test_a_brand_that_is_not_in_the_terms_table_gets_no_warranty() -> None:
    assert lookup_terms("not-a-brand", "Refrigerator", "X") is None
    assert lookup_terms("pel", "Speaker", "Pel Speaker") is None


def test_the_client_confirmed_tv_warranties_are_in_place() -> None:
    """Dawlance 2 years on LED TVs, TCL 1 year on sound bars and speakers."""
    assert lookup_terms("dawlance", "LED TV", "Dawlance 32 Inch Kore LED TV") == [
        ("Panel", "2 Years"),
        ("Parts", "2 Years"),
    ]
    assert lookup_terms("tcl", "Sound Bar", "TCL 5.1ch Soundbar (Q65H)") == [
        ("Parts and Labour", "1 Year"),
    ]
    assert lookup_terms("tcl", "Speaker", "TCL Party Speaker (TP200K)") == [
        ("Parts and Labour", "1 Year"),
    ]


# --------------------------------------------------------------------------
# Variant Weight -- the optional Weight column
# --------------------------------------------------------------------------
def _weight_row(**overrides: str) -> dict[str, str]:
    row = {
        "Title": "Dawlance Deep Freezer (DF-500)",
        "Description": "Brand: Dawlance\nModel: DF-500\nType: Inverter",
        "Sell Price": "1,000",
        "Original Price": "1,100",
        "Categories": "Electronics / Home appliances / Deep Freezer",
        "Brand": "Dawlance",
        "Image": "https://example.com/a.jpg",
        "Vendor": "ignored",
    }
    row.update(overrides)
    return row


def test_weight_column_reaches_both_files(pipeline: Pipeline) -> None:
    result = pipeline([_weight_row(Weight="17.25 kg")])
    assert result["digi"][0]["Variant Weight"] == "17.25"
    assert result["digi"][0]["Variant Weight Unit"] == "kg"
    assert result["alfa"][0]["Variant Weight"] == "17.25"
    assert result["alfa"][0]["Variant Weight Unit"] == "kg"


def test_weight_column_units_and_defaults(pipeline: Pipeline) -> None:
    result = pipeline(
        [
            _weight_row(Weight="500 g", Title="Dawlance Grinder (DG-1)"),
            _weight_row(Weight="16", Title="Dawlance Deep Freezer (DF-501)"),
            _weight_row(Weight="approx 12.5 KG", Title="Dawlance Oven (DO-1)"),
        ]
    )
    assert (result["digi"][0]["Variant Weight"], result["digi"][0]["Variant Weight Unit"]) == ("500", "g")
    assert (result["digi"][1]["Variant Weight"], result["digi"][1]["Variant Weight Unit"]) == ("16", "kg")
    assert (result["digi"][2]["Variant Weight"], result["digi"][2]["Variant Weight Unit"]) == ("12.5", "kg")


def test_weight_column_wins_over_the_description(pipeline: Pipeline) -> None:
    result = pipeline(
        [_weight_row(Weight="20 kg", Description="Brand: Dawlance\nWeight: 18 kg")]
    )
    assert result["digi"][0]["Variant Weight"] == "20"


def test_description_weight_still_used_when_there_is_no_column(pipeline: Pipeline) -> None:
    result = pipeline([_weight_row(Description="Brand: Dawlance\n\u2022 Set Weight: 27 kg")])
    assert result["digi"][0]["Variant Weight"] == "27"
    assert result["alfa"][0]["Variant Weight Unit"] == "kg"


def test_unreadable_weight_column_is_flagged_and_left_empty(pipeline: Pipeline) -> None:
    result = pipeline([_weight_row(Weight="N/A")])
    assert result["digi"][0]["Variant Weight"] == ""
    assert result["alfa"][0]["Variant Weight"] == ""
    assert any(
        flag.category == "weight_unreadable" for flag in result["flags"].flags
    )


def test_weight_unit_column_is_honoured(pipeline: Pipeline) -> None:
    result = pipeline([_weight_row(**{"Weight": "500", "Weight Unit": "g"})])
    assert result["digi"][0]["Variant Weight"] == "500"
    assert result["digi"][0]["Variant Weight Unit"] == "g"


def test_shipping_weight_wins_over_net_whichever_order(pipeline: Pipeline) -> None:
    """The client supplies shipping weight, so the packed figure is the one published."""
    result = pipeline(
        [
            _weight_row(
                Title="PEL Water Dispenser (P-1)",
                Brand="PEL",
                Description="Brand: PEL\n\u2022 Net Weight: 17.5 kg\n\u2022 Gross Weight: 19.5 kg",
            ),
            _weight_row(
                Title="PEL Water Dispenser (P-2)",
                Brand="PEL",
                Description="Brand: PEL\n\u2022 Gross Weight: 19.5 kg\n\u2022 Net Weight: 17.5 kg",
            ),
        ]
    )
    assert result["digi"][0]["Variant Weight"] == "19.5"
    assert result["digi"][1]["Variant Weight"] == "19.5"


def test_shipping_weight_is_read_from_the_description(pipeline: Pipeline) -> None:
    result = pipeline(
        [_weight_row(Description="Brand: Dawlance\n\u2022 Shipping Weight: 12 kg")]
    )
    assert result["digi"][0]["Variant Weight"] == "12"
    assert result["alfa"][0]["Variant Weight"] == "12"


def test_shipping_weight_column_beats_a_net_weight_column(pipeline: Pipeline) -> None:
    result = pipeline(
        [_weight_row(**{"Net Weight": "17.5 kg", "Shipping Weight": "19.5 kg"})]
    )
    assert result["digi"][0]["Variant Weight"] == "19.5"


@pytest.mark.parametrize(
    "column",
    ["Weight", "Weight (kg)", "Shipping Weight", "Gross Weight (kg)", "Wt In Kgs", "Item Weight"],
)
def test_weight_column_spellings_are_matched_loosely(pipeline: Pipeline, column: str) -> None:
    """A real sheet has one weight column, so each spelling is exercised on its own."""
    result = pipeline([_weight_row(**{column: "19.5"})])
    assert result["digi"][0]["Variant Weight"] == "19.5"
    assert result["digi"][0]["Variant Weight Unit"] == "kg"


def test_unreadable_stated_weight_falls_through_to_the_next_line(pipeline: Pipeline) -> None:
    result = pipeline(
        [_weight_row(Description="Brand: Dawlance\nWeight: 3 tonnes\nNet Weight: 12 kg")]
    )
    assert result["digi"][0]["Variant Weight"] == "12"


def test_the_counting_pass_does_not_duplicate_qc_flags(pipeline: Pipeline) -> None:
    """Every flag appears exactly once.

    ``main.run`` walks the rows twice (first to count SKU/Handle collisions,
    then to assign them).  Both passes execute the same row code, so the
    counting pass must report into a scratch collector -- otherwise every
    review flag lands in the report twice and a 1800-row run shows 17,049 QC
    lines where only 9,916 are real.
    """
    result = pipeline([_weight_row(), _weight_row(Title="Dawlance Deep Freezer (DF-501)")])
    seen = [
        (flag.row_number, flag.category, flag.message, flag.platform)
        for flag in result["flags"].flags
    ]
    assert len(seen) == len(set(seen)), sorted(seen)
    defaulted = [f for f in result["flags"].flags if f.category == "quantity_defaulted"]
    assert len({f.row_number for f in defaulted}) == len(defaulted) == 2
