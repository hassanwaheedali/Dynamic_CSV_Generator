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

from textutils import color_in_title, colour_disagreements, find_full_color


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


def test_the_colour_the_shop_wrote_in_his_own_title_beats_a_stamped_spec_line() -> None:
    """Real rows 199-201, 227-228: `• Product Color: Black` stands on every Dawlance refrigerator.

    The same line names Meadow Green, Crimson Red and Platinum Silver as the row's own colourway, so
    the stamp is not a fact about the paint -- it is the template.  Reading it first sold 140 rows
    Black, including the ones his Title spells a different colour.
    """
    title = "Dawlance Avante+ Freezer-On-Top Refrigerator 12 Cu Ft (9178-WB)-Meadow Green"
    text = f"{title}\n• Product Color: Black\n• Capacity: 12 Cu Ft"
    assert find_full_color(text, title) == "Meadow Green"


def test_the_spec_line_names_the_colour_when_the_title_states_none() -> None:
    """The label is still the contract when the row's own name says nothing about paint."""
    title = "Dawlance Avante+ Freezer-On-Top Refrigerator 12 Cu Ft (9178-WB)"
    assert find_full_color(f"{title}\n• Product Color: Blaze Purple", title) == "Blaze Purple"


def test_whichever_side_spells_the_longer_colourway_ships_it() -> None:
    """`Red Blaze` and `Hazel Red Blaze` are one colour, stated twice -- so print the fuller one.

    No disagreement to settle: the Title's words sit inside the label's, and dropping `Hazel` would
    merge this variant with the plain Red Blaze machine beside it.
    """
    title = "PEL 3 Taps Curved Glass Door Water Dispenser (PCGD-525)-Red Blaze"
    text = f"{title}\n• Product Color: Hazel Red Blaze"
    assert find_full_color(text, title) == "Hazel Red Blaze"


def test_a_prose_sentence_spelling_the_same_paint_fuller_is_not_a_second_colour() -> None:
    """Real row 587: `... 11 Cu Ft Grey (HRF-458TIFGU1)` beside `finished in Silver Grey`.

    One colourway stated twice, so the fuller spelling ships -- the Title's word is not a licence to
    drop the words the row added to it, and there is nothing for him to settle.
    """
    title = "Haier Twin Inverter IOT Freezer-On-Top Refrigerator 11 Cu Ft Grey (HRF-458TIFGU1)"
    text = f"{title}\nThe Haier HRF-458TIFGU1 is a refrigerator, finished in Silver Grey."
    assert find_full_color(text, title) == "Silver Grey"
    assert colour_disagreements(text, title) == []


def test_a_three_word_colourway_at_the_end_of_the_title_is_kept_whole() -> None:
    """The tail behind the last separator is a colourway name, so all three words are the name.

    A two-word cap read `Hazel Red Blaze` as `Red Blaze` and lost the word that tells the variant
    from the plain `Red Blaze` row -- the same cut the colour LINE already refuses to make.
    """
    title = "PEL 3 Taps Curved Glass Door Water Dispenser (PCGD-525)-Hazel Red Blaze"
    assert find_full_color(f"{title}\n• Product Color: Grey Blaze", title) == "Hazel Red Blaze"


def test_a_colour_the_title_writes_bare_is_still_the_title_s_colour() -> None:
    """Real row 697: `... Refrigerator 6 Cu Ft Silver (9106)` beside `• Product Color: Black`.

    The paint is not behind a separator and wears no marketing word in front of it, so a reader that
    only knows those two shapes saw a Title stating no colour -- and the stamp on every Dawlance row
    sold the machine Black.  His own word, written anywhere in his own name, is his answer.
    """
    title = "Dawlance Bedroom Series Refrigerator 6 Cu Ft Silver (9106)"
    text = f"{title}\n• Product Color: Black\n• Capacity: 6 Cu Ft"
    assert color_in_title(title) == "Silver"
    assert find_full_color(text, title) == "Silver"


def test_a_line_name_that_happens_to_be_a_colour_word_is_not_the_paint() -> None:
    """Real rows 184-185: `PEL Silver Line ... 23 Ltr Black` -- `Silver Line` is the range he sells.

    The sheet puts the paint last, next to the code, so the LAST colour phrase in the Title is the
    answer and a colour word standing in a name keeps its seat.  Reading the first one sold the
    machine Silver and left `Line` behind to be resold as the series.
    """
    title = "PEL Silver Line Digital Microwave Oven 23 Ltr Black (PMO-23-SLD)"
    assert color_in_title(title) == "Black"


def test_a_colourway_written_over_a_word_that_is_not_a_colour_stays_whole() -> None:
    """Real rows 363/547/676: `Silver Strip Black` and `Silver Strip Grey` are one paint each.

    Owner ruling -- print the full phrase, not the word nearest the code.  A word with paint on both
    sides of it belongs to the colourway; a word with a product noun or a size beside it does not,
    so `Silver Line Digital` is still a range and `Cu Ft Silver` is still just Silver.
    """
    assert (
        color_in_title(
            "PEL DIgitron InverterOn Flat Glass Door Freezer-On-Top Refrigerator 12 Cu Ft "
            "Silver Strip Black (PRINVO GD DT-6460)"
        )
        == "Silver Strip Black"
    )
    assert (
        color_in_title(
            "PEL DIgitron InverterOn Flat Glass Door Freezer-On-Top Refrigerator 11 Cu Ft "
            "Silver Strip Grey (PRINVO GD DT-6360)"
        )
        == "Silver Strip Grey"
    )


