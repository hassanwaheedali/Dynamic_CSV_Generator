"""Section 6 -- the Title decision tree, applied per row.

Title formula (spec section 6)::

    [Brand] [Model] [Capacity] [Color] [Series/Feature] [Inverter] [Category]

Step A rebuilds the Title from those pieces when a real model code exists.
Step B keeps the source Title with light cleanup when there is no model code to
rebuild around -- the spec's Test Case 2 requires the source wording to survive
in that case, so this is a hard rule, not a preference.

Every optional token is skipped when the source never stated it: no capacity,
colour, series or inverter word is ever invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sku_handle import ModelExtraction, parse_capacity
from textutils import clean_inline, find_base_color

# ---------------------------------------------------------------------------
#  EDIT HERE -- title shaping rules
# ---------------------------------------------------------------------------
TITLE_MAX = 90

# Categories where an inverter / non-inverter distinction means something to a
# shopper.  A water dispenser or a TV must never grow an "Inverter" token.
INVERTER_CONCEPT_CATEGORIES: frozenset[str] = frozenset(
    {
        "Air Conditioner",
        "Refrigerator",
        "Deep Freezer",
        "Washing Machine",
    }
)

# Series names that may be added to a rebuilt Title.  Add a word here when the
# terminal summary reports it as a dropped source word.
SERIES_WORDS: tuple[str, ...] = (
    "Infinity",
    "Supreme",
    "Vintage",
    "Aurora",
    "Defender",
    "Mega",
    "Essential",
    "Classic",
    "Elegant",
    "Prime",
    "Ultra",
    "Grand",
    "Advance",
)

TAPS_RE = re.compile(r"\b(\d+)\s*-?\s*taps?\b", re.IGNORECASE)
SERIES_RE = re.compile(r"\b([A-Z][A-Za-z0-9+.\-]{1,20})\s+Series\b")
SERIES_WORD_RE = re.compile(
    "|".join(rf"\b{re.escape(word)}\b" for word in SERIES_WORDS), re.IGNORECASE
)
INVERTER_RE = re.compile(r"\binverter\b", re.IGNORECASE)
NON_INVERTER_RE = re.compile(r"\bnon[-\s]?inverter\b", re.IGNORECASE)

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "from", "that", "this", "your", "into",
        "series", "model", "brand", "new", "best", "price", "only",
    }
)


@dataclass(frozen=True)
class TitleResult:
    """One row's Title, the tokens it was built from, and how it was produced."""

    title: str
    strategy: str  # "rebuilt" | "kept-with-light-cleanup"
    capacity_token: str
    color_token: str
    series_token: str
    inverter_token: str
    dropped_words: tuple[str, ...]


# ---------------------------------------------------------------------------
#  Token helpers
# ---------------------------------------------------------------------------
def extract_series(text: str) -> str:
    """The series name the source itself states, or ``""``.

    Two spellings are honoured: an explicit ``"<Name> Series"`` label, and one
    of the curated :data:`SERIES_WORDS` appearing in the text.
    """
    match = SERIES_RE.search(text)
    if match:
        return match.group(1).strip()
    word = SERIES_WORD_RE.search(text)
    return word.group(0) if word else ""


def extract_taps(text: str) -> str:
    """``"3 Taps"`` when the source states a tap count, else ``""``."""
    match = TAPS_RE.search(text)
    return f"{match.group(1)} Taps" if match else ""


def extract_inverter(text: str) -> str:
    """``"Inverter"`` / ``"Non-Inverter"`` / ``""``.

    Non-inverter is tested first, because ``"non inverter"`` also contains the
    word ``"inverter"``.
    """
    if NON_INVERTER_RE.search(text):
        return "Non-Inverter"
    if INVERTER_RE.search(text):
        return "Inverter"
    return ""


def _trim_to_limit(title: str, limit: int) -> str:
    """Longest whole-word prefix within ``limit``, never ending on a stray
    conjunction or a half-written unit."""
    if len(title) <= limit:
        return title
    cut = title[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,-/")
    return cut or title[:limit].rstrip(" ,-/")


def dropped_words(source_title: str, final_title: str) -> tuple[str, ...]:
    """Meaningful source words the rebuild did not carry over.

    Reported so a human can add a genuine series name to :data:`SERIES_WORDS`
    instead of the rebuild silently losing information.
    """
    final = final_title.lower()
    missing: list[str] = []
    for word in re.findall(r"[A-Za-z0-9][A-Za-z0-9+.\-]{3,}", source_title):
        lowered = word.lower()
        if lowered in _STOPWORDS or lowered in final:
            continue
        if lowered.rstrip("s") in final:
            continue
        if lowered not in missing:
            missing.append(lowered)
    return tuple(missing)


# ---------------------------------------------------------------------------
#  Title
# ---------------------------------------------------------------------------
def build_title(
    brand: str,
    extraction: ModelExtraction,
    product_type: str,
    source_title: str,
    source_description: str,
) -> TitleResult:
    """Build one Title, choosing Step A (rebuild) or Step B (keep) by model
    confidence -- never by whether the rebuild happens to look nicer."""
    text = f"{source_title}\n{source_description}"
    capacity = parse_capacity(text)
    color = find_base_color(text) or ""
    taps = extract_taps(text)
    series = extract_series(text)
    inverter = ""
    if product_type in INVERTER_CONCEPT_CATEGORIES:
        inverter = extract_inverter(text)

    feature = taps or series
    if taps and series and series.lower() not in taps.lower():
        feature = f"{taps} {series}"

    if extraction.confidence in ("high", "medium"):
        pieces: list[str] = []
        for raw_piece in (brand, extraction.code, capacity, color, feature, inverter, product_type):
            piece = clean_inline(raw_piece)
            if not piece:
                continue
            if piece.lower() in " ".join(pieces).lower():
                continue
            pieces.append(piece)
        title = clean_inline(_trim_to_limit(" ".join(pieces), TITLE_MAX))
        strategy = "rebuilt"
    else:
        title = clean_inline(_trim_to_limit(clean_inline(source_title), TITLE_MAX))
        strategy = "kept-with-light-cleanup"

    return TitleResult(
        title=title,
        strategy=strategy,
        capacity_token=capacity,
        color_token=color,
        series_token=feature,
        inverter_token=inverter,
        dropped_words=dropped_words(source_title, title),
    )
