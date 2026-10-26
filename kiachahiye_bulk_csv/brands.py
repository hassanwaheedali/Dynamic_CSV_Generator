"""Section 3 -- deterministic brand lookup for both platforms.

╔══════════════════════════════════════════════════════════════════════════╗
║  ██  EDIT HERE  ██  -- the only two tables you ever need to change        ║
║                                                                            ║
║  1. BRANDS_DIGI  -> add a line:  "brandname": 1234,                        ║
║  2. BRANDS_ALFA  -> add a line:  "brandname": 5678,                        ║
║                                                                            ║
║  Keys are lower-case, single-spaced. Use the EXACT spelling each          ║
║  platform's admin panel shows -- DigiMall's own quirky spellings are      ║
║  kept as-is on purpose (do not "fix" them).                               ║
║                                                                            ║
║  If a brand is missing from one table only, that one file gets an empty   ║
║  Brands cell for those rows -- this is expected and is reported by name   ║
║  in the terminal summary.                                                 ║
║                                                                            ║
║  3. BRAND_ALIASES (optional) -> if your sheet spells a brand differently  ║
║     from the tables above, add the variant here. Example: the sheet has   ║
║     "Superasia" but the lists use "super asia" -- that alias lives below  ║
║     because 45 rows in the current sheet need it.                         ║
╚══════════════════════════════════════════════════════════════════════════╝

Matching is exact-after-normalisation only.  There is deliberately **no** fuzzy
or edit-distance matching: a new spelling variant belongs in ``BRAND_ALIASES``,
added by hand, after a human has seen it in the QC report.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from models import ResolvedBrand
from textutils import normalize

if TYPE_CHECKING:
    from vendor_config import VendorConfig

# ===========================================================================
#  EDIT HERE -- DigiMall brand ids
# ===========================================================================
BRANDS_DIGI: dict[str, int] = {
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
    # "homage":  <-- NOT on DigiMall's list yet. Add the real id here.
    # "hisense": <-- NOT on DigiMall's list yet. Add the real id here.
}

# ===========================================================================
#  EDIT HERE -- Alfa brand ids
# ===========================================================================
BRANDS_ALFA: dict[str, int] = {
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
}

# ===========================================================================
#  EDIT HERE (optional) -- spelling variants seen in the source sheet
#  key = how the sheet spells it (lower-case)   value = the canonical key above
# ===========================================================================
BRAND_ALIASES: dict[str, str] = {
    # -- real variants already needed by the current 1800-row sheet --
    "superasia": "super asia",      # 45 rows in the sheet spell it without a space
    "xiaomi": "xioami",             # Alfa's own list spells the brand "xioami"
    # -- defensive extras: harmless if never hit, handy if a future sheet uses them --
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

BRAND_DISPLAY_MAP: dict[str, str] = {
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


def extract_brand(
    title: str = "",
    fallback_brand: str = "",
    display_map: dict[str, str] | None = None,
    aliases: dict[str, str] | None = None,
) -> str:
    """Extract canonical brand name from title prefix, falling back to fallback_brand."""
    active_map = display_map if display_map is not None else BRAND_DISPLAY_MAP
    if title:
        title_norm = title.strip().lower()
        for key in sorted(active_map, key=len, reverse=True):
            if title_norm.startswith(key + " ") or title_norm == key:
                return active_map[key]
    fallback = fallback_brand.strip()
    if not fallback:
        return ""
    direct = active_map.get(fallback.lower())
    if direct is not None:
        return direct
    canon = canonical_brand_key(fallback, aliases=aliases)
    return active_map.get(canon, fallback)


def canonical_brand_key(
    raw_brand: str,
    aliases: dict[str, str] | None = None,
) -> str:
    """Normalise a source brand string to its canonical lookup key."""
    active_aliases = aliases if aliases is not None else BRAND_ALIASES
    key = normalize(raw_brand)
    return active_aliases.get(key, key)


def resolve_brand(
    raw_brand: str,
    title: str = "",
    vendor_cfg: VendorConfig | None = None,
) -> ResolvedBrand:
    """Resolve one brand string against both platform lists, independently.

    If title is supplied and starts with a known brand (e.g. Nasgas, iFFalcon, Jackpot),
    that brand takes precedence over raw_brand.
    """
    brands_digi = vendor_cfg.digi.brands if vendor_cfg is not None else BRANDS_DIGI
    brands_alfa = vendor_cfg.alfa.brands if vendor_cfg is not None else BRANDS_ALFA
    aliases = vendor_cfg.brand_aliases if vendor_cfg is not None else BRAND_ALIASES
    display_map = (
        vendor_cfg.brand_display_map if vendor_cfg is not None else BRAND_DISPLAY_MAP
    )
    effective = extract_brand(
        title, raw_brand, display_map=display_map, aliases=aliases
    )
    key = canonical_brand_key(effective, aliases=aliases)
    return ResolvedBrand(
        raw=effective,
        normalized=key,
        digi_id=brands_digi.get(key),
        alfa_id=brands_alfa.get(key),
    )
