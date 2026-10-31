"""Section 14 -- the two golden acceptance tests.

Both the DigiMall row AND the Alfa row are checked for each case, and both are
produced by running the real pipeline over the given inputs and reading the two
CSVs back, so parsing, projection and file writing are all exercised.
"""

from __future__ import annotations

import csv
import re

from tests.conftest import Pipeline

TC1_IMAGE = (
    "https://cdn.comverseglobal.com/alfa/products/product_images/"
    "17909706870484183_031026005127254336.jpg"
)
TC2_IMAGE = (
    "https://cdn.comverseglobal.com/alfa/products/product_images/"
    "179097068362529_031026005123829471.jpg"
)

TC1_DESCRIPTION = (
    "The Dawlance WD-1051 HC WHITE is a water dispenser with 2 taps, in white. "
    "Brand: Dawlance\n"
    "Model: WD-1051 HC White\n"
    "Cooling Capacity: 2.5 L/Hour\n"
    "Heating Capacity: 5 L/Hour\n"
    "Cold Water Tank: 3.5 Liters\n"
    "Hot Water Tank: 1.6 Liters\n"
    "Cold Temperature: 7-10\u00b0C\n"
    "Hot Temperature: 85-95\u00b0C\n"
    "Control System: Mechanical\n"
    "Special Feature: Refrigerator Compartment\n"
    "Voltage: 220-240V / 50Hz\n"
    "Dimensions (WxDxH): 34.5 x 35.5 x 107.6 cm\n"
    "Weight: 17.25 kg\n"
    "Color: HC White\n"
    "Warranty: 3 Years Compressor, 1 Year General Warranty"
)

TC2_DESCRIPTION = (
    "The Dawlance Kore QLED HD Google TV 32 is a 32-inch LED TV running Google TV. "
    "Key features include Dolby Audio, Wide Color Gamut, QLED TV, Google TV 1.\n\n"
    "Highlights:\n"
    "\u2022 Dolby Audio\u2014Dolby Audio delivers clearer dialogue, balanced sound, "
    "and enhanced detail for a richer everyday listening experience.\n"
    "\u2022 Wide Color Gamut \u2014 Wide Color Gamut delivers a broader, more vibrant "
    "range of colors and amplifies the impact of HDR.\n"
    "\u2022 QLED TV \u2014 Experience stunning clarity with QLED.\n"
    "\u2022 Google TV 1\u2014What you want to watch, in one place.\n"
    "\u2022 Turbo Sound \u2014 An audio system with a wide range of applications."
)

TC1_ROW = {
    "Title": "Dawlance 2 Taps Water Dispenser White - (WD-1051 HC)",
    "Description": TC1_DESCRIPTION,
    "Sell Price": "36,375",
    "Original Price": "36,475",
    "Categories": "Electronics / Home appliances / Water dispenser",
    "Brand": "Dawlance",
    "Image": TC1_IMAGE,
    "Vendor": "Kia Chahiye Pvt Ltd",
}

TC2_ROW = {
    "Title": "Dawlance 32 Inch Kore Google HD LED TV",
    "Description": TC2_DESCRIPTION,
    "Sell Price": "47,050",
    "Original Price": "47,150",
    "Categories": "LED TV / Smart LED TV / Dawlance LED",
    "Brand": "Dawlance",
    "Image": TC2_IMAGE,
    "Vendor": "Kia Chahiye Pvt Ltd",
}


# ===========================================================================
# Test Case 1 -- Dawlance Water Dispenser (clean Label:Value description)
# ===========================================================================
def test_tc1_shared_fields(pipeline: Pipeline) -> None:
    result = pipeline([TC1_ROW])
    digi, alfa = result["digi"][0], result["alfa"][0]

    for row, label in ((digi, "digi"), (alfa, "alfa")):
        assert row["Title"] == "Dawlance 2 Taps White Water Dispenser - WD-1051 HC - 3 Year Compressor Warranty", label
        assert row["Product Type"] == "Water Dispenser", label
        assert row["Product Images"] == TC1_IMAGE, label
        assert row["Option1 Name"] == "Color", label
        assert row["Option1 Value"] == "White", label  # stripped from "HC White"
        assert row["Variant SKU"] == "KIA-WD-1051HC", label
        assert row["Variant Barcode"] == "KIA-WD-1051HC", label
        assert row["Variant Bin Number"] == "KIA-WD-1051HC", label
        assert row["Variant Weight"] == "17.25", label
        assert row["Variant Weight Unit"] == "kg", label
        assert row["Variant Price"] == "36375", label
        assert row["Variant Compare At Price"] == "36475", label
        assert row["Variant Quantity"] == "20", label
        assert row["Handle"] == "wd-1051hc-water-dispenser", label
        assert row["Product ID"] == "", label
        assert row["Size Chart"] == "", label
        assert row["Collection"] == "", label


