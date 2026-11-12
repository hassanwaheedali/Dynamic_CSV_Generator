"""Section 11 -- attribute extraction: exact-match discipline and scoping."""

from __future__ import annotations

import pytest

import main as pipeline_main
from attributes import ALLOWED, SCOPE, build_attributes
from models import InputRow
from qc_report import QCFlagCollector
from sku_handle import clean_model_code
from tests.conftest import Pipeline
from vendor_config import KIACHAHIYE, VENDOR_REGISTRY


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


@pytest.mark.parametrize("prefix", ["", "• ", "â€¢ ", "- "])
def test_product_voltage_range_never_falls_back_to_a_component(prefix: str) -> None:
    values, gaps = attributes_for(
        "Dawlance DBD-1034 Water Dispenser",
        f"{prefix}Refill System: Auto Refill Technology with 12V Pump (0.41 A)\n"
        f"{prefix}Voltage: 220-240 V\n{prefix}Frequency: 50 Hz",
        "Water Dispenser",
    )
    assert "Attribute_Volt" not in values
    assert ("Attribute_Volt", "220-240 V") in gaps


@pytest.mark.parametrize("label", [
    "Voltage", "Input Voltage", "Rated Voltage", "Operating Voltage", "Power Supply",
    "Rated Voltage (V)", "Rated Voltage / Frequency", "Power Input", "Power supply source",
])
def test_product_voltage_outranks_component_voltage(label: str) -> None:
    values, _gaps = attributes_for(
        "Dawlance Water Dispenser", f"Refill System: 12V Pump\n{label}: 220 V", "Water Dispenser",
    )
    assert values["Attribute_Volt"] == "220V"


@pytest.mark.parametrize("description", [
    "Refill System: Auto Refill Technology with 12V Pump (0.41 A)",
    "Pump Voltage: 12V\nDisplay Voltage: 120V",
    "Voltage Regulator: 12V",
    "Voltage: Not specified\nRefill System: 12V Pump",
    "Voltage: Not specified (12V pump)",
    "Voltage: Pump 12V; product supply unspecified",
])
def test_missing_product_voltage_stays_blank_despite_component_signals(description: str) -> None:
    values, _gaps = attributes_for("Dawlance Water Dispenser", description, "Water Dispenser")
    assert "Attribute_Volt" not in values


def test_unlisted_product_voltage_is_reported_without_selecting_an_allowed_component() -> None:
    values, gaps = attributes_for(
        "Dawlance Water Dispenser", "Voltage: 230V\nRefill System: 12V Pump", "Water Dispenser",
    )
    assert "Attribute_Volt" not in values
    assert ("Attribute_Volt", "230 V") in gaps


def test_component_voltage_in_the_product_voltage_field_cannot_replace_the_primary_value() -> None:
    values, gaps = attributes_for(
        "Dawlance Water Dispenser", "Voltage: 230V (internal pump: 12V)", "Water Dispenser",
    )
    assert "Attribute_Volt" not in values
    assert ("Attribute_Volt", "230 V") in gaps


def test_a_real_12v_product_is_still_allowed() -> None:
    values, _gaps = attributes_for("Portable Fan", "Voltage: 12V", "Fan")
    assert values["Attribute_Volt"] == "12V"


def test_dc_product_voltage_with_the_unit_in_the_label_still_matches() -> None:
    values, _gaps = attributes_for("Solar DC Air Cooler", "Rated Voltage (V): DC-12V", "Air Cooler")
    assert values["Attribute_Volt"] == "12V"


@pytest.mark.parametrize("voltage", ["220~240V", "100V~240V", "220–240V", "110V/220V"])
def test_the_whole_product_voltage_expression_is_preserved(voltage: str) -> None:
    values, gaps = attributes_for("Water Dispenser", f"Voltage: {voltage}\nRefill System: 12V Pump", "Water Dispenser")
    assert "Attribute_Volt" not in values
    assert any(column == "Attribute_Volt" and raw.replace(" ", "") == voltage for column, raw in gaps)


def test_an_unrecognized_primary_voltage_unit_never_promotes_a_later_component() -> None:
    values, gaps = attributes_for("Water Dispenser", "Voltage: 230 volts (pump 12V)", "Water Dispenser")
    assert "Attribute_Volt" not in values
    assert any(column == "Attribute_Volt" and "230" in raw for column, raw in gaps)


@pytest.mark.parametrize("label", ["Power Input", "Power Supply"])
def test_a_power_field_in_watts_does_not_become_a_voltage_gap(label: str) -> None:
    values, gaps = attributes_for("Microwave Oven", f"{label}: 1000W", "Microwave Oven")
    assert "Attribute_Volt" not in values
    assert not any(column == "Attribute_Volt" for column, _raw in gaps)


def test_conflicting_product_voltage_fields_are_reported_instead_of_guessed() -> None:
    values, gaps = attributes_for("Appliance", "Voltage: 220V\nRated Voltage: 240V", "Iron")
    assert "Attribute_Volt" not in values
    assert any(column == "Attribute_Volt" and "220" in raw and "240" in raw for column, raw in gaps)


