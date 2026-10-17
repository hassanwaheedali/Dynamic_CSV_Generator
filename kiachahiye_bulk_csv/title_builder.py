"""Section 6 -- the Title decision tree, applied per row.

Title formula (spec section 6)::

    [Brand] [Capacity] [Color] [Inverter/Non-Inverter] [Category Name]
    - [Model] [Series/Feature Keyword] - [Main Warranty]

When STRICT_TITLE_REBUILD is True in config.py, the Title is ALWAYS strictly
rebuilt from the pieces above. Titles kept as supplied are disabled.

When STRICT_TITLE_REBUILD is False, Step A rebuilds if a confident model code
exists, and Step B keeps the source Title with light cleanup otherwise.

Every optional token is skipped when the source never stated it: no capacity,
colour, series, inverter or warranty word is ever invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import series_corpus
from config import (
    OMIT_TITLE_COLOR_CATEGORIES as OMIT_TITLE_COLOR_CATEGORIES,
)
from config import (
    STRICT_TITLE_REBUILD as STRICT_TITLE_REBUILD,
)
from config import (
    TITLE_MAX as TITLE_MAX,
)
from series_corpus import Corpus, RowAnalysis
from sku_handle import ModelExtraction, find_series_token, parse_capacity
from textutils import clean_inline, find_full_color
from warranty import resolve_main_warranty

# ---------------------------------------------------------------------------
#  EDIT HERE -- title shaping rules
# ---------------------------------------------------------------------------


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
        "warranty", "warranties", "year", "years",
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
    warranty_token: str = ""
    series_name: str = ""
    """The name this row prints in its series slot, exactly as the run's vote chose it.

    Not :attr:`series_token`, which is the whole feature slot and may carry a feature word the vote
    never believed (`Blaze Google`).  A human asked to confirm a name must be shown the name.
    """

    series_earned_by: series_corpus.SeriesProof = ""


# ---------------------------------------------------------------------------
#  Token helpers
# ---------------------------------------------------------------------------
def extract_series(text: str) -> str:
    """The series name the source itself states, or ``""``.

    Two spellings are honoured: an explicit ``"<Name> Series"`` label, and one
    of the curated :data:`SERIES_WORDS` appearing in the text, falling back to
    any distinctive capitalised series word found by :func:`find_series_token`.
    """
    match = SERIES_RE.search(text)
    if match:
        return match.group(1).strip()
    word = SERIES_WORD_RE.search(text)
    if word:
        return word.group(0)
    return find_series_token(text)


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
CATEGORY_WORDS: frozenset[str] = frozenset(
    {
        "air", "conditioner", "conditioners", "split", "ac", "acs",
        "refrigerator", "refrigerators", "fridge", "fridges",
        "freezer", "freezers", "deep", "chest",
        "washing", "machine", "machines", "washer", "dryer",
        "microwave", "microwaves", "oven", "ovens",
        "water", "dispenser", "dispensers",
        "tv", "television", "led", "lcd",
        "cooler", "coolers", "purifier", "purifiers",
        "geyser", "geysers", "heater", "heaters",
    }
)

FEATURE_STOPWORDS: frozenset[str] = frozenset(
    {
        "with", "and", "the", "for", "in", "of", "to", "a", "an", "at", "by", "from",
        "series", "model", "new", "best", "price", "only", "pakistan", "buy",
        "top", "front", "load", "door", "doors", "less", "bezel", "wall", "mount",
        "set", "pcs", "size", "watt", "watts", "volt", "volts", "hz", "amp",
        "glass", "single", "double", "triple", "auto", "automatic", "semi", "manual",
        "fully", "full", "twin", "tub", "tubs", "tube", "tubes", "spin", "spinner", "loading",
        "type", "plus", "pro", "all", "hd", "fhd", "uhd",
        "freezer-on-top", "side-by-side", "french", "direct", "cool", "no-frost",
        "litre", "litres", "liter", "liters", "ltr", "ltrs",
        "inch", "inches", "ton", "tons", "kg", "kgs", "cu", "ft", "cuft", "cft",
        "tap", "taps",
    }
)


# EDIT HERE -- sub-category words that are core to a product type.  They are
# placed just before the category name:  "Fully Automatic Front Load Washing
# Machine".  Each product type has groups; per group the first label whose
# aliases appear in the SOURCE TITLE wins.  Add / remove entries freely.
SUBTYPES: dict[str, tuple[dict[str, tuple[str, ...]], ...]] = {
    "Washing Machine": (
        {
            "Semi Automatic": ("semi automatic", "semi auto"),
            "Twin Tub": ("twin tub",),
            "Fully Automatic": ("fully automatic", "fully auto", "automatic"),
        },
        {
            "Front Load": ("front load", "front loading"),
            "Top Load": ("top load", "top loading"),
        },
    ),
    "Air Conditioner": (
        {
            "Floor Standing": ("floor standing",),
            "Split": ("split",),
        },
        {
            "Heat & Cool": ("heat and cool", "heat cool", "cool and heat", "cool heat"),
            "Cool Only": ("cool only",),
        },
    ),
    "Deep Freezer": (
        {
            "Single Door": ("single door",),
            "Double Door": ("double door",),
        },
        {
            "Chest": ("chest",),
            "Vertical": ("vertical",),
        },
    ),
    "Refrigerator": (
        {
            # What kind of fridge it is, not which line it belongs to: a row saying
            # "No Frost" states the cooling type, while "Dawlance Frost 30" names the Frost
            # model. Reading the first as the second put a type word into [series].
            "No Frost": ("no frost", "frost free", "nofrost", "frostfree"),
        },
    ),
    "Geyser": (
        {"Instant": ("instant",)},
        {
            "Semi Electric": ("semi electric",),
            "Electric": ("electric",),
            "Gas": ("gas",),
        },
    ),
}


def extract_subtype(product_type: str, source_title: str) -> str:
    """Sub-category words the source title states, e.g. ``Fully Automatic Front Load``."""
    title = " " + re.sub(r"[^a-z]+", " ", source_title.lower()) + " "
    labels: list[str] = []
    for group in SUBTYPES.get(product_type, ()):
        for label, aliases in group.items():
            if any(f" {alias} " in title for alias in aliases):
                labels.append(label)
                break
    return " ".join(labels)


def extract_feature(
    text: str = "",
    product_type: str = "",
    source_title: str = "",
    brand: str = "",
    capacity: str = "",
    color: str = "",
    inverter: str = "",
    model: str = "",
    description: str = "",
    series: str | None = None,
) -> str:
    """Extract series and prominent feature keywords dynamically from text.

    `series` is the name the corpus proved for this row's brand; when the caller has one, it IS
    the series half of the slot and `extract_series` is not asked -- the curated path stays as the
    fallback for a corpus that proved nothing, so wiring the vote in can never shorten a Title.
    """
    full_text = f"{source_title}\n{description}" if (source_title or description) else text
    if not source_title and text:
        source_title = text.splitlines()[0]

    candidates: list[str] = []
    chosen = series if series is not None else extract_series(full_text)
    if chosen:
        candidates.append(chosen)

    # Air Fryer special check
    if re.search(r"\bair\s*fryer\b", full_text, re.IGNORECASE) and "Air Fryer" not in candidates:
        candidates.append("Air Fryer")

    # Extra prominent features (Google, Android, QLED, OLED, Grill, Baking, Convection, Solo)
    for feat in ("Google", "Android", "QLED", "OLED", "Grill", "Baking", "Convection", "Solo"):
        if re.search(rf"\b{re.escape(feat)}\b", full_text, re.IGNORECASE) and not any(
            feat.lower() in c.lower() for c in candidates
        ):
            candidates.append(feat)
            break

    return " ".join(candidates[:2])


def build_title(
    brand: str,
    extraction: ModelExtraction,
    product_type: str,
    source_title: str,
    source_description: str,
    warranty: str | None = None,
    strict_rebuild: bool | None = None,
    analysis: RowAnalysis | None = None,
    corpus: Corpus | None = None,
) -> TitleResult:
    """Build one Title using our formula.

    When strict_rebuild is True (configured by STRICT_TITLE_REBUILD in config.py),
    the Title is always strictly rebuilt from our standard formula:
    [Brand] [Capacity] [Color] [Inverter/Non-Inverter] [Category Name]
    - [Model] [Series/Feature Keyword] - [Main Warranty]

    When strict_rebuild is False, Step A rebuilds if a confident model code
    exists, and Step B keeps the source Title with light cleanup otherwise.

    `analysis` and `corpus` are the row's reading and the run's per-brand verdict, both produced by
    `series_corpus`; they arrive together or not at all.  A name the corpus proved for this brand
    fills the series slot in the row's own spelling; a corpus that proved nothing leaves the
    curated path in charge, so a Title can never be shortened by the vote being silent.
    """
    if strict_rebuild is None:
        strict_rebuild = STRICT_TITLE_REBUILD

    text = f"{source_title}\n{source_description}"
    if warranty is None:
        warranty = resolve_main_warranty(text, brand, product_type) or ""

    taps = extract_taps(text)
    capacity = parse_capacity(text)
    if taps:
        capacity = taps

    color = find_full_color(text, source_title) or ""
    inverter = ""
    if product_type in INVERTER_CONCEPT_CATEGORIES:
        inverter = extract_inverter(text)

    corpus_series: str | None = None
    carried_subtype = ""
    series_earned_by: series_corpus.SeriesProof = ""
    if analysis is not None and corpus is not None:
        chosen = series_corpus.pick_candidate(brand, analysis, corpus)
        if chosen is not None:
            corpus_series = chosen.source
            evidence = corpus.evidence(brand, chosen.key)
            series_earned_by = "" if evidence is None else evidence.earned_by
            curated = extract_series(text)
            if curated and curated != corpus_series and series_corpus.names_a_class(curated):
                # The old series guesser sold this row's TYPE as its series name.  The corpus
                # replaced it with the real name, but the word still says what the machine is --
                # and DigiMall's `Attribute_... Type` cell is matched out of this Title, so
                # dropping it would empty a platform column.  It belongs in the [Subtype] slot.
                carried_subtype = curated

    feature = extract_feature(
        text=text,
        product_type=product_type,
        source_title=source_title,
        brand=brand,
        capacity=capacity,
        color=color,
        inverter=inverter,
        model=extraction.code,
        description=source_description,
        series=corpus_series,
    )

    should_rebuild = strict_rebuild or (extraction.confidence in ("high", "medium"))
    slot_printed = False

    if should_rebuild:
        title_color = "" if product_type in OMIT_TITLE_COLOR_CATEGORIES else color
        subtype = extract_subtype(product_type, source_title) or carried_subtype
        part1_pieces: list[str] = []
        for raw_piece in (brand, capacity, title_color, inverter, subtype, product_type):
            piece = clean_inline(raw_piece)
            if not piece:
                continue
            if piece.lower() in " ".join(part1_pieces).lower():
                continue
            part1_pieces.append(piece)
        part1 = " ".join(part1_pieces)

        part2_pieces: list[str] = []
        if extraction.confidence in ("high", "medium") and extraction.code:
            part2_pieces.append(clean_inline(extraction.code))
        elif extraction.code and extraction.source != "fallback":
            clean_code = clean_inline(extraction.code)
            brand_token = re.sub(r"[^A-Za-z0-9]", "", brand).upper()
            if brand_token and clean_code.upper().startswith(f"{brand_token}-"):
                clean_code = clean_code[len(brand_token) + 1:].strip()
            if clean_code and clean_code.lower() not in part1.lower():
                part2_pieces.append(clean_code)
        if feature:
            clean_feat = clean_inline(feature)
            printed = f"{part1} {' '.join(part2_pieces)}".lower()

            def already_printed(word: str) -> bool:
                """Whether this word already stands in the Title as a word of its own.

                A substring test used to drop the `E` of `E Luxury Pro` because `E` is inside
                `Kenwood`, and sold the row as somebody else's line.  A name is repeated by a
                dedupe, never by its letters -- so a row whose name is ALSO a run inside its own
                part number (`H40K85EFX` + `K85 Series`) prints the name and reads redundant.  Seven
                rows do this; hiding the name to avoid the redundancy would repeat the very defect
                the reading layer was built to kill.  Shortlist for T8, not a rule here.
                """
                return (
                    re.search(rf"(?<![a-z0-9]){re.escape(word.lower())}(?![a-z0-9])", printed)
                    is not None
                )

            feat_words = [
                w for w in clean_feat.split()
                if not already_printed(w)
                and not (product_type in OMIT_TITLE_COLOR_CATEGORIES and color and w.lower() == color.lower())
            ]
            if feat_words:
                part2_pieces.append(" ".join(feat_words))
            # The voted name counts as printed only when EVERY one of its words survived the dedupe
            # above.  On the Orient `Icon` rows the name is a word of the model code, so the slot
            # empties and a substring test on the finished Title would still hit; on the Kenwood
            # `eLuxury Pro` rows the code swallows `Pro` and only half the name is left.  A half
            # name is not the name, and QC would ask a human to confirm something the shelf never
            # read.
            slot_printed = all(
                word in feat_words for word in clean_inline(corpus_series or "").split()
            ) and bool(clean_inline(corpus_series or ""))
        part2 = " ".join(part2_pieces)

        part3 = ""
        if warranty:
            clean_warr = clean_inline(warranty)
            if (
                clean_warr.lower() not in part2.lower()
                and clean_warr.lower() not in part1.lower()
            ):
                part3 = clean_warr

        segments = [s for s in (part1, part2, part3) if s]
        combined = " - ".join(segments)

        title = clean_inline(_trim_to_limit(combined, TITLE_MAX))
        strategy = "rebuilt"
    else:
        base_title = clean_inline(source_title)
        if product_type in OMIT_TITLE_COLOR_CATEGORIES and color:
            base_title = re.sub(rf"\b{re.escape(color)}\b", "", base_title, flags=re.IGNORECASE)
            base_title = re.sub(r"\s{2,}", " ", base_title).strip()
        if warranty:
            clean_warr = clean_inline(warranty)
            if clean_warr.lower() not in base_title.lower():
                if " - " in base_title:
                    base_title = f"{base_title} {clean_warr}"
                elif base_title.endswith("-"):
                    base_title = f"{base_title.rstrip('-').strip()} - {clean_warr}"
                else:
                    base_title = f"{base_title} - {clean_warr}"
        title = clean_inline(_trim_to_limit(base_title, TITLE_MAX))
        strategy = "kept-with-light-cleanup"

    # The name reached the series slot; this is the other half of the question -- did it survive the
    # length limit?  `_trim_to_limit` runs after the assembly, so a Title cut down to TITLE_MAX would
    # otherwise report a name the shop never actually sees.
    name_printed = slot_printed and all(
        word.lower() in title.lower() for word in clean_inline(corpus_series or "").split()
    )
    return TitleResult(
        title=title,
        strategy=strategy,
        capacity_token=capacity,
        color_token=color,
        series_token=feature,
        inverter_token=inverter,
        # Recorded only when the voted name really reached the shelf's series slot: a word the
        # dedupe swallowed, or a Title kept from source, is not a name the shop read from the vote.
        series_name=corpus_series if name_printed and corpus_series else "",
        series_earned_by=series_earned_by if name_printed else "",
        dropped_words=dropped_words(source_title, title),
        warranty_token=warranty,
    )


