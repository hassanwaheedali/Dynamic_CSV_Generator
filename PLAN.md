# KiaChahiye Bulk CSV Pipeline — Build Plan

**Status:** plan for approval — nothing built yet.
**Input verified:** `uploads/READY FIRST STEP 1 CSV.csv` — 1,800 rows × 8 columns, all 8 columns populated, 21 distinct `Categories` strings, 11 distinct `Brand` values, 1,798 distinct images, one single `Vendor` value.
**Target:** the `kiachahiye_bulk_csv/` package per spec §13, emitting two separate files under `data/output/digi/` and `data/output/alfa/`.

---

## 1. What the real file actually contains

I profiled the 1,800 rows before planning, because several of the spec's assumptions don't match the data. Everything below is measured, not estimated.

### 1.1 Description shapes — the spec's Branch 2 is the *rare* case, not the norm

| Real shape | Rows | Spec branch it maps to |
|---|---|---|
| Intro line + `Key Specifications:` + `• Label: Value` bullets | **1,550** | not explicitly named in §8 |
| Intro line + `Highlights:` + bullets | 20 | Branch 2 (partially) |
| Single plain line (`The Haier H55K85FX is a 55-inch smart LED TV.`) | **186** | Branch 4 guard |
| Multi-line prose, no labels/bullets | 20 | Branch 2/3 hybrid |
| Colon `Label: Value` lines | 12 | Branch 1 |
| **TAB-separated** label block (`Brand\tDawlance`, `Model\tDF-500DD`) | 12 | Branch 1, different delimiter |

- **15,562 bullets** in total: 14,442 are `Label: Value`, 1,116 are bare features, 4 are section-header junk.
- Top bullet labels: `voltage` (452), `capacity` (436), `frequency` (432), `type` (407), `climate class` (348), `product color` (327), `warranty` (283), `cooling technology` (257), `refrigerant` (249).
- The real-world `• Label: Value` bullet shape is the **dominant format** and is where most of the extractable spec data lives. The bullet separator in the real data is `:` (and also TAB), **not** the `**bold**—explanation` form the spec describes. Only ~169 rows use the em-dash form, and spec §14's Test Case 2 is one of them.

**Consequence:** the classifier is implemented as *one* parser producing `(label, value)` pairs with four ingestion modes (colon lines, TAB lines, `• Label: Value` bullets, `• lead—explanation` bullets), plus the Branch-4 thin guard. That reproduces all three worked examples and handles all 1,800 real rows with a single code path.

### 1.2 Model / SKU — the single biggest structural problem

| Measure | Value |
|---|---|
| Rows with a parenthetical code in the Title | 1,416 (537 distinct — top value `9178-WB` appears 22×) |
| Rows with any model code (paren anywhere / `Model:` line, incl. TAB) | ~1,508 |
| **Distinct SKUs once `KIA-<model>` is formed** | **546** |
| **Rows that would collide on an identical `Variant SKU`** | **~962** |
| **Rows that would collide on an identical `Handle`** | **~1,244** |
| Rows with no model code at all → fallback SKU path | 292 (spec estimated "essentially never") |
| Titles used by more than one row | 657 titles covering 1,705 rows |
| Fully identical rows (all 8 input columns) | 2 |

Worked example of the collision, verbatim from the file — one model code, four genuinely different products at four different prices:

```
DAWLANCE Acce Pro Glass Door Inverter Freezer-on-top Refrigerator (9193-WB)-Meadow Green  109,100
Dawlance AVANTE+ Freezer-On-Top Refrigerator 16 Cu Ft Luxe Brown (9193-WB)                 113,825
Dawlance Avante+ Freezer-On-Top Refrigerator 16 Cu Ft White (9193-WB)                      116,975
Dawlance Chrome FH Freezer-On-Top Refrigerator 16 Cu Ft Hairline Black (9193-WB)           101,225
```

Of the 657 repeated-title groups, 562 differ in sell price, 24 differ in colour, and only **1** group has an identical image — i.e. these are overwhelmingly **real variant rows, not accidental duplicates**, and must all survive. Spec §7 only dedupes `Handle`; it is silent on `Variant SKU`, which is the column a Shopify-style importer actually rejects on. → **Decision 1.**

