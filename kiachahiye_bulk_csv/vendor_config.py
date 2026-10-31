"""Single source of truth for every vendor and their platform configurations.

╔══════════════════════════════════════════════════════════════════════╗
║  ██  ADD A VENDOR HERE  ██                                            ║
║  1. Copy the KIACHAHIYE block below.                                  ║
║  2. Change the keys (sku_prefix, vendor_digi, vendor_alfa, ...).      ║
║  3. Fill in brands_digi, brands_alfa, categories_digi, categories_alfa║
║  4. Run `python run_ui.py` -- the new vendor appears in the menu.     ║
║  No other file needs to change.                                       ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from description_builder import (
    DescriptionTemplate,
    template_for,
    template_problems,
)

TitleFormula = Callable[[dict[str, str]], str]


class ConfigError(ValueError):
    """Raised when a VendorConfig is structurally invalid."""


@dataclass(frozen=True)
class PlatformConfig:
    """Per-platform settings for one vendor."""

    vendor_name: str  # written verbatim into the "Vendor" column
    brands: dict[str, int]  # normalized_brand_key -> platform brand id
    categories: dict[str, str]  # category_key -> platform category path/id
    # This (store x platform) cell's Description shape: a name in
    # description_builder.DESCRIPTION_TEMPLATES, or a DescriptionTemplate written here.
    # One cell's value moves one file: two stores naming the same template share it,
    # and a store that says nothing ships the spec table the shop has always uploaded.
    description_template: str | DescriptionTemplate = "spec_table"


@dataclass(frozen=True)
class VendorConfig:
    """Complete configuration for one vendor (store)."""

    display_name: str  # shown in terminal menus: "Kiachahiye", "Ajmer"
    sku_prefix: str  # e.g. "KC" -> SKU becomes KC-WD-1051HC
    digi: PlatformConfig
    alfa: PlatformConfig
    brand_aliases: dict[str, str] = field(default_factory=dict)
    brand_display_map: dict[str, str] = field(default_factory=dict)
    digi_segment_aliases: dict[str, str] = field(default_factory=dict)
    alfa_segment_aliases: dict[str, str] = field(default_factory=dict)
    product_type_map: dict[str, str] = field(default_factory=dict)
    # Optional title-formula override: "standard" | "brand_first_extended" | custom callable
    title_formula: str | TitleFormula = "standard"
    # Numeric and rule defaults
    default_variant_quantity: int = 20
    default_product_type_colors: dict[str, str] = field(
        default_factory=lambda: {"LED TV": "Black"}
    )
    omit_title_color_categories: frozenset[str] = field(
        default_factory=lambda: frozenset({"LED TV"})
    )
    strict_title_rebuild: bool = True
    apply_tv_warranty_table: bool = True


_SHARED_BRAND_ALIASES: dict[str, str] = {
    "superasia": "super asia",
    "xiaomi": "xioami",
    "dawlanc": "dawlance",
    "dawlance pakistan": "dawlance",
    "haier pakistan": "haier",
    "pel ": "pel",
    "pak electron": "pel",
    "pak electron limited": "pel",
    "orient electronics": "orient",
    "gree pakistan": "gree",
    "tcl pakistan": "tcl",
    "midea pakistan": "midea",
    "kenwood pakistan": "kenwood",
    "west point": "westpoint",
    "super-asia": "super asia",
    "eco star": "ecostar",
    "anex pakistan": "anex",
}

_SHARED_BRAND_DISPLAY_MAP: dict[str, str] = {
    "super asia": "Super Asia",
    "superasia": "Super Asia",
    "dawlance": "Dawlance",
    "haier": "Haier",
    "pel": "PEL",
    "gree": "Gree",
    "ecostar": "EcoStar",
    "eco star": "EcoStar",
    "kenwood": "Kenwood",
    "tcl": "TCL",
    "orient": "Orient",
    "midea": "Midea",
    "westpoint": "Westpoint",
    "west point": "Westpoint",
    "anex": "Anex",
    "homage": "Homage",
    "hisense": "Hisense",
    "iffalcon": "iFFalcon",
    "nasgas": "Nasgas",
    "jackpot": "Jackpot",
    "xiaomi": "Xiaomi",
    "xioami": "Xiaomi",
    "super general": "Super General",
    "philips": "Philips",
    "braun": "Braun",
    "samsung": "Samsung",
}

_SHARED_PRODUCT_TYPE_MAP: dict[str, str] = {
    "air coolers": "Air Cooler",
    "air cooler": "Air Cooler",
    "air purifiers": "Air Purifier",
    "ac inverter": "Air Conditioner",
    "ac non-inverter": "Air Conditioner",
    "air conditioner": "Air Conditioner",
    "air conditioners alfabnpl": "Air Conditioner",
    "ac": "Air Conditioner",
    "fans": "Fan",
    "heaters": "Heater",
    "microwaves": "Microwave Oven",
    "water dispenser": "Water Dispenser",
    "dishwashers": "Dishwasher",
    "dish washer": "Dishwasher",
    "dishwashing": "Dishwashing",
    "refrigerators": "Refrigerator",
    "freezers": "Deep Freezer",
    "deep freezer": "Deep Freezer",
    "ovens": "Oven",
    "oven": "Oven",
    "cooking range": "Cooking Range",
    "irons": "Iron",
    "iron & garment steamer": "Iron",
    "vacuum cleaners": "Vacuum Cleaner",
    "washing machines": "Washing Machine",
    "washing machine": "Washing Machine",
    "juicers": "Juicer",
    "mixers": "Mixer",
    "blenders": "Blender",
    "food processors": "Food Processor",
    "food factory": "Food Processor",
    "air fryers": "Air Fryer",
    "air fryer": "Air Fryer",
    "grinders": "Grinder",
    "sandwich maker": "Sandwich Maker",
    "toaster": "Toaster",
    "hair straightener": "Hair Straightener",
    "geysers": "Geyser",
    "coffee maker": "Coffee Maker",
    "led tv": "LED TV",
    "smart led tv": "LED TV",
    "baking & flavours": "Baking & Flavours",
}

# ---------------------------------------------------------------------------
# KIACHAHIYE  (Store 1 -- migrated from config.py / brands.py / categories.py)
# ---------------------------------------------------------------------------
KIACHAHIYE = VendorConfig(
    display_name="Kiachahiye",
    sku_prefix="KIA",
    title_formula="vip_pipe",
    brand_aliases=dict(_SHARED_BRAND_ALIASES),
    brand_display_map=dict(_SHARED_BRAND_DISPLAY_MAP),
    digi_segment_aliases={
        "deep freezer": "freezers",
        "freezers": "freezers",
        "washing machine": "washing machines",
        "air purifier & humdifier": "air purifiers",
        "air purifier": "air purifiers",
        "air humidifier": "air purifiers",
        "iron": "irons",
        "irons": "irons",
        "iron & garment steamer": "irons",
        "garment steamer": "irons",
        "microwave oven": "microwaves",
        "microwave ovens": "microwaves",
    },
    alfa_segment_aliases={
        "deep freezer": "deep freezer",
        "air purifier & humdifier": "air purifiers",
        "iron": "iron & garment steamer",
        "irons": "iron & garment steamer",
        "iron & garment steamer": "iron & garment steamer",
        "garment steamer": "iron & garment steamer",
        "cooking range": "cooking range",
        "microwave oven": "microwaves",
        "microwave ovens": "microwaves",
    },
    product_type_map=dict(_SHARED_PRODUCT_TYPE_MAP),
    digi=PlatformConfig(
        vendor_name="KiaChahiye PVT LTD",
        brands={
            "gree": 3790,
            "ecostar": 3789,
            "westpoint": 3779,
            "super asia": 3776,
            "midea": 3774,
            "tcl": 3773,
            "orient": 3769,
            "anex": 3766,
            "pel": 3761,
            "haier": 3759,
            "dawlance": 3755,
            "kenwood": 3754,
        },
        categories={
            "air coolers": "11639_11643_11653_11654",
            "air purifiers": "11639_11643_11653_11655",
            "ac inverter": "11639_11643_11653_11782_11783",
            "ac non-inverter": "11639_11643_11653_11782_11784",
            "fans": "11639_11643_11653_11786",
            "heaters": "11639_11643_11653_11813",
            "microwaves": "11639_11643_11661_11666",
            "water dispenser": "11639_11643_11661_11669",
            "dishwashers": "11639_11643_11661_11747",
            "refrigerators": "11639_11643_11661_11787",
            "freezers": "11639_11643_11661_11788",
            "ovens": "11639_11643_11661_11789",
            "irons": "11639_11643_11748_11749",
            "vacuum cleaners": "11639_11643_11751_11795",
            "washing machines": "11639_11643_11791_11792",
            "juicers": "11639_11643_11802_11804",
            "mixers": "11639_11643_11802_11805",
            "blenders": "11639_11643_11802_11806",
            "food processors": "11639_11643_11802_11807",
            "air fryers": "11639_11643_11802_11808",
            "grinders": "11639_11643_11802_11809",
            "sandwich maker": "11639_11643_11802_11814",
            "toaster": "11639_11643_11802_11815",
            "hair straightener": "11773_11777_11823",
        },
    ),
    alfa=PlatformConfig(
        vendor_name="Kia Chahiye Pvt Ltd",
        brands={
            "super general": 4133,
            "midea": 3821,
            "philips": 3802,
            "anex": 3789,
            "braun": 3768,
            "hisense": 3766,
            "westpoint": 3762,
            "gree": 3678,
            "kenwood": 3677,
            "orient": 3676,
            "ecostar": 3675,
            "haier": 3674,
            "dawlance": 3673,
            "samsung": 3669,
        },
        categories={
            "air cooler": "11511",
            "air coolers": "11511",
            "iron & garment steamer": "11515",
            "washing machine": "11506",
            "washing machines": "11506",
            "refrigerators": "11507",
            "water dispenser": "11509",
            "microwaves": "11519",
            "cooking range": "11526",
            "led tv": "11539",
            "baking & flavours": "11856",
            "air conditioners alfabnpl": "12353",
        },
    ),
)

# ---------------------------------------------------------------------------
# AJMER  (Store 2 -- Alfa populated with the platform's 14 brands & its 8 active leaves; Digi left empty)
# ---------------------------------------------------------------------------
AJMER = VendorConfig(
    display_name="Ajmer",
    sku_prefix="AJ",
    title_formula="standard",
    brand_aliases=dict(_SHARED_BRAND_ALIASES),
    brand_display_map=dict(_SHARED_BRAND_DISPLAY_MAP),
    digi_segment_aliases={
        "deep freezer": "freezers",
        "freezers": "freezers",
        "washing machine": "washing machines",
        "air purifier & humdifier": "air purifiers",
        "air purifier": "air purifiers",
        "air humidifier": "air purifiers",
        "iron": "irons",
        "irons": "irons",
        "iron & garment steamer": "irons",
        "garment steamer": "irons",
        "microwave oven": "microwaves",
        "microwave ovens": "microwaves",
    },
    alfa_segment_aliases={
        "microwave oven": "microwaves",
        "microwave ovens": "microwaves",
    },
    product_type_map=dict(_SHARED_PRODUCT_TYPE_MAP),
    digi=PlatformConfig(
        vendor_name="Ajmer PVT LTD",  # TODO: confirm exact DigiMall vendor string when ready
        brands={
            # TODO: fill from DigiMall admin panel for Ajmer's seller account
        },
        categories={
            # TODO: fill from DigiMall admin panel for Ajmer's category tree
        },
    ),
    alfa=PlatformConfig(
        vendor_name="Ajmer Electronics",
        brands={
            # Ajmer's Alfa brand list, exactly as the platform returns it.  Kept as its own
            # dict rather than shared with KiaChahiye even while the two agree: the day one
            # store's account gets a different brand id, a shared constant would change the
            # other store's upload without anyone editing it.
            "super general": 4133,
            "midea": 3821,
            "philips": 3802,
            "anex": 3789,
            "braun": 3768,
            "hisense": 3766,
            "westpoint": 3762,
            "gree": 3678,
            "kenwood": 3677,
            "orient": 3676,
            "ecostar": 3675,
            "haier": 3674,
            "dawlance": 3673,
            "samsung": 3669,
        },
        categories={
            # Ajmer's Alfa tree exactly as the platform lists it.  Alfa takes the
            # bare leaf id.  "Cooking range" (11526) and "Baking & Flavours"
            # (11856) exist in the tree but are is_active:false, so nothing is
            # routed to them; there is no Deep Freezer / Geyser leaf at all, so
            # those rows ship with an empty Category and a category_missing_alfa
            # flag until the platform opens a leaf for them.
            "washing machine": "11506",
            "refrigerators": "11507",
            "water dispenser": "11509",
            "air cooler": "11511",
            "iron & garment steamer": "11515",
            "microwaves": "11519",
            "led tv": "11539",
            "air conditioners alfabnpl": "12353",
        },
    ),
)

# ---------------------------------------------------------------------------
# REGISTRY -- every key here appears in the terminal menu automatically
# ---------------------------------------------------------------------------
VENDOR_REGISTRY: dict[str, VendorConfig] = {
    "kiachahiye": KIACHAHIYE,
    "ajmer": AJMER,
}


def _description_template_errors(cfg: VendorConfig, platform: str) -> list[str]:
    """Why one cell's `description_template` cannot ship, one string per reason.

    Checked here rather than at upload time because the shop's gate reads the built
    Description with markup-shaped rules: a template those rules cannot follow has to
    stop the run at the terminal, naming the exact cell to edit -- not sit unaudited
    in a live listing.
    """
    cell = getattr(cfg, platform)
    label = f"{cfg.display_name}.{platform}.description_template"
    value = cell.description_template
    try:
        template = template_for(value)
    except ValueError as error:
        return [f"{label} -- {error}"]
    return [f"{label} ({template.name}) -- {problem}"
            for problem in template_problems(template)]


def validate_vendor_cfg(cfg: VendorConfig) -> None:
    """Fail loudly if required fields are absent or obviously wrong."""
    errors: list[str] = []
    if not cfg.sku_prefix or not cfg.sku_prefix.replace("-", "").isalnum():
        errors.append(f"sku_prefix {cfg.sku_prefix!r} must be a non-empty alphanumeric string")
    if not cfg.digi.vendor_name.strip():
        errors.append("digi.vendor_name is empty")
    if not cfg.alfa.vendor_name.strip():
        errors.append("alfa.vendor_name is empty")
    if cfg.digi.vendor_name.strip() == cfg.alfa.vendor_name.strip():
        errors.append(
            f"digi.vendor_name and alfa.vendor_name must differ "
            f"(both are {cfg.digi.vendor_name!r})"
        )
    for platform in ("digi", "alfa"):
        errors.extend(_description_template_errors(cfg, platform))
    if errors:
        raise ConfigError(
            f"VendorConfig '{cfg.display_name}' is invalid:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def get_vendor(key: str) -> VendorConfig:
    """Fail loudly when a key is not registered or structurally invalid."""
    norm = key.strip().lower()
    if norm not in VENDOR_REGISTRY:
        raise KeyError(
            f"Vendor {key!r} not found. "
            f"Available vendors: {list(VENDOR_REGISTRY)}"
        )
    cfg = VENDOR_REGISTRY[norm]
    validate_vendor_cfg(cfg)
    return cfg
