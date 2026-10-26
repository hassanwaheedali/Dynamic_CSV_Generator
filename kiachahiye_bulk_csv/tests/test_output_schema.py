"""Schema guarantees for the two output files (spec sections 2 and 15)."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from tests.conftest import Pipeline
from writers import (
    ALFA_COLUMN_COUNT,
    ALFA_HEADER,
    ATTR_COLUMNS,
    DIGI_COLUMN_COUNT,
    DIGI_HEADER,
    VENDOR_ALFA,
    VENDOR_DIGI,
)

DIGI_EXPECTED = ["Product ID", "Title", "Description", "Vendor", "Brands", "Product Type", "Category", "Tags", "SEO Title", "SEO Description", "Product Images", "Option1 Name", "Option1 Value", "Option2 Name", "Option2 Value", "Option3 Name", "Option3 Value", "Variant SKU", "Variant Barcode", "Variant Weight", "Variant Weight Unit", "Variant Price", "Variant Compare At Price", "Variant Bin Number", "Variant Quantity", "Handle", "Size Chart", "Collection", "Short Description", "Commission Percentage", "Attribute_Air Conditioner Type", "Attribute_Washing Machine Type", "Attribute_Washing Machine Capacity", "Attribute_Product Type", "Attribute_Display Size", "Attribute_Capacity", "Attribute_Warranty", "Attribute_Air Conditioner Capacity", "Attribute_Refrigerator Type", "Attribute_Microwave Type", "Attribute_INV/NON-INV", "Attribute_Processor", "Attribute_Water Dispenser Type", "Attribute_LED Type", "Attribute_Geyser Type", "Attribute_Geyser Capacity", "Attribute_Watts", "Attribute_Volt", "Attribute_Generation", "Attribute_Fan Type", "Attribute_Battery", "Attribute_Core", "Attribute_Thickness", "Attribute_BNPL", "Attribute_Fragrance Type", "Attribute_Lasting", "Attribute_Sillage / Projection", "Attribute_Season", "Attribute_UPS Inverter Type", "Attribute_Generator Types", "Attribute_Watch Sizes", "Attribute_Watch Display Type", "Attribute_Watch Band", "Attribute_Watch Sensor Feature", "Attribute_SKin Type", "Attribute_Air Cooler Category"]

ALFA_EXPECTED = ["Product ID", "Title", "Description", "Vendor", "Brands", "Product Type", "Category", "Tags", "SEO Title", "SEO Description", "Product Images", "Option1 Name", "Option1 Value", "Option2 Name", "Option2 Value", "Option3 Name", "Option3 Value", "Variant SKU", "Variant Barcode", "Variant Weight", "Variant Weight Unit", "Variant Price", "Variant Compare At Price", "Variant Bin Number", "Variant Quantity", "Handle", "Size Chart", "Collection"]


def test_digi_header_is_exactly_66_columns() -> None:
    assert len(DIGI_HEADER) == 66
    assert DIGI_COLUMN_COUNT == 66
    assert list(DIGI_HEADER) == DIGI_EXPECTED


def test_alfa_header_is_exactly_28_columns() -> None:
    assert len(ALFA_HEADER) == 28
    assert ALFA_COLUMN_COUNT == 28
    assert list(ALFA_HEADER) == ALFA_EXPECTED


def test_alfa_is_the_shared_prefix_of_digi() -> None:
    assert list(ALFA_HEADER) == list(DIGI_HEADER[:28])


def test_alfa_has_no_attributes_and_no_short_description() -> None:
    for column in ALFA_HEADER:
        assert not column.startswith("Attribute_"), column
    assert "Short Description" not in ALFA_HEADER
    assert "Commission Percentage" not in ALFA_HEADER


def test_digi_has_all_36_attribute_columns() -> None:
    assert len(ATTR_COLUMNS) == 36
    assert all(column.startswith("Attribute_") for column in ATTR_COLUMNS)
    assert set(ATTR_COLUMNS).issubset(set(DIGI_HEADER))


def test_neither_header_contains_the_other_platforms_columns() -> None:
    digi_only = set(DIGI_HEADER) - set(ALFA_HEADER)
    alfa_only = set(ALFA_HEADER) - set(DIGI_HEADER)
    assert alfa_only == set()
    for column in digi_only:
        assert column not in ALFA_HEADER
    for column in ALFA_HEADER:
        assert column in DIGI_HEADER or column not in DIGI_HEADER


def test_no_suffixed_column_names_from_the_old_single_file_design() -> None:
    for column in list(DIGI_HEADER) + list(ALFA_HEADER):
        assert not re.search(r"_(Digi|Alfa)$", column), column
        assert "_Digi" not in column and "_Alfa" not in column, column


def test_the_two_vendor_constants_are_different_strings() -> None:
    assert VENDOR_DIGI == "KiaChahiye PVT LTD"
    assert VENDOR_ALFA == "Ajmer Electronics"
    assert VENDOR_DIGI != VENDOR_ALFA


def test_written_files_match_their_headers_and_vendors(pipeline: Pipeline, tmp_path: Path) -> None:
    rows = [
        {
            "Title": "Dawlance 2 Taps Water Dispenser White - (WD-1051 HC)",
            "Description": "Brand: Dawlance\nModel: WD-1051 HC White\nCooling Capacity: 2.5 L/Hour",
            "Sell Price": "36,375",
            "Original Price": "36,475",
            "Categories": "Electronics / Home appliances / Water dispenser",
            "Brand": "Dawlance",
            "Image": "https://example.com/a.jpg",
            "Vendor": "ignored",
        }
    ]
    result = pipeline(rows)

    with result["digi_path"].open("r", encoding="utf-8-sig", newline="") as handle:
        digi_reader = csv.reader(handle)
        digi_header = next(digi_reader)
        digi_body = list(digi_reader)
    with result["alfa_path"].open("r", encoding="utf-8-sig", newline="") as handle:
        alfa_reader = csv.reader(handle)
        alfa_header = next(alfa_reader)
        alfa_body = list(alfa_reader)

    assert digi_header == list(DIGI_HEADER)
    assert alfa_header == list(ALFA_HEADER)
    assert len(digi_body) == 1 and len(alfa_body) == 1
    assert len(digi_body[0]) == 66
    assert len(alfa_body[0]) == 28
    assert digi_body[0][digi_header.index("Vendor")] == VENDOR_DIGI
    assert alfa_body[0][alfa_header.index("Vendor")] == VENDOR_ALFA


def test_every_field_is_quoted_and_html_is_single_line(pipeline: Pipeline) -> None:
    rows = [
        {
            "Title": "Dawlance 32 Inch Kore Google HD LED TV",
            "Description": "The Dawlance Kore is a TV.\n\nHighlights:\n\u2022 Dolby Audio\u2014Great sound.",
            "Sell Price": "47,050",
            "Original Price": "47,150",
            "Categories": "LED TV / Smart LED TV / Dawlance LED",
            "Brand": "Dawlance",
            "Image": "https://example.com/b.jpg",
            "Vendor": "ignored",
        }
    ]
    result = pipeline(rows)
    for text in (result["digi_text"], result["alfa_text"]):
        assert '\n"' in text or text.count('"') > 0
        for line in text.splitlines():
            assert line.startswith('"') and line.endswith('"'), line[:60]
    # No raw newline may survive inside a quoted HTML field.
    assert "<table" in result["digi_text"]
    for line in result["digi_text"].splitlines():
        assert "<table" not in line or line.count("<html") == 0
    assert result["digi_text"].count("<table") == 1
    # Each data row is one physical line.
    assert len(result["digi_text"].strip().splitlines()) == 2
    assert len(result["alfa_text"].strip().splitlines()) == 2
