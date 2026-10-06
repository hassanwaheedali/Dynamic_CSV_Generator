# KiaChahiye Bulk CSV Pipeline

Turns one product sheet (1,800+ rows) into **two finished bulk-upload CSVs** —
one for DigiMall, one for Alfa — written to two separate folders, plus one
combined QC report naming every row a human should look at.

Everything is plain, deterministic Python: **no LLM calls, no network calls, no
external APIs**. Every business rule is a lookup table, a regex or a
keyword-to-enum dictionary that you can read, edit and audit.

---

## Quick start

```bash
cd kiachahiye_bulk_csv
pip install pytest mypy ruff openpyxl   # only for tests / type-checking / linting / .xlsx input

python main.py                        # uses the paths in CONFIG at the top of main.py
```

That writes:

```
kiachahiye_bulk_csv/data/output/
├── digi/digimall_bulk_import.csv      # 66 columns, Vendor = KiaChahiye PVT LTD
├── alfa/alfa_bulk_import.csv          # 28 columns, Vendor = Kia Chahiye Pvt Ltd
├── qc_report.csv                      # every flagged row, per file
├── title_review_sample.csv            # before/after Title sample for your review
└── row_check.csv                      # one line per row per platform (the row-by-row proof)
```

Then run the pre-upload checker, which re-reads the source sheet and both files
and prints the checklist from `CHECKLIST.md`:

```bash
python3 audit.py --evidence data/output/row_check.csv     # exit 0 only if every check passes
python3 -m pytest tests/ -q                               # 142 tests
```

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
python main.py \
  --input "data/input/NEW SHEET.csv" \
  --digi  "data/output/digi/digimall_bulk_import_2026-01-15.csv" \
  --alfa  "data/output/alfa/alfa_bulk_import_2026-01-15.csv" \
  --qc    "data/output/qc_report_2026-01-15.csv"
```

Or just edit the `CONFIG` block at the top of `main.py`. Nothing else needs to
change — the folder names, file names and input path all live there.

### Re-running the 100-product stress test

```bash
python main.py --input data/input/test100/TEST_100_PRODUCTS.csv \
               --digi   data/output/test100/digi/digimall_bulk_import.csv \
               --alfa   data/output/test100/alfa/alfa_bulk_import.csv \
               --qc     data/output/test100/qc_report.csv \
               --sample-titles data/output/test100/title_review_sample.csv
python audit.py --input data/input/test100/TEST_100_PRODUCTS.csv \
                --digi   data/output/test100/digi/digimall_bulk_import.csv \
                --alfa   data/output/test100/alfa/alfa_bulk_import.csv \
                --qc     data/output/test100/qc_report.csv \
                --evidence data/output/test100/row_check.csv
