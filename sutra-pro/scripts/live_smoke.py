#!/usr/bin/env python3
"""Live smoke of the whole app with the REAL claude and codex CLIs (work package GAP-LIVE, gap G07, decision D8).

    scripts/py scripts/live_smoke.py --fakes --max-usd 0          dry run against the fake CLIs (exit 0); never calls a model
    SUTRA_LIVE=1 scripts/py scripts/live_smoke.py --max-usd 5     the real run, ONLY on the owner's go-ahead

It runs on a temporary data folder and the owner's own logins, in this order (ids for --only / --skip):

    doctor    1. `sutra-pro doctor`
    suites    2. the four existing live suites in ONE pytest process (connectors, chat agent, library transport, engine)
    app       3. "I need a one-page site for a small coffee shop" through the real chat agent, Claude connector and engine
                 (J2_BUDGET=40), Identity's questions answered from a fixed list; time, calls, usd, tokens, atoms by state,
                 verify_failed by check, touches_miss, the Audit verdict, whether the site renders
    t1        4a. J2 test-plan branch T1 (happy path)
    followup  5.  a rehydrated follow-up with realization on; it is also the test plan's T13 (change request after the goal)
    t9        4b. T9 (Audit fails, the finding goes back, rework)
    t14       4c. T14 (the budget runs out)
    image     6.  one image-input call per CLI
    tools     7.  one tool call per CLI through the Sutra MCP tools
    budget        `--max-budget-usd` on one Claude call (open item 6)
    (8. a quota failure is NOT provoked.)

A hard ceiling, `--max-usd` (default 5) and `--max-calls` (default 120), is checked after EVERY call: through the usage sink for the
app (the engine's calls reach it through the projector) and through the connector spawn for the direct calls. The run stops cleanly
(live tasks stopped, the server closed, the report still written) and exits 3. A call is never made once the count is reached.

Output: `live-smoke-report.json` and `.md` in the output folder, and (a real run) the markdown section between the markers
below in docs/notes/GAP-LIVE.md. Each of the eight open items of G07 is `confirmed`, `fallback needed` (with the switch to flip)
or `not testable`. Exit: 0 all steps ran and none failed, 1 a step failed, 2 bad usage, 3 stopped by the ceiling or the time limit.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import datetime
import json
import logging
import os
import shutil
import signal
import sqlite3
import struct
import sys
import tempfile
import threading
import time
import traceback
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEFAULT_MAX_USD = 5.0
DEFAULT_MAX_CALLS = 120
DEFAULT_MAX_MINUTES = 150.0
APP_BUDGET = "40"                  # J2_BUDGET of the runs (the test plan's T1 uses 200: far too costly for a smoke)
TOKEN = "live-smoke-token-0123456789abcdef"
ORG = "cs_org"
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")
TERMINAL = ("done", "done_with_open_items", "stopped", "crashed", "cancelled")
GOOD_END = ("done", "done_with_open_items")
REPLY_FAIL_RATE_OK = 0.10          # an open-item decision (D98): at most one function atom in ten may end verify_failed by reply-valid
NOTES_BEGIN = "<!-- live-smoke:begin -->"
NOTES_END = "<!-- live-smoke:end -->"

FIRST_MESSAGE = "I need a one-page site for a small coffee shop"
# Identity's questions are answered from this list, in order; the last answer repeats. Nothing in it asks for more than the brief.
ANSWERS = (
    "It is called Little Fig, in Koramangala, Bengaluru, open 8am to 8pm every day. Show a short menu with prices (espresso 120, "
    "latte 160, filter coffee 90 rupees), the opening hours and where to find us. Cozy and simple, and it must work on phones.",
    "Option 1: keep going.",
    "Yes, that is fine. Please keep going and finish with what you have.",
)
BREW_LAB = (
    "A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should see the menu with "
    "prices, the opening hours, and where to find us, and be able to pre-order a coffee for pickup. It should feel warm and modern "
    "and work well on a phone. Include a section about our beans and the farms they come from, and a simple loyalty-card explainer "
    "(buy 9, get the 10th free).")
T9_BRIEF = (
    "Brew Lab, Indiranagar, Bengaluru. One-page site. Must-haves, each one will be checked: today's opening hours are highlighted "
    "automatically; the pre-order form shows a running total in rupees; the loyalty section shows 10 stamp circles with the 10th "
    "marked FREE; every menu item shows a price; the location section has a \"Get directions\" link; the page works at 360px wide.")
T13_TEXT = "Add a section with our weekend live music schedule: Saturday 7pm acoustic, Sunday 5pm jazz."

CONFIRMED, FALLBACK, NOT_TESTABLE = "confirmed", "fallback needed", "not testable"
ITEM_TITLES = {
    1: "`anyOf` ops in `--json-schema` / `--output-schema` (chart change request)",
    2: "A rehydrated follow-up with realization on",
    3: "Rate at which real J2 replies fail the closed reply classes",
    4: "Image input through `claude -p` and Codex `-i`",
    5: "A model calling the Sutra MCP tools",
    6: "`--max-budget-usd` behaviour",
    7: "Codex native schema against the real API",
    8: "Browser behaviours measured only in Chrome 156",
}
SAFARI_CHECKLIST = (
    "Manual Safari checklist (nobody can script it here): open the app in Safari; send a message and watch the graph update without a "
    "reload (SSE); reload mid-run and see the state come back (hello-resync); open a function drawer; switch light and dark; "
    "resize to phone width; check the site frames render sandboxed.")


# ---- the ceiling --------------------------------------------------------------------------------------------------------------

class CeilingExceeded(RuntimeError):
    """The run reached `--max-usd`, `--max-calls` or `--max-minutes`; the run stops cleanly."""


class Meter:
    """Counts calls, usd (Claude) and tokens (both), and trips once a ceiling is crossed. `add` is called after every call;
    `guard` before the next one. A trip runs the `on_trip` callbacks once and every later `guard` raises `CeilingExceeded`."""

    def __init__(self, max_usd: float, max_calls: int, deadline: float | None = None, clock: Callable[[], float] = time.time) -> None:
        self.max_usd, self.max_calls, self.deadline, self.clock = float(max_usd), int(max_calls), deadline, clock
        self.calls = 0
        self.usd = 0.0
        self.tokens: dict[str, dict[str, int]] = {}
        self.tripped: str | None = None
        self.step = ""
        self.by_step: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._on_trip: list[Callable[[str], None]] = []

    def on_trip(self, callback: Callable[[str], None]) -> None:
        self._on_trip.append(callback)

    def add(self, provider: str, usd: float | None, tokens_in: int = 0, tokens_out: int = 0) -> None:
        with self._lock:
            self.calls += 1
            self.usd += float(usd or 0.0)
            bucket = self.tokens.setdefault(provider, {"in": 0, "out": 0})
            bucket["in"] += int(tokens_in or 0)
            bucket["out"] += int(tokens_out or 0)
            step = self.by_step.setdefault(self.step, {"calls": 0, "usd": 0.0})
            step["calls"] += 1
            step["usd"] += float(usd or 0.0)
            self._evaluate()

    def _evaluate(self) -> None:
        if self.tripped:
            return
        if self.usd > self.max_usd + 1e-9:
            self._trip(f"cost ceiling: ${self.usd:.4f} spent, more than --max-usd {self.max_usd:g}")
        elif self.calls > self.max_calls:
            self._trip(f"call ceiling: {self.calls} calls, more than --max-calls {self.max_calls}")

    def _trip(self, why: str) -> None:
        self.tripped = why
        for callback in self._on_trip:
            try:
                callback(why)
            except Exception:                                   # noqa: BLE001  (a callback must not hide the trip)
                pass

    def guard(self, *, before_call: bool = False) -> None:
        """Raise `CeilingExceeded` when a ceiling is crossed (or, with `before_call`, when the next call would cross the count)."""
        with self._lock:
            if self.deadline is not None and not self.tripped and self.clock() > self.deadline:
                self._trip("time limit: --max-minutes reached")
            if not self.tripped and before_call and self.calls >= self.max_calls:
                self._trip(f"call ceiling: {self.calls} calls made, --max-calls is {self.max_calls}")
            if self.tripped:
                raise CeilingExceeded(self.tripped)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"calls": self.calls, "usd": round(self.usd, 6), "tokens": {k: dict(v) for k, v in self.tokens.items()}}


def attach_usage_sink(meter: Meter, store: Any) -> None:
    """Count every ledger row of the app (chat agent and engine alike) the moment it is stored. A replayed row (same ledger id) is
    counted once; stub rows are not model calls. The sink never raises: a trip is seen by the next `guard` of the driving thread."""
    original = store.record
    seen: set[int] = set()

    def record(row: Any, *, tx: Any = None) -> int:
        ledger_id = original(row, tx=tx) if tx is not None else original(row)
        if getattr(row, "provider", "stub") != "stub" and ledger_id not in seen:
            seen.add(ledger_id)
            meter.add(row.provider, row.usd, row.tokens_in or 0, row.tokens_out or 0)
        return ledger_id

    store.record = record


@contextlib.contextmanager
def metered_connectors(meter: Meter) -> Iterator[None]:
    """Count every spawn of a connector in this process (the direct calls of steps 2, 6 and 7 do not reach the app's usage sink)."""
    from sutra_app.connectors.base import ModelConnector

    original = ModelConnector._spawn

    def spawn(self: Any, plan: Any, hooks: Any, box: dict) -> Iterator[Any]:
        meter.guard(before_call=True)
        box.pop("turn", None)
        try:
            yield from original(self, plan, hooks, box)
        finally:
            turn = box.get("turn")
            usage = getattr(turn, "usage", None)
            meter.add(self.name, getattr(turn, "usd", None), getattr(usage, "input_total", 0) if usage else 0,
                      getattr(usage, "output_tokens", 0) if usage else 0)
        meter.guard()

    ModelConnector._spawn = spawn                              # type: ignore[method-assign]
    try:
        yield
    finally:
        ModelConnector._spawn = original                       # type: ignore[method-assign]


# ---- pure helpers (tested offline) -------------------------------------------------------------------------------------------

def make_png(width: int = 16, height: int = 16, rgb: tuple[int, int, int] = (220, 30, 30)) -> bytes:
    """A solid-colour PNG, standard library only (the image-input check asks the model for the colour)."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    row = b"\x00" + bytes(rgb) * width
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


class AnswerList:
    """The fixed answers to Identity's questions, in order; the last repeats; `limit` caps how many a task may get."""

    def __init__(self, answers: tuple[str, ...] = ANSWERS, limit: int = 6) -> None:
        self.answers, self.limit, self.given = answers, limit, 0

    @property
    def exhausted(self) -> bool:
        return self.given >= self.limit

    def next(self) -> str:
        text = self.answers[min(self.given, len(self.answers) - 1)]
        self.given += 1
        return text


def verify_failed_by_check(log_rows: list[dict], run_ids: tuple[str, ...] | None = None) -> dict[str, int]:
    """The Atom log's verify_failed rows counted by the check that failed (`body.verify.template`)."""
    found: collections.Counter[str] = collections.Counter()
    for row in log_rows:
        if row.get("status") != "verify_failed":
            continue
        if run_ids is not None and not str(row.get("atom_id", "")).startswith(tuple(f"{r}:" for r in run_ids)):
            continue
        verify = (row.get("body") or {}).get("verify") or {}
        found[str(verify.get("template") or "?")] += 1
    return dict(sorted(found.items()))


def count_touches_miss(run_dirs: list[Path]) -> int:
    """`layer.touches_miss` lines in the runs' trace files."""
    total = 0
    for run_dir in run_dirs:
        try:
            lines = (Path(run_dir) / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                total += json.loads(line).get("type") == "layer.touches_miss"
            except (ValueError, AttributeError):
                continue
    return total


def audit_summary(run_dir: Path) -> dict[str, Any]:
    """The Audit verdict of a run from `audits.json`: how many audits, the last one's verdict and its items by verdict."""
    try:
        data = json.loads((Path(run_dir) / "audits.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"audits": 0, "verdict": "none"}
    audits = [a for a in data if isinstance(a, dict) and a.get("kind") != "recheck"] if isinstance(data, list) else []
    if not audits:
        return {"audits": 0, "verdict": "none"}
    last = audits[-1]
    flags = [bool(a.get("all_pass")) for a in audits]
    verdicts = collections.Counter(str(r.get("verdict")) for r in last.get("results") or [] if isinstance(r, dict))
    return {"audits": len(audits), "verdict": "PASS" if flags[-1] else "FAIL", "verdicts": dict(sorted(verdicts.items())),
            "failed_then_passed": (not flags[0]) and any(flags[1:]) if len(flags) > 1 else False, "first_audit_failed": not flags[0]}


def latest_site_file(run_dir: Path) -> Path | None:
    folder = Path(run_dir) / "site"
    found = sorted(folder.glob("*.html"), key=lambda p: (p.stat().st_mtime, p.name)) if folder.is_dir() else []
    if not found:
        found = [p for p in (Path(run_dir) / "index.html", Path(run_dir) / "site.html") if p.is_file()]
    return found[-1] if found else None


def site_renders(run_dir: Path, *, chrome: str | None = None, runner: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Does the run's site exist and look like a page? With a Chrome, `--dump-dom` must also give a body."""
    path = latest_site_file(run_dir)
    if path is None:
        return {"exists": False, "renders": False, "browser": "none"}
    html = path.read_text(encoding="utf-8", errors="replace")
    low = html.lower()
    static = len(html) > 200 and "<html" in low and "<body" in low and "</html>" in low
    out: dict[str, Any] = {"exists": True, "file": path.name, "bytes": len(html.encode("utf-8")), "static_ok": static, "browser": "not run"}
    renders = static
    if chrome and static:
        import subprocess
        run = runner or subprocess.run
        try:
            done = run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=3000", "--dump-dom",
                        path.resolve().as_uri()], capture_output=True, text=True, timeout=45)
            dom_ok = done.returncode == 0 and "<body" in (done.stdout or "").lower() and len(done.stdout or "") > 200
            out["browser"] = "ok" if dom_ok else f"failed (exit {done.returncode})"
            renders = renders and dom_ok
        except Exception as exc:                                # noqa: BLE001
            out["browser"] = f"error: {type(exc).__name__}"
            renders = False
    out["renders"] = renders
    return out


def splice_section(text: str, section: str) -> str:
    """`text` with the live-smoke section between the markers replaced (or appended when the markers are not there yet)."""
    block = f"{NOTES_BEGIN}\n{section.rstrip()}\n{NOTES_END}\n"
    start, end = text.find(NOTES_BEGIN), text.find(NOTES_END)
    if start != -1 and end > start:
        return text[:start] + block + text[end + len(NOTES_END):].lstrip("\n")
    return text.rstrip("\n") + "\n\n" + block


def parse_junit(xml_text: str) -> dict[str, str]:
    """`{test id: passed|failed|skipped}` from a junit file."""
    import xml.etree.ElementTree as ET
    out: dict[str, str] = {}
    for case in ET.fromstring(xml_text).iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        out[name] = "failed" if case.find("failure") is not None or case.find("error") is not None else (
            "skipped" if case.find("skipped") is not None else "passed")
    return out


# ---- the eight open items ------------------------------------------------------------------------------------------------------

def _outcomes(tests: dict[str, str], *needles: str) -> dict[str, str]:
    return {name: out for name, out in tests.items() if all(n in name for n in needles)}


def _verdict(outcomes: dict[str, str]) -> str:
    """failed if any failed; else passed if any passed; else not run."""
    values = set(outcomes.values())
    return "failed" if "failed" in values else "passed" if "passed" in values else "none"


def judge_items(ev: dict[str, Any], *, fakes: bool = False) -> list[dict[str, Any]]:
    """The eight open items of G07 from the evidence of the steps: confirmed, fallback needed (with the switch) or not testable."""
    def item(n: int, status: str, why: str, switch: str = "") -> dict[str, Any]:
        return {"n": n, "title": ITEM_TITLES[n], "status": status, "why": why, "switch": switch}

    if fakes:
        return [item(n, NOT_TESTABLE, "dry run against the fake CLIs: no live evidence") for n in ITEM_TITLES]
    tests = (ev.get("suites") or {}).get("tests") or {}
    out: list[dict[str, Any]] = []

    ops = _outcomes(tests, "test_chart_change_request_native")
    got = _verdict(ops)
    out.append(item(1, NOT_TESTABLE, "the library live suite did not run or skipped it") if got == "none" else
                item(1, FALLBACK, "the union form failed on " + ", ".join(sorted(k.rsplit("::", 1)[-1] for k, v in ops.items() if v == "failed")),
                     'set CHART_OPS_TRANSPORT = "flat" in sutra_app/library/org_chart.py and add ChartOpFlat') if got == "failed" else
                item(1, CONFIRMED, f"{len(ops)} native chart-change run(s) passed (4 of 5 trials each)"))

    fu = ev.get("followup") or {}
    status = fu.get("status")
    if not fu or not fu.get("seeded"):
        out.append(item(2, NOT_TESTABLE, "the follow-up did not run, or it was not seeded from a finished run"))
    elif status in GOOD_END:
        out.append(item(2, CONFIRMED, f"the follow-up from the finished run ended {status}"))
    elif status == "crashed" or fu.get("rehydrate_refused"):
        out.append(item(2, FALLBACK, f"the follow-up ended {status}: {str(fu.get('outcome', ''))[:160]}",
                        "add `realization == 0` back as a condition in sutra_app/engine/rehydrate.py (S1-contracts-12)"))
    else:
        out.append(item(2, NOT_TESTABLE, f"the follow-up ended {status}, which says nothing about rehydration"))

    rp = ev.get("replies") or {}
    judged, failed = int(rp.get("function_atoms", 0)), int(rp.get("reply_valid_failed", 0))
    if judged == 0:
        out.append(item(3, NOT_TESTABLE, "no function atom was judged in a live run"))
    else:
        rate = failed / judged
        by_check = rp.get("verify_failed_by_check") or {}
        why = f"{failed} of {judged} function atoms ended verify_failed by reply-valid ({rate:.0%}); all failed checks: {by_check or 'none'}"
        if rp.get("touches_miss"):
            why += f"; {rp['touches_miss']} layer.touches_miss line(s): name the records in FunctionSpec.writes / WRITE_TERMS"
        out.append(item(3, CONFIRMED if rate <= REPLY_FAIL_RATE_OK else FALLBACK, why, "" if rate <= REPLY_FAIL_RATE_OK else
                        "loosen the L5 reply classes (sutra_app/library/functions.py validators) for the replies in the Atom log, never the check"))

    for n, key, probe, switch in (
            (4, "image", "ok_color", "set Capabilities(images=False) of the failing CLI (sutra_app/connectors/claude.py:345, codex.py:394)"),
            (5, "tools", "ok_tool", "give chat sessions tool_profile 'none' and keep the chart digest in the prompt (orchestrator/agent)")):
        res = ev.get(key) or {}
        tested = {cli: r for cli, r in res.items() if r.get("status") in ("ok", "fail")}
        bad = sorted(cli for cli, r in tested.items() if not r.get(probe))
        if not tested:
            out.append(item(n, NOT_TESTABLE, "no CLI was installed and signed in, or the step did not run"))
        elif bad:
            out.append(item(n, FALLBACK, "; ".join(f"{cli}: {tested[cli].get('detail', 'failed')}" for cli in bad), switch))
        else:
            out.append(item(n, CONFIRMED, "; ".join(f"{cli}: {r.get('detail', 'ok')}" for cli, r in sorted(tested.items()))))

    bd = ev.get("budget") or {}
    outcome = bd.get("outcome", "not_run")
    if outcome in ("stopped", "accepted"):
        out.append(item(6, CONFIRMED, bd.get("detail") or ("the CLI stopped at the money limit" if outcome == "stopped" else
                                                            "the flag was accepted and the call stayed under the limit")))
    elif outcome == "error":
        out.append(item(6, FALLBACK, bd.get("detail", "the flag broke the call"),
                        "stop passing --max-budget-usd (sutra_app/connectors/claude.py:410) and keep the Router's own Allowance check"))
    else:
        out.append(item(6, NOT_TESTABLE, "Claude was not installed or signed in, or the step did not run"))

    cx = _outcomes(tests, "[codex]")
    cx = {k: v for k, v in cx.items() if "test_native_schema_round_trip" in k or "test_a_corrected_schema_is_accepted" in k}
    got = _verdict(cx)
    out.append(item(7, NOT_TESTABLE, "the Codex native-schema tests did not run or skipped") if got == "none" else
               item(7, FALLBACK, "Codex rejected or mangled the strict schema", "set native_schema=False in CodexConnector.capabilities "
                    "(sutra_app/connectors/codex.py:394): Codex replies take the prompted path with repair") if got == "failed" else
               item(7, CONFIRMED, f"{len(cx)} Codex native-schema test(s) passed against the real API"))

    chrome = (ev.get("browser") or {}).get("chrome", "unknown")
    out.append(item(8, NOT_TESTABLE, f"needs a person at the browser (the engine's render check used Chrome: {chrome}). {SAFARI_CHECKLIST}"))
    return out


# ---- the report ---------------------------------------------------------------------------------------------------------------

def render_markdown(report: dict[str, Any]) -> str:
    lines = [f"## Live smoke results ({report['mode']}, {report['started']})", ""]
    totals = report["totals"]
    tokens = "; ".join(f"{p}: {t['in']} in / {t['out']} out" for p, t in sorted(totals["tokens"].items())) or "none"
    lines += [f"Calls {totals['calls']} of {report['ceiling']['max_calls']}; usd (Claude) ${totals['usd']:.4f} of ${report['ceiling']['max_usd']:g}; "
              f"tokens {tokens}; {report['seconds']:.0f} s." + (f" **Stopped: {report['aborted']}**" if report.get("aborted") else ""), ""]
    lines += ["| # | Open item | Result | Switch to flip / note |", "|---|---|---|---|"]
    for it in report["items"]:
        note = (it["switch"] + " | " if it["switch"] else "") + it["why"]
        lines.append(f"| {it['n']} | {it['title']} | **{it['status']}** | {note.replace('|', '/')} |")
    lines += ["", "| Step | Status | Seconds | Calls | usd | Note |", "|---|---|---:|---:|---:|---|"]
    for s in report["steps"]:
        note = (s.get("error") or "; ".join(s.get("problems", []) + s.get("notes", [])))[:200].replace("|", "/")
        lines.append(f"| {s['id']} | {s['status']} | {s['seconds']:.0f} | {s['calls']} | {s['usd']:.4f} | {note} |")
    runs = [(s["id"], s["detail"]["run"]) for s in report["steps"] if isinstance(s.get("detail"), dict) and isinstance(s["detail"].get("run"), dict)]
    if runs:
        lines += ["", "| Run | Task status | Atoms by state | verify_failed by check | touches_miss | Audit | Site renders |", "|---|---|---|---|---:|---|---|"]
        for step_id, run in runs:
            lines.append(f"| {step_id} | {run.get('status')} | {run.get('atoms_by_state')} | {run.get('verify_failed_by_check') or 'none'} | "
                         f"{run.get('touches_miss', 0)} | {(run.get('audit') or {}).get('verdict')} | {(run.get('site') or {}).get('renders')} |")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="live_smoke.py", description="Live smoke of the whole app with the real claude and codex CLIs.")
    p.add_argument("--fakes", action="store_true", help="dry run: the fake claude and codex of tests/fakes, J2's mock engine, no model call")
    p.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD, help="hard cost ceiling in usd (Claude), default %(default)s")
    p.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS, help="hard ceiling on model calls, default %(default)s")
    p.add_argument("--max-minutes", type=float, default=DEFAULT_MAX_MINUTES, help="time limit, default %(default)s")
    p.add_argument("--out", type=Path, help="output folder (default: a new folder under /tmp)")
    p.add_argument("--notes", default=None, help="markdown file to splice the results into ('-' = none; default: docs/notes/GAP-LIVE.md "
                                                 "for a real run, none for --fakes)")
    p.add_argument("--only", default="", help="comma list of step ids to run")
    p.add_argument("--skip", default="", help="comma list of step ids to leave out")
    p.add_argument("--keep", action="store_true", help="keep the data folder of a --fakes run (a real run always keeps it)")
    args = p.parse_args(argv)
    ids = [s for s, _, _ in STEPS]
    for name in ("only", "skip"):
        picked = [x for x in getattr(args, name).split(",") if x]
        unknown = [x for x in picked if x not in ids]
        if unknown:
            p.error(f"--{name}: unknown step {', '.join(unknown)} (steps: {', '.join(ids)})")
        setattr(args, name, picked)
    if args.max_usd < 0 or args.max_calls < 0 or args.max_minutes <= 0:
        p.error("the ceilings must not be negative, and --max-minutes must be positive")
    return args


