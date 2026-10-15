"""Tests for the reading layer: shape normalisation, slot claims, residue.

Nothing here builds a Title yet.  These tests pin the layer underneath it: which words
the pipeline may even consider, and in what order the formula slots claim them.  A word
claimed by a slot can never surface again as a series name -- that is the structural
reason "Freezer-On-Top", "Split" and "Bedroom" cannot reach a shop title.

The line this layer draws on purpose: it suppresses only words that are NAMED by an
existing table as a category, a type, a unit, a colour, a brand, a warranty or a sub-type.
Words that merely LOOK generic -- mega, ultra, classic, pro, eco -- stay in the residue
even when they appear in sku_handle.TYPE_WORDS, because the corpus vote is the layer that
can actually prove whether such a word names one product line or decorates twenty.  A
reading layer that guessed would erase real variants it cannot see.
"""

from __future__ import annotations

import re

import pytest

import categories
import sku_handle
import textutils
import title_builder
import warranty_terms
from brands import BRAND_ALIASES, BRAND_DISPLAY_MAP, BRANDS_ALFA, BRANDS_DIGI
from series_corpus import (
    REVIVABLE_SLOT,
    RowAnalysis,
    _pieces,
    analyze_row,
    brand_words,
    noise_vocabulary,
    normalize_shape,
)


def test_duplicate_halves_collapse_to_the_fuller_label() -> None:
    """A stock row writes the same label twice; the fuller copy wins."""
    assert normalize_shape("20FROST INVERTER-DAWLANCE 20FROST INVERTER") == "DAWLANCE 20FROST INVERTER"


def test_an_identical_repeated_half_collapses_to_one() -> None:
    assert normalize_shape("MD15 SOLO WHITE-MD15 SOLO WHITE") == "MD15 SOLO WHITE"


def test_a_genuine_dash_tail_is_not_collapsed() -> None:
    """` - (WD-1051 HC)` is a model tail, not a repeated label; it must survive."""
    title = "Dawlance 2 Taps Water Dispenser White - (WD-1051 HC)"
    assert normalize_shape(title) == title


def test_a_non_repeating_dash_is_left_alone() -> None:
    """`DW9101-DAW REF 9101` is a code then brand+code: two different labels, no collapse."""
    title = "DW9101-DAW REF 9101"
    assert normalize_shape(title) == title


def test_a_repeated_label_is_collapsed_at_its_real_separator_not_its_first_dash() -> None:
    """The dash that splits two copies may sit inside a code, so the run has to match."""
    assert normalize_shape("KGP-18C01S GLORY PRO-KGP-18C01S GLORY PRO") == "KGP-18C01S GLORY PRO"
    assert (
        normalize_shape("MIDEA MSEF1C-18HRFN1-QC6-GO EASY-MIDEA MSEF1C-18HRFN1-QC6-GO EASY")
        == "MIDEA MSEF1C-18HRFN1-QC6-GO EASY"
    )
    assert normalize_shape("MD10-DAW MD10") == "DAW MD10"


@pytest.mark.parametrize(
    "title",
    [
        "PEL Premier 316 Water Dispenser Black (PWD-316)",
        "Dawlance Inverter Split Air Conditioner 1 Ton (1867-S)",
        "Haier Heat Cooler Split AC (T3-PRO-11)",
        "Dawlance Deep Freezer 24T5-CFRESH (500L)",
        "Gree 2 Ton Inverter Split AC (MEH-30)",
    ],
)
def test_a_code_tail_is_never_rotated_into_a_truncated_half(title: str) -> None:
    """`316` also appears in `Premier 316`: a substring test cuts the row at the code.

    Every one of these rows states its code twice over in the sheet, and each time the
    builder was handed a label whose code had been chopped in half -- ``pwd`` on its own
    is a letters-only word a slot would then have to explain away.
    """
    assert normalize_shape(title) == title


@pytest.mark.parametrize(
    "title",
    [
        "KGP-18C01S GLORY PRO-KGP-18C01S GLORY PRO",
        "MIDEA MSEF1C-18HRFN1-QC6-GO EASY-MIDEA MSEF1C-18HRFN1-QC6-GO EASY",
        "CANDY CSU-19HF INVERTER H/C (W)-CANDY CSU-19HF INVERTER H/C (W) SILVER",
    ],
)
def test_the_shape_collapse_drops_only_a_run_the_kept_half_also_states(title: str) -> None:
    """Collapsing a repeat may not lose a word: the kept half already states them all."""
    before = set(re.findall(r"[A-Za-z0-9]+", title.upper()))
    after = set(re.findall(r"[A-Za-z0-9]+", normalize_shape(title).upper()))
    assert before == after


