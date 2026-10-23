"""Tests for T4: the corpus wired into the Title builder.

The reading layer (`series_corpus`) decides which words name a product line; the builder decides
what a shop reads.  These tests pin the seam between them: a proven name reaches the Title, and
nothing else about a Title moves.  Every case is a real row from the sheets, not a stand-in.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import main
from qc_report import QCFlagCollector
from series_corpus import (
    Corpus,
    RowAnalysis,
    analyze_row,
    build_corpus,
    pick_candidate,
)
from sku_handle import ModelExtraction
from title_builder import build_title, extract_series

ANCHOR_TITLE = "MIDEA ECO - WALL MOUNTED DC INVERTER MSAG2B-12HRDN1-QC0"
ANCHOR_DESCRIPTION = (
    "Midea 1 Ton DC Inverter Wall Mounted Split Air Conditioner MSAG2B-12HRDN1-QC0 "
    "with copper condenser and a 12 Year Compressor Warranty."
)
ANCHOR_BREADCRUMB = "Electronics / Home appliances / Air Conditioners / Split"


def printed(brand: str, row: RowAnalysis, corpus: Corpus) -> str:
    """The series name `build_title` would ship for this row, as the row wrote it."""
    chosen = pick_candidate(brand, row, corpus)
    return "" if chosen is None else chosen.source


def _write_input_csv(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    """A real sheet on disk, so `main.read_input` -- not a fixture stand-in -- is what gets tested."""
    path = tmp_path / "input.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _rows_for_report() -> list[object]:
    return [
        analyze_row(
            "Gree Pular Split Inverter Air Conditioner 1.5 Ton (GS-18PW)",
            brand="Gree",
            product_type="Air Conditioner",
            breadcrumb=ANCHOR_BREADCRUMB,
        ),
        analyze_row(
            # The SAME product stated twice, on purpose: if rows and products came out equal here,
            # the report could print either count swapped and no test would notice.
            "Gree Pular Split Inverter Air Conditioner 1.5 Ton Black (GS-18PW)",
            brand="Gree",
            product_type="Air Conditioner",
            breadcrumb=ANCHOR_BREADCRUMB,
        ),
        analyze_row(
            "Gree Pular Split Inverter Air Conditioner 2.0 Ton (GS-24PW)",
            brand="Gree",
            product_type="Air Conditioner",
            breadcrumb=ANCHOR_BREADCRUMB,
        ),
        analyze_row(
            "Gree Zeno Split Inverter Air Conditioner 1.0 Ton (GS-12ZN)",
            brand="Gree",
            product_type="Air Conditioner",
            breadcrumb=ANCHOR_BREADCRUMB,
        ),
    ]


def _midea_rows() -> list:
    return [
        analyze_row(
            ANCHOR_TITLE,
            brand="Midea",
            product_type="Air Conditioner",
            breadcrumb=ANCHOR_BREADCRUMB,
            description=ANCHOR_DESCRIPTION,
        )
    ]


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
    assert printed("Midea", analysis, corpus) == "ECO"
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


def test_the_title_records_how_strongly_its_name_was_believed() -> None:
    """A printed name says which rule carried it, so the report and QC can tell the two apart.

    `ECO` on a two-row Midea sheet is believed from ONE row standing right after the brand;
    `eComfort` on two Kenwood rows is stated by two products.  Both print, and a human reviewing
    the run needs to see that difference without recomputing the vote.
    """
    rescued, thin_corpus = _anchor()
    result = build_title(
        brand="Midea",
        extraction=ModelExtraction(code="MSAG2B-12HRDN1-QC0", source="title-code-token", confidence="high"),
        product_type="Air Conditioner",
        source_title=ANCHOR_TITLE,
        source_description=ANCHOR_DESCRIPTION,
        analysis=rescued,
        corpus=thin_corpus,
    )
    assert result.series_earned_by == "brand-position"

    kenwood = [
        analyze_row(
            "Kenwood eComfort Inverter Air Conditioner 1.5 Ton (KEC-1868S)",
            product_type="Air Conditioner",
            brand="Kenwood",
            breadcrumb=ANCHOR_BREADCRUMB,
        ),
        analyze_row(
            "Kenwood eComfort Inverter Air Conditioner 2.0 Ton (KEC-2468S)",
            product_type="Air Conditioner",
            brand="Kenwood",
            breadcrumb=ANCHOR_BREADCRUMB,
        ),
    ]
    full_corpus = build_corpus(kenwood)
    stated = build_title(
        brand="Kenwood",
        extraction=ModelExtraction(code="KEC-1868S", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title=kenwood[0].title,
        source_description="",
        analysis=kenwood[0],
        corpus=full_corpus,
    )
    assert stated.series_earned_by == "siblings"


def test_a_name_believed_from_one_row_is_flagged_for_a_human(pipeline: Pipeline) -> None:
    """The thin-sheet rescue prints a Title; it must also raise a row a human can confirm.

    Two products stating a line is evidence nobody needs to re-check.  One row putting a word right
    after its brand is the vote's weakest answer -- and today it prints silently, so a lucky guess
    would never surface in the QC report.
    """
    rescued = pipeline([_sheet(ANCHOR_TITLE, ANCHOR_DESCRIPTION, "Midea")])
    assert any(
        flag.category == "series_believed_from_one_row" for flag in rescued["flags"].flags
    ), rescued["flags"].flags

    stated = pipeline(
        [
            _sheet(
                "Kenwood eComfort Inverter Air Conditioner 1.5 Ton (KEC-1868S)",
                "Kenwood 1.5 Ton DC Inverter Split Air Conditioner.",
                "Kenwood",
            ),
            _sheet(
                "Kenwood eComfort Inverter Air Conditioner 2.0 Ton (KEC-2468S)",
                "Kenwood 2 Ton DC Inverter Split Air Conditioner.",
                "Kenwood",
            ),
        ]
    )
    assert not any(
        flag.category == "series_believed_from_one_row" for flag in stated["flags"].flags
    )


def test_the_run_reports_what_it_proved_per_brand() -> None:
    """A verdict you cannot read is a verdict you cannot trust, so the run prints its own answers.

    Per brand: the names it proved, how many rows and products stated each, and a mark on the ones
    believed from a single row.  The report is built from the recorded evidence, so it can never
    disagree with the vote that printed the Titles -- and it prints the folded key the vote speaks
    in, not an invented shop spelling the run never stored.
    """
    lines = main.corpus_report_lines(build_corpus(_rows_for_report()))
    body = "\n".join(lines)
    # The counts are asserted exactly, and rows differ from products in the fixture, so a report
    # that mixed the two up or dropped one of them fails here instead of reading plausibly.
    assert "pular [3 rows / 2 products]" in body
    assert "needs a human: zeno [1 row / 1 product]" in body
    assert "undecided words" in body

    rescued = main.corpus_report_lines(build_corpus(_midea_rows()))
    assert any("needs a human" in line and "eco [1 row / 1 product]" in line for line in rescued)


def test_a_name_the_dedupe_swallowed_is_not_reported_as_printed() -> None:
    """`Icon` is Orient's believed name AND a word of this row's model code, so the slot empties.

    QC must not ask a human to confirm a name the shelf never read.  A substring test on the finished
    Title hits here (the code still carries the word), which is exactly the false flag this pins out.
    """
    analysis = analyze_row(
        "Orient Icon 3 Taps Water Dispenser Black",
        brand="Orient",
        product_type="Water Dispenser",
        breadcrumb="Electronics / Home appliances / Water Dispensers",
    )
    result = build_title(
        brand="Orient",
        extraction=ModelExtraction(
            code="Icon 3 Taps Water Dispenser", source="description-model-line", confidence="high"
        ),
        product_type="Water Dispenser",
        source_title="Orient Icon 3 Taps Water Dispenser Black",
        source_description="Orient 3 Taps Water Dispenser Black with a 3 Year Warranty.",
        analysis=analysis,
        corpus=build_corpus([analysis]),
    )
    assert "icon" in result.title.lower()  # the letters are on the shelf...
    assert result.series_name == ""  # ...but not as the series name
    assert result.series_earned_by == ""


def test_the_shipped_file_carries_the_verdict_block(tmp_path: Path, capsys) -> None:
    """`main()` must hand the run's own verdict to the summary, and print it, on a real sheet.

    Unit-testing `corpus_report_lines` and calling `print_summary` by hand both leave the actual
    wiring unguarded: drop the argument and the console quietly says `no corpus was read`, with
    every test still green.  This runs the real entry point end to end.
    """
    path = _write_input_csv(
        tmp_path,
        [
            _sheet(
                "Gree Pular Split Inverter Air Conditioner 1.5 Ton (GS-18PW)",
                "Gree 1.5 Ton DC Inverter Split Air Conditioner with a 10 Year Compressor Warranty.",
                "Gree",
            ),
            _sheet(
                "Gree Pular Split Inverter Air Conditioner 2.0 Ton (GS-24PW)",
                "Gree 2 Ton DC Inverter Split Air Conditioner with a 10 Year Compressor Warranty.",
                "Gree",
            ),
        ],
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    main.main(
        [
            "--input", str(path),
            "--digi", str(out_dir / "digi.csv"),
            "--alfa", str(out_dir / "alfa.csv"),
            "--qc", str(out_dir / "qc.csv"),
            "--sample-titles", str(out_dir / "titles.csv"),
        ]
    )
    printed_out = capsys.readouterr().out
    assert "SERIES NAMES THIS RUN PROVED" in printed_out
    assert "no corpus was read" not in printed_out
    assert "pular" in printed_out


def test_a_name_cut_off_by_the_length_limit_is_not_reported_as_printed() -> None:
    """The limit runs after the slot is assembled, so a cut name is not a name the shop sees.

    A Title over `TITLE_MAX` is trimmed at the end, and when the trim takes the series slot with it
    the row still *proved* the name -- it just never reaches the shelf.  Recording it anyway would
    send a reviewer to confirm a name that appears nowhere in the file they are checking.
    """
    row = analyze_row(
        "Orient Zephyr Split Air Conditioner 1.5 Ton (ACA-1500)",
        brand="Orient",
        product_type="Air Conditioner",
        breadcrumb=ANCHOR_BREADCRUMB,
    )
    result = build_title(
        brand="Orient",
        # A part number long enough that the assembled Title exceeds the limit and is cut back.
        extraction=ModelExtraction(
            code="ACA-" + "X" * 250, source="title-parenthetical", confidence="high"
        ),
        product_type="Air Conditioner",
        source_title=row.title,
        source_description="Orient 1.5 Ton DC Inverter Split Air Conditioner.",
        warranty="",
        analysis=row,
        corpus=build_corpus([row]),
    )
    assert "Zephyr" not in result.title
    assert result.series_name == ""
    assert result.series_earned_by == ""


def test_a_run_that_proved_nothing_says_so() -> None:
    """Silence is a result too, and the report has to state it instead of printing nothing."""
    assert any("proved no name" in line for line in main.corpus_report_lines(build_corpus([])))


def test_a_half_printed_name_is_not_reported_as_the_name() -> None:
    """`Glory Pro` with only `Glory` left in the slot is NOT the name `Glory Pro`.

    The model code `GL-PRO-15` owns the word `Pro` as a token of its own, so the dedupe drops it
    from the series slot and only half the voted name prints.  A guard that asked `any` instead of
    `all` would report the full name here, and the two real rows this mirrors (Kenwood
    `eLuxury Pro`, whose code swallows `Pro`) would get a QC line asking someone to confirm a label
    the shelf never carried.
    """
    rows = [
        # One row states the name with no part number beside it, which is what lets the pair earn
        # its proof; the second row is a different product of the same line.
        analyze_row(
            "Kenwood Glory Pro Inverter Air Conditioner 1.5 Ton",
            brand="Kenwood",
            product_type="Air Conditioner",
            breadcrumb=ANCHOR_BREADCRUMB,
        ),
        analyze_row(
            "Kenwood Glory Pro Inverter Air Conditioner 2.0 Ton (GL-20)",
            brand="Kenwood",
            product_type="Air Conditioner",
            breadcrumb=ANCHOR_BREADCRUMB,
        ),
    ]
    corpus = build_corpus(rows)
    assert printed("Kenwood", rows[0], corpus) == "Glory Pro"
    result = build_title(
        brand="Kenwood",
        extraction=ModelExtraction(code="GL-PRO-15", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title=rows[0].title,
        source_description="Kenwood 1.5 Ton DC Inverter Split Air Conditioner.",
        analysis=rows[0],
        corpus=corpus,
    )
    assert " Glory" in result.title
    assert "Glory Pro" not in result.title
    assert result.series_name == ""


def test_the_flag_names_only_the_word_the_vote_believed(pipeline: Pipeline) -> None:
    """The reviewer is asked to confirm a name, not the feature word sitting beside it.

    `Blaze Google` is what the whole series slot reads; `Blaze` is what the vote believed.  Showing
    the composite would send a human to check a phrase the run never proved.
    """
    rows = [
        _sheet(
            "PEL Blaze Inverter Water Dispenser White (PWD-316)",
            "PEL water dispenser with Google feature and a 1 Year Warranty.",
            "PEL",
        )
    ]
    run = pipeline(rows)
    flagged = [
        flag for flag in run["flags"].flags if flag.category == "series_believed_from_one_row"
    ]
    assert flagged, "this row is the single-row rescue path"
    for flag in flagged:
        assert "Blaze" in flag.message
        assert "Google" not in flag.message


def test_run_refuses_a_reading_voted_from_another_sheet(tmp_path: Path) -> None:
    """A corpus voted from a different sheet would print its brands' names here, silently.

    So the reading carries how many rows it was voted from, and `run()` refuses a pair whose counts
    do not match the rows in front of it.  The Titles still render either way, which is exactly why
    this has to be a raised error and not something a reviewer catches by glancing at the file.
    """
    here = _write_input_csv(
        tmp_path,
        [
            _sheet(ANCHOR_TITLE, ANCHOR_DESCRIPTION, "Midea"),
            _sheet(
                "Kenwood eComfort Inverter Air Conditioner 1.5 Ton (KEC-1868S)",
                "Kenwood 1.5 Ton DC Inverter Split Air Conditioner.",
                "Kenwood",
            ),
        ],
    )
    rows = main.read_input(here)
    analyses, _own = main.read_rows(rows)
    foreign = build_corpus([_midea_rows()[0]])  # voted from ONE row
    with pytest.raises(ValueError, match="read the sheet and vote it in one call"):
        main.run(rows, QCFlagCollector(), (analyses, foreign))


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
    assert printed("Kenwood", kenwood, corpus) == "eComfort"


# --------------------------------------------------------------------------- #
# T4a -- the whole run, through main.py
# --------------------------------------------------------------------------- #
_AC = "Electronics / Home appliances / Air Conditioners / Split"
_MICROWAVE = "Electronics / Kitchen appliances / Microwaves"
_WASHING = "Electronics / Home appliances / Washing machine"


def _sheet(title: str, description: str, brand: str, category: str = _AC) -> dict[str, str]:
    return {
        "Title": title,
        "Description": description,
        "Sell Price": "54999",
        "Original Price": "59999",
        "Categories": category,
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


def test_a_subtype_line_reaches_the_shipped_title_through_the_pipeline(pipeline: Pipeline) -> None:
    """His line, his words, in the sub-type position -- end to end, not inside one function.

    The Description also says `Split`, and nothing disagrees with it: the Title leaves the mounting
    question empty, so one column answering it is the row answering it.  `Heat & Cool` is a DIFFERENT
    question -- cooling and heating -- so the line seats its own group and `Split` stays standing
    (owner ruling, 2026-10-23: pick the value when only one column states it).  Wiping it would have
    printed `Heat & Cool Air Conditioner` and emptied `Attribute_Air Conditioner Type`, which DigiMall
    matches out of this Title -- and a line the shop sells as a Split heat-pump AC is both facts.
    """
    records = pipeline(
        [
            _sheet(
                "Haier Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
                "Haier 1.5 Ton DC Inverter Split Air Conditioner, model HSU-19HFPCAA.\n"
                "SubType: Heat & Cool",
                "Haier",
            )
        ]
    )["records"]
    record = records[0]
    assert record.subtype_from == "label"
    assert " Split Heat & Cool Air Conditioner" in record.title
    assert record.title.count("Heat & Cool") == 1
    # The word the line did NOT overrule still may not be resold behind the model code as a series.
    assert " - HSU-19HFPCAA Split" not in record.title


def test_a_subtype_line_that_adds_no_word_is_flagged(pipeline: Pipeline) -> None:
    """`SubType: Air Conditioner` names the category, not a sub-type -- and he must be told.

    He checks these lines by hand, so a line that silently changes nothing is the one failure mode
    this feature cannot have.
    """
    run = pipeline(
        [
            _sheet(
                "Haier Split Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
                "Haier 1.5 Ton DC Inverter Split Air Conditioner, model HSU-19HFPCAA.\n"
                "SubType: Air Conditioner",
                "Haier",
            )
        ]
    )
    flagged = [f for f in run["flags"].flags if f.category == "subtype_line_added_nothing"]
    assert flagged, "a line that added no word has to reach the QC report"
    assert "Air Conditioner" in flagged[0].message
    assert run["records"][0].subtype_from != "label"


def test_a_row_claiming_two_machines_ships_neither_and_is_sent_to_the_owner(
    pipeline: Pipeline,
) -> None:
    """Real row 290: the Title sells a `Cassette`, the vendor sentence says `split`.

    Nothing in the letters says which is the machine -- `... is a X Ton DC Inverter split air
    conditioner` is template text standing in 204 Descriptions on this sheet, six of them cassettes --
    so the builder must not pick one: a wrong value in `Attribute_Air Conditioner Type` ships a
    product the shop never sold.  The slot stays empty and the row reaches the QC report naming both
    candidates and the one line that settles it.
    """
    run = pipeline(
        [
            _sheet(
                "Haier 4 Way Cassette DC Inverter Air Conditioner 1.5 Ton White (HBU-18HE)",
                "The Haier HBU-18HE/DC-DC Inverter Cassette Type Air Conditioner is a 1.5 Ton DC "
                "Inverter split air conditioner, in White.",
                "Haier",
            )
        ]
    )
    record = run["records"][0]
    assert record.subtype_from == ""
    assert "Cassette" not in record.title
    assert "Split" not in record.title
    flagged = [f for f in run["flags"].flags if f.category == "title_description_conflict"]
    assert len(flagged) == 1
    assert "Cassette" in flagged[0].message and "Split" in flagged[0].message
    assert "SubType:" in flagged[0].message
    # The cell goes with the slot: DigiMall's matcher would otherwise read his Description next and
    # take `split` out of the vendor sentence -- a wrong value in a closed list, shipped under a Title
    # that refused to say it.
    assert record.attributes.get("Attribute_Air Conditioner Type", "") == ""


def test_a_row_that_gains_a_subtype_word_sheds_it_from_the_seo_title_not_its_warranty(
    pipeline: Pipeline,
) -> None:
    """A longer Title must not buy its sub-type with the search title's tail.

    The SEO Title is `Title + " Price in Pakistan"` cut to 90 characters, and it already knows to
    shed its own optional tokens first.  The new `[Subtype]` word was not on that list, so an
    over-budget row cut the last word instead -- `Warranty` on 116 real rows.  The shop Title keeps
    the sub-type; the search title gives up a token instead of eating its own tail.
    """
    run = pipeline(
        [
            {
                "Title": "Dawlance Inverter Deep Freezer 14 Cu Ft Silver (VF-1035-GD-INV)",
                "Description": (
                    "A Dawlance 14 cu ft vertical deep freezer with a 12 Year Compressor Warranty."
                ),
                "Sell Price": "66999",
                "Original Price": "69999",
                "Categories": "Electronics / Home appliances / Deep Freezers",
                "Brand": "Dawlance",
                "Image": "https://example.test/a.jpg",
            }
        ]
    )
    record, seo = run["records"][0], run["digi"][0]["SEO Title"]
    assert record.subtype_from == "list"
    assert " Vertical " in record.title
    assert len(seo) <= 90
    assert "Warranty" in seo, f"the search title cut its tail instead of an added word: {seo!r}"


def test_a_name_the_vote_proves_is_not_stranded_by_the_neighbour_rule(pipeline: Pipeline) -> None:
    """Row 166 of the sheet: the vote proved `Panini`, so the neighbour rule keeps its hands off it.

    `Panini Solo` is the phrase the shop wrote, `Solo` is the type word that moved into `[Subtype]`,
    and `Panini` is the word left beside it -- a stranded fragment under that rule.  It survives
    because this row states it in both columns, which is the evidence the corpus votes on, not
    because a table says the word is allowed.
    """
    records = pipeline(
        [
            _sheet(
                "Orient Panini Solo Microwave Oven 20 Ltr Black",
                "The Orient Panini 20M is a 20 L solo microwave oven in Black.\n\n"
                "Key Specifications:\n• Solo Function: Yes\n• Mechanical Control: Yes",
                "Orient",
                _MICROWAVE,
            )
        ]
    )["records"]
    record = records[0]
    assert " Solo Microwave Oven" in record.title
    assert record.series_token == "Panini"
    assert "Panini" in record.title


def test_a_row_that_states_no_type_word_anywhere_stays_empty(pipeline: Pipeline) -> None:
    """Silence is still the safe answer: no line, no type word, no invented sub-type.

    `Front-Load` in a model code is not a type statement -- the row says `HSU-19HFPCAA` and nothing
    about what kind of unit it is.
    """
    record = pipeline(
        [
            _sheet(
                "Haier Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
                "Haier 1.5 Ton DC Inverter Air Conditioner, model HSU-19HFPCAA with a copper condenser.",
                "Haier",
            )
        ]
    )["records"][0]
    assert record.subtype_from == ""
    assert record.title.count("Inverter") == 1


def test_a_subtype_word_in_the_prose_is_reported_not_guessed_about(pipeline: Pipeline) -> None:
    """The row says `Sub-type` without a labelled line, so the Title cannot use it -- and he hears.

    Reading that prose would be guessing where the sheet is silent, so the safe output stands and
    the QC row names the fix: write it as its own labelled line.
    """
    run = pipeline(
        [
            _sheet(
                "Haier Split Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
                "Haier 1.5 Ton DC Inverter Split Air Conditioner, model HSU-19HFPCAA. "
                "Its sub type is heat and cool.",
                "Haier",
            )
        ]
    )
    flagged = [f for f in run["flags"].flags if f.category == "subtype_line_added_nothing"]
    assert len(flagged) == 1
    assert "own line" in flagged[0].message


def test_a_type_the_row_already_names_is_not_spelled_a_second_time(pipeline: Pipeline) -> None:
    """`Top-Load Automatic` beside the `Top Load` the Title already prints says nothing new.

    Real rows 71 and 72 of Products.csv state their type with hyphens, the sub-type list reads it
    as `Fully Automatic Top Load`, and the stranded-class-word rung used to append the platform's
    own phrase on top of it -- shipping `... Fully Automatic Top Load Top-Load Automatic Washing
    Machine` for a shop to untangle.  The rung is refused by the same one-word rule that stops
    `Mini LED LED TV`; only the words the Title prints, and not just the seat, are put in front of
    it.
    """
    record = pipeline(
        [
            _sheet(
                "Dawlance Top-Load Automatic Washing Machine (DWT-1165PL)",
                "The Dawlance DWT-1165PL is a Green top load fully automatic washing machine.",
                "Dawlance",
                _WASHING,
            )
        ]
    )["records"][0]
    assert record.title.count("Top") == 1
    assert "Top-Load Automatic" not in record.title


def _orient(title: str) -> dict[str, str]:
    return {
        "Title": title,
        "Description": title,
        "Sell Price": "54999",
        "Original Price": "59999",
        "Categories": "Electronics / Home appliances / Refrigerators",
        "Brand": "Orient",
        "Image": "https://example.test/a.jpg",
    }


def test_the_slot_the_row_wrote_replaces_the_vote_instead_of_stacking_with_it(
    pipeline: Pipeline,
) -> None:
    """One seat, one name: `Marvel 200` is a Marvel, and the run's `Blaze` stays out of the Title.

    Both words are proven for Orient on this sheet, so the old seam printed `Marvel Blaze` -- the
    row's own line name followed by whatever else the run believed.  The clause the sheet wrote its
    code into is the row's own answer, so it REPLACES the vote; the vote still speaks (the test above
    this one) where that clause is silent.
    """
    records = pipeline(
        [
            _orient(
                "Orient 7 Cu Ft Blaze Purple Glass Door Direct Cool Non-Inverter Refrigerator "
                "- Marvel 200 - 3 Years Compressor Warranty"
            ),
            _orient(
                "Orient 12 Cu Ft Blaze Purple Glass Door Direct Cool Non-Inverter Refrigerator "
                "- Marvel 330 - 3 Years Compressor Warranty"
            ),
        ]
    )["records"]
    assert [r.series_token for r in records] == ["Marvel", "Marvel"]
    for record in records:
        assert "Blaze" not in record.title