# ---- the app under test -------------------------------------------------------------------------------------------------------

class StepProblem(Exception):
    """A step could not do what it set out to do (the step fails; the run goes on)."""


def engine_environment(root: Path) -> dict[str, str]:
    """The environment the engine processes start from: this process's, minus every name the engine reads for itself."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("J2_", "STUDIO_", "SUTRA_", "FAKE_"))}
    env["SUTRA_ENV_FILE"] = str(Path(root) / "none.env")
    return env


class AppRun:
    """The real app (`create_app`, a real uvicorn thread, the real engine process) on a temporary data folder."""

    def __init__(self, ctx: "Ctx") -> None:
        import httpx
        import uvicorn

        from sutra_app.config import Settings
        from sutra_app.main import GRACEFUL_SHUTDOWN_S, AppServer, bind_socket, create_app
        from sutra_app.orchestrator import wiring
        from sutra_app.orchestrator.runs import ProcessLauncher

        self.ctx = ctx
        root = ctx.root
        access = logging.getLogger("uvicorn.access")      # uvicorn empties its handlers when access_log is off: put them back at the end
        self._access_state = (access, list(access.handlers), access.propagate, access.disabled, access.level)
        self.settings = Settings.load({}, data_dir=root / "data", token=TOKEN, env_file=root / "none.env", engine="process",
                                      connector="auto", offline=False, max_runs=2, max_live=6, watch_ms=200 if ctx.fakes else 400)
        extra = {"SUTRA_HEARTBEAT_S": "1"}
        if ctx.fakes:
            extra.update({"SUTRA_MOCK": "1", "J2_CHROME": ctx.harness.write_fake_chrome(root / "fake-chrome")})

        default_budget = ctx.budget(APP_BUDGET)

        class BudgetLauncher(ProcessLauncher):
            def environment(self, spec: Any) -> dict[str, str]:
                env = super().environment(spec)
                env.setdefault("J2_BUDGET", default_budget)
                return env

        launcher = BudgetLauncher(environ=engine_environment(root), extra_env=extra, stop_grace=5.0, term_grace=3.0)
        sock = bind_socket("127.0.0.1", 0, scan=False)
        self.port = sock.getsockname()[1]
        self.settings = self.settings.model_copy(update={"port": self.port})
        real = wiring.build_connector_router
        if ctx.config is not None:
            wiring.build_connector_router = lambda s, **kw: real(s, config=ctx.config, **kw)
        try:
            self.app = create_app(self.settings, launcher=launcher)
        finally:
            wiring.build_connector_router = real
        attach_usage_sink(ctx.meter, self.app.state.services.usage)
        config = uvicorn.Config(self.app, log_config=None, access_log=False, timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S)
        self.server = AppServer(config, services=self.services, url=self.base_url + "/", open_browser=False)
        self._grace = GRACEFUL_SHUTDOWN_S
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [sock]}, name="uvicorn-smoke", daemon=True)
        self.thread.start()
        end = time.time() + 90
        while not self.server.started:
            if not self.thread.is_alive() or time.time() > end:
                raise StepProblem("the server did not start")
            time.sleep(0.05)
        self.http = httpx.Client(base_url=self.base_url, headers={"X-Sutra-Token": TOKEN}, timeout=60.0)
        self.stopped = False

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def services(self) -> Any:
        return self.app.state.services

    def get(self, path: str, **params: Any) -> Any:
        response = self.http.get(path, params=params or None)
        if response.status_code != 200:
            raise StepProblem(f"GET {path}: {response.status_code} {response.text[:200]}")
        return response.json()

    def post(self, path: str, body: dict | None = None) -> Any:
        return self.http.post(path, json=body if body is not None else {})

    def rows(self, sql: str, *args: Any) -> list[sqlite3.Row]:
        conn = sqlite3.connect(f"file:{self.settings.db_path}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    def one(self, sql: str, *args: Any) -> Any:
        found = self.rows(sql, *args)
        return found[0][0] if found else None

    def task_ids(self) -> list[str]:
        return [r[0] for r in self.rows("SELECT id FROM tasks ORDER BY created_at, rowid")]

    def task_status(self, task_id: str) -> str | None:
        return self.one("SELECT status FROM tasks WHERE id = ?", task_id)

    def run_dir(self, task_id: str) -> Path | None:
        found = self.rows("SELECT dept_id, run_id FROM tasks WHERE id = ?", task_id)
        if not found or not found[0]["run_id"]:
            return None
        return self.settings.data_dir / "departments" / found[0]["dept_id"] / "runs" / found[0]["run_id"]

    def stop_tasks(self, wait: float = 40.0) -> None:
        for (task_id,) in [(r[0],) for r in self.rows("SELECT id FROM tasks WHERE status NOT IN ('done','done_with_open_items','stopped','crashed','cancelled')")]:
            with contextlib.suppress(Exception):
                self.post(f"/api/tasks/{task_id}/stop")
        end = time.time() + wait
        while time.time() < end and self.rows("SELECT 1 FROM tasks WHERE status IN ('starting','running','waiting_user') LIMIT 1"):
            time.sleep(0.3)

    def pids(self) -> list[int]:
        found = []
        for (pid,) in self.rows("SELECT pid FROM tasks WHERE pid IS NOT NULL"):
            with contextlib.suppress(OSError):
                os.kill(pid, 0)
                found.append(pid)
        return found

    def stop(self) -> None:
        if self.stopped:
            return
        self.stopped = True
        with contextlib.suppress(Exception):
            self.http.close()
        self.server.should_exit = True
        self.thread.join(self._grace + 60)
        for pid in self.pids():
            with contextlib.suppress(OSError):
                os.killpg(os.getpgid(pid), signal.SIGKILL)
        logger, handlers, propagate, disabled, level = self._access_state
        logger.handlers[:], logger.propagate, logger.disabled = handlers, propagate, disabled
        logger.setLevel(level)


# ---- the steps ---------------------------------------------------------------------------------------------------------------

@dataclass
class Ctx:
    args: argparse.Namespace
    root: Path
    meter: Meter
    fakes: bool
    harness: Any = None
    cli: Any = None
    config: Any = None                       # ConnectorConfig aimed at the fake executables (fakes only)
    app: AppRun | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    dept: str | None = None
    poll: float = 1.0

    def expect(self, ok: bool, message: str, *, model: bool = False) -> None:
        """A check of a step. `model=True`: it depends on what a real model says, so a dry run (fakes) only notes it."""
        if ok:
            return
        (self.notes if (model and self.fakes) else self.problems).append(("dry run: " if model and self.fakes else "") + message)

    def budget(self, live_value: str) -> str:
        """J2_BUDGET of a run. J2's mock script needs the default budget of 100 to finish, so a dry run uses it for every run but T14."""
        return "100" if self.fakes else live_value

    def ensure_app(self) -> AppRun:
        if self.app is None:
            self.app = AppRun(self)
        return self.app

    def connector_config(self, name: str) -> Any:
        from sutra_app.connectors.models import ConnectorConfig
        if self.config is not None:
            return self.config.model_copy(update={"work_root": self.root / f"work-{name}"})
        return ConnectorConfig(data_dir=self.root / "data", work_root=self.root / f"work-{name}")

    def direct_connector(self, name: str) -> Any:
        """A connector for a direct call, or None (with a note) when the CLI is missing or not signed in with a subscription."""
        import shutil as _shutil

        from sutra_app.connectors.claude import ClaudeConnector
        from sutra_app.connectors.codex import CodexConnector
        from sutra_app.connectors.errors import ConnectorError
        cfg = self.connector_config(name)
        exe = cfg.claude_exe if name == "claude" else cfg.codex_exe
        if _shutil.which(exe) is None and not Path(exe).exists():
            self.notes.append(f"{name} is not installed")
            return None
        connector = ClaudeConnector(cfg) if name == "claude" else CodexConnector(cfg)
        try:
            auth = connector.probe_auth()
        except ConnectorError as err:
            self.notes.append(f"{name} status could not be read: {err.user_message()}")
            return None
        if auth.signed_in is not True or auth.billing == "api_key":
            self.notes.append(f"{name} is not signed in with a subscription login")
            return None
        return connector

    # -- the department the runs go to
    def ensure_department(self) -> str:
        app = self.ensure_app()
        if self.dept:
            return self.dept
        found = app.rows("SELECT id FROM org_nodes WHERE kind = 'department' AND id != 'root' ORDER BY rowid LIMIT 1")
        if found:
            self.dept = found[0][0]
            return self.dept
        from sutra_app.library.org_chart import AddOp, ChartChange, NewNode
        revision = app.get("/api/chart")["version"]
        node = NewNode(ref="$web", kind="department", name="Web", purpose="Websites and landing pages", parent="root")
        change = ChartChange(kind="add", reason="the smoke test needs a team", reuses=[], ops=[AddOp(node=node)], id="chg-9001",
                             task_id="req-smoke", base_revision=revision, ts=1)
        response = app.post("/api/chart/changes", change.model_dump(mode="json"))
        if response.status_code != 200:
            raise StepProblem(f"could not add a team: {response.status_code} {response.text[:200]}")
        self.dept = "web"
        return self.dept