def test_a_glued_size_and_word_waits_for_the_corpus_instead_of_becoming_a_name() -> None:
    """``20FROST`` hides a line name and ``13HFAB`` a code suffix; one row cannot tell them.

    So neither is handed to the builder as a name.  A glued tail is recorded under
    REVIVABLE_SLOT, which is the slot the corpus vote is allowed to take a word back from.
    ``13LF`` is not a tail at all: ``LF`` has no vowel, so the token stays one label.
    """
    frost = analyze_row("DAWLANCE 20FROST INVERTER", product_type="Air Conditioner", brand="Dawlance")
    assert frost.claimed["frost"] == REVIVABLE_SLOT
    assert "frost" not in frost.words
    dashed = analyze_row("HAIER HSU-13HFAB PRIME", product_type="Air Conditioner", brand="Haier")
    assert "hfab" not in dashed.title_words
    assert "hsu" not in dashed.words
    assert dashed.claimed["13hfab"] == "model"
    glued = analyze_row("HAIER 13HFAB PRIME", product_type="Air Conditioner", brand="Haier")
    assert glued.claimed["hfab"] == REVIVABLE_SLOT
    assert "prime" in glued.words
    short = analyze_row("HAIER 13LF PRIME", product_type="Air Conditioner", brand="Haier")
    assert "lf" not in short.title_words
    assert "prime" in short.words


def test_category_words_are_never_in_the_residue() -> None:
    """The 57-row defect: the category name was being sold as a series name."""
    analysis = analyze_row(
        "Dawlance Chrome Freezer-On-Top Refrigerator 10 Cu Ft (9160-WB)",
        product_type="Refrigerator",
        breadcrumb="Electronics / Home appliances / Refrigerators / Freezer-On-Top",
        brand="Dawlance",
        model="9160-WB",
        capacity="10 Cu Ft",
        color="Chrome",
    )
    for word in ("freezer", "on", "top", "refrigerator", "cu", "ft", "dawlance", "9160", "wb"):
        assert word not in analysis.words, word


def test_colour_mode_and_subtype_words_are_claimed_by_their_own_slots() -> None:
    """White / Cool Only / Inverter / Split belong to slots, never to [series]."""
    analysis = analyze_row(
        "Dawlance Frost 30 Inverter Split Air Conditioner White (Cool Only)",
        product_type="Air Conditioner",
        brand="Dawlance",
        capacity="1.5 Ton",
        color="White",
        inverter="Inverter",
    )
    for word in ("white", "cool", "only", "inverter", "split", "air", "conditioner", "dawlance"):
        assert word not in analysis.words, word
    assert "frost" in analysis.words


def test_residue_is_the_same_whatever_the_casing_is() -> None:
    """An all-caps sheet must yield the residue its title-cased twin yields."""
    sentence = "Dawlance Mega Flex Inverter 15"
    caps = analyze_row(sentence.upper(), product_type="Air Conditioner", brand="Dawlance")
    mixed = analyze_row(sentence, product_type="Air Conditioner", brand="Dawlance")
    assert caps.words == mixed.words


def test_no_word_is_invented_or_lost_between_the_pieces_and_the_record() -> None:
    """The invariant the whole design rests on: every piece is accounted for, none twice.

    ``words`` is defined as the unclaimed residue, so asserting the two are disjoint would
    prove nothing.  What can genuinely break is a piece that vanishes from the record, or a
    slot that claims a word the row never stated.
    """
    for title in (
        "MIDEA ECO - WALL MOUNTED DC INVERTER MSAG2B-12HRDN1-QC0",
        "Dawlance Chrome Freezer-On-Top Refrigerator 10 Cu Ft (9160-WB)",
        "PEL Arctic InverterOn Deep Freezer 9 Cu Ft White (PDIN70-180)",
        "DAWLANCE 20FROST INVERTER-DAWLANCE 20FROST INVERTER",
    ):
        analysis = analyze_row(
            title,
            product_type="Air Conditioner",
            brand="Dawlance",
            model="MSAG2B-12HRDN1-QC0",
            capacity="1.5 Ton",
            color="White",
            inverter="Inverter",
        )
        pieces, _, _ = _pieces(normalize_shape(title))
        assert set(pieces) == set(analysis.title_words), title
        assert set(analysis.claimed) <= set(analysis.title_words), title


