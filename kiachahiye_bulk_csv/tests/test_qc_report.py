"""The QC collector's own behaviour: one line per finding, and gap read-back."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from qc_report import CAT_ATTRIBUTE_EMPTY, QCFlagCollector  # noqa: E402


def _collector() -> QCFlagCollector:
    flags = QCFlagCollector()
    flags.flag(
        3, "T", CAT_ATTRIBUTE_EMPTY,
        "Attribute_Volt: raw signal '230 V' did not exactly match any allowed value "
        "-- cell left empty; extend ALIASES/ALLOWED in attributes.py if it should map",
        platform="digi",
    )
    flags.flag(
        3, "T", CAT_ATTRIBUTE_EMPTY,
        "Attribute_Volt: raw signal '230 V' did not exactly match any allowed value "
        "-- cell left empty; extend ALIASES/ALLOWED in attributes.py if it should map",
        platform="digi",
    )
    flags.flag(4, "U", CAT_ATTRIBUTE_EMPTY, "details without a column prefix", platform="digi")
    return flags


def test_attribute_gaps_read_the_column_and_the_raw_string_back() -> None:
    gaps = _collector().attribute_gaps()
    assert gaps[("Attribute_Volt", "230 V")] == 2
    assert len(gaps) == 1, "a message without the column prefix must be skipped, not crash"


def _scoped() -> QCFlagCollector:
    flags = QCFlagCollector()
    flags.flag(2, "A", "attribute_empty", "a DigiMall cell", platform="digi")
    flags.flag(3, "B", "brand_missing", "an Alfa brand", platform="alfa")
    flags.flag(4, "C", "quantity_default", "both files", platform="both")
    return flags


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_the_report_keeps_only_the_files_this_run_uploaded(tmp_path: Path) -> None:
    """A finding about a file nobody wrote is not a finding about the upload in hand."""
    path = tmp_path / "qc_report.csv"
    _scoped().write_csv(path, "alfa")
    assert [row["Row"] for row in _rows(path)] == ["3", "4"], "the DigiMall row must not appear"

    _scoped().write_csv(path, "digi")
    assert [row["Row"] for row in _rows(path)] == ["2", "4"]

    _scoped().write_csv(path)
    assert [row["Row"] for row in _rows(path)] == ["2", "3", "4"], "the default loses nothing"
