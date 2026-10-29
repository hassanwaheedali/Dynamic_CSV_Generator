"""Section 8 -- the classifier, tags and the SEO length constraints."""

from __future__ import annotations

from typing import Any

from description_builder import (
    SEO_DESC_MAX,
    SEO_DESC_MIN,
    SEO_TITLE_MAX,
    SEO_TITLE_MIN,
    _bullet_sentence,
    build_description_bundle,
    build_seo_title,
    parse_description,
    subtype_label,
)
from models import DescriptionBundle, SpecRow

TAB_BLOCK = (
    "The Dawlance DF-500 DD Inverter White is a 15 cu ft freezer, finished in White."
    "Brand\tDawlance\r\nModel\tDF-500DD\r\nCapacity / Size\t68 kg\r\nType\tInverter\r\n"
    "Product Type\tFreezer\r\nColor Pattern\tWhite"
)
LABEL_BULLETS = (
    "The Dawlance Kore FHD Google TV 40 is a 40-inch LED TV running Google TV. "
    "Additional highlights include Dolby Digital.\n\n"
    "Key Specifications:\n"
    "\u2022 Screen Size: 40\"/100 cm\n"
    "\u2022 Resolution: Full HD (1920 x 1080)\n"
    "\u2022 Sound Output: 2 x 8W\n"
    "\u2022 Refresh Rate: 60"
)
EMDASH_BULLETS = (
    "The Dawlance Kore QLED TV is a television.\n\nHighlights:\n"
    "\u2022 Dolby Audio\u2014Clearer dialogue.\n"
    "\u2022 Wide Color Gamut \u2014 Richer colors.\n"
    "\u2022 Turbo Sound \u2014 Wider range."
)
BARE_FEATURES = "Some intro.\nFeatures\n100% Copper\nLong Air Throw\nHidden LED"
THIN = "The Haier H55K85FX is a 55-inch smart LED TV."


def test_tab_label_block_is_parsed() -> None:
    parsed = parse_description(TAB_BLOCK)
    labels = [label for label, _ in parsed.labelled]
    assert "Model" in labels and "Capacity / Size" in labels
    assert parsed.branch in ("label-lines", "label-bullets")


def test_label_bullets_are_parsed_as_spec_rows() -> None:
    parsed = parse_description(LABEL_BULLETS)
    assert parsed.branch == "label-bullets"
    labels = [label for label, _ in parsed.labelled]
    assert "Screen Size" in labels and "Sound Output" in labels
    assert parsed.key_features == []


def test_em_dash_bullets_become_one_key_features_row() -> None:
    parsed = parse_description(EMDASH_BULLETS)
    assert parsed.key_features == ["Dolby Audio", "Wide Color Gamut", "Turbo Sound"]
    assert parsed.labelled == []


def test_bare_bullets_become_features_not_fake_labels() -> None:
    parsed = parse_description(BARE_FEATURES)
    assert parsed.key_features == ["100% Copper", "Long Air Throw", "Hidden LED"]
    assert parsed.labelled == []


def test_single_line_description_is_thin_and_not_padded() -> None:
    parsed = parse_description(THIN)
    assert parsed.thin is True
    assert parsed.labelled == [] and parsed.key_features == []


def _bundle(description: str, **overrides: Any) -> DescriptionBundle:
    kwargs: dict[str, Any] = {
        "brand": "Dawlance",
        "model": "DW-6100",
        "product_type": "Washing Machine",
        "breadcrumb_leaf": "Washing machine",
        "color": "White",
        "capacity": "8 Kg",
        "warranty_rows": [],
        "description": description,
        "title": "Dawlance DW-6100 8 Kg White Washing Machine",
        "has_real_model": True,
        "feature_tokens": ["White", "8 Kg"],
    }
    kwargs.update(overrides)
    return build_description_bundle(**kwargs)


def test_html_table_is_single_line_and_uses_the_specified_style() -> None:
    bundle = _bundle(LABEL_BULLETS)
    assert "\n" not in bundle.description_html
    assert "<thead>" in bundle.description_html and "<tbody>" in bundle.description_html
    assert 'border:1px solid #ddd;padding:10px;"' in bundle.description_html
    assert "Specification" in bundle.description_html and "Details" in bundle.description_html


