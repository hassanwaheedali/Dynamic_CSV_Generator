"""Terminal dashboard for the KiaChahiye pipeline (stdlib only, no installs).

Runs: preflight -> tests -> pipeline -> audit -> thin-description report, with a
live progress bar per stage, then prints a management summary (rows, QC flags,
audit result, files to upload).  The full raw output of every stage is saved to
``run.log`` next to the generated files, so nothing is hidden.

Usage (normally via run_pipeline.bat):
    python run_ui.py                      # asks which sheet, then which platform to run for
    python run_ui.py "D:\\path\\SHEET.csv"  # any sheet -> data/output/<sheet>/
    python run_ui.py --alfa               # Alfa only (also --digi, --platform both|digi|alfa)
    python run_ui.py --no-tests           # skip the test stage
    python run_ui.py --plain              # no colours / box drawing

A chosen platform is the only thing this run produces: that file is written, gated and reported on,
and the other platform's file is not written at all.  ``both`` (the default) does both uploads.
Nothing is asked when the answers are on the command line or nobody is at the keyboard.

Exit code: 0 = clean, 1 = a blocking stage failed, 2 = audit failed.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import config as CONFIG
from vendor_config import VENDOR_REGISTRY, VendorConfig, get_vendor
from writers import template_for_cell

try:
    import msvcrt  # Windows only: single-key prompt at the end
except ImportError:  # pragma: no cover
    msvcrt = None  # type: ignore[assignment]

PKG = Path(__file__).resolve().parent
APP_NAME = "KiaChahiye Bulk CSV Generator"
APP_VERSION = "1.0.0"
WIDTH = 78
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


# ───────────────────────────── terminal helpers ─────────────────────────────
def enable_ansi() -> bool:
    """Turn on VT/ANSI processing on Windows 10+; True when colours are safe."""
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            kernel = ctypes.windll.kernel32
            handle = kernel.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            return bool(kernel.SetConsoleMode(handle, mode.value | 0x0004))
        except Exception:
            return False
    return True


class Theme:
    """Colour + glyph palette; degrades to plain ASCII with --plain."""

    def __init__(self, fancy: bool) -> None:
        self.fancy = fancy
        c = (lambda code: f"\x1b[{code}m") if fancy else (lambda code: "")
        self.reset, self.bold, self.dim = c(0), c(1), c(2)
        self.cyan, self.green, self.red = c("38;5;45"), c("38;5;42"), c("38;5;203")
        self.yellow, self.grey, self.white = c("38;5;221"), c("38;5;245"), c("38;5;255")
        self.blue = c("38;5;75")
        if fancy:
            self.tl, self.tr, self.bl, self.br = "╭", "╮", "╰", "╯"
            self.h, self.v = "─", "│"
            self.full, self.empty = "█", "░"
            self.ok, self.bad, self.warn, self.dot = "✔", "✘", "▲", "●"
            self.arrow = "›"
        else:
            self.tl = self.tr = self.bl = self.br = "+"
            self.h, self.v = "-", "|"
            self.full, self.empty = "#", "."
            self.ok, self.bad, self.warn, self.dot = "OK", "XX", "!!", "*"
            self.arrow = ">"

    def paint(self, text: str, *styles: str) -> str:
        return "".join(styles) + text + self.reset if self.fancy else text


def visible_len(text: str) -> int:
    return len(ANSI_RE.sub("", text))


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - visible_len(text))


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:d}:{s:02d}" if m else f"{seconds:4.1f}s"


def fmt_size(path: Path) -> str:
    size: float = float(path.stat().st_size) if path.exists() else 0.0
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


class UI:
    def __init__(self, theme: Theme) -> None:
        self.t = theme
        self.lock = threading.Lock()

    def write(self, text: str = "") -> None:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def box(self, title: str, lines: list[str], colour: str = "") -> None:
        t, inner = self.t, WIDTH - 4
        colour = colour or t.cyan
        head = f" {title} " if title else ""
        top = t.tl + t.h + head + t.h * (WIDTH - 3 - len(head)) + t.tr
        self.write(t.paint(top, colour))
        for line in lines or [""]:
            self.write(f"{t.paint(t.v, colour)} {pad(line, inner)} {t.paint(t.v, colour)}")
        self.write(t.paint(t.bl + t.h * (WIDTH - 2) + t.br, colour))

    def banner(
        self,
        sheet: Path,
        out_dir: Path,
        py: str,
        upload: str = "",
        vendor_label: str = "",
        description_label: str = "",
    ) -> None:
        t = self.t
        if t.fancy:
            os.system("")  # keeps legacy conhost happy
            sys.stdout.write("\x1b[2J\x1b[H")
        title = t.paint(APP_NAME.upper(), t.bold, t.white)
        sub = t.paint(f"Enterprise catalogue pipeline  {t.dot}  v{APP_VERSION}", t.grey)
        self.box("", [title, sub], t.cyan)
        self.write()
        def clip(text: str, room: int = 62) -> str:
            return text if len(text) <= room else ("…" if t.fancy else "~") + text[-(room - 1):]

        info = [
            f"{t.paint('Vendor  ', t.grey)} {vendor_label}" if vendor_label else "",
            f"{t.paint('Sheet   ', t.grey)} {clip(sheet.name)}",
            f"{t.paint('Upload  ', t.grey)} {upload}" if upload else "",
            f"{t.paint(DESCRIPTION_LABEL, t.grey)} {description_label}" if description_label else "",
            f"{t.paint('Output  ', t.grey)} {clip(str(out_dir))}",
            f"{t.paint('Python  ', t.grey)} {py}",
            f"{t.paint('Started ', t.grey)} {time.strftime('%A %d %B %Y, %H:%M:%S')}",
        ]
        self.box("RUN CONTEXT", [line for line in info if line], t.blue)
        self.write()

    def overall(self, done: int, total: int, label: str) -> None:
        t = self.t
        n = 40
        filled = int(n * done / total)
        bar = t.paint(t.full * filled, t.green) + t.paint(t.empty * (n - filled), t.grey)
        pct = int(100 * done / total)
        self.write(f"  {t.paint('OVERALL', t.bold)} {bar} {pct:3d}%  {t.paint(label, t.grey)}")
        self.write()


# ─────────────────────────────── stage runner ───────────────────────────────
@dataclass
class StageResult:
    name: str
    status: str = "pending"  # ok | warn | fail | skip
    seconds: float = 0.0
    detail: str = ""
    output: str = ""
    code: int = 0
    extra: dict[str, str] = field(default_factory=dict)


def run_stage(ui: UI, index: int, total: int, name: str, cmd: list[str], log, cwd: Path) -> StageResult:
    """Run one subprocess with a live spinner + animated bar; capture its output."""
    t = ui.t
    res = StageResult(name)
    started = time.time()
    proc = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    chunks: list[str] = []
    stdout = proc.stdout
    assert stdout is not None
    reader = threading.Thread(target=lambda: chunks.extend(iter(stdout.readline, "")), daemon=True)
    reader.start()
    tick = 0
    live = t.fancy
    while proc.poll() is None:
        if live:
            elapsed = time.time() - started
            width = 28
            pos = tick % (width * 2 - 6)
            pos = pos if pos < width - 3 else (width * 2 - 6) - pos
            bar = "".join(t.full if pos <= i < pos + 4 else t.empty for i in range(width))
            line = (
                f"  {t.paint(SPINNER[tick % len(SPINNER)], t.cyan)} "
                f"{t.paint(f'[{index}/{total}]', t.grey)} {pad(t.paint(name, t.bold), 34)}"
                f"{t.paint(bar, t.cyan)} {t.paint(fmt_time(elapsed), t.yellow)}"
            )
            sys.stdout.write("\r\x1b[2K" + line)
            sys.stdout.flush()
        tick += 1
        time.sleep(0.08)
    reader.join(timeout=5)
    res.seconds = time.time() - started
    res.code = proc.returncode
    res.output = "".join(chunks)
    log.write(f"\n===== [{index}/{total}] {name}  (exit {res.code}, {res.seconds:.1f}s) =====\n")
    log.write("$ " + " ".join(cmd) + "\n" + res.output + "\n")
    log.flush()
    return res


def finish_line(ui: UI, index: int, total: int, res: StageResult) -> None:
    t = ui.t
    icon, colour = {
        "ok": (t.ok, t.green), "warn": (t.warn, t.yellow),
        "fail": (t.bad, t.red), "skip": ("-", t.grey),
    }[res.status]
    prefix = "\r\x1b[2K" if t.fancy else ""
    ui.write(
        f"{prefix}  {t.paint(icon, colour, t.bold)} {t.paint(f'[{index}/{total}]', t.grey)} "
        f"{pad(t.paint(res.name, t.bold), 34)}{pad(t.paint(res.detail, colour), 30)}"
        f"{t.paint(fmt_time(res.seconds), t.grey)}"
    )


# ─────────────────────────────── result parsing ─────────────────────────────
def parse_tests(out: str) -> tuple[str, str]:
    m = re.search(r"(\d+) passed(?:, (\d+) (?:failed|error))?", out)
    f = re.search(r"(\d+) failed", out)
    if m and not f:
        return "ok", f"{m.group(1)} tests passed"
    return "fail", f"{f.group(1) if f else '?'} tests FAILED"


def parse_audit(out: str) -> tuple[str, str, list[str]]:
    m = re.search(r"checks:\s*(\d+)\s*\|\s*passed:\s*(\d+)\s*\|\s*failed:\s*(\d+)", out)
    fails = [ln.strip() for ln in out.splitlines() if "[FAIL]" in ln]
    if not m:
        return "fail", "audit did not finish", fails
    checks, passed, failed = (int(x) for x in m.groups())
    status = "ok" if failed == 0 else "fail"
    return status, f"{passed}/{checks} checks passed", fails


def read_qc(path: Path) -> Counter:
    counts: Counter = Counter()
    if not path.exists():
        return counts
    csv.field_size_limit(10**9)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            counts[(row.get("Severity", ""), row.get("Flag Type", ""))] += 1
    return counts


def count_rows(path: Path) -> int:
    csv.field_size_limit(10**9)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return max(0, sum(1 for _ in csv.reader(fh)) - 1)


FLAG_LABELS = {
    "quantity_defaulted": "Quantity defaulted to 20 (no stock column)",
    "handle_deduplicated": "Handles made unique (shared titles)",
    "title_kept_from_source": "Titles kept as supplied",
    "title_dropped_words": "Rebuilt titles (dropped extra words)",
    "series_believed_from_one_row": "Series names believed from one row",
    "subtype_line_added_nothing": "SubType: lines that added no word to the Title",
    "attribute_empty": "Attribute values outside the vocabulary",
    "sku_disambiguated": "SKUs made unique",
    "fallback_sku": "SKUs built without a model code",
    "category_missing_digi": "DigiMall categories unmapped",
    "category_missing_alfa": "Alfa categories unmapped",
    "brand_missing_digi": "DigiMall brands unmapped",
    "brand_missing_alfa": "Alfa brands unmapped",
    "thin_description": "Thin descriptions",
    "short_description_thin": "Thin short descriptions",
    "seo_title_length": "Search titles that cannot reach 65-90",
    "ac_inverter_status_unknown": "AC inverter status unknown",
    "title_description_conflict": "Title and description disagree",
    "product_type_inferred": "Product type inferred",
    "price_inversion": "Regular price not above sell price (replaced)",
    "compare_at_derived": "Compare-at derived from sell price",
    "weight_missing": "Weight missing in source",
    "weight_unreadable": "Weight unreadable",
}


# ───────────────────────────────── questions ────────────────────────────────
def parse_choice(answer: str, count: int, default: int) -> int | None:
    """Which numbered choice an answer means, or None when it is not one of them.

    Enter alone takes the default; anything outside the list is refused rather than guessed at.
    """
    text = answer.strip()
    if not text:
        return default
    # isdecimal, not isdigit: "²" is a digit that int() refuses to read.
    if text.isdecimal() and 1 <= int(text) <= count:
        return int(text) - 1
    return None


def elide(text: str, room: int) -> str:
    """Shorten a name past its middle, so the start of it and its extension both still read."""
    if len(text) <= room:
        return text
    return f"{text[: room - 7]}...{text[-4:]}"


def menu(ui: UI, heading: str, entries: list[tuple[str, str]], default: int) -> int | None:
    """Ask one numbered question and return the chosen index, or None to take the default.

    None means nobody is at the keyboard -- a piped or automated run gets the default instead of
    waiting for an answer that will never come.
    """
    t = ui.t
    if not sys.stdin.isatty():
        return None
    # UI.box pads a line but never truncates it, so the widest name and the widest hint are fitted
    # to the panel together before anything is drawn.
    mark = len(str(len(entries))) + 3  # "[10] "
    room = WIDTH - 4 - mark  # what one line has left over for its name and its hint together
    # The hint is the reason a row is worth noticing -- an error name, a row count -- so it takes
    # the larger share of the line, and a long sheet name is the thing that gets shortened.
    hint_room = min(max(len(hint) for _label, hint in entries), room * 3 // 5)
    column = min(50, room - hint_room - 1, max(len(label) for label, _hint in entries) + 1)
    lines = [
        f"{t.paint(f'[{index}]', t.bold, t.cyan)} {pad(elide(label, column), column)}"
        f" {t.paint(elide(hint, hint_room), t.grey)}"
        for index, (label, hint) in enumerate(entries, 1)
    ]
    ui.write()
    ui.box(heading, lines, t.cyan)
    while True:
        try:
            answer = input(f"  {t.paint(f'Choose 1-{len(entries)}', t.grey)}"
                           f"{t.paint(f'  [Enter = {default + 1}]', t.grey)}: ")
        except EOFError:
            return default
        picked = parse_choice(answer, len(entries), default)
        if picked is not None:
            return picked
        ui.write(f"  {t.paint(f'{t.bad} {answer.strip()!r} is not one of those numbers.', t.red)}")


PLATFORM_ENTRIES = [
    ("Both platforms", "write + gate both files"),
    ("DigiMall only", "write + gate the DigiMall file"),
    ("Alfa only", "write + gate the Alfa file"),
]
PLATFORM_NAMES = ("both", "digi", "alfa")
# What each choice puts on disk -- only the chosen upload is written, and only it is gated.
PLATFORM_LABELS = {
    "both": "DigiMall + Alfa",
    "digi": "DigiMall only (Alfa not written)",
    "alfa": "Alfa only (DigiMall not written)",
}
GEN_LABELS = {"both": "DigiMall + Alfa", "digi": "DigiMall", "alfa": "Alfa"}
UPLOAD_LABELS = {"digi": "DigiMall", "alfa": "Alfa"}
# Which of the two uploads this run produces, in the order the screens list them.
PLATFORM_FILES = {"both": ("digi", "alfa"), "digi": ("digi",), "alfa": ("alfa",)}


def scope_note(platform: str) -> str:
    """What a single-platform run did not produce -- short enough to sit inside a panel.

    UI.box pads a line but never truncates it, so anything longer than WIDTH-4 pushes the box's
    own right border off the screen.
    """
    if platform == "both":
        return ""
    other = UPLOAD_LABELS["digi" if platform == "alfa" else "alfa"]
    return f"Written and proved: {UPLOAD_LABELS[platform]} only. No {other} file exists."


#: What the RUN CONTEXT banner calls the Description shapes.  The note that fills it is fitted to
#: exactly what this label leaves of the panel, so label and budget can never drift apart.
DESCRIPTION_LABEL = "Desc    "


def description_templates_note(vendor_cfg: VendorConfig, scope: tuple[str, ...]) -> str:
    """Which Description template serves each file this run writes, fitted to its panel.

    A store may restyle one platform's listings, so the screen names the shape going onto his
    upload, in the same words the terminal summary and the startup config error use.  Only the
    files this run produces are named, and each keeps its own place on the line: a template with a
    100-character name is shortened inside its own half, never by pushing another file's fact off
    the screen.
    """
    sep = " · "
    room = (WIDTH - 4 - len(DESCRIPTION_LABEL) - 1 - len(sep) * (len(scope) - 1)) // len(scope)
    parts = []
    for name in scope:
        label = UPLOAD_LABELS[name]
        template = template_for_cell(vendor_cfg, name)
        parts.append(f"{label} {elide(template.name, max(12, room - len(label) - 1))}")
    return sep.join(parts)


def ask_vendor(ui: UI) -> str:
    """Which vendor (store) to generate for. Listed from VENDOR_REGISTRY, no hardcoding."""
    entries = [
        (cfg.display_name, f"SKU prefix: {cfg.sku_prefix}-")
        for cfg in VENDOR_REGISTRY.values()
    ]
    keys = list(VENDOR_REGISTRY)
    choice = menu(ui, "VENDOR  ·  which store are you generating for?", entries, 0)
    return keys[choice if choice is not None else 0]


def ask_upload(ui: UI) -> str:
    """Which upload this run is proving: both files are always generated, one or both is gated."""
    choice = menu(ui, "UPLOAD  ·  which platform are you uploading today?",
                  PLATFORM_ENTRIES, PLATFORM_NAMES.index("both"))
    return PLATFORM_NAMES[choice if choice is not None else 0]


def ask_sheet(ui: UI) -> Path | None:
    """Which sheet in data/input to run, or None to keep the configured default."""
    folder = PKG / "data" / "input"
    sheets = sorted(folder.glob("*.csv"), key=lambda p: p.name.lower())
    if not sheets:
        return None

    def shape(path: Path) -> str:
        try:
            return f"{count_rows(path):,} rows"
        except Exception as exc:  # a sheet the reader cannot open is still a name he can pick
            return f"cannot be read ({type(exc).__name__})"

    entries = [(path.name, shape(path)) for path in sheets]
    default = next(
        (i for i, path in enumerate(sheets) if path.resolve() == CONFIG.INPUT_FILE.resolve()), 0
    )
    choice = menu(ui, "SHEET  ·  which file do you want to generate from?", entries, default)
    return sheets[choice] if choice is not None else None


# ──────────────────────────────────── main ──────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("sheet", nargs="?", type=Path, help="source CSV (asks for it when omitted)")
    flags = ap.add_mutually_exclusive_group()
    flags.add_argument("--platform", dest="platform", choices=PLATFORM_NAMES,
                       help="produce and gate only this platform (skips the question)")
    flags.add_argument("--digi", dest="platform", action="store_const", const="digi",
                       help="same as --platform digi")
    flags.add_argument("--alfa", dest="platform", action="store_const", const="alfa",
                       help="same as --platform alfa")
    ap.add_argument(
        "--vendor",
        dest="vendor",
        choices=list(VENDOR_REGISTRY),
        default=None,
        help="vendor key from vendor_config.py (skips the question when supplied)",
    )
    ap.add_argument("--no-tests", action="store_true", help="skip the test stage")
    ap.add_argument("--plain", action="store_true", help="no colours or box drawing")
    ap.add_argument("--no-wait", action="store_true", help="do not wait for a key at the end")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fancy = enable_ansi() and not args.plain
    ui = UI(Theme(fancy))
    t = ui.t

    vendor_key = args.vendor or ask_vendor(ui)
    vendor_cfg = get_vendor(vendor_key)
    platform = args.platform or ask_upload(ui)
    sheet = (args.sheet or ask_sheet(ui) or CONFIG.INPUT_FILE).resolve()
    scope_phrase = {"both": "both platforms", "digi": "DigiMall only", "alfa": "Alfa only"}[platform]
    out_dir = PKG / "data" / "output" / vendor_key / sheet.stem
    digi = out_dir / "digi" / "digimall_bulk_import.csv"
    alfa = out_dir / "alfa" / "alfa_bulk_import.csv"
    qc = out_dir / "qc_report.csv"
    evidence = out_dir / "row_check.csv"
    thin = out_dir / "thin_descriptions.csv"
    titles = out_dir / "title_review_sample.csv"
    log_path = out_dir / "run.log"
    py = sys.executable

    vendor_label = f"{vendor_cfg.display_name} (SKU: {vendor_cfg.sku_prefix}-)"
    # One chosen platform is the only thing this run touches: its file is the only one written,
    # the gate reads only it, and the worklists are built from it.
    scope = PLATFORM_FILES[platform]
    ui.banner(
        sheet, out_dir, sys.version.split()[0], PLATFORM_LABELS[platform], vendor_label,
        description_templates_note(vendor_cfg, scope),
    )

    # ── preflight ──
    problems = []
    if not sheet.exists():
        problems.append(f"Sheet not found: {sheet}")
    if problems:
        ui.box("PREFLIGHT FAILED", [t.paint(f"{t.bad} {p}", t.red) for p in problems], t.red)
        if not args.no_wait:
            input("\n  Press Enter to close...")
        return 1
    try:
        rows_in = count_rows(sheet)
    except Exception as exc:
        ui.box("PREFLIGHT FAILED", [t.paint(f"{t.bad} Cannot read sheet: {exc}", t.red)], t.red)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    have_pytest = subprocess.run(
        [py, "-c", "import pytest"], capture_output=True, cwd=PKG, check=False
    ).returncode == 0
    run_tests = (not args.no_tests) and have_pytest and (PKG / "tests").exists()

    paths = {"digi": digi, "alfa": alfa}
    uploads: list[str] = []
    for name in scope:
        uploads += [f"--{name}", str(paths[name])]

    main_cmd = [
        py, "main.py", "--input", str(sheet), "--vendor", vendor_key, *uploads,
        "--qc", str(qc), "--sample-titles", str(titles), "--platform", platform,
    ]
    audit_cmd = [
        py, "audit.py", "--input", str(sheet), "--vendor", vendor_key, *uploads,
        "--qc", str(qc), "--evidence", str(evidence), "--platform", platform,
    ]
    thin_cmd = [py, "thin_report.py", "--input", str(sheet), "--built", str(paths[scope[0]]),
                "--qc", str(qc), "--out", str(thin)]

    stages = [
        ("Quality gate  ·  unit tests" if fancy else "Quality gate - unit tests",
         [py, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"] if run_tests else None),
        (f"Generate  ·  {GEN_LABELS[platform]}" if fancy
         else f"Generate - {GEN_LABELS[platform]}", main_cmd),
        (f"Verify  ·  audit ({scope_phrase})" if fancy
         else f"Verify - audit ({scope_phrase})", audit_cmd),
        ("Review  ·  weak descriptions" if fancy else "Review - weak descriptions", thin_cmd),
    ]
    total = len(stages)
    results: list[StageResult] = []
    started = time.time()
    blocked = False
    audit_failed = False
    audit_fails: list[str] = []

    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"{APP_NAME} run {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                  f"vendor: {vendor_key}\nsheet: {sheet}\nupload: {platform}\n")
        for i, (name, cmd) in enumerate(stages, 1):
            if cmd is None:
                res = StageResult(name, "skip", 0.0,
                                  "skipped" if args.no_tests else "pytest not installed")
            elif blocked:
                res = StageResult(name, "skip", 0.0, "not run (earlier failure)")
            else:
                res = run_stage(ui, i, total, name, cmd, log, PKG)
                if i == 1:
                    res.status, res.detail = parse_tests(res.output)
                    blocked = res.status == "fail"
                elif i == 2:
                    res.status = "ok" if res.code == 0 else "fail"
                    res.detail = f"{rows_in:,} rows processed" if res.code == 0 else "pipeline error"
                    blocked = res.code != 0
                elif i == 3:
                    res.status, res.detail, audit_fails = parse_audit(res.output)
                    audit_failed = res.status == "fail"
                else:
                    m = re.search(r"worth a redo\s*:\s*(\d+)", res.output)
                    res.status = "ok" if res.code == 0 else "warn"
                    res.detail = f"{m.group(1)} flagged (advisory)" if m else "advisory"
            finish_line(ui, i, total, res)
            results.append(res)
        total_time = time.time() - started
        log.write(f"\nTotal: {total_time:.1f}s\n")

    ui.write()
    ui.overall(total, total, "complete" if not (blocked or audit_failed) else "finished with problems")

    # ── failure details ──
    failed = [r for r in results if r.status == "fail"]
    if failed:
        r = failed[0]
        tail = [ln for ln in r.output.splitlines() if ln.strip()][-18:]
        ui.box(f"{t.bad} STAGE FAILED: {r.name}", [t.paint(ln[: WIDTH - 6], t.red) for ln in tail], t.red)
        ui.write(f"  {t.paint('Full log:', t.grey)} {log_path}")
        if audit_fails and r is results[2]:
            ui.write()
            ui.box(f"AUDIT FAILURES  ·  {scope_phrase}",
                   [t.paint(x[: WIDTH - 6], t.red) for x in audit_fails[:15]], t.red)

    # ── management summary ──
    if not blocked:
        qc_counts = read_qc(qc)
        flag_totals: Counter = Counter()
        for (_sev, ftype), n in qc_counts.items():
            flag_totals[ftype] += n
        sev_totals: Counter = Counter()
        for (sev, _f), n in qc_counts.items():
            sev_totals[sev] += n
        rows_out = {UPLOAD_LABELS[name]: count_rows(paths[name]) for name in scope}

        verdict_ok = not audit_failed
        verdict = (
            t.paint(f"{t.ok}  READY TO UPLOAD  ·  {scope_phrase.upper()}", t.bold, t.green)
            if verdict_ok
            else t.paint(f"{t.bad}  DO NOT UPLOAD  ·  AUDIT FAILED  ·  {scope_phrase.upper()}",
                         t.bold, t.red)
        )
        lines = [verdict]
        note = scope_note(platform)
        if note:
            lines.append(t.paint(note, t.grey))
        ui.write()
        ui.box("VERDICT", lines, t.green if verdict_ok else t.red)
        ui.write()

        # One label column for the whole panel, so every value starts at the same character.
        kpi = [
            f"{t.paint(pad('Source rows', 20), t.grey)} {rows_in:,}",
            *(f"{t.paint(pad(f'{label} rows', 20), t.grey)} {count:,}"
              for label, count in rows_out.items()),
            f"{t.paint(pad('Audit', 20), t.grey)} {results[2].detail} "
            f"{t.paint(f'· {scope_phrase}', t.grey)}",
            f"{t.paint(pad('Total run time', 20), t.grey)} {fmt_time(total_time)}",
        ]
        ui.box("SUMMARY", kpi, t.cyan)

        if flag_totals:
            ui.write()
            width_label = 44
            max_n = max(flag_totals.values())
            flag_lines = []
            queue = flag_totals.most_common(8)
            # A category with a label here exists because a human has to act on it, so it is shown
            # even when its volume would push it off the top eight.  Kept in descending order so the
            # panel still reads as a ranking.
            for needed in FLAG_LABELS:
                if needed in flag_totals and all(ftype != needed for ftype, _ in queue):
                    queue.append((needed, flag_totals[needed]))
            queue.sort(key=lambda pair: pair[1], reverse=True)
            for ftype, n in queue:
                label = FLAG_LABELS.get(ftype, ftype.replace("_", " ").capitalize())
                bar_n = max(1, round(18 * n / max_n))
                bar = t.paint(t.full * bar_n, t.yellow) + t.paint(t.empty * (18 - bar_n), t.grey)
                flag_lines.append(f"{pad(label[:width_label], width_label)} {bar} {n:>6,}")
            ui.box(
                f"REVIEW QUEUE  ·  {sum(sev_totals.values()):,} flags (nothing blocks upload)"
                if fancy else f"REVIEW QUEUE - {sum(sev_totals.values()):,} flags",
                flag_lines, t.yellow,
            )

        ui.write()
        # A single-platform run does not write the other file, but an earlier run may have left it
        # in this folder -- named as stale rather than hidden, so an old CSV is never uploaded
        # believing it was proved today.
        stale = [
            (paths[name], f"STALE   {UPLOAD_LABELS[name]}")
            for name in ("digi", "alfa")
            if name not in scope and paths[name].exists()
        ]
        files = [
            *[(paths[name], f"UPLOAD  {UPLOAD_LABELS[name]}") for name in scope],
            *stale,
            (qc, "review  QC report"), (thin, "review  weak descriptions"),
            (evidence, "proof   row-by-row check"), (log_path, "log     full run output"),
        ]
        lines = []
        for path, label in files:
            if path.exists():
                try:
                    shown = path.relative_to(PKG)
                except ValueError:
                    shown = path
                tag = t.paint(
                    pad(label, 26),
                    t.green if label.startswith("UPLOAD") else t.red if label.startswith("STALE")
                    else t.grey,
                )
                text = str(shown)
                if len(text) > 39:
                    text = "…" + text[-38:] if t.fancy else "~" + text[-38:]
                lines.append(f"{tag}{pad(text, 39)} {t.paint(fmt_size(path).rjust(8), t.grey)}")
        ui.box("FILES  ·  STALE = left by an earlier run, not written today" if stale
               else "FILES", lines, t.blue)

    ui.write()
    if not args.no_wait:
        ui.write(f"  {t.paint('Press', t.grey)} {t.paint('[Enter]', t.bold, t.cyan)} "
                 f"{t.paint('or', t.grey)} {t.paint('[O]', t.bold, t.cyan)} "
                 f"{t.paint('to open output folder (or any other key to exit)...', t.grey)}")
        key = ""
        if msvcrt is not None and sys.stdin.isatty():
            try:
                key = msvcrt.getwch().lower()
            except Exception:
                key = ""
        if not key:
            try:
                key = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                key = "q"

        # Accept letter 'o', number '0', '1', or Enter
        if key in ("o", "0", "1", "\r", "\n", ""):
            ui.write(f"  {t.paint(t.ok, t.green)} {t.paint('Opening folder:', t.bold, t.green)} {out_dir}")
            try:
                os.startfile(str(out_dir))  # type: ignore[attr-defined]
            except Exception:
                subprocess.Popen(["explorer", str(out_dir)])
            time.sleep(0.4)
    return 1 if blocked else (2 if audit_failed else 0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  Cancelled by user.")
        sys.exit(130)
