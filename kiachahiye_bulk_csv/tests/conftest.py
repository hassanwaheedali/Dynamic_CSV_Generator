"""Shared pytest fixtures -- runs the real pipeline over tiny in-memory sheets."""

from __future__ import annotations

import csv
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import main  # noqa: E402
from qc_report import QCFlagCollector  # noqa: E402
from writers import (  # noqa: E402
    ALFA_HEADER,
    DIGI_HEADER,
    build_alfa_row,
    build_digi_row,
    write_csv,
)

Pipeline = Callable[[list[dict[str, str]]], dict[str, Any]]

INPUT_COLUMNS = [
    "Title", "Description", "Sell Price", "Original Price",
    "Categories", "Brand", "Image",
]

#: Columns the sheet may carry but the pipeline never reads.  Written only when a
#: test's own row includes them, so "no Vendor column at all" stays testable.
OPTIONAL_INPUT_COLUMNS = ["Vendor"]


def build_input_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Optional columns (Weight, Weight Unit, ...) are written only when a row uses
    # one, exactly like the real sheet: the pipeline treats them as optional.
    columns = list(INPUT_COLUMNS)
    if any("Vendor" in row for row in rows):
        columns.extend(OPTIONAL_INPUT_COLUMNS)
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(column, "") for column in columns])
    return path


def run_pipeline(tmp_path: Path, rows: list[dict[str, str]]) -> dict[str, Any]:
    """Run the real pipeline and return both files' rows plus the QC flags."""
    input_path = build_input_csv(tmp_path / "input.csv", rows)
    digi_path = tmp_path / "digi" / "digimall_bulk_import.csv"
    alfa_path = tmp_path / "alfa" / "alfa_bulk_import.csv"

    parsed = main.read_input(input_path)
    flags = QCFlagCollector()
    records = main.run(parsed, flags)
    write_csv(digi_path, DIGI_HEADER, [build_digi_row(r).values for r in records])
    write_csv(alfa_path, ALFA_HEADER, [build_alfa_row(r).values for r in records])
    qc_path = tmp_path / "qc_report.csv"
    flags.write_csv(qc_path)

    with digi_path.open("r", encoding="utf-8-sig", newline="") as handle:
        digi_rows = list(csv.DictReader(handle))
    with alfa_path.open("r", encoding="utf-8-sig", newline="") as handle:
        alfa_rows = list(csv.DictReader(handle))

    return {
        "records": records,
        "flags": flags,
        "digi": digi_rows,
        "alfa": alfa_rows,
        "digi_path": digi_path,
        "alfa_path": alfa_path,
        "qc_path": qc_path,
        "digi_text": digi_path.read_text(encoding="utf-8-sig"),
        "alfa_text": alfa_path.read_text(encoding="utf-8-sig"),
    }


@pytest.fixture()
def pipeline(tmp_path: Path) -> Pipeline:
    def _run(rows: list[dict[str, str]]) -> dict[str, Any]:
        return run_pipeline(tmp_path, rows)

    return _run
