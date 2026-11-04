"""Section 8 -- the Description classifier plus Tags, SEO and Short Description.

Built once per product.  Tags, SEO Title and SEO Description are shared facts and reach both
files unchanged; the Description is never stored as a string here -- what section 8 hands on is
the rows themselves (``spec_rows``), and each (store x platform) cell renders them in its own
shape.  So one platform's listings can be restyled without a fact moving anywhere else: pick the
shape in ``description_template`` (vendor_config.py), and add a shape to DESCRIPTION_TEMPLATES
here.  Short Description is built for every product but is written into the DigiMall file only
(Alfa's schema has no such column).

Classifier -- four ingestion modes, one row shape (``Label: Value`` pairs):

  A. ``Label: Value`` lines (colon or TAB separated)
  B. ``• Label: Value`` bullets                <- the dominant shape in the sheet
  C. ``• Lead phrase — explanation`` bullets   -> one "Key Features" row
  D. bare ``• feature`` bullets with no labels -> one "Key Features" row

Any source with fewer than two genuine spec rows beyond Brand/Model/Type is
treated as thin: no filler rows are ever added, and the Description is allowed
to be short.
"""

from __future__ import annotations

import dataclasses
import html
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from html.entities import html5 as HTML5_NAMED_REFERENCES
from html.parser import HTMLParser

from models import DescriptionBundle, SpecRow
from textutils import (
    clean_inline,
    dedupe_preserve_order,
    strip_markup_keep_lines as strip_markup_keep_lines,
)

TABLE_HEAD = (
    '<table style="width:100%;border-collapse:collapse;font-family:Arial,sans-serif;'
    'font-size:14px;line-height:1.6;border:1px solid #ddd;"><thead><tr>'
    '<th style="border:1px solid #ddd;border-bottom:none;padding:12px;text-align:left;'
    'width:35%;">Specification</th>'
    '<th style="border:1px solid #ddd;border-bottom:none;padding:12px;text-align:left;'
    'width:65%;">Details</th></tr></thead><tbody>'
)
TABLE_TAIL = "</tbody></table>"
CELL_STYLE = "border:1px solid #ddd;padding:10px;"

BULLET_CHARS = "•·-*–—"
SECTION_HEADERS = {
    "highlights",
    "key specifications",
    "specifications",
    "features",
    "key features",
    "key features (summary)",
    "what's in the box",
    "whats in the box",
}
NOISE_LABELS = {
    "why choose ecostar novo series",
    "key features (summary)",
}

LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /()&%.,'+\-]{1,44}?)\s*:\s*(\S.*)$")
TAB_LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /()&%.,'+\-]{1,44}?)\t\s*(\S.*)?$")
BULLET_RE = re.compile(r"^[" + re.escape(BULLET_CHARS) + r"]\s*(.+)$")
EMDASH_BULLET_RE = re.compile(r"^(?:\*\*)?(.{2,60}?)(?:\*\*)?\s*[—–]\s*(\S.*)$")
INTRO_SPLIT_RE = re.compile(
    r"\.\s*(?=[A-Z][A-Za-z][A-Za-z0-9 /()&%.,'+\-]{0,44}?(?:\t|:)\s*\S)"
)
GENERIC_LABELS = {
    "warranty",
    "model",
    "brand",
    "voltage",
    "frequency",
    "width",
    "depth",
    "height",
    "dimension",
    "dimensions",
    "weight",
    "net weight",
    "gross weight",
    "set weight",
}


@dataclass
class ParsedSpecs:
    """Everything the classifier could genuinely find in one Description."""

    branch: str
    intro: str = ""
    labelled: list[tuple[str, str]] = field(default_factory=list)
    key_features: list[str] = field(default_factory=list)
    thin: bool = False


def _tidy_label(label: str) -> str:
    label = clean_inline(label).strip(" :-\t")
    if label.islower():
        label = label.title()
    return label


def _tidy_value(value: str) -> str:
    value = clean_inline(value)
    return value[0].upper() + value[1:] if value else ""


def _strip_bullet(line: str) -> str:
    match = BULLET_RE.match(line)
    return match.group(1).strip() if match else line.strip()


def split_intro(first_line: str) -> tuple[str, str]:
    """Separate a leading intro sentence from a label glued onto the same line."""
    match = INTRO_SPLIT_RE.search(first_line)
    if match:
        return first_line[: match.end()].strip(), first_line[match.end() :].strip()
    return "", first_line.strip()


def parse_description(description: str) -> ParsedSpecs:
    """Classify a raw Description into rows, features and an intro line."""
    raw_lines = [line for line in re.split(r"[\r\n]+", description) if line.strip()]
    if not raw_lines:
        return ParsedSpecs(branch="thin", thin=True)

    intro, first_rest = split_intro(raw_lines[0])
    lines = ([first_rest] if first_rest else []) + raw_lines[1:]

    labelled: list[tuple[str, str]] = []
    bullets_labelled = 0
    features: list[str] = []
    seen_labels: set[str] = set()

    for index, line in enumerate(lines):
        stripped = line.strip()
        bare = _strip_bullet(stripped)
        if not bare:
            continue

        # Tab-separated label block, with the value on the next line if empty.
        tab_match = TAB_LABEL_RE.match(bare)
        if tab_match and "\t" in bare:
            value = (tab_match.group(2) or "").strip()
            if not value and index + 1 < len(lines):
                value = _strip_bullet(lines[index + 1].strip())
            label = tab_match.group(1)
            if value and label.lower() not in SECTION_HEADERS:
                labelled.append((_tidy_label(label), _tidy_value(value)))
                seen_labels.add(label.lower())
                continue

        if stripped.lower().rstrip(":") in SECTION_HEADERS:
            continue

        # `Label: Value`, whether written as a plain line or as a bullet.
        label_match = LABEL_RE.match(bare)
        if label_match:
            label = label_match.group(1).strip()
            value = label_match.group(2).strip()
            if label.lower() in NOISE_LABELS:
                continue
            if label.lower() not in seen_labels:
                labelled.append((_tidy_label(label), _tidy_value(value)))
                seen_labels.add(label.lower())
            if stripped != bare:
                bullets_labelled += 1
            continue

        # `Lead phrase — explanation` bullet.
        emdash = EMDASH_BULLET_RE.match(bare)
        if emdash and stripped != bare:
            features.append(clean_inline(emdash.group(1).strip(" *")))
            continue

        # Bare feature bullet, or a stray line of prose.
        if stripped != bare:
            features.append(clean_inline(bare))
        elif not intro:
            intro = clean_inline(bare)
        elif ":" not in bare and len(bare) <= 60 and len(bare.split()) <= 8:
            # Section 8 Branch 3: a short, label-free line is a genuine
            # standalone feature, not a sentence of prose.  Section headers are
            # handled by the explicit SECTION_HEADERS set above -- a generic
            # "looks like a heading" regex would swallow real features such as
            # "Long Air Throw" and "Hidden LED".
            features.append(clean_inline(bare))

    labelled = [row for row in labelled if row[1]]
    if len(labelled) >= 3:
        branch = "label-bullets" if bullets_labelled else "label-lines"
    elif features:
        branch = "highlights" if labelled else "features"
    elif labelled:
        branch = "label-lines"
    else:
        branch = "thin"

    spec_like = [
        row
        for row in labelled
        if row[0].lower() not in ("brand", "model", "type")
        and row[0].lower() not in GENERIC_LABELS
    ]
    thin = len(spec_like) < 2 and not features
    return ParsedSpecs(
        branch=branch,
        intro=intro,
        labelled=labelled,
        key_features=features,
        thin=thin,
    )


def _is_subtype_label(label: str) -> bool:
    """Whether a label is this program's own sub-type field, however the row spaced or hyphenated it."""
    return re.sub(r"[^a-z0-9]", "", label.lower()) == "subtype"


def subtype_label(description: str) -> str:
    """The sheet's own sub-type statement: a `SubType: Heat & Cool` line, value exactly as written.

    Read through :func:`parse_description` because a bullet in front of the label is how these
    sheets write it -- a line-start regex probe finds none of them.  Only this label counts:
    `Type:`, `Door Type:` and `Air Conditioner Type:` answer different questions.
    """
    for label, value in parse_description(strip_markup_keep_lines(description)).labelled:
        if _is_subtype_label(label):
            return clean_inline(value)
    return ""


#: A row that talks about a sub-type without writing it as a labelled line.  The Title cannot use
#: that, and the owner checks these by hand, so it has to be reported rather than dropped quietly.
_SUBTYPE_MENTION_RE = re.compile(r"\bsub\s*-?\s*type\b", re.IGNORECASE)


