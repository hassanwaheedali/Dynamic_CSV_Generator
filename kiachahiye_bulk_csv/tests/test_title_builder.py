"""Unit tests for title_builder.py according to Section 6 title formula:
[Brand] [Capacity] [Color] [Inverter/Non-Inverter] [Category Name] - [Model] [Series/Feature Keyword] [Main Warranty]
"""

from __future__ import annotations

from sku_handle import ModelExtraction
from title_builder import TITLE_MAX, build_title


def test_rebuilt_title_full_template() -> None:
    extraction = ModelExtraction(code="HPU-24HDZ", source="description-model-line", confidence="high")
    result = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="Air Conditioner",
        source_title="Haier Inverter Air Conditioner 2 Ton White HPU-24HDZ Duzin Series",
        source_description="Model: HPU-24HDZ\nCapacity: 2 Ton\nColor: White\nDuzin Series\nInverter AC",
    )
    assert result.strategy == "rebuilt"
    assert result.title == "Haier 2 Ton White Inverter Air Conditioner - HPU-24HDZ Duzin - 10 Year Compressor Warranty"


def test_rebuilt_title_without_inverter_for_water_dispenser() -> None:
    extraction = ModelExtraction(code="WD-1051 HC", source="description-model-line", confidence="high")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Water Dispenser",
        source_title="Dawlance 2 Taps Water Dispenser White - (WD-1051 HC)",
        source_description="Model: WD-1051 HC White\n2 Taps\nInverter",  # Water dispenser must never grow inverter
    )
    assert result.strategy == "rebuilt"
    assert result.title == "Dawlance 2 Taps White Water Dispenser - WD-1051 HC - 3 Year Compressor Warranty"


def test_rebuilt_title_washing_machine_with_capacity_and_color() -> None:
    extraction = ModelExtraction(code="DW-6100", source="title-parenthetical", confidence="high")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Washing Machine",
        source_title="Dawlance Advanco Top load Washing Machine 8 Kg Arcelik White (DW-6100)",
        source_description="Automatic Washing Machine 8 Kg White",
    )
    assert result.strategy == "rebuilt"
    assert result.title == "Dawlance 8 KG White Top Load Washing Machine - DW-6100 Advanco - 12 Year Motor Warranty"


def test_rebuilt_title_microwave_oven_with_capacity() -> None:
    extraction = ModelExtraction(code="DW-525-AF", source="title-parenthetical", confidence="high")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Microwave Oven",
        source_title="Dawlance Air Fryer Microwave Oven 25 Ltr Black (DW-525-AF)",
        source_description="Black finish",
    )
    assert result.strategy == "rebuilt"
    assert result.title == "Dawlance 25 Ltr Black Microwave Oven - DW-525-AF Air Fryer - 1 Year Warranty"


def test_user_example_microwave_baking_1_year_warranty() -> None:
    extraction = ModelExtraction(code="DW-115-CHZP", source="title-parenthetical", confidence="high")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Microwave Oven",
        source_title="Dawlance Baking Series Microwave Oven 25 Ltr (DW-115-CHZP)",
        source_description="The Dawlance DW-115-CHZP is a 25 Ltr microwave oven in Black.",
    )
    assert result.strategy == "rebuilt"
    assert result.title == "Dawlance 25 Ltr Black Microwave Oven - DW-115-CHZP Baking - 1 Year Warranty"


def test_user_example_ac_kept_title_with_compressor_warranty() -> None:
    extraction = ModelExtraction(code="Aura 15", source="fallback", confidence="none")
    # Default strict rebuild:
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Air Conditioner",
        source_title="Dawlance Aura 15 Inverter Split Air Conditioner 1.0 Ton White",
        source_description="Split AC 1.0 Ton White. Warranty: 10 Year Compressor Warranty",
    )
    assert result.strategy == "rebuilt"
    assert result.title == "Dawlance 1 Ton White Inverter Split Air Conditioner - Aura - 10 Year Compressor Warranty"

    # When strict_rebuild is toggled False:
    result_kept = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Air Conditioner",
        source_title="Dawlance Aura 15 Inverter Split Air Conditioner 1.0 Ton White",
        source_description="Split AC 1.0 Ton White. Warranty: 10 Year Compressor Warranty",
        strict_rebuild=False,
    )
    expected = "Dawlance Aura 15 Inverter Split Air Conditioner 1.0 Ton White - 10 Year Compressor Warranty"
    assert result_kept.title == expected


