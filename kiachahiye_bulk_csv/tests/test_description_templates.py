"""A Description template is a named writer + reader pair, registered per cell.

These tests hold the two promises the per-(store x platform) template work is built
on: a template reads back exactly what it wrote (so a pasted template can be proved
lossless), and the registry is the only place a cell's template is looked up.
"""

from __future__ import annotations

import dataclasses
import html
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest

import main
import thin_report
from description_builder import (
    _PROBE_STANDIN,
    _TAG_RE,
    CONFORMANCE_ROWS,
    DESCRIPTION_TEMPLATES,
    ESCAPE_PROBE,
    KIACHAHIYE_ALFA_CARD,
    SPEC_TABLE,
    TABLE_HEAD,
    TABLE_TAIL,
    DescriptionTemplate,
    TemplateShapeError,
    _nesting_problems,
    assert_template_conforms,
    build_description_html,
    extract_spec_rows,
    template_for,
    template_problems,
)
from models import DescriptionBundle, SpecRow
from qc_report import QCFlagCollector
from tests.conftest import Pipeline
from textutils import clean_inline
from vendor_config import KIACHAHIYE
from writers import _single_line, build_alfa_row, build_digi_row

#: One real-shaped row: labelled bullets, an escaped `&`, and a warranty line that
#: becomes the bold row the gates read.
PROVEN_ROW = {
    "Title": "Dawlance 2 Taps Water Dispenser White - (WD-1051 HC)",
    "Description": (
        "The Dawlance WD-1051 HC is a 2 tap water dispenser.\n"
        "\u2022 Capacity: 20 Litres\n"
        "\u2022 Color: Black & White\n"
        "\u2022 Body Material: ABS\n"
        "Warranty: 1 Year"
    ),
    "Sell Price": "36,375",
    "Original Price": "36,475",
    "Categories": "Electronics / Home appliances / Water dispenser",
    "Brand": "Dawlance",
    "Image": "https://example.invalid/wd-1051.jpg",
}

PLAIN = [
    SpecRow("Brand", "Haier"),
    SpecRow("Capacity", "8 Kg"),
]
WITH_NOISE = [
    SpecRow("Brand", "Haier"),
    SpecRow("Color", "Black & White"),
    SpecRow("In the Box", "Remote, 2 x AA battery"),
    SpecRow("Warranty", "1 Year", is_warranty=True),
]

SHEETS = [
    Path(__file__).resolve().parent.parent / "data/input/Products.csv",
    Path(__file__).resolve().parent.parent / "data/input/Step 1.csv",
]


@pytest.fixture(scope="module")
def real_spec_rows() -> list[list[SpecRow]]:
    """The ``spec_rows`` of every row of every real sheet the shop's checkout has."""
    rows: list[list[SpecRow]] = []
    for sheet in SHEETS:
        if not sheet.exists():  # unit run on a checkout without the shop's sheets
            continue
        rows += [r.description.spec_rows for r in main.run(main.read_input(sheet), QCFlagCollector())]
    if not rows:
        pytest.skip("no shop sheets present in this checkout")
    return rows


def test_spec_table_writes_todays_markup() -> None:
    """The registry's first template is the markup the shop ships today."""
    assert SPEC_TABLE.name == "spec_table"
    assert SPEC_TABLE.render(PLAIN) == build_description_html(PLAIN)


def test_registry_lookup():
    assert "spec_table" in DESCRIPTION_TEMPLATES
    assert template_for("spec_table") is SPEC_TABLE
    # a template object may be handed straight back -- that is how a cell can hold
    # an inline template without a registry entry.
    assert template_for(SPEC_TABLE) is SPEC_TABLE


def test_unknown_template_key_names_the_registry() -> None:
    with pytest.raises(ValueError) as caught:
        template_for("spec_tabl")
    message = str(caught.value)
    assert "spec_tabl" in message
    assert "DESCRIPTION_TEMPLATES" in message
    assert "spec_table" in message