def test_thin_source_gets_no_filler_rows() -> None:
    bundle = _bundle(THIN, model="", has_real_model=False, product_type="LED TV")
    labels = [row.label for row in bundle.spec_rows]
    assert labels[0] == "Brand"
    assert "Model" not in labels  # no real model code found
    assert len(labels) <= 4
    assert bundle.thin is True


def test_short_description_is_always_built_even_when_thin() -> None:
    bundle = _bundle(THIN, model="", has_real_model=False, product_type="LED TV")
    assert bundle.short_description.startswith("<ul>")
    assert 1 <= bundle.short_description_bullets <= 3


def test_tags_are_five_to_eight_and_unique() -> None:
    bundle = _bundle(LABEL_BULLETS)
    assert 5 <= len(bundle.tags) <= 8
    assert len({tag.lower() for tag in bundle.tags}) == len(bundle.tags)


def test_tags_include_model_price_and_colour_combinations() -> None:
    bundle = _bundle(LABEL_BULLETS)
    joined = " | ".join(bundle.tags)
    assert "Dawlance DW-6100" in joined
    assert "Price in Pakistan" in joined


def test_seo_title_lands_in_the_required_range() -> None:
    """Every base is the shape the Title builder hands over: brand, code, sub-type, type - size."""
    over_budget = "Dawlance DWT 9057 EZ Top Load Fully Automatic Steam Washing Machine - 9.5 KG"
    for title in (
        "Dawlance WD-1051 HC 2 Taps Water Dispenser",
        over_budget,
        "TCL 32S6820 Smart LED TV",
    ):
        seo = build_seo_title(title, "Washing Machine", "Dawlance", ["Top Load Fully Automatic", "9.5 KG"])
        assert SEO_TITLE_MIN <= len(seo) <= SEO_TITLE_MAX, (title, seo)
        assert seo.endswith("Price in Pakistan") or "Pakistan" in seo


def test_an_over_budget_search_title_gives_up_its_subtype_before_its_size() -> None:
    """A base too long for ` Price in Pakistan` sheds the sub-type phrase, never the size.

    The shed takes its tokens in the order the pipeline hands them, and the ruled shape carries only
    two sheddable facts -- the sub-type and the size.  The size is what a buyer types
    ("9.5 kg washing machine price in pakistan"), so the longer phrase goes first.
    """
    seo = build_seo_title(
        "Dawlance DWT 9057 EZ Top Load Fully Automatic Steam Washing Machine - 9.5 KG",
        "Washing Machine",
        "Dawlance",
        ["Top Load Fully Automatic", "9.5 KG"],
    )
    assert "Top Load Fully Automatic" not in seo
    assert "9.5 KG" in seo, f"the shed ate the size the buyer searches on: {seo!r}"
    assert SEO_TITLE_MIN <= len(seo) <= SEO_TITLE_MAX


def test_the_padding_never_names_the_rows_own_brand_or_type_twice() -> None:
    """A short base used to be padded with its own brand and type a second time.

    Measured on the 752-row sheet: 13 rows shipped a search title that named the same brand twice,
    because the ladder added words the base already printed.  The base now carries brand, code,
    sub-type and type by rule, so the only lever left for a short row is the phrase itself.
    """
    seo = build_seo_title("TCL 32S6820 Smart LED TV", "LED TV", "TCL", [])
    assert seo.lower().count("tcl") == 1
    assert seo.lower().count("led tv") == 1
    assert SEO_TITLE_MIN <= len(seo) <= SEO_TITLE_MAX


def test_seo_title_never_mutates_the_stored_title() -> None:
    title = "Dawlance WD-1051 HC White 2 Taps Water Dispenser"
    build_seo_title(title, "Water Dispenser", "Dawlance", ["White"])
    assert title == "Dawlance WD-1051 HC White 2 Taps Water Dispenser"


def test_seo_description_lands_in_151_155_characters() -> None:
    for description, product_type in (
        (LABEL_BULLETS, "LED TV"),
        (TAB_BLOCK, "Deep Freezer"),
        (EMDASH_BULLETS, "LED TV"),
        (THIN, "LED TV"),
    ):
        bundle = _bundle(description, product_type=product_type)
        assert SEO_DESC_MIN <= len(bundle.seo_description) <= SEO_DESC_MAX, (
            product_type,
            len(bundle.seo_description),
            bundle.seo_description,
        )


def test_seo_description_contains_the_recipe_line() -> None:
    bundle = _bundle(LABEL_BULLETS)
    assert "Dawlance" in bundle.seo_description
    assert "Buy the best Washing Machine in Pakistan today" in bundle.seo_description