def test_title_kept_when_no_confident_model() -> None:
    extraction = ModelExtraction(code="Kore 32", source="fallback", confidence="none")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="LED TV",
        source_title="Dawlance 32 Inch Kore Google HD LED TV",
        source_description="32 inch TV",
    )
    assert result.strategy == "rebuilt"
    assert result.title == "Dawlance 32 Inch LED TV - Kore Google - 2 Year Panel Warranty"

    result_kept = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="LED TV",
        source_title="Dawlance 32 Inch Kore Google HD LED TV",
        source_description="32 inch TV",
        strict_rebuild=False,
    )
    assert result_kept.strategy == "kept-with-light-cleanup"
    assert result_kept.title == "Dawlance 32 Inch Kore Google HD LED TV - 2 Year Panel Warranty"


def test_title_kept_without_warranty_when_no_warranty_entry() -> None:
    extraction = ModelExtraction(code="ABC", source="fallback", confidence="none")
    result = build_title(
        brand="UnknownBrand",
        extraction=extraction,
        product_type="UnknownType",
        source_title="UnknownBrand Device Widget",
        source_description="A device without warranty",
    )
    assert result.strategy == "rebuilt"
    assert result.title == "UnknownBrand UnknownType - Device"

    result_kept = build_title(
        brand="UnknownBrand",
        extraction=extraction,
        product_type="UnknownType",
        source_title="UnknownBrand Device Widget",
        source_description="A device without warranty",
        strict_rebuild=False,
    )
    assert result_kept.strategy == "kept-with-light-cleanup"
    assert result_kept.title == "UnknownBrand Device Widget"


def test_no_duplicate_warranty_if_already_in_source_title() -> None:
    extraction = ModelExtraction(code="Kore 32", source="fallback", confidence="none")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="LED TV",
        source_title="Dawlance 32 Inch Kore Google HD LED TV - 2 Year Panel Warranty",
        source_description="32 inch TV",
    )
    assert result.title == "Dawlance 32 Inch LED TV - Kore Google - 2 Year Panel Warranty"

    result_kept = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="LED TV",
        source_title="Dawlance 32 Inch Kore Google HD LED TV - 2 Year Panel Warranty",
        source_description="32 inch TV",
        strict_rebuild=False,
    )
    assert result_kept.title == "Dawlance 32 Inch Kore Google HD LED TV - 2 Year Panel Warranty"



def test_title_length_limit_is_enforced() -> None:
    extraction = ModelExtraction(code="XYZ-999-EXTRA-LONG-MODEL-CODE", source="manual", confidence="high")
    result = build_title(
        brand="Very Long Brand Name Appliance Manufacturer Company",
        extraction=extraction,
        product_type="Commercial Grade Double Door Refrigerator",
        source_title="Super Long Title That Would Normally Exceed Character Limits",
        source_description="Capacity: 500 L\nColor: Metallic Grey\nInverter\nAdvance Series",
    )
    assert len(result.title) <= TITLE_MAX
    assert not result.title.endswith("-")
    assert not result.title.endswith(" ")


def test_full_color_refrigerator_titles() -> None:
    for title, expected_color, expected_model in [
        (
            "DAWLANCE Acce Pro Glass Door Inverter Freezer-on-top Refrigerator (9173-WB)-Crimson Red",
            "Crimson Red",
            "9173-WB",
        ),
        (
            "DAWLANCE Acce Pro Glass Door Inverter Freezer-on-top Refrigerator (9178-WB)-Meadow Green",
            "Meadow Green",
            "9178-WB",
        ),
        (
            "DAWLANCE Acce Pro Glass Door Inverter Freezer-on-top Refrigerator (9191-WB)-Crimson Red",
            "Crimson Red",
            "9191-WB",
        ),
        (
            "DAWLANCE Acce Pro Glass Door Inverter Freezer-on-top Refrigerator (9193-WB)-Meadow Green",
            "Meadow Green",
            "9193-WB",
        ),
    ]:
        extraction = ModelExtraction(code=expected_model, source="title-parenthetical", confidence="high")
        result = build_title(
            brand="Dawlance",
            extraction=extraction,
            product_type="Refrigerator",
            source_title=title,
            source_description="",
        )
        assert result.color_token == expected_color
        expected_title = (
            f"Dawlance {expected_color} Inverter Refrigerator - {expected_model} Acce"
            " - 12 Year Compressor Warranty"
        )
        assert result.title == expected_title


