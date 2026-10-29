"""Unit tests for title_builder.py according to Section 6 title formula:
[Brand] [Capacity] [Color] [Inverter/Non-Inverter] [Category Name] - [Model] [Series/Feature Keyword] [Main Warranty]
"""

from __future__ import annotations

import csv
from pathlib import Path

import description_builder
from sku_handle import ModelExtraction, extract_model
from title_builder import (
    _USP_POSITIVE_VALS,
    TITLE_MAX,
    TitleResult,
    beside_model_code,
    build_title,
    colourway_words,
    extract_inverter,
    extract_series,
    extract_usps,
    stated_class_phrase,
    without_leading_type_words,
    word_identity,
)


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


def test_the_full_colourway_the_description_states_reaches_the_title_whole() -> None:
    """`Color: Blaze Purple` is the row naming its own colourway; `Marvel` is the series.

    The reading used to keep only a known modifier in front of a base colour, so this Title sold
    `Blaze Purple` as `Purple` and left `Blaze` free to be guessed as a line name.
    """
    extraction = ModelExtraction(code="HRF-336EPB", source="title-parenthetical", confidence="high")
    result = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="Refrigerator",
        source_title="Haier 12 CuFt Refrigerator Marvel Series Blaze Purple (HRF-336EPB)",
        source_description="Model: HRF-336EPB\nColor: Blaze Purple\nMarvel Series\n12 CuFt",
    )
    assert result.color_token == "Blaze Purple"
    assert result.title == (
        "Haier 12 Cu Ft Blaze Purple Refrigerator - HRF-336EPB Marvel - 10 Year Compressor Warranty"
    )


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
    # `Fully Automatic` now comes from the Description's own sentence -- the Title said only
    # `Top load`, and the group the Title left unanswered is the one the prose answers.
    assert result.subtype_from == "list"
    assert result.title == (
        "Dawlance 8 KG White Fully Automatic Top Load Washing Machine - DW-6100 Advanco "
        "- 12 Year Motor Warranty"
    )


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
    """His example row: `Dawlance Aura 15 ... 1.0 Ton White`.

    Segment 2 carries `Aura 15` -- the name and the number the row itself wrote.  An earlier
    expectation dropped the `15` and sold the machine by half its name, which the identity rule now
    forbids: a row with no model code is shipped under the stock code the shop uses.
    """
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
    assert result.title == "Dawlance 1 Ton White Inverter Split Air Conditioner - Aura 15 - 10 Year Compressor Warranty"

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
        # `Freezer-on-top` is what the row wrote, and DigiMall's `Attribute_Refrigerator Type` is
        # matched out of the Title -- the class rung re-homes it into [Subtype] instead of letting
        # the rebuild drop it and the cell fall to a value the row never stated.  It prints in the
        # platform's own letters (owner ruling, 2026-10-23): one fact, one spelling on one shelf.
        expected_title = (
            f"Dawlance {expected_color} Inverter Freezer-On-Top Refrigerator - {expected_model} Acce"
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
    # One seat, one kind of word: `Android` is a value of the platform's `Attribute_LED Type`, so it
    # prints in `[Subtype]` beside the size, while `Google` -- an OS the lists never enumerate as a
    # type -- keeps the feature seat behind the code.  Printing the type word in the name seat is what
    # made `- H32K85FX Android Google` read as a line called "Android Google".
    assert result.title == "Haier 32 Inch Android LED TV - H32K85FX Google - 2 Year Panel Warranty"


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


# --------------------------------------------------------------------------- #
# [Capacity] -- a category is sold in its own unit
# --------------------------------------------------------------------------- #
def test_an_air_conditioner_is_sold_in_ton_never_in_the_weight_of_its_own_boxes() -> None:
    """Row 257 of the sheet: `Indoor Unit Weight (kg) 13 kg` beat the row's own `1.5 Ton`.

    The weight guards only know a `Weight:` line, and this sheet writes weight as a spec bullet in
    running prose -- so the first pattern that matched won and the shop's AC Title read `13 KG`.
    The unit is the fact here: a category prints the size written in a unit it is actually sold in,
    and a number in any other unit is not its capacity.
    """
    result = build_title(
        brand="Dawlance",
        extraction=ModelExtraction(
            code="Inverter Frost 30: Yes", source="description-model-line", confidence="high"
        ),
        product_type="Air Conditioner",
        source_title="Dawlance Frost 30 Inverter Split Air Conditioner 1.5 Ton White (Cool Only)",
        source_description=(
            "The Dawlance Frost Inverter 30 White (Cool Only) is a 1.5 Ton DC Inverter split air "
            "conditioner designed for cooling only, in White.Dimensions & Weight Indoor Unit "
            "Weight (kg) 13 kg Outdoor Unit Weight (kg) 30.5 kg Indoor Unit (WxHxD) mm 998x230x328"
        ),
    )
    assert result.capacity_token == "1.5 Ton"
    assert "KG" not in result.title


def test_a_telly_prints_the_size_it_states_and_not_the_weight_of_its_carton() -> None:
    """Row 90: `Capacity / Size: 10.8 kg` is the box, and the row wrote `55 Inch` twice.

    A television is sold in inches; the `Capacity:` label does not make a kilogram figure a size.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="H55K85FX", source="title-parenthetical", confidence="high"),
        product_type="LED TV",
        source_title="Haier 55 Inch Smart Google LED TV (H55K85FX)",
        source_description=(
            "The Haier H55K85FX is a 55-inch smart LED TV.\n\nKey Specifications:\n"
            "• Capacity / Size: 10.8 kg\n• Resolution: 4K ultra HD"
        ),
    )
    assert result.capacity_token == "55 Inch"


def test_a_device_that_only_says_which_air_conditioners_it_runs_prints_no_capacity() -> None:
    """Row 398: `Capacity: Works with 1 Ton and 1.5 Ton UPS-Enabled Haier DC Inverter…`.

    That sentence names the machines the UPS supports, not the size of the thing being sold, and an
    UPS is never sold by the ton -- so the safe answer is that the row stated no capacity.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="", source="fallback", confidence="none"),
        product_type="UPS",
        source_title="Haier Module DC Inverter AC UPS Device White",
        source_description=(
            "The Haier Module DC Inverter AC UPS Device White is an inverter home appliance. "
            "Key Specifications:\n• Capacity: Works with 1 Ton and 1.5 Ton UPS-Enabled Haier DC "
            "Inverter\n• Power Consumption: ~450 Watts (2 Amps)"
        ),
    )
    assert result.capacity_token == ""
    assert " Ton" not in result.title


def test_a_washing_machine_is_still_sold_in_kg() -> None:
    """The gate refuses a foreign unit, it does not delete a category's own.

    Row 170: `Orient Twister 1150 Top Load Fully Automatic Washing Machine 10 Kg Metallic Silver`.
    """
    result = build_title(
        brand="Orient",
        extraction=ModelExtraction(code="", source="fallback", confidence="none"),
        product_type="Washing Machine",
        source_title="Orient Twister 1150 Top Load Fully Automatic Washing Machine 10 Kg Metallic Silver",
        source_description="A 10 kg fully automatic top load washing machine.",
    )
    assert result.capacity_token == "10 KG"


# --------------------------------------------------------------------------- #
# [Subtype] -- the owner's `SubType:` line, and the type list reading the Description
# --------------------------------------------------------------------------- #
def _haier_ac(source_title: str, source_description: str) -> TitleResult:
    return build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HSU-19HFPCAA", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title=source_title,
        source_description=source_description,
    )


def test_a_subtype_line_in_the_description_fills_the_subtype_slot() -> None:
    """He writes the sub-type, the Title prints it -- in the subtype position, not after the code.

    The row states no type word of its own, so today this Title ships bare: the slot is the only
    place `Heat & Cool` belongs, between the inverter signal and the category name.
    """
    result = _haier_ac(
        "Haier Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
        "Model: HSU-19HFPCAA\nSubType: Heat & Cool",
    )
    assert result.subtype_from == "label"
    assert result.title == (
        "Haier 1.5 Ton White Inverter Heat & Cool Air Conditioner - HSU-19HFPCAA "
        "- 10 Year Compressor Warranty"
    )


def test_a_subtype_line_replaces_the_word_the_list_would_have_guessed() -> None:
    """The line is the authority for that row, so it never merges with the guess.

    A Title saying `Split` next to `SubType: Cassette` is him correcting the sheet's own word; if
    the builder printed both, the Title would describe two different machines.
    """
    result = _haier_ac(
        "Haier Split Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
        "Model: HSU-19HFPCAA\nSubType: Cassette",
    )
    assert result.subtype_from == "label"
    assert " Cassette Air Conditioner" in result.title
    assert "Split" not in result.title


def test_a_word_the_subtype_line_claims_is_not_resold_as_the_series_keyword() -> None:
    """Once the slot owns `Split`, the feature path must not print it again behind the code.

    This is the whole leak: a type word that reaches the Title through the feature slot lands after
    the model code, where a series name belongs.
    """
    result = _haier_ac(
        "Haier Split Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
        "Model: HSU-19HFPCAA\nSubType: Split Heat & Cool",
    )
    assert result.title.count("Split") == 1
    assert result.title == (
        "Haier 1.5 Ton White Inverter Split Heat & Cool Air Conditioner - HSU-19HFPCAA "
        "- 10 Year Compressor Warranty"
    )


def test_the_type_list_reads_a_word_the_description_states_when_the_title_does_not() -> None:
    """No line, no guessing from him -- but the row DID say it, one column over.

    `heat and cool` in the prose is the same statement as `Heat & Cool`, and 109 AC rows state a
    type word only in the Description.  The slot's own label prints, in group order after the word
    the Title already gave.
    """
    result = _haier_ac(
        "Haier Split Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
        "Model: HSU-19HFPCAA\nReversible unit with heat and cool mode.",
    )
    assert result.subtype_from == "list"
    assert result.title.count("Cool") == 1
    assert result.title == (
        "Haier 1.5 Ton White Inverter Split Heat & Cool Air Conditioner - HSU-19HFPCAA "
        "- 10 Year Compressor Warranty"
    )


