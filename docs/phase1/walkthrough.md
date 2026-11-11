# Phase 1 implementation walkthrough

Completed M1.1–M1.4 against the supplied Antigravity **Rev 4** specification.
Implementation base: `84992682920ce4650f9db631a7292da189d06be4`.
After reviewing the implementation, the user authorized a local commit on branch
`the-new-way`. The commit identifier is available in Git history.

## Milestones

| Milestone | Result |
| --- | --- |
| M1.1 | Frozen ResolvedCellConfig; first non-None Cell > Vendor > Platform > Engine precedence; silent declarations; read-only mapping snapshots; effective-value validation/readers. Four registry cells explicitly retain their existing settings. |
| M1.2 | Exact warranty/Title/SEO characterization before refactoring; one TITLE_FORMULAS registry; frozen TitleSlots; separated extraction and per-cell rendering; unchanged build_title signature and formula results. |
| M1.3 | resolve_row extracts facts once per invocation and renders Title/SEO once per cell. Writers read existing record Title/SEO fields and select Description at write time. Audit reads resolved policy and ownership snapshots. |
| M1.4 | Dynamic precedence, falsy overrides, marketplace-ID ownership, template inheritance, Title/SEO isolation, back-to-back changes, formula coverage, call counts, writer no-rendering, and public-field compatibility. Fresh-context adversarial review findings fixed and verified. |

## Exact changed files and functions

Production changes:

- `kiachahiye_bulk_csv/vendor_config.py`: PlatformConfig, VendorConfig, CellDefaults,
  PLATFORM_DEFAULTS, ResolvedCellConfig, `_inherit`, `resolve_cell`, registry declarations,
  `_description_template_errors`, `validate_vendor_cfg`.
- `kiachahiye_bulk_csv/title_builder.py`: `_extract_usp_candidates`, `_select_usps`, the
  compatible `extract_usps` API; `_formula_standard`, `_formula_brand_first_extended`,
  `_formula_vip_pipe`, TITLE_FORMULAS, `_apply_formula`; TitleSlots, `extract_title_slots`,
  `_render_title`, `render_title_from_slots`, `render_title_and_seo_from_slots`, `build_title`.
- `kiachahiye_bulk_csv/main.py`: imports and `resolve_row` integration; resolved quantity,
  colour defaults, and SKU prefix. Existing run/collision passes are retained.
- `kiachahiye_bulk_csv/writers.py`: `template_for_cell`, `build_digi_row`, `build_alfa_row`
  use resolved configuration. Their Title/SEO and CSV serialization behavior is preserved.
- `kiachahiye_bulk_csv/audit.py`: `main` reads resolved vendor identity, quantity, mapping
  ownership, cell Title rules, colour defaults, and vendor warranty policy.
- `kiachahiye_bulk_csv/description_builder.py`: `build_description_bundle` accepts optional
  `resolved_seo_title`; independent callers retain the original generation path. One
  pre-existing import-order issue was corrected.

Behavioral contract additions are in existing `tests/test_vendor_config.py` and
`tests/test_platform_title_rules.py`. Existing Description isolation/conformance and
CLI/UI tests remain part of the full suite.

Quality-only changes needed for complete gates:

- `tests/test_main.py`, `tests/test_description_isolation.py`,
  `tests/test_description_templates.py`: consistent shared-fixture import paths;
  test_main also explicitly narrows non-None registered template declarations.
- `tests/test_corpus_wiring.py`: precise RowAnalysis annotations on `_rows_for_report`,
  `_midea_rows`, `_anchor`.
- `tests/test_series_corpus.py`: separate differently typed loop variables; accurate
  error-code annotation for the intentional immutable-mapping assignment test.
- `tests/test_warranty.py`: explicit non-None assertion before reading the expected warranty.
- `tests/test_writers.py`: `_row` accepts its existing integer row-number override.
- `tests/test_acceptance_examples.py`, `tests/test_categories.py`: wrap three existing
  overlong lines; no expected output changes.
- `README.md`: supported configuration semantics, replacement API, rendering lifecycle,
  and verification commands.
- `docs/phase1/walkthrough.md`: implementation, verification, and review record.

`models.py`, user input/output CSVs, dependencies, and baseline expectations were not modified.

## Final gates

| Gate | Result |
| --- | --- |
| Full pytest from kiachahiye_bulk_csv/ | **760 passed, zero skipped**, 26.16 seconds |
| Whole-tree mypy | **47 source files, zero issues** |
| Ruff | **All checks passed** |
| Description conformance | spec_table and kiachahiye_alfa_card pass |
| Startup validation | kiachahiye and ajmer, both cells, pass |
| Baseline audits | 56/56 in each of four vendor/sheet runs auditing both platforms |
| Locked file comparisons | All eight sizes and SHA-256 digests match |
| Independent Title differential review | 4,322 complete TitleResult comparisons match Phase 0 |
| git diff --check | Pass |