def test_ampersands_are_escaped_in_the_html() -> None:
    bundle = _bundle("Brand: X\nCooling & Heating: Yes\nOther: a & b")
    assert "&amp;" in bundle.description_html
    assert " & " not in bundle.description_html


def test_no_tag_may_contain_a_comma() -> None:
    """The Tags cell is comma-separated, so a tag itself must not carry one.

    A source bullet like "Smooth, Noise-free motor" is a fine feature, but as a
    tag it would read as two tags and push a 8-tag row past the schema's limit.
    """
    bundle = build_description_bundle(
        title="Superasia ECM-4600 Advance Air Cooler",
        description=(
            "The Superasia ECM-4600 is an air cooler.\n"
            "Features:\n"
            "• Smooth, Noise-free motor\n"
            "• Special BLDC Motor\n"
            "• Remote control\n"
        ),
        brand="Superasia",
        product_type="Air Cooler",
        capacity="",
        color="",
        breadcrumb_leaf="Air Cooler",
        warranty_rows=[],
        model="ECM-4600",
        has_real_model=True,
        feature_tokens=[],
    )
    assert all("," not in tag for tag in bundle.tags), bundle.tags
    assert len(bundle.tags) <= 8


def test_a_measurement_bullet_keeps_its_label() -> None:
    """'6 Kg.' alone tells a shopper nothing -- 6 kilograms of what?"""
    assert _bullet_sentence("6 Kg", "Drying Capacity") == "Drying Capacity: 6 Kg."
    assert _bullet_sentence("2.5 L/Hour", "Cooling Capacity") == "Cooling Capacity: 2.5 L/Hour."
    assert _bullet_sentence("17.25 kg", "Weight") == "Weight: 17.25 kg."
    assert _bullet_sentence("White", "Product Color") == "Product Color: White."
    # a value that reads on its own still stands alone
    assert _bullet_sentence("Dolby Audio", "Audio") == "Dolby Audio."


def test_short_description_filters_lead_in_and_title_boilerplate() -> None:
    bundle = _bundle(
        "The Panini 20M Solo Black is a microwave.\n"
        "• Key features include Panini 20M Solo Black (Solo Series).\n"
        "• Solo Function\n"
        "• Mechanical Control",
        brand="Panini",
        model="20M Solo Black",
        product_type="Microwave Oven",
    )
    assert "Key features include" not in bundle.short_description
    assert "Solo Series" not in bundle.short_description
    assert "Solo Function." in bundle.short_description
    assert "Mechanical Control." in bundle.short_description


def test_trimming_a_long_seo_title_never_leaves_an_empty_segment() -> None:
    """A word deleted to fit 90 characters must not leave the shelf reading `Dispenser - - 3 Year`.

    The trim loop removes a whole feature token, and when that token was an entire ` - ` segment the
    separator survived on both sides of the hole.  The segment, not just the spaces, has to go.
    """
    seo = build_seo_title(
        "Orient 3 Taps Purple Water Dispenser Glass Door with Heating - Velvet - 3 Year Compressor Warranty",
        "Water Dispenser",
        "Orient",
        ["Velvet", "Heating", "Glass Door"],
    )
    assert " - - " not in seo
    assert not seo.startswith("-")


def test_trimming_never_mutilates_a_part_number_to_buy_room() -> None:
    """`Etech-12` is the model code; deleting the letters `Etech` out of it leaves `--12` and a lie.

    The trim loop matched a feature token as a substring, so on this real Orient row it cut the head
    off the code and shipped `Air Conditioner --12`.  A token is only ever removable when it stands
    as its own word.
    """
    seo = build_seo_title(
        "Orient 1 Ton White Inverter Heat & Cool Air Conditioner - Etech-12 - 10 Year Compressor Warranty",
        "Air Conditioner",
        "Orient",
        ["Etech", "Heat and Cool", "Imprint", "1.0 Ton"],
    )
    assert "Etech-12" in seo
    assert "--" not in seo


def test_an_over_budget_seo_title_sheds_a_name_and_number_as_one_unit() -> None:
    """A row that sells itself as `Twister 1150` must never appear in search as bare `- 1150 -`.

    The trim loop cuts a whole feature token, and the pipeline handed it `Twister` while the Title
    carried `Twister 1150` -- so the length cut ate the name and left the digits standing alone.
    The pair travels as one token, and it goes before a stated size like `10 KG`, never after it.
    """
    seo = build_seo_title(
        "Orient 10 KG Metallic Silver Fully Automatic Top Load Washing Machine - Twister 1150 - 1 Year Warranty",
        "Washing Machine",
        "Orient",
        ["Twister 1150", "Twister", "Metallic Silver", "10 KG", "Top Load"],
    )
    assert "1150" not in seo or "Twister 1150" in seo


