"""Sections 10 and 12 -- warranty extraction, the headline-duration split, and
the brand reference tables.

╔══════════════════════════════════════════════════════════════════════════╗
║  ██  EDIT HERE  ██  -- the brand warranty reference tables               ║
║                                                                            ║
║  WARRANTY_TABLES[brand][product_type] = [(part, duration), ...]           ║
║                                                                            ║
║  • These tables are FALLBACK ONLY -- they are used only when the row's    ║
║    own Description states no warranty at all.  A stated warranty always   ║
║    wins.                                                                  ║
║  • Fill in the empty brand slots below as you send me each brand's        ║
║    warranty terms.  A missing brand/type simply produces no warranty row  ║
║    and is reported in the terminal summary -- nothing is ever invented.   ║
║  • Every (part, duration) pair becomes its own bolded first-column row in  ║
║    the Description table (parts are never collapsed together).            ║
║                                                                            ║
║  APPLY_TV_WARRANTY_FALLBACK: the spec's Test Case 2 requires a Dawlance    ║
║  LED TV with no stated warranty to have NO warranty row, even though the   ║
║  tables here contain a TV entry.  Leave this False to keep that behaviour; ║
║  set it True and every warranty-less LED TV gains its table warranty.      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from config import APPLY_TV_WARRANTY_TABLE
from models import SpecRow

# The terms themselves live in warranty_terms.py -- one line per brand per
# category, right next to the brand and category tables.  This module only knows
# how to read them.
from warranty_terms import WARRANTY_TERMS as WARRANTY_TERMS

# Set in config.py -- the one place to flip it.
APPLY_TV_WARRANTY_FALLBACK = APPLY_TV_WARRANTY_TABLE


# ---------------------------------------------------------------------------
#  Reading the table above -- nothing below needs editing to change a warranty
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TermLine:
    """One entry of WARRANTY_TERMS, already parsed into part/duration pairs."""

    brand: str
    category: str
    variant_words: tuple[str, ...]
    entries: tuple[tuple[str, str], ...]

    def matches(self, title: str) -> bool:
        if not self.variant_words:
            return False  # the plain category is the default, never a match
        lowered = title.lower()
        return any(
            re.search(rf"\b{re.escape(word.lower())}", lowered)
            for word in self.variant_words
        )


def _parse_value(value: str) -> tuple[tuple[str, str], ...]:
    """``"Motor = 10 Years; Parts = 1 Year"`` -> the pairs. A bare duration is a Parts row."""
    entries: list[tuple[str, str]] = []
    for raw_chunk in value.split(";"):
        chunk = raw_chunk.strip()
        if not chunk:
            continue
        if "=" in chunk:
            part, duration = chunk.split("=", 1)
            entries.append((part.strip(), duration.strip()))
        else:
            entries.append(("Parts", chunk))
    return tuple(entries)


def _split_category(key: str) -> tuple[str, tuple[str, ...]]:
    """``"Washing Machine (semi automatic / twin tub)"`` -> category + words."""
    if "(" not in key or ")" not in key:
        return key.strip(), ()
    category, rest = key.split("(", 1)
    words = tuple(
        word.strip()
        for word in re.split(r"[/|]", rest.rstrip(") "))
        if word.strip()
    )
    return category.strip(), words


TERM_LINES: list[TermLine] = [
    TermLine(
        brand=brand,
        category=_split_category(category)[0],
        variant_words=_split_category(category)[1],
        entries=_parse_value(value),
    )
    for brand, table in WARRANTY_TERMS.items()
    for category, value in table.items()
]


def lookup_terms(
    brand_key: str, product_type: str, text: str
) -> list[tuple[str, str]] | None:
    """The reference terms for this row, or ``None`` when there are none.

    Entries with words in brackets are checked first, in the order they appear
    in WARRANTY_TERMS, so a narrower wording such as "non inverter" always wins
    over the plain category underneath it.
    """
    if product_type == "LED TV" and not APPLY_TV_WARRANTY_FALLBACK:
        return None
    b_key = brand_key.strip().lower()
    title = text.splitlines()[0] if text else ""
    default: TermLine | None = None
    for line in TERM_LINES:
        if line.brand != b_key or line.category != product_type:
            continue
        if not line.variant_words:
            if default is None:
                default = line
            continue
        if line.matches(title):
            return list(line.entries)
    return list(default.entries) if default else None


def has_explicit_non_numeric_term(warranty_text: str) -> bool:
    """True when the row states ``N/A`` / ``Lifetime`` rather than a duration."""
    return _EXPLICIT_TERM_RE.search(warranty_text) is not None

_DURATION_RE = re.compile(
    r"\b(\d{1,2})\s*-?\s*(years?|yrs?|months?|mos?)\b", re.IGNORECASE
)
# Matches a warranty clause line, keeping whatever the shop wrote in front of the word
# "warranty" -- "Motor Warranty: 10" must arrive with "Motor" intact, or the part label is lost,
# and so must "10 years compressor warranty: Yes", whose number sits in front of the word and is
# therefore the answer itself.  The colon is required: it is what makes a line a labelled clause,
# while prose that merely mentions a warranty belongs to the sentence path below.  The prefix
# stops at a full stop and at 40 characters for the same reason -- an opening sentence about the
# product names its parts in passing, and is not a label.
_WARRANTY_VALUE_RE = re.compile(
    r"(?im)^[ \t]*(?:[-•*]\s*)?(?P<label>[^.\n\r:]{0,40}?warrant(?:y|ies))"
    r"\s*:[ \t]+(?P<value>[^\n\r]+)"
)
_WARRANTY_SENTENCE_RE = re.compile(r"(?i)([^.\n\r]{0,120}warrant[^.\n\r]{0,120})")
#: The ways the shop writes "this warranty never expires", spelled once for every reader.
_LIFETIME_PHRASE = r"lifetime|life\s*time|full\s+life"
# Terms that ARE the answer, even though they carry no number: the row is
# saying there is no warranty, or that it never expires.  These are never
# replaced by a reference table.
_EXPLICIT_TERM_RE = re.compile(
    rf"(?i)\b(n/?a|not\s+applicable|no\s+warrant(?:y|ies)|{_LIFETIME_PHRASE})\b"
)

# Which component counts as the headline when several parts are stated.
# The empty entry is the row's own bare term -- a `• Warranty: 10 Years` line that names no
# part.  It ranks right after the three big parts, because that line IS the number a shopper
# buys on; a rider such as `• PCB Warranty: 4 Years` must not push it out of the Title.
_UNNAMED_STATED_TERM = ""
HEADLINE_PRIORITY: tuple[str, ...] = (
    "compressor",
    "motor",
    "panel",
    _UNNAMED_STATED_TERM,
    "pcb",
    "evaporator",
    "thermostat",
    "magnetron",
    "heater",
    "parts",
    "general",
)

#: `Lifetime` answers the warranty question without a number, so the part that states it keeps
#: its own row.  ``N/A`` / ``no warranty`` are NOT turned into durations: those rows already take
#: the explicit-term path, which leaves the Title without a warranty tail.
_LIFETIME_TERM_RE = re.compile(rf"(?i)\b({_LIFETIME_PHRASE})\b")


def _heads_the_row(part: str, wanted: str) -> bool:
    """Whether a stated part answers the headline question ``wanted`` asks."""
    if wanted == _UNNAMED_STATED_TERM:
        return not _names_a_component(part)
    return wanted in part.lower()


_PART_LABELS: dict[str, str] = {
    "compressor": "Compressor Warranty",
    "motor": "Motor Warranty",
    "pcb": "PCB Warranty",
    "panel": "Panel Warranty",
    "evaporator": "Evaporator Warranty",
    "thermostat": "Thermostat Warranty",
    "condenser": "Condenser Warranty",
    "heater": "Heater Warranty",
    "magnetron": "Magnetron Warranty",
    "general": "General Warranty",
    "parts": "Parts Warranty",
    "service": "Service Warranty",
}

#: The components that can push the row's own bare line out of the Title are exactly the rungs
#: above -- not every label this reader knows how to print.  `Free Service` names a promise, not a
#: ranked part, so it must not cost the shop his own headline number; and a word counts only as
#: itself, so `panel` inside a longer word names nothing.  A clause whose leftover words match
#: none of them names no part, whatever those words are (`• Warranty: 10 Years Real Free
#: Warranty` states his term, not a component).
_COMPONENT_WORD_RE = re.compile(
    r"(?i)\b(" + "|".join(word for word in HEADLINE_PRIORITY if word) + r")\b"
)


def _names_a_component(part: str) -> bool:
    return _COMPONENT_WORD_RE.search(part) is not None


@dataclass(frozen=True)
class StatedPart:
    """One part/duration pair parsed out of a stated warranty string."""

    part: str
    duration: str | None
    raw: str


# "Motor Warranty: 10" / "Compressor Warranty : 12" -- the source omits the
# unit.  A bare 1-2 digit number attached to a named part is a year count.
_BARE_YEARS_RE = re.compile(r"^\s*(\d{1,2})\s*$")


def parse_bare_years(text: str) -> str | None:
    """``"10"`` -> ``"10 Years"`` when the surrounding text names a part."""
    match = _BARE_YEARS_RE.match(text)
    if not match:
        return None
    return f"{match.group(1)} Years"


def normalise_duration(match: re.Match[str]) -> str:
    """Keep the source's own singular/plural wording ("10 Year" stays "10 Year")."""
    number, unit = match.group(1), match.group(2).lower()
    if unit.startswith(("yr", "year")):
        unit_out = "Year" if unit in ("year", "yr") else "Years"
    else:
        unit_out = "Month" if unit in ("month", "mo") else "Months"
    return f"{number} {unit_out}"


