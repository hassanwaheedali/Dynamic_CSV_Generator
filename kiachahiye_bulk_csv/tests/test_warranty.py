"""Unit tests for warranty.py -- every warranty fact the row states must reach a row.

The owner's rule: what he writes in the Description must appear in the output.  A warranty stated
on two lines is two facts, not one, and the second is never silently dropped.
"""

from __future__ import annotations

from warranty import resolve_main_warranty, resolve_warranty

SAMPLE = (
    "The Haier HSU-18HFPAA is a 1.5 Ton DC Inverter Wall Mounted Split Air Conditioner "
    "from the Pearl Series in Silver.\n"
    "Key Specifications:\n"
    "• Brand: Haier\n"
    "• Capacity: 1.5 Ton\n"
    "• Compressor Warranty: 10 Years\n"
    "• Parts Warranty: 5 Years\n"
)


def test_each_warranty_line_the_row_states_becomes_its_own_row() -> None:
    rows, headline, source = resolve_warranty(SAMPLE, "haier", "Air Conditioner")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [
        ("Compressor Warranty", "10 Years"),
        ("Parts Warranty", "5 Years"),
    ]
    assert headline == "10 Years"


def test_a_warranty_written_inside_the_label_is_kept_too() -> None:
    """The Homage template writes `• 10 years motor warranty: Yes` -- the fact is in the label.

    Only the first such line used to survive, so `1 years all parts warranty` disappeared from
    the table and from every attribute.

    His ruling on the shipped wording: the row's own English is kept exactly as he wrote it,
    plural mistake and all -- `1 years` becomes `1 Years`, not `1 Year`.
    """
    description = (
        "The Homage HAP-251DWB is an air purifier in White.\n"
        "• 10 years motor warranty: Yes\n"
        "• 1 years all parts warranty: Yes\n"
    )
    rows, headline, source = resolve_warranty(description, "homage", "Air Purifier")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [
        ("Motor Warranty", "10 Years"),
        ("Parts Warranty", "1 Years"),
    ]
    assert headline == "10 Years"


def test_two_parts_written_on_one_line_still_split() -> None:
    """The older single-line shape must keep working exactly as before."""
    description = (
        "The Dawlance WD-1051 HC is a water dispenser in White.\n"
        "• Warranty: 3 Years Compressor, 1 Year General Warranty\n"
    )
    rows, headline, source = resolve_warranty(description, "dawlance", "Water Dispenser")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [
        ("Compressor Warranty", "3 Years"),
        ("General Warranty", "1 Year"),
    ]
    assert headline == "3 Years"


def test_a_warranty_named_once_is_not_repeated() -> None:
    description = (
        "The Haier HSU-13HFS is a 1 Ton DC Inverter split air conditioner with "
        "10 Years Compressor Warranty.\n"
        "• Color: White\n"
    )
    rows, headline, source = resolve_warranty(description, "haier", "Air Conditioner")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [("Compressor Warranty", "10 Years")]
    assert headline == "10 Years"


def test_the_generic_warranty_line_is_the_headline_a_lesser_part_names_is_not() -> None:
    """`• Warranty: 10 Years` sells the machine; `• PCB Warranty: 4 Years` is a rider.

    Reading both lines made the rider the headline, so the Title lost its 10 Year tail and said
    `4 Year Pcb Warranty` -- the number a shopper buys on moved backwards.
    """
    description = (
        "The Kenwood KLP-12B02S is a 1 Ton inverter split air conditioner.\n"
        "• Warranty: 10 Years\n"
        "• PCB Warranty: 4 Years\n"
    )
    rows, headline, source = resolve_warranty(description, "kenwood", "Air Conditioner")
    assert source == "stated"
    assert headline == "10 Years"
    assert [(row.label, row.value) for row in rows] == [
        ("Warranty", "10 Years"),
        ("PCB Warranty", "4 Years"),
    ]
    assert resolve_main_warranty(description, "kenwood", "Air Conditioner") == (
        "10 Year Compressor Warranty"
    )


def test_a_named_compressor_line_still_outranks_the_generic_one() -> None:
    """The other direction: a part named with the BIG number must not lose to a bare line."""
    description = (
        "The Dawlance DF-500 DD is a 15 cu ft deep freezer.\n"
        "• Warranty: 1 Year\n"
        "• Compressor Warranty: 12 Years\n"
    )
    _, headline, source = resolve_warranty(description, "dawlance", "Deep Freezer")
    assert source == "stated"
    assert headline == "12 Years"


