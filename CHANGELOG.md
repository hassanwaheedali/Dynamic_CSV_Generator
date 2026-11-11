# Changelog

## [Unreleased]
### Fixed
- Numeric `Model:` values now reach upload titles and SKUs. When no usable model
  label exists, extraction accepts a single standalone title number of at least
  four digits, excluding stated measurements; ambiguous numbers remain unresolved.

### Added
- The file menu in `run_pipeline.bat` and `run_ui.py` lists CSVs from all
  `data/input` subfolders, with folder paths to distinguish matching filenames.

## [1.0.0] - 2026-10-06
### Added
- Bulk CSV pipeline generating alfa and digi store imports from raw catalog rows.
- Dynamic derivation of brand, category, attributes, title, SKU/handle and warranty.
- Description builder: spec table plus short description built directly from features.
- QC, audit and thin-description reports.

### Changed
- Spec values are capitalized dynamically (e.g. "Friendly gas R410").
- Short description drops "Key features include" lead-ins and repeated product titles.
- Generic "Specification(s)" labels are skipped in the table.

### Fixed
- Glued sentences with ALL-CAPS model codes (e.g. `.SPECIFICATION`) now split correctly.