def pending_approvals(app: AppRun) -> list[str]:
    return [c["id"] for c in app.get("/api/chart/changes") if c.get("status") == "pending_approval"]


def answer_needs(app: AppRun, answers: AnswerList, answered: set[int]) -> int:
    """Answer what waits for the owner: a question from the fixed list, a chart approval with yes. Returns how many were answered."""
    done = 0
    for need in app.get("/api/needs-you"):
        if need["message_id"] in answered:
            continue
        if need["kind"] == "approval":
            for change_id in pending_approvals(app):
                app.post(f"/api/chart/changes/{change_id}/decision", {"approve": True})
        elif answers.exhausted:
            continue
        else:
            response = app.post(f"/api/chats/{need['session_id']}/messages", {"text": answers.next()})
            if response.status_code not in (200, 202):
                raise StepProblem(f"could not answer: {response.status_code} {response.text[:160]}")
        answered.add(need["message_id"])
        done += 1
    return done


def wait_tasks(ctx: Ctx, task_ids: list[str], answers: AnswerList, timeout: float) -> dict[str, Any]:
    """Wait until every task is over, answering the team's questions from the fixed list. A task that is still going at `timeout`
    (or has had all its answers and still waits) is stopped. The ceiling is checked every round."""
    app, answered, end = ctx.ensure_app(), set(), time.time() + timeout
    timed_out, stalled_since = [], {}
    while True:
        ctx.meter.guard()
        states = {t: app.task_status(t) for t in task_ids}
        if all(s in TERMINAL for s in states.values()):
            break
        if any(s == "waiting_user" for s in states.values()):
            answer_needs(app, answers, answered)
        for task, state in states.items():
            if state == "waiting_user" and answers.exhausted:
                stalled_since.setdefault(task, time.time())
                if time.time() - stalled_since[task] > 30:
                    app.post(f"/api/tasks/{task}/stop")
                    timed_out.append(task)
            elif state not in TERMINAL and time.time() > end and task not in timed_out:
                app.post(f"/api/tasks/{task}/stop")
                timed_out.append(task)
        if time.time() > end + 120:
            raise StepProblem("a task did not stop after the time limit")
        time.sleep(ctx.poll)
    return {"states": states, "answers_given": answers.given, "stopped_by_smoke": timed_out}


