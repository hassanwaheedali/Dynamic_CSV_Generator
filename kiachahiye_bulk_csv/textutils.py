"""Shared, dependency-free text helpers.

Everything here is plain, deterministic string processing: no LLM calls, no
network calls, no fuzzy matching.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Basic normalisation
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, strip, collapse internal whitespace (cached-lookup key form)."""
    return _WS_RE.sub(" ", text.strip().lower())


# ---------------------------------------------------------------------------
# Weight
# ---------------------------------------------------------------------------
#: Units the two platforms accept, and the spellings a sheet may use for each.
WEIGHT_UNITS: dict[str, str] = {
    "kg": "kg", "kgs": "kg", "k.g": "kg", "k.g.": "kg", "kilo": "kg",
    "kilos": "kg", "kilogram": "kg", "kilograms": "kg",
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
}

#: Which stated weight to publish, best first.  The shipping weight (the packed
#: weight the courier charges on) is the one the client supplies, so it wins; a
#: bare "Weight" comes last, and the net weight sits in between.
PACKED_WEIGHT_WORDS: tuple[str, ...] = (
    "shipping", "gross", "carton", "packed", "packaging", "set wt", "set",
)
PRODUCT_WEIGHT_WORDS: tuple[str, ...] = ("net", "product", "item", "nett")
WEIGHT_UNIT_WORDS: tuple[str, ...] = ("unit", "uom")

#: Header names are matched loosely, so "Shipping Weight (kg)", "Gross Wt" and
#: "Wt In Kgs" all work without being listed anywhere.
WEIGHT_HEADER_RE = re.compile(r"weight|\bwt\b", re.IGNORECASE)

#: A weight written inside a Description, e.g. "• Set Weight: 16 kg".  The label is
#: captured because a row may state several weights and they are not equal.
WEIGHT_LINE_RE = re.compile(
    r"(?im)^[ \t]*(?:•\s*)?"
    r"((?:shipping|gross|carton|packed|packaging|set|net|nett|product|item)?\s*(?:weight|wt))"
    r"\s*:?\t?\s*([\d][\d.,]*)\s*([A-Za-z.]{0,8})?",
)


def weight_rank(label: str) -> int:
    """Sort weight wordings: shipping/packed weight first, net weight second, plain last."""
    lowered = re.sub(r"\s+", " ", label.strip().lower())
    words = [word for word in lowered.replace("-", " ").split() if word not in ("kg", "kgs")]
    if any(word in PACKED_WEIGHT_WORDS for word in words):
        return 0
    if any(word in PRODUCT_WEIGHT_WORDS for word in words):
        return 1
    return 2


def _clean_number(raw: str) -> str:
    """A price-style number as plain text: "1,250" and "17,25" both become decimals."""
    text = raw.strip()
    if "," in text:
        whole, _, fraction = text.rpartition(",")
        digits = whole.replace(",", "")
        # Three digits after the comma is a thousands separator ("1,250 g");
        # anything shorter is a decimal comma ("17,25 kg").
        text = digits + fraction if len(fraction) == 3 else f"{digits}.{fraction}"
    return text


def parse_weight_cell(raw: str) -> tuple[str, str] | None:
    """Read a Weight cell into ``(number, unit)``, or ``None`` when it holds no weight.

    "17.25 kg", "17.25kg", "16", "500 g" and "approx 12.5 KG" all parse; a unit the
    platforms do not accept ("3 tonnes") or a cell with no number at all ("N/A")
    returns ``None`` so the caller can leave the cell empty and flag the row rather
    than guess.  A missing unit defaults to kg, which is how these sheets are written.
    """
    if not raw or not raw.strip():
        return None
    match = re.search(r"(\d[\d.,]*)\s*([A-Za-z.]{0,12})", raw)
    if match is None:
        return None
    number = _clean_number(match.group(1))
    try:
        float(number)
    except ValueError:
        return None
    written = match.group(2).strip().lower().rstrip(".")
    if not written:
        return number, "kg"
    unit = WEIGHT_UNITS.get(written)
    if unit is None:
        return None
    return number, unit


def pick_weight_columns(headers: list[str]) -> tuple[str | None, str | None]:
    """Choose the sheet's weight column and unit column, whatever they are called.

    "Shipping Weight", "Gross Weight (kg)", "Wt In Kgs" and plain "Weight" all
    qualify; a column naming a unit ("Weight Unit", "Weight UOM") is treated as
    the unit.  When a sheet carries several weight columns the same ranking as
    the Description lines applies, so a shipping weight beats a net weight.
    """
    value_columns: list[tuple[int, int, str]] = []
    unit_column: str | None = None
    for index, header in enumerate(headers):
        if not header or not WEIGHT_HEADER_RE.search(header):
            continue
        if any(word in header.lower().split() for word in WEIGHT_UNIT_WORDS):
            unit_column = unit_column or header
            continue
        value_columns.append((weight_rank(header), index, header))
    if not value_columns:
        return None, unit_column
    value_columns.sort()
    return value_columns[0][2], unit_column


