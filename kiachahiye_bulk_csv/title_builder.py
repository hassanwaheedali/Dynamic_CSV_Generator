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
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import attributes
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
from sku_handle import (
    SIZE_UNIT_WORDS,
    TYPE_WORDS,
    ModelExtraction,
    find_series_token,
    resolve_capacity,
)
from textutils import (
    BASE_COLORS,
    SERIES_LABEL_LINE_RE,
    SERIES_NAME_BEFORE_RE,
    clean_inline,
    find_full_color,
)
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
# The two spellings a series LABEL takes -- `Series: Thunder Plus` and `the E Luxury Pro
# Series` -- are read by shared regexes in textutils, because `sku_handle.find_series_token`
# answers the same question for the fallback SKU and the two readers must not drift.
SERIES_WORD_RE = re.compile(
    "|".join(rf"\b{re.escape(word)}\b" for word in SERIES_WORDS), re.IGNORECASE
)
#: The inverter signals, spelled exactly as the other two readers spell them: `categories.py`
#: routes the AC leaf with these, and `attributes.py` fills `Attribute_INV/NON-INV` off the same
#: words (`t-ai`, `bldc`, `inverteron`, `brushless`, a glued `non inv`).  One sheet, one answer:
#: a Title that knows fewer synonyms prints no [Inverter] on a row both other readers call one.
INVERTER_RE = re.compile(
    r"\binverter\b|\bdc\s?inverter\b|\bt-?ai\b|\bbldc\b|\binverteron\b|\bbrushless\b",
    re.IGNORECASE,
)
NON_INVERTER_RE = re.compile(
    r"\bnon[\s\-_]?inverter\b|\bnon[\s\-_]?inv\b", re.IGNORECASE
)

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "from", "that", "this", "your", "into",
        "series", "model", "brand", "new", "best", "price", "only",
        "warranty", "warranties", "year", "years",
    }
)


SubtypeSource = Literal["", "label", "list", "carried", "class"]
"""Which rung of the ladder filled the `[Subtype]` slot for one row.

``class`` is the platform's own type table: the row wrote a phrase like `Freezer-On-Top` that no
sub-type group names, and it had to be placed somewhere or DigiMall's Type cell -- which is matched
out of this Title -- would fall empty.
"""


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
    identity_token: str = ""
    """The name-and-number a codeless row wrote for itself (`Twister 1150`), as it reached segment 2.

    The SEO Title sheds by whole token, so this must be shed as the pair the row wrote: cutting
    `Twister` out of `Twister 1150` left a bare `- 1150 -` in the shop's search result.
    """

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
    """Which rung filled the slot: the sheet's own `SubType:` line, the type list, the series
    carry-over, or the platform's own class phrase.  ``""`` means nothing claimed it -- which is the
    safe answer, not a failure."""

    subtype_label_added: bool = False
    """Whether a `SubType:` line was written AND its words reached the Title.

    A line whose every word the Title already prints (`SubType: Air Conditioner`) adds nothing; the
    row ships as it did before, and he wants to be told, because he checks those lines by hand.
    """

    taps_token: str = ""
    """`3 Taps` when the row states a tap count -- carried beside the capacity, never instead of
    reading it, so the formula rewrite can print a dispenser's taps AND its litres."""

    volume_capacity_token: str = ""
    """The row's volume capacity (`15 Ltr`) as resolved before a tap count took the capacity slot.

    On a Water Dispenser the two facts are different answers -- how many taps, how big the tank --
    and the old assembly overwrote one with the other."""

    subtype_line: str = ""
    """What the row's `SubType:` line said, verbatim, whether or not it was used -- the flag needs
    to quote the line back to the person who wrote it, and re-parsing the Description for that would
    read it a second way."""

    subtype_label_note: str = ""
    """Why a written `SubType:` line added no word, in the builder's own knowledge: the row kept its
    source wording, the line restates what the Title already prints, or the value was a sentence.
    Empty when the line was used."""

    subtype_conflicts: tuple[tuple[str, str], ...] = ()
    """Per question this row's two columns answered DIFFERENTLY: (Title value, Description value).

    A row that sells a `Cassette` in its ad and a `split` in its vendor template is one row claiming
    two machines, and no reader can settle that from letters.  The slot stays empty -- a wrong value
    in a closed `Attribute_... Type` list ships a product the shop never sold, while an empty one is
    a question -- and the pair travels to the QC report for the owner to answer once.
    """

    subtype_undecided_columns: tuple[str, ...] = ()
    usp_tokens: tuple[str, ...] = ()
    seo_base_title: str = ""
    """The `Attribute_... Type` columns an unsettled disagreement leaves this row unable to answer.

    DigiMall's matcher reads the Title first and his Description next, and the Description is where
    the template sentence lives -- so a cell the row cannot stand behind is withheld here too,
    instead of walking back in through the fallback.
    """


# ---------------------------------------------------------------------------
#  Token helpers
# ---------------------------------------------------------------------------
#: The words a model-code clause is padded with: a paint or material abbreviation, or the sheet's own
#: filler.  None of them names a line, and none of them ends the scan.
_SLOT_SKIP_RE = re.compile(r"^(?:[A-Z][A-Z0-9+.\-]{1,7})$")
#: On a sheet typed entirely in capitals, casing carries no signal at all, so only a SHORT block is a
#: paint code there: `Dawlance ... - 9173WB AVANTE` names the Avante, while `DSS-9055 INV Inox` still
#: steps over `INV`.  `sku_handle.find_series_token` reads the same shouty test for the same reason.
_SLOT_SHOUTY_SKIP_RE = re.compile(r"^(?:[A-Z][A-Z0-9]{1,2})$")
_CLAUSE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+.\-]*")
#: A name's `+` is often spaced off it (`9193LF AVANTE + GD INV`), and `Avante+` is a different
#: product from `Avante`, so the sign is read as its own part and glued back onto the word.
_CLAUSE_PART_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+.\-]*|\+")
#: The separators a sheet puts around its clauses: a hyphen, or the en/em dash a typed sheet uses.
_CLAUSE_SPLIT_RE = re.compile(r"\s+[-\u2013\u2014]\s+")
#: The repo's own colour vocabulary, read from the module that owns it: the words that say how the
#: machine is painted, which is exactly the set R1 keeps out of the name seat.
_COLOURWAY_WORDS = series_corpus.colour_words()


def colourway_words(source_title: str, color: str) -> set[str]:
    """The first half of a two-word paint name, when this row wrote one.

    `Cloud White`, `Mystic Grey`, `Hazel Red`: the repo's own colour tables call the first word a
    colour, and standing immediately in front of the row's colour it is half of what the machine is
    PAINTED -- which is how a Dawlance freezer was sold as a `Cloud`.

    One word, one step, and only from that table.  `Haier Pearl DC Inverter Air Conditioner 1.5 Ton
    Silver` keeps Haier's `Pearl`, `Orient Crystal 3 Taps Water Dispenser` keeps Orient's `Crystal`,
    and `PEL ... Hazel Red Blaze` keeps PEL's `Blaze`: a word is swallowed only by the paint it
    actually stands inside, and a name parked in front of a size is a name.
    """
    head = _CLAUSE_SPLIT_RE.split(source_title)[0]
    # Cut on every non-letter, so a sheet that hyphenates its paint -- `Pearl-Copper` -- spends the
    # same word as one that spaces it.
    keys = [match.group(0).lower() for match in re.finditer(r"[A-Za-z]+", head)]
    painted = _COLOURWAY_WORDS | set(color.lower().split())
    taken: set[str] = set()
    for index, key in enumerate(keys):
        if key not in painted:
            continue
        before = keys[index - 1] if index else ""
        if before in _COLOURWAY_WORDS:
            taken.add(before)
    return taken


def warranty_words(warranty: str) -> set[str]:
    """The words of this row's own warranty statement, which no seat may reuse.

    `Lifetime Compressor Warranty` is a promise about how long the machine is covered, and the sheet
    writes it in the clause the formula reserves for `[Main Warranty]` -- or in its Description, where
    `warranty.resolve_main_warranty` already reads it.  Either way the pipeline ends up holding that
    statement as one string, so its words are spent before any name is looked for, and no clause
    punctuation has to be guessed at.
    """
    return {token.lower() for token in _CLAUSE_TOKEN_RE.findall(warranty)}


def _is_code_token(token: str, following: str) -> bool:
    """Whether this token in the clause is the model code the formula puts there.

    Letters and digits together (`9173WB`, `380I`, `KRF-23357`, `HR-47452`), or a number the row wrote
    on its own (`9173`).  `12` in front of `Years` is a warranty, and `White` is a colour -- neither is
    a code, and treating one as the code would read the clause beside it as the machine's name.
    """
    key = token.lower()
    if key in _NOT_A_NAME_WORDS:
        # The same set the seat is read with, defined below with the words it is built from.
        return False
    if not any(character.isdigit() for character in token):
        return False
    # A decimal is a size in the unit the category is sold in (`12.5` Cu Ft, `1.5` Ton) and never a
    # part number, whatever else it looks like.
    if re.fullmatch(r"\d+[.,]\d+", token):
        return False
    if re.fullmatch(r"\d+", token):
        return len(token) >= 3 and following.lower() not in SIZE_UNIT_WORDS
    return True


def _slot_refuses(token: str, key: str, banned: frozenset[str]) -> bool:
    """Whether this word says what the machine IS (or is painted, or is warranted) -- not which line.

    Nothing here is a list of words this function keeps: `_NOT_A_NAME_WORDS` (defined below, with the
    type, category, colour, size and warranty tables it is built from) is the repo's own answer to
    "this word cannot be a name", and `names_a_class` is the test the corpus vote already uses.  A
    word that opens with a long technology word -- `InverterOn`, `DirectCool` -- is that technology
    written camel-case, and a size (`10kg`, `1.5 TON`) or a bare number is the machine's measure,
    which `[Capacity]` and `[Model]` already state.

    Only the SLOT is read with this.  A name the row positioned beside its own code is evidence; the
    same word written loose in the descriptive part is the guesser path's business, where `Pearl`
    really is Haier's line and a colour table alone cannot know that.
    """
    if len(key) < 3 or key.isdigit():
        return True
    # Read on its letters too, or a name wearing the paint's punctuation -- `Pearl+` for `Pearl` --
    # steps past the very ban R1 puts on it.
    forms = {key, "".join(character for character in key if character.isalpha())}
    if forms & _NOT_A_NAME_WORDS or forms & banned:
        return True
    if series_corpus.names_a_class(token) or _SIZE_ANSWER_RE.match(token):
        return True
    return any(len(word) >= 8 and key.startswith(word) for word in TYPE_WORDS)


