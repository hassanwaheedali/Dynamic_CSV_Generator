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
║  A miss on one platform's table NEVER blanks the other platform's cell.   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from models import CategoryStatus, ResolvedCategory

if TYPE_CHECKING:
    from vendor_config import ResolvedCellConfig, VendorConfig

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
    # NOTE (do not remove this comment): KCC's curated DigiMall table has NO "LED TV"
    # leaf and no leaf for geysers / sound bars / speakers / UPS.
}

# ===========================================================================
#  EDIT HERE -- Alfa: bare leaf id only, never a joined path
# ===========================================================================
CATEGORY_ALFA_IDS: dict[str, str] = {
    # KiaChahiye Alfa Category Mapping (exact platform tree):
    # 11504 (Home appliances)
    "ac": "11505",
    "washing machine": "11506",
    "refrigerators": "11507",
    "deep freezer": "11508",
    "water dispenser": "11509",
    "geysers": "11510",
    "air cooler": "11511",
    # 11518 (Kitchen appliances)
    "microwaves": "11519",
    "air fryer": "11522",
    "oven": "11527",
    "blenders": "11528",
    "food factory": "11529",
    "coffee maker": "11530",
    # Root: 11539 (LED TV)
    "led tv": "11539",
    "smart led tv": "11540",
    # Inactive/Special
    "dishwashing": "11874",
    "dish washer": "12068",
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

# Retained for backward compatibility with series_corpus.py vocabulary builder.
# Category resolution no longer globally blocks these before checking the cell's taxonomy.
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

# ===========================================================================
#  Canonical Concept Lexicon & Phrase-First Analyzer (M1.5b)
# ===========================================================================

_BREADCRUMB_DELIM_RE = re.compile(r"\s*(?:[/>|]+)\s*")

# Prepositional markers that introduce secondary features in product titles
# (e.g. "Homage Water Dispenser HWD-49332 with Refrigerator Compartment").
_SECONDARY_PREP_RE = re.compile(
    r"\b(?:with|featuring|including|equipped\s+with|comes\s+with|plus|having)\b",
    re.IGNORECASE,
)

# Structural/organizational breadcrumb headers that name a department rather than
# a specific product type.
_STRUCTURAL_SEGMENTS: frozenset[str] = frozenset(
    {
        "electronics",
        "home & life style",
        "home & lifestyle",
        "home appliances",
        "kitchen appliances",
        "small kitchen appliances",
        "small appliances",
        "large cooking appliances",
        "cooling & heating",
        "air treatment",
        "washer & dryers",
        "vacuum & floor care",
        "garment care",
        "led tvs, audio & cameras",
        "tv & entertainment",
        "tv & video",
        "audio & visuals",
        "computing & gaming",
        "generator, ups, solar & power generation",
        "green energy",
        "power",
        "appliances",
        "cleaners",
        "health & beauty",
        "hair care",
        "men's care",
        "bath & body",
        "beauty tools",
        "health care",
        "makeup",
        "lips",
        "bedding & bath",
        "bath",
        "sports & outdoor",
        "outdoor",
        "camping & hiking",
        "phones",
    }
)

# Canonical concept_id -> canonical Product Type display string
CONCEPT_PRODUCT_TYPES: dict[str, str] = {
    "air_conditioner": "Air Conditioner",
    "air_cooler": "Air Cooler",
    "air_purifier": "Air Purifier",
    "humidifier": "Humidifier",
    "dehumidifier": "Dehumidifier",
    "water_heater": "Geyser",
    "room_heater": "Heater",
    "fan": "Fan",
    "microwave_oven": "Microwave Oven",
    "oven": "Oven",
    "cooking_range": "Cooking Range",
    "range_hood": "Range Hood",
    "water_dispenser": "Water Dispenser",
    "water_purifier": "Water Purifier",
    "water_generator": "Water Generator",
    "dishwasher": "Dishwasher",
    "dishwashing": "Dishwashing",
    "refrigerator": "Refrigerator",
    "deep_freezer": "Deep Freezer",
    "iron": "Iron",
    "garment_steamer": "Garment Steamer",
    "vacuum_cleaner": "Vacuum Cleaner",
    "washing_machine": "Washing Machine",
    "clothes_dryer": "Clothes Dryer",
    "washer_dryer_combo": "Combo Washer Dryer",
    "electric_kettle": "Electric Kettle",
    "juicer": "Juicer",
    "mixer": "Mixer",
    "blender": "Blender",
    "food_processor": "Food Processor",
    "air_fryer": "Air Fryer",
    "grinder": "Grinder",
    "sandwich_maker": "Sandwich Maker",
    "toaster": "Toaster",
    "coffee_maker": "Coffee Maker",
    "bread_maker": "Bread Maker",
    "waffle_maker": "Waffle Maker",
    "egg_boiler": "Egg Boiler",
    "ups": "UPS",
    "solar_panel": "Solar Panel",
    "battery": "Battery",
    "sewing_machine": "Sewing Machine",
    "television": "LED TV",
    "projector": "Projector",
    "sound_bar": "Sound Bar",
    "speaker": "Speaker",
    "home_theater": "Home Theater",
    "camera": "Camera",
    "av_accessory": "Audio Video Accessory",
    "hair_straightener": "Hair Straightener",
    "hair_curler": "Hair Curler",
    "hair_dryer": "Hair Dryer",
    "shaver_trimmer": "Trimmer",
    "hair_removal": "Hair Removal Appliance",
    "body_soap": "Body Soap & Shower Gel",
    "skin_care_tool": "Skin Care Tool",
    "massager": "Massager",
    "smartphone": "Smartphone",
    "tablet": "Tablet",
    "like_new_mobile": "Mobile Phone",
    "laptop": "Laptop",
    "desktop_pc": "Desktop PC",
    "gaming_chair": "Gaming Chair",
    "printer": "Printer",
    "scanner": "Scanner",
    "paper_shredder": "Paper Shredder",
    "attendance_machine": "Attendance Machine",
    "keyboard": "Keyboard",
    "mouse": "Mouse",
    "keyboard_mouse_combo": "Keyboard & Mouse",
    "monitor": "Monitor",
    "console": "Console",
    "console_game": "Game",
    "computer_accessory": "Computer Accessory",
    "bathroom_scale": "Bathroom Scale",
    "medical_equipment": "Medical Equipment",
    "camp_kitchen": "Camp Kitchen",
    "lipstick": "Lipstick",
    "lip_gloss": "Lip Gloss",
    "makeup_accessory": "Makeup Accessory",
    "home_living": "Home & Living",
    "fashion": "Fashion",
    "automotive": "Automotive",
    "campaigns": "Campaigns",
    "mother_baby": "Mother & Baby",
    "bulk_deals": "Bulk Deals",
    "baking_flavours": "Baking & Flavours",
    "accessories": "Accessories",
}

# Broad breadcrumb concepts that a more-specific compound in the product Title may refine
# (e.g. Breadcrumb "Kitchen Appliances > Ovens" + Title "Solo Microwave Oven" -> microwave_oven).
_CONCEPT_REFINEMENTS: dict[str, frozenset[str]] = {
    "oven": frozenset({"microwave_oven"}),
    "blender": frozenset({"juicer"}),
    "room_heater": frozenset({"water_heater"}),
    "mixer": frozenset({"food_processor", "blender"}),
}

# Trait specificity ranks (higher rank = more specific subtype requirement)
_TRAIT_RANKS: dict[str, int] = {
    "ac_form:floor_standing": 2,
    "ac_type:inverter": 1,
    "ac_type:non_inverter": 1,
    "tv_display:qled": 2,
    "tv_type:smart": 1,
    "tv_type:basic": 1,
    "iron_type:dry": 1,
    "iron_type:steam": 1,
    "wash_mode:semi_auto": 1,
    "wash_mode:fully_auto": 1,
    "mixer_type:stand": 1,
    "mixer_type:hand": 1,
    "blender_type:hand": 1,
    "blender_type:countertop": 1,
}

# Phrase -> (concepts_tuple, traits_tuple)
# Ordered strictly from longest multi-word compound to shortest single word so that
# compound phrases ("microwave oven", "water heater", "dish washer", "curling iron")
# consume their tokens before single-word heads ("oven", "heater", "iron") are checked.
_RAW_CONCEPT_PHRASES: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    # --- Multi-concept / Umbrella phrases ---
    ("air purifier & humdifier", ("air_purifier", "humidifier"), ()),
    ("air purifier & humidifier", ("air_purifier", "humidifier"), ()),
    ("irons & garment steamers", ("iron", "garment_steamer"), ()),
    ("iron & garment steamer", ("iron", "garment_steamer"), ()),
    ("water dispensers & purifiers", ("water_dispenser", "water_purifier"), ()),
    ("water dispenser & purifier", ("water_dispenser", "water_purifier"), ()),
    ("juicer & fruit extractors", ("juicer",), ()),
    ("juicer blender & grinder", ("juicer",), ()),
    ("straightening combs & brushes", ("hair_straightener",), ()),
    ("trimmers, groomers & clippers", ("shaver_trimmer",), ()),
    ("mice & keyboard combos", ("keyboard_mouse_combo",), ()),
    ("medical supplies & equipments", ("medical_equipment",), ()),
    ("sound & home theaters", ("sound_bar", "speaker", "home_theater"), ()),
    ("audio video accessories", ("av_accessory",), ()),
    ("camera & accessories", ("camera",), ()),
    ("monitors & accessories", ("monitor",), ()),
    ("body soaps & shower gels", ("body_soap",), ()),
    ("hair removal appliances", ("hair_removal",), ()),
    ("combo washer dryers", ("washer_dryer_combo",), ()),
    ("combo washer dryer", ("washer_dryer_combo",), ()),
    ("clothing & dryers", ("clothes_dryer",), ()),
    ("cooktops & ranges", ("cooking_range",), ()),
    ("tablets & ipads", ("tablet",), ()),
    ("desktops & pc", ("desktop_pc",), ()),
    ("like new mobiles", ("like_new_mobile",), ()),
    ("baking & flavours", ("baking_flavours",), ()),
    ("home & living", ("home_living",), ()),
    ("mother & baby", ("mother_baby",), ()),
    ("shaving & grooming", ("shaver_trimmer",), ()),
    ("skin care tools", ("skin_care_tool",), ()),
    # --- 3-word compounds ---
    ("air conditioners alfabnpl", ("air_conditioner",), ()),
    ("non inverter split ac", ("air_conditioner",), ("ac_type:non_inverter",)),
    ("non-inverter split ac", ("air_conditioner",), ("ac_type:non_inverter",)),
    ("inverter split ac", ("air_conditioner",), ()),
    ("traditional split ac", ("air_conditioner",), ("ac_type:non_inverter",)),
    ("non inverter ac", ("air_conditioner",), ("ac_type:non_inverter",)),
    ("non-inverter ac", ("air_conditioner",), ("ac_type:non_inverter",)),
    ("floor standing ac", ("air_conditioner",), ("ac_form:floor_standing",)),
    ("garment steam iron", ("iron",), ("iron_type:steam",)),
    ("smart led tv", ("television",), ("tv_type:smart",)),
    ("basic led tv", ("television",), ("tv_type:basic",)),
    ("qled smart tv", ("television",), ("tv_display:qled", "tv_type:smart")),
    ("electric oven toaster", ("oven",), ()),
    ("dishwashing machine", ("dishwasher",), ()),
    # --- 2-word compounds (mask constituent single words!) ---
    ("microwave ovens", ("microwave_oven",), ()),
    ("microwave oven", ("microwave_oven",), ()),
    ("oven toasters", ("oven",), ()),
    ("oven toaster", ("oven",), ()),
    ("toaster ovens", ("oven",), ()),
    ("toaster oven", ("oven",), ()),
    ("electric ovens", ("oven",), ()),
    ("electric oven", ("oven",), ()),
    ("baking ovens", ("oven",), ()),
    ("baking oven", ("oven",), ()),
    ("water heaters", ("water_heater",), ()),
    ("water heater", ("water_heater",), ()),
    ("gas geysers", ("water_heater",), ()),
    ("gas geyser", ("water_heater",), ()),
    ("electric geysers", ("water_heater",), ()),
    ("electric geyser", ("water_heater",), ()),
    ("instant geysers", ("water_heater",), ()),
    ("instant geyser", ("water_heater",), ()),
    ("room heaters", ("room_heater",), ()),
    ("room heater", ("room_heater",), ()),
    ("fan heaters", ("room_heater",), ()),
    ("fan heater", ("room_heater",), ()),
    ("electric heaters", ("room_heater",), ()),
    ("electric heater", ("room_heater",), ()),
    ("gas heaters", ("room_heater",), ()),
    ("gas heater", ("room_heater",), ()),
    ("air coolers", ("air_cooler",), ()),
    ("air cooler", ("air_cooler",), ()),
    ("room coolers", ("air_cooler",), ()),
    ("room cooler", ("air_cooler",), ()),
    ("desert coolers", ("air_cooler",), ()),
    ("desert cooler", ("air_cooler",), ()),
    ("air conditioners", ("air_conditioner",), ()),
    ("air conditioner", ("air_conditioner",), ()),
    ("air conditioning", ("air_conditioner",), ()),
    ("split ac", ("air_conditioner",), ()),
    ("ac inverter", ("air_conditioner",), ("ac_type:inverter",)),
    ("ac non-inverter", ("air_conditioner",), ("ac_type:non_inverter",)),
    ("ac non inverter", ("air_conditioner",), ("ac_type:non_inverter",)),
    ("air purifiers", ("air_purifier",), ()),
    ("air purifier", ("air_purifier",), ()),
    ("air humidifiers", ("humidifier",), ()),
    ("air humidifier", ("humidifier",), ()),
    ("air fryers", ("air_fryer",), ()),
    ("air fryer", ("air_fryer",), ()),
    ("deep freezers", ("deep_freezer",), ()),
    ("deep freezer", ("deep_freezer",), ()),
    ("chest freezers", ("deep_freezer",), ()),
    ("chest freezer", ("deep_freezer",), ()),
    ("water dispensers", ("water_dispenser",), ()),
    ("water dispenser", ("water_dispenser",), ()),
    ("water purifiers", ("water_purifier",), ()),
    ("water purifier", ("water_purifier",), ()),
    ("water generators", ("water_generator",), ()),
    ("water generator", ("water_generator",), ()),
    ("dish washers", ("dishwasher",), ()),
    ("dish washer", ("dishwasher",), ()),
    ("washing machines", ("washing_machine",), ()),
    ("washing machine", ("washing_machine",), ()),
    ("clothes dryers", ("clothes_dryer",), ()),
    ("clothes dryer", ("clothes_dryer",), ()),
    ("clothing dryers", ("clothes_dryer",), ()),
    ("clothing dryer", ("clothes_dryer",), ()),
    ("washer dryers", ("washer_dryer_combo",), ()),
    ("washer dryer", ("washer_dryer_combo",), ()),
    ("garment steamers", ("garment_steamer",), ()),
    ("garment steamer", ("garment_steamer",), ()),
    ("clothes steamers", ("garment_steamer",), ()),
    ("clothes steamer", ("garment_steamer",), ()),
    ("dry irons", ("iron",), ("iron_type:dry",)),
    ("dry iron", ("iron",), ("iron_type:dry",)),
    ("steam irons", ("iron",), ("iron_type:steam",)),
    ("steam iron", ("iron",), ("iron_type:steam",)),
    ("hair straighteners", ("hair_straightener",), ()),
    ("hair straightener", ("hair_straightener",), ()),
    ("straightening comb", ("hair_straightener",), ()),
    ("straightening brush", ("hair_straightener",), ()),
    ("flat irons", ("hair_straightener",), ()),
    ("flat iron", ("hair_straightener",), ()),
    ("hair curlers", ("hair_curler",), ()),
    ("hair curler", ("hair_curler",), ()),
    ("curling irons", ("hair_curler",), ()),
    ("curling iron", ("hair_curler",), ()),
    ("hair dryers", ("hair_dryer",), ()),
    ("hair dryer", ("hair_dryer",), ()),
    ("waffle makers", ("waffle_maker",), ()),
    ("waffle maker", ("waffle_maker",), ()),
    ("waffle irons", ("waffle_maker",), ()),
    ("waffle iron", ("waffle_maker",), ()),
    ("bread makers", ("bread_maker",), ()),
    ("bread maker", ("bread_maker",), ()),
    ("egg boilers", ("egg_boiler",), ()),
    ("egg boiler", ("egg_boiler",), ()),
    ("sandwich makers", ("sandwich_maker",), ()),
    ("sandwich maker", ("sandwich_maker",), ()),
    ("coffee machines", ("coffee_maker",), ()),
    ("coffee machine", ("coffee_maker",), ()),
    ("coffee makers", ("coffee_maker",), ()),
    ("coffee maker", ("coffee_maker",), ()),
    ("food processors", ("food_processor",), ()),
    ("food processor", ("food_processor",), ()),
    ("food factory", ("food_processor",), ()),
    ("electric kettles", ("electric_kettle",), ()),
    ("electric kettle", ("electric_kettle",), ()),
    ("juicer blender", ("juicer",), ()),
    ("fruit extractors", ("juicer",), ()),
    ("fruit extractor", ("juicer",), ()),
    ("stand mixers", ("mixer",), ("mixer_type:stand",)),
    ("stand mixer", ("mixer",), ("mixer_type:stand",)),
    ("hand mixers", ("mixer",), ("mixer_type:hand",)),
    ("hand mixer", ("mixer",), ("mixer_type:hand",)),
    ("hand blenders", ("blender",), ("blender_type:hand",)),
    ("hand blender", ("blender",), ("blender_type:hand",)),
    ("immersion blenders", ("blender",), ("blender_type:hand",)),
    ("immersion blender", ("blender",), ("blender_type:hand",)),
    ("countertop blenders", ("blender",), ("blender_type:countertop",)),
    ("countertop blender", ("blender",), ("blender_type:countertop",)),
    ("cooking ranges", ("cooking_range",), ()),
    ("cooking range", ("cooking_range",), ()),
    ("gas ranges", ("cooking_range",), ()),
    ("gas range", ("cooking_range",), ()),
    ("range hoods", ("range_hood",), ()),
    ("range hood", ("range_hood",), ()),
    ("kitchen hoods", ("range_hood",), ()),
    ("kitchen hood", ("range_hood",), ()),
    ("vacuum cleaners", ("vacuum_cleaner",), ()),
    ("vacuum cleaner", ("vacuum_cleaner",), ()),
    ("vaccum cleaners", ("vacuum_cleaner",), ()),
    ("vaccum cleaner", ("vacuum_cleaner",), ()),
    ("sewing machines", ("sewing_machine",), ()),
    ("sewing machine", ("sewing_machine",), ()),
    ("solar panels", ("solar_panel",), ()),
    ("solar panel", ("solar_panel",), ()),
    ("sound bars", ("sound_bar",), ()),
    ("sound bar", ("sound_bar",), ()),
    ("home theaters", ("home_theater",), ()),
    ("home theater", ("home_theater",), ()),
    ("home audio", ("sound_bar", "speaker", "home_theater"), ()),
    ("smart tv", ("television",), ("tv_type:smart",)),
    ("google tv", ("television",), ("tv_type:smart",)),
    ("android tv", ("television",), ("tv_type:smart",)),
    ("basic tv", ("television",), ("tv_type:basic",)),
    ("qled tv", ("television",), ("tv_display:qled", "tv_type:smart")),
    ("led tvs", ("television",), ()),
    ("led tv", ("television",), ()),
    ("gaming chairs", ("gaming_chair",), ()),
    ("gaming chair", ("gaming_chair",), ()),
    ("paper shredders", ("paper_shredder",), ()),
    ("paper shredder", ("paper_shredder",), ()),
    ("attendence machine", ("attendance_machine",), ()),
    ("attendance machine", ("attendance_machine",), ()),
    ("computer accessories", ("computer_accessory",), ()),
    ("bathroom scales", ("bathroom_scale",), ()),
    ("bathroom scale", ("bathroom_scale",), ()),
    ("camp kitchen", ("camp_kitchen",), ()),
    ("lip gloss", ("lip_gloss",), ()),
    ("makeup accessories", ("makeup_accessory",), ()),
    ("bulk deals", ("bulk_deals",), ()),
    # --- 1-word concepts (matched only on unmasked spans) ---
    ("refrigerators", ("refrigerator",), ()),
    ("refrigerator", ("refrigerator",), ()),
    ("fridges", ("refrigerator",), ()),
    ("fridge", ("refrigerator",), ()),
    ("freezers", ("deep_freezer",), ()),
    ("freezer", ("deep_freezer",), ()),
    ("microwaves", ("microwave_oven",), ()),
    ("microwave", ("microwave_oven",), ()),
    ("ovens", ("oven",), ()),
    ("oven", ("oven",), ()),
    ("cooktops", ("cooking_range",), ()),
    ("cooktop", ("cooking_range",), ()),
    ("dishwashers", ("dishwasher",), ()),
    ("dishwasher", ("dishwasher",), ()),
    ("dishwashing", ("dishwashing",), ()),
    ("geysers", ("water_heater",), ()),
    ("geyser", ("water_heater",), ()),
    ("heaters", ("room_heater",), ()),
    ("heater", ("room_heater",), ()),
    ("fans", ("fan",), ()),
    ("fan", ("fan",), ()),
    ("humidifiers", ("humidifier",), ()),
    ("humidifier", ("humidifier",), ()),
    ("humdifier", ("humidifier",), ()),
    ("dehumidifiers", ("dehumidifier",), ()),
    ("dehumidifier", ("dehumidifier",), ()),
    ("ac", ("air_conditioner",), ()),
    ("irons", ("iron",), ()),
    ("iron", ("iron",), ()),
    ("vacuums", ("vacuum_cleaner",), ()),
    ("vacuum", ("vacuum_cleaner",), ()),
    ("juicers", ("juicer",), ()),
    ("juicer", ("juicer",), ()),
    ("mixers", ("mixer",), ()),
    ("mixer", ("mixer",), ()),
    ("blenders", ("blender",), ()),
    ("blender", ("blender",), ()),
    ("grinders", ("grinder",), ()),
    ("grinder", ("grinder",), ()),
    ("toasters", ("toaster",), ()),
    ("toaster", ("toaster",), ()),
    ("kettles", ("electric_kettle",), ()),
    ("kettle", ("electric_kettle",), ()),
    ("ups", ("ups",), ()),
    ("batteries", ("battery",), ()),
    ("battery", ("battery",), ()),
    ("soundbars", ("sound_bar",), ()),
    ("soundbar", ("sound_bar",), ()),
    ("speakers", ("speaker",), ()),
    ("speaker", ("speaker",), ()),
    ("projectors", ("projector",), ()),
    ("projector", ("projector",), ()),
    ("qled", ("television",), ("tv_display:qled", "tv_type:smart")),
    ("oled", ("television",), ("tv_type:smart",)),
    ("televisions", ("television",), ()),
    ("television", ("television",), ()),
    ("tvs", ("television",), ()),
    ("tv", ("television",), ()),
    ("led", ("television",), ()),
    ("smartphones", ("smartphone",), ()),
    ("smartphone", ("smartphone",), ()),
    ("tablets", ("tablet",), ()),
    ("tablet", ("tablet",), ()),
    ("ipads", ("tablet",), ()),
    ("ipad", ("tablet",), ()),
    ("laptops", ("laptop",), ()),
    ("laptop", ("laptop",), ()),
    ("printers", ("printer",), ()),
    ("printer", ("printer",), ()),
    ("scanners", ("scanner",), ()),
    ("scanner", ("scanner",), ()),
    ("keyboards", ("keyboard",), ()),
    ("keyboard", ("keyboard",), ()),
    ("mouse", ("mouse",), ()),
    ("consoles", ("console",), ()),
    ("console", ("console",), ()),
    ("massagers", ("massager",), ()),
    ("massager", ("massager",), ()),
    ("trimmers", ("shaver_trimmer",), ()),
    ("trimmer", ("shaver_trimmer",), ()),
    ("shavers", ("shaver_trimmer",), ()),
    ("shaver", ("shaver_trimmer",), ()),
    ("lipstick", ("lipstick",), ()),
    ("fashion", ("fashion",), ()),
    ("automotive", ("automotive",), ()),
    ("automative", ("automotive",), ()),
    ("campaigns", ("campaigns",), ()),
    ("accessories", ("accessories",), ()),
]

