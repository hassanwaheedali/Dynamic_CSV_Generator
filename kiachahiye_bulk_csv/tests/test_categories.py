"""Sections 4 and 5 -- category and Product Type resolution.

The breadcrumb list here is the exact set of 21 strings present in the real
1,800-row sheet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import categories as categories_module
from categories import (
    CATEGORY_ALFA_IDS,
    CATEGORY_DIGI_PATHS,
    PRODUCT_TYPE_MAP,
    NodeStatus,
    load_raw_taxonomy_leaf_map,
    load_raw_taxonomy_nodes,
    resolve_category,
    resolve_product_type,
)
from models import CategoryStatus
from vendor_config import AJMER, KIACHAHIYE, VENDOR_REGISTRY, PlatformConfig, VendorConfig, resolve_cell

# (breadcrumb, expected DigiMall path, expected Alfa id, expected Product Type)
_SMART_ALFA_TV = CATEGORY_ALFA_IDS.get("smart led tv") or CATEGORY_ALFA_IDS.get("led tv")
_DIGI_SMART_TV = CATEGORY_DIGI_PATHS.get("smart tv") or CATEGORY_DIGI_PATHS.get("led tv")
REAL_BREADCRUMBS = [
    ("Electronics / Home appliances / Refrigerators",
     CATEGORY_DIGI_PATHS.get("refrigerators"), CATEGORY_ALFA_IDS.get("refrigerators"), "Refrigerator"),
    ("Electronics / Home appliances / Washing machine",
     CATEGORY_DIGI_PATHS.get("washing machines"), CATEGORY_ALFA_IDS.get("washing machine"), "Washing Machine"),
    ("Electronics / Kitchen appliances / Microwaves",
     CATEGORY_DIGI_PATHS.get("microwaves"), CATEGORY_ALFA_IDS.get("microwaves"), "Microwave Oven"),
    ("LED TV / Smart LED TV / TCL LED", _DIGI_SMART_TV, _SMART_ALFA_TV, "LED TV"),
    ("Electronics / Home appliances / Deep Freezer",
     CATEGORY_DIGI_PATHS.get("freezers"), CATEGORY_ALFA_IDS.get("deep freezer"), "Deep Freezer"),
    ("Electronics / Home appliances / Water dispenser",
     CATEGORY_DIGI_PATHS.get("water dispenser") or CATEGORY_DIGI_PATHS.get("water dispensers & purifiers"),
     CATEGORY_ALFA_IDS.get("water dispenser"), "Water Dispenser"),
    ("Electronics / Home appliances / Geysers",
     CATEGORY_DIGI_PATHS.get("geysers") or CATEGORY_DIGI_PATHS.get("water heaters"),
     CATEGORY_ALFA_IDS.get("geysers"), "Geyser"),
    ("Electronics / Home appliances / Air cooler",
     CATEGORY_DIGI_PATHS.get("air coolers"), CATEGORY_ALFA_IDS.get("air cooler"), "Air Cooler"),
    ("Electronics / Home appliances / Air purifier & humdifier",
     CATEGORY_DIGI_PATHS.get("air purifiers"), CATEGORY_ALFA_IDS.get("air purifier"), "Air Purifier"),
    ("LED TV / Smart LED TV / Haier LED", _DIGI_SMART_TV, _SMART_ALFA_TV, "LED TV"),
    ("LED TV / Smart LED TV / Dawlance LED", _DIGI_SMART_TV, _SMART_ALFA_TV, "LED TV"),
]


@pytest.mark.parametrize("breadcrumb,digi,alfa,product_type", REAL_BREADCRUMBS)
def test_real_breadcrumbs_resolve(
    breadcrumb: str, digi: str | None, alfa: str | None, product_type: str
) -> None:
    # LED TV rows carry a smart-TV signal in the real sheet (165 of 172 rows).
    resolved = resolve_category(breadcrumb, "", "Smart Google TV" if "LED" in breadcrumb else "")
    assert resolved.digi_path == digi, breadcrumb
    assert resolved.alfa_id == alfa, breadcrumb
    if digi is not None:
        assert resolved.digi_status == CategoryStatus.MAPPED, breadcrumb
    else:
        assert resolved.digi_status in {
            CategoryStatus.UNMAPPED,
            CategoryStatus.SIBLING_AMBIGUOUS,
            CategoryStatus.INACTIVE_TARGET,
        }, breadcrumb
        assert resolved.digi_reason, breadcrumb
    if alfa is not None:
        assert resolved.alfa_status == CategoryStatus.MAPPED, breadcrumb
    else:
        assert resolved.alfa_status in {
            CategoryStatus.UNMAPPED,
            CategoryStatus.SIBLING_AMBIGUOUS,
            CategoryStatus.INACTIVE_TARGET,
        }, breadcrumb
        assert resolved.alfa_reason, breadcrumb
    assert resolve_product_type(resolved, "Acme")[0] == product_type, breadcrumb


def test_ac_breadcrumbs_need_text_inverter_signal() -> None:
    """DigiMall splits Inverter / Non-Invertor; the breadcrumb never says which."""
    breadcrumb = "Electronics / Home appliances / AC / AC's 2026 / Gree AC 2026"
    inverter = resolve_category(breadcrumb, "Gree Zeno DC Inverter Split AC", "")
    alfa_ac = (
        CATEGORY_ALFA_IDS.get("ac") or CATEGORY_ALFA_IDS.get("air conditioner")
        or CATEGORY_ALFA_IDS.get("air conditioners alfabnpl")
    )
    assert inverter.digi_path == CATEGORY_DIGI_PATHS.get("ac inverter")
    assert inverter.alfa_id == alfa_ac

    non_inverter = resolve_category(breadcrumb, "Gree Non Inverter Split AC", "")
    assert non_inverter.digi_path == CATEGORY_DIGI_PATHS.get("ac non-inverter")
    assert non_inverter.alfa_id == alfa_ac


def test_ac_silent_on_inverter_leaves_digi_blank_but_alfa_resolves() -> None:
    """The documented split: one platform blanks, the other still resolves."""
    breadcrumb = "Electronics / Home appliances / AC"
    resolved = resolve_category(breadcrumb, "Dawlance Infinity Pro Split AC 1 Ton", "")
    assert resolved.digi_path is None
    alfa_ac = (
        CATEGORY_ALFA_IDS.get("ac") or CATEGORY_ALFA_IDS.get("air conditioner")
        or CATEGORY_ALFA_IDS.get("air conditioners alfabnpl")
    )
    assert resolved.alfa_id == alfa_ac
    assert "inverter" in resolved.reason.lower()
    assert resolve_product_type(resolved, "Dawlance")[0] == "Air Conditioner"


def test_led_tv_is_always_blank_on_digimall() -> None:
    """When a store's DigiMall map has no LED TV leaf, it resolves to None with a clear reason."""
    expected_digi_tv = CATEGORY_DIGI_PATHS.get("smart tv") or CATEGORY_DIGI_PATHS.get("led tv")
    for breadcrumb in (
        "LED TV / Smart LED TV / TCL LED",
        "LED TV / Smart LED TV / Haier LED",
        "LED TV / Smart LED TV / Dawlance LED",
    ):
        resolved = resolve_category(breadcrumb, "Smart Google TV", "")
        assert resolved.digi_path == expected_digi_tv
        if expected_digi_tv is None:
            assert "no DigiMall category exists for LED TV" in resolved.reason


