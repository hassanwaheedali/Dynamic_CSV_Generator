"""QC flag collection and the combined report writer.

Every module in the pipeline reports uncertainty through a single ``QCFlagCollector``
instance.  Nothing in the pipeline is allowed to *guess*: if a lookup fails, the
cell stays empty and a flag lands here for a human to resolve.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Flag categories (kept explicit so the summary counters can be split per
# platform without string-matching prose later on)
# ---------------------------------------------------------------------------

CAT_BRAND_DIGI = "brand_missing_digi"
CAT_BRAND_ALFA = "brand_missing_alfa"
CAT_CATEGORY_DIGI = "category_missing_digi"
CAT_CATEGORY_ALFA = "category_missing_alfa"
CAT_AC_INVERTER_UNKNOWN = "ac_inverter_status_unknown"
CAT_FALLBACK_SKU = "fallback_sku"
CAT_SKU_DEDUPED = "sku_disambiguated"
CAT_PRICE_INVERSION = "price_inversion"
CAT_QTY_DEFAULTED = "quantity_defaulted"
CAT_HANDLE_DEDUPED = "handle_deduplicated"
CAT_ATTRIBUTE_EMPTY = "attribute_empty"
CAT_THIN_DESCRIPTION = "thin_description"
CAT_PRODUCT_TYPE_INFERRED = "product_type_inferred"
CAT_TITLE_FALLBACK = "title_kept_from_source"
CAT_TITLE_DROPPED_WORDS = "title_dropped_words"
CAT_SERIES_SINGLE_ROW = "series_believed_from_one_row"
CAT_SUBTYPE_LINE_UNUSED = "subtype_line_added_nothing"
CAT_WEIGHT_MISSING = "weight_missing"
CAT_WEIGHT_UNREADABLE = "weight_unreadable"
CAT_SHORT_DESCRIPTION_THIN = "short_description_thin"
CAT_SEO_DESCRIPTION_LENGTH = "seo_description_length"
CAT_TITLE_DESCRIPTION_CONFLICT = "title_description_conflict"

# Pulls the column and the raw string back out of an "attribute_empty" message.
_ATTRIBUTE_GAP_RE = re.compile(r"^(Attribute_\w+): raw signal '([^']*)'")

# Flags that genuinely need a human decision, versus notes that simply record a
# deterministic default (a source with no weight column, the fixed quantity
# default, a handle that was disambiguated on purpose).  Only "review" flags
# count towards a row needing manual attention in the terminal summary.
INFO_CATEGORIES: frozenset[str] = frozenset(
    {
        CAT_QTY_DEFAULTED,
        CAT_WEIGHT_MISSING,
        CAT_HANDLE_DEDUPED,
        CAT_SKU_DEDUPED,
        CAT_TITLE_FALLBACK,
        CAT_TITLE_DROPPED_WORDS,
        CAT_THIN_DESCRIPTION,
    }
)


@dataclass
class QCFlag:
    """A single uncertainty recorded against one source row."""

    row_number: int
    title: str
    category: str
    platform: str  # "digi", "alfa", or "both"
    message: str
    severity: str = "review"  # "review" | "info"

    @property
    def platform_label(self) -> str:
        return {
            "digi": "DigiMall (digimall_bulk_import.csv)",
            "alfa": "Alfa (alfa_bulk_import.csv)",
            "both": "Both files",
        }[self.platform]

@dataclass
class QCFlagCollector:
    """Accumulates flags across the whole run and writes the QC report."""

    flags: list[QCFlag] = field(default_factory=list)

    def flag(
        self,
        row_number: int,
        title: str,
        category: str,
        message: str,
        platform: str = "both",
        severity: str | None = None,
    ) -> None:
        resolved = severity or ("info" if category in INFO_CATEGORIES else "review")
        self.flags.append(
            QCFlag(
                row_number=row_number,
                title=title,
                category=category,
                platform=platform,
                message=message,
                severity=resolved,
            )
        )

    # -- reporting ---------------------------------------------------------

    def flagged_row_ids(self, platform: str, severity: str | None = None) -> set[int]:
        """Row numbers carrying a flag touching ``platform`` at ``severity``."""
        return {
            flag.row_number
            for flag in self.flags
            if flag.platform in ("both", platform)
            and (severity is None or flag.severity == severity)
        }

    def flags_for_row(self, row_number: int) -> list[QCFlag]:
        return [flag for flag in self.flags if flag.row_number == row_number]

    def count(self, category: str) -> int:
        """Count distinct *rows* carrying a given flag category."""
        return len({flag.row_number for flag in self.flags if flag.category == category})

    def attribute_gaps(self) -> Counter[tuple[str, str]]:
        """``(column, raw signal)`` pairs behind every ``attribute_empty`` flag.

        Read back out of the flag message -- the exact text the report shows --
        so the terminal summary and the QC file can never disagree about which
        strings are waiting to be added to ``ALLOWED`` in ``attributes.py``.
        """
        gaps: Counter[tuple[str, str]] = Counter()
        for flag in self.flags:
            if flag.category != CAT_ATTRIBUTE_EMPTY:
                continue
            match = _ATTRIBUTE_GAP_RE.match(flag.message)
            if match:
                gaps[(match.group(1), match.group(2))] += 1
        return gaps

    def platform_summary(self, total_rows: int) -> dict[str, dict[str, int]]:
        """Per-platform clean/flagged row counts plus per-category counters."""
        out: dict[str, dict[str, int]] = {}
        for platform in ("digi", "alfa"):
            review = self.flagged_row_ids(platform, "review")
            info = self.flagged_row_ids(platform, "info") - review
            out[platform] = {
                "rows_total": total_rows,
                "rows_need_review": len(review),
                "rows_info_only": len(info),
                "rows_clean": max(total_rows - len(review) - len(info), 0),
            }
        return out

    def write_csv(self, path: Path, platform: str = "both") -> None:
        """Write the report.

        ``platform`` narrows it to one upload: a finding about a file this run never wrote is
        not news about the file in hand, and a worklist of DigiMall cells is no help to a shop
        uploading to Alfa.  A flag marked ``both`` touches either file, so it always stays.
        """
        keep = {"both", "digi", "alfa"} if platform == "both" else {platform, "both"}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
            writer.writerow(
                [
                    "Row",
                    "Title",
                    "Affected File(s)",
                    "Severity",
                    "Flag Type",
                    "Details",
                ]
            )
            for flag in sorted(self.flags, key=lambda f: (f.row_number, f.category)):
                if flag.platform not in keep:
                    continue
                writer.writerow(
                    [
                        flag.row_number,
                        flag.title,
                        flag.platform_label,
                        flag.severity,
                        flag.category,
                        flag.message,
                    ]
                )
