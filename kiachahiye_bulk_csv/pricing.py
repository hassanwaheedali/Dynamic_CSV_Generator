"""Section 9 -- pricing, quantity defaults, and the shared price pair.

The resolved ``(variant_price, variant_compare_at_price)`` pair is written
identically into both output files.
"""

from __future__ import annotations

from config import COMPARE_AT_MARKUP_PERCENT
from config import DEFAULT_VARIANT_QUANTITY as DEFAULT_VARIANT_QUANTITY  # edit in config.py
from models import InputRow
from qc_report import (
    CAT_COMPARE_AT_DERIVED,
    CAT_PRICE_INVERSION,
    CAT_QTY_DEFAULTED,
    QCFlagCollector,
)


def parse_price(raw: str) -> int | None:
    """Parse a comma-formatted price string into an int, or ``None``."""
    cleaned = raw.replace(",", "").replace("\u00a0", "").strip()
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def round_up_to_round_figure(value: int, price: int) -> int:
    """Round ``value`` UP to the round figure that suits ``price``'s own size.

    The step is read off the Sell Price's digit count instead of a threshold table, so a strike-
    through is as round as the number above which it sits: 61,499 -> 68,000 (nearest 1,000) and
    163,999 -> 190,000 (nearest 10,000).  Only ever larger, so a discount always survives.
    """
    step = 10 ** max(0, len(str(price)) - 2)
    return -(-value // step) * step


def derive_compare_at(sell: int) -> int:
    """The Variant Compare At Price for a row whose sheet states no usable Regular Price.

    Sell Price plus ``COMPARE_AT_MARKUP_PERCENT``, rounded up to a round figure (exact integer
    arithmetic, so a half-rupee is never lost).  Returns 0 for a row with no sell price at all --
    nothing can be built out of a price the pipeline does not have.
    """
    if sell <= 0:
        return 0
    marked_up = -(-sell * (100 + COMPARE_AT_MARKUP_PERCENT) // 100)
    return round_up_to_round_figure(marked_up, sell)


def resolve_prices(row: InputRow, flags: QCFlagCollector) -> tuple[int, int]:
    """Return the shared ``(variant_price, variant_compare_at_price)`` pair.

    A Regular Price the shop wrote is published exactly as written -- but only when it really is
    a strike-through, i.e. above the Sell Price.  A blank, unreadable, equal or smaller cell states
    no discount, so the Compare At is derived from the Sell Price instead; the row is flagged
    either way, because the sheet is where the fix belongs.
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

    if original is not None and original > sell:
        return sell, original

    if original is None:
        if row.original_price.strip():
            flags.flag(
                row.row_number,
                row.title,
                "input_error",
                f"Unparseable Original Price {row.original_price!r} -- derived from the sell price.",
            )
    else:
        flags.flag(
            row.row_number,
            row.title,
            CAT_PRICE_INVERSION,
            f"Regular Price {original} is not above the Sell Price {sell} -- ignored, and "
            "a Variant Compare At Price derived from the Sell Price instead. Fix the source sheet.",
        )

    compare_at = derive_compare_at(sell)
    if compare_at > sell:
        flags.flag(
            row.row_number,
            row.title,
            CAT_COMPARE_AT_DERIVED,
            f"Variant Compare At Price {compare_at} derived from Sell Price {sell} "
            f"(+{COMPARE_AT_MARKUP_PERCENT}%, rounded up) -- no usable Regular Price in the sheet.",
        )
    return sell, compare_at


def resolve_quantity(row: InputRow, flags: QCFlagCollector) -> int:
    """The input sheet has no stock column, so default to 20 and flag the row."""
    flags.flag(
        row.row_number,
        row.title,
        CAT_QTY_DEFAULTED,
        f"Input sheet has no stock column -- Variant Quantity defaulted to {DEFAULT_VARIANT_QUANTITY}.",
    )
    return DEFAULT_VARIANT_QUANTITY
