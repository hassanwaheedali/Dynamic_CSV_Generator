"""Section 7 -- model extraction, SKU, Handle, uniqueness.

SKU shape (user's ruling, locked)::

    KIA-[model]-[variant]      e.g. KIA-WD-1051HC
                                    KIA-9193-WB-16CUFT-MEADOWGREEN

The bare ``KIA-<model>`` is used whenever it is unique across the run.  A
variant suffix is added **only** when the same model code repeats across
genuinely different products, and it is built from dimensions the source
actually stated: capacity, colour, taps, series/generation.  A final ``-2`` /
``-3`` numeric suffix guarantees uniqueness in the worst case and is always
reported so the source sheet can be fixed.

Model extraction order (spec section 7, tightened against the real sheet):

1. an explicit ``Model:`` / ``Model Name:`` label in the Description  -> high
2. the last parenthetical group in the Title that contains a digit    -> high
3. an alphanumeric code token that mixes letters and digits           -> medium
4. nothing found                                                      -> fallback

A parenthetical group with no digit is never a model code: the sheet contains
``(Cool Only)``, which is a feature, not a code.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from textutils import dedupe_preserve_order, find_base_color, normalize, slugify

# ---------------------------------------------------------------------------
#  EDIT HERE -- model, SKU and Handle shaping rules
# ---------------------------------------------------------------------------
SKU_PREFIX = "KIA"
HANDLE_MAX = 65

# Words that carry no model information.  Extend this list if a fallback SKU in
# the terminal summary looks like junk.
TYPE_WORDS: frozenset[str] = frozenset(
    {
        "air", "conditioner", "conditioners", "ac", "acs", "refrigerator",
        "refrigerators", "fridge", "fridges", "freezer", "freezers", "deep",
        "washing", "machine", "machines", "washer", "dryer", "microwave",
        "microwaves", "oven", "ovens", "fryer", "fryers", "airfryer", "airfryers",
        "dispenser", "dispensers", "water",
        "tv", "television", "led", "lcd", "smart", "qled", "uhd", "fhd", "hd",
        "audio", "video", "visuals", "sound", "bar", "bars", "speaker",
        "speakers", "ups", "geyser", "geysers", "heater", "heaters", "cooler",
        "coolers", "fan", "fans", "purifier", "purifiers", "humidifier",
        "humdifier", "inverter", "series", "with", "without", "and", "the",
        "new", "pro", "plus", "inch", "inches", "ton", "pcs", "set", "latest",
        "taps", "tap", "ltr", "ltrs", "liter", "liters", "litre", "litres",
        "kg", "kgs", "cuft", "cft", "watt", "watts", "volt", "volts",
        "technology", "electric", "digital", "automatic", "semi", "auto",
        "fully", "full", "twin", "tub", "tubs", "tube", "tubes", "spin", "spinner", "loading",
        "manual", "top", "front", "load", "double", "single", "door", "doors",
        "glass", "steel", "compressor", "cool", "cooling", "heat", "heating",
        "hot", "cold", "only", "high", "low", "best", "price", "pakistan",
        "buy", "google", "dolby", "turbo", "wide", "color", "colour", "gamut",
        "black", "white", "silver", "grey", "gray", "red", "blue", "golden",
        "gold", "maroon", "green", "brown", "bezel", "less",
    }
)

MODEL_LABEL_RE = re.compile(
    r"(?im)^[ \t]*(?:•\s*)?model(?:\s*(?:name|no\.?|number|code))?\s*:?\t?\s*"
    r"(?P<value>[^\n\r]+)$"
)
TAPS_RE = re.compile(r"\b(\d+)\s*-?\s*taps?\b", re.IGNORECASE)
WEIGHT_LINE_RE = re.compile(
    r"(?im)^[ \t]*(?:•\s*)?(?:set\s+|net\s+|gross\s+|product\s+)?weight[^\n]*$"
)
# "net Weight: 14.45 kg" written inside a sentence (not at the start of a line).
INLINE_WEIGHT_RE = re.compile(
    r"(?i)\bweight\s*[:\-]?\s*\d+(?:\.\d+)?\s*(?:kgs?|kilograms?|g|grams?|lbs?|oz)\b"
)
# Capacity: only units that really describe a product's size.
CAPACITY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:cu\.?\s*ft\.?|cubic\s+feet|cuft)\b", re.IGNORECASE), "Cu Ft"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:cft)\b", re.IGNORECASE), "Cu Ft"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:kg|kgs|kilograms?)\b", re.IGNORECASE), "KG"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:ton|tons)\b", re.IGNORECASE), "Ton"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:inch|inches)\b", re.IGNORECASE), "Inch"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:ltrs?|litres?|liters?)\b(?!\s*(?:/|per\b))", re.IGNORECASE), "Ltr"),
)
# A code token mixes letters and digits, with at least one dash/slash chunk.
CODE_TOKEN_RE = re.compile(
    r"\b(?=[A-Za-z0-9][A-Za-z0-9\-/()]*[0-9])"
    r"(?=[A-Za-z0-9][A-Za-z0-9\-/()]*[A-Za-z])"
    r"[A-Za-z]{1,6}[A-Za-z0-9]*(?:[-/][A-Za-z0-9()]+)+\b"
)
CAPACITY_ONLY_RE = re.compile(
    r"(?i)^\s*\d+(?:\.\d+)?\s*(?:cu\.?\s?ft\.?|liter|litre|ltr|kg|ton|inch|"
    r"inches|watt|watts|w|v|volt|volts|taps?|star)\s*$"
)
TRAILING_DIGITS_RE = re.compile(r"(?:^|[-_])(\d+)$")
DIMENSION_VARIANT_RE = re.compile(r"^(\d+(?:\.\d+)?)([A-Za-z]+)(?:([-_].*))?$")



@dataclass(frozen=True)
class ModelExtraction:
    """The model code a row resolved to, and how confident that is.

    ``source`` is one of ``description-model-line``, ``title-parenthetical``,
    ``title-code-token`` or ``fallback``; ``confidence`` is ``high``,
    ``medium`` or ``none``.
    """

    code: str
    source: str
    confidence: str


# ---------------------------------------------------------------------------
#  Model extraction
# ---------------------------------------------------------------------------
def _last_paren_group(text: str) -> str | None:
    """Content of the last *outermost* ``(...)`` group, nesting-aware."""
    end = text.rfind(")")
    if end == -1:
        return None
    depth = 0
    for index in range(end, -1, -1):
        char = text[index]
        if char == ")":
            depth += 1
        elif char == "(":
            depth -= 1
            if depth == 0:
                return text[index + 1 : end]
    return None


def clean_model_code(value: str) -> str:
    """Tidy a raw model code, dropping a trailing colour word.

    ``"WD-1051 HC White"`` -> ``"WD-1051 HC"``.  Only a *base* colour name is
    stripped, never a colour phrase, so a code like ``WD-1051 HC`` keeps its
    ``HC``.
    """
    cleaned = re.sub(r"\s+", " ", value.replace("®", " ").replace("™", " ")).strip()
    cleaned = re.split(r"\s{2,}|\t", cleaned)[0].strip()
    base = find_base_color(cleaned)
    if base:
        stripped = re.sub(rf"(?i)\b{re.escape(base)}\b", " ", cleaned)
        if stripped.strip(" -,"):
            cleaned = stripped
    # Stripping the colour must not leave debris behind: ".. (ARC-P1 White)" has
    # to become ".. (ARC-P1)", never ".. (ARC-P1  )".
    cleaned = re.sub(r"\s+([)\]}])", r"\1", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip(" -–—/,").strip()


def compact_model(model: str) -> str:
    """SKU/Handle form of a model code: ``WD-1051 HC`` -> ``WD-1051HC``."""
    compact = model.upper().replace("/", "-").replace("(", "").replace(")", "")
    compact = re.sub(r"\s+", "", compact)
    compact = re.sub(r"[^A-Z0-9\-.]+", "", compact)
    return re.sub(r"-{2,}", "-", compact).strip("-.")


def _usable_code(candidate: str) -> bool:
    """Reject anything that carries no model information."""
    value = candidate.strip()
    if len(value) < 3 or len(value) > 40:
        return False
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        return False
    return not CAPACITY_ONLY_RE.match(value)


def extract_model(title: str, description: str) -> ModelExtraction:
    """Resolve one row's model code, most trustworthy source first."""
    match = MODEL_LABEL_RE.search(description)
    if match:
        value = clean_model_code(match.group("value"))
        if _usable_code(value):
            return ModelExtraction(value, "description-model-line", "high")

    group = _last_paren_group(title)
    if group:
        value = clean_model_code(group)
        if _usable_code(value):
            return ModelExtraction(value, "title-parenthetical", "high")

    if " - " in title:
        after_dash = title.rsplit(" - ", 1)[-1].strip()
        first_token = after_dash.split()[0] if after_dash else ""
        cleaned = clean_model_code(first_token)
        if _usable_code(cleaned):
            return ModelExtraction(cleaned, "title-after-hyphen", "high")

    for candidate in reversed(CODE_TOKEN_RE.findall(title)):
        value = clean_model_code(candidate)
        if _usable_code(value):
            return ModelExtraction(value, "title-code-token", "medium")

    for candidate in reversed(re.findall(r"\b[A-Za-z0-9]{4,15}\b", title)):
        cleaned = clean_model_code(candidate)
        if _usable_code(cleaned) and re.search(r"[A-Za-z]", cleaned) and re.search(r"\d", cleaned):
            return ModelExtraction(cleaned, "title-code-token", "medium")

    return ModelExtraction("", "fallback", "none")