def mentions_subtype(description: str) -> bool:
    """Whether the row writes the words `SubType` at all, labelled or not."""
    return _SUBTYPE_MENTION_RE.search(strip_markup_keep_lines(description)) is not None


# ---------------------------------------------------------------------------
# HTML construction
# ---------------------------------------------------------------------------
def _row_html(label: str, value: str, bold: bool = False) -> str:
    label_html = html.escape(label, quote=False)
    value_html = html.escape(value, quote=False)
    if bold:
        label_html = f"<strong>{label_html}</strong>"
        value_html = f"<strong>{value_html}</strong>"
    return (
        f'<tr><td style="{CELL_STYLE}">{label_html}</td>'
        f'<td style="{CELL_STYLE}">{value_html}</td></tr>'
    )


def build_description_html(rows: list[SpecRow]) -> str:
    """The single-line, plain-CSS spec table."""
    body = "".join(_row_html(row.label, row.value, row.is_warranty) for row in rows)
    return TABLE_HEAD + body + TABLE_TAIL


# ---------------------------------------------------------------------------
# Description templates -- one render input, N output shapes, chosen per cell
# ---------------------------------------------------------------------------
class TemplateShapeError(ValueError):
    """A Description that a template's ``extract`` cannot read back as spec rows.

    Raised instead of returning a short list: a silently dropped row is a fact that
    left the listing without anyone noticing, which is the failure this program is
    built to avoid.
    """


@dataclass(frozen=True)
class DescriptionTemplate:
    """One Description output shape: it writes spec rows and reads them back.

    ``render`` produces the cell a (store x platform) pair ships.  ``extract`` is what
    makes the pair provably lossless -- a template that cannot read its own output is
    a template the QC readers cannot follow, so it is rejected here rather than at
    the upload.  ``starts_with`` / ``ends_with`` declare the boundary the reader
    insists on, so no reader has to guess a pasted template's markup.

    Frozen so the same template object may serve several cells (the shop's "give both
    stores this one template" case) with no shared state to edit by accident.
    """

    name: str
    render: Callable[[list[SpecRow]], str]
    extract: Callable[[str], list[SpecRow]]
    starts_with: str
    ends_with: str