def test_a_subtype_line_that_states_nothing_new_changes_nothing_and_says_so() -> None:
    """`SubType: Air Conditioner` is the category name, not a sub-type -- so the row must not move.

    He checks these lines by hand, so the report needs to be able to name the rows where a line he
    wrote added no words at all.
    """
    with_line = _haier_ac(
        "Haier Split Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
        "Model: HSU-19HFPCAA\nSubType: Air Conditioner",
    )
    without_line = _haier_ac(
        "Haier Split Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
        "Model: HSU-19HFPCAA",
    )
    assert with_line.title == without_line.title
    assert with_line.subtype_from != "label"
    assert with_line.subtype_label_added is False


def test_a_word_the_description_negates_never_becomes_a_type_word() -> None:
    """"Not electric, gas only" says NO to Electric and YES to Gas in one breath.

    A phrase match over the whole Description reads that sentence as an electric machine, so the
    shop's `Attribute_Geyser Type` ships `Electric` for a gas geyser -- a wrong value inside a
    closed list, which is the very failure the attribute layer guards against by listing negations
    before their positives (attributes.py).  Reading the row clause by clause is the same guard.
    """
    result = build_title(
        brand="Nasgas",
        extraction=ModelExtraction(code="NG-1100", source="title-parenthetical", confidence="high"),
        product_type="Geyser",
        source_title="Nasgas Water Heater 11 Ltr Copper (NG-1100)",
        source_description="The Nasgas NG-1100 is a copper-tank geyser. Not electric, gas only.",
    )
    assert "Electric" not in result.title
    assert result.subtype_token == "Gas"
    assert " Gas Geyser" in result.title


def test_a_negation_reaches_only_the_clause_it_sits_in() -> None:
    """`No Frost` is a phrase, not a `not` -- and a negation does not blind the clause after it.

    Cut too coarsely, the guard would refuse every word after the first `no` and the row would ship
    with no type at all.  The negation governs its own clause and nothing else.
    """
    result = build_title(
        brand="Nasgas",
        extraction=ModelExtraction(code="NG-1101", source="title-parenthetical", confidence="high"),
        product_type="Geyser",
        source_title="Nasgas Water Heater 11 Ltr Copper (NG-1101)",
        source_description="No Frost insulation on the tank, electric element, 11 litre capacity.",
    )
    assert result.subtype_token == "Electric"
    assert " Electric Geyser" in result.title


def test_a_subtype_line_that_repeats_the_model_code_prints_the_code_once() -> None:
    """A vendor pasting the SKU into his own line must not ship a Title with the code twice.

    Two of the same code in one Title is a row that shadows itself on the shelf.
    """
    result = build_title(
        brand="Dawlance",
        extraction=ModelExtraction(code="DT-1030", source="title-parenthetical", confidence="high"),
        product_type="Refrigerator",
        source_title="Dawlance Inverter Refrigerator 10 Cu Ft White (DT-1030)",
        source_description="Model DT-1030.\nSubType: DT-1030 Double Door",
    )
    assert result.title.count("DT-1030") == 1
    assert result.subtype_token == "Double Door"
    assert " Double Door Refrigerator" in result.title


def test_a_subtype_line_wrapped_in_html_is_still_read() -> None:
    """These sheets arrive with `<b>` around their labels; the line is no less his for the markup."""
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HSU-21", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier Inverter Air Conditioner 1.5 Ton White (HSU-21)",
        source_description="<p><b>SubType:</b> Heat &amp; Cool</p>",
    )
    assert result.subtype_from == "label"
    assert "Heat" in result.title


def test_a_subtype_line_that_is_a_sentence_is_refused_and_says_why() -> None:
    """A value longer than a sub-type is a vendor answering a different question.

    Printing it would fold his whole paragraph into the Title -- one real sheet row reached 249
    characters this way -- and a Title is a product's name, not its spec sheet.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HSU-22", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier Inverter Air Conditioner 1.5 Ton White (HSU-22)",
        source_description=(
            "SubType: Heat & Cool with a 5 Star Energy Rating, Copper Condenser, "
            "Inverter Compressor and Self Cleaning Filter"
        ),
    )
    assert len(result.title) < 130
    assert result.subtype_from != "label"
    assert "words long" in result.subtype_label_note


def test_a_word_left_beside_the_type_phrase_goes_with_the_phrase() -> None:
    """`Classic Split` is one statement about the machine; taking `Split` must not sell `Classic`.

    Row 325 of the sheet.  The curated guesser read the word standing beside the type as a line name,
    so once `Split` moved into `[Subtype]` the row shipped `- HES-2421S Classic` -- a stranded half
    of a phrase reading as a name the shop never sold.  A neighbour is only a name when the run's
    vote proves it for that brand; Homage proved nothing here, so silence is the answer and the QC
    report names the words that went missing.
    """
    result = build_title(
        brand="Homage",
        extraction=ModelExtraction(code="HES-2421S", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Homage Classic Split Inverter Air Conditioner 2.0 Ton (HES-2421S)",
        source_description=(
            "The Homage HES-2421S is a 2.0 Ton inverter split air conditioner. Key features include "
            "t3 climate type, dc inverter up to 60% energy efficient, WiFi Smart Control, "
            "Ampere Lock Mechanism."
        ),
    )
    assert "Classic" not in result.title
    assert result.title == (
        "Homage 2 Ton Inverter Split Air Conditioner - HES-2421S - 1 Year Warranty"
    )


# --------------------------------------------------------------------------- #
# [Subtype] -- the `SubType:` line answers ONE question, not the whole slot
# --------------------------------------------------------------------------- #
def test_a_label_answering_a_second_question_leaves_the_first_answer_standing() -> None:
    """`Split` says the shape, `Heat & Cool` says the cycle -- one machine, two facts, one Title.

    The line used to wipe the slot it touched: a row reading `Haier Split ...` above
    `SubType: Heat & Cool` shipped without its `Split`, and DigiMall's
    `Attribute_Air Conditioner Type` -- matched out of this Title -- fell from `Split` to empty.
    The line is the owner's authority for the question IT answers, not for the ones the type list
    already answered from the same row.
    """
    result = _haier_ac(
        "Haier Split Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
        "Model: HSU-19HFPCAA\nSubType: Heat & Cool",
    )
    assert result.subtype_from == "label"
    assert result.subtype_token == "Split Heat & Cool"
    assert " Split Heat & Cool Air Conditioner" in result.title


def test_a_merged_label_prints_in_the_order_the_type_table_uses() -> None:
    """Two groups answer two questions, and the table's group order is the Title's word order.

    A merge that printed the line first would read `Heat & Cool Split Air Conditioner` on half the
    sheet and the shop's own order on the rest -- one spelling per fact, in one order, always.
    """
    result = _haier_ac(
        "Haier Split Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
        "Model: HSU-19HFPCAA\nSubType: Heat and Cool",
    )
    assert result.subtype_token == "Split Heat & Cool"


def test_a_label_written_with_punctuation_prints_the_words_not_the_marks() -> None:
    """`SubType: Split, Heat & Cool.` is two type words wearing the vendor's commas.

    The value's END punctuation already went; a mark INSIDE the value travelled into the Title
    whole -- `Split,` matched no word guard (it is not the word `Split`), so the shelf read the
    comma.  A sub-type is words; the punctuation around them is handwriting, not content.
    """
    result = _haier_ac(
        "Haier Split Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
        "Model: HSU-19HFPCAA\nSubType: Split, Heat & Cool.",
    )
    assert result.subtype_token == "Split Heat & Cool"
    assert "," not in result.title


def test_a_label_written_in_lower_case_prints_the_shop_s_own_spelling() -> None:
    """`SubType: heat & cool` is the same fact typed quietly -- the Title must not shout it half-case.

    The tidy step capitalizes a value's first letter, which left rows shipping `Heat & cool` -- a
    fact spelled two ways in one Title.  The repair is not a spelling table authored here: the
    type list's own label and the platform Type column's own value ARE the spelling, and words that
    match one (case-blind) print AS one.
    """
    result = _haier_ac(
        "Haier Inverter Air Conditioner 1.5 Ton White (HSU-19HFPCAA)",
        "Model: HSU-19HFPCAA\nSubType: heat & cool",
    )
    assert result.subtype_token == "Heat & Cool"
    assert " Heat & Cool Air Conditioner" in result.title
    assert "Heat & cool" not in result.title


def test_the_description_answers_a_group_the_title_leaves_empty() -> None:
    """One column naming the type is the row naming it: 154 group answers on this sheet come only
    from the prose, and the ad never spelled them (`Side By Side` rows say the type nowhere else).
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HSU-20", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier Inverter Air Conditioner 2 Ton White (HSU-20)",
        source_description="A floor standing unit with heat and cool operation.",
    )
    assert result.subtype_token == "Floor Standing Heat & Cool"
    assert result.subtype_conflicts == ()


def test_two_columns_that_answer_one_question_differently_answer_neither() -> None:
    """`Cassette` in the ad and `split` in the prose is one row claiming two machines.

    The vendor sentence `... is a X Ton DC Inverter split air conditioner` stands in 204
    Descriptions on this sheet, and six of those rows' Titles sell a cassette -- so no column may be
    believed over the other here, and guessing one would print a WRONG value in the platform's closed
    `Attribute_Air Conditioner Type` (owner ruling: a mistake in the sheet is his to make, not ours
    to invent).  The slot stays empty, both candidates travel to the QC report, and his decision --
    written as `SubType: Cassette`, or in the decisions file -- is the only thing that fills it.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HBU-18HE", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier 4 Way Cassette DC Inverter Air Conditioner 1.5 Ton White (HBU-18HE)",
        source_description=(
            "The Haier HBU-18HE/DC-DC Inverter Cassette Type Air Conditioner (H&C) is a 1.5 Ton "
            "DC Inverter split air conditioner, in White."
        ),
    )
    assert result.subtype_token == ""
    assert result.subtype_conflicts == (("Cassette", "Split"),)
    assert "Cassette" not in result.title
    assert "Split" not in result.title


def test_a_longer_platform_spelling_of_the_same_type_is_not_a_conflict() -> None:
    """The ad says `Split` and the prose says `Wall Mounted Split`: one machine, two spellings.

    Not every disagreement is a contradiction -- 14 rows on this sheet answer the mounting question
    with one value nested inside the platform's longer label for it, and the longer spelling is what
    the closed list carries, so the row takes it without being flagged.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HSU-13HFA", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier Split T3 Air Conditioner 1 Ton White (HSU-13HFA)",
        source_description="Haier T3 wall mounted split air conditioner, 1 ton, in White.",
    )
    assert result.subtype_conflicts == ()
    assert result.subtype_token == "Wall Mounted Split"