# Compile phrase regexes sorted by word count descending, then character length descending
_COMPILED_CONCEPT_PHRASES: tuple[tuple[re.Pattern[str], tuple[str, ...], tuple[str, ...]], ...] = tuple(
    (
        re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", re.IGNORECASE),
        concepts,
        traits,
    )
    for phrase, concepts, traits in sorted(
        _RAW_CONCEPT_PHRASES,
        key=lambda item: (len(item[0].split()), len(item[0])),
        reverse=True,
    )
)

# Bound Polarity & Subtype Trait Regexes (Negation checked and masked BEFORE positive)
_NON_INVERTER_RE = re.compile(
    r"\b(?:non[\s\-_]*invert(?:er|or)s?|non[\s\-_]*inv|without[\s\-_]*inverter|fixed[\s\-_]*speed)\b",
    re.IGNORECASE,
)
_INVERTER_RE = re.compile(
    r"\b(?:dc\s+inverter|inverters?|t-?ai|bldc|inverteron)\b",
    re.IGNORECASE,
)
_FLOOR_STANDING_RE = re.compile(
    r"\b(?:floor[\s\-_]*standing|cabinet\s+ac|tower\s+ac)\b",
    re.IGNORECASE,
)
_BASIC_TV_RE = re.compile(
    r"\b(?:non[\s\-_]*smart|basic\s+(?:led\s+)?tv|basic\s+led|standard\s+(?:led\s+)?tv)\b",
    re.IGNORECASE,
)
_QLED_TV_RE = re.compile(r"\bqled\b", re.IGNORECASE)
_SMART_TV_RE = re.compile(
    r"\b(?:smart|google\s*tv|android|andriod|webos|vidaa|tizen)\b",
    re.IGNORECASE,
)
_SEMI_AUTO_WASH_RE = re.compile(
    r"\b(?:semi[\s\-_]*auto(?:matic)?|twin[\s\-_]*tub)\b",
    re.IGNORECASE,
)
_FULLY_AUTO_WASH_RE = re.compile(
    r"\b(?:fully[\s\-_]*auto(?:matic)?|top[\s\-_]*load|front[\s\-_]*load)\b",
    re.IGNORECASE,
)
_DRY_IRON_TRAIT_RE = re.compile(r"\bdry\b", re.IGNORECASE)
_STEAM_IRON_TRAIT_RE = re.compile(r"\bsteam\b", re.IGNORECASE)
_STAND_MIXER_TRAIT_RE = re.compile(r"\bstand\s+mixers?\b", re.IGNORECASE)
_HAND_MIXER_TRAIT_RE = re.compile(r"\bhand\s+mixers?\b", re.IGNORECASE)
_HAND_BLENDER_TRAIT_RE = re.compile(r"\b(?:hand|immersion|stick)\s+blenders?\b", re.IGNORECASE)
_COUNTERTOP_BLENDER_TRAIT_RE = re.compile(
    r"\b(?:countertop|jug|table)\s+blenders?\b", re.IGNORECASE
)


