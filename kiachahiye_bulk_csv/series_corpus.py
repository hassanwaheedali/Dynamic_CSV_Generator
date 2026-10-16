"""The reading layer under the Title builder: shape, claims, residue.

The formula slots may only be filled from words the row actually states, and a word
belongs to exactly one slot.  This module decides which words are still free -- the
residue -- and records the slot that took each of the others, so a wrong pick can be
reviewed instead of guessed at:

    [0] :func:`normalize_shape`  collapse the repeated ``LABEL-CODE`` halves a stock
                                 sheet writes, leaving a genuine `` - (CODE)`` tail alone
    [1] :func:`analyze_row`      the slots claim the title in a fixed order
    [2] the candidates           what no slot took, in title order, keyed lower-cased and
                                 recorded with the row's own spelling

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

A free word is offered as the name the row WROTE, not as its last piece: a single letter no
table named, standing in front of a free word, is that word's initial (``E-Star``, ``E
Chrome``, ``C Glow``), and the key carries the row's own spelling so a later layer can render
``eComfort`` rather than invent ``Ecomfort``.  The bound is one letter because two-letter
pieces are units (``Ft``, ``Kg``) or phrase words (``on``, ``no``) -- measured, not assumed.

Nothing here knows the Title format, and nothing is invented: a slot the row does not
state claims nothing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType
from typing import Any

import attributes
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
#: What may sit between the two halves of a name the sheet wrote: a space, or one dash.
#: A slash or a dot would mean the second run starts a part number, not a level.
_PAIR_SEPARATORS = frozenset({"", *_SHAPE_DASHES})
#: A word run as written, for the spelling a shop may print.
_RUN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+]*")
#: One letter, one separator the sheet writes, one word: the shape every `E-Star` row has.
#: The lookbehind rejects a letter that itself follows a slash or a dot, because that letter is
#: the tail of a written abbreviation (`W/O REF`, `R/C Remote`), not the start of a name.
_SP = r"[ \t\u00a0]"
_INITIAL_RE = re.compile(
    rf"(?<![A-Za-z0-9/.])([A-Za-z])(?:{_SP}*[-‒–—/.]{_SP}*|{_SP}+)"
    r"([A-Za-z][A-Za-z0-9]{2,})\+?(?![A-Za-z0-9])"
)


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
    words |= _single_word_subtype_labels()
    return frozenset(words)


@lru_cache(maxsize=1)
def category_vocabulary() -> frozenset[str]:
    """Category and breadcrumb words: the product's class is never its name."""
    words = _flatten(categories.PRODUCT_TYPE_MAP)
    words |= _flatten(categories.CATEGORY_DIGI_PATHS)
    words |= _flatten(categories.CATEGORY_ALFA_IDS)
    words |= _flatten(categories.DIGI_SEGMENT_ALIASES)
    words |= _flatten(categories.ALFA_SEGMENT_ALIASES)
    words |= _flatten(categories.STOP_SEGMENTS)
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


def _single_word_subtype_labels() -> frozenset[str]:
    """Sub-type labels that are ONE word, for the whole catalogue.

    A multi-word label (``No Frost``, ``Top Load``, ``Heat & Cool``) is a PHRASE: its words are
    type words only when the row writes the phrase, which is what :func:`_subtype_words` does
    per row.  Flattening phrases into words is how ``frost`` would become a type word in an
    air-conditioner row and steal Dawlance's line name.
    """
    words: set[str] = set()
    for group in _subtype_table().values():
        for labels in group:
            for label, aliases in labels.items():
                for variant in (label, *aliases):
                    parts = _WORD_RE.findall(variant.lower())
                    if len(parts) == 1:
                        words.update(parts)
    return frozenset(words)


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
class WordPosition:
    """Where one free word sat in one row -- the evidence stage [4] votes on.

    A line name and a code suffix can recur exactly as often, so the vote reads position
    instead of counting: which brand stood in front of the word, which code pieces touched
    it, and whether the row states a longer class word the word abbreviates.  A bare number
    is deliberately NOT one of those code pieces: `Frost 30` names a line next to a size,
    while `013W USDC` is one part number read aloud.
    """

    brand_adjacent: bool = False
    class_prefixed: bool = False
    beside: frozenset[str] = frozenset()

    @property
    def code_adjacent(self) -> bool:
        return bool(self.beside)


