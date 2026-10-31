"""A Description template is a named writer + reader pair, registered per cell.

These tests hold the two promises the per-(store x platform) template work is built
on: a template reads back exactly what it wrote (so a pasted template can be proved
lossless), and the registry is the only place a cell's template is looked up.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import main
from description_builder import (
    CONFORMANCE_ROWS,
    DESCRIPTION_TEMPLATES,
    SPEC_TABLE,
    DescriptionTemplate,
    TemplateShapeError,
    assert_template_conforms,
    build_description_html,
    extract_spec_rows,
    template_for,
    template_problems,
)
from models import SpecRow
from qc_report import QCFlagCollector

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
    Path("data/input/Products.csv"),
    Path("data/input/Step 1.csv"),
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


def _probe(
    row: str = VALID_ROW,
    *,
    head: str = VALID_HEAD,
    rows: list[SpecRow] | None = None,
    bold_all: bool = False,
    name: str = "probe",
) -> DescriptionTemplate:
    """A template that writes the harness's own sample rows in a given spelling."""
    sample = CONFORMANCE_ROWS if rows is None else rows

    def render(_rows: list[SpecRow]) -> str:
        body = "".join(
            row.format(
                label=f"<strong>{r.label}</strong>" if (bold_all or r.is_warranty) else r.label,
                value=f"<strong>{r.value}</strong>" if (bold_all or r.is_warranty) else r.value,
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
