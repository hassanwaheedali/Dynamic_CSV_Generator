"""The terminal questions: which sheet, which platform, and what a bad answer does.

The menu is the only part of the run that reads a human, so its contract is that it never guesses:
an answer that is not one of the numbers is refused, and an absent human takes the default without
waiting.  The panels it draws are also held to the screen: nothing a run reports may be wider than
the box it is drawn in -- including which Description template serves each file.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

import run_ui
import writers
from description_builder import SPEC_TABLE, DescriptionTemplate
from run_ui import UI, Theme
from vendor_config import VendorConfig


class Captured(UI):
    """A UI that collects what the screen would have shown."""

    def __init__(self) -> None:
        super().__init__(Theme(fancy=False))
        self.lines: list[str] = []
        self.boxes: list[tuple[str, list[str]]] = []

    def write(self, text: str = "") -> None:
        self.lines.append(text)

    def box(self, title: str, lines: list[str], colour: str = "") -> None:
        self.boxes.append((title, lines))


class Keyboard:
    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture()
def typing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Someone is at the terminal."""
    monkeypatch.setattr(sys, "stdin", Keyboard(tty=True))


@pytest.fixture()
def nobody(monkeypatch: pytest.MonkeyPatch) -> None:
    """The run is piped or automated: input() would wait forever."""
    monkeypatch.setattr(sys, "stdin", Keyboard(tty=False))


def _answers(monkeypatch: pytest.MonkeyPatch, values: list[str]) -> None:
    """Feed ``values`` to successive input() calls, failing loudly when the menu asks again."""
    queue = list(values)

    def fake_input(prompt: str = "") -> str:
        assert queue, f"the menu asked again after the answers ran out: {prompt!r}"
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)


def test_enter_takes_the_default_choice() -> None:
    assert run_ui.parse_choice("", 3, 1) == 1


def test_a_number_counts_from_one_as_the_screen_shows_it() -> None:
    assert run_ui.parse_choice("2", 3, 0) == 1
    assert run_ui.parse_choice(" 3 ", 3, 0) == 2