def find_series_token(text: str) -> str:
    """A series name stated by the source, for use in a fallback model.

    Looks for an explicit ``"<Name> Series"`` label first, then the first
    distinctive capitalised word in the title -- skipping the brand itself (the
    first word in this sheet), product-type words and all-caps acronyms.
    """
    labelled = re.search(r"\b([A-Z][A-Za-z0-9+.\-]{1,20})\s+Series\b", text)
    if labelled:
        return labelled.group(1).strip()

    title = text.splitlines()[0] if text else ""
    # A sheet typed entirely in capitals carries no casing signal, so there an
    # all-caps word is not evidence of an acronym.
    shouty = title.upper() == title
    words: list[str] = re.findall(r"[A-Za-z][A-Za-z0-9+.\-]+", title)
    for index, word in enumerate(words):
        if index == 0:  # the leading word is the brand in this sheet
            continue
        key = normalize(word)
        if len(key) < 3 or key in TYPE_WORDS:
            continue
        if shouty:
            if _is_code_like(word) or not _has_vowel(word):
                continue
        elif word.isupper() or lookup_is_acronym(word):
            continue
        return word
    return ""


def _is_code_like(word: str) -> bool:
    """True for a model code token such as ``MSAG2B-12HRDN1-QC0``."""
    return bool(re.search(r"\d", word) or "-" in word or "." in word)