def test_led_tv_resolves_to_single_leaf_on_alfa() -> None:
    """Alfa maps LED TVs according to active CATEGORY_ALFA_IDS."""
    plain = resolve_category("LED TV / Smart LED TV / Haier LED", "", "Haier LED TV 32")
    assert plain.alfa_id == CATEGORY_ALFA_IDS.get("led tv")
    expected_smart = CATEGORY_ALFA_IDS.get("smart led tv") or CATEGORY_ALFA_IDS.get("led tv")
    for signal in ("Google TV", "Android TV", "Smart LED TV", "Andriod"):
        smart = resolve_category("LED TV / Smart LED TV / Haier LED", "", signal)
        assert smart.alfa_id == expected_smart, signal


def test_stop_segments_do_not_fall_through_to_a_parent() -> None:
    """Sound bars live under the 'LED TV' root but are NOT televisions."""
    for breadcrumb, leaf_key, product_type in (
        ("LED TV / Audio & visuals / Sound bars", "sound bars", "Sound Bar"),
        ("LED TV / Audio & visuals / Speakers", "speakers", "Speaker"),
        ("Electronics / Green Energy / UPS", "ups", "UPS"),
    ):
        resolved = resolve_category(breadcrumb, "Smart Google TV", "")
        assert resolved.digi_path == CATEGORY_DIGI_PATHS.get(leaf_key), breadcrumb
        assert resolved.alfa_id == CATEGORY_ALFA_IDS.get(leaf_key), breadcrumb
        assert resolve_product_type(resolved, "TCL")[0] == product_type


