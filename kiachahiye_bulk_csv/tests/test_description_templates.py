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
    DESCRIPTION_TEMPLATES,
    SPEC_TABLE,
    DescriptionTemplate,
    TemplateShapeError,
    build_description_html,
    template_for,
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