def test_tc1_digi_row(pipeline: Pipeline) -> None:
    digi = pipeline([TC1_ROW])["digi"][0]
    assert digi["Vendor"] == "KiaChahiye PVT LTD"
    assert digi["Brands"] == "3755"
    assert digi["Category"] == "11639_11643_11661_11669"
    assert digi["Short Description"].startswith("<ul>")
    assert digi["Short Description"].count("<li>") == 3
    assert digi["Attribute_Water Dispenser Type"] == "With refrigerator"
    assert digi["Attribute_Warranty"] == "3 Years"
    assert digi["Attribute_Volt"] == ""  # a range is never rounded to one value
    assert digi["Commission Percentage"] == ""


def test_tc1_alfa_row(pipeline: Pipeline) -> None:
    alfa = pipeline([TC1_ROW])["alfa"][0]
    assert alfa["Vendor"] == "Ajmer Electronics"
    assert alfa["Brands"] == "3673"
    assert alfa["Category"] == "11509"  # bare leaf id, never a joined path
    # Alfa carries none of the DigiMall-only fields.
    assert "Short Description" not in alfa
    assert not any(key.startswith("Attribute_") for key in alfa)


def test_tc1_description_rows(pipeline: Pipeline) -> None:
    digi = pipeline([TC1_ROW])["digi"][0]
    html = digi["Description"]
    assert html.startswith("<table style=")
    assert "\n" not in html and "\r" not in html
    labels = re.findall(r'<tr><td style="[^"]*">(?:<strong>)?([^<]+)', html)
    for expected in (
        "Brand", "Model", "Cooling Capacity", "Heating Capacity", "Cold Water Tank",
        "Hot Water Tank", "Cold Temperature", "Hot Temperature", "Control System",
        "Special Feature", "Voltage", "Dimensions (WxDxH)",
    ):
        assert expected in labels, expected
    # The two warranty rows are last and bolded.
    assert html.endswith("</tr></tbody></table>")
    assert "<strong>3 Years</strong>" in html
    assert "<strong>1 Year</strong>" in html
    assert labels[-2:] == ["Compressor Warranty", "General Warranty"]


def test_tc1_no_capacity_slot_in_title(pipeline: Pipeline) -> None:
    """'Weight: 17.25 kg' must not be mistaken for a capacity token."""
    assert "17.25" not in pipeline([TC1_ROW])["digi"][0]["Title"]


# ===========================================================================
# Test Case 2 -- Dawlance LED TV (Highlights bullets, no model code)
# ===========================================================================
def test_tc2_shared_fields(pipeline: Pipeline) -> None:
    result = pipeline([TC2_ROW])
    for row in (result["digi"][0], result["alfa"][0]):
        assert row["Title"] == "Dawlance 32 Inch LED TV - Kore Google - 2 Year Panel Warranty"
        assert row["Product Type"] == "LED TV"
        assert row["Option1 Name"] == "Color"
        assert row["Option1 Value"] == "Black"
        assert row["Variant SKU"] == "KIA-DAWLANCE-KORE-32"
        assert row["Variant Barcode"] == "KIA-DAWLANCE-KORE-32"
        assert row["Variant Bin Number"] == "KIA-DAWLANCE-KORE-32"
        assert row["Handle"] == "dawlance-kore-32-led-tv"
        assert row["Variant Price"] == "47050"
        assert row["Variant Compare At Price"] == "47150"
        assert row["Product Images"] == TC2_IMAGE


def test_tc2_fallback_sku_is_flagged(pipeline: Pipeline) -> None:
    result = pipeline([TC2_ROW])
    messages = [flag.message for flag in result["flags"].flags]
    assert any("No formal model code found" in message for message in messages)


def test_tc2_digi_row(pipeline: Pipeline) -> None:
    digi = pipeline([TC2_ROW])["digi"][0]
    assert digi["Vendor"] == "KiaChahiye PVT LTD"
    assert digi["Brands"] == "3755"
    # DigiMall's tree has no LED TV leaf at all -- empty, not forced elsewhere.
    assert digi["Category"] == ""
    # Title-over-body tie-break: "Google" is in the Title, "QLED" only in the body.
    assert digi["Attribute_LED Type"] == "Google TV"


