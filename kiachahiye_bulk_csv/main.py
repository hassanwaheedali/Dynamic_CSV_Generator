"""Entrypoint -- reads the source sheet, resolves every row once, writes both
platform CSVs and the combined QC report.

Usage
-----
    python main.py                       # uses the paths in CONFIG below
    python main.py --input other.csv --digi my_digi.csv --alfa my_alfa.csv
    python main.py --sample-titles 20    # write a before/after Title review file

Nothing here calls an LLM or the network.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

import config as CONFIG
from attributes import build_attributes
from brands import resolve_brand
from categories import resolve_category, resolve_product_type
from description_builder import build_description_bundle, mentions_subtype
from models import InputRow, ProductRecord
from pricing import resolve_prices, resolve_quantity
from qc_report import (
    CAT_AC_INVERTER_UNKNOWN,
    CAT_ATTRIBUTE_EMPTY,
    CAT_BRAND_ALFA,
    CAT_BRAND_DIGI,
    CAT_CATEGORY_ALFA,
    CAT_CATEGORY_DIGI,
    CAT_FALLBACK_SKU,
    CAT_HANDLE_DEDUPED,
    CAT_PRODUCT_TYPE_INFERRED,
    CAT_QTY_DEFAULTED,
    CAT_SEO_DESCRIPTION_LENGTH,
    CAT_SERIES_SINGLE_ROW,
    CAT_SHORT_DESCRIPTION_THIN,
    CAT_SKU_DEDUPED,
    CAT_SUBTYPE_LINE_UNUSED,
    CAT_THIN_DESCRIPTION,
    CAT_TITLE_DESCRIPTION_CONFLICT,
    CAT_TITLE_DROPPED_WORDS,
    CAT_TITLE_FALLBACK,
    CAT_WEIGHT_MISSING,
    CAT_WEIGHT_UNREADABLE,
    QCFlagCollector,
)
from series_corpus import analyze_row, build_corpus, normalize_shape
from sku_handle import (
    ModelExtraction,
    UniqueRegistry,
    build_fallback_model,
    build_handle_token,
    build_sku_token,
    compact_model,
    extract_model,
    extract_variant_tokens,
    find_series_token,
    format_variant,
    handle_normaliser,
    resolve_capacity,
    taps_conflict,
    upper_sku_normaliser,
)
from textutils import (
    colour_disagreements,
    find_weight_in_text,
    parse_weight_cell,
    parse_weight_unit,
    pick_weight_columns,
    strip_markup_keep_lines,
)
from title_builder import build_title, without_leading_type_words, word_identity
from vendor_config import VENDOR_REGISTRY, VendorConfig, get_vendor
from warranty import TERM_LINES, resolve_warranty
from writers import (
    ALFA_HEADER,
    DIGI_HEADER,
    build_alfa_row,
    build_digi_row,
    write_csv,
)

# ===========================================================================
#  CONFIG -- everything editable lives in config.py (vendors, paths, defaults)
# ===========================================================================
PROJECT_ROOT = CONFIG.PROJECT_ROOT
INPUT_FILE = CONFIG.INPUT_FILE
DIGI_OUTPUT = CONFIG.DIGI_OUTPUT
ALFA_OUTPUT = CONFIG.ALFA_OUTPUT
QC_REPORT = CONFIG.QC_REPORT
TITLE_SAMPLE = CONFIG.TITLE_SAMPLE

if TYPE_CHECKING:
    from series_corpus import Corpus, RowAnalysis, WordEvidence

# The only columns the sheet must supply.  "Vendor" is deliberately NOT here:
# neither file's Vendor is ever taken from the sheet (the two literals live in
# config.py -- VENDOR_DIGI / VENDOR_ALFA), so a sheet without a Vendor column is
# perfectly valid.  If the column is present its value is read and ignored.
REQUIRED_COLUMNS = (
    "Title", "Description", "Sell Price", "Original Price",
    "Categories", "Brand", "Image",
)




# ---------------------------------------------------------------------------
# Input reading
# ---------------------------------------------------------------------------
def _normalise_row(raw: dict[str, Any], row_number: int) -> InputRow:
    def get(name: str) -> str:
        for key, value in raw.items():
            if key is not None and key.strip().lower() == name.lower():
                return "" if value is None else str(value)
        return ""


    # The weight columns are found by name, so any spelling works: "Shipping
    # Weight", "Gross Weight (kg)", "Wt In Kgs" or plain "Weight".
    weight_column, unit_column = pick_weight_columns([key or "" for key in raw])

    # A source cell may carry HTML; strip it before anything parses the text, so
    # markup can never reach the specification table or the Attributes as content.
    return InputRow(
        row_number=row_number,
        title=strip_markup_keep_lines(get("Title")).strip(),
        description=strip_markup_keep_lines(get("Description")),
        sell_price=get("Sell Price"),
        original_price=get("Original Price"),
        categories=get("Categories"),
        brand=get("Brand"),
        image=get("Image"),
        vendor=get("Vendor"),  # read but deliberately never used
        weight=get(weight_column) if weight_column else "",
        weight_unit=get(unit_column) if unit_column else "",
    )


def read_input(path: Path) -> list[InputRow]:
    """Read the source sheet (.csv or .xlsx) with a real parser."""
    if not path.exists():
        raise FileNotFoundError(f"Input sheet not found: {path}")

    rows: list[InputRow] = []
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            from openpyxl import (  # type: ignore[import-untyped]  # noqa: PLC0415
                load_workbook,
            )
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "openpyxl is required to read .xlsx input; pip install openpyxl"
            ) from exc
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook.active
        iterator = sheet.iter_rows(values_only=True)
        header = next(iterator)
        columns = [str(cell) if cell is not None else "" for cell in header]
        for index, values in enumerate(iterator, start=2):
            raw = {columns[i]: values[i] for i in range(min(len(columns), len(values)))}
            rows.append(_normalise_row(raw, index))
        workbook.close()
        return rows

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [
            column
            for column in REQUIRED_COLUMNS
            if not any(
                (field or "").strip().lower() == column.lower()
                for field in (reader.fieldnames or [])
            )
        ]
        if missing:
            raise ValueError(f"Input sheet is missing required column(s): {missing}")
        for index, raw in enumerate(reader, start=2):
            rows.append(_normalise_row(raw, index))
    return rows


def resolve_images(raw_image: str) -> str:
    """Pipe-join multiple URLs; never invent one."""
    parts = [part.strip() for part in raw_image.split(",") if part.strip()]
    return "|".join(parts)


def resolve_weight(
    text: str, column_value: str = "", column_unit: str = ""
) -> tuple[str, str, str]:
    """Weight for the Variant Weight cells, and where it came from.

    The sheet's own Weight column wins when it holds a readable weight; otherwise
    the Description is read, which is where most of the current sheet states it.
    Returns ``(number, unit, source)`` with source ``"column"``, ``"description"``
    or ``""`` when neither has one.
    """
    written = parse_weight_cell(column_value)
    if written is not None:
        # A separate unit column, when the sheet has one, refines the unit.
        stated_unit = parse_weight_unit(column_unit) if column_unit else None
        unit = stated_unit if stated_unit is not None else written[1]
        return written[0], unit, "column"
    in_text = find_weight_in_text(text)
    if in_text is not None:
        return in_text[0], in_text[1], "description"
    return "", "", ""


# ---------------------------------------------------------------------------
# Per-row resolution
# ---------------------------------------------------------------------------
def read_rows(
    rows: list[InputRow],
    vendor_cfg: VendorConfig | None = None,
) -> tuple[list[RowAnalysis], Corpus]:
    """Read the whole sheet once and vote which words name a product line, for which brand.

    The vote is a property of the RUN, not of a row: `ECO` is a name because Midea rows stand it
    clear of a part number, and no single row can see that across the sheet.  So every row is read
    here, before any Title is built, and the verdict is handed down to each row.

    Only brand and Product Type are resolved first, because the vote is keyed by both -- and both
    resolvers are pure, so this pre-pass raises no QC flag and cannot double-count one.  Model,
    capacity, colour and inverter are deliberately NOT resolved here: the corpus the measurements
    were made against is the sheet's own columns, and a name must earn its place from what the shop
    wrote, not from what a later rule guessed.
    """
    analyses: list[RowAnalysis] = []
    for row in rows:
        brand = resolve_brand(row.brand, row.title, vendor_cfg=vendor_cfg).raw
        text = f"{row.title}\n{row.description}"
        product_type = resolve_product_type(
            resolve_category(row.categories, text, text, vendor_cfg=vendor_cfg),
            brand,
            vendor_cfg=vendor_cfg,
        )[0]
        analyses.append(
            analyze_row(
                row.title.strip(),
                brand=brand,
                product_type=product_type,
                breadcrumb=row.categories.strip(),
                description=row.description.strip(),
            )
        )
    return analyses, build_corpus(analyses)


def _drop_contained(outer: str, inner: str) -> str:
    """Empty `inner` when every word of it already stands inside `outer` -- one fact, one token.

    The row wrote `Chrome Plus 45` and the vote called the same line `Chrome`.  Handed to the SEO
    shed as two removable tokens, the second cut the head off the first and left `- Plus -` in the
    shop's search result: a fragment that names nothing.
    """
    if outer and inner and set(inner.lower().split()) <= set(outer.lower().split()):
        return ""
    return inner


def resolve_row(
    row: InputRow,
    flags: QCFlagCollector,
    sku_registry: UniqueRegistry,
    handle_registry: UniqueRegistry,
    finalise: bool,
    analysis: RowAnalysis | None = None,
    corpus: Corpus | None = None,
    vendor_cfg: VendorConfig | None = None,
) -> ProductRecord:
    """Resolve one input row into a single shared ProductRecord.

    Runs twice: first pass counts SKU/Handle collisions, second pass assigns the
    final unique values.  The two passes share every other rule, so nothing is
    resolved twice differently.  `analysis` and `corpus` are this row's reading and the run's
    verdict, both built once by :func:`read_rows` and handed to both passes, so the passes can
    never print two different series for one row.
    """
    text = f"{row.title}\n{row.description}"

    # The corpus vote is keyed by the brand and product type THIS row was read with, so the reading
    # handed down must be this row's.  `run()` builds both lists from the same `rows`, in order;
    # this makes a threading mistake fail at the row that broke instead of printing another
    # product's name on this one.
    if analysis is not None:
        assert analysis.title == normalize_shape(row.title.strip()), (
            f"row {row.row_number}: analysis does not belong to this row"
        )

    brand = resolve_brand(row.brand, row.title, vendor_cfg=vendor_cfg)
    effective_brand = brand.raw
    if brand.digi_id is None:
        flags.flag(
            row.row_number, row.title, CAT_BRAND_DIGI,
            f"brand {effective_brand!r} is not in BRANDS_DIGI (brands.py) -- DigiMall Brands left empty",
            platform="digi",
        )
    if brand.alfa_id is None:
        flags.flag(
            row.row_number, row.title, CAT_BRAND_ALFA,
            f"brand {effective_brand!r} is not in BRANDS_ALFA (brands.py) -- Alfa Brands left empty",
            platform="alfa",
        )

    category = resolve_category(row.categories, text, text, vendor_cfg=vendor_cfg)
    if category.digi_path is None:
        digi_reason = category.digi_reason or category.reason
        is_ac_silent = "inverter/non-inverter signal" in digi_reason
        flags.flag(
            row.row_number,
            row.title,
            CAT_AC_INVERTER_UNKNOWN if is_ac_silent else CAT_CATEGORY_DIGI,
            f"{digi_reason} -- DigiMall Category left empty",
            platform="digi",
        )
    if category.alfa_id is None:
        alfa_reason = category.alfa_reason or category.reason
        flags.flag(
            row.row_number, row.title, CAT_CATEGORY_ALFA,
            f"{alfa_reason} -- Alfa Category left empty",
            platform="alfa",
        )

    product_type, inferred = resolve_product_type(
        category, effective_brand, vendor_cfg=vendor_cfg
    )
    if inferred:
        flags.flag(
            row.row_number, row.title, CAT_PRODUCT_TYPE_INFERRED,
            f"Product Type {product_type!r} inferred from the breadcrumb -- please confirm",
        )

    conflict = taps_conflict(row.title, row.description)
    if conflict is not None:
        flags.flag(
            row.row_number, row.title, CAT_TITLE_DESCRIPTION_CONFLICT,
            f"Title says {conflict[0]} but the Description says {conflict[1]} -- the "
            "SKU follows the Title; please confirm which is correct in the source.",
        )

    extraction = without_leading_type_words(extract_model(row.title, row.description))
    capacity = resolve_capacity(text, product_type, brand.normalized, extraction)
    identity = word_identity(row.title, effective_brand) if extraction.confidence == "none" else ""
    if extraction.confidence == "none":
        model = build_fallback_model(
            effective_brand,
            find_series_token(text),
            capacity,
            row.title,
            identity,
        )
        used = ModelExtraction(model, "fallback", "none")
        flags.flag(
            row.row_number, row.title, CAT_FALLBACK_SKU,
            "No formal model code found -- fallback SKU built from title words, "
            "please verify manually before upload.",
        )
    else:
        model = extraction.code
        used = extraction

    title_formula = vendor_cfg.title_formula if vendor_cfg is not None else "standard"
    strict_rebuild = (
        vendor_cfg.strict_title_rebuild if vendor_cfg is not None else None
    )
    title_result = build_title(
        effective_brand, used, product_type, row.title, row.description,
        strict_rebuild=strict_rebuild,
        analysis=analysis, corpus=corpus, capacity=capacity, identity=identity,
        title_formula=title_formula,
    )
    if title_result.strategy == "kept-with-light-cleanup":
        flags.flag(
            row.row_number, row.title, CAT_TITLE_FALLBACK,
            "Title kept from source with light cleanup -- no reliable Model code "
            "found for a full rebuild.",
        )
    elif len(title_result.dropped_words) >= 2:
        flags.flag(
            row.row_number, row.title, CAT_TITLE_DROPPED_WORDS,
            "Rebuilt Title dropped source word(s): "
            + ", ".join(title_result.dropped_words[:8])
            + " -- if one of them names this brand's line, the corpus has to prove it "
            "(series_corpus.py); SERIES_WORDS in title_builder.py is only the thin-sheet fallback.",
        )
    if title_result.series_earned_by == "brand-position":
        flags.flag(
            row.row_number, row.title, CAT_SERIES_SINGLE_ROW,
            f"Series {title_result.series_name!r} for {effective_brand} is believed from ONE row "
            "-- the vote's weakest proof, not two products stating it. "
            "Confirm it is a real line before uploading.",
        )
    if title_result.subtype_line and not title_result.subtype_label_added:
        flags.flag(
            row.row_number, row.title, CAT_SUBTYPE_LINE_UNUSED,
            f"SubType: {title_result.subtype_line!r} added no word to the Title -- it "
            f"{title_result.subtype_label_note}. The Description still shows your line.",
        )
    elif not title_result.subtype_line and mentions_subtype(row.description):
        flags.flag(
            row.row_number, row.title, CAT_SUBTYPE_LINE_UNUSED,
            "The row writes the words `SubType` but not as a labelled line -- write "
            "`SubType: Heat & Cool` on its own line, or the Title cannot use it.",
        )
    for title_value, description_value in title_result.subtype_conflicts:
        # The row claims two machines for one question and no reader may settle it from letters: the
        # vendor sentence `... is a X Ton DC Inverter split air conditioner` stands in 204 of these
        # Descriptions and is wrong on the six rows whose Titles sell a cassette.  The slot ships
        # empty rather than wrong, and the answer is one line on the row.
        flags.flag(
            row.row_number, row.title, CAT_TITLE_DESCRIPTION_CONFLICT,
            f"Title says {title_value!r} but the Description says {description_value!r} for the same "
            "type -- the [Subtype] slot and its Attribute_* cell are left empty. Write `SubType: "
            f"{title_value}` (or the other value) on the row to settle it.",
        )

    warranty_rows, warranty_headline, warranty_source = resolve_warranty(
        text, brand.normalized, product_type
    )

    other_colors = colour_disagreements(text, row.title)
    if other_colors and title_result.color_token:
        # The row states a colour twice and the two statements disagree, so one of them is wrong: the
        # Title ships -- it is the name he gave this machine, while `• Product Color:` is a form he
        # fills in and `Black` stands stamped on every Dawlance refrigerator row on this sheet.
        # Overriding a line silently would leave him reading a colour he never sold, so the losing
        # statement is named in the QC report for him to look at (owner ruling).
        flags.flag(
            row.row_number, row.title, CAT_TITLE_DESCRIPTION_CONFLICT,
            f"This row ships {title_result.color_token!r} as its colour, but the row also states "
            f"{' and '.join(repr(color) for color in other_colors)} -- the Title's colour wins and "
            f"prints in the Title and in Option1 Value. Write "
            f"`Color: {title_result.color_token}` on the row to settle it.",
        )

    description = build_description_bundle(
        brand=effective_brand,
        model=model if used.confidence != "none" else "",
        product_type=product_type,
        breadcrumb_leaf=row.categories.split("/")[-1].strip(),
        color=title_result.color_token,
        capacity=title_result.capacity_token,
        warranty_rows=warranty_rows,
        description=row.description,
        title=title_result.title,
        has_real_model=used.confidence != "none",
        feature_tokens=[
            # A name-and-number is ONE fact and is handed over whole: `build_seo_title` sheds its
            # glued-on digits before the name, and refuses any cut that would leave the number
            # standing alone.  Passing `10` as its own token deleted the WASHING MACHINE's capacity
            # digit instead (`Kenwood KG Semi Automatic`) -- the shed cannot tell two `10`s apart.
            title_result.identity_token,
            # A voted name the row also wrote inside its own name-and-number is ONE fact, offered
            # twice: the shed cut `Chrome` out of `Chrome Plus 45` and left `- Plus -` in the shop's
            # result -- a fragment that names nothing.
            _drop_contained(title_result.identity_token, title_result.series_token),
            title_result.color_token,
            title_result.inverter_token,
            title_result.capacity_token,
            # Last, not first: an over-budget search title must shed the sub-type word before it cut
            # its own TAIL -- measured, 116 rows had lost `Warranty`, `Compressor` or their tonnage.
            # Ahead of this list it became the first casualty on 219 rows whose Title never changed.
            title_result.subtype_token,
        ],
    )
    if description.thin:
        flags.flag(
            row.row_number, row.title, CAT_THIN_DESCRIPTION,
            "Source Description is thin -- the table shows only what was genuinely "
            "stated, with no filler rows added.",
        )
    if not (151 <= len(description.seo_description) <= 155):
        flags.flag(
            row.row_number, row.title, CAT_SEO_DESCRIPTION_LENGTH,
            f"SEO Description is {len(description.seo_description)} characters, outside "
            "the required 151-155 -- the source had too little product-specific "
            "material to pad with honestly.",
        )
    if description.short_description_bullets < 3:
        flags.flag(
            row.row_number, row.title, CAT_SHORT_DESCRIPTION_THIN,
            f"Short Description built with only {description.short_description_bullets} "
            "bullet(s) -- fewer than 3 standout facts existed in the source.",
        )

    attributes, unmatched = build_attributes(
        title=title_result.title,
        description=row.description,
        product_type=product_type,
        warranty_headline=warranty_headline,
    )
    for column in title_result.subtype_undecided_columns:
        # The slot is empty because the row disagrees with itself, and this matcher reads his
        # Description right after the Title -- where the vendor's template sentence lives.  A value
        # read out of a sentence the row contradicts is not a fact about the product, so the cell
        # waits for his answer instead of shipping the template's guess.
        attributes.pop(column, None)
    for column, signal in unmatched:
        flags.flag(
            row.row_number, row.title, CAT_ATTRIBUTE_EMPTY,
            f"{column}: raw signal {signal!r} did not exactly match any allowed value "
            "-- cell left empty; extend ALIASES/ALLOWED in attributes.py if it should map",
            platform="digi",
        )

    price, compare_at = resolve_prices(row, flags)
    quantity = resolve_quantity(row, flags)

    weight, weight_unit, _source = resolve_weight(text, row.weight, row.weight_unit)
    if not weight:
        if row.weight.strip():
            flags.flag(
                row.row_number, row.title, CAT_WEIGHT_UNREADABLE,
                f"Weight column says {row.weight!r}, which is not a weight in kg/g/lb/oz "
                "-- Variant Weight left empty.",
            )
        else:
            flags.flag(
                row.row_number, row.title, CAT_WEIGHT_MISSING,
                "No weight stated in the source -- Variant Weight left empty.",
            )

    variant_tokens = extract_variant_tokens(text, capacity, effective_brand)
    # A dimension already present in the model code (e.g. a colour baked into a
    # fallback model) must not be repeated in the variant suffix.
    compact = compact_model(model).upper()
    variant_tokens = tuple(
        token for token in variant_tokens if token.replace(" ", "").upper() not in compact
    )
    variant_suffix = format_variant(variant_tokens)

    sku_prefix = vendor_cfg.sku_prefix if vendor_cfg is not None else None
    if not finalise:
        sku_registry.register_base(build_sku_token(model, prefix=sku_prefix))
        handle_registry.register_base(build_handle_token(model, product_type))
        sku = handle = ""
    else:
        sku, sku_numeric = sku_registry.assign(
            build_sku_token(model, prefix=sku_prefix), variant_suffix
        )
        handle, handle_numeric = handle_registry.assign(
            build_handle_token(model, product_type),
            f"{variant_suffix} -{product_type}".strip() if variant_suffix else "",
        )
        if sku_numeric:
            flags.flag(
                row.row_number, row.title, CAT_SKU_DEDUPED,
                f"SKU {sku} needed a numeric suffix -- the model plus every "
                "extractable variant dimension was already taken.",
            )
        if handle_numeric:
            flags.flag(
                row.row_number, row.title, CAT_HANDLE_DEDUPED,
                f"Handle {handle} needed a numeric suffix to stay unique in this run.",
            )
        elif handle_registry.base_is_colliding(
            build_handle_token(model, product_type)
        ):
            flags.flag(
                row.row_number, row.title, CAT_HANDLE_DEDUPED,
                f"Handle disambiguated with the variant suffix: {handle}",
            )

    color_defaults = (
        vendor_cfg.default_product_type_colors
        if vendor_cfg is not None
        else getattr(CONFIG, "DEFAULT_PRODUCT_TYPE_COLORS", {})
    )
    option1_color = title_result.color_token or color_defaults.get(product_type, "")

    return ProductRecord(
        row_number=row.row_number,
        source=row,
        title=title_result.title,
        product_type=product_type,
        product_type_inferred=inferred,
        description=description,
        brand=brand,
        category=category,
        images=resolve_images(row.image),
        option1_name="Color" if option1_color else "",
        option1_value=option1_color,
        option2_name="", option2_value="", option3_name="", option3_value="",
        sku=sku,
        barcode=sku,
        bin_number=sku,
        handle=handle,
        weight=weight,
        weight_unit=weight_unit,
        variant_price=price,
        variant_compare_at_price=compare_at,
        variant_quantity=quantity,
        attributes=attributes,
        model=model,
        model_source=used.source,
        model_confidence=used.confidence,
        warranty_source=warranty_source,
        variant_suffix=variant_suffix,
        series_token=title_result.series_token,
        subtype_from=title_result.subtype_from,
        title_strategy=title_result.strategy,
        capacity_token=title_result.capacity_token,
        color_token=title_result.color_token,
        inverter_token=title_result.inverter_token,
        dropped_words=title_result.dropped_words,
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def corpus_report_lines(corpus: Corpus) -> list[str]:
    """What this run proved, brand by brand -- the block a human audits instead of the output CSV.

    A verdict without its evidence is only a claim: `avante` says nothing until the reader knows 32
    rows across 30 products stated it.  A name believed from a single row is called out on its own
    line, because that is the only kind of verdict a human has to act on, and 25 names on one wrapped
    line is a wall nobody reads.  Words print as the vote keys them (folded); the shop's own spelling
    is in the Titles.
    """
    lines: list[str] = []
    for brand in sorted(corpus.proven):
        names = corpus.proven[brand]
        rescued = sorted(word for word in names if names[word].earned_by == "brand-position")
        stated = sorted(set(names) - set(rescued))
        lines.extend(
            _pack_report(f"  {brand:12} ", [_report_name(w, names[w]) for w in stated])
        )
        if rescued:
            lines.extend(
                _pack_report(
                    f"  {'':12} needs a human: ",
                    [_report_name(w, names[w]) for w in rescued],
                )
            )
    if not corpus.proven:
        lines.append("  nothing -- this run proved no name for any brand")
    if corpus.blacklisted:
        lines.extend(_pack_report("  refused as noise : ", sorted(corpus.blacklisted)))
    lines.append(f"  undecided words  : {len(corpus.undecided)}")
    return lines


def _pack_report(label: str, items: list[str]) -> list[str]:
    """Lay the names out within the report's own 78 columns, breaking only between names.

    A line that wrapped mid-item would read `pular [3 rows /`, and the whole point of this block is
    that a person can trust the number printed under each name.  The label heads the group once:
    repeating `needs a human:` on every wrapped line would shout the same thing four times.  One
    name longer than the budget overflows it rather than being split -- names are never broken.
    """
    lines: list[str] = []
    current = ""
    for index, item in enumerate(items):
        piece = item + ("" if index == len(items) - 1 else ",")
        candidate = f"{current} {piece}" if current else piece
        if current and len(label) + len(candidate) > 78:
            lines.append(current)
            current = piece
            continue
        current = candidate
    if current:
        lines.append(current)
    if not lines:
        return [label.rstrip()]
    pad = " " * len(label)
    return [f"{label}{lines[0]}"] + [f"{pad}{line}" for line in lines[1:]]


def _report_name(word: str, evidence: WordEvidence) -> str:
    """`avante [32 rows / 30 products]` -- the evidence counted out for whoever reads it."""
    rows = f"{evidence.rows} row" + ("s" if evidence.rows != 1 else "")
    products = f"{evidence.products} product" + ("s" if evidence.products != 1 else "")
    return f"{word} [{rows} / {products}]"


def run(
    rows: list[InputRow],
    flags: QCFlagCollector,
    prepared: tuple[list[RowAnalysis], Corpus] | None = None,
    vendor_cfg: VendorConfig | None = None,
) -> list[ProductRecord]:
    # The SKU registry upper-cases everything it hands out; the Handle registry
    # slugs it.  Both are applied inside the registry, so a suffix can never
    # leak a raw Title spelling (" -Water Dispenser") into a live handle.
    print(
        f"  Warranty terms: {len(TERM_LINES)} brand/category entries from "
        "warranty_terms.py (edit WARRANTY_TERMS there to change a term)"
    )

    sku_registry = UniqueRegistry(upper_sku_normaliser)
    handle_registry = UniqueRegistry(handle_normaliser)
    if prepared is None:
        analyses, corpus = read_rows(rows, vendor_cfg=vendor_cfg)
    else:
        analyses, corpus = prepared
    # The vote is a fact about THIS sheet: a corpus read from another one would print its brands'
    # names here with no error, and the row-identity check below compares Titles only.  So the
    # reading carries the number of rows it was voted from.
    if len(analyses) != len(rows) or corpus.rows != len(rows):
        raise ValueError(
            f"run() was handed a reading for {corpus.rows} rows / {len(analyses)} analyses "
            f"but got {len(rows)} rows -- read the sheet and vote it in one call"
        )
    # The counting pass exists only so pass two can see which models collide.
    # It runs the same row code, so it must NOT report: a scratch collector
    # swallows those flags and the QC report keeps exactly one row per real
    # finding.  SKU/Handle dedupe flags are raised in pass two only, so nothing
    # is lost by the swap.
    scratch = QCFlagCollector()
    for index, row in enumerate(rows):
        resolve_row(
            row, scratch, sku_registry, handle_registry, finalise=False,
            analysis=analyses[index], corpus=corpus, vendor_cfg=vendor_cfg,
        )
    records: list[ProductRecord] = []
    for index, row in enumerate(rows, start=1):
        if index % 100 == 0 or index == len(rows):
            print(f"  ... resolved {index}/{len(rows)} rows", flush=True)
        records.append(
            resolve_row(
                row, flags, sku_registry, handle_registry, finalise=True,
                analysis=analyses[index - 1], corpus=corpus, vendor_cfg=vendor_cfg,
            )
        )
    return records


def write_title_sample(path: Path, records: list[ProductRecord]) -> None:
    """A before/after review file: 10 rebuilt rows and up to 10 kept rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(
            [
                "Row", "Strategy", "Source Title", "Final Title", "Model", "Capacity",
                "Color", "Series/Feature", "Inverter", "Source words dropped",
            ]
        )
        quotas: Counter[str] = Counter()
        for record in records:
            strategy = record.title_strategy
            if quotas[strategy] >= 10:
                continue
            quotas[strategy] += 1
            # Every column here is read off the record the run actually shipped.  Rebuilding the
            # Title a second time without the corpus would review a different row than the one the
            # shop gets -- the same product, two answers, and the sample would be the misleading one.
            writer.writerow(
                [
                    record.row_number,
                    strategy,
                    record.source.title,
                    record.title,
                    record.model,
                    record.capacity_token,
                    record.color_token,
                    record.series_token,
                    record.inverter_token,
                    ", ".join(record.dropped_words),
                ]
            )


