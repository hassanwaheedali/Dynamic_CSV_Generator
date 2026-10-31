"""What one run puts on disk.

A chosen platform is the only thing this run produces: the other platform's file is not written,
so an output folder for an Alfa upload cannot hold a DigiMall CSV someone might grab by mistake.

The summary also names the Description template that served each file it wrote -- listings are
restyled per (store x platform) cell now, so a run that said nothing about shapes would leave a
reader guessing which cell to edit.
"""

from __future__ import annotations

import csv
import dataclasses
import html as html_module
from pathlib import Path
from typing import Any

import pytest
from conftest import Pipeline, build_input_csv

import main
from description_builder import (
    DESCRIPTION_TEMPLATES,
    SPEC_TABLE,
    DescriptionTemplate,
    extract_spec_rows,
)
from models import SpecRow
from vendor_config import VENDOR_REGISTRY, ConfigError, validate_vendor_cfg

ROW = {
    "Title": "Haier Twin Inverter Freezer-On-Top Refrigerator 18 Cu Ft Black (HRF-538TIFB1U1)",
    "Description": (
        "The Haier HRF-538TIFBU is an 18 cu ft freezer-on-top refrigerator with a twin inverter.\n"
        "• Model: HRF-538TIFBU\n"
        "• Capacity: 538 Liters\n"
        "• Compressor Warranty: 10 Years\n"
        "• Color: Black\n"
    ),
    "Categories": "Electronics / Home appliances / Refrigerators",
    "Brand": "Haier",
    "Sell Price": "95,000",
    "Original Price": "96,000",
    "Image": "https://example.test/haier.jpg",
}


def _run(tmp_path: Path, platform: str) -> dict[str, Any]:
    sheet = build_input_csv(tmp_path / "Products.csv", [ROW])
    digi = tmp_path / "digi" / "digimall_bulk_import.csv"
    alfa = tmp_path / "alfa" / "alfa_bulk_import.csv"
    qc = tmp_path / "qc_report.csv"
    main.main(
        [
            "--input", str(sheet), "--digi", str(digi), "--alfa", str(alfa), "--qc", str(qc),
            "--sample-titles", str(tmp_path / "title_review_sample.csv"), "--platform", platform,
        ]
    )
    return {"digi": digi, "alfa": alfa, "qc": qc}


def _qc_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_an_alfa_run_writes_the_alfa_file_and_nothing_else(tmp_path: Path) -> None:
    out = _run(tmp_path, "alfa")
    assert out["alfa"].exists()
    assert not out["digi"].exists()
    assert not out["digi"].parent.exists(), "an empty digi folder is still a second folder"


def test_a_digmall_run_writes_the_digmall_file_and_nothing_else(tmp_path: Path) -> None:
    out = _run(tmp_path, "digi")
    assert out["digi"].exists()
    assert not out["alfa"].exists()


def test_the_default_run_still_writes_both(tmp_path: Path) -> None:
    out = _run(tmp_path, "both")
    assert out["digi"].exists() and out["alfa"].exists()


def test_the_report_of_an_alfa_run_holds_no_digmall_finding(tmp_path: Path) -> None:
    """DigiMall is where the closed-list cells live, so those flags are not this upload's news."""
    out = _run(tmp_path, "alfa")
    files = {row["Affected File(s)"] for row in _qc_rows(out["qc"])}
    assert "DigiMall (digimall_bulk_import.csv)" not in files


def test_a_colour_line_that_denies_the_title_ships_the_title_and_says_so(
    pipeline: Pipeline,
) -> None:
    """Real Dawlance rows: his Title names Meadow Green, the stamped line says Black.

    The Title ships -- a colour he wrote for this machine outranks a line standing on every row of
    the brand -- but the sheet still contradicts itself, and a silent override would leave him
    reading a Black he never sold.  The row reaches the QC report naming both values.
    """
    run = pipeline(
        [
            {
                "Title": (
                    "Dawlance Avante+ Freezer-On-Top Refrigerator 12 Cu Ft (9178-WB)-Meadow Green"
                ),
                "Description": (
                    "The Dawlance REF 9178LF AVANTE+ is a 12 cu ft refrigerator with Direct Cool "
                    "cooling, finished in Meadow Green.\n"
                    "• Model: 9178-WB\n"
                    "• Capacity: 12 Cu Ft\n"
                    "• Product Color: Black\n"
                    "• Compressor Warranty: 12 Years\n"
                ),
                "Categories": "Electronics / Home appliances / Refrigerators",
                "Brand": "Dawlance",
                "Sell Price": "145,000",
                "Original Price": "150,000",
                "Image": "https://example.test/dawlance.jpg",
            }
        ]
    )
    record = run["records"][0]
    assert record.color_token == "Meadow Green"
    assert "Meadow Green" in record.title
    assert "Black" not in record.title
    flagged = [f for f in run["flags"].flags if f.category == "title_description_conflict"]
    assert flagged, "a colour line that denies the Title may not be overridden in silence"
    assert "Meadow Green" in flagged[0].message and "Black" in flagged[0].message


