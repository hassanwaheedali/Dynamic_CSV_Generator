# Pre-Phase-2 remediation evidence

Date: 2026-11-12. Branch: `the-new-way`.

Checkpoint: `987678ef4a13b1e3c684c27c33bce2b7e380db40` (`chore: checkpoint M1.5 foundation work for follow-up fixes`). The working tree was clean when this task began. This report describes remediation relative to that checkpoint; see Git history for the final remediation commits. The user explicitly authorized review followed by implementation, superseding the attached review-only boundary, and subsequently authorized local Git commits.

## Reconciled findings and implemented corrections

The checkpoint retains the material defects described in the supplied Sol report. Its earlier uncommitted-file inventory describes a historical state, not the starting state of this task.

| Finding | Verification and correction | Regression evidence |
|---|---|---|
| Attributes consume rendered DigiMall Title | Confirmed. Attributes now read the original input title and description. Existing explicit subtype-conflict suppression remains. | Formula-only changes cannot change attributes; source-only `1000W` survives; QLED outranks 4K; unlisted `16 Cu.Ft` is not repaired through title formatting. |
| Product Type reverse-maps marketplace IDs | Confirmed. Removed matched-key/ID-based identity derivation. Canonical identity and source vocabulary determine Product Type independently of category coverage. | Garment Steamer stays Garment Steamer with Alfa's combined leaf and with empty destination maps. |
| Negative label/value evidence establishes positive categories | Confirmed. Boolean answers are bound before keyword matching; unknown answers do not lend their labels as positive evidence. Source title, labelled specifications, folder, then prose determine trait precedence. HTML source cells retain a tab separator, and audit normalizes source markup consistently. | Inverter: No; Smart TV: No; Steam Function: No; Not Supported; Unknown; explicit negative spec versus positive folder; HTML Product Type, boolean and warranty fields. |
| Secondary features establish identity/traits | Confirmed. Shared evidence filtering excludes remote/control/sensor specifications; display feature phrases do not establish television identity. Structured Product Type narrows an umbrella. | LED Display Water Dispenser; Smart Remote; Remote: Smart TV Remote Control; structured Garment Steamer. |
| Invalid raw category overrides publish as mapped | Confirmed. Raw declarations authorize exact existing IDs; they cannot transplant activity, ancestry or concepts from another node. Every direct destination must also satisfy its required traits. | Inactive, fabricated and structural destination overrides stay blank; custom alias cannot bypass inverter requirements. |
| Cached taxonomy declarations share mutable state | Confirmed. Only immutable raw nodes remain cached. Each declaration-map call constructs a new dictionary. | Independent factory results compare equal without sharing identity. |
| Duplicate leaf names collapse; ancestor traits disappear | Confirmed. Duplicate names receive ancestry-qualified declaration keys; selection retains raw IDs. Trait axes inherit through ancestry, with nearer declarations taking precedence. | Two Floor Standing leaves under opposite technology branches retain both IDs and resolve separately. |
| Equal matches depend on configuration order | Confirmed. Matching retains equally specific candidates and reports sibling ambiguity instead of selecting the first declaration. | Reversed wine/beer-chiller declarations give the same unresolved outcome. |
| Inactive atomic category suppresses active combined leaf | Confirmed by source; corrected active-candidate selection before atomic preference. | Synthetic inactive Water Dispenser and active Water Dispensers & Purifiers. |
| Alias outputs bypass ALLOWED | Confirmed. Alias results, inverse boolean answers and the final publication path all enforce the current allowed list. Rejected evidence remains a QC gap. | Removing Inverter from ALLOWED yields a blank plus its raw signal. Negative fields cannot emit their positive aliases. |
| Audit accepts owned but semantically wrong IDs and inapplicable attributes | Confirmed by failing fixtures. Audit now validates concept compatibility, raw-leaf assignability, required traits and attribute SCOPE. | Refrigerator with its vendor's Microwave ID fails; Refrigerator with allowed AC Type=Split fails. |
| Resolved cell vocabulary consumers incomplete | Confirmed. Corpus category vocabulary now reads both resolved cells, including overrides. Both cells' source Product Type maps contribute under an explicit shared-identity policy. Conflicting explicit overrides raise ConfigError, including during vendor validation. | Alfa-only type-map override works; conflicting declarations fail; corpus claims cell-only aliases/type words. |
| Canonical extraction repeats; structured QC unused | Confirmed. PreparedRows retains row cores alongside corpus preparation; run reuses those facts. WarrantyFacts supplies description rows, attribute headline and title wording from one extraction. Sibling/inactive flags and terminal counts use structured results. | Canonical extraction counters; once-per-row builder checks; structured sibling QC fixture. |
| Fractional/ranged warranties become integer suffixes | Confirmed as pre-existing by executing the warranty module from pre-M1.5 commit c9616b7: 0.5 and 3.5 became 5 Years, and 1-3 became 3 Years. Complete decimal and range tokens are now parsed; leading decimal points are preserved, including inside labels. Mixed numeric and explicit nonnumeric component answers all survive. | .5, 0.5, 3.5, hyphen ranges, “1 to 3”; decimal Compressor label beside Motor; component N/A; standalone nonnumeric answers keep Warranty as their label. |
| 752-row warranty audit rejects renderer normalization | Confirmed by focused merged-duration fixture. Audit compares the same warranty component after an optional Warranty suffix and checks individual facts inside merged duration rows. | All six real-data audits pass, including both vendors on Products.csv. Missing warranty labels and invented warranty values still fail existing controls. |
| Brand/category/title tests permit wrong results | Confirmed with deliberate mutations. Added alias-to-ID sweeps, controlled positive mappings for every registered vendor, and independent title identity checks. Raw-tree tests exercise both complete and controlled cells positively. | Missing Superasia IDs, blank category resolver and WRONG PRODUCT TITLE each fail targeted tests. |
| Supported configuration forms fail tests; mypy regresses | Confirmed. Template tests resolve names, inline templates and inheritance; fixed deployment styling uses controlled fixtures. Raw coverage discovers every configured raw cell and honors leaf_only. Real-sheet paths are package-relative. The two reported template-index typing errors are removed. | Third-vendor plus inherited/inline/restyled templates, category color omission and leaf_only experiment; repository-root suite; documented mypy gate. |
| Multiword attribute gaps and tautological assertions | Confirmed. QC captures full column names; always-true assertions are replaced by actual schema/vocabulary conditions. | Attribute_LED Type gap summary and schema checks. |

