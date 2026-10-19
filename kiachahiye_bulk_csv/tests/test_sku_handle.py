"""Tests for `sku_handle` -- the reader that decides what a row's size is.

`parse_capacity` is the only place the sheet's numbers become the `[Capacity]` token, so the rules
it owns are pinned here directly, at the reader, and not only through a Title.
"""

from sku_handle import (
    ModelExtraction,
    parse_capacity,
    resolve_capacity,
    tonnage_from_model_code,
)


def test_an_air_conditioner_reads_its_own_tonnage_not_a_prose_weight_bullet() -> None:
    """Row 257: `Indoor Unit Weight (kg) 13 kg` sits in running text, not on a `Weight:` line."""
    text = (
        "Dawlance Frost 30 Inverter Split Air Conditioner 1.5 Ton White (Cool Only)\n"
        "The Dawlance Frost Inverter 30 is a 1.5 Ton DC Inverter split air conditioner."
        "Dimensions & Weight Indoor Unit Weight (kg) 13 kg Outdoor Unit Weight (kg) 30.5 kg"
    )
    assert parse_capacity(text, "Air Conditioner") == "1.5 Ton"


def test_a_microwave_is_sold_in_litres_and_never_in_the_weight_of_its_carton() -> None:
    """"use ltrs not ton or kg in microwave" -- the unit is the product's, not the box's."""
    assert (
        parse_capacity("Haier 20 Ltr Grill Microwave Oven\nNet Weight: 11 kg", "Microwave Oven")
        == "20 Ltr"
    )
    assert parse_capacity("A microwave oven.\nNet Weight: 11 kg", "Microwave Oven") == ""


def test_a_category_nobody_has_listed_is_read_exactly_as_before() -> None:
    """The gate fails open: an unlisted category never loses its size to this table.

    `Air Fryer` is not in `CAPACITY_UNITS`, so its litres are still read -- a product nobody has
    measured yet cannot be silently emptied by a rule written for air conditioners.
    """
    assert parse_capacity(" PEL 5.5 Ltr Air Fryer Black", "Air Fryer") == "5.5 Ltr"


def test_a_ups_that_only_names_the_machines_it_runs_states_no_size() -> None:
    """Row 398: `Capacity: Works with 1 Ton and 1.5 Ton UPS-Enabled Haier DC Inverter`."""
    text = (
        "Haier Module DC Inverter AC UPS Device White\n"
        "Key Specifications:\n• Capacity: Works with 1 Ton and 1.5 Ton UPS-Enabled Haier DC Inverter"
    )
    assert parse_capacity(text, "UPS") == ""


# --------------------------------------------------------------------------- #
# The model number's own claim -- read only when the row says nothing
# --------------------------------------------------------------------------- #
def _code(code: str) -> ModelExtraction:
    """A resolved model number, as the reader hands it over: high confidence, from the Title."""
    return ModelExtraction(code=code, source="title-code-token", confidence="high")


def test_a_dawlance_code_that_never_writes_a_ton_still_says_the_size() -> None:
    """His example, verbatim from the benchmark corpus: `20FROST INVERTER-DAWLANCE 20FROST INVERTER`.

    The digits in an air conditioner's code are its size, and they are NOT a ton-x-10 rule -- Dawlance
    `20` is 1.25 Ton, and the universal table says nothing about a `20` at all.
    """
    assert tonnage_from_model_code("dawlance", "20FROST") == "1.25 Ton"
    title = "20FROST INVERTER-DAWLANCE 20FROST INVERTER"
    assert resolve_capacity(title, "Air Conditioner", "dawlance", _code("20FROST")) == "1.25 Ton"


def test_the_tonnage_written_with_a_dash_is_still_read_from_the_title() -> None:
    """Row 452: `Gree Floor Standing Air Conditioner 4.0-Ton White (GF-48TF)`.

    The size is written with a hyphen, so the pattern skipped it and read the spec bullet instead --
    and this row's own bullet contradicts itself (`T Fresh Cool Only 2 TON: T Fresh Cool Only 4 TON`).
    The Title is the sentence the buyer sees, and `48` is 4 Ton, so the Title is what ships.
    """
    title = "Gree Floor Standing Air Conditioner 4.0-Ton White (GF-48TF)"
    description = (
        "The Gree GF-48TF is a split air conditioner.\n\nKey Specifications:\n"
        "• T Fresh Cool Only 2 TON: T Fresh Cool Only 4 TON"
    )
    assert parse_capacity(f"{title}\n{description}", "Air Conditioner") == "4 Ton"


