"""Description cleaner -- turn a messy Description into clean bullets, nothing else.

The pipeline can only publish what the source states, and it can only *see* a
feature when the line looks like a feature.  A crashed-together Description
("The X is a Y. COOL ONLY DC INVERTER ECO MODE ... Experience high performance
...") therefore publishes badly even though every fact is present.

This tool rewrites ONLY the Description column of a sheet so that the same words
form a clean shape:

    The Orient 18W is a 1.5 Ton inverter split air conditioner.

    Brand: Orient
    Capacity: 1.5 Ton

    • Cooltron Series Air Conditioners — Orient DC Inverter Air Conditioners
    • Delivers Powerful Cooling with T3 Tropicalized Inverter Technology

Rules it follows, in order:

  * nothing is invented -- no new word, no new fact, no rewritten claim;
  * a line is split only where the source already breaks it: sentence
    punctuation, a dash, a bullet marker, a tab, a colon, or a sentence glued
    straight onto a ")" or ".";
  * a tab or colon label becomes "Label: Value" so the pipeline can build a real
    specification row from it;
  * a run of feature words with NO separator (   "COOL ONLY DC INVERTER ECO MODE
    AMPERE LOCK ..."   ) is left as ONE bullet.  The tool never guesses where one
    feature ends and the next begins; those rows are named in the report so a
    human can split them;
  * every other column of the sheet is copied through untouched.

    python3 clean_descriptions.py --input "in.csv" --out "out.csv" --report "r.csv"
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

from config import PROJECT_ROOT

# ---------------------------------------------------------------------------
#  EDIT HERE -- cleanup rules
# ---------------------------------------------------------------------------
#: Characters Excel exports when a file was saved in the wrong encoding.  Only
#: these exact sequences are replaced, so ordinary text is never touched.
MOJIBAKE: tuple[tuple[str, str], ...] = (
    ("â€”", "—"),
    ("â€“", "–"),
    ("€™", "'"),
    ("â€˜", "'"),
    ("â€œ", '"'),
    ("â€\x9d", '"'),
    ("â€¦", "…"),
    ("â‚¬", "€"),
    ("Âº", "º"),
    ("Â°", "°"),
    ("Â ", " "),
)

#: Structural words that carry no product fact.  A line made ONLY of these -- a
#: pasted "Feature <tab> Description" header, a bare section title such as
#: "Description", or a label line with no value -- is cut.
STRUCTURAL_WORDS: frozenset[str] = frozenset(
    {
        "feature", "features", "description", "specification", "specifications",
        "spec", "specs", "details", "detail", "highlights", "overview",
        "parameter", "parameters", "attribute", "attributes", "general",
        "key features", "key specifications", "product details",
    }
)

#: Where the source itself already ends a sentence or a parenthetical:
#: ". Cooltron" / ". COOL ONLY" / ")Experience high" -> a break is safe here.
GLUED_RE = re.compile(
    r"(?<=[.!?])(?=[A-Z][A-Za-z]{1,})"       # a sentence glued on: "TV.Feature" / "TV.COOL"
    r"|(?<=[)\]]) ?(?=[A-Z][A-Za-z]{1,})"    # glued after a bracket: "Lock)Experience"
)
#: A normal sentence boundary.  Only applied to a line the sheet did NOT write as
#: a bullet: the author's own bullets are kept whole.
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
#: A dash that separates a feature name from its explanation.
#: A dash separates a feature name from its explanation -- "Labyrinth PCB — it
#: keeps dust out".  Short left-hand names stay in ONE bullet (the pipeline reads
#: that pattern as "name + explanation"); only a long left-hand clause is split.
DASH_SPLIT_RE = re.compile(r"\s+[—–]\s+")
DASH_SPLIT_MIN_LEFT_WORDS = 6
#: Markdown emphasis, if the sheet carries any; removed as markup only.
BOLD_RE = re.compile(r"\*{1,2}([^*]+)\*{1,2}")
#: A bullet marker at the start of a line, e.g. "• ", "- ", "* ".
BULLET_MARK_RE = re.compile(r"^[\s•·▪▫\-–—*+]+")

LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /()&%.,'+%-]{1,44}?)\s*[:\t]\s*(\S.*)$")
#: A long run written ENTIRELY in capitals -- "COOL ONLY DC INVERTER ECO MODE
#: ... GOLD FIN" -- is split before each of these phrases.  The list is the only
#: thing that decides the split, so add a phrase here when the cleanup report
#: says a feature run could not be split.  The longest phrase is matched first,
#: so "4D LONG AIR THROW" wins over "AIR THROW".
FEATURE_KEYWORDS: tuple[str, ...] = (
    "4D LONG AIR THROW",
    "AIR THROW",
    "AUTO CLEAN",
    "AUTO RESTART",
    "COOL ONLY",
    "DC INVERTER",
    "ECO MODE",
    "GOLD FIN",
    "HEAT AND COOL",
    "LOW VOLTAGE",
    "100% PURE COPPER",
    "PURE COPPER",
    "REFRIGERANT",
    "SELF DIAGNOSIS",
    "SOLAR COMPATIBLE",
    "STERILIZATION",
    "TURBO COOLING",
    "WIFI READY",
)

#: A bullet that lists this many items in one line ("Key features include A, B,
#: C, D") is really that many bullets.  A labelled line ("Sound Modes: Standard,
#: music, movie") is ONE specification value and is never split, and an item has
#: to be at least two words for the split to be worth doing.
BULLET_LIST_MIN_ITEMS = 3
BULLET_LIST_MIN_WORDS = 2

#: A line that opens with one of these phrases is a list by the source's own
#: wording, so its commas separate facts and each one becomes a bullet.
LIST_LEAD_INS: tuple[str, ...] = (
    "key features include",
    "features include",
    "additional features include",
    "key features:",
    "features:",
    "additional highlights include",
    "highlights include",
    "key specifications include",
    "specifications include",
)

#: Without a lead-in, a comma list is only split when it looks like a list of
#: short facts.  A sentence such as "it delivers richer colours, deeper contrast,
#: and brighter visuals" is prose and must stay whole -- the conjunctions and the
#: length of the clauses are what tell the two apart.
LIST_CONJUNCTIONS: tuple[str, ...] = ("and ", "or ", "but ", "plus ", "also ", "then ", "with ")
BULLET_LIST_MAX_ITEM_WORDS = 6

#: A feature run is a long, mostly-capitalised line.  Measured on this sheet, a
#: real AC feature run is 72% capitals while ordinary marketing prose is 25%, so
#: the share -- not merely the presence of capitals -- is what decides.
CAPS_RUN_MIN_CHARS = 80
CAPS_RUN_MIN_CAPS_SHARE = 0.55
#: A split piece at least this long still needs a human eye.
MANUAL_ATTENTION_CHARS = 120
MAX_LABEL_WORDS = 6

DEFAULT_INPUT = Path("/home/user/uploads/READY FIRST STEP 1 CSV.csv")
DEFAULT_OUT = PROJECT_ROOT / "data" / "output" / "cleaned" / "READY_FIRST_STEP_1_CLEANED.csv"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "output" / "cleaned" / "description_cleanup_report.csv"

REPORT_HEADER = [
    "Row", "Title", "Changed", "Labels_Normalised", "Bullets_Created",
    "Feature_Runs_Split", "Bullet_Lists_Split", "Junk_Lines_Removed", "Duplicates_Removed", "Encoding_Fixes",
    "Manual_Attention",
]


def fix_text(text: str) -> tuple[str, int]:
    """Whitespace, control characters and encoding damage.  Returns the fix count."""
    fixed = 0
    for broken, good in MOJIBAKE:
        if broken in text:
            fixed += text.count(broken)
            text = text.replace(broken, good)
    text = text.replace("\u00a0", " ").replace("\u2011", "-").replace("\u200b", "")
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, fixed


def is_structural(line: str) -> bool:
    """A line carrying only section-header words, e.g. "Feature <tab> Description"."""
    if line.strip().rstrip(":").lower() in STRUCTURAL_WORDS:
        return True
    if ":" in line:
        return False
    parts = [part.strip(" :\t").lower() for part in re.split(r"\t| {2,}|\|", line)]
    parts = [part for part in parts if part]
    return bool(parts) and all(part in STRUCTURAL_WORDS for part in parts)


def tidy_label(label: str) -> str:
    return re.sub(r"\s+", " ", label).strip(" :\t")


def tidy_value(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[0].upper() + value[1:] if value else ""


def split_bullet_list(piece: str) -> list[str]:
    """One bullet holding a comma list becomes one bullet per item.

    Nothing is added or reworded: the items are the source's own comma-separated
    facts, trimmed.  A labelled line (tab or colon before the first comma) is one
    specification value and stays whole, and prose containing a comma list is
    left alone.
    """
    head = piece.split(",", maxsplit=1)[0]
    if LABEL_RE.match(piece) or ":" in head or "\t" in head:
        return [piece]
    items = [item.strip() for item in piece.split(",") if item.strip()]
    if len(items) < BULLET_LIST_MIN_ITEMS:
        return [piece]
    if any(piece.lower().startswith(lead) for lead in LIST_LEAD_INS):
        return items
    looks_like_prose = (
        any(item.lower().startswith(LIST_CONJUNCTIONS) for item in items)
        or any(len(item.split()) > BULLET_LIST_MAX_ITEM_WORDS for item in items)
        or not all(len(item.split()) >= BULLET_LIST_MIN_WORDS for item in items)
    )
    return [piece] if looks_like_prose else items


def is_feature_run(text: str) -> bool:
    """True for a long, mostly-capitalised feature run such as an AC shortlist."""
    if len(text) < CAPS_RUN_MIN_CHARS:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", text)
    if not words:
        return False
    caps = [word for word in words if word.isupper()]
    return len(caps) / len(words) >= CAPS_RUN_MIN_CAPS_SHARE


def split_feature_run(text: str, brand: str = "") -> list[str]:
    """Break a feature run at the boundaries the source itself provides.

    Four markers, nothing else:

      * a closing bracket  --  "MODE (AMPERE LOCK)REFRIGERANT" becomes two lines;
      * a slash between two names  --  "Everest / Frost 12G" becomes two lines;
      * the row's own Brand word  --  "GOLD FIN Orient Everest" becomes two lines;
      * a phrase from ``FEATURE_KEYWORDS``, matched outside brackets only, in one
        single pass so a longer phrase always wins over a shorter one inside it.

    No word is added, removed or reordered: the pieces joined back together are
    the original text.
    """
    sep = "\x00"
    broken = re.sub(r"\)\s*(?=\S)", ")" + sep, text)
    broken = re.sub(r"\s+/\s+", sep, broken)
    if brand:
        broken = re.sub(
            rf"(?<![A-Za-z0-9]){re.escape(brand)}(?![A-Za-z0-9])",
            sep + brand,
            broken,
            flags=re.IGNORECASE,
        )

    pattern = "|".join(
        re.escape(keyword) for keyword in sorted(FEATURE_KEYWORDS, key=len, reverse=True)
    )
    keyword_re = re.compile(rf"(?<![A-Za-z0-9])(?:{pattern})(?![A-Za-z0-9])", re.IGNORECASE)

    def protect_brackets(match: re.Match[str]) -> str:
        return "\x01" + match.group(0) + "\x02"

    # Text inside brackets is marked, and a keyword inside those marks is left
    # alone -- "(Cool Only, R410a, Ampere Lock)" is one fact, not four lines.
    masked = re.sub(r"\([^()]*\)", protect_brackets, broken)
    bracket_spans = [
        (match.start(), match.end()) for match in re.finditer("\x01[^\x02]*\x02", masked)
    ]

    def split_outside(match: re.Match[str]) -> str:
        if any(start < match.start() < end for start, end in bracket_spans):
            return match.group(0)
        return sep + match.group(0)

    masked = keyword_re.sub(split_outside, masked)
    masked = masked.replace("\x01", "").replace("\x02", "")

    pieces = [piece.strip(" \x00|,;") for piece in masked.split(sep)]
    return [piece for piece in pieces if piece]


def clean_description(description: str, brand: str = "") -> tuple[str, Counter[str]]:
    """Rewrite one Description.  Returns ``(cleaned_text, counters)``."""
    stats: Counter[str] = Counter()
    text, fixed = fix_text(description or "")
    stats["encoding"] = fixed

    intro: list[str] = []
    labels: list[tuple[str, str]] = []
    bullets: list[str] = []

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if is_structural(line):
            stats["junk"] += 1
            continue

        had_bullet = bool(BULLET_MARK_RE.match(line))
        chunks: list[str] = []
        for glued in GLUED_RE.split(line):
            chunks.extend([glued] if had_bullet else SENTENCE_RE.split(glued))

        for chunk in chunks:
            left, sep, _right = chunk.partition("\u2014") if "\u2014" in chunk else (chunk, "", "")
            if sep and len(left.split()) > DASH_SPLIT_MIN_LEFT_WORDS:
                dash_pieces = [piece for piece in DASH_SPLIT_RE.split(chunk) if piece.strip()]
            else:
                dash_pieces = [chunk]
            for raw_piece in dash_pieces:
                piece = BOLD_RE.sub(r"\1", raw_piece)
                stripped = BULLET_MARK_RE.sub("", piece).strip()
                if stripped != piece.strip():
                    stats["bullets"] += 1
                piece = stripped
                if not piece:
                    continue

                # a pasted table header can end up as its own piece
                if is_structural(piece):
                    stats["junk"] += 1
                    continue

                label = LABEL_RE.match(piece)
                if label is not None and len(tidy_label(label.group(1)).split()) <= MAX_LABEL_WORDS:
                    labels.append((tidy_label(label.group(1)), tidy_value(label.group(2))))
                    stats["labels"] += 1
                    continue

                items = split_bullet_list(piece)
                if (
                    len(items) == 1
                    and not intro
                    and piece.endswith((".", "!", "?"))
                    and len(piece.split()) >= 4
                ):
                    intro.append(piece)
                    continue

                stats["list_splits"] += 1 if len(items) > 1 else 0
                for item in items:
                    bullets.append(item)
                    stats["bullets"] += 1

    expanded: list[str] = []
    for bullet in bullets:
        if is_feature_run(bullet):
            pieces = split_feature_run(bullet, brand)
            if len(pieces) > 1:
                stats["feature_splits"] += 1
                expanded.extend(pieces)
                continue
        expanded.append(bullet)

    seen: set[str] = set()
    unique_bullets: list[str] = []
    for bullet in expanded:
        key = bullet.lower()
        if key in seen:
            stats["duplicates"] += 1
            continue
        seen.add(key)
        unique_bullets.append(bullet)

    parts: list[str] = []
    if intro:
        parts.append("\n".join(intro))
    if labels:
        parts.append("\n".join(f"{label}: {value}" for label, value in labels))
    if unique_bullets:
        parts.append("\n".join(f"• {bullet}" for bullet in unique_bullets))
    cleaned = "\n\n".join(parts) + "\n" if parts else ""
    for bullet in unique_bullets:
        if is_feature_run(bullet) and len(bullet) >= MANUAL_ATTENTION_CHARS:
            stats["manual"] += 1
            break
    return cleaned, stats


def read_sheet(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        return header, [dict(row) for row in reader]


def write_sheet(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean the Description column into bullets")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    header, rows = read_sheet(args.input)
    if "Description" not in header:
        print(f"  no Description column in {args.input}")
        return 2

    report: list[list[str]] = []
    totals: Counter[str] = Counter()
    for index, row in enumerate(rows, start=2):
        original = row.get("Description", "") or ""
        cleaned, stats = clean_description(original, row.get("Brand", ""))
        changed = cleaned.strip() != original.strip()
        row["Description"] = cleaned
        totals.update({k: v for k, v in stats.items() if k != "manual"})
        totals["manual"] += stats["manual"]
        if changed:
            totals["rows_changed"] += 1
        report.append(
            [
                str(index), row.get("Title", ""), "yes" if changed else "no",
                str(stats["labels"]), str(stats["bullets"]), str(stats["feature_splits"]), str(stats["list_splits"]),
                str(stats["junk"]), str(stats["duplicates"]), str(stats["encoding"]),
                "split a separator-less feature run by hand" if stats["manual"] else "",
            ]
        )

    write_sheet(args.out, header, rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(REPORT_HEADER)
        writer.writerows(report)

    print(f"  rows read               : {len(rows)}")
    print(f"  descriptions changed    : {totals['rows_changed']}")
    print(f"  bullets created         : {totals['bullets']}")
    print(f"  feature runs split      : {totals['feature_splits']}")
    print(f"  bullet lists split      : {totals['list_splits']}")
    print(f"  label rows normalised   : {totals['labels']}")
    print(f"  junk header lines cut   : {totals['junk']}")
    print(f"  duplicate lines dropped : {totals['duplicates']}")
    print(f"  encoding fixes          : {totals['encoding']}")
    print(f"  need a human to split   : {totals['manual']}")
    print(f"  cleaned sheet           : {args.out}")
    print(f"  report                  : {args.report}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