def collect_run(ctx: Ctx, task_ids: list[str], seconds: float) -> dict[str, Any]:
    """What a run did, read from the database and the run folders."""
    app = ctx.ensure_app()
    mark = ",".join("?" * len(task_ids))
    tasks = app.rows(f"SELECT id, dept_id, run_id, status, outcome FROM tasks WHERE id IN ({mark})", *task_ids)
    run_ids = tuple(t["run_id"] for t in tasks if t["run_id"])
    dirs = [d for d in (app.run_dir(t["id"]) for t in tasks) if d is not None]
    atoms = app.rows(f"SELECT node_id, display FROM atoms WHERE task_id IN ({mark})", *task_ids)
    by_state = collections.Counter(a["display"] for a in atoms)
    by_fn = collections.Counter(a["node_id"].rpartition(".")[2] for a in atoms if a["node_id"].rpartition(".")[2] in FUNCTIONS)
    log_rows, after = [], 0
    while True:
        page = app.get("/api/atoms/log", after=after, limit=500)
        if not page:
            break
        log_rows += page
        after = page[-1]["seq"]
        if len(page) < 500:
            break
    usage = app.rows(f"SELECT count(*) c, sum(usd) u, sum(tokens_in) i, sum(tokens_out) o, "
                     f"sum(CASE WHEN atom_id IS NULL THEN 1 ELSE 0 END) missing FROM usage_ledger WHERE provider != 'stub' AND task_id IN ({mark})",
                     *task_ids)[0]
    main = dirs[-1] if dirs else None
    chrome = None if ctx.fakes else _find_chrome()
    return {
        "tasks": [t["id"] for t in tasks], "status": tasks[-1]["status"] if tasks else None, "outcome": (tasks[-1]["outcome"] or "")[:300] if tasks else "",
        "seconds": round(seconds, 1), "engine_calls": usage["c"], "engine_usd": round(usage["u"] or 0.0, 6), "engine_tokens_in": usage["i"] or 0,
        "engine_tokens_out": usage["o"] or 0, "engine_usage_rows_without_atom": usage["missing"] or 0,
        "atoms_by_state": dict(sorted(by_state.items())), "function_atoms": dict(sorted(by_fn.items())),
        "open_atoms_at_end": by_state.get("open", 0),
        "verify_failed_by_check": verify_failed_by_check(log_rows, run_ids), "touches_miss": count_touches_miss(dirs),
        "audit": audit_summary(main) if main else {"audits": 0, "verdict": "none"},
        "site": site_renders(main, chrome=chrome) if main else {"exists": False, "renders": False},
        "run_dirs": [str(d) for d in dirs],
    }