def test_seo_padding_never_shreds_the_title_into_words() -> None:
    """A Title that states `1.5 Ton` used to hand the padding ladder `1.5`, `Ton` and `Air`.

    The shop's meta description then ended `..., 1.5. Buy the best Air Conditioner in Pakistan
    today.` -- fourteen rows read like that.  Padding may only reuse a whole fact about this
    product, so the sentence stays a sentence.
    """
    bundle = _bundle(
        "The Gree 18PITH-10W is a split inverter air conditioner.",
        brand="Gree",
        model="18PITH-10W",
        product_type="Air Conditioner",
        breadcrumb_leaf="Air Conditioners",
        capacity="1.5 Ton",
        title=(
            "Gree 1.5 Ton White Inverter Split Air Conditioner - 18PITH-10W Elegant "
            "- 10 Year Compressor Warranty"
        ),
        feature_tokens=["Elegant", "White", "1.5 Ton"],
    )
    seo = bundle.seo_description
    assert SEO_DESC_MIN <= len(seo) <= SEO_DESC_MAX
    assert ", 1.5." not in seo
    assert ", Ton." not in seo
    assert ", Air." not in seo


def test_the_programs_own_subtype_label_stays_out_of_every_shopper_field() -> None:
    """`SubType:` is a field name this program reads, not a spec a shop wrote for a buyer.

    Hiding it must not blind the reader: the line still answers the row's type question, it only
    stops being rendered.  The shopper already learns the value from the Title and from DigiMall's
    `Attribute_Air Conditioner Type` cell, so nothing about the product is concealed -- only the
    plumbing is.
    """
    description = (
        "The Haier HBU-18HE is a split air conditioner.\n"
        "Key Specifications:\n"
        "• SubType: Cassette\n"
        "• Capacity: 1.5 Ton\n"
        "• Color: White"
    )
    bundle = _bundle(
        description,
        brand="Haier",
        model="HBU-18HE",
        product_type="Air Conditioner",
        breadcrumb_leaf="Air Conditioners",
        capacity="1.5 Ton",
        title="Haier 1.5 Ton White Cassette Air Conditioner - HBU-18HE - 10 Year Compressor Warranty",
        feature_tokens=["White", "1.5 Ton"],
    )
    labels = [row.label for row in bundle.spec_rows]
    assert "SubType" not in labels
    assert "SubType" not in bundle.description_html
    assert "SubType" not in bundle.short_description
    assert "SubType" not in bundle.seo_description
    assert "Capacity" in labels and "Color" in labels  # its neighbours are real specs
    assert subtype_label(description) == "Cassette"


def test_a_warranty_already_printed_as_a_row_is_not_repeated_in_key_features() -> None:
    """The same fact twice in one table is worse than the missing bullet.

    Real sheet, sheet row 324: the shop's warranty bullets sit inside his "Key Features" run, and
    :mod:`warranty` now prints each of them as its own row.  A run left holding those same words
    showed `4-Year PCB Warranty: Yes, 10-Year Compressor Warranty: Yes` under Key Features AND as
    two rows.  The non-warranty features are untouched, and a warranty the reader could not place
    stays in the run -- only what already has a row is cut.
    """
    description = (
        "The Homage HES-1222S is a 1.0 Ton inverter split air conditioner.\n"
        "Key Features:\n"
        "• 4-Year PCB Warranty: Yes\n"
        "• 10-Year Compressor Warranty: Yes\n"
        "• Fast Cool Mode\n"
    )
    bundle = _bundle(
        description,
        warranty_rows=[
            SpecRow("Compressor Warranty", "10 Year", is_warranty=True),
            SpecRow("PCB Warranty", "4 Year", is_warranty=True),
        ],
    )
    features = [row.value for row in bundle.spec_rows if row.label == "Key Features"]
    assert features == ["Fast Cool Mode"]


