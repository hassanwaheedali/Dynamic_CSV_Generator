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
from typing import Literal

import description_builder
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


SubtypeSource = Literal["", "label", "list", "carried"]
"""Which rung of the ladder filled the `[Subtype]` slot for one row."""


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

    subtype_token: str = ""
    """The words that filled this row's `[Subtype]` slot, in the order they print."""

    subtype_from: SubtypeSource = ""
    """Which rung filled the slot: the sheet's own `SubType:` line, the type list, or the series
    carry-over.  ``""`` means nothing claimed it -- which is the safe answer, not a failure."""

    subtype_label_added: bool = False
    """Whether a `SubType:` line was written AND its words reached the Title.

    A line whose every word the Title already prints (`SubType: Air Conditioner`) adds nothing; the
    row ships as it did before, and he wants to be told, because he checks those lines by hand.
    """

    subtype_line: str = ""
    """What the row's `SubType:` line said, verbatim, whether or not it was used -- the flag needs
    to quote the line back to the person who wrote it, and re-parsing the Description for that would
    read it a second way."""

    subtype_label_note: str = ""
    """Why a written `SubType:` line added no word, in the builder's own knowledge: the row kept its
    source wording, the line restates what the Title already prints, or the value was a sentence.
    Empty when the line was used."""


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
            # Most specific first: a row that writes `Wall Mounted Split` is one machine, and
            # printing the shorter `Split` alone costs the shop its `Attribute_Air Conditioner Type`
            # value (measured: 25 rows fell from `Wall Mounted Split`/`Wall Mounted` to `Split`).
            "Wall Mounted Split": ("wall mounted split",),
            "Wall Mounted": ("wall mounted",),
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


def _spaced_words(text: str) -> str:
    """Lower-case the text and cut every non-letter to a space, padded so word tests are exact."""
    return " " + re.sub(r"[^a-z]+", " ", text.lower()) + " "


def word_printed(word: str, printed: str) -> bool:
    """Whether this word already stands in the text as a word of its own.

    A substring test used to drop the `E` of `E Luxury Pro` because `E` is inside `Kenwood`, and
    sold the row as somebody else's line.  A name is repeated by a dedupe, never by its letters --
    so a row whose name is ALSO a run inside its own part number (`H40K85EFX` + `K85 Series`)
    prints the name and reads redundant.  Seven rows do this; hiding the name to avoid the
    redundancy would repeat the very defect the reading layer was built to kill.  Shortlist for T8,
    not a rule here.

    The boundary class carries `.` as well as letters and digits, or the `5` of `SubType: 5 Star`
    counts as already printed by a `1.5 Ton` capacity.
    """
    return re.search(rf"(?<![\w.]){re.escape(word.lower())}(?![\w.])", printed.lower()) is not None


#: Punctuation that ends a vendor's statement -- one clause, one claim.
_CLAUSE_RE = re.compile(r"[^.;,•·\n\r\t]+")
#: A type word standing behind one of these in its own clause was denied, not stated.
_NEGATION_RE = re.compile(r"\b(?:not|no|without|never|nor)\b")


def _clauses(text: str) -> list[str]:
    """The row's text cut into squashed clauses -- the unit a vendor negates inside.

    `Not electric, gas only` answers two questions in one sentence, and a phrase match over the whole
    Description ships that geyser as `Electric` -- a wrong value in a closed attribute list, which is
    the failure `attributes.py` guards against by putting negations before their positives.  Here a
    negation governs its own clause and no other.
    """
    return [_spaced_words(clause) for clause in _CLAUSE_RE.findall(text)]


def _group_label(group: dict[str, tuple[str, ...]], clauses: list[str]) -> str:
    """The first label in this group whose any alias stands, un-negated, in one clause."""
    for label, aliases in group.items():
        for alias in aliases:
            needle = _spaced_words(alias)
            for clause in clauses:
                start = clause.find(needle)
                if start >= 0 and not _NEGATION_RE.search(clause[:start]):
                    return label
    return ""


def extract_subtype(product_type: str, source_title: str, source_description: str = "") -> str:
    """Sub-category words the row states, e.g. ``Fully Automatic Front Load``.

    The Title answers for a group first, because that is the sentence the buyer sees; the
    Description only fills a group the Title said nothing about, so it can add ``Heat & Cool`` to a
    row that wrote ``Split`` but never it -- and never overwrite the row's own word.
    """
    title_clauses = _clauses(source_title)
    row_clauses = title_clauses + _clauses(source_description)
    labels: list[str] = []
    for group in SUBTYPES.get(product_type, ()):
        labels.append(_group_label(group, title_clauses) or _group_label(group, row_clauses))
    return " ".join(label for label in labels if label)


