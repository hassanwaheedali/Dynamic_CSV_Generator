"""Tests for `sku_handle` -- the reader that decides what a row's size is.

`parse_capacity` is the only place the sheet's numbers become the `[Capacity]` token, so the rules
it owns are pinned here directly, at the reader, and not only through a Title.
"""

from sku_handle import parse_capacity


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