def _states_an_answer(clause: str) -> bool:
    """Whether a warranty clause actually answers the question, or only says "Yes".

    ``• Warranty: Yes`` names no duration, so collecting it would replace the brand's reference
    terms with a row that tells the buyer nothing.  The answer is looked for in the WHOLE clause,
    because ``• 10 years compressor warranty: Yes`` answers it too -- he wrote his number in front
    of the word and only a "Yes" after it.
    """
    return bool(
        _DURATION_RE.search(clause)
        or _EXPLICIT_TERM_RE.search(clause)
        or parse_bare_years(clause.split(":", 1)[-1])
    )


def find_stated_warranty_text(text: str) -> str | None:
    """Every warranty clause the row states, joined -- not only the first one.

    ``• Compressor Warranty: 10 Years`` followed by ``• Parts Warranty: 5 Years`` is TWO facts;
    reading only the first line deleted the second from the table and from every attribute, which
    breaks the rule that whatever the shop writes must reach the output.

    Order of authority: a labelled ``Warranty:`` line that states an answer beats prose that states
    one, and either beats a line that states none (``• Warranty: Yes`` tells a buyer nothing and
    would otherwise replace the real fact).  A plain "Warranty" label adds nothing -- the row is
    already labelled "Warranty", so prefixing it would print the word twice ("Warranty | Warranty:
    N/A").  A part name in front of it IS information and is kept ("Motor Warranty: 10").
    """
    clauses: list[str] = []
    for match in _WARRANTY_VALUE_RE.finditer(text):
        label = match.group("label").strip()
        value = match.group("value").strip()
        if not value:
            continue
        clause = (
            value if label.lower() in ("warranty", "warranties") else f"{label}: {value}"
        )
        if clause not in clauses:
            clauses.append(clause)
    answering = [clause for clause in clauses if _states_an_answer(clause)]
    if answering:
        return ", ".join(answering)

    every = [match.group(1).strip(" -•") for match in _WARRANTY_SENTENCE_RE.finditer(text)]
    sentences = [
        sentence
        for sentence in every
        if _DURATION_RE.search(sentence) or _EXPLICIT_TERM_RE.search(sentence)
    ]
    if sentences:
        return ", ".join(sentences)
    # Nothing in the row states an answer.  `• Warranty: Official Brand Warranty` is still what he
    # wrote, and dropping it would delete his warranty from the table and let the brand's
    # reference numbers answer for a product whose terms he stated himself.
    return ", ".join(clauses or sentences or every) or None