def test_template_is_frozen_so_sharing_is_safe() -> None:
    """Requirement: one template may serve two stores; nobody may edit it in place."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        SPEC_TABLE.name = "something_else"  # type: ignore[misc]


@pytest.mark.parametrize("rows", [PLAIN, WITH_NOISE, [], [SpecRow("a", "b")]])
def test_round_trip_is_exact(rows: list[SpecRow]) -> None:
    assert SPEC_TABLE.extract(SPEC_TABLE.render(rows)) == rows


def test_round_trip_covers_every_real_row(real_spec_rows: list[list[SpecRow]]) -> None:
    assert len(real_spec_rows) > 500
    for rows in real_spec_rows:
        assert SPEC_TABLE.extract(SPEC_TABLE.render(rows)) == rows


def test_warranty_bold_survives_the_round_trip() -> None:
    html_out = SPEC_TABLE.render(WITH_NOISE)
    assert "<strong>Warranty</strong>" in html_out
    recovered = SPEC_TABLE.extract(html_out)
    assert [row.is_warranty for row in recovered] == [
        row.is_warranty for row in WITH_NOISE
    ]


def test_entities_survive_the_round_trip() -> None:
    rows = [SpecRow("Color", "Black & White"), SpecRow("Notes", "2 x <b>AA</b>")]
    assert SPEC_TABLE.extract(SPEC_TABLE.render(rows)) == rows


def test_extract_rejects_a_row_that_is_not_two_cells() -> None:
    """A 1-cell or 3-cell row is unreadable: say so instead of dropping it silently."""
    with pytest.raises(TemplateShapeError):
        SPEC_TABLE.extract("<table><tbody><tr><td>Only one</td></tr></tbody></table>")
    with pytest.raises(TemplateShapeError):
        SPEC_TABLE.extract(
            "<table><tbody><tr><td>a</td><td>b</td><td>c</td></tr></tbody></table>"
        )


def test_extract_rejects_a_missing_boundary() -> None:
    with pytest.raises(TemplateShapeError):
        SPEC_TABLE.extract("Haier 8 Kg Washing Machine")


def test_extract_tolerates_attributes_on_the_tags_it_reads() -> None:
    """The reader keys on tag shapes, not on one exact spelling of them."""
    html_out = (
        '<table class="spec"><thead><tr><th>Specification</th><th>Details</th></tr></thead>'
        '<tbody><tr class="r1"><td style="x">Brand</td><td style="y">Haier</td></tr>'
        '<tr><td><strong>Warranty</strong></td><td><strong>1 Year</strong></td></tr></tbody></table>'
    )
    assert SPEC_TABLE.extract(html_out) == [
        SpecRow("Brand", "Haier"),
        SpecRow("Warranty", "1 Year", is_warranty=True),
    ]


def test_template_is_a_declared_shape() -> None:
    """A template states its own boundary so the gate never has to guess markup."""
    assert isinstance(SPEC_TABLE, DescriptionTemplate)
    assert SPEC_TABLE.starts_with == "<table"
    assert SPEC_TABLE.ends_with == "</table>"


# ---------------------------------------------------------------------------
# Task 2 -- the conformance harness a pasted template must pass
# ---------------------------------------------------------------------------
VALID_ROW = "<tr><td style=\"c\">{label}</td><td style=\"c\">{value}</td></tr>"
VALID_HEAD = (
    '<thead><tr><th style="c">Specification</th><th style="c">Details</th></tr></thead>'
)


def _plain_escape(text: str) -> str:
    """Exactly what :func:`_row_html` does to a cell: ``html.escape(text, quote=False)``."""
    return html.escape(text, quote=False)


def _cell_of(text: str, bold: bool, escape=_plain_escape) -> str:
    """One cell of a shape: the text escaped, then bolded if the row says so.

    Every conforming alternative in this file does these two things; they are the
    parts of ``_row_html`` a hand-pasted listing has to keep.
    """
    written = escape(text)
    return f"<strong>{written}</strong>" if bold else written


def _probe(
    row: str = VALID_ROW,
    *,
    head: str = VALID_HEAD,
    rows: list[SpecRow] | None = None,
    bold_all: bool = False,
    name: str = "probe",
) -> DescriptionTemplate:
    """A template that writes the harness's own sample rows in a given spelling.

    Like every shape it stands for, it escapes each cell and bolds what the row says
    to bold.  ``rows`` pins the data instead, for a shape that can only be shown by
    rows the harness does not probe with (a repeated label) -- and a pinned probe is a
    render that ignores what it is handed, so it picks up the escaping and round-trip
    problems on top of the one its test asks about.
    """

    def render(given: list[SpecRow]) -> str:
        sample = given if rows is None else rows
        body = "".join(
            row.format(
                label=_cell_of(r.label, bold_all or r.is_warranty),
                value=_cell_of(r.value, bold_all or r.is_warranty),
            )
            for r in sample
        )
        return f"<table>{head}<tbody>{body}</tbody></table>"

    return DescriptionTemplate(
        name=name,
        render=render,
        extract=lambda text: extract_spec_rows(
            text, starts_with="<table", ends_with="</table>"
        ),
        starts_with="<table",
        ends_with="</table>",
    )


def test_spec_table_conforms() -> None:
    assert template_problems(SPEC_TABLE) == []
    assert_template_conforms(SPEC_TABLE)


def test_a_shape_other_than_spec_tables_passes_too() -> None:
    """The harness reads only render/extract and the declared boundary."""
    assert template_problems(_probe()) == []


@pytest.mark.parametrize(
    "probe,phrase",
    [
        # a header written bare: the gate counts `<th `, so `<th>` reads as unbalanced
        (_probe(head="<thead><tr><th>Specification</th><th>Details</th></tr></thead>"),
         "unbalanced"),
        # an attribute on <tr>: the gate's literal `<tr>` and `<tr><td` both miss it
        (_probe('<tr class="r"><td>{label}</td><td>{value}</td></tr>'), "row reader"),
        # three columns: no reader knows which one is the value
        (_probe("<tr><td>{label}</td><td>{value}</td><td>x</td></tr>"), "two"),
        # pretty-printed markup: collapsed to one line, but `<tr> <td` is not `<tr><td`
        (_probe("<tr>\n<td>{label}</td>\n<td>{value}</td>\n</tr>"), "row reader"),
        # a repeated label: the gate reports a duplicated specification
        (_probe(rows=[SpecRow("Brand", "Haier"), SpecRow("Brand", "Dawlance")]), "label"),
        # an empty cell ships a row with no fact in it
        (_probe("<tr><td>{label}</td><td></td></tr>"), "empty"),
        # bold is the warranty marker; bolding a plain row hides its provenance
        (_probe(bold_all=True), "warrant"),
    ],
)
def test_a_broken_shape_reports_its_own_problem(
    probe: DescriptionTemplate, phrase: str
) -> None:
    problems = template_problems(probe)
    assert problems, f"{probe.name} was accepted"
    assert any(phrase in p.lower() for p in problems), (probe.name, problems)


def test_a_non_table_boundary_is_refused() -> None:
    """The untouched gate demands one <table>...</table>, whatever the template says."""

    def render(_rows: list[SpecRow]) -> str:
        return "<div><p>Haier</p></div>"

    probe = DescriptionTemplate(
        name="div_shape", render=render, extract=SPEC_TABLE.extract,
        starts_with="<div", ends_with="</div>",
    )
    problems = template_problems(probe)
    assert any("<table" in p for p in problems), problems


def test_a_template_that_cannot_read_itself_is_refused() -> None:
    """extract is not decoration: a template whose reader disagrees is a defect."""

    probe = DescriptionTemplate(
        name="lossy",
        render=SPEC_TABLE.render,
        extract=lambda _text: [],
        starts_with="<table",
        ends_with="</table>",
    )
    assert any("extract" in p.lower() for p in template_problems(probe))
    with pytest.raises(ValueError):
        assert_template_conforms(probe)


def test_assert_template_conforms_names_the_template() -> None:
    with pytest.raises(ValueError) as caught:
        assert_template_conforms(_probe("<tr><td>{label}</td><td>{value}</td><td>x</td></tr>"))
    assert "probe" in str(caught.value)


# ---------------------------------------------------------------------------
# Task 10 review -- the rules a pasted table breaks that the harness could not see
# ---------------------------------------------------------------------------
def _shape(render: Callable[[list[SpecRow]], str], name: str) -> DescriptionTemplate:
    """A template around one ``render``, reading back the way ``spec_table`` does."""
    return DescriptionTemplate(
        name=name,
        render=render,
        extract=SPEC_TABLE.extract,
        starts_with="<table",
        ends_with="</table>",
    )


def _is_warranty(row: SpecRow) -> bool:
    """The boldness a conforming shape owes its rows: whatever the row says."""
    return row.is_warranty


def _table_of(
    rows: list[SpecRow],
    bold: Callable[[SpecRow], bool],
    escape=_plain_escape,
    join: str = "",
) -> str:
    """``spec_table``'s shape with boldness, escaping and row padding left to the caller.

    The three knobs a hand-pasted listing varies on its own: which cells it bolds,
    whether it escapes the text it interpolates, and what it puts between the rows.
    """
    body = join.join(
        VALID_ROW.format(
            label=_cell_of(row.label, bold(row), escape),
            value=_cell_of(row.value, bold(row), escape),
        )
        for row in rows
    )
    return f"<table>{VALID_HEAD}<tbody>{body}</tbody></table>"


def test_a_shape_that_interpolates_values_raw_is_refused() -> None:
    """Requirement: a cell ships markup the browser can parse, not the value's own.

    ``spec_table`` escapes each row (``html.escape(value, quote=False)``), so a sheet
    that says ``Steel <b>1 mm</b> & "X"`` arrives as text.  A pasted listing that
    drops the escaping sends the same characters as tags and entities, and the gates
    then count a table that has nothing to do with the specification.
    """
    raw = _shape(lambda rows: _table_of(rows, _is_warranty, escape=str), "raw")
    problems = template_problems(raw)
    assert any("escape" in p.lower() for p in problems), problems
    assert any("&" in p for p in problems), problems
    with pytest.raises(ValueError):
        assert_template_conforms(raw)


def test_a_shape_that_escapes_quotes_too_is_still_accepted() -> None:
    """`&quot;` and `&#x27;` are legal entities: the ampersand rule must not bite them."""
    quoted = _shape(
        lambda rows: _table_of(rows, _is_warranty, escape=_escaper(quotes=True)), "quoted"
    )
    assert template_problems(quoted) == []


def _escaper(entity: str | None = None, quotes: bool = False):
    """An escaping choice for a probe shape, spelling its ampersand ``entity``.

    ``entity`` replaces the ``&amp;`` that ``html.escape`` writes for every `&` in the
    shop's data, which is how a hand-pasted table gets an entity subtly wrong -- and a
    wrong one is the case the round-trip alone cannot see.
    """

    def escape(text: str) -> str:
        written = html.escape(text) if quotes else html.escape(text, quote=False)
        return written if entity is None else written.replace("&amp;", entity)

    return escape


LEGAL_ENTITIES = [
    pytest.param(_escaper(), id="named-&amp;"),
    pytest.param(_escaper("&#38;"), id="decimal"),
    pytest.param(_escaper("&#x26;"), id="hexadecimal"),
    pytest.param(_escaper(quotes=True), id="with-quotes"),
]
BROKEN_ENTITIES = [
    pytest.param(_escaper("&amp"), id="named-without-semicolon"),
    pytest.param(_escaper("&#38"), id="decimal-without-semicolon"),
    pytest.param(_escaper("&"), id="nothing-at-all"),
]


@pytest.mark.parametrize("escape", LEGAL_ENTITIES)
def test_an_entity_a_browser_reads_is_not_an_unescaped_ampersand(
    escape: Callable[[str], str],
) -> None:
    """`&amp;`, `&#38;`, `&#x26;`, `&quot;`, `&#x27;` are all legal spellings of the shop's `&`."""
    shape = _shape(lambda rows: _table_of(rows, _is_warranty, escape=escape), "entity")
    assert template_problems(shape) == []


