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


# ---------------------------------------------------------------------------
# Series names (shared by the Title builder and the SKU fallback)
# ---------------------------------------------------------------------------
#: An explicit ``Series:`` spec line, written the way the sheet writes its other labels
#: (``Model:``, ``Color:``): optional bullet, optional ``Model``/``Product`` prefix, separator,
#: then up to three words of value.  Read case-insensitively -- a label is punctuated, so the
#: colon is the contract and the casing is the typist's.
SERIES_LABEL_LINE_RE = re.compile(
    r"(?im)^[ \t]*(?:•[ \t]*)?(?:model[ \t]+|product[ \t]+)?series[ \t]*[:=][ \t]*"
    r"([A-Za-z][A-Za-z0-9+&.'\-]*(?:[ \t]+[A-Za-z][A-Za-z0-9+&.'\-]*){0,2})\b"
)

#: A name standing before the word ``Series`` -- ``the E Luxury Pro Series``.  Up to two
#: capitalised words ahead of the final one are captured with it, because a line is often
#: spelled over several words and the old single-word reader kept only the last of them.
#: Deliberately capital-required: ``the premium series for homes`` is a sentence about the
#: product, not a name, and lowercase prose must never reach the seat.
SERIES_NAME_BEFORE_RE = re.compile(
    r"\b((?:[A-Z][A-Za-z0-9+.\-]*[ \t]+){0,2}[A-Z][A-Za-z0-9+.\-]*)[ \t]+Series\b"
)


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
    cleaned_text = _strip_false_color_phrases(text)

    match = _COLOR_RE.search(cleaned_text)
    if match is None:
        return None
    return _spell_colour(match.group(1))


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


def _drop_option_words(words: list[str]) -> list[str]:
    """Product and spec nouns out of a colour phrase (`Color: HC White` is White)."""
    return [word for word in words if word.lower() not in COLOR_NON_MODIFIERS]


#: The words that say how a machine is PAINTED: the base colours and their marketing modifiers.
#: One table, and `series_corpus.colour_words()` hands this same set to the series reader, so the
#: paint vocabulary cannot drift apart between the two.
PAINT_WORDS: frozenset[str] = frozenset(
    word.lower() for word in (*BASE_COLORS, *COLOR_MODIFIERS)
)

#: Cut on every non-letter, the repo's own convention for reading a Title word by word: a sheet that
#: hyphenates its paint (`Pearl-Copper`) then spends the same words as one that spaces them, and a
#: code's fragments (`HWD`, `BP`, `S`) are no more paint than the digits between them.
_TITLE_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")


def _strip_false_color_phrases(text: str) -> str:
    for phrase in FALSE_COLOR_PHRASES:
        text = re.sub(phrase, "", text, flags=re.IGNORECASE)
    return text


def color_label_value(text: str) -> str | None:
    r"""The colour the row's own ``Color:`` / ``Product Color:`` line states, or ``None``.

    The label is the contract, and a contract is punctuated: the value must stand behind a
    separator (``:``, ``-``, ``=``, or the tab a spec block uses).  Without one, `Color Depth Black`
    and the scraped column head `Color Pattern        Black` are sentences about the picture,
    and the separator-less reader sold `Depth Black` and `Pattern Black` -- phrases no shop
    wrote -- as the colourway.

    The colourway the label states is kept WHOLE ("Color: Blaze Purple",
    "Color: Dark Jade Silver").  A two-word cap used to cut "Dark Jade Silver" down to
    "Dark Jade"; the ceiling is three, because a colour name is a head with a modifier or
    two, while a longer run is a scraped variant picker ("Color: Choose an option Hairline
    Golden Hairline Red Hairline …") and reading that as one colour invents a phrase no shop
    wrote.  The value is bounded to ITS OWN LINE: `[ \t]+`, never `\s+`, which also matches
    newlines and used to swallow the next spec line's first word ("Color: White\nDuzin Series"
    read the colour as "White Duzin"), and it ends at the first punctuation, so
    "Color: Blaze Purple, Inverter AC" stops at the comma.
    """
    m_color_line = re.search(
        r"(?im)^[ \t]*(?:•\s*)?(?:product\s+|appliance\s+|body\s+)?colo(?:u)?r"
        r"(?:\s*(?:name|code))?\s*[:\-=\t]\s*"
        r"([A-Za-z][A-Za-z'\-]*(?:[ \t]+[A-Za-z][A-Za-z'\-]*){0,2})",
        _strip_false_color_phrases(text),
    )
    if not m_color_line:
        return None
    words = _drop_option_words(m_color_line.group(1).split())
    if any(word.lower() in BASE_COLORS for word in words):
        return _spell_colour(" ".join(words))
    return None


