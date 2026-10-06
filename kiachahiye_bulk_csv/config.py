"""The single place for every setting a person is expected to change.

Nothing in this module imports anything else from the package, so it can be
read (and edited) without following any code.  Every other module imports the
value it needs from here, which means each setting exists in exactly one place.

    ██  EDIT HERE  ██  -- vendors, file paths, and the numeric defaults

Everything else that is editable lives with its own rules, each block marked
with the same banner:

    brands.py            brand ids and name aliases
    categories.py        category ids, breadcrumb aliases, Product Type names
    attributes.py        allowed attribute values, aliases, per-type scope
    warranty_terms.py    the warranty reference table (edit a term here)
    sku_handle.py        model codes, SKU/Handle shaping
    title_builder.py     Title formula and series words
    description_builder.py  description, Tags, SEO and Short Description rules
"""

from __future__ import annotations

from pathlib import Path

# ===========================================================================
#  EDIT HERE -- the two Vendor constants
# ===========================================================================
# These are deliberately different strings, and neither is ever taken from the
# input sheet's own Vendor column (that column is read and then ignored).
#   DigiMall importer expects:  KiaChahiye PVT LTD
#   Alfa importer expects:      Kia Chahiye Pvt Ltd
# Do not make them match each other.
VENDOR_DIGI = "KiaChahiye PVT LTD"
VENDOR_ALFA = "Kia Chahiye Pvt Ltd"

# ===========================================================================
#  EDIT HERE -- files and folders
# ===========================================================================
PROJECT_ROOT = Path(__file__).resolve().parent

# The source product sheet (.csv or .xlsx).
INPUT_FILE = PROJECT_ROOT / "data" / "input" / "Products.csv"

# Dedicated output directory per input sheet (e.g. data/output/Products/):
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / INPUT_FILE.stem

# The two finished bulk-upload files -- separate folders, never combined.
DIGI_OUTPUT = OUTPUT_DIR / "digi" / "digimall_bulk_import.csv"
ALFA_OUTPUT = OUTPUT_DIR / "alfa" / "alfa_bulk_import.csv"

# The combined QC / flagging report and the 20-row Title review sample.
QC_REPORT = OUTPUT_DIR / "qc_report.csv"
TITLE_SAMPLE = OUTPUT_DIR / "title_review_sample.csv"

# The warranty terms themselves live in warranty_terms.py as WARRANTY_TERMS --
# brand -> category -> "Part = Duration".  Nothing to configure here.

# ===========================================================================
#  EDIT HERE -- numeric defaults and length rules
# ===========================================================================
# The sheet has no stock column, so every row gets this quantity and is flagged.
DEFAULT_VARIANT_QUANTITY = 20

# Search-engine copy length windows (characters).
SEO_TITLE_MIN = 65
SEO_TITLE_MAX = 90
SEO_DESC_MIN = 151
SEO_DESC_MAX = 155

# Hard cap for a product Title.
TITLE_MAX = 90

# Thin-content thresholds.  Nothing in the upload pipeline depends on these:
# they only decide which rows land in the "descriptions that need work" report
# written by thin_report.py, so the client can fix the weakest rows first.
THIN_DESCRIPTION_CHARS = 200  # a source Description below this is called very short
SHORT_DESCRIPTION_CHARS = 300  # below this it is called short
THIN_SPEC_ROWS = 3  # a listing table with only Brand/Type (+1 row) shows no real specs
THIN_SHORT_BULLETS = 3  # the spec asks for 3 short-description bullets when the row supports them
THIN_REPORT = PROJECT_ROOT / "data" / "output" / "thin_descriptions.csv"

# ===========================================================================
#  EDIT HERE -- LED TV warranty
# ===========================================================================
# True  = a TV that does not state its own warranty takes the brand's TV terms
#         from WARRANTY_TERMS in warranty_terms.py.  Confirmed by the client:
#         Dawlance gives a 2-year brand warranty on its LED TVs, TCL 2 years on
#         panel and parts.  This supersedes the older Test Case 2 expectation of
#         "no warranty row for a TV".
# False = revert to showing no warranty row for a TV.
APPLY_TV_WARRANTY_TABLE = True
