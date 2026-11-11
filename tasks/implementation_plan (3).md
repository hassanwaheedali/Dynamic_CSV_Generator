# MASTER ARCHITECTURE RESEARCH — CSV GENERATOR
### Flagship Repository Forensics, Universal Configuration Architecture, Multi-Platform Extensibility, Production Engineering & Future SaaS Readiness

---

## Table of Contents
- [Section A — Executive Summary](#section-a--executive-summary)
- [Section B — Repository Inspection and Baseline Evidence](#section-b--repository-inspection-and-baseline-evidence)
- [Section C — Current Architecture Forensics](#section-c--current-architecture-forensics)
- [Section D — Complete Requirements Matrix](#section-d--complete-requirements-matrix)
- [Section E — Architecture Alternatives and Comparative Evaluation](#section-e--architecture-alternatives-and-comparative-evaluation)
- [Section F — Recommended Target Architecture](#section-f--recommended-target-architecture)
- [Section G — Universal Configuration Architecture](#section-g--universal-configuration-architecture)
- [Section H — Title Formula and Title Template Architecture](#section-h--title-formula-and-title-template-architecture)
- [Section I — Description Template Architecture](#section-i--description-template-architecture)
- [Section J — Warranty, Category, Brand, Attribute, Tag, Price and Fallback Configuration](#section-j--warranty-category-brand-attribute-tag-price-and-fallback-configuration)
- [Section K — Future Platform Expansion Study (Shopify, WooCommerce and Beyond)](#section-k--future-platform-expansion-study-shopify-woocommerce-and-beyond)
- [Section L — Multi-Format Input and Output Architecture](#section-l--multi-format-input-and-output-architecture)
- [Section M — Validation, Audit, Quality Gates and Observability](#section-m--validation-audit-quality-gates-and-observability)
- [Section N — Testing Architecture and Verification Strategy](#section-n--testing-architecture-and-verification-strategy)
- [Section O — SaaS and Commercialization Readiness](#section-o--saas-and-commercialization-readiness)
- [Section P — Detailed Design of the Recommended Architecture](#section-p--detailed-design-of-the-recommended-architecture)
- [Section Q — Configuration File Examples](#section-q--configuration-file-examples)
- [Section R — Concrete Developer Workflows (All 22 Scenarios)](#section-r--concrete-developer-workflows-all-22-scenarios)
- [Section S — Architecture Decision Register (ADR)](#section-s--architecture-decision-register-adr)
- [Section T — Migration Roadmap](#section-t--migration-roadmap)
- [Section U — Risk Register and Failure Modes](#section-u--risk-register-and-failure-modes)
- [Section V — What Not To Build (Anti-Overengineering Guardrails)](#section-v--what-not-to-build-anti-overengineering-guardrails)
- [Section W — Final Consolidated Recommendation](#section-w--final-consolidated-recommendation)
- [Section X — Comprehensive Traceability Appendix (File & Line Index)](#section-x--comprehensive-traceability-appendix-file--line-index)
- [Section Y — Self-Critique and Completeness Verification Against Prompt Contract](#section-y--self-critique-and-completeness-verification-against-prompt-contract)
- [Section Z — Final Repository Integrity Confirmation](#section-z--final-repository-integrity-confirmation)

---

## Section A — Executive Summary

### 1. Current State of the Repository
- **Repository evidence**: The application resides in `/kiachahiye_bulk_csv/` (**19 production Python modules totaling 10,636 lines of code**, plus **22 pytest modules containing 599 `def test_*` functions** across 10,852 lines of test code). It ingests vendor product sheets (`.csv` via `csv.DictReader` or `.xlsx` via `openpyxl` in `main.py:150-221`), runs a whole-sheet series-name voting pre-pass (`series_corpus.py:1-1479`), resolves each row in two passes into a canonical `ProductRecord` (`models.py:100-150`, `main.py:261-743`), and projects those records into marketplace bulk-import CSVs (`writers.py:1-245`) accompanied by a QC report (`qc_report.py`), an independent upload gate (`audit.py`), and an advisory thin-description worklist (`thin_report.py`).
- **Repository evidence (Completed Recent Milestones)**:
  1. **Multi-store configuration registry**: `vendor_config.py` defines `VendorConfig` (`lines 51-75`), `PlatformConfig` (`lines 37-47`), and `VENDOR_REGISTRY = {"kiachahiye": KIACHAHIYE, "ajmer": AJMER}` (`lines 373-376`).
  2. **Per-`(vendor, platform)` Description Template Registry & Isolation**: `description_builder.py` defines `DescriptionTemplate` (`lines 822-867`) and `DESCRIPTION_TEMPLATES` (`lines 893-896`) with two registered shapes: `"spec_table"` (`SPEC_TABLE`) and `"kiachahiye_alfa_card"` (`KIACHAHIYE_ALFA_CARD`). `ProductRecord.description` stores `spec_rows: list[SpecRow]` (`models.py:77-97`) rather than pre-rendered HTML, and `writers.py:_description_cell` (`lines 142-151`) renders a shallow copy `list(record.description.spec_rows)` at projection time per `(vendor, platform)` cell.
  3. **Startup Conformance Harness**: `description_builder.py:919-1012` (`template_problems`) and `vendor_config.py:418-439` (`validate_vendor_cfg`) validate registered description templates at startup before any output file is written.
  4. **DRY Dynamic Test Suite**: `tests/test_vendor_config.py` (`589 lines`) and `tests/test_description_isolation.py` (`327 lines`) iterate dynamically over `VENDOR_REGISTRY` and `DESCRIPTION_TEMPLATES`.

### 2. Core Architectural Diagnosis ("Split-Brain Migration")
- **Repository evidence**: Despite the progress in `vendor_config.py` and `description_builder.py`, the repository is currently in a **half-migrated, split-brain state** across five critical dimensions:
  1. **Legacy Fallback Tables Coexist with `vendor_config.py`**: When `--vendor` is omitted (`vendor_cfg=None`), the pipeline falls back to hardcoded module globals in `config.py`, `brands.py`, and `categories.py`. Worse, `config.py:38-39` currently sets `VENDOR_DIGI = "KiaChahiye PVT LTD"` alongside `VENDOR_ALFA = "Ajmer Electronics"`—mixing two different legal entities in a single default run.
  2. **Unwired `VendorConfig` Fields (Silent Dead Knobs)**:
     - `VendorConfig.omit_title_color_categories` (`vendor_config.py:70-72`) is defined on every store config, **but `main.py:376` (`build_title(...)`) never passes it**, and `title_builder.py:2012` ignores `vendor_cfg` and reads `getattr(config, "OMIT_TITLE_COLOR_CATEGORIES", ...)` directly.
     - `VendorConfig.apply_tv_warranty_table` (`vendor_config.py:74`) is defined on every store config, **but `main.py:427` (`resolve_warranty(...)`) and `title_builder.py:2017` (`resolve_main_warranty(...)`) never pass `vendor_cfg`**, and `warranty.py:132` always reads `getattr(config, "APPLY_TV_WARRANTY_TABLE", ...)`.
  3. **Global Un-Parameterized Caches in `series_corpus.py`**: `series_corpus.py:161-190` caches `category_vocabulary()`, `brand_names()`, and `brand_words()` with `@lru_cache(maxsize=1)` reading module-level tables from `categories.py` and `brands.py`, and `series_corpus.py:566` calls `resolve_brand(brand, "")` without `vendor_cfg`. New brands or category keys added only to a `VendorConfig` in `vendor_config.py` are invisible to the corpus voter.
  4. **Asymmetry Between Title Formulas and Description Templates**: Description templates are resolved per `(vendor, platform)` cell at projection time (`PlatformConfig.description_template`), supporting all four sharing/isolation scenarios (Scenarios A–D). In contrast, `title_formula` lives only on `VendorConfig` (`vendor_config.py:64`) and is evaluated once during `resolve_row` (`main.py:376`) into a single `ProductRecord.title: str`. Consequently, **Scenario C (platform-specific title formula) and Scenario D (per-`(vendor, platform)` title formula) are impossible in the current data model**.
  5. **Hardcoded Dual-Platform Schema & Regex-Bound Audit Gate**:
     - `models.py`, `vendor_config.py`, `main.py`, `writers.py`, `qc_report.py`, `audit.py`, and `run_ui.py` hardcode the two-platform universe (`digi` and `alfa`).
     - `audit.py` (`lines 405-417, 492-502`) and `thin_report.py` (`line 36`) inspect rendered HTML using hardcoded `<table>` / `<tr><td` / `<th ` regexes instead of calling the cell's `DescriptionTemplate.extract()`, causing `audit.py:409` and `thin_report.py:36` to **fail to match any row of `KIACHAHIYE_ALFA_CARD`** (`<tr style="background-color:...">`).
     - Under `--platform both`, `audit.py:235` sets `primary = files[0]` (DigiMall) and runs Title (`line 554`), Weight (`line 584`), Colour (`line 642`), and Freezer (`line 673`) checks **only against `primary`**, bypassing Alfa for those checks.

### 3. Consolidated Architectural Recommendation
- **Architectural recommendation**: Adopt **Alternative 2 — Layered Hybrid Architecture (Python Core Engine + Hierarchical `ResolvedCellConfig` + Pluggable `PlatformAdapter` Protocol + Declarative Data Packs)**.
  - Keep the domain-heavy extraction algorithms (model extraction, capacity parsing, series corpus voting, warranty clause parsing, prose/bullet classification) in pure, strongly-typed Python modules.
  - Introduce a 4-level hierarchical configuration resolver (`EngineDefaults` → `PlatformDefinition` → `VendorDefinition` → `CellOverride[vendor, platform]`) that compiles into a frozen `ResolvedCellConfig` per `(vendor, platform)` cell at startup.
  - Keep `ProductRecord` (evolved to `CanonicalProductFacts`) strictly holding extracted domain tokens (`TitleSlots`) and `spec_rows`, moving **both** Title string composition and Description rendering to cell projection time via `ResolvedCellConfig`.
  - Replace hardcoded `build_digi_row` / `build_alfa_row` with a `PlatformAdapter` protocol (`project_all(records, cell_cfg) -> list[ProjectedRow]`) capable of emitting both `1:1` flat rows (DigiMall, Alfa, Daraz) and `1:N` multi-row parent/variant/image structures (Shopify, WooCommerce).
  - Make `audit.py` and `thin_report.py` fully cell-aware and template-aware by delegating HTML read-back to `cell_cfg.description_template.extract(html)` and running all row-level gates against every generated platform file.

---

## Section B — Repository Inspection and Baseline Evidence

### 1. Git Working Tree & Environment Status (Start of Investigation)
- **Repository evidence**: Executing `git status --short --branch` in `/app/applet` returns:
  ```text
  fatal: not a git repository (or any of the parent directories): .git
  ```
- **Explicit Disclosure**: The mounted workspace `/app/applet` is a clean snapshot of the repository working tree without the `.git/` directory attached. Historical commit context is therefore cross-verified against `/CHANGELOG.md`, `/PLAN.md`, `/README.md`, module docstrings, and inline task comments (`Task 2`, `Task 4`, `Task 7`, `Task 10` in `tests/`). Working-tree integrity at the start and end of this research run is verified via both `git status` and full filesystem tree enumeration (`find . -maxdepth 3`).

### 2. Complete Repository File Inventory

| Path | Lines | Role & Architectural Responsibility |
| :--- | ---: | :--- |
| `/README.md` | 630 | Operator & developer documentation, 5-step vendor onboarding guide, lookup priority rules. |
| `/PLAN.md` | 240 | Historical multi-vendor refactoring plan (`vendor_config.py`, `--vendor`, `title_formula`, DRY tests). |
| `/CHANGELOG.md` | 17 | Documents addition of `clean_descriptions.py` and `thin_report.py`. |
| `/kiachahiye_bulk_csv/OUTPUTS_GUIDE.md` | 125 | Roman Urdu operator guide explaining the 6 output files and per-cell description templates. |
| `/kiachahiye_bulk_csv/ruff.toml` | 72 | Ruff linter config (`py310`, line-length 120, explicit ignore rules including `PLC0415` for `series_corpus.py`). |
| `/kiachahiye_bulk_csv/run_pipeline.bat` | 68 | Windows batch launcher invoking `run_ui.py` with `PYTHONUTF8=1`. |
| `/kiachahiye_bulk_csv/config.py` | 144 | Legacy global settings (`VENDOR_DIGI`, `VENDOR_ALFA`, `SEO_TITLE_MIN/MAX`, `SEO_DESC_MIN/MAX`, `DEFAULT_VARIANT_QUANTITY`, `DEFAULT_PRODUCT_TYPE_COLORS`, `OMIT_TITLE_COLOR_CATEGORIES`, `APPLY_TV_WARRANTY_TABLE`, output paths). |
| `/kiachahiye_bulk_csv/vendor_config.py` | 452 | Multi-store configuration (`PlatformConfig`, `VendorConfig`, `KIACHAHIYE`, `AJMER`, `VENDOR_REGISTRY`, `validate_vendor_cfg`). |
| `/kiachahiye_bulk_csv/models.py` | 164 | Frozen/mutable dataclasses (`InputRow`, `BrandResolution`, `CategoryResolution`, `SpecRow`, `DescriptionBundle`, `ProductRecord`, `ProjectedRow`). |
| `/kiachahiye_bulk_csv/main.py` | 1,045 | CLI entry point, `.csv`/`.xlsx` reader, corpus pre-pass caller, 2-pass `resolve_row()` orchestrator, terminal summary printer. |
| `/kiachahiye_bulk_csv/writers.py` | 245 | `SHARED_PREFIX` (28 cols), `DIGI_HEADER` (66 cols), `ALFA_HEADER` (28 cols), `template_for_cell`, `build_digi_row`, `build_alfa_row`, `write_csv`. |
| `/kiachahiye_bulk_csv/title_builder.py` | 2,466 | Slot extraction (`subtype`, `inverter`, `series`, `usps`), 3 title formulas (`standard`, `brand_first_extended`, `vip_pipe`), `TITLE_FORMULAS` registry, length fitting (`<= 195`). |
| `/kiachahiye_bulk_csv/description_builder.py` | 1,650 | 4-branch description parser, `spec_rows` builder, `Short Description` 3-bullet builder, `Tags` (5–8), `SEO Title` (65–90), `SEO Description` (120–155), `DescriptionTemplate` registry (`spec_table`, `kiachahiye_alfa_card`), startup conformance harness (`template_problems`). |
| `/kiachahiye_bulk_csv/series_corpus.py` | 1,479 | Whole-sheet series-name learner: `normalize_shape`, slot word-claiming, residue extraction, brand-level `build_corpus` vote (`siblings` vs `brand-position`). |
| `/kiachahiye_bulk_csv/sku_handle.py` | 691 | 4-rung model extractor (`extract_model`), capacity parser + AC model-code tonnage tables (`resolve_capacity`), SKU/Handle builders, `UniqueRegistry` collision disambiguator. |
| `/kiachahiye_bulk_csv/warranty.py` | 535 | Source warranty clause parser, headline selector, `WARRANTY_TERMS` reference fallback, `resolve_warranty`, `resolve_main_warranty`. |
| `/kiachahiye_bulk_csv/warranty_terms.py` | 129 | `WARRANTY_TERMS` nested dict (`brand -> category_or_variant -> "Part: Duration"`). |
| `/kiachahiye_bulk_csv/brands.py` | 193 | Legacy `BRANDS_DIGI`, `BRANDS_ALFA`, `BRAND_ALIASES`, `BRAND_DISPLAY_MAP`, and `resolve_brand()`. |
| `/kiachahiye_bulk_csv/categories.py` | 442 | Legacy `CATEGORY_DIGI_PATHS`, `CATEGORY_ALFA_IDS`, `DIGI_SEGMENT_ALIASES`, `ALFA_SEGMENT_ALIASES`, `PRODUCT_TYPE_MAP`, `STOP_SEGMENTS`, `resolve_category()`, `resolve_product_type()`. |
| `/kiachahiye_bulk_csv/attributes.py` | 471 | DigiMall's 36 `Attribute_*` closed allowed-value tuples (`ALLOWED`), `SCOPE` by `Product Type`, `ALIASES`, and `build_attributes()`. |
| `/kiachahiye_bulk_csv/pricing.py` | 131 | `parse_price`, `resolve_prices` (+10% magnitude-rounded compare-at derivation on missing/inverted original price), `resolve_quantity`. |
| `/kiachahiye_bulk_csv/textutils.py` | 599 | HTML stripping, mojibake cleanup, weight column/line parser, colour vocabulary (`BASE_COLORS`, `COLOR_MODIFIERS`), `find_full_color`, `colour_disagreements`. |
| `/kiachahiye_bulk_csv/qc_report.py` | 195 | `QCFlag`, `QCFlagCollector`, `SEVERITY_BY_CATEGORY`, platform-scoped `write_csv`, `attribute_gaps`. |
| `/kiachahiye_bulk_csv/audit.py` | 743 | Post-generation verification gate: checks headers, row counts, vendor literals, categories, brands, SKUs/handles, prices, descriptions, SEO ceilings, attributes, titles, weights, colours, and writes `row_check.csv`. |
| `/kiachahiye_bulk_csv/thin_report.py` | 232 | Generates `thin_descriptions.csv` grading source descriptions (`high`/`medium`) by char count, line count, spec rows, and short bullets. |
| `/kiachahiye_bulk_csv/clean_descriptions.py` | 464 | Standalone preprocessor rewriting messy `Description` cells into intro + `Label: Value` + `• Bullet` shape. |
| `/kiachahiye_bulk_csv/run_ui.py` | 747 | Interactive ANSI terminal menu (store, sheet, platform selection) + orchestrator running `main.py` → `audit.py` → `thin_report.py`. |
| `/kiachahiye_bulk_csv/tests/test_*.py` | 10,852 | 22 pytest files (599 test functions) + `conftest.py` (119 lines) + `fixtures/` & `data/input/` sheets (`Step 1.csv`, `test2/TWO_PRODUCTS.csv`, `test100/`). |

---

## Section C — Current Architecture Forensics

### 1. End-to-End Execution Pipeline
- **Repository evidence**:
  ```text
  [Input Sheet (.csv / .xlsx)]
         │
         ▼  main.read_input() (main.py:150-221)
  [list[InputRow]]  (7 required cols; HTML stripped keeping lines; optional Weight/Unit cols detected)
         │
         ├──────────────────────────────────────────────────────────┐
         ▼  main.read_rows() (main.py:224-258)                      │
  [Stage 1: Corpus Pre-Pass (series_corpus.py)]                     │
    ├─ resolve_category() + resolve_product_type()                  │
    ├─ extract_model() + resolve_capacity() + find_full_color()     │
    ├─ series_corpus.analyze_row() -> RowAnalysis                   │
    └─ series_corpus.build_corpus() -> Corpus (proven/blacklisted)  │
         │                                                          │
         ▼  main.run() Pass 1 (main.py:725-734, finalise=False)     │
  [Stage 2a: Collision Counting Pass]  ◄────────────────────────────┘
    ├─ resolve_row(..., scratch_flags, finalise=False)
    └─ sku_registry.register_base(base_sku) & handle_registry.register_base(base_handle)
         │
         ▼  main.run() Pass 2 (main.py:736-742, finalise=True)
  [Stage 2b: Final Resolution Pass]
    ├─ resolve_row(..., real_flags, finalise=True)
    │    ├─ 1. resolve_brand()        -> BrandResolution (digi_id, alfa_id)
    │    ├─ 2. resolve_category()     -> CategoryResolution (digi_path, alfa_id)
    │    ├─ 3. resolve_product_type() -> str (canonical English singular)
    │    ├─ 4. extract_model()        -> ModelExtraction + fallback SKU
    │    ├─ 5. resolve_capacity()     -> str ("1.5 Ton", "16 Cu Ft", ...)
    │    ├─ 6. UniqueRegistry.assign()-> disambiguated SKU & Handle
    │    ├─ 7. build_title()          -> TitleResult (single title string!)
    │    ├─ 8. resolve_warranty()     -> (list[SpecRow], headline, source)
    │    ├─ 9. parse_weight()         -> (weight_val, weight_unit)
    │    ├─ 10. build_description_bundle() -> DescriptionBundle (spec_rows, short_html, tags, seo_*)
    │    ├─ 11. resolve_prices()      -> (price, compare_at_price, quantity)
    │    └─ 12. build_attributes()    -> dict[str, str] (36 DigiMall Attribute_* cols)
    └─ Returns list[ProductRecord]
         │
         ▼  writers.py (main.py:988-1003)
  [Stage 3: Platform Projection & CSV Serialization]
    ├─ If platform in ("digi", "both"):
    │    └─ build_digi_row(record, vendor_cfg) -> renders template_for_cell(vendor_cfg, "digi")
    │    └─ write_csv(digi_path, DIGI_HEADER [66 cols], quoting=QUOTE_ALL, encoding="utf-8-sig")
    ├─ If platform in ("alfa", "both"):
    │    └─ build_alfa_row(record, vendor_cfg) -> renders template_for_cell(vendor_cfg, "alfa")
    │    └─ write_csv(alfa_path, ALFA_HEADER [28 cols], quoting=QUOTE_ALL, encoding="utf-8-sig")
    └─ Writes qc_report.csv (filtered by platform) & title_review_sample.csv
         │
         ▼  Post-Processing (invoked by run_ui.py or CLI)
  [Stage 4: Independent Verification & Worklists]
    ├─ audit.py      -> Re-reads input + generated CSVs + qc_report.csv -> writes row_check.csv
    └─ thin_report.py-> Re-reads input + generated CSV + qc_report.csv -> writes thin_descriptions.csv
  ```

### 2. Deep-Dive Forensics of the 4 Established `(Vendor × Platform)` Cells

| Cell | Vendor Key (`--vendor`) | Platform (`--platform`) | Output Vendor Literal | SKU Prefix | Title Formula | Description Template | Brand Map Size | Category Map Size |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`Kiachahiye.digi`** | `kiachahiye` | `digi` | `"KiaChahiye PVT LTD"` (`vendor_config.py:112`) | `"KC"` (`line 86`) | `"vip_pipe"` (`line 87`) | `"spec_table"` (`line 113`) | 29 brands (`lines 114-144`) | 34 paths (`lines 145-179`) |
| **`Kiachahiye.alfa`** | `kiachahiye` | `alfa` | `"Kia Chahiye Pvt Ltd"` (`vendor_config.py:250`) | `"KC"` (`line 86`) | `"vip_pipe"` (`line 87`) | `"kiachahiye_alfa_card"` (`line 251`) | 14 brands (`lines 252-267`) | 26 leaf IDs (`lines 268-295`) |
| **`Ajmer.digi`** | `ajmer` | `digi` | `"Ajmer Electronics PVT LTD"` (`vendor_config.py:323`) | `"AE"` (`line 317`) | `"standard"` (`line 318`) | `"spec_table"` (`line 324`) | **0 (`{}` at `line 325`, `# TODO`)** | **0 (`{}` at `line 328`, `# TODO`)** |
| **`Ajmer.alfa`** | `ajmer` | `alfa` | `"Ajmer Electronics"` (`vendor_config.py:332`) | `"AE"` (`line 317`) | `"standard"` (`line 318`) | `"spec_table"` (`line 333`) | 17 brands (`lines 334-352`) | 16 leaf IDs (`lines 353-370`) |

### 3. Critical Architectural Flaws Discovered in the Current Codebase

#### Finding C.1 — Unwired `VendorConfig` Fields ("Dead Knobs")
- **Repository evidence**:
  1. `VendorConfig.omit_title_color_categories` (`vendor_config.py:70-72`): Defined on `VendorConfig`, set to `frozenset({"LED TV", "QLED TV", "Smart LED TV"})` on `KIACHAHIYE` (`line 103`) and `AJMER` (`line 320`). However, in `main.py:376-391`, `build_title(...)` is called **without passing `omit_color_categories=vendor_cfg.omit_title_color_categories`**. Inside `title_builder.py:2010-2013`:
     ```python
     active_omit = (
         omit_color_categories
         if omit_color_categories is not None
         else getattr(config, "OMIT_TITLE_COLOR_CATEGORIES", OMIT_TITLE_COLOR_CATEGORIES)
     )
     ```
     Because `main.py` never passes `omit_color_categories`, changing `omit_title_color_categories` on a store in `vendor_config.py` has **zero effect** on pipeline runs!
  2. `VendorConfig.apply_tv_warranty_table` (`vendor_config.py:74`): Defined on `VendorConfig`, set on `KIACHAHIYE` (`line 105`) and `AJMER` (`line 321`). However, `warranty.py:109` (`lookup_terms`), `warranty.py:424` (`resolve_warranty`), and `warranty.py:486` (`resolve_main_warranty`) **do not even accept a `vendor_cfg` or `apply_tv_warranty_table` parameter**! Instead, `warranty.py:132` always evaluates:
     ```python
     if category in NO_FALLBACK_CATEGORIES and not getattr(
         config, "APPLY_TV_WARRANTY_TABLE", APPLY_TV_WARRANTY_FALLBACK
     ):
     ```
     Thus, configuring `apply_tv_warranty_table=False` for a specific store in `vendor_config.py` is completely ignored!
  3. `VendorConfig.seo_title_min/max`, `seo_desc_min/max`, `default_variant_quantity`, `default_product_type_colors`: All of these ARE wired in `main.py` (`lines 466-491, 560-575`), **but in `audit.py`** (`lines 428-431, 650-653`), `audit.py` reads the global `SEO_TITLE_MIN`, `SEO_TITLE_MAX`, `SEO_DESC_MIN`, `SEO_DESC_MAX` imported from `config.py` (`audit.py:44-49`) and `getattr(config, "DEFAULT_PRODUCT_TYPE_COLORS", ...)` (`audit.py:650`) instead of reading them from `vendor_cfg`! If a store customizes `default_product_type_colors` or `seo_title_max` in `vendor_config.py`, `main.py` will generate files using the store's values and **`audit.py` will fail the upload** because `audit.py` checks against `config.py` globals!

#### Finding C.2 — Legacy `config.py` Default Vendor Collision & SKU Prefix Mismatch
- **Repository evidence**:
  - In `config.py:38-39`:
    ```python
    VENDOR_DIGI: str = "KiaChahiye PVT LTD"
    VENDOR_ALFA: str = "Ajmer Electronics"
    ```
  - And in `sku_handle.py:33`:
    ```python
    SKU_PREFIX = "KIA"
    ```
    Whereas in `vendor_config.py:86`, `KIACHAHIYE.sku_prefix = "KC"`.
  - Consequently, running `python3 main.py` **without `--vendor`** produces SKUs starting with `KIA-`, stamps `"KiaChahiye PVT LTD"` on DigiMall, and stamps `"Ajmer Electronics"` on Alfa; whereas running `python3 main.py --vendor kiachahiye` produces SKUs starting with `KC-`, stamps `"KiaChahiye PVT LTD"` on DigiMall, and stamps `"Kia Chahiye Pvt Ltd"` on Alfa!

#### Finding C.3 — Global `@lru_cache` Poisoning in `series_corpus.py`
- **Repository evidence**:
  - `series_corpus.py:161-196` defines `@lru_cache(maxsize=1)` on `category_vocabulary()`, `brand_names()`, and `brand_words()`, reading `categories.PRODUCT_TYPE_MAP`, `categories.CATEGORY_DIGI_PATHS`, `categories.CATEGORY_ALFA_IDS`, `brands.BRANDS_DIGI`, and `brands.BRANDS_ALFA` directly from the legacy global modules rather than from the active `vendor_cfg`.
  - Furthermore, `series_corpus.py:566` calls `resolved_brand = resolve_brand(brand, "").raw or brand` without passing `vendor_cfg`.
  - `main.py:224` (`def read_rows(rows: list[InputRow]) -> tuple[list[RowAnalysis], Corpus]:`) does not even accept `vendor_cfg` (`main.py:722` calls `read_rows(rows)`).

#### Finding C.4 — Incomplete Multi-File Auditing in `audit.py`
- **Repository evidence**:
  - `audit.py:235` defines `primary_label, primary_header, primary, primary_text = files[0]`.
  - Under `--platform both`, `files[0]` is DigiMall and `files[1]` is Alfa.
  - While `audit.py` loops over `for file_label, _header, file_rows, _text in files:` for Description/SEO checks (`line 391`) and no-invented-values checks (`line 505`), it runs the following checks **only on `primary` (`files[0]`)**:
    - `Title` checks (`audit.py:554`: `for idx, (src, out) in enumerate(zip(source, primary, strict=True), start=1):`)
    - `Variant Weight` checks (`audit.py:584`: `for idx, (src, out) in enumerate(zip(source, primary, strict=True), start=1):`)
    - `Option1 Value` / Colour checks (`audit.py:642`: `for idx, (src, out) in enumerate(zip(source, primary, strict=True), start=1):`)
    - `Freezer placement` checks (`audit.py:673`: `for idx, (src, out) in enumerate(zip(source, primary, strict=True), start=1):`)
  - Furthermore, `thin_report.py:194-200` (`main()`) only accepts `--digi` (defaulting to `DIGI_OUTPUT_PATH`) and has no `--alfa` or `--platform` flag at all.

---

## Section D — Complete Requirements Matrix

| Req ID | Requirement Description | Source | Category | Priority | Current Support Status | Architectural Impact | Verification Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-01** | Support established cells (`Kiachahiye.digi`, `Kiachahiye.alfa`, `Ajmer.digi`, `Ajmer.alfa`) with strict cell isolation. | User Prompt §1, §5, §8 | Functional | P0 (Must-Have) | **Partial** (`Ajmer.digi` maps empty; Description isolated; Title only vendor-scoped). | Requires `ResolvedCellConfig` per `(vendor, platform)` cell. | Automated SHA-256 digest isolation test across all cells (`test_description_isolation.py` + title equivalent). |
| **REQ-02** | Support Title & Description Scenario A (2 vendors share same template on same platform). | User Prompt §8, §9 | Config / Sharing | P0 | **Supported** for Description; **Supported** for Title (if both vendors set same `title_formula`). | Registry-backed named references (`TITLE_FORMULAS`, `DESCRIPTION_TEMPLATES`). | Unit & integration tests verifying shared object identity and identical output bytes. |
| **REQ-03** | Support Title & Description Scenario B (1 vendor reuses same template across multiple platforms). | User Prompt §8, §9 | Config / Sharing | P0 | **Supported** for Description & Title. | Default inheritance from `VendorDefinition` to all its platform cells. | Integration test projecting one vendor across multiple platforms. |
| **REQ-04** | Support Title & Description Scenario C (1 platform uses distinct template across vendors). | User Prompt §8, §9 | Config / Sharing | P0 | **Supported** for Description (`PlatformConfig.description_template`); **Unsupported** for Title (`title_formula` is only on `VendorConfig`). | Must move `title_formula` resolution to `ResolvedCellConfig` (Platform default + Cell override) and project titles per cell. | Test vendor with 2 platforms having different `title_formula` settings. |
| **REQ-05** | Support Title & Description Scenario D (1 specific `(vendor, platform)` cell overrides template without affecting any other cell). | User Prompt §8, §9 | Config / Isolation | P0 | **Supported** for Description (`Kiachahiye.alfa` uses `kiachahiye_alfa_card`); **Unsupported** for Title. | Requires `CellOverride` level in config hierarchy and per-cell `Title` rendering in projection layer. | 4-cell SHA-256 digest matrix test proving 1-of-4 cell mutation for both Title and Description. |
| **REQ-06** | Eliminate split-brain configuration between `config.py`, `brands.py`, `categories.py`, and `vendor_config.py`, and wire all dead `VendorConfig` fields. | Repo Forensics §C.1–C.3 | Architecture / Correctness | P0 | **Broken** (`omit_title_color_categories` & `apply_tv_warranty_table` unwired; `audit.py` reads `config.py` globals). | Single source of truth via `ResolvedCellConfig` passed to all builders and `audit.py`. | Unit tests overriding every `VendorConfig` field and asserting end-to-end + audit pass. |
| **REQ-07** | Zero-fabrication / deterministic extraction guarantee (never invent specs, models, capacities, colours, or warranties not in source or explicit reference table). | `.agents/rules/`, `README.md`, `audit.py` | Domain Invariant | P0 | **Supported** (enforced by builders + `audit.py`). | Keep deterministic Python extractors in core domain layer; never replace with fuzzy/LLM guessing. | Adversarial & golden acceptance tests (`test_acceptance_examples.py`, `test_audit.py`). |
| **REQ-08** | Pricing engine rule: `Variant Price = Sell Price`; `Variant Compare At Price = Original Price` if `> Sell Price`, else `Sell Price + 10%` rounded up by magnitude. | `.agents/rules/pricing_engine.md`, `pricing.py` | Domain Invariant | P0 | **Supported** (`pricing.py:51-118`). | Allow `PricingPolicy` parameters (markup %, rounding mode, allow-equal) in `ResolvedCellConfig` while keeping current rule as default. | Parametrized pricing tests (`test_writers.py:176-305`). |
| **REQ-09** | Future platform readiness: Shopify Product CSV (multi-row variants sharing `Handle`, blank product fields on child variant/image rows, `Option1..3`, metafields). | User Prompt §2, §12 | Extensibility | P1 (Core Arch) | **Unsupported** (current `writers.py` is 1-input-row-to-1-output-row with hardcoded 28/66 headers). | `PlatformAdapter` must take `Sequence[CanonicalProductFacts]` and return `list[ProjectedRow]` (1:N row expansion). | Prototype-free contract test with a mock multi-row `PlatformAdapter`. |
| **REQ-10** | Future platform readiness: WooCommerce Product CSV (`Type` = `simple`/`variable`/`variation`, `Parent` SKU reference, `Attribute N name/value(s)/visible/global`, `>` category hierarchy). | User Prompt §2, §12 | Extensibility | P1 (Core Arch) | **Unsupported** (current `writers.py` is 1:1 flat row). | `PlatformAdapter` + `AttributeProjector` supporting dynamic `Attribute N *` column generation and parent/child rows. | Contract test verifying 1:N parent+variation row emission. |
| **REQ-11** | Decouple `audit.py` and `thin_report.py` from hardcoded `<table>`/`<th>` regexes so non-table HTML or plain-text description templates can be audited. | User Prompt §9, §15; Repo Forensics | Audit / Quality | P0 | **Broken** (`audit.py:405-417` requires `<table`, `<tr><td`, `<th `; `description_builder.py:926` bans `<div>` templates). | `audit.py` and `thin_report.py` must use `template_for_cell(vendor_cfg, platform).extract(cell_html)` and `template.starts_with/ends_with`. | Test `audit.py` and `thin_report.py` with a `<div>`/`<ul>` card template and a `<table>` template. |
| **REQ-12** | Startup configuration validation catching missing/invalid templates, formulas, brand/category maps, and cross-field incompatibilities before processing rows. | User Prompt §6, §14 | Validation | P0 | **Partial** (`validate_vendor_cfg` checks `sku_prefix`, `vendor_name`, `title_formula`, `description_template`, but not empty active platform maps or attribute scopes). | Expand startup validator to validate `ResolvedCellConfig` for the requested `--platform` targets. | Startup validation unit tests (`test_vendor_config.py`). |
| **REQ-13** | Maintain 100% DRY dynamic pytest suite where adding a vendor, platform, title formula, or description template automatically joins parametrized contract tests. | `.agents/rules/dry_dynamic_algorithm.md`, Prompt §14 | Testing | P0 | **Supported** for existing 2 vendors × 2 platforms; needs generalization to `PLATFORM_REGISTRY`. | Parametrize tests over `VENDOR_REGISTRY × active_platforms(vendor)`. | `pytest` execution with dynamically injected vendor & platform configs. |
| **REQ-14** | Preserve clean architectural boundary for future FastAPI / SaaS / multi-tenant job execution without premature cloud bloat. | User Prompt §1, §16 | SaaS Readiness | P2 | **Partial** (`main.run()` is mostly pure in-memory, but `audit.py` uses module-global `RESULTS: list` at `audit.py:67`). | Eliminate module-global mutable state (`audit.RESULTS`); expose stateless `execute_pipeline_job()` API returning structured `RunResult`. | Concurrent/repeated in-process invocation test confirming zero state leakage. |

---

## Section E — Architecture Alternatives and Comparative Evaluation

We evaluate four complete, distinct architectural designs against the repository evidence and requirements.

### Alternative 1: Incremental Refactoring of Current Python Dataclasses (`vendor_config.py` Evolution)
- **Philosophy**: Keep all configurations, brand/category dictionaries, title formulas, and description templates inside Python modules (`vendor_config.py`, `title_builder.py`, `description_builder.py`). Fix the unwired fields (`omit_title_color_categories`, `apply_tv_warranty_table`), add `title_formula` to `PlatformConfig`, and add new platforms as additional fields on `VendorConfig` (e.g., `digi: PlatformConfig`, `alfa: PlatformConfig`, `shopify: PlatformConfig | None = None`).
- **Configuration Model**: Pure Python frozen dataclasses in `vendor_config.py`.
- **Title & Description System**: Named Python callables in `TITLE_FORMULAS` and `DescriptionTemplate` instances in `DESCRIPTION_TEMPLATES`.
- **Platform Onboarding**: Requires editing `VendorConfig` dataclass fields, `main.py` CLI flags (`--shopify`), `writers.py`, `audit.py`, and `run_ui.py` for every new platform.
- **Pros**:
  - Smallest immediate diff from the current codebase.
  - Zero new dependencies (`stdlib` + `openpyxl`).
- **Cons**:
  - **Violates Open-Closed Principle for platforms**: `VendorConfig` hardcodes `.digi` and `.alfa` attributes (`vendor_config.py:55-56`), `CategoryResolution` hardcodes `digi_path` and `alfa_id` (`models.py:56-57`), and `BrandResolution` hardcodes `digi_id` and `alfa_id` (`models.py:42-43`). Adding Shopify, WooCommerce, and Daraz turns every dataclass and resolver into a wide N-platform struct.
  - **Massive data duplication remains in Python code**: `vendor_config.py` is already 452 lines for just 2 stores (with `Ajmer.digi` still empty). At 10 stores × 4 platforms, `vendor_config.py` will exceed 5,000 lines of inline Python dicts.

### Alternative 2: Layered Hybrid Architecture — Python Core Engine + Hierarchical `ResolvedCellConfig` + Pluggable `PlatformAdapter` + Declarative Data Packs (**RECOMMENDED**)
- **Philosophy**: Separate **how facts are extracted and projected** (pure Python domain logic, `PlatformAdapter` implementations, `TitleFormula` and `DescriptionTemplate` registries) from **what a store or platform maps and configures** (hierarchical `EngineDefaults → PlatformDefinition → VendorDefinition → CellOverride` backed by declarative TOML/CSV/JSON data files or clean per-vendor Python/TOML manifests).
- **Configuration Model**:
  - `VendorConfig` replaces hardcoded `.digi` and `.alfa` fields with `platforms: Mapping[str, CellConfig]` (while keeping `.digi` and `.alfa` properties for 100% backwards compatibility).
  - A deterministic 4-level resolver compiles `(vendor_key, platform_key)` into a single self-contained `ResolvedCellConfig` before the run starts.
  - Shared lookup tables (e.g., `alfa_common_brands`, `digi_segment_aliases`, `warranty_terms`) are defined once and inherited or overridden per store/cell via explicit composition—eliminating the copy-pasted dictionaries in `vendor_config.py`.
- **Title & Description System**:
  - `CanonicalProductFacts` (`ProductRecord` v2) stores extracted slot tokens (`brand`, `model`, `capacity`, `color_token`, `inverter_token`, `subtype_token`, `series_token`, `warranty_tail`, `spec_rows`).
  - Both `TitleFormula` and `DescriptionTemplate` live on `ResolvedCellConfig` and execute at **projection time**, giving 100% symmetry across Scenarios A, B, C, and D.
- **Platform Onboarding**:
  - `PLATFORM_REGISTRY: dict[str, PlatformAdapter]` registers platform adapters (`"digi"`, `"alfa"`, `"shopify"`, `"woocommerce"`, `"daraz"`).
  - Each `PlatformAdapter` declares its header schema, required mappings, attribute projection strategy, row-expansion cardinality (`1:1` vs `1:N` variant rows), and platform-specific audit rules.
- **Pros**:
  - Directly solves all split-brain bugs, unwired knobs, and Scenario A–D requirements.
  - Scales cleanly to Shopify/WooCommerce (`1:N` rows) and 10+ vendors without touching extraction modules.
  - Can be implemented incrementally in 4 small, non-breaking phases using Python's standard library (`tomllib` in Python 3.11+ or JSON/CSV + dataclasses in Python 3.10).
- **Cons**:
  - Requires refactoring `BrandResolution` and `CategoryResolution` from `{digi_id, alfa_id}` to `by_platform: Mapping[str, str | int | None]` (or resolving brand/category per active cell).

### Alternative 3: Pure Declarative / Schema-Driven DSL Engine (YAML/JSON Rule DSL + Jinja2)
- **Philosophy**: Move not only brand/category maps, but also title slot assembly, regex extraction rules, description HTML templates, and column mappings into external YAML/JSON files and Jinja2 templates. Python becomes a thin generic interpreter.
- **Configuration Model**: 100% YAML/JSON + `.j2` template files.
- **Title & Description System**: Jinja2 templates for both Titles and Descriptions, with YAML pipelines for token cleanup and fallback chains.
- **Pros**:
  - Non-developers can theoretically edit `.j2` and `.yaml` files without touching `.py` files.
- **Cons**:
  - **Catastrophic mismatch with the repository's actual domain complexity**: Inspecting `title_builder.py` (2,466 lines), `series_corpus.py` (1,479 lines), `warranty.py` (535 lines), and `sku_handle.py` (691 lines) proves that Pakistani appliance title/warranty/series extraction is governed by intricate, multi-rung linguistic invariants (e.g., edit-distance class-typo suppression in `series_corpus.py:1193-1221`, non-inverter negation precedence in `categories.py:310-324`, colourway boundary rules in `textutils.py:420-530`). Expressing these in YAML or Jinja2 macros would create an unmaintainable, untestable "inner-platform effect" (Greenspun's Tenth Rule).
  - Adds external dependencies (`PyYAML`, `Jinja2`) and loses static type checking (`mypy`) and IDE navigation.

### Alternative 4: Plugin / Entry-Point / Event-Driven Pipeline Framework
- **Philosophy**: Architect the generator as an abstract event bus or `pluggy` / `importlib.metadata` entry-point framework where every stage (ingestion, brand lookup, model extraction, title building, description building, platform writing, auditing) is a dynamically discovered hook/plugin package.
- **Configuration Model**: Plugin manifests + dependency-injected hook registries.
- **Pros**:
  - Maximum decoupling if third-party external developers were shipping closed-source binary plugins.
- **Cons**:
  - **Severe over-engineering**: Indirection obscures the step-by-step business rules that `ruff.toml:45-48` explicitly protects (*"Functions such as `resolve_row()`, `build_description_bundle()` and the audit's `main()` are long and take several arguments on purpose: they are the readable, step-by-step specification of one business rule each"*).
  - Makes debugging row-level transformations much harder without providing any practical benefit over explicit Python registries (`VENDOR_REGISTRY`, `PLATFORM_REGISTRY`, `TITLE_FORMULAS`, `DESCRIPTION_TEMPLATES`).

### Weighted Architecture Comparison Matrix

| Evaluation Criterion | Weight | Alt 1: Incremental Python Dataclasses | Alt 2: Layered Hybrid + `PlatformAdapter` (**Recommended**) | Alt 3: Pure Declarative YAML/Jinja2 DSL | Alt 4: Dynamic Plugin / Hook Bus |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Multi-Vendor Scalability (2 → 50 stores)** | 15% | 5 / 10 | **9.5 / 10** | 8.5 / 10 | 7.5 / 10 |
| **2. Multi-Platform Extensibility (Shopify/Woo/Daraz)** | 20% | 4 / 10 | **9.5 / 10** | 7 / 10 | 8.5 / 10 |
| **3. Scenario A–D Title & Description Symmetry** | 15% | 7 / 10 | **10 / 10** | 9 / 10 | 8 / 10 |
| **4. Preservation of Domain Extraction Precision** | 20% | 9.5 / 10 | **10 / 10** | 4 / 10 | 8 / 10 |
| **5. Audit & Conformance Verification Integrity** | 10% | 6.5 / 10 | **9.5 / 10** | 6 / 10 | 7 / 10 |
| **6. Developer Ergonomics & Low Cognitive Load** | 10% | 8 / 10 | **9.5 / 10** | 5.5 / 10 | 4.5 / 10 |
| **7. Migration Safety & Low Blast Radius** | 10% | 9 / 10 | **9.0 / 10** | 3 / 10 | 4 / 10 |
| **Weighted Total Score (out of 10.0)** | **100%** | **6.80 / 10** | **9.60 / 10** | **6.18 / 10** | **7.15 / 10** |

---

## Section F — Recommended Target Architecture

### 1. High-Level Component & Package Topology
- **Architectural recommendation**: Evolve `/kiachahiye_bulk_csv/` into a clean 5-layer architecture without breaking existing CLI entry points (`main.py`, `audit.py`, `thin_report.py`, `run_ui.py`, `clean_descriptions.py`):

```text
kiachahiye_bulk_csv/
├── core/                         # Layer 1: Pure Platform-Agnostic Fact Extraction
│   ├── models.py                 # InputRow, CanonicalProductFacts, SpecRow, ProjectedRow
│   ├── textutils.py              # Sanitizers, weight parser, colourway reader
│   ├── series_corpus.py          # Parameterized by VendorCatalog (no global lru_cache)
│   ├── sku_handle.py             # Model & capacity extraction, UniqueRegistry
│   ├── warranty.py               # Clause parser + parameterized warranty table lookup
│   ├── pricing.py                # Parameterized PricingPolicy (markup, rounding, qty)
│   └── description_parser.py     # 4-branch source description -> SpecRow[] + bullets + tags
│
├── rendering/                    # Layer 2: Cell-Scoped Presentation & Composition
│   ├── title_formulas.py         # TitleFormula registry (standard, vip_pipe, brand_first_extended, ...)
│   ├── description_templates.py  # DescriptionTemplate registry (spec_table, kiachahiye_alfa_card, ...)
│   └── seo_builder.py            # Cell-scoped SEO Title & SEO Description builders
│
├── platforms/                    # Layer 3: Pluggable Destination Platform Adapters
│   ├── base.py                   # PlatformAdapter Protocol, ColumnSpec, PlatformSchema
│   ├── digimall.py               # 66-col DigiMall adapter + 36 Attribute_* closed-list matcher
│   ├── alfa.py                   # 28-col Alfa adapter
│   ├── shopify.py                # Future: Multi-row Handle-grouped variant/image adapter
│   └── woocommerce.py            # Future: simple/variable/variation + Parent SKU adapter
│
├── configs/                      # Layer 4: Hierarchical Configuration & Shared Data Packs
│   ├── schema.py                 # EngineDefaults, PlatformDefinition, VendorDefinition,
│   │                             # CellOverride, ResolvedCellConfig, startup validator
│   ├── shared/                   # Shared non-duplicated catalogs (brand_aliases, warranty_terms,
│   │                             # product_types, alfa_base_brands, digi_segment_aliases)
│   └── vendors/                  # Per-vendor definitions (kiachahiye.py/.toml, ajmer.py/.toml)
│
├── verification/                 # Layer 5: Cell- & Template-Aware Quality Gates
│   ├── qc_report.py              # Multi-platform QCFlagCollector
│   ├── audit.py                  # Adapter- & Template.extract()-driven verification gate
│   └── thin_report.py            # Template.extract()-driven thin description worklist
│
└── main.py, audit.py, thin_report.py, run_ui.py, vendor_config.py  # Backwards-compatible facades
```

### 2. Core Data-Flow Invariant: "Extract Once, Project Per Cell"
In the current codebase (`main.py:261-623`), `resolve_row()` mixes **fact extraction** (what the product is) with **cell presentation** (rendering `ProductRecord.title` once using `vendor_cfg.title_formula`) and **hardcoded dual-platform lookups** (`brand.digi_id`, `brand.alfa_id`, `category.digi_path`, `category.alfa_id`).

In the target architecture:
1. **`CanonicalProductFacts` (Platform-Agnostic Fact Record)**:
   - Stores extracted, normalized domain tokens:
     - `source: InputRow`
     - `brand_raw: str`, `brand_normalized: str`
     - `breadcrumb_leaf: str`, `product_type: str`, `product_type_inferred: bool`
     - `model_extraction: ModelExtraction` (`code`, `source`, `confidence`)
     - `capacity_token: str`, `color_token: str`, `color_conflict: tuple[str, ...]`
     - `inverter_token: str`, `subtype_token: str`, `subtype_from: str`, `subtype_conflict: tuple[str, ...]`
     - `series_token: str`, `series_earned_by: SeriesProof`, `usp_tokens: tuple[str, ...]`
     - `warranty_rows: tuple[SpecRow, ...]`, `warranty_headline: str | None`, `warranty_source: str`, `main_warranty_phrase: str | None`
     - `spec_rows: tuple[SpecRow, ...]`, `short_bullets: tuple[str, ...]`, `tags: tuple[str, ...]`
     - `weight_value: str`, `weight_unit: str`
     - `sell_price: int`, `original_price_raw: int | None`
2. **Per-Cell Projection (`PlatformAdapter.project_all(facts_list, cell_cfg, flags)`)**:
   - Given a `ResolvedCellConfig` for `(vendor, platform)`:
     - Resolves the cell's brand ID/name (`cell_cfg.brands.get(facts.brand_normalized)`).
     - Resolves the cell's category ID/path (`cell_cfg.category_resolver(facts, cell_cfg)`).
     - Renders the cell's **Title** using `cell_cfg.title_formula.render(facts.title_slots, cell_cfg)`.
     - Renders the cell's **SEO Title & SEO Description** using `cell_cfg.seo_policy`.
     - Renders the cell's **Description** using `cell_cfg.description_template.render(list(facts.spec_rows))`.
     - Resolves the cell's **Prices & Quantity** using `cell_cfg.pricing_policy`.
     - Projects platform-specific attributes (e.g., DigiMall's 36 `Attribute_*` columns, WooCommerce's `Attribute N *` columns, Shopify's `Option1..3` and `product.metafields.*` columns).

---

## Section G — Universal Configuration Architecture

### 1. The 4-Level Configuration Inheritance Model
To support arbitrary combinations of vendors and platforms without copy-pasting dictionaries across stores, every setting is resolved through a strict, deterministic **4-level precedence hierarchy** (highest wins):

$$\text{Level 4: CellOverride } (V, P) \succ \text{Level 3: VendorDefinition } (V) \succ \text{Level 2: PlatformDefinition } (P) \succ \text{Level 1: EngineDefaults}$$

| Level | Object | What Lives Here | Concrete Examples from Repository |
| :--- | :--- | :--- | :--- |
| **Level 1 (Lowest)** | `EngineDefaults` | Global baseline rules when neither platform nor vendor specifies an override. | `title_formula="standard"`, `description_template="spec_table"`, `default_variant_quantity=20`, `seo_title_min=65`, `seo_title_max=90`, `seo_desc_min=120`, `seo_desc_max=155`, `apply_tv_warranty_table=True`, `omit_title_color_categories={"LED TV", "QLED TV", "Smart LED TV"}`, shared `BRAND_ALIASES`, shared `BRAND_DISPLAY_MAP`, shared `PRODUCT_TYPE_MAP`, shared `WARRANTY_TERMS`. |
| **Level 2** | `PlatformDefinition` (`digi`, `alfa`, `shopify`, `woocommerce`) | Platform-wide schema, column headers, category format rules, platform-wide segment aliases, and platform-wide default templates/formulas. | `digi`: `header=DIGI_HEADER (66 cols)`, `category_format="underscore_path"`, `segment_aliases=DIGI_SEGMENT_ALIASES`, `requires_inverter_ac_split=True`, `attribute_schema=DIGI_36_ATTRIBUTES`.<br>`alfa`: `header=ALFA_HEADER (28 cols)`, `category_format="numeric_leaf_id"`, `segment_aliases=ALFA_SEGMENT_ALIASES`, `base_brands=ALFA_COMMON_BRANDS`. |
| **Level 3** | `VendorDefinition` (`kiachahiye`, `ajmer`, ...) | Vendor identity, SKU prefix, and vendor-wide overrides that apply across all platforms unless overridden at a specific cell. | `kiachahiye`: `display_name="Kiachahiye"`, `sku_prefix="KC"`, `title_formula="vip_pipe"`.<br>`ajmer`: `display_name="Ajmer"`, `sku_prefix="AE"`, `title_formula="standard"`. |
| **Level 4 (Highest)** | `CellOverride` (`(vendor, platform)`) | Cell-specific marketplace account literal (`vendor_name`), store-specific platform brand/category IDs, and cell-specific template/formula overrides. | `Kiachahiye.digi`: `vendor_name="KiaChahiye PVT LTD"`, `brands={...}`, `categories={...}`.<br>`Kiachahiye.alfa`: `vendor_name="Kia Chahiye Pvt Ltd"`, **`description_template="kiachahiye_alfa_card"`**, `brands=ALFA_COMMON_BRANDS | {...}`, `categories={...}`.<br>`Ajmer.alfa`: `vendor_name="Ajmer Electronics"`, `brands=ALFA_COMMON_BRANDS | {"dawlance": 7061, ...}`, `categories={...}`. |

### 2. Compiled `ResolvedCellConfig` Dataclass
Before `main.py` or `audit.py` reads row 1 of the input sheet, `resolve_cell_config(vendor_key, platform_key) -> ResolvedCellConfig` merges Levels 1→4 into a single **frozen, flat dataclass**:

```python
@dataclass(frozen=True)
class ResolvedCellConfig:
    vendor_key: str                           # e.g. "kiachahiye"
    vendor_display_name: str                  # e.g. "Kiachahiye"
    platform_key: str                         # e.g. "alfa"
    platform_display_name: str                # e.g. "Alfa"
    cell_label: str                           # e.g. "Kiachahiye.alfa"
    vendor_name: str                          # e.g. "Kia Chahiye Pvt Ltd"
    sku_prefix: str                           # e.g. "KC"
    title_formula: TitleFormulaSpec           # Resolved callable/object (NOT a raw unvalidated string)
    description_template: DescriptionTemplate # Resolved template object
    brands: Mapping[str, int | str]           # Merged & normalized brand lookup for this cell
    brand_aliases: Mapping[str, str]          # Merged brand aliases
    brand_display_map: Mapping[str, str]      # Merged display names
    categories: Mapping[str, str]             # Merged category lookup for this cell
    category_segment_aliases: Mapping[str, str]
    product_type_map: Mapping[str, str]
    warranty_terms: Mapping[str, Mapping[str, str]]
    apply_tv_warranty_table: bool
    omit_title_color_categories: frozenset[str]
    default_product_type_colors: Mapping[str, str]
    default_variant_quantity: int
    seo_title_min: int
    seo_title_max: int
    seo_desc_min: int
    seo_desc_max: int
    pricing_markup_ratio: float               # Default 1.10 (+10%)
```

- **Why `ResolvedCellConfig` Eliminates Every Split-Brain Bug**:
  - No downstream function (`build_title`, `resolve_warranty`, `build_description_bundle`, `build_digi_row`, `audit`, `thin_report`) ever calls `getattr(config, ...)` or checks `if vendor_cfg is not None`.
  - Every function receives `cell_cfg: ResolvedCellConfig` (or a `VendorCatalog` view for pre-projection extraction).
  - Dictionary merging uses explicit base-plus-override composition (`base_brands | cell_override_brands`), eliminating the verbatim duplication of `alfa.brands` (`vendor_config.py:252-267` vs `334-352`) and `digi_segment_aliases` (`vendor_config.py:180-193` vs `299-312`).

---

## Section H — Title Formula and Title Template Architecture

### 1. Repository Forensics of `title_builder.py`
- **Repository evidence**:
  - `title_builder.py` (`2,466 lines`) currently implements three named formulas registered in `TITLE_FORMULAS` (`title_builder.py:2427-2431`):
    1. `"standard"` (`_formula_standard`, `lines 2070-2177` — used by `AJMER`):
       - **With model code**: `[Brand] [Capacity] [Color] [Inverter] [Subtype] [Category Name] - [Model] [Series/USPs] - [Main Warranty]`
       - **Without model code**: `[Brand] [Capacity] [Color] [Inverter] [Subtype] [Category Name] - [Series/USPs] - [Main Warranty]`
    2. `"brand_first_extended"` (`_formula_brand_first_extended`, `lines 2180-2228`):
       - **With model code**: `[Brand] [Model] - [Capacity] [Color] [Inverter] [Subtype] [Category Name] - [Series/USPs] - [Main Warranty]`
    3. `"vip_pipe"` (`_formula_vip_pipe`, `lines 2231-2424` — used by `KIACHAHIYE`):
       - Category-dispatched pipe (`|`) format with a 150-char soft budget (`_VIP_MAX_LEN = 150`) and 195-char hard ceiling (`TITLE_MAX = 195`):
         - **Refrigerator**: `[Brand] [Model] | [Capacity] [Series] [Subtype] [Inverter] Refrigerator | [Color] | [Main Warranty]` (or `Glass Door` / `Double Door` fallback when `[Series] [Subtype]` is empty).
         - **Air Conditioner**: `[Brand] [Model] | [Capacity] [Series] [Inverter] [Subtype] Air Conditioner | [Main Warranty]` (deliberately omits `[Color]` in AC pipe titles!).
         - **LED TV**: `[Brand] [Model] | [Capacity] [Series] [Subtype] [Resolution] [Smart] TV | [Main Warranty]`.
         - **Washing Machine**: `[Brand] [Model] | [Capacity] [Subtype] Washing Machine | [Color] | [Main Warranty]`.
         - **Microwave Oven**: `[Brand] [Model] | [Capacity] [Series] [Subtype] Microwave Oven | [Color] | [Main Warranty]`.
         - **Water Dispenser**: `[Brand] [Model] | [Taps] [Subtype] Water Dispenser | [Color] | [Main Warranty]`.
         - **Deep Freezer**: `[Brand] [Model] | [Capacity] [Series] [Subtype] [Inverter] Deep Freezer | [Color] | [Main Warranty]`.
         - **Generic fallback**: `[Brand] [Model] | [Capacity] [Series] [Subtype] [Inverter] [Category] | [Color] | [Main Warranty]`.

### 2. Why Current Title Architecture Fails Scenarios C and D
- **Repository evidence**:
  - In `vendor_config.py:64`, `title_formula: str | Callable[..., str] = "standard"` is a field on `VendorConfig`, **not** `PlatformConfig`.
  - In `main.py:376`, `resolve_row()` calls `build_title(..., title_formula=vendor_cfg.title_formula)` once per row and stores the resulting string in `ProductRecord.title` (`main.py:598`).
  - In `writers.py:165`, `_shared_cells()` writes `"Title": record.title` identically into both DigiMall and Alfa.
  - Therefore, if `Kiachahiye.digi` wants `"vip_pipe"` and `Kiachahiye.alfa` wants `"standard"` (Scenario C / Scenario D), **the current architecture cannot represent or execute it**.

### 3. Target Title Architecture: Separating Slot Extraction from Formula Rendering
- **Architectural recommendation**:
  Split `build_title()` in `title_builder.py` into two distinct, composable phases:
  1. **Phase 1 — `extract_title_slots(row, corpus, catalog_cfg) -> TitleSlots` (Executed once per row in `resolve_row`)**:
     - Computes and freezes all extracted slot values into an immutable `TitleSlots` dataclass on `CanonicalProductFacts`:
       ```python
       @dataclass(frozen=True)
       class TitleSlots:
           brand: str
           model: str
           has_real_model: bool
           product_type: str
           capacity: str
           color: str
           inverter: str
           subtype: str
           subtype_from: str
           series: str
           series_earned_by: SeriesProof
           usps: tuple[str, ...]
           warranty_by_policy: Mapping[bool, str] # Cached for apply_tv_warranty_table True/False
           resolution: str                        # For TVs (4K UHD, Full HD, HD)
           smart_os: str                          # For TVs (Google TV, Android TV, Smart)
           taps: str                              # For Water Dispensers (2 Taps, 3 Taps)
       ```
  2. **Phase 2 — `render_title(slots: TitleSlots, cell_cfg: ResolvedCellConfig) -> TitleResult` (Executed per `(vendor, platform)` cell at projection time)**:
     - Applies `cell_cfg.omit_title_color_categories` and `cell_cfg.apply_tv_warranty_table` to `slots`.
     - Invokes `cell_cfg.title_formula.render(slots, cell_cfg)` (from `TITLE_FORMULAS`).
     - Enforces `cell_cfg.title_max_length` (default `195`) with deterministic tail-slot shedding (`usps` → `series` → `subtype` → word boundary).
     - **Support for Scenarios A, B, C, D**:
       - **Scenario A (2 vendors share same formula on same platform)**: Both `Kiachahiye.alfa` and `Ajmer.alfa` resolve `title_formula="standard"` from `TITLE_FORMULAS["standard"]`.
       - **Scenario B (1 vendor reuses same formula across platforms)**: `Kiachahiye` sets `title_formula="vip_pipe"` at Level 3 (`VendorDefinition`); both `Kiachahiye.digi` and `Kiachahiye.alfa` inherit `"vip_pipe"`.
       - **Scenario C (1 platform uses distinct formula)**: `PlatformDefinition("shopify")` sets `title_formula="shopify_seo_clean"` at Level 2; all stores projecting to Shopify inherit it unless overridden at Level 3/4.
       - **Scenario D (1 specific `(vendor, platform)` cell overrides formula)**: `Kiachahiye.alfa` sets `title_formula="standard"` at Level 4 (`CellOverride`), while `Kiachahiye.digi` keeps `"vip_pipe"` and `Ajmer.*` stay untouched.

---

## Section I — Description Template Architecture

### 1. Repository Forensics of `description_builder.py`
- **Repository evidence**:
  - `description_builder.py` (`1,650 lines`) already implements a clean two-stage separation:
    1. **Fact extraction (`build_description_bundle`, `lines 1106-1356`)**: Parses the source description into `spec_rows: list[SpecRow]` (`models.py:67-74`, where each `SpecRow` has `label: str`, `value: str`, `is_warranty: bool = False`), `short_description_html: str`, `tags: list[str]`, `seo_title: str`, and `seo_description: str`.
    2. **Per-cell template projection (`DescriptionTemplate`, `lines 822-907` & `writers.py:119-151`)**:
       - `DESCRIPTION_TEMPLATES` (`lines 893-896`) registers:
         - `"spec_table"` (`SPEC_TABLE`): 2-column HTML `<table>` with `<thead><tr><th ...>Specification</th><th ...>Details</th></tr></thead><tbody>...</tbody></table>`, bolding warranty rows with `<strong>`.
         - `"kiachahiye_alfa_card"` (`KIACHAHIYE_ALFA_CARD`, `lines 405-472`): Styled `<table style="width:100%;max-width:820px;...">` with a dark gradient header (`linear-gradient(135deg,#0f172a 0%,#1e293b 100%)`), alternating zebra rows (`#ffffff` / `#f8fafc`), and amber-highlighted warranty rows (`background-color:#fffbeb`).
       - Each `DescriptionTemplate` is a frozen dataclass (`lines 822-867`) pairing:
         - `name: str`
         - `render: Callable[[list[SpecRow]], str]`
         - `extract: Callable[[str], list[SpecRow]]`
         - `starts_with: str` (currently required to be `"<table"`)
         - `ends_with: str` (currently required to be `"</table>"`)

### 2. Three Critical Flaws in the Current Description Template System
- **Repository evidence**:
  1. **`html.escape(..., quote=False)` Vulnerability (`description_builder.py:256-257, 427-428`)**:
     - Both `_row_html` and `_alfa_card_row_html` call `html.escape(label, quote=False)` and `html.escape(value, quote=False)`.
     - While safe inside `<td>...</td>` text nodes, leaving `"` and `'` unescaped means any template that ever places a label or value inside an HTML attribute (e.g., `data-label="{label}"` or `title="{value}"`) introduces an immediate HTML attribute injection / broken-DOM bug (which `test_description_templates.py:798-820` had to write a special conformance detector to block!).
     - **Fix**: Standardize on a shared helper `escape_cell(text: str) -> str` using `html.escape(text, quote=True)`, which is already proven compatible with the conformance harness (`test_a_shape_that_escapes_quotes_too_is_still_accepted`, `test_description_templates.py:376-382`).
  2. **The `<table` / `<th ` Straitjacket (`description_builder.py:926-961`, `audit.py:405-417`)**:
     - Because `audit.py:405-417` hardcodes `<table`, `</table>`, `<tr><td[^>]*>`, and `for tag in ("table", "thead", "tbody", "tr", "td", "th "):` (note the trailing space in `"th "`, which forces every `<th>` tag to carry a dummy attribute like `<th style="c">`!), `description_builder.py:926-961` (`template_problems`) rejects any template that does not start with `<table` and end with `</table>` or that uses bare `<th>Specification</th>` (`test_description_templates.py:260-261`)!
     - If a store on Shopify or WooCommerce wants a semantic `<div>`/`<dl>`/`<ul>` specification card or a clean two-section HTML block without a `<table>`, the current conformance harness refuses it solely because `audit.py` is not template-aware.
  3. **Smoking-Gun Bug Verified in Repository (`description_builder.py:436` vs `thin_report.py:36` & `audit.py:409`)**:
     - Look at `description_builder.py:436` (`KIACHAHIYE_ALFA_CARD`):
       ```python
       f'<tr style="background-color:{row_bg};">'
       ```
     - Look at `thin_report.py:36`:
       ```python
       _SPEC_ROW_RE = re.compile(r"<tr><td\b", re.IGNORECASE)
       ```
     - Look at `audit.py:409`:
       ```python
       labels = re.findall(r"<tr><td[^>]*>(?:<strong>)?([^<]+)", desc)
       ```
     - Look at `audit.py:706`:
       ```python
       spec_row_count = max(0, desc.count("<tr") - 1)
       ```
     - Because `KIACHAHIYE_ALFA_CARD` puts `style="background-color:..."` on `<tr ...>`, **neither `audit.py:409` (`r"<tr><td[^>]*>"`) nor `thin_report.py:36` (`r"<tr><td\b"`) matches a single row of `KIACHAHIYE_ALFA_CARD`!**
     - In `audit.py:409`, `labels` evaluates to `[]` on `Kiachahiye.alfa`, silently skipping the duplicate-label check on `Kiachahiye.alfa`!
     - In `audit.py:706`, because `KIACHAHIYE_ALFA_CARD` has **two** `<tr>` header rows in `<thead>` (`Product Specifications` banner + `Specification / Details` column headers), `desc.count("<tr") - 1` **overcounts `Spec Rows` by 1 on every single `Kiachahiye.alfa` row** in `row_check.csv`!
     - And why didn't `validate_vendor_cfg(KIACHAHIYE)` catch this at startup? Look at `vendor_config.py:436`:
       ```python
       if platform == "digi":
           problems.extend(...)
       ```
       `vendor_config.py:436` **deliberately skipped running `template_problems(template)` on `platform == "alfa"`**!

### 3. Target Description Template Architecture: Round-Trip `template.extract()` Everywhere
- **Architectural recommendation**:
  1. **Make `template.extract(html) -> list[SpecRow]` the universal reader**:
     - Every registered `DescriptionTemplate` already provides an exact inverse reader `template.extract(html) -> list[SpecRow]` (verified by `test_round_trip_covers_every_real_row`).
     - Update `audit.py` (`lines 405-417`, `492-502`, `706`) and `thin_report.py` (`line 82`) to look up `template = template_for_cell(vendor_cfg, platform)` and call `spec_rows = template.extract(desc)`.
     - Once `audit.py` and `thin_report.py` call `template.extract(desc)` instead of `re.findall(r"<tr><td...", desc)`:
       - `audit.py` accurately checks duplicate labels, empty cells, warranty bolding (`row.is_warranty`), non-invented values (`row.value`), and exact `Spec Rows` count on **all templates** (including `KIACHAHIYE_ALFA_CARD`, `<dl>`/`<div>` cards, and bullet-list templates).
       - `thin_report.py` accurately counts `len(template.extract(desc))` on **any platform file**.
       - `vendor_config.py:436` removes the `if platform == "digi":` workaround and runs `template_problems(template)` on **every platform cell**.
       - `description_builder.py:926` (`template_problems`) no longer needs to enforce literal `<tr><td` or `<th ` (with trailing space)—it only enforces:
         1. `template.starts_with` and `template.ends_with` boundary presence.
         2. Lossless round-trip: `template.extract(clean_inline(template.render(CONFORMANCE_ROWS))) == CONFORMANCE_ROWS`.
         3. Lossless round-trip on `ESCAPE_PROBE` (HTML/entity/quote injection safety).
         4. Valid HTML5 tag nesting (`_nesting_problems`) and printable entity references (`_entity_problems`).
         5. Single-line output after `clean_inline()` with no double spaces in visible text.

---

## Section J — Warranty, Category, Brand, Attribute, Tag, Price and Fallback Configuration

### 1. Granular Scoping Matrix for All Domain Rules

| Domain Rule / Table | Current Location | Current Scope | Target Scope in `ResolvedCellConfig` | Rationale & Inheritance Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **Brand ID / Name Map** | `vendor_config.py` + `brands.py` | `(vendor, platform)` (with fallback to `brands.py`) | **Level 2 (`PlatformDefinition`) base + Level 4 (`CellOverride`) override** | Alfa brand IDs are 90% identical across stores (`KIACHAHIYE.alfa.brands` vs `AJMER.alfa.brands`), with store-specific additions. Defining `ALFA_BASE_BRANDS` on `PlatformDefinition("alfa")` and merging store overrides eliminates duplication while preserving strict store isolation when a store sets `inherit_platform_brands=False`. |
| **Brand Aliases & Display Names** | `brands.py:86-127`, `vendor_config.py:89-99` | Global + Vendor | **Level 1 (`EngineDefaults`) + Level 3 (`VendorDefinition`)** | Spelling normalizations (`"superasia" -> "super asia"`, `"pak electron" -> "pel"`) are universal domain facts; vendors can add store-specific aliases without copying the base dict. |
| **Category ID / Path Map** | `vendor_config.py` + `categories.py` | `(vendor, platform)` | **Level 4 (`CellOverride`)** (or Level 2 for platforms with global taxonomy like Shopify Standard Product Taxonomy) | In DigiMall and Alfa, category IDs/paths are per-merchant catalog assignments (`11639_...` vs `11859`), so they must default to empty `{}` per cell unless explicitly configured, preventing cross-store category leakage (`test_alfa_cells_never_leave_the_stores_own_lists`). |
| **Category Segment Aliases & `PRODUCT_TYPE_MAP`** | `categories.py:39-143`, `vendor_config.py:180-248` | Vendor | **Level 1 (`EngineDefaults`) + Level 2 (`PlatformDefinition`) + Level 3/4 overrides** | `PRODUCT_TYPE_MAP` and `DIGI_SEGMENT_ALIASES` are currently duplicated verbatim between `KIACHAHIYE`, `AJMER`, and `categories.py`. Moving the canonical map to Level 1/2 reduces `vendor_config.py` size by ~60%. |
| **Warranty Reference Table (`WARRANTY_TERMS`)** | `warranty_terms.py:25-128` | Global only | **Level 1 (`EngineDefaults`) + Level 3 (`VendorDefinition`) + Level 4 (`CellOverride`)** | Official Pakistani manufacturer warranties (Dawlance 12Y compressor, Haier 10Y compressor) are shared across authorized dealers, but a vendor may carry an exclusive distributor warranty or disable TV fallback (`apply_tv_warranty_table=False`). |
| **Omit Title Color Categories** | `config.py:72`, `vendor_config.py:70` (unwired!) | Global (broken vendor knob) | **Level 1 → Level 3 → Level 4 (`ResolvedCellConfig.omit_title_color_categories`)** | Must be wired into `render_title()` and `audit.py`. |
| **Default Product Type Colors** | `config.py:66`, `vendor_config.py:68` | Vendor (unwired in `audit.py`!) | **Level 1 → Level 3 → Level 4 (`ResolvedCellConfig.default_product_type_colors`)** | Used when a category (e.g., `LED TV`) omits colour in source text; must be read by both `main.py` and `audit.py`. |
| **Pricing & Inventory Policy** | `pricing.py:20`, `config.py:56` | Vendor (`default_variant_quantity`) + hardcoded `+10%` | **Level 1 → Level 3 → Level 4 (`PricingPolicy`)** | Encapsulates `default_quantity=20`, `compare_at_markup=0.10`, `round_by_magnitude=True`, `require_compare_at_above_sell=True`. |
| **Tags & SEO Bounds** | `description_builder.py:725-816`, `config.py:47-51` | Vendor | **Level 1 → Level 2 → Level 3 → Level 4 (`SEOPolicy`, `TagPolicy`)** | Different platforms have different SEO title ceilings (e.g., Shopify recommends `<= 70` chars, DigiMall/Alfa allow `65–90`) and tag separators (comma-separated vs pipe-separated). |
| **Platform Attributes (`ALLOWED`, `SCOPE`, `ALIASES`)** | `attributes.py:27-269` | Hardcoded global for DigiMall | **Level 2 (`PlatformDefinition.attribute_schema`) + Level 4 (`CellOverride`)** | DigiMall uses 36 fixed `Attribute_*` columns with closed lists; WooCommerce uses dynamic `Attribute N name/value(s)` columns; Shopify uses `Option1..3` and `product.metafields.*`. |

---

## Section K — Future Platform Expansion Study (Shopify, WooCommerce and Beyond)

### 1. External Technical Evidence & Schema Comparison

#### A. Current Platforms (Repository Evidence: `writers.py:34-94`)
- **DigiMall (`DIGI_HEADER`, 66 columns)**:
  - **Row Cardinality**: `1:1` (1 input row → 1 output CSV row).
  - **Columns**: 28 `SHARED_PREFIX` columns (`Product ID`, `Title`, `Description`, `Vendor`, `Brands`, `Product Type`, `Category`, `Tags`, `SEO Title`, `SEO Description`, `Product Images`, `Option1 Name`, `Option1 Value`, `Option2 Name`, `Option2 Value`, `Option3 Name`, `Option3 Value`, `Variant SKU`, `Variant Barcode`, `Variant Weight`, `Variant Weight Unit`, `Variant Price`, `Variant Compare At Price`, `Variant Bin Number`, `Variant Quantity`, `Handle`, `Size Chart`, `Collection`) + `Short Description` + `Commission Percentage` + 36 `Attribute_*` columns.
  - **Brand & Category Format**: Numeric Brand ID (`Brands = "1986"`); full underscore-joined category path (`Category = "11639_11643_11661_11669"`).
- **Alfa (`ALFA_HEADER`, 28 columns)**:
  - **Row Cardinality**: `1:1` (1 input row → 1 output CSV row).
  - **Columns**: Exact 28 `SHARED_PREFIX` columns.
  - **Brand & Category Format**: Numeric Brand ID (`Brands = "6520"`); single leaf category ID (`Category = "11509"`).

#### B. Shopify Official Product CSV Format (External Technical Evidence)
- **Row Cardinality (`1:N` Handle-Grouped Multi-Row Model)**:
  - Shopify groups rows belonging to the same product by the **`Handle`** column.
  - **Row 1 (Primary Product + First Variant Row)**: Populates product-level columns (`Handle`, `Title`, `Body (HTML)`, `Vendor`, `Product Category`, `Type`, `Tags`, `Published`, `SEO Title`, `SEO Description`, `Status`), option names/values (`Option1 Name`, `Option1 Value`, `Option2 Name`, `Option2 Value`, `Option3 Name`, `Option3 Value`), first variant fields (`Variant SKU`, `Variant Grams`, `Variant Inventory Tracker`, `Variant Inventory Qty`, `Variant Inventory Policy`, `Variant Fulfillment Service`, `Variant Price`, `Variant Compare At Price`, `Variant Requires Shipping`, `Variant Taxable`, `Variant Barcode`, `Variant Weight Unit`), and first image (`Image Src`, `Image Position`, `Image Alt Text`, `Variant Image`).
  - **Rows 2..K (Additional Variant Rows for same `Handle`)**: Repeat `Handle`, **leave product-level columns (`Title`, `Body (HTML)`, `Vendor`, `Type`, `Tags`) blank**, and populate `Option1..3 Value`, `Variant SKU`, `Variant Price`, `Variant Inventory Qty`, `Variant Image`.
  - **Additional Image-Only Rows**: Repeat `Handle`, leave product and variant columns blank, and populate `Image Src`, `Image Position` (`2`, `3`, ...), `Image Alt Text`.
- **Key Column & Unit Differences vs DigiMall/Alfa**:
  - Description column is named **`Body (HTML)`** (not `Description`).
  - Product Type column is named **`Type`** (not `Product Type`).
  - Category column is named **`Product Category`** (uses Shopify Standard Product Taxonomy paths or IDs, e.g., `Home & Garden > Household Appliances > Climate Control Appliances > Air Conditioners`).
  - Weight is expressed in **`Variant Grams`** (numeric grams—so `17.25 kg` must be converted to `17250` while setting `Variant Weight Unit = "kg"`!).
  - Images use **`Image Src`** (one URL per row, ordered by `Image Position = 1, 2, ...`, unlike DigiMall/Alfa's `Product Images`).
  - Structured specs can also be projected to **`product.metafields.<namespace>.<key>`** columns.

#### C. WooCommerce Official Product CSV Import Schema (External Technical Evidence)
- **Row Cardinality (`1:1` for `simple` products; `1:N` Parent + Variation rows for `variable` products)**:
  - **Simple Product (`Type = "simple"`)**: Single row per product with `SKU`, `Name`, `Published` (`1`), `Is featured?` (`0`), `Visibility in catalog` (`visible`), `Short description`, `Description`, `Sale price`, `Regular price`, `Weight (kg)`, `Categories`, `Tags`, `Images`, `Brands`, and dynamic attribute columns (`Attribute 1 name`, `Attribute 1 value(s)`, `Attribute 1 visible`, `Attribute 1 global`, `Attribute 2 name`, ...).
  - **Variable Product (`Type = "variable"` + child `Type = "variation"` rows)**:
    - **Parent Row**: `Type = "variable"`, `SKU = "<parent_sku>"`, `Name = "<product_title>"`, `Description = "<html_table>"`, `Attribute 1 name = "Color"`, `Attribute 1 value(s) = "White, Meadow Green"`, `Attribute 1 visible = "1"`, `Attribute 1 global = "1"`, prices left blank.
    - **Child Variation Rows**: `Type = "variation"`, `SKU = "<variant_sku>"`, `Parent = "<parent_sku>"` (references parent by SKU or `id:<ID>`), `Regular price = "<compare_at>"`, `Sale price = "<sell_price>"`, `Attribute 1 name = "Color"`, `Attribute 1 value(s) = "White"`.
- **Key Column & Semantics Differences vs DigiMall/Alfa**:
  - Title column is **`Name`** (not `Title`).
  - SKU column is **`SKU`** (not `Variant SKU`).
  - Pricing inversion semantics: WooCommerce uses **`Regular price`** (always populated, equivalent to `Variant Compare At Price`) and **`Sale price`** (discounted price, equivalent to `Variant Price`).
  - Category hierarchy uses **`>`** with comma-separated multiple categories (e.g., `Home Appliances > Refrigerators`), not numeric IDs.
  - Attributes are **dynamic 4-column groups** (`Attribute 1 name`, `Attribute 1 value(s)`, `Attribute 1 visible`, `Attribute 1 global`), not 36 fixed `Attribute_*` columns.

### 2. How the Recommended `PlatformAdapter` Protocol Handles All Four Platforms Cleanly
To ensure adding Shopify or WooCommerce requires **zero changes to `CanonicalProductFacts` or extraction logic**, the `PlatformAdapter` protocol in `platforms/base.py` is designed around **batch projection (`Sequence[CanonicalProductFacts] -> list[ProjectedRow]`)** rather than assuming 1-to-1 row mapping:

```python
class PlatformAdapter(Protocol):
    platform_key: str
    display_name: str
    default_filename: str

    def header_for(self, records: Sequence[CanonicalProductFacts], cell_cfg: ResolvedCellConfig) -> tuple[str, ...]:
        """Return ordered CSV column headers (static 66/28 cols for Digi/Alfa, or dynamic Attribute N cols for WooCommerce)."""
        ...

    def project_all(
        self,
        records: Sequence[CanonicalProductFacts],
        cell_cfg: ResolvedCellConfig,
        flags: QCFlagCollector,
    ) -> list[ProjectedRow]:
        """Project canonical records into 1..N CSV rows per product (1:1 for Digi/Alfa; 1:N for Shopify/WooCommerce)."""
        ...

    def audit_file(
        self,
        source_rows: Sequence[InputRow],
        records: Sequence[CanonicalProductFacts],
        csv_header: Sequence[str],
        csv_rows: Sequence[Mapping[str, str]],
        cell_cfg: ResolvedCellConfig,
        flags: QCFlagCollector,
    ) -> list[AuditCheckResult]:
        """Run platform-specific schema and cell invariants against the written CSV."""
        ...
```

---

## Section L — Multi-Format Input and Output Architecture

### 1. Input Format Readers (`InputReader` Protocol)
- **Current State (`main.py:150-221`)**: `read_input(path)` supports `.csv` (`utf-8-sig`) and `.xlsx` (`openpyxl` active worksheet), requiring exact header names (`Title`, `Description`, `Sell Price`, `Original Price`, `Categories`, `Brand`, `Image`) and using `pick_weight_columns()` (`textutils.py:108-128`) for loose weight header matching.
- **Target Architecture**:
  - Introduce `InputColumnMapping` on `VendorDefinition` (Level 3) with default identity mapping to the 7 standard columns. If a new vendor supplies a sheet where `Sell Price` is named `"Discounted Price (PKR)"` or `Categories` is named `"Department"`, the vendor config maps `"sell_price": ("Sell Price", "Discounted Price (PKR)")` without preprocessing the sheet by hand.
  - Support `.csv` (auto-detecting `utf-8-sig` / `utf-8` / `cp1252` with a QC warning if non-UTF-8 mojibake was repaired), `.xlsx`, `.tsv`, and `.json`/`.jsonl` product feeds.

### 2. Output Format Writers (`OutputWriter` Protocol)
- **Current State (`writers.py:228-242`)**: Writes RFC-4180 CSV with UTF-8 BOM (`utf-8-sig`), `csv.QUOTE_ALL`, `\r\n` line endings, and single-line flattened cells (`_single_line`).
- **Target Architecture**:
  - Preserve `utf-8-sig` + `csv.QUOTE_ALL` + single-line HTML flattening as the default `CsvOutputWriter` (required by DigiMall and Alfa bulk importers so Excel on Windows never corrupts UTF-8 characters like `°C` or `—`).
  - Allow `PlatformDefinition` to specify `csv_encoding` (e.g., `"utf-8-sig"` vs `"utf-8"`), `csv_quoting` (`csv.QUOTE_ALL` vs `csv.QUOTE_MINIMAL`), or `.xlsx` workbook export when a marketplace requires Excel upload templates.

---

## Section M — Validation, Audit, Quality Gates and Observability

### 1. Three-Tier Verification Architecture

| Tier | When It Runs | Component | What It Verifies | Failure Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1: Startup Config & Conformance Gate** | Before reading row 1 (`< 50 ms`) | `validate_cell_config(cell_cfg)` | 1. Non-empty `sku_prefix` and `vendor_name` (and distinct `vendor_name` across platforms for the same vendor).<br>2. `title_formula` exists in `TITLE_FORMULAS` and renders `CONFORMANCE_SLOTS` without error or exceeding `TITLE_MAX`.<br>3. `description_template` exists in `DESCRIPTION_TEMPLATES` and passes `template_problems()` (round-trip `extract(render(rows)) == rows`, HTML escaping on `ESCAPE_PROBE`, tag nesting stack check, entity check, single-line check) **for EVERY active platform, not just `digi`**.<br>4. Active platform's `brands` and `categories` maps are non-empty (or raises an explicit `ConfigError` if a user runs `--vendor ajmer --platform digi` while `Ajmer.digi.categories` is still `{}`!). | Raises `ConfigError` listing **all** configuration defects across all requested cells in one message; writes **zero** files to disk. |
| **Tier 2: Row-Level QC Collector** | During `resolve_row()` & `project_cell()` | `QCFlagCollector` (`qc_report.py`) | Records `review` flags (`category_missing_*`, `brand_missing_*`, `attribute_empty`, `price_inversion`, `title_description_conflict`, `series_believed_from_one_row`, `input_error`, `weight_unreadable`) and `info` flags (`quantity_defaulted`, `compare_at_derived`, `warranty_fallback`, `fallback_sku`, `title_kept`, `seo_title_length`, `seo_description_length`, `thin_description`). | Never crashes the run; leaves unmappable closed-list cells blank and logs actionable human remediation instructions in `qc_report.csv`. |
| **Tier 3: Independent Post-Write Upload Gate** | After CSVs are written (`audit.py`) | `audit.run_audit(cell_configs, ...)` | Re-reads the physical CSV files from disk and verifies **for every generated platform file**:<br>1. File exists, UTF-8-sig readable, header matches `adapter.header_for(...)`, row count matches input.<br>2. Every cell is single-line, no raw `\n`/`\r`, no mojibake, no double spaces.<br>3. `Vendor` column equals `cell_cfg.vendor_name`; `Category` and `Brands` exist in `cell_cfg.categories` / `cell_cfg.brands` (or are blank with a corresponding `qc_report.csv` flag).<br>4. `Variant SKU`, `Variant Barcode`, `Variant Bin Number` start with `f"{cell_cfg.sku_prefix}-"` and are 100% unique across the file.<br>5. `Variant Compare At Price > Variant Price` (unless `price == 0` with `input_error` flag).<br>6. **Template-aware Description audit**: Calls `cell_cfg.description_template.extract(desc)` to verify zero empty values, zero duplicate labels, warranty row bolding, and zero invented spec values.<br>7. **Cell-aware Title, Weight, Colour, and Freezer audit**: Runs on **every** generated platform file using `cell_cfg` (fixing the `primary = files[0]` bug in `audit.py:235`). | Prints structured PASS/FAIL checklist, writes `row_check.csv`, and exits with code `1` if any check failed. |

### 2. Eliminating Module-Global State in `audit.py`
- **Repository evidence**: `audit.py:67` declares `RESULTS: list[tuple[bool, str, str]] = []` at module scope and mutates it via `check()` (`lines 70-72`). Tests in `test_audit.py:72` have to manually call `audit.RESULTS.clear()` before invoking `audit.main()`.
- **Architectural recommendation**: Encapsulate audit state in an `AuditSession` instance returned by `run_audit(...) -> AuditSession`, keeping `audit.RESULTS` only as a backwards-compatible alias updated at the end of `audit.main()` so existing tests in `test_audit.py` continue to pass unchanged.

---

## Section N — Testing Architecture and Verification Strategy

### 1. Forensics of the Existing Test Suite (`599` Tests across `22` Files)
- **Repository evidence**:
  - The repository has a strong pytest suite (`599` test functions) adhering to `.agents/rules/dry_dynamic_algorithm.md`:
    - `test_vendor_config.py` (`23` tests, `589` lines): Iterates dynamically over `VENDOR_REGISTRY`, testing brand/category isolation, SKU prefixing, startup validation refusals (`_LOSSY`, `_CRASHING`, `_CROSSED`), and end-to-end CLI + audit runs.
    - `test_description_templates.py` (`60` tests, `1,270` lines): Tests round-trip `extract(render(rows)) == rows` across all rows of the real sheets, HTML entity/quote/tag injection differential probes, DOM tag-nesting stack validation, and `KIACHAHIYE_ALFA_CARD` rendering.
    - `test_description_isolation.py` (`9` tests, `327` lines): Proves across all 4 cells (`{kiachahiye, ajmer} × {digi, alfa}`) that mutating one cell's `description_template` changes **only** that cell's SHA-256 output digest while leaving the other 3 cells byte-identical.
    - `test_title_builder.py` (`110` tests, `2,209` lines), `test_series_corpus.py` (`101` tests, `2,053` lines), `test_corpus_wiring.py` (`29` tests, `971` lines), `test_writers.py` (`43` tests, `596` lines), `test_audit.py` (`23` tests, `556` lines), `test_description_builder.py` (`32` tests, `531` lines), `test_textutils.py` (`28` tests, `312` lines), `test_acceptance_examples.py` (`15` tests, `293` lines).

### 2. Gaps in the Current Test Suite & Required New Contract Tests
1. **Gap 1 — Unwired `VendorConfig` Knobs Not Tested End-to-End**:
   - No test in `test_vendor_config.py` overrides `omit_title_color_categories` or `apply_tv_warranty_table` on a `VendorConfig` and runs `pipeline(rows, vendor_cfg=cfg)`—which is why both fields remained unwired in `main.py`!
   - **New Test Contract**: Add `test_all_vendor_config_knobs_affect_pipeline_and_pass_audit()`, dynamically overriding every field of `ResolvedCellConfig` (`sku_prefix`, `vendor_name`, `title_formula`, `description_template`, `omit_title_color_categories`, `apply_tv_warranty_table`, `default_product_type_colors`, `default_variant_quantity`, `seo_title_min/max`, `seo_desc_min/max`) and asserting both output change and `audit.main() == 0`.
2. **Gap 2 — Title Isolation Across All 4 `(Vendor × Platform)` Cells (Scenarios A–D)**:
   - `test_description_isolation.py` proves 4-cell isolation for Description templates, but there is no `test_title_isolation.py` proving Scenarios A, B, C, and D for Title formulas.
   - **New Test Contract**: Add `test_editing_one_cells_title_formula_moves_only_that_file()` parametrized over `CELLS = [(store, platform) for store in VENDOR_REGISTRY for platform in PLATFORMS]`.
3. **Gap 3 — `audit.py` and `thin_report.py` on Non-`SPEC_TABLE` Templates (`KIACHAHIYE_ALFA_CARD`)**:
   - In `test_description_templates.py:1034-1041`, a comment explicitly notes that `audit.py`'s evidence counter and `thin_report.py`'s `_SPEC_ROW_RE` were still hardcoded to `spec_table`.
   - **New Test Contract**: Parametrize `test_audit_and_thin_report_count_exact_spec_rows()` over **every** template in `DESCRIPTION_TEMPLATES` (`spec_table`, `kiachahiye_alfa_card`, and any future template).

---

## Section O — SaaS and Commercialization Readiness

### 1. Pragmatic Path from Local CLI to Multi-Tenant SaaS
Per Section 1 and Section 16 of the prompt, we **must not** prematurely build cloud infrastructure, databases, or auth into the CLI repository today, **but** we must structure the core engine so it can be wrapped by a FastAPI web service or background worker (`Celery` / `RQ` / `Cloud Run Jobs`) with zero refactoring of the core modules.

### 2. Three Architectural Boundaries Required Now for Future SaaS
1. **Stateless Execution Boundary (`run_job(request: PipelineJobRequest) -> PipelineJobResult`)**:
   - Eliminate all module-level mutable state (`audit.RESULTS` in `audit.py:67`) and process-global `@lru_cache` functions that read global tables (`series_corpus.py:161-196`).
   - Cache derived vocabularies on the immutable `VendorCatalog` / `ResolvedCellConfig` instance (or key `@lru_cache` by `cell_cfg.cache_key`), making concurrent multi-tenant runs inside one Python worker process 100% thread- and async-safe.
2. **Storage-Agnostic Stream / Path Interface**:
   - Keep `read_input()` and `write_csv()` accepting either `Path` or file-like streams (`io.TextIOBase` / `io.BytesIO`), so a future FastAPI endpoint can stream uploaded sheets from S3/GCS or memory without relying on hardcoded local `data/output/<sheet>/` paths.
3. **Serializable Configuration Packs**:
   - Because `ResolvedCellConfig` separates data dictionaries (`brands`, `categories`, `warranty_terms`, `default_product_type_colors`, `seo_*`, `pricing_*`) from registered strategy names (`title_formula: str`, `description_template: str`, `platform_key: str`), a future SaaS database (PostgreSQL / JSONB) can store a tenant's configuration as a pure JSON document that hydrates directly into `ResolvedCellConfig` and looks up `TITLE_FORMULAS[name]` and `DESCRIPTION_TEMPLATES[name]` in Python!

---

## Section P — Detailed Design of the Recommended Architecture

### 1. Exact Data Contracts (`models.py` & `configs/schema.py`)

```python
@dataclass(frozen=True)
class TitleFormulaSpec:
    """A named, reusable Title formula strategy."""
    name: str
    render: Callable[[TitleSlots, ResolvedCellConfig], TitleResult]
    max_length: int = 195


@dataclass(frozen=True)
class PricingPolicy:
    """Per-cell pricing and inventory fallback policy."""
    default_variant_quantity: int = 20
    compare_at_markup_ratio: float = 0.10
    round_compare_at_by_magnitude: bool = True


@dataclass(frozen=True)
class SEOPolicy:
    """Per-cell SEO Title and SEO Description length bounds and suffix."""
    title_min: int = 65
    title_max: int = 90
    title_suffix: str = " Price in Pakistan"
    desc_min: int = 120
    desc_max: int = 155


@dataclass(frozen=True)
class CellConfig:
    """Configuration for one (vendor, platform) cell in VendorConfig."""
    vendor_name: str
    brands: Mapping[str, int | str] = field(default_factory=dict)
    categories: Mapping[str, str] = field(default_factory=dict)
    inherit_platform_brands: bool = True
    title_formula: str | TitleFormulaSpec | None = None          # None => inherit from Vendor -> Platform -> Default
    description_template: str | DescriptionTemplate | None = None # None => inherit from Vendor -> Platform -> Default
    omit_title_color_categories: frozenset[str] | None = None
    apply_tv_warranty_table: bool | None = None
    default_product_type_colors: Mapping[str, str] | None = None
    pricing_policy: PricingPolicy | None = None
    seo_policy: SEOPolicy | None = None
```

### 2. Backwards Compatibility with Existing `VendorConfig.digi` and `VendorConfig.alfa`
To ensure **zero breakage** of the 599 existing tests (`cfg.digi.vendor_name`, `cfg.alfa.description_template`, `dataclasses.replace(cfg, alfa=...)`), `VendorConfig` retains `.digi` and `.alfa` fields (or properties synced with `platforms: Mapping[str, CellConfig]`) and adds:
- `PlatformConfig.title_formula: str | Callable[..., str] | None = None` (allowing per-cell title formula overrides on `cfg.digi` or `cfg.alfa`!).
- `PlatformConfig.omit_title_color_categories: frozenset[str] | None = None`
- `PlatformConfig.apply_tv_warranty_table: bool | None = None`
- `VendorConfig.resolve_cell(platform: str) -> ResolvedCellConfig`: Resolves the inheritance chain `EngineDefaults → PlatformDefinition[platform] → VendorConfig → PlatformConfig` in one deterministic call.

### 3. Fixing Title & Description Projection in `writers.py`
In `writers.py`:
- `_shared_cells(record: ProductRecord, vendor_cfg: VendorConfig | None, platform: str)` is updated to receive `platform: str` (just as `_description_cell` already does at `writers.py:142`!).
- When `cell_cfg = resolve_cell(vendor_cfg, platform)` has a cell-specific `title_formula` (or `omit_title_color_categories` / `apply_tv_warranty_table`) that differs from the record's default, `_title_cell(record, vendor_cfg, platform)` renders the title for that specific `(vendor, platform)` cell from the record's extracted tokens, while keeping every extracted fact single-sourced on `ProductRecord`!

---

## Section Q — Configuration File Examples

### Example 1: Shared Platform Defaults + Store Definitions (`vendor_config.py` with Inheritance & Zero Duplication)

```python
# Level 2: Shared Alfa Platform Defaults (defined ONCE, inherited by stores)
ALFA_BASE_BRANDS: Mapping[str, int] = {
    "dawlance": 6520, "gree": 6352, "haier": 5999, "hisense": 7060,
    "kenwood": 6519, "midea": 6521, "orient": 6522, "pel": 6980,
    "samsung": 2127, "tcl": 6353, "waves": 6523, "xioami": 6589,
    "ankex": 7066, "ecovacs": 6861,
}

# Level 3 & 4: Kiachahiye Store Definition
KIACHAHIYE = VendorConfig(
    display_name="Kiachahiye",
    sku_prefix="KC",
    title_formula="vip_pipe",                  # Level 3: Vendor default for all Kiachahiye platforms
    digi=PlatformConfig(                       # Level 4: Kiachahiye.digi cell
        vendor_name="KiaChahiye PVT LTD",
        description_template="spec_table",
        brands={...},                          # 29 DigiMall brand IDs
        categories={...},                      # 34 DigiMall category paths
    ),
    alfa=PlatformConfig(                       # Level 4: Kiachahiye.alfa cell
        vendor_name="Kia Chahiye Pvt Ltd",
        description_template="kiachahiye_alfa_card",  # Scenario D: Cell-specific card template
        brands=ALFA_BASE_BRANDS,               # Zero copy-paste duplication!
        categories={...},                      # 26 Alfa leaf IDs
    ),
)

# Level 3 & 4: Ajmer Store Definition
AJMER = VendorConfig(
    display_name="Ajmer",
    sku_prefix="AE",
    title_formula="standard",                  # Level 3: Vendor default for all Ajmer platforms
    digi=PlatformConfig(                       # Level 4: Ajmer.digi cell
        vendor_name="Ajmer Electronics PVT LTD",
        description_template="spec_table",
        brands={},
        categories={},
    ),
    alfa=PlatformConfig(                       # Level 4: Ajmer.alfa cell
        vendor_name="Ajmer Electronics",
        description_template="spec_table",     # Scenario A: Shares "spec_table" with DigiMall cells
        brands={
            **ALFA_BASE_BRANDS,
            "dawlance": 7061,                  # Store-specific override on top of base Alfa brands
            "super asia": 6913,
            "enviro": 7062,
            "homage": 6959,
        },
        categories={...},
    ),
)
```

### Example 2: Demonstrating Scenarios A, B, C, and D for Both Titles and Descriptions

```python
# Scenario A: Two vendors share the same Title formula ("standard") and Description template ("spec_table") on Alfa
ajmer_alfa = resolve_cell("ajmer", "alfa")
metro_alfa = resolve_cell("metro", "alfa")
assert ajmer_alfa.title_formula is metro_alfa.title_formula          # Both -> TITLE_FORMULAS["standard"]
assert ajmer_alfa.description_template is metro_alfa.description_template  # Both -> DESCRIPTION_TEMPLATES["spec_table"]

# Scenario B: One vendor (Kiachahiye) reuses "vip_pipe" across both DigiMall and Alfa
kc_digi = resolve_cell("kiachahiye", "digi")
kc_alfa = resolve_cell("kiachahiye", "alfa")
assert kc_digi.title_formula is kc_alfa.title_formula                # Both -> TITLE_FORMULAS["vip_pipe"]

# Scenario C: One platform (e.g., Shopify) sets a platform-wide default Title formula ("shopify_clean")
# while DigiMall and Alfa use "standard"
shopify_cell = resolve_cell("ajmer", "shopify")
assert shopify_cell.title_formula.name == "shopify_clean"

# Scenario D: Kiachahiye.alfa overrides EITHER description_template OR title_formula without affecting
# Kiachahiye.digi, Ajmer.digi, or Ajmer.alfa
kc_custom = dataclasses.replace(
    KIACHAHIYE,
    alfa=dataclasses.replace(
        KIACHAHIYE.alfa,
        title_formula="brand_first_extended",
        description_template="kiachahiye_alfa_card",
    ),
)
```

---

## Section R — Concrete Developer Workflows (All 22 Scenarios)

Below are the exact, step-by-step developer workflows in the recommended architecture, specifying **files touched**, **files untouched**, and **automated verification**.

### Workflow 1: Add a New Vendor (`Metro`) Using Existing Platforms (`digi`, `alfa`)
- **Files Modified**: `vendor_config.py` (1 file).
- **Files Untouched**: `main.py`, `writers.py`, `title_builder.py`, `description_builder.py`, `audit.py`, `run_ui.py`, `tests/*`.
- **Steps**:
  1. In `vendor_config.py`, define `METRO = VendorConfig(display_name="Metro", sku_prefix="MT", title_formula="standard", digi=PlatformConfig(...), alfa=PlatformConfig(...))`.
  2. Register `"metro": METRO` in `VENDOR_REGISTRY`.
- **Automated Verification**: `validate_vendor_cfg(METRO)` runs automatically on import; `pytest` automatically includes `"metro"` in all `VENDOR_REGISTRY` loops in `test_vendor_config.py`, `test_description_isolation.py`, and `test_run_ui.py`.

### Workflow 2: Add a New Destination Platform (e.g., `Daraz` — 1:1 Flat CSV)
- **Files Modified**: New `platforms/daraz.py` + register in `PLATFORM_REGISTRY` (`platforms/__init__.py`) + add `daraz` cell config to stores that sell on Daraz.
- **Files Untouched**: `series_corpus.py`, `sku_handle.py`, `warranty.py`, `pricing.py`, `textutils.py`, `title_builder.py`, `description_builder.py`.
- **Steps**:
  1. Implement `DarazAdapter` in `platforms/daraz.py` defining `DARAZ_HEADER`, `project_all()`, and platform-specific audit checks.
  2. Register `"daraz": DarazAdapter()` in `PLATFORM_REGISTRY`.
  3. Add `"daraz": CellConfig(...)` to the vendor's `platforms` map.
- **Automated Verification**: Parametrized platform schema and isolation tests automatically run against `"daraz"`.

### Workflow 3: Add `Shopify` as a Platform (`1:N` Handle-Grouped Variant & Image Rows)
- **Files Modified**: New `platforms/shopify.py` + register in `PLATFORM_REGISTRY`.
- **Files Untouched**: All core extraction modules (`series_corpus.py`, `sku_handle.py`, `warranty.py`, `title_builder.py`, `description_builder.py`).
- **Steps**:
  1. Implement `ShopifyAdapter` in `platforms/shopify.py` with Shopify's official header (`Handle`, `Title`, `Body (HTML)`, `Vendor`, `Product Category`, `Type`, `Tags`, `Published`, `Option1 Name`, `Option1 Value`, `Variant SKU`, `Variant Grams`, `Variant Inventory Qty`, `Variant Price`, `Variant Compare At Price`, `Image Src`, `Image Position`, `SEO Title`, `SEO Description`, `Status`).
  2. In `ShopifyAdapter.project_all()`, group records sharing a product group (or emit 1 primary row + N additional image rows per `CanonicalProductFacts`), converting `kg` to `Variant Grams` (`float(weight) * 1000`).
  3. Implement `ShopifyAdapter.audit_file()` verifying Handle grouping, blank `Title`/`Body (HTML)` on child rows, and `Variant Grams` numeric conversion.

### Workflow 4: Add `WooCommerce` as a Platform (`simple` / `variable` / `variation` + Dynamic `Attribute N` Columns)
- **Files Modified**: New `platforms/woocommerce.py` + register in `PLATFORM_REGISTRY`.
- **Files Untouched**: All core extraction modules.
- **Steps**:
  1. Implement `WooCommerceAdapter` in `platforms/woocommerce.py`.
  2. In `header_for(records, cell_cfg)`, compute the maximum number of populated `spec_rows` / attributes across the batch and append `Attribute N name`, `Attribute N value(s)`, `Attribute N visible`, `Attribute N global` columns dynamically.
  3. Map `Variant Compare At Price -> Regular price`, `Variant Price -> Sale price`, `Short Description -> Short description`, `Description -> Description`, and `Categories` using ` > ` hierarchy.

### Workflow 5: Change `Kiachahiye.alfa` Description Template Only (Scenario D)
- **Files Modified**: `vendor_config.py` (1 line: `KIACHAHIYE.alfa.description_template = "<template_name>"`).
- **Files Untouched**: All other files (`Kiachahiye.digi`, `Ajmer.digi`, `Ajmer.alfa` remain 100% byte-identical).
- **Automated Verification**: `pytest tests/test_description_isolation.py` verifies via SHA-256 digest that only `kiachahiye.alfa` changed.

### Workflow 6: Share One Description Template Between `Kiachahiye.alfa` and `Ajmer.alfa` (Scenario A)
- **Files Modified**: `vendor_config.py` (set `description_template="kiachahiye_alfa_card"` on `AJMER.alfa`, or set it on `PlatformDefinition("alfa")` so both inherit it).
- **Files Untouched**: `description_builder.py`, `writers.py`, `main.py`.
- **Automated Verification**: `test_a_template_may_be_shared_by_name_across_stores` (`test_vendor_config.py:408-416`).

### Workflow 7: Share One Description Template Across `Ajmer.digi` and `Ajmer.alfa` (Scenario B)
- **Files Modified**: `vendor_config.py` (set `description_template="spec_table"` at `AJMER` vendor level; leave cell overrides as `None` to inherit).
- **Files Untouched**: All engine modules.

### Workflow 8: Change `Kiachahiye.digi` Title Formula Only (Scenario D)
- **Files Modified**: `vendor_config.py` (1 line: set `title_formula="vip_pipe"` on `KIACHAHIYE.digi` while `KIACHAHIYE.alfa` sets `title_formula="standard"`).
- **Files Untouched**: `title_builder.py`, `main.py`, `writers.py`, `audit.py`.
- **Automated Verification**: `test_title_isolation.py` verifies via SHA-256 digest that only `kiachahiye.digi`'s `Title` column changed while `kiachahiye.alfa`, `ajmer.digi`, and `ajmer.alfa` remain byte-identical.

### Workflow 9: Share One Title Formula Across `Kiachahiye.digi` and `Ajmer.digi` (Scenario A)
- **Files Modified**: `vendor_config.py` (set `title_formula` on `PlatformDefinition("digi")` or on both `.digi` cells).
- **Files Untouched**: `title_builder.py`, `main.py`, `writers.py`.

### Workflow 10: Add a New Reusable Title Formula (e.g., `"compact_dash"`)
- **Files Modified**: `title_builder.py` (add `_formula_compact_dash(slots, cell_cfg)` and register `"compact_dash"` in `TITLE_FORMULAS`).
- **Files Untouched**: `main.py`, `writers.py`, `audit.py`, `vendor_config.py` (until a cell opts in).
- **Automated Verification**: Startup validator and `test_title_formula_strategies` automatically test every entry in `TITLE_FORMULAS` against `CONFORMANCE_SLOTS` and length bounds (`<= 195`).

### Workflow 11: Add a New Reusable Description Template (e.g., `"modern_grid"`)
- **Files Modified**: `description_builder.py` (add `MODERN_GRID = DescriptionTemplate(name="modern_grid", render=..., extract=..., starts_with=..., ends_with=...)` and register in `DESCRIPTION_TEMPLATES`).
- **Files Untouched**: `main.py`, `writers.py`, `audit.py`, `thin_report.py`.
- **Automated Verification**: `test_description_templates.py` automatically runs all round-trip, escaping, tag-nesting, entity, and `audit.py`/`thin_report.py` spec-row count tests on every registered template in `DESCRIPTION_TEMPLATES`.

### Workflow 12: Add a New Brand (`"Changhong Ruba"`)
- **Files Modified**: `vendor_config.py` (add brand ID to the store's `digi.brands` / `alfa.brands`, plus optional alias in `brand_aliases` and display casing in `brand_display_map`).
- **Files Untouched**: `brands.py`, `series_corpus.py`, `title_builder.py`, `main.py`, `audit.py`.
- **Automated Verification**: Because `series_corpus.py` reads `cell_cfg.brands` instead of global `brands.py`, the new brand is immediately recognized by both brand resolution and corpus voting.

### Workflow 13: Add a New Category Mapping (`"Air Fryer"`)
- **Files Modified**: `vendor_config.py` (add `"air fryer"` path/ID to store's `digi.categories` and `alfa.categories`; if new product type, add `"air fryer": "Air Fryer"` to shared `PRODUCT_TYPE_MAP`).
- **Files Untouched**: `categories.py` logic, `main.py`, `writers.py`, `audit.py`.

### Workflow 14: Add or Change Warranty Rules for a Brand or Category
- **Files Modified**: `warranty_terms.py` (for universal manufacturer terms) or `vendor_config.py` (for store/cell-specific `warranty_terms` override or `apply_tv_warranty_table=False`).
- **Files Untouched**: `warranty.py`, `main.py`, `title_builder.py`, `audit.py`.

### Workflow 15: Add or Change Platform Attribute Mappings (e.g., New Allowed Value `"18 Cu Ft"` or Alias)
- **Files Modified**: `attributes.py` (add literal to `ALLOWED["Attribute_Capacity"]` or alias to `ALIASES["Attribute_Capacity"]`).
- **Files Untouched**: `main.py`, `writers.py`, `audit.py`, `series_corpus.py` (automatically picks up new class phrases from `attributes.ALLOWED`).

### Workflow 16: Add or Change Tag Generation Rules
- **Files Modified**: `vendor_config.py` (configure `TagPolicy(min_tags=5, max_tags=8, include_price_in_pakistan=True)` on `VendorConfig` or `PlatformConfig`) or `description_builder.py:build_tags`.
- **Files Untouched**: `main.py`, `writers.py`.

### Workflow 17: Add or Change Default / Fallback Values (`default_variant_quantity`, `default_product_type_colors`)
- **Files Modified**: `vendor_config.py` (edit `default_variant_quantity` or `default_product_type_colors` on store or cell).
- **Files Untouched**: `config.py`, `main.py`, `pricing.py`, `audit.py` (since `audit.py` reads `cell_cfg.default_product_type_colors`).

### Workflow 18: Add a New Input Column Mapping (e.g., Vendor Sheet Uses `"Sale Price"` Instead of `"Sell Price"`)
- **Files Modified**: `vendor_config.py` (add `input_column_aliases={"Sell Price": ("Sale Price",)}` on the store's `VendorConfig`).
- **Files Untouched**: `main.py`, `writers.py`, `audit.py`.

### Workflow 19: Add a New Output Column for One Platform
- **Files Modified**: The platform's adapter file (e.g., `platforms/digimall.py` header tuple + row dictionary + `test_output_schema.py` contract literal).
- **Files Untouched**: All other platform adapters and core extraction modules.

### Workflow 20: Run Validation and Tests Before Release
- **Commands**:
  1. `ruff check .` (static lint verification per `ruff.toml`).
  2. `pytest` (runs all 599+ unit, conformance, isolation, and end-to-end audit tests).
  3. `python3 main.py --input "data/input/Step 1.csv" --vendor kiachahiye --platform both` followed by `python3 audit.py --input "data/input/Step 1.csv" --vendor kiachahiye --platform both`.

### Workflow 21: Onboard a Non-Appliance Product Vertical (e.g., Mobile Phones / Laptops)
- **Files Modified**:
  1. `vendor_config.py` / `shared/product_types.py`: Add `"smartphones": "Smartphone"`, `"laptops": "Laptop"` to `PRODUCT_TYPE_MAP` and store category maps.
  2. `sku_handle.py`: Add `"Smartphone": frozenset({"GB", "TB", "Inch"})` to `CAPACITY_UNITS`.
  3. `title_builder.py`: Add `"Smartphone"` subtype groups (`5G`, `Dual SIM`, `Official PTA Approved`) to `SUBTYPES`.
  4. `warranty_terms.py`: Add brand warranty terms (`"1 Year Official PTA Warranty"`).
- **Files Untouched**: `main.py`, `writers.py`, `description_builder.py`, `pricing.py`, `qc_report.py`, `audit.py`, `thin_report.py`.

### Workflow 22: Wrap the Engine in a Future FastAPI SaaS Endpoint
- **Files Modified**: New `api/app.py` (outside or alongside CLI entry points) calling `execute_pipeline_job(request: PipelineJobRequest) -> PipelineJobResult`.
- **Files Untouched**: All core extraction, rendering, platform adapter, and verification modules.

---

## Section S — Architecture Decision Register (ADR)

| Decision ID | Decision Topic | Chosen Option | Rejected Options | Repository & Technical Evidence | Migration Cost | Future Reversibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ADR-01** | **Overall Architecture Style** | **Layered Hybrid Architecture** (Python Core + `ResolvedCellConfig` + `PlatformAdapter` + Shared Data Packs) | 1. Pure Python Dataclass Monolith<br>2. Pure YAML/Jinja2 DSL<br>3. Dynamic Hook/Plugin Bus | `title_builder.py` (2,466 lines) & `series_corpus.py` (1,479 lines) contain algorithmic linguistic rules that fail in YAML/Jinja2, while `vendor_config.py` (452 lines) has duplicated dicts that need hierarchical inheritance. | Low–Medium (4 incremental phases) | High (clean boundary between config data and Python strategies). |
| **ADR-02** | **Configuration Precedence Hierarchy** | **4-Level Deterministic Resolution**: `CellOverride(V,P) > Vendor(V) > Platform(P) > EngineDefaults` compiled into `ResolvedCellConfig` | 1. Flat per-vendor config only<br>2. Implicit fallback to `config.py` globals | Fixes split-brain bugs (`config.py:38-39`, unwired `omit_title_color_categories` at `main.py:376`, unwired `apply_tv_warranty_table` at `main.py:427`) and eliminates duplicated `alfa.brands` dicts. | Low | High |
| **ADR-03** | **Title Formula Scoping & Execution Stage** | **Extract `TitleSlots` once in `resolve_row()`; render `Title` string per `(vendor, platform)` cell at projection time** | Compute single `ProductRecord.title: str` once per vendor in `resolve_row()` | Current `ProductRecord.title` (`main.py:376`) makes Scenarios C & D impossible for Titles and breaks `audit.py` if two platforms use different title formulas. | Low | High |
| **ADR-04** | **Description Template Representation & Escaping** | **Registered `DescriptionTemplate(render, extract)` with mandatory `html.escape(text, quote=True)`** | 1. Pre-rendered HTML on `ProductRecord`<br>2. `html.escape(text, quote=False)`<br>3. Unvalidated raw Jinja2 strings | `quote=False` (`description_builder.py:256, 427`) is unsafe in attribute contexts; pairing `render` with `extract` enables automated startup round-trip verification (`template_problems`). | Trivial | High |
| **ADR-05** | **Audit & Thin-Report HTML Inspection** | **Delegate spec-row extraction in `audit.py` and `thin_report.py` to `cell_template.extract(html)`** | Hardcoded regexes (`r"<tr><td[^>]*>"`, `<th `, `count("<tr") - 1`) | Current regexes in `audit.py:409, 706` and `thin_report.py:36` **fail on `KIACHAHIYE_ALFA_CARD`** because its `<tr style=...>` has an inline `style` attribute and its `<thead>` has 2 `<tr>` rows! | Low | High |
| **ADR-06** | **Multi-Platform Projection Abstraction** | **`PlatformAdapter` Protocol with `project_all(records, cell_cfg) -> list[ProjectedRow]` (supporting `1:1` and `1:N` rows)** | Hardcoded `build_digi_row(record)` and `build_alfa_row(record)` functions | Official Shopify CSVs require `1:N` Handle-grouped variant/image rows, and official WooCommerce CSVs require `1:N` `variable`/`variation` rows with `Parent` SKU references. | Medium | High |
| **ADR-07** | **Corpus Pre-Pass Vocabulary Scoping** | **Pass `VendorCatalog` into `read_rows()` / `series_corpus.py`; key caches by config hash instead of `@lru_cache(maxsize=1)` on global modules** | Global `@lru_cache(maxsize=1)` reading `brands.py` and `categories.py` (`series_corpus.py:161-196`) | Global caches ignore store-specific brands/categories in `vendor_config.py` and leak state across multi-vendor in-process runs. | Low | High |

---

## Section T — Migration Roadmap

The transition from the current split-brain state to the target architecture is designed as **4 incremental, non-breaking phases** where all 599 existing pytest tests stay green at every commit.

### Phase 0 — Immediate Bug & Split-Brain Remediation (1–2 Days, Zero Structural Risk)
1. **Wire dead `VendorConfig` fields**:
   - Pass `omit_color_categories=vendor_cfg.omit_title_color_categories` in `main.py:376` (`build_title(...)`).
   - Add `apply_tv_warranty_table: bool | None = None` parameter to `lookup_terms()`, `resolve_warranty()`, and `resolve_main_warranty()` in `warranty.py`, and pass `vendor_cfg.apply_tv_warranty_table` from `main.py:427` and `title_builder.py:2017`.
   - Pass `vendor_cfg` to `audit.py`'s SEO bounds (`SEO_TITLE_MIN/MAX`, `SEO_DESC_MIN/MAX`) and `DEFAULT_PRODUCT_TYPE_COLORS` (`audit.py:428-431, 650`).
2. **Fix `KIACHAHIYE_ALFA_CARD` & `audit.py` / `thin_report.py` regex mismatch**:
   - Update `audit.py:409, 494, 706` and `thin_report.py:36, 82` to use `template_for_cell(vendor_cfg, platform).extract(desc)`.
   - Upgrade `html.escape(..., quote=False)` to `html.escape(..., quote=True)` in `description_builder.py:256-257, 427-428`.
   - Run `audit.py`'s Title (`line 554`), Weight (`line 584`), Colour (`line 642`), and Freezer (`line 673`) loops over **all** audited `files`, not just `primary = files[0]`.
3. **Fix `series_corpus.py` vendor wiring**:
   - Pass `vendor_cfg` into `main.read_rows(rows, vendor_cfg)` and `series_corpus.analyze_row(..., vendor_cfg=vendor_cfg)`.

### Phase 1 — Hierarchical `ResolvedCellConfig` & Cell-Scoped Title Formulas (2–3 Days)
1. Introduce `ResolvedCellConfig` and `resolve_cell(vendor_cfg, platform)` implementing the 4-level hierarchy (`EngineDefaults → PlatformDefinition → VendorConfig → PlatformConfig`).
2. Add `title_formula: str | Callable[..., str] | None = None` to `PlatformConfig` (falling back to `VendorConfig.title_formula` when `None`).
3. Store `TitleSlots` on `ProductRecord` and add `title_for_cell(record, vendor_cfg, platform)` in `writers.py` so Titles can be customized at the `(vendor, platform)` cell level (unlocking Scenarios C and D for Titles with the exact same ergonomics as `description_template`).
4. Deduplicate `ALFA_BASE_BRANDS`, `DIGI_SEGMENT_ALIASES`, and `PRODUCT_TYPE_MAP` in `vendor_config.py`.
5. Add `tests/test_title_isolation.py` mirroring `tests/test_description_isolation.py` across all 4 cells.

### Phase 2 — Template-Aware Conformance & Multi-Template Support (2 Days)
1. Refactor `description_builder.py:template_problems()` so it validates round-trip `template.extract(clean_inline(template.render(...)))`, HTML escaping, tag nesting, and entity validity on **all** platform cells (`digi`, `alfa`, and future platforms), removing the `if platform == "digi":` skip in `vendor_config.py:436` and removing the artificial `<th ` trailing-space requirement.
2. Add `--platform` and `--vendor` flags to `thin_report.py` so thin-description worklists can be generated for Alfa-only runs as well as DigiMall runs.

### Phase 3 — `PlatformAdapter` Protocol & Multi-Row Expansion for Shopify / WooCommerce (3–5 Days)
1. Extract `DigiMallAdapter` and `AlfaAdapter` into `platforms/digimall.py` and `platforms/alfa.py` behind `PLATFORM_REGISTRY`, keeping `writers.build_digi_row` and `writers.build_alfa_row` as thin wrappers so all existing unit tests in `test_writers.py` and `test_output_schema.py` continue to pass unchanged.
2. Implement `ShopifyAdapter` (`platforms/shopify.py`) and `WooCommerceAdapter` (`platforms/woocommerce.py`) supporting `1:N` row expansion (`Handle`-grouped rows for Shopify; `variable`/`variation` rows with `Parent` SKU for WooCommerce).
3. Update CLI (`--platform`) and `run_ui.py` to discover registered platforms from `PLATFORM_REGISTRY`.

### Phase 4 — Stateless Job API & Externalized Data Packs for SaaS Readiness (Optional / On-Demand)
1. Replace `audit.RESULTS` global list with `AuditSession` and expose `execute_pipeline_job(PipelineJobRequest) -> PipelineJobResult`.
2. Support loading vendor brand/category/warranty packs from validated TOML/JSON documents alongside Python configs.

---

## Section U — Risk Register and Failure Modes

| Risk ID | Risk / Failure Mode | Severity | Likelihood | Concrete Repository Evidence | Mitigation Strategy |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **RISK-01** | **`KIACHAHIYE_ALFA_CARD` spec rows silently skipped by `audit.py` and miscounted as `0` by `thin_report.py`** | **High** | **Certain (Present Now)** | `description_builder.py:436` writes `<tr style="background-color:...">`, whereas `audit.py:409` matches `r"<tr><td[^>]*>"` and `thin_report.py:36` matches `r"<tr><td\b"`. Plus `KIACHAHIYE_ALFA_CARD` has 2 `<tr>` rows in `<thead>`, breaking `audit.py:706` (`count("<tr") - 1`). | Immediately switch `audit.py` and `thin_report.py` to call `template_for_cell(vendor_cfg, platform).extract(desc)` in Phase 0. |
| **RISK-02** | **Store-level `omit_title_color_categories` and `apply_tv_warranty_table` changes silently ignored** | **High** | **Certain (Present Now)** | `main.py:376` and `main.py:427` never pass these fields from `vendor_cfg` to `build_title()` or `resolve_warranty()`. | Wire both via `ResolvedCellConfig` in Phase 0 and add mandatory end-to-end knob tests in `test_vendor_config.py`. |
| **RISK-03** | **Running `--vendor ajmer --platform digi` or `both` ships 100% blank Categories and Brands on DigiMall** | **Medium** | **High** | `vendor_config.py:325-330` sets `AJMER.digi.brands = {}` and `AJMER.digi.categories = {}` with `# TODO: Populate Ajmer DigiMall brand IDs when onboarding to DigiMall`. | Add `enabled: bool = True` (or `active_platforms: tuple[str, ...] = ("alfa",)` on `AJMER`) and fail fast in `validate_vendor_cfg` if a user requests an unconfigured platform cell. |
| **RISK-04** | **`audit.py` fails valid store runs when a store customizes `seo_title_max` or `default_product_type_colors`** | **Medium** | **High** | `main.py:486, 562` reads these from `vendor_cfg`, but `audit.py:428, 650` reads them from `config.py` globals. | Pass `ResolvedCellConfig` into all `audit.py` checks in Phase 0. |
| **RISK-05** | **Cross-platform Title divergence breaks `audit.py` under `--platform both`** | **High** | **High (when Scenario C/D enabled for Titles)** | `audit.py:235, 554` only audits `Title` on `primary = files[0]` (DigiMall) and re-calls `build_title()` once per vendor rather than once per `(vendor, platform)` cell. | Audit `Title`, `Weight`, `Colour`, and `Freezer` inside the `for file_label, ... in files:` loop using each file's own `ResolvedCellConfig`. |
| **RISK-06** | **Multi-row platforms (Shopify / WooCommerce) break `len(output_rows) == len(source_rows)` assumption in `audit.py:242`** | **Medium** | **Medium (Phase 3)** | `audit.py:242` checks `len(rows) == len(source)`. On Shopify/WooCommerce, 1 product with 3 variants or 4 images produces multiple CSV rows. | Delegate row-count and grouping verification to `PlatformAdapter.audit_file()` (e.g., checking unique `Handle` count or `Type in ("simple", "variable")` count == `len(source)`). |

---

## Section V — What Not To Build (Anti-Overengineering Guardrails)

1. **Do NOT replace `title_builder.py`, `series_corpus.py`, `warranty.py`, or `sku_handle.py` with a YAML/JSON Regex DSL**:
   - The 5,171 lines across those four modules encode hard-won empirical rulings from real 752-row and 1,800-row Pakistani appliance sheets (e.g., Dawlance `20FROST` = `1.25 Ton`, Haier `HSU-14HFT` != `1.25 Ton`, `Silver Line` as series vs `Silver Strip Black` as 3-word colourway, 1-edit-distance class typo suppression for `Inventer`). Moving this logic into YAML regex chains would destroy debuggability and type safety.
2. **Do NOT introduce Jinja2, Mako, or external HTML parser dependencies (`BeautifulSoup4`, `lxml`) for Description Templates**:
   - Python's standard library (`html.escape`, `html.unescape`, `html.entities.html5`, dataclasses, and `DescriptionTemplate(render, extract)`) executes 1,504 renders in `128 ms` (`test_description_isolation.py:234`) with zero external dependencies and mathematically provable round-trip extraction.
3. **Do NOT build a database, web UI, authentication system, or Celery queue inside this repository now**:
   - The current operator workflow (`run_pipeline.bat` → `run_ui.py` interactive terminal menu) is fast, offline-capable, and zero-ops. Prepare for SaaS solely by keeping `execute_pipeline_job()` stateless and side-effect-free.
4. **Do NOT use fuzzy string matching (`difflib`, Levenshtein) for Brand, Category, or Closed-List Attribute lookups**:
   - As pinned by `test_brands.py:63` (`test_no_fuzzy_matching_ever`) and `test_attributes.py:69` (`test_punctuation_is_never_rewritten`), guessing a closed-list marketplace ID corrupts live catalog listings. Unmatched values must always ship blank with a `qc_report.csv` review flag.

---

## Section W — Final Consolidated Recommendation

1. **Adopt Alternative 2 (Layered Hybrid Architecture)** as the single consolidated architecture for the CSV Generator.
2. **Execute Phase 0 immediately** upon implementation authorization to fix the five concrete repository defects uncovered by this forensic investigation:
   - Wire `vendor_cfg.omit_title_color_categories` (`main.py:376`) and `vendor_cfg.apply_tv_warranty_table` (`main.py:427`, `title_builder.py:2017`).
   - Fix `audit.py` (`lines 409, 494, 706`) and `thin_report.py` (`line 36`) to use `template_for_cell(vendor_cfg, platform).extract(desc)` so `KIACHAHIYE_ALFA_CARD` is properly audited and counted, and remove `if platform == "digi":` from `vendor_config.py:436`.
   - Fix `audit.py` (`lines 428, 554, 584, 642, 650, 673`) to read `vendor_cfg` thresholds/defaults and audit **every** generated platform file rather than only `files[0]`.
   - Pass `vendor_cfg` into `series_corpus.py` (`main.py:224, 722`).
   - Upgrade `html.escape(..., quote=False)` to `html.escape(..., quote=True)` in `description_builder.py:256-257, 427-428`.
3. **Execute Phases 1–3 sequentially** to introduce `ResolvedCellConfig` (4-level inheritance), cell-scoped `title_formula` projection (unlocking Scenarios C and D for Titles), and `PLATFORM_REGISTRY` (`PlatformAdapter` protocol ready for Shopify and WooCommerce).

---

## Section X — Comprehensive Traceability Appendix (File & Line Index)

| Subsystem | Primary File(s) & Exact Line Ranges | Key Symbols Inspected |
| :--- | :--- | :--- |
| **CLI & Row Orchestration** | `/kiachahiye_bulk_csv/main.py:150-221` (`read_input`), `224-258` (`read_rows`), `261-623` (`resolve_row`), `694-743` (`run`), `896-1041` (`main`) | `read_input`, `read_rows`, `resolve_row`, `run`, `print_summary`, `main` |
| **Multi-Vendor Config & Validation** | `/kiachahiye_bulk_csv/vendor_config.py:37-47` (`PlatformConfig`), `51-75` (`VendorConfig`), `84-296` (`KIACHAHIYE`), `315-371` (`AJMER`), `373-451` (`VENDOR_REGISTRY`, `validate_vendor_cfg`) | `PlatformConfig`, `VendorConfig`, `KIACHAHIYE`, `AJMER`, `VENDOR_REGISTRY`, `validate_vendor_cfg` |
| **Legacy Global Config** | `/kiachahiye_bulk_csv/config.py:38-39` (`VENDOR_DIGI`, `VENDOR_ALFA`), `47-56` (SEO & Qty), `66-80` (`DEFAULT_PRODUCT_TYPE_COLORS`, `OMIT_TITLE_COLOR_CATEGORIES`, `APPLY_TV_WARRANTY_TABLE`) | `VENDOR_DIGI`, `VENDOR_ALFA`, `OMIT_TITLE_COLOR_CATEGORIES`, `APPLY_TV_WARRANTY_TABLE` |
| **Domain Data Models** | `/kiachahiye_bulk_csv/models.py:16-36` (`InputRow`), `39-64` (`BrandResolution`, `CategoryResolution`), `67-97` (`SpecRow`, `DescriptionBundle`), `100-163` (`ProductRecord`, `ProjectedRow`) | `InputRow`, `SpecRow`, `DescriptionBundle`, `ProductRecord`, `ProjectedRow` |
| **Title Extraction & Formulas** | `/kiachahiye_bulk_csv/title_builder.py:1985-2067` (`build_title`), `2070-2177` (`_formula_standard`), `2180-2228` (`_formula_brand_first_extended`), `2231-2424` (`_formula_vip_pipe`), `2427-2431` (`TITLE_FORMULAS`) | `build_title`, `_formula_standard`, `_formula_brand_first_extended`, `_formula_vip_pipe`, `TITLE_FORMULAS` |
| **Description Parser, Templates & Conformance** | `/kiachahiye_bulk_csv/description_builder.py:251-271` (`_row_html`, `build_description_html`), `405-472` (`KIACHAHIYE_ALFA_CARD`), `822-916` (`DescriptionTemplate`, `DESCRIPTION_TEMPLATES`, `template_for`), `919-1012` (`template_problems`), `1106-1356` (`build_description_bundle`) | `DescriptionTemplate`, `SPEC_TABLE`, `KIACHAHIYE_ALFA_CARD`, `DESCRIPTION_TEMPLATES`, `template_problems`, `build_description_bundle` |
| **Whole-Sheet Series Learner** | `/kiachahiye_bulk_csv/series_corpus.py:161-196` (cached vocabularies), `542-635` (`analyze_row`), `1341-1376` (`Corpus`), `1416-1478` (`build_corpus`) | `normalize_shape`, `analyze_row`, `build_corpus`, `Corpus`, `pick_candidate` |
| **SKU, Handle & Capacity** | `/kiachahiye_bulk_csv/sku_handle.py:121-225` (`TONNAGE_BY_BRAND`), `257-350` (`parse_capacity`, `resolve_capacity`), `369-515` (`extract_model`), `562-680` (`build_sku_token`, `build_handle_token`, `UniqueRegistry`) | `extract_model`, `resolve_capacity`, `build_sku_token`, `build_handle_token`, `UniqueRegistry` |
| **Warranty Engine & Reference Terms** | `/kiachahiye_bulk_csv/warranty.py:109-151` (`lookup_terms`), `424-483` (`resolve_warranty`), `486-534` (`resolve_main_warranty`); `/kiachahiye_bulk_csv/warranty_terms.py:25-128` (`WARRANTY_TERMS`) | `lookup_terms`, `resolve_warranty`, `resolve_main_warranty`, `WARRANTY_TERMS` |
| **Brands, Categories & Attributes** | `/kiachahiye_bulk_csv/brands.py:130-192`; `/kiachahiye_bulk_csv/categories.py:257-441`; `/kiachahiye_bulk_csv/attributes.py:27-269, 392-470` | `resolve_brand`, `resolve_category`, `resolve_product_type`, `ALLOWED`, `SCOPE`, `build_attributes` |
| **Platform Projection & CSV Writer** | `/kiachahiye_bulk_csv/writers.py:34-94` (`SHARED_PREFIX`, `DIGI_HEADER`, `ALFA_HEADER`), `119-151` (`template_for_cell`, `_description_cell`), `193-242` (`build_digi_row`, `build_alfa_row`, `write_csv`) | `DIGI_HEADER`, `ALFA_HEADER`, `template_for_cell`, `build_digi_row`, `build_alfa_row`, `write_csv` |
| **Audit, QC & Thin Reports** | `/kiachahiye_bulk_csv/audit.py:173-738`; `/kiachahiye_bulk_csv/qc_report.py:86-194`; `/kiachahiye_bulk_csv/thin_report.py:36-227` | `audit.main`, `QCFlagCollector`, `thin_report.read_listing_facts`, `thin_report.classify` |

---

## Section Y — Self-Critique and Completeness Verification Against Prompt Contract

1. **Did we assume the current architecture is correct?**
   - No. By tracing every field of `VendorConfig` and `PlatformConfig` through `main.py`, `title_builder.py`, `warranty.py`, `series_corpus.py`, `writers.py`, `audit.py`, and `thin_report.py`, we uncovered **five concrete architectural defects** (including unwired `omit_title_color_categories` and `apply_tv_warranty_table`, global `@lru_cache` poisoning in `series_corpus.py`, `audit.py` ignoring `vendor_cfg` SEO/colour settings and skipping Alfa on Title/Weight/Colour/Freezer under `--platform both`, and `KIACHAHIYE_ALFA_CARD`'s `<tr style=...>` bypassing `audit.py:409` and `thin_report.py:36`).
2. **Did we evaluate all 4 sharing/isolation scenarios (Scenarios A, B, C, D) for BOTH Titles and Descriptions?**
   - Yes (Sections D, G, H, I, P, Q, R). We proved why Descriptions currently satisfy A–D (with the `audit.py` regex caveat) while Titles only satisfy A–B, and designed `TitleSlots` + `ResolvedCellConfig.title_formula` so Titles achieve 100% symmetry across Scenarios A, B, C, and D.
3. **Did we ground Shopify and WooCommerce expansion in official external schema rules?**
   - Yes (Section K), documenting Shopify's `Handle`-grouped `1:N` variant/image rows, `Body (HTML)`, and `Variant Grams`, and WooCommerce's `simple`/`variable`/`variation` row hierarchy, `Parent` SKU linkage, inverted `Regular price`/`Sale price` naming, and dynamic `Attribute N *` column groups.

---

## Section Z — Final Repository Integrity Confirmation

- **Repository Modification Policy**: Strictly observed (**RESEARCH ONLY — ZERO REPOSITORY FILES MODIFIED, CREATED, OR DELETED**).
- **End-of-Run Workspace Verification (`run_command` in `/app/applet`)**:
  1. `git status --short --branch`: Returns `fatal: not a git repository (or any of the parent directories): .git` (identical to baseline at start of run; disclosed in Section B.1).
  2. Full directory tree check (`find . -maxdepth 3 -not -path '*/.*' | sort`): Confirmed exact match with initial file tree:
     - Zero new `.py`, `.toml`, `.yaml`, `.json`, or `.csv` files created inside `/app/applet`.
     - Zero `.pyc`, `__pycache__`, or `.pytest_cache` artifacts created inside `/app/applet`.
     - All 19 production Python files and 22 test files in `/kiachahiye_bulk_csv/` remain completely untouched at their original byte counts and timestamps.
