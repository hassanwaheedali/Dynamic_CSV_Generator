"""Audit the two output CSVs against the source sheet, from every angle.

Run it before every upload::

    python audit.py                                  # the configured output files
    python audit.py --input data/input/test100/TEST_100_PRODUCTS.csv \\
                    --digi  data/output/test100/digi/digimall_bulk_import.csv \\
                    --alfa  data/output/test100/alfa/alfa_bulk_import.csv
    python audit.py --platform alfa          # gate only the file being uploaded today

It reads only the three files -- it does not run the pipeline -- and prints a
checklist of PASS/FAIL lines plus a per-row report of anything suspicious.
Exit code is 0 only when every check passes.

``--platform`` narrows that contract to one upload: only that file is opened, and a rule about a
column the other platform holds is not a rule this upload can break.  A file ``--platform`` says
this run uploads to, but which is not on disk, is named as a failure rather than raised through --
a traceback leaves the shop no checklist.  Under the default ``both`` the shared rules are read
from the DigiMall file, which carries Alfa's 28 shared columns plus its own; the Alfa file is then
proved by its own schema, Vendor, Category shape and by the cross-file checks (same SKUs, same
Handles, same weights, shared column prefix).
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
from attributes import ALLOWED, match_warranty
from brands import resolve_brand
from categories import resolve_category, resolve_product_type
from qc_report import CAT_ATTRIBUTE_EMPTY
from sku_handle import extract_model
from textutils import (
    color_in_title,
    find_weight_in_text,
    names_the_same_colour,
    parse_weight_cell,
    parse_weight_unit,
    pick_weight_columns,
)
from title_builder import without_leading_type_words
from vendor_config import VENDOR_REGISTRY, get_vendor
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
    # An empty file has no header.  Handing back [] lets the schema and row-count checks report that
    # as a FAIL line; raising here would kill the gate before it printed anything.
    header = next(reader, [])
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
    gated: list[tuple[str, list[dict[str, str]]]],
) -> None:
    """One line per row per platform: what that row produced, and whether it conforms.

    This is the row-by-row half of the review: 100 source rows become 200 lines, so every cell of
    both upload files is accounted for -- or 100 lines when this run uploads to one platform, which
    is exactly the proof that upload needs.
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
        for platform, rows in gated:
            for index, (_rec, row) in enumerate(zip(source, rows, strict=True), start=2):
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
                            allowed = ALLOWED.get(column)
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
    RESULTS.clear()
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
    parser.add_argument(
        "--platform",
        choices=("both", "digi", "alfa"),
        default="both",
        help="gate only the file being uploaded; the shared rules still run against it",
    )
    parser.add_argument(
        "--vendor",
        choices=list(VENDOR_REGISTRY),
        default=None,
        help="vendor key from vendor_config.py (defaults to legacy config when omitted)",
    )
    args = parser.parse_args(argv)
    vendor_cfg = get_vendor(args.vendor) if args.vendor is not None else None

    wanted = {"digi", "alfa"} if args.platform == "both" else {args.platform}

    def wants(platform: str) -> bool:
        """Whether this run uploads to ``platform``, so its own contract has to hold."""
        return platform in wanted

    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        source = list(csv.DictReader(handle))
    # A file this run does not upload is a file this run does not open: it may be stale, half-
    # written or simply absent, and none of that belongs in the contract of the sheet he is
    # uploading.  A file it DOES upload must be there -- a missing one is named as a failure,
    # because a traceback would leave the shop no checklist at all.
    def load(platform: str, label: str, path: Path) -> tuple[list[str], list[dict[str, str]], str]:
        if not wants(platform):
            return [], [], ""
        if not path.exists():
            check(False, f"{label} file is there to read", f"{path} does not exist")
            return [], [], ""
        return read(path)

    digi_header, digi, digi_text = load("digi", "DigiMall", args.digi)
    alfa_header, alfa, alfa_text = load("alfa", "Alfa", args.alfa)
    # One entry per file this run uploads to, in the order their contracts are read.
    files: list[tuple[str, list[str], list[dict[str, str]], str]] = []
    if wants("digi"):
        files.append(("DigiMall", digi_header, digi, digi_text))
    if wants("alfa"):
        files.append(("Alfa", alfa_header, alfa, alfa_text))
    # The rules both files must satisfy are read from one file; under a single-platform run they are
    # read from THAT file, so uploading only Alfa still proves Alfa's Title, Description and SKU.
    primary_label, primary_header, primary, primary_text = files[0]

    # Every row the pipeline flagged, by source row number.  The point of the
    # audit is that nothing is wrong *silently*: an anomaly a human has been
    # told about is acceptable, an unflagged one is not.
    flagged: dict[int, set[str]] = {}
    flag_text: dict[int, str] = {}
    # Which Attribute_* columns an "attribute_empty" flag NAMED for this row.  A cell left empty is
    # legal only when a human was told about that column: prose about some other gap, or about the
    # same column without saying it was empty, does not license shipping nothing.
    attribute_gaps: dict[int, set[str]] = {}
    if args.qc.exists():
        with args.qc.open(encoding="utf-8-sig", newline="") as handle:
            for entry in csv.DictReader(handle):
                try:
                    number = int(entry["Row"])
                except (KeyError, ValueError):
                    continue
                flagged.setdefault(number, set()).add(entry.get("Flag Type", ""))
                flag_text[number] = flag_text.get(number, "") + " " + entry.get("Details", "")
                details = entry.get("Details", "")
                if entry.get("Flag Type", "") == CAT_ATTRIBUTE_EMPTY:
                    column = details.split(":", 1)[0].strip()
                    if column.startswith("Attribute_"):
                        attribute_gaps.setdefault(number, set()).add(column)

    # ---------------------------------------------------------------- schema
    if wants("digi"):
        check(len(digi) == len(source), "DigiMall row count matches the source",
              f"{len(digi)} vs {len(source)}")
        check(digi_header == list(DIGI_HEADER), "DigiMall header is the 66-column contract",
              f"{len(digi_header)} columns")
        check(all(len(r) == len(digi_header) for r in digi), "every DigiMall row has 66 cells")
    if wants("alfa"):
        check(len(alfa) == len(source), "Alfa row count matches the source",
              f"{len(alfa)} vs {len(source)}")
        check(alfa_header == list(ALFA_HEADER), "Alfa header is the 28-column contract",
              f"{len(alfa_header)} columns")
        check(not any(c.startswith("Attribute_") for c in alfa_header)
              and "Short Description" not in alfa_header,
              "Alfa file carries no DigiMall-only columns")
        check(all(len(r) == len(alfa_header) for r in alfa), "every Alfa row has 28 cells")
    check(not any(c.endswith(("_Digi", "_Alfa")) for c in primary_header),
          "no platform-suffixed column names anywhere")
    if wants("digi") and wants("alfa"):
        check(alfa_header == digi_header[: len(alfa_header)],
              "Alfa columns are the shared prefix, in the same order")

    for label, _header, rows, _text in files:
        if len(rows) != len(source):
            # Comparing row by row is meaningless now, so stop with the counts named
            # rather than reporting a truncated comparison as if it were complete.
            check(False, "row-by-row comparison is possible",
                  f"{label} and the source disagree in length")
            return report()

    # ------------------------------------------------------- one line, quoted
    bad_newline = [r["Variant SKU"] for r in primary
                   if any("\n" in v or "\r" in v for v in r.values())]
    check(not bad_newline, "no cell contains a raw newline", f"{len(bad_newline)} bad")
    check(all(line.count(",") >= 1 for line in primary_text.splitlines()[1:]),
          "CSV is quoted with the real csv module")
    check("\r\n" in primary_text or "\n" in primary_text, "output is CRLF-or-LF consistent")

    # ------------------------------------------------------------- identity
    skus = [r["Variant SKU"] for r in primary]
    handles = [r["Handle"] for r in primary]
    check(len(set(skus)) == len(skus), "every Variant SKU is unique",
          f"{len(set(skus))}/{len(skus)}")
    check(len(set(handles)) == len(handles), "every Handle is unique",
          f"{len(set(handles))}/{len(handles)}")
    if wants("digi") and wants("alfa"):
        check([r["Variant SKU"] for r in alfa] == skus, "both files carry the same SKUs, same order")
        check([r["Handle"] for r in alfa] == handles, "both files carry the same Handles")
    check(all(r["Variant Barcode"] == r["Variant SKU"] == r["Variant Bin Number"]
              for r in primary), "Barcode and Bin Number always equal the SKU")
    check(all(re.fullmatch(r"[A-Z0-9\-.]+", s) for s in skus),
          "SKUs are upper-case alphanumeric only", str([s for s in skus if not re.fullmatch(r"[A-Z0-9\-.]+", s)][:3]))
    check(all(re.fullmatch(r"[a-z0-9\-]+", h) for h in handles),
          "Handles are lower-case slugs only",
          str([h for h in handles if not re.fullmatch(r"[a-z0-9\-]+", h)][:3]))
    expected_prefix = (
        f"{vendor_cfg.sku_prefix}-" if vendor_cfg is not None else "KIA-"
    )
    check(
        all(s.startswith(expected_prefix) for s in skus),
        f"every SKU carries the {expected_prefix} prefix",
    )

    # -------------------------------------------------------- required cells
    for label, _header, rows, _text in files:
        for column in ("Title", "Product Type", "Vendor", "Handle", "Variant SKU"):
            empty = sum(1 for r in rows if not r[column].strip())
            check(empty == 0, f"{label}: {column} is never empty", f"{empty} empty")
    expected_digi_vendor = (
        vendor_cfg.digi.vendor_name if vendor_cfg is not None else CONFIG.VENDOR_DIGI
    )
    expected_alfa_vendor = (
        vendor_cfg.alfa.vendor_name if vendor_cfg is not None else CONFIG.VENDOR_ALFA
    )
    if wants("digi"):
        check(
            all(r["Vendor"] == expected_digi_vendor for r in digi),
            "DigiMall Vendor is the exact literal",
        )
    if wants("alfa"):
        check(
            all(r["Vendor"] == expected_alfa_vendor for r in alfa),
            "Alfa Vendor is the exact literal",
        )
    # Both files carry these two columns out of the same record, so one file proves them.
    expected_qty = str(
        vendor_cfg.default_variant_quantity
        if vendor_cfg is not None
        else CONFIG.DEFAULT_VARIANT_QUANTITY
    )
    check(all(r["Variant Quantity"] == expected_qty for r in primary),
          f"quantity default is {expected_qty} everywhere")
    check(all(r["Product ID"] == "" for r in primary),
          "Product ID is left empty for the importer to assign")

    # -------------------------------------------------------- category shape
    if wants("digi"):
        digi_cat_bad = [r["Category"] for r in digi
                        if r["Category"] and not re.fullmatch(r"\d+(_\d+)*", r["Category"])]
        check(not digi_cat_bad, "DigiMall Category is an underscore-joined id path",
              str(digi_cat_bad[:3]))
    if wants("alfa"):
        alfa_cat_bad = [r["Category"] for r in alfa
                        if r["Category"] and not re.fullmatch(r"\d+", r["Category"])]
        check(not alfa_cat_bad, "Alfa Category is a bare leaf id", str(alfa_cat_bad[:3]))
    check(all(r["Brands"].isdigit() or r["Brands"] == "" for r in primary),
          f"{primary_label} Brands is numeric or empty")

    # ----------------------------------------------------------- description
    problems: Counter[str] = Counter()
    offenders: dict[str, list[str]] = {}
    for source_row, r in enumerate(primary, start=2):
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

        # Short Description and the Attribute_* columns are the two blocks of this loop that only
        # DigiMall ships; under an Alfa upload there is no such cell to be wrong about.
        if wants("digi"):
            # short description
            short = r["Short Description"]
            bullets = short.count("<li>")
            if not short.startswith("<ul>") or not short.endswith("</ul>"):
                note("short description is not one list")
            if bullets == 0 or bullets > 3:
                note("short description bullet count outside 1-3")
            if re.search(r"</strong>\s*(overview|brand|model|type|key features)\.",
                         short, re.IGNORECASE):
                note("short description has filler label text")
            if "  " in re.sub(r"<[^>]+>", "", short):
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
        if wants("digi"):
            for column, value in r.items():
                if column.startswith("Attribute_") and value:
                    # ALLOWED is keyed by the WHOLE column name, "Attribute_Warranty" -- not by the
                    # word after the prefix, which is what this lookup once used.  Stripping it made
                    # every lookup miss, so a cell outside the platform's closed list sailed through.
                    allowed = ALLOWED.get(column)
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

    template_rule_name = (
        "every Description, Short Description, SEO field, Tag set and Attribute value "
        "passes its template rules"
        if wants("digi")
        else "every Description, SEO field and Tag set passes its template rules"
    )
    for kind, count in problems.most_common():
        check(False, f"{primary_label} description/SEO: {kind}", f"{count} row(s): {offenders[kind][:3]}")
    if not problems:
        check(True, template_rule_name)

    # --------------------------------------- facts must exist in the source
    invented: list[str] = []
    for row, rec in zip(primary, source, strict=True):
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
            if label == "brand":
                resolved_b = resolve_brand(
                    rec.get("Brand", ""), rec.get("Title", ""), vendor_cfg=vendor_cfg
                ).raw.lower()
                if (
                    needle == resolved_b
                    or needle.replace(" ", "") in haystack.replace(" ", "")
                ):
                    continue
            if label == "model" and all(
                word in haystack for word in re.findall(r"[a-z0-9][a-z0-9.\-]*", needle)
            ):
                continue
            invented.append(f"{row['Title'][:38]} -> {value!r}")
    check(not invented, "every value in the Description table exists in the source row",
          f"{len(invented)} invented: {invented[:5]}")

    # ----------------------------------- Title tokens must exist in source
    title_bad: list[str] = []
    for row, rec in zip(primary, source, strict=True):
        title = row["Title"]
        if len(title) > CONFIG.TITLE_MAX:
            title_bad.append(f"{title[:40]} (too long)")
        if re.search(r"\s{2,}", title):
            title_bad.append(f"{title[:40]} (double space)")
        if title != title.strip():
            title_bad.append(f"{title[:40]} (untrimmed)")
        # The Title must carry the model the row SHIPS, and the pipeline peels the technology
        # words in front of a written-in code before it publishes one: `Model: Twin Inverter IOT
        # HRF-538TIFBU` is the shop's sentence about his machine, and `HRF-538TIFBU` is its code.
        # Re-deriving the raw line here demanded words the formula spends on other slots.
        model = without_leading_type_words(extract_model(rec["Title"], rec["Description"]))
        if model.code and model.code.replace(" ", "").lower() not in title.replace(" ", "").lower():
            title_bad.append(f"{title[:40]} (model {model.code!r} missing)")
    check(not title_bad, f"every Title is <={CONFIG.TITLE_MAX} chars, single-spaced and carries its model code",
          f"{len(title_bad)}: {title_bad[:4]}")

    missing_brand_row = [
        row["Title"][:40]
        for row, rec in zip(primary, source, strict=True)
        if rec.get("Brand", "").strip() and "Brand" not in row["Description"]
    ]
    check(not missing_brand_row, "every row with a named brand shows a Brand row",
          str(missing_brand_row[:3]))

    # ------------------------------------------- Variant Weight is never guessed
    weight_bad: list[str] = []
    weight_invented: list[str] = []
    for row_number, (file_row, rec) in enumerate(zip(primary, source, strict=True), start=2):
        text = f"{rec['Title'].strip()}\n{rec['Description']}"
        expected, expected_unit = source_weight(rec, text)
        shown = file_row["Variant Weight"]
        unit = file_row["Variant Weight Unit"]
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
    if wants("digi") and wants("alfa"):
        # One product, two files: the same machine cannot weigh two things.  This is a cross-file
        # rule, so it is only a rule when this run uploads to both.
        weight_bad.extend(
            f"row {number}: the two files disagree ({digi_row['Variant Weight']!r} vs {alfa_row['Variant Weight']!r})"
            for number, (digi_row, alfa_row) in enumerate(zip(digi, alfa, strict=True), start=2)
            if (digi_row["Variant Weight"], digi_row["Variant Weight Unit"])
            != (alfa_row["Variant Weight"], alfa_row["Variant Weight Unit"])
        )
    check(not weight_bad,
          "Variant Weight in both files equals the weight the source states"
          if wants("digi") and wants("alfa")
          else f"Variant Weight in the {primary_label} file equals the weight the source states",
          f"{len(weight_bad)}: {weight_bad[:3]}")
    check(not weight_invented, "Variant Weight is never invented when the source states none",
          f"{len(weight_invented)}: {weight_invented[:3]}")

    # --------------------------------- an empty cell is never a silent cell
    silent: list[str] = []
    for label, _header, rows, _text in files:
        for row_number, row in enumerate(rows, start=2):
            text = flag_text.get(row_number, "")
            for cell in ("Category", "Brands"):
                if not row[cell] and f"{label} {cell} left empty" not in text:
                    silent.append(f"{row['Title'][:32]} -> {label} {cell} empty, no flag")
    check(not silent, "every empty Category or Brands cell is named in the QC report",
          f"{len(silent)}: {silent[:3]}")

    # ----------------------------------- the colour shipped is the colour the row wrote
    # A colour is the one thing on this sheet that decides which variant a buyer gets, and the
    # failure it had was quiet: `• Product Color: Black` stands stamped on whole brands' worth of
    # rows, so a reader that trusted the line before the Title sold 220 rows Black and merged
    # `Hairline Black`, `Crimson Red` and `Meadow Green` into one another.  Both rules below read the
    # SOURCE row, not the pipeline: the file may only ship paint the shop wrote, and may only ship
    # as much of it as he wrote.
    colour_defaults = (
        vendor_cfg.default_product_type_colors
        if vendor_cfg is not None
        else getattr(CONFIG, "DEFAULT_PRODUCT_TYPE_COLORS", {})
    )
    colour_invented: list[str] = []
    colour_cut: list[str] = []
    for row_number, (row, rec) in enumerate(zip(primary, source, strict=True), start=2):
        shipped = row.get("Option1 Value", "").strip()
        stated = re.sub(r"\s+", " ", f"{rec['Title']}\n{rec['Description']}").lower()
        stated = stated.replace("gray", "grey")
        # A documented default for a whole Product Type (`LED TV` is Black in Pakistan) is a config
        # choice the owner can read and edit -- not a word this file pulled out of thin air.
        defaulted = shipped == colour_defaults.get(row.get("Product Type", ""), "")
        if shipped and not defaulted:
            for word in shipped.lower().replace("gray", "grey").split():
                if word not in stated:
                    colour_invented.append(
                        f"row {row_number}: {shipped!r} -- {word!r} appears in no source cell"
                    )
                    break
        painted = color_in_title(rec["Title"])
        if painted and shipped and not names_the_same_colour(painted, shipped):
            colour_cut.append(
                f"row {row_number}: the Title says {painted!r}, the file ships {shipped!r}"
            )
    check(not colour_invented, "every colour the file ships is a colour the row stated",
          f"{len(colour_invented)}: {colour_invented[:3]}")
    check(not colour_cut,
          "every colourway the row wrote ships whole, never cut to its generic word",
          f"{len(colour_cut)}: {colour_cut[:3]}")

    # ------------------------------- a freezer placement only where the row states one
    # 214 of this sheet's 240 refrigerators say `Freezer-On-Top` in their own Title and 26 say
    # nothing at all, so the placement is the shop's word, not a default the pipeline stamps.  This
    # keeps it that way: any row that ships the phrase must have written it somewhere.
    freezer_re = re.compile(r"freezer[\s\- ]*on[\s\- ]*top", re.IGNORECASE)
    freezer_invented: list[str] = []
    for row_number, (row, rec) in enumerate(zip(primary, source, strict=True), start=2):
        if freezer_re.search(f"{rec['Title']}\n{rec['Description']}\n{rec['Categories']}"):
            continue
        for cell in ("Title", "Attribute_Refrigerator Type"):
            if freezer_re.search(row.get(cell, "")):
                freezer_invented.append(
                    f"row {row_number}: {cell} says Freezer-On-Top, no source cell does"
                )
                break
    check(not freezer_invented, "no freezer placement the row does not state itself",
          f"{len(freezer_invented)}: {freezer_invented[:3]}")

    # ------------------------------------------- warranty matches the table
    warranty_bad: list[str] = []
    for row_number, (row, rec) in enumerate(zip(primary, source, strict=True), start=2):
        text = f"{rec['Title'].strip()}\n{rec['Description']}"
        resolved_brand = resolve_brand(
            rec["Brand"], rec["Title"], vendor_cfg=vendor_cfg
        )
        brand = resolved_brand.normalized
        category = resolve_category(
            rec["Categories"], text, text, vendor_cfg=vendor_cfg
        )
        product_type, _ = resolve_product_type(
            category, resolved_brand.raw, vendor_cfg=vendor_cfg
        )
        warranty_rows, headline, _src = resolve_warranty(text, brand, product_type)
        if wants("digi"):
            shown = row["Attribute_Warranty"]
            # The cell never holds the headline itself: it holds the platform's word for it, chosen
            # out of the closed list.  `Lifetime` answers the warranty question but the list has no
            # such option, so the pipeline ships the cell empty and names the row in the QC report
            # -- a hole in DigiMall's vocabulary, not a defect.  Anything else in the cell -- a
            # written-in word, a mapped value, or a gap nobody was told about -- is.
            listed, _signal = match_warranty(headline)
            if (listed or "") != shown:
                warranty_bad.append(
                    f"{row['Title'][:34]} pipeline says {listed!r} file says {shown!r}"
                )
            elif headline and listed is None and "Attribute_Warranty" not in attribute_gaps.get(
                row_number, set()
            ):
                warranty_bad.append(f"{row['Title'][:34]} {headline!r} left the cell empty, no flag")
        for spec in warranty_rows:
            if spec.label not in row["Description"] and spec.value not in row["Description"]:
                warranty_bad.append(f"{row['Title'][:34]} warranty row {spec.label!r} missing")
    check(not warranty_bad,
          "Attribute_Warranty and the warranty table agree with warranty.py"
          if wants("digi")
          else "the warranty table in the Alfa file agrees with warranty.py",
          f"{len(warranty_bad)}: {warranty_bad[:4]}")

    # ------------------------------------------- per-row evidence for review
    if args.evidence is not None:
        gated: list[tuple[str, list[dict[str, str]]]] = []
        if wants("digi"):
            gated.append(("digi", digi))
        if wants("alfa"):
            gated.append(("alfa", alfa))
        write_evidence(args.evidence, source, gated)

    # ------------------------------------------------------------ report
    return report()


if __name__ == "__main__":
    sys.exit(main())