def parse_warranty_parts(warranty_text: str) -> list[StatedPart]:
    """Split ``"3 Years Compressor, 1 Year General Warranty"`` into its parts."""
    parts: list[StatedPart] = []
    for raw_chunk in re.split(r"[,;]|\s\+\s|\band\b", warranty_text):
        chunk = raw_chunk.strip(" .")
        if not chunk:
            continue
        duration_match = _DURATION_RE.search(chunk)
        duration = normalise_duration(duration_match) if duration_match else None
        qualifier = _DURATION_RE.sub("", chunk).strip(" -,")
        if duration is None:
            # "Motor Warranty: 10" -- a bare number beside a named part is years.
            value = qualifier.split(":", 1)[-1].strip(" -,")
            bare = parse_bare_years(value)
            if bare:
                duration = bare
                label = _label_for(qualifier)
                qualifier = label.replace(" Warranty", "") if label != "Warranty" else ""
        if duration is None and _LIFETIME_TERM_RE.search(chunk):
            # `Lifetime` is this part's answer; without it the part has no row at all.  The word
            # is the answer and not the part, so it leaves the name: a bare `• Warranty: Lifetime`
            # line stays the row's own unnamed term and prints `Warranty: Lifetime`, never
            # `Lifetime Warranty: Lifetime`.
            duration = "Lifetime"
            qualifier = _LIFETIME_TERM_RE.sub("", qualifier).strip(" -,")
        parts.append(StatedPart(part=qualifier, duration=duration, raw=chunk))
    return parts