def _has_vowel(word: str) -> bool:
    """True for a pronounceable marketing word; rejects ``DC`` and ``HTZ``."""
    return bool(re.search(r"[AEIOUY]", word.upper()))


def lookup_is_acronym(word: str) -> bool:
    """True for short all-consonant marketing tokens like ``HD`` or ``TV``."""
    return len(word) <= 4 and word.upper() == word


def build_fallback_model(
    brand: str, series: str, capacity: str, title: str
) -> str:
    """A readable, stable model stand-in for a row with no formal code.

    ``Dawlance ... Kore 32 Inch ...`` becomes ``DAWLANCE-KORE-32``.  Every row
    built this way is flagged for a human.
    """
    pieces: list[str] = []
    if brand:
        pieces.append(re.sub(r"[^A-Za-z0-9]", "", brand).upper())
    if series and series.upper() not in pieces:
        pieces.append(re.sub(r"[^A-Za-z0-9]", "", series).upper())
    digits = re.match(r"\d+(?:\.\d+)?", capacity or "")
    if digits:
        pieces.append(digits.group(0).replace(".", ""))
    if len(pieces) <= 1:
        fallback = find_series_token(title)
        if fallback:
            pieces.append(re.sub(r"[^A-Za-z0-9]", "", fallback).upper())
    return "-".join(piece for piece in pieces if piece) or "PRODUCT"