def _find_chrome() -> str | None:
    try:
        from sutra_app.engine.j2_check import find_chrome
        return find_chrome()
    except Exception:                                           # noqa: BLE001
        return None


def run_and_collect(ctx: Ctx, task_ids: list[str], timeout: float = 1500.0) -> dict[str, Any]:
    started = time.time()
    waited = wait_tasks(ctx, task_ids, AnswerList(), timeout if not ctx.fakes else 240.0)
    run = collect_run(ctx, task_ids, time.time() - started)
    run.update(answers_given=waited["answers_given"], stopped_by_smoke=waited["stopped_by_smoke"])
    return run


def expect_run(ctx: Ctx, label: str, run: dict[str, Any], *, allow_stop: bool = False) -> None:
    ok_status = run["status"] in GOOD_END or (allow_stop and run["status"] == "stopped")
    ctx.expect(ok_status, f"{label}: the task ended {run['status']}: {run['outcome'][:120]}")
    ctx.expect(run["open_atoms_at_end"] == 0, f"{label}: {run['open_atoms_at_end']} atom(s) were left open")
    ctx.expect(run["engine_usage_rows_without_atom"] == 0, f"{label}: {run['engine_usage_rows_without_atom']} usage row(s) carry no atom id")


# -- step 1
def step_doctor(ctx: Ctx) -> dict[str, Any]:
    from sutra_app.config import Settings
    from sutra_app.ops import doctor
    settings = Settings.load({}, data_dir=ctx.root / "data", token=TOKEN, env_file=ctx.root / "none.env", engine="process", port=0)
    report = doctor.run(settings, offline=False, config=ctx.config)
    checks = [c.to_dict() for c in report.checks]
    chrome = next((c["detail"] for c in checks if c["id"] == "chrome"), "unknown")
    ctx.evidence["browser"] = {"chrome": chrome}
    bad = [f"{c['id']}: {c['detail']}" for c in checks if c["status"] == "fail"]
    ctx.expect(report.ok, "doctor failed: " + "; ".join(bad), model=True)
    return {"ok": report.ok, "checks": [{k: c[k] for k in ("id", "status", "detail")} for c in checks]}