def _label_for(qualifier: str) -> str:
    lowered = qualifier.lower()
    for key, label in _PART_LABELS.items():
        if key in lowered:
            return label
    # `• 10 Years Nationwide Warranty: Yes` names the part `Nationwide`, and the "Yes" after the
    # colon is no answer at all -- keeping it printed "Nationwide : Yes Warranty" inside a Title.
    # The cut comes AFTER the part lookup above, because a line written `Warranty: 10 Years
    # Compressor` names its part beyond the colon and must still be recognised.
    head = qualifier.split(":", 1)[0]
    cleaned = re.sub(r"(?i)\bwarrant(?:y|ies)\b", "", head).strip(" -,")
    cleaned = re.sub(r"(?i)^(official|brand|the)\b\s*", "", cleaned).strip()
    if not cleaned or re.match(r"^\d+$", cleaned):
        return "Warranty"
    return f"{cleaned.title()} Warranty"


def build_stated_rows(warranty_text: str) -> list[SpecRow]:
    """Rows for the Description table: parts kept separate, never collapsed."""
    rows: list[SpecRow] = []
    seen: set[tuple[str, str]] = set()
    for part in parse_warranty_parts(warranty_text):
        if not part.duration:
            continue
        label = _label_for(part.part)
        key = (label.lower(), part.duration.lower())
        # The same fact written twice -- once in the opening sentence, once as a bullet -- is one
        # row.  Two identical rows made the table's duplicate-label rename print
        # `Compressor Warranty Warranty`.
        if key in seen:
            continue
        seen.add(key)
        rows.append(SpecRow(label=label, value=part.duration, is_warranty=True))
    if not rows:
        # No parsable duration -- keep the text as found rather than inventing one.
        return [SpecRow(label="Warranty", value=warranty_text.strip(), is_warranty=True)]
    return rows


def headline_duration(parts: list[StatedPart]) -> str | None:
    """The major/headline component's bare duration, or ``None``."""
    dated = [part for part in parts if part.duration]
    if not dated:
        return None
    for wanted in HEADLINE_PRIORITY:
        for part in dated:
            if _heads_the_row(part.part, wanted):
                return part.duration
    return dated[0].duration


def resolve_warranty(
    source_text: str, brand_key: str, product_type: str
) -> tuple[list[SpecRow], str | None, str]:
    """Return ``(rows, headline_duration, source)`` for one product.

    Order of authority:

    1. a duration the row itself states  -> used, and the table is ignored;
    2. an explicit non-numeric term (``N/A``, ``Lifetime``) -> kept exactly as
       the row states it, because that IS the answer;
    3. anything else -- no warranty text, or text with no duration in it
       (``"Warranty: Official Haier Brand Warranty"``) -> the brand's reference
       table, which is the authoritative terms for that brand and product type;
    4. otherwise the row's own wording is kept so nothing is lost.
    """
    stated = find_stated_warranty_text(source_text)
    if stated:
        rounds = parse_warranty_parts(stated)
        headline = headline_duration(rounds)
        if headline:
            return build_stated_rows(stated), headline, "stated"
        if has_explicit_non_numeric_term(stated):
            return build_stated_rows(stated), None, "stated"

    entries = lookup_terms(brand_key, product_type, source_text)
    if entries is None:
        if stated:
            return build_stated_rows(stated), None, "stated"
        return [], None, "none"
    rows = [
        SpecRow(label=part, value=duration, is_warranty=True)
        for part, duration in entries
    ]
    return rows, (entries[0][1] if entries else None), f"reference-{brand_key}"