def test_tc2_warranty_row(pipeline: Pipeline) -> None:
    """The TV states no warranty, so the brand's own TV terms apply.

    Changed from the original spec's "no warranty row for a TV": the client
    confirmed Dawlance gives a 2-year brand warranty on its LED TVs, so the
    warranty rows are expected here now.  See APPLY_TV_WARRANTY_TABLE in
    config.py to revert the behaviour.
    """
    digi = pipeline([TC2_ROW])["digi"][0]
    html = digi["Description"]
    assert digi["Attribute_Warranty"] == "2 Years"
    bold_cells = re.findall(r"<td[^>]*><strong>([^<]+)</strong></td>", html)
    assert list(zip(bold_cells[0::2], bold_cells[1::2], strict=True)) == [
        ("Panel", "2 Years"),
        ("Parts", "2 Years"),
    ]


def test_tc2_description_shape(pipeline: Pipeline) -> None:
    html = pipeline([TC2_ROW])["digi"][0]["Description"]
    labels = re.findall(r'<tr><td style="[^"]*">(?:<strong>)?([^<]+)', html)
    # the two warranty rows are last and bolded, per section 8
    assert labels == ["Brand", "Type", "Key Features", "Panel", "Parts"]
    for phrase in ("Dolby Audio", "Wide Color Gamut", "QLED TV", "Turbo Sound"):
        assert phrase in html


def test_tc2_alfa_row(pipeline: Pipeline) -> None:
    alfa = pipeline([TC2_ROW])["alfa"][0]
    assert alfa["Vendor"] == "Ajmer Electronics"
    assert alfa["Brands"] == "3673"
    assert alfa["Category"] == "11539"  # LED TV -- mapped to 11539 in current category list
    assert not any(key.startswith("Attribute_") for key in alfa)


# ===========================================================================
# Both cases -- shared guarantees
# ===========================================================================
def test_both_input_vendor_column_is_ignored(pipeline: Pipeline) -> None:
    rows = [dict(TC1_ROW), dict(TC2_ROW)]
    rows[0]["Vendor"] = "SOME OTHER VENDOR ENTIRELY"
    result = pipeline(rows)
    assert result["digi"][0]["Vendor"] == "KiaChahiye PVT LTD"
    assert result["alfa"][0]["Vendor"] == "Ajmer Electronics"


def test_a_sheet_with_no_vendor_column_at_all_is_accepted(pipeline: Pipeline) -> None:
    """The Vendor column is optional: neither file's Vendor comes from the sheet.

    Both literals are fixed in config.py, so a sheet that simply has no Vendor
    column must still run -- and must still publish both exact strings.
    """
    rows = [dict(TC1_ROW), dict(TC2_ROW)]
    for row in rows:
        row.pop("Vendor", None)
    result = pipeline(rows)
    assert result["digi"][0]["Vendor"] == "KiaChahiye PVT LTD"
    assert result["alfa"][0]["Vendor"] == "Ajmer Electronics"
    assert len(result["digi"]) == 2 and len(result["alfa"]) == 2


def test_both_files_written_and_readable(pipeline: Pipeline) -> None:
    result = pipeline([TC1_ROW, TC2_ROW])
    assert len(result["digi"]) == 2
    assert len(result["alfa"]) == 2
    for path in (result["digi_path"], result["alfa_path"]):
        assert path.exists()
    with result["digi_path"].open("r", encoding="utf-8-sig", newline="") as handle:
        assert next(csv.reader(handle))[0] == "Product ID"


def test_shared_fields_never_drift_between_files(pipeline: Pipeline) -> None:
    """Derive once, project twice: every shared column is byte-identical.

    Description is the one shared column a store may split, and only by naming a
    different `description_template` on one of its two cells -- which is what
    tests/test_description_templates.py and tests/test_description_isolation.py
    prove.  This fixture projects with no store config, so both cells take the shop's
    own table and identical bytes are still demanded here.
    """
    result = pipeline([TC1_ROW, TC2_ROW])
    shared = [
        "Title", "Description", "Brands", "Product Type", "Tags", "SEO Title",
        "SEO Description", "Product Images", "Option1 Name", "Option1 Value",
        "Variant SKU", "Variant Barcode", "Variant Price", "Variant Compare At Price",
        "Variant Bin Number", "Variant Quantity", "Handle",
    ]
    for digi, alfa in zip(result["digi"], result["alfa"], strict=True):
        for column in shared:
            if column == "Brands":
                continue  # platform-specific by design
            assert digi[column] == alfa[column], column
    # Vendor must NOT match.
    assert result["digi"][0]["Vendor"] != result["alfa"][0]["Vendor"]