def parse_weight_unit(raw: str) -> str | None:
    """Read a unit-only cell such as "g" or "KG" from a Weight Unit column."""
    written = raw.strip().lower().rstrip(".")
    if not written:
        return None
    return WEIGHT_UNITS.get(written)


def find_weight_in_text(text: str) -> tuple[str, str] | None:
    """Read the weight out of a Description, e.g. "• Set Weight: 16 kg" -> ("16", "kg").

    When a row states several weights the product's own weight wins over the set
    weight and the gross weight, whichever order the sheet lists them in.  A
    weight written with a unit the platforms do not accept is ignored, and the
    next stated weight is used instead.
    """
    best: tuple[int, int, tuple[str, str]] | None = None
    for index, match in enumerate(WEIGHT_LINE_RE.finditer(text)):
        written = (match.group(3) or "").strip().lower().rstrip(".")
        unit = WEIGHT_UNITS.get(written) if written else "kg"
        if unit is None:
            continue
        priority = weight_rank(match.group(1))
        candidate = (priority, index, (_clean_number(match.group(2)), unit))
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    return best[2] if best is not None else None


def clean_inline(text: str) -> str:
    """Collapse *all* whitespace (including newlines) into single spaces.

    Used on values that are about to be dropped into an HTML field, because the
    output CSVs must never contain a raw newline inside a field.
    """
    return _WS_RE.sub(" ", text).strip()


def strip_html_tags(text: str) -> str:
    """Remove HTML tags and unescape the handful of entities we generate."""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    replacements = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
    }
    for entity, char in replacements.items():
        text = text.replace(entity, char)
    return clean_inline(text)


def strip_markup_keep_lines(text: str) -> str:
    """Remove HTML markup from a source cell, keeping its line structure.

    Descriptions are parsed line by line ("Capacity: 25 Ltr"), so flattening the
    newlines would break every label.  Block-level tags become newlines instead,
    and the same handful of entities ``strip_html_tags`` handles are unescaped.
    Plain text passes through untouched, which is the case for every row of the
    current sheet.
    """
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(
        r"</?(?:p|div|li|ul|ol|tr|h[1-6]|table|thead|tbody)\b[^>]*>", "\n", text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    for entity, char in (
        ("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", '"'), ("&#39;", "'"),
    ):
        text = text.replace(entity, char)
    # Collapse runs of spaces only: a tab is a label/value separator in some
    # sheets and must survive, or the specification block is lost.
    return re.sub(r" {2,}", " ", text)


def slugify(text: str) -> str:
    """ASCII-only, hyphenated slug used for Handles (and fallback SKUs)."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    return re.sub(r"-+", "-", ascii_text).strip("-")


def dedupe_preserve_order(values: list[str]) -> list[str]:
    """Case-insensitive de-duplication that preserves first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value.strip())
    return out


# ---------------------------------------------------------------------------
# Colour recognition (shared by the Title builder, the SKU builder and §9)
# ---------------------------------------------------------------------------
# The base colour words.  A leading marketing modifier ("HC White", "Metallic
# Grey", "Hairline Black") is stripped, so the Option1 Value is the base colour
# alone, exactly as §6/§9 require.
BASE_COLORS: list[str] = [
    "white", "black", "grey", "gray", "silver", "red", "blue", "gold", "golden",
    "champagne", "purple", "brown", "green", "maroon", "beige", "copper", "rose",
    "pink", "graphite", "bronze", "cream", "ivory", "jade", "burgundy", "navy",
    "steel", "mirror",
]

_COLOR_RE = re.compile(
    r"\b(" + "|".join(BASE_COLORS) + r")\b", re.IGNORECASE
)


# False-positive colour phrases that are technical features, NOT product body colours.
FALSE_COLOR_PHRASES: tuple[str, ...] = (
    r"\bgolden\s+fin\b",
    r"\bgold\s+fin\b",
)


def find_base_color(text: str) -> str | None:
    """Return the first base colour word in ``text`` (Title case), or ``None``.

    ``Grey``/``Gray`` are folded to ``Grey`` because §9's own colour list writes
    them as a single entry.
    """
    cleaned_text = text
    for phrase in FALSE_COLOR_PHRASES:
        cleaned_text = re.sub(phrase, "", cleaned_text, flags=re.IGNORECASE)

    match = _COLOR_RE.search(cleaned_text)
    if match is None:
        return None
    word = match.group(1).lower()
    if word == "gray":
        word = "grey"
    return word.title()


