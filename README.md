# Bulk CSV Pipeline

Turns one product sheet (1,800+ rows) into **two finished bulk-upload CSVs** —
one for DigiMall, one for Alfa — written to two separate folders, plus one
combined QC report naming every row a human should look at.

Everything is plain, deterministic Python: **no LLM calls, no network calls, no
external APIs**. Every business rule is a lookup table, a regex or a
keyword-to-enum dictionary that you can read, edit and audit.

For the current multi-store configuration and completed Phase 0/1 work, see
[The New Way](#the-new-way). The operating guide and historical sheet measurements
below are retained; dataset-specific counts describe those measured runs.

---

## Quick start

### Easiest way on Windows: double-click run_pipeline.bat

**Put your CSV in the input folder, double-click the launcher, select the store,
platform, and file, and collect the generated upload CSVs.** The launcher runs
generation, audit, and the advisory report together; no separate commands are needed.
Python 3.10+ must already be installed and available on PATH.

1. **Prepare the input sheet.** Keep these column headers spelled exactly as shown:

   ```csv
   Title,Description,Sell Price,Original Price,Categories,Brand,Image
   ```

   Put one product on each row. In Excel, use **Save As -> CSV UTF-8 (Comma delimited)**,
   for example `MY_PRODUCTS.csv`. A price or Description containing commas/newlines
   must remain a properly quoted CSV cell; Excel handles that when exporting.
   See [The input sheet](#the-input-sheet) for optional weight columns and details.

2. **Copy the CSV into this folder or any subfolder inside it:**

   ```text
   D:\Dynamic_CSV_Generator\kiachahiye_bulk_csv\data\input\
   ```

   Examples: `data/input/MY_PRODUCTS.csv` or
   `data/input/100_Products/step1_batch_01.csv`. The file menu searches all subfolders
   and shows each CSV's path relative to `data/input`, such as
   `100_Products/step1_batch_01.csv`. Excel `.xlsx` files are not listed.

3. **Double-click this launcher in File Explorer:**

   ```text
   D:\Dynamic_CSV_Generator\kiachahiye_bulk_csv\run_pipeline.bat
   ```

4. **Answer the three menus in order.** Type the displayed option number and press Enter:

   | Menu | What to choose |
   | --- | --- |
   | **VENDOR** | The store whose account you are preparing: Kiachahiye or Ajmer. |
   | **UPLOAD** | Both platforms, DigiMall only, or Alfa only. |
   | **SHEET** | Your input filename, for example `MY_PRODUCTS.csv`. |

5. **Wait for the result.** The tool generates the selected upload(s), audits them,
   and prepares QC and weak-description reports. The final screen shows
   **READY TO UPLOAD** when the audit passes. If it shows **DO NOT UPLOAD / AUDIT FAILED**,
   read the failure details and `run.log`, correct the problem, and run again.
   Review any QC findings even when the audit passes.

6. **Press Enter or O at the final prompt to open the output folder.** For
   Kiachahiye and `MY_PRODUCTS.csv`, the files are under:

   ```text
   kiachahiye_bulk_csv/data/output/kiachahiye/MY_PRODUCTS/
   ├── digi/digimall_bulk_import.csv    # upload this to DigiMall
   ├── alfa/alfa_bulk_import.csv        # upload this to Alfa
   ├── qc_report.csv
   ├── title_review_sample.csv
   ├── row_check.csv
   ├── thin_descriptions.csv
   └── run.log
   ```

   Ajmer runs use `data/output/ajmer/<input-filename-without-extension>/`.
   A single-platform run regenerates only that platform's upload. Files left by an
   earlier run for the other platform are marked **STALE** in the final file list.

**Another easy input option:** drag your CSV from any folder onto `run_pipeline.bat`.
That supplies the input path directly, so you only select the vendor and platform.
You do not have to copy that file into `data/input/`.

If the launcher reports **Python was not found**, install Python 3.10+ with
**Add Python to PATH** enabled, then reopen the launcher.

### Direct CLI (advanced)

For scripts or manual generation/audit steps, use the commands below. These direct
CLI defaults differ from the launcher's vendor/sheet-specific output folders.

```bash
cd kiachahiye_bulk_csv
pip install pytest mypy ruff openpyxl   # only for tests / type-checking / linting / .xlsx input

python main.py --vendor kiachahiye    # paths default to config.py; choose the store explicitly
```

That writes:

```
kiachahiye_bulk_csv/data/output/Products/
├── digi/digimall_bulk_import.csv      # 66 columns, Vendor = KiaChahiye PVT LTD
├── alfa/alfa_bulk_import.csv          # 28 columns, Vendor = Kia Chahiye Pvt Ltd
├── qc_report.csv                      # every flagged row, per file
├── title_review_sample.csv            # before/after Title sample for your review
└── row_check.csv                      # one line per row per platform (the row-by-row proof)
```

Then run the pre-upload checker, which re-reads the source sheet and the upload
files it is given and prints its checklist as it runs -- every rule is a
`check(...)` line in `audit.py`, and the screen shows each one as `[PASS]` or `[FAIL]`:

```bash
python audit.py --vendor kiachahiye --evidence data/output/Products/row_check.csv
python -m pytest tests/ -q                               # 760 tests at Phase 1 verification
```

`--platform digi` / `--platform alfa` runs one upload from end to end: `main.py`
writes only that file, `qc_report.csv` carries only its findings, and `audit.py`
opens only it. A rule about a column the other platform holds is not a rule this
upload can break, so an Alfa run never produces a DigiMall CSV and never blocks on
a DigiMall-only column. Under `both`, the audit checks both requested files,
including their cell-specific Title/SEO rules, Description rows, Vendor, IDs,
weights, and shared identity contracts. The Phase 0/1 baseline runs pass 56/56
checks; the checklist depends on which platforms are requested.

### Optional weight column

If the sheet carries a weight per row, the pipeline fills `Variant Weight` and
`Variant Weight Unit` in both files from it. The header is matched loosely
(`Weight`, `Weight (kg)`, `Shipping Weight`, `Gross Wt`, `Wt In Kgs`, …), with an
optional `Weight Unit` column. Without such a column the Description is read
instead (`Shipping Weight: 12 kg`, `Weight: 17.25 kg`).

**Shipping weight wins**: when a row states more than one weight, the packed
family (shipping / gross / carton / packed / set) is published in preference to
the net weight, in whatever order they appear. Units are normalised to the four
the platforms accept (`kg`, `g`, `lb`, `oz`); an unreadable cell leaves both
cells empty and flags the row rather than guessing.

### Pointing it at a new sheet

```bash
python main.py --vendor kiachahiye \
  --input "data/input/NEW SHEET.csv" \
  --digi  "data/output/digi/digimall_bulk_import_2026-01-15.csv" \
  --alfa  "data/output/alfa/alfa_bulk_import_2026-01-15.csv" \
  --qc    "data/output/qc_report_2026-01-15.csv"
```

Or edit the path defaults in `config.py`. For the interactive vendor/sheet/platform
workflow, run `python run_ui.py`; it uses vendor/sheet-specific output folders.

### Re-running the 100-product stress test

```bash
python main.py --vendor kiachahiye --input data/input/test100/TEST_100_PRODUCTS.csv \
               --digi   data/output/test100/digi/digimall_bulk_import.csv \
               --alfa   data/output/test100/alfa/alfa_bulk_import.csv \
               --qc     data/output/test100/qc_report.csv \
               --sample-titles data/output/test100/title_review_sample.csv
python audit.py --vendor kiachahiye --input data/input/test100/TEST_100_PRODUCTS.csv \
                --digi   data/output/test100/digi/digimall_bulk_import.csv \
                --alfa   data/output/test100/alfa/alfa_bulk_import.csv \
                --qc     data/output/test100/qc_report.csv \
                --evidence data/output/test100/row_check.csv
```

Pass `--sample-titles` every time: without it the run writes its Title sample to
the default path and replaces the real sheet's review file.

### Checks

Run from `kiachahiye_bulk_csv/` (PowerShell):

```powershell
python -m pytest tests/ -q                       # includes the real-sheet tests
$env:MYPYPATH = (Get-Location).Path
python -m mypy --explicit-package-bases .         # production modules and tests
python -m ruff check .
```

---

## The input sheet

The sheet must supply `Title`, `Description`, `Sell Price`, `Original Price`,
`Categories`, `Brand` and `Image`.  `Vendor` is **not** required: neither file's
Vendor is ever taken from the sheet -- each selected store/platform cell supplies
its own literal from `vendor_config.py`, so a sheet without a Vendor column
runs normally, and a sheet that has one has its value read and ignored.
`Weight`, `Weight Unit` (and any other weight-worded column) are optional; when
absent, the Description is searched instead.


These 7 columns, any order, `.csv` or `.xlsx`:

`Title, Description, Sell Price, Original Price, Categories, Brand, Image`

plus, optionally: `Vendor` (ignored) and any weight column (`Weight`,
`Shipping Weight`, `Weight (kg)`, …) with an optional unit column.

* Descriptions may span many lines — they are read with a real CSV parser.
* Prices may carry thousands commas (`"36,375"`).
* `Vendor` is read and then **ignored on purpose**: each output file uses its
  configured store/platform literal. Legacy `vendor_cfg=None` Python callers
  retain the constants in `config.py`.

---

## Two files, never one

| | DigiMall | Alfa |
|---|---|---|
| Columns | 66 | 28 |
| Vendor constant | `KiaChahiye PVT LTD` | `Kia Chahiye Pvt Ltd` |
| `Category` shape | full path, `11639_11643_11661_11669` | bare leaf id, `11509` |
| `Brands` | DigiMall's own numeric id | Alfa's own numeric id (often a different number) |
| `Description` shape | that cell's `description_template` | that cell's `description_template` |
| `Short Description`, `Commission Percentage`, 36 × `Attribute_*` | yes | **none of these columns exist** |

Both files are projected from **one** internal `ProductRecord` per row. SKU, price,
images, Handle, and other shared facts retain their common contracts. Title/SEO,
Vendor, marketplace IDs, and Description presentation follow each cell’s settings.

For `Description`, the record carries the spec rows once, and each of the four
cells renders those facts in its selected template. Restyling Alfa does not move
a fact in DigiMall's file. See
[Restyling one file's Description](#restyling-one-files-description-the-template).

---

## Reading the QC report (`qc_report.csv`)

One row per flagged source row: row number, title, **which file is affected**,
severity, flag type and a plain-English reason. **Exactly one line per finding** --
the counting pass that resolves SKU/Handle collisions reports into a scratch
collector, so a finding is never listed twice.

**Severity `review`** — a human should decide something:

| Flag | Meaning |
|---|---|
| `brand_missing_digi` / `brand_missing_alfa` | brand has no id in that platform's list → `Brands` left empty |
| `category_missing_digi` / `category_missing_alfa` | breadcrumb matched no category key → `Category` left empty |
| `ac_inverter_status_unknown` | an air conditioner whose text never says inverter / non-inverter, and DigiMall has separate leaves for those → left empty rather than guessed |
| `fallback_sku` | no model code found; SKU built from title words — **verify before upload** |
| `attribute_empty` | DigiMall `Attribute_*` had a raw signal that matched no allowed value; the raw text is in the report so you can extend the alias table (1,022 cells on this sheet -- every string is listed under *Known gaps*) |
| `price_inversion` | the sheet's Regular Price is **not above** its Sell Price (smaller or equal — a data-entry mistake); that number is ignored, a Compare At is derived instead, and the row is listed so the sheet gets fixed |
| `product_type_inferred` | the breadcrumb matched nothing, so Product Type was derived from it |
| `short_description_thin` | the source states fewer than 3 standout facts, so the field is left short rather than padded (216 rows on this sheet; see *Short Description* below) |
| `title_description_conflict` | the Title and the Description state a different tap count; the SKU follows the Title (2 rows) |
| `seo_description_length` | SEO Description could not be padded into 151-155 from real source facts — fires 0 times on this sheet |

**Severity `info`** — a deterministic default, nothing to fix:

`quantity_defaulted` (input has no stock column → 20), `weight_missing` (no
weight in the source → blank), `compare_at_derived` (sheet stated no Regular
Price at all → Variant Compare At Price = Sell Price + `COMPARE_AT_MARKUP_PERCENT`
rounded up to a round figure), `handle_deduplicated` / `sku_disambiguated`
(uniqueness suffixes, see below), `title_kept_from_source`,
`thin_description` (no filler rows were invented).

### Cleaning a messy Description column first (optional)

If a sheet's Description is a crashed-together blob -- an intro sentence glued to
an all-caps feature run, a pasted "Feature <tab> Description" header, tab labels,
mojibake -- the pipeline publishes it badly even though every fact is present.
`clean_descriptions.py` rewrites **only** the Description column, using only the
words already there:

```bash
python3 clean_descriptions.py --input "sheet.csv" --out "sheet_CLEANED.csv" --report "cleanup.csv"
```

It splits a line only where the source already breaks it (sentence punctuation, a
dash, a bullet, a tab, a colon, or a sentence glued onto a `)`), turns tab/colon
labels into `Label: Value` rows, cuts structural lines that carry no fact, and
fixes the encoding damage Excel exports. A run of feature words with **no**
separator is left as one bullet and named in the report for a human to split --
the tool never guesses where one feature ends.

A **feature run** -- a long line written almost entirely in capitals, like an AC
shortlist -- is split too, at markers the source itself provides: a closing
bracket, a slash, the row's own Brand word, and any phrase from the editable
`FEATURE_KEYWORDS` list (matched outside brackets, longest phrase first). Joined
back together the pieces are the original text, word for word; the report counts
the runs it split, and the audit still has to pass. Runs the list cannot split are
named in the report rather than guessed at (0 on this sheet after the list was
completed).

Measured on the client's 1800-row sheet (raw vs cleaned, same pipeline):

| | raw sheet | cleaned sheet |
|---|---|---|
| Key Features items published | 1,507 | **5,021** |
| spec rows in the tables | 22,224 | **23,323** |
| `thin_description` flags | 235 | **115** |
| `short_description_thin` flags | 216 | **126** |
| rows whose Short Description holds all three bullets | 1,584 | **1,674** |
| audit | 45/45 | **45/45** |

Every other column is copied through untouched (byte-for-byte, checked), and the
cleaned sheet is audited exactly like the original. The only character the cleaner
ever adds is a plain `-` where the source used a non-breaking hyphen (`‑`,
U+2011, Word's invisible look-alike); nothing else is ever inserted.

### Short Description: three bullets only where the source pays for three

The field always asks for three standout facts and takes them, in order, from:
the table's headline specs, the row's individual Key Features (short ones first),
the Description's own opening sentence, and finally the Product Type. Nothing is
invented to reach three.

That means the count depends on the **source**, and the cleaner is what moves it:

| | rows with 1 / 2 / 3 bullets | three bullets |
|---|---|---|
| your sheet as-is | 180 / 36 / 1,584 | **1,584 of 1,800** |
| cleaned sheet | 112 / 14 / 1,674 | **1,674 of 1,800** |

The 126 rows the cleaned sheet still cannot fill are listed, with the reason, in
`data/output/cleaned/short_description_worklist.csv` -- 110 of them are rows whose
Description states exactly **one** fact (a name, a capacity, a type), and 16 state
two. Those rows need a sentence from you, not a guess from the tool. The list is
rebuilt from the advisory report for the cleaned sheet:

```bash
python3 thin_report.py --input "data/output/cleaned/READY_FIRST_STEP_1_CLEANED.csv" \
  --vendor kiachahiye --platform digi --built data/output/cleaned/digi/digimall_bulk_import.csv \
  --qc data/output/cleaned/qc_report.csv \
  --out data/output/cleaned/thin_descriptions_cleaned.csv   # then keep Short_Desc_Bullets < 3
```

### Which Descriptions need work (`thin_descriptions.csv`)

A separate, advisory report — it never changes an upload file, and the pipeline
never reads it. It grades the **source** Description of every row against the
listing that row actually produced, and writes the weak ones worst-first:

```bash
python3 thin_report.py            # uses the paths in config.py
python3 thin_report.py --input X.csv --built Y.csv --qc Z.csv --out W.csv
```

| Column | Meaning |
|---|---|
| `Row` | the source sheet's own line number — the same number the QC report uses, so you can jump straight to it in Excel |
| `Severity` | `high` = the listing is visibly poor; `medium` = usable but the source could say much more |
| `Issues` | every reason that row was listed, e.g. `one-line Description; very short source (43 chars)` |
| `One_Line` | `yes` when the source Description is a single line — filter this column for exactly that list |
| `Description_Chars` / `Description_Lines` | what the sheet itself contains |
| `Spec_Rows_In_Listing` / `Short_Desc_Bullets` | what the file named by `--built` really shows — on a one-platform run that is that platform's own upload (`run_ui.py` grades the first file in scope, so an Alfa-only run reads the Alfa CSV, not a DigiMall one). This report counts rows through the selected Description template's `extract()` function |
| `Why_It_May_Matter` | the same reasons in plain English |
| `QC_Flags` | the row's flags from the QC report, for context |

The thresholds are `THIN_*` in `config.py` (`THIN_DESCRIPTION_CHARS` = 200,
`SHORT_DESCRIPTION_CHARS` = 300, `THIN_SPEC_ROWS` = 3, `THIN_SHORT_BULLETS` = 3).
Change a number and the worklist re-grades on the next run.

On the real sheet it lists **536 rows: 206 high and 330 medium, of which 186 are
one-line sources** — the 186 are the rows to send back to whoever writes the copy.

The terminal summary prints, at the end of every run:

* rows needing review / info-only / completely clean, **per platform, never merged**
* DigiMall-vs-Alfa empty `Category` and `Brands` counts, side by side
* **`BRAND NOT FOUND IN LOOKUP TABLE`** — each brand name, its row count, and the exact constant to edit
* **`CATEGORY NOT FOUND IN LOOKUP TABLE`** — each breadcrumb, its row count, and the constant to edit
* **`DESCRIPTION TEMPLATE PER FILE`** — the shape that served each file this run wrote, and the exact `vendor_config.py` cell to edit to change it
* warranty coverage by source, and which brands still have no warranty table

---

## Where to edit things (the only places you ever need to touch)

| To change… | Open | Constant |
|---|---|---|
| **Vendor strings** | `vendor_config.py` | `<store>.<platform>.vendor_name`; config.py constants are legacy API defaults |
| Input / output file paths | `config.py` | `INPUT_FILE`, `DIGI_OUTPUT`, `ALFA_OUTPUT`, … |
| Default quantity, SEO length windows, Title cap | `config.py` | `DEFAULT_VARIANT_QUANTITY`, `SEO_*`, `TITLE_MAX` |
| What counts as a thin Description in the worklist | `config.py` | `THIN_*` |
| **One file's `Description` shape** | `vendor_config.py` | `<store>.<platform>.description_template` — the screen spells it `Kiachahiye.alfa.description_template` (see [Restyling one file's Description](#restyling-one-files-description-the-template)) |
| **A new `Description` shape** | `description_builder.py` | `DESCRIPTION_TEMPLATES` — paste a live listing's HTML and register it |
| **Warranty terms** | `warranty_terms.py` | `WARRANTY_TERMS` — brand → category → parts |
| LED TV warranty on/off | `vendor_config.py` | `<store>.apply_tv_warranty_table`; config.py retains the legacy default |
| DigiMall brand ids | `vendor_config.py` | `<store>.digi.brands` |
| Alfa brand ids | `vendor_config.py` | `<store>.alfa.brands` |
| Brand spelling variants | `vendor_config.py` | `<store>.brand_aliases` / `brand_display_map` |
| DigiMall category paths | `vendor_config.py` | `<store>.digi.categories` |
| Alfa category leaf ids | `vendor_config.py` | `<store>.alfa.categories` |
| Breadcrumb wording → table key | `categories.py` | `DIGI_SEGMENT_ALIASES`, `ALFA_SEGMENT_ALIASES` |
| Breadcrumbs that are outside the catalogue | `categories.py` | `STOP_SEGMENTS` |
| Plain-text `Product Type` | `categories.py` | `PRODUCT_TYPE_MAP` |
| Allowed attribute values (incl. exact warranty wordings) | `attributes.py` | `ALLOWED` |
| Attribute phrasing → allowed value | `attributes.py` | `ALIASES` |
| Which attributes apply to which Product Type | `attributes.py` | `SCOPE` |
| Warranty terms, brand by brand | `warranty_terms.py` | `WARRANTY_TERMS` |
| Series words kept in rebuilt Titles | `sku_handle.py` | `SERIES_WORDS` |
| Filenames / folders | `config.py` | CLI path defaults; run_ui.py selects vendor/sheet folders |

Every one of those blocks is marked with a banner comment:

```
# ===========================================================================
#  EDIT HERE -- <what it is>
# ===========================================================================
```

Adding a brand id is one line: `"newbrand": 1234,`. Adding a category is a key
in the id table **and** a key in `PRODUCT_TYPE_MAP`. Nothing is computed or
inferred behind your back.

**Proof that an edit propagates** (both measured on the 100-product file, then
reverted -- the outputs came back byte-identical, md5 for md5):

| One-line edit | Effect on the next run |
|---|---|
| Added `"Duzin"` to `SERIES_WORDS` (`sku_handle.py`) | 1 of 100 rows changed: its Title and SEO Title gained the series word (`Haier HPU-24HDZ 2 Ton White **Duzin** Inverter Air Conditioner`), and the Alfa file followed from the same internal record |
| Added `"230 V"` to `ALLOWED["Attribute_Volt"]` (`attributes.py`) | `Attribute_Volt` filled on **306** previously-empty rows (`220V` 98 -> 95, as `230 V` won the earlier candidate), and `attribute_empty` flags fell **1,018 -> 715** |

Neither edit needed a code change anywhere else: the tables are read at run time
and flow straight into the output columns.

---

## Restyling one file's Description (the template)

There are four cells -- `Kiachahiye.digi`, `Kiachahiye.alfa`, `Ajmer.digi`,
`Ajmer.alfa` -- and each one names the shape of the `Description` column in **its own
file**. The value is a name from `DESCRIPTION_TEMPLATES` (`"spec_table"` is the table
the shop has always uploaded and is the default when a cell says nothing), or, rarely,
a `DescriptionTemplate` written inline.

Editing one cell edits one file. Pointing `Kiachahiye.alfa` at a new shape leaves
`Kiachahiye.digi`, `Ajmer.digi` and `Ajmer.alfa` uploading byte-identical CSVs -- not a
hope, a test (`tests/test_description_isolation.py` proves it on the real sheet, digest
by digest). Two stores may name the **same** template and then ship the same bytes from
one registry entry.

Every cell renders its own rows, every row: nothing is cached and nothing is shared
between files. Re-measured on the real sheet (2026-11-02, 752 rows, `--platform both`,
so 1,504 renders): 128 ms for the fastest of nine passes -- about 92 microseconds a
render, ~1.8% of the ~7.5 s run -- and it is what keeps "Alfa looks different now" from
ever meaning "check DigiMall again".

### Handing over a live listing

This is how a new shape gets made -- copy the Description of a listing you like:

1. Open that listing in a browser, view its page source, and select the **whole**
   Description table, from `<table …>` to `</table>`.
2. In `description_builder.py`, write a `DescriptionTemplate` around that markup:
   `render(rows)` fills it with the `Label: Value` pairs it is handed, `extract(text)`
   reads the same markup back into those pairs, and `starts_with` / `ends_with` declare
   the boundary it ships (`"<table"` / `"</table>"`).
3. Register it in `DESCRIPTION_TEMPLATES` under a short name.
4. Name it on **one** cell in `vendor_config.py`, e.g.
   `description_template="wide_table"` inside `Kiachahiye`'s `alfa=PlatformConfig(...)`.
5. Run `python main.py --vendor kiachahiye` (or the store you edited). The summary names the shape for each
   file before you upload anything.

Step 4 is the whole deployment; steps 2-3 only *offer* a shape that no file uses yet,
which is why they are safe to leave half-finished.

### The promises a new shape has to keep

**Current status:** startup validation checks template round trips, escaping,
nesting, and warranty markers. Since Phase 0, audit.py and thin_report.py read
rows through the selected template’s `extract()` function on the requested
platform files. Remaining table-specific conformance restrictions are future
Phase 2 work.

**Historical compatibility notes:** the detailed notes below describe the earlier
markup-reader contract and the audit gaps that motivated Phase 0. They are kept
as project history; statements below that an extractor-based audit is still
pending were resolved in Phase 0.


`audit.py` (the upload gate) and `thin_report.py` (the weak-Description worklist) both
read the **built file** with markup-shaped patterns, and this change deliberately left
them alone. So a pasted shape must keep these rules -- and it does not have to hope the
gate notices later: `validate_vendor_cfg` runs the conformance harness
(`template_problems`) over both cells of the store you are about to run, at startup, on
six probe rows (a plain label, a hyphenated code, an `&`, a value with doubled spaces,
and the bolded warranty line) plus a five-row **markup probe** whose own text is markup:
`<b>` in a value, a `<td>` inside a value, `<strong>` inside a row the shape already
bolds, markup in a **label**, and an unterminated `<b`. Each markup row is also rendered
once with its label and value cleared to plain text, and the two renders are compared
**tag by tag, by count** -- so a tag the shape already writes is caught exactly like one
it never writes. Counts are not structure: the finished fragment is also walked with the
open-element stack a browser keeps, so a closing tag written out of order is refused even
when every count agrees with the well-formed table. A shape that *raises* while being
judged is named the same way instead of crashing the run. One broken rule = one
plain-English line naming the exact cell, and no file is written:

| The shape must… | Because the readers… |
|---|---|
| ship one complete `<table …>` … `</table>`, declared via `starts_with` / `ends_with` | reject a Description that does not start with `<table`, and read rows inside that one fragment |
| write every spec row as exactly two `<td>` cells -- label first, value second | count a row only as a label/value pair; a one- or three-cell row is unreadable |
| write the row literally as `<tr><td…>` -- no space, no line break, no attribute on the `<tr>` | read rows with `<tr><td[^>]*>(?:<strong>)?([^<]+)`, and match a bare `<tr>` when checking a row's facts |
| keep `<table>` / `<thead>` / `<tbody>` / `<tr>` / `<td>` / `<th …>` balanced, and head a cell with an attribute (`<th style=…>`, never bare `<th>`) | count those six tags, spelling the header `"th "` with a trailing space |
| close them **in the order it opened them** -- no `</tr>` before its `</td>`, no `<strong>` left running into the next row | a crossing writes the same tags as a clean table, so no count can see it; the browser closes the cell at the `</tr>` and drops what follows, and the gate then finds one `<td>` in that row and skips it (`audit.py:494`) |
| carry exactly **one** header row of `<th>` cells | `row_check.csv`'s `Spec Rows` is `count("<tr") − 1`; no header (or two) reports one row short |
| leave no cell empty and never repeat a label | the gate calls an empty `<td></td>` a broken description, and a row whose label duplicates another reads back as one row, not two |
| bold exactly the rows it is *handed* as warranty rows -- both cells, as `spec_table` does -- whichever label they carry and wherever they sit | read bold as *the* warranty marker and prove `Attribute_Warranty` from it; most of the shop's listings state a term after a part (`Compressor`, `Parts`, `PCB`), not after the word `Warranty` |
| spell that bold as a literal `<strong>` and `</strong>` -- no attribute, no space inside the tag | `audit.py:408` and `:496` look for the text `<strong>`; `<strong class="w">` is bold to a browser and plain to the gate, so the warranty it marks stops being proved |
| escape every label **and** value it interpolates (`html.escape(text, quote=False)`), so `&` ships as `&amp;` and a value's `<b>` as text | a bare `&` is not an entity and the shop's own tag joins the table's, so the file the gate counts rows in is not the table the shop wrote |
| put the shop's words **between** the tags only, never inside one -- `title="{value}"` is not a smaller version of the same mistake | every reader takes a cell from between `>` and `<`, so text parked in an attribute is invisible to all of them, and `quote=False` -- the escaping this program documents -- leaves a `"` free to end the attribute early |
| write only entities a browser has a name for (`&amp; &lt; &gt; &nbsp; &#38; &#x26;`) -- never a made-up `&bogus;`, and never a semicolon-less `&amp` | an unknown name is not an entity either: the browser prints the letters and `html.unescape` leaves them, so the customer reads the code and no reader can tell the cell meant one `&` |
| write a numeric reference only where Unicode has a printable character (`&#38;`, `&#x26;`, `&#233;`) -- never `&#999999999;`, `&#0;`, `&#xD800;` or a control code like `&#27;` | `html.unescape` answers those with U+FFFD -- the replacement glyph in the middle of a specification -- or with nothing at all, and the shop's text silently loses a character |
| read back what it wrote: `extract(render(rows)) == rows` | no report can verify a shape that cannot state its own rows |

The harness cannot see that header row: a table written with no `<th>` at all passes every
machine rule above and still reports one spec row short in `row_check.csv`. It is the one
promise to check by eye -- and `tests/test_description_templates.py` holds every template
in the registry to it, so a shape that trips it fails the suite before a listing ships.

**A shape outside this list is not impossible -- it needs the audit upgrade agreed
first.** That upgrade is to make the gate and the worklist count rows through the
template's own `extract()` instead of through markup regexes. Until it happens the
harness above is the gate, and `tests/test_description_templates.py` keeps watch on the
one rule the harness cannot see (a header-less table that passes every startup check and
still reports one row short in `row_check.csv`).

Two `audit.py` gaps stay open, and both matter more now that files can be styled
separately. First, the gate reads its per-row Description rules -- and the "nothing was
invented" pass over the table -- from **one** file: the first in scope, which is DigiMall
in a both-platform run. Alfa's own `Description` therefore goes unproven, which was
harmless while both files shipped identical bytes and is not harmless once a cell can
pick its own shape. Second, its provenance parse matches rows literally as `<tr>`: markup
it cannot read gives it nothing to check, and it says nothing about that. The startup
harness blocks the second from `vendor_config.py` (a template with an attribute on its
`<tr>` tags is refused), but a harness is not a gate -- the real fix is the same one:
make `audit.py` and `thin_report.py` read rows through the template's `extract()`.

---

## Rules that are deliberately strict

* **Never invent a value.** If a lookup fails, the cell stays empty and the row
  is flagged. No rounding, no "closest match", no default category. When the
  source itself is contradictory (a Title saying "3 Taps" over a Description
  saying "2 Taps"), the Title wins and the row is flagged — nothing is smoothed
  over silently.
* **No fuzzy brand matching.** A near-miss name does not resolve; add it to
  `BRAND_ALIASES` by hand once you've seen it in the report.
* **Attributes are a closed vocabulary.** A value is written only if it matches
  an allowed string. Whitespace inside a token is ignored (`12 kg` = `12KG`), but
  units and punctuation are never rewritten — so `16 Cu.Ft` does **not** match
  `16 Cu Ft`, and a range like `220-240V` matches neither `220V` nor `240V`.
* **A flow rate is never a capacity.** `2.5 L/H` is a cooling rate, not a 2.5-litre
tank: the volume patterns refuse a `L`/`Ltr`/`Litre` unit immediately followed by
`/` or `per`, so a litre-per-hour phrasing can never be published as a tank size.
* **Attributes are scoped by Product Type**, so a refrigerator's "Inverter
  Compressor" bullet cannot land in `Attribute_INV/NON-INV` for a fridge unless
  you add `Refrigerator` to that column's `SCOPE` set.
* **Negations are checked first** — "Water Dispenser *Without* Refrigerator
  Cabinet" maps to `Without Refrigerator`, never to `With refrigerator`.
* **A stated warranty always beats a reference table**, and table parts are kept
  separate (never collapsed into one row).

## Duplicate SKUs and Handles

The sheet reuses one model code across genuinely different variants (e.g.
`9193-WB` appears 22 times at different prices and colours). Every SKU is
therefore unique, always:

1. `KIA-<model>` when that is unique in the run;
2. otherwise `KIA-<model>-<variant>`, where `<variant>` is built from the
   dimensions that actually distinguish variants — capacity, colour, taps,
   series, inverter state (e.g. `KIA-9193-WB-16CUFT-MEADOWGREEN`);
3. a last-resort `-2`, `-3` suffix, always flagged.

Handles follow the same pattern. Both are checked once, globally, across the
whole run, so the two files always carry the same SKU and Handle for a product.

---

## Warranty: one dict in the code, brand by brand

All warranty terms live in **`warranty_terms.py`** — one small file, nothing but
the table, sitting beside `brands.py` and `categories.py` exactly the same way:

```python
WARRANTY_TERMS: dict[str, dict[str, str]] = {
    "dawlance": {
        "Refrigerator": "Compressor = 12 Years; Parts = 1 Year",
        "Washing Machine (semi automatic / twin tub / single tub)": "Motor = 10 Years; Parts = 1 Year",
        "Washing Machine": "Motor = 12 Years; PCB = 4 Years; Parts = 1 Year",
        "LED TV": "Panel = 2 Years; Parts = 2 Years",
        ...
    },
    "tcl": {
        "Air Conditioner": "Compressor = 10 Years; PCB = 5 Years; Parts = 5 Years",
        "LED TV": "Panel = 2 Years; Parts = 2 Years",
        "Sound Bar": "Parts and Labour = 1 Year",
        "Speaker": "Parts and Labour = 1 Year",
    },
    ...
}
```

**To change a warranty, change the number.** That is the whole maintenance
story:

* one line per brand per category — `"brand": {"Category": "Part = Duration"}`;
* a bare duration means `Parts`: `"12 Years"` == `"Parts = 12 Years"`;
* a brand that gives one category two different warranties puts the words that
  tell the products apart in brackets, and the first entry whose words appear in
  the product Title wins:
  `"Air Conditioner (non inverter)"` then `"Air Conditioner (inverter)"` then the
  plain `"Air Conditioner"` as the default;
* a brand or category that is not listed gets no warranty row, and the run
  prints exactly which brand + category was left blank, so a gap is never
  hidden;
* the parts land in the Description table with the part name bolded, and the
  most important one becomes `Attribute_Warranty` (DigiMall only).  That bold is not
  styling: `audit.py` locates the warranty row by looking for `<strong>`, so every
  Description shape -- today's `spec_table` and any listing that gets pasted in later
  -- must bold exactly its warranty rows and nothing else.  Freeing bold from that
  meaning belongs to the deferred audit work described in
  [Restyling one file's Description](#restyling-one-files-description-the-template).

### What was applied, and from where

Every value came from the warranty catalogue you supplied, plus your three
confirmations: **Dawlance LED TV = 2 years**, **TCL sound bar = 1 year**,
**TCL speaker = 1 year parts and labour**.

Verified one row at a time against your catalogue — **every non-TV row matches
exactly**, and now every TV does too:

| | rows |
|---|---|
| identical to your catalogue | 1,405 |
| row states its own warranty, so the catalogue is rightly not used | 389 |
| **mismatches** | **0** |

Coverage on the 1,800-row sheet: **1,765 rows carry `Attribute_Warranty`**, and
the only 35 without it are rows whose own text says `Warranty: N/A` (33) or
`Compressor Warranty: Lifetime` (2) — a stated term always beats the table, and
those are kept exactly as the sheet wrote them.

The LED TV fallback switch is `VendorConfig.apply_tv_warranty_table` for configured
store runs; set it to `False` to disable TV reference fallback for that vendor.
The source’s own stated terms retain their established precedence. The global
`config.py` switch remains the default for legacy Python callers.

## Known gaps you can close by supplying data

The counts below are the historical 1,800-row sheet snapshot, not current
per-store totals. Current runs report their own gaps. Fill marketplace IDs in
the exact vendor/platform cell in `vendor_config.py`; the older legacy-table
names in this snapshot describe the original configuration.

These gaps were reported until the corresponding data was supplied:

1. **Brands with no id** — `Homage` (78 rows) and `Hisense` (4) are missing from
   **both** lists; `Orient` (83) is missing from Alfa's only. Add the real ids to
   `BRANDS_DIGI` / `BRANDS_ALFA`.
2. **Categories with no leaf** — DigiMall has no leaf for LED TV (166 rows),
   geysers (19), sound bars (4), speakers (2) or UPS (3); Alfa has none for air
   purifiers (4), sound bars (4), speakers (2) or UPS (3). Those cells stay empty
   until a leaf exists.
3. **Warranty terms** — complete for all 11 brands, including the three you
   confirmed. Only rows whose own text says `N/A` or `Lifetime` show no term.
4. **Weights** — your sheet now carries a `Weight` column, so all 1,800 rows ship
   a `Variant Weight` (the column beats the Description, and a shipping/gross
   figure outranks a net one); `weight_missing` fires 0 times. A row with no
   readable weight still leaves the cells empty and flags itself rather than
   borrowing a number.
5. **Attribute values** -- 1,022 cells carry a real signal that is not in the closed
   vocabulary yet, so the cell stays empty and the exact string is printed in the
   QC report (97 distinct column/value pairs). Ranked by how many rows each column
   affects:

   | Column | Rows | Strings the sheet used (rows) |
   |---|---|---|
   | `Attribute_Volt` | 607 | `230 V` (303), `105 V` (77), `220-240 V` (73), `100-240 V` (31), `125 V` / `160 V` / `170 V` |
   | `Attribute_Capacity` | 288 | `20 L` (35), `18000 L` (28), `3.7 Liters` (24), `25 Ltr`, `2.5 L`, `55 Ltr` |
   | `Attribute_Watts` |  87 | `900 W` (30), `800 W` (9), `8 W` (6) |

   Add the ones your marketplace really accepts to `ALLOWED` and they fill on the
   next run -- that is the `230 V` line in the table above, demonstrated.
   (`18000 L` is the sheet's own line for an AC's *heating capacity in BTU/h*; the
   pipeline reports it rather than turning it into a volume.)

---

## Layout

```
kiachahiye_bulk_csv/
├── config.py               path defaults, legacy values, length windows, thresholds
├── vendor_config.py        vendor/platform cells, maps, four-level resolved settings
├── series_corpus.py        vendor-aware whole-sheet series analysis
├── main.py                 entrypoint, CLI, terminal summary
├── models.py               dataclasses; one ProductRecord, two projections
├── textutils.py            string/colour/weight helpers
├── brands.py               §3  brand ids + aliases
├── categories.py           §4 + §5  category trees and Product Type
├── title_builder.py        §6  Title formula (rebuild-first, validate-fallback)
├── sku_handle.py           §7  model extraction, SKU, Handle, uniqueness
├── description_builder.py  §8  classifier, Tags, SEO, Short Description + DESCRIPTION_TEMPLATES
├── pricing.py              §9  prices and quantity
├── warranty.py             §10 + §12  warranty reading logic
├── warranty_terms.py       §10 + §12  WARRANTY_TERMS, the only table to edit
├── attributes.py           §11  the 36 DigiMall-only attributes
├── writers.py              §2  the two schemas and the two CSVs
├── qc_report.py            flag collection and the combined report
├── audit.py                independent checks on requested platform files
├── thin_report.py          the weak-Description worklist (advisory, below)
├── clean_descriptions.py   rewrite a messy Description column into clean bullets (pre-step)
├── ruff.toml               lint policy, every ignore commented
├── README.md               this file
├── OUTPUTS_GUIDE.md        Roman-Urdu guide: kaunsi file kis kaam ki hai
├── WHAT_CHANGED.md         code + CSV change log, verified on two products
├── tests/                  760 tests at completed Phase 1 verification
└── data/
    ├── input/              the source sheet
    └── output/             the two CSVs, the QC report, the Title sample, row_check.csv,
                            thin_descriptions.csv
```

## The New Way

This section records the project’s completed architecture improvements alongside
the full operating guide above. The layered hybrid approach keeps deterministic
Python extraction reusable while explicit vendor/platform configuration controls
presentation. Destination adapters and external data packs remain future work.

Design background: [master architecture research](<tasks/implementation_plan (3).md>).
Phase 1 follows the later approved Rev 4 refinements: strict cell-owned IDs,
local TitleSlots, unchanged ProductRecord fields, and rendering during row resolution.

### Phase 0: stabilization and compatibility

Phase 0, committed as `8499268`, established the verified foundation:

- Require an explicit CLI vendor while preserving legacy Python API callers.
- Wire vendor title-colour and TV warranty settings and configured SEO bounds.
- Use vendor-aware series vocabularies without cross-store leakage.
- Audit both requested outputs and read Description rows through each template’s extractor.
- Correct terminal UI audit-stage handling and thin-report vendor/platform selection.
- Preserve blank missing IDs, QC/UI reporting, HTML escaping, and CSV serialization.

All eight baseline outputs stayed byte-identical; baseline audits passed 56/56 checks.

### Phase 1: effective cell configuration and Title rendering

`vendor_config.resolve_cell(cfg, "digi" | "alfa")` returns a frozen
`ResolvedCellConfig`. Presentation settings use **Cell > Vendor > Platform > Engine**:
`title_formula`, `description_template`, `include_inverter`, `include_warranty`,
`omit_title_color_categories`, and `strict_title_rebuild`.

Raw `VendorConfig` and `PlatformConfig` attributes are declarations. `None` means
inherit; explicit `False`, empty strings, and empty sets are never treated as missing.
Use the resolved object to read effective values. Platform defaults live in
`PLATFORM_DEFAULTS`; a silent vendor allows them to take effect. Invalid formula or
template names fail startup validation, including explicit empty names.

```python
from dataclasses import replace
from vendor_config import KIACHAHIYE, resolve_cell

cfg = replace(KIACHAHIYE, alfa=replace(KIACHAHIYE.alfa, include_warranty=False))
assert resolve_cell(cfg, "alfa").include_warranty is False
cfg = replace(cfg, alfa=replace(cfg.alfa, include_warranty=None))  # inherit again
```

`dataclasses.replace()` and, on Python 3.13+, `copy.replace()` are supported.
Marketplace Brand/Category IDs always belong to the specific vendor/platform cell.
They never inherit from platform defaults, another cell, or legacy global tables.
Resolved mappings are read-only snapshots. Missing IDs remain blank with existing
non-blocking QC/UI reporting. The legacy Python API with `vendor_cfg=None` keeps its
legacy tables; user-facing CLI execution still requires `--vendor`.

`TITLE_FORMULAS` in `title_builder.py` is the authoritative named formula registry;
custom callables and the `ajmer_variant` alias remain supported. Each `resolve_row()`
call extracts immutable `TitleSlots` once and renders Title/SEO once for each cell,
even when both cells select identical policies. The pipeline retains its two existing
SKU/Handle collision passes. TV warranty fallback remains a vendor extraction policy;
`include_warranty` controls each cell's presentation.

`ProductRecord` fields are unchanged. Title/SEO are resolution-time outputs: re-run
`run()`/`resolve_row()` after changing their configuration. Writers only project those
fields; Description templates are still selected and rendered at write time.

### Verification and future changes

The completed implementation passed 760 tests with zero skips, mypy across 47
source files, Ruff, Description conformance, and all eight locked output comparisons.
Fresh-context adversarial reviews found and resolved legacy SKU-prefix and VIP
source-pipe compatibility issues; 4,322 complete TitleResult comparisons matched Phase 0.

Registry-driven tests adapt to registered vendors and settings. Fixed algorithm
regression cases remain independent oracles, and some older assertions still
assume particular configuration values. Intentional future changes may require
reviewing those assertions and the separate CSV baselines.

From the repository root, verify with the existing environment:

```powershell
Push-Location .\kiachahiye_bulk_csv
python -m pytest -q
Pop-Location
$env:MYPYPATH = (Resolve-Path .\kiachahiye_bulk_csv).Path
python -m mypy --explicit-package-bases kiachahiye_bulk_csv
python -m ruff check kiachahiye_bulk_csv
git diff --check
```

The eight locked output digests and review evidence are recorded in
`docs/phase1/walkthrough.md`.

### Roadmap beyond Phase 1

| Phase | Status | Scope |
| --- | --- | --- |
| 0 | Complete | Stabilization, vendor wiring, template-aware readers, multi-file audit, UI fixes. |
| 1 | Complete | Resolved configuration, immutable Title facts, independent cell rendering, dynamic contracts. |
| 2 | Future | Generalize remaining table-specific template conformance restrictions. |
| 3 | Future | Platform adapters and additional formats, including Shopify/WooCommerce multi-row output. |
| 4 | Future, on demand | Stateless job API and external configuration packs. |