@dataclass(frozen=True)
class ResidueCandidate:
    """One name the row offers: the key the vote counts, the spelling the shop may print.

    The key is folded so an all-caps sheet votes exactly like a title-cased one, and it joins a
    one-letter initial to the word it introduces (``e-star``, ``e-chrome``) so the line the
    vendor wrote is the line the corpus is asked about.  ``pieces`` records every piece the
    candidate covers, which is what keeps the row's pieces partitioned: claimed XOR covered.

    ``offers`` are a different object and are deliberately NOT a partition: a row puts a name
    forward on its own AND, when the very next piece is a level word, forward again with that
    word attached (``chrome``, ``chrome pro``).  The pair re-covers its head on purpose -- the
    vote has to be asked about both, and :func:`pick_series` then takes the longest one the run
    proved.  What is pinned over offers instead is fidelity: every piece of every offer must be
    contiguous in the row, and ``source`` must be letters the row itself wrote.
    """

    key: str
    source: str
    pieces: tuple[str, ...]


@dataclass(frozen=True)
class RowAnalysis:
    """One row read once: its pieces, the slot that owns each, and the free candidates."""

    title: str
    brand: str
    product_key: str
    title_words: tuple[str, ...]
    claimed: Mapping[str, str] = field(default_factory=dict)
    positions: Mapping[str, WordPosition] = field(default_factory=dict)
    candidates: tuple[ResidueCandidate, ...] = ()
    offers: tuple[ResidueCandidate, ...] = ()

    def __post_init__(self) -> None:
        # The dicts handed in are the builder's working copies; freezing them here is what
        # makes one analysis safe to hand to both pipeline passes and to the corpus vote.
        object.__setattr__(self, "claimed", MappingProxyType(dict(self.claimed)))
        object.__setattr__(self, "positions", MappingProxyType(dict(self.positions)))

    @property
    def words(self) -> tuple[str, ...]:
        """What the vote is asked about: every name this row offers, one or two words."""
        return tuple(offer.key for offer in self.offers)


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
    row_class_words: frozenset[str]


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


