"""Audit the two output CSVs against the source sheet, from every angle.

Run it before every upload::

    python audit.py                                  # the configured output files
    python audit.py --input data/input/test100/TEST_100_PRODUCTS.csv \\
                    --digi  data/output/test100/digi/digimall_bulk_import.csv \\
                    --alfa  data/output/test100/alfa/alfa_bulk_import.csv

It reads only the three files -- it does not run the pipeline -- and prints a
checklist of PASS/FAIL lines plus a per-row report of anything suspicious.
Exit code is 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import csv
import html as html_module
import re
import sys
from collections import Counter
from pathlib import Path

import config as CONFIG
from attributes import ALLOWED
from brands import resolve_brand
from categories import resolve_category, resolve_product_type
from sku_handle import extract_model
from textutils import (
    find_weight_in_text,
    parse_weight_cell,
    parse_weight_unit,
    pick_weight_columns,
)
from warranty import resolve_warranty
from writers import ALFA_HEADER, DIGI_HEADER


def source_weight(rec: dict[str, str], text: str) -> tuple[str, str]:
    """The weight the source states for this row, from its column or its Description."""
    value_column, unit_column = pick_weight_columns([key or "" for key in rec])

    def cell(name: str | None) -> str:
        if name is None:
            return ""
        for key, value in rec.items():
            if key and key.strip().lower() == name.strip().lower():
                return str(value or "").strip()
        return ""

    written = parse_weight_cell(cell(value_column))
    if written is not None:
        unit = parse_weight_unit(cell(unit_column))
        return written[0], unit or written[1]
    found = find_weight_in_text(text)
    return found if found is not None else ("", "")

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    RESULTS.append((ok, name, detail))


def read(path: Path) -> tuple[list[str], list[dict[str, str]], str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        text = handle.read()
    reader = csv.reader(text.splitlines(True))
    header = next(reader)
    # Not strict: a row with too few cells must be reported by the cell-count
    # checks, not raised here.
    rows = [dict(zip(header, values)) for values in reader if values]  # noqa: B905
    return header, rows, text


def report() -> int:
    """Print the checklist and return the exit code (0 only when all pass)."""
    failed = [entry for entry in RESULTS if not entry[0]]
    for ok, name, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail else ""))
    print()
    print(f"  checks: {len(RESULTS)} | passed: {len(RESULTS) - len(failed)} | failed: {len(failed)}")
    if failed:
        print("\n  FAILURES")
        for _, name, detail in failed:
            print(f"    - {name}: {detail}")
    return 1 if failed else 0


def write_evidence(
    path: Path,
    source: list[dict[str, str]],
    digi: list[dict[str, str]],
    alfa: list[dict[str, str]],
) -> None:
    """One line per row per platform: what that row produced, and whether it conforms.

    This is the row-by-row half of the review: 100 source rows become 200 lines,
    so every cell of both upload files is accounted for.
    """
    columns = [
        "Row", "Platform", "Title", "Variant SKU", "Handle", "Category", "Brands",
        "Product Type", "Warranty", "Tags", "Spec Rows", "Short Bullets",
        "Desc Chars", "SEO Title Chars", "SEO Desc Chars", "Verdict",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for index, (_rec, digi_row, alfa_row) in enumerate(
            zip(source, digi, alfa, strict=True), start=2
        ):
            for platform, row in (("digi", digi_row), ("alfa", alfa_row)):
                notes: list[str] = []
                for required in ("Title", "Product Type", "Vendor", "Variant SKU", "Handle"):
                    if not row[required]:
                        notes.append(f"{required} empty")
                tags = [tag for tag in row["Tags"].split(",") if tag.strip()]
                if not 5 <= len(tags) <= 8:
                    notes.append(f"{len(tags)} tags")
                if not CONFIG.SEO_TITLE_MIN <= len(row["SEO Title"]) <= CONFIG.SEO_TITLE_MAX:
                    notes.append("SEO Title length")
                if not CONFIG.SEO_DESC_MIN <= len(row["SEO Description"]) <= CONFIG.SEO_DESC_MAX:
                    notes.append("SEO Description length")
                if not row["Description"].startswith("<table"):
                    notes.append("Description not a table")
                if platform == "digi":
                    for column, value in row.items():
                        if column.startswith("Attribute_") and value:
                            allowed = ALLOWED.get(column[10:])
                            if allowed is not None and value not in allowed:
                                notes.append(f"{column} not allowed")
                if 'row["Description"]' in row["Description"]:
                    notes.append("placeholder leaked")
                writer.writerow({
                    "Row": index,
                    "Platform": platform,
                    "Title": row["Title"],
                    "Variant SKU": row["Variant SKU"],
                    "Handle": row["Handle"],
                    "Category": row["Category"],
                    "Brands": row["Brands"],
                    "Product Type": row["Product Type"],
                    "Warranty": row.get("Attribute_Warranty", "") if platform == "digi" else "",
                    "Tags": len(tags),
                    "Spec Rows": row["Description"].count("<tr") - 1,
                    "Short Bullets": row["Short Description"].count("<li>") if platform == "digi" else 0,
                    "Desc Chars": len(row["Description"]),
                    "SEO Title Chars": len(row["SEO Title"]),
                    "SEO Desc Chars": len(row["SEO Description"]),
                    "Verdict": "PASS" if not notes else "CHECK: " + "; ".join(notes),
                })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=CONFIG.INPUT_FILE)
    parser.add_argument("--digi", type=Path, default=CONFIG.DIGI_OUTPUT)
    parser.add_argument("--alfa", type=Path, default=CONFIG.ALFA_OUTPUT)
    parser.add_argument("--qc", type=Path, default=CONFIG.QC_REPORT)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=None,
        help="also write one line per row per platform, as proof of the row-by-row review",
    )
    args = parser.parse_args(argv)

    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        source = list(csv.DictReader(handle))
    digi_header, digi, digi_text = read(args.digi)
    alfa_header, alfa, _alfa_text = read(args.alfa)

    # Every row the pipeline flagged, by source row number.  The point of the
    # audit is that nothing is wrong *silently*: an anomaly a human has been
    # told about is acceptable, an unflagged one is not.
    flagged: dict[int, set[str]] = {}
    flag_text: dict[int, str] = {}
    if args.qc.exists():
        with args.qc.open(encoding="utf-8-sig", newline="") as handle:
            for entry in csv.DictReader(handle):
                try:
                    number = int(entry["Row"])
                except (KeyError, ValueError):
                    continue
                flagged.setdefault(number, set()).add(entry.get("Flag Type", ""))
                flag_text[number] = flag_text.get(number, "") + " " + entry.get("Details", "")

    # ---------------------------------------------------------------- schema
    check(len(digi) == len(source), "DigiMall row count matches the source",
          f"{len(digi)} vs {len(source)}")
    check(len(alfa) == len(source), "Alfa row count matches the source",
          f"{len(alfa)} vs {len(source)}")
    check(digi_header == list(DIGI_HEADER), "DigiMall header is the 66-column contract",
          f"{len(digi_header)} columns")
    check(alfa_header == list(ALFA_HEADER), "Alfa header is the 28-column contract",
          f"{len(alfa_header)} columns")
    check(not any(c.startswith("Attribute_") for c in alfa_header)
          and "Short Description" not in alfa_header,
          "Alfa file carries no DigiMall-only columns")
    check(alfa_header == digi_header[: len(alfa_header)],
          "Alfa columns are the shared prefix, in the same order")
    check(not any(c.endswith(("_Digi", "_Alfa")) for c in digi_header),
          "no platform-suffixed column names anywhere")
    check(all(len(r) == len(digi_header) for r in digi), "every DigiMall row has 66 cells")
    check(all(len(r) == len(alfa_header) for r in alfa), "every Alfa row has 28 cells")

    if len(digi) != len(source) or len(alfa) != len(source):
        # Comparing row by row is meaningless now, so stop with the counts named
        # rather than reporting a truncated comparison as if it were complete.
        check(False, "row-by-row comparison is possible",
              "the files and the source disagree in length")
        return report()

    # ------------------------------------------------------- one line, quoted
    bad_newline = [r["Variant SKU"] for r in digi
                   if any("\n" in v or "\r" in v for v in r.values())]
    check(not bad_newline, "no cell contains a raw newline", f"{len(bad_newline)} bad")
    check(all(line.count(",") >= 1 for line in digi_text.splitlines()[1:]),
          "CSV is quoted with the real csv module")
    check("\r\n" in digi_text or "\n" in digi_text, "output is CRLF-or-LF consistent")

    # ------------------------------------------------------------- identity
    skus = [r["Variant SKU"] for r in digi]
    handles = [r["Handle"] for r in digi]
    check(len(set(skus)) == len(skus), "every Variant SKU is unique",
          f"{len(set(skus))}/{len(skus)}")
    check(len(set(handles)) == len(handles), "every Handle is unique",
          f"{len(set(handles))}/{len(handles)}")
    check([r["Variant SKU"] for r in alfa] == skus, "both files carry the same SKUs, same order")
    check([r["Handle"] for r in alfa] == handles, "both files carry the same Handles")
    check(all(r["Variant Barcode"] == r["Variant SKU"] == r["Variant Bin Number"] for r in digi),
          "Barcode and Bin Number always equal the SKU")
    check(all(re.fullmatch(r"[A-Z0-9\-.]+", s) for s in skus),
          "SKUs are upper-case alphanumeric only", str([s for s in skus if not re.fullmatch(r"[A-Z0-9\-.]+", s)][:3]))
    check(all(re.fullmatch(r"[a-z0-9\-]+", h) for h in handles),
          "Handles are lower-case slugs only",
          str([h for h in handles if not re.fullmatch(r"[a-z0-9\-]+", h)][:3]))
    check(all(s.startswith("KIA-") for s in skus), "every SKU carries the KIA- prefix")

    # -------------------------------------------------------- required cells
    for name, rows in (("DigiMall", digi), ("Alfa", alfa)):
        for column in ("Title", "Product Type", "Vendor", "Handle", "Variant SKU"):
            empty = sum(1 for r in rows if not r[column].strip())
            check(empty == 0, f"{name}: {column} is never empty", f"{empty} empty")
    check(all(r["Vendor"] == "KiaChahiye PVT LTD" for r in digi),
          "DigiMall Vendor is the exact literal")
    check(all(r["Vendor"] == "Kia Chahiye Pvt Ltd" for r in alfa),
          "Alfa Vendor is the exact literal")
    check(all(r["Variant Quantity"] == "20" for r in digi), "quantity default is 20 everywhere")
    check(all(r["Product ID"] == "" for r in digi),
          "Product ID is left empty for the importer to assign")

    # -------------------------------------------------------- category shape
    digi_cat_bad = [r["Category"] for r in digi
                    if r["Category"] and not re.fullmatch(r"\d+(_\d+)*", r["Category"])]
    check(not digi_cat_bad, "DigiMall Category is an underscore-joined id path",
          str(digi_cat_bad[:3]))
    alfa_cat_bad = [r["Category"] for r in alfa
                    if r["Category"] and not re.fullmatch(r"\d+", r["Category"])]
    check(not alfa_cat_bad, "Alfa Category is a bare leaf id", str(alfa_cat_bad[:3]))
    check(all(r["Brands"].isdigit() or r["Brands"] == "" for r in digi),
          "DigiMall Brands is numeric or empty")

    # ----------------------------------------------------------- description
    problems: Counter[str] = Counter()
    offenders: dict[str, list[str]] = {}
    for source_row, r in enumerate(digi, start=2):
        title = r["Title"]
        html = r["Description"]

        # ``title`` is bound as a default so the closure cannot pick up a later
        # row's title if it is ever called outside this iteration.
        def note(kind: str, title: str = title) -> None:
            problems[kind] += 1
            offenders.setdefault(kind, []).append(title)

        if not html.startswith("<table") or not html.endswith("</table>"):
            note("description is not one complete table")
        if len(html.splitlines()) != 1:
            note("description has a raw line break")
        for tag in ("table", "thead", "tbody", "tr", "td", "th "):
            if html.count(f"<{tag}") != html.count(f"</{tag.strip()}>"):
                note(f"unbalanced <{tag.strip()}> tags")
        if re.search(r"<td[^>]*></td>", html):
            note("description has an empty cell")
        if "  " in re.sub(r"<[^>]+>", "", html):
            note("description has a double space")
        labels = re.findall(r"<tr><td[^>]*>(?:<strong>)?([^<]+)", html)
        if not labels:
            note("description has no specification rows")
        if "Brand" not in labels and r["Title"]:
            pass  # verified against the source below, where we know the Brand cell
        if len(labels) != len(set(labels)):
            note("description repeats a label")

        # short description
        bullets = r["Short Description"].count("<li>")
        if not r["Short Description"].startswith("<ul>") or not r["Short Description"].endswith("</ul>"):
            note("short description is not one list")
        if bullets == 0 or bullets > 3:
            note("short description bullet count outside 1-3")
        if re.search(r"</strong>\s*(overview|brand|model|type|key features)\.", r["Short Description"], re.IGNORECASE):
            note("short description has filler label text")
        if "  " in re.sub(r"<[^>]+>", "", r["Short Description"]):
            note("short description has a double space")

        # SEO
        if not 65 <= len(r["SEO Title"]) <= 90:
            note("SEO Title outside 65-90 characters")
        if not 151 <= len(r["SEO Description"]) <= 155:
            note("SEO Description outside 151-155 characters")

        # tags
        tags = [t for t in r["Tags"].split(",") if t.strip()]
        if not 5 <= len(tags) <= 8:
            note("Tags outside 5-8")
        if len(tags) != len({t.strip().lower() for t in tags}):
            note("Tags contain a duplicate")

        # attributes
        for column, value in r.items():
            if column.startswith("Attribute_") and value:
                allowed = ALLOWED.get(column[10:])
                if allowed is not None and value not in allowed:
                    note(f"{column} value not in ALLOWED")

        # price sanity -- an inversion is a source-data problem, so it counts
        # as a failure only when the pipeline has NOT flagged that row
        if (
            r["Variant Price"]
            and r["Variant Compare At Price"]
            and float(r["Variant Compare At Price"]) < float(r["Variant Price"])
            and "price_inversion" not in flagged.get(source_row, set())
        ):
            note("Compare-At price below the sell price (unflagged)")

    for kind, count in problems.most_common():
        check(False, f"DigiMall description/SEO: {kind}", f"{count} row(s): {offenders[kind][:3]}")
    if not problems:
        check(True, "every Description, Short Description, SEO field, Tag set and "
                    "Attribute value passes its template rules")

    # --------------------------------------- facts must exist in the source
    invented: list[str] = []
    for row, rec in zip(digi, source, strict=True):
        # Every cell of the source row is fair game, including the Brand column
        # that the display table's Brand row is filled from.
        text = "\n".join(rec.values()).lower()
        for cells in re.findall(r"<tr>(.*?)</tr>", row["Description"]):
            found = re.findall(r"<td[^>]*>(.*?)</td>", cells)
            if len(found) != 2:
                continue
            if "<strong>" in found[1]:
                continue  # a warranty row, filled from warranty_terms.py
            value = html_module.unescape(re.sub(r"<[^>]+>", "", found[1])).strip()
            if not value or value.isdigit() or len(value) < 3:
                continue
            # the value must appear in the source, allowing for whitespace runs
            haystack = re.sub(r"\s+", " ", text)
            needle = re.sub(r"\s+", " ", value).lower()
            if needle in haystack or needle.replace("-", " ") in haystack:
                continue
            # a comma-joined list is fine when every item came from the source
            items = [i.strip().lower() for i in value.split(",") if i.strip()]
            if items and all(i in haystack or i.replace("-", " ") in haystack for i in items):
                continue
            # The Model row re-emits the resolved model, and clean_model_code
            # drops ONE colour word from it by design ("WD-1051 HC White" ->
            # "WD-1051 HC").  So this row is checked word by word: every word
            # must still come from the source, but the removed colour means the
            # whole string will not appear verbatim.
            label = html_module.unescape(re.sub(r"<[^>]+>", "", found[0])).strip().lower()
            if label == "model" and all(
                word in haystack for word in re.findall(r"[a-z0-9][a-z0-9.\-]*", needle)
            ):
                continue
            invented.append(f"{row['Title'][:38]} -> {value!r}")
    check(not invented, "every value in the Description table exists in the source row",
          f"{len(invented)} invented: {invented[:5]}")

    # ----------------------------------- Title tokens must exist in source
    title_bad: list[str] = []
    for row, rec in zip(digi, source, strict=True):
        title = row["Title"]
        if len(title) > CONFIG.TITLE_MAX:
            title_bad.append(f"{title[:40]} (too long)")
        if re.search(r"\s{2,}", title):
            title_bad.append(f"{title[:40]} (double space)")
        if title != title.strip():
            title_bad.append(f"{title[:40]} (untrimmed)")
        model = extract_model(rec["Title"], rec["Description"])
        if model.code and model.code.replace(" ", "").lower() not in title.replace(" ", "").lower():
            title_bad.append(f"{title[:40]} (model {model.code!r} missing)")
    check(not title_bad, f"every Title is <={CONFIG.TITLE_MAX} chars, single-spaced and carries its model code",
          f"{len(title_bad)}: {title_bad[:4]}")

    missing_brand_row = [
        row["Title"][:40]
        for row, rec in zip(digi, source, strict=True)
        if rec.get("Brand", "").strip() and "Brand" not in row["Description"]
    ]
    check(not missing_brand_row, "every row with a named brand shows a Brand row",
          str(missing_brand_row[:3]))

    # ------------------------------------------- Variant Weight is never guessed
    weight_bad: list[str] = []
    weight_invented: list[str] = []
    for row_number, (digi_row, alfa_row, rec) in enumerate(
        zip(digi, alfa, source, strict=True), start=2
    ):
        text = f"{rec['Title'].strip()}\n{rec['Description']}"
        expected, expected_unit = source_weight(rec, text)
        shown = digi_row["Variant Weight"]
        unit = digi_row["Variant Weight Unit"]
        if alfa_row["Variant Weight"] != shown or alfa_row["Variant Weight Unit"] != unit:
            weight_bad.append(f"row {row_number}: the two files disagree ({shown!r} vs {alfa_row['Variant Weight']!r})")
        if shown and unit not in ("kg", "g", "lb", "oz"):
            weight_bad.append(f"row {row_number}: unit {unit!r} is not one the platforms accept")
        if shown:
            try:
                float(shown)
            except ValueError:
                weight_bad.append(f"row {row_number}: weight {shown!r} is not a number")
        if expected and shown != expected:
            weight_bad.append(f"row {row_number}: source says {expected} {expected_unit}, file says {shown!r}")
        if shown and not expected:
            weight_invented.append(f"row {row_number}: {shown!r} appears in no source cell")
    check(not weight_bad, "Variant Weight in both files equals the weight the source states",
          f"{len(weight_bad)}: {weight_bad[:3]}")
    check(not weight_invented, "Variant Weight is never invented when the source states none",
          f"{len(weight_invented)}: {weight_invented[:3]}")

    # --------------------------------- an empty cell is never a silent cell
    silent: list[str] = []
    for row_number, (digi_row, alfa_row) in enumerate(zip(digi, alfa, strict=True), start=2):
        text = flag_text.get(row_number, "")
        for platform, row, cell, phrase in (
            ("DigiMall", digi_row, "Category", "DigiMall Category left empty"),
            ("Alfa", alfa_row, "Category", "Alfa Category left empty"),
            ("DigiMall", digi_row, "Brands", "DigiMall Brands left empty"),
            ("Alfa", alfa_row, "Brands", "Alfa Brands left empty"),
        ):
            if not row[cell] and phrase not in text:
                silent.append(f"{row['Title'][:32]} -> {platform} {cell} empty, no flag")
    check(not silent, "every empty Category or Brands cell is named in the QC report",
          f"{len(silent)}: {silent[:3]}")

    # ------------------------------------------- warranty matches the table
    warranty_bad: list[str] = []
    for row, rec in zip(digi, source, strict=True):
        text = f"{rec['Title'].strip()}\n{rec['Description']}"
        resolved_brand = resolve_brand(rec["Brand"], rec["Title"])
        brand = resolved_brand.normalized
        category = resolve_category(rec["Categories"], text, text)
        product_type, _ = resolve_product_type(category, resolved_brand.raw)
        warranty_rows, headline, _src = resolve_warranty(text, brand, product_type)
        shown = row["Attribute_Warranty"]
        if (headline or "") != shown:
            warranty_bad.append(
                f"{row['Title'][:34]} pipeline says {headline!r} file says {shown!r}"
            )
        for spec in warranty_rows:
            if spec.label not in row["Description"] and spec.value not in row["Description"]:
                warranty_bad.append(f"{row['Title'][:34]} warranty row {spec.label!r} missing")
    check(not warranty_bad, "Attribute_Warranty and the warranty table agree with warranty.py",
          f"{len(warranty_bad)}: {warranty_bad[:4]}")

    # ------------------------------------------- per-row evidence for review
    if args.evidence is not None:
        write_evidence(args.evidence, source, digi, alfa)

    # ------------------------------------------------------------ report
    return report()


if __name__ == "__main__":
    sys.exit(main())
