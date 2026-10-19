"""Unit tests for title_builder.py according to Section 6 title formula:
[Brand] [Capacity] [Color] [Inverter/Non-Inverter] [Category Name] - [Model] [Series/Feature Keyword] [Main Warranty]
"""

from __future__ import annotations

from sku_handle import ModelExtraction
from title_builder import TITLE_MAX, TitleResult, build_title


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


