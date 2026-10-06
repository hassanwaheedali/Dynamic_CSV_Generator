"""Section 10 / 12 -- the brand warranty terms.

╔══════════════════════════════════════════════════════════════════════════╗
║  ██  EDIT HERE  ██  -- the only warranty table you ever need to change    ║
║                                                                            ║
║  WARRANTY_TERMS["brand"]["Category"] = "Part = Duration; Part = Duration"  ║
║                                                                            ║
║  One line per brand per category.  To change a warranty, change the        ║
║  number -- nothing else in the project needs touching.                     ║
║                                                                            ║
║  • A bare duration means "Parts":   "12 Years" == "Parts = 12 Years"       ║
║  • Empty cell part = that part has no term for this brand                  ║
║  • A brand that gives one category TWO different warranties puts the       ║
║    words that tell the products apart in brackets:                         ║
║                                                                            ║
║        "Air Conditioner (non inverter)": "...",     <- narrower first      ║
║        "Air Conditioner (inverter)":     "...",                            ║
║        "Air Conditioner":                "...",     <- the default         ║
║                                                                            ║
║    The first line whose bracketed words appear in the product Title        ║
║    wins; the plain category is the fallback when none match.               ║
║                                                                            ║
║  • A brand or category that is not listed gets NO warranty row.  The       ║
║    run prints exactly which brand + category was left blank, so a gap      ║
║    is never hidden and nothing is ever invented.                           ║
║                                                                            ║
║  • A warranty stated in the product's own Description always beats         ║
║    this table, including when it says "N/A" or "Lifetime".                 ║
║                                                                            ║
║  Part names become their own bolded row in the Description table, and      ║
║  the most important one becomes Attribute_Warranty (DigiMall only).        ║
╚══════════════════════════════════════════════════════════════════════════╝

Every value here came from the client's warranty catalogue, plus three
confirmations given directly: Dawlance LED TV = 2 years, TCL sound bar =
1 year, TCL speaker = 1 year parts and labour.
"""

from __future__ import annotations

# ===========================================================================
#  EDIT HERE -- brand -> category -> warranty
# ===========================================================================
WARRANTY_TERMS: dict[str, dict[str, str]] = {

    "dawlance": {
        "Refrigerator": "Compressor = 12 Years; Parts = 1 Year",
        "Deep Freezer": "Compressor = 12 Years; Parts = 1 Year",
        "Air Conditioner": "Compressor = 12 Years; PCB = 4 Years; Evaporator = 3 Years; Parts = 1 Year",
        "Washing Machine (semi automatic / twin tub / single tub)": "Motor = 10 Years; Parts = 1 Year",
        "Washing Machine": "Motor = 12 Years; PCB = 4 Years; Parts = 1 Year",
        "LED TV": "Panel = 2 Years; Parts = 2 Years",
        "Microwave Oven": "Parts = 1 Year",
        "Water Dispenser": "Compressor = 3 Years; Parts = 1 Year",
    },

    "haier": {
        "Refrigerator": "Compressor = 10 Years; PCB = 3 Years; Parts = 1 Year",
        "Deep Freezer": "Compressor = 10 Years; Parts = 1 Year",
        "Air Conditioner": "Compressor = 10 Years; Evaporator = 5 Years; Parts = 5 Years",
        "Washing Machine": "Motor = 10 Years; Parts = 1 Year",
        "Microwave Oven": "Parts = 1 Year",
        "LED TV (mini led / m80 / m90)": "Panel = 3 Years; Parts = 3 Years",
        "LED TV": "Panel = 2 Years; Parts = 2 Years",
        "UPS": "Parts = 1 Year",
        "Water Dispenser": "Compressor = 5 Years; Parts = 1 Year",
    },

    "pel": {
        "Refrigerator": "Compressor = 10 Years; Parts = 1 Year",
        "Deep Freezer": "Compressor = 10 Years; Parts = 1 Year",
        "Air Conditioner": "Compressor = 10 Years; PCB = 5 Years; Parts = 1 Year",
        "Washing Machine": "Motor = 10 Years; Parts = 1 Year",
        "Microwave Oven": "Parts = 1 Year",
        "Water Dispenser": "Parts = 1 Year",
    },

    "tcl": {
        "Air Conditioner": "Compressor = 10 Years; PCB = 5 Years; Parts = 5 Years",
        "LED TV": "Panel = 2 Years; Parts = 2 Years",
        "Sound Bar": "Parts and Labour = 1 Year",
        "Speaker": "Parts and Labour = 1 Year",
    },

    "gree": {
        "Air Conditioner (non inverter)": "Compressor = 3 Years; Parts = 1 Year",
        "Air Conditioner (inverter)": "Compressor = 10 Years; PCB = 4 Years; Evaporator = 2 Years; Parts = 1 Year",
        "Air Conditioner": "Compressor = 3 Years; Parts = 1 Year",
    },

    "orient": {
        "Refrigerator": "Compressor = 3 Years; Parts = 1 Year",
        "Air Conditioner": "Compressor = 10 Years; PCB = 4 Years; Parts = 1 Year",
        "Microwave Oven": "Parts = 1 Year",
        "Washing Machine": "Parts = 1 Year",
        "Water Dispenser": "Compressor = 3 Years; Parts = 1 Year",
    },

    "kenwood": {
        "Refrigerator": "Compressor = 12 Years; PCB = 4 Years; Parts = 1 Year",
        "Air Conditioner": "Compressor = 10 Years; PCB = 4 Years; Parts = 1 Year",
        "Washing Machine": "Motor = 10 Years; Parts = 1 Year",
    },

    "homage": {
        "Refrigerator": "Compressor = 7 Years; Parts = 1 Year",
        "Air Conditioner": "Parts = 1 Year",
        "Deep Freezer": "Parts = 1 Year",
        "Microwave Oven": "Parts = 1 Year",
        "Washing Machine": "Parts = 1 Year",
        "Water Dispenser": "Parts = 1 Year",
        "Air Purifier": "Parts = 1 Year",
    },

    "super asia": {
        "Washing Machine": "Motor = 10 Years; Parts = 1 Year",
        "Geyser": "Parts = 1 Year",
        "Air Cooler": "Parts = 1 Year",
    },

    "ecostar": {
        "Air Conditioner": "Compressor = 10 Years; PCB = 4 Years; Evaporator = 2 Years; Parts = 1 Year",
    },

    "hisense": {
        "Air Conditioner": "Compressor = 10 Years; PCB = 4 Years; Parts = 1 Year",
    },
}
