"""The thin-Description worklist: grading rules and one real end-to-end run."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import main  # noqa: E402
import thin_report  # noqa: E402

Pipeline = Any


def test_classify_calls_a_one_line_description_high() -> None:
    severity, issues, why = thin_report.classify(chars=43, lines=1, spec_rows=4, bullets=1)
    assert severity == "high"
    assert "one-line Description" in issues
    assert why.endswith(".")


def test_classify_calls_a_short_but_usable_row_medium_and_a_rich_row_ok() -> None:
    medium, _, _ = thin_report.classify(chars=250, lines=6, spec_rows=9, bullets=3)
    assert medium == "medium", "a 250-char source is usable but thin"
    ok, issues, why = thin_report.classify(chars=480, lines=13, spec_rows=14, bullets=3)
    assert (ok, issues, why) == ("", "", "")


def test_a_row_with_no_real_spec_rows_is_high_even_when_the_copy_is_long() -> None:
    severity, issues, _ = thin_report.classify(chars=900, lines=20, spec_rows=2, bullets=3)
    assert severity == "high"
    assert "2 spec row(s)" in issues


def test_report_finds_the_one_line_row_and_leaves_the_rich_row_out(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """End to end: the real pipeline's own files, read back by the report."""
    one_line = {
        "Title": "Dawlance Thin Freezer (DF-1)",
        "Description": "Dawlance DF-1 deep freezer in White.",
        "Sell Price": "1",
        "Original Price": "2",
        "Categories": "Electronics / Home appliances / Deep Freezer",
        "Brand": "Dawlance",
        "Image": "https://example.com/a.jpg",
        "Vendor": "ignored",
    }
    rich = dict(one_line)
    rich["Title"] = "Dawlance Rich Freezer (DF-2)"
    rich["Description"] = "\n".join(
        [
            "The Dawlance DF-2 is a 300 L deep freezer in White, built for families who "
            "need dependable freezing through long power cuts, with a fast freeze "
            "function and a lockable lid that keeps the cold air inside.",
            "",
            "Capacity: 300 L",
            "Product Color: White",
            "Type: Deep Freezer",
            "Compressor: Inverter",
            "Cooling Method: Direct Cool",
            "Door Type: Single Door",
            "Freezing Capacity: 12 kg",
            "Temperature Range: -18 to -24 C",
            "Voltage: 230 V",
            "Refrigerant: R-600a",
        ]
    )
    result = pipeline([one_line, rich])

    parsed = main.read_input(result["digi_path"].parent.parent / "input.csv")
    rows = thin_report.build_rows(
        parsed,
        thin_report.read_listing_facts(result["digi_path"]),
        thin_report.read_flags(result["qc_path"]),
    )
    titles = [row[4] for row in rows]
    assert titles == ["Dawlance Thin Freezer (DF-1)"], rows
    assert rows[0][1] == "high"
    assert rows[0][3] == "yes", "the One_Line column must say yes"
    assert "thin_description" in rows[0][12] or "short_description_thin" in rows[0][12]


def test_the_report_writes_the_documented_header(tmp_path: Path) -> None:
    out = tmp_path / "thin.csv"
    thin_report.write_report(out, [])
    assert out.read_text(encoding="utf-8").strip().strip('"').startswith("Row")
    assert len(thin_report.HEADER) == 13


@pytest.mark.parametrize("chars,lines", [(0, 0), (43, 1)])
def test_source_shape_counts_characters_and_non_empty_lines(chars: int, lines: int) -> None:
    text = "x" * chars if lines else ""
    assert thin_report.source_shape(text) == (chars, lines)


def test_an_upload_with_no_short_description_column_is_not_judged_on_bullets(
    tmp_path: Path,
) -> None:
    """The Alfa file has no Short Description column -- reading it must not call every row thin."""
    path = tmp_path / "alfa_bulk_import.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(["Title", "Description", "Product Type"])
        writer.writerow(["A", "<table><tr><td>Color</td><td>Black</td></tr></table>", "Freezer"])
    facts = thin_report.read_listing_facts(path)
    assert facts[2][1] is None, "no column at all is not the same as an empty one"
    assert thin_report.classify(chars=2000, lines=8, spec_rows=4, bullets=facts[2][1])[0] == ""