def test_the_part_word_and_its_value_never_become_one_label() -> None:
    """`• 10 Years Nationwide Warranty: Yes` is the part `Nationwide`, not `Nationwide : Yes`."""
    description = (
        "The Kenwood KES-1270S is a 1 Ton inverter split air conditioner.\n"
        "• 10 Years Nationwide Warranty: Yes\n"
    )
    rows, headline, source = resolve_warranty(description, "kenwood", "Air Conditioner")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [("Nationwide Warranty", "10 Years")]
    assert headline == "10 Years"
    assert resolve_main_warranty(description, "kenwood", "Air Conditioner") == (
        "10 Year Nationwide Warranty"
    )


def test_a_part_that_states_lifetime_keeps_its_own_row() -> None:
    """`Lifetime` IS the answer, so the part that gives it cannot be dropped.

    The row lost its compressor fact twice over: the table printed no compressor row, and the
    Title fell back to the smaller `3 Year Warranty` when it used to print the compressor term.
    """
    description = (
        "The Homage HRF-47552-GD-INV is a 15 cu ft inverter refrigerator.\n"
        "• Lifetime compressor warranty: Yes\n"
        "• 3 years all parts warranty: Yes\n"
    )
    rows, headline, source = resolve_warranty(description, "homage", "Refrigerator")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [
        ("Compressor Warranty", "Lifetime"),
        ("Parts Warranty", "3 Years"),
    ]
    assert headline == "Lifetime"


def test_the_generic_line_keeps_its_number_when_boilerplate_follows_it() -> None:
    """Real sheet, sheet row 490: `• Warranty: 10 Years Real Free Warranty`.

    The words after the number are his term, not a component, so the line names no part and must
    head the Title.  Collecting the second clause made `Parts Warranty: 5 Years` the headline,
    which moved the number a shopper buys on from 10 Years to 5 Years.
    """
    description = (
        "The Haier Solar Hybrid-IV-T3 Plus is a 1.5 Ton inverter split heat & cool air "
        "conditioner.\n"
        "• Warranty: 10 Years Real Free Warranty\n"
        "• Parts Warranty: 5 Years Real Free Warranty\n"
    )
    rows, headline, source = resolve_warranty(description, "haier", "Air Conditioner")
    assert source == "stated"
    assert headline == "10 Years"
    assert [(row.label, row.value) for row in rows] == [
        ("Real Free Warranty", "10 Years"),
        ("Parts Warranty", "5 Years"),
    ]


def test_a_bare_lifetime_line_is_labelled_once() -> None:
    """Real sheet, sheet row 510: `• Warranty: Lifetime` above `• All Parts Warranty: 3 Years`.

    The word `Lifetime` is the answer, not the part, so the table row is `Warranty: Lifetime` --
    printing it as `Lifetime Warranty: Lifetime` states the same word twice in one row.  It also
    heads the Title: the shop's own general warranty outranks the parts rider, exactly as a bare
    `Warranty: 10 Years` does.
    """
    description = (
        "The Homage HRF-47442-GD is a 13 cu ft refrigerator.\n"
        "• Warranty: Lifetime\n"
        "• All Parts Warranty: 3 Years\n"
    )
    rows, headline, source = resolve_warranty(description, "homage", "Refrigerator")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [
        ("Warranty", "Lifetime"),
        ("Parts Warranty", "3 Years"),
    ]
    assert headline == "Lifetime"


def test_the_same_fact_written_twice_becomes_one_row() -> None:
    """Real sheet, sheet row 324: the intro prose and the bullet state one warranty.

    `... with 10-year compressor warranty for long-term peace of mind` above
    `• 10-Year Compressor Warranty: Yes` is the same fact written twice, so the table shows it
    once, in the order he wrote his lines.  Two identical rows made the builder's duplicate-label
    rename print `Compressor Warranty Warranty`.
    """
    description = (
        "The Homage HES-1222S is a 1.0 Ton inverter split air conditioner with 10-year "
        "compressor warranty for long-term peace of mind.\n"
        "• 4-Year PCB Warranty: Yes\n"
        "• 10-Year Compressor Warranty: Yes\n"
    )
    rows, headline, source = resolve_warranty(description, "homage", "Air Conditioner")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [
        ("PCB Warranty", "4 Year"),
        ("Compressor Warranty", "10 Year"),
    ]
    assert headline == "10 Year"


