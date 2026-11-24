#!/usr/bin/env python3
"""Vendor the J2 prototype's engine into `sutra_app/engine/` (work package E1; engine design 3.1 and 3.4, decision D13).

    scripts/py scripts/vendor_j2.py --source /path/to/extraction --commit ee659fb5... [--dest .] [--check]

Since sync 4 (D136), and in syncs 5 and 6 (D160, D176) again, the source is the folder `prototypes/j2` of this repository at the pinned sutra commit, extracted with
`git archive <commit> prototypes/j2 | tar -x --strip-components=2 -C <new, empty folder>` (never the working tree).

What it does, in this order, and nothing else:

  1. reads the J2 files from `--source`, an extraction of `prototypes/j2` at ONE commit (a plain folder, so an edited working
     tree, a `.pyc` or a stray file is never vendored), with `--commit` naming the commit it was taken from;
  2. copies the 19 code modules and applies the numbered patches (P1 to P5, P7 to P12, P14 to P19; no P6, no P13) as exact
     text edits: every edit names its old text and how often it must occur, so a J2 change under an anchor stops the run
     instead of producing a silently different file (P1 is a counted rule over every import line, see `apply_p1`; P15 is a
     data patch: see `scrub_seed_index`);
  3. copies the data files byte for byte: role files, the whole `conditions/` and `templates/` trees (types are data, D161:
     no type name is listed here), the `artifacts/` tree (`types.json`, `real_run.md`), the seed template library (but for P15) and the reference docs;
  4. writes `sutra_app/engine/VENDORED.md`: the commit, the sha256 of every J2 file and of its vendored copy, and the patch
     list with the line ranges the patches ended up on.

`--check` changes nothing: it builds the same tree in memory and compares it with `--dest` (exit 1 on any difference,
including a file that should not be there). Re-running the script on an unchanged source writes the same bytes: a re-sync
to a newer commit of `prototypes/j2` is a new extraction, `--source` plus `--commit`, a review of the diff, and a look at the
patch table.

The patched files never `import j2` or `import llm` any more: the siblings are package-relative (P1), so the whole tree
imports as `sutra_app.engine.*`. Only the standard library is used here.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
BASELINE = "ee659fb54aec75bf7f5139516791aee20a0474fa"        # main (sync 8, D244): Kaivan's #205 and the dry-run fix #206 merged; J2 has not tagged it
BASELINE_TREE = "ddc9a7875b4e4d0d2d6af1d8f8764e1f0ddd2d37"   # `git rev-parse <BASELINE>:prototypes/j2`
PREVIOUS_BASELINES = ("9200cf6", "33aeeda", "025e265c", "1d537295", "1adb8ecd", "dee83d5c")       # commits the earlier syncs took the J2 prototype at (025e265c: sync 4, 1d537295: sync 5, tag cut-off/2026-11-12, 1adb8ecd: sync 6): history only, never a source
DESIGNED_AGAINST = "ce2631f"                                  # the design documents' line numbers (`j2.py:n`) are those of this commit: history only
J2_ENV = "SUTRA_J2_CHECKOUT"

CODE = ("j2.py", "j2_agent.py", "j2_agent_models.py", "j2_agent_views.py", "j2_artifact_lib.py", "j2_artifact_models.py", "j2_artifacts.py",
        "j2_board.py", "j2_change.py", "j2_check.py", "j2_map.py", "j2_realization.py", "j2_rules.py", "j2_schema.py",
        "j2_send.py", "j2_story.py", "j2_studio.py", "j2_template_lib.py", "j2_types.py")
ROLE_FILES = ("team.md", "identity.md", "adaptation.md", "priority.md", "coordination.md", "audit.md", "builder.md",
              "confidence-judge.md", "rates.json", "stages.json")          # agents/j2/ without the never-read _placeholders/
TREES = (("artifacts", "sutra_app/engine/artifacts", ("artifacts/types.local.json",)),      # sync 7: types.json and real_run.md (a run's own types stay out)
         ("conditions", "sutra_app/engine/conditions", ()),       # (J2 folder, vendored folder, excluded paths below the J2 folder)
         ("templates", "sutra_app/engine/templates", ("templates/README.md",)))      # D161: whole trees, no type is named here
REF_TOP = ("README.md", "SETUP.md")
REF_DOCS = ("atom-schema.json", "atom-schema.md", "map-schema.md", "realization-schema.json", "realization-axis.md",
            "j2-handoff.md", "j2-prompts.md", "j2-test-plan.md", "agent-views-j2-proposal.md",
            "hardcoding-inventory.md", "library-reuse-order.md",
            "remove-restrictions-plan.md", "remove-group-c-plan.md", "planner-thresholds-proposal.md")      # sync 7: Disha's #202 and #203
REF_TREES = ("docs/superpowers",)
MANAGED = ("sutra_app/engine/agents", "sutra_app/engine/conditions", "sutra_app/engine/artifacts",
           "sutra_app/engine/templates", "sutra_app/engine/seed", "docs/reference/j2")      # stale files in these are removed
VENDORED_MD = "sutra_app/engine/VENDORED.md"


class VendorError(Exception):
    """The source does not look as the patches expect, or a file is missing."""


# ---- the patches --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Edit:
    patch: str          # "P1" .. "P35" (P15 is the data patch below, not an Edit; P20 is reserved)
    file: str
    old: str
    new: str
    count: int = 1      # how often `old` must occur


P1_NOTE = ("sibling imports become package-relative by one counted rule over every code line (not comment) of every code module "
           "(44 lines, `P1_COUNTS`): `import j2_x[ as Y]` and `import llm` -> `from . import ...` (indentation kept), `from j2_x import y` "
           "-> `from .j2_x import y`; `j2_agent_views.py` also loses its `sys.path` insert (an anchor edit)")

# P1 (D162): the rule's expected number of changed lines per code module (a module not named here must have none). A J2 change
# that adds or removes a sibling import changes a count and stops the run, like a missing anchor.
P1_COUNTS = {"j2.py": 15, "j2_agent_views.py": 4, "j2_artifact_lib.py": 1, "j2_artifact_models.py": 2, "j2_artifacts.py": 7, "j2_change.py": 2,
             "j2_map.py": 2, "j2_realization.py": 2, "j2_rules.py": 1, "j2_story.py": 2, "j2_template_lib.py": 4, "j2_types.py": 2}
_P1_IMPORT = re.compile(r"^([ \t]*)import (j2_[a-z0-9_]+|llm)((?:[ \t]+as[ \t]+\w+)?)(?=[ \t]*(?:#.*)?$)", re.M)
_P1_FROM = re.compile(r"^([ \t]*)from (j2_[a-z0-9_]+) import ", re.M)
_P1_DONE = re.compile(r"^[ \t]*from \.(?:j2_[a-z0-9_]+ import |[ \t]+import (?:j2_[a-z0-9_]+|llm)\b)", re.M)      # a changed line, as it reads afterwards


def apply_p1(text: str, name: str):
    """P1: the sibling imports of one code module made package-relative. (new text, number of lines changed); a count that
    differs from P1_COUNTS raises VendorError."""
    text, a = _P1_IMPORT.subn(r"\1from . import \2\3", text)
    text, b = _P1_FROM.subn(r"\1from .\2 import ", text)
    want = P1_COUNTS.get(name, 0)
    if a + b != want:
        raise VendorError(f"{name}: P1 expects {want} import line(s) to change, found {a + b}")
    return text, a + b


def p1_lines(text: str):
    """The line numbers of the lines apply_p1 made (found again in the finished text)."""
    return [text.count("\n", 0, m.start()) + 1 for m in _P1_DONE.finditer(text)]

J2_EDITS = (
    # ---- imports (P1) and what the other patches import
    Edit("P8", "j2.py", r'''import shutil
import subprocess
import tempfile
import threading
''', r'''import shutil
import subprocess
import sys
import tempfile
import threading
'''),
    # P1's rule (apply_p1) has already made the sibling imports package-relative when these edits run
    Edit("P8", "j2.py", r'''from . import llm
''', r'''from . import llm
from . import hooks as _hooks                    # P3, P8: NullHooks, TurnInfo, CallInfo, TurnOutcome
from .port import ModelError as _ModelError      # P8: the code of a failed model call, for run_error
'''),
    # ---- P2: the role files
    Edit("P2", "j2.py", r'''J2_DIR = os.path.join(HERE, "agents", "j2")
''', r'''J2_DIR = os.getenv("J2_AGENTS_DIR") or os.path.join(HERE, "agents", "j2")     # P2: J2_AGENTS_DIR replaces the role-file folder
'''),
    # ---- P7, P8: tagging helper and the step table, beside the other module constants
    Edit("P7", "j2.py", r'''TO_USER = re.compile(r"@(?:requester|user)\b", re.I)
''', r'''TO_USER = re.compile(r"@(?:requester|user)\b", re.I)

# P8: the J2 step (STEPS) each turn sets before its first model call, told to the hooks when the turn starts.
TURN_STEPS = {"identity": {"intake": 1, "approval": 6, "stage_decision": 8, "requester_answered": 8, "limit": 8, "audit": 8,
                           None: 4},      # any other kind: resolve, ruling_budget, question
              "adaptation": {None: 2}, "priority": {"envelope": 6, None: 3}, "coordination": {None: 6}, "audit": {None: 7}}
KEEP_STEP = {("identity", "send_confirm"), ("priority", "dispute"), ("coordination", "dispute"), ("audit", "dispute")}


def turn_step(fn, kind, current):
    """P8: the step (STEPS 1..8) the turn of `fn` sets for a hand-off of `kind`; `current` where it sets none."""
    if is_wf_agent(fn):
        return 6
    steps = TURN_STEPS.get(fn)
    if steps is None or (fn, kind) in KEEP_STEP:
        return current
    return steps.get(kind, steps[None])


def _ask(tag, *args, **kw):
    """P7: llm.ask inside a tagged block. Run, department and task come from the base tag the host set (llm.configure)."""
    with llm.tagged(**tag):
        return llm.ask(*args, **kw)
'''),
    # ---- P5: memory and saved runs with explicit paths
    Edit("P5", "j2.py", r'''def load_lessons():
    if not memory_on() or not os.path.exists(MEMORY_FILE):
        return []
    out = []
    with open(MEMORY_FILE, encoding="utf-8") as f:
''', r'''def load_lessons(path=None):
    path = path or MEMORY_FILE        # P5: another department's file; the old constant is the default
    if not memory_on() or not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
'''),
    Edit("P5", "j2.py", r'''def save_lesson(lesson):
    if not memory_on():
        return
    lesson = {**lesson, **({"mock": True} if llm.MOCK else {})}   # mock memory never reaches a live run
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
''', r'''def save_lesson(lesson, path=None):
    path = path or MEMORY_FILE        # P5
    if not memory_on():
        return
    lesson = {**lesson, **({"mock": True} if llm.MOCK else {})}   # mock memory never reaches a live run
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
'''),
    Edit("P5", "j2.py", r'''def clear_lessons():
    """Delete memory/lessons.jsonl; returns how many lessons it held."""
    if not os.path.exists(MEMORY_FILE):
        return 0
    with open(MEMORY_FILE, encoding="utf-8") as f:
        n = sum(1 for ln in f if ln.strip())
    os.remove(MEMORY_FILE)
    return n
''', r'''def clear_lessons(path=None):
    """Delete memory/lessons.jsonl; returns how many lessons it held."""
    path = path or MEMORY_FILE        # P5
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        n = sum(1 for ln in f if ln.strip())
    os.remove(path)
    return n
'''),
    Edit("P5", "j2.py", r'''def load_playbooks():
    if not memory_on() or not os.path.exists(PLAYBOOK_FILE):
        return []
    with open(PLAYBOOK_FILE, encoding="utf-8") as f:
''', r'''def load_playbooks(path=None):
    path = path or PLAYBOOK_FILE      # P5
    if not memory_on() or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
'''),
    Edit("P5", "j2.py", r'''def save_playbook(pb):
    """One playbook per run: a later Done in the same run (after a change request) replaces it."""
    if not memory_on():
        return
    pb = {**pb, **({"mock": True} if llm.MOCK else {})}       # mock memory never reaches a live run
    keep = [x for x in load_playbooks() if x.get("id") != pb["id"]]
    os.makedirs(os.path.dirname(PLAYBOOK_FILE), exist_ok=True)
    with open(PLAYBOOK_FILE, "w", encoding="utf-8") as f:
''', r'''def save_playbook(pb, path=None):
    """One playbook per run: a later Done in the same run (after a change request) replaces it."""
    path = path or PLAYBOOK_FILE      # P5
    if not memory_on():
        return
    pb = {**pb, **({"mock": True} if llm.MOCK else {})}       # mock memory never reaches a live run
    keep = [x for x in load_playbooks(path) if x.get("id") != pb["id"]]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
'''),
    Edit("P5", "j2.py", r'''def clear_playbooks():
    if not os.path.exists(PLAYBOOK_FILE):
        return 0
    with open(PLAYBOOK_FILE, encoding="utf-8") as f:
        n = sum(1 for ln in f if ln.strip())
    os.remove(PLAYBOOK_FILE)
    return n
''', r'''def clear_playbooks(path=None):
    path = path or PLAYBOOK_FILE      # P5
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        n = sum(1 for ln in f if ln.strip())
    os.remove(path)
    return n
'''),
    Edit("P5", "j2.py", r'''def saved_dir(name):
    """A saved run's folder, or None. Only names like j2-20261007-101500 inside RUNS_DIR (no path tricks)."""
    if not SAVED.fullmatch(str(name or "")):
        return None
    d = os.path.join(RUNS_DIR, name)
''', r'''def saved_dir(name, runs_dir=None):
    """A saved run's folder, or None. Only names like j2-20261007-101500 inside RUNS_DIR (no path tricks)."""
    if not SAVED.fullmatch(str(name or "")):
        return None
    d = os.path.join(runs_dir or RUNS_DIR, name)       # P5: another department's runs folder
'''),
    Edit("P5", "j2.py", r'''def list_runs(limit=60):
    out = []
    for name in sorted(os.listdir(RUNS_DIR), reverse=True) if os.path.isdir(RUNS_DIR) else []:
        d = saved_dir(name)
''', r'''def list_runs(limit=60, runs_dir=None):
    runs_dir = runs_dir or RUNS_DIR       # P5
    out = []
    for name in sorted(os.listdir(runs_dir), reverse=True) if os.path.isdir(runs_dir) else []:
        d = saved_dir(name, runs_dir)
'''),
    Edit("P5", "j2.py", r'''def saved_snapshot(name, since=0):
    """The page's state for a saved run, read from its folder (read-only)."""
    d = saved_dir(name)
    if not d:
        return None
    rows = _jsonl(d, "chat.jsonl")
''', r'''def saved_snapshot(name, since=0):
    """The page's state for a saved run, read from its folder (read-only)."""
    d = saved_dir(name)
    return saved_snapshot_dir(d, name, since) if d else None


def saved_snapshot_dir(d, name, since=0):
    """P5: saved_snapshot for a folder the caller has already resolved (the server resolves it per department)."""
    rows = _jsonl(d, "chat.jsonl")
'''),
    # ---- P3: the host names the run folder and id; P8: the hooks
    Edit("P3", "j2.py", r'''class J2Run:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self):
        self.run_id = time.strftime("%Y%m%d-%H%M%S")
        self.dir = os.path.join(RUNS_DIR, "j2-" + self.run_id)
        n = 2
        while os.path.exists(self.dir):          # two runs started in the same second get separate folders
            self.dir = os.path.join(RUNS_DIR, f"j2-{self.run_id}-{n}")
            n += 1
        self.run_id = os.path.basename(self.dir)[3:]     # and separate ids (lesson and playbook ids use it)
''', r'''class J2Run:
    def __init__(self, *, run_dir=None, run_id=None, hooks=None):
        # P3: the host names the run folder (and the id); without them J2 makes a timestamp folder under RUNS_DIR.
        # P8: `hooks` is where the function nodes and the library look on (engine design 4.3); none by default.
        if run_dir is None and run_id is not None:
            raise ValueError("run_id needs run_dir: the id names a run folder the host has made")
        self.lock = threading.Lock()
        self.hooks = hooks if hooks is not None else _hooks.NullHooks()
        self._given = (os.path.abspath(os.fspath(run_dir)) if run_dir is not None else None, run_id)
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self):
        given, self._given = self._given, (None, None)       # P3: the first reset, from __init__, takes the host's folder
        if given[0]:
            self.dir = given[0]
            self.run_id = str(given[1]) if given[1] else os.path.basename(self.dir)[3:]      # as J2: the folder name without "j2-"
        else:
            self.run_id = time.strftime("%Y%m%d-%H%M%S")
            self.dir = os.path.join(RUNS_DIR, "j2-" + self.run_id)
            n = 2
            while os.path.exists(self.dir):          # two runs started in the same second get separate folders
                self.dir = os.path.join(RUNS_DIR, f"j2-{self.run_id}-{n}")
                n += 1
            self.run_id = os.path.basename(self.dir)[3:]     # and separate ids (lesson and playbook ids use it)
'''),
    Edit("P8", "j2.py", r'''        self.turn, self.handoff, self.outcome = None, {}, None
''', r'''        self.turn, self.handoff, self.outcome = None, {}, None
        self.turn_no = 0            # P8: turns taken in this run, for the hooks
'''),
    # ---- P8: the hook machinery, after _event
    Edit("P8", "j2.py", r'''        self.events.append({"agent": agent, "type": kind, "detail": detail, "msg": len(self.chat) + 1,
                            "cycle": self.cycle, **extra})

    def _raise_budget(self, add, why):
