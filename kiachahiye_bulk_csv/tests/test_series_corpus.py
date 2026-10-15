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

import csv
import re
from pathlib import Path

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
    build_corpus,
    category_vocabulary,
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


# --------------------------------------------------------------------------- #
# [3]-[4]: the corpus vote -- what the whole run says about a residue word
# --------------------------------------------------------------------------- #
def _rows(*rows: tuple[str, ...]) -> list[RowAnalysis]:
    """Read (title, brand, breadcrumb, product_type) rows the way the pipeline will.

    The product type is not decoration: `No Frost` is a type only for a Refrigerator row, and a
    test that forgets it is testing a different contract than main.py will run.
    """
    return [
        analyze_row(
            row[0],
            brand=row[1],
            breadcrumb=row[2],
            product_type=row[3] if len(row) > 3 else "",
        )
        for row in rows
    ]


def test_a_residue_word_is_recorded_with_where_it_sat_in_its_row() -> None:
    """The vote needs more than the word: the position is the evidence."""
    midea = analyze_row(
        "MIDEA ECO - WALL MOUNTED DC INVERTER MSAG2B-12HRDN1-QC0",
        product_type="Air Conditioner",
        brand="Midea",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
    )
    assert midea.positions["eco"].brand_adjacent
    assert not midea.positions["eco"].code_adjacent
    haier = analyze_row(
        "HAIER HSU 19HFPCAA 013W USDC (G) INVERTER SPLIT AC",
        product_type="Air Conditioner",
        brand="Haier",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
    )
    assert haier.positions["usdc"].beside == frozenset({"013w"})
    assert not haier.positions["usdc"].brand_adjacent
    dawlance = analyze_row(
        "Dawlance Frost 30 Inverter Split Air Conditioner 1.5 Ton",
        product_type="Air Conditioner",
        brand="Dawlance",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
    )
    # `30` is a size the row states, not a part number, so `Frost` stands free of codes.
    assert dawlance.positions["frost"].brand_adjacent
    assert not dawlance.positions["frost"].code_adjacent


def test_a_word_one_brand_states_in_several_rows_is_a_proven_name() -> None:
    corpus = build_corpus(
        _rows(
            ("Gree Avante 9173 Inverter Split Air Conditioner 1.5 Ton", "Gree", "Air Conditioners"),
            ("Gree Avante Plus 12354 Inverter Split Air Conditioner 1.5 Ton", "Gree", "Air Conditioners"),
            ("Gree Chrome 8841 Split Air Conditioner 2 Ton", "Gree", "Air Conditioners"),
        )
    )
    assert set(corpus.proven) == {"gree"}
    assert set(corpus.proven["gree"]) == {"avante", "chrome"}
    assert corpus.proven["gree"]["avante"].rows == 2


def test_a_word_three_brands_share_is_a_modifier_not_a_name() -> None:
    """Decorating three brands is exactly what no product line can do."""
    corpus = build_corpus(
        _rows(
            ("Dawlance Ultra Inverter Split Air Conditioner 1.5 Ton", "Dawlance", "Air Conditioners"),
            ("Haier Ultra Inverter Split Air Conditioner 1 Ton", "Haier", "Air Conditioners"),
            ("PEL Ultra Deep Freezer 9 Cu Ft", "PEL", "Deep Freezers"),
            ("Dawlance Infinity Inverter Split Air Conditioner 1.5 Ton", "Dawlance", "Air Conditioners"),
            ("Dawlance Infinity Split Air Conditioner 1 Ton", "Dawlance", "Air Conditioners"),
        )
    )
    assert "ultra" in corpus.blacklisted
    assert corpus.is_proven("Dawlance", "infinity")


def test_a_word_that_abbreviates_the_class_every_row_states_is_noise() -> None:
    """The 26-row `DAW REF 9101` class: `ref` abbreviates the row's own Refrigerator."""
    corpus = build_corpus(
        _rows(
            ("DW9101-DAW REF 9101", "Dawlance", "Electronics / Home appliances / Refrigerators"),
            ("DAW REF 9173WB AVANTE GD INV", "Dawlance", "Electronics / Home appliances / Refrigerators"),
            ("DAW REF 9151CH AVANTE CQ INV", "Dawlance", "Electronics / Home appliances / Refrigerators"),
        )
    )
    assert "ref" in corpus.blacklisted
    assert corpus.blacklisted["ref"].class_prefixed == 3
    # In these two rows `avante` sits against a part number every single time, so the vote
    # cannot yet tell it from a code tail -- the real sheet proves it because 9 of its 20
    # rows state avante away from any code.
    assert "avante" in corpus.undecided
    assert corpus.undecided["avante"].code_adjacent == 2
    standing_free = build_corpus(
        _rows(
            ("DAW REF 9173WB AVANTE GD INV", "Dawlance", "Electronics / Home appliances / Refrigerators"),
            ("DAW REF 9151CH AVANTE CQ INV", "Dawlance", "Electronics / Home appliances / Refrigerators"),
            ("Dawlance Avante Deep Freezer 9 Cu Ft White", "Dawlance", "Electronics / Deep Freezers"),
        )
    )
    assert standing_free.is_proven("Dawlance", "avante")