@pytest.mark.parametrize("escape", BROKEN_ENTITIES)
def test_an_entity_the_browser_cannot_read_is_refused(
    escape: Callable[[str], str],
) -> None:
    """A missing semicolon (or no escaping at all) ships an ampersand the file cannot mean."""
    shape = _shape(lambda rows: _table_of(rows, _is_warranty, escape=escape), "half-entity")
    problems = template_problems(shape)
    assert any("ampersand" in p for p in problems), problems


def test_a_structural_entity_in_the_skeleton_is_accepted() -> None:
    """The shape's own `&nbsp;` between rows is not the shop's text, and not a defect.

    Two rules could mistake it for one: the ampersand scan (it is a valid entity) and
    the leaked-markup scan (it is in every render the shape makes, padded or not).
    """
    padded = _shape(
        lambda rows: _table_of(rows, _is_warranty, join="&nbsp;"), "nbsp_padded"
    )
    assert template_problems(padded) == []


@pytest.mark.parametrize("entity", ["&nbsp;", "&copy;", "&deg;", "&mdash;"])
def test_a_standard_name_the_browser_decodes_is_accepted_in_that_position(
    entity: str,
) -> None:
    """Names straight from the HTML5 table stay legal, in the shape's own markup."""
    padded = _shape(
        lambda rows: _table_of(rows, _is_warranty, join=entity), f"padded_{entity[1:-1]}"
    )
    assert template_problems(padded) == []


def test_an_entity_no_browser_has_a_name_for_is_refused() -> None:
    """`&bogus;` is the shape of an entity and not the thing itself.

    Syntactically the ampersand rule has to wave it through -- it is followed by a
    name and a semicolon -- but the HTML5 table has no such entry, so `html.unescape`
    leaves all eight characters alone and the listing prints `&bogus;` to the customer.
    In a structural position (here, between the rows) no cell reads it back either, so
    the round-trip cannot see it: this rule is the only one that can.
    """
    padded = _shape(
        lambda rows: _table_of(rows, _is_warranty, join="&bogus;"), "bogus_padded"
    )
    problems = template_problems(padded)
    assert any("&bogus;" in p and "entity" in p.lower() for p in problems), problems
    with pytest.raises(ValueError):
        assert_template_conforms(padded)


def test_a_data_ampersand_spelled_as_an_unknown_name_is_refused_too() -> None:
    """The same mistake in the shop's own text, where the round-trip also objects."""
    unknown = _shape(
        lambda rows: _table_of(rows, _is_warranty, escape=_escaper("&bogus;")), "bogus_data"
    )
    assert any("&bogus;" in p for p in template_problems(unknown))


def _keep_strong(text: str) -> str:
    """Escape as `spec_table` does, then let the shop's own `<strong>` back through.

    This is the mistake a copied listing makes most: the writer keeps the emphasis it
    can see in the page source.  The name is in the shape's own vocabulary, so only a
    count of it can object -- which is what the differential is.
    """
    written = html.escape(text, quote=False)
    return written.replace("&lt;strong&gt;", "<strong>").replace("&lt;/strong&gt;", "</strong>")


def test_a_duplicate_of_a_tag_the_shape_itself_writes_is_refused() -> None:
    """A duplicated tag is refused by its count, not by whether the name is new.

    `Matte <td>brushed</td> steel` gives a row three cells where the plain-value row has
    two, and the harness says so in counts (3 written, not 2).  The sharper case is
    :func:`test_a_value_that_bolds_itself_inside_a_bold_row_is_refused`, where the
    injected spelling is one the shape writes itself and no name comparison can see it.
    """
    raw = _shape(lambda rows: _table_of(rows, _is_warranty, escape=str), "raw_cell")
    problems = template_problems(raw)
    assert any("<td>" in p for p in problems), problems


def test_a_value_that_bolds_itself_inside_a_bold_row_is_refused() -> None:
    """A shape that lets the shop's `<strong>` through, in a row that is already bold.

    The name is in the shape's own vocabulary and the row keeps its two cells, so a
    comparison of *which* tags appear sees nothing; the count is what objects.  This is
    the mistake a listing copied out of a page source makes -- the writer keeps the
    emphasis it can see and escapes the rest.
    """
    kept = _shape(lambda rows: _table_of(rows, _is_warranty, escape=_keep_strong), "strong_kept")
    problems = template_problems(kept)
    assert any("<strong>" in p for p in problems), problems


