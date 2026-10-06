"""Section 9 -- pricing, quantity defaults, and the shared price pair.

The resolved ``(variant_price, variant_compare_at_price)`` pair is written
identically into both output files.
"""

from __future__ import annotations

from config import DEFAULT_VARIANT_QUANTITY as DEFAULT_VARIANT_QUANTITY  # edit in config.py
from models import InputRow
from qc_report import CAT_PRICE_INVERSION, CAT_QTY_DEFAULTED, QCFlagCollector


def parse_price(raw: str) -> int | None:
    """Parse a comma-formatted price string into an int, or ``None``."""
    cleaned = raw.replace(",", "").replace("\u00a0", "").strip()
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def resolve_prices(
    row: InputRow, flags: QCFlagCollector
) -> tuple[int, int]:
    """Return the shared ``(variant_price, variant_compare_at_price)`` pair.

    Never publishes a price inversion (Original < Sell) silently: the flagged
    row keeps the source numbers but the human is told, rather than the
    pipeline quietly inventing a "corrected" price.
    """
    sell = parse_price(row.sell_price)
    original = parse_price(row.original_price)

    if sell is None:
        sell = 0
        flags.flag(
            row.row_number,
            row.title,
            "input_error",
            f"Unparseable Sell Price {row.sell_price!r} -- written as 0, fix the source sheet.",
        )
    if original is None:
        original = sell
        flags.flag(
            row.row_number,
            row.title,
            "input_error",
            f"Unparseable Original Price {row.original_price!r} -- fell back to the sell price.",
        )

    if original < sell:
        flags.flag(
            row.row_number,
            row.title,
            CAT_PRICE_INVERSION,
            f"Price inversion: Original ({original}) < Sell ({sell}) -- "
            "looks like a data-entry mistake, not published as-is.",
        )
    return sell, original


def resolve_quantity(row: InputRow, flags: QCFlagCollector) -> int:
    """The input sheet has no stock column, so default to 20 and flag the row."""
    flags.flag(
        row.row_number,
        row.title,
        CAT_QTY_DEFAULTED,
        f"Input sheet has no stock column -- Variant Quantity defaulted to {DEFAULT_VARIANT_QUANTITY}.",
    )
    return DEFAULT_VARIANT_QUANTITY