def color_in_title(title: str) -> str | None:
    """The colourway spelled inside a Title, or ``None`` when the Title states none.

    Two readings, both anchored on the Title and both confined to words the repo's own colour
    tables call colours.  The first is the tail behind the last separator (`(9178-WB)-Meadow
    Green`), which is where these sheets hang the variant name, and it keeps up to three words
    because `Hazel Red Blaze` is one name and cutting it to `Red Blaze` merges it with the plain
    `Red Blaze` row beside it.  The second is the Title's own LAST run of paint words, wherever it
    stands: real row 697 writes `... 6 Cu Ft Silver (9106)` with no separator and no marketing word
    in front of it, and a reader that only knew those two shapes reported a Title stating no
    colour -- so the `• Product Color: Black` stamp on every Dawlance row sold the machine Black.

    Last, not first, because the sheet puts the paint next to its code: `PEL Silver Line Digital
    Microwave Oven 23 Ltr Black` sells the `Silver Line` range in Black, and reading the first
    colour word sold it Silver and left `Line` behind to be resold as the series.
    """
    scope_title = title.strip()

    m_hyphen = re.search(
        r"-\s*([A-Za-z]+(?:[ \t]+[A-Za-z]+){0,2})\s*$", scope_title
    )
    if m_hyphen:
        words = [w.lower() for w in m_hyphen.group(1).strip().split()]
        if any(w in BASE_COLORS for w in words) and not any(
            w in COLOR_NON_MODIFIERS for w in words
        ):
            return _spell_colour(" ".join(words))

    phrases = paint_phrases(scope_title)
    if phrases:
        return _spell_colour(phrases[-1])
    return None


def _spell_colour(phrase: str) -> str:
    """The phrase in the spelling §9's colour list uses: `Gray` and `Grey` are one entry."""
    words = [word.title() for word in phrase.split()]
    return " ".join("Grey" if word == "Gray" else word for word in words)


def paint_phrases(title: str) -> list[str]:
    """Every colour phrase the Title writes as one run of paint words, in the order it wrote them.

    A run must hold a base colour: `Pearl` alone is Haier's line, not a paint.  One word that is
    not a colour is carried along when paint stands on BOTH sides of it, because the sheet writes
    `Silver Strip Black` and `Silver Strip Grey` as single colourways and the owner's ruling is to
    print the full phrase -- but a word beside a product noun, a size or a code never travels, so
    `12 Cu Ft Silver` is still Silver and `Silver Line Digital` is still a range name.
    """
    words = _TITLE_WORD_RE.findall(_strip_false_color_phrases(title))
    keys = [word.lower() for word in words]
    runs: list[list[int]] = []
    current: list[int] = []
    bridged = False

    def painted(key: str) -> bool:
        return key in PAINT_WORDS and key not in COLOR_NON_MODIFIERS

    def holds_a_colour(run: list[int]) -> bool:
        return any(keys[index] in BASE_COLORS for index in run)

    for index, key in enumerate(keys):
        if painted(key):
            current.append(index)
            continue
        following = keys[index + 1] if index + 1 < len(keys) else ""
        if current and not bridged and key not in COLOR_NON_MODIFIERS and painted(following):
            current.append(index)
            bridged = True
            continue
        runs.append(current)
        current, bridged = [], False
    runs.append(current)

    phrases: list[str] = []
    for run in runs:
        # A paint word standing in front of a product noun belongs to that noun, not to the paint:
        # `Pearl Copper Steel Door` is the Pearl Copper machine with a steel door.  It is dropped
        # only while the phrase still names a colour without it -- `Burgundy 11 Cu Ft` and
        # `Oven Silver 20 Ltr` keep the word they are, because the noun after them is a size.
        trimmed_run = run
        while len(trimmed_run) > 1:
            after = keys[trimmed_run[-1] + 1] if trimmed_run[-1] + 1 < len(keys) else ""
            if after not in COLOR_NON_MODIFIERS or not holds_a_colour(trimmed_run[:-1]):
                break
            trimmed_run = trimmed_run[:-1]
        if holds_a_colour(trimmed_run):
            phrases.append(" ".join(words[index] for index in trimmed_run))
    return phrases


def color_in_prose(text: str) -> str | None:
    """The colour a sentence in the row states -- `finished in`, `available in`, `product color:`."""
    m_desc = re.search(
        r"(?:finished in|product color:[ \t]*|available in)[ \t]*([A-Za-z]+(?:[ \t]+[A-Za-z]+)?)\b",
        _strip_false_color_phrases(text),
        re.IGNORECASE,
    )
    if not m_desc:
        return None
    words = m_desc.group(1).split()
    filtered = _drop_option_words(words)
    if any(w.lower() in BASE_COLORS for w in filtered):
        return _spell_colour(" ".join(filtered))
    return None