def _headline_part_name(part_name: str) -> str:
    """The part word a Title should carry for a clause, or ``Warranty`` when it names none.

    ``Real Free Warranty`` and ``Manufacturer`` are the shop's own words after his number, not
    components this module knows; keeping them means the Title never has to borrow a part from the
    brand's reference table that he did not claim.  Anything past the colon is his answer, not his
    part, so it leaves the name -- `Nationwide: Yes` printed inside a Title otherwise.
    """
    head = part_name.split(":", 1)[0]
    cleaned = re.sub(r"(?i)\bwarrant(?:y|ies)\b", "", head).strip(" -:")
    if not cleaned or re.match(r"^\d+$", cleaned):
        return "Warranty"
    return cleaned.title()


def headline_part_and_duration(
    parts: list[StatedPart],
) -> tuple[str, str] | None:
    """Return ``(part_name, duration)`` for the headline component."""
    dated = [(p.part, p.duration) for p in parts if p.duration is not None]
    if not dated:
        return None
    for wanted in HEADLINE_PRIORITY:
        for part_name, duration in dated:
            if _heads_the_row(part_name, wanted):
                # A known component is named by the rung's word; a clause naming none is named by
                # whatever the shop wrote beside his number.
                return (
                    _headline_part_name(part_name)
                    if wanted == _UNNAMED_STATED_TERM
                    else wanted.title(),
                    duration,
                )
    part_name, duration = dated[0]
    return _headline_part_name(part_name), duration


def format_main_warranty(part: str, duration: str) -> str:
    """Format duration + part into the title warranty token.

    Examples:
        format_main_warranty("Parts", "1 Year") -> "1 Year Warranty"
        format_main_warranty("Compressor", "10 Years") -> "10 Year Compressor Warranty"
        format_main_warranty("Motor", "10 Years") -> "10 Year Motor Warranty"
        format_main_warranty("Panel", "2 Years") -> "2 Year Panel Warranty"
    """
    duration_clean = re.sub(r"(?i)\b(year|month)s\b", r"\1", duration.strip())
    part_clean = re.sub(r"(?i)\bwarrant(?:y|ies)\b", "", part).strip(" -:")
    part_lower = part_clean.lower()
    if not part_clean or re.match(r"^\d+$", part_clean) or part_lower in (
        "warranty",
        "parts",
        "general",
        "service",
        "parts and labour",
        "official",
        "brand",
    ):
        return f"{duration_clean} Warranty"
    return f"{duration_clean} {part_clean.title()} Warranty"


def resolve_main_warranty(
    source_text: str, brand_key: str, product_type: str
) -> str | None:
    """Return the formatted main warranty phrase for the title, or ``None``."""
    entries = lookup_terms(brand_key, product_type, source_text)

    stated = find_stated_warranty_text(source_text)
    if stated:
        rounds = parse_warranty_parts(stated)
        headline_pair = headline_part_and_duration(rounds)
        if headline_pair:
            part_name, dur = headline_pair
            # If stated headline part is generic ('Warranty'), but the reference
            # table has a specific major component (e.g. Motor or Compressor):
            if part_name in ("Warranty", "") and entries:
                ref_part, ref_dur = entries[0]
                dur_clean = re.sub(r"(?i)\b(year|month)s\b", r"\1", dur)
                ref_dur_clean = re.sub(r"(?i)\b(year|month)s\b", r"\1", ref_dur)
                if dur_clean.lower() == ref_dur_clean.lower() or ref_part.lower() in source_text.lower():
                    part_name = ref_part
            return format_main_warranty(part_name, dur)
        if has_explicit_non_numeric_term(stated):
            return None

    if entries:
        return format_main_warranty(entries[0][0], entries[0][1])

    return None