def _singularise(words: str) -> str:
    """Small, explicit plural fold used for normalized phrase comparison."""
    return re.sub(r"\b([a-z]{4,})s\b", r"\1", words)


def _word_in(phrase: str, text: str) -> bool:
    """True when ``phrase`` appears as whole word(s) inside ``text``."""
    return bool(phrase and re.search(rf"\b{re.escape(phrase)}\b", text))


def _match_table_key(segment: str, table_keys: list[str]) -> str | None:
    """Deterministic whole-word key match against a flat category dictionary."""
    if segment in table_keys:
        return segment
    folded = _singularise(segment)
    for key in table_keys:
        if _singularise(key) == folded:
            return key
    for key in sorted(table_keys, key=len, reverse=True):
        if _word_in(key, segment) or _word_in(_singularise(key), folded):
            return key
    for key in sorted(table_keys, key=len, reverse=True):
        if _word_in(segment, key) or _word_in(folded, _singularise(key)):
            return key
    return None


def _split_primary_secondary(text: str) -> tuple[str, str]:
    """Split text at the first secondary-feature preposition ('with', 'featuring', etc.)."""
    if not text:
        return "", ""
    first_line = text.splitlines()[0] if "\n" in text else text
    match = _SECONDARY_PREP_RE.search(first_line)
    if not match:
        return first_line, ""
    return first_line[: match.start()], first_line[match.end() :]


