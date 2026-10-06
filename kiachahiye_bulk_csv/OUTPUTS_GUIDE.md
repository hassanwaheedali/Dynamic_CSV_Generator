# OUTPUTS — kaunsi file banti hai aur kis kaam ki hai

## Pehle poora flow, ek nazar mein

```
   AAP KA INPUT                      PIPELINE                    OUTPUT (6 files)
   ─────────────                     ────────                    ────────────────
                                                        ┌── 1. digi/digimall_bulk_import.csv   ← UPLOAD
   data/input/                                          │
   Products.csv  ──►  main.py  ───────────┼── 2. alfa/alfa_bulk_import.csv        ← UPLOAD
   (1800 rows, 7 zaroori columns)                       │
                                                        ├── 3. qc_report.csv                   ← aap parhein
                                                        └── 4. title_review_sample.csv         ← aap dekhein
                                audit.py   ──► 5. row_check.csv                  ← saboot / proof
                                thin_report.py ──► 6. thin_descriptions.csv      ← kaam ki list
```

Ek command = 6 files. Do files **upload** ke liye, chaar files **aap ke liye** (check karne ke liye).

---

## 1 aur 2 — Upload files (yahi marketplace par jayengi)

| | DigiMall | Alfa |
|---|---|---|
| Path | `data/output/<sheet>/digi/digimall_bulk_import.csv` | `data/output/<sheet>/alfa/alfa_bulk_import.csv` |
| Rows | 1800 (input ke barabar) | 1800 |
| Columns | **66** | **28** |
| Vendor | `KiaChahiye PVT LTD` | `Kia Chahiye Pvt Ltd` |
| Category | `11639_11643_11661_11669` (poora path) | `11509` (sirf leaf id) |
| Attributes | 36 `Attribute_*` + Short Description | **koi nahi** |

Yehi do files import ki jati hain. Inhen haath se edit karne ki zaroorat nahi — jo masla ho, woh QC report ke through theek karwayein.

## 3 — `qc_report.csv` (1 file, 9908 lines)

Har woh row jis par insaan ka ek faisla chahiye. Columns: `Row` (sheet ki line number), `Title`, `Affected File(s)`, `Severity`, `Flag Type`, `Details`.

Do tarah ke flags:
- **`review`** = aap ka faisla chahiye. Jaise `category_missing_digi` (kategori ka id nahi mila → cell khaali chhori), `brand_missing_alfa`, `attribute_empty` (sheet ki wording aap ki allowed list mein nahi hai).
- **`info`** = sirf note, kuch theek karne ki zaroorat nahi. Jaise `quantity_defaulted` (20 default), `weight_missing` (source mein weight nahi), `title_kept_from_source`.

**Kaise parhein:** Excel mein khol kar `Flag Type` par filter lagayein. Sab se pehle `category_missing_*` aur `brand_missing_*` dekhein — wohi cheez hai jo client se pooch kar list mein add karni hoti hai.

## 4 — `title_review_sample.csv` (20 rows)

Title **pehle → baad** ka sample. `Title (source)` aur `Title (final)` sath sath, 10 rebuilt + 10 kept.

Faida: ek nazar mein pata chal jata hai ke naya Title kaise banaya ja raha hai (brand + model + capacity + colour …). Poori file ke 1800 titles ke liye yehi rule har row par laga hai.

## 5 — `row_check.csv` (3600 lines = 1800 × 2 platforms)

Har row ka **saboot**: DigiMall aur Alfa dono ke liye ek ek line, columns mein Title, SKU, Handle, Category, Brands, Product Type, Warranty, Tags count, SEO length, aur `Verdict` = PASS.

Ye audit.py likhta hai (`--evidence` ke sath) — matlab ye "humne kaha theek hai" nahi, balke **checker ki likhi hui gawahi** hai. 3600/3600 PASS.

## 6 — `thin_descriptions.csv` (536 rows)

Woh rows jinki **source Description bahut kamzor** hai — aap ki sheet ka masla, code ka nahi.

- `One_Line = yes` → Description sirf **ek line** ka hai (186 rows).
- `Severity = high` → listing ka table bilkul khali (206 rows).
- `Severity = medium` → chal jayega magar source mein bohat kam maloomat (330 rows).

**Kaam:** ye rows likhne wale ko wapas bhejein. Behtar copy aayi → pipeline dobara chalayein → listing khud behtar ho jayegi.

---

## Har sheet ka apna dedicated folder (`data/output/<sheet-name>/`)
 
Har run ke saare outputs us sheet ke naam ke folder mein bante hain:
 
```
run_pipeline.bat                                        → data/output/Products/…
run_pipeline.bat "…\TEST_100_PRODUCTS.csv"              → data/output/TEST_100_PRODUCTS/…
```
 
Har sheet folder ke andar 2 platform folders (`alfa/`, `digi/`) aur saari report files hoti hain. Root `data/output/` bilkul saaf rehta hai.

## Description sudharne wala step (`data/output/cleaned/`)

Agar aap ki sheet ke Description ek doosre se chipke hue hain, pehle yeh chalayein:

```
python3 clean_descriptions.py
```

Yeh aap ki sheet ki sirf **Description** column theek karta hai (baki saare columns
jaisay ke taisay). Neeche wali files banti hain:

| File | Kis kaam ki |
|---|---|
| `READY_FIRST_STEP_1_CLEANED.csv` | **Yahi sheet aage chalayein** (`main.py --input …`) |
| `description_cleanup_report.csv` | Kaunsi row mein kya theek hua |
| `short_description_worklist.csv` | Woh 126 rows jahan source mein hi 3 facts nahi hain |
| `thin_descriptions_cleaned.csv` | Upar wali list ka poora advisory report |
| `two_product_preview.html` | Do rows ka before / after, browser mein |

```
python3 main.py --input "data/output/cleaned/READY_FIRST_STEP_1_CLEANED.csv" ^
  --digi data/output/cleaned/digi/digimall_bulk_import.csv ^
  --alfa data/output/cleaned/alfa/alfa_bulk_import.csv ^
  --qc   data/output/cleaned/qc_report.csv ^
  --sample-titles data/output/cleaned/title_review_sample.csv
python3 audit.py --input "data/output/cleaned/READY_FIRST_STEP_1_CLEANED.csv" ^
  --digi data/output/cleaned/digi/digimall_bulk_import.csv ^
  --alfa data/output/cleaned/alfa/alfa_bulk_import.csv ^
  --qc   data/output/cleaned/qc_report.csv ^
  --evidence data/output/cleaned/row_check.csv
```

## Ek line mein yaad rakhne wali baat

| File | Kis ke liye |
|---|---|
| `digi/digimall_bulk_import.csv` aur `alfa/alfa_bulk_import.csv` | **Upload** karein |
| `qc_report.csv` | Masle **dekhein** aur client se data/**allowed values** lein |
| `title_review_sample.csv` | Title ka tareeqa **check** karein |
| `row_check.csv` | Proof — har row PASS (audit likhta hai) |
| `thin_descriptions.csv` | Kamzor descriptions ki **kaam ki list** |
| `cleaned/READY_FIRST_STEP_1_CLEANED.csv` | Saaf ki hui sheet — isi ko aage barhayein |
