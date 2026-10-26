"""The upload gate itself: what the audit stage may call a failure.

The gate reads the two generated files back and re-derives each fact from the source, so a rule
that disagrees with the pipeline stops an upload that is actually correct.  These rows are the
ones the real 752-row sheet failed on, written small.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import audit
from tests.conftest import Pipeline

HAIER_FREEZER = {
    "Title": "Haier Twin Inverter IOT Freezer-On-Top Refrigerator 18 Cu Ft Black (HRF-538TIFB1U1)",
    "Description": (
        "The Haier HRF-538TIFBU is an 18 cu ft freezer-on-top refrigerator.\n"
        "• Model: Twin Inverter IOT HRF-538TIFBU\n"
        "• Capacity: 538 Liters\n"
        "• Compressor Warranty: 10 Years\n"
    ),
    "Categories": "Electronics / Home appliances / Refrigerators",
    "Brand": "Haier",
    "Sell Price": "95,000",
    "Original Price": "96,000",
    "Image": "https://example.test/haier.jpg",
}

HOMAGE_LIFETIME = {
    "Title": "Homage Freezer-on-Top Refrigerator 13 Cu Ft Maroon (HRF-47442-GD)",
    "Description": (
        "The Homage HRF-47442-GD is a 13 cu ft refrigerator.\n"
        "• Warranty: Lifetime\n"
        "• All Parts Warranty: 3 Years\n"
    ),
    "Categories": "Electronics / Home appliances / Refrigerators",
    "Brand": "Homage",
    "Sell Price": "87,680",
    "Original Price": "87,780",
    "Image": "https://example.test/homage.jpg",
}

SUPER_ASIA_TWO_NUMBERS = {
    "Title": "Super Asia Hi Wash Top Load Washing Machine 10kg Grey (SA-260)",
    "Description": (
        "The Super Asia SA-260 is a 10 kg top load washing machine.\n"
        "• Warranty: 1 Year, 10 Years\n"
        "• Capacity: 10 kg\n"
    ),
    "Categories": "Home appliances / Laundry / Washing Machines",
    "Brand": "Super Asia",
    "Sell Price": "32,000",
    "Original Price": "33,000",
    "Image": "https://example.test/super-asia.jpg",
}


def _gate(
    result: dict[str, Any], input_path: Path, platform: str = "both"
) -> dict[str, tuple[bool, str]]:
    """Run the gate over one pipeline output and return every check it ran.

    Each entry is the check's pass/fail and its failure detail -- so a rule that quietly stopped
    existing shows up here as a missing name, not as a passing test.
    """
    audit.RESULTS.clear()
    command = [
        "--input",
        str(input_path),
        "--digi",
        str(result["digi_path"]),
        "--alfa",
        str(result["alfa_path"]),
        "--qc",
        str(result["qc_path"]),
    ]
    if platform != "both":
        command += ["--platform", platform]
    audit.main(command)
    return {name: (ok, detail) for ok, name, detail in audit.RESULTS}


def _failure(failures: dict[str, tuple[bool, str]], startswith: str) -> str:
    names = [name for name in failures if name.startswith(startswith)]
    assert len(names) == 1, f"the gate ran {len(names)} checks named {startswith!r}..."
    ok, detail = failures[names[0]]
    return "" if ok else detail


def _rejected(failures: dict[str, tuple[bool, str]]) -> list[str]:
    names = [name for name, (ok, _d) in failures.items() if not ok]
    return sorted(names)


def _edit_cell(path: Path, column: str, edit: Callable[[str], str]) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    index = rows[0].index(column)
    rows[1][index] = edit(rows[1][index])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerows(rows)


def _rewrite_cell(path: Path, column: str, value: str) -> None:
    _edit_cell(path, column, lambda _before: value)


def _add_empty_spec_row(path: Path) -> None:
    """Append a table row whose answer is blank -- a defect in whichever file carries it."""

    def edit(html: str) -> str:
        cut = html.rindex("</tr>") + len("</tr>")
        return html[:cut] + "<tr><td>Gate probe</td><td></td></tr>" + html[cut:]

    _edit_cell(path, "Description", edit)


def _drop_flags(path: Path, phrase: str) -> None:
    """Delete every QC line whose Details mention ``phrase``, as if nobody had flagged the row."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    index = rows[0].index("Details")
    header, body = rows[0], [row for row in rows[1:] if phrase not in row[index]]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        writer.writerows(body)