def test_the_model_code_is_claimed_and_never_offered_as_a_name() -> None:
    analysis = analyze_row(
        "MIDEA ECO - WALL MOUNTED DC INVERTER MSAG2B-12HRDN1-QC0",
        product_type="Air Conditioner",
        brand="Midea",
    )
    assert "eco" in analysis.words
    for fragment in ("msag2b", "hrdn", "qc", "12hrdn", "msag"):
        assert fragment not in analysis.words, fragment


def test_the_residue_keeps_words_in_title_order() -> None:
    analysis = analyze_row(
        "KENWOOD 1267S COMFORT PRO INVERTER",
        product_type="Air Conditioner",
        brand="Kenwood",
    )
    assert analysis.words == ("comfort",)


def test_a_tier_word_claimed_as_a_type_word_stays_recoverable() -> None:
    """'pro' is in TYPE_WORDS, but the corpus must be able to take it back.

    This is the one slot the reading layer does not get to close forever: a word claimed
    as a generic type word is recorded under REVIVABLE_SLOT so a proven tier can be
    restored, while a word owned by the model, colour or category slot never can.
    """
    analysis = analyze_row(
        "KENWOOD 1267S COMFORT PRO INVERTER",
        product_type="Air Conditioner",
        brand="Kenwood",
    )
    assert analysis.claimed["pro"] == REVIVABLE_SLOT
    assert "inverter" not in analysis.words
    # 'inverter' is a category word too ("AC Inverter" is a breadcrumb segment), and a
    # category claim is NOT revivable -- only a generic type-word claim is.
    assert analysis.claimed["inverter"] != REVIVABLE_SLOT


def test_a_shared_adjective_is_left_for_the_corpus_not_eaten_here() -> None:
    """TYPE_WORDS calls mega a type word; the corpus is the layer that can prove it."""
    analysis = analyze_row("DAWLANCE MEGA FLEX 30 INVERTER", product_type="Air Conditioner", brand="Dawlance")
    assert "mega" in analysis.words
    assert "flex" in analysis.words


def test_a_two_letter_word_is_never_offered_as_a_line_name() -> None:
    """214 rows offered "on" as a series name when the breadcrumb did not spell it out.

    A word this short cannot carry a product line in this catalogue, and the reference
    learner requires at least three letters for exactly this reason -- so the bound is
    structural here, not a list of banned words.
    """
    analysis = analyze_row(
        "Dawlance Acce Pro Glass Door Inverter Freezer-On-Top Refrigerator (9173-WB)",
        product_type="Refrigerator",
        breadcrumb="Electronics / Home appliances / Deep Freezers",
        brand="Dawlance",
        model="9173-WB",
        color="White",
        inverter="Inverter",
    )
    assert "on" not in analysis.words
    assert "acce" in analysis.words


def test_every_chunk_of_a_dashed_code_is_code_not_a_name() -> None:
    """`SaveIN-AI-11` and `HSU-13HFAB` are one label each.

    Splitting them on the dash is right for the code, but the letter runs inside --
    ``savein``, ``ai``, ``hsu`` -- are code fragments.  Offering them as names put a
    fragment of a part number into 22 shop titles.
    """
    tcl = analyze_row(
        "TCL SaveIN-AI-11 Inverter Split Air Conditioner Heat & Cool 1.5 Ton White",
        product_type="Air Conditioner",
        brand="TCL",
    )
    assert "savein" not in tcl.words
    haier = analyze_row(
        "Haier Inventer T3 Air Conitioner 1 Ton Grey (HSU-13HFAB)",
        product_type="Air Conditioner",
        brand="Haier",
    )
    assert "hsu" not in haier.words
    assert "hf" not in haier.words


def test_a_glued_pair_of_type_words_is_not_offered_as_a_name() -> None:
    """Sheets glue two known words into one token: "Inverter On" -> InverterOn.

    The word is not in any table, but it decomposes entirely into words that are, so it
    cannot be a product line name.  A genuine name in the same title survives untouched.
    """
    analysis = analyze_row(
        "PEL Arctic InverterOn Deep Freezer 9 Cu Ft White (PDIN70-180)",
        product_type="Deep Freezer",
        brand="PEL",
    )
    assert "inverteron" not in analysis.words
    assert "arctic" in analysis.words


