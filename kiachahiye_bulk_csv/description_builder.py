"""Section 8 -- the Description classifier plus Tags, SEO and Short Description.

Built once per product; both output files receive the identical Description,
Tags, SEO Title and SEO Description.  Short Description is built here too but is
written into the DigiMall file only (Alfa's schema has no such column).

Classifier -- four ingestion modes, one output shape (``Label: Value`` pairs):

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
from collections.abc import Sequence
from dataclasses import dataclass, field

from models import DescriptionBundle, SpecRow
from textutils import clean_inline, dedupe_preserve_order

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


def build_seo_title(
    title: str,
    product_type: str,
    brand: str,
    feature_tokens: list[str],
) -> str:
    """``Title + " Price in Pakistan"`` trimmed/padded into 65-90 characters.

    The suffix is anchored: only the Title's own copy is ever trimmed, so the
    result always ends on a complete phrase and never mid-word.
    """
    suffix = " Price in Pakistan"
    budget = SEO_TITLE_MAX - len(suffix)

    trimmed = title.strip()
    if len(trimmed) > budget:
        for token in feature_tokens:
            if len(trimmed) <= budget:
                break
            # Only a token that stands as its own word may be removed: cutting `Etech` out of the
            # part number `Etech-12` shipped `Air Conditioner --12` -- a mutilated code and a hole.
            pattern = rf"(?<!\S){re.escape(token)}(?!\S)"
            if token and re.search(pattern, trimmed):
                trimmed = re.sub(pattern, "", trimmed, count=1)
                # A deleted token can empty a whole ` - ` segment; the segment goes with it, or the
                # shop's search result reads "Dispenser - - 3 Year Compressor Warranty".
                trimmed = " - ".join(
                    part.strip(" -,")
                    for part in re.split(r"\s+-\s+", trimmed)
                    if part.strip(" -,")
                )
                trimmed = re.sub(r"\s{2,}", " ", trimmed).strip(" -,")
        if len(trimmed) > budget:
            trimmed = trimmed[:budget].rsplit(" ", 1)[0].rstrip(" -,")

    # Search a small, closed set of combinations: the Title (optionally padded
    # with its own brand/type words) against three honest suffixes.  The first
    # combination inside 65-90 characters wins.
    suffixes = (
        suffix,
        f" Price in Pakistan - Buy {brand} {product_type} Online",
        " Price in Pakistan - Buy Online at Best Price",
    )
    best = ""
    for title_variant in (
        trimmed,
        f"{trimmed} {brand}".strip(),
        f"{trimmed} {brand} {product_type}".strip(),
    ):
        for candidate_suffix in suffixes:
            candidate = f"{title_variant}{candidate_suffix}".strip()
            if len(candidate) > SEO_TITLE_MAX:
                continue
            if len(candidate) >= SEO_TITLE_MIN:
                return candidate
            if len(candidate) > len(best):
                best = candidate
    if best:
        return best
    return f"{trimmed}{suffix}".strip()[:SEO_TITLE_MAX].rsplit(" ", 1)[0] or trimmed


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
    title: str,
    tags: list[str] | None = None,
) -> str:
    """The section 8 recipe, then padded/trimmed into 151-155 characters.

    Padding only ever reuses this product's own facts -- its extracted specs,
    its key features, its real Title and its tags.
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

    # Keyword phrases this sentence may be padded with, richest first: the row's
    # own tags, then brand+type, then its extracted feature phrases.  Single
    # words from the Title are the last resort.
    phrases: list[str] = list(tags or [])
    phrases.extend([f"{brand} {type_short}", f"{brand} {type_short} price in Pakistan"])
    phrases.extend(features)
    words: list[str] = []
    if title:
        words.extend(title.split())
    words.extend([brand, type_short, category_name, "Pakistan"])

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
        if "warrant" in label.lower() or label.lower() in (
            "brand", "model", "specification", "specifications"
        ):
            continue
        rows.append(SpecRow(label, value))
    if parsed.thin and not parsed.labelled and parsed.intro:
        rows.append(SpecRow("Overview", parsed.intro))
    if not parsed.labelled and not parsed.thin:
        rows.append(SpecRow("Type", product_type))
    if parsed.key_features:
        clean_kf = [
            _clean_feature(f)
            for f in parsed.key_features
            if not _is_boilerplate_feature(f, brand=brand, model=model)
        ]
        rows.append(SpecRow("Key Features", ", ".join(clean_kf or parsed.key_features)))
    rows.extend(warranty_rows)

    deduped: list[SpecRow] = []
    seen: set[str] = set()
    for source_row in rows:
        row = source_row
        key = row.label.lower()
        if key in seen and not row.is_warranty:
            continue
        if key in seen:
            # Two different facts share one label -- the source's own
            # "Motor: Normal" and the brand's "Motor: 10 Years".  The warranty
            # row is the one renamed, so the source's wording is never touched
            # and the duplicate label disappears from the table.
            row = dataclasses.replace(row, label=f"{row.label} Warranty")
            key = row.label.lower()
        seen.add(key)
        deduped.append(row)

    description_html = clean_inline(build_description_html(deduped))
    short_html, bullet_count = build_short_description(
        deduped, product_type, parsed.key_features, parsed.intro, brand=brand, model=model
    )
    tags = build_tags(
        brand, model, product_type, capacity, color, parsed.key_features, breadcrumb_leaf
    )
    seo_title = build_seo_title(title, product_type, brand, feature_tokens)
    seo_description = clean_inline(
        build_seo_description(
            brand, model, product_type, product_type, warranty_duration, deduped,
            title, tags,
        )
    )
    thin = parsed.thin and not parsed.key_features
    return DescriptionBundle(
        branch=parsed.branch,
        description_html=description_html,
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
