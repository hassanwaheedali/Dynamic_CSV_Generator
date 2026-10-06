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
)
from models import DescriptionBundle

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
    long_title = (
        "Dawlance Advanco Top load Washing Machine 8 Kg Arcelik White Twin Inverter "
        "Automatic Series"
    )
    for title in (
        "Dawlance WD-1051 HC White 2 Taps Water Dispenser",
        long_title,
        "TCL 32 Inch LED TV",
    ):
        seo = build_seo_title(title, "Washing Machine", "Dawlance", ["White", "8 Kg"])
        assert SEO_TITLE_MIN <= len(seo) <= SEO_TITLE_MAX, (title, seo)
        assert seo.endswith("Price in Pakistan") or "Pakistan" in seo


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