def _owner_slots(piece: str, vocabulary: _Vocabulary) -> tuple[list[str], bool]:
    """Every slot that could claim this piece, and whether a TABLE named it.

    The named-slot vocabularies are consulted before the structural guesses at the end, so
    a word a table already knows is filed under its real slot rather than being guessed at:
    ``ft`` is a capacity unit, not a part number, even though it has no vowel, and a bare
    number is a part number unless this row states it as a capacity.

    The flag matters because a guess is a different fact from a name: only a piece no table
    named at all can turn out to be the initial of the word next to it.
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
    named = bool(owners)
    if not owners:
        # Nothing in any table named this piece, so the only claims left are structural
        # facts about the string itself -- tried last, so a known unit word like ``ft``
        # keeps its real slot instead of being called a code fragment.
        if _is_code_fragment(piece) or piece.isdigit():
            owners.append("model")
        elif len(piece) < _MIN_NAME_LENGTH or _is_glued_known_words(piece, vocabulary.structural):
            owners.append(REVIVABLE_SLOT)
    return owners, named


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
        subtype=_subtype_words(product_type, tuple(pieces)),
        category=frozenset(category_vocabulary() | row_context),
        brands=brand_words() | frozenset(row_words),
        row_brand=_alnum(row_brand_raw).lower(),
        row_brand_words=frozenset(row_words),
        warranty=warranty_vocabulary(),
        structural=frozenset(noise_vocabulary() | row_context),
        colors=color_vocabulary(),
        row_class_words=frozenset(row_context),
    )

    # A chunk of a token that carries a digit is part of that label, whatever it looks like
    # on its own, so it is claimed before any slot gets a chance to read it as a name.  A
    # bare number is the exception: it stays for the slots, so the Capacity column owns the
    # capacity this row states instead of filing it as a part number.
    claimed = {piece: "model" for piece in code_parts if piece in present and not piece.isdigit()}
    claimed.update(_claim_brand_phrases(present, vocabulary))
    unnamed: set[str] = set()
    for piece in present:
        if piece in claimed:
            continue
        owners, named = _owner_slots(piece, vocabulary)
        if not named:
            unnamed.add(piece)
        slot = next((name for name in SLOT_ORDER if name in owners), None)
        if slot is not None:
            claimed[piece] = slot
        elif piece in glued_tails:
            # A size+word glue (`20FROST`, `13HFAB`) is a name candidate the row cannot
            # prove, so it waits in the revivable slot rather than reaching the residue.
            claimed[piece] = REVIVABLE_SLOT
    # A word one letter off from a class word this very row states is that word misspelt, so it
    # belongs to the class slot and never reaches the vote as a candidate. The class words are
    # whatever this row wrote -- in its title, in its columns, or in its breadcrumb -- never a
    # dictionary and never a list of banned spellings.
    row_class_words = dict.fromkeys(vocabulary.row_class_words, "category")
    row_class_words.update(dict.fromkeys(vocabulary.explicit["inverter"], "inverter"))
    row_class_words.update(dict.fromkeys(vocabulary.explicit["capacity"], "capacity"))
    row_class_words.update(
        {piece: slot for piece, slot in claimed.items() if slot in CLASS_SLOTS}
    )
    claimed.update(_claim_class_typos(present, row_class_words))
    residue = frozenset(
        piece
        for piece in present
        if piece not in claimed and _LETTER_RE.search(piece) and not _DIGIT_RE.search(piece)
    )
    candidates, absorbed = _candidates(normalized, pieces, residue, unnamed)
    for letter in absorbed:
        claimed.pop(letter, None)
    offers = _offers(normalized, pieces, candidates, claimed)
    # The class words this row states -- in its columns, and in its own title wherever a slot
    # recognised one. A sheet that writes "Split AC" instead of a breadcrumb still states Air
    # Conditioner, and the abbreviation guard has to read what the row itself says.
    class_words = frozenset(
        set(vocabulary.row_class_words)
        | {piece for piece, slot in claimed.items() if slot in ("category", "subtype", REVIVABLE_SLOT)}
    )
    # The product this row offers: its part numbers if it states any, else its whole word set.
    # Colour and tonnage variants share it, which is the point.
    code_parts_key = "|".join(sorted(piece for piece in present if _has_digit_and_letter(piece)))
    return RowAnalysis(
        title=normalized,
        brand=_alnum(row_brand_raw).lower(),
        product_key=code_parts_key or "|".join(sorted(present)),
        title_words=tuple(present),
        claimed=claimed,
        positions=_positions(pieces, present, offers, code_parts, class_words, vocabulary),
        candidates=candidates,
        offers=offers,
    )


def pick_series(brand: str, analysis: RowAnalysis, corpus: Corpus) -> str:
    """The series word for this row: the longest name the run proved for its brand, as written.

    `Chrome` and `Chrome Pro` are two models, so both are asked of the corpus and the row's own
    words decide which applies.  Length is counted in name words, so a row that wrote `AVANTE
    PLUS` or `AVANTE+` takes the Plus model over the plain one; a head joined from an initial may
    make the label three words long (`E Luxury Plus`), and the cap that holds is the one in
    :func:`_offers` -- one name plus at most one level word.  A row whose words the run never
    proved prints nothing: silence is the safe output, not a gap to fill with a guess.
    """
    proven = [offer for offer in analysis.offers if corpus.is_proven(brand, offer.key)]
    if not proven:
        return ""
    return max(proven, key=lambda offer: len(offer.key.split())).source


def _offers(
    title: str,
    pieces: list[str],
    candidates: tuple[ResidueCandidate, ...],
    claimed: Mapping[str, str],
) -> tuple[ResidueCandidate, ...]:
    """Every name the row puts forward: each free word, and each free word plus a level word.

    A pair forms only when the two are ADJACENT pieces and the second passes
    :func:`_is_level_tail` -- `Chrome Pro`, `Acce Pro`, `Avante Plus`.  A word owned by the model,
    category, colour, brand or capacity slot always breaks a pair, and so does a FREE word:
    measured on the sheets, letting free words be tails invented `ECO WALL` from the very row
    this project was opened for, plus `Flat Glass` and `REF AVANTE` -- two facts written side by
    side, not one name.

    A trailing ``+`` IS the word ``plus`` -- the rule as `image_pipeline` writes it, with the sign
    in its punctuation set and `plus` in its tail stopwords -- so `AVANTE+`, `Avante Plus` and
    plain `Avante` offer one identity and their evidence votes together, while each row keeps the
    form it printed.

    Nothing here chooses between the offers: that is :func:`build_corpus`, then
    :func:`pick_series`.  A bare level word is never offered alone, because a row that wrote only
    `Pro` wrote a decoration, not a name.
    """
    found: list[ResidueCandidate] = []
    seen: set[str] = set()

    def emit(key: str, source: str, span: tuple[str, ...]) -> None:
        if key not in seen:
            seen.add(key)
            found.append(ResidueCandidate(key=key, source=source, pieces=span))

    for candidate in candidates:
        emit(candidate.key, candidate.source, candidate.pieces)
        head = _written_span(title, candidate.pieces)
        if head is not None:
            written = title[head[0] : head[1]]
            # The sign is either glued to the run the row wrote or spaced off it; both are `plus`.
            if written.endswith("+") or re.match(r"[ \t\u00a0]*\+", title[head[1] :]):
                emit(f"{candidate.key} plus", written.rstrip("+") + "+", candidate.pieces)
        end = _span_end(pieces, candidate.pieces)
        if (
            end is not None
            and end < len(pieces)
            and _is_level_tail(pieces[end], claimed)
            and not _names_a_class(f"{candidate.key} {pieces[end]}")
        ):
            following = pieces[end]
            pair = _written_span(title, (*candidate.pieces, following))
            if pair is not None:
                emit(
                    f"{candidate.key} {following}",
                    title[pair[0] : pair[1]],
                    (*candidate.pieces, following),
                )
    return tuple(found)


@lru_cache(maxsize=1)
def _class_phrases() -> frozenset[str]:
    """Every two-or-more-word value the platform's own attribute tables enumerate.

    `Multi Door`, `Table Top`, `Side-By-Side`, `Twin Tub`, `Freezer-On-Top`, `Mini LED`: the
    shop's per-category attribute lists say what a product IS, and none of them lists `pro`,
    `plus` or `max`.  Reading those tables is what lets a class phrase be refused as a name
    without authoring a list of banned words here.
    """
    found: set[str] = set()
    for column, values in attributes.ALLOWED.items():
        if not column.endswith((" Type", " Category")):
            continue
        for variant in (*values, *attributes.ALIASES.get(column, {})):
            words = _WORD_RE.findall(variant.lower())
            if len(words) >= 2:
                found.add(" ".join(words))
    return frozenset(found)


def _names_a_class(pair_key: str) -> bool:
    """Whether the two words, read together, are what the attribute tables call a product type."""
    return " ".join(pair_key.split("-")) in _class_phrases()


def _written_span(title: str, pieces: tuple[str, ...]) -> tuple[int, int] | None:
    """Where the row wrote these pieces, in this order, or None when it never wrote them together.

    The halves of one label may be split by a space or by a single dash, and a ``+`` may hang off
    either of them, because that is how these sheets spell ``E STAR PRO``, ``AVANTE-PRO`` and
    ``AVANTE+``.  A slash or a dot between them means two facts side by side, and a name the row
    never spelt is not offered at all: synthesising ``AVANTE PRO`` from ``AVANTE/PRO`` would put a
    spelling on the shop shelf that no sheet ever used.
    """
    runs = list(_RUN_RE.finditer(title))
    for index in range(len(runs) - len(pieces) + 1):
        window = runs[index : index + len(pieces)]
        if [run.group().lower().rstrip("+") for run in window] != list(pieces):
            continue
        gaps = [
            title[window[i].end() : window[i + 1].start()].strip(" \t\u00a0")
            for i in range(len(window) - 1)
        ]
        if all(gap in _PAIR_SEPARATORS for gap in gaps):
            return window[0].start(), window[-1].end()
    return None


#: How long a level word may be.  `pro`, `plus`, `max` fit; `mounted`, `cooling`, `series` do not.
_MAX_LEVEL_LENGTH = 4


def _is_level_tail(piece: str, claimed: Mapping[str, str]) -> bool:
    """Whether this piece may be the SECOND word of an offered name -- the shape of `Chrome Pro`.

    This is the row-local *shape* test only, three facts about this row: the word is one the
    generic tables borrowed (``REVIVABLE_SLOT``) rather than one this row's category, colour,
    brand, capacity, model or warranty column owns; it is short, because the level words these
    sheets use are `pro`, `plus`, `max` while the descriptors that merely sit beside a name are
    long (`mounted`, `cooling`, `cooking`); and it is not a word the builder itself refuses to
    print (`title_builder._STOPWORDS` holds `series`, `model`, `new`, `price`, `warranty`),
    because `Persona Series` sells `Persona`.

    It is deliberately not a verdict.  The generic table also holds `load`, `cool` and `door` next
    to `pro` and `plus`, so shape alone would call `Bottom Load` and `Multi Door` names -- measured
    on the real sheets, that is exactly what it did.  Three more facts, each read from a table that
    already exists, settle it: a colour or colour-modifier word never marks a level
    (:func:`_colour_words`, and `textutils.COLOR_NON_MODIFIERS` is the repo's own statement that
    `pro`, `plus`, `door` and `top` are NOT colours), a word that abbreviates a longer word in the
    same vocabulary is that word shortened, not a level (:func:`_abbreviates_noise_word`:
    `inv`/inverter, `load`/loading, `cool`/cooler), and a phrase the shop enumerates as an
    attribute value names what the product IS (:func:`_names_a_class`).

    A FREE word is never a tail: `wall`, `glass` and `blaze` are names in their own right, and
    letting them be tails is what invented `eco wall` on the anchor row and `flat blaze` for PEL.
    """
    return (
        claimed.get(piece) == REVIVABLE_SLOT
        and _MIN_NAME_LENGTH <= len(piece) <= _MAX_LEVEL_LENGTH
        and piece not in _title_stopwords()
        and piece not in _colour_words()
        and not _abbreviates_noise_word(piece)
    )


@lru_cache(maxsize=1)
def _colour_words() -> frozenset[str]:
    """Base colours and their modifiers: `Pearl`, `Mist`, `Gold` never name a level.

    :data:`textutils.COLOR_NON_MODIFIERS` is deliberately NOT used -- the repo's own table puts
    `pro`, `plus`, `door` and `top` in it, which is that table saying these are not colours.
    """
    return frozenset(
        word.lower() for word in (*textutils.BASE_COLORS, *textutils.COLOR_MODIFIERS)
    )


def _abbreviates_noise_word(piece: str) -> bool:
    """Whether a longer word in the same generic vocabulary is what this short one abbreviates.

    `INV` for inverter, `LOAD` for loading, `COOL` for cooler/cooling: measured on the two sheets
    these three were exactly the tails that made `Dual INV`, `Bottom Load` and `Emperor Cool` look
    like series names.  The gap of two letters is what keeps `PRO` (no longer word in the table
    starts with it) and `MAX` in play.
    """
    return any(
        known.startswith(piece) and len(known) >= len(piece) + 2
        for known in noise_vocabulary()
    )


def _span_end(pieces: list[str], span: tuple[str, ...]) -> int | None:
    """Where this candidate's pieces finish in the row, or None when they never appear together."""
    target = list(span)
    for index in range(len(pieces) - len(target) + 1):
        if pieces[index : index + len(target)] == target:
            return index + len(target)
    return None


