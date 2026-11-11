# Implementation Plan: Vendor Title Formula Upgrade (`vip_pipe` for Kiachahiye & `standard` for Ajmer)

## Overview

Upgrade the multi-store title generation engine in [`kiachahiye_bulk_csv/`](file:///D:/Dynamic_CSV_Generator/kiachahiye_bulk_csv) so each store uses its designated marketplace-optimized formula:
- **Kiachahiye (`kiachahiye`)**: Official Brand VIP Pipe Formula (`"vip_pipe"`):
  `[Brand] [Capacity / Taps] [Series / Popular Identity] [Inverter / Non-Inverter] [Subtype] [Product Type] ([Color]) | [USP 1] | [USP 2] | [USP 3] | [Model Code] | [Main Warranty]`
- **Ajmer Electronics (`ajmer`)**: Switched from `"brand_first_extended"` to classic Kiachahiye `"standard"` formula:
  `[Brand] [Capacity / Taps] [Color] [Inverter / Non-Inverter] [Subtype] [Product Type] - [Model / Identity] [Series / Feature] - [Main Warranty]`

This upgrade strictly obeys all marketplace contracts:
1. DigiMall closed-list attribute matching.
2. Google Search Central 65–90 char SEO Title window (without pipe/bracket shedding failures).
3. Hard 255-character title limit (`TITLE_MAX`) with zero model/warranty truncation.
4. [`audit.py`](file:///D:/Dynamic_CSV_Generator/kiachahiye_bulk_csv/audit.py) 12-section zero-invention quality gates.

---

## Architecture Decisions & Semantic Rules

### 1. Position 3 (`[Series / Popular Identity]`) Mechanics in `vip_pipe`
Position 3 (immediately after `[Capacity / Taps]`) is strictly reserved for the **Series / Line Name** or codeless **Popular Identity**:
- **Scenario A (Both Series & Technical Model Code exist)**:
  - Series / Line Name (`Eco`, `Duzin`, `Avante+`, `Advanco`, `Pearl`, `Acce`, `K85`) sits in Position 3.
  - Technical model code (`MSAG2B-12HRDN1-QC0`, `HPU-24HDZ`, `9178LF`, `DW-6100`) sits cleanly in its own pipe segment after USPs: `| [Model Code] | [Main Warranty]`.
- **Scenario B (Codeless Products / Popular Identity only)**:
  - When no separate technical part number exists, the popular market identity (`Aura 15`, `Frost 30`, `Twister 1150`) sits in Position 3.
  - It is **never** duplicated in the rear pipe segment (`back_model` is empty).
- **Scenario C (Technical Model Code only, No Series)**:
  - Position 3 is skipped. The technical model code sits in `| [Model Code] |` after USPs.

### 2. Segment 1 Tokens Order
Single-space joined:
1. `[Brand]`
2. `[Capacity / Taps]`
3. `[Series / Popular Identity]` (Position 3)
4. `[Inverter / Non-Inverter]` (Preserved verbatim: `DC Inverter`, `Inverter`, `Non-Inverter`)
5. `[Subtype]` (e.g. `Wall Mounted Split`, `Double Door Glass Door`, `Top Load Fully Automatic`)
6. `[Product Type]` (e.g. `Air Conditioner`, `Refrigerator`, `Washing Machine`)
7. `([Color])` (In parentheses right after product type, e.g. `(White)`, `(Ruby Red)`. Omitted for `OMIT_TITLE_COLOR_CATEGORIES` like LED TV or when color is absent).

### 3. Zero-Invention Dynamic USPs (`| [USP 1] | [USP 2] | [USP 3] |`)
- Extracted strictly from row's own source text via a 3-rung extractor in [`title_builder.py`](file:///D:/Dynamic_CSV_Generator/kiachahiye_bulk_csv/title_builder.py):
  1. Rung 1: Description key feature bullets (`Highlights:` / `Features:`).
  2. Rung 2: High-signal spec labels (`Special Feature`, `Cooling Technology`, `Self-Cleaning`).
  3. Rung 3: Verbatim high-converting appliance pattern scan (`4D Airflow`, `Gold Fin`, `Low Voltage Operation`, `Vitamin Fresh`, etc.).
- Word-deduped against all tokens already printed in Segment 1.
- **Budget-checked**: Only appended if `len(assembled_title) <= 255`, guaranteeing `| [Model Code] | [Main Warranty]` are never cut off.

### 4. Search-Engine & Downstream Protection
- [`TitleResult.seo_base_title`](file:///D:/Dynamic_CSV_Generator/kiachahiye_bulk_csv/title_builder.py) preserves the clean, hyphen-separated standard base title so `build_seo_title()` retains 100% Google compatibility in the 65–90 char window.
- Shedding order in [`main.py`](file:///D:/Dynamic_CSV_Generator/kiachahiye_bulk_csv/main.py) drops `- [Warranty]` first, then `[Color]`, then secondary subtype prefix, protecting 100% of high-volume buyer search keywords (`Capacity`, `Series`, `Inverter`, `Model`).

---

## Dependency Graph

```
Task 1: title_builder.py (extract_usps + TitleResult fields)
    │
    ├── Task 2: title_builder.py (vip_pipe formula in _apply_formula & build_title)
    │       │
    │       ├── Task 3: main.py + description_builder.py (seo_base_title & shedding order)
    │       │       │
    │       │       └── Task 4: vendor_config.py (KIACHAHIYE="vip_pipe", AJMER="standard")
    │       │               │
    │       │               └── Task 5: tests/test_title_builder.py + test_vendor_config.py
    │       │                       │
    │       │                       └── Task 6: End-to-end multi-vendor audit & run verification
```

---

## Task List

### Phase 1: Foundation — USP Extractor & `vip_pipe` Formula

## Task 1: Add `usp_tokens` & `seo_base_title` to `TitleResult` and implement `extract_usps` in `title_builder.py`
**Description:** Implement `extract_usps(source_title, source_description, product_type, said_already, max_usps=3)` using the 3-rung source-backed extraction logic (bullets, spec labels, verbatim patterns). Extend `TitleResult` with `usp_tokens: tuple[str, ...] = ()` and `seo_base_title: str = ""`.

**Acceptance criteria:**
- [ ] Returns up to 3 non-redundant, verbatim phrases found in source title/description.
- [ ] Returns empty tuple `()` when source text has no features (never invents words).
- [ ] Deduplicates words against `said_already`.

**Verification:**
- [ ] `pytest tests/test_title_builder.py -k test_extract_usps`
- [ ] `ruff check title_builder.py`

**Dependencies:** None
**Files touched:** `kiachahiye_bulk_csv/title_builder.py`
**Estimated scope:** Small (1 file)

---

## Task 2: Implement `"vip_pipe"` Formula & Slot Wiring in `title_builder.py`
**Description:** Wire `front_identity`, `back_model`, and `usps` in `build_title()`. Implement `"vip_pipe"` in `_apply_formula()`. Update `_trim_to_limit()` to strip trailing `" ,-/|"`. Construct `seo_base_title` for downstream SEO Title generation.

**Acceptance criteria:**
- [ ] Row with Series + Model Code formats Position 3 as Series, Model Code as `| [Model Code] |`.
- [ ] Codeless row with Popular Identity formats Position 3 as Popular Identity, empty `back_model`.
- [ ] Row with Model Code only skips Position 3, puts Model Code after USPs.
- [ ] Color is bracketed `([Color])` at end of Segment 1 (omitted for LED TV or when empty).
- [ ] Output respects `TITLE_MAX` (255 chars) without truncating model code or warranty.

**Verification:**
- [ ] `pytest tests/test_title_builder.py`
- [ ] `ruff check title_builder.py`

**Dependencies:** Task 1
**Files touched:** `kiachahiye_bulk_csv/title_builder.py`
**Estimated scope:** Small (1 file)

---

### Checkpoint 1: Foundation
- [ ] All existing `tests/test_title_builder.py` pass.
- [ ] New unit tests verifying Scenarios A, B, and C pass.

---

### Phase 2: Pipeline Wiring & Vendor Configuration

## Task 3: Wire `seo_base_title` & Search-First Token Shedding in `main.py`
**Description:** Pass `title_res.seo_base_title` to `build_description_bundle()` in `main.py`. Update shedding logic so warranty is shed first when title exceeds 90 chars, preserving Brand, Capacity, Series, Inverter, Subtype, and Model.

**Acceptance criteria:**
- [ ] `SEO Title` stays within 65–90 characters.
- [ ] High-volume search keywords (`Capacity`, `Series`, `Inverter`, `Model`) survive Google SEO title trimming.

**Verification:**
- [ ] `pytest tests/test_description_builder.py tests/test_main.py`
- [ ] `ruff check main.py`

**Dependencies:** Task 2
**Files touched:** `kiachahiye_bulk_csv/main.py`
**Estimated scope:** Small (1 file)

---

## Task 4: Configure `KIACHAHIYE` to `"vip_pipe"` and `AJMER` to `"standard"` in `vendor_config.py`
**Description:** Update `KIACHAHIYE.title_formula = "vip_pipe"` and `AJMER.title_formula = "standard"` in `vendor_config.py`.

**Acceptance criteria:**
- [ ] `KIACHAHIYE.title_formula == "vip_pipe"`
- [ ] `AJMER.title_formula == "standard"`

**Verification:**
- [ ] `pytest tests/test_vendor_config.py`
- [ ] `ruff check vendor_config.py`

**Dependencies:** Task 3
**Files touched:** `kiachahiye_bulk_csv/vendor_config.py`
**Estimated scope:** XS (1 file)

---

### Checkpoint 2: Core Pipeline Features
- [ ] Full pytest suite passes (`pytest -q`).
- [ ] Linter clean (`ruff check .`).

---

### Phase 3: Comprehensive Testing & End-to-End Audit

## Task 5: Add Multi-Vendor Title & Regression Unit Tests
**Description:** Add dedicated tests in `tests/test_title_builder.py` and `tests/test_vendor_config.py` verifying both formulas across categories (AC, Refrigerator, Washing Machine, LED TV, Microwave, Water Dispenser).

**Acceptance criteria:**
- [ ] Covers all 3 scenarios (Series+Model, Popular Identity, Model only).
- [ ] Covers bracketed colors and LED TV color omission.
- [ ] Covers USP extraction and budget protection.

**Verification:**
- [ ] `pytest tests/ -q`
- [ ] `mypy .`

**Dependencies:** Task 4
**Files touched:** `kiachahiye_bulk_csv/tests/test_title_builder.py`, `kiachahiye_bulk_csv/tests/test_vendor_config.py`
**Estimated scope:** Small (2 files)

---

## Task 6: Run Full End-to-End Pipeline & Audit Gate on Real Data
**Description:** Run `main.py` and `audit.py` on real datasets (`midea_eco_products.csv`, `Products.csv`) for both `kiachahiye` and `ajmer`.

**Acceptance criteria:**
- [ ] `audit.py` passes with 0 failures for `kiachahiye` (`digi` and `alfa`).
- [ ] `audit.py` passes with 0 failures for `ajmer` (`alfa`).
- [ ] Generated CSV outputs verified for correct title structure.

**Verification:**
- [ ] `python main.py --vendor kiachahiye --input data/input/midea_eco_products.csv ... && python audit.py ...`
- [ ] `python main.py --vendor ajmer --platform alfa --input data/input/midea_eco_products.csv ... && python audit.py ...`

**Dependencies:** Task 5
**Files touched:** Generated CSV outputs under `data/output/`
**Estimated scope:** Small (CLI runs)

---

### Checkpoint 3: Production Ready
- [ ] 100% tests pass.
- [ ] Zero audit failures across all 12 sections.
- [ ] Clean git status ready for commit.