Additional model-code quirks found:
- 185 rows put the code **mid-string**, followed by a colour suffix: `… Freezer (9193-WB)-Meadow Green`, `… (HRF-538IF)-Red`.
- 8 rows have **two** parenthetical groups: `Haier Solar Hybrid T3 Plus … (Solar Hybrid-IV(OW)-T3)` — the naive `\(([A-Z0-9][A-Z0-9\- ]+)\)` regex captures nothing usable here; needs innermost/last-group handling.
- 3 rows have a parenthetical with **no digit at all**: `(Cool Only)` → must be rejected as a model code (needs a "contains ≥1 digit" guard).
- Trailing `-Color` after a closing paren appears in ~185 rows and feeds the Option1/Color slot.

### 1.3 Brands — 3 real gaps, one of them a pure spacing artifact

| Brand | Rows | DigiMall | Alfa |
|---|---|---|---|
| Dawlance / Haier / Pel / TCL / Kenwood / Gree / Ecostar | 1,500 | ✅ | ✅ |
| **Superasia** (input spells it with no space; both lists have `"super asia"`) | 45 | alias → 3776 | alias → 4395 |
| **Orient** | 83 | ✅ 3769 | ❌ not on Alfa's list |
| **Homage** | 78 | ❌ not on either list | ❌ not on either list |
| **Hisense** | 4 | ❌ not on either list | ❌ not on either list |

So after the explicit `"superasia" → "super asia"` alias: **82 rows ship with an empty DigiMall `Brands`** and **165 rows with an empty Alfa `Brands`**. Spec §3 anticipates this ("Orient — not on Alfa's approved brand list") but does not say what to do when a brand is missing from **both** — that's 82 rows that can't be imported into either platform as-is. → **Decision 4.**

### 1.4 Categories — 21 distinct strings, 5 gaps

| Breadcrumb (last segment) | Rows | DigiMall | Alfa |
|---|---|---|---|
| Refrigerators | 539 | ✅ | ✅ |
| Washing machine | 225 | ✅ | ✅ |
| Microwaves | 167 | ✅ | ✅ |
| `… / AC` and `… / <Brand> AC 2026` | 517 | ✅ (inverter split, below) | ✅ 11505 |
| LED TV / Smart LED TV / `<Brand>` LED | 166 | ❌ **documented gap** | ✅ 11540 (165) / 11539 (7) |
| Deep Freezer | 88 | ✅ | ✅ |
| Water dispenser | 57 | ✅ | ✅ |
| Geysers | 19 | ⚠️ **no `geysers` key in `CATEGORY_DIGI_PATHS`** — only `heaters` | ✅ 11510 |
| Air cooler | 9 | ✅ | ✅ |
| Air purifier & humdifier | 4 | ✅ `air purifiers` | ❌ no Alfa leaf |
| Sound bars | 4 | ❌ | ❌ |
| UPS | 3 | ❌ | ❌ |
| Speakers | 2 | ❌ | ❌ |

**Net empty-`Category` impact:** DigiMall **253 rows** (166 LED TV + 46 inverter-silent AC + 19 geysers + 9 sound bar/speaker/UPS), Alfa **13 rows** (air purifier + sound bar + speaker + UPS).

Two sub-findings:
- The spec's caution that "the input sheet's `Categories` column won't say inverter" is **wrong for 427 rows** — the breadcrumb literally says `<Brand> AC 2026`. The inverter/non-inverter signal must still come from Title/Description text per spec, but the breadcrumb is not the blocker it was expected to be.
- **46 AC rows are genuinely silent on inverter status** → DigiMall `Category` blank + flag, Alfa still resolves to 11505. Exactly the split the spec describes.

### 1.5 Attributes — the exact-match rule costs real coverage

Measured signal-vs-match rates across the file:

| Attribute | Rows with a raw signal | Strict literal match | Match after collapsing whitespace only |
|---|---|---|---|
| `Attribute_Washing Machine Capacity` | 335 | 75 | **143** |
| `Attribute_Volt` | 711 | 86 | **213** |
| `Attribute_Capacity` | 825 | 498 | 505 |
| `Attribute_Display Size` | 167 | 165 | 165 |
| `Attribute_Warranty` | 454 | 349 | 349 |

The gap is caused entirely by spacing inside the token (`12 kg` vs list entry `12KG`; `220 V` vs `220V`). Collapsing **whitespace only** never rescues a genuine unit/punctuation difference, so the spec's own worked example (`16 Cu.Ft` must **not** match `16 Cu Ft`) still fails exactly as required. → **Decision 5.**

Other attribute findings:
- 795 rows contain the substring "inverter", but only 517 are actual air conditioners — attributes **must be scoped by resolved Product Type**, or a refrigerator's "Inverter Compressor" bullet leaks into `Attribute_INV/NON-INV`. Same trap for `Attribute_Fan Type`: a naive keyword scan "matches" 85 rows although the sheet contains **zero fan products**; correctly scoped, it should be empty everywhere.
- Negation trap: `Homage HWD-49331P Water Dispenser **Without** Refrigerator Cabinet` must map to `Without Refrigerator`, not `With refrigerator`. The spec's alias table lists `"refrigerator cabinet" → "With refrigerator"` — a substring match would produce the **opposite** of the truth for real rows in this file. Negations must be tested first (same discipline as the `non-inverter`-before-`inverter` rule).

### 1.6 Weight, warranty, prices, hygiene

- **Weight:** only **164 rows** carry a weight value; **1,636 rows** would ship an empty `Variant Weight` + flag.
- **Warranty:** 404 rows state a warranty; 1,396 are silent. Of the silent rows, **712** are eligible for a §12 fallback table (e.g. Dawlance/Refrigerator 221, Haier/Refrigerator 115, Dawlance/Washing Machine 95). The other 684 (notably all 166 LED TVs) have no table coverage. → **Decision 2.**
- **Prices:** every single row has `Original = Sell + 100` exactly. **Zero inversions**, so the §9 safety branch never fires — it stays implemented and unit-tested with synthetic data.
- **Text hygiene:** descriptions contain raw newlines (must be parsed with a real CSV parser — confirmed working), 359 contain `&` as literal text (e.g. `Cooling & Heating`), 51 contain `"` characters, 3 titles contain non-ASCII. Zero HTML tags in the source. Output HTML must escape `&` so `Cooling & Heating` doesn't leak into the CSV as a malformed entity.
- **Intro line:** all 1,800 descriptions open with `The <multi-word model> is a <type> …` — the `^The \S+ is an?` pattern needs to be `^The .+? is an?`.

---

## 2. Architecture

Exactly the module layout of spec §13 — no extra modules — plus a small `textutils.py` for shared string helpers (slugify, whitespace collapse, HTML escape, label casing).

```
kiachahiye_bulk_csv/
├── main.py                 # entrypoint + CLI + all output-path/filename constants + progress/summary
├── models.py               # InputRow, ResolvedBrand, ResolvedCategory, SpecRow,
│                           #   DescriptionBundle, ProductRecord,
│                           #   DigiOutputRow, AlfaOutputRow, QCFlag
├── textutils.py            # NEW (helpers only, no business rules)
├── brands.py               # §3   BRANDS_DIGI / BRANDS_ALFA / BRAND_ALIASES / resolve_brand()
├── categories.py           # §4+§5 CATEGORY_DIGI_PATHS / CATEGORY_ALFA_IDS / PRODUCT_TYPE_MAP
├── title_builder.py        # §6
├── sku_handle.py           # §7
├── description_builder.py  # §8   the unified classifier + HTML + tags + SEO + Short Description
├── pricing.py              # §9
├── warranty.py             # §10 + §12
├── attributes.py           # §11  DigiMall only — never imported by the Alfa path
├── writers.py              # §2   the two projections + both CSVs, the only place column order lives
├── qc_report.py            # flag collection + combined report + per-platform counters
├── tests/                  # 7 test modules (§13 list + test_writers.py)
├── data/input/             # a copy of the source sheet (pipeline is self-contained)
├── data/output/digi/digimall_bulk_import.csv
├── data/output/alfa/alfa_bulk_import.csv
└── README.md
```

