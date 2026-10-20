"""Unit tests for title_builder.py according to Section 6 title formula:
[Brand] [Capacity] [Color] [Inverter/Non-Inverter] [Category Name] - [Model] [Series/Feature Keyword] [Main Warranty]
"""

from __future__ import annotations

from sku_handle import ModelExtraction
from title_builder import (
    TITLE_MAX,
    TitleResult,
    build_title,
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


def test_the_title_answers_a_group_before_the_description_does() -> None:
    """When the two columns name different machines, the Title's answer is the row's answer.

    The case that decides the rule is a disagreement: the Title says `Split`, the prose says
    `floor standing`.  Read the prose first and the table's own order picks the word the buyer was
    NOT shown -- measured, that swap moves 26 real rows on this sheet.
    """
    result = build_title(
        brand="Haier",
        extraction=ModelExtraction(code="HSU-20", source="title-parenthetical", confidence="high"),
        product_type="Air Conditioner",
        source_title="Haier Split Inverter Air Conditioner 2 Ton White (HSU-20)",
        source_description="A floor standing unit with heat and cool operation.",
    )
    assert result.subtype_token == "Split Heat & Cool"
    assert "Floor Standing" not in result.title


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