def test_a_shape_that_escapes_values_but_not_labels_is_refused() -> None:
    """Half an escaping rule is no escaping rule: the label is interpolated too.

    A pasted skeleton often runs the value through a helper and drops the label
    straight into the row -- or into an attribute, where it sits outside every cell and
    so is invisible to ``extract``.  The probe therefore carries markup in a label as
    well as in a value.
    """

    def cell(text: str, bold: bool, escape_text: bool) -> str:
        written = _plain_escape(text) if escape_text else text
        return f"<strong>{written}</strong>" if bold else written

    def render(rows: list[SpecRow]) -> str:
        body = "".join(
            VALID_ROW.format(
                label=cell(row.label, row.is_warranty, escape_text=False),
                value=cell(row.value, row.is_warranty, escape_text=True),
            )
            for row in rows
        )
        return f"<table>{VALID_HEAD}<tbody>{body}</tbody></table>"

    problems = template_problems(_shape(render, "label_raw"))
    assert any("<b>" in p for p in problems), problems


def test_an_unterminated_tag_is_reported_as_the_cell_it_ate() -> None:
    """The other direction of the same mistake: the shop's text swallows the shape's tag.

    A value ending in a bare `<b` has no closing `>`, so the table's own `</td>` is read
    as part of it -- one fewer of the shape's tags ships than the plain-value row
    writes, and the row loses the cell that closed it.
    """
    open_tag = _shape(
        lambda rows: _table_of([row for row in rows if row.label == "Notes"], _is_warranty,
                               escape=str),
        "open_tag_only",
    )
    problems = template_problems(open_tag)
    assert any("</td>" in p and "loses the shape" in p for p in problems), problems


def test_the_markup_probe_ships_the_tags_a_shape_already_uses() -> None:
    """The probe rows have to try the injections that a set of names cannot see.

    A value holding only a `<b>` is caught by any comparison; a value holding `<td>`
    or `<strong>` -- tags a conforming table writes itself -- is the one that proves
    the harness compares structure and not vocabulary.  The bold case has to sit in a
    bold row, or an injected `<strong>` would be a new name and prove nothing.
    """
    vocabulary = set(_TAG_RE.findall(_table_of(list(_PROBE_STANDIN), _is_warranty)))
    injected = {
        tag for row in ESCAPE_PROBE for tag in _TAG_RE.findall(f"{row.label} {row.value}".lower())
    }
    assert injected & vocabulary, (sorted(injected), sorted(vocabulary))
    assert any(row.is_warranty and "<strong>" in row.value.lower() for row in ESCAPE_PROBE), (
        "no bold probe row carries markup, so injected `<strong>` is a new name here"
    )
    assert any("<" in row.label for row in ESCAPE_PROBE), (
        "every probe label is plain, so a shape that escapes values and not labels passes"
    )


def test_the_sample_harness_bold_matches_what_the_shop_ships() -> None:
    """The rows the bold rule is tried on have to look like real listings.

    A warranty statement is most often a component (`Compressor`, `Parts`, `PCB`), so
    the sample holds two bold rows, one of them named for a part and one of them
    followed by a plain row.  Without both, a shape that bolds by the word `Warranty`
    or by position passes the harness and ships a Description the gate reads as plain.
    """
    bold = [index for index, row in enumerate(CONFORMANCE_ROWS) if row.is_warranty]
    assert len(bold) >= 2, "one bold row proves nothing about where bold comes from"
    assert any("warranty" not in CONFORMANCE_ROWS[i].label.lower() for i in bold), (
        "every bold row is named Warranty, so a template that keys on that word passes"
    )
    assert any(not row.is_warranty for row in CONFORMANCE_ROWS[bold[0] + 1 :]), (
        "no plain row follows the first bold one, so a template that bolds a trailing "
        "run of the table passes"
    )


def test_a_shape_that_bolds_by_the_word_warranty_is_refused() -> None:
    """The concrete failure the single-warranty sample hid."""
    by_word = _shape(
        lambda rows: _table_of(rows, lambda row: row.label == "Warranty"),
        "warranty_word_only",
    )
    problems = template_problems(by_word)
    assert any("warrant" in p.lower() for p in problems), problems


def test_a_round_trip_failure_names_the_field_that_differs() -> None:
    """Say which row and which field went missing -- not the same label list twice.

    The first version of this message printed `wrote [...]` and `read back [...]`,
    which are identical when the damage is inside a value or in its boldness, so the
    operator was handed a diff of the same thing twice.
    """
    loses_bold = DescriptionTemplate(
        name="flattened",
        render=SPEC_TABLE.render,
        extract=lambda text: [
            dataclasses.replace(row, is_warranty=False) for row in SPEC_TABLE.extract(text)
        ],
        starts_with="<table",
        ends_with="</table>",
    )
    bold_line = next(p for p in template_problems(loses_bold) if "extract" in p.lower())
    assert "row" in bold_line and "bold" in bold_line.lower(), bold_line
    assert "[]" not in bold_line, bold_line

    loses_value = DescriptionTemplate(
        name="valueless",
        render=SPEC_TABLE.render,
        extract=lambda text: [
            dataclasses.replace(row, value="") for row in SPEC_TABLE.extract(text)
        ],
        starts_with="<table",
        ends_with="</table>",
    )
    value_line = next(p for p in template_problems(loses_value) if "extract" in p.lower())
    assert "value" in value_line and "row" in value_line, value_line


# ---------------------------------------------------------------------------
# Task 10 review, part 2 -- the structure a tag count cannot see
# ---------------------------------------------------------------------------
def _reader_of_what_it_wrote(text: str) -> list[SpecRow]:
    """The reader a crossed writer would ship: rows on ``<tr``, cells on ``<td``.

    It reads a malformed table back whole, which is precisely why the round-trip rule is
    not the check that has to object.  The rows are still two cells and the words are all
    there -- only the tree is wrong, and the tree is what the browser builds.
    """
    rows: list[SpecRow] = []
    for chunk in re.findall(r"<tr\b.*?(?=<tr\b|</tbody>)", text, re.DOTALL):
        cells = [
            html.unescape(_TAG_RE.sub("", cell)).strip()
            for cell in re.split(r"<td\b[^>]*>", chunk)[1:]
        ]
        cells = [cell for cell in cells if cell]
        header = [
            html.unescape(_TAG_RE.sub("", cell)).strip()
            for cell in re.split(r"<th\b[^>]*>", chunk)[1:]
        ]
        if len(header) == 2 and not cells:
            continue
        if len(cells) == 2:
            rows.append(SpecRow(cells[0], cells[1], "<strong" in chunk))
    return rows


def _moved(rows: list[SpecRow], old: str, new: str) -> str:
    """``spec_table``'s own fragment with ONE closing tag relocated -- tags untouched."""
    return _table_of(rows, _is_warranty).replace(old, new, 1)