## Shared causes addressed

The corrections remove three harmful dependencies: marketplace IDs determining intrinsic identity, rendered titles determining source attributes, and mutable cached declarations crossing configuration boundaries. They also complete resolved-configuration consumption and reuse canonical facts rather than extracting them again for rendering.

Product Type remains one fact shared by both exports. Explicit cell type-map declarations can add source vocabulary or override inherited values; two explicit declarations of different names for the same source key are invalid. Marketplace ID tables are never merged into this policy.

The existing deterministic pipeline, platform headers, separate cell rendering, source evidence and title collision handling remain. The Phase 2 description AST redesign has not begun. Historical task documents and unrelated rules were not rewritten.

## Verification

Runtime: repository virtual environment, Python 3.12.14.

- Full suite from repository root: `python -B -m pytest kiachahiye_bulk_csv/tests/ -q -p no:cacheprovider --basetemp <isolated-dir>`: **891 passed, zero skips**, 202.53 seconds. Log: `pytest-release-gate.log` in the evidence directory below.
- `python -B -m mypy --explicit-package-bases --cache-dir <isolated-cache> .`: clean, 48 source files.
- `python -B -m ruff check . --no-cache`: clean.
- `git diff --check`: clean.
- Valid-configuration experiment: **254 targeted cases passed** with a third vendor, inherited and inline restyled templates, category color omission and raw leaf_only formatting. Log: `valid-configs-final.log`.
- Deliberate negative controls: all three mutations failed as required (missing alias IDs, blank positive categories, wrong formula title).
- Two fresh-context adversarial review rounds produced concrete edge cases; these were reproduced as failing tests and corrected. The user declined an additional external cross-model review.