```

Pass `--sample-titles` every time: without it the run writes its Title sample to
the default path and replaces the real sheet's review file.

### Checks

```bash
python -m pytest tests/ -q                       # 142 tests, incl. both acceptance cases
python -m mypy --strict --ignore-missing-imports $(ls *.py)   # production code
python -m mypy --strict --ignore-missing-imports --explicit-package-bases $(ls *.py) tests/*.py
ruff check .                                     # lint, policy in ruff.toml
```

---

## The input sheet

The sheet must supply `Title`, `Description`, `Sell Price`, `Original Price`,
`Categories`, `Brand` and `Image`.  `Vendor` is **not** required: neither file's
Vendor is ever taken from the sheet -- those two literals are fixed in
`config.py` (`VENDOR_DIGI` / `VENDOR_ALFA`), so a sheet without a Vendor column
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
  own fixed constant (the two strings are genuinely different, and neither comes
  from the sheet).

---

## Two files, never one

| | DigiMall | Alfa |
|---|---|---|
| Columns | 66 | 28 |
| Vendor constant | `KiaChahiye PVT LTD` | `Kia Chahiye Pvt Ltd` |
| `Category` shape | full path, `11639_11643_11661_11669` | bare leaf id, `11509` |
| `Brands` | DigiMall's own numeric id | Alfa's own numeric id (often a different number) |
| `Short Description`, `Commission Percentage`, 36 × `Attribute_*` | yes | **none of these columns exist** |

Both files are projected from **one** internal `ProductRecord` per row, so a
shared fact (Title, Description, SKU, price, images, Handle…) can never drift
between the two files.

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
| `price_inversion` | Original < Sell |
| `product_type_inferred` | the breadcrumb matched nothing, so Product Type was derived from it |
| `short_description_thin` | the source states fewer than 3 standout facts, so the field is left short rather than padded (216 rows on this sheet; see *Short Description* below) |
| `title_description_conflict` | the Title and the Description state a different tap count; the SKU follows the Title (2 rows) |
| `seo_description_length` | SEO Description could not be padded into 151-155 from real source facts — fires 0 times on this sheet |

**Severity `info`** — a deterministic default, nothing to fix:

`quantity_defaulted` (input has no stock column → 20), `weight_missing` (no
weight in the source → blank), `handle_deduplicated` / `sku_disambiguated`
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
  --digi data/output/cleaned/digi/digimall_bulk_import.csv \
  --qc data/output/cleaned/qc_report.csv \
  --out data/output/cleaned/thin_descriptions_cleaned.csv   # then keep Short_Desc_Bullets < 3
```

### Which Descriptions need work (`thin_descriptions.csv`)

A separate, advisory report — it never changes an upload file, and the pipeline
never reads it. It grades the **source** Description of every row against the
listing that row actually produced, and writes the weak ones worst-first:

```bash
python3 thin_report.py            # uses the paths in config.py
python3 thin_report.py --input X.csv --digi Y.csv --qc Z.csv --out W.csv
```

| Column | Meaning |
|---|---|
| `Row` | the source sheet's own line number — the same number the QC report uses, so you can jump straight to it in Excel |
| `Severity` | `high` = the listing is visibly poor; `medium` = usable but the source could say much more |
| `Issues` | every reason that row was listed, e.g. `one-line Description; very short source (43 chars)` |
| `One_Line` | `yes` when the source Description is a single line — filter this column for exactly that list |
| `Description_Chars` / `Description_Lines` | what the sheet itself contains |
| `Spec_Rows_In_Listing` / `Short_Desc_Bullets` | what the finished listing really shows |
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
* warranty coverage by source, and which brands still have no warranty table

---

## Where to edit things (the only places you ever need to touch)

| To change… | Open | Constant |
|---|---|---|
| **The two vendor strings** | `config.py` | `VENDOR_DIGI`, `VENDOR_ALFA` |
| Input / output file paths | `config.py` | `INPUT_FILE`, `DIGI_OUTPUT`, `ALFA_OUTPUT`, … |
| Default quantity, SEO length windows, Title cap | `config.py` | `DEFAULT_VARIANT_QUANTITY`, `SEO_*`, `TITLE_MAX` |
| What counts as a thin Description in the worklist | `config.py` | `THIN_*` |
| **Warranty terms** | `warranty_terms.py` | `WARRANTY_TERMS` — brand → category → parts |
| LED TV warranty on/off | `config.py` | `APPLY_TV_WARRANTY_TABLE` |
| DigiMall brand ids | `brands.py` | `BRANDS_DIGI` |
| Alfa brand ids | `brands.py` | `BRANDS_ALFA` |
| Brand spelling variants | `brands.py` | `BRAND_ALIASES` |
| DigiMall category paths | `categories.py` | `CATEGORY_DIGI_PATHS` |
| Alfa category leaf ids | `categories.py` | `CATEGORY_ALFA_IDS` |
| Breadcrumb wording → table key | `categories.py` | `DIGI_SEGMENT_ALIASES`, `ALFA_SEGMENT_ALIASES` |
| Breadcrumbs that are outside the catalogue | `categories.py` | `STOP_SEGMENTS` |
| Plain-text `Product Type` | `categories.py` | `PRODUCT_TYPE_MAP` |
| Allowed attribute values (incl. exact warranty wordings) | `attributes.py` | `ALLOWED` |
| Attribute phrasing → allowed value | `attributes.py` | `ALIASES` |
| Which attributes apply to which Product Type | `attributes.py` | `SCOPE` |
| Warranty terms, brand by brand | `warranty_terms.py` | `WARRANTY_TERMS` |
| Series words kept in rebuilt Titles | `sku_handle.py` | `SERIES_WORDS` |
| Filenames / folders | `main.py` | `CONFIG` block |

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
  most important one becomes `Attribute_Warranty` (DigiMall only).

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

The LED TV switch from the original spec's Test Case 2 is now **on**, in
`config.py`: `APPLY_TV_WARRANTY_TABLE = True`. Set it to `False` to go back to
showing no warranty row for a TV.

## Known gaps you can close by supplying data

These are reported by every run until filled in:

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
├── config.py               every path, the two vendors, length windows, thresholds
├── main.py                 entrypoint, CLI, terminal summary
├── models.py               dataclasses; one ProductRecord, two projections
├── textutils.py            string/colour/weight helpers
├── brands.py               §3  brand ids + aliases
├── categories.py           §4 + §5  category trees and Product Type
├── title_builder.py        §6  Title formula (rebuild-first, validate-fallback)
├── sku_handle.py           §7  model extraction, SKU, Handle, uniqueness
├── description_builder.py  §8  classifier, HTML table, Tags, SEO, Short Description
├── pricing.py              §9  prices and quantity
├── warranty.py             §10 + §12  warranty reading logic
├── warranty_terms.py       §10 + §12  WARRANTY_TERMS, the only table to edit
├── attributes.py           §11  the 36 DigiMall-only attributes
├── writers.py              §2  the two schemas and the two CSVs
├── qc_report.py            flag collection and the combined report
├── audit.py                the 45 machine checks (run after every run)
├── thin_report.py          the weak-Description worklist (advisory, below)
├── clean_descriptions.py   rewrite a messy Description column into clean bullets (pre-step)
├── ruff.toml               lint policy, every ignore commented
├── README.md               this file
├── CHECKLIST.md            the pre-upload checklist and the audit result
├── OUTPUTS_GUIDE.md        Roman-Urdu guide: kaunsi file kis kaam ki hai
├── WHAT_CHANGED.md         code + CSV change log, verified on two products
├── tests/                  142 tests, including both acceptance cases
└── data/
    ├── input/              the source sheet
    └── output/             the two CSVs, the QC report, the Title sample, row_check.csv,
                            thin_descriptions.csv
```