_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<t([dh])\b[^>]*>(.*?)</t\1>", re.IGNORECASE | re.DOTALL)
_STRONG_RE = re.compile(r"^\s*<strong>(.*)</strong>\s*$", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _cell_text(inner: str) -> tuple[str, bool]:
    """``(text, bold)`` of one cell, un-escaping exactly what :func:`_row_html` did.

    Tags are stripped BEFORE entities are unescaped: `_row_html` escapes first, so a
    source value that really wrote `<b>` arrives here as `&lt;b&gt;` and must survive
    as those two characters, not be mistaken for markup and removed.
    """
    bold = False
    matched = _STRONG_RE.match(inner)
    if matched:
        bold = True
        inner = matched.group(1)
    return html.unescape(_TAG_RE.sub("", inner)).strip(), bold


def extract_spec_rows(
    text: str, *, starts_with: str, ends_with: str
) -> list[SpecRow]:
    """Read a spec table back into the rows that produced it.

    Tolerant of the things a hand-authored template varies (tag attributes, casing,
    whitespace), strict about the two things the gates count on: a row is a pair of
    cells, and the whole thing is one ``starts_with``...``ends_with`` fragment.  A
    ``<th>`` row is the table's own caption, not a specification, so it is skipped.
    """
    body = (text or "").strip()
    if not (body.lower().startswith(starts_with.lower()) and body.lower().endswith(ends_with.lower())):
        raise TemplateShapeError(
            f"Description is not one {starts_with!r}...{ends_with!r} fragment: {body[:60]!r}"
        )
    rows: list[SpecRow] = []
    for chunk in _ROW_RE.findall(body):
        cells = _CELL_RE.findall(chunk)
        if cells and all(tag.lower() == "h" for tag, _ in cells):
            continue  # the header row names the columns; it is not a spec row
        if len(cells) != 2 or any(tag.lower() != "d" for tag, _ in cells):
            raise TemplateShapeError(
                f"a spec row must be exactly two <td> cells, got {len(cells)}: {chunk[:60]!r}"
            )
        (label, bold), (value, _) = (
            _cell_text(cells[0][1]),
            _cell_text(cells[1][1]),
        )
        rows.append(SpecRow(label, value, is_warranty=bold))
    return rows


SPEC_TABLE = DescriptionTemplate(
    name="spec_table",
    render=build_description_html,
    extract=lambda text: extract_spec_rows(
        text, starts_with="<table", ends_with="</table>"
    ),
    starts_with="<table",
    ends_with="</table>",
)

#: Every Description shape the shop may choose, by name.  A cell's
#: ``description_template`` is a key of this dict (or an inline template object), so
#: two stores can point at one entry and a new listing shape is added here once.
_ALFA_CARD_HEAD = (
    '<table style="width:100%;border-collapse:separate;border-spacing:0;border-radius:14px;'
    "overflow:hidden;border:1px solid #ebd9dc;"
    "box-shadow:0 12px 32px rgba(91,20,155,0.06),0 2px 8px rgba(215,35,20,0.04);"
    "margin-bottom:20px;background:#ffffff;font-family:Arial,sans-serif;font-size:13px;"
    'line-height:1.6;text-align:left !important;">'
    '<caption style="caption-side:top;padding:0;text-align:left;background:#ffffff;">'
    '<div style="height:4px;background:linear-gradient(90deg,#d72314 0%,#5b149b 50%,#f5a623 100%);">'
    "</div>"
    '<div style="background:linear-gradient(180deg,#fdfbfe 0%,#faf8fc 100%);padding:12px 16px;'
    "border-bottom:1px solid #ede4f5;display:flex;flex-wrap:wrap;align-items:center;"
    'justify-content:space-between;gap:10px;text-align:left !important;">'
    '<div style="display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:bold;'
    "color:#b31b0e;background:rgba(215,35,20,0.09);border:1px solid rgba(215,35,20,0.28);"
    "padding:5px 13px;border-radius:20px;box-shadow:0 2px 6px rgba(215,35,20,0.08);"
    'text-align:left !important;">'
    '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#d72314;">'
    "</span>100% Genuine Pin-Packed</div>"
    '<div style="display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:bold;'
    "color:#5b149b;background:rgba(91,20,155,0.09);border:1px solid rgba(91,20,155,0.28);"
    "padding:5px 13px;border-radius:20px;box-shadow:0 2px 6px rgba(91,20,155,0.08);"
    'text-align:left !important;">'
    '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#5b149b;">'
    "</span>Delivery All Over Pakistan</div>"
    '<div style="display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:bold;'
    "color:#8a5600;background:rgba(245,166,35,0.14);border:1px solid rgba(245,166,35,0.36);"
    "padding:5px 13px;border-radius:20px;box-shadow:0 2px 6px rgba(245,166,35,0.1);"
    'text-align:left !important;">'
    '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#f5a623;">'
    "</span>After Sales Service</div>"
    "</div></caption>"
    "<thead><tr>"
    '<th style="background:linear-gradient(90deg,#fdf4f4 0%,#f9f3fa 100%);padding:12px 16px;'
    "text-align:left !important;width:35%;color:#222;font-weight:bold;letter-spacing:0.3px;"
    'font-size:14px;border-bottom:2px solid #5b149b;">Specification</th>'
    '<th style="background:linear-gradient(90deg,#f9f3fa 0%,#f8f3fc 38%,#fffdf7 100%);padding:12px 16px;'
    "text-align:left !important;width:65%;color:#222;font-weight:bold;letter-spacing:0.3px;"
    'font-size:14px;border-bottom:2px solid #5b149b;">Details</th>'
    "</tr></thead><tbody>"
)
_WARRANTY_STAR_SPAN = '<span style="color:#d72314;margin-right:4px;">\u2605</span> '
_STRUCTURAL_STAR_RE = re.compile(
    r"^\s*<span\b(?P<attrs>[^>]*)>(?P<star>.*?)</span>\s*",
    re.IGNORECASE | re.DOTALL,
)


def _alfa_card_row_html(
    row: SpecRow,
    *,
    index: int,
    total_rows: int,
    first_warranty_index: int | None,
) -> str:
    """Render one specification or warranty row for the Kiachahiye.alfa card."""
    label_html = html.escape(row.label, quote=False)
    value_html = html.escape(row.value, quote=False)
    is_last = index == total_rows - 1

    if row.is_warranty:
        border_top = "border-top:1px solid #f0d5db;" if index == first_warranty_index else ""
        border_bottom = "border-bottom:none;" if is_last else "border-bottom:1px solid #f0d5db;"
        left_style = (
            "background:linear-gradient(90deg,#fff5f5 0%,#fcf4f9 100%);"
            f"{border_top}{border_bottom}padding:12px 16px;text-align:left !important;"
            "color:#d72314;font-weight:bold;"
        )
        right_style = (
            "background:linear-gradient(90deg,#fcf4f9 0%,#faf4ff 100%);"
            f"{border_top}{border_bottom}padding:12px 16px;text-align:left !important;"
            "color:#5b149b;font-weight:bold;"
        )
        return (
            f'<tr><td style="{left_style}"><strong>{label_html}</strong></td>'
            f'<td style="{right_style}"><strong>{_WARRANTY_STAR_SPAN}{value_html}</strong></td></tr>'
        )

    bg = "background:#faf8fd;" if index % 2 == 1 else ""
    border_bottom = "border-bottom:none;" if is_last else "border-bottom:1px solid #f2ecf7;"
    left_style = (
        f"{bg}{border_bottom}padding:10px 16px;text-align:left !important;"
        "color:#2c3345;font-weight:600;"
    )
    label_key = row.label.strip().lower()
    if label_key == "model":
        right_style = f"{bg}{border_bottom}padding:10px 16px;text-align:left !important;"
        rendered_value = (
            '<span style="background:rgba(91,20,155,0.08);color:#5b149b;'
            f'padding:2px 8px;border-radius:4px;font-weight:bold;">{value_html}</span>'
        )
    elif label_key in ("brand", "capacity"):
        right_style = (
            f"{bg}{border_bottom}padding:10px 16px;text-align:left !important;"
            "color:#111;font-weight:600;"
        )
        rendered_value = value_html
    else:
        right_style = (
            f"{bg}{border_bottom}padding:10px 16px;text-align:left !important;color:#222;"
        )
        rendered_value = value_html

    return (
        f'<tr><td style="{left_style}">{label_html}</td>'
        f'<td style="{right_style}">{rendered_value}</td></tr>'
    )


def build_kiachahiye_alfa_card_html(rows: list[SpecRow]) -> str:
    """Render the rounded-card specification table for Kiachahiye.alfa."""
    first_warranty_index = next(
        (idx for idx, r in enumerate(rows) if r.is_warranty), None
    )
    total = len(rows)
    body = "".join(
        _alfa_card_row_html(
            row,
            index=idx,
            total_rows=total,
            first_warranty_index=first_warranty_index,
        )
        for idx, row in enumerate(rows)
    )
    return _ALFA_CARD_HEAD + body + TABLE_TAIL


def extract_kiachahiye_alfa_card_rows(text: str) -> list[SpecRow]:
    """Read a Kiachahiye.alfa card table back into its SpecRow list.

    Structurally validates the table, ensures warranty rows have the required warranty
    star badge without coupling to exact inline styles or attribute ordering, and rejects
    missing stars, malformed markup, or ambiguous multiple stars.
    """
    body = (text or "").strip()
    if not (body.lower().startswith("<table") and body.lower().endswith("</table>")):
        raise TemplateShapeError(
            f"Description is not one '<table'...'</table>' fragment: {body[:60]!r}"
        )
    rows: list[SpecRow] = []
    for chunk in _ROW_RE.findall(body):
        cells = _CELL_RE.findall(chunk)
        if cells and all(tag.lower() == "h" for tag, _ in cells):
            continue  # table header
        if len(cells) != 2 or any(tag.lower() != "d" for tag, _ in cells):
            raise TemplateShapeError(
                f"a spec row must be exactly two <td> cells, got {len(cells)}: {chunk[:60]!r}"
            )
        label_raw = cells[0][1]
        val_raw = cells[1][1]

        label_match = _STRONG_RE.match(label_raw)
        is_warranty = bool(label_match)
        label_inner = label_match.group(1) if label_match else label_raw
        label_text = html.unescape(_TAG_RE.sub("", label_inner)).strip()

        val_match = _STRONG_RE.match(val_raw)
        val_inner = val_match.group(1) if val_match else val_raw

        if is_warranty:
            if not val_match:
                raise TemplateShapeError(
                    f"warranty row {label_text!r} value is not wrapped in strong tags: {val_raw[:60]!r}"
                )
            star_match = _STRUCTURAL_STAR_RE.match(val_inner)
            if not star_match:
                if any(probe in val_inner for probe in ("\u2605", "&#9733;", "&#x2605;", "&starf;")):
                    raise TemplateShapeError(
                        f"malformed warranty star markup in row {label_text!r}: {val_inner[:60]!r}"
                    )
                raise TemplateShapeError(
                    f"warranty row {label_text!r} is missing the required warranty star badge: {val_inner[:60]!r}"
                )
            star_content = html.unescape(star_match.group("star")).strip()
            if star_content != "\u2605":
                raise TemplateShapeError(
                    f"warranty row {label_text!r} star span contains {star_content!r}, expected '\\u2605'"
                )
            attrs = star_match.group("attrs")
            if attrs.count('"') % 2 != 0 or attrs.count("'") % 2 != 0:
                raise TemplateShapeError(
                    f"malformed quotes in warranty star attributes for row {label_text!r}: {attrs!r}"
                )
            remainder = val_inner[star_match.end():]
            if _STRUCTURAL_STAR_RE.search(remainder):
                raise TemplateShapeError(
                    f"ambiguous multiple warranty stars in row {label_text!r}: {val_inner[:60]!r}"
                )
            value_text = html.unescape(_TAG_RE.sub("", remainder)).strip()
            rows.append(SpecRow(label_text, value_text, is_warranty=True))
        else:
            if val_match:
                raise TemplateShapeError(
                    f"mismatched boldness in spec row {label_text!r}: value is bold but label is not"
                )
            star_match = _STRUCTURAL_STAR_RE.search(val_inner)
            if star_match and html.unescape(star_match.group("star")).strip() == "\u2605":
                raise TemplateShapeError(
                    f"unexpected warranty star badge in non-warranty row {label_text!r}: {val_inner[:60]!r}"
                )
            value_text = html.unescape(_TAG_RE.sub("", val_inner)).strip()
            rows.append(SpecRow(label_text, value_text, is_warranty=False))
    return rows


KIACHAHIYE_ALFA_CARD = DescriptionTemplate(
    name="kiachahiye_alfa_card",
    render=build_kiachahiye_alfa_card_html,
    extract=extract_kiachahiye_alfa_card_rows,
    starts_with="<table",
    ends_with="</table>",
)

DESCRIPTION_TEMPLATES: dict[str, DescriptionTemplate] = {
    SPEC_TABLE.name: SPEC_TABLE,
    KIACHAHIYE_ALFA_CARD.name: KIACHAHIYE_ALFA_CARD,
}


def template_for(key: str | DescriptionTemplate) -> DescriptionTemplate:
    """Resolve a cell's ``description_template`` value to the template itself.

    Same shape as ``title_formula``: an object is taken as given, a string is a
    registry name, and a bad name is an error that names the registry.
    """
    if isinstance(key, DescriptionTemplate):
        return key
    found = DESCRIPTION_TEMPLATES.get(key) if isinstance(key, str) else None
    if found is None:
        raise ValueError(
            f"unknown DescriptionTemplate {key!r} -- DESCRIPTION_TEMPLATES holds "
            f"{', '.join(sorted(DESCRIPTION_TEMPLATES)) or 'nothing yet'}"
        )
    return found


# ---------------------------------------------------------------------------
# Template conformance -- run once at startup, in place of a gate that reads markup
# ---------------------------------------------------------------------------
#: The rows every template is tried on: a Brand row, a hyphenated code, an escaped
#: ``&``, a value whose doubled space ``clean_inline`` must collapse, and **two** bold
#: rows -- a component's term in the middle of the table and the Warranty line at the
#: end.  The shop's listings name bold after a part far more often than after the word
#: ``Warranty`` (``Compressor``, ``Parts``, ``PCB``), and a plain row follows the first
#: bold one, so a shape that bolds by that word, by position or by a trailing run is
#: caught here instead of shipping a Description the gate reads as unbolded.
CONFORMANCE_ROWS: list[SpecRow] = [
    SpecRow("Brand", "Haier"),
    SpecRow("Model", "WD-1051 HC"),
    SpecRow("Compressor", "10 Years", is_warranty=True),
    SpecRow("Color", "Black & White"),
    SpecRow("In the Box", "Remote  with  2 x AA"),
    SpecRow("Warranty", "1 Year", is_warranty=True),
]

#: Rows whose own values are markup, for the rules a plain sample cannot show.
#: :func:`_row_html` escapes each cell (``html.escape(text, quote=False)``), so these
#: arrive as text; a pasted listing that interpolates ``{value}`` straight into the
#: table sends the ``<b>`` as a tag and the ``&`` as a broken entity.  The other rows
#: try the mistakes a *vocabulary* comparison cannot see: a value carrying tags the
#: table itself writes (``<td>``, and ``<strong>`` inside a row the shape already
#: bolds), a label carrying markup (a shape that escapes values and forgets labels), and
#: the unterminated ``<b`` whose closing tag swallows the cell after it.
ESCAPE_PROBE: list[SpecRow] = [
    SpecRow("Material", 'Steel <b>1 mm</b> & "X"'),
    SpecRow("Finish", "Matte <td>brushed</td> steel"),
    SpecRow("Warranty", "Covers <strong>parts</strong> only", is_warranty=True),
    SpecRow("Class <b>Room</b>", "Sits under the sink"),
    SpecRow("Notes", "Cable <b"),
]

#: The same rows, same boldness, same label *words*, with nothing in the text a browser
#: could read as markup.  Any tag this renders -- or any count of a tag -- that the real
#: render does not match came out of the shop's text, not from the shape.  The label is
#: cleared of markup but keeps its words, so a shape that bolds by the word ``Warranty``
#: still bolds the same row here and does not show up as an injected tag.
_PROBE_STANDIN: list[SpecRow] = [
    SpecRow(_TAG_RE.sub("", row.label), "plain text", row.is_warranty) for row in ESCAPE_PROBE
]

#: An ``&`` is legal only as the start of an entity reference -- a named one, ``&#dd;``
#: or ``&#xhh;``.  Everything else is text the template forgot to escape.
_BARE_AMP_RE = re.compile(r"&(?![A-Za-z][A-Za-z0-9]*;|#[0-9]+;|#[Xx][0-9A-Fa-f]+;)")

#: A named reference, for the second half of that rule: ``&bogus;`` has the shape of an
#: entity and no browser's table has the name, so it is shipped as the letters.
#: :data:`html.entities.html5` is the HTML5 named-character-reference table -- the same
#: one :func:`html.unescape` decodes with -- and every key carries its ``;``.
_NAMED_REF_RE = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")

#: A numeric reference: ``&#38;`` or ``&#x26;``.  The digits are a code point, so the
#: third half of the rule asks whether Unicode has a character at that number at all.
_NUMERIC_REF_RE = re.compile(r"&#([Xx])?([0-9A-Fa-f]+);")

#: Categories that name no printable glyph: control codes, surrogates, and code points
#: Unicode has not assigned.  A browser answers each one with the replacement character
#: or with nothing, and both are visible to the customer.
_UNPRINTABLE_CATEGORIES = frozenset({"Cc", "Cn", "Cs"})

#: HTML5's void elements -- they open and close in one tag, so they never belong on the
#: open-element stack a shape is judged against.  ``<br>`` between two spec lines is a
#: legitimate way to space a table out and must not read as an unclosed tag.
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
})