def test_a_word_that_only_ever_sits_next_to_a_code_is_never_a_name() -> None:
    """`USDC` in `HSU 19HFPCAA 013W USDC (G)` recurs three times and names nothing.

    This is the reviewer's case: recurrence alone is not proof, because a code suffix
    recurs as much as a line name does.  A line name appears somewhere away from the code.
    """
    corpus = build_corpus(
        _rows(
            ("HAIER HSU 19HFPCAA 013W USDC (G) INVERTER SPLIT AC", "Haier", "Air Conditioners"),
            ("HAIER HSU 19HFPCAA 013W USDC (B) INVERTER SPLIT AC", "Haier", "Air Conditioners"),
            ("HAIER HSU 19HFPCAA 013W USDC (S) INVERTER SPLIT AC", "Haier", "Air Conditioners"),
        )
    )
    assert not corpus.is_proven("Haier", "usdc")
    assert corpus.undecided["usdc"].code_adjacent == 3


def test_a_single_row_word_is_proven_only_when_the_brand_introduces_it() -> None:
    """The thin-sheet rescue: one row, but the brand puts the word in front of the class."""
    corpus = build_corpus(
        _rows(
            ("MIDEA ECO - WALL MOUNTED DC INVERTER MSAG2B-12HRDN1-QC0", "Midea", "Air Conditioners"),
            ("MIDEA MSAG2B-12HRDN1-QC0 WALL MOUNTED INVERTER", "Midea", "Air Conditioners"),
        )
    )
    assert corpus.is_proven("Midea", "eco")


def test_a_word_a_row_only_writes_glued_to_its_size_is_not_a_candidate() -> None:
    """A sheet that only ever writes `20FROST` proves nothing; one bare `Frost` does.

    The glued tail waits in the revivable slot, so it never reaches the vote.  The row that
    writes the word on its own, straight after the brand, is what proves it -- and then
    stage [5] is allowed to take `frost` back out of the revivable slot on the glued rows.
    """
    glued_only = build_corpus(
        _rows(
            ("DAWLANCE 20FROST INVERTER", "Dawlance", "Air Conditioners"),
            ("DAWLANCE 30FROST INVERTER", "Dawlance", "Air Conditioners"),
        )
    )
    assert not glued_only.is_proven("Dawlance", "frost")
    with_one_bare = build_corpus(
        _rows(
            ("DAWLANCE 20FROST INVERTER", "Dawlance", "Air Conditioners"),
            ("DAWLANCE 30FROST INVERTER", "Dawlance", "Air Conditioners"),
            ("Dawlance Frost 30 Inverter Split Air Conditioner 1.5 Ton", "Dawlance", "Air Conditioners"),
        )
    )
    assert with_one_bare.is_proven("Dawlance", "frost")


def test_the_vote_reads_both_sheets_and_proves_the_names_the_shop_uses() -> None:
    """The real 752-row sheet, not a sample: the shipped names must be in the proven set."""
    path = Path(__file__).resolve().parents[1] / "data/input/Products.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        analyses = [
            analyze_row(
                (row.get("Title") or "").strip(),
                brand=(row.get("Brand") or "").strip(),
                breadcrumb=(row.get("Categories") or "").strip(),
            )
            for row in csv.DictReader(handle)
        ]
    corpus = build_corpus(analyses)
    earned = {word for words in corpus.proven.values() for word in words}
    for name in ("avante", "chrome", "pular", "acce", "icemax", "glory", "persona", "zeno"):
        assert name in earned, name
    # Measured ownership, not guessed: Frost is Dawlance's (3 rows stating it after the brand,
    # the rest being the No Frost type phrase), Blaze is Pel's (29 rows), and neither is judged
    # by what the other brand does with the word.
    assert corpus.is_proven("Dawlance", "frost")
    assert corpus.is_proven("pel", "blaze")
    for noise in ("ultra", "classic", "mega", "grill", "wash", "cabinet"):
        assert noise not in earned, noise
    # Known misses, measured here so they stay visible rather than silently accepted: a feature
    # word that one brand states in two or more rows still earns that brand, because no table
    # calls it a type.  This is the vocabulary gap (plan T5), not a voting bug.
    for feature in ("wifi", "iot", "solo", "cooking", "flat"):
        assert feature in earned or feature in corpus.blacklisted, feature