def _candidates(
    title: str,
    pieces: list[str],
    residue: frozenset[str],
    unnamed: set[str],
) -> tuple[tuple[ResidueCandidate, ...], frozenset[str]]:
    """Group the free pieces into the names the row actually wrote.

    A single letter that no table named, standing on its own directly in front of a free word,
    is that word's initial -- the sheet's own way of writing ``E-Star``, ``E Chrome`` and
    ``C Glow``.  Joining it is what stops fourteen Haier ``E-Star`` rows from voting for a name
    nobody sold, and the canonical key keeps the dashed and the space-written form of one line
    together while each row still carries its own spelling.

    One letter is the whole rule.  Two-letter pieces are units (``Ft``, ``Kg``), phrase words
    (``on`` in ``Freezer-On-Top``, ``no`` in ``No Frost``) or code fragments, and every one of
    those sits directly in front of a word somewhere in the two sheets, so a wider bound would
    glue a size onto a name.  A letter claimed by a second name is not shared: the first name it
    introduces keeps it and the next word stands alone, so a row's pieces stay partitioned.
    """
    spelled: dict[tuple[str, str], str] = {}
    for match in _INITIAL_RE.finditer(title):
        spelled.setdefault((match.group(1).lower(), match.group(2).lower()), match.group())

    found: list[ResidueCandidate] = []
    seen: set[str] = set()
    absorbed: set[str] = set()
    for index, piece in enumerate(pieces):
        if piece not in residue or piece in seen:
            continue
        letter = pieces[index - 1] if index else ""
        pair = (letter, piece)
        if (
            len(letter) == 1
            and letter.isalpha()
            and letter in unnamed
            and letter not in absorbed
            and pair in spelled
        ):
            absorbed.add(letter)
            seen.add(piece)
            found.append(
                ResidueCandidate(
                    key=f"{letter}-{piece}", source=spelled[pair], pieces=(letter, piece)
                )
            )
        else:
            seen.add(piece)
            found.append(
                ResidueCandidate(key=piece, source=_source_run(title, piece), pieces=(piece,))
            )
    return tuple(found), frozenset(absorbed)


