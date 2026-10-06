"""Terminal dashboard for the KiaChahiye pipeline (stdlib only, no installs).

Runs: preflight -> tests -> pipeline -> audit -> thin-description report, with a
live progress bar per stage, then prints a management summary (rows, QC flags,
audit result, files to upload).  The full raw output of every stage is saved to
``run.log`` next to the generated files, so nothing is hidden.

Usage (normally via run_pipeline.bat):
    python run_ui.py                      # default sheet from config.py
    python run_ui.py "D:\\path\\SHEET.csv"  # any sheet -> data/output/<sheet>/
    python run_ui.py --no-tests           # skip the test stage
    python run_ui.py --plain              # no colours / box drawing

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
    size = path.stat().st_size if path.exists() else 0
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

    def banner(self, sheet: Path, out_dir: Path, py: str) -> None:
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
            f"{t.paint('Sheet   ', t.grey)} {clip(sheet.name)}",
            f"{t.paint('Output  ', t.grey)} {clip(str(out_dir))}",
            f"{t.paint('Python  ', t.grey)} {py}",
            f"{t.paint('Started ', t.grey)} {time.strftime('%A %d %B %Y, %H:%M:%S')}",
        ]
        self.box("RUN CONTEXT", info, t.blue)
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
    reader = threading.Thread(target=lambda: chunks.extend(iter(proc.stdout.readline, "")), daemon=True)
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
    "attribute_empty": "Attribute values outside the vocabulary",
    "sku_disambiguated": "SKUs made unique",
    "fallback_sku": "SKUs built without a model code",
    "category_missing_digi": "DigiMall categories unmapped",
    "category_missing_alfa": "Alfa categories unmapped",
    "brand_missing_digi": "DigiMall brands unmapped",
    "brand_missing_alfa": "Alfa brands unmapped",
    "thin_description": "Thin descriptions",
    "short_description_thin": "Thin short descriptions",
    "ac_inverter_status_unknown": "AC inverter status unknown",
    "title_description_conflict": "Title and description disagree",
    "product_type_inferred": "Product type inferred",
    "price_inversion": "Original price below sell price",
    "weight_missing": "Weight missing in source",
    "weight_unreadable": "Weight unreadable",
}


# ──────────────────────────────────── main ──────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("sheet", nargs="?", type=Path, help="source CSV (default: config.INPUT_FILE)")
    ap.add_argument("--no-tests", action="store_true", help="skip the test stage")
    ap.add_argument("--plain", action="store_true", help="no colours or box drawing")
    ap.add_argument("--no-wait", action="store_true", help="do not wait for a key at the end")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fancy = enable_ansi() and not args.plain
    ui = UI(Theme(fancy))
    t = ui.t

    custom = args.sheet is not None
    sheet = (args.sheet or CONFIG.INPUT_FILE).resolve()
    out_dir = (PKG / "data" / "output" / sheet.stem) if custom else CONFIG.DIGI_OUTPUT.parent.parent
    digi = out_dir / "digi" / "digimall_bulk_import.csv"
    alfa = out_dir / "alfa" / "alfa_bulk_import.csv"
    qc = out_dir / "qc_report.csv"
    evidence = out_dir / "row_check.csv"
    thin = out_dir / "thin_descriptions.csv"
    titles = out_dir / "title_review_sample.csv"
    log_path = out_dir / "run.log"
    py = sys.executable

    ui.banner(sheet, out_dir, f"{sys.version.split()[0]}")

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

    main_cmd = [py, "main.py", "--input", str(sheet)]
    if custom:
        main_cmd += ["--digi", str(digi), "--alfa", str(alfa), "--qc", str(qc),
                     "--sample-titles", str(titles)]
    audit_cmd = [py, "audit.py", "--input", str(sheet), "--digi", str(digi), "--alfa", str(alfa),
                 "--qc", str(qc), "--evidence", str(evidence)]
    thin_cmd = [py, "thin_report.py", "--input", str(sheet), "--digi", str(digi), "--qc", str(qc),
                "--out", str(thin)]

    stages = [
        ("Quality gate  ·  unit tests" if fancy else "Quality gate - unit tests",
         [py, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"] if run_tests else None),
        ("Generate  ·  DigiMall + Alfa" if fancy else "Generate - DigiMall + Alfa", main_cmd),
        ("Verify  ·  row-by-row audit" if fancy else "Verify - row-by-row audit", audit_cmd),
        ("Review  ·  weak descriptions" if fancy else "Review - weak descriptions", thin_cmd),
    ]
    total = len(stages)
    results: list[StageResult] = []
    started = time.time()
    blocked = False
    audit_failed = False
    audit_fails: list[str] = []

    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"{APP_NAME} run {time.strftime('%Y-%m-%d %H:%M:%S')}\nsheet: {sheet}\n")
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
            ui.box("AUDIT FAILURES", [t.paint(x[: WIDTH - 6], t.red) for x in audit_fails[:15]], t.red)

    # ── management summary ──
    if not blocked:
        qc_counts = read_qc(qc)
        flag_totals: Counter = Counter()
        for (_sev, ftype), n in qc_counts.items():
            flag_totals[ftype] += n
        sev_totals: Counter = Counter()
        for (sev, _f), n in qc_counts.items():
            sev_totals[sev] += n
        rows_out = {"DigiMall": count_rows(digi) if digi.exists() else 0,
                    "Alfa": count_rows(alfa) if alfa.exists() else 0}

        verdict_ok = not audit_failed
        verdict = (
            t.paint(f"{t.ok}  READY TO UPLOAD", t.bold, t.green)
            if verdict_ok else t.paint(f"{t.bad}  DO NOT UPLOAD — AUDIT FAILED", t.bold, t.red)
        )
        ui.write()
        ui.box("VERDICT", [verdict], t.green if verdict_ok else t.red)
        ui.write()

        kpi = [
            f"{t.paint('Source rows        ', t.grey)} {rows_in:,}",
            f"{t.paint('DigiMall rows      ', t.grey)} {rows_out['DigiMall']:,}",
            f"{t.paint('Alfa rows          ', t.grey)} {rows_out['Alfa']:,}",
            f"{t.paint('Audit              ', t.grey)} {results[2].detail}",
            f"{t.paint('Total run time     ', t.grey)} {fmt_time(total_time)}",
        ]
        ui.box("SUMMARY", kpi, t.cyan)

        if flag_totals:
            ui.write()
            width_label = 44
            max_n = max(flag_totals.values())
            flag_lines = []
            for ftype, n in flag_totals.most_common(8):
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
        files = [
            (digi, "UPLOAD  DigiMall"), (alfa, "UPLOAD  Alfa"),
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
                tag = t.paint(pad(label, 26), t.green if label.startswith("UPLOAD") else t.grey)
                text = str(shown)
                if len(text) > 39:
                    text = "…" + text[-38:] if t.fancy else "~" + text[-38:]
                lines.append(f"{tag}{pad(text, 39)} {t.paint(fmt_size(path).rjust(8), t.grey)}")
        ui.box("FILES", lines, t.blue)

    ui.write()
    if not args.no_wait and msvcrt is not None:
        ui.write(f"  {t.paint('Press', t.grey)} {t.paint('O', t.bold, t.cyan)} "
                 f"{t.paint('to open the output folder, any other key to exit', t.grey)}")
        if msvcrt.getwch().lower() == "o":
            os.startfile(out_dir)  # type: ignore[attr-defined]
    return 1 if blocked else (2 if audit_failed else 0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  Cancelled by user.")
        sys.exit(130)