def test_a_number_before_a_word_is_code_evidence_and_a_number_after_it_is_not() -> None:
    """The two directions of a bare number state different facts.

    `HRF 418 IFP` is one part number the sheet wrote with a space, so `418` proves IFP is a
    code tail.  `Frost 30` is how the stock rows write their identity -- the size follows the
    name -- and reading `30` as code evidence would delete every name+size pair in the file.
    """
    suffix = analyze_row(
        "HAIER HRF 418 IFP NO FROST REFRIGERATOR",
        product_type="Refrigerator",
        brand="Haier",
        breadcrumb="Electronics / Home appliances / Refrigerators",
    )
    assert suffix.positions["ifp"].beside == frozenset({"418"})
    identity = analyze_row(
        "Dawlance Frost 30 Inverter Split Air Conditioner 1.5 Ton",
        product_type="Air Conditioner",
        brand="Dawlance",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
    )
    assert identity.positions["frost"].beside == frozenset()


def test_a_code_suffix_stays_unproven_even_when_its_code_varies() -> None:
    """Recurrence is not proof: `USDC` sits against a part number in every row that states it.

    The draft rule also believed a word whose neighbouring codes differed, which turned
    `toploader`, `grill` and `classic` into product lines and proved USDC as soon as one of
    its three rows carried a different size.
    """
    corpus = build_corpus(
        _rows(
            ("HAIER HSU 19HFPCAA 013W USDC (G) INVERTER SPLIT AC", "Haier", "Air Conditioners"),
            ("HAIER HSU 19HFPCAA 021W USDC (B) INVERTER SPLIT AC", "Haier", "Air Conditioners"),
            ("HAIER HSU 19HFPCAA 013W USDC (S) INVERTER SPLIT AC", "Haier", "Air Conditioners"),
        )
    )
    assert "usdc" not in corpus.proven
    assert corpus.undecided["usdc"].code_adjacent == 3


def test_one_free_standing_word_in_one_row_is_not_a_name() -> None:
    """A word that appears once, in no informative position, must not be printed.

    Loosening the sibling rule from two rows to one is the cheapest way to turn every typo in
    the sheet into a product line, so the thin-sheet path is reached only through the brand.
    """
    corpus = build_corpus(
        _rows(
            ("Gree Split Divine Air Conditioner 2 Ton White (GS-24DW)", "Gree", "Air Conditioners"),
            ("Gree Inverter Split Air Conditioner 1.5 Ton White (GS-18NW)", "Gree", "Air Conditioners"),
        )
    )
    assert not corpus.is_proven("Gree", "divine")
    assert corpus.undecided["divine"].rows == 1


def test_the_rescue_needs_both_the_brand_position_and_no_code_touch() -> None:
    """One row is believed when the brand introduces the word AND no part number touches it."""
    corpus = build_corpus(
        _rows(
            ("GREE 24DW PULSE INVERTER SPLIT AIR CONDITIONER", "Gree", "Air Conditioners"),
            ("GREE 18DW INVERTER SPLIT AIR CONDITIONER", "Gree", "Air Conditioners"),
        )
    )
    assert not corpus.is_proven("Gree", "pulse")


def test_a_word_two_brands_state_earns_only_the_one_with_its_own_evidence() -> None:
    """Per brand means per brand evidence: two Dawlance rows prove Dawlance's, not Haier's.

    The whole-catalogue count used to put any word two brands shared into the tie box, which
    silenced Dawlance's own lines.  Now each brand is judged on its own rows, and a brand that
    states the word once without introducing it stays undecided -- and prints nothing.
    """
    corpus = build_corpus(
        _rows(
            ("Dawlance Magnum Inverter Split Air Conditioner 1.5 Ton", "Dawlance", "Air Conditioners"),
            ("Dawlance Magnum Split Air Conditioner 1 Ton White", "Dawlance", "Air Conditioners"),
            ("Haier Inverter Double Door Deep Freezer Magnum 9 Cu Ft", "Haier", "Deep Freezers"),
        )
    )
    assert corpus.is_proven("Dawlance", "magnum")
    assert not corpus.is_proven("Haier", "magnum")
    assert set(corpus.proven) == {"dawlance"}