def test_a_row_closed_before_its_cell_is_refused() -> None:
    """Same tags, same counts, same rows -- and a browser that cannot build the table.

    This is the case a ``Counter`` cannot see: ``</td></tr>`` written as ``</tr></td>``
    moves no tag in or out, so every count agrees with the well-formed table, and the
    shape's own reader gets all six rows back.  The browser closes the cell at the
    ``</tr>`` and drops the tag after it, and ``audit.py`` (:494) then finds one cell in
    that row and skips it -- a spec row that stops being checked.
    """
    well_formed = _table_of(list(CONFORMANCE_ROWS), _is_warranty)
    crossed = _moved(CONFORMANCE_ROWS, "</td></tr>", "</tr></td>")
    assert Counter(_TAG_RE.findall(crossed)) == Counter(_TAG_RE.findall(well_formed))
    shape = DescriptionTemplate(
        name="crossed_row",
        render=lambda rows: _moved(rows, "</td></tr>", "</tr></td>"),
        extract=_reader_of_what_it_wrote,
        starts_with="<table",
        ends_with="</table>",
    )
    assert _reader_of_what_it_wrote(shape.render(list(CONFORMANCE_ROWS))) == CONFORMANCE_ROWS
    problems = template_problems(shape)
    assert len(problems) == 1, problems
    assert "</tr> written while <td> is still open" in problems[0], problems


def test_a_bold_row_that_leaks_into_the_next_one_is_refused() -> None:
    """The crossing the customer actually sees: bold that walks past the warranty row.

    One ``</strong>`` moved from the warranty cell into the row after it keeps every tag
    count identical.  The browser keeps the ``<strong>`` open across the boundary, so the
    next specification renders bold -- and bold is how the gate spots a warranty, so that
    plain row is read as one the shop has to prove.
    """
    shape = DescriptionTemplate(
        name="crossed_bold",
        render=lambda rows: _moved(
            rows, "</strong></td></tr><tr><td style=\"c\">", "</td></tr><tr><td style=\"c\"></strong>"
        ),
        extract=_reader_of_what_it_wrote,
        starts_with="<table",
        ends_with="</table>",
    )
    well_formed = _table_of(list(CONFORMANCE_ROWS), _is_warranty)
    assert Counter(_TAG_RE.findall(shape.render(list(CONFORMANCE_ROWS)))) == Counter(
        _TAG_RE.findall(well_formed)
    )
    problems = template_problems(shape)
    assert any("while <strong> is still open" in p for p in problems), problems


def test_the_nesting_rule_leaves_a_well_formed_table_alone() -> None:
    """The must-not-refuse half: the shop's own table, and its own spacing, are clean."""
    assert _nesting_problems(_table_of(list(CONFORMANCE_ROWS), _is_warranty)) == []
    assert template_problems(SPEC_TABLE) == []


def test_a_void_element_is_not_read_as_an_unclosed_tag() -> None:
    """``<br>`` between two spec lines is a shape's own business, not a crossing.

    The stack has to know HTML5's void elements or every spaced-out listing would be
    refused for a tag that never takes a closing partner.
    """
    braced = _table_of(list(CONFORMANCE_ROWS), _is_warranty).replace("</td></tr>", "<br></td></tr>", 1)
    assert _nesting_problems(braced) == []
    assert _nesting_problems("<table><tr><td/></tr></table>") == [
        "a self-closed <td/> writes no cell the gate can fill"
    ]
    assert any("never closed" in p for p in _nesting_problems("<table><tr><td>a</td>"))


def test_a_table_crossed_in_every_row_is_reported_once_not_tag_by_tag() -> None:
    """The terminal gets the shape of the mistake, not a line per tag after it.

    Five rows written ``</tr></td>`` break the walk ten-odd times over.  Two named lines
    plus a count is what an operator can act on -- the same reason the diagnostics name a
    row instead of dumping the table.
    """
    problems = _nesting_problems("<table>" + "<tr><td>a</tr></td>" * 5 + "</table>")
    assert len(problems) == 3, problems
    assert "more tags closed out of order" in problems[2], problems


def test_an_attribute_on_the_bold_tag_is_refused() -> None:
    """``<strong class="w">`` is bold to a browser and plain to the gate.

    The gate reads bold as the literal text (``audit.py`` :408 and :496), exactly like it
    reads a row as a literal ``<tr>`` -- so a shape that styles its own bold tag stops
    telling the platform which line is the warranty, and no count of the tags says so.
    """

    def bold_attr(text: str, bold: bool) -> str:
        return f'<strong class="w">{text}</strong>' if bold else text

    def render(rows: list[SpecRow]) -> str:
        body = "".join(
            VALID_ROW.format(
                label=bold_attr(_plain_escape(row.label), row.is_warranty),
                value=bold_attr(_plain_escape(row.value), row.is_warranty),
            )
            for row in rows
        )
        return f"<table>{VALID_HEAD}<tbody>{body}</tbody></table>"

    def read(text: str) -> list[SpecRow]:
        return SPEC_TABLE.extract(re.sub(r"<strong\b[^>]*>", "<strong>", text))

    stiff = DescriptionTemplate(
        name="bold_attr",
        render=render,
        extract=read,
        starts_with="<table",
        ends_with="</table>",
    )
    assert read(stiff.render(list(CONFORMANCE_ROWS))) == CONFORMANCE_ROWS
    problems = template_problems(stiff)
    # 4 `<strong class="w">` opened, 4 plain `</strong>` closed: 0 of the exact opening text.
    assert any("literal text" in p and "0/4" in p for p in problems), problems


# ---------------------------------------------------------------------------
# Task 10 review, part 2 -- where the shop's text may sit, and what may name a character
# ---------------------------------------------------------------------------
def test_shop_text_reaching_an_attribute_is_refused() -> None:
    """A correctly escaped value is still a defect one position to the left.

    ``title="{value}"`` with ``html.escape(text, quote=False)`` -- the convention this
    repository documents -- escapes ``&`` and ``<`` perfectly and leaves the ``"`` to end
    the attribute, and nothing in the cell changes, so no round-trip can notice.  The
    differential does: the probe's tag and its plain twin's tag are different strings.
    """

    def render(rows: list[SpecRow]) -> str:
        body = "".join(
            f'<tr><td style="c" title="{_plain_escape(row.label)}">'
            f'{_cell_of(row.label, row.is_warranty)}</td>'
            f'<td style="c" title="{_plain_escape(row.value)}">'
            f'{_cell_of(row.value, row.is_warranty)}</td></tr>'
            for row in rows
        )
        return f"<table>{VALID_HEAD}<tbody>{body}</tbody></table>"

    problems = template_problems(_shape(render, "titled"))
    assert any("title=" in p for p in problems), problems
    assert any("ships the shop's own text as markup" in p for p in problems), problems