# -- step 2
SUITES = ("tests/connectors/test_live.py", "tests/orchestrator/live/test_live_chat_agent.py", "tests/library/test_lib_live_transport.py",
          "tests/engine/test_engine_live.py")


def step_suites(ctx: Ctx) -> dict[str, Any]:
    import pytest
    xml = ctx.root / "suites.xml"
    args = [*(str(REPO / s) for s in SUITES), "-m", "live", "-p", "no:cacheprovider", "-q", f"--junitxml={xml}", f"--basetemp={ctx.root / 'pytest'}",
            "-c", str(REPO / "pyproject.toml"), "--rootdir", str(REPO)]
    if ctx.fakes:
        args += ["--collect-only"]
    old = os.environ.get("SUTRA_LIVE")
    os.environ["SUTRA_LIVE"] = "1"
    try:
        with metered_connectors(ctx.meter), contextlib.redirect_stdout(sys.stderr):
            code = int(pytest.main(args))
    finally:
        if old is None:
            os.environ.pop("SUTRA_LIVE", None)
        else:
            os.environ["SUTRA_LIVE"] = old
    if ctx.fakes:
        ctx.expect(code in (0, 5), f"the four live suites could not be collected (pytest exit {code})")
        return {"collected_only": True, "exit": code}
    tests = parse_junit(xml.read_text(encoding="utf-8")) if xml.exists() else {}
    ctx.evidence["suites"] = {"tests": tests, "exit": code}
    # the engine suite runs its own engine process: its usage events are read from the run folder it left
    calls = usd = 0
    for events in (ctx.root / "pytest").rglob("events.jsonl"):
        for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("t") == "usage" and row.get("provider") in ("claude", "codex"):
                ctx.meter.add(row["provider"], row.get("usd"), int(row.get("tokens_in") or 0), int(row.get("tokens_out") or 0))
                calls, usd = calls + 1, usd + float(row.get("usd") or 0.0)
    ctx.meter.guard()
    failed = sorted(n for n, o in tests.items() if o == "failed")
    ctx.expect(not failed, "live tests failed: " + ", ".join(n.rsplit("::", 1)[-1] for n in failed))
    ctx.expect(any(o == "passed" for o in tests.values()), "no live test ran (CLIs missing or signed out?)", model=True)
    count = collections.Counter(tests.values())
    return {"exit": code, "tests": dict(count), "engine_suite_calls": calls, "engine_suite_usd": round(usd, 6), "failed": failed}


# -- step 3 and the runs of step 4
def step_app(ctx: Ctx) -> dict[str, Any]:
    app = ctx.ensure_app()
    if ctx.fakes:
        ctx.cli.push("claude", *ctx.harness.new_team_script())
    before, started = set(app.task_ids()), time.time()
    response = app.post(f"/api/chats/{ORG}/messages", {"text": FIRST_MESSAGE})
    if response.status_code != 202:
        raise StepProblem(f"the chat did not accept the message: {response.status_code} {response.text[:200]}")
    clarified, new = 0, []
    while True:
        end = time.time() + 600
        while app.services.runner.busy:
            ctx.meter.guard()
            if time.time() > end:
                raise StepProblem("the chat turn did not end in 10 minutes")
            time.sleep(0.2)
        ctx.meter.guard()
        new = [t for t in app.task_ids() if t not in before]
        if new:
            break
        if pending_approvals(app):
            for change_id in pending_approvals(app):
                app.post(f"/api/chart/changes/{change_id}/decision", {"approve": True})
            continue
        if clarified >= 2:
            raise StepProblem("the chat agent made no task after two clarifying answers")
        app.post(f"/api/chats/{ORG}/messages", {"text": ANSWERS[clarified]})
        clarified += 1
        time.sleep(0.5)
    ctx.dept = app.rows("SELECT dept_id FROM tasks WHERE id = ?", new[0])[0][0]
    run = run_and_collect(ctx, new)
    run["chat_seconds_before_tasks"] = round(time.time() - started - run["seconds"], 1)
    run["clarifying_answers"] = clarified
    expect_run(ctx, "app", run)
    ctx.expect(all(run["function_atoms"].get(fn, 0) >= 1 for fn in FUNCTIONS), f"a function has no atom: {run['function_atoms']}", model=True)
    ctx.expect(run["site"].get("renders"), f"the site does not render: {run['site']}", model=True)
    _note_replies(ctx, run)
    return {"run": run}