def _source_run(title: str, piece: str) -> str:
    """The row's own letters for a folded piece: what a shop title may print for it.

    A run may carry the ``+`` the sheet glued to the word -- `AVANTE+` is this row's spelling of
    `avante`, and the sign is kept because stage [5] renders the sheet's own form, not "Plus".
    """
    for match in _RUN_RE.finditer(title):
        run = match.group()
        if run.lower() == piece or run.lower() == f"{piece}+":
            return run
    return piece


#: Slots whose words name what the product IS -- a typo of one of them is not a product line.
CLASS_SLOTS = frozenset({"inverter", "category", "subtype", "capacity", "warranty"})


def _one_edit_apart(one: str, other: str) -> bool:
    """True when the two words differ by exactly one substitution, insertion or deletion."""
    if abs(len(one) - len(other)) > 1 or one == other:
        return False
    if len(one) == len(other):
        return sum(1 for first, second in zip(one, other, strict=True) if first != second) == 1
    longer, shorter = (one, other) if len(one) > len(other) else (other, one)
    return any(longer[:skip] + longer[skip + 1 :] == shorter for skip in range(len(longer)))


def _claim_class_typos(present: dict[str, None], class_words: dict[str, str]) -> dict[str, str]:
    """Claim a word that is one letter off from a class word THIS row states.

    The vendor's own spelling is the evidence, so no dictionary and no word list is consulted:
    the row that writes `Haier Inventer ... Inverter Split Air Conditioner` has already given
    `inverter` to the inverter slot, and `inventer` differs from it by one character, so it is
    that word misspelt -- not a line name, and not something the vote should ever be asked to
    weigh.  The comparison is deliberately row-local and only against class words, which is why
    `Frost` beside `Freezer` and `Chrome` beside `Phone` stay names.
    """
    typos: dict[str, str] = {}
    for piece in present:
        if piece in class_words or len(piece) < 5 or not piece.isalpha():
            continue
        for word, slot in class_words.items():
            if len(word) >= 5 and _one_edit_apart(piece, word):
                typos[piece] = slot
                break
    return typos