def _scan_concepts_in_zone(text: str) -> tuple[tuple[str, ...], frozenset[str]]:
    """Scan a text zone longest-phrase-first, masking matched character spans."""
    if not text or not text.strip():
        return (), frozenset()
    norm = re.sub(r"\s+", " ", text.strip().lower())
    consumed = [False] * len(norm)
    matched_with_pos: list[tuple[int, str]] = []
    traits: set[str] = set()

    for pattern, concepts, phrase_traits in _COMPILED_CONCEPT_PHRASES:
        for m in pattern.finditer(norm):
            start, end = m.span()
            if any(consumed[i] for i in range(start, end)):
                continue
            for i in range(start, end):
                consumed[i] = True
            for idx, c in enumerate(concepts):
                matched_with_pos.append((start + idx, c))
            traits.update(phrase_traits)

    matched_with_pos.sort(key=lambda item: item[0])
    ordered_concepts: list[str] = []
    for _, c in matched_with_pos:
        if c not in ordered_concepts:
            ordered_concepts.append(c)
    return tuple(ordered_concepts), frozenset(traits)


def _extract_traits(
    primary_text: str,
    full_text: str = "",
    leaf_segment: str = "",
    active_concepts: frozenset[str] = frozenset(),
) -> frozenset[str]:
    """Extract bound polarity and subtype traits without allowing negative terms to trigger positive."""
    traits: set[str] = set()
    combined = f"{leaf_segment}\n{primary_text}\n{full_text}".strip()
    if not combined:
        return frozenset()

    # 1. AC Inverter / Non-Inverter & Floor Standing
    masked_ac = combined
    if _NON_INVERTER_RE.search(masked_ac):
        traits.add("ac_type:non_inverter")
        masked_ac = _NON_INVERTER_RE.sub(" ", masked_ac)
    if _INVERTER_RE.search(masked_ac) and "ac_type:non_inverter" not in traits:
        traits.add("ac_type:inverter")
    if _FLOOR_STANDING_RE.search(combined):
        traits.add("ac_form:floor_standing")

    # 2. TV Smart / Basic / QLED
    masked_tv = combined
    if _BASIC_TV_RE.search(masked_tv):
        traits.add("tv_type:basic")
        masked_tv = _BASIC_TV_RE.sub(" ", masked_tv)
    if _QLED_TV_RE.search(masked_tv):
        traits.add("tv_display:qled")
        if "tv_type:basic" not in traits:
            traits.add("tv_type:smart")
    if _SMART_TV_RE.search(masked_tv) and "tv_type:basic" not in traits:
        traits.add("tv_type:smart")

    # 3. Washing Machine Semi / Fully Automatic
    masked_wash = combined
    if _SEMI_AUTO_WASH_RE.search(masked_wash):
        traits.add("wash_mode:semi_auto")
        masked_wash = _SEMI_AUTO_WASH_RE.sub(" ", masked_wash)
    if _FULLY_AUTO_WASH_RE.search(masked_wash) and "wash_mode:semi_auto" not in traits:
        traits.add("wash_mode:fully_auto")

    # 4. Iron Dry / Steam (scoped to primary text & leaf segment so secondary "with steam generator"
    # on a Garment Steamer never turns it into a Steam Iron)
    iron_scope = f"{leaf_segment}\n{primary_text}\n{full_text}".strip()
    if "iron" in active_concepts or not active_concepts:
        if _DRY_IRON_TRAIT_RE.search(iron_scope):
            traits.add("iron_type:dry")
        if _STEAM_IRON_TRAIT_RE.search(iron_scope):
            # Ignore "garment steamer" when checking for steam iron trait
            cleaned_iron = re.sub(r"\bgarment\s+steamers?\b", " ", iron_scope, flags=re.IGNORECASE)
            if _STEAM_IRON_TRAIT_RE.search(cleaned_iron):
                traits.add("iron_type:steam")

    # 5. Mixer / Blender subtypes
    if _STAND_MIXER_TRAIT_RE.search(combined):
        traits.add("mixer_type:stand")
    if _HAND_MIXER_TRAIT_RE.search(combined):
        traits.add("mixer_type:hand")
    if _HAND_BLENDER_TRAIT_RE.search(combined):
        traits.add("blender_type:hand")
    if _COUNTERTOP_BLENDER_TRAIT_RE.search(combined):
        traits.add("blender_type:countertop")

    return frozenset(traits)


