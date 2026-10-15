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