def test_a_paint_of_three_colour_words_is_never_cut_down_to_two() -> None:
    """Real rows 106 and 561: `Dark Jade Silver` and `Metallic Golden Brown` are one paint each.

    The modifier reader took the FIRST word it found in front of a base colour and stopped there, so
    it sold `Dark Jade` and `Metallic Golden` -- half a colourway, and the half that merges this
    variant with the plainer one beside it.
    """
    assert (
        color_in_title(
            "Haier Front Load Fully Automatic Washing Machine 12KG Dark Jade Silver "
            "(HWD-120-BP12357S8)"
        )
        == "Dark Jade Silver"
    )
    assert (
        color_in_title(
            "PEL Life Pro Freezer-On-Top Refrigerator 9 Cu Ft - Metallic Golden Brown (PRLP-2550)"
        )
        == "Metallic Golden Brown"
    )


def test_a_fin_is_a_part_of_the_machine_and_never_its_paint() -> None:
    """Real row 360: `Gold Fin` names the condenser's coating, which is why the tables strip it."""
    assert color_in_title("Orient Mega 12G Inverter Air Conditioner 1 Ton Gold Fin") is None


def test_a_paint_word_in_front_of_a_product_noun_belongs_to_that_noun() -> None:
    """`Pearl Copper Steel Door` is the Pearl Copper machine with a steel door -- owner ruling.

    The paint is what the buyer picks, so the word the shop put in front of `Door` stays out of it,
    while a word in front of a SIZE is still the paint: `Freezer Burgundy 11 Cu Ft` and
    `Microwave Oven Silver 20 Ltr` have nothing else to be.
    """
    assert (
        color_in_title(
            "Dawlance 12 Cu Ft Pearl Copper Steel Door Direct Cool Non-Inverter Refrigerator "
            "- 9173WB - 12 Years Compressor Warranty"
        )
        == "Pearl Copper"
    )
    assert color_in_title("Dawlance Vertical Freezer Burgundy 11 Cu Ft (VF-1035GD)") == "Burgundy"
    assert (
        color_in_title("Haier Grill Series Microwave Oven Silver 20 Ltr (HMW-DGS-20)") == "Silver"
    )


def test_the_two_spellings_of_one_grey_ship_as_the_list_spells_it() -> None:
    """§9's colour list carries one entry, so a Title writing `Gray` still ships `Grey`."""
    assert (
        color_in_title("Dawlance Top Load Fully Automatic Washing Machine 11kg Gray (DWT-11671-FLT)")
        == "Grey"
    )


def test_a_colour_word_behind_the_title_s_word_is_a_second_colour_not_a_fuller_spelling() -> None:
    """`Black` inside `Black White` is a second paint, so the Title's word ships and he gets the row.

    A colourway is its head with the modifiers IN FRONT of it (`Silver Grey`, `Hazel Red Blaze`), so a
    longer spelling only restates the Title's paint when the Title's words sit at its END.  A reader
    that asked merely whether the Title's word appeared somewhere took `Black White` as the fuller
    spelling of `Black` -- shipping a colour the Title never chose and raising no flag, which is the
    silent override the two-colour ruling forbids.
    """
    title = "Dawlance Bedroom Series Refrigerator 7 Cu Ft Black (9173)"
    text = f"{title}\n• Product Color: Black White"
    assert find_full_color(text, title) == "Black"
    assert colour_disagreements(text, title) == ["Black White"]


def test_the_label_s_gray_ships_the_spelling_the_list_uses() -> None:
    """§9's colour list has one entry for the two spellings, and every reader has to fold to it.

    The Title reader folded `Gray` to `Grey`; the label reader answered in its own spelling, so a row
    whose Title states no paint shipped `Manhattan Gray` into the Option1 Value.
    """
    title = "Dawlance 9 Cu Ft Direct Cool Refrigerator (9173W)"
    text = f"{title}\n• Product Color: Manhattan Gray"
    assert find_full_color(text, title) == "Manhattan Grey"


def test_a_row_that_states_two_colours_ships_the_title_s_and_names_the_other() -> None:
    """Owner ruling: two colours -- print the Title's, and hand him the row to look at.

    Both sides are reported, whichever way the second colour was written: a `Color:` line, a
    `finished in` sentence, or a second colour phrase in the Title itself.
    """
    title = "Dawlance Bedroom Series Refrigerator 6 Cu Ft Silver (9106)"
    assert colour_disagreements(f"{title}\n• Product Color: Black", title) == ["Black"]
    assert colour_disagreements(f"{title}\nfinished in Black", title) == ["Black"]
    other = "Haier Pearl DC Inverter Air Conditioner 1.5 Ton Silver (HSU-19HFPA)-Black"
    assert colour_disagreements(other, other) == ["Silver"]
    # One colour, stated twice in two spellings, is not a disagreement to settle.
    same = "Haier Front Load Fully Automatic Washing Machine 10Kg Grey (HW 100-BP14929S6)"
    assert colour_disagreements(f"{same}\n• Color: Dark Grey", same) == []

