"""The "weakest descriptions first" worklist.

Answers one question about a finished run: **which products' source Description
carries so little information that the listing suffers -- and which are a single
line?**  Those are the rows worth sending back to whoever writes the copy.

It reads three things and writes one CSV:

    the source sheet        the Description itself (characters, lines)
    the DigiMall output     the spec rows the listing really shows, the Product
                            Type and the Short Description's bullet count
    the QC report           the flags already raised against that row

Nothing here feeds the pipeline, and the pipeline never reads this report: the
thresholds live in ``config.py`` (``THIN_*``) and only decide what this report
calls out.  Row numbers are the source sheet's own line numbers, the same ones
the QC report uses, so a row can be found in the sheet by its number.

    python3 thin_report.py                      # the paths in config.py
    python3 thin_report.py --input X.csv --digi Y.csv --qc Z.csv --out W.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

from config import (
    DIGI_OUTPUT,
    INPUT_FILE,
    QC_REPORT,
    SHORT_DESCRIPTION_CHARS,
    THIN_DESCRIPTION_CHARS,
    THIN_REPORT,
    THIN_SHORT_BULLETS,
    THIN_SPEC_ROWS,
)
from main import read_input
from models import InputRow

HEADER = [
    "Row",
    "Severity",
    "Issues",
    "One_Line",
    "Title",
    "Brand",
    "Product_Type",
    "Description_Chars",
    "Description_Lines",
    "Spec_Rows_In_Listing",
    "Short_Desc_Bullets",
    "Why_It_May_Matter",
    "QC_Flags",
]

#: The listing table's own rows.  The header row uses <th>, so it is not counted.
_SPEC_ROW_RE = re.compile(r"<tr><td")
_BULLET_RE = re.compile(r"<li>")


def source_shape(description: str) -> tuple[int, int]:
    """``(characters, non-empty lines)`` of one source Description."""
    text = (description or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line for line in text.split("\n") if line.strip()]
    return len(text), len(lines)


def classify(*, chars: int, lines: int, spec_rows: int, bullets: int) -> tuple[str, str, str]:
    """Return ``(severity, issues, why)`` for one row.  Severity is "" when fine.

    ``high``   -- the listing is visibly poor: a one-line Description, a very
                  short one, or a table with no real specification rows.
    ``medium`` -- usable, but the source could say much more: a short
                  Description, or fewer than the three Short Description bullets
                  the spec asks for where the row could support them.
    """
    issues: list[str] = []
    why: list[str] = []
    if lines == 1:
        issues.append("one-line Description")
        why.append("the source Description is a single line, so the listing has no product narrative")
    if chars < THIN_DESCRIPTION_CHARS:
        issues.append(f"very short source ({chars} chars)")
        why.append("there is hardly any product-specific copy to show")
    if spec_rows <= THIN_SPEC_ROWS:
        issues.append(f"only {spec_rows} spec row(s) in the listing")
        why.append("the published table is nearly empty")
    if bullets < THIN_SHORT_BULLETS:
        issues.append(f"{bullets} Short Description bullet(s)")
        why.append("the marketplace's short spec block is nearly empty")

    if lines == 1 or chars < THIN_DESCRIPTION_CHARS or spec_rows <= THIN_SPEC_ROWS:
        severity = "high"
    elif chars < SHORT_DESCRIPTION_CHARS or bullets < THIN_SHORT_BULLETS:
        severity = "medium"
    else:
        severity = ""
    return severity, "; ".join(issues), "; ".join(why) + ("." if why else "")


def read_output(path: Path) -> list[dict[str, str]]:
    """Rows of a finished output file, keyed by its header."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        return [dict(zip(header, values)) for values in reader if values]  # noqa: B905


def read_digi_facts(path: Path) -> dict[int, tuple[int, int, str]]:
    """``sheet row number -> (spec rows shown, short-description bullets, type)``.

    Row numbers start at 2 to match ``read_input`` and the QC report: the first
    data row of the sheet is row 2.
    """
    facts: dict[int, tuple[int, int, str]] = {}
    for index, row in enumerate(read_output(path), start=2):
        html = row["Description"]
        facts[index] = (
            len(_SPEC_ROW_RE.findall(html)),
            len(_BULLET_RE.findall(row["Short Description"])),
            row["Product Type"].strip(),
        )
    return facts


def read_flags(path: Path) -> dict[int, list[str]]:
    """``sheet row number -> that row's QC flag types``, in report order, deduplicated."""
    flags: dict[int, list[str]] = defaultdict(list)
    if not path.exists():
        return {}
    for row in read_output(path):
        flag_type = row["Flag Type"]
        bucket = flags[int(row["Row"])]
        if flag_type not in bucket:
            bucket.append(flag_type)
    return dict(flags)


def build_rows(
    parsed: list[InputRow],
    facts: dict[int, tuple[int, int, str]],
    flagged: dict[int, list[str]],
) -> list[list[str]]:
    """Every row worth a second look, worst first, as ready-to-write cells."""
    found: list[tuple[str, int, list[str]]] = []
    for row in parsed:
        chars, lines = source_shape(row.description)
        spec_rows, bullets, product_type = facts.get(row.row_number, (0, 0, ""))
        severity, issues, why = classify(
            chars=chars, lines=lines, spec_rows=spec_rows, bullets=bullets
        )
        if not severity:
            continue
        found.append(
            (
                severity,
                chars,
                [
                    str(row.row_number),
                    severity,
                    issues,
                    "yes" if lines == 1 else "no",
                    row.title,
                    row.brand,
                    product_type,
                    str(chars),
                    str(lines),
                    str(spec_rows),
                    str(bullets),
                    why,
                    "; ".join(flagged.get(row.row_number, [])),
                ],
            )
        )

    order = {"high": 0, "medium": 1}
    found.sort(key=lambda item: (order[item[0]], item[1]))
    return [cells for _, _, cells in found]


def write_report(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(HEADER)
        writer.writerows(rows)


def print_summary(rows: list[list[str]], total: int, path: Path) -> None:
    high = sum(1 for row in rows if row[1] == "high")
    medium = sum(1 for row in rows if row[1] == "medium")
    one_line = sum(1 for row in rows if row[3] == "yes")
    print(f"  Rows in the sheet          : {total}")
    print(f"  Descriptions worth a redo  : {len(rows)}  (high {high}, medium {medium})")
    print(f"  Of those, one-line sources : {one_line}")
    print(f"  Worklist written to        : {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Thin-Description worklist")
    parser.add_argument("--input", type=Path, default=INPUT_FILE)
    parser.add_argument("--digi", type=Path, default=DIGI_OUTPUT)
    parser.add_argument("--qc", type=Path, default=QC_REPORT)
    parser.add_argument("--out", type=Path, default=THIN_REPORT)
    args = parser.parse_args(argv)

    parsed = read_input(args.input)
    rows = build_rows(parsed, read_digi_facts(args.digi), read_flags(args.qc))
    write_report(args.out, rows)
    print_summary(rows, len(parsed), args.out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