def test_a_class_abbreviation_is_disqualified_only_when_every_row_states_the_class() -> None:
    """`REF` is noise when the row says Refrigerator; a row that says nothing cannot disprove it."""
    every_row = build_corpus(
        _rows(
            ("DW9101-DAW REF 9101", "Dawlance", "Electronics / Home appliances / Refrigerators"),
            ("DAW REF 9106", "Dawlance", "Electronics / Home appliances / Refrigerators"),
        )
    )
    assert "ref" in every_row.blacklisted
    one_row_silent = build_corpus(
        _rows(
            ("Dawlance Ref Inverter Split Air Conditioner 1.5 Ton", "Dawlance", "Air Conditioners"),
            ("Dawlance Ref Split Air Conditioner 1 Ton White", "Dawlance", "Air Conditioners"),
        )
    )
    assert one_row_silent.is_proven("Dawlance", "ref")


def test_the_category_table_contributes_the_words_of_its_multi_word_entries() -> None:
    """A table read as whole strings can never match a word -- so those words were not covered."""
    vocabulary = category_vocabulary()
    for word in ("green", "energy", "audio", "visuals", "sound", "bars"):
        assert word in vocabulary, word


# --------------------------------------------------------------------------- #
# slice 2: verdicts belong to a brand, and a TYPE phrase is not a name
# --------------------------------------------------------------------------- #
def test_no_frost_is_a_type_so_frost_is_not_that_rows_name() -> None:
    """`No Frost` says what kind of fridge it is; `Frost` says which Dawlance line.

    The phrase lives in the existing sub-type config, so the word is claimed as a type word
    and never reaches the vote as a candidate -- no word list and no special case.
    """
    haier = analyze_row(
        "Haier No Frost Freezer On Top Refrigerator 17 Cu Ft Black (HRF-488IFFB)",
        product_type="Refrigerator",
        brand="Haier",
        breadcrumb="Electronics / Home appliances / Refrigerators / Freezer-On-Top",
    )
    assert "frost" not in haier.words
    assert haier.claimed["frost"] == "subtype"
    dawlance = analyze_row(
        "Dawlance Frost 30 Inverter Split Air Conditioner 1.5 Ton White (Cool Only)",
        product_type="Air Conditioner",
        brand="Dawlance",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
    )
    assert "frost" in dawlance.words


def test_a_word_is_proven_for_the_brand_that_earned_it_and_not_for_the_other() -> None:
    """One global verdict per word was wrong: Frost is Dawlance's line.

    Haier states `Frost` too, and the old whole-catalogue count put the word in the tie box,
    which silenced the Dawlance rows that sell the Frost model.  Per-brand evidence decides
    per brand, and the brand that states it only inside a type phrase states no candidate.
    """
    corpus = build_corpus(
        _rows(
            (
                "Dawlance Frost 30 Inverter Split Air Conditioner 1.5 Ton White",
                "Dawlance",
                "Electronics / Home appliances / Air Conditioners",
                "Air Conditioner",
            ),
            (
                "Dawlance Frost 45 Inverter Split Air Conditioner 2 Ton White",
                "Dawlance",
                "Electronics / Home appliances / Air Conditioners",
                "Air Conditioner",
            ),
            (
                "Haier No Frost Refrigerator 17 Cu Ft Black (HRF-488IFFB)",
                "Haier",
                "Electronics / Home appliances / Refrigerators / Freezer-On-Top",
                "Refrigerator",
            ),
            (
                "Haier No Frost Refrigerator 18 Cu Ft Silver (HRF-518IFFB)",
                "Haier",
                "Electronics / Home appliances / Refrigerators / Freezer-On-Top",
                "Refrigerator",
            ),
        )
    )
    assert corpus.is_proven("Dawlance", "frost")
    assert not corpus.is_proven("Haier", "frost")
    assert not corpus.is_proven("Samsung", "frost")


def test_a_word_three_brands_share_is_still_disqualified_for_every_one_of_them() -> None:
    """Per-brand proof must not reopen the door the multi-brand blacklist closes."""
    corpus = build_corpus(
        _rows(
            ("Dawlance Ultra Inverter Split Air Conditioner 1.5 Ton", "Dawlance", "Air Conditioners"),
            ("Dawlance Ultra Split Air Conditioner 1 Ton White", "Dawlance", "Air Conditioners"),
            ("Haier Ultra Inverter Split Air Conditioner 1 Ton", "Haier", "Air Conditioners"),
            ("Haier Ultra Split Air Conditioner 1.5 Ton", "Haier", "Air Conditioners"),
            ("PEL Ultra Deep Freezer 9 Cu Ft White", "PEL", "Deep Freezers"),
            ("PEL Ultra Deep Freezer 12 Cu Ft Black", "PEL", "Deep Freezers"),
        )
    )
    assert "ultra" in corpus.blacklisted
    assert not corpus.is_proven("Dawlance", "ultra")
    assert not corpus.is_proven("Haier", "ultra")


