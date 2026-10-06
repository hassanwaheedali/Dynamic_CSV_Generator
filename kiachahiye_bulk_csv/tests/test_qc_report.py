"""The QC collector's own behaviour: one line per finding, and gap read-back."""

from __future__ import annotations

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