def colour_disagreements(text: str, title: str = "") -> list[str]:
    """Every OTHER colour this row states, once the Title's own paint has been taken.

    Owner ruling: a row that states two colours ships the Title's and is handed back for review, so
    the losing statement is collected rather than quietly dropped.  Only a sentence the shop wrote
    ABOUT the paint counts -- a second colour phrase in the Title itself, its `Color:` line, or a
    `finished in`/`available in` clause.  A colour word merely sitting in a spec cell is not a
    statement, and reading one as such would flag half the sheet.
    """
    painted = color_in_title(title) if title else None
    if not painted:
        return []
    earlier = paint_phrases(title)[:-1]
    stated: list[str] = []
    for candidate in (
        *(_spell_colour(phrase) for phrase in earlier),
        *(
            found
            for found in (color_label_value(text), color_in_prose(text))
            if found
        ),
    ):
        if _same_paint(candidate, painted) or any(
            _same_paint(candidate, kept) for kept in stated
        ):
            continue
        stated.append(candidate)
    return stated


def _same_paint(one: str, other: str) -> bool:
    return _extends_a_colour(one, other) or _extends_a_colour(other, one)


def _extends_a_colour(short: str, long: str) -> bool:
    """Does ``long`` say the paint ``short`` names, with words added IN FRONT of it?

    A colourway is its head colour with its modifiers ahead of it -- `Grey`, `Dark Grey`,
    `Silver Grey` are one paint written three ways -- so the short spelling has to sit at the END of
    the long one.  `Black` inside `Black White` does not: that is a SECOND paint written after the
    one the Title chose, and a row that does that is a row stating two colours, not one colour
    stated twice.  Treating any containment as a restatement let the spec line append its own word
    and ship a compound the shop never put in his Title, with no flag to show him.
    """
    head = _colour_words(short)
    tail = _colour_words(long)
    if not head or len(head) > len(tail):
        return False
    return tail[-len(head):] == head


def _colour_words(phrase: str) -> list[str]:
    """One spelling per colour: `Manhattan Gray` and `Manhattan Grey` are the same paint."""
    return [w.lower().replace("gray", "grey") for w in phrase.split()]


def names_the_same_colour(one: str, other: str) -> bool:
    """``Red Blaze`` and ``Hazel Red Blaze`` are one colourway, stated twice, not two colours."""
    needles = _colour_words(one)
    haystack = _colour_words(other)
    if not needles:
        return False
    return any(
        haystack[i : i + len(needles)] == needles for i in range(len(haystack) - len(needles) + 1)
    )


def _fuller(one: str, other: str) -> str:
    return one if len(one.split()) >= len(other.split()) else other


def find_full_color(text: str, title: str = "") -> str | None:
    """Return the full colour name (e.g. ``Crimson Red``, ``Meadow Green``, ``White``), or ``None``.

    When a marketing or descriptive modifier is present, returns the full colour phrase.
    Otherwise falls back to :func:`find_base_color`.

    The Title is read FIRST because it is the name the shop gave this machine, while a spec line is
    a form he fills in: `• Product Color: Black` stands on every Dawlance refrigerator row on the
    sheet -- 140 rows shipped Black, Meadow Green and Crimson Red among them -- and reading the
    stamp first sold those machines the wrong paint.  Two sides stating the same colourway still
    print the fuller spelling, and when the Title states no colour at all the label keeps the
    contract it always had.
    """
    # The pipeline hands this the row's whole text AND its Title, and that text already opens with
    # the Title -- prepending it a second time scans the same words twice for no second answer.
    full_text = text if (not title or text.startswith(title)) else f"{title}\n{text}"
    cleaned_full_text = _strip_false_color_phrases(full_text)

    painted = color_in_title(title) if title else None
    labeled = color_label_value(full_text)
    # 'finished in <Color>' or 'available in <Color>' in the row's own prose
    prose = color_in_prose(cleaned_full_text)
    if painted:
        # Another side spelling the SAME paint fuller is not a second colour: `11 Cu Ft Grey` beside
        # `finished in Silver Grey` is one colourway, and the row loses words if the shorter ships.
        # It is only a fuller spelling when the words are added in FRONT of the Title's colour -- a
        # word added BEHIND it (`Black White`) is a second paint, and the Title's own word ships.
        for stated in (labeled, prose):
            if stated and _extends_a_colour(painted, stated):
                painted = _fuller(painted, stated)
        return painted
    if labeled:
        return labeled
    if prose:
        return prose

    # Fallback to base color
    return find_base_color(cleaned_full_text)