def test_two_brands_each_with_their_own_evidence_both_keep_their_word() -> None:
    """Gree Blaze and Pel Blaze are different lines; the vote is not asked to choose."""
    corpus = build_corpus(
        _rows(
            ("Gree Blaze Inverter Split Air Conditioner 1.5 Ton", "Gree", "Air Conditioners"),
            ("Gree Blaze Split Air Conditioner 2 Ton White", "Gree", "Air Conditioners"),
            ("PEL Blaze Deep Freezer 9 Cu Ft White", "PEL", "Deep Freezers"),
            ("PEL Blaze Deep Freezer 12 Cu Ft Black", "PEL", "Deep Freezers"),
        )
    )
    assert corpus.is_proven("Gree", "blaze")
    assert corpus.is_proven("PEL", "blaze")


def test_a_word_one_edit_from_the_class_word_the_same_row_states_is_that_typo() -> None:
    """`Haier Inventer ... Inverter Split AC` states its class twice, one of them misspelled.

    The sheet is the only evidence: the row already gives `inverter` to the inverter slot, and
    `inventer` differs from it by one letter, so the second spelling is the vendor's typo, not a
    product line.  `conditioner`/`conitioner` is the same case in the category slot.  No dictionary
    and no word list is involved -- only words this very row states.
    """
    haier = analyze_row(
        "Haier Inventer Split Air Conditioner 1 Ton White (HSU-19HFP)",
        product_type="Air Conditioner",
        brand="Haier",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
        inverter="Inverter",
    )
    assert "inventer" not in haier.words
    assert haier.claimed["inventer"] == "inverter"
    wrong_category = analyze_row(
        "Haier Inverter Split Conitioner 1 Ton White (HSU-19HFP)",
        product_type="Air Conditioner",
        brand="Haier",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
        inverter="Inverter",
    )
    assert "conitioner" not in wrong_category.words
    assert wrong_category.claimed["conitioner"] == "category"


def test_a_real_line_name_one_edit_away_from_a_class_word_is_still_a_name() -> None:
    """The guard may not eat a genuine series: Frost is not Freezer, Chrome is not Phone.

    Both rows state the class word right next to the name, so a looser rule (same length, or any
    shared prefix) would have deleted the line name from the shop title.
    """
    dawlance = analyze_row(
        "Dawlance Frost Freezer-On-Top Refrigerator 10 Cu Ft White (9173-WB)",
        product_type="Refrigerator",
        brand="Dawlance",
        breadcrumb="Electronics / Home appliances / Refrigerators / Freezer-On-Top",
    )
    assert "frost" in dawlance.words
    gree = analyze_row(
        "Gree Chrome Split Air Conditioner 1.5 Ton White (GS-18CH)",
        product_type="Air Conditioner",
        brand="Gree",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
    )
    assert "chrome" in gree.words


def test_the_vote_needs_two_distinct_products_not_two_colour_variants_of_one_sku() -> None:
    """Four shop rows of one model prove nothing: a row is an offer, not a product.

    This is the class the reviewer measured on the real sheet -- one Haier SKU restated in three
    colour/tonnage variants carried its own typo to three votes and looked like a line name.
    """
    variants = _rows(
        ("Haier Inventer Split AC 1 Ton White (Y2K61M)", "Haier", "Air Conditioners", "Air Conditioner"),
        ("Haier Inventer Split AC 1.5 Ton Black (Y2K61M)", "Haier", "Air Conditioners", "Air Conditioner"),
        ("Haier Inventer Split AC 1 Ton Red (Y2K61M)", "Haier", "Air Conditioners", "Air Conditioner"),
    )
    corpus = build_corpus(variants)
    assert not corpus.is_proven("Haier", "inventer")
    across_models = build_corpus(
        _rows(
            ("Dawlance Avante Deep Freezer 9 Cu Ft White (9173WB)", "Dawlance", "Deep Freezers", "Deep Freezer"),
            ("Dawlance Avante Deep Freezer 12 Cu Ft Black (9151CH)", "Dawlance", "Deep Freezers", "Deep Freezer"),
        )
    )
    assert across_models.is_proven("Dawlance", "avante")
    assert across_models.proven["dawlance"]["avante"].products == 2