def _positions(
    pieces: list[str],
    present: dict[str, None],
    offers: tuple[ResidueCandidate, ...],
    code_parts: frozenset[str],
    class_words: frozenset[str],
    vocabulary: _Vocabulary,
) -> dict[str, WordPosition]:
    """Record where each offered name stood, once per name, across the whole row.

    A word a slot claimed for a reason that can be taken back (see REVIVABLE_SLOT) is still a
    candidate: the vote has to see it to decide.  A candidate that occurs twice in one row keeps
    the strongest reading it got -- standing free of codes somewhere in the row is what the vote
    needs to see.

    A joined candidate is read as the one label it is: the pieces on either SIDE of the whole
    pair are what touched it, so `Haier E-Star` is brand-adjacent and `9149WB E-CHROME` is not
    free of codes.

    The two directions of a bare number are NOT the same fact.  A number BEFORE a word is the
    rest of a part number the sheet split with a space (`HRF 418 IFP`, `013W USDC`), so it is
    code evidence.  A number AFTER a word is the size that word sells in (`Frost 30`,
    `Infinity Pro 15`), which is how the stock rows write their identity -- treating it as code
    evidence would delete every name+size pair in the catalogue.
    """
    codes = {
        piece
        for piece in present
        if _has_digit_and_letter(piece) or (piece in code_parts and _LETTER_RE.search(piece))
    }
    positions: dict[str, WordPosition] = {}
    for candidate in offers:
        span = list(candidate.pieces)
        for index in range(len(pieces) - len(span) + 1):
            if pieces[index : index + len(span)] != span:
                continue
            previous = pieces[index - 1] if index else ""
            following = pieces[index + len(span)] if index + len(span) < len(pieces) else ""
            beside = {part for part in (previous, following) if part in codes}
            if previous.isdigit():
                beside.add(previous)
            brand_adjacent = (
                previous in vocabulary.row_brand_words or previous == vocabulary.row_brand
            )
            class_prefixed = any(
                word.startswith(candidate.key) and len(word) >= len(candidate.key) + 2
                for word in class_words
            )
            earlier = positions.get(candidate.key)
            positions[candidate.key] = WordPosition(
                brand_adjacent=brand_adjacent or bool(earlier and earlier.brand_adjacent),
                class_prefixed=class_prefixed or bool(earlier and earlier.class_prefixed),
                beside=frozenset(beside | set(earlier.beside if earlier else ())),
            )
    return positions