def test_the_words_the_row_states_always_beat_what_a_model_number_implies() -> None:
    """The table is a reading of digits; the row is the product's own words, and it wins.

    Row 452's shape on purpose: a code the universal table reads as 4 Ton on a row selling itself
    as 1.5 Ton.  The rung is never consulted when the row has already spoken.
    """
    text = "Gree Floor Standing Air Conditioner 1.5 Ton White (GF-48TF)"
    assert resolve_capacity(text, "Air Conditioner", "gree", _code("GF-48TF")) == "1.5 Ton"


def test_a_brand_with_its_own_table_is_never_rescued_by_the_universal_one() -> None:
    """Haier `HSU-14HFT` carries no Haier tonnage, and 14 is not one.

    Reading the universal table here would ship `1.25 Ton` on a 1 Ton Haier split -- the same digits
    mean different sizes, which is the whole reason the tables are per brand.
    """
    assert tonnage_from_model_code("haier", "HSU-14HFT") == ""


def test_only_the_first_size_group_in_a_code_is_read() -> None:
    """Row 508: `12KB60T3` is a 1 Ton split, and its `60` is not a second claim about size.

    The scan used to keep looking until it found a number some table carried, so a code with two
    known groups could be read from the later one -- `60` is 5 Ton in the universal table, and
    Hisense has no table of its own to read it from.
    """
    assert tonnage_from_model_code("hisense", "12KB60T3") == "1 Ton"


def test_a_model_line_written_as_prose_is_not_a_model_number() -> None:
    """Row 257: the sheet's `Model:` line resolved to `Inverter Frost 30: Yes`.

    Prose can be read as anything, so a code with a space or a colon in it is not evidence about a
    size at all -- the digits in `Yes` belong to a sentence.
    """
    assert tonnage_from_model_code("dawlance", "Inverter Frost 30: Yes") == ""


def test_a_code_the_pipeline_invented_is_never_read_back_as_evidence() -> None:
    """A fallback SKU is built FROM the capacity (`DAWLANCE-ECONO-15`); it cannot also prove one.

    Row 206: `Dawlance 30 Econo + Inverter Split Air Conditioner 1.5 Ton` carries no formal model
    code, so its stand-in holds the size digits -- reading them back would turn one statement into
    two and let a number the pipeline wrote become a fact about the machine.
    """
    text = "Dawlance Econo Inverter Split Air Conditioner White"
    fallback = ModelExtraction(code="DAWLANCE-ECONO-15", source="fallback", confidence="none")
    assert resolve_capacity(text, "Air Conditioner", "dawlance", fallback) == ""


def test_a_code_digit_nobody_has_written_down_states_no_size() -> None:
    """Silence is the answer, not a plausible number: `TAC-99X` is in no table (constructed)."""
    text = "TCL Split Air Conditioner White (TAC-99X)"
    assert resolve_capacity(text, "Air Conditioner", "tcl", _code("TAC-99X")) == ""


def test_only_an_air_conditioner_is_read_from_a_model_number() -> None:
    """Microwaves are litres, never tonnage -- and a code is no excuse to say it.

    The same `20` that makes a Dawlance split 1.25 Ton would put `1.25 Ton` on a microwave Title,
    which is the failure he named: "use ltrs not ton or kg in microwave".
    """
    assert resolve_capacity(
        "Dawlance Solo Microwave Oven Black (DW-20X)", "Microwave Oven", "dawlance", _code("DW-20X")
    ) == ""
    assert resolve_capacity(
        "Dawlance 20 Ltr Solo Microwave Oven Black (DW-20X)",
        "Microwave Oven",
        "dawlance",
        _code("DW-20X"),
    ) == "20 Ltr"