def test_a_phrase_is_matched_in_the_order_the_row_wrote_it() -> None:
    """Deduplicating before matching breaks a phrase whose words repeat: `Cool ... Cool Only`."""
    row = analyze_row(
        "Haier Cool Inverter Air Conditioner Cool Only 1.5 Ton (19LF)",
        product_type="Air Conditioner",
        brand="Haier",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
    )
    assert row.claimed["only"] == "subtype"


def test_a_single_letter_written_in_front_of_a_name_is_part_of_that_name() -> None:
    """Owner ruling: Haier's line is `E-Star`, so the sheet never offered `star` alone.

    `E` is not a word any table names and not a code: it is the initial of the word after it.
    Joining it is what stops 14 Haier rows from voting for a name the vendor never wrote.
    """
    haier = analyze_row(
        "Haier E-Star Freezer-On-Top Refrigerator 12 Cu Ft (HRF-346EPB)",
        product_type="Refrigerator",
        brand="Haier",
        breadcrumb="Electronics / Home appliances / Refrigerators / Freezer-On-Top",
    )
    assert "e-star" in haier.words
    assert "star" not in haier.words
    assert source_of(haier, "e-star") == "E-Star"


def test_the_space_and_the_dash_form_of_one_line_share_one_vote_key() -> None:
    """`E Chrome` and `E-CHROME` are Dawlance's one line; the key must not fork it.

    The key is canonical so the evidence of both writings votes together, while each row keeps
    its own spelling for rendering -- which is why the dash is not simply stripped.
    """
    spaced = analyze_row(
        "Dawlance E Chrome Freezer-On-Top Refrigerator Metallic Grey (REF-9149WB)",
        product_type="Refrigerator",
        brand="Dawlance",
        breadcrumb="Electronics / Home appliances / Refrigerators / Freezer-On-Top",
    )
    dashed = analyze_row(
        "DAW 9149WB E-CHROME METALLIC GRAY",
        product_type="Refrigerator",
        brand="Dawlance",
        breadcrumb="Refrigerators",
    )
    assert "e-chrome" in spaced.words and "e-chrome" in dashed.words
    assert "chrome" not in spaced.words and "chrome" not in dashed.words
    assert source_of(spaced, "e-chrome") == "E Chrome"
    assert source_of(dashed, "e-chrome") == "E-CHROME"


def test_the_letter_may_only_take_a_word_that_no_slot_claimed() -> None:
    """A one-letter initial joins a NAME, never a word a slot already owns.

    `X Inverter` is a mode statement and `U Cool` is the brand: joining either would invent a
    word the row does not sell.  The pairs are real rows from the two sheets.
    """
    dawlance = analyze_row(
        "Dawlance Elegance X Inverter Split Air Conditioner 1 Ton",
        product_type="Air Conditioner",
        brand="Dawlance",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
    )
    assert "x-inverter" not in dawlance.words
    homage = analyze_row(
        "U COOL AIR CURTAIN UCA-315Y 3FT",
        product_type="Air Curtain",
        brand="U Cool",
        breadcrumb="Air Curtains",
    )
    assert "u-cool" not in homage.words


def test_a_two_letter_word_is_never_glued_to_the_name_after_it() -> None:
    """The bound is one letter, measured: two-letter pieces are units and phrase words.

    `Cu Ft Red`, `Freezer-On-Top` and `No Frost` all put a two-letter piece directly in front of
    a word, and gluing them would have destroyed the capacity unit, the category phrase and the
    type phrase this very row states.
    """
    dawlance = analyze_row(
        "Dawlance 12 Cu Ft Red Freezer-On-Top Refrigerator No Frost (HRF-346EPR)",
        product_type="Refrigerator",
        brand="Dawlance",
        breadcrumb="Electronics / Home appliances / Refrigerators / Freezer-On-Top",
    )
    for glued in ("ft-red", "on-top", "no-frost", "cu-ft"):
        assert glued not in dawlance.words, glued
    assert "frost" not in dawlance.words


def test_every_candidate_carries_the_rows_own_spelling() -> None:
    """The folded key decides the vote; the sheet's own letters are what a shop can print.

    `eComfort` is Haier's/Midea's spelling of a line.  A pipeline that renders the key would
    ship `Ecomfort`, so the reading layer has to hand both forms down.
    """
    midea = analyze_row(
        "Midea eComfort Inverter Split Air Conditioner 1 Ton White (MSAG2B-12HRDN1-QC0)",
        product_type="Air Conditioner",
        brand="Midea",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
    )
    assert "ecomfort" in midea.words
    assert source_of(midea, "ecomfort") == "eComfort"