def test_led_tv_title_omits_color_even_when_in_source() -> None:
    extraction = ModelExtraction(code="H32K85FX", source="description-model-line", confidence="high")
    result = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="LED TV",
        source_title="Haier 32 Inch Black Google Android LED TV (H32K85FX)",
        source_description="Model: H32K85FX\nColor: Black\n32 Inch Google TV",
    )
    assert result.strategy == "rebuilt"
    assert "Black" not in result.title
    assert result.color_token == "Black"
    assert result.title == "Haier 32 Inch LED TV - H32K85FX Android Google - 2 Year Panel Warranty"


def test_led_tv_kept_title_omits_color() -> None:
    extraction = ModelExtraction(code="H32K85FX", source="fallback", confidence="none")
    result = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="LED TV",
        source_title="Haier 32 Inch Black Google Android LED TV",
        source_description="Color: Black",
        strict_rebuild=False,
    )
    assert result.strategy == "kept-with-light-cleanup"
    assert "Black" not in result.title


def test_washing_machine_title_no_fully_and_correct_warranty() -> None:
    extraction = ModelExtraction(code="HW120-BP12357S8", source="title-parenthetical", confidence="high")
    source_title = "Haier Front Load Fully Automatic Washing Machine 12KG (HW120-BP12357S8)"
    source_desc = (
        "Capacity: 12 KG\nColor: Grey\nWarranty: 10\n"
        "Front Load Fully Automatic\na 10 motor and 3 years panel warranty"
    )
    result = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="Washing Machine",
        source_title=source_title,
        source_description=source_desc,
    )
    assert "10 Year 10 Warranty" not in result.title
    expected = (
        "Haier 12 KG Grey Fully Automatic Front Load Washing Machine"
        " - HW120-BP12357S8 - 10 Year Motor Warranty"
    )
    assert result.title == expected



def test_a_name_the_row_wrote_prints_even_when_its_letters_are_inside_the_code() -> None:
    """`K85 Series` is the row's own name, so it prints -- even though `H40K85EFX` already contains it.

    The rebuild used to drop any feature word whose letters appeared inside a word already printed.
    That is why `Kenwood … (KEL-2470S)` shipped as `Luxury Pro`: the `E` of the name was inside the
    code, and a row lost the line it sells.  The rule is now words, not letters; the cost is that
    7 rows read redundantly (`H40K85EFX K85`), which is a presentation question for the owner, not
    a reason to hide a name no other rule can see.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="H40K85EFX", source="title-parenthetical", confidence="high"),
        product_type="LED TV",
        source_title="Haier 40 Inch FHD K85 Series Smart Google LED TV (H40K85EFX)",
        source_description="Haier 40 inch FHD Smart Google LED TV.",
    )
    assert " K85" in result.title


def test_geyser_capacity_ignores_inline_weight_and_keeps_nasgas() -> None:
    extraction = ModelExtraction(code="MEH-30", source="title-parenthetical", confidence="high")
    result = build_title(
        brand="Superasia",
        extraction=extraction,
        product_type="Geyser",
        source_title="Super Asia Mega Electric Water Heater 30Ltr White (MEH-30)",
        source_description=(
            "A 30 L water heater. Key features include capacity: 30 Liters, "
            "net Weight: 14.45 kg, gross Weight: 16.25 kg."
        ),
    )
    assert result.capacity_token == "30 Ltr"
    assert "KG" not in result.title

    nas = build_title(
        brand="Nasgas",
        extraction=ModelExtraction(code="Sem-120", source="title-parenthetical", confidence="high"),
        product_type="Geyser",
        source_title="Nasgas Semi Electric Geyser 12 Litre (Sem-120)",
        source_description="",
    )
    assert nas.title.startswith("Nasgas")