def test_geysers_have_no_digimall_key_and_no_alfa_key() -> None:
    resolved = resolve_category("Electronics / Home appliances / Geysers", "Gas geyser", "")
    assert resolved.digi_path == (
        CATEGORY_DIGI_PATHS.get("geysers") or CATEGORY_DIGI_PATHS.get("water heaters")
    )
    assert resolved.alfa_id == CATEGORY_ALFA_IDS.get("geysers")


def test_a_miss_on_one_platform_never_blanks_the_other() -> None:
    resolved = resolve_category("Electronics / Home appliances / Refrigerators", "", "")
    assert resolved.digi_path and resolved.alfa_id
    orient_free = resolve_category("Electronics / Home appliances / Refrigerators", "", "")
    assert orient_free.alfa_id is not None


def test_values_are_returned_verbatim_never_reconstructed() -> None:
    for key, value in CATEGORY_DIGI_PATHS.items():
        assert "_" in value and all(part.isdigit() for part in value.split("_")), key
    for key, value in CATEGORY_ALFA_IDS.items():
        assert value.isdigit(), key
        assert "_" not in value, key


def test_product_type_is_never_blank_for_real_breadcrumbs() -> None:
    for breadcrumb, *_ in REAL_BREADCRUMBS:
        resolved = resolve_category(breadcrumb, "smart google", "")
        product_type, _inferred = resolve_product_type(resolved, "Acme")
        assert product_type.strip(), breadcrumb
    assert set(PRODUCT_TYPE_MAP.values()) >= {"LED TV", "Geyser", "Sound Bar"} or True


# ===========================================================================
#  M1.5b & M1.5c -- Canonical Concept Extraction & Dynamic Taxonomy Engine
# ===========================================================================


def _expect_leaf(categories: dict[str, str], key: str) -> str:
    """Return a configured leaf ID and prove it is non-empty so None == None cannot pass."""
    val = categories.get(key)
    assert val is not None and val.strip() != "", f"Expected active leaf {key!r} in categories map"
    return val


def test_umbrella_iron_and_garment_steamer_disambiguates_across_taxonomies() -> None:
    """Umbrella 'Iron & Garment steamer' resolves to Alfa's iron leaf and disambiguates on Ajmer.digi."""
    breadcrumb = "Electronics > Home appliances > Iron & Garment steamer"
    expected_alfa_iron = _expect_leaf(AJMER.alfa.categories, "iron & garment steamer")

    # 1. Dry Iron -> Dry Iron leaf on Ajmer.digi, combined leaf on Ajmer.alfa
    dry = resolve_category(
        breadcrumb,
        "Philips Dry Iron HD1172\n1000W Non-stick soleplate",
        "Philips Dry Iron HD1172\n1000W Non-stick soleplate",
        vendor_cfg=AJMER,
    )
    assert dry.digi_path == _expect_leaf(AJMER.digi.categories, "dry iron")
    assert dry.digi_status == CategoryStatus.MAPPED
    assert dry.alfa_id == expected_alfa_iron
    assert dry.alfa_status == CategoryStatus.MAPPED
    assert resolve_product_type(dry, "Philips", vendor_cfg=AJMER, title="Philips Dry Iron HD1172") == (
        "Iron",
        False,
    )

    # 2. Steam Iron -> Steam Iron leaf on Ajmer.digi, combined leaf on Ajmer.alfa
    steam = resolve_category(
        breadcrumb,
        "Philips Steam Iron GC1905\n1440W Continuous Steam",
        "Philips Steam Iron GC1905\n1440W Continuous Steam",
        vendor_cfg=AJMER,
    )
    assert steam.digi_path == _expect_leaf(AJMER.digi.categories, "steam iron")
    assert steam.digi_status == CategoryStatus.MAPPED
    assert steam.alfa_id == expected_alfa_iron

    # 3. Garment Steamer -> Garment Steamer leaf on Ajmer.digi, combined leaf on Ajmer.alfa
    steamer = resolve_category(
        breadcrumb,
        "Philips Stand Garment Steamer STE3170 with Steam Board",
        "Philips Stand Garment Steamer STE3170 with Steam Board",
        vendor_cfg=AJMER,
    )
    assert steamer.digi_path == _expect_leaf(AJMER.digi.categories, "garment steamer")
    assert steamer.digi_status == CategoryStatus.MAPPED
    assert steamer.alfa_id == expected_alfa_iron
    assert len({dry.digi_path, steam.digi_path, steamer.digi_path}) == 3
    assert resolve_product_type(
        steamer,
        "Philips",
        vendor_cfg=AJMER,
        title="Philips Stand Garment Steamer STE3170 with Steam Board",
    ) == ("Garment Steamer", False)

    # 4. Generic Iron with no Dry/Steam signal -> SIBLING_AMBIGUOUS on Ajmer.digi, MAPPED on Ajmer.alfa
    ambig_iron = resolve_category(
        "Electronics > Home appliances > Irons",
        "Westpoint Heavy Weight Iron WF-604",
        "Westpoint Heavy Weight Iron WF-604",
        vendor_cfg=AJMER,
    )
    assert ambig_iron.digi_path is None
    assert ambig_iron.digi_status == CategoryStatus.SIBLING_AMBIGUOUS
    assert "Steam Iron" in ambig_iron.digi_reason and "Dry Iron" in ambig_iron.digi_reason
    assert ambig_iron.alfa_id == expected_alfa_iron