def test_a_candidate_records_every_piece_it_covers() -> None:
    """The invariant the whole design rests on, stated on candidates: claimed XOR covered.

    A joined pair covers two pieces under one candidate, so coverage -- not the key -- is what
    must partition the row's pieces.
    """
    for title in (
        "Haier E-Star Freezer-On-Top Refrigerator 12 Cu Ft (HRF-346EPB)",
        "MIDEA ECO - WALL MOUNTED DC INVERTER MSAG2B-12HRDN1-QC0",
        "Dawlance Chrome Freezer-On-Top Refrigerator 10 Cu Ft (9160-WB)",
        "KENWOOD 1267S COMFORT PRO INVERTER",
    ):
        analysis = analyze_row(
            title,
            product_type="Air Conditioner",
            brand="Dawlance",
            breadcrumb="Electronics / Home appliances / Air Conditioners",
        )
        covered = [piece for candidate in analysis.candidates for piece in candidate.pieces]
        assert not set(analysis.claimed) & set(covered), title
        assert set(analysis.claimed) | set(covered) == set(analysis.title_words), title
        assert len(covered) == len(set(covered)), title


def test_a_letter_that_is_half_of_an_abbreviation_is_not_an_initial() -> None:
    """`W/O REF` is a note, not a name: the letter after the slash belongs to the slash.

    Review finding.  A one-letter piece that itself follows a slash or a dot is the tail of a
    written abbreviation (`W/O`, `M/O`, `R/C`), so joining it to the next word both invents a
    label nobody sells (`o-ref`) and deletes the row's one genuine free word (`ref`) from the
    vote.  `E-Star` stays joinable because its letter begins a written word.
    """
    note = analyze_row(
        "DW1060FP-DAWLANCE 1060FP W/O REF WHITE",
        product_type="Deep Freezer",
        brand="Dawlance",
        breadcrumb="Electronics / Home appliances / Deep Freezers",
    )
    assert "o-ref" not in note.words
    assert "ref" in note.words
    remote = analyze_row(
        "Haier Split AC 1.5 Ton R/C Remote White",
        product_type="Air Conditioner",
        brand="Haier",
        breadcrumb="Electronics / Home appliances / Air Conditioners",
    )
    assert "c-remote" not in remote.words
    assert "remote" in remote.words


@pytest.mark.parametrize("dash", ["-", "\u2013", "\u2014", " - ", "\u00a0", " "])
def test_the_join_reads_every_way_the_sheet_writes_a_separator(dash: str) -> None:
    """One line, one key: `E-Star` and `E\u2013Star` must not vote as two names.

    Review finding.  The stock and Shape-A sheets both emit en/em dashes, and a separator class
    that lists only ASCII dashes leaves `E\u2013Star` as bare `star` -- exactly the name ruling 3
    exists to retire.  The spelling stays the row's own; only the key is canonical.
    """
    title = f"Haier E{dash}Star Freezer-On-Top Refrigerator 12 Cu Ft (HRF-346EPB)"
    analysis = analyze_row(
        title,
        product_type="Refrigerator",
        brand="Haier",
        breadcrumb="Electronics / Home appliances / Refrigerators / Freezer-On-Top",
    )
    assert "e-star" in analysis.words, repr(dash)
    assert "star" not in analysis.words, repr(dash)
    assert source_of(analysis, "e-star") in title, repr(dash)


def test_a_letter_is_never_absorbed_into_two_names_at_once() -> None:
    """Two initials in one row: the second word stands alone rather than sharing its letter.

    Review finding, from a fuzzed shape: `E-Star E-Glow` covered the piece `e` in two
    candidates, so the row's pieces stopped partitioning -- the one invariant the whole design
    rests on.  Ownership of a letter is decided once per row, and the first name it introduces
    keeps it.
    """
    analysis = analyze_row(
        "Haier E-Star E-Glow Refrigerator 12 Cu Ft (HRF-346EPB)",
        product_type="Refrigerator",
        brand="Haier",
        breadcrumb="Electronics / Home appliances / Refrigerators",
    )
    covered = [piece for candidate in analysis.candidates for piece in candidate.pieces]
    assert len(covered) == len(set(covered)), covered
    assert set(analysis.claimed) | set(covered) == set(analysis.title_words)
    assert "e-star" in analysis.words
    assert "glow" in analysis.words


