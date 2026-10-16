"""Tests for T4: the corpus wired into the Title builder.

The reading layer (`series_corpus`) decides which words name a product line; the builder decides
what a shop reads.  These tests pin the seam between them: a proven name reaches the Title, and
nothing else about a Title moves.  Every case is a real row from the sheets, not a stand-in.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from series_corpus import Corpus, analyze_row, build_corpus, pick_series
from sku_handle import ModelExtraction
from title_builder import build_title, extract_series

ANCHOR_TITLE = "MIDEA ECO - WALL MOUNTED DC INVERTER MSAG2B-12HRDN1-QC0"
ANCHOR_DESCRIPTION = (
    "Midea 1 Ton DC Inverter Wall Mounted Split Air Conditioner MSAG2B-12HRDN1-QC0 "
    "with copper condenser and a 12 Year Compressor Warranty."
)
ANCHOR_BREADCRUMB = "Electronics / Home appliances / Air Conditioners / Split"


def _anchor() -> tuple[object, Corpus]:
    analysis = analyze_row(
        ANCHOR_TITLE,
        product_type="Air Conditioner",
        brand="Midea",
        breadcrumb=ANCHOR_BREADCRUMB,
        description=ANCHOR_DESCRIPTION,
        model="MSAG2B-12HRDN1-QC0",
        capacity="1 Ton",
        color="White",
        inverter="Inverter",
    )
    return analysis, build_corpus([analysis])


def test_the_wired_builder_ships_the_series_the_corpus_proves() -> None:
    """The row this project was opened for: `ECO` reaches the Title, from the corpus, not a list.

    `MIDEA ECO - WALL MOUNTED DC INVERTER ...` shipped as
    `Midea 1 Ton White Inverter Air Conditioner - MSAG2B-12HRDN1-QC0 - 12 Year Compressor Warranty`,
    which sells the mounting instead of the line.

    Recorded honestly: the old curated guesser reaches `ECO` on this row too, so the Title text does
    not by itself prove the corpus was consulted.  What is pinned here is the claim that matters --
    the name is EARNED by the vote from the sheet's own letters, not from `SERIES_WORDS`.
    """
    analysis, corpus = _anchor()
    assert pick_series("Midea", analysis, corpus) == "ECO"
    assert corpus.is_proven("Midea", "eco")
    result = build_title(
        brand="Midea",
        extraction=ModelExtraction(code="MSAG2B-12HRDN1-QC0", source="title-code-token", confidence="high"),
        product_type="Air Conditioner",
        source_title=ANCHOR_TITLE,
        source_description=ANCHOR_DESCRIPTION,
        analysis=analysis,
        corpus=corpus,
    )
    assert " ECO" in result.title


def test_a_corpus_that_proved_nothing_leaves_the_title_exactly_as_it_is_today() -> None:
    """Silence is the corpus's safe answer, and it must never delete a name the builder already had.

    A thin or unrelated sheet therefore changes no Title: the fallback is the current path, so
    wiring the corpus in cannot make a shipped Title shorter or emptier.
    """
    without = build_title(
        brand="Midea",
        extraction=ModelExtraction(code="MSAG2B-12HRDN1-QC0", source="title-code-token", confidence="high"),
        product_type="Air Conditioner",
        source_title=ANCHOR_TITLE,
        source_description=ANCHOR_DESCRIPTION,
    )
    analysis, _proven = _anchor()
    empty: Corpus = build_corpus([])
    with_empty_corpus = build_title(
        brand="Midea",
        extraction=ModelExtraction(code="MSAG2B-12HRDN1-QC0", source="title-code-token", confidence="high"),
        product_type="Air Conditioner",
        source_title=ANCHOR_TITLE,
        source_description=ANCHOR_DESCRIPTION,
        analysis=analysis,
        corpus=empty,
    )
    assert with_empty_corpus.title == without.title
    assert with_empty_corpus.strategy == without.strategy


def test_the_name_is_rendered_the_way_the_row_spells_it() -> None:
    """`eComfort` and `eSmart` are the shop's words, so the Title shows them, not `Ecomfort`.

    The reading layer folds case to vote; folding must never leak into what a customer reads.
    """
    kenwood = analyze_row(
        "Kenwood eComfort Inverter Air Conditioner 1.5 Ton (KEC-1868S)",
        product_type="Air Conditioner",
        brand="Kenwood",
        breadcrumb=ANCHOR_BREADCRUMB,
        description="The Kenwood 1.5 Ton eComfort Series Split Air Conditioner.",
    )
    corpus = build_corpus(
        [
            kenwood,
            analyze_row(
                "Kenwood eComfort Inverter Air Conditioner 2.0 Ton (KEC-2468S)",
                product_type="Air Conditioner",
                brand="Kenwood",
                breadcrumb=ANCHOR_BREADCRUMB,
                description="The Kenwood 2 Ton eComfort Series Split Air Conditioner.",
            ),
        ]
    )
    assert pick_series("Kenwood", kenwood, corpus) == "eComfort"


# --------------------------------------------------------------------------- #
# T4a -- the whole run, through main.py
# --------------------------------------------------------------------------- #
_AC = "Electronics / Home appliances / Air Conditioners / Split"


def _sheet(title: str, description: str, brand: str) -> dict[str, str]:
    return {
        "Title": title,
        "Description": description,
        "Sell Price": "54999",
        "Original Price": "59999",
        "Categories": _AC,
        "Brand": brand,
        "Image": "https://example.test/a.jpg",
    }


#: The repo's own end-to-end fixture: writes a tiny sheet and runs `main.run` over it.
Pipeline = Callable[[list[dict[str, str]]], dict[str, Any]]


def test_the_pipeline_ships_the_name_the_run_proved(pipeline: Pipeline) -> None:
    """The anchor bug, closed at the level a shop reads: the shipped Title carries `ECO`.

    `build_title` was already shown to do this; what this pins is that `run()` reads every row
    once, votes over the whole sheet, and hands THIS row's reading and the run's verdict down to
    the builder -- not one builder call inside a test.

    Honest note: on this particular row the old curated guesser also reaches `ECO`, so the Title
    text alone does not prove the corpus was consulted.  The two rows that follow cannot be named
    any other way, and they are what actually pins the wiring.
    """
    records = pipeline(
        [
            _sheet(
                "MIDEA ECO - WALL MOUNTED DC INVERTER MSAG2B-12HRDN1-QC0",
                ANCHOR_DESCRIPTION,
                "Midea",
            )
        ]
    )["records"]
    assert [r.series_token for r in records] == ["ECO"]
    assert " ECO -" in records[0].title


def test_the_name_reaches_the_title_whole_letters_including_its_head(pipeline: Pipeline) -> None:
    """`E Luxury Pro` is the name; a Title that reads `Luxury Pro` sells somebody else's line.

    Two Kenwood rows that both spell the name prove it, and the assembled Title must carry all
    three words.  It shipped `KEL-2470S Luxury Pro` because the rebuild drops a feature word that
    it finds inside a word already printed -- and `E` is inside `Kenwood`.
    """
    records = pipeline(
        [
            _sheet(
                "Kenwood E Luxury Pro Inverter Air Conditioner 2.0 Ton (KEL-2470S)",
                "Kenwood 2 Ton DC Inverter Split Air Conditioner with a 10 Year Compressor Warranty.",
                "Kenwood",
            ),
            _sheet(
                "Kenwood E Luxury Pro Inverter Air Conditioner 1.5 Ton (KEL-1870S)",
                "Kenwood 1.5 Ton DC Inverter Split Air Conditioner with a 10 Year Compressor Warranty.",
                "Kenwood",
            ),
        ]
    )["records"]
    assert [r.series_token for r in records] == ["E Luxury Pro", "E Luxury Pro"]
    for record in records:
        assert " E Luxury Pro" in record.title
        # The name could not have come from the old guesser: on this very row it returns `Pro`.
        # This is what makes the assertion a test of the wiring and not of a coincidence.
        assert extract_series(
            f"{record.source.title}\n{record.source.description}"
        ) != record.series_token


def test_a_type_the_old_guesser_sold_as_a_series_stays_in_the_title(pipeline: Pipeline) -> None:
    """Replacing a fake series must not delete the row's TYPE -- a Type cell is read from the Title.

    `Dawlance AVANTE+ Freezer-On-Top Refrigerator ...` used to ship with `Freezer-On-Top` in the
    series slot because that is what the old guesser found there.  Once the corpus names the real
    line, the type word has nowhere to go and DigiMall's `Attribute_Refrigerator Type` falls from
    `Freezer-On-Top` to empty.  So the word the platform's own tables call a product type moves to
    the formula's `[Subtype]` slot instead of being dropped.
    """
    records = pipeline(
        [
            _fridge(
                "Dawlance AVANTE+ Freezer-On-Top Refrigerator 16 Cu Ft Luxe Brown (9193-WB)",
                "16",
            ),
            _fridge(
                "Dawlance AVANTE+ Freezer-On-Top Refrigerator 14 Cu Ft White (9173-WB)",
                "14",
            ),
        ]
    )["records"]
    for record in records:
        assert record.series_token == "AVANTE+"
        assert " Freezer-On-Top Refrigerator" in record.title


def _fridge(title: str, capacity: str) -> dict[str, str]:
    return {
        "Title": title,
        "Description": f"Dawlance {capacity} Cu Ft refrigerator with a 12 Year Compressor Warranty.",
        "Sell Price": "74999",
        "Original Price": "79999",
        "Categories": "Electronics / Home appliances / Refrigerators / Freezer-On-Top",
        "Brand": "Dawlance",
        "Image": "https://example.test/a.jpg",
    }


def test_a_row_the_vote_stays_silent_on_ships_exactly_the_unwired_title(pipeline: Pipeline) -> None:
    """A nameless row must not merely look fine -- it must be byte-identical to the old path.

    This is the invariant that makes the wiring safe to land on 752 rows at once: every Title the
    corpus has nothing to say about is the Title `title_builder` produced before it existed.
    """
    records = pipeline(
        [
            _sheet(
                "HAIER HSU 19HFPCAA 013W USDC (G) INVERTER SPLIT AIR CONDITIONER",
                "Haier 1.5 Ton DC Inverter Split Air Conditioner, model HSU-19HFPCAA.",
                "Haier",
            )
        ]
    )["records"]
    record = records[0]
    unwired = build_title(
        record.brand.raw,
        ModelExtraction(record.model, record.model_source, record.model_confidence),
        record.product_type,
        record.source.title,
        record.source.description,
    )
    assert record.title == unwired.title