ACCE = {
    "Title": "Dawlance Acce Glass Door Freezer-On-Top Refrigerator (9173)-Coral Red",
    "Description": (
        "The Dawlance REF 9173 Acce Coral Red is a refrigerator with Direct Cool cooling, "
        "finished in Coral Red.\n"
        "• Cooling Technology: Direct Cool\n"
        "• Product Color: Black\n"
        "• Compressor Warranty: 12 Years\n"
    ),
    "Categories": "Electronics / Home appliances / Refrigerators",
    "Brand": "Dawlance",
    "Sell Price": "120,000",
    "Original Price": "125,000",
    "Image": "https://example.test/dawlance.jpg",
}


def test_two_machines_that_differ_only_by_their_code_do_not_share_a_title(
    pipeline: Pipeline,
) -> None:
    """Real rows 213-216: four Dawlance fridges, four codes, ONE repeated Title on the shelf.

    The only word telling `(9173)` from `(9178)` was the code, and a code with no letter in it was
    refused -- so all four shipped as `Dawlance Coral Red Freezer-On-Top Refrigerator - Acce - ...`
    with fallback SKUs that then needed numeric suffixes to stay apart.
    """
    rows = [
        ACCE,
        {**ACCE, "Title": ACCE["Title"].replace("(9173)", "(9178)")},
        {**ACCE, "Title": ACCE["Title"].replace("(9173)", "(9191)")},
        {**ACCE, "Title": ACCE["Title"].replace("(9173)", "(9193)")},
    ]
    run = pipeline(rows)
    titles = [record.title for record in run["records"]]
    assert len(set(titles)) == 4, titles
    for code, title in zip(("9173", "9178", "9191", "9193"), titles, strict=True):
        assert code in title
    assert not [f for f in run["flags"].flags if f.category == "fallback_sku"], (
        "a code the row wrote in its own Title is not a row with no code"
    )


BURGUNDY = {
    "Title": "Dawlance Vertical Freezer Burgundy 11 Cu Ft (VF-1035GD)",
    "Description": (
        "The Dawlance VF-1035GD is an 11 cu ft vertical freezer, finished in Black.\n"
        "• Model: VF-1035GD\n"
        "• Capacity: 11 Cu Ft\n"
        "• Compressor Warranty: 12 Years\n"
    ),
    "Categories": "Electronics / Home appliances / Freezers",
    "Brand": "Dawlance",
    "Sell Price": "95,000",
    "Original Price": "100,000",
    "Image": "https://example.test/dawlance.jpg",
}


def test_a_paint_the_title_states_is_never_resold_as_the_line_name(
    pipeline: Pipeline,
) -> None:
    """Real row 78: `Dawlance Vertical Freezer Burgundy 11 Cu Ft (VF-1035GD)` -- owner ruling.

    Burgundy is the colour, not a series.  The word is spent on the paint the moment the Title's own
    colour word is read, so the name seat behind the code stays empty instead of printing this
    machine's colour twice, and the prose that calls it Black reaches the QC report for his review.
    """
    run = pipeline([BURGUNDY])
    record = run["records"][0]
    assert record.color_token == "Burgundy"
    assert "VF-1035GD Burgundy" not in record.title, record.title
    assert record.title.count("Burgundy") == 1, record.title
    flagged = [f for f in run["flags"].flags if f.category == "title_description_conflict"]
    assert flagged, "a row that states two colours may not ship one of them in silence"
    assert "Burgundy" in flagged[0].message and "Black" in flagged[0].message


# ────────────────── which Description shape served each file ──────────────────
def _plain_shape(rows: list[SpecRow]) -> str:
    """A second conforming shape: no header row, no inline styles."""
    body = "".join(
        "<tr>"
        f"<td>{'<strong>' if r.is_warranty else ''}"
        f"{html_module.escape(r.label, quote=False)}"
        f"{'</strong>' if r.is_warranty else ''}</td>"
        f"<td>{'<strong>' if r.is_warranty else ''}"
        f"{html_module.escape(r.value, quote=False)}"
        f"{'</strong>' if r.is_warranty else ''}</td>"
        "</tr>"
        for r in rows
    )
    return f"<table><tbody>{body}</tbody></table>"