def _demote_gap_flags(path: Path, column: str) -> None:
    """Keep the prose naming ``column`` but stop reporting an empty cell behind it.

    A report that merely mentions the column while flagging something else tells the shop nothing
    about a cell he would otherwise upload empty, so it must not excuse one.
    """
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    header = rows[0]
    type_index, details_index = header.index("Flag Type"), header.index("Details")
    for row in rows[1:]:
        if row[type_index] == "attribute_empty" and row[details_index].startswith(f"{column}:"):
            row[type_index] = "thin_description"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerows(rows)


def test_the_warranty_gate_accepts_a_cell_the_platform_list_has_no_value_for(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """Real sheet, sheet row 512: `• Warranty: Lifetime` and no `Lifetime` option to sell it with.

    DigiMall's closed list stops at `12 Years`, so the pipeline ships the cell empty and names the
    row in the QC report.  Comparing the raw headline to the cell called that a defect and blocked
    an upload over a hole in the platform's own list.
    """
    result = pipeline([HOMAGE_LIFETIME])
    assert result["digi"][0]["Attribute_Warranty"] == ""
    assert any(
        flag.category == "attribute_empty" and flag.message.startswith("Attribute_Warranty:")
        for flag in result["flags"].flags
    )

    failures = _gate(result, tmp_path / "input.csv")
    assert _failure(failures, "Attribute_Warranty and the warranty table agree") == ""


def test_an_invented_warranty_cell_is_still_a_failure(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """The relaxation is only for a value the platform does not carry: a written-in word fails."""
    result = pipeline([HOMAGE_LIFETIME])
    _rewrite_cell(result["digi_path"], "Attribute_Warranty", "Lifetime")

    failures = _gate(result, tmp_path / "input.csv")
    assert "file says 'Lifetime'" in _failure(
        failures, "Attribute_Warranty and the warranty table agree"
    )


def test_the_empty_cell_must_still_be_named_in_the_qc_report(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """Silence is the failure this gate exists to catch, so an unflagged empty cell still bites."""
    result = pipeline([HOMAGE_LIFETIME])
    _drop_flags(result["qc_path"], "Attribute_Warranty")

    failures = _gate(result, tmp_path / "input.csv")
    assert "no flag" in _failure(
        failures, "Attribute_Warranty and the warranty table agree"
    )


def test_a_flag_that_names_the_column_without_reporting_a_gap_does_not_excuse_it(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """Only a gap reported for THIS column licenses shipping nothing in it."""
    result = pipeline([HOMAGE_LIFETIME])
    _demote_gap_flags(result["qc_path"], "Attribute_Warranty")

    failures = _gate(result, tmp_path / "input.csv")
    assert "no flag" in _failure(
        failures, "Attribute_Warranty and the warranty table agree"
    )


def test_the_title_gate_checks_the_model_the_pipeline_publishes(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """Real sheet, sheet row 668: the shop wrote `Model: Twin Inverter IOT HRF-538TIFBU`.

    `Twin Inverter IOT` is the technology in front of the code, so the row ships `HRF-538TIFBU` as
    its model -- which is what the rebuilt Title carries.  Re-deriving the raw line instead of the
    published model demanded words the formula spends on other slots.
    """
    result = pipeline([HAIER_FREEZER])
    failures = _gate(result, tmp_path / "input.csv")
    assert _failure(failures, "every Title is ") == ""


def test_one_warranty_line_naming_no_part_prints_one_row(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """Real sheet, sheet row 596: `• Warranty: 1 Year, 10 Years` is one answer to one question.

    His two numbers share one label, so the table printed `Warranty` twice and the gate refused the
    description.  The row keeps both numbers, in the order he wrote them, under the one label his
    line gives them.
    """
    result = pipeline([SUPER_ASIA_TWO_NUMBERS])
    html = result["digi"][0]["Description"]
    spec_rows = re.findall(
        r"<tr><td[^>]*>(?:<strong>)?([^<]+)(?:</strong>)?</td>"
        r"<td[^>]*>(?:<strong>)?([^<]+)",
        html,
    )
    assert spec_rows.count(("Warranty", "1 Year, 10 Years")) == 1

    failures = _gate(result, tmp_path / "input.csv")
    assert [name for name in failures if "repeats a label" in name] == []
    assert _failure(failures, "every Description, Short Description") == ""


def test_the_alfa_gate_ignores_a_digmall_only_defect(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """Uploading only Alfa cannot be blocked by a cell Alfa does not carry.

    `Attribute_Warranty` is a DigiMall column: the Alfa file has 28 columns and none of them is an
    attribute.  Inventing a value there is a real defect -- just not one an Alfa upload can ship.
    """
    result = pipeline([HOMAGE_LIFETIME])
    _rewrite_cell(result["digi_path"], "Attribute_Warranty", "Lifetime")

    both = _gate(result, tmp_path / "input.csv")
    assert _rejected(both) != [], "the invented cell must fail an unscoped gate"

    failures = _gate(result, tmp_path / "input.csv", platform="alfa")
    assert _rejected(failures) == []
    assert not [name for name in failures if name.startswith("DigiMall")]


def test_the_digmall_gate_ignores_an_alfa_only_defect(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """The two files carry different Vendor literals, so each upload answers for its own."""
    result = pipeline([HOMAGE_LIFETIME])
    _rewrite_cell(result["alfa_path"], "Vendor", "KiaChahiye PVT LTD")

    both = _gate(result, tmp_path / "input.csv")
    assert "Alfa Vendor is the exact literal" in _rejected(both)

    failures = _gate(result, tmp_path / "input.csv", platform="digi")
    assert _rejected(failures) == []
    assert not [name for name in failures if name.startswith("Alfa")]


def test_the_single_platform_gate_reads_that_file_for_the_shared_rules(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """Gating Alfa must prove Alfa's own Description, not DigiMall's copy of the same product.

    A table with an empty cell is a defect in whichever file carries it; reading the other file
    would let the upload gate certify a document it never opened.
    """
    result = pipeline([HOMAGE_LIFETIME])
    _add_empty_spec_row(result["alfa_path"])

    failures = _gate(result, tmp_path / "input.csv", platform="alfa")
    assert _rejected(failures) == ["Alfa description/SEO: description has an empty cell"]

    other = _gate(result, tmp_path / "input.csv", platform="digi")
    assert _rejected(other) == []


def test_the_alfa_gate_never_opens_the_digmall_file(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """A stale or missing DigiMall CSV must not stop an Alfa upload, nor crash the gate."""
    result = pipeline([HOMAGE_LIFETIME])
    result["digi_path"].unlink()

    failures = _gate(result, tmp_path / "input.csv", platform="alfa")
    assert _rejected(failures) == []
    assert "Alfa header is the 28-column contract" in failures
    assert "DigiMall row count matches the source" not in failures


def test_an_empty_upload_file_is_a_failure_the_gate_names(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """Zero bytes where the header should be is the worst a file can be, and still a FAIL line.

    Reading the header raised straight through the gate, so the shop saw a traceback and no
    checklist -- the one thing an upload gate must never do is stop before naming the failure.
    """
    result = pipeline([HOMAGE_LIFETIME])
    result["alfa_path"].write_text("", encoding="utf-8")

    rejected = _rejected(_gate(result, tmp_path / "input.csv", platform="alfa"))
    assert "Alfa header is the 28-column contract" in rejected
    assert "Alfa row count matches the source" in rejected
    assert "row-by-row comparison is possible" in rejected


def test_an_upload_that_was_never_written_fails_the_gate_by_name(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """A DigiMall-only run leaves no Alfa file, and a `both` gate meeting that must still print.

    Opening the missing CSV raised straight through the gate, so the shop saw a traceback and no
    checklist -- exactly the silence an upload gate is hired to prevent.
    """
    result = pipeline([HOMAGE_LIFETIME])
    result["digi_path"].unlink()
    result["digi_path"].parent.rmdir()

    rejected = _rejected(_gate(result, tmp_path / "input.csv"))
    assert "DigiMall file is there to read" in rejected
    assert "DigiMall header is the 66-column contract" in rejected


def test_a_value_outside_the_platform_closed_list_fails_the_gate(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """`Top Mount` is the owner's word, not DigiMall's: the list is closed and the gate must know.

    The rule looked each column up under its own name with the `Attribute_` prefix stripped, while
    `ALLOWED` is keyed BY THAT FULL NAME -- so every lookup missed and any value at all passed.
    """
    result = pipeline([HAIER_FREEZER])
    assert "Attribute_Refrigerator Type" in audit.ALLOWED
    assert "Top Mount" not in audit.ALLOWED["Attribute_Refrigerator Type"]
    _rewrite_cell(result["digi_path"], "Attribute_Refrigerator Type", "Top Mount")

    failures = _gate(result, tmp_path / "input.csv", platform="digi")
    assert _rejected(failures) == [
        "DigiMall description/SEO: Attribute_Refrigerator Type value not in ALLOWED"
    ]

    # An Alfa upload ships no such column, so it is not Alfa's problem.
    assert _rejected(_gate(result, tmp_path / "input.csv", platform="alfa")) == []


HAIER_HAIRLINE = {
    **HAIER_FREEZER,
    "Title": (
        "Haier Twin Inverter Freezer-On-Top Refrigerator 18 Cu Ft Hairline Black (HRF-538TIFB1U1)"
    ),
    "Description": HAIER_FREEZER["Description"] + "• Product Color: Black\n",
}


def test_a_colour_no_source_cell_states_is_rejected(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """`Option1 Value` is a claim about the paint, so a phrase the row never wrote is invented."""
    result = pipeline([HAIER_FREEZER])
    _rewrite_cell(result["digi_path"], "Option1 Value", "Neon Tangerine")

    failures = _gate(result, tmp_path / "input.csv")
    assert "Neon Tangerine" in _failure(
        failures, "every colour the file ships is a colour the row stated"
    )


def test_a_colourway_cut_down_to_its_generic_word_is_rejected(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """`Hairline Black` is the variant name; shipping `Black` merges it with every other row.

    The stamped `• Product Color: Black` line stands on whole brands' worth of rows, so a reader
    that trusts the line before the Title sells the shop's own colourway away for a generic word.
    """
    result = pipeline([HAIER_HAIRLINE])
    assert result["digi"][0]["Option1 Value"] == "Hairline Black"
    _rewrite_cell(result["digi_path"], "Option1 Value", "Black")

    failures = _gate(result, tmp_path / "input.csv")
    assert "Hairline Black" in _failure(failures, "every colourway the row wrote ships whole")


def test_the_config_default_colour_is_not_called_invented(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """`LED TV` ships Black when the row states no colour -- a documented default, not a guess."""
    row = {
        **HAIER_FREEZER,
        "Title": "Haier 32 Inch Smart Google LED TV (H32K85FX)",
        "Description": (
            "The Haier H32K85FX is a 32 inch smart LED TV.\n"
            "• Model: H32K85FX\n"
            "• Panel Warranty: 2 Years\n"
        ),
        "Categories": "Electronics / TV & Video / LED TV",
    }
    result = pipeline([row])
    assert result["digi"][0]["Option1 Value"] == "Black"

    failures = _gate(result, tmp_path / "input.csv")
    assert _failure(failures, "every colour the file ships is a colour the row stated") == ""


def test_a_freezer_placement_the_row_never_stated_is_rejected(
    pipeline: Pipeline, tmp_path: Path
) -> None:
    """214 of this sheet's 240 refrigerators say Freezer-On-Top themselves; the rest must not inherit it."""
    result = pipeline([SUPER_ASIA_TWO_NUMBERS])
    _rewrite_cell(result["digi_path"], "Attribute_Refrigerator Type", "Freezer-On-Top")

    failures = _gate(result, tmp_path / "input.csv", platform="digi")
    assert "Freezer-On-Top" in _failure(
        failures, "no freezer placement the row does not state itself"
    )