The "derive once, project twice" rule is enforced by the type system, not by discipline: shared facts exist **only** as fields on `ProductRecord`; `DigiOutputRow` and `AlfaOutputRow` are the only two classes that can be written to CSV, and each is produced by a single function that reads a `ProductRecord`. There is no code path that can produce an Alfa row without a `ProductRecord`, so the two files cannot drift.

---

## 3. Implementation plan, section by section

| Spec | Module | What gets built |
|---|---|---|
| §1 input | `main.py` | CSV **and** `.xlsx` reader (openpyxl); real CSV parser so multi-line descriptions stay one field; discovers the 8 columns case-insensitively; ignores the input `Vendor` column entirely. Pre-pass builds the two caches: `Categories` string → `ResolvedCategory`, `Brand` string → `ResolvedBrand`, each resolved for **both** platforms in one call. |
| §2 output | `writers.py` | Two literal header tuples (66 / 28 columns) as module constants; `build_digi_row(record)` and `build_alfa_row(record)`; `csv.writer(..., quoting=QUOTE_ALL)`; HTML fields collapsed to one line; `VENDOR_DIGI` / `VENDOR_ALFA` as two separate constants with a unit test asserting they differ and are never swapped. |
| §3 brands | `brands.py` | Both dicts verbatim + explicit `BRAND_ALIASES` (`superasia`→`super asia` included, since 45 real rows need it) + `resolve_brand()` returning `ResolvedBrand(digi_id, alfa_id)`. No fuzzy matching anywhere. |
| §4 categories | `categories.py` | Both trees verbatim; `resolve_category()` walks breadcrumb segments most-specific-first with substring containment; **AC special case** reads inverter signals from Title+Description and leaves DigiMall blank + flagged when silently ambiguous (46 rows); **LED TV special case** — DigiMall always blank + the documented-gap flag, Alfa 11540 when a smart signal is present else 11539. Returns the dictionary's literal value, never a reconstructed path. |
| §5 product type | `categories.py` | `PRODUCT_TYPE_MAP` verbatim. Every real category resolves, so `Product Type` is never blank. The `"geysers" → "Geyser"` entry exists in the map, so the DigiMall *Category* gap (Decision 4) does not block `Product Type`. |
| §6 title | `title_builder.py` | One formula with optional slots. Step A rebuild when a confident model exists (1,508 rows), Step B validate-and-fix otherwise (292 rows) + the specified flag. Capacity regex with whole-number decimal dropping; colour via the §9 recognition list; Series/Feature slot filled only from source-backed tokens (explicit series list + `X Series` pattern); Inverter slot only when the source states it **and** the category has the concept. Guard: no empty brackets, no double spaces, no trailing hyphen, ≤90 chars. → **Decision 3.** |
| §7 sku/handle | `sku_handle.py` | The 4-step hierarchy (paren-at-end → paren-anywhere → `Model:`/TAB line → alphanumeric token), with the ≥1-digit guard that rejects `(Cool Only)` and innermost-group handling for the 8 double-paren rows. `KIA-` prefix, whitespace-stripped; Barcode = Bin = SKU; Handle = `model + product type` slug ≤65 chars, globally unique across the run. Colour-stripping applies to the SKU only, never to the Title. → **Decision 1.** |
| §8 description | `description_builder.py` | The unified 4-mode classifier described in §1.1; always emits Brand + Model rows first; `Type` row only when the source supplies one; every warranty part as its own bolded final row; the exact HTML table template from §8; Tags (5–8, deduped, model+colour combos); SEO Title with a deterministic trim/pad ladder into 65–90 chars; SEO Description built to the recipe and then asserted into 151–155 chars; Short Description (3 bullets, or 1–2 with a flag, **DigiMall-only output**). |
| §9 pricing | `pricing.py` | Comma-stripping int parse, inversion flag (never fires on this data), quantity default 20 + flag on all 1,800 rows. |
| §10 + §12 warranty | `warranty.py` | Stated-warranty parsing (compressor/motor/panel/PCB parts kept separate), headline-duration split for `Attribute_Warranty`, and the Dawlance/Haier fallback tables behind an explicit `ProductType → table key` map. → **Decision 2.** |
| §11 attributes | `attributes.py` | All 36 lists verbatim + alias dicts for the appliance-relevant set; **category-scoped** so a refrigerator's "Inverter" bullet can't populate `Attribute_INV/NON-INV`; negation-first alias resolution; numeric attributes extracted by regex then compared for equality (per Decision 5); every unmatched-but-signalled cell recorded with its raw text for the QC report. `Attribute_Product Type` restricted to Deep Freezer / Refrigerator / Phones. |
| §13 progress | `main.py` | Progress line every 100 rows; final summary with the seven counters split per platform (`DigiMall Category empty: N` / `Alfa Category empty: N`, never merged). |
| §14 tests | `tests/` | Both golden cases reproduced **exactly**, for the Digi row *and* the Alfa row. |
| §15 QC | `qc_report.py` | Per-row report CSV: row number, title, **affected file(s)** named explicitly, flag type, details; plus a summary block with per-platform clean/flagged counts. |