def print_summary(
    records: list[ProductRecord],
    flags: QCFlagCollector,
    digi_path: Path,
    alfa_path: Path,
    corpus: Corpus | None = None,
    upload: str = "both",
) -> None:
    # Only the uploads this run actually produced are reported on; a DigiMall finding is not news
    # in an Alfa run.
    scope: tuple[str, ...] = ("digi", "alfa") if upload == "both" else (upload,)
    total = len(records)
    print()
    print("=" * 78)
    print(f"RUN COMPLETE -- {total} rows processed")
    print("=" * 78)
    if "digi" in scope:
        print(f"  DigiMall file : {digi_path}")
    if "alfa" in scope:
        print(f"  Alfa file     : {alfa_path}")

    summary = flags.platform_summary(total)
    print()
    print("ROWS NEEDING MANUAL REVIEW (split per platform -- never merged)")
    for platform, label, path in (
        ("digi", "DigiMall", digi_path),
        ("alfa", "Alfa", alfa_path),
    ):
        if platform not in scope:
            continue
        stats = summary[platform]
        print(
            f"  {label:9} need review: {stats['rows_need_review']:5} | "
            f"info-only notes: {stats['rows_info_only']:5} | "
            f"completely clean: {stats['rows_clean']:5}   ({path.name})"
        )

    print()
    print("PER-PLATFORM CELL COUNTS")
    if "digi" in scope:
        print(f"  DigiMall Category empty : {flags.count(CAT_CATEGORY_DIGI):5} rows")
        print(f"  DigiMall Brands empty   : {flags.count(CAT_BRAND_DIGI):5} rows")
    if "alfa" in scope:
        print(f"  Alfa     Category empty : {flags.count(CAT_CATEGORY_ALFA):5} rows")
        print(f"  Alfa     Brands empty   : {flags.count(CAT_BRAND_ALFA):5} rows")
    print(f"  AC rows with unknown inverter status : {flags.count(CAT_AC_INVERTER_UNKNOWN):5} rows")

    print()
    print("SHARED FLAGS (both files)")
    for category, label in (
        (CAT_FALLBACK_SKU, "Fallback SKU built from title words"),
        (CAT_SKU_DEDUPED, "SKU disambiguated (variant suffix, then numeric)"),
        (CAT_HANDLE_DEDUPED, "Handle needed a uniqueness suffix"),
        (CAT_WEIGHT_MISSING, "Variant Weight left empty (no weight in source)"),
        (CAT_WEIGHT_UNREADABLE, "Weight column not readable as kg/g/lb/oz"),
        (CAT_QTY_DEFAULTED, "Variant Quantity defaulted to 20"),
        (CAT_ATTRIBUTE_EMPTY, "DigiMall Attribute_* left empty despite a raw signal"),
        (CAT_THIN_DESCRIPTION, "Description thin (no filler rows added)"),
        (CAT_TITLE_FALLBACK, "Title kept from source"),
        (CAT_TITLE_DROPPED_WORDS, "Rebuilt Title dropped extra source words"),
        (CAT_SERIES_SINGLE_ROW, "Series name believed from a single row"),
        (CAT_SUBTYPE_LINE_UNUSED, "SubType: line added no word to the Title"),
        (CAT_TITLE_DESCRIPTION_CONFLICT, "Title and Description disagree (type, size or colour)"),
        (CAT_PRODUCT_TYPE_INFERRED, "Product Type inferred from breadcrumb"),
    ):
        if category == CAT_ATTRIBUTE_EMPTY and "digi" not in scope:
            continue  # the Attribute_* cells live only in the DigiMall file
        print(f"  {label:60} {flags.count(category):5} rows")

    # ---- the explicit "not found in the lookup table" listing you asked for --
    brand_misses: dict[str, Counter[str]] = {"digi": Counter(), "alfa": Counter()}
    category_misses: dict[str, Counter[str]] = {"digi": Counter(), "alfa": Counter()}
    for record in records:
        if record.brand.digi_id is None:
            brand_misses["digi"][record.brand.raw] += 1
        if record.brand.alfa_id is None:
            brand_misses["alfa"][record.brand.raw] += 1
        if record.category.digi_path is None:
            category_misses["digi"][record.category.raw] += 1
        if record.category.alfa_id is None:
            category_misses["alfa"][record.category.raw] += 1

    print()
    print("SUBTYPE SLOTS THIS RUN")
    slots: Counter[str] = Counter(record.subtype_from for record in records)
    print(
        f"  your SubType: line {slots['label']:5} | type list read from the row "
        f"{slots['list']:5} | carried off the series slot {slots['carried']:5} | "
        f"the platform's own type table {slots['class']:5} | "
        f"nothing states one {slots['']:5}"
    )

    print()
    print("SERIES NAMES THIS RUN PROVED")
    if corpus is None:
        print("  no corpus was read for this run")
    else:
        for line in corpus_report_lines(corpus):
            print(line)

    print()
    print("BRAND NOT FOUND IN LOOKUP TABLE")
    for platform, table, filename in (
        ("digi", "BRANDS_DIGI", "brands.py"),
        ("alfa", "BRANDS_ALFA", "brands.py"),
    ):
        if platform not in scope:
            continue
        misses = brand_misses[platform]
        if not misses:
            print(f"  {platform.upper():5} none -- every brand resolved")
            continue
        print(f"  {platform.upper():5} edit {table} in {filename}:")
        for name, count in misses.most_common():
            print(f"          {name!r} -> {count} rows left with an empty Brands cell")

    print()
    print("CATEGORY NOT FOUND IN LOOKUP TABLE")
    for platform, table, filename in (
        ("digi", "CATEGORY_DIGI_PATHS", "categories.py"),
        ("alfa", "CATEGORY_ALFA_IDS", "categories.py"),
    ):
        if platform not in scope:
            continue
        misses = category_misses[platform]
        if not misses:
            print(f"  {platform.upper():5} none -- every breadcrumb resolved")
            continue
        print(f"  {platform.upper():5} edit {table} in {filename}:")
        for name, count in misses.most_common():
            print(f"          {name!r} -> {count} rows left with an empty Category cell")

    if "digi" in scope:
        print()
        print("ATTRIBUTE VALUES NOT IN THE VOCABULARY YET (DigiMall Attribute_* cells left empty)")
        gaps = flags.attribute_gaps()
        if not gaps:
            print("  none -- every signal the sheet stated is on the allowed list")
        else:
            total = sum(gaps.values())
            print(f"  {total} empty cells across {len(gaps)} column/string pairs "
                  "-- edit ALLOWED in attributes.py:")
            for (column, raw), count in gaps.most_common(12):
                print(f"          {column} <- {raw!r} on {count} rows")
            if len(gaps) > 12:
                print(
                    f"          ... and {len(gaps) - 12} more pairs; "
                    "the full list is in the QC report"
                )

    print()
    print("WARRANTY COVERAGE")
    sources = Counter(record.warranty_source for record in records)
    for source, count in sources.most_common():
        print(f"  {source:26} {count:5} rows")
    brands_without_table = Counter(
        record.brand.normalized
        for record in records
        if record.warranty_source == "none"
    )
    if brands_without_table:
        print(
            "  rows with no warranty row "
            "(add the brand and category to WARRANTY_TERMS in warranty_terms.py):"
        )
        blanks: Counter[tuple[str, str]] = Counter(
            (record.brand.normalized, record.product_type)
            for record in records
            if record.warranty_source == "none"
        )
        for (brand, product_type), count in blanks.most_common(12):
            print(f"          {brand!r} / {product_type} -> {count} rows")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KiaChahiye bulk CSV pipeline")
    parser.add_argument("--input", type=Path, default=INPUT_FILE)
    parser.add_argument("--digi", type=Path, default=DIGI_OUTPUT)
    parser.add_argument("--alfa", type=Path, default=ALFA_OUTPUT)
    parser.add_argument("--qc", type=Path, default=QC_REPORT)
    parser.add_argument(
        "--sample-titles", type=Path, default=TITLE_SAMPLE,
        help="write a before/after Title review file to this path",
    )
    parser.add_argument(
        "--platform", choices=("both", "digi", "alfa"), default="both",
        help="produce only this upload: write its file and report its findings (default: both)",
    )
    parser.add_argument(
        "--vendor",
        choices=list(VENDOR_REGISTRY),
        default=None,
        help="which vendor's config to use (e.g. kiachahiye, ajmer)",
    )
    args = parser.parse_args(argv)
    vendor_cfg = get_vendor(args.vendor) if args.vendor is not None else None

    # One platform chosen means that platform only: the other file is not written, so an output
    # folder for an Alfa upload holds no DigiMall CSV to grab by mistake.
    scope: tuple[str, ...] = ("digi", "alfa") if args.platform == "both" else (args.platform,)

    print(f"Reading {args.input}")
    rows = read_input(args.input)
    print(f"  {len(rows)} data rows, {len(DIGI_HEADER)} DigiMall columns, "
          f"{len(ALFA_HEADER)} Alfa columns")

    flags = QCFlagCollector()
    prepared = read_rows(rows, vendor_cfg=vendor_cfg)
    records = run(rows, flags, prepared, vendor_cfg=vendor_cfg)

    labels = " + ".join("DigiMall" if p == "digi" else "Alfa" for p in scope)
    print(f"Writing the {labels} file{'s' if len(scope) > 1 else ''}")
    if "digi" in scope:
        write_csv(
            args.digi,
            DIGI_HEADER,
            [build_digi_row(r, vendor_cfg=vendor_cfg).values for r in records],
        )
    if "alfa" in scope:
        write_csv(
            args.alfa,
            ALFA_HEADER,
            [build_alfa_row(r, vendor_cfg=vendor_cfg).values for r in records],
        )
    flags.write_csv(args.qc, args.platform)
    write_title_sample(args.sample_titles, records)

    print_summary(records, flags, args.digi, args.alfa, prepared[1], args.platform)
    print()
    print(f"  QC report        : {args.qc}")
    print(f"  Title sample     : {args.sample_titles}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