def beside_model_code(
    source_title: str, model: str, banned: frozenset[str] = frozenset()
) -> tuple[str, str]:
    """The name the row wrote beside its model code, and whether the row has such a clause at all.

    The formula writes `[Model] [Series]` in one ` - ` clause after the descriptive part, so THAT
    clause -- not the whole Title -- is the row's own answer to "which line is this":
    `9173WB Chrome`, `9193LF Acce`, `9178LF Avante+`, `Ultron 380I GD`, `HR-47452 BKG Tech Inverter`.

    A paint abbreviation (`BKG`, `GD`, `VCM`, `MRG`) or a filler (`New`) is stepped over, because the
    sheet stands them in the same clause; the first word that could be a name is taken and its
    immediate neighbours with it, up to three, in the order the row wrote them -- `Ref Avante 9173WB`
    is the line the sheet named, never its letters reversed.  A word naming the class, the colourway,
    the warranty or the technology ends the scan and reports an empty slot: the row said nothing
    there, and silence is right where a guess would be wrong.

    When the row resolved NO code at all, a bare number is not allowed to stand in for one: beside it
    the name must be touching the number, because ` - 828 New Design -` is a stock number followed by
    a sentence, and a sentence stepped over its first word invents a line (`Design`) that then
    crowds out the name the run's vote actually proved.

    A `+` the sheet spaced off its word is glued back (`AVANTE + GD INV` is `Avante+`, a different
    product from `Avante`), and on a sheet typed in capitals only a SHORT block is read as a paint
    code, because there `AVANTE` and `INV` look exactly alike to a casing test.

    An empty clause means the Title was written without the ` - ` clauses at all -- there is no slot
    to read here, and the curated path stays in charge exactly as it was.
    """
    clauses = _CLAUSE_SPLIT_RE.split(source_title)
    shouty = source_title.upper() == source_title
    spoken_clause = ""
    for clause in clauses[1:]:
        tokens = _CLAUSE_PART_RE.findall(clause)
        code_index = -1
        bare_number = False
        for position, token in enumerate(tokens):
            following = tokens[position + 1] if position + 1 < len(tokens) else ""
            if not _is_code_token(token, following):
                continue
            if model:
                # The anchor is THIS row's resolved code: a clause carrying some other number is the
                # warranty or the size, and reading beside it would name the machine after its price.
                if token.lower() in model.lower():
                    code_index = position
                    break
                continue
            # With no code resolved, the row's own part number is still the clause's anchor -- but a
            # bare number (`828`) is a stock number or a size, and the words around it are prose: the
            # name has to be TOUCHING it, or `- 828 New Design -` makes a line of `Design`.
            code_index = position
            bare_number = not any(character.isalpha() for character in token)
            break
        if code_index == -1:
            continue
        if not spoken_clause:
            # The row put its code in a clause of its own, so its name slot exists: a later rung may
            # not guess past it, even when this clause held a paint code and nothing else.
            spoken_clause = clause
        before = list(reversed(tokens[:code_index]))
        for run in (tokens[code_index + 1 :], before):
            kept: list[str] = []
            trailing_plus = False
            for token in run:
                key = token.lower()
                if token == "+":
                    # The sign belongs to the word in front of it, and to nothing else: a row that
                    # wrote `+` with no name behind it wrote a sum, not a line.  Read backwards, the
                    # word in front of it is the one this scan meets NEXT (`AVANTE + 9178LF`).
                    if kept:
                        kept[-1] = f"{kept[-1]}+"
                    elif run is before:
                        trailing_plus = True
                        continue
                    else:
                        break
                    continue
                if _slot_skips(token, shouty) or _slot_refuses(token, key, banned):
                    # The sheet stands a paint code or a filler word in the same clause as the name;
                    # once a name has begun, either of them ends it instead of joining it.  And beside
                    # a bare number the name has to stand TOUCHING it: `- 828 New Design -` is a stock
                    # number followed by a sentence, and stepping over `New` made a line of `Design`.
                    if kept or bare_number:
                        break
                    continue
                kept.append(f"{token}+" if trailing_plus else token)
                trailing_plus = False
                if len(kept) == 3:
                    break
            if run is before:
                kept.reverse()  # read backwards to find it, print it the way the row spelled it
            # Each word alone can look like a name while the phrase they spell says what the machine
            # IS: `Side` is not a type, `Side By Side` is, and shipping the first of them sold a
            # fragment of a class word as Dawlance's line.
            if kept and series_corpus.names_a_class(" ".join(kept)):
                kept = []
            if kept:
                return " ".join(kept), clause
    return "", spoken_clause


def _slot_skips(token: str, shouty: bool) -> bool:
    """Whether this token is a paint code the scan steps over rather than a name."""
    if shouty:
        return bool(_SLOT_SHOUTY_SKIP_RE.match(token))
    return bool(_SLOT_SKIP_RE.match(token))


def _series_name(capture: str, banned: frozenset[str] = frozenset()) -> str:
    """The name inside a labelled series capture, with its leading junk peeled off.

    The shared readers capture up to three words -- `E Luxury Pro Series` names `E Luxury Pro` --
    so whatever stands in FRONT of the real name is captured with it: `White HPU-24HDZ Duzin
    Series` names `Duzin`, and `Dawlance Avante Series` names `Avante`.  A label value may also
    repeat the label's own keyword (`Series: KB Series` names `KB`), so a trailing `Series` goes
    first.  Only LEADING words are then peeled, and only ones the repo's own tables already refuse
    -- a word carrying digits (a code), a brand name, `_NOT_A_NAME_WORDS` minus the identity words
    (`Pro`, `Plus`, `Turbo`, `Master`, which a shop really does begin a line with), and the words
    this row already spent elsewhere.  The word touching `Series` is the name itself, so digits
    never peel IT: `K85 Series` names `K85`, a line whose letters happen to be digits.  Nothing
    here is a keep-list; after the first word survives, the rest of the capture is the shop's own
    spelling and travels whole.
    """
    words = capture.split()
    if words and words[-1].lower() == "series":
        words.pop()
    last = len(words) - 1
    for index, head in enumerate(words):
        key = head.lower()
        if (
            (index != last and any(character.isdigit() for character in head))
            or key in series_corpus.brand_words()
            or (key in _NOT_A_NAME_WORDS and key not in IDENTITY_NAME_WORDS)
            or key in banned
        ):
            continue
        return " ".join(words[index:])
    return ""


def extract_series(
    text: str,
    model: str = "",
    banned: frozenset[str] = frozenset(),
    product_type: str = "",
) -> str:
    """The series name the source itself states, or ``""``.

    Four spellings are honoured, in this order: an explicit ``Series:`` spec line (the row's own
    label, the same mechanism as ``Model:`` and ``Warranty:``); a name written before the word
    ``Series`` (``the E Luxury Pro Series``); the word the row wrote BESIDE its model code, which
    is where the formula puts the name (`9173WB Chrome`, `Ultron 380I GD`); and one of the
    curated :data:`SERIES_WORDS`.

    The slot outranks everything but the label because it is the row's own answer, positioned: the
    old reader took the FIRST capitalised word in the Title instead, and on a sheet written
    `[Brand] [size] [colour] [type] [category] - [code] [name] - [warranty]` that word is always the
    colour -- `Pearl`, `Coral`, `Cloud`, `Hairline` -- three characters from the front of the row and
    never its name, while the name at char 82 is never reached.

    Once the row has written a clause holding its code, nothing is guessed after those three: an
    empty seat is correct and a leftover word is not.  `banned` carries the words this row already
    spent -- its colourway, its type words.
    """
    for regex in (SERIES_LABEL_LINE_RE, SERIES_NAME_BEFORE_RE):
        match = regex.search(text)
        if match:
            named = _series_name(match.group(1), banned)
            if named:
                return named
    title = text.splitlines()[0] if text else ""
    name, clause = beside_model_code(title, model, banned)
    if name:
        return name
    word = SERIES_WORD_RE.search(text)
    # Capitalised only: a curated word in lowercase is prose, not a name -- `orders are paid in
    # advance` sold a Homage refrigerator as the `advance` line the moment the label rung above
    # stopped swallowing the text with its own (empty) answer.
    if word and word.group(0)[0].isupper() and word.group(0).lower() not in banned:
        return word.group(0)
    if clause:
        return ""
    guess = find_series_token(text, banned)
    # The leftover-word reader stops at a class word when it is one token (`Freezer-on-top`) and not
    # when the sheet spaced it (`Side By Side`), so the phrase is tested around the word it picked:
    # a word that only says what the machine IS cannot be the name, and `[Subtype]` already has it.
    if guess and _says_what_it_is(guess, text, product_type):
        return ""
    return guess


def _heads_class_phrase(word: str, text: str) -> bool:
    """Whether this word is only a piece of a class phrase the row spaced out.

    `Side` names nothing on its own, but `Side By Side` is what the platform calls the machine, and
    the leftover-word reader stranded the first of them into the name slot.  Every window of two to
    four words that contains this one is asked of the same test the corpus vote uses.
    """
    tokens = _CLAUSE_TOKEN_RE.findall(text)
    try:
        position = next(
            index for index, token in enumerate(tokens) if token.lower() == word.lower()
        )
    except StopIteration:
        return False
    for size in (2, 3, 4):
        for start in range(max(0, position - size + 1), min(position + 1, len(tokens) - size + 1)):
            window = " ".join(tokens[start : start + size])
            if series_corpus.names_a_class(window):
                return True
    return False