def test_the_vote_keys_the_line_the_sheet_wrote_not_its_last_word() -> None:
    """What ruling 3 buys, on the real sheets, driven the way main.py drives it.

    `star` earned 14 Haier rows that all read `E-Star`; after the join `e-star` earns them and
    Haier stops earning `star`.  `f-stand` is three brands' shorthand for a floor stand, so the
    existing three-brand rule disqualifies the joined form too -- no new rule, no word list.
    """
    shape_a, stock = _real_rows()
    a_corpus = build_corpus(shape_a)
    assert a_corpus.is_proven("Haier", "e-star")
    assert not a_corpus.is_proven("Haier", "star")
    assert a_corpus.is_proven("Dawlance", "e-chrome")
    b_corpus = build_corpus(stock)
    assert "f-stand" in b_corpus.blacklisted


def test_joining_costs_the_stock_sheet_a_proof_it_had_only_by_faking_a_neighbour() -> None:
    """Pinned, not fixed: Dawlance `Chrome` stops earning on the stock sheet, and this says why.

    Before the join it earned on 16 rows with 12 of them code-adjacent, and the 4 free-standing
    rows were exactly the `E-CHROME` / `E CHROME` rows -- the word looked un-adjacent to a code
    only because the single letter in front of it was not one.  Once that letter belongs to the
    name, the pair sits after `9149WB` like everything else on a stock sheet, so neither
    `chrome` nor `e-chrome` clears the "stands free of a part number" bar here.

    Whether an initial-delimited label should still count as code-adjacent is a rule for the
    VOTE, not for the reading layer, and the stock corpus is not wired into main.py yet, so it
    is recorded as a decision for T4 rather than quietly answered here.
    """
    _, stock = _real_rows()
    corpus = build_corpus(stock)
    chrome = corpus.undecided["chrome"]
    assert chrome.code_adjacent == chrome.rows
    assert not corpus.is_proven("Dawlance", "chrome")
    assert not corpus.is_proven("Dawlance", "e-chrome")


def test_every_piece_of_every_real_row_is_claimed_or_covered_by_exactly_one_candidate() -> None:
    """The partition the whole design rests on, checked on all 1,620 real rows.

    A piece may be owned by a slot or sit inside one name candidate, never both and never
    nowhere -- that is what makes a dropped word a bug a test can see instead of a title that
    silently loses it.
    """
    shape_a, stock = _real_rows()
    for analysis in [*shape_a, *stock]:
        covered = [piece for candidate in analysis.candidates for piece in candidate.pieces]
        assert not set(analysis.claimed) & set(covered), analysis.title
        assert set(analysis.claimed) | set(covered) == set(analysis.title_words), analysis.title
        assert len(covered) == len(set(covered)), analysis.title
        keys = [candidate.key for candidate in analysis.candidates]
        assert len(keys) == len(set(keys)), analysis.title


def source_of(analysis: RowAnalysis, key: str) -> str:
    """The row's own spelling of one candidate, looked up by its vote key."""
    return {candidate.key: candidate.source for candidate in analysis.candidates}[key]


def _real_rows() -> tuple[list[RowAnalysis], list[RowAnalysis]]:
    """Both sheets read the way main.py reads them: product type and brand resolved first."""
    root = Path(__file__).resolve().parents[1]
    with (root / "data/input/Products.csv").open(encoding="utf-8-sig", newline="") as handle:
        shape_a = [
            analyze_row(
                (row.get("Title") or "").strip(),
                brand=(row.get("Brand") or "").strip(),
                product_type=_product_type(
                    (row.get("Brand") or "").strip(),
                    (row.get("Categories") or "").strip(),
                    f"{(row.get('Title') or '').strip()} {(row.get('Description') or '').strip()}",
                ),
                breadcrumb=(row.get("Categories") or "").strip(),
            )
            for row in csv.DictReader(handle)
        ]
    stock_path = (
        root
        / "tests/fixtures"
        / "Classified_Stock_Inventory_Master - KiaChahiye 12-10-2026 - Classified Stock.csv"
    )
    with stock_path.open(encoding="utf-8-sig", newline="") as handle:
        stock = [
            analyze_row(
                (row.get("Original_Title") or "").strip(),
                brand=(row.get("Brand") or "").strip(),
                product_type=_product_type(
                    (row.get("Brand") or "").strip(),
                    (row.get("Category") or "").strip(),
                    (row.get("Original_Title") or "").strip(),
                ),
                breadcrumb=(row.get("Category") or "").strip(),
            )
            for row in csv.DictReader(handle)
        ]
    return shape_a, stock


def _product_type(brand: str, breadcrumb: str, text: str) -> str:
    category = categories.resolve_category(breadcrumb, text, text)
    return categories.resolve_product_type(category, brand)[0]