def test_a_real_two_word_line_name_is_never_glue_split() -> None:
    """Gree Pular and Dawlance Blaze are names; the glue rule must not eat them."""
    gree = analyze_row(
        "Gree Pular T3 Inverter Split Air Conditioner 2 Ton White (GS-24PITH15W-T3)",
        product_type="Air Conditioner",
        brand="Gree",
    )
    assert "pular" in gree.words
    dawlance = analyze_row(
        "Dawlance Blaze Series 32 Inch 2K HD Google TV (32 Inch E22)",
        product_type="LED TV",
        brand="Dawlance",
    )
    assert "blaze" in dawlance.words


def test_noise_vocabulary_invents_no_words() -> None:
    """Every word it can suppress must already live in one of the repo's tables."""
    vocabulary = noise_vocabulary()
    assert vocabulary
    sources = _all_source_words()
    invented = {word for word in vocabulary if word not in sources}
    assert not invented, sorted(invented)


def _all_source_words() -> set[str]:
    """Flatten every existing table into bare words, computed here, not imported."""
    words: set[str] = set()
    for pool in (
        sku_handle.TYPE_WORDS,
        title_builder._STOPWORDS,
        textutils.BASE_COLORS,
        textutils.COLOR_MODIFIERS,
        textutils.COLOR_NON_MODIFIERS,
        categories.STOP_SEGMENTS,
    ):
        for item in pool:
            words.update(re.findall(r"[a-z]+", str(item).lower()))
    for group in title_builder.SUBTYPES.values():
        for labels in group:
            for label, aliases in labels.items():
                words.update(re.findall(r"[a-z]+", label.lower()))
                for alias in aliases:
                    words.update(re.findall(r"[a-z]+", alias.lower()))
    for table in (
        categories.PRODUCT_TYPE_MAP,
        categories.CATEGORY_DIGI_PATHS,
        categories.CATEGORY_ALFA_IDS,
        categories.DIGI_SEGMENT_ALIASES,
        categories.ALFA_SEGMENT_ALIASES,
        BRAND_ALIASES,
        BRAND_DISPLAY_MAP,
    ):
        for key, value in table.items():
            words.update(re.findall(r"[a-z]+", f"{key} {value}".lower()))
    for table in (BRANDS_ALFA, BRANDS_DIGI):
        for key, value in table.items():
            words.update(re.findall(r"[a-z]+", f"{key} {value}".lower()))
    for by_type in warranty_terms.WARRANTY_TERMS.values():
        for product_type, clause in by_type.items():
            words.update(re.findall(r"[a-z]+", f"{product_type} {clause}".lower()))
    return words


def test_noise_vocabulary_covers_the_words_it_must_kill() -> None:
    """The exact words that reached shop titles must be suppressible."""
    vocabulary = noise_vocabulary()
    for word in (
        "freezer", "split", "inverter", "refrigerator", "washing", "taps",
        "white", "grey", "warranty", "years", "model", "cu", "ft", "dawlance",
    ):
        assert word in vocabulary, word


def test_noise_vocabulary_leaves_the_words_the_corpus_must_judge() -> None:
    """Proven line names and shared adjectives must survive to be voted on."""
    vocabulary = noise_vocabulary()
    for word in ("eco", "frost", "chrome", "comfort", "infinity"):
        assert word not in vocabulary, word


def test_analysis_names_the_slot_that_claimed_each_word() -> None:
    """A wrong pick is reviewable only if the claim carries its slot name."""
    analysis = analyze_row(
        "Dawlance 1.5 Ton White Inverter Cool Only Split Air Conditioner",
        product_type="Air Conditioner",
        brand="Dawlance",
        capacity="1.5 Ton",
        color="White",
        inverter="Inverter",
    )
    assert analysis.claimed["ton"] == "capacity"
    assert analysis.claimed["white"] == "color"
    assert analysis.claimed["inverter"] == "inverter"
    assert analysis.claimed["split"] == "subtype"
    assert analysis.claimed["air"] == "category"
    assert analysis.claimed["dawlance"] == "brand"