#: The tag pairs ``audit.py`` counts, spelled as that gate spells them.  The
#: trailing space in ``"th "`` is the gate's own blind spot -- a header written
#: bare as ``<th>`` counts as unbalanced -- and a template has to live with it,
#: because the gate is not being changed to accommodate a new shape.
CONFORMANCE_TAGS = ("table", "caption", "thead", "tbody", "tr", "td", "th ")

_EMPTY_CELL_RE = re.compile(r"<td[^>]*></td>", re.IGNORECASE)
_GATE_ROW_RE = re.compile(r"<tr>", re.IGNORECASE)
_GATE_LABEL_RE = re.compile(r"<tr><td[^>]*>(?:<strong>)?([^<]+)", re.IGNORECASE)


def _composed_cell(template: DescriptionTemplate) -> str:
    """Exactly the string a cell ships: the render, inline-flattened."""
    return clean_inline(template.render(list(CONFORMANCE_ROWS)))


def _value_of_row_chunk(chunk: str) -> str:
    """Inner HTML of a row's second cell, or "" when the row is not two cells."""
    cells = _CELL_RE.findall(chunk)
    return cells[1][1] if len(cells) == 2 else ""


def _clip(text: str) -> str:
    """``text`` as a repr short enough to read on a terminal line."""
    shown = repr(text)
    return shown if len(shown) <= 60 else shown[:57] + "...'"


def _round_trip_problem(wrote: list[SpecRow], got: list[SpecRow], where: str) -> str:
    """One line naming the first field a template's pair disagreed about.

    This used to print the two label lists, which are identical whenever the damage is
    inside a value or in its boldness -- the operator got a diff of the same thing
    twice and had to guess.  Say which row, which field, and what each side holds.
    The harness cannot tell whether ``render`` wrote it wrong or ``extract`` read it
    wrong, so the line names the disagreement, not a culprit.  Returns "" when the
    read-back matches, so the caller only appends real problems.
    """
    if len(got) != len(wrote):
        return (
            f"{where}: {len(got)} rows came back where the harness wrote {len(wrote)}"
            f" -- {[row.label for row in got]} instead of {[row.label for row in wrote]}"
        )
    for index, (want, have) in enumerate(zip(wrote, got, strict=True), start=1):
        differs: list[str] = []
        if want.label != have.label:
            differs.append(f"label {_clip(have.label)}, not {_clip(want.label)}")
        if want.value != have.value:
            differs.append(f"value {_clip(have.value)}, not {_clip(want.value)}")
        if want.is_warranty != have.is_warranty:
            differs.append(
                f"{'bold' if have.is_warranty else 'plain'},"
                f" not {'bold' if want.is_warranty else 'plain'}"
            )
        if differs:
            return f"{where}: row {index} ({_clip(want.label)}) " + "; ".join(differs)
    return ""


def _row_markup_diffs(template: DescriptionTemplate) -> list[str]:
    """One line per probe row whose own render writes a different table than its plain twin.

    Row by row, not over the whole fragment: two rows can damage the same tag name in
    opposite directions -- one injects a ``</td>``, the next swallows one -- and a
    table-wide count then agrees with the plain table and says nothing.  Comparing a
    row against the same row with ``plain text`` in it keeps every wrapper tag the
    shape writes on both sides, so what is left is the shop's own markup.
    """
    lines: list[str] = []
    for index, (probe, standin) in enumerate(zip(ESCAPE_PROBE, _PROBE_STANDIN, strict=True), 1):
        have = Counter(_TAG_RE.findall(clean_inline(template.render([probe]))))
        wrote = Counter(_TAG_RE.findall(clean_inline(template.render([standin]))))
        extra = [f"{tag} written {have[tag]}x, not {wrote[tag]}x"
                 for tag in sorted(set(have) | set(wrote)) if have[tag] > wrote[tag]]
        eaten = [f"{tag} written {have[tag]}x, not {wrote[tag]}x"
                 for tag in sorted(set(have) | set(wrote)) if have[tag] < wrote[tag]]
        culprit = next((text for text in (probe.label, probe.value) if "<" in text), "")
        if extra:
            lines.append(
                f"row {index} ({_clip(probe.label)}) ships the shop's own text as markup: "
                + ", ".join(extra[:3])
                + f" -- the tag came from {_clip(culprit)}; escape every label and value "
                "(html.escape(text, quote=False)) so the table's tags stay the only tags"
            )
        if eaten:
            lines.append(
                f"row {index} ({_clip(probe.label)}) loses the shape's own markup: "
                + ", ".join(eaten[:3])
                + f" -- an unterminated '<' in {_clip(culprit)} swallows the tag that "
                "follows it; escape every label and value the same way"
            )
    return lines