def test_the_shop_s_own_word_survives_when_his_line_names_no_component() -> None:
    """Real sheet, sheet rows 490 and 516: `Real Free`, `Manufacturer` are his words.

    `• Warranty: 10 Years Real Free Warranty` names no component, so it heads the Title -- but the
    Title must then carry the words he wrote after his number.  Sorting the clause into the
    unnamed group made the phrase fall back to the brand's reference part, which printed
    `10 Year Compressor Warranty` (a part he never named) and erased `1 Year Manufacturer`.
    """
    haier = (
        "The Haier Solar Hybrid-IV-T3 Plus is a 1.5 Ton inverter split heat & cool air "
        "conditioner.\n"
        "• Warranty: 10 Years Real Free Warranty\n"
        "• Parts Warranty: 5 Years Real Free Warranty\n"
    )
    kenwood = (
        "The Kenwood KGP-12C03S is a 1 Ton inverter split air conditioner.\n"
        "• Warranty: 1 Year Manufacturer\n"
    )
    assert resolve_main_warranty(haier, "haier", "Air Conditioner") == (
        "10 Year Real Free Warranty"
    )
    assert resolve_main_warranty(kenwood, "kenwood", "Air Conditioner") == (
        "1 Year Manufacturer Warranty"
    )


def test_the_reference_table_never_names_a_part_the_row_left_unnamed() -> None:
    """Real sheet, sheet row 629: `• Warranty: 2 Year Official Warranty` on a TCL TV.

    A line stating no part at all still borrows the brand's headline component -- but only when the
    shop wrote nothing but the number.  `Official` is a term he chose, and pasting `Panel` in front
    of it sold him a panel warranty he never claimed.
    """
    description = (
        "The TCL 55A400 Pro is a 55 inch 4K UHD smart LED television.\n"
        "• Warranty: 2 Year Official Warranty\n"
    )
    assert resolve_main_warranty(description, "tcl", "LED TV") == "2 Year Warranty"


def test_a_row_whose_only_warranty_line_states_no_number_keeps_that_line() -> None:
    """`• Warranty: Official Brand Warranty` names no duration, and it is all he wrote.

    Ignoring a clause that answers nothing is right when the row also states a number -- otherwise
    `• Warranty: Yes` prints as a fact beside the real one.  When it is the row's ONLY warranty
    line, filtering it out deletes his warranty from the table and hands the brand's reference
    numbers to a product whose terms he stated himself.
    """
    description = "The Nasgas NWH-35 is a 35 litre geyser.\n• Warranty: Official Brand Warranty\n"
    rows, headline, source = resolve_warranty(description, "nasgas", "Geyser")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [("Warranty", "Official Brand Warranty")]
    assert headline is None


def test_a_yes_written_beside_a_real_term_is_still_ignored() -> None:
    """The other half of the same rule: an answerless line loses only to a line that answers."""
    description = (
        "The Kenwood KES-1270S is a 1 Ton inverter split air conditioner.\n"
        "• Warranty: Yes\n"
        "• 10 Years Nationwide Warranty: Yes\n"
    )
    rows, headline, source = resolve_warranty(description, "kenwood", "Air Conditioner")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [("Nationwide Warranty", "10 Years")]
    assert headline == "10 Years"


def test_a_warranty_line_that_wears_its_number_in_the_label_is_a_second_fact() -> None:
    """`• 10 years compressor warranty: Yes` answers the question -- the number is just not after
    the colon.  Reading only what follows the colon made this line look like a `Yes`, so a row that
    also states `• PCB Warranty: 2 Years` kept the PCB and deleted the compressor, which is the
    same bug the owner reported: a second warranty line that never reaches the output.
    """
    description = (
        "The TCL T-0129WP6I is a 1.5 Ton inverter split air conditioner.\n"
        "• PCB Warranty: 2 Years\n"
        "• 10 years compressor warranty: Yes\n"
    )
    rows, headline, source = resolve_warranty(description, "tcl", "Air Conditioner")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [
        ("PCB Warranty", "2 Years"),
        ("Compressor Warranty", "10 Years"),
    ]
    assert headline == "10 Years"


def test_a_service_rider_does_not_make_a_bare_warranty_line_a_part_line() -> None:
    """`• Warranty: 10 Years Free Service` still answers the whole product, not one part.

    The bare line owns the headline unless another line names a part that could outrank it.  A
    rider such as Free Service names nothing in the ranking, so treating it as a part pushed the
    shop's own 10 Years out of the Title in favour of a lesser `• PCB Warranty: 2 Years`.
    """
    description = (
        "The Super Asia SAC-1288 is a 1 Ton split air conditioner.\n"
        "• Warranty: 10 Years Free Service\n"
        "• PCB Warranty: 2 Years\n"
    )
    rows, headline, source = resolve_warranty(description, "super asia", "Air Conditioner")
    assert source == "stated"
    assert [(row.label, row.value) for row in rows] == [
        ("Service Warranty", "10 Years"),
        ("PCB Warranty", "2 Years"),
    ]
    assert headline == "10 Years"
    tail = resolve_main_warranty(description, "super asia", "Air Conditioner")
    assert tail.startswith("10 Year") and "Pcb" not in tail