def test_a_long_sheet_name_and_hint_stay_inside_the_panel(
    typing: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UI.box pads a line but never truncates it, so a wide choice pushes its own border off screen."""
    ui = Captured()
    _answers(monkeypatch, ["1"])
    name = "Products.backup-before-conflict-fix-2026-10-24.csv"
    hint = "cannot be read (UnicodeDecodeError)"
    run_ui.menu(ui, "SHEET", [(name, hint), ("Products.csv", "752 rows")], 0)
    lines = ui.boxes[0][1]
    assert all(len(line) <= run_ui.WIDTH - 4 for line in lines)
    assert lines[0].startswith("[1] Products.backup") and ".csv " in lines[0]


def test_the_verdict_note_fits_the_panel_it_is_drawn_in() -> None:
    """A single-platform run says what it did not write -- inside the box, not past its border."""
    assert run_ui.scope_note("both") == ""
    for platform in ("digi", "alfa"):
        note = run_ui.scope_note(platform)
        assert len(note) <= run_ui.WIDTH - 4, note
    assert "DigiMall" in run_ui.scope_note("alfa") and "Alfa" in run_ui.scope_note("digi")


def test_every_files_tag_fits_its_column() -> None:
    """The FILES column pads its tag to 26; a longer one walks the path off the right edge."""
    for label in run_ui.UPLOAD_LABELS.values():
        for tag in (f"UPLOAD  {label}", f"STALE   {label}"):
            assert len(tag) <= 26, tag


def test_a_hint_wider_than_the_panel_is_shortened_too(
    typing: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long sheet name is fitted to the panel; a long error message beside it still walks off screen."""
    ui = Captured()
    _answers(monkeypatch, ["1"])
    hint = "cannot be read (UnicodeDecodeError: 'Products.csv' codec can't decode byte 0x92)"
    run_ui.menu(ui, "SHEET", [("Products.csv", hint), ("Suzuki.csv", "752 rows")], 0)
    lines = ui.boxes[0][1]
    assert all(len(line) <= run_ui.WIDTH - 4 for line in lines)
    assert lines[0].startswith("[1] Products.csv")


def test_an_answer_outside_the_list_is_refused() -> None:
    """Choosing platform 4 is not 'Alfa, roughly' -- it is no answer at all."""
    assert run_ui.parse_choice("4", 3, 0) is None
    assert run_ui.parse_choice("alfa", 3, 0) is None
    assert run_ui.parse_choice("-1", 3, 0) is None
    assert run_ui.parse_choice("\u00b2", 3, 0) is None  # a digit int() cannot read


def test_the_menu_does_not_wait_when_nobody_is_typing(nobody: None) -> None:
    """A piped run falls through to the default instead of hanging on input()."""
    ui = Captured()
    assert run_ui.menu(ui, "SHEET", [("Products.csv", "752 rows")], 0) is None
    assert ui.lines == [] and ui.boxes == []


def test_a_wrong_answer_is_shown_and_asked_again(typing: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing about his upload is decided behind his back."""
    ui = Captured()
    _answers(monkeypatch, ["9", "3"])
    picked = run_ui.menu(
        ui, "UPLOAD", [("Both platforms", ""), ("DigiMall only", ""), ("Alfa only", "")], 0
    )
    assert picked == 2
    assert any("not one of those numbers" in line for line in ui.lines)
    assert ui.boxes[0][1][0].startswith("[1] Both platforms")


def test_ask_vendor_lists_registered_vendors_dynamically(
    typing: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ask_vendor() builds its menu from VENDOR_REGISTRY without hardcoding store keys."""
    ui = Captured()
    _answers(monkeypatch, ["2"])
    picked = run_ui.ask_vendor(ui)
    assert picked == list(run_ui.VENDOR_REGISTRY)[1]
    panel_lines = ui.boxes[0][1]
    for cfg in run_ui.VENDOR_REGISTRY.values():
        assert any(
            cfg.display_name in line and f"{cfg.sku_prefix}-" in line
            for line in panel_lines
        )


# ─────────────────── the shape each written file will take ───────────────────
def _shape(name: str) -> DescriptionTemplate:
    """SPEC_TABLE wearing another name -- a cell's own shape, without the gate's objection."""
    return dataclasses.replace(SPEC_TABLE, name=name)


def _store_with(digi_template: str | DescriptionTemplate, alfa_template: str | DescriptionTemplate) -> VendorConfig:
    """The registered Kiachahiye block with each cell's Description shape chosen."""
    cfg = run_ui.VENDOR_REGISTRY["kiachahiye"]
    return dataclasses.replace(
        cfg,
        digi=dataclasses.replace(cfg.digi, description_template=digi_template),
        alfa=dataclasses.replace(cfg.alfa, description_template=alfa_template),
    )


def test_the_note_names_the_shape_of_every_file_this_run_writes() -> None:
    """Before he uploads, the screen says which Description template served which file."""
    cfg = _store_with(SPEC_TABLE, _shape("wide_table"))
    note = run_ui.description_templates_note(cfg, ("digi", "alfa"))
    assert "DigiMall spec_table" in note, note
    assert "Alfa wide_table" in note, note


def test_a_single_platform_note_says_nothing_about_the_other_file() -> None:
    cfg = _store_with(SPEC_TABLE, _shape("wide_table"))
    note = run_ui.description_templates_note(cfg, ("alfa",))
    assert "Alfa wide_table" in note, note
    assert "DigiMall" not in note and "spec_table" not in note, note


def test_every_registered_store_says_what_shape_it_ships() -> None:
    """Read from VENDOR_REGISTRY, so a new store is named on the banner the day it joins."""
    for cfg in run_ui.VENDOR_REGISTRY.values():
        for scope in (("digi",), ("alfa",), ("digi", "alfa")):
            note = run_ui.description_templates_note(cfg, scope)
            assert len(note) <= run_ui.WIDTH - 4, (cfg.display_name, scope, note)
            assert note.split(" · ")[0].startswith(run_ui.UPLOAD_LABELS[scope[0]]), note
            for name in scope:
                assert run_ui.UPLOAD_LABELS[name] in note, note
                assert writers.template_for_cell(cfg, name).name in note, note


def test_a_shape_name_wider_than_the_panel_is_shortened_inside_its_own_half() -> None:
    """A long template name loses its own middle; it never pushes the other file's fact off screen.

    The banner used to clip the whole line, which kept the tail and silently deleted DigiMall's
    shape -- so the note now fits the panel by construction, and the drawn box is checked too.
    """
    monster = "ajmer_" + "two_column_descriptive_wrapper_" * 3
    assert len(monster) > run_ui.WIDTH, "the fixture is not wide enough to prove the fit"
    note = run_ui.description_templates_note(
        _store_with(_shape(monster), _shape("wide_table")), ("digi", "alfa")
    )
    assert len(note) <= run_ui.WIDTH - 4, note
    assert "DigiMall ajmer" in note and "..." in note, note
    assert "Alfa wide_table" in note, note

    ui = Captured()
    ui.banner(
        Path("Products.csv"), Path("out"), "3.14", "DigiMall + Alfa",
        "Kiachahiye (SKU: KC-)", note,
    )
    title, lines = ui.boxes[1]
    assert title == "RUN CONTEXT", title
    assert all(run_ui.visible_len(line) <= run_ui.WIDTH - 4 for line in lines), lines
    assert any("Desc" in line for line in lines), lines