''', r'''        self.events.append({"agent": agent, "type": kind, "detail": detail, "msg": len(self.chat) + 1,
                            "cycle": self.cycle, **extra})

    # ------------------------------------------------------------------ P8: hooks (engine design 4.3)
    def _hook(self, name, *args, **kw):
        """Call one hook and return what it returns. A hook only observes: its error goes to stderr and never reaches the
        run, unless it is fatal (`fatal = True`, or a class named RecordRejected: the library's strict mode)."""
        fn = getattr(self.hooks, name, None)
        if fn is None or type(self.hooks) is _hooks.NullHooks:
            return None
        try:
            return fn(*args, **kw)
        except Exception as e:  # noqa: BLE001
            if getattr(e, "fatal", False) or type(e).__name__ == "RecordRejected":
                raise
            print(f"hook {name} failed: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr)
            return None

    def _observed(self):
        return type(self.hooks) is not _hooks.NullHooks

    def _status_snap(self):
        """What run_status gets: the snapshot's own keys for the state of the run, not the whole snapshot."""
        return {"status": self.status, "done": self.done, "turn": self.turn, "step": self.step, "cycle": self.cycle,
                "calls": self.calls, "error": self.error, "outcome": self.outcome,
                "paused": {"kind": self.paused["kind"], "msg": self.paused["msg"]} if self.paused else None}

    def _run_status(self):
        if self._observed():
            self._hook("run_status", self._status_snap())

    def _ask_tag(self, fn, purpose, call_no=0, atom=None):
        """P7: the CallTag fields of one model call. call_no is the id in calls.jsonl (0: J2 does not log the call)."""
        return {"function": fn, "role": "builder" if is_wf_agent(fn) else None, "purpose": purpose, "step": self.step,
                "cycle": self.cycle, "stage": self.stage_kind or self.output, "call_no": call_no, "atom": atom}

    def _turn_info(self, fn, kind, step):
        tag = llm.current_tag()      # the host's base tag: the orchestrator's run id, department and task
        return _hooks.TurnInfo(
            run_id=tag.run_id or self.run_id, dept_id=tag.dept_id, task_id=tag.task_id, turn_no=self.turn_no, function=fn,
            kind=kind, step=step, step_label=STEPS.get(step, ""), cycle=self.cycle, stage=self.stage_kind or self.output,
            task=str(self.handoff.get("why") or kind or ""),
            context=[tuple(p) for p in self._inputs(fn, "") if p[0] != "task"])

    def _turn_ended(self, info, mark, exc):
        if info is None:
            return
        try:
            chat0, calls0, events0 = mark
            events = self.events[events0:]
            notes = [f"{e['type']}: {e['detail']}" for e in events][:20]
            if exc is not None:
                result, notes = "error", [f"{type(exc).__name__}: {str(exc)[:300]}"] + notes
            elif self.paused:
                result = "paused"
            elif self.relay or any(e["type"] in ("redirect", "invalid_move", "repeat") for e in events):
                result = "redirected"
            else:
                result = "ok"
            out = _hooks.TurnOutcome(result=result, next=self.turn, messages=[m["id"] for m in self.chat[chat0:]],
                                     calls=[c["id"] for c in self.call_log if c["id"] > calls0], notes=notes)
        except Exception as e:  # noqa: BLE001
            print(f"hook turn_finished: could not describe the turn: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr)
            return
        try:
            self._hook("turn_finished", info, out)
        except Exception:
            if exc is None:      # a fatal hook error stops the run, but never hides the error that ended the turn
                raise

    def _dispatch_turn(self):
        """One agent turn. P8: turn_started before it and turn_finished after it (also when it raises). P7: every model call
        of the turn carries its function, step, cycle and stage; a helper call (planner, judge) names only its purpose."""
        self.turn_no += 1
        fn = "adaptation" if self.turn == "change" else self.turn      # a charter-change turn is Adaptation's
        kind = self.handoff.get("kind") or ("change" if self.turn == "change" else None)
        step = turn_step(fn, kind, self.step)
        mark, info = (len(self.chat), self.calls, len(self.events)), None
        if self._observed():
            try:
                info = self._turn_info(fn, kind, step)
            except Exception as e:  # noqa: BLE001  describing a turn can never stop it
                print(f"hook turn_started: could not describe the turn: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr)
            if info is not None:
                self._hook("turn_started", info)
        try:
            with llm.tagged(function=fn, step=step, cycle=self.cycle, stage=self.stage_kind or self.output,
                            **({"purpose": "change"} if self.turn == "change" else {})):
                if is_wf_agent(self.turn):
                    self._turn_workflow_agent(self.handoff)
                else:
                    getattr(self, "_turn_" + self.turn)(self.handoff)
        except BaseException as e:
            self._turn_ended(info, mark, e)
            raise
        self._turn_ended(info, mark, None)

    def _call_finished(self, rec, reply, meta):
        try:
            info = _hooks.CallInfo(
                call_no=rec["id"], function=rec["fn"], step=rec["step"], stage=self.stage_kind or self.output,
                purpose="agent_turn", model=rec["model"], provider=meta.get("provider"), tokens=rec["tokens"],
                usd=meta.get("usd"), seconds=rec["seconds"], session_id=meta.get("session_id"), inputs=rec["inputs"],
                reply=copy.deepcopy(reply) if isinstance(reply, dict) else None, reason=rec["reason"],
                atom=self.atom or llm.bound_atom())
        except Exception as e:  # noqa: BLE001
            print(f"hook call_finished: could not describe the call: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr)
            return
        self._hook("call_finished", info)

    def _raise_budget(self, add, why):
'''),
    # ---- P8: post, save
    Edit("P8", "j2.py", r'''            f.write(json.dumps(m, ensure_ascii=False) + "\n")
        return m

    def _all_wfs(self):
''', r'''            f.write(json.dumps(m, ensure_ascii=False) + "\n")
        if meta.get("act") != "ASK_REQUESTER":      # P8: _ask_user tells the hook itself, once `paused` is set
            self._hook("message_posted", m)
        return m

    def _all_wfs(self):
'''),
    Edit("P8", "j2.py", r'''        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    COST_KEYS =''', r'''        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._hook("record_saved", name, data)      # P8: warnings only; the library's strict mode raises a fatal error

    COST_KEYS ='''),
    # ---- P9, P7: call()
    Edit("P9", "j2.py", r'''        system = system_prompt(fn, reply_format, self._builder_for(fn))
        if self.calls and call_delay():
            time.sleep(call_delay())
        self.calls += 1
        self.thinking = fn
''', r'''        system = system_prompt(fn, reply_format, self._builder_for(fn))
        if self._observed():      # P9: empty unless a node-context file names text for this function
            addendum = self._hook("system_addendum", fn)
            system += addendum if isinstance(addendum, str) else ""
        if self.calls and call_delay():
            time.sleep(call_delay())
        self.calls += 1
        self.thinking = fn
'''),
    Edit("P7", "j2.py", r'''                    raw = llm.ask(system, user, mock, max_tokens=max_tokens, effort="low" if json_reply else "high",
                                  json_mode=json_reply, images=images, schema=schema, timeout=timeout, tools=tools)
                    break
''', r'''                    raw = _ask(self._ask_tag(fn, "agent_turn", self.calls, self.atom or None), system, user, mock,
                               max_tokens=max_tokens, effort="low" if json_reply else "high", json_mode=json_reply,
                               images=images, schema=schema, timeout=timeout, tools=tools)
                    break
'''),
    Edit("P7", "j2.py", r'''        self.summary = llm.ask(
            "You keep a running summary of a team's group chat.''', r'''        self.summary = _ask(self._ask_tag("summariser", "summary"),
            "You keep a running summary of a team's group chat.'''),
    # ---- P8: _log_call
    Edit("P8", "j2.py", r'''               "seconds": round(secs, 2), "model": None if llm.MOCK else meta.get("model") or llm.MODEL,
''', r'''               "seconds": round(secs, 2), "model": None if llm.MOCK else meta.get("model") or llm.MODEL,
               "provider": meta.get("provider"), "usd": meta.get("usd"),      # P8: additive fields (None in mock mode)
'''),
    Edit("P8", "j2.py", r'''            f.write(json.dumps({**rec, "system": system, "prompt": user, "raw": raw}, ensure_ascii=False) + "\n")
        return rec
''', r'''            f.write(json.dumps({**rec, "system": system, "prompt": user, "raw": raw}, ensure_ascii=False) + "\n")
        if self._observed():
            self._call_finished(rec, reply, meta)      # P8
        return rec
'''),
    # ---- P8: _ask_user
    Edit("P8", "j2.py", r'''        self.paused = {"kind": kind, "questions": questions, "to": to, "handoff": handoff or {}, "msg": m["id"]}
''', r'''        self.paused = {"kind": kind, "questions": questions, "to": to, "handoff": handoff or {}, "msg": m["id"]}
        self._hook("message_posted", m, questions=self.paused["questions"])      # P8: post() left this message to us
'''),
    # ---- P4, P11 (and P8): the entry points
    Edit("P4", "j2.py", r'''    def user_says(self, text):
        with self.lock:
            if self.status == "running":
                return False
            key = os.getenv("J2_OVERRIDE_KEY")
            if key and str(text).strip().startswith(key):
                return self._override(str(text).strip()[len(key):].strip())   # the key is never posted or stored
            self.post("user", text, **({"change": True} if self.done and not self.paused else {}))
            if self.done:
                self.done = False
                if not self.paused:          # an answer to Identity's questions is not a change request
                    self.feedback = text
            self.status = "running"
            threading.Thread(target=self._run_safe, daemon=True).start()
            return True
''', r'''    def user_says(self, text):
        # P4: False at once when the run holds the lock. J2 took `with self.lock` BEFORE it looked at the status, and the run
        # thread holds that lock for the whole run, so a call mid-run waited (1.21 s measured) and then started a new turn.
        if not self.lock.acquire(blocking=False):
            return False
        try:
            if self.status == "running":
                return False
            key = os.getenv("J2_OVERRIDE_KEY")
            if key and str(text).strip().startswith(key):
                return self._override(str(text).strip()[len(key):].strip())   # the key is never posted or stored
            self.post("user", text, **({"change": True} if self.done and not self.paused else {}))
            if self.done:
                self.done = False
                if not self.paused:          # an answer to Identity's questions is not a change request
                    self.feedback = text
            self.status = "running"
            self._run_status()      # P8
            threading.Thread(target=self._run_safe, daemon=True).start()
            return True
        finally:
            self.lock.release()

    def apply_override(self, cmd):
        """P4: the owner's override command (budget +N, ship, drop <item>) without the key: the server checked the key and
        the host passes the command. False at once while the run holds the lock or is running; True once it has been handled."""
        if not self.lock.acquire(blocking=False):
            return False
        try:
            if self.status == "running":
                return False
            return self._override(str(cmd).strip())
        finally:
            self.lock.release()
'''),
    # ---- P11: continue a finished run
    Edit("P11", "j2.py", r'''    def _override(self, cmd):
''', r'''    def rehydrate(self, src_dir):
        """P11: continue a finished run from its folder (rehydrate.py): the team keeps its charter, workflows, findings and
        site, and the next message is a change request. Raises RehydrateRefused when that cannot be done."""
        from . import rehydrate as _rehydrate
        return _rehydrate.rehydrate(self, src_dir)

    def _override(self, cmd):
'''),
    # ---- P8: run end paths
    Edit("P8", "j2.py", r'''                self.post("system", f"Stopped: {self.error}")
                self.outcome = f"Crashed: {self.error}"
                try:
                    self._write_summary()      # code only, before the slow reviewer call
''', r'''                self.post("system", f"Stopped: {self.error}")
                self.outcome = f"Crashed: {self.error}"
                self._hook("run_error", getattr(e, "code", "internal") if isinstance(e, (_ModelError, llm.CallTimeout)) else "internal", self.error)
                try:
                    self._write_summary()      # code only, before the slow reviewer call
'''),
    Edit("P8", "j2.py", r'''                self.turn = None
                self.status = "waiting"

    def _run(self):
''', r'''                self.turn = None
                self.status = "waiting"
                self._run_status()      # P8

    def _run(self):
'''),
    Edit("P8", "j2.py", r'''            if is_wf_agent(self.turn):
                self._turn_workflow_agent(self.handoff)
            else:
                getattr(self, "_turn_" + self.turn)(self.handoff)
            if self.board_failed''', r'''            self._dispatch_turn()      # P8: the turn, between turn_started and turn_finished
            if self.board_failed'''),
    Edit("P8", "j2.py", r'''        self.save("timing.json", self.timing())
        self._make_report(review=not self.paused)
        self.status = "waiting"

    def timing(self):
''', r'''        self.save("timing.json", self.timing())
        self._make_report(review=not self.paused)
        self.status = "waiting"
        self._run_status()      # P8

    def timing(self):
'''),
    # ---- P7: the template generator and the reviewer
    Edit("P7", "j2.py", r'''        raw = llm.ask(system, user, mock, max_tokens=8000, effort="low", json_mode=True, schema=schema)
''', r'''        raw = _ask(self._ask_tag("template", "template"), system, user, mock, max_tokens=8000, effort="low", json_mode=True,
                   schema=schema)
'''),
    Edit("P7", "j2.py", r'''        raw = llm.ask(
            "You review one test run of J2, a department''', r'''        raw = _ask(self._ask_tag("reviewer", "review"),
            "You review one test run of J2, a department'''),
    # ---- P7 (sync 5, sync 6): the planner call (`_deliverables`, or `_run_tpl_start` which calls it) runs in `_plan_stages`, before Adaptation's turn: no function or step on it
    Edit("P7", "j2.py", r'''        chosen = self._run_tpl_start(said) if self.run_tpl else self._deliverables(said)      # J2_RUN_TEMPLATES=1: the template's stages
''', r'''        with llm.tagged(function="adaptation", step=2, cycle=self.cycle, stage=self.stage_kind or self.output):      # P7: Adaptation's planner call, made before its turn
            chosen = self._run_tpl_start(said) if self.run_tpl else self._deliverables(said)      # J2_RUN_TEMPLATES=1: the template's stages
'''),
    # ---- P14: an output that says `single` is never swapped for the documents a brief names (the project output, D128)
    Edit("P14", "j2.py", r'''        if self.stages or self.goal:
            return
        said = [self.request] + [x["answer"] for x in self.intake]''', r'''        if self.stages or self.goal or (self.out or {}).get("single"):      # P14: `single` outputs (project work) keep their output; no output yet: none
            return
        said = [self.request] + [x["answer"] for x in self.intake]'''),
    # ---- P16: Decide for me's two writes of settings.json add their key to the file the host wrote there; they no longer replace it
    Edit("P16", "j2.py", '''            self.save("settings.json", {"decide_for_me": self.auto})
''', '''            self.save("settings.json", {**(_read(self.dir, "settings.json", {}) or {}), "decide_for_me": self.auto})      # P16: the host's dump stays
'''),
    Edit("P16", "j2.py", '''                self.save("settings.json", {"decide_for_me": True})
''', '''                self.save("settings.json", {**(_read(self.dir, "settings.json", {}) or {}), "decide_for_me": True})      # P16
'''),
    # ---- P21 (D245): the host's own run files written during a builder tools call are not the builder's writes
    Edit("P21", "j2.py", r'''        outside = sorted(k for k in set(before) | set(after)
                         if not mine(k) and before.get(k) != after.get(k) and os.path.normpath(k) not in self.wrote)
        held = [k for k in after if mine(k)]
        size = sum(after[k][0] for k in held)
        over = ([f"{len(held)} files, over J2_AGENT_MAX_FILES ({tools['max_files']})"] if len(held) > tools["max_files"]
                else []) + ([f"{size} bytes, over J2_AGENT_MAX_BYTES ({tools['max_bytes']})"]
                            if size > tools["max_bytes"] else [])
        m = llm.LAST_META
''', r'''        # P21 (D245): the host writes its own run files during the call (rehydrate.HOST_FILES: the live view, the snapshot, the
        # event log); they are not the builder's, unless the CLI's own tool calls name one (then it is still a write outside)
        # (a host file's atomic-write temp file, oslayer.temp_path, is its target: caught mid-write it is the host's too)
        from sutra_app.oslayer import temp_target
        from .rehydrate import HOST_FILES
        m = llm.LAST_META
        said = json.dumps([c.get("input") for c in m.get("tool_calls") or [] if isinstance(c, dict)], ensure_ascii=False)
        host = lambda k: (lambda t: t in HOST_FILES and t not in said and os.path.join(self.dir, t) not in said)(temp_target(k) or k)
        outside = sorted(k for k in set(before) | set(after)
                         if not mine(k) and before.get(k) != after.get(k) and os.path.normpath(k) not in self.wrote and not host(k))
        held = [k for k in after if mine(k)]
        size = sum(after[k][0] for k in held)
        over = ([f"{len(held)} files, over J2_AGENT_MAX_FILES ({tools['max_files']})"] if len(held) > tools["max_files"]
                else []) + ([f"{size} bytes, over J2_AGENT_MAX_BYTES ({tools['max_bytes']})"]
                            if size > tools["max_bytes"] else [])
'''),
    # ---- P22 (D246): a real run's item covered by another workflow; the same rejection twice in a row stops the cycle
    Edit("P22", "j2.py", r'''            if left:
                self._ask_after_audit(left)
            if missing:
                return self._handoff("adaptation", kind="propose", why=(
                    f"Plan gap: the {self.out['noun']} sections {', '.join(missing)} have no registered workflow"
                    + (f" (the validator rejected: {'; '.join(refused)})" if refused else "")
                    + ". Propose the workflow(s) that write them, naming each in \"sections\"; the other sections are "
                    "registered."))
            return self._handoff("coordination", kind="schedule")
        self._say("validator", f"Rejected: {'; '.join(refused) or 'the agreed set was empty'}. Adaptation reshapes or "
                               "parks it.", "adaptation", register=False)
        self._parked("the validator registered nothing")

''', r'''            if left:
                self._ask_after_audit(left)
            # P22 (D246): a repeated rejection stops the cycle; "keep going" then builds what was registered
            nxt = ({"to": "adaptation", "handoff": {"kind": "propose", "why": (
                f"Plan gap: the {self.out['noun']} sections {', '.join(missing)} have no registered workflow"
                + (f" (the validator rejected: {'; '.join(refused)})" if refused else "")
                + ". Propose the workflow(s) that write them, naming each in \"sections\"; the other sections are "
                "registered.")}} if missing else {"to": "coordination", "handoff": {"kind": "schedule"}})
            if self._repeat_stop(nxt):
                return
            return self._handoff(nxt["to"], **nxt["handoff"])
        self._say("validator", f"Rejected: {'; '.join(refused) or 'the agreed set was empty'}. Adaptation reshapes or "
                               "parks it.", "adaptation", register=False)
        if self._repeat_stop():      # P22 (D246)
            return
        self._parked("the validator registered nothing")

'''),
    Edit("P22", "j2.py", r'''        (_late_judge), and every workflow is placed in a stage with a certainty zone (_place_wf)."""
        remaining, registered, refused, defaults = self.budget - self.spent, [], [], []
        covered = {i for x in self.workflows if x["status"] in ("registered", "held", "running", "done")
                   for i in self._wf_items(x)}
''', r'''        (_late_judge), and every workflow is placed in a stage with a certainty zone (_place_wf)."""
        remaining, registered, refused, defaults = self.budget - self.spent, [], [], []
        n0 = len(self.rejections)      # P22 (D246): this call's rejections, for "the same rejection twice in a row"
        covered = {i for x in self.workflows if x["status"] in ("registered", "held", "running", "done")
                   for i in self._wf_items(x)}
'''),
    Edit("P22", "j2.py", r'''        if plan_ix:
            batch.sort(key=lambda x: plan_ix.get(x.get("name"), 10 ** 6))
        planned = covered | {i for x in batch for i in self._covers(x)}    # every item the plan's workflows cover
        for w in batch:
            c, name = granted(w), w.get("name") or "?"
''', r'''        if plan_ix:
            batch.sort(key=lambda x: plan_ix.get(x.get("name"), 10 ** 6))
        # P22 (D246): an item a real run checks is decided by the run's receipt. A proposal without a real run that covers
        # it is refused, not the real-run workflow (runs/j2-20261118-110800-0c75: "Write run_on_sort_me.md" covered item 3,
        # which the real run of "Build sort_files.py" checks, and the script was refused four times instead)
        # a waiting workflow a proposal of this batch supersedes (named in "replaces", or the same name: _supersede) covers
        # nothing for this check, so following the refusal's advice in one batch lets the real-run workflow register
        gone = {str(r) for x in batch for r in (x.get("replaces") if isinstance(x.get("replaces"), list)
                                               else [x.get("replaces")]) if r} | {x.get("name") for x in batch}
        cover_now = {i for x in self.workflows if x["status"] in ("running", "done") or x["status"] in ("registered", "held")
                     and x["id"] not in gone and x["name"] not in gone for i in self._wf_items(x)}
        at0 = self._item_at()
        rr_by = {at0[as_int(i)]: x.get("name") or "?" for x in batch if isinstance(x.get("real_run"), dict)
                 and isinstance(x["real_run"].get("checks"), list) for i in x["real_run"]["checks"] if as_int(i) in at0}
        clash = {id(x): sorted(set(self._covers(x)) & set(rr_by)) for x in batch
                 if x.get("real_run") is None and set(self._covers(x)) & set(rr_by)}
        planned = cover_now | {i for x in batch if id(x) not in clash for i in self._covers(x)}    # every item the plan's workflows cover
        for w in batch:
            c, name = granted(w), w.get("name") or "?"
'''),
    Edit("P22", "j2.py", r'''            reason = (f"a check or report on the {self.out['label']} is Audit's job, not a workflow"
                      if w.get("kind") == "audit"
                      else f"required field(s) missing: {', '.join(missing)}" if missing
                      else "; ".join(no_atom) if no_atom
''', r'''            reason = (f"a check or report on the {self.out['label']} is Audit's job, not a workflow"
                      if w.get("kind") == "audit"
                      else (f"it covers done-when item(s) {', '.join(str(self._no_at(i)) for i in clash[id(w)])}, which "
                            f"the real run of {', '.join(sorted({repr(rr_by[i]) for i in clash[id(w)]}))} checks: a real "
                            "run's receipt decides such an item, so a workflow without a real run doesn't cover it; take "
                            "it out of covers") if id(w) in clash      # P22 (D246)
                      else f"required field(s) missing: {', '.join(missing)}" if missing
                      else "; ".join(no_atom) if no_atom
'''),
    Edit("P22", "j2.py", r'''                             "Requester's files can meet, so name them there"] if not checks
                       else [f"real_run checks item {i}, which is not a done-when item" for i in checks if as_int(i) not in at]
                       + [f"done-when item {i} is checked by the real run's receipt, so no workflow covers it: take it "
                          "out of covers and keep it in real_run checks" for i in checks if at.get(as_int(i)) in planned])
                if bad:
                    refused.append(self._reject(name, "; ".join(bad)))
''', r'''                             "Requester's files can meet, so name them there"] if not checks
                       else [f"real_run checks item {i}, which is not a done-when item" for i in checks if as_int(i) not in at]
                       + [self._cover_conflict(i, at[as_int(i)], batch, w, clash)     # P22 (D246): names the other workflow
                          or (f"done-when item {i} is checked by the real run's receipt, so no workflow covers it: take it "
                              "out of covers and keep it in real_run checks")
                          for i in checks if at.get(as_int(i)) in planned])
                if bad:      # key (D431): the rule and the item numbers, never the other workflow's name
                    refused.append(self._reject(name, "; ".join(bad), ("real_run_checks", tuple(
                        as_int(i) for i in checks) if isinstance(checks, list) else ())))
'''),
    Edit("P22", "j2.py", r'''                          + (f" The planning documents {', '.join(docs)} are not revised, so they no longer match "
                             "what is built." if docs else ""), change=c["id"])
        return registered, refused, defaults

    def _supersede(self, wf, replaces=None):
''', r'''                          + (f" The planning documents {', '.join(docs)} are not revised, so they no longer match "
                             "what is built." if docs else ""), change=c["id"])
        # P22 (D246): a rejection the validator's last call also made is a repeated failure. Amended in D431: the same
        # code-set key (the rule and code-made ids, _reject), whatever any workflow is called; the words are for display
        now = [(x["workflow"], x["reason"], json.dumps(x.get("key"))) for x in self.rejections[n0:]]
        self.repeat_rejected = [x for x in now if x[2] in {k for *_, k in getattr(self, "last_rejected", None) or []}]
        self.last_rejected = now
        return registered, refused, defaults

    def _cover_conflict(self, n, pos, batch, w, skip=()):
        """P22 (D246): the refusal when item n (at position pos), which w's real run checks, is covered by another workflow:
        it names that workflow and says the conflict is there. One still waiting (registered or held) can be superseded
        (_supersede) or replaced; one running or done can't, so the item can't be met in this run, and the same rejection
        twice in a row stops the cycle for the Requester (_repeat_stop). Another proposal of this batch (not one in skip)
        is named too. None when w covers the item itself or nothing else does."""
        if pos in self._covers(w):
            return None
        head = f"done-when item {n} is checked by this real run, but {{}} covers it, so the conflict is in {{}}: "
        old = next((x for x in self.workflows if x["status"] in ("registered", "held", "running", "done")
                    and pos in self._wf_items(x)), None)
        if old and old["status"] in ("registered", "held"):
            who = f"{old['id']} {old['name']}"
            return (head.format(who, who) + f"it is {old['status']} and not built, so supersede it (name {old['id']} in "
                    f"\"replaces\") or replace it with a workflow that doesn't cover item {n}; this workflow keeps it in "
                    "real_run checks")
        if old:
            who = f"{old['id']} {old['name']}"
            return (head.format(who, who) + f"it is {old['status']} and can't be superseded or replaced, so item {n} can't "
                    "be met by this real run in this run")
        who = next((repr(x.get("name") or "?") for x in batch if x is not w and id(x) not in skip and pos in self._covers(x)), None)
        return who and (head.format(who, who) + f"a real run's receipt decides the item, so {who} takes it out of its covers; "
                                                "this workflow keeps it in real_run checks")

    def _repeat_stop(self, resume=None):
        """P22 (D246): the validator rejected a workflow for the same reason as at its last call, so another cycle would
        likely repeat it: the cycle stops and Identity asks the Requester (a safety limit). True when it stopped."""
        rep, self.repeat_rejected = getattr(self, "repeat_rejected", None) or [], []
        if not rep:
            return False
        self.last_rejected = []
        said = "; ".join(f"{n} ({r})" for n, r, *_ in rep)
        self._event("validator", "repeat", said)
        self._handoff("identity", kind="limit", reason=f"The same failure came back twice in a row: the validator rejected "
                                                       f"{said} again, so another cycle would likely repeat it.",
                      **({"resume": resume} if resume else {}))
        return True

    def _supersede(self, wf, replaces=None):
'''),
    # ---- P23 (D247): ended_workable is true only for a clean "Done:" end (no accepted items, no real run still waiting)
    Edit("P23", "j2.py", r'''def ended_workable(run_dir):
    """A saved run ended workable: its last audit (audits.json, the board's re-checks left out) passes workable().
    False when there is no audit to read."""
    try:
        with open(os.path.join(run_dir or "", "audits.json"), encoding="utf-8") as f:
            a = [x for x in json.load(f) if isinstance(x, dict) and x.get("kind") != "recheck"]
    except (OSError, ValueError, TypeError):
        return False
    return bool(a) and workable(a[-1]) == []
''', r'''def ended_workable(run_dir):
    """A saved run ended workable: its last audit (audits.json, the board's re-checks left out) passes workable().
    False when there is no audit to read.
    P23 (D247): and only a clean end. summary.json's outcome starts "Done:" (never "Done with open items"), and the last
    audit passes with nothing taken as passing: no item the Requester accepted as it is and no item still waiting for a
    real run (workable() counts both). So a run that ended with open items is never saved as a run template, reused as a
    folder, or served by the content door."""
    try:
        with open(os.path.join(run_dir or "", "audits.json"), encoding="utf-8") as f:
            a = [x for x in json.load(f) if isinstance(x, dict) and x.get("kind") != "recheck"]
        with open(os.path.join(run_dir or "", "summary.json"), encoding="utf-8") as f:
            outcome = str((json.load(f) or {}).get("outcome") or "")
    except (OSError, ValueError, TypeError, AttributeError):
        return False
    return bool(a) and outcome.startswith("Done:") and workable({**a[-1], "accepted": [], "after_real_run": []}) == []
'''),
    # ---- P19 (sync 6, D179): the host's reviewer switch; only an explicit False turns the reviewer off
    Edit("P19", "j2.py", r'''        metrics = self._metrics()
        self.thinking = None
        metrics["ai_calls"] = self.calls + (1 if review else 0)      # counting the reviewer's call
        self.report_gen = getattr(self, "report_gen", 0) + 1
        self._save_report(metrics, {"verdict": "The reviewer is writing its notes; they appear here when done." if review
                                    else "Paused for the Requester; the reviewer runs when the run ends."})
''', r'''        off = review and self._hook("review_enabled") is False      # P19: the host's reviewer setting; only an explicit False switches it off
        review = review and not off
        metrics = self._metrics()
        self.thinking = None
        metrics["ai_calls"] = self.calls + (1 if review else 0)      # counting the reviewer's call
        self.report_gen = getattr(self, "report_gen", 0) + 1
        self._save_report(metrics, {"verdict": "The reviewer is writing its notes; they appear here when done." if review
                                    else "The reviewer is switched off in this team's settings." if off
                                    else "Paused for the Requester; the reviewer runs when the run ends."})
'''),
    # ---- P24 (D250): Priority's move is a workflow's id and its envelope; the validator charges the money limit, rejects a
    # COUNTER without one and a limit below the rate card, and tells Adaptation of any other field the move set (prompt-changing, D249)
    Edit('P24', "j2.py", r'''def granted(w):
    """Rate-card price when the rate card is on; otherwise the money Priority granted (envelope.money_limit),
    and Adaptation's estimate only if no limit was given."""
    c, _ = price(w)
''', r'''def granted(w):
    """The money Priority granted (envelope.money_limit); without a limit, the rate-card price when the rate card is on,
    else Adaptation's estimate. P24 (D250): the limit is what is charged, also with the rate card on, where the rate-card
    price is a floor the validator checks (_register), never a price put in the place of Priority's."""
    m = as_int((w.get("envelope") or {}).get("money_limit"))
    if m > 0:
        return m
    c, _ = price(w)
'''),
    Edit('P24', "j2.py", r'''    c, _ = price(w)
    if c is not None:
        return c
    m = as_int((w.get("envelope") or {}).get("money_limit"))
    return m if m > 0 else wf_cost(w)

''', r'''    c, _ = price(w)
    return c if c is not None else wf_cost(w)

'''),
    Edit('P24', "j2.py", r'''                               '"retry_limit": int, "stop_loss": str}}]')

''', r'''                               '"retry_limit": int, "stop_loss": str}}]')
    # P24 (D250): what Priority sends for each workflow it funds (both pricing turns): the proposal's id and the envelope
    PRICE_FMT = ('[{"id": str (the proposed workflow\'s id), "envelope": {"money_limit": int, "model_call_limit": int, '
                 '"time_limit_minutes": int, "retry_limit": int, "stop_loss": str}}]')

'''),
    Edit('P24', "j2.py", r'''
    PRIORITY_OWNS = ("cost", "estimate", "envelope")      # price, and the envelope: limits, approval, stop-loss

''', r'''
    PRIORITY_OWNS = ("envelope",)      # P24 (D250): Priority's move is a workflow's id and its envelope, nothing else
    NOT_SENT = ("id", "name", "cost", "estimate")      # how a move names a workflow, and what norm() adds to every one

'''),
    Edit('P24', "j2.py", r'''
    def _carry(self, wfs):
        """Priority's GRANT or COUNTER, or a ruling, echoes each workflow; only its price and envelope are Priority's.
        Code registers Adaptation's proposal (found by id, then name) with just PRIORITY_OWNS taken from the echo, so
        the grant can't drop or change a planning field (runs/j2-20261111-124718 dropped "sections";
        runs/release/j2-20261114-130736 dropped "real_run" and set covers [1]). One Adaptation never proposed is
        left as it is."""
        out = []
        for w in wfs:
''', r'''
    def _carry(self, wfs, who="The ruling", shown=None):
        """P24 (D250): a pricing move (Priority's GRANT or COUNTER, or a ruling) is each workflow's id and its envelope;
        the rest of the workflow is Adaptation's proposal (found by id, then name), so it is registered as Adaptation's
        proposal plus the move's envelope (runs/j2-20261111-124718 lost "sections" to an echo; runs/release/
        j2-20261114-130736 lost "real_run"). A field the move sends with another value than Adaptation proposed is
        neither taken nor dropped in silence: Adaptation gets a visible note naming the field and the move's value
        (runs/j2-20261118-090053-4a9c: a COUNTER added F-10 to "fixes" and was logged only as an autofix). A field the
        move leaves out is not part of it. One Adaptation never proposed is left as it is. `shown`: the table Priority
        priced (a ruling's workflows), looked up before the proposals."""
        out, said = [], []
        by = {**self.proposed_fields, **{str(k): x for x in shown or [] for k in (x.get("name"), x.get("id")) if k}}
        # the proposal's atoms carry the item numbers code tagged in place (cover_expected); an echo is compared the same way
        same = lambda k, a, b: a == b or k == "atoms" and isinstance(a, list) and \
            [cover_expected(copy.deepcopy(x)) if isinstance(x, dict) else x for x in a] == b
        for w in wfs:
'''),
    Edit('P24', "j2.py", r'''        for w in wfs:
            src = (self.proposed_fields.get(str(w.get("id"))) or self.proposed_fields.get(str(w.get("name"))) or {}) \
                if isinstance(w, dict) else {}
            if src:
''', r'''        for w in wfs:
            src = (by.get(str(w.get("id"))) or by.get(str(w.get("name"))) or {}) if isinstance(w, dict) else {}
            if src:
'''),
    Edit('P24', "j2.py", r'''            if src:
                put = sorted(k for k in set(src) | set(w) if k not in self.PRIORITY_OWNS and w.get(k) != src.get(k))
                if put:
                    self._autofix(w.get("name") or "?", "carried", "Priority's or the ruling's version dropped or changed "
                                  + ", ".join(put) + "; kept as Adaptation proposed it")
                w = {**copy.deepcopy(src), **{k: w[k] for k in self.PRIORITY_OWNS if k in w}}
''', r'''            if src:
                said += [f"{k} of '{src.get('name') or '?'}' to {json.dumps(w[k], ensure_ascii=False)[:200]}"
                         for k in sorted(w) if k not in self.PRIORITY_OWNS + self.NOT_SENT and not same(k, w[k], src.get(k))]
                w = {**copy.deepcopy(src), **{k: w[k] for k in self.PRIORITY_OWNS if k in w}}
'''),
    Edit('P24', "j2.py", r'''            out.append(w)
        return out
''', r'''            out.append(w)
        if said:
            self.post("validator", f"@Adaptation {who} also set {'; '.join(said)}. Only the envelope is theirs to set, so "
                                   "the workflow stays as you proposed it; propose a revision to make that change.",
                      audience="adaptation")
        return out
'''),
    Edit('P24', "j2.py", r'''                       "@Priority Without any content beyond listings the page feels empty. I can't accept zero.")
                return json.dumps({"say": say, "act": "REVISE", "workflows": with_atoms(offer + [stories], self.out.get("mock_atom")),
                                   "next": "Priority"})
''', r'''                       "@Priority Without any content beyond listings the page feels empty. I can't accept zero.")
                # P24 (D250): the cut to the animations is Adaptation's to make (Priority sends only a money limit of 10)
                cut = [{**w, "parts": ["interactive_feature"]} if "anim" in str(w.get("name")).lower()
                       and as_int((w.get("envelope") or {}).get("money_limit")) == 10 else w for w in offer]
                return json.dumps({"say": say, "act": "REVISE", "workflows": with_atoms(cut + [stories], self.out.get("mock_atom")),
                                   "next": "Priority"})
'''),
    Edit('P24', "j2.py", r'''                                        "the validator.")
            return self._agree(offer)
        if act == "PARK":
''', r'''                                        "the validator.")
            return self._agree(offer, counter=dec == "counter")
        if act == "PARK":
'''),
    Edit('P24', "j2.py", r'''
        def env(w):
            return {**w, "envelope": {"money_limit": w["cost"], "model_call_limit": 2, "time_limit_minutes": 10,
                                      "retry_limit": 1, "stop_loss": "stop if the build fails twice"}}

''', r'''
        def env(w):      # P24 (D250): a move names the workflow and sets its envelope, nothing else
            return {**({"id": w["id"]} if w.get("id") else {}), "name": w.get("name"),
                    "envelope": {"money_limit": w["cost"], "model_call_limit": 2, "time_limit_minutes": 10,
                                 "retry_limit": 1, "stop_loss": "stop if the build fails twice"}}

'''),
    Edit('P24', "j2.py", r'''            if self.cycle == 1 and len(table) >= 4 and any("stories" in w["name"].lower() for w in table):
                offer = [env({**w, "parts": ["interactive_feature"], "cost": 10} if "anim" in w["name"].lower() else w)
                         for w in table if "stories" not in w["name"].lower()]
''', r'''            if self.cycle == 1 and len(table) >= 4 and any("stories" in w["name"].lower() for w in table):
                offer = [env({**w, "cost": 10} if "anim" in w["name"].lower() else w)
                         for w in table if "stories" not in w["name"].lower()]
'''),
    Edit('P24', "j2.py", r'''        fmt = ('{"say": str (address @Adaptation), "decision": "GRANT"|"COUNTER"|"REFUSE", '
               '"workflows": ' + self.GRANT_FMT + ' (what you fund, each with its envelope; for COUNTER, your '
               'smaller version), '
               + next_field(("adaptation", "identity"), f"Adaptation normally; Identity only once {MAX_ATTEMPTS} "
''', r'''        fmt = ('{"say": str (address @Adaptation), "decision": "GRANT"|"COUNTER"|"REFUSE", '
               '"workflows": ' + self.PRICE_FMT + ' (one entry per workflow you fund: its id and your envelope, nothing '
               'else, since the workflow itself stays as Adaptation proposed it; a COUNTER funds fewer workflows or '
               'sets a lower money_limit, and must state every money_limit), '
               + next_field(("adaptation", "identity"), f"Adaptation normally; Identity only once {MAX_ATTEMPTS} "
'''),
    Edit('P24', "j2.py", r'''                      f"Exchange {self.exchanges + 1} of {MAX_ATTEMPTS}; after that Identity rules on both final "
                      "positions." + (" Prices are fixed by the rate card: to spend less, remove parts or whole "
                                      "workflows, not the price." if RATES else "")
                      + (f" CHANGE {self.change['id']}: its planning-document revisions ({', '.join(self.change['docs'])})"
''', r'''                      f"Exchange {self.exchanges + 1} of {MAX_ATTEMPTS}; after that Identity rules on both final "
                      "positions." + (" The rate card is a floor: a money_limit below a workflow's rate-card price is "
                                      "rejected, so to spend less, fund fewer workflows." if RATES else "")
                      + (f" CHANGE {self.change['id']}: its planning-document revisions ({', '.join(self.change['docs'])})"
'''),
    Edit('P24', "j2.py", r'''            dec = str(p.get("decision") or "").lower()
            wfs = norm(p.get("workflows")) or (table if dec == "grant" else [])
            if dec != "grant":
''', r'''            dec = str(p.get("decision") or "").lower()
            wfs = self._carry(norm(p.get("workflows")), "Priority", table) or (table if dec == "grant" else [])
            if dec != "grant":
'''),
    Edit('P24', "j2.py", r'''            p = self.call("priority", fmt, task + "\nYOUR LAST REPLY GRANTED WITHOUT A PRICE: every workflow in "
                          "workflows needs its own cost (or estimated_resources.money) and envelope.money_limit. "
                          "Send the same decision again with those filled in.", mock)
        note = None
''', r'''            p = self.call("priority", fmt, task + "\nYOUR LAST REPLY GRANTED WITHOUT A PRICE: every workflow in "
                          "workflows needs its own envelope.money_limit. Send the same decision again with those "
                          "filled in.", mock)
        note = None
'''),
    Edit('P24', "j2.py", r'''                keep.pop()
            env = lambda w: {**w, "envelope": {"money_limit": w["cost"], "model_call_limit": 2, "retry_limit": 1}}
            return json.dumps({"say": f"@Adaptation Identity's ruling priced: {granted_total(keep)} of {remaining} left.",
''', r'''                keep.pop()
            env = lambda w: {**({"id": w["id"]} if w.get("id") else {}), "name": w.get("name"),      # P24 (D250)
                             "envelope": {"money_limit": w["cost"], "model_call_limit": 2, "retry_limit": 1}}
            return json.dumps({"say": f"@Adaptation Identity's ruling priced: {granted_total(keep)} of {remaining} left.",
'''),
    Edit('P24', "j2.py", r'''                               "workflows": [env(w) for w in keep]})
        p = self.call("priority", '{"say": str, "decision": "GRANT"|"COUNTER"|"REFUSE", "workflows": ' + self.GRANT_FMT
                      + ' (what you fund, each with its envelope)}',
                      f"IDENTITY RULED ON {c['id']}: {(c['identity'] or [{}])[-1].get('say')}\nTHE RULING TO PRICE: "
''', r'''                               "workflows": [env(w) for w in keep]})
        p = self.call("priority", '{"say": str, "decision": "GRANT"|"COUNTER"|"REFUSE", "workflows": ' + self.PRICE_FMT
                      + ' (one entry per workflow you fund: its id and your envelope, nothing else; a COUNTER must state '
                        'every money_limit)}',
                      f"IDENTITY RULED ON {c['id']}: {(c['identity'] or [{}])[-1].get('say')}\nTHE RULING TO PRICE: "
'''),
    Edit('P24', "j2.py", r'''        dec = str(p.get("decision") or "").lower()
        wfs = norm(p.get("workflows")) or (table if dec == "grant" else [])
        if dec == "grant":      # the same rule: an echo without a price keeps the price code computed for the ruling
''', r'''        dec = str(p.get("decision") or "").lower()
        wfs = self._carry(norm(p.get("workflows")), "Priority", table) or (table if dec == "grant" else [])
        if dec == "grant":      # the same rule: an echo without a price keeps the price code computed for the ruling
'''),
    Edit('P24', "j2.py", r'''        self._settle(c, "priority", f"Priority's final answer on Identity's ruling: {dec.upper()} {brief_list(wfs)}.")
        if wfs:
            return self._agree(wfs)
        self.conflict, self.exchanges, self.a_pos, self.p_pos = None, 0, [], []
        self._parked(f"Priority refused Identity's ruling on {c['id']} when pricing it")
''', r'''        self._settle(c, "priority", f"Priority's final answer on Identity's ruling: {dec.upper()} {brief_list(wfs)}.")
        if wfs:
            return self._agree(wfs, counter=dec == "counter")
        self.conflict, self.exchanges, self.a_pos, self.p_pos = None, 0, [], []
        self._parked(f"Priority refused Identity's ruling on {c['id']} when pricing it")
'''),
    Edit('P24', "j2.py", r'''        self._settle(c, "priority", f"The Requester kept Priority's final answer: {brief_list(wfs)}.")
        if wfs:
            return self._agree(wfs)
        self.conflict, self.exchanges, self.a_pos, self.p_pos = None, 0, [], []
        self._parked(f"the Requester kept Priority's refusal on {c['id']}")
''', r'''        self._settle(c, "priority", f"The Requester kept Priority's final answer: {brief_list(wfs)}.")
        if wfs:
            return self._agree(wfs, counter=(c.get("repricing") or {}).get("decision") == "COUNTER")
        self.conflict, self.exchanges, self.a_pos, self.p_pos = None, 0, [], []
        self._parked(f"the Requester kept Priority's refusal on {c['id']}")
'''),
    Edit('P24', "j2.py", r'''
    def _agree(self, wfs):
        self.step = 5
''', r'''
    def _agree(self, wfs, counter=False):
        self.step = 5
'''),
    Edit('P24', "j2.py", r'''        first = self.doc and not self.workflows       # a document stage's first plan
        registered, refused, defaults = self._register(wfs)
        self.cycle_registered = self.cycle_registered or bool(registered)
''', r'''        first = self.doc and not self.workflows       # a document stage's first plan
        registered, refused, defaults = self._register(wfs, counter)
        self.cycle_registered = self.cycle_registered or bool(registered)
'''),
    Edit('P24', "j2.py", r'''
    def _register(self, agreed):
        """J2.e, plain code: every proposal is checked before it is registered, including one from an Identity ruling.
''', r'''
    def _register(self, agreed, counter=False):
        """J2.e, plain code: every proposal is checked before it is registered, including one from an Identity ruling.
'''),
    Edit('P24', "j2.py", r'''        Checks: required fields present, priced from the rate card, nothing Priority refused, cost fits what's left.
        With realization on, a proposal the plan has not judged (a fix, a replacement, a relay revision) is judged first
''', r'''        Checks: required fields present, priced from the rate card, nothing Priority refused, cost fits what's left.
        P24 (D250): the money limit is charged; a COUNTER (`counter`) without one is rejected, and with the rate card on
        a limit below the rate-card price is rejected with the reason, never raised to it.
        With realization on, a proposal the plan has not judged (a fix, a replacement, a relay revision) is judged first
'''),
    Edit('P24', "j2.py", r'''                      else f"{self.p_refused[name]}, so it can't be registered" if name in self.p_refused
                      else "no rate-card parts, so it has no price" if RATES and rc is None
''', r'''                      else f"{self.p_refused[name]}, so it can't be registered" if name in self.p_refused
                      else "a counter must state its money limit"      # P24 (D250)
                      if counter and as_int((w.get("envelope") or {}).get("money_limit")) <= 0
                      else "no rate-card parts, so it has no price" if RATES and rc is None
'''),
    Edit('P24', "j2.py", r'''                      else f"unknown rate-card parts {unknown}; allowed: {', '.join(RATES)}" if unknown
                      else (f"the judge scored it {w['judge']['score']:.2f}, below the {j2_realization.THRESHOLD:.2f} gate"
''', r'''                      else f"unknown rate-card parts {unknown}; allowed: {', '.join(RATES)}" if unknown
                      else (f"its money limit {c} is below its rate-card price {rc} ({' + '.join(map(str, w['parts']))}), "
                            "the floor") if rc is not None and c < rc      # P24 (D250)
                      else (f"the judge scored it {w['judge']['score']:.2f}, below the {j2_realization.THRESHOLD:.2f} gate"
'''),
    # ---- P25 (D251): the budget cap only when J2_BUDGET_CAP is set; Decide for me never approves a raise; a raise question shows
    # the credits approved so far (prompt-changing, D249: the raise question's text)
    Edit('P25', "j2.py", r'''BUDGET = int(os.getenv("J2_BUDGET", "100"))           # starting budget
BUDGET_CAP = int(os.getenv("J2_BUDGET_CAP", str(2 * BUDGET)))   # most the Requester's approvals can raise it to
MAX_ATTEMPTS = 4           # attempts two disagreeing agents get before Identity rules (priority.md: four exchanges)
''', r'''BUDGET = int(os.getenv("J2_BUDGET", "100"))           # starting budget
# P25 (D251): the most the Requester's approvals can raise the budget to, only when J2_BUDGET_CAP is set; unset: no cap
BUDGET_CAP = int(os.environ["J2_BUDGET_CAP"]) if os.getenv("J2_BUDGET_CAP") else None


def budget_room(budget):
    """P25 (D251): how much more the Requester may approve: up to the cap when there is one, else without end."""
    return BUDGET_CAP - budget if BUDGET_CAP is not None else float("inf")


def own_number(room):
    """P25 (D251): the "type your own number" words of a raise option; "up to N" only when there is a cap."""
    return "Or type your own number" + (f", up to {room}" if BUDGET_CAP is not None else "")
MAX_ATTEMPTS = 4           # attempts two disagreeing agents get before Identity rules (priority.md: four exchanges)
'''),
    Edit('P25', "j2.py", r'''    def _raise_budget(self, add, why):
        """Only after the Requester approved more budget in answer to Identity's question; capped at BUDGET_CAP."""
        if add <= 0:
''', r'''    def _raise_budget(self, add, why):
        """Only after the Requester approved more budget in answer to Identity's question; capped at BUDGET_CAP (P25: when
        J2_BUDGET_CAP is set)."""
        if add <= 0:
'''),
    Edit('P25', "j2.py", r'''            return
        new = min(self.budget + add, BUDGET_CAP)
        if new <= self.budget:
''', r'''            return
        new = min(self.budget + add, BUDGET_CAP) if BUDGET_CAP is not None else self.budget + add
        if new <= self.budget:
'''),
    Edit('P25', "j2.py", r'''        self.raises.append({"cycle": self.cycle, "asked": add, "from": old, "to": new, "why": why})
        self._event("identity", "budget_raise", f"{old} -> {new} (asked +{add}, cap {BUDGET_CAP}; {why})")
        self.post("system", f"Budget raised on the Requester's approval: {old} -> {new}"
''', r'''        self.raises.append({"cycle": self.cycle, "asked": add, "from": old, "to": new, "why": why})
        self._event("identity", "budget_raise", f"{old} -> {new} (asked +{add}, cap {BUDGET_CAP or 'none'}; {why})")
        self.post("system", f"Budget raised on the Requester's approval: {old} -> {new}"
'''),
    Edit('P25', "j2.py", r'''                  + f". Remaining: {self.budget - self.spent}.")

''', r'''                  + f". Remaining: {self.budget - self.spent}.")

    def _so_far(self):
        """P25 (D251): the work credits the Requester has approved so far, as a sum, for a question that asks for more:
        "So far: 100 + 30 = 130 work credits approved." (the start alone when nothing was added yet)."""
        if USD_BUDGET:
            return self._usd_so_far()      # P26 (D422): in dollar mode the approved total is in dollars
        start =self.raises[0]["from"] if self.raises else self.budget
        adds = [r["to"] - r["from"] for r in self.raises]
        return "So far: " + " + ".join(str(x) for x in [start, *adds]) + (f" = {self.budget}" if adds else "") + \
            " work credits approved."

'''),
    Edit('P25', "j2.py", r'''        questions = [{**q, "options": q.get("options") or []} for q in questions]
        if kind != "limit":
''', r'''        questions = [{**q, "options": q.get("options") or []} for q in questions]
        if kind in ("approval", "ruling_budget") or any(as_int(b) > 0 for q in questions for b in q.get("budget") or []):
            questions = [{**q, "question": f"{q['question']} {self._so_far()}"} for q in questions]      # P25 (D251)
        if kind != "limit":
'''),
    Edit('P25', "j2.py", r'''            return None      # J2.g: only a decision is Decide for me's; a fact waits for the Requester
        return self._auto_choice(p)

''', r'''            return None      # J2.g: only a decision is Decide for me's; a fact waits for the Requester
        pick = self._auto_choice(p)
        # P25 (D251): every raise needs the Requester's own approval; Decide for me waits instead of approving one
        if p["kind"] in ("approval", "ruling_budget"):
            return None
        qs = p.get("questions") or []
        if pick[2] and len(qs) == 1 and as_int((qs[0].get("budget") or [0] * pick[2])[pick[2] - 1]) > 0:
            return None
        return pick

'''),
    Edit('P25', "j2.py", r'''        need = sum(c for _, c, _ in rows) - left
        room = BUDGET_CAP - self.budget
        add = min(max(need, 1), room) if room > 0 else 0
''', r'''        need = sum(c for _, c, _ in rows) - left
        room = budget_room(self.budget)
        add = min(max(need, 1), room) if room > 0 else 0
'''),
    Edit('P25', "j2.py", r'''            opts.append(f"Add {add} work credits{' (the most allowed)' if add < need else ''} and keep going: you get more "
                        f"of what you asked for built. Or type your own number, up to {room}")
            budget.append(add)
''', r'''            opts.append(f"Add {add} work credits{' (the most allowed)' if add < need else ''} and keep going: you get more "
                        f"of what you asked for built. {own_number(room)}")
            budget.append(add)
'''),
    Edit('P25', "j2.py", r'''        cheapest = min(RATES.values()) if RATES else 1
        room = BUDGET_CAP - self.budget
        short = self.budget - self.spent < cheapest       # whatever the limit was, nothing new can be funded
''', r'''        cheapest = min(RATES.values()) if RATES else 1
        room = budget_room(self.budget)
        short = self.budget - self.spent < cheapest       # whatever the limit was, nothing new can be funded
'''),
    Edit('P25', "j2.py", r'''            opts.append((f"Add {add} work credits{' (the most allowed)' if add < want else ''} and keep going: {more}. "
                         f"Or type your own number, up to {room}" if add else
                         f"Keep going: {more}")
''', r'''            opts.append((f"Add {fmt_usd(add)} and keep going: {more}. Or type your own amount" if add and USD_BUDGET else      # P26 (D422)
                         f"Add {add} work credits{' (the most allowed)' if add < want else ''} and keep going: {more}. "
                         f"{own_number(room)}" if add else
                         f"Keep going: {more}")
'''),
    # ---- P26 (D421, D422): dollar mode, on only when J2_USD_BUDGET is set. Part 1: each logged AI call adds its API price (the usd
    # it reported, or an estimate from its tokens) to the run's cost; no behaviour changes
    Edit('P26', "j2.py", r'''LIMIT_ADD = int(os.getenv("J2_LIMIT_ADD", "30"))    # budget the "keep working" option adds when the budget ran out
''', r'''LIMIT_ADD = int(os.getenv("J2_LIMIT_ADD", "30"))    # budget the "keep working" option adds when the budget ran out
# P26 (D421, D422): dollar mode, on only when J2_USD_BUDGET is set: a run's limit is dollars (API price), credits stay internal
USD_BUDGET = float(os.environ["J2_USD_BUDGET"]) if os.getenv("J2_USD_BUDGET") else None
USD_CAP = float(os.environ["J2_USD_CAP"]) if os.getenv("J2_USD_CAP") else None      # the most a run may be raised to; unset: no cap
USD_PER_CREDIT = 0.0187          # D421: measured on the beta's runs (median dollars per work credit)
USD_PER_MTOK_FALLBACK = 3.18     # D421: dollars per million tokens for a call with no price before any priced call in the run
USD_RAISE_SHARE = 0.5            # the suggested raise without a stated need: half the run's limit
BIG_RAISE = 5                    # a typed raise above this many times the limit is asked back
USD_RAISE_TEXT = re.compile(r"\s*add \$[\d,]+(?:\.\d{1,2})?(?: and keep going)?\.?\s*", re.I)      # what a card's raise input sends
USD_RATE_MIN_CALLS = 8           # D422: a run's own dollars per credit counts from its 8th call (the opening, 7 calls, spends none)
if USD_BUDGET:
    BUDGET = math.ceil(USD_BUDGET / USD_PER_CREDIT)      # P26 (D422): the starting credits follow the dollar limit; J2_BUDGET is ignored


def call_tokens(rec):
    """P26: a calls.jsonl row's tokens (input + output), or its characters / 4 when the call has no token count (mock mode)."""
    t = rec.get("tokens") or {}
    if t:
        return (t.get("input") or 0) + (t.get("output") or 0)
    c = rec.get("chars") or {}
    return ((c.get("prompt") or 0) + (c.get("reply") or 0)) / 4


def call_usd(rec, run_rate):
    """P26 (D421): (dollars, estimated) for one calls.jsonl row: the usd it reported (or its rate card's), else its tokens times
    `run_rate` (this run's dollars per token from its priced calls), else times USD_PER_MTOK_FALLBACK."""
    if rec.get("usd") is not None:
        return float(rec["usd"]), False
    return call_tokens(rec) * (run_rate if run_rate else USD_PER_MTOK_FALLBACK / 1_000_000), True


def fmt_usd(x):
    """P26: "$20", "$20.40", "$1.25"; a positive amount below a cent shows as "$0.01"."""
    c = max(round(x, 2), 0.01) if x > 0 else 0.0
    return f"${c:,.0f}" if c == int(c) else f"${c:,.2f}"


_USD = re.compile(r"\$\s*(\d[\d,]*(?:\.\d{1,2})?)|\b(\d[\d,]*(?:\.\d{1,2})?)\s*(?:dollars?|usd)\b", re.I)


def parse_usd(text):
    """P26: the dollar amount in an answer ("Add $10 and keep going", "$12.50", "add 10 dollars"), else None ("add 30")."""
    m = _USD.search(text or "")
    return float((m[1] or m[2]).replace(",", "")) if m else None
'''),
    Edit('P26', "j2.py", r'''        self.budget, self.raises = BUDGET, []
''', r'''        self.budget, self.raises = BUDGET, []
        # P26 (D422): the run's cost in dollar mode: used, its limit, the Requester's raises, calls estimated (by provider)
        self.usd_used, self.usd_limit, self.usd_raises = 0.0, USD_BUDGET or 0.0, []
        self.usd_estimated_calls, self.usd_estimated_by, self.usd_priced, self.usd_priced_tokens = 0, {}, 0.0, 0
'''),
    Edit('P26', "j2.py", r'''    def _log_call(self, fn, task, system, user, raw, reply, secs, tools=None):
''', r'''    def _count_usd(self, rec):
        """P26 (D421): in dollar mode, add this call's API price to the run's cost: what it reported, or an estimate at this
        run's own rate (its priced calls' dollars per token), else at USD_PER_MTOK_FALLBACK. The row keeps what was counted."""
        if not USD_BUDGET:
            return
        usd, estimated = call_usd(rec, self.usd_priced / self.usd_priced_tokens if self.usd_priced_tokens else None)
        if estimated:
            self.usd_estimated_calls += 1
            who = rec.get("provider") or "mock"
            self.usd_estimated_by[who] = self.usd_estimated_by.get(who, 0) + 1
            rec["usd_estimated"] = True
        else:
            self.usd_priced += usd
            self.usd_priced_tokens += call_tokens(rec)
        self.usd_used += usd
        rec["usd_counted"] = round(usd, 6)

    def _usd_metrics(self):
        """P26: the summary's `budget.usd` in dollar mode: used, limit, approved (the start, then each raise) and calls estimated."""
        if not USD_BUDGET:
            return {}
        start = self.usd_raises[0]["from"] if self.usd_raises else self.usd_limit
        return {"usd": {"used": round(self.usd_used, 4), "limit": self.usd_limit,
                        "approved": [start, *(r["to"] - r["from"] for r in self.usd_raises)],
                        "estimated_calls": self.usd_estimated_calls}}

    def _usd_rate(self):
        """P26 (D422): the run's one rate between dollars and work credits, used both ways: to price a raise (`_usd_raise`) and to
        turn dollars into credits (`_usd_credits`). Its own dollars per credit (dollars used / credits spent) once it has spent
        credits and made USD_RATE_MIN_CALLS calls, else USD_PER_CREDIT."""
        if self.spent > 0 and self.usd_used > 0 and len(self.call_log) >= USD_RATE_MIN_CALLS:
            return self.usd_used / self.spent
        return USD_PER_CREDIT

    def _usd_credits(self, usd, rate=None):
        """P26 (D422): the whole work credits `usd` dollars buy at `rate` (the rate a question was priced at), else the run's."""
        return math.floor(max(0.0, usd) / (rate or self._usd_rate()) + 1e-9)

    def _top_up(self, need=0):
        """P26 (D422): in dollar mode the credits follow the dollars left: code raises the budget to what they buy at the run's
        rate (`_usd_rate`; no question, no cap) and says so. True when `need` credits are free now; always False when off."""
        if not USD_BUDGET:
            return False
        want = self.spent + self._usd_credits(self.usd_limit - self.usd_used)
        if want > self.budget:
            old, self.budget = self.budget, want
            self.raises.append({"cycle": self.cycle, "asked": want - old, "from": old, "to": want,
                                "why": "code top-up from dollars left", "code": True})
            self._event("system", "budget_raise", f"{old} -> {want} (code top-up from dollars left)")
            self.post("system", f"Code added {want - old} work credits from the dollars left.")
        return self.budget - self.spent >= need

    def _usd_raise(self, budget_needed=None, rate=None):
        """P26 (D422): the dollars the raise question suggests: the credits needed at `rate` (the run's, `_usd_rate`), else
        USD_RAISE_SHARE of the limit; to the cent (to $1 above $10), at least $1, at most the cap's room. 0: no raise."""
        if budget_needed:
            x = as_int(budget_needed) * (rate or self._usd_rate())
        else:
            x = self.usd_limit * USD_RAISE_SHARE
        x = max(1.0, math.ceil(x) if x > 10 else math.ceil(x * 100) / 100)
        if USD_CAP is not None:
            x = min(x, max(0.0, USD_CAP - self.usd_limit))
        return round(x, 2)

    def _usd_so_far(self):
        """P26 (D422): "So far: $20 + $10 = $30 approved." and, when some calls had no price, " 3 calls estimated: Codex
        reports no price." (the dollar question's closing words; P25's `_so_far` returns this in dollar mode)."""
        start = self.usd_raises[0]["from"] if self.usd_raises else self.usd_limit
        adds = [r["to"] - r["from"] for r in self.usd_raises]
        out = ("So far: " + " + ".join(fmt_usd(x) for x in [start, *adds])
               + (f" = {fmt_usd(self.usd_limit)}" if adds else "") + " approved.")
        n = self.usd_estimated_calls
        if n:
            who = and_list(k.capitalize() for k in sorted(self.usd_estimated_by))
            out += f" {n} call{'s' if n != 1 else ''} estimated: {who} reports no price."
        return out

    def _usd_add(self, add, answer, rate=None):
        """P26 (D422): the Requester's dollar raise: the limit goes up (to the cap when one is set), and the dollars it adds buy
        credits at `rate`, the rate the question was priced at (`usd_rate` in its handoff), so an approved raise funds exactly what
        it was priced for; then the dollars left top credits up as usual."""
        old = self.usd_limit
        new = round(min(old + add, USD_CAP) if USD_CAP is not None else old + add, 2)
        if new <= old:
            self.post("system", f"The budget is at its cap ({fmt_usd(old)}, API price): nothing was added.")
            return
        self.usd_limit = new
        self.usd_raises.append({"cycle": self.cycle, "asked": add, "from": old, "to": new, "why": f"the Requester's answer: {answer}"})
        self._event("identity", "usd_raise", f"{fmt_usd(old)} -> {fmt_usd(new)} (asked +{fmt_usd(add)})")
        self.post("system", f"Budget raised on the Requester's approval: {fmt_usd(old)} -> {fmt_usd(new)} (API price).")
        rate = rate or self._usd_rate()
        got = self._usd_credits(new - max(old, self.usd_used), rate)      # dollars already spent past the limit buy nothing
        if got:
            was, self.budget = self.budget, self.budget + got
            self.raises.append({"cycle": self.cycle, "asked": got, "from": was, "to": self.budget,
                                "why": f"the Requester's dollar raise at ${rate:.4f} per credit", "code": True})
            self._event("system", "budget_raise", f"{was} -> {self.budget} (the Requester's dollar raise at ${rate:.4f} per credit)")
        self._top_up()

    def _usd_confirm(self, q, h, typed):
        """P26 (D422): a typed raise above BIG_RAISE times the limit is asked back: the same question, its continue option
        now the typed amount; a click on it, or the same amount sent again (`confirm_usd`, the card's button), confirms."""
        i = (h.get("choices") or []).index("continue")
        opts, budget = list(q.get("options") or []), list(q.get("budget") or [0] * len(q.get("options") or []))
        opts[i], budget[i] = re.sub(r"^Add \$[\d,.]+", f"Add {fmt_usd(typed)}", opts[i]), typed
        question = re.sub(r"Add \$[\d,.]+\?", f"Add {fmt_usd(typed)}?", q.get("question", "").split(" So far: ")[0])
        self._event("identity", "usd_big_raise", f"typed {fmt_usd(typed)}, limit {fmt_usd(self.usd_limit)}")
        self._ask_user(f"You typed {fmt_usd(typed)}, more than {BIG_RAISE} times this run's limit of {fmt_usd(self.usd_limit)}. "
                       "Pick it to confirm, or choose another option.",
                       [{**q, "question": question, "options": opts, "budget": budget}], "limit",
                       handoff={**{k: v for k, v in h.items() if k not in ("answer", "asked")}, "confirm_usd": typed})

    def _usd_ruling_reask(self, c, h, typed, short=False):
        """P26 (D422, R2-2): the ruling's dollar question asked again. "Add $0" adds nothing and an amount that funds less than the
        ruling (`short`) is asked again with the amount offered; a typed raise above BIG_RAISE times the limit comes back with that
        amount as its first option, and Approve (or the same amount sent again) confirms it. The stored question stays the first one."""
        q = c["user_question"]
        keep = {k: v for k, v in h.items() if k not in ("answer", "asked", "confirm_usd")}
        if typed and not short:
            q = {**q, "question": re.sub(r"Add \$[\d,.]+ so", f"Add {fmt_usd(typed)} so", q["question"], count=1),
                 "options": [re.sub(r"^Add \$[\d,.]+", f"Add {fmt_usd(typed)}", q["options"][0]), *q["options"][1:]],
                 "budget": [typed, 0]}
            keep.update(usd=typed, confirm_usd=typed)
            self._event("identity", "usd_big_raise", f"typed {fmt_usd(typed)}, limit {fmt_usd(self.usd_limit)}")
            say = (f"You typed {fmt_usd(typed)}, more than {BIG_RAISE} times this run's limit of {fmt_usd(self.usd_limit)}. Approve it "
                   "to confirm, or choose another option.")
        else:
            keep["usd"] = (q.get("budget") or [h.get("usd")])[0]      # the amount first offered
            say = (f"{fmt_usd(typed)} does not fund the ruling in full: it needs {fmt_usd(keep['usd'])}. Approve that amount, type "
                   "another, or go with Priority's final answer." if short else "Add $0 adds nothing. Approve the amount offered, "
                   "type another, or go with Priority's final answer.")
        self._ask_user(say, [q], "ruling_budget", conflict=c["id"], auto=True, handoff=keep)

    def _log_call(self, fn, task, system, user, raw, reply, secs, tools=None):
'''),
    Edit('P26', "j2.py", r'''        self.call_log.append(rec)
''', r'''        self._count_usd(rec)      # P26 (D421): before the row is written, so calls.jsonl says what was counted
        self.call_log.append(rec)
'''),
    Edit('P26', "j2.py", r'''"spent": self.spent, "rate_card": bool(RATES)},
''', r'''"spent": self.spent, "rate_card": bool(RATES), **self._usd_metrics()},      # P26
'''),
    Edit('P26', "j2.py", r'''"budget": {"start": BUDGET, "granted": self.budget, "used": self.spent, "raises": self.raises},''',
         r'''"budget": {"start": BUDGET, "granted": self.budget, "used": self.spent, "raises": self.raises, **self._usd_metrics()},      # P26'''),
    # ---- P26 part 2 (D422): the dollar limit. Credits follow the dollars left wherever J2 asked for credits (code top-ups);
    # only the dollar limit asks the Requester, in dollars; Decide for me never answers it (prompt-changing in dollar mode, D249)
    Edit('P26', "j2.py", r'''                elif self.goal and self.budget - self.spent < cheapest:
''', r'''                elif self.goal and not self._top_up(cheapest) and self.budget - self.spent < cheapest:      # P26: dollars left first
'''),
    Edit('P26', "j2.py", r'''            if self.cycle_turns >= self._turn_cap() and self.handoff.get("kind") != "limit" and not j2h:
''', r'''            # P26 (D422): the dollar limit, checked between turns (a turn in progress may pass it); the answer to it is let through
            if USD_BUDGET and self.usd_used >= self.usd_limit and self.handoff.get("kind") not in ("limit", "requester_answered") \
                    and not j2h:
                self._handoff("identity", kind="limit", usd=True, reason=f"Dollar limit: this run has used {fmt_usd(self.usd_used)} "
                                                                         f"of {fmt_usd(self.usd_limit)} (API price).")
                continue
            if self.cycle_turns >= self._turn_cap() and self.handoff.get("kind") != "limit" and not j2h:
'''),
    Edit('P26', "j2.py", r'''        env, remaining = w.get("envelope") or {}, self.budget - self.spent
''', r'''        if USD_BUDGET and not w.get("charged"):      # P26 (D422): the dollars left fund it before Priority can hold it (R2-1)
            self._top_up(w["cost"])
        env, remaining = w.get("envelope") or {}, self.budget - self.spent
'''),
    Edit('P26', "j2.py", r'''        need = max(0, w["cost"] - (self.budget - self.spent))
        if answer:
''', r'''        need = max(0, w["cost"] - (self.budget - self.spent))
        if not answer and need > 0 and USD_BUDGET:      # P26 (D422): the dollars left fund it, else the dollar question
            if self._top_up(w["cost"]):
                return self._handoff("priority", kind="envelope", wid=w["id"])
            return self._handoff("identity", kind="limit", usd=True, budget_needed=w["cost"] - (self.budget - self.spent),
                                 reason=f"Dollar limit: running {w['name']} needs more than the dollars left fund "
                                        f"({fmt_usd(self.usd_used)} of {fmt_usd(self.usd_limit)} used, API price).",
                                 resume={"to": "priority", "handoff": {"kind": "envelope", "wid": w["id"]}})
        if answer:
'''),
    Edit('P26', "j2.py", r'''        cost = granted_total(table)
        if cost > remaining:
''', r'''        cost = granted_total(table)
        if cost > remaining and self._top_up(cost):      # P26 (D422): the dollars left fund the ruling, as choice 1 of the question does
            self.p_refused = {}
            self._settle(c, c["pending_winner"], "Code funded Identity's ruling from the dollars left: it goes to the validator.")
            return self._agree(c["ruled_wfs"])
        usd_rate = self._usd_rate() if USD_BUDGET else None      # P26 (D422): the rate this question is priced at, carried to its answer
        usd = self._usd_raise(cost - (self.budget - self.spent), usd_rate) if USD_BUDGET and cost > remaining else 0
        if cost > remaining and (usd or not USD_BUDGET):      # P26: at the dollar cap nothing can be added; Priority's answer stands
'''),
    Edit('P26', "j2.py", r'''        need, have = self._change_cost(rows), self.budget - self.spent
        if need > have:
''', r'''        need, have = self._change_cost(rows), self.budget - self.spent
        if need > have and not self._top_up(need):      # P26 (D422): the dollars left fund the change first
'''),
    Edit('P26', "j2.py", r'''        twice = [c for c in left if len(self.deferred[c]) >= 2]
        need = sum(item_min(c, self.goal) for c in left) - (self.budget - self.spent)
''', r'''        twice = [c for c in left if len(self.deferred[c]) >= 2]
        self._top_up(sum(item_min(c, self.goal) for c in left))      # P26 (D422): the dollars left fund what a ruling left out first
        need = sum(item_min(c, self.goal) for c in left) - (self.budget - self.spent)
'''),
    Edit('P26', "j2.py", r'''        want = max(as_int(h.get("budget_needed")) or LIMIT_ADD, cheapest)
        add = min(want, room) if short or h.get("budget_needed") else 0
''', r'''        want = max(as_int(h.get("budget_needed")) or LIMIT_ADD, cheapest)
        add = min(want, room) if short or h.get("budget_needed") else 0
        usd, need = False, h.get("budget_needed")
        if USD_BUDGET:      # P26 (D422): credits follow the dollars left; a raise is the dollar question, in dollars
            if need and not h.get("usd") and self._top_up(as_int(need)):
                need = None      # the dollars left fund what was asked for: no raise to ask
            short = bool(h.get("usd")) or not self._top_up(cheapest)
            usd = short or bool(need)
            usd_rate = self._usd_rate()      # the rate this question is priced at, carried to its answer (usd_rate)
            add = want = self._usd_raise(need, usd_rate) if usd else 0
'''),
    Edit('P26', "j2.py", r'''        if (not short or self.budget + add - self.spent >= cheapest) and not stale and (add or not h.get("budget_needed")):
''', r'''        if (not short or (add > 0 if USD_BUDGET else self.budget + add - self.spent >= cheapest)) and not stale \
                and (add or not (need if USD_BUDGET else h.get("budget_needed"))):      # P26: a dollar raise funds keep going
'''),
    Edit('P26', "j2.py", r'''        q["question"] = str(r.get("question") or "").strip() or q["question"]
''', r'''        q["question"] = str(r.get("question") or "").strip() or q["question"]
        if usd:      # P26 (D422): the dollar question is code's own words; P25 adds what was approved so far
            q["question"] = (f"This run has used {fmt_usd(self.usd_used)} of {fmt_usd(self.usd_limit)} (API price)."
                             + (f" Add {fmt_usd(add)}?" if "continue" in choices and add else f" {ask[0].upper() + ask[1:]}?"))
'''),
    Edit('P26', "j2.py", r'''        handoff = {"kind": "requester_answered", "limit": reason, "choices": choices, "resume": resume,
''', r'''        handoff = {"kind": "requester_answered", "limit": reason, "choices": choices, "resume": resume, **({"usd": True, "usd_rate": usd_rate} if usd else {}),
'''),
    Edit('P26', "j2.py", r'''            add = max(0, as_int(r.get("add"))) or None
''', r'''            add = max(0, as_int(r.get("add"))) or None
            if h.get("usd"):      # P26 (D422): code reads a typed dollar amount, never the model's credits; a click takes the option's
                add = None if ONLY_PICK.fullmatch(answer) else parse_usd(answer)
                if add == 0:
                    decision = None      # "Add $0" is no raise and names no option: asked again
                if add and "continue" in choices and decision in (None, "continue"):
                    decision = "continue"
'''),
    Edit('P26', "j2.py", r'''                add = q["budget"][choices.index("continue")] or None       # the option's own amount
''', r'''                add = q["budget"][choices.index("continue")] or None       # the option's own amount
            if h.get("usd") and add and decision == "continue" and not ONLY_PICK.fullmatch(answer) and add > BIG_RAISE * self.usd_limit \
                    and add != h.get("confirm_usd"):
                return self._usd_confirm(q, h, add)      # P26 (D422): a typed raise over 5x the limit is asked back, once
'''),
    Edit('P26', "j2.py", r'''        if add and decision != "ship":
            self._raise_budget(add, f"the Requester's answer: {answer}")
''', r'''        if add and decision != "ship":
            if h.get("usd"):
                self._usd_add(add, answer, h.get("usd_rate"))      # P26 (D422)
            else:
                self._raise_budget(add, f"the Requester's answer: {answer}")
'''),
    Edit('P26', "j2.py", r'''(f" and add {add} work credits" if add and
''', r'''(f" and add {fmt_usd(add) if h.get('usd') else str(add) + ' work credits'}" if add and
'''),
    Edit('P26', "j2.py", r'''"choices", "failing_items", "resume", "drop_texts",
                                          "drop_named"))''', r'''"choices", "failing_items", "resume", "drop_texts",
                                          "drop_named", "usd", "confirm_usd", "usd_rate"))'''),
    Edit('P26', "j2.py", r'''        p = self.paused
        if not (self.auto and p) or p["kind"] in AUTO_ASK or len(self.auto_log) >= AUTO_CAP:
            return None
''', r'''        p = self.paused
        if not (self.auto and p) or p["kind"] in AUTO_ASK or len(self.auto_log) >= AUTO_CAP:
            return None
        if (p.get("handoff") or {}).get("usd"):
            return None      # P26 (D422): only the Requester answers the dollar question
'''),
    Edit('P26', "j2.py", r'''"auto_waits": self.paused["kind"] in AUTO_ASK,''',
         r'''"auto_waits": self.paused["kind"] in AUTO_ASK or bool(self.paused["handoff"].get("usd")),'''),
    Edit('P26', "j2.py", r'''                             f"Go with Priority's final answer ({dec.upper()}): {brief_list(wfs)}"]}
            c.update(user_question=q, escalated_to_user=True)
''', r'''                             f"Go with Priority's final answer ({dec.upper()}): {brief_list(wfs)}"]}
            if USD_BUDGET:      # P26 (D422): the dollar question; choice 1 raises the dollar limit, never credits
                names = lambda ws: and_list(x.get("name") for x in ws) or "nothing"
                q = {"question": f"This run has used {fmt_usd(self.usd_used)} of {fmt_usd(self.usd_limit)} (API price). Add "
                                 f"{fmt_usd(usd)} so Identity's ruling is funded in full?",
                     "options": [f"Add {fmt_usd(usd)} so the ruling is funded in full: {names(table)}",
                                 f"Go with Priority's final answer ({dec.upper()}): {names(wfs)}"], "budget": [usd, 0]}
            c.update(user_question=q, escalated_to_user=True)
'''),
    # P26 (D422, R2-2): the ruling's dollar question keeps its amount ("[adds $Z]"), so its card takes a typed amount too
    Edit('P26', "j2.py", r'''            questions = [{k: v for k, v in q.items() if k != "budget"} for q in questions]
''', r'''            questions = [{k: v for k, v in q.items() if k != "budget" or (kind == "ruling_budget" and USD_BUDGET)}
                         for q in questions]
'''),
    Edit('P26', "j2.py", r'''        c, answer, need = self._conflict(h.get("conflict")), h.get("answer"), as_int(h.get("need"))
        c["user_answer"] = answer
''', r'''        c, answer, need = self._conflict(h.get("conflict")), h.get("answer"), as_int(h.get("need"))
        # P26 (D422, R2-2): a typed dollar amount: "Add $0" and an amount that funds less than the ruling are asked again, one over
        # BIG_RAISE times the limit is asked back once; it is the raise only when the Requester chose to add (below)
        typed = parse_usd(answer) if h.get("usd") and not ONLY_PICK.fullmatch(answer or "") else None
        if typed is not None:
            buys = self._usd_credits(typed - max(0.0, self.usd_used - self.usd_limit), h.get("usd_rate"))
            if typed == 0 or buys < need:
                return self._usd_ruling_reask(c, h, typed, short=bool(typed))
            if typed > BIG_RAISE * self.usd_limit and typed != h.get("confirm_usd"):
                return self._usd_ruling_reask(c, h, typed)
        c["user_answer"] = answer
'''),
    Edit('P26', "j2.py", r'''        if as_int(r.get("choice")) == 1:
''', r'''        if typed and (as_int(r.get("choice")) == 1 or USD_RAISE_TEXT.fullmatch(answer)):      # P26 (D422): the card's own raise
            r["choice"], h = 1, {**h, "usd": typed}                                         # text is choice 1; a refusal never raises
        if as_int(r.get("choice")) == 1:
'''),
    Edit('P26', "j2.py", r'''"need": need},''', r'''"need": need, **({"usd": usd, "usd_rate": usd_rate} if USD_BUDGET else {})},'''),
    Edit('P26', "j2.py", r'''            self._raise_budget(need, f"{c['id']} ruling")
''', r'''            if h.get("usd"):
                self._usd_add(h["usd"], answer, h.get("usd_rate"))      # P26 (D422)
            else:
                self._raise_budget(need, f"{c['id']} ruling")
'''),
    # P26 (D422): a document chain's shortfall: the dollars left fund it first, then the dollar question (R1-4)
    Edit('P26', "j2.py", r'''        left, todo = self.budget - self.spent, self.stages[i:]
''', r'''        self._top_up()      # P26 (D422): the dollars left fund the chain first
        left, todo = self.budget - self.spent, self.stages[i:]
'''),
    Edit('P26', "j2.py", r'''        opts, budget, choices = [], [], []
        if add:
''', r'''        usd_rate = self._usd_rate() if USD_BUDGET else None      # P26 (D422): the rate this question is priced at, carried to its answer
        if USD_BUDGET:
            add = self._usd_raise(need, usd_rate)      # P26 (D422): the raise is dollars
        opts, budget, choices = [], [], []
        if add and USD_BUDGET:
            opts.append(f"Add {fmt_usd(add)} and keep going: you get more of what you asked for built. Or type your own amount")
            budget.append(add)
            choices.append("continue")
        elif add:
'''),
    Edit('P26', "j2.py", r'''        shown = [f"{self._sw(k)} (needs at least {c} work credits{'' if ok else '; not covered'})" for k, c, ok in rows]
''', r'''        shown = [f"{self._sw(k)} (needs at least {c} work credits{'' if ok else '; not covered'})" for k, c, ok in rows]
        if USD_BUDGET:      # P26 (D422): the Requester reads dollars, never credits
            q["question"] = (f"This run has used {fmt_usd(self.usd_used)} of {fmt_usd(self.usd_limit)} (API price)."
                             + (f" Add {fmt_usd(add)}?" if add else f" {ask[0].upper() + ask[1:]}?"))
            shown = [f"{self._sw(k)}{'' if ok else ' (not covered)'}" for k, c, ok in rows]
'''),
    Edit('P26', "j2.py", r'''self.post("system", f"The work credits left ({left}) can't cover {names}.''',
         r'''self.post("system", f"The {'dollars' if USD_BUDGET else f'work credits ({left})'} left can't cover {names}.'''),
    Edit('P26', "j2.py", r'''        self._ask_user(f"You asked for {and_list(self._sw(k) for k in todo)}, which needs at least "
                       f"{sum(c for _, c, _ in rows)} work credits; {left} are left.", [q], "limit", gaps=shown,
''', r'''        self._ask_user(f"You asked for {and_list(self._sw(k) for k in todo)}, which needs more than the dollars left fund."
                       if USD_BUDGET else f"You asked for {and_list(self._sw(k) for k in todo)}, which needs at least "
                       f"{sum(c for _, c, _ in rows)} work credits; {left} are left.", [q], "limit", gaps=shown,
'''),
    Edit('P26', "j2.py", r'''"unfunded": short, "limit": "stages"}''', r'''"unfunded": short, "limit": "stages", **({"usd": True, "usd_rate": usd_rate} if USD_BUDGET else {})}'''),
    Edit('P26', "j2.py", r'''"choices", "unfunded", "limit"))''', r'''"choices", "unfunded", "limit", "usd", "confirm_usd", "usd_rate"))'''),
    Edit('P26', "j2.py", r'''        add = d.get("add") or (q.get("budget")[choices.index("continue")] if decision == "continue" and q.get("budget") else None)
''', r'''        add = d.get("add") or (q.get("budget")[choices.index("continue")] if decision == "continue" and q.get("budget") else None)
        if h.get("usd"):      # P26 (D422): a typed dollar amount, else the option's own; never the model's credits
            typed = None if ONLY_PICK.fullmatch(answer) else parse_usd(answer)
            if typed == 0:      # "Add $0" is no raise: asked again
                return self._reask(q, h, ("kind", "stage_i", "started", "choices", "unfunded", "limit", "confirm_usd", "usd", "usd_rate"))
            add = typed or (q["budget"][choices.index("continue")] if decision == "continue" and q.get("budget") else None)
            if typed and decision == "continue" and typed > BIG_RAISE * self.usd_limit and typed != h.get("confirm_usd"):
                return self._usd_confirm(q, h, typed)      # over 5x the limit: asked back once
'''),
    Edit('P26', "j2.py", r'''+ (f" and add {add} work credits" if add else "")''',
         r'''+ (f" and add {fmt_usd(add) if h.get('usd') else str(add) + ' work credits'}" if add else "")'''),
    Edit('P26', "j2.py", r'''        if add:
            self._raise_budget(add, f"the Requester's answer: {answer}")
        if decision == "continue":
            self.post("identity", "Got it. We'll keep going." + (f" {add} work credits added." if add else ""), to_user=True,
''', r'''        if add and h.get("usd"):
            self._usd_add(add, answer, h.get("usd_rate"))      # P26 (D422)
        elif add:
            self._raise_budget(add, f"the Requester's answer: {answer}")
        if decision == "continue":
            self.post("identity", "Got it. We'll keep going." + ((f" {fmt_usd(add)} added (API price)." if h.get("usd") else
                                                                  f" {add} work credits added.") if add else ""), to_user=True,
'''),
    # P26 (D422): Identity is told the dollar limit, never a credit one, so its words to the Requester carry no credits (R1-10)
    Edit('P26', "j2.py", r'''        reason, last = h.get("reason") or "", self.audits[-1] if self.audits else None
''', r'''        reason, last = h.get("reason") or "", self.audits[-1] if self.audits else None
        if USD_BUDGET and reason.startswith("Out of budget"):
            reason = (f"Out of budget: this run has used {fmt_usd(self.usd_used)} of {fmt_usd(self.usd_limit)} approved (API price), "
                      "and what is left does not fund the next step.")
'''),
    Edit('P26', "j2.py", r'''(f" [adds {add} work credits]" if add else "")''',
         r'''((f" [adds {fmt_usd(add)}]" if USD_BUDGET else f" [adds {add} work credits]") if add else "")'''),
    # ---- P22 amended (D431, review R1-2): every rejection carries a code-set key (its rule and code-made ids), compared by P22
    Edit("P22", "j2.py", r'''    def _reject(self, name, reason):
        """A validator rejection: counted, saved for summary.json, and posted as a system note with the exact reason."""
        self.rejections.append({"cycle": self.cycle, "workflow": name, "reason": reason})
''', r'''    def _reject(self, name, reason, key):
        """A validator rejection: counted, saved for summary.json, and posted as a system note with the exact reason.
        P22 amended (D431): key is set by code at the rejection, the rule and code-made ids only (item numbers, workflow
        ids), never a name, an agent's or the judge's words; the same rejection twice in a row is the same key."""
        self.rejections.append({"cycle": self.cycle, "workflow": name, "reason": reason, "key": json.loads(json.dumps(key))})      # as summary.json keeps it
'''),
    Edit("P22", "j2.py", r'''                refused.append(self._reject(name, f"it is not in the change plan of {self.change['id']} (change.json); "
                                                  "propose only the workflows the change plan names"))
''', r'''                refused.append(self._reject(name, f"it is not in the change plan of {self.change['id']} (change.json); "
                                                  "propose only the workflows the change plan names", ("change_plan",)))
'''),
    Edit("P22", "j2.py", r'''            why = [self._reject(n, "; ".join(m)) for n, m in bad.items()]
''', r'''            why = [self._reject(n, "; ".join(m), ("atoms_checked",)) for n, m in bad.items()]      # key: P22 (D431)
'''),
    Edit("P22", "j2.py", r'''                self._reject(f"{a['id']} corrected check", "; ".join(probs))
''', r'''                self._reject(f"{a['id']} corrected check", "; ".join(probs), ("corrected_check", a["id"]))      # key: P22 (D431)
'''),
    Edit("P22", "j2.py", r'''                bad = real_run_problems(w["real_run"], self._fact_source(), self.out.get("test_runner"), self.dir)
                if bad:
                    refused.append(self._reject(name, "; ".join(bad)))
''', r'''                bad = real_run_problems(w["real_run"], self._fact_source(), self.out.get("test_runner"), self.dir)
                if bad:
                    refused.append(self._reject(name, "; ".join(bad), ("real_run",)))      # key: P22 (D431)
'''),
    Edit("P22", "j2.py", r'''            if reason:
                refused.append(self._reject(name, reason))
                self._refused_for(w, reason)
''', r'''            if reason:
                # P22 amended (D431): the rule that fired, in the order of the reason above, with code-made ids only (the
                # done-when items of a real-run clash, the required fields); names, sections, dependencies, LLD ids, parts
                # and the judge's words stay out of the key
                # P22 amended (D431): the rule that fired, one entry per test of the reason chain above, with the same test in
                # the same order (tests/engine/test_engine_patches.py checks it from the code), and code-made ids only (the
                # done-when items of a real-run clash, the required fields); names, sections, dependencies, LLD ids, parts and
                # the judge's words stay out of the key. A reason no entry names gets its own ("unkeyed",) bucket.
                key_rules = (
                    (("audit_job",), w.get("kind") == "audit"),
                    (("real_run_covers", tuple(self._no_at(i) for i in clash.get(id(w), ()))), id(w) in clash),
                    (("missing", tuple(missing)), missing),
                    (("atom_problems",), no_atom),
                    (("dependencies",), (odd := self._unknown_deps(w, batch)) and (names := self._dep_names(batch))),
                    (("lld",), unknown_lld),
                    (("sections",), bad_secs),
                    (("no_section",), no_sec),
                    (("priority_refused",), name in self.p_refused),
                    (("counter_limit",), counter and as_int((w.get("envelope") or {}).get("money_limit")) <= 0),
                    (("no_price",), RATES and rc is None),
                    (("parts",), unknown),
                    (("floor",), rc is not None and c < rc),
                    (("judge",), (w.get("judge") or {}).get("ready") is False),
                    (("sections_cost",), c < sec_min),
                    (("cost_zero",), c <= 0),
                    (("over_budget",), reason == f"it costs {c}, over the {remaining} left in the budget"),
                    (("underpriced",), RATES))
                key = next((k for k, on in key_rules if on), ("unkeyed",))
                refused.append(self._reject(name, reason, key))
                self._refused_for(w, reason)
'''),
    # ---- P28 (D431): every build failure records a code-made signature; the same one twice in a row, across workflows, stops the cycle
    Edit("P28", "j2.py", r'''    def __init__(self, kind, detail):
        super().__init__(detail)
        self.kind = kind
''', r'''    def __init__(self, kind, detail, files=()):
        super().__init__(detail)
        self.kind = kind
        self.files = sorted(files)      # P28 (D431): every file outside the folder (the message names five), for build_failure
'''),
    Edit("P28", "j2.py", r'''            raise BuilderToolFault("outside", f"changed outside its folder: {where}")
''', r'''            raise BuilderToolFault("outside", f"changed outside its folder: {where}", files=rec["outside"])      # P28 (D431)
'''),
    Edit("P28", "j2.py", r'''def failure_signature(audit):
    return sorted(f"{r['criterion']}|{r['verdict']}" for r in audit["results"] + audit.get("rubric", []) if not r["pass"]) \
        + sorted(j2_check.problems(audit.get("mechanical") or {})) \
        + sorted(f"{c['id']}|{c['evidence']}" for c in audit.get("conditions") or [] if blocks(c))
''', r'''def failure_signature(audit):
    return sorted(f"{r['criterion']}|{r['verdict']}" for r in audit["results"] + audit.get("rubric", []) if not r["pass"]) \
        + sorted(j2_check.problems(audit.get("mechanical") or {})) \
        + sorted(f"{c['id']}|{c['evidence']}" for c in audit.get("conditions") or [] if blocks(c))


def build_failure(w):
    """P28 (D431): what a finished build failed on, judged on the failure, never on the workflow's name or words: a failed
    workflow gives (kind, detail) as code set them at the failure site (w["failure"]; an older record without one gives
    ("failed", "")); a built one whose atoms' latest receipts failed gives ("checks", sorted (check type, evidence) pairs),
    without the check's own wording or id; anything else (a pass) gives None."""
    w = w or {}
    if w.get("status") == "failed":
        kind, detail = (list(w.get("failure") or []) + ["failed", ""])[:2] if w.get("failure") else ("failed", "")
        return str(kind), tuple(sorted(map(str, detail))) if isinstance(detail, (list, tuple)) else str(detail)
    bad = {(str(r.get("type")), str(r.get("evidence"))) for a in w.get("atoms") or [] for r in a.get("results") or []
           if isinstance(r, dict) and r.get("pass") is False}
    return ("checks", tuple(sorted(bad))) if bad else None
'''),
    Edit("P28", "j2.py", r'''        self.fail_floor = 0          # audits before this index don't count for "same failure twice in a row"
''', r'''        self.fail_floor = 0          # audits before this index don't count for "same failure twice in a row"
        self.last_failure, self.repeat_steps = None, []      # P28 (D431): the last finished build's failure; the two that repeated it
'''),
    Edit("P28", "j2.py", r'''        self.write_lock = self.atom = None
        self.site_tag = kind + "-"
''', r'''        self.write_lock = self.atom = None
        self.last_failure, self.repeat_steps = None, []      # P28 (D431): a new stage's builds start fresh
        self.site_tag = kind + "-"
'''),
    Edit("P28", "j2.py", r'''            if got is None:      # code writes the failure report, so the unusable reply isn't route-checked
                self.write_lock = self.atom = None
                w["status"] = "failed"
''', r'''            if got is None:      # code writes the failure report, so the unusable reply isn't route-checked
                self.write_lock = self.atom = None
                w["status"] = "failed"
                w["failure"] = ["unusable_reply", w.get("last_check") or ""]      # P28 (D431): code's own last parse error
'''),
    Edit("P28", "j2.py", r'''        if text is None:
            w["status"] = "failed"
''', r'''        if text is None:
            w["status"] = "failed"
            w["failure"] = ["no_artifact", evidence]      # P28 (D431): code's last evidence
'''),
    Edit("P28", "j2.py", r'''        attempt, evidence, r, failed, stop, leak = 0, "", {}, [], None, ""
''', r'''        attempt, evidence, r, failed, stop, leak = 0, "", {}, [], None, ""
        fault = None      # P28 (D431): the outside-write fault, for the failure's signature
'''),
    Edit("P28", "j2.py", r'''                        stop = f"it changed files outside its folder ({e})"
''', r'''                        stop, fault = f"it changed files outside its folder ({e})", e      # P28 (D431)
'''),
    Edit("P28", "j2.py", r'''            why = stop or f"no usable build after {attempt} attempt(s)"
''', r'''            why = stop or f"no usable build after {attempt} attempt(s)"
            # P28 (D431): code's own failure: every outside file, the real-path refusal, else the last evidence (a failed
            # check always published a build first, so it never ends here)
            w["failure"] = (["outside_write", fault.files] if fault else ["real_path", leak] if leak else ["no_build", evidence])
'''),
    Edit("P28", "j2.py", r'''            remaining -= c
            env = {k: (w.get("envelope") or {}).get(k) for k in ("money_limit", "model_call_limit", "time_limit_minutes",
''', r'''            if (ids := self._redoes_repeat(w)) and not str(w.get("cause_change") or "").strip():      # P28 (D431)
                refused.append(self._reject(name, f"it redoes {and_list(ids)}, which failed the same way twice, and its "
                                                  "cause_change is empty: say what is different about the cause this time",
                                            ("cause_change", tuple(ids))))
                self._refused_for(w, "its cause_change is empty")
                continue
            remaining -= c
            env = {k: (w.get("envelope") or {}).get(k) for k in ("money_limit", "model_call_limit", "time_limit_minutes",
'''),
    Edit("P28", "j2.py", r'''            wf["atoms"] = [{**a, "id": f"{wf['id']}.a{n}"} for n, a in enumerate(atoms, 1)]
''', r'''            wf["atoms"] = [{**a, "id": f"{wf['id']}.a{n}"} for n, a in enumerate(atoms, 1)]
            if str(w.get("cause_change") or "").strip():      # P28 (D431): what is different about the cause this time
                wf["cause_change"] = str(w["cause_change"]).strip()
'''),
    Edit("P28", "j2.py", r'''        real, replan = None, self.real_replan
''', r'''        task += self._repeat_note()      # P28 (D431): only while a repeated step exists
        real, replan = None, self.real_replan
'''),
    Edit("P28", "j2.py", r'''                      + self._priority_file_note(table))
        p = self.call("priority", fmt, task, mock)
''', r'''                      + self._priority_file_note(table) + self._repeat_price_note(table))      # P28 (D431)
        p = self.call("priority", fmt, task, mock)
'''),
    Edit("P28", "j2.py", r'''    def _turn_workflow_agent(self, h):
''', r'''    def _turn_workflow_agent(self, h):
        """P28 (D431): one workflow's build (_build_workflow), then the same build failure twice in a row stops the cycle."""
        wid = h.get("wid") or self.turn
        self._build_workflow(h)
        self._repeat_build_stop(wid)

    def _repeat_build_stop(self, wid):
        """P28 (D431): the build that just finished failed exactly as the previous finished build did (build_failure: the
        failure's kind and code-made detail, never a workflow's name or words), also when it is another workflow (a
        replacement, a reworded copy): another attempt would likely repeat it, so the cycle stops and Identity asks the
        Requester (a safety limit, as P22's _repeat_stop), resuming at Adaptation's hand-off when the build had one, else
        at Coordination's queue when work waits (review R1-5). The two
        workflows become repeat_steps. A passing build clears the memory; the Requester's answer does not, so after "keep
        going" the next identical failure asks again (run 17e1 went on to W-12 and W-13). True when it stopped."""
        w = self._wf(wid)
        if not w or w.get("status") not in ("failed", "done") or self.paused:
            return False
        sig, prev = build_failure(w), self.last_failure
        if sig is None:
            self.last_failure, self.repeat_steps = None, []
            return False
        self.last_failure = {"sig": sig, "wid": wid}
        if not prev or prev["sig"] != sig or prev["wid"] == wid:
            return False
        self.repeat_steps = [prev["wid"], wid]
        words = self._failure_words(sig)
        self._event("system", "repeat", f"{prev['wid']} and {wid}: {words}")
        self.post("system", f"{prev['wid']} and {wid} failed the same way ({words}). Code stops the cycle: Identity asks the "
                            "Requester before another attempt.")
        self._handoff("identity", kind="limit", reason=f"The same failure came back twice in a row: {prev['wid']} and {wid} "
                                                       f"both failed ({words}), so another attempt would likely repeat it.",
                      **({"resume": {"to": "adaptation", "handoff": dict(self.handoff)}} if self.turn == "adaptation" else
                         {"resume": {"to": "coordination", "handoff": {"kind": "schedule"}}} if self._waiting_work() else {}))
        return True

    @staticmethod
    def _failure_words(sig):
        """P28 (D431): a build failure's signature in words, by code: every outside file, or each failed check's type and
        evidence, or the code-made detail."""
        kind, detail = sig
        return ("changed files outside its folder: " + ", ".join(detail) if kind == "outside_write" else
                "the same checks failed: " + "; ".join(f"{t}: {e}" for t, e in detail) if kind == "checks" else
                str(detail) or kind)

    def _redoes_repeat(self, p):
        """P28 (D431): the repeat_steps workflows proposal p redoes: it names one in revises or replaces, or covers one of
        its done-when items. Ids and item numbers are compared; no word of a name, and not a shared output file (nearly
        every page workflow writes index.html)."""
        rep = p.get("replaces") if isinstance(p.get("replaces"), list) else [p.get("replaces")]
        named = {str(x).upper() for x in rep + [p.get("revises")] if x}
        items = set(self._covers(p))
        return [wid for wid in self.repeat_steps if (s := self._wf(wid) or {}) and (wid in named or items & set(self._wf_items(s)))]

    def _repeat_note(self):
        """P28 (D431): Adaptation's line while a repeated step exists ("" otherwise, so its prompt is unchanged)."""
        if not self.repeat_steps:
            return ""
        a, b = self.repeat_steps
        return (f"\nA STEP FAILED THE SAME WAY TWICE: {a} and {b} failed the same way twice "
                f"({self._failure_words(build_failure(self._wf(b)) or ('failed', ''))}). A workflow that redoes this step "
                f"(names {a} or {b} in revises or replaces, or covers one of their done-when items) must carry "
                "\"cause_change\": what is different about the cause this time; without one the validator rejects it.")

    def _repeat_price_note(self, table):
        """P28 (D431): Priority's line when a proposal on the table redoes a repeated step ("" otherwise). Whether its
        cause_change names something new is Priority's judgement; code only shows it."""
        redo = {str(w.get("id") or w.get("name")): str(w.get("cause_change") or "").strip() for w in table
                if isinstance(w, dict) and self._redoes_repeat(w)}
        return (f" REDOES A STEP THAT FAILED THE SAME WAY TWICE: {json.dumps(redo, ensure_ascii=False)}. If a cause_change "
                "names nothing new about the cause, the money buys the same failure: REFUSE it with that reason." if redo else "")

    def _build_workflow(self, h):
'''),
    # ---- P29 (D431): with nothing built, no option that leaves nothing to build, and never Done without a deliverable
    # (and, follow-up: the same necessary condition unmet for the same code-made reason in two audits in a row asks the Requester)
    Edit("P29", "j2.py", r'''        same = len(recent) == 2 and failure_signature(recent[0]) == failure_signature(recent[1]) and fails
''', r'''        same = len(recent) == 2 and failure_signature(recent[0]) == failure_signature(recent[1]) and fails
        # P29 (D431): a necessary condition unmet for the same code-made reason (its id and evidence, never its wording) in two
        # audits in a row, whatever else moved, can't be met by building (runs/j2-20261123-103238-3429: C1 "the charter lists
        # no files" and C2 "the test '' is not a file in the folder" in every audit while the run kept building)
        # only a condition the charter decides (from_charter, set by code where the condition is checked: _folder_condition);
        # one the build can meet goes back to Adaptation as before (review R1-1)
        before = {(x["id"], x.get("evidence")) for x in (recent[0].get("conditions") or [] if len(recent) == 2 else [])
                  if blocks(x) and x.get("from_charter")}
        stuck = [c for c in (last or {}).get("conditions") or []
                 if blocks(c) and c.get("from_charter") and (c["id"], c.get("evidence")) in before]
'''),
    Edit("P29", "j2.py", r'''        if len(choices) < 2:
            # Never a one-option question. The only lone option is "finish as it is" (with no site, "stop here" is
            # always added, and money is never added without asking): code applies it and says so.
''', r'''        if len(choices) < 2 and self.sites:
            # With a site, the only lone option is "finish as it is" (money is never added without asking): code applies it
            # and says so. P29 (D431): with nothing built the lone option is "Stop here", and the Requester is asked, like
            # every limit question (review R1-3): a run that built nothing never ends without their word.
'''),
    Edit("P29", "j2.py", r'''            want = charter_list(g, cond.get("charter_field"))
''', r'''            want = charter_list(g, cond.get("charter_field"))
            if not want:      # P29 (D431): unmet because the charter lists none: building can't change it
                c["from_charter"] = True
'''),
    Edit("P29", "j2.py", r'''            t = (charter_list(g, cond.get("charter_field")) or [""])[0]
''', r'''            t = (charter_list(g, cond.get("charter_field")) or [""])[0]
            if not t:      # P29 (D431): the charter names no test: building can't change it
                c["from_charter"] = True
'''),
    Edit("P29", "j2.py", r'''        if fails and not facts and (same or only_tbc):
            return self._identity_limit({"reason": "Only you can close what's left: these done-when items are to be "
                                                   "confirmed." if only_tbc else
''', r'''        if fails and not facts and (same or only_tbc or stuck):
            return self._identity_limit({"reason": "Only you can close what's left: these done-when items are to be "
                                                   "confirmed." if only_tbc else
                                         "This condition comes from the charter, and building can't change it. The charter "
                                         "needs fixing." if stuck else      # P29 (D431)
'''),
    Edit("P29", "j2.py", r'''AUTO_ASK = {"send_confirm", "real_run"}
''', r'''AUTO_ASK = {"send_confirm", "real_run", "limit"}      # P29 (D431): a limit question (the same failure twice among them) is the Requester's own
'''),
    Edit("P29", "j2.py", r'''        return ["no site has been audited yet"]
''', r'''        return ["no site has been audited yet"]
    if audit.get("version") == 0:      # P29 (D431): taken before anything was built, so nothing can be workable or done
        return ["nothing has been built yet"]
'''),
    Edit("P29", "j2.py", r'''            named = named if len(kept) > 1 else []
''', r'''            named = named if len(kept) > 1 else []
        if not self.sites:      # P29 (D431): with nothing built, never a "Leave out" that leaves nothing to build (the gate item isn't)
            cut = {t for r in named for t in r.get("texts", [r["text"]])}
            named = named if [c for c in crit if c not in cut and c != GATE_TEXT] else []
'''),
    Edit("P29", "j2.py", r'''        if self.decisions and limit:
''', r'''        if limit and gone and not self.sites and not [c for c in crit if c not in gone and c != GATE_TEXT]:
            # P29 (D431): a typed answer that leaves out everything still to build, with nothing built, is a stop, never a
            # finished run with no deliverable: the stop branch below says "Stopped ...: nothing was built"
            decision, gone = "stop", []
            r["to_requester"] = "Got it. Nothing is built yet and nothing would be left to build, so we're stopping here."
            if self.last_limit:
                self.last_limit["decision"] = "stop"
            if self.decisions:
                self.decisions[-1]["decision"] = "stop"
        if self.decisions and limit:
'''),
    # ---- P30 (D433): every done-when item has a runnable check (goal["item_checks"]) and a status its builder sets
    # (w["item_status"]), both by item text; code runs the checks at every audit, and "Done:" needs every item built and passing
    Edit("P30", "j2.py", r'''AUTO_ASSUME = ("Decide for me: go with sensible, typical choices for anything I haven't told you, "
               "and list them as assumptions I can check later.")
''', r'''AUTO_ASSUME = ("Decide for me: go with sensible, typical choices for anything I haven't told you, "
               "and list them as assumptions I can check later.")

# P30 (D433): every done-when item has a runnable check (goal["item_checks"], by item text) and a status its builder sets in
# a field (w["item_status"]); "Done:" only when every item is built and its check passes. Code never reads a word for either.
ITEM_STATUSES = ("built", "blocked", "not_built")
BEHAVIOUR_RULE = ("\nEvery behaviour the brief requires (each thing it must do, when it must do it, and where its result goes) is "
                  "its own done-when item, besides any item the form asks for; one the charter can't hold goes in dropped_from_brief.")
ITEM_STATUS_FMT = (', "item_status": [{"item": int (one of your items), "status": "built"|"blocked"|"not_built", '
                   '"reason": str (blocked: the fact or access it needs that you don\'t have; not_built: what stops it)}] (one per item '
                   'in your items; an item whose action you prepared but did not perform (e.g. a message written but never sent, '
                   'for lack of access or credentials) is blocked with that reason, never built)')      # beta fix (c), D249
ITEM_STATUS_SCHEMA = {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                 "properties": {"item": {"type": "integer"},
                                                                "status": {"type": "string", "enum": list(ITEM_STATUSES)},
                                                                "reason": {"type": "string"}},
                                                 "required": ["item", "status", "reason"]}}


def mock_item_check(out):
    """P30 (D433), mock only: a check the mock build passes, from the form's fields (never a type name)."""
    if out.get("output") == "folder":      # main.py: the file the mock folder builder always writes (mock_form_folder_files)
        return {"type": "file-exists", "target": "main.py", "expect": True}
    if out.get("sections"):
        return {"type": "heading-present", "target": out["sections"][0]}
    return {"type": "file-exists", "target": PAGE_FILE, "expect": True}
'''),
    Edit("P30", "j2.py", r'''        self.real_runs_done = {}     # step 7: workflow id -> True when its real run was approved and exited 0 (its receipt)
''', r'''        self.real_runs_done = {}     # step 7: workflow id -> True when its real run was approved and exited 0 (its receipt)
        self.real_run_item_ok = {}     # P30 (D433): item text -> Audit passed that item on its real run's output (P33 fills it)
'''),
    Edit("P30", "j2.py", r'''            "rules": ["No invented facts"], "done_when": items, "core": [True] * len(items), "item_kinds": kinds,
''', r'''            "rules": ["No invented facts"], "done_when": items, "core": [True] * len(items), "item_kinds": kinds,
            "item_checks": {t: {"type": "section-not-empty", "target": s, "expect": 1}      # P30 (D433): one item per section
                            for t, s in zip(items, output_def(kind)["sections"])},
'''),
    Edit("P30", "j2.py", r'''                      'depends on a date, such as a deadline or an early-bird price), ')
''', r'''                      'depends on a date, such as a deadline or an early-bird price), ')
        kinds_fmt += ('"item_checks": [{"type": one of ' + json.dumps(self._item_check_types())
                      + ', "target": str|[str]|null, "expect": any|null}] (one per done-when item, same order: the check code '
                      'runs to show the item is built; "real-run" for an item only running it on the Requester\'s own files '
                      'can show), ')      # P30 (D433)
'''),
    Edit("P30", "j2.py", r'''"Don't plan costs or resources.") + (SITE_LATER.format(''',
         r'''"Don't plan costs or resources.") + BEHAVIOUR_RULE + (SITE_LATER.format('''),
    Edit("P30", "j2.py", r'''        tags = r.get("item_kinds") if isinstance(r.get("item_kinds"), list) else []
''', r'''        tags = r.get("item_kinds") if isinstance(r.get("item_kinds"), list) else []
        checks = r.get("item_checks") if isinstance(r.get("item_checks"), list) else []      # P30 (D433)
'''),
    Edit("P30", "j2.py", r'''                tags = []          # code's items replace Identity's: their kinds are the sections' parts
''', r'''                tags = []          # code's items replace Identity's: their kinds are the sections' parts
                checks = [goal["item_checks"][c] for c in goal["done_when"]]      # P30 (D433): and their checks are code's
'''),
    Edit("P30", "j2.py", r'''        if given or kept or goal.get("item_kinds"):
            goal["item_kinds"] = {**kept, **(goal.get("item_kinds") or {}), **given}
''', r'''        if given or kept or goal.get("item_kinds"):
            goal["item_kinds"] = {**kept, **(goal.get("item_kinds") or {}), **given}
        # P30 (D433): each item's runnable check, stored by text like its kind; a change request keeps the checks of items that
        # stay; the no-errors gate is code's own render check. An item left without one is refused at the stamp.
        kept = {c: k for c, k in ((self.goal or {}).get("item_checks") or {}).items() if c in crit}
        mocked = [mock_item_check(self.out)] * len(crit) if llm.MOCK and not checks else []      # mock only: any mock reply
        goal["item_checks"] = {**kept, **self._item_checks_from(checks or mocked, crit),
                               **({GATE_TEXT: {"type": "render-check"}} if GATE_TEXT in crit else {})}
'''),
    # T5 gate fix (D433): a scripted port serving a run outside mock mode (the host's connector test) answers as a live
    # Identity must, one check per item; in mock mode normalise fills them as before. A live model never sees this reply.
    Edit("P30", "j2.py", r'''                               **({"item_kinds": [mock_item_kind(c) for c in dw]} if dw and len(kinds) > 1 else {})})
''', r'''                               **({"item_kinds": [mock_item_kind(c) for c in dw]} if dw and len(kinds) > 1 else {}),
                               **({"item_checks": [mock_item_check(self.out)] * len(dw)} if dw and not llm.MOCK else {})})
'''),
    # T5 gate fix (D433): a charter refused a second time because items have no runnable check never starts work (no item
    # without a check can pass, so the cycle would repeat until a limit): the run stops and Identity asks the Requester
    Edit("P30", "j2.py", r'''        self.stamped = True
        self.post("system", "Charter accepted after two attempts; the validator's concern is on record.")
''', r'''        have = self.goal.get("item_checks")      # P30 (D433): None for a charter without item_checks (FR-9)
        miss = [c for c in self.goal.get("done_when") or [] if have is not None and c not in have]
        if miss:
            self._event("validator", "refused", f"charter, second time: {why}")
            self.post("system", f"Charter rejected twice: {why}. Code stops: no work starts, Identity asks the Requester.")
            return self._ask_user("I could not give a runnable check for these done-when items: "
                                  + "; ".join(f"{self._no(c)}. {c}" for c in miss) + ". Work starts after your answer.",
                                  [{"question": "How can each of these be checked, or should it be reworded or dropped?",
                                    "options": []}], "info", handoff={"kind": "intake", "change": change, "mark": mark})
        self.stamped = True
        self.post("system", "Charter accepted after two attempts; the validator's concern is on record.")
'''),
    Edit("P30", "j2.py", r'''                           f"needs at least {need})")
        return True, "passes code checks"
''', r'''                           f"needs at least {need})")
        if "item_checks" in g:      # P30 (D433): structural only, by set membership at normalise
            miss = [n for n, c in enumerate(g.get("done_when") or [], 1) if c not in g["item_checks"]]
            if miss:
                allowed = self._item_check_types()
                return False, f"done-when item(s) {miss} have no runnable check (item_checks: one of {allowed})"
        return True, "passes code checks"
'''),
    Edit("P30", "j2.py", r'''        brief["covers_items"] = [((self.goal or {}).get("done_when") or [])[i - 1] for i in self._wf_items(w)]
''', r'''        brief["covers_items"] = [((self.goal or {}).get("done_when") or [])[i - 1] for i in self._wf_items(w)]
        if "item_checks" in (self.goal or {}):      # P30 (D433): the items it owns, each with its check and its status so far
            states, checks = self._item_states(), self.goal["item_checks"]
            brief["items"] = [{"item": self._no(t), "text": t, "check": checks.get(t),
                               "status": (states.get(t) or {}).get("status", "not_built")} for t in self._owned_items(w)]
'''),
    Edit("P30", "j2.py", r'''                "atom_human_output": "This part was taken from an earlier finished run and checked again here.",
''', r'''                "atom_human_output": "This part was taken from an earlier finished run and checked again here.",
                "item_status": self._served_status(w, src),      # P30 (D433): the earlier run's builder set it (review R1-6)
'''),
    Edit("P30", "j2.py", r'''                board_extra = self._mock_board_extra(w, attempt) if j2_board.enabled() else {}
''', r'''                board_extra = {**(self._mock_board_extra(w, attempt) if j2_board.enabled() else {}),
                               "item_status": self._built_status(w)}      # P30 (D433)
'''),
    Edit("P30", "j2.py", r'''                schema = j2_artifact_models.reply_schema(art_model, extra)
''', r'''                extra["item_status"] = ITEM_STATUS_SCHEMA      # P30 (D433): the closed reply schema takes the builder's status
                schema = j2_artifact_models.reply_schema(art_model, extra)
'''),
    Edit("P30", "j2.py", r'''[] otherwise), "next": "Coordination", ' + (self.SPEC_FMT''',
         r'''[] otherwise)' + ITEM_STATUS_FMT + ', "next": "Coordination", ' + (self.SPEC_FMT'''),
    Edit("P30", "j2.py", r'''[] otherwise), "next": "Coordination", '
                + (self.BOARD_FMT''', r'''[] otherwise)' + ITEM_STATUS_FMT + ', "next": "Coordination", '
                + (self.BOARD_FMT'''),
    Edit("P30", "j2.py", r'''                  'everyday words)',
                  '"next": "Coordination"',
''', r'''                  'everyday words)',
                  ITEM_STATUS_FMT[2:],      # P30 (D433)
                  '"next": "Coordination"',
'''),
    Edit("P30", "j2.py", r'''               'selectors), "next": "Coordination"}. Then the whole file between a line <<<FILE and a line FILE>>>.')
''', r'''               'selectors)' + ITEM_STATUS_FMT + ', "next": "Coordination"}. Then the whole file between a line <<<FILE and a '
               'line FILE>>>.')      # P30 (D433)
'''),
    Edit("P30", "j2.py", r'''                                "page follow.", "next": "Coordination"})
''', r'''                                "page follow.", "item_status": self._built_status(w), "next": "Coordination"})      # P30
'''),
    Edit("P30", "j2.py", r'''                 '"atom_human_output": str (1 or 2 plain sentences in everyday words: no ids, no selectors), '
                 '"next": "Coordination"}')
''', r'''                 '"atom_human_output": str (1 or 2 plain sentences in everyday words: no ids, no selectors)'
                 + ITEM_STATUS_FMT + ', "next": "Coordination"}')      # P30 (D433)
'''),
    Edit("P30", "j2.py", r'''                           "atom_human_output": "This adds a working part of the result.", "next": "Coordination"})
''', r'''                           "atom_human_output": "This adds a working part of the result.",
                           "item_status": self._built_status(w), "next": "Coordination"})      # P30 (D433)
'''),
    Edit("P30", "j2.py", r'''    def _atom_outputs(self, w, meta, attempt):
        """Every atom's human_output (the builder's words, checked by atom_human_problem, asked once more if bad, else
        written by code from the atom's expected output), then, for an atom whose checks passed, its agent_output."""
''', r'''    def _item_check_types(self):
        """P30 (D433): the check types an item may have: the form's, without inside-folder (a guard on the whole build that
        holds for every build, never evidence for one item; review R1-5), and "real-run"."""
        return sorted(set(self.out["check_types"]) - {"inside-folder"} | {"real-run"})

    def _item_checks_from(self, raw, crit):
        """P30 (D433): Identity's item_checks (one per item, same order) as {item text: {type, target, expect}}: only a type
        of _item_check_types is kept, and a list of the wrong length gives none (the stamp then refuses)."""
        allowed = set(self._item_check_types())
        if len(raw) != len(crit):
            return {}
        return {c: {k: x[k] for k in ("type", "target", "expect") if k in x} for c, x in zip(crit, raw)
                if isinstance(x, dict) and x.get("type") in allowed}

    def _owned_items(self, w):
        """P30 (D433): the texts of the done-when items a workflow owns: those it covers, and the items of the findings
        (F-n is item n) it fixes."""
        crit, at = (self.goal or {}).get("done_when") or [], self._item_at()
        fixed = [crit[at[int(f[2:])] - 1] for f in map(str, w.get("fixes") or []) if FINDING_ID.fullmatch(f) and int(f[2:]) in at]
        return list(dict.fromkeys([crit[i - 1] for i in self._wf_items(w)] + fixed))

    def _built_status(self, w):
        """P30 (D433), mock builders only: every item the workflow owns, set built (the scripted builder's reply)."""
        return [{"item": self._no(t), "status": "built", "reason": ""} for t in self._owned_items(w)]

    def _served_status(self, w, src):
        """P30 (D433): a section the content door served unchanged carries the status the earlier run's builders set for the
        items this workflow owns (its stored workflows.json, the latest done workflow wins, by item text); an item it holds
        none for is not_built. Code copies a status an agent set, never decides one (review R1-6)."""
        try:
            with open(os.path.join((src or {}).get("dir") or "", "workflows.json"), encoding="utf-8") as f:
                old = json.load(f)
        except (OSError, ValueError):
            old = []
        st = {}
        for x in old if isinstance(old, list) else []:
            if isinstance(x, dict) and x.get("status") == "done" and isinstance(x.get("item_status"), dict):
                st.update(x["item_status"])
        return [{"item": self._no(t), "status": (st.get(t) or {}).get("status", "not_built"),
                 "reason": (st.get(t) or {}).get("reason") or ("" if t in st else "the earlier run stored no status for it")}
                for t in self._owned_items(w)]

    def _store_item_status(self, w, meta):
        """P30 (D433): the builder's item_status field, kept on its workflow by item text. A missing entry or an unknown
        status is not_built, and blocked without a reason is not_built: a field, never the reply's words."""
        if "item_checks" not in (self.goal or {}):
            return
        mine = {self._no(t): t for t in self._owned_items(w)}
        raw = meta.get("item_status") if isinstance(meta, dict) else None
        got = {}
        for x in raw if isinstance(raw, list) else []:
            if isinstance(x, dict) and as_int(x.get("item")) in mine:
                got.setdefault(mine[as_int(x.get("item"))], x)
        w["item_status"] = {}
        for t in mine.values():
            s, why = got.get(t, {}).get("status"), str(got.get(t, {}).get("reason") or "").strip()
            if s not in ITEM_STATUSES:
                s, why = "not_built", "the builder set no status"
            elif s == "blocked" and not why:
                s, why = "not_built", "blocked without a reason"
            w["item_status"][t] = {"status": s, "reason": why}

    def _item_states(self):
        """P30 (D433): {item text: {status, reason, wid}}, the latest done workflow that owns the item wins."""
        out = {}
        for w in self.workflows:
            if w.get("status") == "done":
                out.update({t: {**s, "wid": w["id"]} for t, s in (w.get("item_status") or {}).items()})
        return out

    def _open_items(self, skip=()):
        """P30 (D433): every done-when item whose builder did not set it built, with why ([] for a charter without item_checks).
        The no-errors gate is code's own (render-check): no builder owns it, and the audit gate and workable() decide it.
        Neither does a builder own an item a planned real run decides (_register refuses a builder that covers one): its
        receipt, Audit's reading of the output (P33), _real_run_pending and workable() decide it (review R1-1)."""
        if "item_checks" not in (self.goal or {}):
            return []
        states, out, by_run, tbc = self._item_states(), [], set(self._real_run_items()), self._tbc_blocked()
        for t in (self.goal or {}).get("done_when") or []:
            if t in skip:
                continue
            s = {"status": "blocked", "reason": tbc[t]} if t in tbc else \
                states.get(t) or {"status": "not_built", "reason": "no workflow built it"}      # beta fix b: the charter's fact
            if t not in tbc and (t in by_run or (self.goal["item_checks"].get(t) or {}).get("type") == "render-check"):
                continue
            if s["status"] == "blocked":      # beta fix d: the missing fact (an agent's field) and how to give it (code's text)
                out.append(f"done-when item {self._no(t)}: {t.rstrip('.')} blocked: needs {s['reason']}. "
                           "Send it as a follow-up to finish.")
            elif s["status"] != "built":
                out.append(f"done-when item {self._no(t)}: {t} ({s['status'].replace('_', ' ')}: {s['reason'] or 'no reason given'})")
        return out

    def _blocked_items(self):
        """P30 (D433, beta fix): the done-when items whose latest done owner set them blocked (always with a reason:
        _store_item_status keeps blocked only with one). They never hold back the planned real run; the run then ends
        "Done with open items", naming each with its reason (_open_items). The builder's field, never a word of a reply."""
        if "item_checks" not in (self.goal or {}):
            return []
        states, by_run = self._item_states(), set(self._real_run_items())     # review R3-1: a real-run item is decided
        tbc = self._tbc_blocked()                                             # by its receipt and Audit, never a builder
        return [t for t in self.goal.get("done_when") or []
                if t in tbc or (t not in by_run and (states.get(t) or {}).get("status") == "blocked")]

    def _tbc_blocked(self):
        """P30 (D433, beta fix b): {item text: fact} for each done-when item the latest audit marks TO_BE_CONFIRMED because
        the charter's to_be_confirmed (Identity's field) names it: it counts as blocked, its reason the entry's own fact
        field, never a word of a note. Never an item a planned real run decides (review R3-1)."""
        if "item_checks" not in (self.goal or {}) or not self.audits:
            return {}
        facts, by_run = {t["criterion"]: t["fact"] for t in self.goal.get("to_be_confirmed") or []}, set(self._real_run_items())
        return {r["criterion"]: facts[r["criterion"]] for r in self.audits[-1].get("results") or []
                if r.get("verdict") == "TO_BE_CONFIRMED" and r["criterion"] in facts and r["criterion"] not in by_run}

    def _stage_blocked(self):
        """P30 (D433, review R4-1): the blocked lines of each earlier stage of a design-document chain, kept when it was left
        (_next_stage), named by stage: _begin_stage resets the goal, audits and workflows, so the outcome reads them here."""
        return [f"{a['stage'].upper()} {line}" for a in self.stage_archive if a.get("stage") != self.stage_kind
                for line in a.get("blocked") or []]

    def _run_item_check(self, text, chk, built, mech):
        """P30 (D433): {"pass": True|False|None (did not run), "evidence"} of one item's check on the latest build, with the
        runners the work atoms' checks use."""
        t, folder = chk.get("type"), self._out_dir() if self.folder else None
        try:
            if t == "real-run":      # decided by its real run's receipt (approved, ran, exit 0) and Audit's reading of
                n = self._no(text)      # its output for this item (real_run_item_ok, P33; review R1-4), never by a builder
                ok = any(self.real_runs_done.get(w["id"]) is True for w in self.workflows
                         if n in {as_int(c) for c in (w.get("real_run") or {}).get("checks") or []}) \
                    and self.real_run_item_ok.get(text, True)
                return {"pass": ok, "evidence": "its real run was approved, exited 0 and Audit passed its output" if ok else
                        "its real run did not pass (approved, exit 0 and Audit PASS)"}
            if t == "render-check":
                if not mech.get("available"):
                    return {"pass": None, "evidence": f"the render check didn't run: {mech.get('note')}"}
                probs = j2_check.problems(mech)
                return {"pass": not probs, "evidence": "; ".join(probs) or "the render check found no problem"}
            if folder and t == "test-passed":
                if not self.out.get("test_runner"):
                    return {"pass": None, "evidence": "this output's form names no test runner"}
                tg = chk.get("target")
                rr = sandbox_rerun(folder, self.out["test_runner"], tg[0] if isinstance(tg, list) else tg, builder_timeout())
                return {"pass": rr["pass"], "evidence": rr["evidence"]}
            return run_check(chk, folder or os.path.join(self.dir, "site"), built, self.doc)
        except (OSError, ValueError) as e:
            return {"pass": None, "evidence": f"the check could not run: {e}"}

    def _item_check_gate(self, results, built, mech):
        """P30 (D433): an item Audit passed stays passed only when code ran its check and it passed; otherwise the row is
        BLOCKED_BY_EVIDENCE with code's evidence. Nothing for a charter without item_checks."""
        checks = (self.goal or {}).get("item_checks")
        if checks is None:
            return
        for i, row in enumerate(results):
            chk = checks.get(row["criterion"])
            if not row["pass"]:
                continue
            res = self._run_item_check(row["criterion"], chk, built, mech) if chk else \
                {"pass": False, "evidence": "this item has no runnable check"}
            if res.get("pass") is True:
                continue
            results[i] = {**row, "verdict": "BLOCKED_BY_EVIDENCE", "pass": False,
                          "note": f"Code ran this item's check ({(chk or {}).get('type', 'none')}): {res['evidence']}. "
                                  f"(Audit's own note: {row.get('note') or 'none'})"}
            self._event("validator", "item_check", f"{row['id']} item {row['item']}: {res['evidence']}")

    def _atom_outputs(self, w, meta, attempt):
        """Every atom's human_output (the builder's words, checked by atom_human_problem, asked once more if bad, else
        written by code from the atom's expected output), then, for an atom whose checks passed, its agent_output."""
        self._store_item_status(w, meta)      # P30 (D433): the builder's status of each item it owns, a field
'''),
    Edit("P30", "j2.py", r'''        results, extras = self._audit_findings(r.get("findings") or r.get("results") or [], crit)
        forced = self._force_fail(results)
''', r'''        results, extras = self._audit_findings(r.get("findings") or r.get("results") or [], crit)
        self._item_check_gate(results, site, mech)      # P30 (D433): a PASS needs its item's check to pass, run by code
        forced = self._force_fail(results)
'''),
    Edit("P30", "j2.py", r'''        if self.audits and (fails := workable(self.audits[-1]) + self._real_run_pending()) and \
                (self.real_runs_done or self._real_run_pending()):    # step 7: workable only after an approved run passed
            self.outcome = (f"Done with open items: the real run {'did not pass' if self.real_runs_done else 'has not run'}."
                            f" Still not workable: {'; '.join(fails)}.")
''', r'''        rest = workable({**self.audits[-1], "accepted": list(self.audits[-1].get("accepted") or []) + self._blocked_items()}) \
            + self._real_run_pending() if self.audits else []      # beta fix: a blocked item is no real-run failure
        rr = bool(rest and (self.real_runs_done or self._real_run_pending()))    # step 7: workable only after an approved run passed
        opened = self._stage_blocked() + (self._open_items() if self.audits else [])      # P30 (D433), R4-1: earlier stages too
        if rr or opened:
            self.outcome = ("Done with open items: "
                            + (f"the real run {'did not pass' if self.real_runs_done else 'has not run'}." if rr else
                               "not every done-when item is built.") + f" Still not workable: {'; '.join(rest + opened).rstrip('.')}.")
'''),
    Edit("P30", "j2.py", r'''        fails = workable(self.audits[-1]) if self.audits else ["nothing has been checked"]
        fails = self.open_docs + fails + self._real_run_pending()
        if not fails:
            return self.out["done"]
        return f"Done with open items: shipped as is {why}. Still not workable: {'; '.join(fails)}."
''', r'''        fails = workable({**self.audits[-1], "accepted": list(self.audits[-1].get("accepted") or []) + self._blocked_items()}) \
            if self.audits else ["nothing has been checked"]      # beta fix (b): a blocked item is listed once, by _open_items
        fails = self.open_docs + fails + self._real_run_pending() + self._stage_blocked() + self._open_items()      # P30 (D433)
        if not fails:
            return self.out["done"]
        return f"Done with open items: shipped as is {why}. Still not workable: {'; '.join(fails).rstrip('.')}."      # beta fix d
'''),
    Edit("P30", "j2.py", r'''        if not fails and self._ask_real_run({}):     # step 7: the rest is workable, so the planned run is asked for now,
            return                                    # without waiting on Identity's done (runs/j2-20261114-123619)
''', r'''        held = workable({**last, "accepted": list(last.get("accepted") or []) + self._blocked_items()}) if last else fails
        if not held and self._ask_real_run({}):     # step 7: the rest is workable, so the planned run is asked for now,
            return                                    # without waiting on Identity's done (runs/j2-20261114-123619)
        if fails and not held and (blocked := self._blocked_items()) and not self._open_items(skip=blocked) \
                and not self._real_run_pending():
            # beta fix d (D433): everything else is built and passes, and what is left is blocked on what only the Requester
            # has: the run ends now, "Done with open items" naming each with its missing fact, with no retry, no Adaptation
            # and no second audit (it looped to Adaptation and then the same-failure limit question: run 8b10)
            self.post("system", "Everything else is built and passes. What is left is blocked, so no fix round is started.")
            return self._goal_done({"to_requester": "Everything else is built and passes. Still open: "
                                                    + "; ".join(self._open_items())})
'''),      # beta fix (D433): an item its builder set blocked, with a reason, does not hold back the real run
    # beta fix (D433): a follow-up to a charter with to-be-confirmed facts takes J2_FIXES' change-request intake, so Identity can
    # take the fact and drop the entry (by default it went straight to Adaptation and the entry stayed). The trigger is the entry.
    # review R4-1 (D433): a stage left with blocked items (fix d ends it at once, then the chain moves on) keeps their lines, so the
    # run's outcome still names them (_stage_blocked); _begin_stage resets the goal, audits and workflows
    Edit("P30", "j2.py", '''        self.stage_archive.append({"stage": self.stage_kind, "goal": base, "audits": self.audits, "sections": self.sections})
''', '''        blocked = set(self._blocked_items())
        left = self._open_items(skip=[t for t in base.get("done_when") or [] if t not in blocked]) if blocked else []
        self.stage_archive.append({"stage": self.stage_kind, "goal": base, "audits": self.audits, "sections": self.sections,
                                   **({"blocked": left} if left else {})})      # review R4-1 (D433)
'''),
    Edit("P30", "j2.py", '''            elif self.fixes or self._change_applies():   # fix (b): a change request is checked at J2.a first
''', '''            elif self.fixes or self._change_applies() or self.goal.get("to_be_confirmed"):   # fix (b): a change request is
                # checked at J2.a first; beta fix (D433): always, while the charter waits on a fact only the Requester has
'''),
    Edit("P30", "j2.py", '''                         f"CURRENT CHARTER: {json.dumps(self.goal, ensure_ascii=False)}")
''', '''                         f"CURRENT CHARTER: {json.dumps(self.goal, ensure_ascii=False)}")
            if self.goal.get("to_be_confirmed"):      # beta fix (D433): the follow-up may give a fact the charter waits on
                feedback += ("\\nThe charter's to_be_confirmed lists facts only the Requester can give. If the change gives "
                             "one, put it in the charter and leave its entry out of to_be_confirmed; giving a fact is not a "
                             "new done-when item.")
'''),
    # ---- P31 (D434): a failed dry run goes back to the build; only RUN <code> or Don't run answers the real-run question
    Edit("P31", "j2.py", 'AUTO_CAP = int(os.getenv("J2_AUTO_CAP") or 6)\n',
         'AUTO_CAP = int(os.getenv("J2_AUTO_CAP") or 6)\n'
         'REAL_RUN_DECLINE = "Don\'t run"      # P31 (D434): the real-run card\'s decline, compared whole (stripped, any case)\n'),
    Edit("P31", "j2.py", r'''        res = real_run(out_dir, {**rr, "folder": copies[0], "reads": copies[1:], "command": cmd}, timeout)
''', r'''        res = real_run(out_dir, {**rr, "folder": copies[0], "reads": copies[1:], "command": cmd}, timeout)
        out = (res.get("output") or "").replace(tmp, "<copy>")      # P31 (D434): its output's end, no temp path (P28 signs it)
'''),
    Edit("P31", "j2.py", '"exit": res.get("exit"), "command": cmd, **d, "real_changed"',
         '"exit": res.get("exit"), "output": out, "command": cmd, **d, "real_changed"', count=2),
    Edit("P31", "j2.py", r'''        at, crit = self._item_at(), (self.goal or {}).get("done_when") or []
        return [crit[at[n] - 1] for w in self.workflows if w.get("real_run")
                and not (pending and w["id"] in self.real_runs_done)
                for n in w["real_run"].get("checks") or [] if n in at and at[n] <= len(crit)]
''', r'''        at, crit = self._item_at(), (self.goal or {}).get("done_when") or []
        ran = {n for w in self.workflows if w.get("real_run") and w["id"] in self.real_runs_done
               for n in w["real_run"].get("checks") or []} if pending else set()      # P31 (D434): any receipt decides it (a replacement)
        return [crit[at[n] - 1] for w in self.workflows if w.get("real_run")
                for n in w["real_run"].get("checks") or [] if n not in ran and n in at and at[n] <= len(crit)]
'''),
    Edit("P31", "j2.py", r'''            self.turn, self.handoff = None, {}
            return True
        self.post("system", f"{w['id']} wants to run what it built on your own files.''', r'''            self.turn, self.handoff = None, {}
            return True
        if dry.get("ran") and dry.get("exit") != 0:      # P31 (D434): a failed dry run goes back to the build, never to the Requester
            last = next((x.strip() for x in reversed((dry.get("output") or "").splitlines()) if x.strip()), "no output")
            return self._dry_run_failed(w, dry, (f"exit {dry['exit']}" if dry["exit"] is not None else "stopped at the time limit")
                                        + f": {last[:160]}")
        self.post("system", f"{w['id']} wants to run what it built on your own files.'''),
    Edit("P31", "j2.py", r'''                            "Any other reply: it is not run.", real_run=w["id"])
        self._ask_user("One of the workflows wants to run what it built on your files. The exact command is above.",
                       [{"question": "Run it for real?"}], "real_run", handoff={"kind": "real_run", "r": r, "wid": w["id"]})
        return True
''', r'''                            "Or press Run. To decline, press Don't run.", real_run=w["id"])      # P31 (D434)
        self._ask_user("One of the workflows wants to run what it built on your files. The exact command is above.",
                       [{"question": "Run it for real?"}], "real_run", handoff={"kind": "real_run", "r": r, "wid": w["id"]})
        return True

    def _dry_run_failed(self, w, dry, detail):
        """P31 (D434): a real run whose dry run on copies failed is a build failure, never a question: w fails with code's
        detail (P28's signature), keeps its output's end for the revising builder, a not-run receipt is written, its code is
        forgotten, and Adaptation proposes the fix, unless the same failure twice in a row stops the cycle. True (handled)."""
        w["status"], w["failure"], w["dry_run_output"] = "failed", ["dry_run", detail], dry.get("output") or ""
        code = self.real_runs_asked.pop(w["id"], None)
        with open(os.path.join(self.dir, "receipts.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "real_run", "workflow": w["id"], **w["real_run"], "code": code, "approved": False,
                                "ran": False, "exit": None, "evidence": f"not asked: the dry run on copies failed ({detail})",
                                "dry_run": {k: v for k, v in dry.items() if k != "evidence"},
                                "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "by": "code"}, ensure_ascii=False) + "\n")
        self._event("code", "real_run", f"{w['id']}: the dry run on copies failed ({detail})")
        self.post("system", "Dry run failed, sent back to the builder")      # owner (review R1-7): a plain info line, never a question or card
        self.save("workflows.json", self.workflows)
        if self.last_failure is None:      # a passing build in between cleared P28's memory; it says nothing of the dry run after it
            self.last_failure = getattr(self, "dry_failure", None)
        stop = self._repeat_build_stop(w["id"])
        self.dry_failure = self.last_failure
        if not stop:
            self._handoff("adaptation", kind="propose", new_cycle=True,
                          why=f"{w['id']}'s real run failed its dry run on copies ({detail}). Propose a workflow that revises "
                              f"{w['id']} and keeps its real_run. Its output (end): {w['dry_run_output']}")
        return True
'''),
    Edit("P31", "j2.py", r'''        ok = bool(w and code) and not last.get("auto") and str(h.get("answer") or "").strip() == f"RUN {code}"
        res = real_run(self._out_dir(), w["real_run"], builder_timeout()) if ok else \
            {"ran": False, "exit": None, "evidence": "not run: the reply was not exactly RUN " + str(code)}
''', r'''        ans = str(h.get("answer") or "").strip()
        ok = bool(w and code) and not last.get("auto") and ans == f"RUN {code}"
        declined = not last.get("auto") and ans.casefold() == REAL_RUN_DECLINE.casefold()      # P31 (D434): the whole reply
        if w and code and not ok and not declined:      # P31 (D434): any other reply asks again, the same code; the run stays open
            self._event("identity", "real_run_unclear", f"{h.get('wid')}: the reply was neither RUN <code> nor {REAL_RUN_DECLINE}")
            return self._ask_user(f"Not run. Press Run or type RUN {code}.", [{"question": "Run it for real?"}], "real_run",
                                  handoff={"kind": "real_run", "r": h.get("r") or {}, "wid": h.get("wid")})
        res = real_run(self._out_dir(), w["real_run"], builder_timeout()) if ok else \
            {"ran": False, "exit": None, "evidence": "not run: the Requester chose Don't run" if declined else
             "not run: the reply was not exactly RUN " + str(code)}
'''),
    Edit("P31", "j2.py", r'''                              "workflow": self.paused["handoff"].get("wid")}) if self.paused else None,
''', r'''                              "workflow": self.paused["handoff"].get("wid"),
                              "code": self.real_runs_asked.get(self.paused["handoff"].get("wid"))      # P31 (D434): the Run button's
                              if self.paused["kind"] == "real_run" else None}) if self.paused else None,
'''),
    Edit("P31", "j2.py", r'''        self.atom = (w.get("atoms") or [{}])[0].get("id")     # its AI calls are tagged with the atom they build
''', r'''        mine = set((w.get("real_run") or {}).get("checks") or [])      # P31 (D434): the latest workflow whose real run checked one of
        if mine and (rv := next((x for x in reversed(self.workflows) if x is not w and (x.get("failure") or [None])[0] == "dry_run"
                                 and mine & set(x["real_run"].get("checks") or [])), None)):      # these items and failed its dry run
            brief["dry_run_failure"] = rv.get("dry_run_output")      # (by item number: a folder run drops "revises"): what it printed
        self.atom = (w.get("atoms") or [{}])[0].get("id")     # its AI calls are tagged with the atom they build
'''),
    # beta fix (D434): a real-run folder written ~/x is the folder it names: absolute, named in the brief as ~/x or written out
    Edit("P31", "j2.py", r'''def real_folders(workflows):
''', r'''def home_expanded(rr):
    """P31 (D434, beta fix): rr with "~" and "~/..." in its folder, reads and command arguments (the value after "=" too)
    written out as the home folder (os.path.expanduser): a brief says ~/x, and no shell expands it when code runs the
    command. Anything else, and anything not a string, is left for real_run_problems to judge."""
    if not isinstance(rr, dict):
        return rr
    ex = lambda v: os.path.expanduser(v) if isinstance(v, str) and (v == "~" or v.startswith("~/")) else v

    def arg(x):
        k, eq, v = x.partition("=") if isinstance(x, str) and "=" in x else ("", "", x)
        return k + eq + ex(v)
    return {**rr, "folder": ex(rr.get("folder")),
            **({"reads": [ex(x) for x in rr["reads"]]} if isinstance(rr.get("reads"), list) else {}),
            **({"command": [arg(x) for x in rr["command"]]} if isinstance(rr.get("command"), list) else {})}


def home_tilde(f):
    """P31 (D434, beta fix): f under the home folder written ~/..., as a brief writes it (f itself otherwise)."""
    h = os.path.expanduser("~").rstrip("/")
    return "~" + f[len(h):] if h and (f == h or f.startswith(h + "/")) else f


def real_folders(workflows):
'''),
    Edit("P31", "j2.py", r'''    out, cmd, folder, reads = [], rr.get("command"), rr.get("folder"), rr.get("reads") or []
''', r'''    rr = home_expanded(rr)      # P31 (D434, beta fix): ~/x is the folder it names (absolute; named in the brief either way)
    out, cmd, folder, reads = [], rr.get("command"), rr.get("folder"), rr.get("reads") or []
'''),
    Edit("P31", "j2.py", r'''        if not re.search(re.escape(squash(f).rstrip("/")) + r"/?(?=$|[\s,;:)'\"]|\.(?:\s|$))", source):
''', r'''        if not any(re.search(re.escape(squash(g).rstrip("/")) + r"/?(?=$|[\s,;:)'\"]|\.(?:\s|$))", source)
                   for g in {f, home_tilde(f)}):      # P31 (D434, beta fix): the brief may write it ~/x
'''),
    Edit("P31", "j2.py", r'''            if w.get("real_run") is not None:      # step 7: checked here, asked for when the deliverable is workable
''', r'''            if w.get("real_run") is not None:      # step 7: checked here, asked for when the deliverable is workable
                w["real_run"] = home_expanded(w["real_run"])      # P31 (D434, beta fix): stored, dry-run and run written out
'''),
    # ---- P32 (D435): the dry run always runs inside the sandbox runtime (no network), or it is not run
    Edit("P32", "j2.py", r'''    cmd = agent_setting("J2_SANDBOX_CMD") if sandbox_on() else None
    if sandbox_on() and not cmd:
        return {"ran": False, "exit": None, "evidence": "J2_SANDBOX_CMD is not set, so nothing was run"}
''', r'''    fence = rr.get("fence") is True      # P32 (D435): the dry run (real_run_dry) always goes through the sandbox runtime
    cmd = agent_setting("J2_SANDBOX_CMD") if sandbox_on() or fence else None
    if fence and (shutil.which(shlex.split(cmd)[0]) is None or (llm.MOCK and not os.getenv("J2_SANDBOX"))):      # none here
        return {"ran": False, "exit": None, "evidence": "no sandbox runtime here: the dry run was not run, because it never "
                                                        "runs with network"}      # (or offline without J2_SANDBOX): never unfenced
    if sandbox_on() and not cmd:
        return {"ran": False, "exit": None, "evidence": "J2_SANDBOX_CMD is not set, so nothing was run"}
'''),
    Edit("P32", "j2.py", r'''        cmd = [moved(x) for x in rr["command"]]
''', r'''        cmd = [moved(x) for x in rr["command"]]
        rr = {**rr, "fence": True}      # P32 (D435): set by code here only (a stored real_run keeps command, folder, reads, why)
'''),
    Edit("P32", "j2.py", '{"ran": res.get("ran"), ', '{"ran": res.get("ran"), "fenced": res.get("ran") is True, ', count=2),
    Edit("P32", "j2.py", r'''                            + f"\nWhy: {rr.get('why') or 'not given'}\nWhat it would do, from a {dry['evidence']}"
''', r'''                            + f"\nWhy: {rr.get('why') or 'not given'}\n" + (f"What it would do, from a {dry['evidence']}\nThe "
                                                                            "dry run had no network access: results may differ."
                                                                            if dry.get("fenced") else      # P32 (D435)
                                                                            "No dry run: this computer has no sandbox, so it wasn't tested first")
'''),
    # ---- P33 (D436): Audit reads an approved real run's output against the brief; exit 0 alone never passes an item
    Edit("P33", "j2.py", r'''        with open(os.path.join(self.dir, "receipts.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "real_run", "workflow": h.get("wid"), **(w or {}).get("real_run", {}), "code": code,
                                "approved": ok, "answer_msg": last.get("id"), **res,
''', r'''        nums = {as_int(c) for c in ((w or {}).get("real_run") or {}).get("checks") or []}      # P33 (D436): the items it decides
        mine = [t for t in (self.goal or {}).get("done_when") or [] if self._no(t) in nums]
        judged = self._judge_real_run(w, res, mine) if mine and ok and res.get("ran") and res.get("exit") == 0 else {}
        with open(os.path.join(self.dir, "receipts.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "real_run", "workflow": h.get("wid"), **(w or {}).get("real_run", {}), "code": code,
                                "approved": ok, "answer_msg": last.get("id"), **res,
                                **({"audit": {self._no(t): {"verdict": "PASS" if v[0] else "NEEDS_REVISION", "evidence": v[1]}
                                              for t, v in judged.items()}} if judged else {}),      # P33 (D436)
'''),
    Edit("P33", "j2.py", r'''        passed = self.real_runs_done[h.get("wid")] = bool(ok and res.get("ran") and res.get("exit") == 0)
''', r'''        ran_ok = self.real_runs_done[h.get("wid")] = bool(ok and res.get("ran") and res.get("exit") == 0)      # the receipt
        self.real_run_item_ok.update({t: v[0] for t, v in judged.items()})      # P33 (D436): Audit's verdict per item (P30 reads it)
        passed = ran_ok and all(v[0] for v in judged.values())      # P33 (D436): an item it did not judge needs every one passed
'''),
    Edit("P33", "j2.py", r'''                    x.update({"pass": passed, "verdict": "PASS" if passed else "FAIL",
                              "note": f"real run receipt ({h.get('wid')}): {res['evidence']}"})
''', r'''                    j = judged.get(x["criterion"])      # P33 (D436): Audit's verdict on the output decides each item it judged
                    p = j[0] if j else passed
                    x.update({"pass": p, "verdict": "PASS" if p else "NEEDS_REVISION" if j else "FAIL",
                              "note": f"real run receipt ({h.get('wid')}): {res['evidence']}"
                                      + (f"; Audit read its output: {j[1]}" if j else "")})
'''),
    Edit("P33", "j2.py", r'''    def _send_args(self, atom):
''', r'''    def _judge_real_run(self, w, res, items):
        """P33 (D436): one Audit call reads an approved real run's output (exit 0) against the Requester's brief, for the items
        the run decides. {item text: (passed, evidence)}: PASS with evidence passes; anything else, or no finding, does not.
        Code reads only the verdict field, never the words. A plain call: budget and dollar accounting count it like any."""
        rr, dry = w["real_run"], self.real_runs_dry.get(w["id"]) or {}
        r = self.call("audit", '{"say": str, "findings": [{"item": int, "verdict": "PASS"|"NEEDS_REVISION", "evidence": str '
                               '(one line: what in the output shows it)}] (exactly one per item)}',
                      f"REQUESTER'S BRIEF: {self.request}\n"
                      f"ITEMS THIS REAL RUN DECIDES: {json.dumps([{'item': self._no(t), 'criterion': t} for t in items], ensure_ascii=False)}\n"
                      f"COMMAND: {shlex.join(rr['command'])}\n"
                      f"WHAT THE DRY RUN DID TO THE COPY: {json.dumps({k: dry.get(k) or [] for k in ('created', 'changed', 'deleted')}, ensure_ascii=False)}\n"
                      f"ITS OUTPUT (the end, by code): {res.get('output') or '(no output)'}\n"
                      "Judge each item only from this output against the brief: PASS only when the output shows the item "
                      "done; say what shows it.",
                      lambda: json.dumps({"say": "Read the real run's output.", "findings": [
                          {"item": self._no(t), "verdict": "PASS", "evidence": "mock: the output was read"} for t in items]}))
        got = {as_int(f.get("item")): f for f in (r.get("findings") if isinstance(r, dict) else None) or [] if isinstance(f, dict)}
        out = {}
        for t in items:
            f = got.get(self._no(t))
            ev = str((f or {}).get("evidence") or "").strip()
            out[t] = (f is not None and f.get("verdict") == "PASS" and bool(ev),
                      ev or ("Audit filed no finding" if f is None else "Audit gave no evidence"))
        return out

    def _send_args(self, atom):
'''),
    # ---- P34 (D437): a build's output holds only what was built; the CLI's .claude folder is removed and never copied
    Edit("P34", "j2.py", '''        after = file_states(self.dir)
''', '''        shutil.rmtree(os.path.join(tools["cwd"], ".claude"), ignore_errors=True)      # P34 (D437): the Claude CLI's own folder (its cwd is the output folder), whatever it holds
        after = file_states(self.dir)
'''),
    Edit("P34", "j2.py", '''            shutil.copytree(d, os.path.join(self.dir, "site"), dirs_exist_ok=True)
''', '''            shutil.copytree(d, os.path.join(self.dir, "site"), dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(".claude"))      # P34 (D437)
'''),
    # ---- P35 (D438): a real run states what it creates, changes and deletes; the dry run must match it and leave read-only folders alone
    Edit("P35", "j2.py", r'''def real_run_problems(rr, source, runner, run_dir):
''', r'''EXPECT_KEYS = ("created", "changed", "deleted")      # P35 (D438): a real run's expected result, by kind
REAL_RUN_EXPECT_RULE = ('\nREAL RUN EXPECT: the real_run also carries "expect": {"created": [file paths or globs], "changed": [...], '
                        '"deleted": [...]}, each relative to folder, naming files, never a folder (pdf/a.pdf or pdf/*, not pdf/ '
                        'or ./a.pdf): exactly what running it on the folder creates, changes and deletes (an empty list: nothing '
                        'of that kind). Code runs it on copies first and compares; anything else, or any change in a folder it '
                        'only reads, sends it back.')


def real_run_expect_problems(rr):
    """P35 (D438): why a planned real run's "expect" is not usable ([] when it is): exactly the three lists of EXPECT_KEYS,
    each of non-empty relative file paths or globs (no absolute path, no .., no leading ./, no trailing / that names a
    folder: the dry run lists file paths, so such a glob never matches; review R1-8), not all empty. Structure only."""
    ex = rr.get("expect")
    if ex is None:
        return ['real_run expect is missing: say what running it does to folder, {"created": [...], "changed": [...], '
                '"deleted": [...]}, each a list of file paths or globs relative to folder']
    if not isinstance(ex, dict) or set(ex) != set(EXPECT_KEYS):
        return ['real_run expect must be exactly {"created": [...], "changed": [...], "deleted": [...]}']
    out = [f"real_run expect {k} must be a list of non-empty file paths or globs relative to folder (no absolute path, "
           "no .., no leading ./, no trailing / naming a folder)"
           for k in EXPECT_KEYS if not (isinstance(ex[k], list) and all(
               isinstance(g, str) and g.strip() and not os.path.isabs(g) and ".." not in re.split(r"[/\\]", g)
               and not g.startswith(("./", ".\\")) and not g.endswith(("/", "\\")) for g in ex[k]))]
    if not out and not any(ex.values()):
        out.append("real_run expect lists nothing: a real run that creates, changes and deletes nothing has nothing to run")
    return out


def expect_mismatch(expect, dry):
    """P35 (D438): "" when the dry run's created/changed/deleted paths match expect, else what differs, sorted: per kind, a
    glob no path matched ("expected <glob>, got none") and a path no glob matched ("unexpected <path>"). An empty list
    means nothing of that kind. fnmatchcase: "*" also matches across "/"."""
    from fnmatch import fnmatchcase
    out = []
    for k in EXPECT_KEYS:
        globs, got = sorted(expect.get(k) or []), sorted(dry.get(k) or [])
        out += [f"{k}: expected {g}, got none" for g in globs if not any(fnmatchcase(p, g) for p in got)]
        out += [f"{k}: unexpected {p}" for p in got if not any(fnmatchcase(p, g) for g in globs)]
    return "; ".join(out)


def real_run_problems(rr, source, runner, run_dir):
'''),
    Edit("P35", "j2.py", r'''        before = _tree(copies[0])
''', r'''        before, reads_before = _tree(copies[0]), [_tree(c) for c in copies[1:]]      # P35 (D438): the read-only copies too
'''),
    Edit("P35", "j2.py", r'''        d = _tree_diff(before, _tree(copies[0]))
''', r'''        d = _tree_diff(before, _tree(copies[0]))
        reads_changed = {str(i): x for i, (c, b) in enumerate(zip(copies[1:], reads_before), 1)      # P35 (D438): {n: diff}
                         if any((x := _tree_diff(b, _tree(c))).values())}      # of the n-th read-only copy, when it changed
'''),
    Edit("P35", "j2.py", '"real_changed": real,', '"real_changed": real, "reads_changed": reads_changed,'),
    Edit("P35", "j2.py", '"real_changed": {},', '"real_changed": {}, "reads_changed": reads_changed,'),
    Edit("P35", "j2.py", r'''        if dry.get("real_changed"):      # the dry run reached the Requester's own folders: stop, never ask, never "0 changed"
''', r'''        if dry.get("ran") and dry.get("exit") == 0 and not dry.get("real_changed"):      # P35 (D438): after the stop and P31's
            if dry.get("reads_changed"):      # exit check (both below): a write into a read-only copy, then a result unlike expect
                return self._dry_run_failed(w, dry, "wrote into a folder it may only read: " + "; ".join(
                    f"read folder {i}: " + ", ".join(f"{len(v)} {k}" for k, v in x.items())
                    for i, x in sorted(dry["reads_changed"].items(), key=lambda kv: int(kv[0]))))
            if rr.get("expect") and (mm := expect_mismatch(rr["expect"], dry)):      # a real run registered before P35 has none
                dry["expect_mismatch"] = mm
                return self._dry_run_failed(w, dry, "not what it said it would do: " + mm)
        if dry.get("real_changed"):      # the dry run reached the Requester's own folders: stop, never ask, never "0 changed"
'''),
    Edit("P35", "j2.py", r'''                checks = w["real_run"].get("checks") or []
''', r'''                if bad := real_run_expect_problems(w["real_run"]):      # P35 (D438): what it will create, change and delete
                    refused.append(self._reject(name, "; ".join(bad), ("real_run_expect",)))
                    continue
                checks = w["real_run"].get("checks") or []
'''),
    Edit("P35", "j2.py", '''for k in ("command", "folder", "reads", "why")}
''', '''for k in ("command", "folder", "reads", "why", "expect")}      # P35 (D438)
'''),
    Edit("P35", "j2.py", r'''                self.ATOM_RULES += "\n" + (j2_types.builder_tools().get("real_run") or "")
''', r'''                self.ATOM_RULES += "\n" + (j2_types.builder_tools().get("real_run") or "") + REAL_RUN_EXPECT_RULE      # P35 (D438)
'''),
)

OTHER_EDITS = (
    # ---- P1 in the other modules: the rule (apply_p1) did the imports; the sys.path insert of j2_agent_views is an anchor edit
    Edit("P1", "j2_agent_views.py", "if HERE not in sys.path:\n    sys.path.insert(0, HERE)\n",
         "# P1: the siblings are package-relative, nothing is put on the import path\n"),
    # ---- P2: j2_realization
    Edit("P2", "j2_realization.py", 'AGENTS = os.path.join(HERE, "agents", "j2")\n',
         'AGENTS = os.getenv("J2_AGENTS_DIR") or os.path.join(HERE, "agents", "j2")     # P2: J2_AGENTS_DIR replaces the folder\n'),
    # ---- P7: the planner and judge calls
    Edit("P7", "j2_realization.py", r'''        t0 = time.time()
        raw = llm.ask(system, user, mock, max_tokens=16000, effort="high", json_mode=True)
''', r'''        t0 = time.time()
        purpose = "change" if llm.current_tag().purpose == "change" else ("plan" if who == "adaptation" else "judge")
        with llm.tagged(role="planner" if who == "adaptation" else "judge", purpose=purpose):      # P7
            raw = llm.ask(system, user, mock, max_tokens=16000, effort="high", json_mode=True)
'''),
    # ---- P10: the template library lock
    Edit("P10", "j2_template_lib.py", "import copy\nimport hashlib\n", "import contextlib\nimport copy\nimport hashlib\n"),
    Edit("P10", "j2_template_lib.py", r'''def store(t, fingerprint=None):
    """Write a specialised template, checked again here: (template, version, created). The same sha is the same
    version (nothing written); any change is v<N+1>. Versions are immutable."""
''', r'''LOCK_WAIT_S = 30.0      # P10: the most a run waits for the library lock


class LibraryBusy(RuntimeError):
    """P10: another run held the library lock for LOCK_WAIT_S seconds. J2's router treats any error as 'use the generic
    template' (j2.py _route_template)."""


@contextlib.contextmanager
def _library_lock():
    """P10: one writer at a time, across processes: an exclusive lock on <library>/.lock around a whole read-modify-write of the index.
    J2 read the index, changed it and wrote it back with no lock, so two runs storing different templates could lose one
    entry. Waits at most LOCK_WAIT_S seconds, then raises LibraryBusy."""
    os.makedirs(lib_dir(), exist_ok=True)
    fd = os.open(os.path.join(lib_dir(), ".lock"), os.O_RDWR | oslayer.O_BINARY | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + LOCK_WAIT_S
        while not oslayer.try_lock(fd):
            if time.monotonic() >= deadline:
                raise LibraryBusy(f"the template library is locked by another run (waited {LOCK_WAIT_S:g} s)") from None
            time.sleep(0.05)
        try:
            yield
        finally:
            oslayer.unlock(fd)
    finally:
        os.close(fd)


def store(t, fingerprint=None):
    with _library_lock():       # P10
        return _store(t, fingerprint)


def _store(t, fingerprint=None):
    """Write a specialised template, checked again here: (template, version, created). The same sha is the same
    version (nothing written); any change is v<N+1>. Versions are immutable."""
'''),
    Edit("P10", "j2_template_lib.py", r'''def mark_used(t, use, fingerprint=None):
    """Append a use (run, workflow, atom, action) to the version's meta.json and the index; and the need's
    fingerprint, so the same need reuses it next time."""
''', r'''def mark_used(t, use, fingerprint=None):
    with _library_lock():       # P10
        return _mark_used(t, use, fingerprint)


def _mark_used(t, use, fingerprint=None):
    """Append a use (run, workflow, atom, action) to the version's meta.json and the index; and the need's
    fingerprint, so the same need reuses it next time."""
'''),
    # ---- P10 (sync 6, D181): the two more runtime writers of the index
    Edit("P10", "j2_template_lib.py", r'''def note_version(t, **notes):
    """Provenance notes (adapted_from, renamed_from) on a stored version: meta.json and its index row."""
''', r'''def note_version(t, **notes):
    with _library_lock():       # P10
        return _note_version(t, **notes)


def _note_version(t, **notes):
    """Provenance notes (adapted_from, renamed_from) on a stored version: meta.json and its index row."""
'''),
    Edit("P10", "j2_template_lib.py", r'''def mark_run_template_used(tid, use):
    """A run that started from a run template, added to its used_by (template.json and the index row), once."""
''', r'''def mark_run_template_used(tid, use):
    with _library_lock():       # P10
        return _mark_run_template_used(tid, use)


def _mark_run_template_used(tid, use):
    """A run that started from a run template, added to its used_by (template.json and the index row), once."""
'''),
    # ---- P12: Windows (D101), nothing else
    Edit("P12", "j2_template_lib.py", "import os\nimport re\nimport shutil\n", "import os\nfrom sutra_app import oslayer\nimport re\nimport shutil\n"),
    Edit("P12", "j2_template_lib.py", "        f.write(text)\n    os.replace(tmp, path)\n", "        f.write(text)\n    oslayer.replace(tmp, path)\n"),
    Edit("P12", "j2_template_lib.py", '''    return os.path.join("templates", rec["artifact"], slug(rec["section"]), f"{slug(rec['template'])}@v{rec['version']}")\n''',
         '''    return "/".join(("templates", rec["artifact"], slug(rec["section"]), f"{slug(rec['template'])}@v{rec['version']}"))     # P12: a path in a record is POSIX on every system\n'''),
    Edit("P12", "j2_template_lib.py", ''' or ".." in rel.split(os.sep):\n''', ''' or ".." in re.split(r"[\\\\/]", rel):          # P12: either separator, on every system\n'''),
    Edit("P12", "j2_check.py", '''    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text, start_new_session=True)\n''',
         '''    # start_new_session is ignored on Windows. The output is decoded as UTF-8 whatever the console code page is.
    decoding = {"encoding": "utf-8", "errors": "replace"} if text else {}
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text, start_new_session=True, **decoding)\n'''),
    Edit("P12", "j2_check.py", '''    for p in (os.getenv("J2_CHROME"), os.getenv("CHROME_PATH"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",\n''',
         '''    windows = [os.path.join(root, "Google", "Chrome", "Application", "chrome.exe")
               for root in (os.getenv(name) for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "LOCALAPPDATA")) if root]
    for p in (os.getenv("J2_CHROME"), os.getenv("CHROME_PATH"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", *windows,\n'''),
    # ---- P2 (third edit), P17 and P18: j2_types.py
    Edit("P17", "j2_types.py", "import shutil\nimport sys\n\nHERE = os.path.dirname(os.path.abspath(__file__))\n",
         "import shutil\nimport sys\nimport time\nfrom sutra_app import oslayer      # P17: the lock and the atomic replace\n\nHERE = os.path.dirname(os.path.abspath(__file__))\n"),
    Edit("P2", "j2_types.py", 'AGENTS_DIR = os.path.join(HERE, "agents", "j2")\n',
         'AGENTS_DIR = os.getenv("J2_AGENTS_DIR") or os.path.join(HERE, "agents", "j2")     # P2: a page type\'s builder is a role file\n'),
    Edit("P17", "j2_types.py", '''LOCAL_TYPES_PATH = os.path.join(HERE, "artifacts", "types.local.json")
LOCAL_LIBRARY_DIR = os.path.join(HERE, "library", "types")
''', '''_STORE = os.getenv("J2_TYPES_DIR")      # P17: the host's per-user folder for the types runs make; unset: J2's own places
LOCAL_TYPES_PATH = os.path.join(_STORE, "types.local.json") if _STORE else os.path.join(HERE, "artifacts", "types.local.json")
LOCAL_LIBRARY_DIR = os.path.join(_STORE, "templates") if _STORE else os.path.join(HERE, "library", "types")
TYPES_LOCK_WAIT_S = 30.0      # P17: the most `create` waits for the store lock
'''),
    Edit("P18", "j2_types.py", '''NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
''', '''NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

# P18: output types the host registers in its own process (the project output): name -> {"entry": json-safe entry,
# "extras": what data cannot carry (callables, flags), handed to output_def unchanged}. Never written to a file.
HOST = {}


def register(entry, extras=None):
    """P18: add a host type. `entry` is a JSON-safe `kind: "type"` entry whose name NAME_RE accepts and that names its owner
    in entry["host"]. A name types.json or the local store already has is refused (ValueError); the same owner registering
    the same name again replaces its entry; another owner is refused. `extras` (callables, flags) ride beside the entry."""
    try:
        entry = json.loads(json.dumps(entry))      # a copy, and the proof that it is JSON-safe
    except (TypeError, ValueError) as e:
        raise ValueError(f"host type: the entry is not JSON-safe ({e})") from None
    if not isinstance(entry, dict) or entry.get("kind") != "type":
        raise ValueError("host type: the entry must be an object with kind: type")
    name, owner = entry.get("name"), entry.get("host")
    if not NAME_RE.match(str(name or "")):
        raise ValueError(f"host type {name!r}: the name must match {NAME_RE.pattern}")
    if not isinstance(owner, str) or not owner:
        raise ValueError(f"host type {name}: the entry must name its owner in \\"host\\"")
    with open(TYPES_PATH, encoding="utf-8") as f:
        taken = {t.get("name") for t in json.load(f)["types"]} | {t.get("name") for t in _read_local()}
    if name in taken:
        raise ValueError(f"host type {name}: the name is already a type of {os.path.basename(TYPES_PATH)} or of the local store")
    if name in HOST and HOST[name]["entry"].get("host") != owner:
        raise ValueError(f"host type {name}: already registered by {HOST[name]['entry'].get('host')}")
    HOST[name] = {"entry": entry, "extras": dict(extras or {})}
    _CACHE.clear()
'''),
    Edit("P18", "j2_types.py", '''        d["types"][at:at] = local
''', '''        d["types"][at:at] = local + [e["entry"] for e in HOST.values()]      # P18
'''),
    Edit("P18", "j2_types.py", '''    rel = e.get("template") or f"templates/{name}/generic.json"
    if rel.startswith(LOCAL_LIBRARY_REL + "/"):
''', '''    rel = e.get("template") or f"templates/{name}/generic.json"
    if os.path.isabs(rel):      # P18: a host type's template is a file of the host
        return rel
    if rel.startswith(LOCAL_LIBRARY_REL + "/"):
'''),
    Edit("P18", "j2_types.py", '''        out["mock"] = dict(entry["mock"])
    return out
''', '''        out["mock"] = dict(entry["mock"])
    out.update(HOST.get(name, {}).get("extras") or {})      # P18: the keys J2 cannot read from data (single, workspace, mocks)
    return out
'''),
    Edit("P18", "j2_types.py", '''        if t.get("kind") != "type":
            continue
        guide = ((d.get("forms")''', '''        if t.get("kind") != "type" or t.get("name") in HOST:      # P18: a host type is not a template-library artifact
            continue
        guide = ((d.get("forms")'''),
    Edit("P17", "j2_types.py", '''def _write_local(types):
    os.makedirs(os.path.dirname(LOCAL_TYPES_PATH), exist_ok=True)
    with open(LOCAL_TYPES_PATH, "w", encoding="utf-8") as f:
        f.write('{\\n  "types": [\\n' + ",\\n".join("    " + json.dumps(t, ensure_ascii=False) for t in types) + "\\n  ]\\n}\\n")
''', '''def _write_local(types):
    os.makedirs(os.path.dirname(LOCAL_TYPES_PATH), exist_ok=True)
    tmp = LOCAL_TYPES_PATH + ".tmp"      # P17: a temp file and a replace, so a reader never sees half a file
    with open(tmp, "w", encoding="utf-8") as f:
        f.write('{\\n  "types": [\\n' + ",\\n".join("    " + json.dumps(t, ensure_ascii=False) for t in types) + "\\n  ]\\n}\\n")
    oslayer.replace(tmp, LOCAL_TYPES_PATH)
'''),
    Edit("P17", "j2_types.py", '''def create(name, label, secs, file=None, path=None, practice=None, form=None):
    """Save a new document type, locally:''', '''def create(name, label, secs, file=None, path=None, practice=None, form=None):
    """P17: `_create` inside an exclusive lock on <store>/.lock (oslayer.try_lock, as P10): the whole read-modify-write is one
    step across runs and processes. Waits TYPES_LOCK_WAIT_S; a busy lock is a ValueError, which J2 already turns into the
    event new_type_refused."""
    store = os.path.dirname(LOCAL_TYPES_PATH)
    os.makedirs(store, exist_ok=True)
    fd = os.open(os.path.join(store, ".lock"), os.O_RDWR | oslayer.O_BINARY | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + TYPES_LOCK_WAIT_S
        while not oslayer.try_lock(fd):
            if time.monotonic() >= deadline:
                raise ValueError(f"new type {name}: the local type store is locked by another run "
                                 f"(waited {TYPES_LOCK_WAIT_S:g} s)") from None
            time.sleep(0.05)
        try:
            return _create(name, label, secs, file, path, practice, form)
        finally:
            oslayer.unlock(fd)
    finally:
        os.close(fd)


def _create(name, label, secs, file=None, path=None, practice=None, form=None):
    """Save a new document type, locally:'''),
    # ---- P27 (main c9d4e662): a type's file pattern lists files only; Windows refuses to open (hash) a folder it matches
    Edit("P27", "j2_artifacts.py", 'sorted(glob.glob(os.path.join(d, t["file"])), key=_num)] \\\n',
         'sorted(glob.glob(os.path.join(d, t["file"])), key=_num) if os.path.isfile(p)] \\\n'),
)

EDITS = J2_EDITS + OTHER_EDITS

PATCH_NOTES = {
    "P1": P1_NOTE,
    "P2": "role files: `J2_DIR` (j2.py), `AGENTS` (j2_realization.py) and `AGENTS_DIR` (j2_types.py: a page type's builder is a role file) are `J2_AGENTS_DIR` or the package copy `agents/j2/`; conditions, `artifacts/types.json` and `templates/` stay package-relative; `J2_RUNS_DIR`, `J2_MEMORY_FILE`, `J2_PLAYBOOK_FILE` and `J2_LIBRARY_DIR` were already environment-driven",
    "P3": "`J2Run.__init__(*, run_dir=None, run_id=None, hooks=None)`: the host names the run folder and id (the first `reset` takes them; `run_id` without `run_dir` is an error; default id = folder name without `j2-`, as before); `self.hooks` defaults to `NullHooks()`",
    "P4": "`user_says` returns False at once when the run holds its lock (J2 took the lock before it looked at the status and then waited, 1.21 s measured, and started a new turn); new `apply_override(cmd)`: the same non-blocking lock around `_override`, for the host (the server checked the key)",
    "P5": "explicit-path variants, the old constants as defaults: `saved_dir(name, runs_dir=None)`, `list_runs(limit=60, runs_dir=None)`, `saved_snapshot_dir(d, name, since=0)` (called by `saved_snapshot`), `load/save/clear_lessons(path=None)`, `load/save/clear_playbooks(path=None)`",
    "P7": "every `llm.ask` is inside a tagged block: `J2Run.call` (function, step, cycle, stage, call_no, builder atom), the chat summary, the template generator and the reviewer through `_ask(...)` (`_ask` passes `timeout` on; since sync 5 `call` keeps J2's retry loop and `except llm.CallTimeout`); the planner call of `_plan_stages` (`_run_tpl_start` for a run template, which calls `_deliverables` itself, or `_deliverables`: one expression, so both paths), made before the turn of Adaptation, runs in `llm.tagged(function=\"adaptation\", step=2, ...)`; the planner and judge (`Session.ask`, j2_realization.py) name role and purpose and inherit the turn's function; each hook-observed turn runs inside `llm.tagged(function, step, cycle, stage)`",
    "P8": "hook calls (`NullHooks` by default, nothing is built for it): `post` (`message_posted`, not for ASK_REQUESTER), `_ask_user` (`message_posted(m, questions=)` once `paused` is set), `save` (`record_saved`), `_log_call` (`call_finished`; `calls.jsonl` also gains `provider` and `usd`), the turn dispatch (`turn_started`, `turn_finished` through `_dispatch_turn`), `user_says` and both run ends (`run_status`; since sync 6 the first fires after `_make_report` has started the reviewer thread, so the host joins that thread, D179), the crash path (`run_error`); a hook error goes to stderr unless it is fatal (`fatal = True` or a class named RecordRejected)",
    "P9": "`call` appends `system_addendum(fn)` to the system prompt: empty unless the hooks have a node-context file (anchored on the delay lines of `call` only, `if self.calls and call_delay():`; the two other `call_delay()` sites, in `_summarize` and the reviewer call, are not under a patch)",
    "P10": "`store`, `mark_used`, `note_version` and `mark_run_template_used` (sync 6, D181: four writers) of the template library run inside an exclusive lock on `<library>/.lock` (`oslayer.try_lock`: `flock`, or `msvcrt.locking` on Windows) (waits `LOCK_WAIT_S` = 30 s, then raises `LibraryBusy(RuntimeError)`, which `_route_template` already turns into the generic template); the originals are kept as `_store`, `_mark_used`, `_note_version` and `_mark_run_template_used` (a wrapper never calls another wrapper: the lock is not reentrant); `save_run_template`, `move_versions` and the module's `__main__` commands are developer tools and stay unpatched",
    "P21": "`_tool_record` (D245, builder tools live): a file outside the builder's folder that changed during a tools call is not the builder's write when it is one of the host's own run files (`rehydrate.HOST_FILES`: the live view, the snapshot, the event log) or the atomic-write temp file of one (`oslayer.temp_target` maps it back), unless the CLI's tool calls (`LAST_META[\"tool_calls\"]`) name it, so a builder that touches a host file is still stopped",
    "P22": "`_register` (D246): a done-when item a real run checks is decided by the run's receipt; a proposal without a real run that covers it is refused (\"the real run of 'X' checks\"), not the real-run workflow, and the real-run workflow's refusal for an item another workflow covers names that workflow and says the conflict is there (`_cover_conflict`): one registered or held is to be superseded (named in `replaces`) or replaced by one that doesn't cover the item, and a waiting workflow a proposal of the same batch supersedes no longer counts against the real run; one running or done can't be superseded, so the refusal says the item can't be met by that real run in this run; a rejection the validator's last call also made (amended in D431: the same code-set key, which `_reject` now takes from every caller: the rule and code-made ids only, never a name, an agent's or the judge's words; in `_register` the key comes from `key_rules`, one entry per test of the reason chain with the same test in the same order, each its own rule name, and a reason no entry names gets its own `(\"unkeyed\",)`, never another rule's; `test_p22_every_rejection_path_in_the_validator_sets_its_own_key` checks this from j2.py's code; the worded reason is kept for display) is a repeated failure: `_agree` stops the cycle with an Identity limit for the Requester (`_repeat_stop`, \"The same failure came back twice in a row\"), resuming where the validator was going when it registered something (runs/j2-20261118-110800-0c75: the script was refused four times for an item the run notes covered)",
    "P23": "`ended_workable(run_dir)` (D247) is true only for a clean end: `summary.json`'s outcome starts \"Done:\" and the last audit passes `workable()` with `accepted` and `after_real_run` emptied, so a run that ended \"Done with open items\" (an item accepted as it is, a real run that never ran or did not pass) is never saved as a run template (`_save_run_template`), reused as a folder (`_reuse_folder`) or served by the content door",
    "P24": "(D250, prompt-changing per D249) Priority's move is each workflow's id and its envelope: both pricing turns ask for `PRICE_FMT` (`[{id, envelope}]`) and `_carry` expands the reply to Adaptation's proposal (the table Priority was shown, then the proposals, by id then name) plus the envelope; a field the move sends with another value than Adaptation proposed is not taken, and the validator posts Adaptation a visible note naming the field and the value (no `carried` autofix); `granted` charges `envelope.money_limit`, also with the rate card on; `_register` rejects a COUNTER without a money limit (\"a counter must state its money limit\") and, with the rate card on, a limit below the rate-card price (the floor); J2's mock Priority sends `{id, name, envelope}`, its cycle-1 COUNTER sets the animations' limit to 10, and the mock Adaptation answers by revising their parts (runs/j2-20261118-090053-4a9c: a COUNTER's terms were logged as \"kept as Adaptation proposed it\")",
    "P25": "(D251, prompt-changing per D249: the raise question's text) `BUDGET_CAP` comes from `J2_BUDGET_CAP` only when it is set; unset means no cap (`budget_room` is unbounded, `_raise_budget` adds the whole approval, and a raise option says \"Or type your own number\" without \"up to N\", `own_number`); Decide for me (`_auto_pick`) waits for the Requester instead of answering an approval, a ruling_budget question or a limit option that adds credits; a question that asks for more credits ends with the credits approved so far (`_so_far`: \"So far: 100 + 30 = 130 work credits approved.\")",
    "P27": "(main `c9d4e662`) `rows()` in `j2_artifacts.py` lists only the files a type's `*` pattern matches, never a folder: Windows refuses to open a folder to hash it (PermissionError, Errno 13), which made every page that lists a run's files fail",
    "P28": "(D431) every build failure records a code-made `failure` on its workflow (`[kind, detail]`: `outside_write` with every outside file, `BuilderToolFault.files`; `real_path`; `unusable_reply`; `no_artifact`; `no_build`), and `build_failure(w)` gives a finished build's signature (that, or `checks` with the sorted (type, evidence) of its atoms' failed receipts, never a name or a check's words; None for a pass)",
    "P29": "(D431) with nothing built (`self.sites` empty): `workable()` gives \"nothing has been built yet\" for an audit at `version` 0 (an audit without `version` is unchanged), so Identity's done goes back to Adaptation; `_identity_limit` offers no \"Leave out\" that leaves no done-when item but the gate (`GATE_TEXT`) to build (a partial one stays, and \"Stop here\" is added when fewer than two options are left; a lone \"Stop here\" is asked, never applied without the Requester); `_identity_hears_requester` applies a typed answer that leaves out everything still to build as a stop (\"Stopped on the Requester's decision (...): nothing was built.\"); Decide for me never answers a limit question (`AUTO_ASK` holds `limit`, so `_auto_pick` waits and the snapshot's `auto_waits` says so, as for P26's dollar question): run 17e1's second limit question took its last option, which left out every item; `_identity_audit` asks the Requester (the limit question) when a necessary condition the charter decides (`from_charter`, set by `_folder_condition` when the charter lists no files or no test) is unmet for the same code-made reason (its id and evidence) in two audits in a row, whatever else moved: \"This condition comes from the charter, and building can't change it. The charter needs fixing.\" (any other condition goes back to Adaptation) (runs/j2-20261123-103238-3429: C1 \"the charter lists no files\", C2 \"the test '' is not a file in the folder\")",
    "P31": "(D434) a real run's dry run on copies that ran and did not exit 0 (a timeout too) is a build failure, never a question: `_dry_run_failed(w, dry, detail)` sets the workflow `failed` with the code-made `failure` `[\"dry_run\", \"exit <n>: <last output line>\"]` (`real_run_dry` returns its output's end with the temp root written `<copy>`, so P28's signature is the same across temp folders, and every real-run receipt keeps it in `dry_run.output`), keeps the output on the workflow (`dry_run_output`, shown as `dry_run_failure` to the builder of the next workflow whose real run checks one of its items, by item number, because a folder run drops `revises`), writes a not-run receipt, forgets its code (`real_runs_asked`), posts a system note (not to the Requester), and hands Adaptation a `propose` unless `_repeat_build_stop` stops the cycle (a passing build between two dry-run failures keeps P28's memory); a planned real run's item is no longer pending once any real run that checks it has a receipt (a replacement after a failed dry run); `_identity_real_run` takes exactly `RUN <code>` (runs) or the whole reply `REAL_RUN_DECLINE` (\"Don't run\", any case: the not-run receipt, then `_goal_done`), and any other reply, or one Decide for me sent, is asked again with the same code (\"Not run. Press Run or type RUN <code>.\": no receipt, the run stays paused); the snapshot's `paused.code` gives the card's Run button its code (port edit E28); no word of a reply is read; a real-run folder written `~/x` is the folder it names (beta fix, run 8b10: refused as not absolute, then, written out, as not named in the brief): `home_expanded` writes `~` out in its folder, reads and command arguments, `real_run_problems` judges that form and accepts the folder when the brief names it either way (`home_tilde`), and `_register` stores it written out, so the dry run and the approved run get absolute paths",
    "P32": "(D435) the dry run on copies always runs inside the sandbox runtime (`J2_SANDBOX_CMD`, network `allowedDomains: []`), whatever `J2_SANDBOX` says: `real_run_dry` passes `fence` in the run it hands `real_run` (code sets it there only; a stored `real_run` keeps `command`, `folder`, `reads`, `why`), and `real_run` with `fence` and no sandbox runtime (the program not on PATH, as on Windows, or an offline run without `J2_SANDBOX`) returns `ran` false (\"no sandbox runtime here: ...\") and runs nothing; both dry-run results carry `fenced` (it ran, so fenced); the real-run card says \"The dry run had no network access: results may differ.\" after a fenced dry run, else \"No dry run: this computer has no sandbox, so it wasn't tested first\", and the Requester is still asked; the approved real run is unchanged (it follows `J2_SANDBOX`); the environment is not scrubbed (a follow-up)",
    "P33": "(D436, prompt-changing per D249: a new Audit prompt after an approved real run; no golden scenario reaches it) after an approved real run that ran and exited 0, `_identity_real_run` makes one Audit call (`_judge_real_run`, a plain `self.call`, so calls.jsonl, budget and dollar accounting count it; its format has no `next`, and code reads no route from it) with the Requester's brief, the items the run decides (its `real_run.checks`), the command, the dry run's created/changed/deleted lists and the real run's output end; an item passes only when Audit filed PASS with evidence for it (no finding, or empty evidence, does not; no word of the output is read by code); the receipt gains `audit` `{item: {verdict, evidence}}`, the audit row's note gives the receipt evidence and Audit's, a judged failure is `NEEDS_REVISION`, and `real_runs_done` is true only when Audit passed every item the run decides (so P30's `real-run` item check requires it too); a run not approved, not run, or not exit 0 makes no Audit call and its items fail as before; without the real run the items stay pending (SUT-18: exit 0 alone passed the item)",
    "P35": "(D438, prompt-changing per D249: the real-run rule asks for expect; it joins `ATOM_RULES` only with builder tools on and a form with a `test_runner`, which no golden scenario has) a planned real run carries `expect` `{\"created\": [glob], \"changed\": [glob], \"deleted\": [glob]}` relative to its folder, set by whoever proposes the real run (Adaptation, next to `command`; `REAL_RUN_EXPECT_RULE` follows `artifacts/real_run.md` in the proposal rules); `_register` refuses a missing or malformed one (`real_run_expect_problems`: exactly the three lists, non-empty relative paths or globs, not all empty) with the P22 key `(\"real_run_expect\",)` (no `key_rules` entry: that list follows the reason chain only) and stores it; `real_run_dry` also diffs every read-only copy (`reads_changed` `{n: diff}`); `_ask_real_run`, after the real-folder stop and P31's exit check, sends a dry run that changed a read-only copy, or whose created/changed/deleted paths differ from `expect` (`expect_mismatch`: `fnmatchcase`, sorted, a glob that matched nothing or a path no glob matched; no word read; kept as `dry_run.expect_mismatch`), through P31's `_dry_run_failed` (back to the build, P28, never to the Requester); a real run registered before P35 (no `expect`) skips only the expect comparison; with no sandbox runtime (P32) there is no dry run, so nothing is compared (SUT-12: `copy.py <input> <output>` called with the folders swapped wrote into the read-only copy and was shown \"0 created\")",
    "P34": "(D437) `_tool_record` first removes `<builder folder>/.claude` entirely (`shutil.rmtree`, errors ignored), whatever it holds: the Claude CLI makes it in its cwd (the output folder), with an empty `.cc-writes` staging folder inside; it runs after every tools call (a failed or stopped one too) and before `file_states`, so the files-written list, the P21/P28 outside-write check and the folder limits never see it; `_publish_out` copies the output folder into `site/` without `.claude` (`shutil.ignore_patterns`) (SUT-12: `.claude/.cc-writes` showed in output and `site/` folders)",
    "P30": "(D433, prompt-changing per D249: Identity's intake format and rule, every builder's reply format and brief) every done-when item has a runnable check and a status its builder sets, both by item text: Identity returns `item_checks` (one per item, the type one of the form's `check_types` or `real-run`; `_item_checks_from` keeps `type`, `target`, `expect`), code stores them in `goal[\"item_checks\"]` (a change request keeps those of kept items; `GATE_TEXT` gets code's `render-check`; `stage_goal`'s items `section-not-empty` on their section) and `_stamp_check` refuses an item without one; the intake prompt adds `BEHAVIOUR_RULE` (every required behaviour is its own item); a builder's brief lists its items (`_owned_items`: covered, and the items of the findings it fixes) with check and status, every builder reply format asks for `item_status` (`ITEM_STATUS_FMT`; the closed artifact reply schema takes `ITEM_STATUS_SCHEMA`), and `_store_item_status` keeps it on the workflow (missing or unknown: `not_built`; `blocked` without a reason: `not_built`; no word of the reply is read; the mock builders, and a section the content door serves unchanged, set every owned item built, `_built_status`; in mock mode a reply without `item_checks` gets `mock_item_check` per item; the scripted Identity reply carries one per item only when a scripted port serves a run outside mock mode; code fills none in a live run); a charter refused a second time while an item has no check never starts work: the run stops and Identity asks the Requester, naming the items; at every audit `_item_check_gate` runs each passed item's check (`_run_item_check`: the real run's receipt, the render check, the folder test rerun, or `run_check`) and makes a PASS whose check did not pass, did not run or does not exist BLOCKED_BY_EVIDENCE with code's evidence; `_goal_done` and `_ship_outcome` end \"Done with open items\" while an item's latest done owner did not set it built (`_open_items`; the no-errors gate, code's own `render-check`, needs no builder); an item its latest done owner set `blocked` (always with a reason, `_blocked_items`; never an item a planned real run decides, which only its receipt and Audit decide, review R3-1) does not hold back the planned real run: J2.h asks for it once everything else is workable, and `_goal_done` ends \"Done with open items\" naming the item once, with its reason, not \"the real run did not pass\" (beta fix, run 8b10); an item the latest audit marks TO_BE_CONFIRMED because the charter's `to_be_confirmed` (Identity's field) names it is blocked too, its reason that entry's `fact` (`_tbc_blocked`, never a real-run item; beta fix b), and `_ship_outcome` lists a blocked item once; `ITEM_STATUS_FMT` tells every builder that an item whose action was prepared but not performed (a message written but never sent, for lack of access or credentials) is `blocked` with that reason, never `built`, and that a blocked reason is the fact or access it needs (beta fix c, prompt-changing per D249; code reads no word of the reason); `not_built` still holds it back. With no real run left to ask, J2.h ends the run at once when every other item is built and passes and only blocked items are left: `_goal_done` with no Identity, Adaptation or Audit call (beta fix d); the outcome names each blocked item as \"<item> blocked: needs <reason or fact>. Send it as a follow-up to finish.\" (the reason an agent's field, the hint code's text); a follow-up to a charter with a `to_be_confirmed` entry goes through Identity's change-request intake (the J2_FIXES path) with the current charter, whose prompt then says a fact the follow-up gives leaves its entry, so Identity can drop it and the item is built again (the trigger is the entry, never the message's words; without one a follow-up goes to Adaptation as before); a design-document stage left with blocked items keeps their lines in its `stage_archive` entry (`blocked`, only when there are some), and the run's outcome names them by stage (`_stage_blocked`, in `_goal_done` and `_ship_outcome`; review R4-1). A charter without `item_checks` behaves as before (SUT-18, run 01a2: scheduling had no item, and an item described as not yet built passed Audit)",
    "P26": "(D421, D422, prompt-changing in dollar mode per D249: the raise question's text) dollar mode is on only when `J2_USD_BUDGET` is set (`USD_BUDGET`, `USD_CAP`, `USD_PER_CREDIT`, `USD_PER_MTOK_FALLBACK`, `USD_RAISE_SHARE`, `BIG_RAISE`, `USD_RATE_MIN_CALLS`); off, nothing changes. `_log_call` adds each call's API price to `usd_used` (`_count_usd`, `call_usd`: the usd it reported, else its tokens, or characters / 4, at the run's own rate, else the fallback rate) and writes `usd_counted` and `usd_estimated` on its `calls.jsonl` row; the summary's `budget.usd` (`_usd_metrics`). The starting credits are `ceil(USD_BUDGET / USD_PER_CREDIT)` (`J2_BUDGET` ignored) and follow the dollars left at the run's one rate (`_usd_rate`: its dollars per credit from its 8th call, else `USD_PER_CREDIT`; `_usd_credits`) (`_top_up`, a `code: true` raise, no question, no cap) at the cycle start, the envelope check (before Priority can hold an uncharged workflow), an over-envelope approval, a ruling over budget and a change that costs more than is left; between turns, `usd_used >= usd_limit` hands Identity the dollar limit; the limit question is code's (\"This run has used $X of $Y (API price). Add $Z? So far: $Y approved.\", `_usd_raise`, P25's `_so_far` returns `_usd_so_far`), its continue option and `[adds $Z]` tail are in dollars, the answer's amount is read by code (`parse_usd`, never the model's credits), a typed raise over `BIG_RAISE` times the limit is asked back once (`_usd_confirm`; the same amount sent again, `confirm_usd`, confirms it; `Add $0` is asked again), the raise goes to `_usd_add` (capped by `USD_CAP`), which adds the credits the added dollars buy at the rate the question was priced at (`usd_rate` in its handoff, R2-1); where the dollars left cannot fund an over-envelope approval (the dollar limit, resuming at the envelope check), a ruling over budget (its own question, in dollars, keeping its `budget` so the option says `[adds $Z]`; a typed amount is the raise when the Requester chose to add (the model's choice 1, or the card's own `USD_RAISE_TEXT`), `Add $0` and an amount that funds less than the ruling are asked again and over `BIG_RAISE` times the limit is asked back once, `_usd_ruling_reask`) or a document chain (`_stage_gate`, after a top-up) the question is in dollars; a stated `budget_needed` the dollars left fund is topped up, not asked for; Identity is told an `Out of budget` limit in dollars; Decide for me (`_auto_pick`) never answers it (`auto_waits`)",
    "P19": "`_make_report` asks `self._hook(\"review_enabled\")` (sync 6, D179): only an explicit `False` switches the reviewer off (no thread, `ai_calls` without the reviewer's call) and the run report then says \"The reviewer is switched off in this team's settings.\"; under `NullHooks` `_hook` returns `None`, so a bare J2 and a host without the hook behave as before",
    "P11": "`J2Run.rehydrate(src_dir)` delegates to `rehydrate.py`",
    "P12": "Windows (D101), nothing else: `j2_check.find_chrome` also looks in the Windows install folders of Chrome, `j2_check._chrome` decodes Chrome's output as UTF-8 with replacement, `j2_template_lib` writes its index with `oslayer.replace` (a rename that waits out a reader) and takes its library lock through `oslayer` (P10), records a template's saved path with `/` on every system (`run_tpl_rel`) and splits it on either separator when it checks for `..` (`run_saved_dir`)",
    "P14": "`J2Run._plan_stages` returns early for an output that says `single` (`if self.stages or self.goal or (self.out or {}).get(\"single\"):`, guarded since sync 5 because `_plan_stages` runs while `out` is still `None`): named documents in a brief (\"update the PRD in the repo\") do not swap the project output for a PRD stage chain, and a host-pinned project run makes no planner call (D129). No other output has `single`. The output itself is registered by `sutra_app/engine/capabilities/` through P18 (Sutra's own files, not J2's)",
    "P16": "Decide for me's two writes of `settings.json` (`set_auto`, and the one at the start of `_run_safe`) add `decide_for_me` to what the file holds instead of replacing it: the engine host writes its resolved engine settings to the same file before J2 starts, and that dump now survives (`saved_snapshot` keeps reading `decide_for_me` from the same file)",
    "P17": "`j2_types.py`: the types a run makes (`create`) are kept where the host says (`J2_TYPES_DIR`: `types.local.json` and `templates/<name>/generic.json` below it; unset: J2's own places, so J2's flow test and developer use are unchanged); `_write_local` writes a temp file and `oslayer.replace`s it; `create` runs the original (now `_create`) inside an exclusive lock on `<store>/.lock` (`oslayer.try_lock`, waits `TYPES_LOCK_WAIT_S` = 30 s; a busy lock is a `ValueError`, which `J2Run._deliverables` already turns into the event `new_type_refused`). `promote` (a developer command) is not changed (D163)",
    "P18": "`j2_types.py`: host type registration (D164): `HOST` and `register(entry, extras=None)` (a JSON-safe `kind: \"type\"` entry that names its owner in `host`; a name of `types.json` or of the local store is refused; the same owner again replaces; another owner is refused), `_read_types` adds the host entries after the local types, `template_path` accepts an absolute path, `load` returns the registered `extras` (keys data cannot carry: `single`, `workspace`, `deliver`, the mocks), `templated` skips a host type",
    "P15": "seed data: the six `runs[].library` values of `library/index.json` that held a J2 developer's absolute home-folder path become `not recorded` (R5: no absolute home path in any file of this product); nothing reads the field; the two `/tmp/` values stay",
}


# ---- applying edits -----------------------------------------------------------------------------------------------
def apply_edits(text: str, edits, *, name: str = "?"):
    """`text` with every edit applied in order. Each `old` must occur exactly `count` times in the text AS IT IS at that
    point; the same holds for the finished text and every `new` (an edit must not be undone or split by a later one).
    Returns (new text, {patch id: [(first line, last line), ...]})."""
    for e in edits:
        found = text.count(e.old)
        if found != e.count:
            raise VendorError(f"{name}: {e.patch} expects its anchor {e.count} time(s), found {found}: {e.old[:90]!r}")
        text = text.replace(e.old, e.new)
    ranges = {}
    for e in edits:
        if text.count(e.new) != e.count:
            raise VendorError(f"{name}: after all edits {e.patch} appears {text.count(e.new)} time(s), not {e.count}: {e.new[:90]!r}")
        start = 0
        for _ in range(e.count):
            at = text.index(e.new, start)
            first = text.count("\n", 0, at) + 1
            ranges.setdefault(e.patch, []).append((first, first + e.new.rstrip("\n").count("\n")))
            start = at + len(e.new)
    return text, {k: sorted(v) for k, v in ranges.items()}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- P15: the one data patch ---------------------------------------------------------------------------------------------
SEED_INDEX = "library/index.json"
HOME_PATH = re.compile(r'"library": "/(?:Users|home)/[^"]*"')        # the pattern only: a literal path would put one into this product (R5)
NOT_RECORDED = '"library": "not recorded"'
HOME_PATHS = 6                                                          # what the pinned seed holds; J2 changing it stops the run


def scrub_seed_index(text: str):
    """P15: (new text, lines). The seed's `library/index.json` records, per development run, the library folder of the J2
    developer's machine (`runs[].library`). Six of those values are absolute home-folder paths; R5 forbids one in any file of this
    product and nothing reads the field, so each becomes `not recorded` (the two `/tmp/` values are left as they are). `lines`
    are the line numbers of the changed lines (the same in both texts: no newline is added or removed). It must find exactly
    HOME_PATHS values: any other number means J2 changed under the patch, which stops the run like a missing anchor."""
    found = list(HOME_PATH.finditer(text))
    if len(found) != HOME_PATHS:
        raise VendorError(f"{SEED_INDEX}: P15 expects {HOME_PATHS} home-folder paths in `runs[].library`, found {len(found)}")
    lines = sorted({text.count("\n", 0, m.start()) + 1 for m in found})
    return HOME_PATH.sub(NOT_RECORDED, text), lines


# ---- reading J2 ----------------------------------------------------------------------------------------------------
class Source:
    """The J2 files of one commit, read from `root`: an extraction of `prototypes/j2` (plain files; `commit` names the sutra commit
    it was taken from). A `root` that is itself a git repository is read as that commit's blobs instead."""

    def __init__(self, root: Path, commit: Optional[str]):
        self.root = Path(root)
        if (self.root / ".git").exists():
            rev = commit or "HEAD"
            out = self._git("rev-parse", "--verify", f"{rev}^{{commit}}")
            self.commit, self.git = out.decode().strip(), True
        else:
            if not commit:
                raise VendorError(f"{root} has no git history: name the commit the extraction was taken from with --commit")
            self.commit, self.git = commit, False

    def _git(self, *args: str) -> bytes:
        done = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True)
        if done.returncode:
            raise VendorError(f"git {' '.join(args)}: {done.stderr.decode().strip()}")
        return done.stdout

    def read(self, rel: str) -> bytes:
        if self.git:
            return self._git("show", f"{self.commit}:{rel}")
        try:
            return (self.root / rel).read_bytes()
        except OSError as exc:
            raise VendorError(f"J2 file missing: {rel} ({exc.strerror})") from None

    def tree(self, rel: str) -> list:
        """Every file below the folder `rel`, as paths relative to the J2 root, sorted."""
        if self.git:
            out = self._git("ls-tree", "-r", "--name-only", self.commit, rel + "/")
            return sorted(line for line in out.decode().splitlines() if line)
        base = self.root / rel
        if not base.is_dir():
            raise VendorError(f"J2 folder missing: {rel}")
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file() and not p.is_symlink())


# ---- building the tree in memory --------------------------------------------------------------------------------------
def build(src: Source):
    """(files, rows, ranges): files maps a path relative to the repo to its bytes; rows are the VENDORED.md file rows
    (vendored path, J2 path, patch ids, J2 sha256, vendored sha256); ranges maps a patch id to ['file:first-last', ...]."""
    files, rows, ranges = {}, [], {}

    def add(dest: str, origin: str, data: bytes, original: bytes, patches=()):
        files[dest] = data
        rows.append((dest, origin, ",".join(patches), sha256(original), sha256(data)))

    for name in CODE:
        raw = src.read(name)
        mine = [e for e in EDITS if e.file == name]
        try:
            text, p1 = apply_p1(raw.decode("utf-8"), name)
            text, found = apply_edits(text, mine, name=name)
        except UnicodeDecodeError as exc:
            raise VendorError(f"{name} is not UTF-8: {exc}") from None
        if p1:
            found.setdefault("P1", []).extend((n, n) for n in p1_lines(text))
            found["P1"].sort()
        for patch, spans in found.items():
            ranges.setdefault(patch, []).extend(f"{name}:{a}-{b}" if a != b else f"{name}:{a}" for a, b in spans)
        add(f"sutra_app/engine/{name}", name, text.encode("utf-8"), raw,
            sorted({e.patch for e in mine} | ({"P1"} if p1 else set()), key=_pnum))
    unknown = {e.file for e in EDITS} - set(CODE)
    if unknown:
        raise VendorError(f"edits for files that are not vendored: {sorted(unknown)}")
    for name in ROLE_FILES:
        data = src.read(f"agents/j2/{name}")
        add(f"sutra_app/engine/agents/j2/{name}", f"agents/j2/{name}", data, data)
    for folder, vendored, excluded in TREES:      # D161: types are data; every file of the tree, no name listed
        for rel in src.tree(folder):
            if rel not in excluded:
                data = src.read(rel)
                add(f"{vendored}/{rel[len(folder) + 1:]}", rel, data, data)
    patched_index = False
    for rel in src.tree("library"):
        data = src.read(rel)
        if rel == SEED_INDEX:        # P15: the only seed file that is not a byte copy
            try:
                text, lines = scrub_seed_index(data.decode("utf-8"))
            except UnicodeDecodeError as exc:
                raise VendorError(f"{rel} is not UTF-8: {exc}") from None
            ranges.setdefault("P15", []).extend(f"seed/{rel}:{n}" for n in lines)
            add(f"sutra_app/engine/seed/{rel}", rel, text.encode("utf-8"), data, ("P15",))
            patched_index = True
        else:
            add(f"sutra_app/engine/seed/{rel}", rel, data, data)
    if not patched_index:
        raise VendorError(f"the seed has no {SEED_INDEX}: P15 has nothing to patch")
    for name in REF_TOP:
        data = src.read(name)
        add(f"docs/reference/j2/{name}", name, data, data)
    for name in REF_DOCS:
        data = src.read(f"docs/{name}")
        add(f"docs/reference/j2/docs/{name}", f"docs/{name}", data, data)
    for tree in REF_TREES:
        for rel in src.tree(tree):
            data = src.read(rel)
            add(f"docs/reference/j2/{rel}", rel, data, data)
    files[VENDORED_MD] = render_vendored_md(src.commit, rows, ranges).encode("utf-8")
    return files, rows, ranges


def _pnum(patch: str) -> int:
    return int(patch[1:])


def render_vendored_md(commit: str, rows, ranges) -> str:
    tree = f" (tree of `prototypes/j2`: `{BASELINE_TREE}`, J2's main, not tagged)" if commit == BASELINE else ""      # the tree id belongs to the pinned commit only
    out = [
        "# Vendored J2 engine",
        "",
        f"Source: the J2 prototype as it is kept in this repository's own copy `prototypes/j2`, at the sutra commit `{commit}`{tree}, "
        f"extracted with `git archive {commit} prototypes/j2 | tar -x --strip-components=2 -C <empty folder>` (sync 8, D244). That "
        "extraction, given to the script with `--source` and `--commit`, is the only source of every file below, never the working tree. "
        f"History, not a source: the earlier syncs took the J2 prototype at the commits `{PREVIOUS_BASELINES[0]}` and "
        f"`{PREVIOUS_BASELINES[1]}` and `{PREVIOUS_BASELINES[2]}` (sync 4) and `{PREVIOUS_BASELINES[3]}` (sync 5, the tag `cut-off/2026-11-12`) and `{PREVIOUS_BASELINES[4]}` (sync 6) and `{PREVIOUS_BASELINES[5]}` (sync 7); the design documents cite the line numbers (`j2.py:n`) of `{DESIGNED_AGAINST}`, and everything "
        "after `j2.py:8313` has moved. Patches are located by anchor text, never by line.",
        "",
        "Copied into `sutra_app/engine/` with the same module names; every change to a J2 file is one of the numbered patches "
        "below and nothing else (decision D13). Prompts stay byte-identical, except where a patch says it changes a prompt (D249: J2 is "
        "frozen at `cut-off/2026-11-17` and the app is the product, so a recorded patch may change what the engine asks the model; the "
        "prompt goldens are recorded from the engine with its patches applied): P24 changes Priority's reply format, P25 the raise "
        "question's text, and P30 Identity's intake and every builder's reply format and brief. There is no P6 (the design's table skips it) and no "
        "P13 (retired in sync 4, D140: its code is Sutra's own `engine/runlist.py`); P20 is reserved for a late-judge switch (D145, D162, D180); P21 (D245) keeps the host's own run files out of a builder's writes outside its folder; P22 (D246) refuses the workflow without a real run that covers a real run's item, and stops the cycle on the same validator rejection twice in a row; P23 (D247) makes `ended_workable` true only for a clean \"Done:\" end; P24 (D250) makes Priority's move a workflow's id and its envelope; P25 (D251) takes the budget cap only from J2_BUDGET_CAP and keeps every raise the Requester's own. P26 (D421, D422) is dollar mode (`J2_USD_BUDGET`): the engine sums each run's API price.  P27 lists only files, never folders, for a type's file pattern (main `c9d4e662`). P28 (D431) stops the cycle on the same build failure twice in a row, across workflows; P29 (D431) never offers or applies a \"Leave out\" that leaves nothing to build while nothing is built, and makes an audit taken with nothing built never workable; P30 (D433) gives every done-when item a runnable check and a status its builder sets, and ends \"Done:\" only when every item is built and passes; P31 (D434) sends a failed dry run back to the build and takes only RUN <code> or Don't run as the real-run answer; P32 (D435) runs the dry run only inside the sandbox runtime, never with network; P33 (D436) has Audit read an approved real run's output against the brief, so exit 0 alone never passes an item; P34 (D437) removes the Claude CLI's `.claude` folder from a builder's output folder after every tools call and never copies it into `site/`; P35 (D438) makes a real run state what it creates, changes and deletes (`expect`), and sends a dry run that differs from it, or writes into a folder it may only read, back to the build. "
        "Sync 5 (D160 to D163): the pin moved to the tag `cut-off/2026-11-12`; the types are vendored as data (`conditions/` and "
        "`templates/` as whole trees, D161); P1 is a counted rule, P7, P8, P9, P12 and P14 were repaired, P2 gained a third edit, "
        "P17 and P18 are new (D162). "
        "Sync 6 (D176 to D181): the pin moved to J2 main `1adb8ecd` (J2 has not tagged it; the tag name is added when it does); the "
        "seven commits labelled \"needs owner review\" (run templates, auto-reuse) are carried inert behind `J2_RUN_TEMPLATES` and "
        "`J2_AUTO_REUSE`; P1 (15 lines in `j2.py`, one in the new `j2_artifact_lib.py`, 41 in all), P7, P8 and P9 were re-anchored, "
        "P10 covers two more writers of the library index, P19 is new (the reviewer switch). "
        "Sync 7 (D239 to D241): the pin moved to J2 main `dee83d5c` (Disha's remove-restrictions #202 and group C #203: builders "
        "with tools on a general path, a planned real run, the sandbox off by default); the `artifacts/` folder is vendored as a "
        "tree (it gains `real_run.md`); P1 (seven lines in `j2_artifacts.py`), P7 (the call passes `tools` on), P8 (the import "
        "block) and P17 (`create` takes the form) were re-anchored; no patch was dropped. Sutra's `llm` shim reports builder tools "
        "off (D240), so the vendored engine takes J2's section path. "
        "Sync 8 (D244): the pin moved to J2 main `ee659fb5` (Kaivan's reuse fixes #205 and the review of 17 Nov, a workable run saved "
        "as a run template, and the dry-run fix #206: a real run passes its folders as arguments, a build that holds a real folder is "
        "refused, the real folders are read before and after the dry run, the charter lists only built files); every patch applied "
        "unchanged, none was re-anchored or dropped. The new reuse code is carried inert behind J2's library flags; builder tools stay "
        "off (D240). "
        "This file is written by `scripts/vendor_j2.py`; `scripts/py scripts/vendor_j2.py --source <the extraction> --commit "
        f"{commit} --check` re-derives every file below from the J2 source and fails on any difference.",
        "",
        "## Patches",
        "| Id | What changes | Where (vendored file:lines) |",
        "|---|---|---|",
    ]
    for patch in sorted(PATCH_NOTES, key=_pnum):
        where = "; ".join(ranges.get(patch, []))
        out.append(f"| {patch} | {PATCH_NOTES[patch]} | {where} |")
    out += ["", "## Files",
            "J2 sha256 is the file at the commit above; Vendored sha256 is the copy in this repository (equal when the file is "
            "copied unchanged). A vendored file that is not in this table, or whose hash differs, fails "
            "`tests/engine/test_engine_vendor.py`.", "",
            "| Vendored path | J2 path | Patches | J2 sha256 | Vendored sha256 |", "|---|---|---|---|---|"]
    for dest, origin, patches, original, vendored in rows:
        out.append(f"| `{dest}` | `{origin}` | {patches or '-'} | `{original}` | `{vendored}` |")
    out += ["", "Not vendored (engine design 3.2): `templates/README.md`, `tools/`, `fixtures/n6-sudoku-*` and `docs/word-matching-followups.md` (working notes and tools of J2, D161), the older studio (`studio.py`, `server.py`, `ui.html`, `mock_site.py`, "
                "`agents/{product,design,development,team}.md`), the budget-conflict demo (`negotiate*`, `scenarios/`), "
                "`agents/j2/_placeholders/`, the saved runs, the IDE and environment files, the page and its scripts "
                "(`j2_ui.html`, `j2_ui_render.js`, `j2_graph_layout.js`, `vendor/`: the UI package ports them), "
                "`docs/mocks/*.html` and `docs/build-on-run-design.md` of the copy (mocks; a design with no code), "
                "`j2_server.py` (WP E2) and the legacy test scripts (WP E5).", ""]
    return "\n".join(out)


# ---- writing / checking ---------------------------------------------------------------------------------------------
def existing(dest: Path):
    """Every file the script manages in `dest`, relative to it."""
    found = set()
    for rel in MANAGED:
        base = dest / rel
        if base.is_dir():
            found |= {str(p.relative_to(dest)) for p in base.rglob("*") if p.is_file() or p.is_symlink()}
    return found


def compare(files: dict, dest: Path) -> list:
    """Differences between the tree built in memory and the one in `dest`: human-readable lines, empty when equal."""
    problems = []
    for rel in sorted(files):
        path = dest / rel
        if not path.is_file():
            problems.append(f"missing: {rel}")
        elif path.read_bytes() != files[rel]:
            problems.append(f"differs: {rel}")
    for rel in sorted(existing(dest) - set(files)):
        problems.append(f"not in the J2 snapshot: {rel}")
    return problems


def write(files: dict, dest: Path) -> None:
    for rel in sorted(existing(dest) - set(files)):
        (dest / rel).unlink()
    for rel, data in files.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vendor the J2 engine from an extraction of prototypes/j2 into sutra_app/engine/ (WP E1, sync 5).")
    ap.add_argument("--source", default=os.environ.get(J2_ENV),
                    help=f"an extraction of this repository's prototypes/j2 (see the module docstring); default: ${J2_ENV}")
    ap.add_argument("--commit", default=None,
                    help="the sutra commit the extraction was taken from (required: an extraction is a plain folder with no history)")
    ap.add_argument("--dest", default=str(REPO), help="the repository to write into (default: this one)")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if the repository differs from the J2 snapshot")
    args = ap.parse_args(argv)
    if not args.source:
        ap.error(f"--source (an extraction of prototypes/j2, or ${J2_ENV}) is required")
    try:
        src = Source(Path(args.source), args.commit)
        if src.commit != BASELINE:
            print(f"note: vendoring {src.commit}, not the baseline {BASELINE}; check the patch table afterwards", file=sys.stderr)
        files, rows, _ = build(src)
    except VendorError as exc:
        print(f"vendor_j2: {exc}", file=sys.stderr)
        return 2
    dest = Path(args.dest)
    if args.check:
        problems = compare(files, dest)
        for line in problems:
            print(line)
        print(f"vendor_j2 --check: {len(files)} files, {'ok' if not problems else str(len(problems)) + ' problem(s)'}")
        return 1 if problems else 0
    write(files, dest)
    print(f"vendor_j2: {len(files)} files written from J2 {src.commit[:7]} into {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