COLOR_MODIFIERS: frozenset[str] = frozenset(
    {
        "crimson", "meadow", "coral", "emerald", "forest", "olive", "mint", "mist",
        "jade", "ruby", "burgundy", "wine", "rose", "cherry", "magnetic", "silky",
        "silk", "pearl", "midnight", "navy", "cosmic", "ocean", "sky", "royal",
        "clear", "ice", "charcoal", "metallic", "manhattan", "mystic", "graphite",
        "space", "dark", "light", "hairline", "starry", "platinum", "diamond",
        "titanium", "snow", "milky", "cloud", "pure", "crystal", "piano", "matte",
        "matt", "glossy", "luxe", "hazel", "amber", "grace", "gem", "deep",
    }
)

COLOR_NON_MODIFIERS: frozenset[str] = frozenset(
    {
        "air", "conditioner", "split", "ac", "refrigerator", "fridge", "freezer",
        "deep", "chest", "washing", "machine", "washer", "dryer", "microwave",
        "oven", "water", "dispenser", "tv", "television", "led", "lcd", "cooler",
        "purifier", "geyser", "heater", "ft", "cuft", "cft", "cu", "kg", "kgs",
        "ton", "tons", "ltr", "ltrs", "litre", "litres", "liter", "liters", "inch",
        "inches", "watt", "watts", "volt", "volts", "taps", "tap", "door", "doors",
        "glass", "top", "front", "load", "side", "series", "inverter", "non",
        "inv", "new", "best", "pro", "plus", "direct", "cool", "auto", "automatic",
        "semi", "manual", "the", "with", "and", "for", "in", "of", "to", "a",
        "an", "at", "by", "from", "size", "hc", "arcelik", "dawlance", "haier",
        "pel", "homage", "orient", "gree", "kenwood", "tcl", "ecostar", "superasia",
    }
)


def find_full_color(text: str, title: str = "") -> str | None:
    """Return the full colour name (e.g. ``Crimson Red``, ``Meadow Green``, ``White``), or ``None``.

    When a marketing or descriptive modifier is present, returns the full colour phrase.
    Otherwise falls back to :func:`find_base_color`.
    """
    full_text = f"{title}\n{text}" if title else text
    scope_title = title or text.splitlines()[0]

    # Clean false-positive phrases (like 'Golden Fin')
    cleaned_full_text = full_text
    for phrase in FALSE_COLOR_PHRASES:
        cleaned_full_text = re.sub(phrase, "", cleaned_full_text, flags=re.IGNORECASE)

    # 1. Explicit 'Color:' or 'Product Color:' spec line anywhere in text
    m_color_line = re.search(
        r"(?im)^[ \t]*(?:•\s*)?(?:product\s+|appliance\s+|body\s+)?colo(?:u)?r(?:\s*(?:name|code))?\s*[:\-]?\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)\b",
        cleaned_full_text,
    )
    if m_color_line:
        cand = m_color_line.group(1).strip()
        words = cand.lower().split()
        if any(w in BASE_COLORS for w in words):
            filtered = [w for w in words if w not in COLOR_NON_MODIFIERS]
            if any(w in BASE_COLORS for w in filtered):
                return " ".join(w.title() for w in filtered)

    # 2. Hyphen color at end of title: e.g. '-(9173-WB)-Crimson Red' or '-Crimson Red'
    m_hyphen = re.search(r"-\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)\s*$", scope_title.strip())
    if m_hyphen:
        cand = m_hyphen.group(1).strip()
        words = cand.lower().split()
        if any(w in BASE_COLORS for w in words) and not any(
            w in COLOR_NON_MODIFIERS for w in words
        ):
            return " ".join(w.title() for w in words)

    # 3. 'finished in <Color>' or 'Product Color: <Color>' in details
    m_desc = re.search(
        r"(?:finished in|product color:\s*|available in)\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)\b",
        cleaned_full_text,
        re.IGNORECASE,
    )
    if m_desc:
        cand = m_desc.group(1).strip()
        words = cand.lower().split()
        if any(w in BASE_COLORS for w in words):
            filtered = [w for w in words if w not in COLOR_NON_MODIFIERS]
            if any(w in BASE_COLORS for w in filtered):
                return " ".join(w.title() for w in filtered)

    # 4. Known modifier + base color in title
    base_re = "|".join(BASE_COLORS)
    m_mod = re.search(rf"\b([A-Za-z]+)\s+({base_re})\b", scope_title, re.IGNORECASE)
    if m_mod:
        mod, base = m_mod.group(1).lower(), m_mod.group(2).lower()
        if mod in COLOR_MODIFIERS and mod not in COLOR_NON_MODIFIERS:
            if base == "gray":
                base = "grey"
            return f"{mod.title()} {base.title()}"

    # 5. Fallback to base color
    return find_base_color(cleaned_full_text)