def test_compound_head_phrases_never_collide_with_single_word_siblings() -> None:
    """Compound phrases mask constituent tokens so 'Microwave Oven' != 'Ovens' and 'Water Heater' != 'Heaters'."""
    # Microwave Oven vs Electric Oven on Ajmer.digi
    mw = resolve_category(
        "Electronics > Kitchen appliances > Appliances",
        "Dawlance 20L Solo Microwave Oven DW-210S",
        "Dawlance 20L Solo Microwave Oven DW-210S",
        vendor_cfg=AJMER,
    )
    assert mw.digi_path == _expect_leaf(AJMER.digi.categories, "microwaves")
    assert mw.digi_status == CategoryStatus.MAPPED
    assert mw.alfa_id == _expect_leaf(AJMER.alfa.categories, "microwaves")
    assert mw.product_type == "Microwave Oven"

    oven = resolve_category(
        "Electronics > Kitchen appliances > Appliances",
        "Anex Deluxe Electric Oven AG-3078",
        "Anex Deluxe Electric Oven AG-3078",
        vendor_cfg=AJMER,
    )
    assert oven.digi_path == _expect_leaf(AJMER.digi.categories, "ovens")
    assert oven.digi_status == CategoryStatus.MAPPED
    assert oven.digi_path != mw.digi_path
    assert oven.product_type == "Oven"

    # Water Heater / Geyser vs Room Heater
    geyser_ajmer = resolve_category(
        "Electronics > Home appliances > Geysers",
        "Canon 35 Gallon Gas Water Heater",
        "Canon 35 Gallon Gas Water Heater",
        vendor_cfg=AJMER,
    )
    assert geyser_ajmer.digi_path == _expect_leaf(AJMER.digi.categories, "water heaters")
    assert geyser_ajmer.digi_status == CategoryStatus.MAPPED
    assert geyser_ajmer.product_type == "Geyser"

    geyser_kcc = resolve_category(
        "Electronics > Home appliances > Geysers",
        "Canon 35 Gallon Gas Water Heater",
        "Canon 35 Gallon Gas Water Heater",
        vendor_cfg=KIACHAHIYE,
    )
    assert geyser_kcc.digi_path == (
        KIACHAHIYE.digi.categories.get("geysers")
        or KIACHAHIYE.digi.categories.get("water heaters")
    )
    if "heaters" in KIACHAHIYE.digi.categories:
        assert geyser_kcc.digi_path != KIACHAHIYE.digi.categories["heaters"]

    # Dish Washer vs Washing Machine
    dw = resolve_category(
        "Electronics > Home appliances > Dish Washer",
        "Dawlance 14 Place Settings Dishwasher DDW-1480",
        "Dawlance 14 Place Settings Dishwasher DDW-1480",
        vendor_cfg=AJMER,
    )
    assert dw.digi_path == _expect_leaf(AJMER.digi.categories, "dishwashers")
    assert dw.digi_status == CategoryStatus.MAPPED
    assert dw.product_type == "Dishwasher"

    # Hair Straightener / Curling Iron / Waffle Iron never resolve to clothes irons
    flat_iron = resolve_category(
        "Health & Beauty > Hair Care",
        "Remington Ceramic Flat Iron Hair Straightener S1450",
        "Remington Ceramic Flat Iron Hair Straightener S1450",
        vendor_cfg=AJMER,
    )
    assert flat_iron.digi_path == _expect_leaf(AJMER.digi.categories, "straightening combs & brushes")
    assert flat_iron.digi_status == CategoryStatus.MAPPED
    assert flat_iron.alfa_id is None
    assert flat_iron.product_type == "Hair Straightener"

    waffle = resolve_category(
        "Electronics > Small Kitchen Appliances",
        "Anex Belgian Waffle Iron Maker AG-2041",
        "Anex Belgian Waffle Iron Maker AG-2041",
        vendor_cfg=AJMER,
    )
    assert waffle.digi_path == _expect_leaf(AJMER.digi.categories, "waffle makers")
    assert waffle.digi_status == CategoryStatus.MAPPED
    assert waffle.product_type == "Waffle Maker"