@pytest.mark.parametrize("name", sorted(DESCRIPTION_TEMPLATES))
def test_every_registered_template_interpolates_only_into_text_nodes(name: str) -> None:
    """The constraint the harness enforces, shown on the templates that actually ship.

    Not one word of a specification reaches a tag: every label and value in the sample
    appears in the cell's text and in no tag spelling.  A template that ever starts
    putting them in an attribute will fail here, and the README says why it must not.
    """
    cell = clean_inline(DESCRIPTION_TEMPLATES[name].render(list(CONFORMANCE_ROWS)))
    tags = "".join(_TAG_RE.findall(cell))
    for row in CONFORMANCE_ROWS:
        assert row.label not in tags, (name, row.label, tags[:120])
        assert row.value not in tags, (name, row.value, tags[:120])


UNPRINTABLE_REFERENCES = [
    pytest.param("&#999999999;", id="past-the-unicode-range"),
    pytest.param("&#0;", id="zero"),
    pytest.param("&#x110000;", id="hex-past-the-range"),
    pytest.param("&#xD800;", id="a-surrogate"),
    pytest.param("&#27;", id="an-escape-code"),
    pytest.param("&#65534;", id="a-noncharacter"),
    pytest.param("&#9;", id="a-tab"),
]
PRINTABLE_REFERENCES = [
    pytest.param("&#38;", id="decimal-ampersand"),
    pytest.param("&#x26;", id="hex-ampersand"),
    pytest.param("&#233;", id="latin-e-acute"),
    pytest.param("&#x1F600;", id="an-emoji"),
]


@pytest.mark.parametrize("reference", UNPRINTABLE_REFERENCES)
def test_a_numeric_reference_with_no_character_behind_it_is_refused(reference: str) -> None:
    """``&#999999999;`` passes the ampersand rule and prints the replacement glyph.

    Measured: :func:`html.unescape` answers it (and ``&#0;``, ``&#xD800;``, ``&#65534;``)
    with U+FFFD, and ``&#27;`` and ``&#9;`` with a control code or nothing -- so the shop's
    specification ships a box of pixels, or loses a character silently.  The number has to
    name a printable character or the cell is refused before anything is written.
    """
    padded = _shape(
        lambda rows: _table_of(rows, _is_warranty, join=reference), f"pad_{reference[2:-1]}"
    )
    problems = template_problems(padded)
    assert any(reference in p and "numeric reference" in p for p in problems), problems
    with pytest.raises(ValueError):
        assert_template_conforms(padded)


@pytest.mark.parametrize("reference", PRINTABLE_REFERENCES)
def test_a_numeric_reference_that_names_a_character_is_accepted(reference: str) -> None:
    """Not a ban on numeric spelling -- decimal and hex, accents and emoji all ship."""
    padded = _shape(
        lambda rows: _table_of(rows, _is_warranty, join=reference), f"pad_{reference[2:-1]}"
    )
    problems = template_problems(padded)
    assert not any("numeric reference" in p for p in problems), problems


# ---------------------------------------------------------------------------
# Task 4 -- the Description is rendered at projection, from this cell's template
# ---------------------------------------------------------------------------
def _plain_two_column_table(rows: list[SpecRow]) -> str:
    """A second conforming shape: no header, no inline styles."""
    body = "".join(
        "<tr>"
        f"<td>{'<strong>' if row.is_warranty else ''}{html.escape(row.label, quote=False)}"
        f"{'</strong>' if row.is_warranty else ''}</td>"
        f"<td>{'<strong>' if row.is_warranty else ''}{html.escape(row.value, quote=False)}"
        f"{'</strong>' if row.is_warranty else ''}</td>"
        "</tr>"
        for row in rows
    )
    return f"<table><tbody>{body}</tbody></table>"


PLAIN_TABLE = DescriptionTemplate(
    name="plain_table",
    render=_plain_two_column_table,
    extract=lambda text: extract_spec_rows(
        text, starts_with="<table", ends_with="</table>"
    ),
    starts_with="<table",
    ends_with="</table>",
)

#: Indented the way a hand-pasted listing usually is, one line per row.
SPACED_ROW = '<tr><td style="c">{label}</td><td style="c">{value}</td></tr>'


def _pretty(rows: list[SpecRow]) -> str:
    """One row per line -- legal, because each break leaves exactly one space."""
    body = "".join(
        "\n  " + SPACED_ROW.format(
            label=_cell_of(r.label, r.is_warranty),
            value=_cell_of(r.value, r.is_warranty),
        )
        for r in rows
    )
    return f"{TABLE_HEAD}{body}\n{TABLE_TAIL}"


PRETTY_TABLE = DescriptionTemplate(
    name="pretty_table",
    render=_pretty,
    extract=SPEC_TABLE.extract,
    starts_with="<table",
    ends_with="</table>",
)


def test_a_second_shape_passes_the_same_harness() -> None:
    """Two real alternatives prove the harness is not spec_table in disguise."""
    assert template_problems(PLAIN_TABLE) == []
    assert template_problems(PRETTY_TABLE) == []


def test_a_skeleton_indented_between_its_block_tags_is_refused() -> None:
    """Stripped of tags, `<thead>\\n <tr>\\n <th` leaves runs of spaces the gate bans.

    This is not pedantry: it is `audit.py`'s own rule, so a pasted listing whose table
    tag, header and body each sit on their own line cannot ship until that gate is
    made template-aware.
    """
    indented = _probe(
        VALID_ROW,
        head='<thead>\n  <tr><th style="c">Specification</th>'
        '<th style="c">Details</th></tr>\n</thead>\n',
    )
    assert any("double space" in p for p in template_problems(indented))


def test_the_bundle_stores_rows_not_a_rendered_string() -> None:
    """One derivation, many projections: nothing may cache the chosen shape."""
    names = {f.name for f in dataclasses.fields(DescriptionBundle)}
    assert "description_html" not in names
    assert "spec_rows" in names


def test_the_file_cell_is_this_cells_template_over_the_records_rows(
    pipeline: Pipeline,
) -> None:
    result = pipeline([PROVEN_ROW])
    for row, record in zip(result["digi"], result["records"], strict=True):
        assert row["Description"] == clean_inline(
            SPEC_TABLE.render(record.description.spec_rows)
        )
    for row, record in zip(result["alfa"], result["records"], strict=True):
        assert row["Description"] == clean_inline(
            SPEC_TABLE.render(record.description.spec_rows)
        )


