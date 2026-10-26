"""The terminal questions: which sheet, which platform, and what a bad answer does.

The menu is the only part of the run that reads a human, so its contract is that it never guesses:
an answer that is not one of the numbers is refused, and an absent human takes the default without
waiting.
"""

from __future__ import annotations

import sys

import pytest

import run_ui
from run_ui import UI, Theme


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