# ---------------------------------------------------------------------------
#  Capacity
# ---------------------------------------------------------------------------
def parse_capacity(text: str) -> str:
    """The product's own stated size, e.g. ``16 Cu Ft``, ``1.5 Ton``.

    Weight lines are blanked out first: ``Weight: 17.25 kg`` describes shipping,
    not the product's capacity, and the spec forbids putting it in the Title.
    """
    cleaned = WEIGHT_LINE_RE.sub(" ", text)
    cleaned = INLINE_WEIGHT_RE.sub(" ", cleaned)
    cleaned = re.sub(r"(?im)^[ \t]*.*tank.*$", " ", cleaned)
    for pattern, unit in CAPACITY_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            number = match.group(1)
            number = number.removesuffix(".0")
            return f"{number} {unit}"
    return ""


# ---------------------------------------------------------------------------
#  Variant tokens -- only used to break a real collision
# ---------------------------------------------------------------------------
def extract_variant_tokens(
    text: str, capacity: str, brand: str
) -> tuple[str, ...]:
    """Ordered, source-backed dimensions that separate equal model codes.

    Capacity, colour and taps always come first (the dimensions the sheet
    repeats most); a stated series or a ``T3 Pro`` generation marker follows.
    Nothing is invented: a dimension the source never stated contributes
    nothing.
    """
    tokens: list[str] = []
    brand_key = normalize(brand)

    if capacity:
        tokens.append(capacity.replace(" ", "").upper())

    base_color = find_base_color(text)
    if base_color and base_color.lower() != brand_key:
        tokens.append(re.sub(r"[^A-Za-z0-9+]+", "", base_color).upper())

    taps = TAPS_RE.search(text)
    if taps:
        tokens.append(f"{taps.group(1)}TAPS")

    series = re.search(r"\b([A-Z][A-Za-z0-9+.\-]{1,20})\s+Series\b", text)
    if series:
        name = re.sub(r"[^A-Za-z0-9+]+", "", series.group(1)).upper()
        if name and name not in tokens:
            tokens.append(name)

    if re.search(r"\bT3\s+Pro\b", text, re.IGNORECASE):
        tokens.append("T3PRO")
    elif re.search(r"\bnon[-\s]?T3\b", text, re.IGNORECASE):
        tokens.append("NONT3")

    deduped = [token for token in dedupe_preserve_order(tokens) if token]
    return tuple(token for token in deduped if token.lower() != brand_key)


def format_variant(tokens: tuple[str, ...]) -> str:
    """``("1.5 Ton", "White", "3 Taps")`` -> ``"1.5TON-WHITE-3TAPS"``."""
    return "-".join(token.upper().replace(" ", "") for token in tokens if token)


def taps_conflict(title: str, description: str) -> tuple[str, str] | None:
    """``(title_taps, description_taps)`` when the two disagree.

    The SKU's variant token comes from the Title, so a Description stating a
    different tap count is a source data error a human should see.
    """
    title_taps = TAPS_RE.search(title)
    description_taps = TAPS_RE.search(description)
    if title_taps is None or description_taps is None:
        return None
    if title_taps.group(1) == description_taps.group(1):
        return None
    return f"{title_taps.group(1)} Taps", f"{description_taps.group(1)} Taps"


# ---------------------------------------------------------------------------
#  SKU / Handle builders
# ---------------------------------------------------------------------------
def build_sku_token(model: str) -> str:
    """``KIA-`` plus the compact, upper-cased model code."""
    return f"{SKU_PREFIX}-{compact_model(model)}".strip("-")


def build_handle_token(model: str, product_type: str) -> str:
    """Lower-case, hyphenated Handle, capped so it stays importable."""
    stem = slugify(compact_model(model))
    suffix = slugify(product_type)
    handle = "-".join(part for part in (stem, suffix) if part)
    if len(handle) > HANDLE_MAX:
        handle = handle[:HANDLE_MAX].rstrip("-")
    return handle