def test_the_capacity_slot_owns_the_number_a_row_states_as_capacity() -> None:
    """``1.5`` in the Capacity column is a capacity, not a fragment of a part number.

    The code chunks are claimed before the slots run, and a bare number on its own really
    is part of a label -- but a number the row hands over as its capacity must be recorded
    as a capacity, or the review of a wrong pick points at the wrong slot.
    """
    analysis = analyze_row(
        "Dawlance 1.5 Ton White Inverter Split Air Conditioner (HWF-18DFA)",
        product_type="Air Conditioner",
        brand="Dawlance",
        capacity="1.5 Ton",
        color="White",
        inverter="Inverter",
    )
    assert analysis.claimed["1"] == "capacity"
    assert analysis.claimed["5"] == "capacity"
    assert analysis.claimed["hwf"] == "model"
    assert analysis.claimed["18dfa"] == "model"
    # A number the row does NOT state as its capacity stays a piece of a label: 20 here is
    # the Dawlance stock code, and the brand map (not this layer) decides what it means.
    frost = analyze_row(
        "DAWLANCE 20FROST INVERTER", product_type="Air Conditioner", brand="Dawlance", capacity="1.5 Ton"
    )
    assert frost.claimed["20"] == "model"


def test_a_colour_word_is_filed_under_the_colour_slot_even_without_a_colour_column() -> None:
    """A sheet title states the colour in prose and keeps no Colour column.

    ``black`` is then still a colour, not a word the corpus may sell as a series name.  A
    colour MODIFIER alone is different: ``pearl`` may name a line, so it stays revivable.
    """
    analysis = analyze_row(
        "PEL Black Pearl Deep Freezer 9 Cu Ft", product_type="Deep Freezer", brand="PEL"
    )
    assert analysis.claimed["black"] == "color"
    assert analysis.claimed["pearl"] == REVIVABLE_SLOT
    assert "black" not in analysis.words


def test_a_vowel_less_run_is_a_code_fragment_and_not_a_name() -> None:
    """``HTZ`` cannot be read as a word, so no slot has to be told it is not a name."""
    analysis = analyze_row(
        "Gree HTZ GD-18WBS Split Air Conditioner 2 Ton White",
        product_type="Air Conditioner",
        brand="Gree",
    )
    assert analysis.claimed["htz"] == "model"
    assert "htz" not in analysis.words
    assert analysis.claimed["gd"] == "model"


def test_a_two_word_brand_written_as_one_word_is_still_the_brand() -> None:
    """ECOSTAR is how the sheet writes Eco Star -- and ECO on a Midea row is still free."""
    eco_star = analyze_row(
        "ECOSTAR ES-12DU01GC Inverter Split Air Conditioner 1.5 Ton",
        product_type="Air Conditioner",
        brand="Eco Star",
    )
    assert eco_star.claimed["ecostar"] == "brand"
    assert "ecostar" not in eco_star.words
    midea = analyze_row(
        "MIDEA ECO - WALL MOUNTED DC INVERTER MSAG2B-12HRDN1-QC0",
        product_type="Air Conditioner",
        brand="Midea",
    )
    assert "eco" in midea.words


def test_the_words_inside_a_catalogue_brand_name_are_never_flattened() -> None:
    """``eco star`` contributes ECOSTAR to the brand words, never bare ``eco``.

    A brand table that contributed its words would suppress the series word of every Midea
    and Gree row that sells an ECO line.
    """
    assert "ecostar" in brand_words()
    for word in ("eco", "star", "west", "point", "super", "asia", "pakistan"):
        assert word not in brand_words(), word


def test_a_brand_written_as_a_sheet_abbreviation_is_still_claimed() -> None:
    """Stock rows abbreviate the brand in the text: DAW is Dawlance."""
    analysis = analyze_row("DAW MEGA FLEX 30 INVERTER", product_type="Air Conditioner", brand="Dawlance")
    assert "daw" not in analysis.words
    assert analysis.claimed["daw"] == "brand"


def test_row_analysis_is_an_immutable_value() -> None:
    """Both pipeline passes must see one analysis, so neither can edit it."""
    analysis = analyze_row("Dawlance Frost Inverter", product_type="Air Conditioner", brand="Dawlance")
    assert isinstance(analysis, RowAnalysis)
    assert isinstance(analysis.words, tuple)
    with pytest.raises(TypeError):
        analysis.claimed["frost"] = "model"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        analysis.title = "edited"  # type: ignore[misc]