def test_two_columns_naming_one_machine_in_two_pieces_answer_the_platforms_value() -> None:
    """The ad says `Split`, the row's own `Type:` bullet says `Wall Mounted`: ONE machine, in pieces.

    `Wall Mounted Split` is the platform's own third air-conditioner value, and these two words are
    its two runs, so the row is not claiming two machines and is not a decision owed -- 14 rows on
    this sheet say it this way, and calling it a contradiction emptied 14 filled
    `Attribute_Air Conditioner Type` cells.  The union rule is read off the closed list: `Split` and
    `Floor Standing` are tested against the same list, find no value holding both, and stay a
    conflict.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HSU-13HFA", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier Split T3 Air Conditioner 1 Ton (HSU-13HFA)",
        source_description=(
            "The Haier 1.0 Ton T3 Inverter (HSU-13HFAB) is a 1 Ton split air conditioner.\n"
            "• Type: Wall Mounted"
        ),
    )
    assert result.subtype_conflicts == ()
    assert result.subtype_token == "Wall Mounted Split"
    assert result.subtype_undecided_columns == ()
    assert "Split" not in result.title.replace("Wall Mounted Split", "")


def test_a_written_subtype_line_clears_the_flag_that_asked_for_it() -> None:
    """The flag's own cure works: write `SubType: Cassette` and the row stops being a decision owed.

    It is the whole point of handing the 33 rows back to the owner -- and a QC report that keeps
    saying "the slot and its Attribute_* cell are left empty" under a Title that ships the word he
    wrote is worse than no report at all.
    """
    source_description = (
        "The Haier HBU-18HE/DC-DC Inverter Cassette Type Air Conditioner (H&C) is a 1.5 Ton DC "
        "Inverter split air conditioner, in White.\nSubType: Cassette"
    )
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HBU-18HE", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier 4 Way Cassette DC Inverter Air Conditioner 1.5 Ton White (HBU-18HE)",
        source_description=source_description,
    )
    assert result.subtype_conflicts == ()
    assert result.subtype_undecided_columns == ()
    assert result.subtype_token == "Cassette"
    assert "Split" not in result.title


def test_a_written_subtype_line_clears_the_flag_even_by_naming_a_third_type() -> None:
    """He may settle a disagreement with a word NEITHER column fought over -- `SubType: Cassette`.

    Row 441's ad says `Floor Standing` and its vendor sentence says `split`, and a Gree 24000 BTU
    cabinet is neither.  The line is what settles the question, not a vote between the two candidates,
    so keying the dismissal on the disputed WORDS leaves the row flagged -- claiming the slot and its
    `Attribute_Air Conditioner Type` cell are empty -- under a Title that prints exactly what he wrote.
    """
    source_title = "Gree 24000 BTU Floor Standing 2.0 Ton Air Conditioner (GF-24ISH)"
    source_description = "The Gree GF-24ISH is a 2.0 Ton split air conditioner.\nSubType: Cassette"
    disputed = build_title(
        brand="Gree",
        extraction=ModelExtraction(code="GF-24ISH", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title=source_title,
        source_description=source_description,
    )
    assert disputed.subtype_token == "Cassette"
    assert disputed.subtype_conflicts == ()
    assert disputed.subtype_undecided_columns == ()
    # ...and the same row without his line is still a decision owed, with both words spent.
    open_row = build_title(
        brand="Gree",
        extraction=ModelExtraction(code="GF-24ISH", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title=source_title,
        source_description="The Gree GF-24ISH is a 2.0 Ton split air conditioner.",
    )
    assert open_row.subtype_conflicts == (("Floor Standing", "Split"),)
    assert open_row.subtype_undecided_columns == ("Attribute_Air Conditioner Type",)
    assert "Floor Standing" not in open_row.title and "Split" not in open_row.title


def test_a_hyphenated_type_prints_the_platforms_own_spelling() -> None:
    """`Freezer-on-top` is DigiMall's `Freezer-On-Top`: one fact, and one spelling of it on the shelf.

    32 rows wrote the value with their own hyphens while 135 wrote it the platform's way, and the
    second seat reader printed the row's letters.  The value is the platform's, so its spelling is
    too; a phrase the platform does not list keeps the row's letters, because inventing a spelling
    is worse than keeping one (owner ruling, 2026-10-23).
    """
    result = build_title(
        brand="Dawlance",
        extraction=ModelExtraction(code="9173-WB", source="title-parenthetical", confidence="high"),
        product_type="Refrigerator",
        source_title=(
            "DAWLANCE Acce Pro Glass Door Inverter Freezer-on-top Refrigerator (9173-WB)-Crimson Red"
        ),
        source_description=(
            "Dawlance 9173-WB Acce Pro 18 Cu Ft Glass Door inverter refrigerator, in Crimson Red."
        ),
    )
    assert result.subtype_from == "class"
    assert result.subtype_token == "Freezer-On-Top"
    assert "Freezer-on-top" not in result.title


def test_the_title_still_answers_a_group_the_description_says_nothing_about() -> None:
    """Description-first is an order, not a ban: a group the prose never mentions keeps its ad word.

    Most rows write their type only in the Title -- reversing the order must not lose the type
    for them, only settle it when the two columns disagree.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HSU-20", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier Split Inverter Air Conditioner 2 Ton White (HSU-20)",
        source_description="Copper condenser, 5 Star energy rating.",
    )
    assert result.subtype_token == "Split"
    assert " Split Air Conditioner" in result.title




# --------------------------------------------------------------------------- #
# [Model] -- a row with no code is sold by the name and number it wrote
# --------------------------------------------------------------------------- #
def _fallback_dawlance(source_title: str, source_description: str = "") -> TitleResult:
    return build_title(
        brand="Dawlance",
        extraction=ModelExtraction(code="", source="fallback", confidence="none"),
        product_type="Air Conditioner",
        source_title=source_title,
        source_description=source_description,
    )


def test_a_number_before_its_name_word_still_becomes_the_stock_code() -> None:
    """Row 206: `Dawlance 30 Econo + Inverter Split Air Conditioner 1.5 Ton`.

    The shop says `Econo 30`; the number the sheet wrote first is the same number, and a SKU built
    from the tonnage digits instead sold this row as a machine it is not.
    """
    result = _fallback_dawlance(
        "Dawlance 30 Econo + Inverter Split Air Conditioner 1.5 Ton",
        "1.5 Ton split inverter air conditioner.",
    )
    assert result.title == (
        "Dawlance 1.5 Ton Inverter Split Air Conditioner - Econo 30 - 12 Year Compressor Warranty"
    )


def test_every_word_of_a_two_word_name_travels_with_the_number() -> None:
    """Row 250: `Dawlance Chrome Plus 45 Inverter Split Air Conditioner 2 Ton` is a Chrome Plus."""
    result = _fallback_dawlance(
        "Dawlance Chrome Plus 45 Inverter Split Air Conditioner 2 Ton",
        "2 Ton inverter split air conditioner.",
    )
    assert " - Chrome Plus 45 - " in result.title


def test_a_number_written_in_its_own_unit_is_a_size_and_never_a_name() -> None:
    """Row 169: `Orient Roast Microwave Oven Solo 23 Ltr Black`.

    `23 Ltr` is the capacity, and `Solo` is the type word -- neither is a stock number, so no
    identity may be invented out of them and the row keeps the name-only slot it had before.
    """
    assert word_identity("Orient Roast Microwave Oven Solo 23 Ltr Black", "Orient") == ""
    assert word_identity("Dawlance Frost 30 Inverter Split Air Conditioner", "Dawlance") == "Frost 30"
    assert word_identity("PEL 215 Pearl 2 Taps Water Dispenser White", "PEL") == "Pearl 215"


def test_a_real_model_code_outranks_a_word_identity() -> None:
    """Row 213 writes `(9173)`: a code the vendor printed beats any reading of the words around it.

    The identity slot is only ever reached by a row that has no code at all.
    """
    result = build_title(
        brand="Dawlance",
        extraction=ModelExtraction(code="9173", source="title-parenthetical", confidence="high"),
        product_type="Refrigerator",
        source_title="Dawlance Acce Glass Door Freezer-On-Top Refrigerator (9173)-Cool Inverter White",
        source_description="A glass door refrigerator.",
    )
    assert " - 9173 " in result.title


def test_a_number_glued_into_a_dashed_part_number_is_not_a_stock_number() -> None:
    """Row 181 writes `PMO-23 Kitchen Pro GR` inside an unclosed bracket -- not a name and a number.

    The `23` belongs to the part number `PMO-23` (the sheet spells that joiner an en dash); taking it
    for a stock number shipped this row as `Kitchen Pro GR 23`, which is the debris of a broken Title
    rather than the shop's name for it.
    """
    assert word_identity("PEL Kitchen Pro Grill Microwave Oven (PMO-23 Kitchen Pro GR", "PEL") == ""


def test_a_model_line_written_as_prose_gives_up_the_code_inside_it() -> None:
    """Row 257: the vendor's `Model:` line answered `Inverter Frost 30: Yes`.

    `: Yes` is that sheet's checkbox column and `Inverter` is a drive word, so the code inside the
    sentence is `Frost 30` -- the name the shop sells it by.  A line that already holds a code is
    returned untouched, because `Icon 3 Taps Water Dispenser` really is Orient's `Icon`.
    """
    prose = ModelExtraction("Inverter Frost 30", "description-model-line", "high")
    assert without_leading_type_words(prose).code == "Frost 30"
    clean = ModelExtraction("Icon 3 Taps Water Dispenser", "description-model-line", "high")
    assert without_leading_type_words(clean).code == "Icon 3 Taps Water Dispenser"

    result = build_title(
        brand="Dawlance",
        extraction=without_leading_type_words(
            ModelExtraction("Inverter Frost 30", "description-model-line", "high")
        ),
        product_type="Air Conditioner",
        source_title="Dawlance Frost 30 Inverter Split Air Conditioner 1.5 Ton White (Cool Only)",
        source_description="1.5 Ton split air conditioner.",
    )
    assert " - Frost 30 - " in result.title


