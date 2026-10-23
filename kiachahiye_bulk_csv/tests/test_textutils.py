"""Unit tests for the colour rules in textutils.py.

A colour phrase is confined to the LINE it is written on: it must never extend across
a line break into the next spec line.  When it did, the Title grew a word from the
following line into its colour slot ("Color: White" + "Duzin Series" -> "White Duzin"),
and that stolen word was no longer available for [series].

These tests pin the LINE boundary only.  A colour line that carries a stray word on its
OWN line ("Color: Black & Red") is a separate, wider question with 24 real rows behind
it, and is deliberately not asserted here.
"""

from __future__ import annotations

from textutils import find_full_color


def test_spec_line_colour_stops_at_the_line_break() -> None:
    """`Color: White` states White -- the series name on the next line is not part of it."""
    text = (
        "Model: HPU-24HDZ\n"
        "Capacity: 2 Ton\n"
        "Color: White\n"
        "Duzin Series\n"
        "Inverter AC"
    )
    assert find_full_color(text) == "White"


def test_spec_line_colour_never_swallows_the_next_label() -> None:
    """`Color: Grey` followed by `Warranty: ...` must not read the label word as a colour."""
    text = "Color: Grey\nWarranty: 10 Year Motor Warranty"
    assert find_full_color(text) == "Grey"


def test_finished_in_colour_stops_at_the_line_break() -> None:
    """The same boundary applies to the `finished in <colour>` phrasing."""
    text = "Finished in White\nWarranty: 5 Years"
    assert find_full_color(text) == "White"


def test_available_in_colour_stops_at_the_line_break() -> None:
    """`Available in Silver` then a `Model:` line must read Silver, not `Silver Model`."""
    text = "Available in Silver\nModel: HW120-BP12357S8"
    assert find_full_color(text) == "Silver"


def test_modifier_and_base_colour_on_one_line_still_join() -> None:
    """A real two-word colour on one line is still one colour -- do not over-fix."""
    assert find_full_color("Color: Crimson Red") == "Crimson Red"


def test_product_colour_line_keeps_its_modifier() -> None:
    """`Product Color: Metallic Grey` is Metallic Grey, grey spelled the §9 way."""
    assert find_full_color("Product Color: Metallic Grey") == "Metallic Grey"


def test_a_full_colourway_name_survives_the_colour_line() -> None:
    """The label states a colourway, not just a head colour -- keep the whole name.

    `Blaze Purple` and `Red Blaze` are the names these machines are sold under; printing
    only `Purple` or `Red` drops the word that tells two variants apart.
    """
    assert find_full_color("Color: Blaze Purple") == "Blaze Purple"
    assert find_full_color("Colour: Red Blaze") == "Red Blaze"


def test_a_three_word_colour_line_keeps_every_word() -> None:
    """`Dark Jade Silver` is three words, and all three are the name -- no two-word cap."""
    assert find_full_color("Color: Dark Jade Silver") == "Dark Jade Silver"


def test_a_colour_line_stops_at_the_punctuation_that_ends_it() -> None:
    """A comma closes the value: the words after it are the next spec, not part of the colour."""
    assert find_full_color("Color: Blaze Purple, Inverter AC") == "Blaze Purple"


def test_a_scraped_option_picker_is_not_read_as_one_colour() -> None:
    """A variant picker dump is a list of options, not a colour phrase.

    Row 537's description carries `Color: Choose an option Hairline Golden Hairline Red
    Hairline ...`.  Reading the first words as a colourway invents a phrase no shop wrote;
    the Title's own `Red` is the answer instead.
    """
    text = (
        "• Color: Choose an option Hairline Golden Hairline Red Hairline Hairline Black "
        "Hairline Silver"
    )
    title = "Orient Grand 335 Freezer-on-Top Refrigerator 12 Cu Ft Red"
    assert find_full_color(text, title) == "Red"


def test_a_label_line_without_a_separator_is_prose_not_a_colour_statement() -> None:
    """`Color Pattern        Black` is a scraped spec table's own column head, not `Color: ...`.

    Without a required separator the reader took `Pattern Black` -- two words no shop wrote -- as
    the colourway.  The label is a contract only when the row punctuated it as one.
    """
    text = "Color Pattern        Black\nModel: DW-5502\nWarranty: 1 Year"
    assert find_full_color(text) == "Black"


def test_a_tab_is_a_separator_the_label_can_stand_on() -> None:
    """The tab-separated spec blocks these sheets write are still labels: `Color<TAB>Black`."""
    assert find_full_color("Color\tBlack\nModel: DW-5502") == "Black"


def test_a_bullet_prose_line_starting_with_the_word_color_names_no_colour() -> None:
    """`• Color Depth Black` is a sentence about the PICTURE, not a `Color:` label.

    The separator-less reader took `Depth Black` -- a phrase no shop wrote -- as the colourway.
    With the label punctuated, the row's paint is what the base reader finds, never the sentence.
    """
    text = "• Color Depth Black\nModel: 55P6K"
    assert find_full_color(text, "TCL 55 Inch 4K LED TV") == "Black"