def _subtype_words(product_type: str, row_words: tuple[str, ...]) -> frozenset[str]:
    """The sub-type words of THIS row's product type -- phrases claimed only when stated.

    A label is two or more words exactly when the phrase is what names the type: `No Frost` is
    a cooling type, while `Frost` on its own is Dawlance's line, and claiming the words of every
    label in the table would have made `frost` a type word in an air-conditioner row too.  So a
    multi-word label contributes its words only when the row writes the phrase, in order.
    """
    words: set[str] = set()
    for group in _subtype_table().get(product_type, ()):
        for label, aliases in group.items():
            for variant in (label, *aliases):
                parts = _WORD_RE.findall(variant.lower())
                if len(parts) == 1 or _contains_run(row_words, tuple(parts)):
                    words.update(parts)
    return frozenset(words)


def _contains_run(words: tuple[str, ...], run: tuple[str, ...]) -> bool:
    """True when ``run`` appears in ``words`` as a contiguous run."""
    span = len(run)
    return any(words[start : start + span] == run for start in range(len(words) - span + 1))


# --------------------------------------------------------------------------- #
# [4] the corpus vote
# --------------------------------------------------------------------------- #
#: How many brands must share a word before it decorates rather than names.  This is a
#: whole-catalogue judgement and the only one the vote makes: everything else is decided per
#: brand, so two brands sharing a word no longer blocks either of them from earning it on its
#: own rows -- it only means the word is not yet obviously a type word.
BLACKLIST_BRANDS = 3


@dataclass(frozen=True)
class WordEvidence:
    """What the whole run said about one residue word, kept so a decision is reviewable."""

    rows: int
    products: int
    brands: frozenset[str]
    brand_adjacent: int
    code_adjacent: int
    class_prefixed: int
    codes: frozenset[str]


@dataclass(frozen=True)
class Corpus:
    """The run's verdict on every residue word: proven per brand, disqualified, or undecided.

    A word is not a name in the abstract.  ``Frost`` is Dawlance's model line and, on a Haier
    row, half of the type phrase ``No Frost`` -- so the proof belongs to the brand that earned
    it, and one whole-catalogue verdict could only be wrong for one of them.  The maps are
    plain dicts rather than live objects because a later learning area is meant to write them
    out and read them back (plan D11/D12), which is also why the evidence travels with the
    verdict instead of being recomputed from it.
    """

    proven: Mapping[str, Mapping[str, WordEvidence]]
    blacklisted: Mapping[str, WordEvidence]
    undecided: Mapping[str, WordEvidence]

    def is_proven(self, brand: str, word: str) -> bool:
        """True when THIS run proved this word names a line for this brand."""
        return word in self.proven.get(_alnum(brand).lower(), {})