def test_two_answers_to_one_warranty_question_print_one_row() -> None:
    """Real sheet, sheet row 596: `• Warranty: 1 Year, 10 Years` -- two numbers, no parts.

    The rename exists so a warranty row never collides with a spec row of the same name.  Applying
    it to a label that already ends in the word printed `Warranty Warranty: 10 Years`, and leaving
    both rows printed `Warranty` twice -- a label a shop's table never repeats.  One question, one
    row, with his numbers in the order he wrote them.
    """
    bundle = _bundle(
        "The Super Asia SA-260 is a 10 kg washing machine.\n",
        warranty_rows=[
            SpecRow("Warranty", "1 Year", is_warranty=True),
            SpecRow("Warranty", "10 Years", is_warranty=True),
        ],
    )
    labels = [row.label for row in bundle.spec_rows]
    assert len(labels) == len(set(labels))
    assert [
        (row.label, row.value) for row in bundle.spec_rows if row.label == "Warranty"
    ] == [("Warranty", "1 Year, 10 Years")]


def test_a_feature_that_only_shares_the_part_word_with_a_row_keeps_its_own_claim() -> None:
    """Cutting a duplicate needs the number too, or the cut eats a claim the table never prints.

    `10-Year Compressor Warranty: Yes` restates the row, so it goes.  `Extended Compressor Warranty
    For First Buyers` shares only the part word: the shop is promising something the table does not
    say, and deleting it hides a fact he wrote -- the opposite of the rule this run exists for.
    """
    description = (
        "The Haier HPU-24VN3 is a 2.0 Ton inverter split air conditioner.\n"
        "Key Features:\n"
        "• Extended Compressor Warranty For First Buyers\n"
        "• 10-Year Compressor Warranty: Yes\n"
    )
    bundle = _bundle(
        description,
        product_type="Air Conditioner",
        warranty_rows=[SpecRow("Compressor Warranty", "10 Years", is_warranty=True)],
    )
    features = [row.value for row in bundle.spec_rows if row.label == "Key Features"]
    assert features == ["Extended Compressor Warranty For First Buyers"]


def test_a_subtype_line_spaced_his_way_is_hidden_the_same_way() -> None:
    """The reader folds punctuation when it looks for the program's field, so the hide must too.

    `• Sub Type: Cassette` answers the row's type question exactly like `SubType:` does -- so it was
    used for the Title AND printed in the shopper's table, because the filter compared spellings.
    """
    description = (
        "The Haier HBU-18HE is a split air conditioner.\n"
        "Key Specifications:\n"
        "• Sub Type: Cassette\n"
        "• Capacity: 1.5 Ton\n"
    )
    bundle = _bundle(
        description,
        brand="Haier",
        model="HBU-18HE",
        product_type="Air Conditioner",
        breadcrumb_leaf="Air Conditioners",
        capacity="1.5 Ton",
    )
    labels = [row.label for row in bundle.spec_rows]
    assert "Sub Type" not in labels
    assert subtype_label(description) == "Cassette"


def test_a_feature_stating_a_different_number_is_never_the_row_s_fact() -> None:
    """`10 Years Compressor Warranty` is not the fact the table shows as `Compressor | 1 Year`.

    Comparing only the digits let the row's `1` match inside the bullet's `10`, so the bullet was
    cut and the shop's 10-year claim reached no row at all -- the number has to be a whole number.
    """
    description = (
        "The Kenwood KES-1270S is a 1 Ton inverter split air conditioner.\n"
        "Key Features:\n"
        "• 10 Years Compressor Warranty\n"
    )
    bundle = _bundle(
        description,
        product_type="Air Conditioner",
        warranty_rows=[SpecRow("Compressor Warranty", "1 Year", is_warranty=True)],
    )
    features = [row.value for row in bundle.spec_rows if row.label == "Key Features"]
    assert features == ["10 Years Compressor Warranty"]


def test_one_fact_written_two_ways_still_prints_once() -> None:
    """`10 Yr` and `10 Years` are the same duration, so the bullet repeats the row and leaves."""
    description = (
        "The Kenwood KES-1270S is a 1 Ton inverter split air conditioner.\n"
        "Key Features:\n"
        "• 10 Yr Compressor Warranty\n"
        "• Turbo Cool Mode\n"
    )
    bundle = _bundle(
        description,
        product_type="Air Conditioner",
        warranty_rows=[SpecRow("Compressor Warranty", "10 Years", is_warranty=True)],
    )
    features = [row.value for row in bundle.spec_rows if row.label == "Key Features"]
    assert features == ["Turbo Cool Mode"]
