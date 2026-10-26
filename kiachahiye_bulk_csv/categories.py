"""Sections 4 and 5 -- category classification and Product Type, both platforms.

╔══════════════════════════════════════════════════════════════════════════╗
║  ██  EDIT HERE  ██  -- category id tables for each platform              ║
║                                                                            ║
║  CATEGORY_DIGI_PATHS  : DigiMall needs the FULL underscore-joined         ║
║                         root-to-leaf path (e.g. 11639_11643_11661_11669). ║
║  CATEGORY_ALFA_IDS    : Alfa needs ONLY the bare leaf id (e.g. 11509).    ║
║  PRODUCT_TYPE_MAP     : the plain-text "Product Type" column, shared by   ║
║                         both output files.                                ║
║                                                                            ║
║  The values below are final, verified output strings.  The code never     ║
║  reconstructs or concatenates an id -- it returns the table's literal     ║
║  value unmodified.  To add a category, add a key to the relevant table    ║
║  AND a matching key in PRODUCT_TYPE_MAP.                                  ║
║                                                                            ║
║  DIGI_SEGMENT_ALIASES / ALFA_SEGMENT_ALIASES                              ║
║      Breadcrumb wording varies ("Deep Freezer" vs the table's "freezers", ║
║      "Air purifier & humdifier" vs "air purifiers").  When a breadcrumb   ║
║      segment does not match a table key, add the segment wording here     ║
║      pointing at the table key it should resolve to.                      ║
║                                                                            ║
║  A miss on one platform's table NEVER blanks the other platform's cell.   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from models import ResolvedCategory

if TYPE_CHECKING:
    from vendor_config import VendorConfig

# ===========================================================================
#  EDIT HERE -- DigiMall: full root-to-leaf path, underscore-joined
# ===========================================================================
CATEGORY_DIGI_PATHS: dict[str, str] = {
    "air coolers": "11639_11643_11653_11654",
    "air purifiers": "11639_11643_11653_11655",
    "ac inverter": "11639_11643_11653_11782_11783",  # Air Conditioners > Inverters
    "ac non-inverter": "11639_11643_11653_11782_11784",  # Air Conditioners > Non-Invertors
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
    # NOTE (do not remove this comment): DigiMall has NO "LED TV" leaf anywhere
    # in its tree, and no leaf for geysers / sound bars / speakers / UPS.
    # Products in those groups get an EMPTY DigiMall Category plus a QC flag.
    # If DigiMall adds any of those leaves later, just add the entry here.
}

# ===========================================================================
#  EDIT HERE -- Alfa: bare leaf id only, never a joined path
# ===========================================================================
CATEGORY_ALFA_IDS: dict[str, str] = {
    # Leaves from Alfa category tree:
    # 11504 -> 11506 (Washing machine), 11507 (Refrigerators), 11509 (Water dispenser), 11511 (Air cooler), 11515 (Iron & Garment steamer)
    "air cooler": "11511",
    "air coolers": "11511",
    "iron & garment steamer": "11515",
    "washing machine": "11506",
    "washing machines": "11506",
    "refrigerators": "11507",
    "water dispenser": "11509",
    # 11518 -> 11519 (Microwaves), 11526 (Cooking range)
    "microwaves": "11519",
    "cooking range": "11526",
    # Root: 11539 (LED TV)
    "led tv": "11539",
    # 11855 -> 11856 (Baking & Flavours)
    "baking & flavours": "11856",
    # 12351 -> 12353 (Air Conditioners AlfaBNPL)
    "air conditioners alfabnpl": "12353",
}

# ===========================================================================
#  EDIT HERE -- breadcrumb wording -> table key (only when wording differs)
# ===========================================================================
DIGI_SEGMENT_ALIASES: dict[str, str] = {
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
}

ALFA_SEGMENT_ALIASES: dict[str, str] = {
    "deep freezer": "deep freezer",
    "air purifier & humdifier": "air purifiers",  # not in Alfa table -> stays unresolved
    "iron": "iron & garment steamer",
    "irons": "iron & garment steamer",
    "iron & garment steamer": "iron & garment steamer",
    "garment steamer": "iron & garment steamer",
    "cooking range": "cooking range",
    "microwave oven": "microwaves",
    "microwave ovens": "microwaves",
}

# Breadcrumb wordings that mean "this row sits OUTSIDE the mapped catalogue".
# When the most specific segment is one of these, the walk stops immediately and
# that platform's Category stays EMPTY -- it must not fall through to a parent
# segment that happens to match (e.g. "Sound bars" sitting under an "LED TV"
# root is NOT a TV).  If a later sheet has a genuine UPS/Speaker category, add
# its id to the id table above and delete the wording from these sets.
STOP_SEGMENTS: set[str] = {
    "sound bars",
    "soundbar",
    "speakers",
    "ups",
    "audio & visuals",
    "green energy",
}

# ===========================================================================
#  EDIT HERE -- plain-text Product Type column (shared by BOTH output files)
# ===========================================================================
PRODUCT_TYPE_MAP: dict[str, str] = {
    "air coolers": "Air Cooler",
    "air cooler": "Air Cooler",
    "air purifiers": "Air Purifier",
    "ac inverter": "Air Conditioner",
    "ac non-inverter": "Air Conditioner",
    "air conditioner": "Air Conditioner",  # Alfa's flat AC leaf
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
    "air fryers": "Air Fryer",
    "air fryer": "Air Fryer",
    "grinders": "Grinder",
    "sandwich maker": "Sandwich Maker",
    "toaster": "Toaster",
    "hair straightener": "Hair Straightener",
    "geysers": "Geyser",
    "coffee maker": "Coffee Maker",
    "food factory": "Food Processor",
    "led tv": "LED TV",
    "smart led tv": "LED TV",
    "baking & flavours": "Baking & Flavours",
}

# Delimiters commonly used in product hierarchy breadcrumbs: "/", ">", "|", ">>"
_BREADCRUMB_DELIM_RE = re.compile(r"\s*(?:[/>|]+)\s*")

# Keywords that mark a breadcrumb segment as belonging to the AC group.
_AC_SEGMENT_RE = re.compile(r"\bac\b|\bair[\s\-_]?condition(?:er|ers|ing)?\b", re.IGNORECASE)
# Keywords that mark a breadcrumb segment as belonging to the LED-TV group.
_LED_SEGMENT_RE = re.compile(r"\b(?:[qo]?led)\b")
# Inverter / non-inverter signals, checked in this order (negation first).
_NON_INVERTER_RE = re.compile(r"\bnon[\s\-_]?inverter\b|\bnon[\s\-_]?inv\b", re.IGNORECASE)
_INVERTER_RE = re.compile(
    r"\binverter\b|\bdc inverter\b|\bt-?ai\b|\bbldc\b|\binverteron\b", re.IGNORECASE
)
_SMART_TV_RE = re.compile(r"\bsmart\b|\bgoogle\s?tv\b|\bandroid\b|\bandriod\b", re.IGNORECASE)

# Group markers used internally; never written to a CSV cell.
_GROUP_AC = "__ac_group__"
_GROUP_LED = "__led_group__"


def _singularise(words: str) -> str:
    """Very small, explicit plural fold used only for table-key comparison."""
    return re.sub(r"\b([a-z]{4,})s\b", r"\1", words)


def _word_in(phrase: str, text: str) -> bool:
    """True when ``phrase`` appears as whole word(s) inside ``text``."""
    return bool(phrase and re.search(rf"\b{re.escape(phrase)}\b", text))


def _match_table_key(segment: str, table_keys: list[str]) -> str | None:
    """Find the table key a breadcrumb segment refers to, or ``None``.

    Order of attempts, all deterministic:
      1. exact key equality
      2. exact equality ignoring a trailing plural "s"
      3. the key (or its singular form) appears as whole word(s) inside the segment
      4. the segment (or its singular form) appears as whole word(s) inside the key
    """
    if segment in table_keys:
        return segment
    folded = _singularise(segment)
    for key in table_keys:
        if _singularise(key) == folded:
            return key
    for key in table_keys:
        if _word_in(key, segment) or _word_in(_singularise(key), folded):
            return key
    for key in table_keys:
        if _word_in(segment, key) or _word_in(folded, _singularise(key)):
            return key
    return None


def _resolve_group(
    segments: list[str],
    digi: bool,
    table: dict[str, str] | None = None,
    aliases: dict[str, str] | None = None,
) -> tuple[str | None, str]:
    """Walk breadcrumb segments most specific -> least, returning (key|GROUP, reason)."""
    active_table = (
        table
        if table is not None
        else (CATEGORY_DIGI_PATHS if digi else CATEGORY_ALFA_IDS)
    )
    table_keys = list(active_table)
    active_aliases = (
        aliases
        if aliases is not None
        else (DIGI_SEGMENT_ALIASES if digi else ALFA_SEGMENT_ALIASES)
    )
    for segment in reversed(segments):
        if segment in STOP_SEGMENTS:
            return None, "segment marked as outside the mapped catalogue"
        if _AC_SEGMENT_RE.search(segment):
            return _GROUP_AC, "ac group"
        if _LED_SEGMENT_RE.search(segment):
            return _GROUP_LED, "led group"
        key = active_aliases.get(segment)
        if key is None:
            key = _match_table_key(segment, table_keys)
        if key is not None and key in table_keys:
            return key, "matched"
    return None, "unmatched"


def _ac_inverter_key(text: str) -> tuple[str | None, str]:
    """Decide DigiMall's inverter vs non-inverter AC leaf from the row's own text."""
    if _NON_INVERTER_RE.search(text):
        return "ac non-inverter", "non-inverter signal"
    if _INVERTER_RE.search(text):
        return "ac inverter", "inverter signal"
    return None, (
        "air conditioner with no inverter/non-inverter signal in Title OR Description -- "
        "DigiMall has separate Inverter and Non-Invertor leaves, so this needs a human decision"
    )


def resolve_category(
    raw_breadcrumb: str,
    digi_text: str,
    alfa_text: str,
    vendor_cfg: VendorConfig | None = None,
) -> ResolvedCategory:
    """Resolve one breadcrumb string for BOTH platforms, independently.

    ``digi_text`` / ``alfa_text`` are the row's Title + Description, passed
    separately because the two platforms key off different signals (DigiMall
    needs inverter status, Alfa needs TV smartness).
    """
    digi_cats = (
        vendor_cfg.digi.categories if vendor_cfg is not None else CATEGORY_DIGI_PATHS
    )
    alfa_cats = (
        vendor_cfg.alfa.categories if vendor_cfg is not None else CATEGORY_ALFA_IDS
    )
    digi_aliases = (
        vendor_cfg.digi_segment_aliases
        if vendor_cfg is not None and vendor_cfg.digi_segment_aliases
        else DIGI_SEGMENT_ALIASES
    )
    alfa_aliases = (
        vendor_cfg.alfa_segment_aliases
        if vendor_cfg is not None and vendor_cfg.alfa_segment_aliases
        else ALFA_SEGMENT_ALIASES
    )
    segments = [s.strip().lower() for s in _BREADCRUMB_DELIM_RE.split(raw_breadcrumb) if s.strip()]

    # ---- DigiMall ---------------------------------------------------------
    digi_key, _ = _resolve_group(
        segments, digi=True, table=digi_cats, aliases=digi_aliases
    )
    digi_path: str | None = None
    digi_reason = ""
    if digi_key == _GROUP_AC:
        ac_key, ac_reason = _ac_inverter_key(digi_text)
        if ac_key is not None:
            digi_path = digi_cats.get(ac_key)
            if digi_path is None:
                digi_reason = (
                    f"DigiMall category key {ac_key!r} is not configured for this vendor"
                )
        else:
            digi_reason = ac_reason
    elif digi_key == _GROUP_LED:
        digi_reason = (
            "no DigiMall category exists for LED TV -- confirmed gap in current tree"
        )
    elif digi_key is None:
        digi_reason = (
            f"breadcrumb {raw_breadcrumb!r} did not match any DigiMall category key -- "
            "add a keyword or a DIGI_SEGMENT_ALIASES entry"
        )
    else:
        digi_path = digi_cats.get(digi_key)

    # ---- Alfa -------------------------------------------------------------
    alfa_key, _ = _resolve_group(
        segments, digi=False, table=alfa_cats, aliases=alfa_aliases
    )
    alfa_id: str | None = None
    alfa_reason = ""
    if alfa_key == _GROUP_AC:
        alfa_id = (
            alfa_cats.get("air conditioners alfabnpl")
            or alfa_cats.get("air conditioner")
            or alfa_cats.get("ac")
        )
    elif alfa_key == _GROUP_LED:
        # If smart led tv is present in the row text or leaf segment use it, otherwise use led tv
        is_smart_tv = bool(
            _SMART_TV_RE.search(alfa_text)
            or (segments and _SMART_TV_RE.search(segments[-1]))
        )
        alfa_id = (
            alfa_cats.get("smart led tv")
            if is_smart_tv and "smart led tv" in alfa_cats
            else alfa_cats.get("led tv")
        )
    elif alfa_key is None:
        alfa_reason = (
            f"breadcrumb {raw_breadcrumb!r} did not match any Alfa category key -- "
            "add a keyword or an ALFA_SEGMENT_ALIASES entry"
        )
    else:
        alfa_id = alfa_cats.get(alfa_key)

    real_digi = digi_key if digi_key in digi_cats else None
    real_alfa = alfa_key if alfa_key in alfa_cats else None
    reason = digi_reason or alfa_reason
    return ResolvedCategory(
        raw=raw_breadcrumb,
        digi_path=digi_path,
        alfa_id=alfa_id,
        matched_key=real_digi or real_alfa,
        reason=reason,
        digi_reason=digi_reason,
        alfa_reason=alfa_reason,
    )


def _infer_product_type(category: ResolvedCategory, source_brand: str) -> str:
    """Section 5 fallback: a plain generic singular name from the product's own words."""
    segments = [s.strip() for s in _BREADCRUMB_DELIM_RE.split(category.raw) if s.strip()]
    last = segments[-1] if segments else category.raw.strip()
    last = re.sub(re.escape(source_brand), "", last, flags=re.IGNORECASE).strip(" -")
    if last.isupper():
        return last  # keep acronyms such as UPS exactly as the sheet spells them
    if len(last) > 3 and last.lower().endswith("s") and not last.lower().endswith(("ss", "us")):
        last = last[:-1]
    return last.title() if last else "Product"


