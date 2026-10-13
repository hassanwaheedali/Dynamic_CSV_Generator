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

from models import ResolvedBrand
from textutils import normalize

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
    "super asia": 4395,
    "midea": 3821,
    "pel": 3767,
    "xioami": 3763,
    "westpoint": 3762,
    "gree": 3678,
    "kenwood": 3677,
    "ecostar": 3675,
    "haier": 3674,
    "dawlance": 3673,
    "tcl": 3667,
    # "orient":  <-- NOT on Alfa's list. Add the real id here if it exists.
    # "homage":  <-- NOT on Alfa's list. Add the real id here.
    # "hisense": <-- NOT on Alfa's list. Add the real id here.
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
}


def extract_brand(title: str = "", fallback_brand: str = "") -> str:
    """Extract canonical brand name from title prefix, falling back to fallback_brand."""
    if title:
        title_norm = title.strip().lower()
        for key in sorted(BRAND_DISPLAY_MAP, key=len, reverse=True):
            if title_norm.startswith(key + " ") or title_norm == key:
                return BRAND_DISPLAY_MAP[key]
    fallback = fallback_brand.strip()
    return BRAND_DISPLAY_MAP.get(fallback.lower(), fallback)


def canonical_brand_key(raw_brand: str) -> str:
    """Normalise a source brand string to its canonical lookup key."""
    key = normalize(raw_brand)
    return BRAND_ALIASES.get(key, key)


def resolve_brand(raw_brand: str, title: str = "") -> ResolvedBrand:
    """Resolve one brand string against both platform lists, independently.

    If title is supplied and starts with a known brand (e.g. Nasgas, iFFalcon, Jackpot),
    that brand takes precedence over raw_brand.
    """
    effective = extract_brand(title, raw_brand) if title else raw_brand
    key = canonical_brand_key(effective)
    return ResolvedBrand(
        raw=effective,
        normalized=key,
        digi_id=BRANDS_DIGI.get(key),
        alfa_id=BRANDS_ALFA.get(key),
    )