### 3.1 Cross-cutting decisions I will implement without asking

1. **Two prompt conflicts resolved in favour of the acceptance tests** (acceptance tests are the spec's own stated ground truth, "fix the code, don't adjust the expected values"):
   - TC2 requires **no warranty row** for a Dawlance LED TV even though §12's `DAWLANCE_WARRANTY` contains an `"led"` key. I treat §12's table keys as matching **resolved Product Type** strings only; `"led"` ≠ `"LED TV"`, so no fallback fires. (Ties into Decision 2.)
   - TC1 requires `Attribute_Volt` to be **empty** for `220-240V` — a range is never rounded into a single value. Implemented as a hard rule.
2. **Source fidelity beats prettification:** the pipeline never rewrites the source's own spec values; it only maps them to catalogue enums. `Andriod TV` (Alfa's own misspelling) is preserved as the catalogue value.
3. **Never drop a row.** All 1,800 rows appear in both files. Duplicates are disambiguated, not deleted.
4. **All 36 attribute columns exist in the DigiMall file** (fixed schema) and are simply empty where nothing matched.
5. **`Attribute_Air Cooler Category`** gets a small explicit alias dict (`dc` → `Air Cooler DC`; `ac-dc`/`inverter` → `Air Cooler AC-DC`), and stays empty + flagged for the 9 air-cooler rows whose text states neither.
6. **Encoding:** output written UTF-8 with BOM (`utf-8-sig`) so the files open cleanly in Excel for eyeballing, `QUOTE_ALL` as specified. Configurable constant.

---

## 4. Decisions — ANSWERED (locked)

| # | Decision | Your ruling |
|---|---|---|
| 1 | Duplicate `Variant SKU` | **No duplicate SKUs, ever.** Scheme: `KIA-<model>-<variant>`. The `<variant>` part is built from the dimensions that actually distinguish variants in your file — capacity, colour, taps (2/3), T3/non-T3 generation, series — in a fixed order. A variant suffix is added only when the bare `KIA-<model>` is not unique across the run; a final `-2`, `-3` fallback guarantees uniqueness in the worst case and is always flagged. This preserves Test Case 1's exact `KIA-WD-1051HC`. |
| 2 | Warranty fallback tables | **You will supply the complete warranty reference.** Ship with §12's Dawlance + Haier tables as-is and clearly-marked empty slots for every other brand → blank warranty + flag until you send the data. |
| 3 | Title strategy | **Rebuild-first, but produce a 20-row before/after sample for your review before the full run.** |
| 4 | Unresolvable brand/category IDs | **Leave the cell empty, never invent.** The terminal summary must explicitly list which brand and which category was not found, and in which platform's table. All lookup data lives in one clearly-banner-marked "edit here" block per module, referenced by file + constant name in the summary so it is obvious what to edit next time. |
| 5 | Attribute matching | **Collapse whitespace only** inside the extracted token. Never rewrite units or punctuation. |

