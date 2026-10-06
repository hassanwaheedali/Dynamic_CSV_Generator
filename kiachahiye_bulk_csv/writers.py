"""Section 2 -- the two platform projections and the two output CSVs.

This is the ONLY module that knows either file's column order, and the only one
that may write a CSV.  Both rows are projected from a single ``ProductRecord``,
which is what makes "derive once, project twice" (spec section 0) structural
rather than a matter of discipline.

Two genuinely different Vendor constants live here and are never derived from
the input sheet's own Vendor column, whose value is ignored entirely.
"""

from __future__ import annotations

import csv
from pathlib import Path

from config import VENDOR_ALFA as VENDOR_ALFA  # edit in config.py
from config import VENDOR_DIGI as VENDOR_DIGI
from models import AlfaOutputRow, DigiOutputRow, ProductRecord

# Both Vendor constants come from config.py -- the one file to edit when a
# vendor spelling ever changes.  They are re-exported here so every existing
# `from writers import VENDOR_DIGI` keeps working.
# (the two constants themselves live in config.py)

ATTR_COLUMNS: tuple[str, ...] = (
    "Attribute_Air Conditioner Type",
    "Attribute_Washing Machine Type",
    "Attribute_Washing Machine Capacity",
    "Attribute_Product Type",
    "Attribute_Display Size",
    "Attribute_Capacity",
    "Attribute_Warranty",
    "Attribute_Air Conditioner Capacity",
    "Attribute_Refrigerator Type",
    "Attribute_Microwave Type",
    "Attribute_INV/NON-INV",
    "Attribute_Processor",
    "Attribute_Water Dispenser Type",
    "Attribute_LED Type",
    "Attribute_Geyser Type",
    "Attribute_Geyser Capacity",
    "Attribute_Watts",
    "Attribute_Volt",
    "Attribute_Generation",
    "Attribute_Fan Type",
    "Attribute_Battery",
    "Attribute_Core",
    "Attribute_Thickness",
    "Attribute_BNPL",
    "Attribute_Fragrance Type",
    "Attribute_Lasting",
    "Attribute_Sillage / Projection",
    "Attribute_Season",
    "Attribute_UPS Inverter Type",
    "Attribute_Generator Types",
    "Attribute_Watch Sizes",
    "Attribute_Watch Display Type",
    "Attribute_Watch Band",
    "Attribute_Watch Sensor Feature",
    "Attribute_SKin Type",
    "Attribute_Air Cooler Category",
)

SHARED_PREFIX: tuple[str, ...] = (
    "Product ID",
    "Title",
    "Description",
    "Vendor",
    "Brands",
    "Product Type",
    "Category",
    "Tags",
    "SEO Title",
    "SEO Description",
    "Product Images",
    "Option1 Name",
    "Option1 Value",
    "Option2 Name",
    "Option2 Value",
    "Option3 Name",
    "Option3 Value",
    "Variant SKU",
    "Variant Barcode",
    "Variant Weight",
    "Variant Weight Unit",
    "Variant Price",
    "Variant Compare At Price",
    "Variant Bin Number",
    "Variant Quantity",
    "Handle",
    "Size Chart",
    "Collection",
)

# DigiMall: 66 columns.  Alfa: 28 columns -- the shared prefix, full stop.
DIGI_HEADER: tuple[str, ...] = (
    *SHARED_PREFIX,
    "Short Description",
    "Commission Percentage",
    *ATTR_COLUMNS,
)
ALFA_HEADER: tuple[str, ...] = SHARED_PREFIX

DIGI_COLUMN_COUNT = 66
ALFA_COLUMN_COUNT = 28


def _single_line(value: str) -> str:
    """HTML fields must never carry a raw newline into the CSV."""
    return value.replace("\r", " ").replace("\n", " ")


def _record_common(record: ProductRecord, vendor: str) -> dict[str, str]:
    """Every field that is identical in both files, plus that file's Vendor."""
    desc = record.description
    return {
        "Product ID": "",
        "Title": record.title,
        "Description": _single_line(desc.description_html),
        "Vendor": vendor,
        "Brands": "",
        "Product Type": record.product_type,
        "Category": "",
        "Tags": ", ".join(desc.tags),
        "SEO Title": desc.seo_title,
        "SEO Description": _single_line(desc.seo_description),
        "Product Images": record.images,
        "Option1 Name": record.option1_name,
        "Option1 Value": record.option1_value,
        "Option2 Name": record.option2_name,
        "Option2 Value": record.option2_value,
        "Option3 Name": record.option3_name,
        "Option3 Value": record.option3_value,
        "Variant SKU": record.sku,
        "Variant Barcode": record.barcode,
        "Variant Weight": record.weight,
        "Variant Weight Unit": record.weight_unit,
        "Variant Price": str(record.variant_price),
        "Variant Compare At Price": str(record.variant_compare_at_price),
        "Variant Bin Number": record.bin_number,
        "Variant Quantity": str(record.variant_quantity),
        "Handle": record.handle,
        "Size Chart": "",
        "Collection": "",
    }


def build_digi_row(record: ProductRecord) -> DigiOutputRow:
    """Project one ProductRecord into DigiMall's 66-column schema (section 2A)."""
    values = _record_common(record, VENDOR_DIGI)
    values["Brands"] = "" if record.brand.digi_id is None else str(record.brand.digi_id)
    values["Category"] = record.category.digi_path or ""
    values["Short Description"] = _single_line(record.description.short_description)
    values["Commission Percentage"] = ""
    for column in ATTR_COLUMNS:
        values[column] = record.attributes.get(column, "")
    return DigiOutputRow(values=values)


def build_alfa_row(record: ProductRecord) -> AlfaOutputRow:
    """Project one ProductRecord into Alfa's 28-column schema (section 2B).

    No Short Description, no Commission Percentage, and none of the 36
    Attribute_* columns exist in this file.
    """
    values = _record_common(record, VENDOR_ALFA)
    values["Brands"] = "" if record.brand.alfa_id is None else str(record.brand.alfa_id)
    # Alfa's Category is the BARE LEAF ID only -- never a joined path.
    values["Category"] = record.category.alfa_id or ""
    return AlfaOutputRow(values=values)


def write_csv(path: Path, header: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    """Write one platform's file: every field quoted, HTML fields single-line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        for row in rows:
            writer.writerow([_single_line(str(row.get(column, ""))) for column in header])