def _collapse_dimension_stutter(
    base: str, variant: str, base_digits: str
) -> str | None:
    """Collapse repeating numbers when the variant starts with a unit-bearing dimension."""
    m_var = DIMENSION_VARIANT_RE.match(variant)
    if not m_var:
        return None

    var_num = m_var.group(1)
    unit = m_var.group(2)
    rest = m_var.group(3) or ""

    if base_digits not in (var_num.replace(".", ""), var_num):
        return None

    stem = base[:-len(base_digits)].rstrip("-_")
    return f"{stem}-{var_num}-{unit}{rest}"


def _collapse_prefixed_digits(base: str, variant: str, digits: str) -> str | None:
    """Collapse exact matching digits or a 'digits-' prefix."""
    if variant == digits:
        return base
    prefix = f"{digits}-"
    if variant.startswith(prefix):
        return f"{base}-{variant[len(prefix):]}"
    return None


def join_base_variant(base: str, variant: str) -> str:
    """Join a base code with a variant suffix, collapsing stuttered dimension tokens.

    When a fallback base already ends in the capacity number (e.g. ``KIA-...-32``
    or ``KIA-...-15`` for 1.5 Ton) and the variant suffix repeats that number
    (e.g. ``32INCH`` or ``1.5TON-WHITE``), the repeating number is collapsed so the
    SKU reads ``KIA-...-32-INCH`` or ``KIA-...-1.5-TON-WHITE`` instead of
    stuttering as ``KIA-...-32-32INCH`` or ``KIA-...-15-1.5TON-WHITE``.
    """
    if not (base and variant):
        return base or variant

    m_base = TRAILING_DIGITS_RE.search(base)
    if not m_base:
        return f"{base}-{variant}"

    base_digits = m_base.group(1)
    collapsed = _collapse_dimension_stutter(base, variant, base_digits)
    if collapsed:
        return collapsed

    collapsed = _collapse_prefixed_digits(base, variant, base_digits)
    if collapsed:
        return collapsed

    return f"{base}-{variant}"


# ---------------------------------------------------------------------------
#  Uniqueness
# ---------------------------------------------------------------------------
class UniqueRegistry:
    """Hands out values that are unique across the whole run.

    Two passes: the first counts every base value, the second appends a suffix
    only where a real collision exists.  Nothing is suffixed just in case.

    ``normaliser`` shapes whatever the registry hands back -- the SKU registry
    upper-cases, the Handle registry slugs.  Left unset it changes nothing.
    """

    def __init__(self, normaliser: Callable[[str], str] | None = None) -> None:
        self._normaliser: Callable[[str], str] = normaliser or (lambda value: value)
        self._bases: dict[str, int] = {}
        self._taken: set[str] = set()

    def register_base(self, base: str) -> None:
        """Count one row's base value (first pass)."""
        base = self._normaliser(base)
        self._bases[base] = self._bases.get(base, 0) + 1

    def base_is_colliding(self, base: str) -> bool:
        return self._bases.get(self._normaliser(base), 0) > 1

    def assign(self, base: str, variant: str = "") -> tuple[str, bool]:
        """Return ``(final_value, needed_numeric_suffix)``.

        The bare base is kept when it is unique in the run.  A colliding base
        gets the variant suffix; if that is taken too (or no variant exists) a
        numeric suffix is added as a last resort and reported.
        """
        base = self._normaliser(base)
        variant = self._normaliser(variant).strip("-") if variant else ""
        if variant:
            variant = re.sub(r"\s+", "-", variant)

        if not self.base_is_colliding(base) and base not in self._taken:
            self._taken.add(base)
            return base, False

        candidate = join_base_variant(base, variant) if variant else base
        if candidate not in self._taken:
            self._taken.add(candidate)
            return candidate, False

        counter = 2
        while f"{candidate}-{counter}" in self._taken:
            counter += 1
        final = f"{candidate}-{counter}"
        self._taken.add(final)
        return final, True


def upper_sku_normaliser(value: str) -> str:
    """The SKU registry's normaliser: codes are always upper case."""
    return value.upper()


def handle_normaliser(value: str) -> str:
    """The Handle registry's normaliser: always a lower-case slug."""
    return slugify(value)