def resolve_product_type(
    category: ResolvedCategory,
    source_brand: str,
    vendor_cfg: VendorConfig | None = None,
) -> tuple[str, bool]:
    """Return ``(product_type, was_inferred)``.

    Product Type is never left blank in either output file: if neither
    platform's table matched, a generic singular name is derived from the
    product's own breadcrumb and the row is flagged for a human glance.
    """
    pt_map = (
        vendor_cfg.product_type_map
        if vendor_cfg is not None and vendor_cfg.product_type_map
        else PRODUCT_TYPE_MAP
    )
    alfa_cats = (
        vendor_cfg.alfa.categories if vendor_cfg is not None else CATEGORY_ALFA_IDS
    )
    digi_cats = (
        vendor_cfg.digi.categories if vendor_cfg is not None else CATEGORY_DIGI_PATHS
    )

    if category.matched_key and category.matched_key in pt_map:
        return pt_map[category.matched_key], False

    # Alfa's leaf may still be known even when DigiMall's is not (and vice versa).
    if category.alfa_id:
        for key, value in alfa_cats.items():
            if value == category.alfa_id and key in pt_map:
                return pt_map[key], False
    if category.digi_path:
        for key, value in digi_cats.items():
            if value == category.digi_path and key in pt_map:
                return pt_map[key], False
    return _infer_product_type(category, source_brand), True