def test_a_peeled_model_line_keeps_a_bare_number_because_the_row_wrote_it() -> None:
    """`Model: Inverter 30` -> `30`.  A bare number is the vendor's own answer, not a size.

    Only a number written WITH its unit is a size (`1.5 Ton`); this sheet also writes real codes as
    bare digits (`Model: Water Dispenser 2101`), and refusing those would drop a model number a
    shopper searches for and quietly degrade the row to a made-up fallback SKU.
    """
    prose = ModelExtraction("Inverter 30", "description-model-line", "high")
    assert without_leading_type_words(prose).code == "30"
    digits = ModelExtraction("Water Dispenser 2101", "description-model-line", "high")
    assert without_leading_type_words(digits).code == "2101"


def test_the_name_words_a_row_wrote_after_its_number_keep_their_place() -> None:
    """Row 682: `Midea ECM 3500 Plus DC Air Cooler` sells itself as `ECM 3500 Plus DC`.

    A number the row wrote in the middle of its name must not drag the words behind it across the
    front -- the run is read in the order the shop printed it.
    """
    assert word_identity("Midea ECM 3500 Plus DC Air Cooler", "Midea") == "ECM 3500 Plus DC"


def test_a_colour_word_never_becomes_part_of_a_stock_name() -> None:
    """`White 20` is a paint and a size, not a name -- row 533 sold that row as `White 20`."""
    assert word_identity("Gree White 20 Split Air Conditioner 1.5 Ton", "Gree") == ""


def test_a_number_after_a_unit_word_is_a_second_size_and_never_a_name() -> None:
    """`Washing Machine 7 Kg 1000 RPM` states a weight and a spin speed, not a stock number.

    A unit only shields the number written in front of it, so `1000` was read as the row's name and
    the row shipped as `Kg 1000 RPM` -- a size word standing where a name belongs.
    """
    assert word_identity("LG Inverter Washing Machine 7 Kg 1000 RPM", "LG") == ""
    assert word_identity("Gree Inverter Split Air Conditioner 1.5 Ton 9000 BTU White", "Gree") == ""


def test_the_prose_after_a_stock_number_is_not_taken_as_its_name() -> None:
    """`Crompton Arithmetic Neo 120 Watt Ceiling Fan` states a wattage, not a stock number.

    The unbounded run collected the whole tail of the Title -- unit word, category and all -- into
    the model slot.  A number written in its own unit is a size, so this row says nothing nameable.
    """
    identity = word_identity("Crompton Arithmetic Neo 120 Watt Ceiling Fan", "Crompton")
    assert identity == ""


def test_a_name_never_reaches_over_the_dashes_into_the_next_clause() -> None:
    """`Gree Eco 15 - Frost Split Air Conditioner` is `Eco 15`, not `Eco 15 Frost`.

    ` - ` is the boundary the Title formula itself is written with; the word on its far side belongs
    to another slot and welding it in invents a name the shop never said.
    """
    assert word_identity("Gree Eco 15 - Frost Split Air Conditioner", "Gree") == "Eco 15"


def test_a_number_written_as_an_inch_mark_is_a_size() -> None:
    """`Weston Bravia 55" Split Air Conditioner` sells a 55-inch machine, not a `Bravia 55`."""
    assert word_identity('Weston Bravia 55" Split Air Conditioner', "Weston") == ""


def test_a_model_line_of_a_number_and_a_unit_is_still_no_code() -> None:
    """`Model: Inverter 1.5 Ton` is the vendor stating the size in the wrong cell.

    Leaving it alone put a drive word and a duplicated capacity in the model slot and let the
    Description claim a model number the row never gave.  A remainder of number-plus-unit is no code
    at all, so the row goes the way of every other codeless row -- and `12EM/DU`, which opens with a
    digit and IS a code, survives the same test untouched.
    """
    prose = ModelExtraction("Inverter 1.5 Ton", "description-model-line", "high")
    peeled = without_leading_type_words(prose)
    assert peeled.code == "" and peeled.confidence == "none"
    bare = ModelExtraction("18000 BTU", "description-model-line", "high")
    assert without_leading_type_words(bare).confidence == "none"
    other = ModelExtraction("Non Inverter 9000 BTU", "description-model-line", "high")
    assert without_leading_type_words(other).confidence == "none"
    real = ModelExtraction("Inverter 12EM/DU", "description-model-line", "high")
    assert without_leading_type_words(real).code == "12EM/DU"


def test_a_warranty_written_in_months_states_no_stock_number() -> None:
    """`Hisense 24 Months Warranty LED TV` says how long the cover runs, not what the set is called.

    A duration is a measure like a tonnage, so its digits are never the stock number, and `Months`
    is not a name word.
    """
    assert word_identity("Hisense 24 Months Warranty LED TV", "Hisense") == ""
    assert word_identity("Dawlance 18 Months Compressor Warranty Freezer", "Dawlance") == ""


def test_a_cooling_type_written_around_a_number_is_not_that_number_s_name() -> None:
    """`Rattan Frost Free 250 Deep Freezer` is a 250-litre Frost Free machine, not a `Frost Free 250`.

    The owner's own ruling kills `Frost` when the row wrote `No Frost`; the two-word type written in
    front of a size may not walk back in through the identity slot.
    """
    assert word_identity("Rattan Frost Free 250 Deep Freezer", "Rattan") == ""


def test_a_category_word_the_type_list_knows_may_not_stand_as_a_name() -> None:
    """`Royal 1200 Fan`: `fan` carries no model information, exactly as `sku_handle` already says.

    The identity list reuses that vocabulary instead of keeping a second copy of it.
    """
    assert word_identity("Royal 1200 Fan", "Royal") == ""


# --------------------------------------------------------------------------- #
#  T9 -- the Series seat reads the slot the sheet wrote the name in
# --------------------------------------------------------------------------- #
def _build(title: str, description: str = "") -> TitleResult:
    extraction = extract_model(title, description or title)
    return build_title(
        title.split(maxsplit=1)[0], extraction, "Refrigerator", title, description or title
    )


def test_the_word_beside_the_model_code_is_the_series_not_the_colour() -> None:
    """`... Pearl Copper Steel Door ... - 9173WB Chrome - 12 Years ...` is a Chrome.

    The sheet writes `[Model] [Series]` inside one clause, so the word standing next to the code IS
    its answer to "which line is this".  The old reader took the FIRST capitalised word in the Title
    instead -- char 18, the colourway -- printed `Pearl` as the Series, swallowed it as an already
    printed colour, and `Chrome` was never looked at.
    """
    result = _build(
        "Dawlance 12 Cu Ft Pearl Copper Steel Door Direct Cool Non-Inverter Refrigerator "
        "- 9173WB Chrome - 12 Years Compressor Warranty"
    )
    assert result.series_token == "Chrome"
    assert " - 9173WB Chrome - " in result.title


def test_a_name_written_BEFORE_the_code_is_found_too() -> None:
    """`Orient 13 Cu Ft Triangle Black ... - Ultron 380I GD - 3 Years ...` is an Ultron.

    Same slot, the other side of the code: `GD` is a colour code, so nothing survives after `380I`
    and the word in front of it is the name.  `Triangle` is part of the colourway phrase and died
    here as the Series while `Ultron` vanished from the Title.
    """
    result = _build(
        "Orient 13 Cu Ft Triangle Black Glass Door Direct Cool Inverter Refrigerator "
        "- Ultron 380I GD - 3 Years Compressor Warranty"
    )
    assert result.series_token == "Ultron"
    assert "Ultron" in result.title


def test_a_trailing_plus_belongs_to_the_name() -> None:
    """`Avante+` and `Chrome+` are different products from `Avante` and `Chrome`.

    The sign is the row's own punctuation, so the name ships with it or it ships wrong.
    """
    plus = _build(
        "Dawlance 12 Cu Ft Cloud White Glass Door Direct Cool Inverter Refrigerator "
        "- 9178LF Avante+ - 12 Years Compressor Warranty"
    )
    assert plus.series_token == "Avante+"
    assert "Avante+" in plus.title


def test_a_colour_word_can_never_become_the_series_even_when_it_is_first() -> None:
    """Strip the real name out of the slot and the answer is silence, not `Pearl`.

    A row that states no name next to its code has no line name in it; the colour the shop painted
    the door with is not one, and inventing it costs the buyer the truth for a guess.
    """
    result = _build(
        "Dawlance 12 Cu Ft Pearl Copper Steel Door Direct Cool Non-Inverter Refrigerator "
        "- 9173WB - 12 Years Compressor Warranty"
    )
    assert result.series_token == ""
    assert result.title == (
        "Dawlance 12 Cu Ft Pearl Copper Non-Inverter Refrigerator - 9173WB "
        "- 12 Year Compressor Warranty"
    )


def test_a_bare_number_sheet_names_no_series() -> None:
    """Adversarial: a Title with a code, no label and no name beside the code stays silent.

    Every leftover word here (`Steel`, `Door`, `Direct`, `Cool`) is material or type -- none is a
    line name -- and the seat must stay empty rather than sell a material as a model.
    """
    result = _build(
        "Dawlance 12 Cu Ft Steel Door Direct Cool Non-Inverter Refrigerator "
        "- 9173 - 12 Years Compressor Warranty"
    )
    assert result.series_token == ""


def test_a_line_name_the_guards_refuse_is_still_reported_as_dropped() -> None:
    """`Twin Cooling Plus` cannot pass the type-word guard, so it must at least leave evidence.

    A silent deletion is the bug: the QC flag is what tells him the row states a name the pipeline
    could not read.
    """
    result = _build(
        "Samsung 19 Cu Ft Silver French Door Steel Door No Frost Inverter Refrigerator "
        "- RF49A5202SL Twin Cooling Plus - 10 Years Compressor Warranty"
    )
    assert result.series_token == ""
    assert "twin" in result.dropped_words