class _Nesting(HTMLParser):
    """The open-element stack a browser keeps while it reads this fragment.

    Counts cannot see a crossing: ``<td>A</td><td>B</tr></td>`` writes exactly the tags
    ``<td>A</td><td>B</td></tr>`` does, and so does a ``<strong>`` whose partner lands in
    the next row.  A browser reads them differently -- it closes the open cell at the
    ``</tr>`` and drops the tag that arrives after it, or keeps bolding into the row
    after the warranty line -- so a shape is not finished when its tag counts agree.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.open: list[str] = []
        self.problems: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _VOID_TAGS:
            self.open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _VOID_TAGS:
            self.problems.append(f"a self-closed <{tag}/> writes no cell the gate can fill")

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            return
        if not self.open:
            self.problems.append(f"a stray </{tag}> with nothing open to close")
        elif self.open[-1] != tag:
            self.problems.append(
                f"a </{tag}> written while <{self.open[-1]}> is still open -- the browser "
                "closes that element first, so the tags that follow land in a cell the "
                "shape did not put them in; close every tag in the order it opened them"
            )
            if tag in self.open:
                del self.open[self.open.index(tag)]
            else:
                self.open.pop()
        else:
            self.open.pop()


def _nesting_problems(markup: str) -> list[str]:
    """Crossed, stray, self-closed or never-closed tags in one fragment.

    One crossing usually breaks the next few tags too, so the walk reports the first two
    and counts the rest: the operator needs the shape of the mistake, not a line for
    every tag after it.
    """
    walker = _Nesting()
    walker.feed(markup)
    walker.close()
    if walker.open:
        walker.problems.append(
            f"never closed: {walker.open[:3]} -- the browser carries them past the end of "
            "the table and the listing prints the rest of the page inside them"
        )
    if len(walker.problems) > 3:
        return [
            *walker.problems[:2],
            f"and {len(walker.problems) - 2} more tags closed out of order in the same table",
        ]
    return walker.problems


def _unprintable_references(markup: str) -> list[str]:
    """Every ``&#...;`` with no character behind it, in first-seen order.

    ``&#999999999;`` is a syntactically clean reference, so the ampersand rule lets it
    past, and :func:`html.unescape` answers it with U+FFFD -- the replacement glyph the
    customer reads where the shop wrote a specification.  A surrogate, a zero, a code
    point past U+10FFFF and the control and unassigned ranges all fail the same way, and
    a control code like ``&#27;`` can silently disappear instead.
    """
    bad: list[str] = []
    for match in _NUMERIC_REF_RE.finditer(markup):
        value = int(match.group(2), 16 if match.group(1) else 10)
        unprintable = (
            not 0 < value <= 0x10FFFF
            or unicodedata.category(chr(value)) in _UNPRINTABLE_CATEGORIES
        )
        if unprintable:
            bad.append(match.group(0))
    return dedupe_preserve_order(bad)


def _unknown_entities(markup: str) -> list[str]:
    """Every ``&name;`` the HTML5 table has no entry for, in first-seen order.

    The shape's structural markup is scanned too: an entity out between the rows never
    reaches a cell, so no round-trip can notice that the browser has no name for it.
    """
    return dedupe_preserve_order(
        [
            f"&{match.group(1)};"
            for match in _NAMED_REF_RE.finditer(markup)
            if f"{match.group(1)};" not in HTML5_NAMED_REFERENCES
        ]
    )


def _escaping_problems(template: DescriptionTemplate) -> list[str]:
    """Whether a shape keeps the shop's text as text: markup escaped, references intact.

    Five independent rules, because a pasted listing fails them separately: it can leak
    the value's own tag, swallow one of the shape's, send a bare ``&`` that no browser
    has to read as one character, ship a name no browser has, ship a number no browser
    has a character for, or escape correctly while its ``extract`` forgets to undo it.
    """
    problems: list[str] = []
    probe_html = template.render(list(ESCAPE_PROBE))
    shipped = clean_inline(probe_html)

    problems.extend(_row_markup_diffs(template))
    unknown = _unknown_entities(shipped)
    if unknown:
        problems.append(
            f"an entity no browser has a name for: {unknown[:3]} -- the HTML5 table has no such "
            "entry, so the characters ship as they are and the listing prints the code to the "
            "customer; write the character itself, or a name the table has (&amp;, &lt;, &gt;)"
        )
    unprintable = _unprintable_references(shipped)
    if unprintable:
        problems.append(
            f"a numeric reference with no character behind it: {unprintable[:3]} -- the browser "
            "prints the replacement glyph, or nothing at all, where the shop wrote a "
            "specification; write the character itself, or a number that names one (&#38;, &#x26;)"
        )
    bare = _BARE_AMP_RE.search(shipped)
    if bare is not None:
        problems.append(
            "an unescaped '&' in the cell: "
            f"{shipped[max(0, bare.start() - 15):bare.start() + 15]!r} -- a bare ampersand "
            "is not an entity, and the browser is free to read the letters after it as one; "
            "ship '&' as '&amp;'"
        )
    try:
        back = template.extract(probe_html)
    except TemplateShapeError as error:
        problems.append(f"the markup probe: extract() refused its own output: {error}")
    else:
        problem = _round_trip_problem(ESCAPE_PROBE, back, "the markup probe read back")
        if problem:
            problems.append(problem)
    return problems


def template_problems(template: DescriptionTemplate) -> list[str]:
    """Every way one Description shape would fail the gates that already exist.

    The shop's upload gate (``audit.py``) and the thin-listing report read the
    *built* file with markup-shaped regexes.  A template is free to look however
    the store wants -- provided those readers still see every row it writes and the
    browser still sees the shop's words as words.  This checks a template's own
    ``render`` and ``extract`` against exactly the rules those readers apply, plus the
    nesting, escaping and boldness rules a plain sample cannot show, so a pasted listing
    shape they could not follow is refused at startup instead of shipping listings nobody
    can verify.

    Returns one human-readable string per failed rule; empty means conforming.
    """
    problems: list[str] = []
    cell = _composed_cell(template)

    # --- the boundary, both as declared and as the gate hard-codes it
    if (template.starts_with, template.ends_with) != ("<table", "</table>"):
        problems.append(
            "the gates demand one complete <table>...</table>, so a template must "
            f"declare starts_with='<table' and ends_with='</table>', not "
            f"{template.starts_with!r}/{template.ends_with!r}"
        )
    if not (cell.startswith("<table") and cell.endswith("</table>")):
        problems.append(
            f"description is not one complete <table>...</table> fragment: {cell[:60]!r}"
        )
    if len(cell.splitlines()) != 1:
        problems.append("description has a raw line break")
    for tag in CONFORMANCE_TAGS:
        opened, closed = cell.count(f"<{tag}"), cell.count(f"</{tag.strip()}>")
        if opened != closed:
            problems.append(
                f"unbalanced <{tag.strip()}> tags: {opened} open, {closed} close"
            )
    # Balance counts each tag on its own; this one asks whether they are closed in the
    # order they were opened, which a count can never show (see _Nesting).
    problems.extend(_nesting_problems(cell))
    if _EMPTY_CELL_RE.search(cell):
        problems.append("description has an empty cell")
    if "  " in _TAG_RE.sub("", cell):
        problems.append("description has a double space after the tags are stripped")

    # --- the row and label readers the gate and the thin report both use
    found = [html.unescape(_TAG_RE.sub("", m)) for m in _GATE_LABEL_RE.findall(cell)]
    wanted = [row.label for row in CONFORMANCE_ROWS]
    if found != wanted:
        problems.append(
            f"the gate's row reader found {len(found)} spec rows where the template "
            f"wrote {len(wanted)}: {found} -- it reads rows only as `<tr><td...>`"
        )
    if len(found) != len(set(found)):
        problems.append("description repeats a label")
    if cell.count("<tr") != len(_GATE_ROW_RE.findall(cell)):
        problems.append(
            "the gate's fact checker reads only a literal <tr>; an attribute on the "
            "row tag makes the row invisible to it"
        )
    strong_open, strong_close = cell.count("<strong"), cell.count("</strong")
    if (strong_open, strong_close) != (cell.count("<strong>"), cell.count("</strong>")):
        problems.append(
            "the gate reads a bold row as the literal text `<strong>...</strong>`: this shape "
            f"opens {strong_open} and closes {strong_close} of them but spells that exact text "
            f"{cell.count('<strong>')}/{cell.count('</strong>')} -- an attribute or a space "
            "inside the tag makes the warranty the shop paid for read as a plain row"
        )

    # --- bold is the warranty marker, not decoration
    body_rows = [chunk for chunk in _ROW_RE.findall(cell) if "<td" in chunk.lower()]
    if len(body_rows) == len(CONFORMANCE_ROWS):
        bolded = [i for i, chunk in enumerate(body_rows) if "<strong>" in _value_of_row_chunk(chunk)]
        expected = [i for i, row in enumerate(CONFORMANCE_ROWS) if row.is_warranty]
        if bolded != expected:
            problems.append(
                "bold and the warranty rows disagree: this shape bolds "
                f"{bolded}, the harness writes warranty rows {expected} -- the gate reads "
                "<strong> as *the* warranty marker, so a term it has to prove arrives "
                "unbolded and a bolded plain row is read as a warranty"
            )

    # --- and the template must read back what it wrote
    try:
        back = template.extract(template.render(list(CONFORMANCE_ROWS)))
    except TemplateShapeError as error:
        problems.append(f"extract() refused its own output: {error}")
    else:
        problem = _round_trip_problem(CONFORMANCE_ROWS, back, "extract() vs render()")
        if problem:
            problems.append(problem)

    # --- and the shop's text has to stay text, whatever the shape looks like
    problems.extend(_escaping_problems(template))
    return problems


def assert_template_conforms(template: DescriptionTemplate) -> None:
    """Raise with every reason ``template`` cannot ship, if there is any."""
    problems = template_problems(template)
    if problems:
        raise ValueError(
            f"DescriptionTemplate {template.name!r} cannot ship a Description the "
            "existing gates can read:\n  " + "\n  ".join(problems)
        )


# ---------------------------------------------------------------------------
# Short Description (DigiMall file only)
# ---------------------------------------------------------------------------
def _headline_rows(rows: list[SpecRow], limit: int = 3) -> list[SpecRow]:
    """Pick the most headline-worthy rows: differentiators before generic ones.

    Real ``Label: Value`` facts outrank whole-sentence rows (Overview / Key
    Features), which in turn outrank bookkeeping rows (Weight).
    """
    scored: list[tuple[int, int, SpecRow]] = []
    for index, row in enumerate(rows):
        if row.is_warranty:
            continue
        label = row.label.lower()
        if label in _STRUCTURAL_LABELS:
            score = 1
        elif label in GENERIC_LABELS:
            score = 2
        else:
            score = 0
        if re.search(r"\d", row.value):
            score -= 1
        scored.append((score, index, row))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored[:limit]]


#: Rows that say nothing a shopper would want in a buying summary.  The brand
#: and the model already appear in the Title, right above these bullets, and the
#: model is the SKU; repeating either as a bullet of its own is filler.
_BOILERPLATE_LABELS = frozenset(
    {"brand", "model", "sku", "item", "availability", "specification", "specifications"}
)

#: A value this shape cannot stand on its own in a sentence: a bare number
#: ("3"), a bare word ("White") or a code.  It is shown as "Label: value".
_BARE_VALUE_RE = re.compile(r"^[^\s]*$|^\d+(?:\.\d+)?\s*(?:x\s*\d+)?$", re.IGNORECASE)

#: A measurement on its own ("6 Kg", "2.5 L/Hour", "20 L") is meaningless as a
#: bullet -- 6 kilograms of WHAT? -- so it keeps its label too.
_MEASUREMENT_RE = re.compile(r"^[\d.,]+\s*[A-Za-z%][A-Za-z%/.\-]{0,6}$")

#: A feature this long is only used as a Short Description bullet when nothing
#: shorter is left -- it does not read as a bullet.
FEATURE_BULLET_MAX_WORDS = 12

LEAD_IN_RE = re.compile(
    r"^(?:(?:key|additional)\s+)?(?:features?|specifications?|highlights?)\s*(?:include|are)?\s*[:—–-]?\s*",
    re.IGNORECASE,
)


def _clean_feature(feature: str) -> str:
    cleaned = LEAD_IN_RE.sub("", feature).strip()
    return cleaned[0].upper() + cleaned[1:] if cleaned else ""


def _is_boilerplate_feature(feature: str, brand: str = "", model: str = "") -> bool:
    cleaned = LEAD_IN_RE.sub("", feature).strip()
    if not cleaned:
        return True
    norm = re.sub(r"[()\s]+", " ", cleaned).strip().lower()
    brand_l = brand.lower().strip()
    model_l = model.lower().strip()
    return bool(brand_l and model_l and brand_l in norm and model_l in norm)


def _fact_matcher(value: str) -> re.Pattern[str]:
    """Match a warranty duration the way the shop re-writes it: `10 Years`, `10-Year`, `10 Yrs`.

    The bare digits are not enough -- a row's `1 Year` must not be found inside `10 Years` -- so the
    number is matched as one whole number with its unit, and a value carrying no number at all
    (`Official Brand Warranty`) is matched as the phrase it is.
    """
    number = re.search(r"\d+", value)
    if not number:
        return re.compile(re.escape(value.strip()), re.IGNORECASE)
    if re.search(r"(?i)y(ea)?rs?", value):
        unit = r"year|yr"
    elif re.search(r"(?i)mo", value):
        unit = r"month|mo"
    else:
        unit = ""
    tail = rf"\s*(?:{unit})s?\b" if unit else r"\b"
    return re.compile(rf"\b{number.group()}{tail}", re.IGNORECASE)


def _printed_warranty_terms(
    warranty_rows: list[SpecRow],
) -> tuple[list[tuple[str, re.Pattern[str]]], list[re.Pattern[str]]]:
    """What the warranty table already shows: each row's part word with its own duration, plus bare rows.

    A row labelled ``Warranty`` states no part, so its value is the whole fact -- a feature bullet
    carrying the same fact is the same fact.
    """
    facts: list[tuple[str, re.Pattern[str]]] = []
    unnamed: list[re.Pattern[str]] = []
    for row in warranty_rows:
        if not row.is_warranty:
            continue
        value = re.sub(r"\s+", " ", row.value).strip().lower()
        if not value:
            continue
        if row.label.lower() == "warranty":
            unnamed.append(_fact_matcher(value))
            continue
        part = re.sub(r"(?i)\s*warrant(?:y|ies)\s*$", "", row.label).strip().lower()
        if part:
            facts.append((part, _fact_matcher(value)))
    return facts, unnamed


def _states_a_printed_warranty(
    feature: str,
    facts: list[tuple[str, re.Pattern[str]]],
    unnamed: list[re.Pattern[str]],
) -> bool:
    """Whether this feature bullet is a warranty fact the table already prints as its own row.

    A warranty written as a bullet is collected by :mod:`warranty` and printed as a row, so leaving
    the same words inside "Key Features" shows the buyer the fact twice.  A bullet repeats a row
    only when it names the same part AND the same duration: `Extended Compressor Warranty For First
    Buyers` shares only a word with the `Compressor Warranty | 10 Years` row, and cutting it would
    delete a claim the table never prints.
    """
    lowered = re.sub(r"\s+", " ", feature.replace("-", " ")).strip().lower()
    if "warrant" not in lowered:
        return False
    return any(
        re.search(rf"\b{re.escape(part)}\b", lowered) and duration.search(lowered)
        for part, duration in facts
    ) or any(matcher.search(lowered) for matcher in unnamed)


def _bullet_sentence(value: str, label: str) -> str:
    """One shopper-readable line from a spec row.

    "Capacity: 11 Cubic Feet" reads well as "11 Cubic Feet capacity."; a bare
    value such as "White" or "3" does not, so those keep their label in front
    ("Product Color: White", "HDMI: 3") rather than producing the ungrammatical
    "3 hdmi." A value that already ends in its own label is not made to repeat
    the word, and a value that is already a sentence is left exactly as written.
    """
    value = value.strip().rstrip(".")
    if not value:
        return ""
    if _BARE_VALUE_RE.match(value) or _MEASUREMENT_RE.match(value):
        return f"{label}: {value}."
    if " " in value and value[-1] not in ",;:-–—":
        return value + "."
    if value.split()[-1].lower() == label.rsplit(maxsplit=1)[-1].lower():
        return value + "."
    return f"{value} {label.lower()}."


def build_short_description(
    bundle_rows: list[SpecRow],
    product_type: str,
    feature_items: Sequence[str] = (),
    intro: str = "",
    brand: str = "",
    model: str = "",
) -> tuple[str, int]:
    """Three bullets whenever the source states three facts; fewer only if thin.

    Nothing is invented to reach three, and nothing is padded with filler.  The
    facts are taken in this order:

      1. the headline spec rows (a real ``Label: Value`` outranks a sentence);
      2. the row's own individual feature bullets -- so a product whose table is
         one long "Key Features" run gets three short bullets instead of that
         whole run repeated as a single bullet;
      3. the opening sentence of the Description;
      4. the joined Key Features row (only when nothing above filled three);
      5. the Product Type, when the source states nothing else at all.
    """
    brand = brand or next((row.value for row in bundle_rows if row.label.lower() == "brand"), "")
    model = model or next((row.value for row in bundle_rows if row.label.lower() == "model"), "")
    facts = [
        row
        for row in bundle_rows
        if not row.is_warranty
        and row.label.lower() not in _BOILERPLATE_LABELS
        and row.label.lower() not in _STRUCTURAL_LABELS
    ]
    rows: list[SpecRow] = _headline_rows(facts, limit=3)

    items: list[str] = []
    seen: set[str] = set()
    for row in rows:
        sentence = _bullet_sentence(row.value, row.label)
        if not sentence or sentence in seen:
            continue
        seen.add(sentence)
        items.append(f"<li><p>{html.escape(sentence, quote=False)}</p></li>")

    if len(items) < SHORT_DESC_BULLETS:
        # The row's own features, in the order the source wrote them.  A short
        # feature is preferred; a long one is only used when nothing shorter is
        # left, because a bullet a shopper cannot scan at a glance is worse than
        # a longer one (the source's words are kept either way).
        short_features = [f for f in feature_items if len(f.split()) <= FEATURE_BULLET_MAX_WORDS]
        long_features = [f for f in feature_items if len(f.split()) > FEATURE_BULLET_MAX_WORDS]
        for raw_feature in short_features + long_features:
            if len(items) >= SHORT_DESC_BULLETS:
                break
            if _is_boilerplate_feature(raw_feature, brand=brand, model=model):
                continue
            feature = _clean_feature(raw_feature)
            if not feature:
                continue
            sentence = _bullet_sentence(feature, "Key Features")
            if not sentence or sentence in seen:
                continue
            seen.add(sentence)
            items.append(f"<li><p>{html.escape(sentence, quote=False)}</p></li>")

    if len(items) < SHORT_DESC_BULLETS and intro.strip():
        # The Description's own opening sentence: the source supplied it, so a
        # row whose table holds only two facts still reaches three bullets.
        sentence = intro.strip()
        if sentence not in seen:
            seen.add(sentence)
            items.append(f"<li><p>{html.escape(sentence, quote=False)}</p></li>")

    if len(items) < SHORT_DESC_BULLETS:
        # The Description's own opening sentence is prose the source supplied.
        for row in bundle_rows:
            if row.label.lower() in ("overview", "key features") and row.value.strip():
                sentence = row.value.strip()
                if sentence not in seen:
                    seen.add(sentence)
                    items.append(f"<li><p>{html.escape(sentence, quote=False)}</p></li>")
                break

    if not items:
        # The least we can say without inventing a claim: what the product is.
        items = [f"<li><p>{html.escape(product_type, quote=False)}.</p></li>"]
    return "<ul>" + "".join(items) + "</ul>", len(items)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------
def build_tags(
    brand: str,
    model: str,
    product_type: str,
    capacity: str,
    color: str,
    features: list[str],
    breadcrumb_leaf: str,
) -> list[str]:
    """5-8 tags built only from facts the classifier actually extracted."""
    candidates: list[str] = []
    if brand and model:
        candidates.append(f"{brand} {model}")
        candidates.append(f"{brand} {model} Price in Pakistan")
        if color:
            candidates.append(f"{model} {color}")
    if brand:
        candidates.append(brand)
        candidates.append(f"{brand} {product_type}")
    if capacity:
        candidates.append(f"{product_type} {capacity}")
        candidates.append(f"{brand} {product_type} {capacity}")
    candidates.append(product_type)
    if breadcrumb_leaf:
        candidates.append(breadcrumb_leaf)
    for feature in features[:3]:
        # A tag must never carry a comma: the Tags cell is itself a comma-
        # separated list, so "Smooth, Noise-free motor" would read as two tags
        # and push the row past the eight the schema allows.
        if len(feature.split()) <= 4 and "," not in feature:
            candidates.append(feature)
    # Two honest generic tags, built from the resolved Product Type rather than
    # invented product facts.  They only ever reach the list when the source was
    # too thin to supply five tags of its own, which is why they come last.
    candidates.append(f"{product_type} Price in Pakistan")
    candidates.append(f"Buy {product_type} in Pakistan")
    # "Sound Bar" and "Sound bars" are the same keyword to a search engine, so
    # only the first spelling of each is kept.
    tags: list[str] = []
    seen: set[str] = set()
    for tag in dedupe_preserve_order([tag for tag in candidates if tag.strip()]):
        key = re.sub(r"[^a-z0-9]", "", tag.lower())
        key = key[:-1] if len(key) > 3 and key.endswith("s") else key
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags[:8]


# ---------------------------------------------------------------------------
# SEO Title / SEO Description
# ---------------------------------------------------------------------------
# Kept beside the SEO code that uses them, so the numbers to edit are where the
# rule lives (config.py is still the one place to change a value).
from config import SEO_DESC_MAX as SEO_DESC_MAX  # noqa: E402  # edit in config.py
from config import SEO_DESC_MIN as SEO_DESC_MIN  # noqa: E402
from config import SEO_TITLE_MAX as SEO_TITLE_MAX  # noqa: E402
from config import SEO_TITLE_MIN as SEO_TITLE_MIN  # noqa: E402
from config import THIN_SHORT_BULLETS as SHORT_DESC_BULLETS  # noqa: E402  # edit in config.py

#: A ` - ` segment that survived as nothing but a number (`- 30 -`, `- 9.5 -`): a size with no name on it.
_BARE_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?[A-Za-z]?")


def _segments(text: str) -> list[str]:
    """The Title cut on its own ` - ` clause breaks, with separators and blanks stripped."""
    return [part.strip(" -,") for part in re.split(r"\s+-\s+", text) if part.strip(" -,")]


def _tidy_segments(text: str) -> str:
    """Rejoin segments, dropping any the cut emptied -- `Dispenser - - 3 Year Warranty` never ships."""
    return re.sub(r"\s{2,}", " ", " - ".join(_segments(text))).strip(" -,")


def _bare_number_segments(text: str) -> set[str]:
    return {part for part in _segments(text) if _BARE_NUMBER_RE.fullmatch(part)}


def _shed_token(text: str, token: str) -> str:
    """Take ONE fact out of the copy to fit the budget, or return the text untouched.

    Only a token standing as its own whole word is removable: cutting `Etech` out of the part number
    `Etech-12` shipped `Air Conditioner --12`, a mutilated code and a hole.  A cut that CREATES a
    segment of bare digits is refused too -- deleting `Frost` out of `- Frost 30 -` left the shop's
    result reading `- 30 -`, a number standing where a name was.  A number the row wrote by itself
    (`- 18G -`) is not created here and must not freeze the whole shed.
    """
    if not token:
        return text
    pattern = rf"(?<!\S){re.escape(token)}(?!\S)"
    if not re.search(pattern, text):
        return text
    candidate = _tidy_segments(re.sub(pattern, "", text, count=1))
    if _bare_number_segments(candidate) - _bare_number_segments(text):
        return text
    return candidate


def build_seo_title(base: str, feature_tokens: list[str]) -> str:
    """Fit the search-title base behind ` Price in Pakistan` -- the only words ever added.

    The base arrives already naming this row's brand, code, sub-type and type -- the shape ruled in
    ``title_builder.build_title`` -- so all that is left here is the fit: shed a whole fact when the
    base runs over budget, then cut on a word boundary.  The suffix is anchored: only the base's own
    copy is ever trimmed, so the result always ends on a complete phrase and never mid-word.

    Nothing is borrowed to reach the 65-90 window.  A row whose own words run short ships short, and
    ``main.py`` names it in the summary and ``qc.csv`` as ``seo_title_length`` -- padding it with a
    marketing clause would put words in the shop that the shop never wrote.
    """
    suffix = " Price in Pakistan"
    budget = SEO_TITLE_MAX - len(suffix)

    trimmed = base.strip()
    if len(trimmed) > budget:
        for token in feature_tokens:
            if len(trimmed) <= budget:
                break
            trimmed = _shed_token(trimmed, token)
        if len(trimmed) > budget:
            trimmed = trimmed[:budget].rsplit(" ", 1)[0].rstrip(" -,")

    return f"{trimmed}{suffix}".strip()


_STRUCTURAL_LABELS = {"brand", "model", "type", "overview", "key features"}


def _feature_phrases(rows: list[SpecRow]) -> list[str]:
    """Readable, source-backed feature phrases, most distinctive first."""
    phrases: list[str] = []
    for row in _headline_rows(rows, limit=12):
        if row.label.lower() in _STRUCTURAL_LABELS or row.label.lower() in GENERIC_LABELS:
            continue
        phrases.append(f"{row.label} {row.value}")
    for row in rows:
        if row.label.lower() == "key features":
            phrases.extend(
                item.strip() for item in row.value.split(",") if item.strip()
            )
    return phrases


def _grow_into_range(head: str, recipe: str, phrases: list[str], words: list[str]) -> str:
    """Extend ``head`` with this product's own keywords until the sentence reaches 151-155.

    The padding goes *inside* the sentence, in front of the closing recipe line,
    so the finished text always reads "... , keyword, keyword. Buy the best ...".
    Multi-word phrases are preferred because they read naturally; single words are
    a last resort.  Nothing that is not a fact about this product is ever added.
    """
    head = head.rstrip(".")
    extra: list[str] = []
    pool = list(dict.fromkeys(phrase for phrase in phrases if phrase.strip()))
    spare = list(dict.fromkeys(word for word in words if word.strip()))

    def render(chosen: list[str]) -> str:
        if not chosen:
            return f"{head}. {recipe}"
        return f"{head}, {', '.join(chosen)}. {recipe}"

    def grow(source: list[str], require_fit: bool) -> bool:
        for item in sorted(source, key=len, reverse=True):
            # Never say the same fact twice: the padding pool is built from the same spec rows the
            # head already quotes, so `..., Inverter Yes, Inverter Yes.` is reachable without this.
            if item in extra or item.lower() in head.lower():
                continue
            candidate = render([*extra, item])
            if len(candidate) > SEO_DESC_MAX:
                continue
            if require_fit and len(candidate) < SEO_DESC_MIN:
                continue
            extra.append(item)
            source.remove(item)
            return True
        return False

    while len(render(extra)) < SEO_DESC_MIN:
        # prefer a phrase that lands exactly inside the window
        # Prefer a phrase that lands inside the window; failing that, take the
        # longest item that still fits and keep going.  ``and`` short-circuits,
        # so the fallback grow only runs when the preferred one found nothing.
        if (
            not grow(pool, require_fit=True)
            and not grow(spare, require_fit=True)
            and not grow(pool, require_fit=False)
            and not grow(spare, require_fit=False)
        ):
            break
    return render(extra)


def build_seo_description(
    brand: str,
    model: str,
    product_type: str,
    category_name: str,
    warranty_duration: str | None,
    rows: list[SpecRow],
    tags: list[str] | None = None,
) -> str:
    """The section 8 recipe, then padded/trimmed into 151-155 characters.

    Padding only ever reuses this product's own facts -- its extracted specs, its key features and
    its brand, type and category.
    """
    brand_token = clean_inline(f"{brand} {model}").strip() or brand
    features = _feature_phrases(rows)
    type_short = " ".join(product_type.split()[:2])

    # Several closing lines, every one built only from this product's own brand
    # and category.  Offering more than one length is what lets the finished
    # sentence land inside 151-155 instead of stalling a character short.
    tails = [
        f"Buy the best {category_name} in Pakistan today.",
        f"Buy the best {brand} {category_name} in Pakistan today.",
        f"Buy the best {category_name} in Pakistan today at the best price.",
        f"Buy the best {brand} {category_name} in Pakistan at the best price today.",
    ]

    heads: list[str] = []
    for with_warranty in (True, False):
        for count in range(1, max(len(features), 1) + 1):
            head = f"{brand_token} {type_short}"
            if with_warranty and warranty_duration:
                head += f" with {warranty_duration} warranty"
            if features[:count]:
                head += ", " + ", ".join(features[:count])
            heads.append(head)
    heads.append(f"{brand_token} {type_short}")
    heads = list(dict.fromkeys(heads))
    heads.sort(key=len, reverse=True)

    # Keyword phrases this sentence may be padded with, richest first: the row's own tags, then
    # brand+type, then its extracted feature phrases.  The last resort is a whole fact about this
    # product -- never one word cut out of the Title, because a Title that states `1.5 Ton` hands
    # the ladder `1.5`, `Ton` and `Air`, and the shop's meta description then ends
    # `..., 1.5. Buy the best Air Conditioner in Pakistan today.`: a shredded Title, not a sentence.
    phrases: list[str] = list(tags or [])
    phrases.extend([f"{brand} {type_short}", f"{brand} {type_short} price in Pakistan"])
    phrases.extend(features)
    words: list[str] = [brand, type_short, category_name, "Pakistan"]

    longest = ""
    for tail in tails:
        for head in heads:
            base = f"{head.rstrip('.')}. {tail}"
            if SEO_DESC_MAX >= len(base) > len(longest):
                longest = base
            if SEO_DESC_MIN <= len(base) <= SEO_DESC_MAX:
                return base
            grown = _grow_into_range(head, tail, phrases, words)
            if SEO_DESC_MIN <= len(grown) <= SEO_DESC_MAX:
                return grown
            if len(grown) <= SEO_DESC_MAX and len(grown) > len(longest):
                longest = grown
    return longest[:SEO_DESC_MAX]


def build_description_bundle(
    *,
    brand: str,
    model: str,
    product_type: str,
    breadcrumb_leaf: str,
    color: str,
    capacity: str,
    warranty_rows: list[SpecRow],
    description: str,
    title: str,
    has_real_model: bool,
    feature_tokens: list[str],
) -> DescriptionBundle:
    """Assemble every §8 output for one product."""
    parsed = parse_description(description)
    warranty_duration = next(
        (row.value for row in warranty_rows if row.label.lower().startswith("compressor")),
        warranty_rows[0].value if warranty_rows else None,
    )

    rows: list[SpecRow] = []
    if brand:
        rows.append(SpecRow("Brand", brand))
    if has_real_model and model:
        rows.append(SpecRow("Model", model))
    for label, value in parsed.labelled:
        # Brand/Model are re-emitted from the resolved values, and Warranty rows
        # come from warranty_terms.py -- so the source's own lines are skipped
        # to avoid showing the same fact twice.
        # Warranty facts come only from warranty.py, which knows the brand's
        # reference terms.  Emitting the source's own warranty line as well would
        # print the same fact twice ("Motor Warranty: 10" and "10 Years").
        # `SubType` is this program's own field name, not a spec a shop wrote for a buyer: measured
        # on the 752-row sheet, 19 rows carry the line and all 19 were written here, to settle a type
        # question the Title and Description disagreed about.  It answers that question silently --
        # :func:`subtype_label` reads the source text, not this table -- and the buyer already
        # learns the value from the Title and from DigiMall's `Attribute_..._Type` cell.  It is
        # recognised the same way the reader recognises it, punctuation folded, because
        # `• Sub Type: Cassette` settles the very same question and would otherwise be printed.
        if "warrant" in label.lower() or _is_subtype_label(label) or label.lower() in (
            "brand", "model", "specification", "specifications"
        ):
            continue
        rows.append(SpecRow(label, value))
    if parsed.thin and not parsed.labelled and parsed.intro:
        rows.append(SpecRow("Overview", parsed.intro))
    if not parsed.labelled and not parsed.thin:
        rows.append(SpecRow("Type", product_type))
    if parsed.key_features:
        # Warranty facts are printed by warranty.py as their own rows; the ones it printed leave
        # the "Key Features" run so the buyer does not read them twice.  A warranty the reader
        # could not place stays exactly where the shop put it.
        printed_facts, printed_unnamed = _printed_warranty_terms(warranty_rows)
        features = [
            f
            for f in parsed.key_features
            if not _states_a_printed_warranty(f, printed_facts, printed_unnamed)
        ]
        clean_kf = [
            _clean_feature(f)
            for f in features
            if not _is_boilerplate_feature(f, brand=brand, model=model)
        ]
        if features:
            rows.append(SpecRow("Key Features", ", ".join(clean_kf or features)))
    rows.extend(warranty_rows)

    deduped: list[SpecRow] = []
    seen: set[str] = set()
    for source_row in rows:
        row = source_row
        key = row.label.lower()
        if key in seen and not row.is_warranty:
            continue
        # Two different facts share one label -- the source's own "Motor: Normal" and the brand's
        # "Motor: 10 Years".  The warranty row is the one renamed, so the source's wording is never
        # touched and the duplicate label disappears from the table.  A label that already ends in
        # the word is left alone: renaming "Warranty" made the table print "Warranty Warranty".
        if key in seen and not key.endswith("warranty"):
            row = dataclasses.replace(row, label=f"{row.label} Warranty")
            key = row.label.lower()
        # One label sells one question, so a second answer joins the first instead of printing the
        # label twice: `• Warranty: 1 Year, 10 Years` names no part and states two numbers, and
        # both are his, in his order.  A rename would have invented a word he never wrote.
        if key in seen:
            for index, earlier in enumerate(deduped):
                if earlier.label.lower() == key:
                    deduped[index] = dataclasses.replace(
                        earlier, value=f"{earlier.value}, {row.value}"
                    )
                    break
            continue
        seen.add(key)
        deduped.append(row)

    short_html, bullet_count = build_short_description(
        deduped, product_type, parsed.key_features, parsed.intro, brand=brand, model=model
    )
    tags = build_tags(
        brand, model, product_type, capacity, color, parsed.key_features, breadcrumb_leaf
    )
    seo_title = build_seo_title(title, feature_tokens)
    seo_description = clean_inline(
        build_seo_description(
            brand, model, product_type, product_type, warranty_duration, deduped, tags,
        )
    )
    thin = parsed.thin and not parsed.key_features
    return DescriptionBundle(
        branch=parsed.branch,
        short_description=clean_inline(short_html),
        short_description_bullets=bullet_count,
        tags=tags,
        seo_title=seo_title,
        seo_description=seo_description,
        spec_rows=deduped,
        key_features=parsed.key_features,
        warranty_rows=warranty_rows,
        thin=thin,
    )