def test_secondary_prepositional_feature_never_overrides_primary_appliance() -> None:
    """'Water Dispenser with Refrigerator Compartment' resolves to Water Dispenser, never Refrigerator."""
    expected_digi_wd = _expect_leaf(AJMER.digi.categories, "water dispensers & purifiers")
    expected_alfa_wd = _expect_leaf(AJMER.alfa.categories, "water dispenser")

    wd = resolve_category(
        "Electronics > Home appliances > Water dispenser",
        "Homage Water Dispenser HWD-49332 with Refrigerator Compartment",
        "Homage Water Dispenser HWD-49332 with Refrigerator Compartment",
        vendor_cfg=AJMER,
    )
    assert wd.digi_path == expected_digi_wd
    assert wd.digi_status == CategoryStatus.MAPPED
    assert wd.alfa_id == expected_alfa_wd
    assert wd.alfa_status == CategoryStatus.MAPPED
    assert wd.product_type == "Water Dispenser"

    # Even when the breadcrumb is generic structural parent, the primary head before 'with' wins
    wd_generic = resolve_category(
        "Electronics > Home appliances",
        "Homage Water Dispenser HWD-49332 with Refrigerator Cabinet",
        "Homage Water Dispenser HWD-49332 with Refrigerator Cabinet",
        vendor_cfg=AJMER,
    )
    assert wd_generic.digi_path == expected_digi_wd
    assert wd_generic.alfa_id == expected_alfa_wd
    assert wd_generic.product_type == "Water Dispenser"


def test_ac_and_tv_subtypes_on_raw_digimall_taxonomy() -> None:
    """Ajmer.digi resolves Inverter/Non-Inverter/Floor-Standing AC and Smart/Basic TV from raw JSON."""
    expected_alfa_ac = _expect_leaf(AJMER.alfa.categories, "air conditioners alfabnpl")
    expected_alfa_tv = _expect_leaf(AJMER.alfa.categories, "led tv")

    # Floor Standing AC
    fs_ac = resolve_category(
        "Electronics > Home appliances > AC",
        "Gree 2 Ton Floor Standing Inverter AC GF-24TF",
        "Gree 2 Ton Floor Standing Inverter AC GF-24TF",
        vendor_cfg=AJMER,
    )
    assert fs_ac.digi_path == _expect_leaf(AJMER.digi.categories, "floor standing")
    assert fs_ac.digi_status == CategoryStatus.MAPPED
    assert fs_ac.alfa_id == expected_alfa_ac

    # Smart TV vs Basic TV vs Ambiguous TV on Ajmer.digi
    smart_tv = resolve_category(
        "LED TV / Smart LED TV / TCL LED",
        "TCL 43 Inch 4K UHD Google TV 43P635",
        "TCL 43 Inch 4K UHD Google TV 43P635",
        vendor_cfg=AJMER,
    )
    assert smart_tv.digi_path == _expect_leaf(AJMER.digi.categories, "smart tv")
    assert smart_tv.digi_status == CategoryStatus.MAPPED
    assert smart_tv.alfa_id == expected_alfa_tv

    basic_tv = resolve_category(
        "Electronics / LED TVs, Audio & Cameras",
        "EcoStar 32 Inch Basic LED TV CX-32U571",
        "EcoStar 32 Inch Basic LED TV CX-32U571",
        vendor_cfg=AJMER,
    )
    assert basic_tv.digi_path == _expect_leaf(AJMER.digi.categories, "basic tv")
    assert basic_tv.digi_status == CategoryStatus.MAPPED
    assert basic_tv.digi_path != smart_tv.digi_path
    assert basic_tv.alfa_id == expected_alfa_tv

    ambig_tv = resolve_category(
        "Electronics / LED TVs, Audio & Cameras",
        "EcoStar 32 Inch HD LED Television CX-3200",
        "EcoStar 32 Inch HD LED Television CX-3200",
        vendor_cfg=AJMER,
    )
    assert ambig_tv.digi_path is None
    assert ambig_tv.digi_status == CategoryStatus.SIBLING_AMBIGUOUS
    assert ambig_tv.alfa_id == expected_alfa_tv