def test_a_size_written_where_the_name_belongs_states_no_line() -> None:
    """`Washing Machine - 10kg (KWM-211059)`: the seat already said `10 KG` -- it cannot be a name.

    The row wrote its size into the clause the formula reserves for `[Model] [Series]`, and a size is
    the one fact the Title prints twice over -- once as the number and once as the digits behind it.
    """
    result = build_title(
        brand="Kenwood",
        extraction=ModelExtraction(
            code="KWM-211059", source="title-parenthetical", confidence="high"
        ),
        product_type="Washing Machine",
        source_title="Kenwood Top Load Semi Automatic Twin Tub Washing Machine - 10kg (KWM-211059)",
        source_description="Kenwood KWM-211059 semi automatic washing machine, 10 kg.",
        capacity="10 KG",
    )
    assert result.series_token == ""
    assert "10kg" not in result.title


def test_a_paint_word_standing_in_front_of_the_colour_is_never_the_line_name() -> None:
    """`Dawlance Inverter Vertical Freezer Cloud White` is a WHITE freezer, not a `Cloud` one.

    `Cloud` is a colour word in the repo's own table and it stands in the paint position; R1 puts it
    with its colour and leaves the seat empty rather than naming a line after a finish.
    """
    result = build_title(
        brand="Dawlance",
        extraction=ModelExtraction(
            code="VF-1035-GD-INV", source="title-parenthetical", confidence="high"
        ),
        product_type="Deep Freezer",
        source_title="Dawlance Inverter Vertical Freezer Cloud White (VF-1035-GD-INV)",
        source_description="Dawlance vertical freezer, 11 Cu Ft, 12 Year Compressor Warranty.",
        capacity="11 Cu Ft",
    )
    assert result.series_token == ""


def test_a_name_written_AWAY_from_the_paint_keeps_its_seat() -> None:
    """The same rule leaves `Haier Pearl DC Inverter Air Conditioner 1.5 Ton Silver` alone.

    `Pearl` is a colour word too, but it stands in the name position, four words clear of the paint:
    swallowing every colour word a row writes would delete Haier's real line, and a name is what the
    seat exists for.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HSU-19HFPA", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier Pearl DC Inverter Air Conditioner 1.5 Ton Silver (HSU-19HFPA)",
        source_description="Haier 1.5 Ton DC Inverter Air Conditioner with a 10 Year Compressor Warranty.",
        capacity="1.5 Ton",
    )
    assert result.series_token == "Pearl"


def test_a_type_word_the_seat_refuses_still_reaches_the_title() -> None:
    """`Haier ... Freezer-On-Top Refrigerator 12 CFT - Red (HRF-346 IARA)`: the word moves, it does
    not vanish.  A class word may not sit behind the code where a line name belongs, but DigiMall's
    `Attribute_Refrigerator Type` is matched out of the Title -- so `[Subtype]` carries it.
    """
    result = _build(
        "Haier Digital Inverter Freezer-On-Top Refrigerator 12 CFT - Red (HRF-346 IARA) "
        "- 10 Years Compressor Warranty"
    )
    assert "Freezer-On-Top" in result.title
    assert result.series_token != "Freezer-On-Top"
    assert result.subtype_from == "class"


def test_a_series_label_does_not_blind_the_builder_to_the_type_the_title_writes() -> None:
    """Row 505's shape: the vendor ANSWERED the series question, so the old gate went quiet.

    The class-phrase rung used to run only when the leftover-word guesser spoke -- and a row whose
    series slot was filled by its own `Series:` line never reached it: `Side-By-Side` fell out of
    the Title and DigiMall's `Attribute_Refrigerator Type` shipped EMPTY.  The `[Subtype]` slot
    answers for itself, independent of whatever the series reader did (owner ruling).
    """
    result = build_title(
        brand="Dawlance",
        extraction=ModelExtraction(code="S-9173WB", source="title-parenthetical", confidence="high"),
        product_type="Refrigerator",
        source_title="Dawlance 12 Cu Ft Side-By-Side Refrigerator Black (S-9173WB)",
        source_description="Model: S-9173WB\nSeries: T-Door",
    )
    assert result.subtype_from == "class"
    assert "Side-By-Side" in result.title
    assert result.subtype_token == "Side-By-Side"


def test_a_one_word_type_the_platform_lists_reaches_the_subtype_slot_too() -> None:
    """`Haier Cassette Inverter Air Conditioner 2 Ton`: `Cassette` IS the platform's AC Type.

    DigiMall enumerates `Cassette` in `Attribute_Air Conditioner Type` and six Titles on this sheet
    sell it, while the builder's own group table stopped at the four mountings its author wrote -- so
    the word had no seat: the reader answered the mounting question from the vendor's boilerplate and
    `Cassette` fell out of the Title.  The group is now read WITH the platform's list beside it, so the
    word takes its place in `[Subtype]` from the type table itself.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HCD-24C", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier Cassette Inverter Air Conditioner 2 Ton White (HCD-24C)",
        source_description="Haier 2 Ton cassette air conditioner with a 10 Year Compressor Warranty.",
    )
    assert result.subtype_from == "list"
    assert result.subtype_token == "Cassette"
    assert " Cassette Air Conditioner" in result.title


def test_a_one_word_type_never_stacks_on_the_type_the_row_already_printed() -> None:
    """`Haier Split Cassette ...` is a row contradicting itself, and the Title may answer one
    mounting question once.  `Split` and `Cassette` are two values of the platform's ONE AC Type
    column, and every other value of that column lives in the same shape group -- so a row that
    already prints `Split` cannot gain `Cassette` from the class rung, and the stray word may not
    be resold behind the code as a line name either.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HSU-24C", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier Split Cassette Inverter Air Conditioner 2 Ton White (HSU-24C)",
        source_description="Haier 2 Ton inverter air conditioner with a 10 Year Compressor Warranty.",
    )
    assert result.subtype_token == "Split"
    assert "Cassette" not in result.title


def test_a_one_word_type_orthogonal_to_the_row_s_answers_travels_free() -> None:
    """`PEL 12 Kg Semi Automatic Spinner`: the shop stacks these two every day.

    `Spinner` and `Semi Automatic` both appear in `Attribute_Washing Machine Type`, but that column
    is where the builder's OWN table asks two questions -- drum AND lid (`Twin Tub` and `Top Load`
    sit in different groups) -- so sharing it proves nothing.  The never-stack rule bites only a
    column the groups recognise as exactly one question, and the spinner row keeps its type.
    """
    result = build_title(
        brand="PEL",
        extraction=ModelExtraction(code="PW-120ST", source="title-parenthetical", confidence="high"),
        product_type="Washing Machine",
        source_title="PEL 12 Kg Semi Automatic Spinner Washing Machine White (PW-120ST)",
        source_description="PEL semi-automatic washing machine with a spinner.",
    )
    assert result.subtype_token == "Semi Automatic Spinner"
    assert " Spinner Washing Machine" in result.title


def test_a_denial_written_lowercase_still_never_gets_placed() -> None:
    """`Not side by side, double door` denies one type and states another.

    The prose view (`_clauses()`) is lowercased before it is read, so a denial there IS honoured: a
    denied phrase cannot become the value this row earned in the platform's closed list.
    """
    assert "Side By Side" not in stated_class_phrase(
        "Refrigerator",
        "Haier Inverter Refrigerator 12 CFT, not side by side (HRF-346)",
        "Haier Inverter Refrigerator HRF-346",
    )


def test_no_frost_states_a_type_it_does_not_denied_one() -> None:
    """`No Frost ... Freezer-on-top` -- the `No` belongs to `Frost`, not to the type beside it.

    Read case-blind, `no` would deny the row's own `Freezer-On-Top` and the phrase would never reach
    the Title -- and DigiMall's closed `Attribute_Refrigerator Type` is matched out of that Title, so
    the row would ship `Double Door`, a value it never wrote.  Nine rows on the sheet are this shape.
    The phrase prints in the platform's letters, not the row's hyphens (owner ruling, 2026-10-23).
    """
    assert stated_class_phrase(
        "Refrigerator",
        "Dawlance No Frost Glass Door Inverter Freezer-on-top Refrigerator (DTM-7650 INV GD IoT)",
        "Dawlance Black Inverter Refrigerator DTM-7650",
    ) == "Freezer-On-Top"


def test_a_paint_written_with_a_hyphen_spends_its_first_word_just_the_same() -> None:
    """`Pearl-Copper` is the same paint as `Pearl Copper`, so `Pearl` is spent either way (R1).

    The colour reader answers `Copper` for the hyphenated spelling, and the ban used to read only the
    words that colour split into -- so the sheet's own first word slipped into the name slot whole.
    """
    title = (
        "Dawlance 12 Cu Ft Pearl-Copper Refrigerator - 9173WB Pearl "
        "- 12 Years Compressor Warranty"
    )
    assert beside_model_code(title, "9173WB", frozenset(colourway_words(title, "Copper"))) == (
        "",
        "9173WB Pearl",
    )


def test_a_year_written_where_the_name_belongs_is_not_a_name() -> None:
    """`- 2024 Model -` states a vintage and the word `Model`; neither is a line (R4).

    The seat read `Model`, because the guard read a word as a type only from the tables that spell
    out product types, and `Model` appears nowhere in them.
    """
    result = _build(
        "Falcon 10 Cu Ft Brown Refrigerator - 2024 Model - 1 Year Compressor Warranty"
    )
    assert result.series_token == ""


def test_a_bare_number_clause_names_no_line_when_the_row_states_no_code() -> None:
    """`- 828 New Design -` on a row whose code the pipeline never found: the seat stays empty (R4).

    A number with no letters in it is not the `[Model]` this row resolved, so nothing stands beside
    it, and `Design` -- a word about the machine, not a line -- was read as its name.  Worse, that
    invention outranked the run's proven name, which the seat then crowded out.
    """
    result = _build("Homage 7 Kg Washing Machine - 828 New Design - 1 Year Motor Warranty")
    assert result.series_token == ""


def test_a_spaced_plus_in_front_of_the_code_still_belongs_to_the_name() -> None:
    """`- Avante + 9178LF -`: the sign is the name's, whichever side of the code the row wrote it (R3).

    Read backwards from the code the scan met the lonely sign first and gave up, so `Avante+` shipped
    with no name at all -- and `Avante` and `Avante+` are different products on his shelf.
    """
    result = _build(
        "Dawlance 12 Cu Ft White Deep Freezer - Avante + 9178LF - 2 Years Motor Warranty"
    )
    assert result.series_token == "Avante+"
    assert " Avante+" in result.title


def test_the_inverter_slot_reads_the_signals_the_other_two_readers_already_read() -> None:
    """`categories.py` routes the AC leaf and `attributes.py` fills INV/NON-INV off `T-AI`, `BLDC`,
    `InverterOn`, `brushless` and a glued `non inv`.  A Title reader that knows fewer synonyms prints
    no [Inverter] on a row both other readers call an inverter -- one sheet, three answers."""
    assert extract_inverter("Haier T-AI Air Conditioner 1.5 Ton") == "Inverter"
    assert extract_inverter("Orient BLDC Washing Machine 8 Kg") == "Inverter"
    assert extract_inverter("Gree InverterOn Refrigerator 12 Cu Ft") == "Inverter"
    assert extract_inverter("Dawlance Brushless Washing Machine") == "Inverter"
    assert extract_inverter("Haier DC Inverter Air Conditioner") == "Inverter"
    assert extract_inverter("Dawlance non inv Air Conditioner") == "Non-Inverter"
    assert extract_inverter("Super Asia NON-INV Air Conditioner") == "Non-Inverter"
    # The negation still wins over the positive word hiding inside it.
    assert extract_inverter("Haier Non-Inverter Air Conditioner") == "Non-Inverter"
    assert extract_inverter("Dawlance Frost 30 Air Conditioner") == ""


def test_a_dispenser_keeps_both_its_taps_and_its_litres() -> None:
    """`3 Taps` and `15 Litres` answer different questions; the tank used to be overwritten."""
    extraction = ModelExtraction(
        code="HWD-49332P", source="title-parenthetical", confidence="high"
    )
    result = build_title(
        brand="Homage",
        extraction=extraction,
        product_type="Water Dispenser",
        source_title="Homage 3 Taps Water Dispenser 15 Litres Red (HWD-49332P)",
        source_description="Homage 3 Taps Water Dispenser 15 Litres Red (HWD-49332P)",
    )
    assert result.taps_token == "3 Taps"
    assert result.volume_capacity_token == "15 Ltr"
    # The printed slot still shows the taps until the formula rewrite says otherwise.
    assert result.capacity_token == "3 Taps"


def test_a_series_label_in_the_description_names_the_line() -> None:
    """`Model: HSU-19HFPCAA` + `Series: Thunder Plus` -- his own label is the row's answer."""
    text = (
        "Haier Split Inverter Air Conditioner 1.5 Ton White\n"
        "Model: HSU-19HFPCAA\nSeries: Thunder Plus"
    )
    assert extract_series(text, model="HSU-19HFPCAA") == "Thunder Plus"