#: A sub-type names what the machine is; a sentence after `SubType:` is a vendor answering a
#: different question.  Four words is the longest real one on these sheets (`Split DC Inverter AC`).
SUBTYPE_MAX_WORDS = 4


def subtype_line_words(value: str, said_already: str) -> tuple[list[str], str]:
    """The words of a `SubType:` line that the row has not already printed, and why if none.

    Punctuation at the ends of the value goes; a sign BETWEEN two words stays, because
    `Heat & Cool` is how he wrote it and how the shelf must read it.  A value that repeats the
    model code, the warranty or the category is refused word by word, because a Title that says the
    SKU twice is a row shadowing itself.
    """
    if not value:
        return [], ""
    line_words = value.strip(" .,:;-–—").split()
    if len(line_words) > SUBTYPE_MAX_WORDS:
        return [], (
            f"is {len(line_words)} words long -- a sub-type is 1-{SUBTYPE_MAX_WORDS} words, "
            "so nothing was added"
        )
    kept: list[str] = []
    for index, word in enumerate(line_words):
        if not re.search(r"[A-Za-z0-9]", word):
            if 0 < index < len(line_words) - 1 and kept:
                kept.append(word)
            continue
        if word_printed(word, said_already) or word_printed(word, " ".join(kept)):
            continue
        kept.append(word)
    if kept:
        return kept, ""
    return [], "states only words this Title already prints"


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
    subtype: str = ""
    subtype_from: SubtypeSource = ""
    title_color = "" if product_type in OMIT_TITLE_COLOR_CATEGORIES else color
    label_value = clean_inline(description_builder.subtype_label(source_description))
    # A word the Title prints anyway is not a sub-type word: `SubType: Air Conditioner` states the
    # category, and `Double Door Refrigerator` exactly one word more than `Double Door`.  The model
    # code and the warranty are refused for the same reason -- a Title carrying its own SKU twice is
    # a row shadowing itself.  Read before the rebuild test, because a row kept from source still
    # has a Title, and he is owed the truth about his line either way.
    said_already = " ".join(
        (brand, capacity, title_color, color, inverter, product_type, extraction.code, warranty)
    )
    kept_words, label_note = subtype_line_words(label_value, said_already)
    listed_subtype = extract_subtype(product_type, source_title, source_description)
    if kept_words and " ".join(kept_words).lower() == listed_subtype.lower():
        label_note = "restates the word this row's own type already gives"

    if should_rebuild:
        if kept_words:
            subtype, subtype_from = " ".join(kept_words), "label"
        else:
            # His line said nothing, so the row is built exactly as it was before the line existed.
            subtype = listed_subtype or carried_subtype
            subtype_from = "list" if listed_subtype else ("carried" if carried_subtype else "")
        # When his line overrules the word the row wrote, that word is still a TYPE word, and a
        # type word with no slot to stand in must not be resold as the series keyword behind the
        # model code -- `... Air Conditioner - HSU-19HFPCAA Split` describes two machines.
        sold_words = (
            {w.lower() for w in f"{listed_subtype} {carried_subtype}".split()} if kept_words else set()
        )
        part1_pieces: list[str] = []
        for raw_piece in (brand, capacity, title_color, inverter, subtype, product_type):
            piece = clean_inline(raw_piece)
            if not piece:
                continue
            joined = " ".join(part1_pieces)
            # Word-level, never letters: `Gas` is a type word even next to a brand called `Nasgas`,
            # and a substring test here drops the row's own sub-type on the way to the category name.
            if joined and all(word_printed(word, joined) for word in piece.split()):
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

            feat_words = [
                w for w in clean_feat.split()
                if not word_printed(w, printed)
                and w.lower() not in sold_words
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
    # Same question for his line: it only counts as added if the words reached the shipped Title.
    # Tested against the Title, not against which rung the builder claims, because a Title kept from
    # source may well print the very word he wrote -- and then his line was not ignored.
    label_printed = bool(kept_words) and all(word_printed(word, title) for word in kept_words)
    subtype_printed = bool(subtype) and all(word_printed(word, title) for word in subtype.split())
    if label_value and not label_printed and not label_note:
        if strategy != "rebuilt":
            label_note = "this row keeps its own source wording"
        elif kept_words:
            label_note = "its words were cut by the Title's length limit"
        else:
            label_note = "states only words this Title already prints"
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
        subtype_token=subtype if subtype_printed else "",
        subtype_from=subtype_from if subtype_printed else "",
        subtype_label_added=label_printed,
        subtype_line=label_value,
        subtype_label_note="" if label_printed else label_note,
    )