---

## 5. Test plan

`pytest`, run before the real file is touched.

**Acceptance (`test_acceptance_examples.py`)** — the gate:
- TC1 Dawlance WD-1051 HC: asserts the **DigiMall row** field-by-field (Vendor `KiaChahiye PVT LTD`, Brands `3755`, Category `11639_11643_11661_11669`, SKU `KIA-WD-1051HC`, Handle `wd-1051hc-water-dispenser`, price 36375/36475, `Attribute_Water Dispenser Type` = `With refrigerator`, `Attribute_Warranty` = `3 Years`, **`Attribute_Volt` empty**) and the **Alfa row** (Vendor `Kia Chahiye Pvt Ltd`, Brands `3673`, Category `11509`, no Short Description, no attributes).
- TC2 Dawlance LED TV: asserts the Digi row (Title kept verbatim, fallback SKU `KIA-DAWLANCE-KORE-32`, Handle `dawlance-kore-32-led-tv`, **Category empty**, `Attribute_LED Type` = `Google TV` by title-over-body tie-break, `Attribute_Warranty` empty) and the Alfa row (Category `11540`, Brands `3673`).
- Both tests build the row by running the real pipeline entrypoint on a two-row input file written to `tmp_path`, then read the two produced CSVs back — so the tests exercise parsing, projection, and file writing, not just the rule functions.

**Schema (`test_output_schema.py`):** DigiMall header is exactly the 66 §2A columns in order; Alfa is exactly the 28 §2B columns in order; neither file contains any column belonging to the other schema; no `_Digi`/`_Alfa`-suffixed name anywhere; Alfa has zero `Attribute_*` and no `Short Description`.

**Unit suites:** `test_brands.py` (aliases, Superasia spacing, one-sided presence, no fuzzy match), `test_categories.py` (all 21 real breadcrumbs, AC silent→blank, LED TV gap, Alfa leaf shapes, never a joined path in Alfa), `test_attributes.py` (negation-first, category scoping, the `16 Cu.Ft` non-match, the range non-match, per-attribute fill counts), `test_description_builder.py` (all 4 shapes incl. the TAB variant, thin guard, SEO length assertion, tag dedupe), plus `test_writers.py` (Vendor constants differ, quantity default + flag, byte-level CSV checks for single-line HTML fields).

**Whole-file smoke test:** run over all 1,800 rows, assert both files have exactly 1,801 lines, 1,800 data rows, zero raw newlines inside any field, and print the per-platform summary.

---

## 6. Run, review and verification

1. Copy the source sheet to `kiachahiye_bulk_csv/data/input/`.
2. `pytest -q` — must be fully green, acceptance tests included.
3. `mypy --strict .` — must be clean.
4. Full run on all 1,800 rows → both CSVs + `data/output/qc_report.csv`.
5. I then report, with real numbers: rows written per file, DigiMall/Alfa empty `Category` and `Brands` counts, fallback-SKU count, handle-dedupe count, weight-blank count, per-attribute fill rates, and the clean-vs-flagged split per platform.
6. I'll hand you a **sample of 20 resolved rows** (10 Digi + 10 Alfa, spanning the shapes: a label-bullet refrigerator, a TAB-block freezer, a single-line TV, an inverter-silent AC) so you can eyeball the output before anyone uploads it to a platform.

Nothing gets uploaded anywhere, and no row is ever silently fabricated — every judgement call lands in the QC report.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| A rule that fills an attribute wrongly is worse than one that leaves it empty | Category scoping + negation-first aliases + conservative fallback; every miss is reported with its raw text |
| 1,636 rows with an empty `Variant Weight` | Flagged per row; if you give me a per-category default weight table I'll wire it in, otherwise blank is honest |
| Title rebuild may read worse than the source titles for some rows | Decision 3's `validate_only` switch + pre-run sample before the full rebuild |
| 292 fallback SKUs are title-derived, not real codes | Every one flagged with the instruction to verify before upload (as §7 requires) |
| Duplicate SKUs across variants | Decision 1 |
| New phrasings in future sheets | Alias tables are all in one place per module; README documents how to extend each |