def test_a_multi_word_name_before_the_word_series_is_captured_whole() -> None:
    """`Part of the E Luxury Pro Series` names `E Luxury Pro`, not just the word beside `Series`."""
    text = (
        "Kenwood Microwave Oven 25 Ltr\n"
        "Part of the E Luxury Pro Series with fast cooling."
    )
    assert extract_series(text) == "E Luxury Pro"


def test_a_prose_sentence_ending_in_the_word_series_names_no_line() -> None:
    """`the premium series` is a sentence, not a label: no capitalised name stands before it."""
    text = "Haier Air Conditioner 1.5 Ton\nthe premium series for homes."
    assert extract_series(text) == ""


def test_a_word_the_title_already_prints_is_not_sold_again_behind_the_code() -> None:
    """Two readers name the same fact for this Haier row, and the shop was shown it twice.

    `Haier Air Fryer Series Microwave Oven` spells its own line in the sheet's Title and the row's
    Description repeats it (`Category: Convection Air Fryer Series`, `Unique Feature: Built In Air
    Fryer`), so the leftover-word reader and the Air Fryer feature check both hand the name slot the
    same phrase.  The slot was deduped against a snapshot of what the Title printed BEFORE its own
    words went in, so the second copy walked straight through: HEAD shipped
    `... - HMW-30AFS Fryer Air Fryer` (the stranding that snapshot left behind), and clearing the
    stranding without clearing the snapshot ships `... - HMW-30AFS Air Fryer Air Fryer`.
    One fact, one token -- the rule `subtype_line_words` applies to his own `SubType:` line, applied
    to the name slot.
    """
    source_title = "Haier Air Fryer Series Microwave Oven 30 Ltr (HMW-30AFR)"
    source_description = (
        "The Haier HMW-30AFR is a 30 L air fryer microwave oven. It offers touch control controls.\n"
        "Key Specifications:\n"
        "• Capacity: 30 Ltr\n"
        "• Control Type: Touch Control\n"
        "• Category: Convection Air Fryer Series\n"
        "• Unique Feature: Built In Air Fryer"
    )
    extraction = without_leading_type_words(extract_model(source_title, source_description))
    result = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="Microwave Oven",
        source_title=source_title,
        source_description=source_description,
    )
    assert result.title.count("Air Fryer") == 1
    assert result.title == (
        "Haier 30 Ltr Convection Microwave Oven - HMW-30AFR Air Fryer - 1 Year Warranty"
    )


def test_vip_pipe_scenario_a_series_and_model_code() -> None:
    """Scenario A: Series sits in Position 3, Technical Model comes before the key features."""
    extraction = ModelExtraction(code="MSAG2B-12HRDN1-QC0", source="description-model-line", confidence="high")
    result = build_title(
        brand="Midea",
        extraction=extraction,
        product_type="Air Conditioner",
        source_title="Midea Eco MSAG2B-12HRDN1-QC0 DC Inverter AC 1.5 Ton White",
        source_description=(
            "Model: MSAG2B-12HRDN1-QC0\nCapacity: 1.5 Ton\nColor: White\nEco Series\n"
            "Key Specifications:\n"
            "• Golden Fin: Anti-corrosion coating\n"
            "• Dual Filter: High density filter\n"
            "• Fireproof Electric Control Box: Safe housing\n"
            "Warranty: 12 Year Compressor Warranty"
        ),
        title_formula="vip_pipe",
    )
    # Series 'Eco' in Position 3, (White) bracketed
    assert "Midea 1.5 Ton Eco Inverter Air Conditioner (White)" in result.title
    # Technical model code comes right after segment one, before the key features
    assert " | MSAG2B-12HRDN1-QC0 | Anti-corrosion coating | High density filter |" in result.title
    # Warranty still closes the Title
    assert result.title.endswith(" | 12 Year Compressor Warranty")
    # A spec row sells its ANSWER: `Golden Fin: Anti-corrosion coating` prints the coating, because
    # the words before the colon are the table's question, not the feature (measured on the owner's
    # sheets, where that column holds `Screen Size`, `Voltage`, `SubType`).
    assert "Anti-corrosion coating" in result.title
    assert "High density filter" in result.title
    assert result.usp_tokens == ("Anti-corrosion coating", "High density filter", "Safe housing")


def test_vip_pipe_scenario_b_codeless_popular_identity() -> None:
    """Scenario B: Popular identity sits in Position 3, the model part is empty (no duplicate)."""
    extraction = ModelExtraction(code="", source="", confidence="none")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Air Conditioner",
        source_title="Dawlance 15 Econo + Inverter Split Air Conditioner 1 Ton White",
        source_description=(
            "Capacity: 1 Ton\nColor: White\nInverter AC\n"
            "Highlights:\n"
            "• Gold Fin Protection\n"
            "• Low Voltage Startup\n"
            "Warranty: 12 Year Compressor Warranty"
        ),
        title_formula="vip_pipe",
    )
    # Popular identity 'Econo 15' in Position 3
    assert "Dawlance 1 Ton Econo 15 Inverter Split Air Conditioner (White)" in result.title
    # Rear model is not repeated
    assert "| Econo" not in result.title.rsplit("|", 1)[0]  # not repeated before warranty
    assert result.title.endswith("| 12 Year Compressor Warranty")


def test_vip_pipe_scenario_c_model_code_only() -> None:
    """Scenario C: When no series exists, Position 3 is skipped and Model leads the feature pipe parts."""
    extraction = ModelExtraction(code="DW-6100", source="description-model-line", confidence="high")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Washing Machine",
        source_title="Dawlance Semi Automatic Top Load Washing Machine White DW-6100",
        source_description=(
            "Model: DW-6100\nColor: White\n"
            "Highlights:\n"
            "• Deep Clean Pulsator\n"
            "• Rust Proof Body\n"
            "Warranty: 10 Year Motor Warranty"
        ),
        title_formula="vip_pipe",
    )
    # Position 3 skipped: Brand -> Type directly
    assert result.title.startswith("Dawlance Semi Automatic Top Load Washing Machine (White)")
    assert result.title == (
        "Dawlance Semi Automatic Top Load Washing Machine (White) | DW-6100 | "
        "Deep Clean Pulsator | Rust Proof Body | 10 Year Motor Warranty"
    )


def test_vip_pipe_color_parentheses_and_led_tv_omission() -> None:
    """LED TV category omits color bracket; other categories include ([Color])."""
    extraction = ModelExtraction(code="", source="", confidence="none")
    tv_result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="LED TV",
        source_title="Dawlance 32 Inch Kore Google HD LED TV Black",
        source_description="Size: 32 Inch\nColor: Black\nHighlights:\n• Dolby Audio\nWarranty: 2 Year Panel Warranty",
        title_formula="vip_pipe",
    )
    assert "(Black)" not in tv_result.title
    assert "Black" not in tv_result.title
    assert tv_result.title.startswith("Dawlance 32 Inch Kore Google LED TV |")