@dataclass(frozen=True)
class ProductConcept:
    """Canonical product identity and traits extracted from source evidence (M1.5b)."""

    primary_concepts: tuple[str, ...]
    canonical_product_type: str
    traits: frozenset[str]
    secondary_concepts: frozenset[str]
    breadcrumb_concepts: tuple[str, ...]
    inferred: bool

    @property
    def primary_concept(self) -> str:
        return self.primary_concepts[0] if self.primary_concepts else ""


def _fallback_inferred_product_type(raw_breadcrumb: str, source_brand: str, title: str = "") -> str:
    """Derive a clean singular fallback Product Type when no known concept matches."""
    segments = [s.strip() for s in _BREADCRUMB_DELIM_RE.split(raw_breadcrumb) if s.strip()]
    last = segments[-1] if segments else (raw_breadcrumb.strip() or title.strip())
    if source_brand:
        last = re.sub(re.escape(source_brand), "", last, flags=re.IGNORECASE).strip(" -")
    if last.isupper():
        return last
    if len(last) > 3 and last.lower().endswith("s") and not last.lower().endswith(("ss", "us")):
        last = last[:-1]
    return last.title() if last else "Product"


def extract_product_concept(
    raw_breadcrumb: str,
    title: str = "",
    description: str = "",
    source_brand: str = "",
) -> ProductConcept:
    """Extract canonical ProductConcept from breadcrumb, title, and description evidence."""
    raw_segments = [s.strip() for s in _BREADCRUMB_DELIM_RE.split(raw_breadcrumb) if s.strip()]
    norm_segments = [s.lower() for s in raw_segments]

    # Walk breadcrumb segments from leaf to root to find the most specific non-structural concept(s)
    leaf_concepts: tuple[str, ...] = ()
    leaf_traits: frozenset[str] = frozenset()
    leaf_segment_str = norm_segments[-1] if norm_segments else ""
    for seg in reversed(norm_segments):
        if seg in _STRUCTURAL_SEGMENTS:
            continue
        cleaned_seg = seg
        if source_brand:
            cleaned_seg = re.sub(
                rf"\b{re.escape(source_brand.lower())}\b", " ", cleaned_seg
            ).strip()
        c_tuple, t_set = _scan_concepts_in_zone(cleaned_seg)
        if not c_tuple and cleaned_seg != seg:
            c_tuple, t_set = _scan_concepts_in_zone(seg)
        if c_tuple:
            leaf_concepts = c_tuple
            leaf_traits = t_set
            break

    # Split title into primary appliance zone vs prepositional secondary feature zone
    primary_title_zone, secondary_title_zone = _split_primary_secondary(title)
    title_concepts, title_phrase_traits = _scan_concepts_in_zone(primary_title_zone)
    sec_concepts, _ = _scan_concepts_in_zone(secondary_title_zone)

    # Reconcile Breadcrumb Concepts with Title Primary Concepts:
    # 1. If breadcrumb had no specific appliance concept (empty or only structural parents),
    #    use Title primary concepts (or scan description if title was also empty).
    # 2. If breadcrumb was a multi-concept umbrella (e.g. {"iron", "garment_steamer"}) and
    #    Title primary concepts narrow it to a subset (e.g. {"iron"} or {"garment_steamer"}),
    #    use the narrowed Title concept!
    # 3. If breadcrumb was a broad concept in _CONCEPT_REFINEMENTS (e.g. "oven") and Title
    #    states a compound refinement (e.g. "microwave_oven"), use the compound refinement!
    # 4. Otherwise, keep the specific breadcrumb leaf concept so mentions in text never
    #    override a specific breadcrumb leaf like "Sound bars" or "UPS".
    resolved_concepts: tuple[str, ...]
    if not leaf_concepts:
        if title_concepts:
            resolved_concepts = (title_concepts[0],)
        else:
            desc_primary, _ = _split_primary_secondary(description)
            desc_concepts, _ = _scan_concepts_in_zone(desc_primary)
            resolved_concepts = (desc_concepts[0],) if desc_concepts else ()
    elif len(leaf_concepts) > 1 and title_concepts:
        narrowed = tuple(c for c in title_concepts if c in leaf_concepts)
        resolved_concepts = (narrowed[0],) if narrowed else leaf_concepts
    elif (
        len(leaf_concepts) == 1
        and leaf_concepts[0] in _CONCEPT_REFINEMENTS
        and title_concepts
        and title_concepts[0] in _CONCEPT_REFINEMENTS[leaf_concepts[0]]
    ):
        resolved_concepts = (title_concepts[0],)
    else:
        resolved_concepts = leaf_concepts

    active_concept_set = frozenset(resolved_concepts)
    title_traits = (
        leaf_traits
        | title_phrase_traits
        | _extract_traits(
            primary_text=primary_title_zone,
            full_text="",
            leaf_segment=leaf_segment_str,
            active_concepts=active_concept_set,
        )
    )
    title_axes = {t.partition(":")[0] for t in title_traits}
    desc_traits = (
        _extract_traits(
            primary_text="",
            full_text=description,
            leaf_segment="",
            active_concepts=active_concept_set,
        )
        if description
        else frozenset()
    )
    # Generic axis-precedence rule: a trait axis explicitly stated in the Breadcrumb/Title
    # is authoritative and is never overridden by marketing comparisons in Description prose.
    all_traits = title_traits | frozenset(
        t for t in desc_traits if t.partition(":")[0] not in title_axes
    )

    if resolved_concepts and resolved_concepts[0] in CONCEPT_PRODUCT_TYPES:
        canonical_pt = CONCEPT_PRODUCT_TYPES[resolved_concepts[0]]
        inferred = False
    else:
        canonical_pt = _fallback_inferred_product_type(raw_breadcrumb, source_brand, title=title)
        inferred = True

    return ProductConcept(
        primary_concepts=resolved_concepts,
        canonical_product_type=canonical_pt,
        traits=all_traits,
        secondary_concepts=frozenset(sec_concepts) - active_concept_set,
        breadcrumb_concepts=leaf_concepts,
        inferred=inferred,
    )


# ===========================================================================
#  Validated Taxonomy Graph & 4-Stage Category Resolver (M1.5c)
# ===========================================================================


