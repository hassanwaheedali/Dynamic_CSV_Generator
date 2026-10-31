"""The owner's rule, made executable: one cell's template moves one file.

Four cells exist -- {kiachahiye, ajmer} x {digi, alfa}.  Editing the Description
template of one must leave the other three byte-identical, and nothing may win that
back by rendering once and sharing the string between cells.

The cells are read from ``VENDOR_REGISTRY``, never named here, so a new store joins
the proof the moment it is registered.
"""

from __future__ import annotations

import dataclasses
import hashlib
import html as html_module
from pathlib import Path
from typing import Any

import pytest
from conftest import run_pipeline

import main
from description_builder import (
    DESCRIPTION_TEMPLATES,
    SPEC_TABLE,
    DescriptionTemplate,
    extract_spec_rows,
)
from models import SpecRow
from qc_report import QCFlagCollector
from vendor_config import VENDOR_REGISTRY
from writers import build_alfa_row, build_digi_row


def _plain_shape(rows: list[SpecRow]) -> str:
    """A conforming second shape with no header and no inline styles."""
    body = "".join(
        "<tr>"
        f"<td>{'<strong>' if r.is_warranty else ''}"
        f"{html_module.escape(r.label, quote=False)}"
        f"{'</strong>' if r.is_warranty else ''}</td>"
        f"<td>{'<strong>' if r.is_warranty else ''}"
        f"{html_module.escape(r.value, quote=False)}"
        f"{'</strong>' if r.is_warranty else ''}</td>"
        "</tr>"
        for r in rows
    )
    return f"<table><tbody>{body}</tbody></table>"


#: Registered by each test that uses it, so the shop's own registry stays clean.
PROBE = DescriptionTemplate(
    name="probe",
    render=_plain_shape,
    extract=lambda text: extract_spec_rows(
        text, starts_with="<table", ends_with="</table>"
    ),
    starts_with="<table",
    ends_with="</table>",
)

PLATFORMS = ("digi", "alfa")
CELLS = [(store, platform) for store in VENDOR_REGISTRY for platform in PLATFORMS]

#: Two real-shaped rows: one labelled-bullet product, one bullet product, both with
#: the warranty line that becomes the bold row.
ROWS = [
    {
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
    },
    {
        "Title": "Haier 8 Kg Automatic Washing Machine HWM80-B1515U6",
        "Description": (
            "Haier front load washing machine.\n"
            "Brand: Haier\n"
            "Capacity: 8 Kg\n"
            "Color: White\n"
            "Inverter: Yes\n"
            "Warranty: 1 Year"
        ),
        "Sell Price": "149,999",
        "Original Price": "159,999",
        "Categories": "Electronics / Home appliances / Washing Machine",
        "Brand": "Haier",
        "Image": "https://example.invalid/hwm80.jpg",
    },
]

#: The shop's small real sheet, projected four ways.  The 752-row sheet gets the same
#: proof by hand at the plan's checkpoints, not on every pytest run.
STEP_ONE = Path("data/input/Step 1.csv")


def _cell(cfg: Any, platform: str, template: object) -> Any:
    """A copy of one store's config with this one cell's template replaced."""
    return dataclasses.replace(
        cfg, **{platform: dataclasses.replace(getattr(cfg, platform), description_template=template)}  # type: ignore[arg-type]
    )


def _project(records: list[Any], cfg: Any, platform: str) -> list[str]:
    builder = build_digi_row if platform == "digi" else build_alfa_row
    return [builder(record, cfg).values["Description"] for record in records]


def _all_cells(records: list[Any]) -> dict[tuple[str, str], list[str]]:
    return {cell: _project(records, VENDOR_REGISTRY[cell[0]], cell[1]) for cell in CELLS}


def test_the_registry_holds_four_cells_all_on_todays_table() -> None:
    """What the proof covers, stated rather than assumed."""
    assert len(CELLS) >= 4
    for store, platform in CELLS:
        cell = getattr(VENDOR_REGISTRY[store], platform)
        assert cell.description_template == "spec_table", (store, platform)


