#!/usr/bin/env python3
"""Record the function-node golden run into `tests/engine/golden/` (work package E7, engine design 9, function-nodes.md 9).

    scripts/py scripts/record_fn_golden.py [--out-dir DIR] [--check]

Runs the engine host IN-PROCESS (a thread, like `tests/engine/test_engine_host.py`) on a temp run folder in mock mode with
J2's Chrome checks faked (as J2's own `--fast` flow does): the Brew Lab brief arrives as a vague first line ("a website for my
cafe"), the Requester's answer is the full Brew Lab brief, so Identity asks, the turn pauses and the manual atom appears.
The run is made twice, with the function-node layer on and with `SUTRA_NODES=off`, in the same way and with the same clock.
Unlike J2's recorders this one needs no extraction of `prototypes/j2`: the layer is new code, so the golden is the engine's own
measured behaviour, whichever J2 the engine was vendored from (what the strict reply classes say about the mock's replies is part
of it, see docs/notes/E7.md).

It writes two files:

    fn_atoms_brewlab.json   the atoms in order (id, node, J2 step, work kind, checks, every transition, final display, ledger
                            status, the failing check), per-function kinds, the prompt digest list that must equal the one of
                            the `SUTRA_NODES=off` run, and the usage counts per atom family
    run_events.jsonl        the deterministic events of the layer-on run (run.started, say, the function atoms, usage,
                            run.ended) with the wall-clock `at` and a usage row's stopwatch `seconds` replaced by fixed values;
                            node, step, heartbeat and the builders' atom/1 views depend on thread timing (how many 250 ms
                            publishes fit in a run) and are left out; `test_engine_events_contract.py` checks those on a live run

`--check` records again and exits 1 when a file differs. The module is also imported by the two tests (`run_scenario`,
`atoms_golden`, `normalized_events`, `prompt_digest`), so the recorder and the tests ask the same questions.
"""
import argparse
import contextlib
import hashlib
import importlib
import json
import os
import re
import sys
import tempfile
import threading
import time
import types
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
OUT_DIR = REPO / "tests" / "engine" / "golden"
ATOMS_FILE, EVENTS_FILE = "fn_atoms_brewlab.json", "run_events.jsonl"
SCHEMA = "fn-atoms-golden/1"

ENGINE = "sutra_app.engine"
J2_MODULES = ("j2", "j2_agent", "j2_agent_models", "j2_agent_views", "j2_artifact_models", "j2_artifacts", "j2_board", "j2_change",
              "j2_check", "j2_map", "j2_realization", "j2_rules", "j2_schema", "j2_send", "j2_story", "j2_studio", "j2_template_lib",
              "j2_types", "rehydrate")
RUN_ID, TASK_ID, DEPT = "j2-20261104-100004-7f3a", "tsk_a1b2c3d4e5f6", "web"
VAGUE = "a website for my cafe"
BREW_LAB = ("A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should "
            "see the menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for "
            "pickup. It should feel warm and modern and work well on a phone. Include a section about our beans and the "
            "farms they come from, and a simple loyalty-card explainer (buy 9, get the 10th free).")
SETTINGS = {"J2_MEMORY": "0", "J2_REALIZATION": "0"}       # the engine tests' QUIET settings: no lessons file, no realization plan
CLOCK_START = 1_793_795_000                                 # epoch seconds of the fake clock (a fixed point in 2026)
FIXED_AT = "2026-11-04T10:00:00Z"
CLOCK_RE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d")
GOLDEN_EVENT_TYPES = ("run.started", "say", "atom", "usage", "run.ended")
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")


# ---- the scenario ---------------------------------------------------------------------------------------------------
class FakeClock:
    """Epoch seconds that advance by one on every call: the atoms' timestamps are the same in every run."""

    def __init__(self, start: int = CLOCK_START):
        self.now, self.lock = start, threading.Lock()

    def __call__(self) -> float:
        with self.lock:
            self.now += 1
            return float(self.now)


def _fake_check(j2_check, html):
    st = j2_check.static_checks(html)
    return {"available": True, **st, "phone": {"width": 360, "overflow_px": 0}, "desktop": {"width": 1280, "overflow_px": 0},
            "js_errors": [], "design": {}, "form_results": [{"index": i + 1, "has_submit": True, "submitted": True, "invalid": [],
                                                           "errors_during": [], "ok": True} for i in range(st["forms"])]}


def _fake_chrome(j2_check) -> None:
    """J2's --fast stub: the render checks without a browser."""
    j2_check.find_chrome = lambda: None
    j2_check.tap_targets = lambda html, selector, min_px=44: {"available": True, "roots": 1, "checked": 0, "small_count": 0,
                                                              "small": []}
    j2_check.check = lambda html: _fake_check(j2_check, html)