| Vendor | Dataset | Rows | Generation | Expanded audit |
|---|---|---:|---|---|
| Kiachahiye | TEST_100_PRODUCTS.csv | 100 | Pass | 58/58 |
| Kiachahiye | Products.csv | 752 | Pass | 58/58 |
| Kiachahiye | Step 1.csv | 30 | Pass | 58/58 |
| Ajmer | TEST_100_PRODUCTS.csv | 100 | Pass | 58/58 |
| Ajmer | Products.csv | 752 | Pass | 58/58 |
| Ajmer | Step 1.csv | 30 | Pass | 58/58 |

All generated outputs, QC files, audit evidence and logs are isolated beneath `C:/Users/uzair/.codex/visualizations/2026/11/12/01a1cec2-606b-7d01-a2be-fd400eeb2d5f/`. Final real-data results are in `generation-final/summary.json`; per-input directories contain both CSVs and verification logs. Normal output directories were not used.

These are bounded correctness checks, not a statistical claim about arbitrary future catalogs. Corrected identity and warranty evidence can legitimately change titles, Product Type, category assignments or derived handles relative to the erroneous checkpoint output.

## Readiness and authoritative evidence

The implemented remediation is available for final independent release review. The user authorized local commits after receiving the implementation summary. No push, upload or Phase 2 implementation was performed.

The supplied repository taxonomy snapshot contains 116 nodes: 64 assignable leaves, 25 structural parents, six depleted branches and 21 inactive nodes. Final review must distinguish the following evidence statuses:

| Evidence | Status | What the evidence establishes |
|---|---|---|
| Supplied 116-node snapshot | Internally verified | Graph consistency, ancestry, activity and assignability within that supplied snapshot; engine behavior against its configured category permissions. |
| Current live DigiMall taxonomy export | Not independently verified | The snapshot's provenance, freshness and agreement with the current live marketplace taxonomy have not been established. |
| Current seller category permissions | Not independently verified | The configured category permissions have not been checked against either seller's current DigiMall account permissions. |
| Ajmer DigiMall seller literal, Data Electronics | User-confirmed | The user confirmed the exact seller-name literal. This confirmation does not independently establish live taxonomy validity or seller category permissions. |

The passing tests and CSV audits support engineering correctness against the supplied snapshot and configured permissions. They do not establish that the same category assignments are currently authorized for live marketplace uploads. Final review must report engineering-remediation readiness separately from live-upload readiness; the latter remains unverified on the evidence collected here.

## User-supplied configuration at commit preparation

The engine remediation is committed separately as `575b752` (`fix: stabilize product evidence before Phase 2`). The user added the following Ajmer DigiMall brand declarations and confirmed that these additions were theirs:

| Brand key | Declared DigiMall ID |
|---|---:|
| gree | 3790 |
| ecostar | 3789 |
| haier | 3759 |
| dawlance | 3755 |

These entries are maintained in a separate configuration commit. They are user-supplied declarations, not independently verified live seller brand permissions. The repository suite and real-data audits are rerun against the updated configuration before committing it. The missing-brand workflow test explicitly removes Gree from a temporary configuration, so it continues testing a real negative case when production mappings are populated.

Revalidation with these declarations passed **891 tests with zero skips** in 166.79 seconds (`pytest-config-commit-final.log`), the 68 focused vendor/brand cases, mypy and Ruff. All six real-data generation runs and their **58/58** audits passed again (`precommit-generation.log` and `generation-final/summary.json`).