def _note_replies(ctx: Ctx, run: dict[str, Any]) -> None:
    rp = ctx.evidence.setdefault("replies", {"function_atoms": 0, "reply_valid_failed": 0, "verify_failed_by_check": {}, "touches_miss": 0})
    rp["function_atoms"] += sum(run["function_atoms"].values())
    for check, n in run["verify_failed_by_check"].items():
        rp["verify_failed_by_check"][check] = rp["verify_failed_by_check"].get(check, 0) + n
    rp["reply_valid_failed"] = rp["verify_failed_by_check"].get("reply-valid", 0)
    rp["touches_miss"] += run["touches_miss"]


def direct_task(ctx: Ctx, text: str, settings: dict[str, str]) -> list[str]:
    app = ctx.ensure_app()
    dept = ctx.ensure_department()
    response = app.post("/api/tasks", {"dept_id": dept, "text": text, "settings": settings})
    if response.status_code != 201:
        raise StepProblem(f"could not give the task: {response.status_code} {response.text[:200]}")
    return [response.json()["id"]]


def step_t1(ctx: Ctx) -> dict[str, Any]:
    run = run_and_collect(ctx, direct_task(ctx, BREW_LAB, {"J2_BUDGET": ctx.budget(APP_BUDGET)}))
    expect_run(ctx, "T1", run)
    ctx.expect(run["answers_given"] == 0, f"T1: Identity asked {run['answers_given']} question(s); the happy path asks none", model=True)
    ctx.expect(run["site"].get("renders"), f"T1: the site does not render: {run['site']}", model=True)
    _note_replies(ctx, run)
    return {"run": run, "branch": "T1 happy path (budget 40, not 200)"}


def step_followup(ctx: Ctx) -> dict[str, Any]:
    app = ctx.ensure_app()
    dept = ctx.ensure_department()
    seed = app.rows("SELECT id, run_id, status FROM tasks WHERE dept_id = ? AND run_id IS NOT NULL ORDER BY created_at DESC, rowid DESC LIMIT 1", dept)
    if not seed or seed[0]["status"] not in GOOD_END:
        ctx.notes.append("no finished run to continue from")
        ctx.evidence["followup"] = {"seeded": False}
        return {"skipped": "no finished run in the department"}
    session = app.one("SELECT chat_session_id FROM graph_nodes WHERE id = ?", dept)
    response = app.post(f"/api/chats/{session}/messages", {"text": T13_TEXT})
    if response.status_code != 200 or response.json().get("delivered") != "follow_up":
        raise StepProblem(f"the follow-up was not started: {response.status_code} {response.text[:200]}")
    task = response.json()["task_id"]
    seeded = "_seed_from" in (app.one("SELECT settings_json FROM tasks WHERE id = ?", task) or "")
    run = run_and_collect(ctx, [task])
    outcome = run["outcome"]
    ctx.evidence["followup"] = {"seeded": seeded, "status": run["status"], "outcome": outcome,
                                "rehydrate_refused": "rehydrat" in outcome.lower() and run["status"] != "done"}
    ctx.expect(seeded, "T13: the follow-up task was not seeded from the finished run")
    expect_run(ctx, "T13", run)
    _note_replies(ctx, run)
    return {"run": run, "branch": "T13 change request after the goal (also open item 2: rehydrated follow-up, realization on)", "seeded": seeded}


def step_t9(ctx: Ctx) -> dict[str, Any]:
    run = run_and_collect(ctx, direct_task(ctx, T9_BRIEF, {"J2_BUDGET": ctx.budget("60")}))
    expect_run(ctx, "T9", run, allow_stop=True)
    ctx.expect(run["audit"].get("audits", 0) >= 1, "T9: Audit never filed a verdict", model=True)
    _note_replies(ctx, run)
    return {"run": run, "branch": "T9 Audit fails and the finding goes back (budget 60)",
            "audit_failed_then_passed": run["audit"].get("failed_then_passed", False)}


def step_t14(ctx: Ctx) -> dict[str, Any]:
    run = run_and_collect(ctx, direct_task(ctx, BREW_LAB, {"J2_BUDGET": "15"}))
    ctx.expect(run["status"] in TERMINAL and not run["stopped_by_smoke"], "T14: the run did not end by itself", model=True)
    ctx.expect(run["open_atoms_at_end"] == 0, f"T14: {run['open_atoms_at_end']} atom(s) were left open")
    ctx.expect(bool(run["outcome"]), "T14: the final report is empty", model=True)
    _note_replies(ctx, run)
    return {"run": run, "branch": "T14 budget runs out (budget 15)"}