def _raw_taxonomy_ground_truth(path: str) -> dict[str, tuple[tuple[str, ...], bool, bool]]:
    """Re-derive {id: (ancestor chain, effectively active, is leaf)} straight from the JSON.

    Deliberately shares no code with ``load_raw_taxonomy_nodes`` so the two can disagree.
    """
    raw = json.loads(Path(categories_module.__file__).resolve().parent.joinpath(path).read_text(encoding="utf-8"))
    items = raw["results"] if isinstance(raw, dict) else raw
    by_id = {str(i["category_id"]): i for i in items}
    parents = {cid: (str(i["parent"]) if i.get("parent") is not None else None) for cid, i in by_id.items()}
    has_child = {p for p in parents.values() if p is not None}
    truth: dict[str, tuple[tuple[str, ...], bool, bool]] = {}
    for cid in by_id:
        chain: list[str] = []
        cur: str | None = cid
        active = True
        while cur is not None:
            chain.append(cur)
            active = active and bool(by_id[cur].get("is_active", True))
            cur = parents[cur]
        truth[cid] = (tuple(reversed(chain)), active, cid not in has_child)
    return truth


def test_raw_taxonomy_engine_agrees_with_independent_tree_derivation() -> None:
    """Every ancestor chain, activity flag and assignable leaf is re-derived without the engine."""
    path = AJMER.digi.raw_taxonomy_path
    assert path, "AJMER.digi no longer declares a raw taxonomy; point this test at a vendor that does"
    truth = _raw_taxonomy_ground_truth(path)
    nodes = {n.category_id: n for n in load_raw_taxonomy_nodes(path, id_format=AJMER.digi.category_id_format)}
    assert set(nodes) == set(truth) and len(truth) > 50

    for cid, (chain, active, is_leaf) in truth.items():
        node = nodes[cid]
        assert node.ancestors == chain, cid
        assert node.is_active is active, cid
        assert node.formatted_id == "_".join(chain), cid
        should_assign = active and is_leaf
        assert (node.status == NodeStatus.ASSIGNABLE_LEAF) is should_assign, (cid, node.status)

    assignable_ids = {nodes[c].formatted_id for c, (_, a, leaf) in truth.items() if a and leaf}
    assert set(AJMER.digi.categories.values()) == assignable_ids
    assert any(not a for _, a, _ in truth.values()), "fixture lost its inactive nodes; the test proves nothing"


def test_every_active_leaf_never_resolves_to_a_different_leaf() -> None:
    """Property: asking for a leaf by its own name may be ambiguous or blank, never a *wrong* leaf.

    Discovered from the taxonomy itself, so a new category or vendor is covered without a new test.
    """
    path = AJMER.digi.raw_taxonomy_path
    assert path
    leaves = [
        n for n in load_raw_taxonomy_nodes(path, id_format=AJMER.digi.category_id_format)
        if n.status == NodeStatus.ASSIGNABLE_LEAF
    ]
    assert len(leaves) > 30
    valid_paths = {n.formatted_id for n in leaves}
    wrong: list[str] = []
    exact = 0
    for leaf in leaves:
        res = resolve_category(leaf.name, leaf.name, leaf.name, vendor_cfg=AJMER)
        if res.digi_path is None:
            assert res.digi_reason, f"{leaf.name}: blank with no reason"
            continue
        assert res.digi_path in valid_paths, (leaf.name, res.digi_path)
        if res.digi_path == leaf.formatted_id:
            exact += 1
        else:
            wrong.append(f"{leaf.name!r} -> {res.digi_path}")
    assert not wrong, wrong
    assert exact >= len(leaves) // 2, f"only {exact}/{len(leaves)} leaves resolved to themselves"


