"""The reading layer under the Title builder: shape, claims, residue.

The formula slots may only be filled from words the row actually states, and a word
belongs to exactly one slot.  This module decides which words are still free -- the
residue -- and records the slot that took each of the others, so a wrong pick can be
reviewed instead of guessed at:

    [0] :func:`normalize_shape`  collapse the repeated ``LABEL-CODE`` halves a stock
                                 sheet writes, leaving a genuine `` - (CODE)`` tail alone
    [1] :func:`analyze_row`      the slots claim the title in a fixed order
    [2] the residue              what no slot took, in title order, lower-cased

Three boundaries this layer keeps on purpose.

It suppresses a word only when an EXISTING table names that word as a category, a type,
a unit, a colour, a brand, a sub-type or a warranty word.  Words that merely look
decorative stay in the residue: ``mega``, ``ultra``, ``classic`` and ``luxury`` appear in
none of those tables, and the corpus vote is the layer that can prove whether such a word
names one product line or decorates twenty.  A reading layer that guessed would erase
real variants it cannot see.

A word claimed from the generic tables is recorded under :data:`REVIVABLE_SLOT` so a tier
the corpus later proves can be taken back; a word owned by the model, colour, category or
brand slot never can.  Several generic tables can name the same word (``pro`` is in
:data:`sku_handle.TYPE_WORDS` and ``inverter`` is both a type word and a breadcrumb
segment), and that overlap is exactly why the slot name is recorded instead of the word
being silently dropped.  Words only the colour table knows -- ``black``, ``white`` -- are
filed under the colour slot, not the revivable one.

A brand is claimed as a WHOLE name: a two-word name is matched as a run of pieces, or as
its glued form (``ECO STAR`` also covers ``ECOSTAR``), and the words inside a name the
CATALOGUE holds are never flattened.  The one exception is the row's own ``Brand`` column:
those words are that row's brand data, so they are claimed as written.

Nothing here knows the Title format, and nothing is invented: a slot the row does not
state claims nothing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType
from typing import Any

import categories
import sku_handle
import textutils
import warranty_terms
from brands import BRAND_ALIASES, BRAND_DISPLAY_MAP, BRANDS_DIGI, resolve_brand

#: The slots in claim order; the first slot that can own a word owns it.
SLOT_ORDER: tuple[str, ...] = (
    "model", "capacity", "color", "inverter", "subtype", "category", "brand", "warranty", "type",
)

#: The one slot a proven tier word may be taken back from (see the module docstring).
REVIVABLE_SLOT = "type"

#: A piece shorter than this cannot name a product line, so no slot needs to claim it:
#: 214 rows offered "on" as a series name before this bound existed.  Three letters is
#: also the floor the reference learner uses for a tier word, for the same reason.
_MIN_NAME_LENGTH = 3

#: How long a known spec word must be before a stub tail after it counts as glued text.
#: Six keeps "inverter|on" as glue while "art|ic" can never eat a real name.
_MIN_GLUE_HEAD_LENGTH = 6

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+./\-]*")
_TRIM_RE = re.compile(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$")
_GLUED_RE = re.compile(r"^(\d{1,3})([A-Za-z]{2,})$")
_VOWEL_RE = re.compile(r"[AEIOUY]", re.IGNORECASE)
_LETTER_RE = re.compile(r"[A-Za-z]")
_DIGIT_RE = re.compile(r"\d")
_WORD_RE = re.compile(r"[a-z]+")
_NUM_RE = re.compile(r"\d+")
_SPACES_RE = re.compile(r"\s+")
_LABEL_RE = re.compile(r"[A-Za-z0-9]+")
#: The dashes a sheet actually writes between two halves of one label.
_SHAPE_DASHES = frozenset("-\u2013\u2014")


# --------------------------------------------------------------------------- #
# vocabulary: unions of tables that already exist, authoring nothing
# --------------------------------------------------------------------------- #
def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _value_words(text: str) -> frozenset[str]:
    """Every word AND every number a slot value states, as pieces a title can match.

    :func:`_words` keeps letters only, which is right for a vocabulary table but not for a
    value: a Capacity of ``1.5 Ton`` has to account for the digits the title writes next to
    it, or those digits get filed as a fragment of a part number.
    """
    return frozenset(_words(text) | set(_NUM_RE.findall(text)))


def _flatten(table: Any) -> set[str]:
    """Every word a table can hold -- keys, values and nested pairs, as bare words."""
    words: set[str] = set()
    if isinstance(table, dict):
        for key, value in table.items():
            words |= _words(f"{key} {value}")
    else:
        for item in table:
            words |= _words(str(item))
    return words


@lru_cache(maxsize=1)
def noise_vocabulary() -> frozenset[str]:
    """Words that name a slot, so they can never name a product line.

    A union of the repo's own generic tables and nothing else.  A word absent from all of
    them is absent here too -- which is how ``ECO`` stays available as a name.
    """
    words = _flatten(sku_handle.TYPE_WORDS)
    words |= _flatten(_title_stopwords())
    words |= _flatten(textutils.BASE_COLORS)
    words |= _flatten(textutils.COLOR_MODIFIERS)
    words |= _flatten(textutils.COLOR_NON_MODIFIERS)
    words |= _flatten(_subtype_table())
    return frozenset(words)


@lru_cache(maxsize=1)
def category_vocabulary() -> frozenset[str]:
    """Category and breadcrumb words: the product's class is never its name."""
    words = _flatten(categories.PRODUCT_TYPE_MAP)
    words |= _flatten(categories.CATEGORY_DIGI_PATHS)
    words |= _flatten(categories.CATEGORY_ALFA_IDS)
    words |= _flatten(categories.DIGI_SEGMENT_ALIASES)
    words |= _flatten(categories.ALFA_SEGMENT_ALIASES)
    words |= set(categories.STOP_SEGMENTS)
    return frozenset(words)