# -- steps 6, 7 and the budget flag
def _per_cli(ctx: Ctx, work: Callable[[Any, str], dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    with metered_connectors(ctx.meter):
        for name in ("claude", "codex"):
            connector = ctx.direct_connector(name)
            if connector is None:
                out[name] = {"status": "skipped", "detail": ctx.notes[-1] if ctx.notes else "not available"}
                continue
            try:
                out[name] = work(connector, name)
            except CeilingExceeded:
                raise
            except Exception as exc:                               # noqa: BLE001
                from sutra_app.connectors.errors import ConnectorError
                text = exc.user_message() if isinstance(exc, ConnectorError) else f"{type(exc).__name__}: {exc}"
                out[name] = {"status": "fail", "detail": text[:240]}
            finally:
                with contextlib.suppress(Exception):
                    connector.runner.stop_all()
    return out


def step_image(ctx: Ctx) -> dict[str, Any]:
    image = ctx.root / "red.png"
    image.write_bytes(make_png())

    def work(connector: Any, name: str) -> dict[str, Any]:
        turn = connector.call_text("What is the dominant colour of this image? Answer with one word.", images=[str(image)], effort="low",
                                   timeout=240.0)
        text = (turn.text or "").strip()
        saw = "red" in text.lower()
        return {"status": "ok", "ok_color": saw, "detail": f"answered {text[:60]!r}" + ("" if saw else " (not red: the image may have been ignored)")}

    results = _per_cli(ctx, work)
    ctx.evidence["image"] = results
    for name, res in results.items():
        ctx.expect(res["status"] != "fail", f"image input through {name} failed: {res['detail']}", model=True)
    return {"results": results, "nothing_ran": all(r["status"] == "skipped" for r in results.values())}


def step_tools(ctx: Ctx) -> dict[str, Any]:
    from sutra_app.connectors.models import Message, SessionSpec
    ctx.ensure_app()                                                # the tools read the app's database (G04)

    def work(connector: Any, name: str) -> dict[str, Any]:
        state = connector.start(SessionSpec(session_id=f"smoke_{name}", provider=name, tool_profile="sutra"))
        seen: list[Any] = []
        try:
            turn = connector.send(state, Message(role="user", text="Call the tool sutra_chart_read exactly once with no arguments, then reply "
                                                 "with the name of the first department you saw, or the word none."),
                                  timeout_s=240.0, on_event=seen.append)
        finally:
            with contextlib.suppress(Exception):
                connector.forget(state)
        calls = [e for e in seen if e.kind == "tool_call"]
        return {"status": "ok", "ok_tool": bool(calls), "tool_calls": len(calls), "detail": f"{len(calls)} tool call(s); replied {turn.text.strip()[:60]!r}"}

    results = _per_cli(ctx, work)
    ctx.evidence["tools"] = results
    for name, res in results.items():
        ctx.expect(res["status"] != "fail", f"the Sutra tools through {name} failed: {res['detail']}", model=True)
        ctx.expect(res["status"] != "ok" or res["ok_tool"], f"{name} made no tool call", model=True)
    return {"results": results, "nothing_ran": all(r["status"] == "skipped" for r in results.values())}


def step_budget(ctx: Ctx) -> dict[str, Any]:
    from sutra_app.connectors.errors import ConnectorError, EnvelopeExceededError
    from sutra_app.connectors.models import RouteContext
    from sutra_app.engine.port import Allowance
    result: dict[str, Any] = {"outcome": "not_run"}
    with metered_connectors(ctx.meter):
        connector = ctx.direct_connector("claude")
        if connector is not None:
            try:
                turn = connector.call_text("Reply with the single word ok.", effort="low", timeout=240.0,
                                           ctx=RouteContext(allowance=Allowance(max_usd=0.0005)))
                result = {"outcome": "accepted", "detail": f"the flag was accepted; the call cost {turn.usd} and was not stopped"}
            except EnvelopeExceededError as err:
                result = {"outcome": "stopped", "detail": f"the CLI stopped at the money limit ({err.user_message()[:100]})"}
            except ConnectorError as err:
                result = {"outcome": "error", "detail": f"{err.code}: {err.user_message()[:200]}"}
            finally:
                with contextlib.suppress(Exception):
                    connector.runner.stop_all()
    ctx.evidence["budget"] = result
    ctx.expect(result["outcome"] != "error", f"--max-budget-usd broke the call: {result.get('detail')}", model=True)
    return {**result, "nothing_ran": result["outcome"] == "not_run"}


STEPS: list[tuple[str, str, Callable[[Ctx], dict[str, Any]]]] = [
    ("doctor", "1 doctor", step_doctor),
    ("suites", "2 the four live suites", step_suites),
    ("app", "3 the whole app (coffee shop)", step_app),
    ("t1", "4 T1 happy path", step_t1),
    ("followup", "5 rehydrated follow-up (T13)", step_followup),
    ("t9", "4 T9 audit fails", step_t9),
    ("t14", "4 T14 budget runs out", step_t14),
    ("image", "6 image input", step_image),
    ("tools", "7 Sutra MCP tools", step_tools),
    ("budget", "--max-budget-usd", step_budget),
]


# ---- the run ------------------------------------------------------------------------------------------------------------------

def log(message: str) -> None:
    print(f"[live-smoke {time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def run_steps(ctx: Ctx, selected: list[tuple[str, str, Callable[[Ctx], dict[str, Any]]]]) -> tuple[list[dict[str, Any]], str | None]:
    results: list[dict[str, Any]] = []
    aborted: str | None = None
    for step_id, title, fn in selected:
        if aborted:
            results.append({"id": step_id, "title": title, "status": "skipped", "seconds": 0.0, "calls": 0, "usd": 0.0, "detail": {},
                            "problems": [], "notes": [f"not run: {aborted}"]})
            continue
        ctx.problems, ctx.notes = [], []
        ctx.meter.step = step_id
        before, started = ctx.meter.snapshot(), time.time()
        log(f"step {step_id}: start")
        detail: dict[str, Any] = {}
        error = ""
        try:
            ctx.meter.guard()
            detail = fn(ctx) or {}
            status = "fail" if ctx.problems else "skipped" if detail.get("nothing_ran") else "ok"
        except CeilingExceeded as exc:
            status, aborted, error = "aborted", str(exc), str(exc)
        except Exception as exc:                                  # noqa: BLE001
            status, error = "error", f"{type(exc).__name__}: {exc}"
            log(traceback.format_exc(limit=4))
        after = ctx.meter.snapshot()
        results.append({"id": step_id, "title": title, "status": status, "seconds": round(time.time() - started, 1),
                        "calls": after["calls"] - before["calls"], "usd": round(after["usd"] - before["usd"], 6), "detail": detail,
                        "problems": list(ctx.problems), "notes": list(ctx.notes), **({"error": error} if error else {})})
        log(f"step {step_id}: {status} in {results[-1]['seconds']:.0f} s, {results[-1]['calls']} call(s), ${results[-1]['usd']:.4f}"
            + (f" ({error})" if error else ""))
    return results, aborted


def build_report(args: argparse.Namespace, ctx: Ctx, steps: list[dict[str, Any]], aborted: str | None, started: float) -> dict[str, Any]:
    items = judge_items(ctx.evidence, fakes=ctx.fakes)
    return {"schema": "live-smoke/1", "mode": "fakes" if ctx.fakes else "live", "started": datetime.datetime.fromtimestamp(started).isoformat(timespec="seconds"),
            "seconds": round(time.time() - started, 1), "ceiling": {"max_usd": args.max_usd, "max_calls": args.max_calls, "max_minutes": args.max_minutes},
            "totals": ctx.meter.snapshot(), "aborted": aborted, "steps": steps, "items": items, "data_dir": str(ctx.root / "data"),
            "evidence": {k: v for k, v in ctx.evidence.items() if k != "suites"}}


def exit_code(report: dict[str, Any]) -> int:
    if report["aborted"]:
        return 3
    return 1 if any(s["status"] in ("fail", "error") for s in report["steps"]) else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = time.time()
    root = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="sutra-live-smoke-", dir="/tmp"))
    root.mkdir(parents=True, exist_ok=True)
    meter = Meter(args.max_usd, args.max_calls, deadline=started + args.max_minutes * 60)
    ctx = Ctx(args=args, root=root, meter=meter, fakes=args.fakes, poll=0.2 if args.fakes else 1.0)
    if args.fakes:
        sys.path.insert(0, str(REPO / "tests" / "e2e"))
        try:
            import harness
        finally:
            sys.path.remove(str(REPO / "tests" / "e2e"))
        from sutra_app.connectors.models import ConnectorConfig
        ctx.harness = harness
        ctx.cli = harness.FakeCliBin(root)
        kwargs = ctx.cli.config_kwargs()
        kwargs["extra_env"] = {**kwargs["extra_env"], "FAKE_COST_USD": "0"}          # a dry run costs nothing, so --max-usd 0 holds
        ctx.config = ConnectorConfig(**kwargs)
    selected = [s for s in STEPS if (not args.only or s[0] in args.only) and s[0] not in args.skip]
    log(f"{'dry run (fakes)' if args.fakes else 'LIVE run'}: {len(selected)} step(s), ceiling ${args.max_usd:g} / {args.max_calls} calls / {args.max_minutes:g} min; folder {root}")
    steps, aborted = [], None
    try:
        steps, aborted = run_steps(ctx, selected)
    finally:
        if ctx.app is not None:
            with contextlib.suppress(Exception):
                ctx.app.stop_tasks()
            ctx.app.stop()
    report = build_report(args, ctx, steps, aborted, started)
    markdown = render_markdown(report)
    (root / "live-smoke-report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (root / "live-smoke-report.md").write_text(markdown, encoding="utf-8")
    notes = args.notes if args.notes is not None else (None if args.fakes else str(REPO / "docs" / "notes" / "GAP-LIVE.md"))
    if notes and notes != "-":
        path = Path(notes)
        path.write_text(splice_section(path.read_text(encoding="utf-8") if path.exists() else "", markdown), encoding="utf-8")
    log(f"report: {root / 'live-smoke-report.json'}" + (f"; notes: {notes}" if notes and notes != "-" else ""))
    print(markdown)
    if args.fakes and not args.keep and not args.out:
        shutil.rmtree(root, ignore_errors=True)
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