def test_vip_pipe_budget_protection_does_not_truncate_model_or_warranty() -> None:
    """USPs are budget-checked so Model Code and Warranty are never truncated within 255 chars."""
    extraction = ModelExtraction(
        code="EXTREMELY-LONG-MODEL-CODE-NUMBER-1234567890-SERIES-EDITION", source="model-line", confidence="high"
    )
    long_desc = (
        "Model: EXTREMELY-LONG-MODEL-CODE-NUMBER-1234567890-SERIES-EDITION\n"
        "Color: Crimson Burgundy Red\n"
        "Capacity: 2 Ton\n"
        "Highlights:\n"
        "• Golden Fin Protection\n"
        "• Dual Filter Clean\n"
        "• Self Cleaning Drive\n"
        "Warranty: 12 Year Compressor And 6 Year Parts Official Brand Warranty"
    )
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Air Conditioner",
        source_title=(
            "Dawlance Super Extended Massive Title With Enormous Amount Of Extra Words To Force "
            "Severe Budget Pressure On Segment One 2 Ton Crimson Burgundy Red"
        ),
        source_description=long_desc,
        title_formula="vip_pipe",
    )
    assert len(result.title) <= 255
    # Model code and warranty MUST be preserved intact: model leads the feature parts,
    # warranty still closes the Title.
    assert "EXTREMELY-LONG-MODEL-CODE-NUMBER-1234567890-SERIES-EDITION" in result.title
    assert result.title.endswith(" | 12 Year Compressor Warranty")
    model_pos = result.title.index("EXTREMELY-LONG-MODEL-CODE")
    assert model_pos < result.title.index("Golden Fin Protection")
    assert result.title.count("(") == result.title.count(")")


def test_usfd_haier_h32k85fx_spec_leak_eliminated() -> None:
    """Haier H32K85FX: spec table headers (Screen Size, Resolution, HDMI) must NEVER leak into USPs."""
    extraction = ModelExtraction(code="H32K85FX", source="description-model-line", confidence="high")
    result = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="LED TV",
        source_title="Haier 32 Inch Bezel Less Google TV (H32K85FX)",
        source_description=(
            "Screen Size: 32\"\n"
            "Resolution: 1366*768\n"
            "Operating System: Google TV\n"
            "Refresh Rate: 60Hz\n"
            "HDMI: 3\n"
            "USB: 2\n"
            "Net Dimension: 715.7*180.8*464.1mm\n"
            "Packaging Dimension: 800x118x495 mm\n"
            "Voltage: 100-240V 50/60Hz\n"
            "Warranty: 2 Year Panel Warranty"
        ),
        title_formula="vip_pipe",
    )
    # Zero USPs survive since all rows are spec questions/measurements
    assert result.usp_tokens == ()
    assert "Screen Size" not in result.title
    assert "Resolution" not in result.title
    assert "HDMI" not in result.title
    assert "Refresh Rate" not in result.title
    assert "||" not in result.title
    assert result.title == "Haier 32 Inch Google LED TV | H32K85FX | 2 Year Panel Warranty"