@lru_cache(maxsize=1)
def warranty_vocabulary() -> frozenset[str]:
    """Compressor, parts, years, panel: words that state a warranty, not a product."""
    words: set[str] = set()
    for by_type in warranty_terms.WARRANTY_TERMS.values():
        for product_type, clause in by_type.items():
            words |= _words(f"{product_type} {clause}")
    return frozenset(words)


@lru_cache(maxsize=1)
def brand_names() -> frozenset[str]:
    """Every name a brand is known by, kept whole."""
    names = (
        set(BRAND_DISPLAY_MAP)
        | set(BRAND_DISPLAY_MAP.values())
        | set(BRANDS_DIGI)
        | set(BRAND_ALIASES)
        | set(BRAND_ALIASES.values())
    )
    return frozenset(_SPACES_RE.sub(" ", name.strip().lower()) for name in names if name.strip())


@lru_cache(maxsize=1)
def brand_words() -> frozenset[str]:
    """Each brand name as one word: ``dawlance`` stays, ``eco star`` also becomes ``ecostar``.

    Only the glued form of a two-word name is added.  Adding the words inside it instead is
    how a brand table would eat ``ECO`` from a Midea row -- the bug this project opened for.
    """
    return frozenset(_alnum(name).lower() for name in brand_names())


@lru_cache(maxsize=1)
def brand_phrases() -> tuple[tuple[str, ...], ...]:
    """Multi-word brand names, longest first, for claiming a run of pieces at once."""
    return tuple(sorted((tuple(name.split()) for name in brand_names() if " " in name), key=lambda w: -len(w)))


@lru_cache(maxsize=1)
def color_vocabulary() -> frozenset[str]:
    """The base colour words, so a colour is filed under the colour slot, not the revivable one.

    :data:`textutils.COLOR_MODIFIERS` is deliberately absent: ``pearl`` or ``silky`` alone can
    name a line, and whatever the row's own Color column states is claimed by that column.
    """
    return frozenset(word.lower() for word in textutils.BASE_COLORS)