def test_an_explicitly_allowed_product_voltage_range_can_be_published(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(ALLOWED, "Attribute_Volt", [*ALLOWED["Attribute_Volt"], "220-240V"])
    values, gaps = attributes_for(
        "Dawlance Water Dispenser", "Refill System: 12V Pump\nVoltage: 220-240V", "Water Dispenser",
    )
    assert values["Attribute_Volt"] == "220-240V"
    assert not any(column == "Attribute_Volt" for column, _raw in gaps)


def test_removing_the_product_voltage_from_allowed_never_promotes_a_component(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(ALLOWED, "Attribute_Volt", ["12V"])
    values, gaps = attributes_for(
        "Water Dispenser", "Voltage: 220V\nRefill System: 12V Pump", "Water Dispenser",
    )
    assert "Attribute_Volt" not in values
    assert ("Attribute_Volt", "220 V") in gaps


def test_repeated_identical_product_voltage_fields_are_consistent() -> None:
    values, _gaps = attributes_for("Iron", "Voltage: 220V\nRated Voltage: 220 V", "Iron")
    assert values["Attribute_Volt"] == "220V"


def test_table_cells_preserve_the_product_voltage_label() -> None:
    values, _gaps = attributes_for(
        "Water Dispenser",
        "<table><tr><td>Refill System</td><td>12V Pump</td></tr>"
        "<tr><td>Voltage</td><td>220V</td></tr></table>",
        "Water Dispenser",
    )
    assert values["Attribute_Volt"] == "220V"


@pytest.mark.parametrize("vendor_key", list(VENDOR_REGISTRY))
def test_html_source_product_voltage_does_not_publish_pump_voltage(pipeline: Pipeline, vendor_key: str) -> None:
    result = pipeline([{
        "Title": "Dawlance DBD-1034 Glass Door Bottom Load Water Dispenser Champagne",
        "Description": "â€¢ Refill System: Auto Refill Technology with 12V Pump (0.41 A)<br>"
                       "â€¢ Voltage: 220-240 V<br>â€¢ Compressor Warranty: 5 Years",
        "Categories": "Water Dispenser", "Brand": "Dawlance", "Sell Price": "10000", "Original Price": "11000",
    }], VENDOR_REGISTRY[vendor_key])
    assert result["digi"][0]["Attribute_Volt"] == ""
    assert any(
        flag.category == "attribute_empty" and "Attribute_Volt:" in flag.message and "220-240" in flag.message
        for flag in result["flags"].flags
    )


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


def test_newly_mapped_small_appliances_extract_scoped_attributes() -> None:
    """M1.5d: Newly mapped appliance Product Types extract Watts, Capacity, Volt, and Warranty."""
    for pt in (
        "Iron",
        "Garment Steamer",
        "Oven",
        "Electric Kettle",
        "Blender",
        "Juicer",
        "Mixer",
        "Food Processor",
        "Grinder",
        "Toaster",
        "Sandwich Maker",
        "Coffee Maker",
    ):
        values, unmatched = attributes_for(
            f"Philips {pt} 1000W",
            "Power: 1000W\nVoltage: 220V",
            pt,
            warranty="2 Years",
        )
        assert values.get("Attribute_Watts") == "1000W", pt
        assert values.get("Attribute_Volt") == "220V", pt
        assert values.get("Attribute_Warranty") == "2 Years", pt
        assert not unmatched, pt

    kettle_vals, _ = attributes_for(
        "Anex Deluxe Electric Kettle 1.8 Litter",
        "Capacity: 1.8 Litter\nPower: 1500W",
        "Electric Kettle",
    )
    assert kettle_vals.get("Attribute_Capacity") == "1.8 Litter"
    assert kettle_vals.get("Attribute_Watts") == "1500W"


def test_run_executes_heavy_builders_once_per_row(monkeypatch) -> None:
    """M1.5d: run() executes title/description/attribute/warranty builders once per row, not twice."""
    counts = {"slots": 0, "desc": 0, "attr": 0, "warranty": 0}
    orig_slots = pipeline_main.extract_title_slots
    orig_desc = pipeline_main.build_description_bundle
    orig_attr = pipeline_main.build_attributes
    orig_warranty = pipeline_main.extract_warranty

    def spy_slots(*args, **kwargs):
        counts["slots"] += 1
        return orig_slots(*args, **kwargs)

    def spy_desc(*args, **kwargs):
        counts["desc"] += 1
        return orig_desc(*args, **kwargs)

    def spy_attr(*args, **kwargs):
        counts["attr"] += 1
        return orig_attr(*args, **kwargs)

    def spy_warranty(*args, **kwargs):
        counts["warranty"] += 1
        return orig_warranty(*args, **kwargs)

    monkeypatch.setattr(pipeline_main, "extract_title_slots", spy_slots)
    monkeypatch.setattr(pipeline_main, "build_description_bundle", spy_desc)
    monkeypatch.setattr(pipeline_main, "build_attributes", spy_attr)
    monkeypatch.setattr(pipeline_main, "extract_warranty", spy_warranty)

    rows = [
        InputRow(
            2,
            "Gree 1.5 Ton Inverter Split AC (GS-18PITH11W)",
            "10 Years Compressor Warranty",
            "145000",
            "155000",
            "Electronics / Home appliances / AC",
            "Gree",
            "https://example.com/1.jpg",
            "",
        ),
        InputRow(
            3,
            "Dawlance 12 Cu Ft Double Door Refrigerator (9178LF)",
            "12 Years Compressor Warranty",
            "85000",
            "95000",
            "Electronics / Home appliances / Refrigerators",
            "Dawlance",
            "https://example.com/2.jpg",
            "",
        ),
    ]
    records = pipeline_main.run(rows, QCFlagCollector(), vendor_cfg=KIACHAHIYE)
    assert len(records) == 2
    assert counts == {"slots": 2, "desc": 2, "attr": 2, "warranty": 2}