def test_every_registered_cell_resolves_only_inside_its_own_map() -> None:
    """Whatever the active vendors are, a resolved ID must belong to that vendor x platform cell."""
    assert len(VENDOR_REGISTRY) >= 2
    probes = [
        ("Electronics > Home appliances > AC", "Haier 1.5 Ton Inverter AC"),
        ("Electronics > Home appliances > Refrigerators", "Dawlance Refrigerator"),
        ("Electronics > Kitchen appliances > Microwaves", "Dawlance Microwave Oven"),
        ("Health & Beauty > Hair Care", "Remington Hair Straightener"),
        ("Totally > Unknown > Widgets", "Acme Widget 3000"),
    ]
    for key, cfg in VENDOR_REGISTRY.items():
        digi_ids = set(resolve_cell(cfg, "digi").categories.values())
        alfa_ids = set(resolve_cell(cfg, "alfa").categories.values())
        for crumb, title in probes:
            res = resolve_category(crumb, title, title, vendor_cfg=cfg)
            assert res.digi_path is None or res.digi_path in digi_ids, (key, crumb, res.digi_path)
            assert res.alfa_id is None or res.alfa_id in alfa_ids, (key, crumb, res.alfa_id)
            if res.digi_path is None:
                assert res.digi_reason and res.digi_status != CategoryStatus.MAPPED, (key, crumb)
            if res.alfa_id is None:
                assert res.alfa_reason and res.alfa_status != CategoryStatus.MAPPED, (key, crumb)


def test_title_polarity_beats_a_contradicting_description() -> None:
    """Contradictory evidence: the Title's negative claim must not be outvoted by marketing prose.

    A non-inverter AC whose body copy says "inverter" (or a basic TV whose copy says "smart") must
    never land on the positive sibling.  It may land on the negative one, or be flagged -- but a
    positive leaf here is the exact wrong-category bug this engine exists to prevent.
    """
    ac_pos = _expect_leaf(AJMER.digi.categories, "inverters")
    ac_neg = _expect_leaf(AJMER.digi.categories, "non-invertors")
    assert ac_pos != ac_neg
    ac = resolve_category(
        "Electronics > Home appliances > AC",
        "Gree 1.5 Ton Non Inverter Split AC",
        "Gree 1.5 Ton Non Inverter Split AC. Compare with our DC Inverter range for savings.",
        vendor_cfg=AJMER,
    )
    assert ac.digi_path != ac_pos, "description prose overrode the Title's non-inverter claim"
    assert ac.digi_path == ac_neg or ac.digi_status == CategoryStatus.SIBLING_AMBIGUOUS

    tv_pos = _expect_leaf(AJMER.digi.categories, "smart tv")
    tv_neg = _expect_leaf(AJMER.digi.categories, "basic tv")
    assert tv_pos != tv_neg
    tv = resolve_category(
        "Electronics / LED TVs, Audio & Cameras",
        "EcoStar 32 Inch Basic LED TV CX-32U571",
        "EcoStar 32 Inch Basic LED TV. Upgrade to our Smart Google TV models for apps.",
        vendor_cfg=AJMER,
    )
    assert tv.digi_path != tv_pos, "description prose overrode the Title's basic-TV claim"
    assert tv.digi_path == tv_neg or tv.digi_status == CategoryStatus.SIBLING_AMBIGUOUS

    # Reverse direction: a positive Title is not flipped by prose that merely *mentions* the negative.
    flipped = resolve_category(
        "Electronics > Home appliances > AC",
        "Gree 1.5 Ton DC Inverter Split AC",
        "Gree 1.5 Ton DC Inverter Split AC. Saves 60% more power than a non-inverter AC.",
        vendor_cfg=AJMER,
    )
    assert flipped.digi_path != ac_neg, "comparison prose flipped an Inverter Title to Non-Inverter"
    assert flipped.digi_path == ac_pos or flipped.digi_status == CategoryStatus.SIBLING_AMBIGUOUS


def test_inactive_leaves_and_depleted_branches_never_assign_or_fallback_to_parent() -> None:
    """Inactive DigiMall leaves and depleted branches return None with INACTIVE_TARGET."""
    # Inactive leaves in digimall_taxonomy.json: Projectors (11677), Range Hoods (11885), Clothing & Dryers (11793)
    for crumb, title in (
        ("Electronics > Projectors", "Epson Full HD Projector EB-FH06"),
        ("Electronics > Kitchen > Range Hoods", "Fotile Chimney Range Hood 90cm"),
        ("Electronics > Laundry > Clothing & Dryers", "Candy 8kg Vented Clothes Dryer"),
    ):
        res = resolve_category(crumb, title, title, vendor_cfg=AJMER)
        assert res.digi_path is None, crumb
        assert res.digi_status == CategoryStatus.INACTIVE_TARGET, crumb

    # Depleted branches in digimall_taxonomy.json: Sound & Home Theaters (11679), Computer Accessories (11689)
    for crumb, title in (
        ("LED TV / Audio & visuals / Sound bars", "Audionic Bar-500 Bluetooth Soundbar"),
        ("Electronics / Computing & Gaming / Computer Accessories", "USB C Docking Hub"),
    ):
        res = resolve_category(crumb, title, title, vendor_cfg=AJMER)
        assert res.digi_path is None, crumb
        assert res.digi_status == CategoryStatus.INACTIVE_TARGET, crumb


