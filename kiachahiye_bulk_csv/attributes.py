"""Section 11 -- the 36 DigiMall-only custom attributes.

Alfa's schema has none of these columns, so this module is never consulted when
building the Alfa row.

╔══════════════════════════════════════════════════════════════════════════╗
║  ██  EDIT HERE  ██ -- allowed values, aliases and scope                  ║
║                                                                            ║
║  ALLOWED   : the closed vocabulary for each column.  A value is ONLY ever  ║
║              written if it appears literally in the matching list.         ║
║  ALIASES   : recognised real-world phrasing -> one exact allowed string.   ║
║              Add a line here when the QC report shows a raw phrase that    ║
║              should have matched.  Order matters: the first matching alias ║
║              wins, so put negations ("without refrigerator") BEFORE their  ║
║              positive counterparts.                                        ║
║  SCOPE     : which Product Types the column applies to.  This is what      ║
║              stops a refrigerator's "Inverter Compressor" bullet from      ║
║              landing in Attribute_INV/NON-INV for a fridge... unless you   ║
║              want it to, in which case add the Product Type to the set.    ║
║                                                                            ║
║  Numeric attributes are extracted by regex and then compared for equality  ║
║  after collapsing whitespace inside the token only ("12 kg" == "12KG").    ║
║  Units and punctuation are NEVER rewritten, so "16 Cu.Ft" correctly does   ║
║  NOT match the list's "16 Cu Ft", and a range like "220-240V" correctly    ║
║  does NOT match either "220V" or "240V".                                   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import re

# ===========================================================================
#  EDIT HERE -- the closed vocabulary for every Attribute_* column
# ===========================================================================
ALLOWED: dict[str, list[str]] = {
    "Attribute_Air Conditioner Type": [
        "Wall Mounted", "Wall Mounted Split", "Split", "Cassette", "Floor Standing",
    ],
    "Attribute_Air Conditioner Capacity": [
        "2 Ton", "1.6 Ton", "1 Ton", "4 Ton", "3 Ton", "1.25 Ton", "0.8 Ton",
        "0.75 Ton", "1.5 Ton",
    ],
    "Attribute_INV/NON-INV": ["T-AI Inverter", "Non Inverter", "Non-Inverter", "Inverter"],
    "Attribute_Washing Machine Type": [
        "Washing Machine", "Semi Auto", "Semi Automatic", "Fully Automatic Machine",
        "Top Load", "Top-Load", "Front Load", "Automatic", "Semi-Automatic",
        "Front-Load Automatic", "Single Tub", "Spinner", "Top-Load Automatic", "Twin Tub",
    ],
    "Attribute_Washing Machine Capacity": [
        "25KG", "6.5KG", "1KG", "20KG", "5KG", "4KG", "12.5KG", "15KG", "13KG",
        "10.5KG", "7KG", "7.5KG", "6KG", "8KG", "14KG", "12KG", "9KG", "9.5KG",
        "8.5KG", "17KG", "11KG", "10KG", "12.5 kg", "21 kg", "12 kg", "13 kg",
        "14 kg", "16 kg", "17 kg", "20 kg", "4 kg", "5 kg", "6 kg", "7 kg",
        "7.5 kg", "8.5 kg", "9.5 kg", "15 kg", "10 Kg", "9 Kg", "10.5 Kg",
        "8 Kg", "11 Kg",
    ],
    "Attribute_Refrigerator Type": [
        "Multi Door", "Freezer-On-Top", "Top Mount Freezer", "French Door",
        "Double Door", "Single Door", "Side-By-Side",
    ],
    "Attribute_Microwave Type": [
        "Microwave Oven", "Grill", "Heating", "All in one", "Oven Plus Heating",
        "Oventoaster Heating Option", "Heating Plus Cooking",
    ],
    "Attribute_Water Dispenser Type": [
        "Top Load", "Table Top", "Without Refrigerator", "With refrigerator",
    ],
    "Attribute_Geyser Type": ["Hybrid", "Electric", "Gas"],
    "Attribute_LED Type": [
        "LED TV", "FHD", "Andriod TV", "QLED", "Google TV", "Mini", "Smart LED TV",
        "Android TV", "2K", "Neo", "Mini LED", "O LED", "Q LED", "4K", "Android", "Basic",
    ],
    "Attribute_Fan Type": [
        "Circumatic Fan", "Portable Fan", "Bracket Fan", "Exhaust Fan", "Tower Fan",
        "Floor Fan", "Wall Fan", "Table/Desk Fan", "Pedestal Fan", "Ceiling Fan",
    ],
    "Attribute_Air Cooler Category": ["Air Cooler DC", "Air Cooler AC-DC", "Air Cooler AC"],
    "Attribute_Capacity": [
        "411 Ltr", "391 Ltr", "348 Ltr", "304 Ltr", "540 Ltr", "8 Kg", "30 Ltr",
        "50 Ltr", "40 Ltr", "200 Ltr", "140 Ltr", "80 Litter", "100 Ltr",
        "50 Litters", "60 Ltr", "15 Ltr", "200ml", "80ml", "75ml", "90ml", "400ml",
        "150ml", "100ml", "250ml", "27 Litter", "38 Litter", "1.8 Litter",
        "1.7 Litter", "1.5 Litter", "4 Litter", "45 Litter", "2.5 Cu Ft", "17 Cu Ft",
        "20 Cu Ft", "28 Litter", "8.5 Cu Ft", "7.5 Cu Ft", "19 Cu Ft", "11.5 Cu Ft",
        "24 cu ft", "42 Litter", "36 Litter", "62 Litter", "12.5 Cu Ft", "6 Cu Ft",
        "25 Litter", "15 Cu.Ft", "12 Litter", "15 Litter", "16 Cu Ft", "18 Cu Ft",
        "34 Litter", "7 Cu Ft", "20 Litter", "23 Litter", "8 Cu Ft", "4 Cu Ft",
        "5 Cu Ft", "9 Cu Ft", "10 Cu Ft", "13 Cu Ft", "26 Litter", "15 Cu Ft",
        "8 Litter", "6 Litter", "10 Litter", "11 Cu Ft", "12 Cu Ft", "30 Litter",
        "14 Cu Ft",
    ],
    "Attribute_Watts": [
        "650W", "720W", "700W", "600W", "500W", "400W", "100W", "50W", "30W",
        "130W", "295W", "1500W", "1000W", "1200W",
    ],
    "Attribute_Volt": ["240V", "220V", "12V", "120V"],
    "Attribute_Warranty": [
        "1 Year", "1 Year Warranty", "1 years Brand Warranty", "1 year brand warranty",
        "1 year brand warrenty", "2 Years", "2 Years Warranty", "2 Years Brand Warranty",
        "3 Years", "3 Years Brand Warranty", "4 Years Warranty", "5 Year Warranty",
        # Forms the source sheet actually uses, kept exactly as written -- the
        # rule is never to rewrite a unit or a digit, so the exact wording is
        # listed here instead of being normalised in code.
        "2 Year", "3 Year", "5 Years", "4 Years", "12 Year", "05 Year",
        "6 Months", "7 Years", "8 Years", "10 Year", "10 Years", "10 Year Warranty",
        "10 Years Warranty", "11 Years", "12 Years", "15 Years", "20 Months",
        "24 Months", "36 Months", "Brand Warranty", "No Warranty", "Official Warranty",
        "12 Months + 1 Month (Carlcare)",
    ],
    "Attribute_Display Size": [
        "58 Inch", "100 Inch", "65inches", "43 inches", "55 Inches", "15 Inch",
        "83 Inch", "77 Inch", "11.6 Inch", "50", "55", "26.5 Inch", "24.5 Inch",
        "49 Inch", "31.5 Inch", "86 Inch", "10 Inch", "27 Inch", "22 Inch",
        "23.8 Inch", "21.5 Inch", "15.6 Inch", "14 Inch", "15.8 Inch", "34 Inch",
        "24 Inch", "20 Inch", "16 Inch", "14.5 Inch", "15.3 Inch", "98 Inch",
        "85 Inch", "75 Inch", "65 Inch", "55 Inch", "50 Inch", "40 Inch", "43 Inch",
        "32 Inch",
    ],
    "Attribute_Product Type": ["Deep Freezer", "Refrigerator", "Phones"],
    "Attribute_Processor": ["i3", "i7", "i5"],
    "Attribute_Core": [
        "Ryzen 7", "Ryzen 5", "i3", "Core 5", "Core 7", "Ultra 7", "Ultra 5", "i7",
        "i10", "i8", "i5",
    ],
    "Attribute_Generation": ["8th", "10th", "13th", "12th", "11th"],
    "Attribute_Battery": ["Lithium", "Graphene"],
    "Attribute_Thickness": ["8 inches", "6 inches", "10 inches"],
    "Attribute_BNPL": ["No", "Yes"],
    "Attribute_UPS Inverter Type": ["Hybrid", "On-grid", "Off-grid"],
    "Attribute_Generator Types": ["Canopy", "Open generators"],
    "Attribute_Fragrance Type": ["Woody", "Sweet", "Oriental", "Fruity", "Floral", "Citrus"],
    "Attribute_Lasting": ["Upto 12 hrs", "Upto 7 hrs"],
    "Attribute_Sillage / Projection": ["Medium", "Strong"],
    "Attribute_Season": ["Spring", "Autumn", "Winter", "Summer"],
    "Attribute_Watch Sizes": ["Women's Sizes", "Men's Sizes"],
    "Attribute_Watch Display Type": ["Digital & Analog", "Analog", "Digital"],
    "Attribute_Watch Band": [
        "Nylon", "Metal", "Silicone", "Synthetic leather bands", "Genuine Leather",
        "Resin", "Cloth", "Stainless Steel",
    ],
    "Attribute_Watch Sensor Feature": [
        "Number of steps", "Humidity", "Heart rate", "Barometric pressure",
        "Temperature", "Altitude", "Direction",
    ],
    "Attribute_SKin Type": [
        "Fairness", "Dark Spot", "Oil Control", "Acne", "Dry", "Dull", "Pores",
        "Sensitive Skin", "Oily", "Normal", "All Skin Types",
    ],
    "Attribute_Geyser Capacity": [],  # no enumerated list printed in the spec
}

# ===========================================================================
#  EDIT HERE -- recognised phrasing -> one exact allowed value.
#  FIRST MATCH WINS, so negations must come first.
# ===========================================================================
ALIASES: dict[str, dict[str, str]] = {
    "Attribute_Water Dispenser Type": {
        "without refrigerator": "Without Refrigerator",  # negation FIRST
        "without ref": "Without Refrigerator",
        "refrigerator compartment": "With refrigerator",
        "refrigerator cabinet": "With refrigerator",
        "with refrigerator": "With refrigerator",
        "table top": "Table Top",
        "top load": "Top Load",
    },
    "Attribute_INV/NON-INV": {
        "non-inverter": "Non-Inverter",  # negation BEFORE the plain rule below
        "non inverter": "Non Inverter",
        "noninverter": "Non Inverter",
        "t-ai inverter": "T-AI Inverter",
        "t ai inverter": "T-AI Inverter",
        "dc inverter": "Inverter",
        "bldc": "Inverter",
        "brushless": "Inverter",
        "inverter": "Inverter",
    },
    "Attribute_LED Type": {
        "google tv": "Google TV",
        "android tv": "Android TV",
        "andriod tv": "Andriod TV",  # exact catalogue misspelling -- do not "fix"
        "smart led tv": "Smart LED TV",
        "smart tv": "Smart LED TV",
        "mini led": "Mini LED",
        "qled": "QLED",
        "q led": "Q LED",
        "oled": "O LED",
        "o led": "O LED",
        "4k": "4K",
        "2k": "2K",
        "fhd": "FHD",
        "neo": "Neo",
        "google": "Google TV",  # a Dawlance/Haier "Google" TV is a Google TV
        "android": "Android",
        "andriod": "Andriod TV",
        "smart": "Smart LED TV",
        "basic": "Basic",
        "led tv": "LED TV",
    },
    "Attribute_Refrigerator Type": {
        "side by side": "Side-By-Side",
        "side-by-side": "Side-By-Side",
        "french door": "French Door",
        "freezer on top": "Freezer-On-Top",
        "freezer-on-top": "Freezer-On-Top",
        "top mount": "Top Mount Freezer",
        "multi door": "Multi Door",
        "double door": "Double Door",
        "single door": "Single Door",
    },
    "Attribute_Air Conditioner Type": {
        "wall mounted split": "Wall Mounted Split",
        "wall mount split": "Wall Mounted Split",
        "wall mounted": "Wall Mounted",
        "wall mount": "Wall Mounted",
        "floor standing": "Floor Standing",
        "floor-standing": "Floor Standing",
        "cassette": "Cassette",
        "split": "Split",
    },
    "Attribute_Washing Machine Type": {
        "twin tub": "Twin Tub",
        "single tub": "Single Tub",
        "front-load automatic": "Front-Load Automatic",
        "front load": "Front Load",
        "front-load": "Front Load",
        "top-load automatic": "Top-Load Automatic",
        "top load": "Top Load",
        "top-load": "Top Load",
        "semi-automatic": "Semi-Automatic",
        "semi automatic": "Semi Automatic",
        "semi auto": "Semi Auto",
        "fully automatic": "Fully Automatic Machine",
        "spinner": "Spinner",
        "automatic": "Automatic",
        "washing machine": "Washing Machine",
    },
    "Attribute_Microwave Type": {
        "oven plus heating": "Oven Plus Heating",
        "oven toaster": "Oventoaster Heating Option",
        "oven-toaster": "Oventoaster Heating Option",
        "heating plus cooking": "Heating Plus Cooking",
        "all in one": "All in one",
        "microwave oven": "Microwave Oven",
        "grill": "Grill",
        "heating": "Heating",
    },
    "Attribute_Geyser Type": {
        "hybrid": "Hybrid",
        "gas": "Gas",
        "electric": "Electric",
    },
    "Attribute_Air Cooler Category": {
        "ac-dc": "Air Cooler AC-DC",
        "ac dc": "Air Cooler AC-DC",
        "inverter": "Air Cooler DC",
        "dc": "Air Cooler DC",
        "ac": "Air Cooler AC",
    },
    "Attribute_Fan Type": {
        "circumatic": "Circumatic Fan",
        "portable": "Portable Fan",
        "bracket": "Bracket Fan",
        "exhaust": "Exhaust Fan",
        "tower": "Tower Fan",
        "floor": "Floor Fan",
        "wall": "Wall Fan",
        "table": "Table/Desk Fan",
        "desk": "Table/Desk Fan",
        "pedestal": "Pedestal Fan",
        "ceiling": "Ceiling Fan",
    },
}

# ===========================================================================
#  EDIT HERE -- which Product Types each column applies to (None = any)
# ===========================================================================
SCOPE: dict[str, frozenset[str] | None] = {
    "Attribute_Air Conditioner Type": frozenset({"Air Conditioner"}),
    "Attribute_Air Conditioner Capacity": frozenset({"Air Conditioner"}),
    "Attribute_Washing Machine Type": frozenset({"Washing Machine"}),
    "Attribute_Washing Machine Capacity": frozenset({"Washing Machine"}),
    "Attribute_Refrigerator Type": frozenset({"Refrigerator", "Deep Freezer"}),
    "Attribute_Microwave Type": frozenset({"Microwave Oven"}),
    "Attribute_Water Dispenser Type": frozenset({"Water Dispenser"}),
    "Attribute_LED Type": frozenset({"LED TV"}),
    "Attribute_Geyser Type": frozenset({"Geyser"}),
    "Attribute_Geyser Capacity": frozenset({"Geyser"}),
    "Attribute_Fan Type": frozenset({"Fan"}),
    "Attribute_Air Cooler Category": frozenset({"Air Cooler"}),
    "Attribute_INV/NON-INV": frozenset(
        {"Air Conditioner", "Refrigerator", "Deep Freezer", "Washing Machine", "Air Cooler"}
    ),
    "Attribute_Capacity": frozenset(
        {
            "Refrigerator", "Deep Freezer", "Water Dispenser", "Microwave Oven",
            "Air Cooler", "Air Conditioner", "LED TV",
        }
    ),
    "Attribute_Display Size": frozenset({"LED TV"}),
    "Attribute_Watts": frozenset(
        {"Microwave Oven", "Air Fryer", "LED TV", "Air Cooler", "Refrigerator", "Washing Machine"}
    ),
    "Attribute_Product Type": frozenset({"Deep Freezer", "Refrigerator"}),
}

# Numeric attributes: (regex, units already baked in).  The range form is
# captured deliberately so "220-240V" is one candidate that matches nothing.
#
# _RATE_GUARD rejects a FLOW RATE on the volume units: "2.5 L/H" is a cooling
# rate, not a 2.5-litre tank, so a litre-per-hour phrasing must never become a
# capacity candidate.  (Without it, "18000 L/h" could match a tank size if that
# number were ever added to ALLOWED.)
_RATE_GUARD = r"(?!\s*(?:/|per\b))"

NUMERIC_PATTERNS: dict[str, str] = {
    "Attribute_Capacity": (
        r"(?<![\d.])(?P<n1>\d+(?:\.\d+)?)\s*(?P<unit>Cu\.?\s?Ft|Ltr|Litre|Litter|Liter|Liters|L)\b"
        + _RATE_GUARD
    ),
    "Attribute_Washing Machine Capacity": r"(?<![\d.])(?P<n1>\d+(?:\.\d+)?)\s*(?:-\s*(?P<n2>\d+(?:\.\d+)?)\s*)?(?P<unit>[Kk][Gg])\b",
    "Attribute_Air Conditioner Capacity": r"(?<![\d.])(?P<n1>\d+(?:\.\d+)?)\s*(?:-\s*(?P<n2>\d+(?:\.\d+)?)\s*)?(?P<unit>Ton)\b",
    "Attribute_Display Size": r"(?<![\d.])(?P<n1>\d+(?:\.\d+)?)\s*(?:-\s*(?P<n2>\d+(?:\.\d+)?)\s*)?-?\s?(?P<unit>inch|inches|\")\b",
    "Attribute_Watts": r"(?<![\d.])(?P<n1>\d+(?:\.\d+)?)\s*(?:-\s*(?P<n2>\d+(?:\.\d+)?)\s*)?(?P<unit>W)\b",
    "Attribute_Volt": r"(?<![\d.])(?P<n1>\d+(?:\.\d+)?)\s*(?:[-\u2013/]\s*(?P<n2>\d+(?:\.\d+)?)\s*)?(?P<unit>V)\b",
    "Attribute_Geyser Capacity": (
        r"(?<![\d.])(?P<n1>\d+(?:\.\d+)?)\s*(?:-\s*(?P<n2>\d+(?:\.\d+)?)\s*)?"
        r"(?P<unit>Ltr|Litre|Liter|L|gal|Gallon)\b" + _RATE_GUARD
    ),
}

_LABEL_HINTS: dict[str, tuple[str, ...]] = {
    "Attribute_Capacity": ("capacity", "gross capacity", "net capacity", "tank"),
    "Attribute_Washing Machine Capacity": ("capacity", "wash capacity"),
    "Attribute_Air Conditioner Capacity": ("capacity", "tonnage"),
    "Attribute_Display Size": ("screen size", "display size", "size"),
    "Attribute_Watts": ("power", "rating power", "watt"),
    "Attribute_Volt": ("voltage",),
    "Attribute_Geyser Capacity": ("capacity",),
}


def _collapse_ws(token: str) -> str:
    """Whitespace-only collapse, used for equality tests against the lists."""
    return re.sub(r"\s+", "", token)


def _allowed_lookup(column: str) -> dict[str, str]:
    return {_collapse_ws(value).lower(): value for value in ALLOWED[column]}


def _candidate_tokens(text: str, column: str) -> list[str]:
    """Ordered candidate tokens: label-hinted lines first, then everything else."""
    pattern = NUMERIC_PATTERNS.get(column)
    if pattern is None:
        return []
    hints = _LABEL_HINTS.get(column, ())
    preferred: list[str] = []
    other: list[str] = []
    lines = [line for line in re.split(r"[\r\n]+", text) if line.strip()]
    label_re = re.compile(
        r"^[ \t]*(?:•\s*)?" + "(?:" + "|".join(re.escape(h) for h in hints) + r")",
        re.IGNORECASE,
    )
    for line in lines:
        tokens = _tokens_in(line, pattern)
        if not tokens:
            continue
        if hints and label_re.match(line):
            preferred.extend(tokens)
        else:
            other.extend(tokens)
    return preferred + other


def _tokens_in(text: str, pattern: str) -> list[str]:
    """Full candidate tokens (unit included) found in one line of text."""
    tokens: list[str] = []
    for match in re.finditer(pattern, text, re.IGNORECASE):
        groups = match.groupdict()
        number = groups.get("n1") or ""
        second = groups.get("n2")
        unit = (groups.get("unit") or "").strip()
        if second:
            tokens.append(f"{number}-{second} {unit}".strip())
        else:
            tokens.append(f"{number} {unit}".strip())
    return tokens


def _match_numeric(text: str, column: str) -> tuple[str | None, str | None]:
    """Return ``(allowed_value, raw_signal)``; either may be ``None``."""
    candidates = _candidate_tokens(text, column)
    if not candidates:
        return None, None
    lookup = _allowed_lookup(column)
    for candidate in candidates:
        hit = lookup.get(_collapse_ws(candidate).lower())
        if hit is not None:
            return hit, candidate
    return None, candidates[0]


def _match_alias(text: str, column: str) -> tuple[str | None, str | None]:
    """First matching alias (in table order) wins; negations are listed first."""
    aliases = ALIASES.get(column)
    if not aliases:
        return None, None
    lowered = text.lower()
    for phrase, value in aliases.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", lowered):
            return value, phrase
    return None, None


def match_warranty(headline: str | None) -> tuple[str | None, str | None]:
    """The DigiMall word for a warranty headline, and the raw signal behind it.

    The second half of the answer is the signal the QC report names when the first half is
    ``None`` -- the platform's closed list has no value for it, so no caller may write one in.
    """
    if not headline:
        return None, None
    lookup = _allowed_lookup("Attribute_Warranty")
    return lookup.get(_collapse_ws(headline).lower()), headline


def build_attributes(
    *,
    title: str,
    description: str,
    product_type: str,
    warranty_headline: str | None,
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Return ``(attribute_values, unmatched_signals)`` for the DigiMall row.

    Every column that finds a raw signal but no exact allowed value is returned
    in ``unmatched_signals`` so the QC report can name it -- the alias tables are
    then extended deliberately by a human, never guessed by the code.
    """
    text = f"{title}\n{description}"
    values: dict[str, str] = {}
    unmatched: list[tuple[str, str]] = []

    for column, allowed_values in ALLOWED.items():
        allowed_scope = SCOPE.get(column)
        if allowed_scope is not None and product_type not in allowed_scope:
            continue

        if column == "Attribute_Warranty":
            value, signal = match_warranty(warranty_headline)
        elif column == "Attribute_Product Type":
            value, signal = (
                (product_type, product_type) if product_type in allowed_values else (None, None)
            )
        elif column in NUMERIC_PATTERNS:
            value, signal = _match_numeric(text, column)
        else:
            # Tie-break rule (section 11): a keyword that appears in the TITLE
            # outranks one that only appears in the Description body.
            value, signal = _match_alias(title, column)
            if value is None and signal is None and description:
                value, signal = _match_alias(description, column)

        if value is not None:
            values[column] = value
        elif signal is not None:
            unmatched.append((column, signal))

    return values, unmatched