@dataclass
class _Tally:
    """One word's running count while the run is walked."""

    rows: int = 0
    products: set[str] = field(default_factory=set)
    brands: set[str] = field(default_factory=set)
    brand_adjacent: int = 0
    code_adjacent: int = 0
    class_prefixed: int = 0
    codes: set[str] = field(default_factory=set)

    def record(self, word: str, analysis: RowAnalysis) -> None:
        self.rows += 1
        # One shop row is one offer, not one product: the same SKU restated in three colours or
        # tonnage variants used to "prove" the vendor's own typo (`inventer` on 4 Haier rows of
        # one model).  Distinct products is the count that means something.
        self.products.add(analysis.product_key)
        if analysis.brand:
            self.brands.add(analysis.brand)
        position = analysis.positions.get(word, WordPosition())
        self.brand_adjacent += int(position.brand_adjacent)
        self.code_adjacent += int(position.code_adjacent)
        self.class_prefixed += int(position.class_prefixed)
        self.codes |= position.beside

    def evidence(self) -> WordEvidence:
        return WordEvidence(
            rows=self.rows,
            products=len(self.products),
            brands=frozenset(self.brands),
            brand_adjacent=self.brand_adjacent,
            code_adjacent=self.code_adjacent,
            class_prefixed=self.class_prefixed,
            codes=frozenset(self.codes),
        )


def build_corpus(analyses: Iterable[RowAnalysis]) -> Corpus:
    """Vote over a whole run's residue: which words name a line, for which brand.

    Every signal comes from the rows, not from a word list: how many rows of one brand state
    the word, whether it stands clear of a part number somewhere, whether the brand itself
    introduces it, and whether the rows state a longer class word it abbreviates.

    - abbreviates its own class in every row, or shared by three brands: disqualified for all
      of them, because a word that decorates three catalogues names none.
    - one brand, two rows, and clear of every part number in at least one of them: that brand's
      name.  Recurrence alone is NOT the signal -- `USDC` recurs in three rows and is the tail
      of one part number read aloud.
    - one brand, one row: believed when the brand introduces the word and no code touches it,
      which is how a two-row sheet can still state ECO.
    - anything else: undecided, and an undecided word prints nothing.  The vote's silence is
      the safe answer, not a gap to fill with a guess.
    """
    whole_run: dict[str, _Tally] = {}
    per_brand: dict[tuple[str, str], _Tally] = {}
    for analysis in analyses:
        for word in analysis.words:
            whole_run.setdefault(word, _Tally()).record(word, analysis)
            per_brand.setdefault((analysis.brand, word), _Tally()).record(word, analysis)

    blacklisted: dict[str, WordEvidence] = {}
    for word, tally in whole_run.items():
        evidence = tally.evidence()
        if evidence.class_prefixed == evidence.rows or len(evidence.brands) >= BLACKLIST_BRANDS:
            blacklisted[word] = evidence

    proven: dict[str, dict[str, WordEvidence]] = {}
    earned: set[str] = set()
    for (brand, word), tally in per_brand.items():
        if not brand or word in blacklisted:
            continue
        evidence = tally.evidence()
        siblings = (
            evidence.products >= 2
            and evidence.rows >= 2
            and evidence.rows > evidence.code_adjacent
        )
        # A single word standing right after its own brand is the cleanest name a thin sheet can
        # state (`Midea ECO - ...`).  Two words seen once are not: the second may be borrowed, so a
        # pair needs the sibling evidence above, and a row that states it once stays undecided.
        brand_position = (
            len(word.split()) == 1 and evidence.brand_adjacent == 1 and not evidence.code_adjacent
        )
        if siblings or brand_position:
            proven.setdefault(brand, {})[word] = evidence
            earned.add(word)

    undecided = {
        word: tally.evidence()
        for word, tally in whole_run.items()
        if word not in blacklisted and word not in earned
    }
    return Corpus(proven=proven, blacklisted=blacklisted, undecided=undecided)