def _jsonl(path: Path) -> list:
    """The complete lines of a JSONL file. The owner thread reads events.jsonl while the engine appends to it, so a last line without its
    newline is a line still being written and is left for the next read (it failed on a fast Linux runner as a JSONDecodeError)."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    if not text.endswith("\n"):
        lines = lines[:-1]
    return [json.loads(line) for line in lines if line.strip()]


def _hooks_module(clock: FakeClock) -> types.ModuleType:
    """The hook factory the host is given through `SUTRA_HOOKS`. The host calls `factory(writer=, notify=, validator=,
    node_context_file=, spec=<TaskSpec>)` and the layer's `factory` names its last argument `task`, so the default wiring
    raises TypeError and the host falls back to the plain hooks (E3 and E6 both noted it; neither owns the other's file).
    This adapter maps the one name and passes the fake clock; nothing else differs from the default."""
    from sutra_app.engine.fnodes import layer
    mod = types.ModuleType("fn_golden_hooks")
    mod.factory = lambda **kw: layer.factory(kw["writer"], kw["notify"], kw["validator"], kw["node_context_file"],
                                             task=kw["spec"], clock=clock)
    return mod


def _write_task(run: Path, user_text: str) -> None:
    task = {"schema": "run-spec/1", "run_id": RUN_ID, "task_id": TASK_ID, "dept_id": DEPT, "dept_label": "Web", "scope_id": None,
            "scope_label": None, "user_text": user_text, "framing": "", "parent_run_id": None, "seed_from": None, "upstream": [],
            "settings": dict(SETTINGS), "connector": "auto"}
    temp = run / ".task.json.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(task, f)
    os.replace(temp, run / "task.json")
    for name in ("inbox.jsonl", "events.jsonl"):
        os.close(os.open(run / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))


def _answer(run: Path, answers: list[str], stop: threading.Event, stop_run: bool = False) -> None:
    """The owner: every question that asks the Requester is answered at once with the next text (the last one repeats); with
    `stop_run` the first question is answered by a `stop` line instead."""
    asked, n = 0, 0
    while not stop.is_set():
        rows = _jsonl(run / "events.jsonl")
        if any(e["t"] == "run.ended" for e in rows):
            return
        questions = [e for e in rows if e["t"] == "say" and e.get("act") == "ASK_REQUESTER"]
        while asked < len(questions):
            line = {"kind": "stop"} if stop_run else {"kind": "user", "text": answers[min(asked, len(answers) - 1)]}
            asked += 1
            n += 1
            with open(run / "inbox.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"n": n, **line, "at": FIXED_AT}) + "\n")
        time.sleep(0.005)


@contextlib.contextmanager
def _isolated(base: Path, nodes: str):
    """Mock-mode environment, a fresh import of the vendored J2 and the llm module's state; everything put back afterwards.
    `nodes`: `on` (layer through the adapter), `off` (`SUTRA_NODES=off`) or `default` (nothing set: the host's own wiring)."""
    saved_env = dict(os.environ)
    llm = importlib.import_module(f"{ENGINE}.llm")
    package = importlib.import_module(ENGINE)
    saved_llm = {name: getattr(llm, name) for name in ("_PORT", "_DEFAULT_PORT", "_BASE_TAG", "_BOUND_ATOM", "MOCK", "PROVIDER", "MODEL")}
    saved_mods = {name: (sys.modules.pop(f"{ENGINE}.{name}", None), package.__dict__.pop(name, None)) for name in J2_MODULES}
    hooks_before = sys.modules.get("fn_golden_hooks")
    try:
        for name in list(os.environ):
            if name.startswith(("J2_", "STUDIO_", "SUTRA_")):
                del os.environ[name]
        os.environ.update({"STUDIO_MOCK": "1", "J2_MEMORY": "0", "J2_REALIZATION": "0", "J2_MEMORY_FILE": str(base / "lessons.jsonl"),
                           "J2_PLAYBOOK_FILE": str(base / "playbooks.jsonl"), "J2_RUNS_DIR": str(base / "runs"),
                           "J2_LIBRARY_DIR": str(base / "library"), "SUTRA_HEARTBEAT_S": "0.2",
                           "SUTRA_ENV_FILE": str(base / "none.env")})
        llm.PROVIDER = llm.MODEL = llm._PORT = llm._DEFAULT_PORT = llm._BOUND_ATOM = None
        llm.MOCK = True
        llm.LAST_META.clear()
        if nodes == "off":
            os.environ["SUTRA_NODES"] = "off"
        elif nodes == "on":
            sys.modules["fn_golden_hooks"] = _hooks_module(FakeClock())
            os.environ["SUTRA_HOOKS"] = "fn_golden_hooks:factory"
        elif nodes != "default":
            raise ValueError(f"nodes must be on, off or default, not {nodes!r}")
        j2 = importlib.import_module(f"{ENGINE}.j2")
        _fake_chrome(j2.j2_check)
        yield
    finally:
        for name, (old, attr) in saved_mods.items():
            sys.modules.pop(f"{ENGINE}.{name}", None)
            package.__dict__.pop(name, None)
            if old is not None:
                sys.modules[f"{ENGINE}.{name}"] = old
            if attr is not None:
                package.__dict__[name] = attr
        for name, value in saved_llm.items():
            setattr(llm, name, value)
        llm.LAST_META.clear()
        if hooks_before is None:
            sys.modules.pop("fn_golden_hooks", None)
        else:
            sys.modules["fn_golden_hooks"] = hooks_before
        os.environ.clear()
        os.environ.update(saved_env)


def run_scenario(base: Path, nodes: str = "on", *, user_text: str = VAGUE, answers: Optional[list[str]] = None,
                 stop_on_question: bool = False) -> dict:
    """Run the golden scenario once in `base` (an empty folder) and return what it left: `events`, `trace`, `calls`, `chat`,
    `code` (the host's exit code) and `run_dir`. `nodes`: see `_isolated`. `stop_on_question`: the owner answers the first
    question with a `stop` line (the run ends `stopped` with the manual atom still open)."""
    base = Path(base)
    run = base / "data" / "departments" / DEPT / "runs" / RUN_ID
    run.mkdir(parents=True)
    os.chmod(run, 0o700)
    _write_task(run, user_text)
    with _isolated(base, nodes):
        from sutra_app.engine.host import loop
        host = loop.Host(loop._parse(["--run-dir", str(run), "--mock"]), None)
        result: dict[str, Any] = {}

        def go():
            try:
                result["code"] = host.execute()
            except BaseException as exc:  # noqa: BLE001
                result["error"] = exc
        stop = threading.Event()
        thread = threading.Thread(target=go, daemon=True)
        owner = threading.Thread(target=_answer, args=(run, [BREW_LAB] if answers is None else answers, stop, stop_on_question), daemon=True)
        thread.start()
        owner.start()
        thread.join(120)
        stop.set()
        owner.join(5)
        if thread.is_alive():
            raise RuntimeError("the host did not finish within 120 s")
        if "error" in result:
            raise result["error"]
    return {"code": result["code"], "run_dir": run, "events": _jsonl(run / "events.jsonl"), "trace": _jsonl(run / "trace.jsonl"),
            "calls": _jsonl(run / "calls.jsonl"), "chat": _jsonl(run / "chat.jsonl")}


# ---- what is recorded ---------------------------------------------------------------------------------------------------
def prompt_digest(calls: list[dict]) -> list[list[str]]:
    """`[function, sha(system), sha(prompt)]` per call, in call order: what the model was asked, byte for byte except for J2's own
    wall-clock stamps (`2026-11-04T18:09:57`, the `t` of a check result in a builder's prompt), which differ between two runs
    of the same J2 and are replaced by `<time>` before hashing."""
    def sha(text: Any) -> str:
        return hashlib.sha256(CLOCK_RE.sub("<time>", str(text or "")).encode("utf-8")).hexdigest()[:16]
    return [[c.get("fn"), sha(c.get("system")), sha(c.get("prompt"))] for c in calls]


def function_atom_events(events: list[dict]) -> list[dict]:
    """The `atom` events of function atoms (`work-atom/0.3`), in file order."""
    return [e for e in events if e["t"] == "atom" and e["atom"]["schema"] == "work-atom/0.3"]


def failing_check(reason: Optional[str]) -> Optional[str]:
    """`verify failed: reply-valid: goal: ...` -> `reply-valid` (the text after it is pydantic's and not part of the golden)."""
    if reason and reason.startswith("verify failed: "):
        return reason[len("verify failed: "):].split(":", 1)[0]
    return None


def touches_misses(trace: list[dict]) -> dict[str, int]:
    """`layer.touches_miss` trace lines counted by `<function> <record or message>`: the write-scope misses the layer only logs."""
    counts: dict[str, int] = {}
    for t in trace:
        if t["type"] == "layer.touches_miss":
            key = f"{t['data']['fn']} {t['data']['target']}"
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def atoms_golden(events: list[dict], trace: list[dict]) -> dict:
    """The per-atom story of a run, without anything that depends on the clock or on the wording of an error."""
    from sutra_app.library.atom import atom_display_state
    atoms: dict[str, dict] = {}
    for e in function_atom_events(events):
        a = e["atom"]
        body = a["body"]
        row = atoms.setdefault(a["id"], {
            "id": a["id"], "node": e["node"], "step": body["work"]["steps"], "work_kind": a["work_kind"],
            "checks": [c["template"] for c in body["verify"]["checks"]], "transitions": [], "final": None, "ledger": None,
            "failing_check": None})
        row["transitions"].append({"outcome": e["outcome"], "status": a["status"], "attempt": a["attempt"]})
        row["failing_check"] = failing_check(a["reason"]) or row["failing_check"]
        row["final"] = {"status": a["status"], "display": atom_display_state(body), "abandon_code": body.get("abandon_code")}
        if e.get("ledger"):
            row["ledger"] = e["ledger"]["status"]
    ordered = list(atoms.values())
    per_function: dict[str, dict] = {}
    for row in ordered:
        fn = row["node"].rpartition(".")[2]
        entry = per_function.setdefault(fn, {"atoms": 0, "steps": [], "work_kinds": []})
        entry["atoms"] += 1
        for key, value in (("steps", row["step"]), ("work_kinds", row["work_kind"])):
            if value not in entry[key]:
                entry[key].append(value)
    usage = [e for e in events if e["t"] == "usage"]
    ids = {a["id"] for a in ordered}
    return {
        "schema": SCHEMA,
        "scenario": {"run_id": RUN_ID, "dept": DEPT, "user_text": VAGUE, "answers": ["<the Brew Lab brief>"], "settings": SETTINGS,
                     "mode": "mock (ScriptedPort), Chrome faked, fake clock, one answer per question"},
        "atoms": ordered,
        "per_function": per_function,
        "touches_miss": touches_misses(trace),
        "usage": {"rows": len(usage), "on_function_atoms": sum(1 for u in usage if u["atom"] in ids),
                  "on_builder_atoms": sum(1 for u in usage if u["atom"] and u["atom"].startswith("W-")),
                  "on_other": sum(1 for u in usage if u["atom"] not in ids and not (u["atom"] or "").startswith("W-"))},
    }


def normalized_events(events: list[dict]) -> list[dict]:
    """The deterministic events with one fixed `at`: the golden `run_events.jsonl`. `pid` is the test process's, a usage row's
    `seconds` is a stopwatch reading, and a builder's `atom/1` view carries J2's wall-clock seconds and is written by the
    250 ms publisher (how many views fit in a run varies), so only the function atoms stay."""
    out = []
    for e in events:
        if e["t"] not in GOLDEN_EVENT_TYPES or (e["t"] == "atom" and e["atom"]["schema"] != "work-atom/0.3"):
            continue
        e = {**e, "at": FIXED_AT}
        if e["t"] == "run.started":
            e["pid"] = 1
        elif e["t"] == "usage":
            e["seconds"] = 0.0
        out.append(e)
    return out


def encode_events(events: list[dict]) -> str:
    return "".join(json.dumps(e, sort_keys=True, separators=(",", ":")) + "\n" for e in events)


def record(out_dir: Path = OUT_DIR) -> dict[str, str]:
    """Run the scenario with the layer on and off; return {file name: content}. Raises when the two runs ask different prompts."""
    with tempfile.TemporaryDirectory(prefix="fn-golden-on-") as a, tempfile.TemporaryDirectory(prefix="fn-golden-off-") as b:
        on, off = run_scenario(Path(a), "on"), run_scenario(Path(b), "off")
    if prompt_digest(on["calls"]) != prompt_digest(off["calls"]):
        raise RuntimeError("the layer changed a prompt: the digests of the two runs differ")
    golden = atoms_golden(on["events"], on["trace"])
    golden["prompts"] = {"calls": len(on["calls"]), "digest": prompt_digest(on["calls"])}
    return {ATOMS_FILE: json.dumps(golden, indent=1, sort_keys=True) + "\n", EVENTS_FILE: encode_events(normalized_events(on["events"]))}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--check", action="store_true", help="record again and exit 1 when a file differs")
    args = ap.parse_args(argv)
    files = record(args.out_dir)
    stale = [name for name, text in files.items() if not (args.out_dir / name).exists() or (args.out_dir / name).read_text("utf-8") != text]
    if args.check:
        print("golden files differ: " + ", ".join(stale) if stale else "golden files are current")
        return 1 if stale else 0
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (args.out_dir / name).write_text(text, encoding="utf-8")
        print(f"wrote {args.out_dir / name}: {len(text)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