@pytest.mark.parametrize("platform", PLATFORMS)
@pytest.mark.parametrize("store", list(VENDOR_REGISTRY))
def test_editing_one_cell_moves_only_that_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    store: str,
    platform: str,
) -> None:
    """Requirement 1: the edited cell changes; every other cell keeps each byte."""
    monkeypatch.setitem(DESCRIPTION_TEMPLATES, PROBE.name, PROBE)
    records = run_pipeline(tmp_path, ROWS)["records"]
    baseline = _all_cells(records)
    monkeypatch.setitem(VENDOR_REGISTRY, store, _cell(VENDOR_REGISTRY[store], platform, PROBE.name))
    after = _all_cells(records)

    for cell, before in baseline.items():
        moved = after[cell] != before
        assert moved is (cell == (store, platform)), (
            f"{cell[0]}.{cell[1]} changed={moved}; only {store}.{platform} may"
        )
    assert after[(store, platform)][0].startswith("<table><tbody>")


def test_two_cells_naming_one_template_ship_one_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requirement 3: sharing a name is not copying a file -- it is one shape, twice."""
    monkeypatch.setitem(DESCRIPTION_TEMPLATES, PROBE.name, PROBE)
    records = run_pipeline(tmp_path, ROWS)["records"]
    cfg = _cell(
        _cell(VENDOR_REGISTRY["kiachahiye"], "digi", PROBE.name), "alfa", PROBE.name
    )
    digi = _project(records, cfg, "digi")
    alfa = _project(records, cfg, "alfa")
    assert digi == alfa
    assert digi == [_plain_shape(r.description.spec_rows) for r in records]


def test_the_real_sheet_moves_exactly_one_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The owner's own case on shop data: kiachahiye.alfa edits, three digests stay."""
    if not STEP_ONE.exists():  # unit run on a checkout without the shop's sheets
        pytest.skip(f"{STEP_ONE} is not in this checkout")
    rows = main.read_input(STEP_ONE)
    monkeypatch.setitem(DESCRIPTION_TEMPLATES, PROBE.name, PROBE)
    resolved = {
        store: main.run(rows, QCFlagCollector(), vendor_cfg=cfg)
        for store, cfg in VENDOR_REGISTRY.items()
    }

    def digests() -> dict[tuple[str, str], str]:
        out: dict[tuple[str, str], str] = {}
        for store, records in resolved.items():
            for platform in PLATFORMS:
                blob = "\n".join(_project(records, VENDOR_REGISTRY[store], platform))
                out[(store, platform)] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        return out

    before = digests()
    assert len(before) == len(CELLS)
    monkeypatch.setitem(
        VENDOR_REGISTRY,
        "kiachahiye",
        _cell(VENDOR_REGISTRY["kiachahiye"], "alfa", PROBE.name),
    )
    after = digests()
    moved = [f"{s}.{p}" for s, p in before if before[(s, p)] != after[(s, p)]]
    assert moved == ["kiachahiye.alfa"], moved


def test_no_cell_may_reuse_another_cells_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requirement 4: each cell renders, every time -- no shared string, no cache."""
    calls: list[int] = []

    def counting(rows: list[SpecRow]) -> str:
        calls.append(len(rows))
        return SPEC_TABLE.render(rows)

    template = DescriptionTemplate(
        name="counting",
        render=counting,
        extract=SPEC_TABLE.extract,
        starts_with="<table",
        ends_with="</table>",
    )
    monkeypatch.setitem(DESCRIPTION_TEMPLATES, "counting", template)
    record = run_pipeline(tmp_path, ROWS)["records"][0]
    cfg = _cell(
        _cell(VENDOR_REGISTRY["kiachahiye"], "digi", "counting"), "alfa", "counting"
    )
    build_digi_row(record, cfg)
    build_alfa_row(record, cfg)
    build_digi_row(record, cfg)
    assert len(calls) == 3, (
        "a Description was rendered once and handed to two cells: the shop chose "
        "per-cell templates over speed (41 ms for 1504 renders against a 7 s run)"
    )


def test_the_other_columns_stay_shared_when_one_cell_renders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only Description may split: every other column of that same file still matches."""
    monkeypatch.setitem(DESCRIPTION_TEMPLATES, PROBE.name, PROBE)
    result = run_pipeline(tmp_path, ROWS)
    cfg = _cell(VENDOR_REGISTRY["kiachahiye"], "alfa", PROBE.name)
    shared = [
        "Title", "Product Type", "Tags", "SEO Title", "SEO Description",
        "Variant SKU", "Variant Price", "Handle", "Product Images",
    ]
    for record in result["records"]:
        digi = build_digi_row(record, cfg).values
        alfa = build_alfa_row(record, cfg).values
        for column in shared:
            assert digi[column] == alfa[column], column