def test_usfd_dawlance_wd1051hc_water_dispenser() -> None:
    """Dawlance WD-1051 HC: Cooling Capacity/Control System dropped; Refrigerator Compartment kept."""
    extraction = ModelExtraction(code="WD-1051 HC", source="description-model-line", confidence="high")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Water Dispenser",
        source_title="Dawlance 2 Taps Water Dispenser White - (WD-1051 HC)",
        source_description=(
            "Model: WD-1051 HC White\n"
            "Cooling Capacity: 2.5 L/Hour\n"
            "Heating Capacity: 5 L/Hour\n"
            "Cold Water Tank: 3.5 Liters\n"
            "Hot Water Tank: 1.6 Liters\n"
            "Control System: Mechanical\n"
            "Special Feature: Refrigerator Compartment\n"
            "Voltage: 220-240V / 50Hz\n"
            "Dimensions (WxDxH): 34.5 x 35.5 x 107.6 cm\n"
            "Weight: 17.25 kg\n"
            "Color: HC White\n"
            "Warranty: 3 Years Compressor, 1 Year General Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert "Cooling Capacity" not in result.title
    assert "Control System" not in result.title
    assert "Dimensions" not in result.title
    assert "Refrigerator Compartment" in result.title
    expected_title = (
        "Dawlance 2 Taps Water Dispenser (White) | WD-1051 HC | "
        "Refrigerator Compartment | 3 Year Compressor Warranty"
    )
    assert result.title == expected_title


def test_usfd_dawlance_dw6100_washing_machine_zero_noise_collapse() -> None:
    """Dawlance DW-6100: technical spec table rows must not leak, collapsing cleanly to 0 USPs."""
    extraction = ModelExtraction(code="DW-6100", source="description-model-line", confidence="high")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Washing Machine",
        source_title="Dawlance Top Load Semi Automatic Washing Machine White (DW-6100)",
        source_description=(
            "Body Type: Plastic\n"
            "Motor / Compressor: Induction\n"
            "Voltage: 220 V\n"
            "Frequency: 50 Hz\n"
            "Color: White\n"
            "Lid Color & Material: White Opaque\n"
            "Set Weight: 16 kg\n"
            "Width: 56 cm\n"
            "Warranty: 10 Year Motor Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert result.usp_tokens == ()
    assert "Body Type" not in result.title
    assert "Set Weight" not in result.title
    assert "||" not in result.title
    assert result.title == "Dawlance Semi Automatic Top Load Washing Machine (White) | DW-6100 | 10 Year Motor Warranty"


def test_usfd_negative_and_boolean_rules() -> None:
    """Negative claims dropped; positive booleans promoted unless parameter stems."""
    extraction = ModelExtraction(code="TEST-TV-01", source="description-model-line", confidence="high")
    result = build_title(
        brand="TCL",
        extraction=extraction,
        product_type="LED TV",
        source_title="TCL 55 Inch 4K UHD Smart LED TV (TEST-TV-01)",
        source_description=(
            "Key Features:\n"
            "• 3D: No\n"
            "• 8K: No\n"
            "• Screen Size: Yes\n"
            "• Child Lock: Yes\n"
            "• Voice Assistant: True\n"
            "• Bluetooth: 1\n"
            "Warranty: 2 Year Panel Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert "3D" not in result.title
    assert "8K" not in result.title
    assert "Screen Size" not in result.title
    assert "Child Lock" in result.title
    assert "Voice Assistant" in result.title
    assert "Bluetooth" in result.title


def test_usfd_spec_value_promotion_and_multi_value_splitting() -> None:
    """Non-boolean descriptive values promoted, multi-value cells split on comma/semicolon."""
    extraction = ModelExtraction(code="TEST-REF-01", source="description-model-line", confidence="high")
    result = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="Refrigerator",
        source_title="Haier 15 Cu Ft Refrigerator Red (TEST-REF-01)",
        source_description=(
            "Cooling Technology: No Frost\n"
            "Special Feature: Built-In Ice Maker\n"
            "Smart Features: Dolby Audio, Multi Air Flow\n"
            "Warranty: 10 Year Compressor Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert "Cooling Technology" not in result.title
    assert "Special Feature" not in result.title
    assert "Smart Features" not in result.title
    assert "Built-In Ice Maker" in result.title
    assert "Dolby Audio" in result.title
    assert "Multi Air Flow" in result.title


def test_usfd_multi_word_features_not_killed_by_parameter_stems() -> None:
    """Multi-word marketing phrases containing parameter words (e.g. voltage, body, mode) survive."""
    extraction = ModelExtraction(code="TEST-MW-01", source="description-model-line", confidence="high")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Air Conditioner",
        source_title="Dawlance 1.5 Ton AC White (TEST-MW-01)",
        source_description=(
            "Key Features:\n"
            "• Low Voltage Startup\n"
            "• Rust Proof Body\n"
            "• Eco Mode\n"
            "• Stainless Steel Tank\n"
            "Warranty: 12 Year Compressor Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert "Low Voltage Startup" in result.title
    assert "Rust Proof Body" in result.title
    assert "Eco Mode" in result.title


def test_usfd_tech_acronyms_accepted() -> None:
    """Acronyms lacking Latin vowels (HDR10, DTS, VRR) are recognized and preserved."""
    extraction = ModelExtraction(code="TEST-TV-HDR", source="description-model-line", confidence="high")
    result = build_title(
        brand="TCL",
        extraction=extraction,
        product_type="LED TV",
        source_title="TCL 55 Inch LED TV (TEST-TV-HDR)",
        source_description=(
            "Highlights:\n"
            "• HDR10\n"
            "• DTS\n"
            "• VRR\n"
            "Warranty: 2 Year Panel Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert "HDR10" in result.title
    assert "DTS" in result.title
    assert "VRR" in result.title


def test_usfd_hyphenated_features_not_killed_as_model_codes() -> None:
    """Hyphenated uppercase words without digits (Wi-Fi, No-Frost) and number combos (T-3) survive."""
    extraction = ModelExtraction(code="TEST-HYPH-01", source="description-model-line", confidence="high")
    result = build_title(
        brand="Gree",
        extraction=extraction,
        product_type="Air Conditioner",
        source_title="Gree 1.5 Ton Inverter AC (TEST-HYPH-01)",
        source_description=(
            "Key Features:\n"
            "• Wi-Fi\n"
            "• T-3 Compressor\n"
            "• 3-in-1 Filter\n"
            "Warranty: 10 Year Compressor Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert "Wi-Fi" in result.title
    assert "T-3 Compressor" in result.title
    assert "3-in-1 Filter" in result.title


def test_usfd_multi_air_flow_on_air_conditioner() -> None:
    """Multi Air Flow is not dropped on an Air Conditioner despite 'Air' being in the product type."""
    extraction = ModelExtraction(code="TEST-AC-AIR", source="description-model-line", confidence="high")
    result = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="Air Conditioner",
        source_title="Haier 1.5 Ton DC Inverter Air Conditioner White (TEST-AC-AIR)",
        source_description=(
            "Highlights:\n"
            "• Multi Air Flow\n"
            "• Golden Fin\n"
            "Warranty: 10 Year Compressor Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert "Multi Air Flow" in result.title
    assert "Golden Fin" in result.title


def test_usfd_type_b_spec_rows_promoted() -> None:
    """Spec table Type B rows (e.g. Cooling System: No Frost, Audio: Dolby Atmos) promote feature values."""
    extraction = ModelExtraction(code="TEST-TYPEB-01", source="description-model-line", confidence="high")
    result = build_title(
        brand="PEL",
        extraction=extraction,
        product_type="Refrigerator",
        source_title="PEL 14 Cu Ft Refrigerator Silver (TEST-TYPEB-01)",
        source_description=(
            "Cooling System: No Frost\n"
            "Audio: Dolby Atmos\n"
            "Connectivity: Bluetooth 5.0\n"
            "Screen Size: 55 Inch\n"
            "Warranty: 10 Year Compressor Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert "Cooling System" not in result.title
    assert "Audio" not in result.title
    assert "Screen Size" not in result.title
    assert "No Frost" in result.title
    assert "Dolby Atmos" in result.title
    assert "Bluetooth 5.0" in result.title


def test_vip_pipe_a_spec_row_contributes_its_value_never_its_table_label() -> None:
    """`SubType: Semi Automatic Twin Tub` is the sheet asking a question and answering it.

    The Title may print the answer; the question is the table's own field name and is never a
    feature a shop sells.  Measured on the owner's 30-row washing-machine sheet, where 65 of the
    86 feature slots printed a bare label (`SubType`, `Sensor`, `Wash Programs`, `Control Type`).
    """
    extraction = ModelExtraction(code="HTW-130-178", source="description-model-line", confidence="high")
    result = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="Washing Machine",
        source_title="Haier HTW-130-178 13 KG Wash & Spin Semi Automatic Twin Tub Washing Machine",
        source_description=(
            "Model: HTW-130-178\nCapacity: 13 KG\nColor: White\nSubType: Semi Automatic Twin Tub\n"
            "Key Specifications:\n"
            "• Sensor: Turbidity Sensor\n"
            "• Wash Programs: 8 Programs Including Quick\n"
            "• Control Type: Mechanical Rotary Knobs\n"
            "Warranty: 10 Year Motor Warranty"
        ),
        title_formula="vip_pipe",
    )
    feature_slots = {part.strip() for part in result.title.split(" | ")[1:]}
    for label in ("SubType", "Sensor", "Wash Programs", "Control Type"):
        assert label not in feature_slots, result.title
    assert "Turbidity Sensor" in result.title, result.title
    assert "Mechanical Rotary Knobs" in result.title, result.title


def test_vip_pipe_one_spec_row_stays_one_feature_whole_its_value() -> None:
    """`Wash Programs: Gentle, Standard, and Heavy Wash Modes` states ONE fact.

    Reading the value as a comma list stranded `Gentle` as a feature beside `and Heavy Wash Modes`
    -- observed on the owner's 30-row sheet.  Only a grouping header (`Smart Features: ...`) owns a
    list; every other row's value travels whole.
    """
    extraction = ModelExtraction(code="DW 11100 C", source="description-model-line", confidence="high")
    result = build_title(
        brand="Dawlance",
        extraction=extraction,
        product_type="Washing Machine",
        source_title="Dawlance DW 11100 C 11 KG Clear Lid Semi Automatic Twin Tub Washing Machine",
        source_description=(
            "Model: DW 11100 C\nCapacity: 11 KG\nColor: Grey\nSubType: Semi Automatic Twin Tub\n"
            "Wash Programs: Gentle, Standard, and Heavy Wash Modes\n"
            "Lint Filter: Reusable Cassette-Type Lint Filter\n"
            "Warranty: 10 Year Motor Warranty"
        ),
        title_formula="vip_pipe",
    )
    slots = [part.strip() for part in result.title.split(" | ")[1:]]
    assert "Gentle" not in slots, result.title
    assert not any(slot.lower().startswith("and ") for slot in slots), result.title
    assert any(slot == "Gentle, Standard, and Heavy Wash Modes" for slot in slots), result.title


def test_vip_pipe_a_real_key_feature_keeps_its_words_whole() -> None:
    """A marketing bullet is not disqualified for being a phrase; the 255-char Title is the only limit.

    The old brevity gate (35 characters or 4 words) killed 120 of the 142 Key Features bullets on
    the owner's 30-row sheet, which is what left the feature slots empty for a table label to fill.
    """
    extraction = ModelExtraction(code="HTW-130-178", source="description-model-line", confidence="high")
    result = build_title(
        brand="Haier",
        extraction=extraction,
        product_type="Washing Machine",
        source_title="Haier HTW-130-178 13 KG Wash & Spin Semi Automatic Twin Tub Washing Machine",
        source_description=(
            "Model: HTW-130-178\nCapacity: 13 KG\nColor: White\n"
            "Key Features:\n"
            "• High-Efficiency Copper Winding Motor\n"
            "• Rust-Resistant Durable Plastic Body\n"
            "• Dedicated Wash and Rinse Timer Controls\n"
            "Warranty: 10 Year Motor Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert "High-Efficiency Copper Winding Motor" in result.title, result.title
    assert "Rust-Resistant Durable Plastic Body" in result.title, result.title
    assert len(result.title) <= TITLE_MAX, result.title
    assert result.title.endswith(" | 10 Year Motor Warranty"), result.title


def test_vip_pipe_a_feature_is_printed_without_its_sentence_mark() -> None:
    """A feature is a phrase, not a sentence, so its full stop does not travel into the Title.

    Measured on the owner's catalogue after the brevity ceiling went: the surviving long bullets did
    reach the Title, with their sentence mark attached -- `... 40% faster cooling performance.` --
    because candidates were printed as the Description wrote them while validation read them cleaned.
    """
    extraction = ModelExtraction(code="ECM-4600", source="description-model-line", confidence="high")
    result = build_title(
        brand="Super Asia",
        extraction=extraction,
        product_type="Air Cooler",
        source_title="Super Asia AC/DC Plus Inverter Easy Cool Air Cooler (ECM-4600)",
        source_description=(
            "Model: ECM-4600\n"
            "Key Features:\n"
            "• 18-minute instant freeze and 40% faster cooling performance.\n"
            "• Energy-saving operation with low voltage startup support.\n"
            "Warranty: 1 Year Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert result.usp_tokens, result.title
    assert all(not tok.endswith((".", "!", "?", "…")) for tok in result.usp_tokens), result.usp_tokens
    assert "18-minute instant freeze and 40% faster cooling performance" in result.title, result.title


def test_vip_pipe_a_feature_bullet_with_a_colon_prints_its_value_too() -> None:
    """The value-first rule is one rule for the whole Description, not one per section heading.

    Real row `Homage Air Purifier (HAP-403DWB)` writes `• 3 Settings: Turbo, Silent Mode`.  The
    parser files that bullet with the Key Features, where the Title printed the key -- the question
    `3 Settings` -- because only the spec-table loop had been taught to take the answer.  24 rows of
    the owner's catalogue state a written value inside a feature bullet this way.
    """
    extraction = ModelExtraction(code="HAP-403DWB", source="description-model-line", confidence="high")
    result = build_title(
        brand="Homage",
        extraction=extraction,
        product_type="Air Purifier",
        source_title="Homage Air Purifier (HAP-403DWB)",
        source_description=(
            "The Homage HAP-403DWB is an air purifier.\n"
            "Key Specifications:\n"
            "• CADR380 m³/h , ideal for 30-45m² area: Yes\n"
            "• H13 True HEPA Filter: Yes\n"
            "• 3 Settings: Turbo, Silent Mode\n"
            "• Plasma Ion Function Indicator: Yes\n"
            "Warranty: 1 Year Warranty"
        ),
        title_formula="vip_pipe",
    )
    slots = result.title.split(" | ")
    assert "3 Settings" not in slots, result.title
    assert "Turbo, Silent Mode" in slots, result.title


def test_vip_pipe_seller_prose_is_never_a_feature() -> None:
    """A bullet that runs two sentences is the shop talking, not a feature to seat in a Title.

    Measured on the owner's catalogue: `Note: For orders of more than 1 air cooler, a 50% advance
    payment is required. Our team will contact you for payment details after order placement.` --
    141 characters -- reached an Air Cooler Title whole the moment the 35-character ceiling was
    removed.  A real marketing phrase of comparable length still has to pass.
    """
    extraction = ModelExtraction(code="ECM-4600", source="description-model-line", confidence="high")
    result = build_title(
        brand="Super Asia",
        extraction=extraction,
        product_type="Air Cooler",
        source_title="Super Asia AC/DC Plus Inverter Easy Cool Air Cooler (ECM-4600)",
        source_description=(
            "The Super Asia ECM-4600 is an air cooler.\n"
            "Key Specifications:\n"
            "• Water Tank Capacity: 50 Liters\n"
            "• Special BLDC Motor: Yes\n"
            "• 6 Re-Freezable Ice Packs for Extra Cooling: Yes\n"
            "• Note: For orders of more than 1 air cooler, a 50% advance payment is required. "
            "Our team will contact you for payment details after order placement.\n"
            "Warranty: 1 Year Warranty"
        ),
        title_formula="vip_pipe",
    )
    assert "advance payment" not in result.title, result.title
    assert "order placement" not in result.title, result.title
    # The row's own `Yes`-valued feature survives, and the Title stays inside its budget.
    assert "6 Re-Freezable Ice Packs for Extra Cooling" in result.title, result.title
    assert len(result.title) <= TITLE_MAX, result.title


def test_the_owners_30_washing_machine_rows_never_sell_a_table_label() -> None:
    """The guard for the defect the owner reported: a feature slot is never a spec table's question.

    Every one of these 30 rows failed it before the value-first rule -- `Haier HTW-130-178` printed
    `SubType | Type | Wash Programs`, the questions its own Description asked, while the answers
    (`Semi Automatic Twin Tub`, `Turbidity Sensor`) sat unread -- and no title came out right.  The
    sheet is what the shop still uploads from, so it is the input this test reads.

    A `Yes`-valued row is the one case where the label IS the feature (`AI Mode: Yes`), and the
    Title is allowed to print it; every other row states its fact in the value.
    """
    sheet = Path(__file__).resolve().parents[1] / "data/input/Step 1.csv"
    with sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 30, len(rows)

    for row in rows:
        description = row["Description"]
        parsed = description_builder.parse_description(
            description_builder.strip_markup_keep_lines(description)
        )
        # `said_already` here is the raw source Title, looser than the built segment one the
        # pipeline passes, so this sees MORE candidates than a real run -- a stricter guard.
        features = extract_usps(
            source_title=row["Title"],
            source_description=description,
            product_type=row["Categories"].split(">")[-1].strip(),
            said_already=row["Title"],
        )
        questions = {
            label.strip().lower()
            for label, value in parsed.labelled
            if value.strip().lower() not in _USP_POSITIVE_VALS
        }
        leaked = [feature for feature in features if feature.lower() in questions]
        assert not leaked, f"{row['Title']}: {leaked}"