Initial root-level pytest was 681 passed/3 skipped. The final root-level result is
757 passed/3 skipped; those existing tests resolve real sheets relative to the application
directory. Running the final full suite there executes all **760** tests with no skips.

Mypy uses `MYPYPATH` pointing at kiachahiye_bulk_csv because this project imports flat
modules such as main, models, and vendor_config. Fixture imports and the pre-existing
test annotations were corrected rather than suppressing the whole-tree errors.

## Eight locked comparisons

The unchanged supplied verify_baseline.py writes only temporary files and compares their
physical bytes against the locked oracle. Expected and actual digests below are identical.

| Sheet | Cell | Expected = actual bytes | Expected = actual SHA-256 | Result |
| --- | --- | ---: | --- | --- |
| TWO_PRODUCTS.csv | kiachahiye.digi | 6396 | `0cd91604d47d4521631477bde6b288edcac40f2d1d0c15c5d28743a8d90bd7be` | MATCH |
| TWO_PRODUCTS.csv | kiachahiye.alfa | 12565 | `f01d24cc95de44b81c6000ab93ad0fcaba2a3ed35eb873d21d795eb85886c6a0` | MATCH |
| TWO_PRODUCTS.csv | ajmer.digi | 6341 | `b8671454c5ebe1fc4ee51e561f2153994675fc5c3cbe5380268c03a32283c4da` | MATCH |
| TWO_PRODUCTS.csv | ajmer.alfa | 4982 | `54d00723b1f4636b8a6b6d171bb0322a7456f1b39eb89c16da6c5945f46dac31` | MATCH |
| Step 1.csv | kiachahiye.digi | 151893 | `ad713adaac30b78070ae3ac7c91b9496f589baf135979f1f104c3118e39d65b1` | MATCH |
| Step 1.csv | kiachahiye.alfa | 311356 | `41677faff93f38fefbd307d1607f54224c782504af30c8474e5cc515cdd6dd78` | MATCH |
| Step 1.csv | ajmer.digi | 150843 | `54343cc4c782492eacade381226ed4d2874c68e2817bb8d774dc1c8e5e8895a9` | MATCH |
| Step 1.csv | ajmer.alfa | 142935 | `545f41e6ddbd0a06b85a6faa5b9ef04be2d349a578739a90760452df7fedef7e` | MATCH |

## Isolation and review evidence

- Tests enumerate VENDOR_REGISTRY × (digi, alfa) and all current TITLE_FORMULAS,
  including the existing ajmer_variant alias. Literal formula outputs are pinned.
- Each of five Title-affecting settings changes the target cell's Title/SEO while
  preserving the other three cells. Restoring the configuration restores the outputs
  in the same Python process.
- Direct resolve_row spies prove one extraction, two independent renders, two SEO
  generations, and the same immutable slots object. Identical cell policies are tested.
  Both writers are then executed with canonical extraction/rendering forbidden.
- Mapping mutation after resolution cannot change snapshots; writes to them fail;
  empty maps stay empty; platform defaults cannot own marketplace IDs.
- Existing negative mapping, non-blocking QC/audit, Description digest isolation,
  CLI vendor requirement, and terminal UI tests pass.
- Review found a stale legacy SKU import and a protected VIP source-pipe regression.
  Both were corrected and guarded. The writer test was strengthened after a reviewer
  found its original spying boundary too narrow. All three findings were actionable
  and resolved; reviewer rechecks found no remaining substantive production issues.

## Supported limits and deferred work

- Raw config attributes may now be None; use resolve_cell for effective settings.
- None means inheritance, not a real resolved value. An empty formula/template name is
  explicit but invalid and is rejected at startup.
- copy.replace is supported where Python provides it (3.13+); dataclasses.replace
  remains supported. Verification used the installed Python 3.14.7 environment.
- TV warranty fallback remains vendor-scoped because it changes extracted facts.
- Titles/SEO are resolution-time values. A changed title config requires re-resolution;
  writer-only Description changes do not re-render Titles.
- Extraction occurs once per resolve_row invocation. The existing run function still
  invokes row resolution in its collision-counting and finalization passes.
- Existing Digi-scoped SEO-length QC is preserved; audit still checks both platforms.
- The suite combines dynamic configuration contracts with fixed algorithm regression
  oracles. Some older assertions still assume particular registered settings. A valid
  future configuration change may require adjusting those assertions; intentionally
  changed CSV output also requires reviewing the separate locked baseline expectations.
- No Phase 2 template-shape expansion, new platform adapters, external data packs,
  SaaS features, cache, or model-field expansion is included.

## Commit scope

The authorized commit includes README.md, six production modules, eleven test modules,
and this walkthrough. The original untracked tasks/ directory is excluded and preserved.
No push, reset, restore, or cleaning is part of this operation.
