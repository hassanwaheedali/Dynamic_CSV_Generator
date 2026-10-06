"""Section 11 -- attribute extraction: exact-match discipline and scoping."""

from __future__ import annotations

from attributes import ALLOWED, SCOPE, build_attributes
from sku_handle import clean_model_code


def attributes_for(
    title: str,
    description: str,
    product_type: str,
    warranty: str | None = None,
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    values, unmatched = build_attributes(
        title=title,
        description=description,
        product_type=product_type,
        warranty_headline=warranty,
    )
    return values, unmatched


def test_water_dispenser_refrigerator_compartment_maps_to_with_refrigerator() -> None:
    """The spec's worked semantic-classification example."""
    values, _ = attributes_for(
        "Homage HWD-49331P Water Dispenser With Refrigerator Cabinet",
        "Special Feature: Refrigerator Compartment",
        "Water Dispenser",
    )
    assert values["Attribute_Water Dispenser Type"] == "With refrigerator"


def test_without_refrigerator_is_not_inverted() -> None:
    """Negation must win: a substring match would publish the opposite truth."""
    values, _ = attributes_for(
        "Homage HWD-49331P Water Dispenser Without Refrigerator Cabinet",
        "Water Dispenser without refrigerator cabinet",
        "Water Dispenser",
    )
    assert values["Attribute_Water Dispenser Type"] == "Without Refrigerator"


def test_non_inverter_is_not_swallowed_by_the_inverter_rule() -> None:
    values, _ = attributes_for(
        "Gree Non Inverter Split Air Conditioner 1.5 Ton",
        "",
        "Air Conditioner",
    )
    assert values["Attribute_INV/NON-INV"] == "Non Inverter"


def test_range_is_never_rounded_into_a_single_value() -> None:
    """'220-240V' matches neither '220V' nor '240V'."""
    values, unmatched = attributes_for(
        "Dawlance Water Dispenser", "Voltage: 220-240V / 50Hz", "Water Dispenser"
    )
    assert "Attribute_Volt" not in values
    assert any(column == "Attribute_Volt" for column, _signal in unmatched)


def test_whitespace_only_collapse_allows_12_kg_to_match_12KG() -> None:
    values, _ = attributes_for(
        "Haier Top Load Washing Machine 12 kg", "", "Washing Machine"
    )
    assert values["Attribute_Washing Machine Capacity"] == "12 kg"


def test_punctuation_is_never_rewritten() -> None:
    """'16 Cu.Ft' must NOT match the list's '16 Cu Ft'."""
    values, unmatched = attributes_for(
        "Dawlance Refrigerator 16 Cu.Ft", "", "Refrigerator"
    )
    assert "Attribute_Capacity" not in values
    assert any(column == "Attribute_Capacity" for column, _ in unmatched)


def test_exact_capacity_match_is_returned_as_the_list_literal() -> None:
    values, _ = attributes_for(
        "Dawlance Refrigerator", "Capacity: 16 Cu Ft", "Refrigerator"
    )
    assert values["Attribute_Capacity"] == "16 Cu Ft"


def test_attributes_are_scoped_by_product_type() -> None:
    """795 rows contain 'inverter', but only ACs may fill INV/NON-INV here."""
    values, _ = attributes_for(
        "Dawlance Inverter Refrigerator", "Inverter Compressor", "Water Dispenser"
    )
    assert "Attribute_INV/NON-INV" not in values

    ac_values, _ = attributes_for(
        "Dawlance Inverter Air Conditioner", "DC Inverter", "Air Conditioner"
    )
    assert ac_values["Attribute_INV/NON-INV"] == "Inverter"


def test_fan_type_stays_empty_because_the_sheet_has_no_fans() -> None:
    """A naive keyword scan would fill this from unrelated words."""
    values, _ = attributes_for(
        "Dawlance Refrigerator", "Exhaust vent and wall mount bracket", "Refrigerator"
    )
    assert "Attribute_Fan Type" not in values


def test_led_type_title_beats_description() -> None:
    values, _ = attributes_for(
        "Dawlance 32 Inch Kore Google HD LED TV",
        "running Google TV, QLED panel",
        "LED TV",
    )
    assert values["Attribute_LED Type"] == "Google TV"


def test_product_type_narrow_list() -> None:
    freeze, _ = attributes_for("Dawlance Deep Freezer", "", "Deep Freezer")
    assert freeze["Attribute_Product Type"] == "Deep Freezer"
    fridge, _ = attributes_for("Dawlance Refrigerator", "", "Refrigerator")
    assert fridge["Attribute_Product Type"] == "Refrigerator"
    cleaner, _ = attributes_for("TCL Smart LED TV", "", "LED TV")
    assert "Attribute_Product Type" not in cleaner


def test_warranty_attribute_uses_the_headline_duration() -> None:
    values, _ = attributes_for(
        "Dawlance Water Dispenser", "", "Water Dispenser", warranty="3 Years"
    )
    assert values["Attribute_Warranty"] == "3 Years"


def test_warranty_is_never_rounded_or_reworded() -> None:
    """A value the allowed list does not contain is left empty and reported.

    Nothing is rounded ('3.5 Years' must never become '4 Years') and nothing is
    reworded -- when the sheet uses a form we want to accept, that exact form is
    added to ALLOWED in attributes.py instead of being normalised in code.
    """
    values, unmatched = attributes_for(
        "Dawlance Water Dispenser", "", "Water Dispenser", warranty="3.5 Years"
    )
    assert "Attribute_Warranty" not in values
    assert any(column == "Attribute_Warranty" for column, _ in unmatched)


def test_warranty_keeps_the_source_wording_exactly() -> None:
    """The sheet's '3 Year' is written as '3 Year' -- never silently corrected."""
    values, _ = attributes_for(
        "Dawlance Water Dispenser", "", "Water Dispenser", warranty="3 Year"
    )
    assert values["Attribute_Warranty"] == "3 Year"


def test_unmatched_signal_is_reported_with_its_raw_text() -> None:
    """A raw numeric signal with no exact list match is flagged, never guessed."""
    values, unmatched = attributes_for(
        "Haier Microwave Oven 1350W", "Rating Power: 1350 W", "Microwave Oven"
    )
    assert "Attribute_Watts" not in values  # 1350W is not on the allowed list
    reported = [(column, raw) for column, raw in unmatched if column == "Attribute_Watts"]
    assert reported, unmatched
    assert "1350" in reported[0][1]


def test_every_allowed_value_is_scoped_or_unscoped_consistently() -> None:
    for column, scope in SCOPE.items():
        assert column in ALLOWED, column
        if scope is not None:
            assert isinstance(scope, frozenset) and scope, column


def test_a_flow_rate_is_never_a_capacity() -> None:
    """'2.5 L/h' states a cooling RATE -- it must not become a tank capacity.

    The guard matters because a rate is a different quantity: if "2.5 L" were
    ever added to ALLOWED, an unguarded regex would publish the dispenser's
    hourly cooling rate as its tank size.
    """
    values, unmatched = attributes_for(
        "Dawlance Water Dispenser",
        "Cooling Capacity: 2.5 L/H\nHot Tank: 1.6 Liters",
        "Water Dispenser",
    )
    assert values.get("Attribute_Capacity") != "2.5 L"
    assert all(raw != "2.5 L" for _, raw in unmatched)


def test_a_plain_volume_still_matches_after_the_rate_guard() -> None:
    """The guard must not cost a real capacity: '15 Ltr' still reads as a volume."""
    values, _ = attributes_for(
        "Haier Water Dispenser", "Tank Capacity: 15 Ltr", "Water Dispenser"
    )
    assert values.get("Attribute_Capacity") == "15 Ltr"


def test_removing_a_colour_from_a_model_leaves_no_debris() -> None:
    """clean_model_code drops ONE colour word; it must not leave "()" behind.

    "Dawlance DF-200P D Solar (ARC-P1 White)" -> "... (ARC-P1)", never
    "... (ARC-P1  )", which would also fail the audit's no-invention check.
    """
    assert (
        clean_model_code("Dawlance DF-200P D Solar (ARC-P1 White)")
        == "Dawlance DF-200P D Solar (ARC-P1)"
    )
    assert clean_model_code("WD-1051 HC White") == "WD-1051 HC"
    assert clean_model_code("GS-185 White") == "GS-185"
