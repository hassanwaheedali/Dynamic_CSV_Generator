"""What one run puts on disk.

A chosen platform is the only thing this run produces: the other platform's file is not written,
so an output folder for an Alfa upload cannot hold a DigiMall CSV someone might grab by mistake.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import main
from tests.conftest import Pipeline, build_input_csv

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