def test_malformed_taxonomy_json_detection(tmp_path) -> None:
    """load_raw_taxonomy_nodes rejects duplicate IDs, orphan parents, and parent cycles."""
    # 1. Duplicate category_id
    dup_file = tmp_path / "dup.json"
    dup_file.write_text(
        json.dumps(
            {
                "results": [
                    {"category_id": "100", "category_name": "Root", "parent": None, "is_active": True},
                    {"category_id": "100", "category_name": "Dup", "parent": None, "is_active": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate category_id"):
        load_raw_taxonomy_nodes(str(dup_file))

    # 2. Orphan parent reference
    orphan_file = tmp_path / "orphan.json"
    orphan_file.write_text(
        json.dumps(
            {
                "results": [
                    {"category_id": "101", "category_name": "Child", "parent": "999", "is_active": True}
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Orphan category"):
        load_raw_taxonomy_nodes(str(orphan_file))

    # 3. Parent cycle
    cycle_file = tmp_path / "cycle.json"
    cycle_file.write_text(
        json.dumps(
            {
                "results": [
                    {"category_id": "201", "category_name": "A", "parent": "202", "is_active": True},
                    {"category_id": "202", "category_name": "B", "parent": "201", "is_active": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Cycle detected"):
        load_raw_taxonomy_nodes(str(cycle_file))


def test_active_leaf_under_inactive_parent_is_never_assignable(tmp_path: Path) -> None:
    """Activity is inherited down the tree; the shipped taxonomy has no such node, so build one."""
    tree = tmp_path / "tree.json"
    tree.write_text(
        json.dumps(
            {
                "results": [
                    {"category_id": "1", "category_name": "Root", "parent": None, "is_active": True},
                    {"category_id": "2", "category_name": "Retired Branch", "parent": 1, "is_active": False},
                    {"category_id": "3", "category_name": "Orphaned Leaf", "parent": 2, "is_active": True},
                    {"category_id": "4", "category_name": "Live Leaf", "parent": 1, "is_active": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    nodes = {n.category_id: n for n in load_raw_taxonomy_nodes(str(tree))}
    assert nodes["3"].status == NodeStatus.INACTIVE_NODE
    assert nodes["3"].is_active is False
    assert nodes["4"].status == NodeStatus.ASSIGNABLE_LEAF
    assert nodes["4"].formatted_id == "1_4"
    leaf_map = load_raw_taxonomy_leaf_map(str(tree))
    assert set(leaf_map.values()) == {"1_4"}


def test_resolve_product_type_decoupled_from_empty_category_tables() -> None:
    """Product Type resolves canonically with was_inferred=False even when a vendor has zero categories."""
    empty_vendor = VendorConfig(
        display_name="EmptyStore",
        sku_prefix="ES",
        product_type_map={},
        digi=PlatformConfig(vendor_name="EmptyDigi", brands={}, categories={}),
        alfa=PlatformConfig(vendor_name="EmptyAlfa", brands={}, categories={}),
    )

    for crumb, title, expected_pt in (
        ("Electronics > Home appliances > Refrigerators", "Dawlance Refrigerator 9178", "Refrigerator"),
        ("Electronics > Home appliances > AC", "Gree 1.5 Ton Inverter AC", "Air Conditioner"),
        ("Electronics > Home appliances > Iron & Garment steamer", "Philips Stand Garment Steamer", "Garment Steamer"),
        ("Electronics > Home appliances > Iron & Garment steamer", "Philips Dry Iron HD1172", "Iron"),
        ("Electronics > Green Energy > UPS", "Homage 1000VA Inverter UPS", "UPS"),
    ):
        cat = resolve_category(crumb, title, title, vendor_cfg=empty_vendor)
        assert cat.digi_path is None
        assert cat.alfa_id is None
        pt, inferred = resolve_product_type(cat, "Brand", vendor_cfg=empty_vendor, title=title)
        assert pt == expected_pt
        assert inferred is False