class NodeStatus(str, Enum):
    """Assignability status of a node in a compiled TaxonomyTree."""

    ASSIGNABLE_LEAF = "assignable_leaf"
    STRUCTURAL_PARENT = "structural_parent"
    DEPLETED_BRANCH = "depleted_branch"
    INACTIVE_NODE = "inactive_node"


@dataclass(frozen=True)
class TaxonomyNode:
    """One validated category node in a platform or cell TaxonomyTree."""

    category_id: str
    name: str
    key: str
    parent_id: str | None
    handle: str
    is_active: bool
    ancestors: tuple[str, ...]
    formatted_id: str
    status: NodeStatus
    concepts: frozenset[str]
    required_traits: frozenset[str]
    trait_rank: int = 0


@dataclass(frozen=True)
class TaxonomyTree:
    """Immutable compiled category taxonomy for one cell."""

    nodes: tuple[TaxonomyNode, ...]
    by_key: Mapping[str, TaxonomyNode]


def _resolve_taxonomy_file_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.exists():
        return path
    pkg_dir = Path(__file__).resolve().parent
    candidate = pkg_dir / path
    if candidate.exists():
        return candidate
    repo_candidate = pkg_dir.parent / path
    if repo_candidate.exists():
        return repo_candidate
    raise ValueError(f"Taxonomy file not found: {raw_path!r}")


def _node_concepts_and_traits(
    name: str, handle: str = ""
) -> tuple[frozenset[str], frozenset[str], int]:
    """Analyze a taxonomy node's name/handle into (concepts, required_traits, trait_rank)."""
    norm_name = name.strip().lower()
    concepts_tuple, phrase_traits = _scan_concepts_in_zone(norm_name)
    traits = set(phrase_traits) | set(
        _extract_traits(primary_text=norm_name, active_concepts=frozenset(concepts_tuple))
    )
    if not concepts_tuple and handle:
        tail = handle.strip("/").split("/")[-1].replace("-", " ")
        c_tail, t_tail = _scan_concepts_in_zone(tail)
        concepts_tuple = c_tail
        traits |= set(t_tail)
    rank = max((_TRAIT_RANKS.get(t, 0) for t in traits), default=0)
    return frozenset(concepts_tuple), frozenset(traits), rank