def _title_stopwords() -> Any:
    """The Title builder's stop list.

    Imported inside the function, not at module scope: the builder reads through this layer
    once it is wired (plan task T4), and a top-level import in both directions would be a
    cycle the module would not survive loading.
    """
    import title_builder

    return title_builder._STOPWORDS  # reusing the existing table; authoring no new word list


def _subtype_table() -> dict[str, Any]:
    import title_builder

    return title_builder.SUBTYPES


# --------------------------------------------------------------------------- #
# [0] shape normalisation
# --------------------------------------------------------------------------- #
def _alnum(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", text).upper()


def normalize_shape(raw_title: str) -> str:
    """One label per row, even when the sheet wrote the same label twice.

    A stock sheet stores many rows as ``LABEL-CODE LABEL-CODE`` around a dash.  The repeat
    is recognised on the WORDS of the two halves, and only when the shorter half's word run
    sits at the start or the end of the longer half's run -- which is what makes the collapse
    information-preserving: the half that is kept already states every word the half that is
    dropped stated.

    Splitting on the raw text instead, as a substring test does, rotates the row:
    ``PEL Premier 316 Water Dispenser Black (PWD-316)`` states ``316`` twice over, so a
    substring rule cuts it to ``... Black (PWD`` and hands ``pwd`` to the builder as a
    possible name.  A code tail therefore has to match whole words in order, and a row whose
    halves are two different labels (``DW9101-DAW REF 9101``) is left alone.
    """
    title = raw_title.strip()
    for index, char in enumerate(title):
        if index == 0 or char not in _SHAPE_DASHES:
            continue
        left, right = title[:index], title[index + 1 :]
        one, two = _LABEL_RE.findall(left.upper()), _LABEL_RE.findall(right.upper())
        if not one or not two:
            continue
        short, full = (one, two) if len(one) <= len(two) else (two, one)
        if full[: len(short)] == short or full[len(full) - len(short) :] == short:
            return (left if len(one) > len(two) else right).strip()
    return title



# --------------------------------------------------------------------------- #
# [1] claims and [2] residue
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RowAnalysis:
    """One row read once: its pieces, the slot that owns each, and the free residue."""

    title: str
    title_words: tuple[str, ...]
    claimed: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # The dict handed in is the builder's working copy; freezing it here is what makes
        # one analysis safe to hand to both pipeline passes.
        object.__setattr__(self, "claimed", MappingProxyType(dict(self.claimed)))

    @property
    def words(self) -> tuple[str, ...]:
        """The residue: pieces no slot claimed, letters-only, in title order."""
        return tuple(
            word
            for word in self.title_words
            if word not in self.claimed and _LETTER_RE.search(word) and not _DIGIT_RE.search(word)
        )


@dataclass(frozen=True)
class _Vocabulary:
    """The word sets one row brings to the claim test, built once per row."""

    explicit: Mapping[str, frozenset[str]]
    subtype: frozenset[str]
    category: frozenset[str]
    brands: frozenset[str]
    row_brand: str
    row_brand_words: frozenset[str]
    warranty: frozenset[str]
    structural: frozenset[str]
    colors: frozenset[str]


def _pieces(title: str) -> tuple[list[str], frozenset[str], frozenset[str]]:
    """Split a title into claimable atoms, marking which are part of a code or of a glue.

    A code is taken apart (``MSAG2B-12HRDN1-QC0`` -> its chunks) so a fragment of it can
    never be offered as a name, and ``20FROST`` is split so the capacity number and the
    word that names the line are decided separately.  A token that carries a digit is ONE
    label, so every chunk of it -- including a letters-only chunk like ``hsu`` in
    ``HSU-13HFAB`` or ``savein`` in ``SaveIN-AI-11`` -- is code, not a name.

    The size+word glue is the one exception, and it is recorded rather than trusted:
    ``20FROST`` hides a line name and ``13HFAB`` hides a code suffix, and nothing inside a
    single row can tell them apart.  A glued tail therefore reaches the residue only after
    the corpus proves it, which is why :func:`analyze_row` files it under
    :data:`REVIVABLE_SLOT` instead of leaving it free.
    """
    out: list[str] = []
    code_parts: set[str] = set()
    glued_tails: set[str] = set()
    for raw in _TOKEN_RE.findall(title):
        token = _TRIM_RE.sub("", raw)
        glued = _GLUED_RE.match(token)
        if glued and _VOWEL_RE.search(glued.group(2)):
            tail = glued.group(2).lower()
            out.extend((glued.group(1), tail))
            glued_tails.add(tail)
            continue
        chunks = [chunk for chunk in re.split(r"[-/.]", token) if chunk]
        parts = [chunk.lower() for chunk in chunks]
        out.extend(parts)
        if any(_DIGIT_RE.search(part) for part in parts):
            code_parts.update(parts)
    return out, frozenset(code_parts), frozenset(glued_tails)


def _abbreviates_row_brand(piece: str, row_brand: str) -> bool:
    """True for a sheet abbreviation of THIS row's brand: ``DAW`` for Dawlance.

    Scoped to the brand the caller resolved, never to the whole catalogue: a fragment test
    against every brand would claim ``ECO`` as an abbreviation of ECOSTAR and re-create the
    bug this project was opened for.  No abbreviation table is authored either -- the test
    is simply whether the piece leads this row's brand name.
    """
    return len(piece) >= _MIN_NAME_LENGTH and row_brand.startswith(piece) and row_brand != piece


def _owner_slots(piece: str, vocabulary: _Vocabulary) -> list[str]:
    """Every slot that could claim this piece; the earliest one in SLOT_ORDER wins.

    The named-slot vocabularies are consulted before the structural guesses at the end, so
    a word a table already knows is filed under its real slot rather than being guessed at:
    ``ft`` is a capacity unit, not a part number, even though it has no vowel, and a bare
    number is a part number unless this row states it as a capacity.
    """
    explicit = vocabulary.explicit
    owners: list[str] = []
    if piece in explicit["model"] or _has_digit_and_letter(piece):
        owners.append("model")
    if piece in explicit["capacity"]:
        owners.append("capacity")
    if piece in explicit["color"] or piece in vocabulary.colors:
        owners.append("color")
    if piece in explicit["inverter"]:
        owners.append("inverter")
    if piece in vocabulary.subtype:
        owners.append("subtype")
    if piece in vocabulary.category:
        owners.append("category")
    if piece in vocabulary.brands or _abbreviates_row_brand(piece, vocabulary.row_brand):
        owners.append("brand")
    if piece in vocabulary.warranty:
        owners.append("warranty")
    if piece in vocabulary.structural:
        owners.append(REVIVABLE_SLOT)
    if not owners:
        # Nothing in any table named this piece, so the only claims left are structural
        # facts about the string itself -- tried last, so a known unit word like ``ft``
        # keeps its real slot instead of being called a code fragment.
        if _is_code_fragment(piece) or piece.isdigit():
            owners.append("model")
        elif len(piece) < _MIN_NAME_LENGTH or _is_glued_known_words(piece, vocabulary.structural):
            owners.append(REVIVABLE_SLOT)
    return owners


def _has_digit_and_letter(piece: str) -> bool:
    """Letters and digits in one piece: unmistakably a part number or a fragment of one."""
    return bool(_DIGIT_RE.search(piece)) and bool(_LETTER_RE.search(piece))


def _is_code_fragment(piece: str) -> bool:
    """A vowel-less run (``WB``, ``LF``, ``GD``, ``HTZ``) cannot be read as a word."""
    return bool(piece) and not _DIGIT_RE.search(piece) and not _VOWEL_RE.search(piece)


def _is_glued_known_words(piece: str, known: frozenset[str]) -> bool:
    """True when a word no table holds is really two spec words run together.

    Sheets glue spec words without a space and the result looks like a name:
    ``InverterOn`` is ``inverter`` + ``on``.  Only two shapes count, both safe for real
    names: the piece splits into two known words, or it starts with a long known word
    (six letters or more) and leaves a tail too short to name anything.  A line name like
    ``blaze``, ``pular`` or ``arctic`` has no such head, so it is never eaten -- and this
    matters, because a glued word confined to one brand is exactly what the corpus vote
    would otherwise "prove" as that brand's series name.
    """
    if len(piece) < _MIN_GLUE_HEAD_LENGTH + 2:
        return False
    for cut in range(2, len(piece) - 1):
        head, tail = piece[:cut], piece[cut:]
        if head in known and tail in known:
            return True
        if len(head) >= _MIN_GLUE_HEAD_LENGTH and head in known and len(tail) < _MIN_NAME_LENGTH:
            return True
    return False


def _claim_brand_phrases(present: dict[str, None], vocabulary: _Vocabulary) -> dict[str, str]:
    """Claim the brand names this row actually states, so a two-word brand is read as one brand."""
    claimed: dict[str, str] = {}
    pieces = list(present)
    for words in brand_phrases():
        span = len(words)
        for start in range(len(pieces) - span + 1):
            if tuple(pieces[start : start + span]) == words:
                claimed.update(dict.fromkeys(words, "brand"))
    # The row's Brand column is that row's own data, so the words it is written with are
    # brand words here -- and so is the single word a sheet gets when it drops the space.
    for word in vocabulary.row_brand_words:
        if word in present and len(word) >= _MIN_NAME_LENGTH:
            claimed[word] = "brand"
    if vocabulary.row_brand in present:
        claimed[vocabulary.row_brand] = "brand"
    return claimed


def analyze_row(
    title: str,
    *,
    brand: str = "",
    product_type: str = "",
    breadcrumb: str = "",
    model: str = "",
    capacity: str = "",
    color: str = "",
    inverter: str = "",
) -> RowAnalysis:
    """Read one row once: normalise its shape, let the slots claim it, return the residue."""
    normalized = normalize_shape(title)
    pieces, code_parts, glued_tails = _pieces(normalized)
    present = dict.fromkeys(pieces)
    row_brand_raw = resolve_brand(brand, "").raw or brand
    row_words = _words(row_brand_raw)
    row_context = _words(product_type) | _words(breadcrumb)
    vocabulary = _Vocabulary(
        explicit={
            "model": _value_words(model),
            "capacity": _value_words(capacity),
            "color": _value_words(color),
            "inverter": _value_words(inverter),
        },
        subtype=frozenset(_subtype_words(product_type)),
        category=frozenset(category_vocabulary() | row_context),
        brands=brand_words() | frozenset(row_words),
        row_brand=_alnum(row_brand_raw).lower(),
        row_brand_words=frozenset(row_words),
        warranty=warranty_vocabulary(),
        structural=frozenset(noise_vocabulary() | row_context),
        colors=color_vocabulary(),
    )

    # A chunk of a token that carries a digit is part of that label, whatever it looks like
    # on its own, so it is claimed before any slot gets a chance to read it as a name.  A
    # bare number is the exception: it stays for the slots, so the Capacity column owns the
    # capacity this row states instead of filing it as a part number.
    claimed = {piece: "model" for piece in code_parts if piece in present and not piece.isdigit()}
    claimed.update(_claim_brand_phrases(present, vocabulary))
    for piece in present:
        if piece in claimed:
            continue
        owners = _owner_slots(piece, vocabulary)
        slot = next((name for name in SLOT_ORDER if name in owners), None)
        if slot is not None:
            claimed[piece] = slot
        elif piece in glued_tails:
            # A size+word glue (`20FROST`, `13HFAB`) is a name candidate the row cannot
            # prove, so it waits in the revivable slot rather than reaching the residue.
            claimed[piece] = REVIVABLE_SLOT
    return RowAnalysis(title=normalized, title_words=tuple(present), claimed=claimed)


def _subtype_words(product_type: str) -> set[str]:
    """The sub-type labels for this product type, plus every alias that spells them."""
    words: set[str] = set()
    for group in _subtype_table().get(product_type, ()):
        for label, aliases in group.items():
            words |= _words(label)
            for alias in aliases:
                words |= _words(alias)
    return words