def test_a_cell_can_ship_a_different_shape_than_its_sibling(
    pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner's rule, smallest version: alfa's cell changes, digi's does not."""
    result = pipeline([PROVEN_ROW])
    cfg = dataclasses.replace(
        KIACHAHIYE,
        alfa=dataclasses.replace(KIACHAHIYE.alfa, description_template="plain_table"),
    )
    monkeypatch.setitem(DESCRIPTION_TEMPLATES, PLAIN_TABLE.name, PLAIN_TABLE)

    digi = [build_digi_row(r, cfg).values["Description"] for r in result["records"]]
    alfa = [build_alfa_row(r, cfg).values["Description"] for r in result["records"]]

    assert digi == [
        clean_inline(SPEC_TABLE.render(r.description.spec_rows))
        for r in result["records"]
    ]
    assert alfa == [
        clean_inline(PLAIN_TABLE.render(r.description.spec_rows))
        for r in result["records"]
    ]
    assert alfa != digi


def test_a_pretty_printed_template_still_ships_one_flat_line(
    pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The trap audit.py sets: a template may be indented, its cell may not be."""
    result = pipeline([PROVEN_ROW])
    cfg = dataclasses.replace(
        KIACHAHIYE,
        alfa=dataclasses.replace(KIACHAHIYE.alfa, description_template="pretty_table"),
    )
    monkeypatch.setitem(DESCRIPTION_TEMPLATES, PRETTY_TABLE.name, PRETTY_TABLE)

    for record in result["records"]:
        cell = build_alfa_row(record, cfg).values["Description"]
        assert len(cell.splitlines()) == 1
        assert "  " not in re.sub(r"<[^>]+>", "", cell)
        assert cell.startswith("<table") and cell.endswith("</table>")
        assert SPEC_TABLE.extract(cell) == record.description.spec_rows


def test_no_vendor_config_falls_back_to_the_shops_own_table(
    pipeline: Pipeline,
) -> None:
    """The fixture path (and any caller without a store) keeps today's bytes."""
    result = pipeline([PROVEN_ROW])
    for row in result["digi"] + result["alfa"]:
        assert row["Description"].startswith(
            '<table style="width:100%;border-collapse:collapse'
        )


# ---------------------------------------------------------------------------
# Task 7 -- the two readers that count the BUILT file, not the record
# ---------------------------------------------------------------------------
# `audit.py`'s evidence column and `thin_report.py`'s worklist grade the finished CSV, and both
# were written while every cell shipped spec_table, so they count that shape: audit subtracts the
# one `<th>` header row it expects (`count("<tr") - 1`), thin_report matches the literal `<tr><td`
# (`thin_report._SPEC_ROW_RE`).  The conformance harness above already refuses most drift, because
# it mirrors those two spellings -- which is why this is a WATCH and not a fix: `audit.py` is
# off-limits in this change, so a template the harness happens to tolerate while these counters
# stumble over it has to be caught here, in words that say the real upgrade is to make those
# readers template-aware.
def _cell_as_uploaded(template: DescriptionTemplate, rows: list[SpecRow]) -> str:
    """The exact string a Description cell holds in the CSV -- same composition as writers."""
    return _single_line(clean_inline(template.render(list(rows))))


def _counter_drift(template: DescriptionTemplate, rows: list[SpecRow]) -> list[str]:
    """Where the two file readers stop reporting the number of rows this template actually wrote."""
    cell = _cell_as_uploaded(template, rows)
    drift: list[str] = []
    counters = (
        ("audit.py's evidence column", 'count("<tr") - 1', cell.count("<tr") - 1),
        ("thin_report.py's worklist", "findall(_SPEC_ROW_RE)", len(thin_report._SPEC_ROW_RE.findall(cell))),
    )
    for name, counting, got in counters:
        if got != len(rows):
            drift.append(
                f"{name} reports {got} spec rows where {template.name} wrote {len(rows)} "
                f"({counting}) -- make that reader template-aware (or give the template the "
                "single <th> header row and the literal <tr><td shape it assumes) before "
                "registering it on a cell"
            )
    try:
        own = len(template.extract(cell))
    except TemplateShapeError as error:
        own = -1
        drift.append(f"{template.name}.extract refuses its own render: {error}")
    if own != len(rows):
        drift.append(f"{template.name}.extract counts {own}, not {len(rows)}")
    return drift


@pytest.mark.parametrize(
    "rows", [PLAIN, WITH_NOISE, CONFORMANCE_ROWS], ids=["plain", "noise", "conformance"]
)
def test_every_registered_template_still_tells_both_counters_the_row_count(
    rows: list[SpecRow],
) -> None:
    """The registry is the promise a cell may make; this is the part of it the gates check by hand."""
    for template in DESCRIPTION_TEMPLATES.values():
        drift = _counter_drift(template, rows)
        assert drift == [], "; ".join(drift)


def test_an_indented_shape_with_a_header_row_still_counts_right() -> None:
    """`pretty_table` breaks no rule the counters use, so it must raise no watch here either."""
    assert _counter_drift(PRETTY_TABLE, CONFORMANCE_ROWS) == []


def test_the_watch_catches_the_one_drift_the_harness_cannot_see() -> None:
    """`plain_table` passes every startup rule -- and still makes audit's evidence one row short.

    This is the hole the deferred audit upgrade has to close: the harness reads labels and tags,
    never the header-row arithmetic `audit.py` does.  So the day a header-less shape is registered,
    this test -- not the gate -- is what tells him his evidence sheet is lying.
    """
    assert template_problems(PLAIN_TABLE) == [], "the harness is what this drift hides behind"
    drift = _counter_drift(PLAIN_TABLE, CONFORMANCE_ROWS)
    assert any("audit.py" in problem for problem in drift), drift
    assert not any("thin_report.py" in problem for problem in drift), (
        f"plain_table keeps the <tr><td shape thin_report counts: {drift}"
    )


def test_kiachahiye_alfa_card_conforms() -> None:
    """The Kiachahiye.alfa card passes the full startup conformance and escaping harness."""
    assert KIACHAHIYE_ALFA_CARD.name == "kiachahiye_alfa_card"
    assert template_for("kiachahiye_alfa_card") is KIACHAHIYE_ALFA_CARD
    assert template_problems(KIACHAHIYE_ALFA_CARD) == []
    assert_template_conforms(KIACHAHIYE_ALFA_CARD)


def test_kiachahiye_alfa_card_round_trip_covers_every_real_row(
    real_spec_rows: list[list[SpecRow]],
) -> None:
    """Every product row in the real sheets round-trips losslessly through the card."""
    assert len(real_spec_rows) > 500
    for rows in real_spec_rows:
        rendered = KIACHAHIYE_ALFA_CARD.render(rows)
        assert KIACHAHIYE_ALFA_CARD.extract(rendered) == rows
        assert KIACHAHIYE_ALFA_CARD.extract(clean_inline(rendered)) == rows


def test_kiachahiye_alfa_card_dynamic_model_badges_and_warranty_rows() -> None:
    """Model badge, static caption badges, alternating stripes, and 0/1/multi warranty rows."""
    no_warranty = [
        SpecRow("Brand", "Gree"),
        SpecRow("Model", "GS-18PITH11W"),
        SpecRow("Capacity", "1.5 Ton"),
        SpecRow("Color", "White"),
    ]
    html_no_w = KIACHAHIYE_ALFA_CARD.render(no_warranty)
    assert "100% Genuine Pin-Packed" in html_no_w
    assert "Delivery All Over Pakistan" in html_no_w
    assert "After Sales Service" in html_no_w
    assert (
        '<span style="background:rgba(91,20,155,0.08);color:#5b149b;'
        'padding:2px 8px;border-radius:4px;font-weight:bold;">GS-18PITH11W</span>'
    ) in html_no_w
    assert "<strong>" not in html_no_w
    assert "\u2605" not in html_no_w
    assert KIACHAHIYE_ALFA_CARD.extract(html_no_w) == no_warranty

    multi_warranty = [
        *no_warranty,
        SpecRow("Compressor Warranty", "10 Years", is_warranty=True),
        SpecRow("Parts Warranty", "1 Year", is_warranty=True),
    ]
    html_multi = KIACHAHIYE_ALFA_CARD.render(multi_warranty)
    assert html_multi.count("\u2605") == 2
    assert html_multi.count("<strong>") == 4
    assert "<strong>Compressor Warranty</strong>" in html_multi
    assert "<strong>Parts Warranty</strong>" in html_multi
    assert KIACHAHIYE_ALFA_CARD.extract(html_multi) == multi_warranty


def test_kiachahiye_alfa_card_warranty_star_style_resilience() -> None:
    """Warranty star extraction is resilient to style reordering, whitespace, extra attributes, and entities."""
    base_rows = [
        SpecRow("Brand", "Haier"),
        SpecRow("Compressor Warranty", "10 Years", is_warranty=True),
    ]
    standard_html = KIACHAHIYE_ALFA_CARD.render(base_rows)

    # Harmless variation 1: reversed style properties and extra whitespace
    alt_style = standard_html.replace(
        '<span style="color:#d72314;margin-right:4px;">\u2605</span> ',
        '<span style="margin-right: 4px; color: #d72314;">  \u2605  </span>  ',
    )
    assert KIACHAHIYE_ALFA_CARD.extract(alt_style) == base_rows

    # Harmless variation 2: extra attributes and attribute ordering
    alt_attrs = standard_html.replace(
        '<span style="color:#d72314;margin-right:4px;">\u2605</span> ',
        '<span class="warranty-star" aria-hidden="true" style="color:#d72314;margin-right:4px;">\u2605</span> ',
    )
    assert KIACHAHIYE_ALFA_CARD.extract(alt_attrs) == base_rows

    # Harmless variation 3: single quotes in attributes
    alt_quotes = standard_html.replace(
        '<span style="color:#d72314;margin-right:4px;">\u2605</span> ',
        "<span style='color:#d72314;margin-right:4px;'>\u2605</span> ",
    )
    assert KIACHAHIYE_ALFA_CARD.extract(alt_quotes) == base_rows

    # Harmless variation 4: HTML entity &#9733; for star
    alt_entity = standard_html.replace(
        '<span style="color:#d72314;margin-right:4px;">\u2605</span> ',
        '<span style="color:#d72314;margin-right:4px;">&#9733;</span> ',
    )
    assert KIACHAHIYE_ALFA_CARD.extract(alt_entity) == base_rows


def test_kiachahiye_alfa_card_rejects_missing_and_malformed_warranty_stars() -> None:
    """Malformed, missing, or ambiguous star markup is safely rejected with TemplateShapeError."""
    base_rows = [
        SpecRow("Brand", "Haier"),
        SpecRow("Compressor Warranty", "10 Years", is_warranty=True),
    ]
    standard_html = KIACHAHIYE_ALFA_CARD.render(base_rows)

    # 1. Missing star on warranty row
    missing_star = standard_html.replace(
        '<span style="color:#d72314;margin-right:4px;">\u2605</span> ', ""
    )
    with pytest.raises(TemplateShapeError, match="missing the required warranty star badge"):
        KIACHAHIYE_ALFA_CARD.extract(missing_star)

    # 2. Bare star without span element
    bare_star = standard_html.replace(
        '<span style="color:#d72314;margin-right:4px;">\u2605</span> ', "\u2605 "
    )
    with pytest.raises(TemplateShapeError, match="malformed warranty star markup"):
        KIACHAHIYE_ALFA_CARD.extract(bare_star)

    # 3. Unclosed star span element
    unclosed_star = standard_html.replace(
        '<span style="color:#d72314;margin-right:4px;">\u2605</span> ',
        '<span style="color:#d72314;margin-right:4px;">\u2605 ',
    )
    with pytest.raises(TemplateShapeError, match="malformed warranty star markup"):
        KIACHAHIYE_ALFA_CARD.extract(unclosed_star)

    # 4. Ambiguous multiple star badges
    double_star = (
        '<span style="color:#d72314;margin-right:4px;">\u2605</span> '
        '<span style="color:#d72314;margin-right:4px;">\u2605</span> '
    )
    multi_star = standard_html.replace(
        '<span style="color:#d72314;margin-right:4px;">\u2605</span> ',
        double_star,
    )
    with pytest.raises(TemplateShapeError, match="ambiguous multiple warranty stars"):
        KIACHAHIYE_ALFA_CARD.extract(multi_star)

    # 5. Unexpected star badge in non-warranty row
    unexpected_star = standard_html.replace(
        ">Haier</td>",
        '><span style="color:#d72314;margin-right:4px;">\u2605</span> Haier</td>',
    )
    with pytest.raises(TemplateShapeError, match="unexpected warranty star badge in non-warranty row"):
        KIACHAHIYE_ALFA_CARD.extract(unexpected_star)


def test_caption_tag_validation_catches_unbalanced_and_malformed_caption() -> None:
    """template_problems catches unbalanced <caption> tags and malformed elements inside <caption>."""
    # A custom template with an unclosed <caption> tag
    unclosed_caption = dataclasses.replace(
        KIACHAHIYE_ALFA_CARD,
        render=lambda rows: KIACHAHIYE_ALFA_CARD.render(rows).replace("</caption>", ""),
    )
    problems = template_problems(unclosed_caption)
    assert any("unbalanced <caption> tags" in p for p in problems)

    # An unclosed <div> inside <caption>
    unclosed_div = dataclasses.replace(
        KIACHAHIYE_ALFA_CARD,
        render=lambda rows: KIACHAHIYE_ALFA_CARD.render(rows).replace("</div></caption>", "</caption>"),
    )
    problems_div = template_problems(unclosed_div)
    assert any("never closed" in p or "closed out of order" in p for p in problems_div)

    # Stray </caption>
    stray_caption = dataclasses.replace(
        KIACHAHIYE_ALFA_CARD,
        render=lambda rows: "</caption>" + KIACHAHIYE_ALFA_CARD.render(rows),
    )
    problems_stray = template_problems(stray_caption)
    assert any("unbalanced <caption> tags" in p for p in problems_stray)