@lru_cache(maxsize=8)
def load_raw_taxonomy_nodes(
    raw_path: str, id_format: str = "ancestor_chain"
) -> tuple[TaxonomyNode, ...]:
    """Load and validate a raw hierarchical taxonomy JSON file."""
    file_path = _resolve_taxonomy_file_path(raw_path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    items = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
    if not isinstance(items, list):
        raise ValueError(f"Malformed taxonomy JSON in {raw_path!r}: expected list of nodes")

    raw_by_id: dict[str, dict[str, object]] = {}
    children_map: dict[str, list[str]] = {}
    for entry in items:
        if not isinstance(entry, dict) or "category_id" not in entry:
            raise ValueError(f"Malformed taxonomy entry in {raw_path!r}: {entry!r}")
        cid = str(entry["category_id"]).strip()
        if not cid:
            raise ValueError(f"Empty category_id in {raw_path!r}")
        if cid in raw_by_id:
            raise ValueError(f"Duplicate category_id {cid!r} in {raw_path!r}")
        raw_by_id[cid] = entry
        children_map[cid] = []

    parent_map: dict[str, str | None] = {}
    for cid, entry in raw_by_id.items():
        raw_parent = entry.get("parent")
        pid = str(raw_parent).strip() if raw_parent is not None and str(raw_parent).strip() else None
        if pid is not None and pid not in raw_by_id:
            raise ValueError(f"Orphan category {cid!r} references missing parent {pid!r}")
        parent_map[cid] = pid
        if pid is not None:
            children_map[pid].append(cid)

    ancestors_map: dict[str, tuple[str, ...]] = {}
    effective_active_map: dict[str, bool] = {}
    for cid in raw_by_id:
        chain: list[str] = []
        seen: set[str] = set()
        cur: str | None = cid
        active = True
        while cur is not None:
            if cur in seen:
                raise ValueError(f"Cycle detected in taxonomy at category_id {cur!r}")
            seen.add(cur)
            chain.append(cur)
            if not bool(raw_by_id[cur].get("is_active", True)):
                active = False
            cur = parent_map[cur]
        ancestors_map[cid] = tuple(reversed(chain))
        effective_active_map[cid] = active

    def _has_active_descendant(cid: str) -> bool:
        for child_id in children_map[cid]:
            if effective_active_map[child_id] and (
                not children_map[child_id] or _has_active_descendant(child_id)
            ):
                return True
        return False

    own_analysis: dict[str, tuple[frozenset[str], frozenset[str], int]] = {}
    for cid, entry in raw_by_id.items():
        name = str(entry.get("category_name", "")).strip()
        handle = str(entry.get("handle", "")).strip()
        own_analysis[cid] = _node_concepts_and_traits(name, handle)

    nodes: list[TaxonomyNode] = []
    for cid, entry in raw_by_id.items():
        name = str(entry.get("category_name", "")).strip()
        handle = str(entry.get("handle", "")).strip()
        ancestors = ancestors_map[cid]
        eff_active = effective_active_map[cid]
        kids = children_map[cid]

        if not eff_active:
            status = NodeStatus.INACTIVE_NODE
        elif not kids:
            status = NodeStatus.ASSIGNABLE_LEAF
        elif _has_active_descendant(cid):
            status = NodeStatus.STRUCTURAL_PARENT
        else:
            status = NodeStatus.DEPLETED_BRANCH

        concepts, req_traits, rank = own_analysis[cid]
        # If a child node states only a subtype trait (e.g. "Inverters", "Non-Invertors",
        # "Floor Standing" under "Air Conditioners"), inherit concepts from its nearest ancestor.
        if not concepts:
            p_cur = parent_map[cid]
            while p_cur is not None:
                p_concepts, _, _ = own_analysis[p_cur]
                if p_concepts:
                    concepts = p_concepts
                    break
                p_cur = parent_map[p_cur]
        if not concepts and name:
            concepts = frozenset({f"dynamic:{_singularise(name.lower())}"})

        formatted_id = cid if id_format == "leaf_only" else "_".join(ancestors)
        nodes.append(
            TaxonomyNode(
                category_id=cid,
                name=name,
                key=name.lower(),
                parent_id=parent_map[cid],
                handle=handle,
                is_active=eff_active,
                ancestors=ancestors,
                formatted_id=formatted_id,
                status=status,
                concepts=concepts,
                required_traits=req_traits,
                trait_rank=rank,
            )
        )
    return tuple(nodes)


@lru_cache(maxsize=8)
def load_raw_taxonomy_leaf_map(
    raw_path: str, id_format: str = "ancestor_chain"
) -> dict[str, str]:
    """Return {normalized_key: formatted_id} for all active assignable leaves in raw_path."""
    nodes = load_raw_taxonomy_nodes(raw_path, id_format=id_format)
    return {
        node.key: node.formatted_id
        for node in nodes
        if node.status == NodeStatus.ASSIGNABLE_LEAF
    }


def _compile_cell_taxonomy(cell: ResolvedCellConfig) -> TaxonomyTree:
    """Compile the authoritative TaxonomyTree for one ResolvedCellConfig."""
    authorized_map = cell.categories
    authorized_ids = set(authorized_map.values())
    nodes: list[TaxonomyNode] = []
    by_key: dict[str, TaxonomyNode] = {}

    if cell.raw_taxonomy_path:
        raw_nodes = load_raw_taxonomy_nodes(
            cell.raw_taxonomy_path, id_format=cell.category_id_format
        )
        seen_ids: set[str] = set()
        for rnode in raw_nodes:
            node_to_add = rnode
            seen_ids.add(rnode.formatted_id)
            if rnode.status == NodeStatus.ASSIGNABLE_LEAF:
                override_id = authorized_map.get(rnode.key)
                if override_id is None and rnode.formatted_id in authorized_ids:
                    override_id = rnode.formatted_id
                if override_id is None:
                    # Leaf exists in platform tree but is not authorized in this cell's categories map
                    continue
                if override_id != rnode.formatted_id:
                    node_to_add = TaxonomyNode(
                        category_id=rnode.category_id,
                        name=rnode.name,
                        key=rnode.key,
                        parent_id=rnode.parent_id,
                        handle=rnode.handle,
                        is_active=rnode.is_active,
                        ancestors=rnode.ancestors,
                        formatted_id=override_id,
                        status=rnode.status,
                        concepts=rnode.concepts,
                        required_traits=rnode.required_traits,
                        trait_rank=rnode.trait_rank,
                    )
                seen_ids.add(override_id)
            nodes.append(node_to_add)
            if node_to_add.status == NodeStatus.ASSIGNABLE_LEAF:
                by_key[node_to_add.key] = node_to_add

        # Include any custom flat entries in cell.categories that were added outside raw_taxonomy_path
        for key, val in authorized_map.items():
            norm_key = key.strip().lower()
            if val in seen_ids:
                # Point alias key at the existing assignable leaf node
                for existing in nodes:
                    if existing.formatted_id == val and existing.status == NodeStatus.ASSIGNABLE_LEAF:
                        by_key[norm_key] = existing
                        break
                continue
            concepts, req_traits, rank = _node_concepts_and_traits(norm_key)
            if not concepts:
                concepts = frozenset({f"dynamic:{_singularise(norm_key)}"})
            custom_node = TaxonomyNode(
                category_id=val,
                name=key,
                key=norm_key,
                parent_id=None,
                handle="",
                is_active=True,
                ancestors=tuple(val.split("_")),
                formatted_id=val,
                status=NodeStatus.ASSIGNABLE_LEAF,
                concepts=concepts,
                required_traits=req_traits,
                trait_rank=rank,
            )
            nodes.append(custom_node)
            by_key[norm_key] = custom_node
        return TaxonomyTree(nodes=tuple(nodes), by_key=by_key)

    # Flat dictionary compilation (e.g. KCC.digi, KCC.alfa, AJMER.alfa)
    for key, val in authorized_map.items():
        norm_key = key.strip().lower()
        concepts, req_traits, rank = _node_concepts_and_traits(norm_key)
        if not concepts:
            concepts = frozenset({f"dynamic:{_singularise(norm_key)}"})
        flat_node = TaxonomyNode(
            category_id=val,
            name=key,
            key=norm_key,
            parent_id=None,
            handle="",
            is_active=True,
            ancestors=tuple(val.split("_")),
            formatted_id=val,
            status=NodeStatus.ASSIGNABLE_LEAF,
            concepts=concepts,
            required_traits=req_traits,
            trait_rank=rank,
        )
        nodes.append(flat_node)
        by_key[norm_key] = flat_node

    return TaxonomyTree(nodes=tuple(nodes), by_key=by_key)


def _resolve_for_cell(
    cell: ResolvedCellConfig,
    raw_breadcrumb: str,
    segments: list[str],
    text: str,
    concept: ProductConcept,
) -> tuple[str | None, str | None, CategoryStatus, str]:
    """Resolve one platform cell's category ID, matched_key, CategoryStatus, and reason."""
    platform_label = "DigiMall" if cell.platform == "digi" else "Alfa"
    alias_name = "DIGI_SEGMENT_ALIASES" if cell.platform == "digi" else "ALFA_SEGMENT_ALIASES"
    tree = _compile_cell_taxonomy(cell)

    if not cell.categories:
        return (
            None,
            None,
            CategoryStatus.UNMAPPED,
            f"no {platform_label} categories are configured for this vendor cell",
        )

    target_concepts = set(concept.primary_concepts)
    traits = concept.traits

    # Stage 1: Check explicit cell segment aliases or direct custom table keys on non-structural
    # segments when no canonical concept was found (supports dynamic custom keys like "wine chillers").
    aliases = cell.category_segment_aliases
    table_keys = list(tree.by_key)
    direct_alias_node: TaxonomyNode | None = None
    for seg in reversed(segments):
        if seg in _STRUCTURAL_SEGMENTS:
            continue
        mapped_key = aliases.get(seg)
        if mapped_key is not None and mapped_key in tree.by_key:
            candidate_node = tree.by_key[mapped_key]
            # Only use direct alias immediately if the target concept does not have sibling partitions
            # in this cell's tree and is not contradicted by a specific title concept.
            sibling_leaves = [
                n
                for n in tree.nodes
                if n.status == NodeStatus.ASSIGNABLE_LEAF
                and (n.concepts & candidate_node.concepts)
            ]
            if len(sibling_leaves) == 1 and not sibling_leaves[0].required_traits:
                direct_alias_node = sibling_leaves[0]
            break
        if not target_concepts:
            matched_k = _match_table_key(seg, table_keys)
            if matched_k is not None and matched_k in tree.by_key:
                direct_alias_node = tree.by_key[matched_k]
                break

    if direct_alias_node is not None:
        return (
            direct_alias_node.formatted_id,
            direct_alias_node.key,
            CategoryStatus.MAPPED,
            "",
        )

    if not target_concepts:
        return (
            None,
            None,
            CategoryStatus.UNMAPPED,
            f"breadcrumb {raw_breadcrumb!r} did not match any {platform_label} category key -- "
            f"add a keyword or a {alias_name} entry",
        )

    # Stage 2: Retrieve all nodes in the cell's TaxonomyTree matching target_concepts
    matching_nodes = [n for n in tree.nodes if n.concepts & target_concepts]
    if not matching_nodes:
        display_type = CONCEPT_PRODUCT_TYPES.get(concept.primary_concepts[0], raw_breadcrumb)
        return (
            None,
            None,
            CategoryStatus.UNMAPPED,
            f"no {platform_label} category exists for {display_type} -- "
            f"breadcrumb {raw_breadcrumb!r} did not match any {platform_label} category key "
            f"(add a keyword or a {alias_name} entry)",
        )

    # Separate assignable leaves from inactive nodes / depleted branches / structural parents
    leaf_candidates = [
        n
        for n in matching_nodes
        if n.status in (NodeStatus.ASSIGNABLE_LEAF, NodeStatus.INACTIVE_NODE)
    ]
    depleted_candidates = [
        n for n in matching_nodes if n.status == NodeStatus.DEPLETED_BRANCH
    ]

    if not leaf_candidates:
        if depleted_candidates:
            dep = depleted_candidates[0]
            return (
                None,
                None,
                CategoryStatus.INACTIVE_TARGET,
                f"{platform_label} category branch {dep.name!r} ({dep.category_id}) has only inactive "
                "child categories and cannot be assigned",
            )
        return (
            None,
            None,
            CategoryStatus.UNMAPPED,
            f"breadcrumb {raw_breadcrumb!r} matched only structural parent category in {platform_label}",
        )

    # Prefer atomic concept leaves (len(n.concepts) == 1) over combined multi-concept leaves
    # WHEN narrower leaves exist for the target concept in this taxonomy.
    if len(target_concepts) == 1:
        narrow_leaves = [n for n in leaf_candidates if n.concepts == target_concepts]
        if narrow_leaves:
            leaf_candidates = narrow_leaves
    else:
        # Multi-concept umbrella (e.g. "Iron & Garment steamer" with no narrowing Title/Description):
        # 1. If a combined leaf in this taxonomy covers all target_concepts (e.g. Alfa "11515"), use it.
        covering_leaves = [n for n in leaf_candidates if target_concepts <= n.concepts]
        if covering_leaves:
            leaf_candidates = covering_leaves
        else:
            # 2. If this taxonomy splits the umbrella into multiple distinct atomic concept leaves
            #    (e.g. separate "Iron" and "Garment Steamer" branches), refuse to guess between them.
            distinct_concept_groups = {
                frozenset(n.concepts & target_concepts)
                for n in leaf_candidates
                if (n.concepts & target_concepts)
            }
            if len(distinct_concept_groups) > 1:
                unique_umbrella: dict[str, TaxonomyNode] = {}
                for n in leaf_candidates:
                    if n.formatted_id not in unique_umbrella:
                        unique_umbrella[n.formatted_id] = n
                cand_names = ", ".join(
                    f"{w.name!r} ({w.category_id})" for w in unique_umbrella.values()
                )
                return (
                    None,
                    None,
                    CategoryStatus.SIBLING_AMBIGUOUS,
                    f"umbrella breadcrumb {raw_breadcrumb!r} spans multiple {platform_label} "
                    f"categories [{cand_names}] and Title/Description does not narrow the product type",
                )

    # Stage 3: Trait Partition & Sibling Disambiguation
    satisfied = [
        n for n in leaf_candidates if n.required_traits <= traits
    ]

    if satisfied:
        max_rank = max(n.trait_rank for n in satisfied)
        top_matches = [n for n in satisfied if n.trait_rank == max_rank]
        # Deduplicate by formatted_id in case multiple alias keys point to the same leaf
        unique_by_id: dict[str, TaxonomyNode] = {}
        for n in top_matches:
            if n.formatted_id not in unique_by_id:
                unique_by_id[n.formatted_id] = n
        winners = list(unique_by_id.values())

        if len(winners) == 1:
            winner = winners[0]
            # Stage 4: Assignability Verification
            if winner.status == NodeStatus.INACTIVE_NODE:
                return (
                    None,
                    None,
                    CategoryStatus.INACTIVE_TARGET,
                    f"matched {platform_label} category {winner.name!r} ({winner.category_id}) "
                    "is marked inactive (is_active=False)",
                )
            return winner.formatted_id, winner.key, CategoryStatus.MAPPED, ""

        active_winners = [w for w in winners if w.status == NodeStatus.ASSIGNABLE_LEAF]
        if not active_winners:
            cand_names = ", ".join(f"{w.name!r} ({w.category_id})" for w in winners)
            return (
                None,
                None,
                CategoryStatus.INACTIVE_TARGET,
                f"matched {platform_label} categories [{cand_names}] are all marked inactive (is_active=False)",
            )
        if len(active_winners) == 1:
            winner = active_winners[0]
            return winner.formatted_id, winner.key, CategoryStatus.MAPPED, ""

        # Multiple distinct active leaves tied (e.g. un-narrowed umbrella breadcrumb against atomic leaves)
        cand_names = ", ".join(f"{w.name!r} ({w.category_id})" for w in active_winners)
        return (
            None,
            None,
            CategoryStatus.SIBLING_AMBIGUOUS,
            f"ambiguous {platform_label} sibling categories [{cand_names}] -- Title/Description "
            "does not state which subtype applies",
        )

    # Zero candidates satisfied required_traits -> missing distinguishing subtype signal!
    unique_unmet: dict[str, TaxonomyNode] = {}
    for n in leaf_candidates:
        if n.formatted_id not in unique_unmet:
            unique_unmet[n.formatted_id] = n
    cand_names = ", ".join(f"{w.name!r} ({w.category_id})" for w in unique_unmet.values())
    return (
        None,
        None,
        CategoryStatus.SIBLING_AMBIGUOUS,
        f"missing subtype signal in Title/Description to disambiguate {platform_label} "
        f"sibling categories [{cand_names}]",
    )


def resolve_category(
    raw_breadcrumb: str,
    digi_text: str,
    alfa_text: str,
    vendor_cfg: VendorConfig | None = None,
) -> ResolvedCategory:
    """Resolve one breadcrumb string for BOTH platforms, independently."""
    from vendor_config import resolve_cell  # noqa: PLC0415

    digi_cell = resolve_cell(vendor_cfg, "digi")
    alfa_cell = resolve_cell(vendor_cfg, "alfa")
    segments = [
        s.strip().lower() for s in _BREADCRUMB_DELIM_RE.split(raw_breadcrumb) if s.strip()
    ]

    digi_title, _, digi_desc = digi_text.partition("\n")
    alfa_title, _, alfa_desc = alfa_text.partition("\n")

    concept_digi = extract_product_concept(
        raw_breadcrumb, title=digi_title, description=digi_desc
    )
    concept_alfa = (
        concept_digi
        if digi_text == alfa_text
        else extract_product_concept(raw_breadcrumb, title=alfa_title, description=alfa_desc)
    )

    digi_path, digi_key, digi_status, digi_reason = _resolve_for_cell(
        digi_cell, raw_breadcrumb, segments, digi_text, concept_digi
    )
    alfa_id, alfa_key, alfa_status, alfa_reason = _resolve_for_cell(
        alfa_cell, raw_breadcrumb, segments, alfa_text, concept_alfa
    )

    primary_concept = (
        concept_digi if not concept_digi.inferred or concept_alfa.inferred else concept_alfa
    )
    reason = digi_reason or alfa_reason
    return ResolvedCategory(
        raw=raw_breadcrumb,
        digi_path=digi_path,
        alfa_id=alfa_id,
        matched_key=digi_key or alfa_key,
        reason=reason,
        digi_reason=digi_reason,
        alfa_reason=alfa_reason,
        digi_status=digi_status,
        alfa_status=alfa_status,
        product_type=primary_concept.canonical_product_type,
        product_type_inferred=primary_concept.inferred,
    )


def resolve_product_type(
    category: ResolvedCategory,
    source_brand: str,
    vendor_cfg: VendorConfig | None = None,
    title: str = "",
    description: str = "",
) -> tuple[str, bool]:
    """Return ``(product_type, was_inferred)``.

    Decoupled from marketplace category lookup success: even when neither platform
    maps a category ID (or when a vendor's category table is empty), known product
    concepts resolve deterministically to their canonical Product Type with
    ``was_inferred=False``.
    """
    from vendor_config import resolve_cell  # noqa: PLC0415

    digi_cell = resolve_cell(vendor_cfg, "digi")
    alfa_cell = resolve_cell(vendor_cfg, "alfa")
    pt_map = digi_cell.product_type_map
    alfa_cats = alfa_cell.categories
    digi_cats = digi_cell.categories

    concept = extract_product_concept(
        category.raw,
        title=title,
        description=description,
        source_brand=source_brand,
    )

    # When Title/Description narrows a multi-concept umbrella breadcrumb (e.g. "Iron & Garment steamer"
    # narrowed to "Garment Steamer"), return the narrowed canonical Product Type directly.
    if (
        not concept.inferred
        and len(concept.breadcrumb_concepts) > 1
        and len(concept.primary_concepts) == 1
    ):
        return concept.canonical_product_type, False

    # 1. Check explicit cell product_type_map overrides first
    if pt_map:
        if category.matched_key and category.matched_key in pt_map:
            return pt_map[category.matched_key], False
        if category.alfa_id:
            for key, value in alfa_cats.items():
                if value == category.alfa_id and key in pt_map:
                    return pt_map[key], False
        if category.digi_path:
            for key, value in digi_cats.items():
                if value == category.digi_path and key in pt_map:
                    return pt_map[key], False
        segments = [
            s.strip().lower() for s in _BREADCRUMB_DELIM_RE.split(category.raw) if s.strip()
        ]
        if segments:
            leaf_seg = segments[-1]
            if leaf_seg in pt_map:
                return pt_map[leaf_seg], False
            folded = _singularise(leaf_seg)
            if folded in pt_map:
                return pt_map[folded], False

    # 2. Canonical ProductConcept resolution (independent of category mapping tables)
    if not concept.inferred:
        return concept.canonical_product_type, False

    if category.product_type and not category.product_type_inferred:
        return category.product_type, False

    if pt_map:
        segments = [
            s.strip().lower() for s in _BREADCRUMB_DELIM_RE.split(category.raw) if s.strip()
        ]
        for seg in reversed(segments[:-1]):
            if seg in pt_map:
                return pt_map[seg], False
            folded = _singularise(seg)
            if folded in pt_map:
                return pt_map[folded], False

    return _fallback_inferred_product_type(category.raw, source_brand, title=title), True
