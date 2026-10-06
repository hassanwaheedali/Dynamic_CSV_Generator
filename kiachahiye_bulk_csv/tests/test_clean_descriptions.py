"""The Description cleaner: shape only, never content."""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from clean_descriptions import (  # noqa: E402
    clean_description,
    is_feature_run,
    split_bullet_list,
    split_feature_run,
)

ORIENT_RUN = (
    "COOL ONLY DC INVERTER ECO MODE (AMPERE LOCK) REFRIGERANT (R410) AUTO CLEAN "
    "STERILIZATION SOLAR COMPATIBLE 100% PURE COPPER 4D LONG AIR THROW GOLD FIN "
    "Orient Everest / Frost 12G Cooltron 1.0 TON DC Inverter (Cool Only, R410a, Ampere Lock)"
)
TCL_PROSE = (
    "Discover the TCL C8L SQD-Mini LED TV -the ultimate choice with 2040 precise "
    "dimming zones, up to 6,000nits HDR peak brightness, TCL AI and TSR AiPQ "
    "Processor deliver intelligent picture optimization for the ultimate home cinema."
)


def test_a_feature_run_is_recognised_by_its_capital_share() -> None:
    assert is_feature_run(ORIENT_RUN) is True
    assert is_feature_run(TCL_PROSE) is False, "ordinary prose is not a feature run"


def test_splitting_keeps_every_word_in_order() -> None:
    """The pieces joined back together are the original text, word for word."""
    pieces = split_feature_run(ORIENT_RUN, "Orient")
    assert len(pieces) > 8
    original = ORIENT_RUN.replace("/", " ").split()
    rebuilt = " ".join(pieces).replace("/", " ").split()
    assert rebuilt == original


def test_a_keyword_inside_brackets_never_starts_a_new_line() -> None:
    """'(Cool Only, R410a, Ampere Lock)' is one fact, not three lines."""
    pieces = split_feature_run(ORIENT_RUN, "Orient")
    assert "DC Inverter (Cool Only, R410a, Ampere Lock)" in pieces
    assert all(piece.strip() for piece in pieces)


def test_the_cleaner_turns_a_glued_blob_into_labelled_rows_and_bullets() -> None:
    blob = (
        "The EcoStar 12EM/DU is a 1.0 Ton inverter split air conditioner."
        "Brand\tEcoStar\nModel\t12EM/DU\nDescription\t\nReal 4 Star Product\n0.3 W Standby"
    )
    cleaned, stats = clean_description(blob, "EcoStar")
    assert cleaned.splitlines()[0] == (
        "The EcoStar 12EM/DU is a 1.0 Ton inverter split air conditioner."
    )
    assert "Brand: EcoStar" in cleaned
    assert "Model: 12EM/DU" in cleaned
    assert "• Real 4 Star Product" in cleaned
    assert "• 0.3 W Standby" in cleaned
    assert "Description" not in cleaned, "a bare section word carries no fact"
    assert stats["labels"] == 2


def test_encoding_damage_is_repaired_only_where_it_exists() -> None:
    cleaned, stats = clean_description("• Labyrinth PCB \u00e2\u20ac\u201d keeps dust out")
    assert "—" in cleaned
    assert stats["encoding"] == 1


def test_a_comma_list_inside_one_bullet_becomes_separate_bullets() -> None:
    """The source's own list markers decide the split -- nothing is guessed."""
    listed = (
        "Key features include 9kg wash capacity handles large family loads, "
        "Low-noise motor for quiet operation day and night, Full Plastic Body, Big Pulsator."
    )
    assert split_bullet_list(listed) == [
        "Key features include 9kg wash capacity handles large family loads",
        "Low-noise motor for quiet operation day and night",
        "Full Plastic Body",
        "Big Pulsator.",
    ]


def test_prose_that_merely_contains_commas_is_left_whole() -> None:
    """'...delivers richer colours, deeper contrast, and brighter visuals' is a
    sentence, not a list: splitting it would shatter the source's own prose."""
    prose = (
        "Quantum Dot technology delivers richer colors, deeper contrast, "
        "and brighter visuals that bring every scene to life."
    )
    assert split_bullet_list(prose) == [prose]
    labelled = "Sound Modes: Standard, music, movie, sports, vivid, news, user"
    assert split_bullet_list(labelled) == [labelled], "a labelled list is one spec value"
