# Vendor Title Formula Upgrade — Task Checklist (`tasks/todo.md`)

## Phase 1: Foundation — USP Extractor & `vip_pipe` Formula in `title_builder.py`
- [x] **Task 1: Add `usp_tokens` & `seo_base_title` to `TitleResult` and implement `extract_usps` in `title_builder.py`**
  - [x] Implement purely dynamic `extract_usps()` (zero hardcoding, reading exclusively from `parse_description` bullets, em-dashes, and non-generic spec labels)
  - [x] Deduplicate USP words against tokens already spoken in Segment 1
  - [x] Extend `TitleResult` dataclass with `usp_tokens: tuple[str, ...] = ()` and `seo_base_title: str = ""`
  - [x] Verify: `pytest tests/test_title_builder.py` and `ruff check title_builder.py`

- [x] **Task 2: Implement `"vip_pipe"` formula and slot wiring in `title_builder.py`**
  - [x] Populate `front_identity`, `back_model`, and `usps` in `build_title()`
  - [x] Handle Scenario A (Series in Position 3, Model Code in `| [Model Code] |`)
  - [x] Handle Scenario B (Popular Identity in Position 3, empty `back_model`)
  - [x] Handle Scenario C (Skip Position 3, Model Code in `| [Model Code] |`)
  - [x] Handle bracketed colors `([Color])` at end of Segment 1 (omitted for LED TV and empty colors)
  - [x] Handle 255-character budget protection so Model Code and Warranty are never cut off
  - [x] Update `_trim_to_limit()` to strip trailing `" ,-/|"`
  - [x] Register `"vip_pipe"` in `_apply_formula()`
  - [x] Verify: `pytest tests/test_title_builder.py` and `ruff check title_builder.py`

- [x] **Checkpoint 1: Foundation Verification**
  - [x] All existing tests pass
  - [x] Unit tests verifying Scenarios A, B, and C pass

---

## Phase 2: Pipeline Wiring & Vendor Configuration
- [x] **Task 3: Wire `seo_base_title` & Search-First Token Shedding in `main.py`**
  - [x] Pass `title_result.seo_base_title` to `build_description_bundle()`
  - [x] Protect core buyer search keywords (`Capacity`, `Series`, `Inverter`, `Model`) in `SEO Title` (65–90 chars)
  - [x] Verify: `pytest tests/test_corpus_wiring.py` and `ruff check main.py`

- [x] **Task 4: Configure `KIACHAHIYE` to `"vip_pipe"` and `AJMER` to `"standard"` in `vendor_config.py`**
  - [x] Set `KIACHAHIYE.title_formula = "vip_pipe"`
  - [x] Set `AJMER.title_formula = "standard"`
  - [x] Retain `"brand_first_extended"` for backward compatibility
  - [x] Verify: `pytest tests/test_vendor_config.py` and `ruff check vendor_config.py`

- [x] **Checkpoint 2: Core Pipeline Features**
  - [x] Full pytest suite passes (`python -m pytest tests -q` — 503 passed)
  - [x] Ruff linter clean (`python -m ruff check .`)
  - [x] Mypy type checks clean (`python -m mypy title_builder.py vendor_config.py main.py`)

---

## Phase 3: Comprehensive Testing & End-to-End Audit Gate
- [x] **Task 5: Add Multi-Vendor Title & Regression Unit Tests**
  - [x] Add unit tests for `vip_pipe` across AC, Refrigerator, Washing Machine, LED TV, Dispenser, Microwave
  - [x] Add unit tests for `standard` formula under `AJMER`
  - [x] Add unit tests for color brackets, budget clipping, and zero-invention compliance
  - [x] Verify: `pytest tests/ -q` (503 passed) and `mypy .`

- [x] **Task 6: Run Full End-to-End Pipeline & Audit Gate on Real Data**
  - [x] Run `main.py` with `--vendor kiachahiye` on `midea_eco_products.csv`
  - [x] Run `audit.py` with `--vendor kiachahiye` on generated outputs (48/48 checks PASSED)
  - [x] Run `main.py` with `--vendor ajmer --platform alfa` on `midea_eco_products.csv`
  - [x] Run `audit.py` with `--vendor ajmer --platform alfa` on generated outputs (35/35 checks PASSED)
  - [x] Run `main.py` + `audit.py` on 752-row `Products.csv` (48/48 checks PASSED, 0 failures)

- [x] **Checkpoint 3: Production Ready**
  - [x] 100% tests pass (503 passed in 11.3s)
  - [x] Zero audit failures across all sections
  - [x] Clean git status ready for commit