#: Registered only by the test that uses it, so the shop's own registry stays clean.
PROBE = DescriptionTemplate(
    name="probe",
    render=_plain_shape,
    extract=lambda text: extract_spec_rows(text, starts_with="<table", ends_with="</table>"),
    starts_with="<table",
    ends_with="</table>",
)


def _summary_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    vendor: str | None = None,
    platform: str = "both",
) -> tuple[list[str], dict[str, Path]]:
    sheet = build_input_csv(tmp_path / "Products.csv", [ROW])
    paths = {
        "digi": tmp_path / "digi" / "digimall_bulk_import.csv",
        "alfa": tmp_path / "alfa" / "alfa_bulk_import.csv",
    }
    argv = [
        "--input", str(sheet),
        "--digi", str(paths["digi"]), "--alfa", str(paths["alfa"]),
        "--qc", str(tmp_path / "qc_report.csv"),
        "--sample-titles", str(tmp_path / "title_review_sample.csv"),
        "--platform", platform,
    ]
    if vendor is not None:
        argv += ["--vendor", vendor]
    main.main(argv)
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert "DESCRIPTION TEMPLATE PER FILE" in lines, out
    start = lines.index("DESCRIPTION TEMPLATE PER FILE")
    block: list[str] = []
    for line in lines[start + 1:]:
        if not line.strip():
            break  # every section in the summary opens with a blank line
        block.append(line)
    return block, paths


def _csv_description(path: Path) -> str:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return next(iter(csv.DictReader(handle)))["Description"]


def test_the_summary_names_the_template_that_served_each_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same rule as the lookup tables: tell the reader which cell actually served this run."""
    block, _ = _summary_run(tmp_path, capsys, vendor="kiachahiye")
    assert len(block) == 2, block
    assert block[0].startswith("  DigiMall spec_table"), block[0]
    assert "Kiachahiye.digi.description_template in vendor_config.py" in block[0], block[0]
    assert block[1].startswith("  Alfa     spec_table"), block[1]
    assert "Kiachahiye.alfa.description_template in vendor_config.py" in block[1], block[1]


def test_a_single_platform_run_names_only_the_file_it_wrote(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An Alfa upload is not this run's news about DigiMall -- and never names its cell to edit."""
    block, _ = _summary_run(tmp_path, capsys, vendor="ajmer", platform="alfa")
    assert len(block) == 1, block
    assert block[0].startswith("  Alfa     spec_table"), block[0]
    assert "Ajmer.alfa.description_template in vendor_config.py" in block[0], block[0]
    assert "digi" not in block[0].lower(), block[0]


def test_the_cell_the_summary_names_is_the_cell_the_startup_error_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One spelling of the fix location, so a reader never hunts between the two messages."""
    cfg = VENDOR_REGISTRY["ajmer"]
    broken = dataclasses.replace(
        cfg, digi=dataclasses.replace(cfg.digi, description_template="spec_tabel")
    )
    with pytest.raises(ConfigError) as caught:
        validate_vendor_cfg(broken)
    label = "Ajmer.digi.description_template"
    assert label in str(caught.value), str(caught.value)
    block, _ = _summary_run(tmp_path, capsys, vendor="ajmer", platform="digi")
    assert label in block[0], block[0]


def test_the_name_printed_for_a_cell_is_the_shape_that_reached_its_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restyled Alfa cell must be reported as restyled -- and must actually be restyled."""
    monkeypatch.setitem(DESCRIPTION_TEMPLATES, PROBE.name, PROBE)
    cfg = VENDOR_REGISTRY["kiachahiye"]
    restyled = dataclasses.replace(
        cfg, alfa=dataclasses.replace(cfg.alfa, description_template="probe")
    )
    monkeypatch.setitem(VENDOR_REGISTRY, "kiachahiye", restyled)

    block, paths = _summary_run(tmp_path, capsys, vendor="kiachahiye")
    assert "  DigiMall spec_table" in block[0], block[0]
    assert "  Alfa     probe" in block[1], block[1]
    # SPEC_TABLE's own shape carries a <th> header row; PROBE's does not.
    assert "<th" in _csv_description(paths["digi"]), "the DigiMall file lost the shop's table"
    assert "<th" not in _csv_description(paths["alfa"]), "the summary named a shape the file lacks"


def test_a_run_with_no_store_names_the_shape_without_blaming_the_builder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No --vendor means every cell took the shop's table; that is a fact about the run, not a bug."""
    block, _ = _summary_run(tmp_path, capsys)
    assert len(block) == 2, block
    assert all(SPEC_TABLE.name in line for line in block), block
    assert "spec_table" in block[0] and "spec_table" in block[1], block
    joined = " ".join(block).lower()
    assert "description_builder" not in joined, block
    assert "--vendor" in joined, block