def _says_what_it_is(word: str, text: str, product_type: str = "") -> bool:
    """Whether a candidate name only says what the machine is: a type, a class, a size, a warranty.

    The test the name SLOT is read with, minus the row's own colour words.  A vote or a curated hit
    has no position behind it, so `Inverter` and the `Multi` stranded out of `Multi Door` still have
    to be stopped -- while `Pearl`, `Room` and `Crystal`, which the tables also call colours, are
    real lines the shop sells and stay where the vote put them.

    Only a lone word is read word by word.  A name spelled over several words carries its own type
    word inside it -- Kenwood sells `E Luxury Pro`, and `Pro` there is part of the line, not the
    machine's shape -- so a phrase is refused only when the WHOLE of it is what the platform's own
    tables call the product.

    `product_type` adds the columns THIS row is asked: `Cassette` is a value of
    `Attribute_Air Conditioner Type` and nothing else, so on an air-conditioner row it says what the
    machine IS -- while `Mini` stays a line name for a brand whose list does not spell a type that way.
    """
    parts = word.split()
    if len(parts) > 1:
        return series_corpus.names_a_class(word)
    for part in parts:
        key = part.lower()
        if len(key) < 3:
            continue  # an initial glued to a word (`E-Chrome`) travels with its name
        if (
            key in CATEGORY_WORDS
            or key in TYPE_WORDS
            or key in SIZE_UNIT_WORDS
            or (product_type != "" and key in series_corpus.class_words(product_type))
            or series_corpus.names_a_class(part)
            or _SIZE_ANSWER_RE.match(part)
            or _heads_class_phrase(part, text)
        ):
            return True
    return False


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
    conjunction, open bracket, or a half-written unit."""
    if len(title) <= limit:
        return title
    cut = title[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,-/|(")
    return cut or title[:limit].rstrip(" ,-/|(")


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
    # 33 microwave rows print `Solo`/`Grill` behind the model code as if it were a line name; the
    # words say what the oven does, so they belong here, before the category.
    "Microwave Oven": (
        {
            "Convection": ("convection",),
            "Grill": ("grill",),
            "Solo": ("solo",),
        },
    ),
    "Water Dispenser": (
        {
            "Bottom Load": ("bottom load",),
            "Top Load": ("top load",),
            "Table Top": ("table top",),
        },
    ),
}


# EDIT HERE -- the unit vocabulary lives in `sku_handle.SIZE_UNIT_WORDS`, beside TYPE_WORDS: the
# model reader needs it too, and one list serves both.  It is imported at the top of this file.

# EDIT HERE -- words a shop says INSIDE a model name, so the type list above may not block them:
# `Chrome Plus 45`, `Infinity Pro 15`, `Sprinter Turbo` are the name, not the technology.  `Star` is
# deliberately NOT here: on its own it is an energy rating, and Haier's `E-Star` reaches the Title
# through the vote, whole -- a half name read off one side of its own hyphen is worse than silence.
IDENTITY_NAME_WORDS: frozenset[str] = frozenset({"plus", "pro", "turbo", "master"})

# EDIT HERE -- words that name a machine's shape, size, colour or spec answer.  A stock name is the
# run of words a shop actually says -- `Frost 30`, `Chrome Plus 45`, `Twister 1150` -- and these
# words are never part of one: they are the category, the type, the technology or the paint.
# TYPE_WORDS is the sheet's own list of words that carry no model information, so it is reused here
# rather than a second copy of the same vocabulary being kept by hand.
_NOT_A_NAME_WORDS: frozenset[str] = (
    CATEGORY_WORDS
    | SIZE_UNIT_WORDS
    | TYPE_WORDS
    | frozenset(BASE_COLORS)
    | {
        "inverter", "non", "series", "model", "type", "size", "capacity", "brand",
        "google", "android", "qled", "oled", "uhd", "fhd", "hd", "smart", "digital",
        "manual", "semi", "fully", "automatic", "auto", "top", "front", "load",
        "loading", "door", "doors", "glass", "single", "double", "triple", "side",
        "by", "french", "vertical", "horizontal", "mounted", "mount", "standing",
        "floor", "wall", "table", "twin", "tub", "tubs", "cabinet", "cool", "heat",
        "hot", "with", "and", "the", "for", "new", "best", "price", "buy", "online",
        "wifi", "wi", "iot", "remote", "touch", "copper", "year", "years", "warranty",
        "free", "yes", "no",
    }
)

# The identity ladder may not eat a name, but a `Model:` sentence is prose first and a code last, so
# the peel is allowed to remove these too: a vendor who answers `Model: Turbo Inverter Split 1.5 Ton`
# wrote a sentence, not a name.
IDENTITY_NOT_A_NAME: frozenset[str] = _NOT_A_NAME_WORDS - IDENTITY_NAME_WORDS

# A stock number is 2-4 digits, optionally with one letter tail (`1150`, `20M`).  It is not a
# fragment of a longer token -- the `405` inside `HDF-405INV` belongs to a code -- it is not the
# digits of a dashed part number (`PMO-23`), and it is not the whole side of a decimal size: the
# `12` inside `12.5 Kg` is a weight.
_IDENTITY_NUMBER_RE = re.compile(r"(?<![\w\u2013\u2014.-])(\d{2,4}[A-Za-z]?)(?![\w.-])")
# A number followed by its unit is the product's size, stated plainly, and not its name.  The inch
# mark is a unit too, and it is written glued to the digits: `55"`.
_SIZE_UNIT_RE = re.compile(
    r'^\s*(?:["\u201d\u2033]|(?:'
    + "|".join(sorted(SIZE_UNIT_WORDS, key=lambda w: (-len(w), w)))
    + r")\b)",
    re.IGNORECASE,
)
_NAME_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z+]*")
# A whole answer of a number WITH its unit (`1.5 Ton`, `9000 BTU`, `55 Inches`) is a size the vendor
# typed into the `Model:` cell, not a code.  A bare `30` or `2101` is their own answer and stays --
# this sheet writes real codes as bare digits, so only the unit word gives the shape away.
_SIZE_ANSWER_RE = re.compile(
    r'^\d+(?:[.,]\d+)?\s*["\u201d]?(?:'
    + "|".join(sorted(SIZE_UNIT_WORDS, key=lambda w: (-len(w), w)))
    + r")\.?$",
    re.IGNORECASE,
)


def word_identity(title: str, brand: str) -> str:
    """The name-and-number a row writes when it never wrote a model code: `Frost 30`, `15 Econo`.

    The shop sells these products by that pair, so nothing tidier may be invented for them.  The
    answer is the run of name words the row wrote around the number, in the order it wrote them --
    `Frost 30 Inverter` gives `Frost 30` and `ECM 3500 Plus DC` gives `ECM 3500 Plus DC`.  A number
    written in its own unit is a size, not a name, and a word that names the category, the type, the
    drive or the colour is not part of a name either.  At most three name words may be taken, so a
    row that says nothing but marketing prose yields nothing rather than a sentence.
    """
    brand_words = {word.lower() for word in _NAME_TOKEN_RE.findall(brand)}

    def is_name(word: str) -> bool:
        return (
            len(word) > 1
            and word.lower() not in IDENTITY_NOT_A_NAME
            and word.lower() not in brand_words
        )

    for match in _IDENTITY_NUMBER_RE.finditer(title):
        after = title[match.end():]
        if _SIZE_UNIT_RE.match(after):
            continue
        before = title[: match.start()]
        head_run: list[str] = []
        while len(head_run) < 3:
            head = re.search(rf"({_NAME_TOKEN_RE.pattern}) ?$", before)
            if head is None or not is_name(head.group(1)):
                break
            head_run.insert(0, head.group(1))
            before = before[: head.start()]
        tail_run: list[str] = []
        while len(head_run) + len(tail_run) < 3:
            tail = re.match(rf" ?({_NAME_TOKEN_RE.pattern})", after)
            if tail is None or not is_name(tail.group(1)):
                break
            # `Plus` and `Pro` are suffixes: they join a name only behind one.  A row that writes
            # `Refrigerator 90 Plus Double Door` states a size and a suffix, and the suffix alone is
            # not a name -- reading it as one shipped that row as `Plus 90`.
            if not head_run and tail.group(1).lower() in IDENTITY_NAME_WORDS:
                break
            tail_run.append(tail.group(1))
            after = after[tail.end():]
        if not head_run and not tail_run:
            continue
        # Only a name word written before the number lets the words after it keep their place; a
        # row that leads with the number (`30 Econo`) is read as `Econo 30`, the way the shop says it.
        if head_run:
            return " ".join([*head_run, match.group(1), *tail_run])
        return f"{' '.join(tail_run)} {match.group(1)}"
    return ""


def without_leading_type_words(extraction: ModelExtraction) -> ModelExtraction:
    """`Inverter Frost 30` -> `Frost 30`: a `Model:` line the vendor answered with prose.

    The line is the sheet's own answer, but it is often a short sentence with the code at the end.
    Words that name a shape or a drive are not part of a code, so they are peeled until a word that
    could be a name is left -- and a code that was already clean comes back untouched, because
    `Icon 3 Taps Water Dispenser` really is Orient's `Icon` and nothing here may eat its name.
    Unlike the name scan, the peel also drops `Plus`, `Pro` and `Turbo`: a line that OPENS with one
    of those is a sentence about the machine, and shipping it whole built the SKU
    `KIA-TURBOINVERTERSPLIT1.5TON` out of a size.
    """
    if extraction.source != "description-model-line" or not extraction.code:
        return extraction
    # A cell filled with a number and its unit states the size, not a code (`18000 BTU`), whether it
    # needed peeling to say so or not.  A bare `2101` is the vendor's own answer and stays.
    if _SIZE_ANSWER_RE.match(extraction.code):
        return ModelExtraction("", extraction.source, "none")
    tokens = extraction.code.split()
    while len(tokens) > 1 and tokens[0].lower() in _NOT_A_NAME_WORDS:
        tokens.pop(0)
    cleaned = " ".join(tokens)
    if not cleaned or cleaned == extraction.code:
        return extraction
    if _SIZE_ANSWER_RE.match(cleaned):
        return ModelExtraction("", extraction.source, "none")
    return ModelExtraction(cleaned, extraction.source, extraction.confidence)


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
#: A type word standing behind one of these in its own clause was denied, not stated.  Deliberately
#: casing-aware on the RAW clause: `No Frost` is a type the platform enumerates, so a case-insensitive
#: `no` reads nine Dawlance/Haier rows' own `Freezer-On-Top` as a denial and drops the wording the
#: closed-list matcher in `attributes.py` needs to find the value the row actually earned.  Measured:
#: no Title on the sheet writes a capitalised denial; three Descriptions do, and those clauses reach
#: the matcher through `_clauses()`, which lowercases first and so IS read case-insensitively.
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
    """The label this group's aliases stand for in these clauses, un-negated -- the longest if two.

    A group's list is written most-specific first (`Wall Mounted Split` before `Wall Mounted` before
    `Split`), and the platform's longer label is the fuller spelling of ONE machine, so when a row's
    words satisfy two nested labels the longer is the answer: `Split` beside `Wall Mounted Split` is
    one AC spelled twice, not a row contradicting itself, and the closed list carries the longer.
    """
    best = ""
    for label, aliases in group.items():
        for alias in aliases:
            needle = _spaced_words(alias)
            for clause in clauses:
                start = clause.find(needle)
                if start >= 0 and not _NEGATION_RE.search(clause[:start]):
                    if len(label.split()) > len(best.split()):
                        best = label
                    break
            else:
                continue
            break
    return best


def _compound_value(first: str, second: str) -> str:
    """The platform's ONE value whose words are exactly these two runs put together.

    `Split` in the ad and `Wall Mounted` in the row's own `Type:` bullet are the two runs of
    `Wall Mounted Split`, which the closed air-conditioner list carries: the row named ONE machine in
    two pieces, so the pieces join and nothing is flagged.  The same test on `Split` and
    `Floor Standing` searches the same list and finds no such value, because those are two machines
    -- which is why this is a reading of the platform's table and not a list of words to forgive.

    An empty side returns nothing: one column's word is not a run of a two-part value, it is that
    column's own answer, and the join must never hand a word to a row whose other column said
    nothing (an empty disjunction would otherwise make the FIRST column's value the answer to
    whatever its second word happened to combine with).
    """
    if not first or not second:
        return ""
    wanted = set(_spelling_words(first)) | set(_spelling_words(second))
    if len(wanted) != len(_spelling_words(first)) + len(_spelling_words(second)):
        return ""  # they share a word: one is inside the other, and the caller already knows that
    for column, values in attributes.ALLOWED.items():
        if not column.endswith(" Type"):
            continue
        for value in values:
            if set(_spelling_words(value)) == wanted:
                return value
    return ""


def _nests(shorter: str, longer: str) -> bool:
    """Whether one value's words stand, unbroken, inside the other's.

    `Split` inside `Wall Mounted Split` is the same machine spelled by the platform's longer label,
    not a second answer: 14 rows on this sheet state a type one way in the ad and the other way in
    the prose, and calling that a contradiction would empty 14 filled cells.
    """
    a, b = _spelling_words(shorter), _spelling_words(longer)
    return len(a) <= len(b) and any(
        b[start : start + len(a)] == a for start in range(len(b) - len(a) + 1)
    )


def extract_subtype_groups(
    product_type: str, source_title: str, source_description: str = ""
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[int, str, str], ...]]:
    """Per group: what this row answers, the words it spent getting there, and what it cannot settle.

    A group is answered by whichever of the row's two columns names it (owner ruling, 2026-10-23).
    The Title and the Description are read as EQUAL evidence, because on this sheet neither is the
    trusted one: 154 group answers come only from the prose -- the side the ad never spelled -- and
    47 come only from the Title.

    When BOTH columns answer the same group they must agree, and agreement is spelled one way:
    identical, or one value's words standing inside the other (`Split` and `Wall Mounted Split` are
    the platform's two labels for one machine, and the longer is taken).  Two values that neither
    match nor nest are one row claiming two machines -- `Haier 4 Way Cassette ... (HBU-18HE)` whose
    vendor sentence reads `... is a 1.5 Ton DC Inverter split air conditioner`, a template that says
    `split` on 204 rows of this sheet and is wrong on 6 of them.  The builder then answers NEITHER
    and hands the pair to the owner as a decision, because a guessed value inside
    `Attribute_Air Conditioner Type` is a wrong shipping fact while an empty one is a question he can
    answer in one line.

    Every word the row wrote toward a group that went unanswered or was out-spelled travels back in
    `overruled`: a type word is spent, and may not be resold behind the model code where a line name
    belongs.

    A conflict carries the GROUP it belongs to, not just its two words, because the thing that closes
    a decision is his `SubType:` line answering THAT question -- and he may answer it with a third
    value neither column fought over (`SubType: Cassette` on a row whose Title said `Floor Standing`
    and whose prose said `split`).  Matching the closed pairs on words instead would leave such a row
    flagged while its Title prints the very word the flag told him to write.
    """
    title_clauses = _clauses(source_title)
    description_clauses = _clauses(source_description)
    answers: list[str] = []
    overruled: list[str] = []
    conflicts: list[tuple[int, str, str]] = []
    for position, group in enumerate(subtype_groups(product_type)):
        from_description = _group_label(group, description_clauses)
        from_title = _group_label(group, title_clauses)
        if from_title and from_description:
            if from_title == from_description:
                answer = from_title
            elif _nests(from_title, from_description):
                answer = from_description
            elif _nests(from_description, from_title):
                answer = from_title
            elif _compound_value(from_title, from_description):
                # One machine named in two pieces: the ad says `Split`, the row's own `Type:` bullet
                # says `Wall Mounted`, and the closed list carries `Wall Mounted Split` -- so the
                # pieces join into the value the platform actually offers, and both runs are spent.
                answer = _compound_value(from_title, from_description)
                overruled.extend((from_title, from_description))
            else:
                answer = ""
                conflicts.append((position, from_title, from_description))
                overruled.extend((from_title, from_description))
        else:
            # Only one column spoke, or neither did: the row's own word stands, and nothing is spent.
            answer = from_title or from_description
        answers.append(answer)
    return tuple(answers), tuple(overruled), tuple(conflicts)


def _spelling_words(spelling: str) -> list[str]:
    """The lower-case letter-and-digit words of a vocabulary spelling.

    `Side-By-Side` gives `side by side` and `Heat & Cool` gives `heat cool`: the marks a shop puts
    BETWEEN the words of its own values -- hyphens, ampersands -- are that shop's handwriting, and
    matching is on the words.
    """
    return [word.lower() for word in re.findall(r"[A-Za-z0-9]+", spelling)]


#: Lazily built, per product type: every vocabulary key mapped to how the shop writes it.
_CANONICAL: dict[str, dict[str, str]] = {}


def _canonical_spellings(product_type: str) -> dict[str, str]:
    """Every spelling this category's type vocabulary knows, mapped to the shop's own version.

    Not a vocabulary kept by hand: the type list's printed labels AND aliases, plus the values the
    platform enumerates in the Type columns that answer for THIS product type (`attributes.SCOPE`).
    A vendor who writes `heat and cool` is asking for the shop's own value `Heat & Cool`, and the
    right spelling is read from where that value lives.  Aliases join so one reader cannot undo
    what another reads -- the list matches a row through `heat and cool`, and the same words in a
    `SubType:` line must re-spell through them, not stand next to them.
    """
    cached = _CANONICAL.get(product_type)
    if cached is None:
        found: dict[str, str] = {}
        for group in subtype_groups(product_type):
            for label, aliases in group.items():
                for spelling in (label, *aliases):
                    found.setdefault(" ".join(_spelling_words(spelling)), label)
        for column, scope in attributes.SCOPE.items():
            if not column.endswith(" Type"):
                continue
            if scope is not None and product_type not in scope:
                continue
            for value in attributes.ALLOWED.get(column, ()):
                found.setdefault(" ".join(_spelling_words(value)), value)
        cached = found
        _CANONICAL[product_type] = cached
    return cached


def canonical_type_value(value: str, product_type: str) -> str:
    """Re-write a vendor's type words in the shop's own spellings; keep an unknown word as written.

    Matching is longest-first and by word count: `heat  cool` is the two words of `Heat & Cool`,
    while `heat cool cool` is three words no two-word value may stand for.  An unmatched lower-case
    word at least starts with a capital, so a Title never ships `Heat & cool` -- one fact, two
    spellings.
    """
    spellings = sorted(_canonical_spellings(product_type), key=lambda s: (-len(s.split()), s))
    # One value, written in the row's own punctuation: `Freezer-on-top` IS the platform's
    # `Freezer-On-Top`, and a shelf that shows both spellings shows one fact twice.  Tested as the
    # WHOLE phrase, so `heat cool cool` -- three words no two-word value owns -- still falls through
    # to the window loop below and is left as written.
    whole = " ".join(_spelling_words(value))
    known = _canonical_spellings(product_type)
    if whole in known:
        return known[whole]
    words = value.split()
    out: list[str] = []
    index = 0
    while index < len(words):
        for spelling in spellings:
            tokens = spelling.split()
            candidate = words[index : index + len(tokens)]
            if len(candidate) == len(tokens) and " ".join(
                _spelling_words(" ".join(candidate))
            ) == spelling:
                out.append(_canonical_spellings(product_type)[spelling])
                index += len(tokens)
                break
        else:
            word = words[index].strip(".,:;!?\u2013\u2014")
            out.append(word.capitalize() if word.islower() else words[index])
            index += 1
    return " ".join(out)


def _type_column(phrase: str) -> str:
    """The platform Type column that enumerates this value verbatim, or ``""``.

    Which values answer which question is the platform's table, read here, not authored.
    """
    needle = " ".join(_spelling_words(phrase))
    for column, values in attributes.ALLOWED.items():
        if not column.endswith(" Type"):
            continue
        for value in values:
            if " ".join(_spelling_words(value)) == needle:
                return column
    return ""


def _owns_column(column: str, group: dict[str, tuple[str, ...]], except_word: str) -> bool:
    """Whether every value of this platform column but one stands inside this one group.

    A column whose whole list lives in one SUBTYPES group asks exactly that group's question, so
    ANY value of it -- even one the group has no alias for, like `Cassette` -- is that same
    question answered differently, and the two may never stack (`Split Cassette Air Conditioner`
    names two machines, and DigiMall's matcher would pick one of them at random).  A column whose
    values span two groups is asked two questions at once -- `Attribute_Washing Machine Type`
    enumerates both `Twin Tub` and `Top Load`, and the shop stacks them in one Title routinely --
    so sharing it is no contradiction, and the builder may not forbid what its own table prints.
    """
    if column == "":
        return False
    table: set[str] = set()
    for label, aliases in group.items():
        table.add(" ".join(_spelling_words(label)))
        table.update(" ".join(_spelling_words(alias)) for alias in aliases)
    needle = " ".join(_spelling_words(except_word))
    held = [
        " ".join(_spelling_words(value))
        for value in attributes.ALLOWED.get(column, ())
        if " ".join(_spelling_words(value)) != needle
    ]
    # An empty `held` means this column lists no value this group could ever answer -- a column the
    # type does not fill (`Attribute_Lamp Type` for a TV) or a column holding only the tested word.
    # `all([])` is True, so without this line such a column looked OWNED by every group, and a value
    # that appears in no vocabulary at all (`LED`) was refused a seat it contradicted nothing about.
    return bool(held) and all(key in table for key in held)


#: Per product type, the group tables once the platform's own closed list has filled them out.
_WIDENED: dict[str, tuple[dict[str, tuple[str, ...]], ...]] = {}

#: Per product type, the `Attribute_... Type` column each group asks, when exactly one group does.
_GROUP_COLUMNS: dict[str, dict[int, str]] = {}


def _column_keys() -> dict[str, set[str]]:
    """Every platform Type column, as the spelling keys of the values it enumerates."""
    return {
        column: {" ".join(_spelling_words(value)) for value in values}
        for column, values in attributes.ALLOWED.items()
        if column.endswith(" Type")
    }


def _group_keys(group: dict[str, tuple[str, ...]]) -> set[str]:
    keys = {" ".join(_spelling_words(label)) for label in group}
    keys.update(" ".join(_spelling_words(alias)) for aliases in group.values() for alias in aliases)
    return keys


def _group_column_map(product_type: str) -> dict[int, str]:
    """Which group asks which platform column -- only where ONE group's labels fit one list.

    A column the platform's list answers with values from two different groups (`Attribute_Washing
    Machine Type` knows both `Twin Tub` and `Top Load`, and the shop stacks them) belongs to neither,
    so it widens nothing: the builder must not move a word across the line its own table draws.
    """
    cached = _GROUP_COLUMNS.get(product_type)
    if cached is not None:
        return cached
    columns = _column_keys()
    owners: dict[str, list[int]] = {}
    for position, group in enumerate(SUBTYPES.get(product_type, ())):
        for column, values in columns.items():
            if _group_keys(group) <= values:
                owners.setdefault(column, []).append(position)
    resolved = {
        position: column
        for column, positions in owners.items()
        if len(positions) == 1
        for position in positions
    }
    _GROUP_COLUMNS[product_type] = resolved
    return resolved


def subtype_groups(product_type: str) -> tuple[dict[str, tuple[str, ...]], ...]:
    """The sub-type groups this type is read from, widened by the platform's own list.

    A group whose every label is a value of ONE `Attribute_... Type` column asks that column's
    question, so the column's remaining values join the group as labels of their own.  DigiMall
    enumerates `Cassette` in `Attribute_Air Conditioner Type` and the shop's Titles write it, and
    while the group did not know the word it had no seat: the reader answered the mounting question
    from the vendor's boilerplate, `Cassette` fell out of the Title, and a value the row earned was
    never shipped.

    Nothing is invented -- the vocabulary is `attributes.ALLOWED`, the platform's closed list, read
    instead of copied.  A group the lists place nowhere (`Heat & Cool`) keeps exactly the labels the
    table authored, and a column split across two groups widens neither.
    """
    cached = _WIDENED.get(product_type)
    if cached is not None:
        return cached
    owners = _group_column_map(product_type)
    widened: list[dict[str, tuple[str, ...]]] = []
    for position, group in enumerate(SUBTYPES.get(product_type, ())):
        column = owners.get(position, "")
        if not column:
            widened.append(dict(group))
            continue
        table = dict(group)
        known = _group_keys(group)
        for value in attributes.ALLOWED.get(column, ()):
            if " ".join(_spelling_words(value)) not in known:
                # The platform's own spelling is the label, and its words are the alias: the reader
                # that matches a row's clause re-spaces the alias itself.
                table[value] = (" ".join(_spelling_words(value)),)
        widened.append(table)
    result = tuple(widened)
    _WIDENED[product_type] = result
    return result


def _answer_for_group(group: dict[str, tuple[str, ...]], phrase: str) -> str:
    """What this group's OWN alias reader would answer from this phrase, alone.

    The line contradicts a group's answer when the group would name a different label from the
    line's words than from the row's -- the same question, two machines.  Asked of the group's own
    reader, the closed platform lists join the test for free: a value no group knows (`Cassette`)
    is answered by :func:`_owns_column` instead, and a value some other group knows (`Top Load`)
    takes that group's seat rather than contradicting this one.
    """
    if not phrase:
        return ""
    return _group_label(group, _clauses(phrase))


def merge_subtype_type(
    label: str, answers: tuple[str, ...], product_type: str
) -> tuple[str, bool]:
    """Place the owner's `SubType:` line against the type list's per-group answers.

    The line REPLACES a group's answer only where the two answer the same question differently --
    the group's own alias reader would name one label from the row and a different one from the
    line, or the platform's column that enumerates both knows them as its two values (`Split` vs
    `Cassette`) -- and then it prints IN that group's seat, because the assembly prints groups in
    order, which is the shop's order (`Front Load Twin Tub` never ships).  Everything else MERGES:
    a line that answers a second question (`Heat & Cool` beside a standing `Split`) joins the slot
    without wiping it, and a line that speaks a word another fact already carries is not printed
    twice.  A line the table asks no question about (`Spinner`) travels at the end.
    """
    if not label:
        return " ".join(answer for answer in answers if answer), False
    groups = subtype_groups(product_type)
    label_key = " ".join(_spelling_words(label))
    label_tokens = _spelling_words(label)
    line_answer = [_answer_for_group(group, label) for group in groups]
    anchor = next((p for p, read in enumerate(line_answer) if read), None)
    column_owner = next(
        (p for p, group in enumerate(groups) if _owns_column(_type_column(label), group, label)),
        None,
    )
    seats: list[tuple[int, str]] = []
    replaced = False
    seated = False
    for position, group in enumerate(groups):
        answer = answers[position] if position < len(answers) else ""
        if anchor == position or (anchor is None and column_owner == position):
            # The line's OWN question: it takes this seat, and a different value the group had
            # answered from the row is the answer the line corrects.
            if not seated:
                seats.append((position, label))
                seated = True
            replaced = replaced or (bool(answer) and line_answer[position] != answer)
            continue
        if not answer:
            continue
        answer_tokens = _spelling_words(answer)
        contained = len(answer_tokens) <= len(label_tokens) and any(
            label_tokens[start : start + len(answer_tokens)] == answer_tokens
            for start in range(len(label_tokens) - len(answer_tokens) + 1)
        )
        contradicts = line_answer[position] not in ("", answer) or (
            _type_column(answer) != ""
            and _type_column(answer) == _type_column(label)
            and _owns_column(_type_column(answer), group, answer)
        )
        if contradicts or contained or label_key == " ".join(answer_tokens):
            if not seated:
                seats.append((position, label))
                seated = True
            replaced = replaced or contradicts
            continue
        seats.append((position, answer))
    if not seated:
        seats.append((len(groups), label))
    return " ".join(text for _, text in seats), replaced


def undecided_attribute_columns(
    answers: tuple[str, ...], conflicts: tuple[tuple[str, str], ...]
) -> tuple[str, ...]:
    """The platform columns this row left unanswered, and must not be filled from its prose.

    A `[Subtype]` word withheld because the row's two columns disagreed is only half the ruling:
    DigiMall's matcher reads this Title first and the raw Description next, and the Description is
    where the vendor sentence sits -- so leaving the slot empty without withholding the cell lets the
    same wrong value walk back in through the back door (`Kenwood ... - KCT-2402H` shipping
    `Attribute_Air Conditioner Type: Split` under a Title that refuses to call the machine a Split).
    A column another group of the same row did answer -- `Top Load` beside an unsettled
    `Semi Automatic` question -- stays open: the row answered that question, and an empty cell would
    then be the builder's loss rather than the sheet's.
    """
    settled = {_type_column(answer) for answer in answers if answer}
    undecided: list[str] = []
    for pair in conflicts:
        for value in pair:
            column = _type_column(value)
            if column and column not in settled and column not in undecided:
                undecided.append(column)
    return tuple(undecided)


def stated_class_phrase(
    product_type: str, source_title: str, said_already: str, refuse: tuple[str, ...] = ()
) -> str:
    """The type phrase this row writes that its own `[Subtype]` list has no group for.

    `Haier Digital Inverter Freezer-On-Top Refrigerator 12 CFT` states a TYPE the platform
    enumerates for a refrigerator, and neither the sub-type table nor a `SubType:` line names it.
    The Series seat may not hold it either -- R1 and R4 put a class word outside the name slot -- so
    a rebuild that prints neither drops the word from the Title, and DigiMall's
    `Attribute_Refrigerator Type` cell is matched out of that Title: the row loses a platform value
    it earned.  Reading the platform's own list for THIS type is how the phrase is found without a
    second vocabulary living here, and the row's own letters are what gets printed.

    Only clauses the row did not negate: `Not side by side, double door` denies one type and states
    another, and a denied phrase cannot be the value this row earned.  The RAW clauses are searched,
    not `_clauses()` -- that view is squashed to letters, and a value the row hyphenated into
    `Freezer-on-top` has to be found behind its own punctuation before the platform's spelling of it
    is printed.

    The one-word values the same columns enumerate (`Cassette`, `Spinner`, `QLED`) join the search,
    but under a stricter placement test: a word may take the slot only when its OWN platform column
    has not already been answered by the row -- and only when that column is even a single question
    to begin with (see :func:`_owns_column`), because `Attribute_Washing Machine Type` knows both
    `Twin Tub` and `Top Load` and the shop stacks them daily.
    """
    stated = " ".join(
        clause for clause in _CLAUSE_RE.findall(source_title) if not _NEGATION_RE.search(clause)
    )

    def stacks_on_answered_column(word: str) -> bool:
        """Whether this one-word type contradicts a value the Title already prints.

        `Split` and `Cassette` are two values of the platform's ONE AC Type column and every other
        value of that column stands in one shape group -- so a row that already prints `Split` may
        not gain `Cassette` here, and one Title would answer the mounting question twice.  A column
        the builder's own table splits across two questions asks both, and `Spinner` beside
        `Semi Automatic` contradicts nothing: it travels free.
        """
        column = _type_column(word)
        if column == "":
            return False
        groups = subtype_groups(product_type)
        if not any(_owns_column(column, group, word) for group in groups):
            return False
        mine = " ".join(_spelling_words(word))
        for value in attributes.ALLOWED.get(column, ()):
            other = " ".join(_spelling_words(value))
            if other == mine:
                continue
            if all(word_printed(part, said_already) for part in other.split()):
                return True
        return False

    best: tuple[int, int, str] | None = None
    candidates = [(phrase, False) for phrase in series_corpus.class_phrases(product_type)]
    candidates += [(word, True) for word in series_corpus.class_words(product_type)]
    for phrase, one_word in candidates:
        if " ".join(_spelling_words(phrase)) in {" ".join(_spelling_words(word)) for word in refuse}:
            continue  # the row stated this type and its two columns disagreed -- the owner decides
        pattern = r"\b" + r"[\s\-]+".join(re.escape(word) for word in phrase.split()) + r"\b"
        match = re.search(pattern, stated, re.IGNORECASE)
        if not match:
            continue
        written = match.group(0)
        # A phrase sharing even ONE word with what the Title already prints is that same fact spelled
        # twice: `TCL 65 Inch Mini LED TV` printed as `Mini LED LED TV` reads as a broken row, and
        # `Top-Load Automatic` beside `Top Load` says nothing new.  The words are cut on punctuation
        # too, because the row spells `Top-Load` where its own sub-type list spaced it to `Top Load`,
        # and a hyphen is not a second type.
        if any(word_printed(word, said_already) for word in _spaced_words(written).split()):
            continue
        if one_word and stacks_on_answered_column(written):
            continue
        # The row's own order wins over the table's: `Kenwood Multi Door Side-by-Side` states its
        # first type first, and a longest-first pick would delete the word it wrote first.
        candidate = (match.start(), -len(written), written)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return ""
    # The platform's own letters, when it has any for what the row wrote: 32 rows spelled
    # `Freezer-on-top` while 135 spelled `Freezer-On-Top`, and one fact does not get two spellings on
    # one shelf.  An unknown phrase keeps the row's letters, because inventing a spelling is worse
    # than keeping one (owner ruling, 2026-10-23).
    return canonical_type_value(best[2], product_type)


#: A sub-type names what the machine is; a sentence after `SubType:` is a vendor answering a
#: different question.  Four words is the longest real one on these sheets (`Split DC Inverter AC`).
SUBTYPE_MAX_WORDS = 4


def _phrase_neighbours(text: str, phrase: str) -> set[str]:
    """The words written immediately around a phrase, in lower case.

    `Turbo Cool Split Air Conditioner` is one statement about the machine.  When `[Subtype]` takes
    `Split`, the word left beside it is not a second fact -- it is the other half of the same
    phrase, and shipping it alone behind the model code sold `Cool` as a Haier line name.
    """
    hay = _spaced_words(text)
    needle = _spaced_words(phrase).strip()
    if not needle:
        return set()
    neighbours: set[str] = set()
    start = hay.find(f" {needle} ")
    while start >= 0:
        before = hay[:start].split()
        after = hay[start + len(needle) + 2 :].split()
        if before:
            neighbours.add(before[-1])
        if after:
            neighbours.add(after[0])
        start = hay.find(f" {needle} ", start + 1)
    return neighbours


def subtype_line_words(
    value: str, said_already: str, product_type: str = ""
) -> tuple[list[str], str]:
    """The words of a `SubType:` line that the row has not already printed, and why if none.

    The line is re-spelled through the shop's own vocabulary first (:func:`canonical_type_value`):
    `heat & cool` becomes `Heat & Cool` because that is the platform's value, and a vendor's commas
    inside the value -- `Split, Heat & Cool.` -- are handwriting, not content, so every word loses
    its edge punctuation before it is kept.  A sign BETWEEN two words stays, because `Heat & Cool`
    is how he wrote it and how the shelf must read it.  A value that repeats the model code, the
    warranty or the category is refused word by word, because a Title that says the SKU twice is a
    row shadowing itself.
    """
    if not value:
        return [], ""
    if product_type:
        value = canonical_type_value(value, product_type)
    line_words = [word.strip(" .,:;-–—") for word in value.split()]
    line_words = [word for word in line_words if word]
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
        spelling = word.capitalize() if word.islower() else word
        if word_printed(spelling, said_already) or word_printed(spelling, " ".join(kept)):
            continue
        kept.append(spelling)
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
    absorbed: frozenset[str] = frozenset(),
    warranty: str = "",
) -> str:
    """Extract series and prominent feature keywords dynamically from text.

    `series` is the name the corpus proved for this row's brand; when the caller has one, it IS
    the series half of the slot and `extract_series` is not asked -- the curated path stays as the
    fallback for a corpus that proved nothing, so wiring the vote in can never shorten a Title.

    `absorbed` are the words the row spent on saying what the machine is, and the word its Title
    left beside them.  A candidate built from any of them is dropped whole: a candidate cut down to
    its leftovers is the stranding this rule exists to remove -- `... - HSU-12CF Cool`, one half of
    the phrase the shop wrote, printed where a line name belongs.  `warranty` is the row's own
    guarantee statement, whose words are spent the same way.
    """
    full_text = f"{source_title}\n{description}" if (source_title or description) else text
    if not source_title and text:
        source_title = text.splitlines()[0]

    # A word this row spent on its paint can never be its line name: `Pearl Copper`, `Cloud White`
    # and `Green Texture` are colours, and a Series seat reading `Pearl`, `Cloud` or `Texture` out of
    # one is the defect R1 removes -- absolutely, so the ban is in place BEFORE the row's own clause
    # is read.  A sheet that writes `9173WB Pearl` behind a `Pearl Copper` row states its paint
    # twice, and an empty seat is the honest answer.
    spent = (
        frozenset(word.lower() for word in color.split())
        | colourway_words(source_title, color)
        | frozenset(warranty_words(warranty))
        | absorbed
    )

    candidates: list[str] = []
    # The row's own clause outranks the run's vote, because position is the row's own evidence:
    # `KRF-23357 VCM INV Invertech VCM Inverter` names the machine `Invertech` inside the clause it
    # wrote its code into, while the corpus, reading residue words left to right, believed
    # `Texture` out of the colourway at char 25.
    #
    # And it REPLACES the vote rather than standing beside it: one seat, one name.  A second word
    # from the run's vote printed `Invertech Texture` and `Room Lifetime` -- the name followed by
    # the material or warranty word the very same row wrote somewhere else, which is the defect this
    # task was opened for.  So the vote speaks only where the row's own clause stayed silent.
    slot_name, _slot_clause = beside_model_code(source_title, model, spent)
    if slot_name:
        candidates.append(slot_name)
    else:
        chosen = series if series is not None else extract_series(
            full_text, model=model, banned=spent, product_type=product_type
        )
        # A name with no position behind it still has to pass the type test: the vote proved
        # `Inverter` for one Haier brand and the residue read `Multi` out of `Multi Door`, and neither
        # is a line -- they are the machine's shape, which `[Subtype]` already carries.
        if chosen and _says_what_it_is(chosen, full_text, product_type):
            chosen = ""
        if chosen:
            candidates.append(chosen)

    # Air Fryer special check
    if re.search(r"\bair\s*fryer\b", full_text, re.IGNORECASE) and "Air Fryer" not in candidates:
        candidates.append("Air Fryer")

    # Extra prominent features (Google, Android, QLED, OLED, Grill, Baking, Convection, Solo).  A word
    # the platform lists as THIS category's own type value is not a feature to sell behind the model
    # code -- it says what the machine IS, and `[Subtype]` is the seat for that -- so this hand-written
    # list is filtered by the platform's columns instead of growing a second exception table by hand.
    for feat in ("Google", "Android", "QLED", "OLED", "Grill", "Baking", "Convection", "Solo"):
        if product_type and feat.lower() in series_corpus.class_words(product_type):
            continue
        if re.search(rf"\b{re.escape(feat)}\b", full_text, re.IGNORECASE) and not any(
            feat.lower() in c.lower() for c in candidates
        ):
            candidates.append(feat)
            break

    kept = [c for c in candidates if not set(c.lower().split()) & (absorbed | spent)]
    return " ".join(kept[:2])


PARAMETER_QUESTION_STEMS: frozenset[str] = frozenset(
    {
        "size", "dimension", "dimensions", "width", "height", "depth", "weight",
        "voltage", "frequency", "power", "current", "capacity", "refrigerant", "volume",
        "rate", "ratio", "temperature", "type", "color", "colour", "model",
        "brand", "warranty", "price", "resolution", "port", "ports", "shelf", "pocket",
        "input", "output", "inlet", "outlet", "system", "installation", "class",
        "btu", "hertz", "amps", "watts", "seer", "eer", "operating",
        "hdmi", "usb", "tank", "faucet", "taps", "speed", "rpm", "gross", "net",
        "load", "loading", "stand", "cabinet", "material", "lid", "body", "door", "doors",
        "mode", "modes", "format", "speaker", "speakers",
        "accessory", "accessories", "package", "packaging", "packing",
        "series", "inverter", "grade", "motor", "compressor",
    }
)

USP_DISCARD_WORDS: frozenset[str] = frozenset(
    {
        "details", "specification", "specifications", "specs", "features", "feature",
        "overview", "description", "note", "notes", "general", "basic", "item", "items",
        "manual", "standard", "conventional", "top", "front", "single", "double",
        "yes", "no", "true", "false", "na", "n/a", "none", "nil", "other", "others",
        "direct cool", "direct cooling",
    }
)

EXACT_PARAMETER_QUESTIONS: frozenset[str] = frozenset(
    {
        "screen size", "cooling capacity", "heating capacity", "rating power",
        "control system", "body type", "net dimension", "packaging dimension",
        "refresh rate", "contrast ratio", "audio output", "set weight",
        "cold water tank", "hot water tank", "display type", "screen type",
        "product color", "door type", "climate class", "energy class",
        "voltage", "frequency", "dimensions", "weight", "resolution", "hdmi", "usb",
    }
)

QUESTION_SUFFIXES: frozenset[str] = frozenset(
    {
        "type", "size", "capacity", "system", "weight", "rate", "ratio",
        "dimension", "dimensions", "class", "voltage", "frequency", "input", "output",
        "specifications", "specification", "specs", "details",
    }
)

KNOWN_ACRONYMS: frozenset[str] = frozenset(
    {
        "hdr", "hdr10", "hdr10+", "dts", "vrr", "allm", "memc", "qled", "oled",
        "uhd", "fhd", "hd", "4k", "8k", "led", "ipx4", "bldc",
    }
)

USP_WARRANTY_WORDS: frozenset[str] = frozenset(
    {
        "warranty", "guarantee", "official", "year", "years", "yr", "yrs",
    }
)

SPEC_MEASUREMENT_STEMS: frozenset[str] = frozenset(
    {
        "size", "dimension", "dimensions", "width", "height", "depth", "weight",
        "voltage", "frequency", "power", "current", "capacity", "refrigerant", "volume",
        "temperature", "color", "colour", "model", "brand", "warranty", "price",
        "port", "ports", "shelf", "pocket", "input", "output", "inlet", "outlet",
        "taps", "tank", "faucet", "speed", "rpm", "gross", "net", "material", "body", "lid",
        "system", "motor", "compressor",
    }
)

FEATURE_HEADER_STEMS: frozenset[str] = frozenset(
    {
        "feature", "features", "technology", "technologies", "function", "functions",
        "coating", "coatings", "audio", "sound", "display", "connectivity",
    }
)


def _is_spec_measurement(text: str) -> bool:
    """Whether text names a physical dimension, electrical spec, or table measurement question."""
    words = re.findall(r"[a-z]+", text.lower())
    return any(w in SPEC_MEASUREMENT_STEMS for w in words)


_USP_NEGATIVE_VALS: frozenset[str] = frozenset(
    {"no", "0", "false", "n/a", "none", "na", "nil", ""}
)

_USP_POSITIVE_VALS: frozenset[str] = frozenset(
    {"yes", "1", "true"}
)

_USP_MEASUREMENT_RE: re.Pattern[str] = re.compile(
    r"(?:"
    r"^\d+(?:\.\d+)?\s*(?:[x*×]\s*\d+(?:\.\d+)?)+\s*(?:mm|cm|m|inch|\")?$"
    r"|^\d+(?:\.\d+)?\s*(?:v|volt|volts|hz|hertz|w|watt|watts|kw|a|amp|amps|kg|kgs|g|gm|liter|liters|litre|litres|ltr|ltrs|l|ml|cm|mm|m|inch|inches|\"|\'|btu|btu/h|c|°c|ton|tons|seer|eer|l/hour)\b"
    r"|^\d+$"
    r"|^\d+\s*[-~]\s*\d+\s*(?:mm|cm|m|kg|g|v|w|hz|c|°c|l|ltr|inch)?$"
    r"|^[-~]\d+\s*(?:°?c|f)?$"
    r")",
    re.IGNORECASE,
)


def _is_parameter_question(text: str) -> bool:
    """Whether candidate text is an exact parameter question or 1-2 word question label."""
    low = text.lower().strip()
    if low in EXACT_PARAMETER_QUESTIONS or low in PARAMETER_QUESTION_STEMS:
        return True
    words = re.findall(r"[a-z]+", low)
    if not words:
        return False
    return len(words) <= 2 and words[-1] in QUESTION_SUFFIXES


def _is_feature_header(text: str) -> bool:
    """Whether label is a generic feature category header (e.g. Special Feature, Smart Features)."""
    words = re.findall(r"[a-z]+", text.lower())
    return any(w in FEATURE_HEADER_STEMS for w in words)


def _usp_text(cand: str) -> str:
    """The candidate exactly as a Title would print it: markup gone, no dangling sentence mark."""
    cleaned = clean_inline(cand).strip(" :-•·*–—\t\"'“”‘’✔✓★▶►")
    cleaned = re.sub(r"[\uFFFD\u200B\uFEFF\u00A0]", " ", cleaned).strip()
    cleaned = re.sub(r"[®™©]", "", cleaned).strip()
    return cleaned.rstrip(".!?…").strip()


def _is_valid_usp(cand: str) -> bool:
    """Check if candidate string is a real, non-measurement feature phrase fit to seat in a Title.

    Brevity is not judged here: the Title's own 255-character budget in `build_title` decides how
    many features fit.  A fixed 35-character / 4-word ceiling rejected 120 of the 142 Key Features
    bullets the owner writes, because a real feature is a phrase (`High-Efficiency Copper Winding
    Motor`), and every slot it left empty was filled by a table label instead.
    """
    cleaned = _usp_text(cand)
    if len(cleaned) < 2:
        return False
    # A feature is a phrase, not a paragraph.  Two sentences in one cell is the shop writing terms
    # beside its specs (`... a 50% advance payment is required. Our team will contact you ...`), and
    # it measured 141 characters into one Title once the brevity ceiling went.
    if re.search(r"[.!?…]\s", cleaned):
        return False
    low = cleaned.lower()
    if low in USP_DISCARD_WORDS or low in EXACT_PARAMETER_QUESTIONS:
        return False
    words = re.findall(r"[a-zA-Z0-9+]+", cleaned)
    if not words:
        return False
    # Check if has Latin vowel OR matches known industry tech acronyms
    has_vowel = any(re.search(r"[aeiouy]", w, re.IGNORECASE) for w in words)
    is_acronym = any(w.lower() in KNOWN_ACRONYMS for w in words) or low in KNOWN_ACRONYMS
    if not (has_vowel or is_acronym):
        return False
    # Reject model codes: requires digits AND letters separated by slash/hyphen (e.g. GS-24PITH15W-T3)
    if re.search(r"\b(?=[A-Z0-9]*\d)[A-Z0-9]+[/-][A-Z0-9]+\b", cleaned):
        return False
    if _USP_MEASUREMENT_RE.search(cleaned):
        return False
    return not any(w.lower() in USP_WARRANTY_WORDS for w in words)


def _value_parts(label: str, val: str) -> list[str]:
    """The facts a `Label: Value` cell states -- its written answer, split only when it is a LIST.

    One rule for both places a sheet can write it: a Key Specifications row and a Key Features
    bullet are the same shape.  A written value IS the fact the row sells; the label is only the
    question the table asks, so `SubType: Semi Automatic Twin Tub` contributes its answer and never
    the word `SubType`, and `3 Settings: Turbo, Silent Mode` never the word `3 Settings`.  A
    grouping header (`Special Feature: Dolby Audio, Multi Air Flow`) states a LIST, so each part
    counts; every other cell states one fact, and splitting its sentence on commas printed `Gentle`
    and `and Heavy Wash Modes` as two separate features.
    """
    parts = re.split(r"[,;]+", val) if _is_feature_header(label) else [val]
    return [_usp_text(p) for p in parts]


def extract_usps(
    source_title: str,
    source_description: str,
    product_type: str,
    said_already: str,
    max_usps: int = 3,
) -> tuple[str, ...]:
    """Extract up to ``max_usps`` high-converting, non-redundant USP phrases purely dynamically.

    Universal Semantic Feature Discovery (USFD):
    Zero hardcoding & Zero invention: reads exclusively from ``description_builder.parse_description``:
      1. Genuine marketing bullet highlights from ``parsed.key_features``.
         - Drops negative claims ("3D: No", "8K: No", "N/A").
         - Promotes positive booleans ("Google Assistant: Yes" -> "Google Assistant").
         - Discards spec parameter questions ("Screen Size: 32"").
      2. Non-parameter marketing feature rows from ``parsed.labelled``.
         - Never extracts technical table question labels as USPs.
         - Promotes non-boolean feature values ("Cooling Technology: No Frost" -> "No Frost").
         - Splits multi-value feature cells on commas and semicolons.

    Args:
        source_title: Raw product title from the input sheet.
        source_description: Raw product description from the input sheet.
        product_type: Resolved canonical product type (e.g. "Air Conditioner").
        said_already: Text of tokens already printed in Segment 1 / Model for deduplication.
        max_usps: Maximum number of USP phrases to return (default 3).

    Returns:
        A tuple of up to ``max_usps`` clean USP strings. Empty tuple if no valid USPs survive.
    """
    if not source_description:
        return ()

    clean_desc = description_builder.strip_markup_keep_lines(source_description)
    parsed = description_builder.parse_description(clean_desc)
    candidates: list[str] = []

    # 1. Key features (bullets/em-dashes)
    for feat in parsed.key_features:
        cleaned = _usp_text(feat)
        if not cleaned:
            continue
        if ":" in cleaned:
            k, _, v = cleaned.partition(":")
            k_clean = k.strip()
            v_clean = v.strip().lower()
            if v_clean in _USP_NEGATIVE_VALS:
                continue
            if v_clean in _USP_POSITIVE_VALS:
                if not _is_spec_measurement(k_clean) and _is_valid_usp(k_clean):
                    candidates.append(k_clean)
                continue
            if _is_spec_measurement(k_clean):
                continue
            # A value is the fact the bullet sells; the key is only the question it answers.
            for sub in _value_parts(k_clean, v):
                if _is_valid_usp(sub):
                    candidates.append(sub)
        elif _is_valid_usp(cleaned):
            candidates.append(cleaned)

    # 2. Spec rows from parsed.labelled
    for label, val in parsed.labelled:
        lbl_clean = clean_inline(label).strip(" :-\t")
        v_clean = clean_inline(val).strip(" :-\t").lower()
        if v_clean in _USP_NEGATIVE_VALS:
            continue

        # If val is boolean positive ("yes", "1", "true"), the feature is in the label!
        if v_clean in _USP_POSITIVE_VALS:
            if not _is_spec_measurement(lbl_clean) and _is_valid_usp(lbl_clean):
                candidates.append(lbl_clean)
            continue

        # Technical measurement rows (Dimensions, Body Type, Weight, Voltage, Color, etc.) -> SKIP completely!
        if _is_spec_measurement(lbl_clean):
            continue

        for sub in _value_parts(lbl_clean, val):
            if _is_valid_usp(sub):
                candidates.append(sub)
        continue

    if not candidates:
        return ()

    category_words = {w.lower() for w in re.findall(r"[A-Za-z0-9+]+", product_type)}
    category_words.update(CATEGORY_WORDS)
    stopwords = {"and", "with", "for", "the", "of", "to", "in", "by", "on", "at"}

    said_words: set[str] = {
        w.lower()
        for w in re.findall(r"[A-Za-z0-9+]+", said_already)
        if len(w) >= 2 and not w.isdigit() and w.lower() not in category_words and w.lower() not in stopwords
    }
    said_words.update(USP_WARRANTY_WORDS)

    selected: list[str] = []
    seen_phrases: set[str] = set()

    for cand in candidates:
        cand_clean = _usp_text(cand)
        if not _is_valid_usp(cand_clean):
            continue
        phrase_key = cand_clean.lower()
        if phrase_key in seen_phrases:
            continue

        cand_words = [
            w.lower()
            for w in re.findall(r"[A-Za-z0-9+]+", cand_clean)
            if len(w) >= 2 and not w.isdigit() and w.lower() not in stopwords
        ]
        if not cand_words:
            continue

        if any(w in said_words for w in cand_words):
            continue

        selected.append(cand_clean)
        seen_phrases.add(phrase_key)
        said_words.update(cand_words)

        if len(selected) >= max_usps:
            break

    return tuple(selected)


TitleFormulaFn = Callable[[dict[str, str]], str]


def _apply_formula(
    slots: dict[str, str],
    formula: str | TitleFormulaFn,
) -> str:
    """Apply a vendor-specific formula to the extracted, deduplicated title slots."""
    if callable(formula):
        return formula(slots)
    if formula == "vip_pipe":
        color_paren = f"({slots['color']})" if slots.get("color") else ""
        seg1 = " ".join(
            t
            for t in (
                slots["brand"],
                slots["capacity"],
                slots.get("front_identity", ""),
                slots["inverter"],
                slots["subtype"],
                slots["product_type"],
                color_paren,
            )
            if t
        ).strip()
        usp_list = [u.strip() for u in slots.get("usps", "").split("|") if u.strip()]
        pipe_parts = [
            seg1,
            slots.get("back_model", "").strip(),
            *usp_list,
            slots["warranty"].strip(),
        ]
        return " | ".join(p for p in pipe_parts if p)
    if formula == "standard":
        segments = [s for s in (slots["part1"], slots["part2"], slots["part3"]) if s]
        return " - ".join(segments)
    if formula in ("brand_first_extended", "ajmer_variant"):
        if slots["model"]:
            model_tok = slots["model"]
            brand_tok = slots["brand"]
            if brand_tok:
                prefix_re = re.compile(
                    rf"^{re.escape(brand_tok)}(?:\s+|\s*-\s*)", re.IGNORECASE
                )
                stripped = prefix_re.sub("", model_tok).strip()
                if stripped:
                    model_tok = stripped
            head = " ".join(t for t in (brand_tok, model_tok) if t).strip()
            body = " ".join(
                t
                for t in (
                    slots["capacity"],
                    slots["color"],
                    slots["inverter"],
                    slots["subtype"],
                    slots["product_type"],
                    slots["feature"],
                )
                if t
            ).strip()
        else:
            head = " ".join(
                t
                for t in (
                    slots["brand"],
                    slots["product_type"],
                    slots["subtype"],
                    slots["capacity"],
                    slots["color"],
                    slots["inverter"],
                )
                if t
            ).strip()
            body = slots["feature"].strip()
        tail = slots["warranty"].strip()
        return " - ".join(s for s in (head, body, tail) if s)
    raise ValueError(
        f"Unknown title_formula {formula!r}. Add it to title_builder._apply_formula."
    )


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
    capacity: str | None = None,
    identity: str | None = None,
    title_formula: str | TitleFormulaFn = "standard",
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

    `capacity` and `identity` are what the row stated -- the pipeline resolves them once, in
    `main`, and hands them here so a Title and the SKU under it can never disagree.
    """
    if strict_rebuild is None:
        strict_rebuild = STRICT_TITLE_REBUILD

    text = f"{source_title}\n{source_description}"
    if warranty is None:
        warranty = resolve_main_warranty(text, brand, product_type) or ""

    taps = extract_taps(text)
    if capacity is None:
        # The run resolves each row's size once (`main.py`), because the Title, the SKU and the
        # attribute cells must all answer to the same number.  Resolving here would read the brand
        # as the sheet spelled it instead of as the brand registry resolved it.
        capacity = resolve_capacity(text, product_type, brand, extraction)
    # Two facts, two tokens: how many taps the dispenser has, and how big its tank is.  The tap
    # count still takes the printed [Capacity] slot today, but the litres are carried beside it
    # instead of being overwritten -- the formula rewrite prints both.
    volume_capacity = capacity
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
            # Read with THIS row's code and its own colour words: called bare, any digit in the row
            # would anchor the slot scan and its answer would be the code itself, or the paint standing
            # beside it -- neither is a line name.
            curated = extract_series(
                text,
                model=extraction.code,
                banned=frozenset(word.lower() for word in f"{color} {warranty}".split())
                | colourway_words(source_title, color),
                product_type=product_type,
            )
            if curated and curated != corpus_series and series_corpus.names_a_class(curated):
                # The old series guesser sold this row's TYPE as its series name.  The corpus
                # replaced it with the real name, but the word still says what the machine is --
                # and DigiMall's `Attribute_... Type` cell is matched out of this Title, so
                # dropping it would empty a platform column.  It belongs in the [Subtype] slot.
                carried_subtype = curated

    should_rebuild = bool(
        strict_rebuild or (extraction.confidence in ("high", "medium"))
    )
    slot_printed = False
    identity_printed = ""
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
    kept_words, label_note = subtype_line_words(label_value, said_already, product_type)
    answers, list_overruled, list_conflicts = extract_subtype_groups(
        product_type, source_title, source_description
    )
    # A written `SubType:` line settles the questions its own words answer, so a group the two
    # columns disagreed about is AGREED the moment he speaks: the label's value becomes that group's
    # answer and nothing is flagged for it.  A question the line does not address stays open.
    label_answers = list(answers)
    settled_groups: set[int] = set()
    conflicts: list[tuple[str, str]] = []
    overruled = list(list_overruled)
    if kept_words:
        label_phrase = " ".join(kept_words)
        for index, group in enumerate(subtype_groups(product_type)):
            from_label = _group_label(group, _clauses(label_phrase))
            if not from_label:
                continue
            settled_groups.add(index)
            if answers[index] != from_label:
                if answers[index]:
                    overruled.append(answers[index])
                label_answers[index] = from_label
    for position, title_value, description_value in list_conflicts:
        if position in settled_groups:
            # His own line answered THIS question -- whichever word he chose, even a third one the
            # two columns never fought over.  The group carries his word now, so the row is no
            # longer a decision owed; and both disputed words are already spent, because the reading
            # that recorded the disagreement spent them.  Keying this on the WORD instead would keep
            # flagging a row whose Title ships exactly what he wrote: the flag tells him the slot and
            # its Attribute_* cell are empty, which on these rows is a lie.
            continue
        conflicts.append((title_value, description_value))
    answers = tuple(label_answers)
    listed_subtype = " ".join(answer for answer in answers if answer)
    # The line and the list are placed TOGETHER (merge_subtype_type): the line answers the question
    # it answers and leaves the other groups' answers standing, unless the two contradict.
    merged_subtype, _ = merge_subtype_type(" ".join(kept_words), answers, product_type)
    if kept_words and " ".join(kept_words).lower() == listed_subtype.lower():
        label_note = "restates the word this row's own type already gives"
    # Neither value of an unsettled disagreement reaches the Title: the words of a question the
    # builder may not answer are spent, so they cannot reappear behind the model code either, and the
    # class rung below is refused them -- the owner settles it, not a reader guessing between columns.
    for title_value, description_value in conflicts:
        overruled.extend((title_value, description_value))
    refuse = tuple(word for pair in conflicts for word in pair)

    # The words the row spent saying what the machine is -- the answers, the type word a column
    # overruled, and the word the series reader carried -- plus the word the TITLE left standing
    # immediately beside them: none may be resold behind the model code, where a line name belongs.
    # `... - HSU-12CF Cool` is the half of "Turbo Cool" a type word strands, and a fragment reads as
    # a name the shop never sold.  The one thing that saves such a word is the run's vote -- a name
    # proved for this brand is what the corpus was built to find.  Prose is not scanned for
    # neighbours: a Description bullet's neighbour is grammar (`with`, `Yes`), and absorbing it
    # deleted the `Air` of `Air Fryer` from two Haier rows while leaving `Fryer` behind.
    own_words = {
        word.lower()
        for phrase in (listed_subtype, carried_subtype, *overruled)
        for word in phrase.split()
    }
    beside = (
        {
            word
            for phrase in (listed_subtype, carried_subtype)
            for word in _phrase_neighbours(source_title, phrase)
        }
        - set(_spaced_words(said_already).split())
    )
    protected = {w.lower() for w in clean_inline(corpus_series or "").split()}
    absorbed = frozenset((own_words | beside) - protected)
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
        absorbed=absorbed,
        warranty=warranty,
    )

    # A word the old leftover-word reader sold as a series is a TYPE the platform enumerates, and it
    # has to stay in the Title or DigiMall's Type column falls to empty -- so it moves to the slot
    # built for what a machine IS.  Scoped to exactly the words that reader used to pick up, because a
    # rebuild that never touched them must not gain a new [Subtype] word either; and it is placed as
    # the WHOLE phrase, since `Side` alone is the fragment the reader stranded out of `Side By Side`.
    stranded_subtype = ""
    if not carried_subtype and not kept_words:
        # The rung that reads the platform's own list for what the machine IS is gated only on the
        # slot being unfilled -- never on whether the leftover-word reader had anything to say.
        # Row 505: a `Series:` line filled the name slot honestly, the old gate fell silent, and
        # `Side-By-Side` left the Title with DigiMall's Type cell empty.  `[Subtype]` answers for
        # itself, independent of the series reader (owner ruling).
        # `said_already` carries the row's own type words and the seat too: a phrase sharing a
        # word with what the Title already prints is that same fact spelled twice, and shipping
        # it read `Fully Automatic Top Load Top-Load Automatic` for the shop to untangle.
        phrase = stated_class_phrase(
            product_type,
            source_title,
            f"{said_already} {listed_subtype} {feature}",
            refuse,
        )
        if phrase:
            stranded_subtype = phrase

    if should_rebuild:
        if kept_words:
            subtype, subtype_from = merged_subtype, "label"
        else:
            # His line said nothing, so the row is built exactly as it was before the line existed.
            subtype = " ".join(
                filter(None, (listed_subtype or carried_subtype, stranded_subtype))
            )
            subtype_from = (
                "list"
                if listed_subtype
                else (
                    "carried"
                    if carried_subtype
                    else ("class" if stranded_subtype else "")
                )
            )
        slot_names = ("brand", "capacity", "color", "inverter", "subtype", "product_type")
        raw_slots = (brand, capacity, title_color, inverter, subtype, product_type)
        deduped_slots: dict[str, str] = dict.fromkeys(slot_names, "")
        part1_pieces: list[str] = []
        for slot_name, raw_piece in zip(slot_names, raw_slots, strict=True):
            piece = clean_inline(raw_piece)
            if not piece:
                continue
            joined = " ".join(part1_pieces)
            # Word-level, never letters: `Gas` is a type word even next to a brand called `Nasgas`,
            # and a substring test here drops the row's own sub-type on the way to the category name.
            if joined and all(word_printed(word, joined) for word in piece.split()):
                continue
            part1_pieces.append(piece)
            deduped_slots[slot_name] = piece
        part1 = " ".join(part1_pieces)

        part2_pieces: list[str] = []
        model_slot = ""
        if extraction.confidence in ("high", "medium") and extraction.code:
            model_slot = clean_inline(extraction.code)
            part2_pieces.append(model_slot)
        elif extraction.code and extraction.source != "fallback":
            clean_code = clean_inline(extraction.code)
            brand_token = re.sub(r"[^A-Za-z0-9]", "", brand).upper()
            if brand_token and clean_code.upper().startswith(f"{brand_token}-"):
                clean_code = clean_code[len(brand_token) + 1:].strip()
            if clean_code and clean_code.lower() not in part1.lower():
                model_slot = clean_code
                part2_pieces.append(clean_code)
        if extraction.confidence == "none":
            # A row with no model code is sold by the name and number IT wrote, so that pair is
            # segment 2 -- not a bare word, and not a number the pipeline invented from its size.
            if identity is None:
                identity = word_identity(source_title, brand)
            if identity:
                model_slot = clean_inline(identity)
                part2_pieces.append(model_slot)
                identity_printed = identity
        feature_slot = ""
        if feature:
            clean_feat = clean_inline(feature)
            # What the Title prints so far, GROWING as words are accepted.  It used to be a snapshot
            # taken before any of the slot's own words went in, so a name slot handed the same phrase
            # by two readers walked straight through it: `... - HMW-30AFR Air Fryer Air Fryer`.
            # A word is printed once in a Title -- the rule `subtype_line_words` already applies to
            # his own `SubType:` line, and the `part1` loop above applies to every other slot.
            printed = f"{part1} {' '.join(part2_pieces)}"
            feat_words: list[str] = []
            for word in clean_feat.split():
                if word_printed(word, printed):
                    continue
                if product_type in OMIT_TITLE_COLOR_CATEGORIES and color and word.lower() == color.lower():
                    continue
                feat_words.append(word)
                printed = f"{printed} {word}"
            if feat_words:
                feature_slot = " ".join(feat_words)
                part2_pieces.append(feature_slot)
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

        # Determine front_identity and back_model for vip_pipe
        is_popular_identity = bool(identity_printed) or (identity is not None and model_slot == clean_inline(identity))
        if is_popular_identity:
            id_tok = identity_printed or model_slot
            if feature_slot and feature_slot.lower() not in id_tok.lower():
                front_identity = f"{id_tok} {feature_slot}".strip()
            else:
                front_identity = id_tok.strip()
            back_model = ""
        else:
            front_identity = feature_slot.strip()
            back_model = model_slot.strip()

        # Color handling: LED TV category omits color from title
        color_val = deduped_slots.get("color", "")
        if product_type in OMIT_TITLE_COLOR_CATEGORIES:
            color_val = ""

        # Extract USPs with budget protection so back_model and warranty are never truncated
        color_paren = f"({color_val})" if color_val else ""
        seg1 = " ".join(
            t
            for t in (
                deduped_slots["brand"],
                deduped_slots["capacity"],
                front_identity,
                deduped_slots["inverter"],
                deduped_slots["subtype"],
                deduped_slots["product_type"],
                color_paren,
            )
            if t
        ).strip()

        if title_formula == "vip_pipe":
            raw_usps = extract_usps(
                source_title=source_title,
                source_description=source_description,
                product_type=product_type,
                said_already=f"{seg1} {front_identity} {back_model}",
                max_usps=3,
            )
        else:
            raw_usps = ()

        # The Model Code and the Warranty are the two parts the shop must get whole, wherever
        # they sit, so their space is reserved before any USP is allowed in.
        protected_parts = [p for p in (back_model, part3) if p]
        protected_len = sum(len(p) for p in protected_parts) + (3 * len(protected_parts))
        budget_left = TITLE_MAX - len(seg1) - protected_len

        valid_usps: list[str] = []
        for u in raw_usps:
            if budget_left - (len(u) + 3) >= 0:
                valid_usps.append(u)
                budget_left -= (len(u) + 3)
            else:
                break
        usp_tokens_tuple = tuple(valid_usps)

        slots = {
            **deduped_slots,
            "color": color_val,
            "model": model_slot,
            "feature": feature_slot,
            "front_identity": front_identity,
            "back_model": back_model,
            "usps": " | ".join(valid_usps),
            "warranty": part3,
            "part1": part1,
            "part2": part2,
            "part3": part3,
        }
        if title_formula == "vip_pipe" and protected_parts:
            protected_str = " | ".join(protected_parts)
            needed_space = len(protected_str) + 3
            if len(seg1) + needed_space > TITLE_MAX:
                allowed_seg1 = max(0, TITLE_MAX - needed_space)
                seg1 = _trim_to_limit(seg1, allowed_seg1)
            pipe_parts = [p for p in (seg1, back_model, *valid_usps, part3) if p]
            combined = " | ".join(pipe_parts)
        else:
            combined = _apply_formula(slots, title_formula)

        title = clean_inline(_trim_to_limit(combined, TITLE_MAX))
        strategy = "rebuilt"
        # The search title is the owner's shape, not the shop Title's wording: brand, the code (or
        # the name-and-number) the row states, the kind of machine it is, then the size it is sold by.
        # The colour, the inverter and the warranty are facts a buyer reads off the shelf, not words he
        # types into a search box, so they never enter this string -- ` Price in Pakistan` is appended
        # by `build_seo_title`, which only ever fits this base into 65-90 characters.
        seo_brand = deduped_slots["brand"]
        seo_code = model_slot
        if seo_brand and seo_code:
            # `• Model Name: TCL 24T5-VOX-13` puts the brand INSIDE the code, and the brand already
            # leads this string -- 3 rows shipped `TCL TCL 24T5-VOX-13`.  The prefix comes off for the
            # search title only: the shop Title, the Tags and the Description table keep the code the
            # row wrote, because there his own wording is the product.
            seo_code = re.sub(
                rf"^{re.escape(seo_brand)}(?:\s+|\s*-\s*)",
                "",
                seo_code,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
        seo_head = " ".join(
            piece
            for piece in (
                seo_brand,
                seo_code,
                deduped_slots["subtype"],
                deduped_slots["product_type"],
            )
            if piece
        )
        seo_base = (
            f"{seo_head} - {deduped_slots['capacity']}"
            if deduped_slots["capacity"]
            else seo_head
        )
    else:
        usp_tokens_tuple = ()
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
        identity_token=identity_printed,
        warranty_token=warranty,
        subtype_token=subtype if subtype_printed else "",
        subtype_from=subtype_from if subtype_printed else "",
        subtype_label_added=label_printed,
        subtype_line=label_value,
        subtype_label_note="" if label_printed else label_note,
        subtype_conflicts=tuple(conflicts),
        subtype_undecided_columns=undecided_attribute_columns(answers, tuple(conflicts)),
        taps_token=taps,
        volume_capacity_token=volume_capacity if taps else "",
        usp_tokens=usp_tokens_tuple,
        seo_base_title=seo_base if strategy == "rebuilt" else title,
    )


