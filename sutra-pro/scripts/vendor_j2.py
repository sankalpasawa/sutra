#!/usr/bin/env python3
"""Vendor the J2 prototype's engine into `sutra_app/engine/` (work package E1; engine design 3.1 and 3.4, decision D13).

    scripts/py scripts/vendor_j2.py --source /path/to/extraction --commit 00efb179... [--dest .] [--check]

Since sync 4 (D136) the source is the folder `prototypes/j2` of this repository at the pinned sutra commit, extracted with
`git archive <commit> prototypes/j2 | tar -x --strip-components=2 -C <new, empty folder>` (never the working tree).

What it does, in this order, and nothing else:

  1. reads the J2 files from `--source`, an extraction of `prototypes/j2` at ONE commit (a plain folder, so an edited working
     tree, a `.pyc` or a stray file is never vendored), with `--commit` naming the commit it was taken from;
  2. copies the 16 code modules and applies the numbered patches (P1 to P5, P7 to P12, P14 and P15; no P6, no P13) as exact
     text edits: every edit names its old text and how often it must occur, so a J2 change under an anchor stops the run
     instead of producing a silently different file (P15 is a data patch: see `scrub_seed_index`);
  3. copies the data files byte for byte: role files, conditions, artifact types, generic templates, the seed template
     library (but for P15) and the reference docs;
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
BASELINE = "00efb179e21cb79fae157a0679e819921ac37726"        # sutra commit that last touched prototypes/j2 (sync 4, D136)
BASELINE_TREE = "99b6f3a05de78a609b593d81d7fb06b55c32b961"   # `git rev-parse <BASELINE>:prototypes/j2`
PREVIOUS_BASELINES = ("9200cf6", "33aeeda")                   # commits the earlier syncs took the J2 prototype at: history only, never a source
DESIGNED_AGAINST = "ce2631f"                                  # the design documents' line numbers (`j2.py:n`) are those of this commit: history only
J2_ENV = "SUTRA_J2_CHECKOUT"

CODE = ("j2.py", "j2_agent.py", "j2_agent_models.py", "j2_agent_views.py", "j2_artifact_models.py", "j2_artifacts.py",
        "j2_board.py", "j2_change.py", "j2_check.py", "j2_map.py", "j2_realization.py", "j2_rules.py", "j2_schema.py",
        "j2_send.py", "j2_story.py", "j2_template_lib.py")
ROLE_FILES = ("team.md", "identity.md", "adaptation.md", "priority.md", "coordination.md", "audit.md", "builder.md",
              "confidence-judge.md", "rates.json", "stages.json")          # agents/j2/ without the never-read _placeholders/
CONDITIONS = ("hld.json", "lld.json", "prd.json", "website.json")
GENERIC_TEMPLATES = tuple(f"{a}/generic.json" for a in ("design", "hld", "lld", "prd", "website"))
REF_TOP = ("README.md", "SETUP.md")
REF_DOCS = ("atom-schema.json", "atom-schema.md", "map-schema.md", "realization-schema.json", "realization-axis.md",
            "j2-handoff.md", "j2-prompts.md", "j2-test-plan.md", "agent-views-j2-proposal.md")
REF_TREES = ("docs/superpowers",)
MANAGED = ("sutra_app/engine/agents", "sutra_app/engine/conditions", "sutra_app/engine/artifacts",
           "sutra_app/engine/templates", "sutra_app/engine/seed", "docs/reference/j2")      # stale files in these are removed
VENDORED_MD = "sutra_app/engine/VENDORED.md"


class VendorError(Exception):
    """The source does not look as the patches expect, or a file is missing."""


# ---- the patches --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Edit:
    patch: str          # "P1" .. "P15" (P15 is the data patch below, not an Edit)
    file: str
    old: str
    new: str
    count: int = 1      # how often `old` must occur


P1_NOTE = ("sibling imports become package-relative: `import x` -> `from . import x`, `from x import y` -> `from .x import y`; "
           "`j2_agent_views.py` also loses its `sys.path` insert")

J2_EDITS = (
    # ---- imports (P1) and what the other patches import
    Edit("P8", "j2.py", r'''import shutil
import threading
''', r'''import shutil
import sys
import threading
'''),
    Edit("P1", "j2.py", r'''import j2_artifacts
import j2_artifact_models
import j2_board
import j2_change
import j2_check
import j2_map
import j2_realization
import j2_rules
import j2_schema
import j2_send
import j2_template_lib
import llm
''', r'''from . import j2_artifacts
from . import j2_artifact_models
from . import j2_board
from . import j2_change
from . import j2_check
from . import j2_map
from . import j2_realization
from . import j2_rules
from . import j2_schema
from . import j2_send
from . import j2_template_lib
from . import llm
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
    Edit("P9", "j2.py", r'''        system = system_prompt(fn, reply_format, self.out["builder"])
        if self.calls and DELAY:
            time.sleep(DELAY)
        self.calls += 1
        self.thinking = fn
''', r'''        system = system_prompt(fn, reply_format, self.out["builder"])
        if self._observed():      # P9: empty unless a node-context file names text for this function
            addendum = self._hook("system_addendum", fn)
            system += addendum if isinstance(addendum, str) else ""
        if self.calls and DELAY:
            time.sleep(DELAY)
        self.calls += 1
        self.thinking = fn
'''),
    Edit("P7", "j2.py", r'''        try:
            raw = llm.ask(system, user, mock, max_tokens=max_tokens, effort="low" if json_reply else "high",
                          json_mode=json_reply, images=images, schema=schema)
        finally:
            self.thinking = None
''', r'''        try:
            raw = _ask(self._ask_tag(fn, "agent_turn", self.calls, self.atom or None), system, user, mock,
                       max_tokens=max_tokens, effort="low" if json_reply else "high", json_mode=json_reply, images=images,
                       schema=schema)
        finally:
            self.thinking = None
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
                self._hook("run_error", getattr(e, "code", "internal") if isinstance(e, _ModelError) else "internal", self.error)
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
    Edit("P8", "j2.py", r'''            self.change["phase"] = "closed"
        self.status = "waiting"

    # ------------------------------------------------------------------ Identity
''', r'''            self.change["phase"] = "closed"
        self.status = "waiting"
        self._run_status()      # P8

    # ------------------------------------------------------------------ Identity
'''),
    # ---- P7: the template generator and the reviewer
    Edit("P7", "j2.py", r'''        raw = llm.ask(system, user, mock, max_tokens=8000, effort="low", json_mode=True, schema=schema)
''', r'''        raw = _ask(self._ask_tag("template", "template"), system, user, mock, max_tokens=8000, effort="low", json_mode=True,
                   schema=schema)
'''),
    Edit("P7", "j2.py", r'''        raw = llm.ask(
            "You review one test run of J2, a department''', r'''        raw = _ask(self._ask_tag("reviewer", "review"),
            "You review one test run of J2, a department'''),
    # ---- P14: an output that says `single` is never swapped for the documents a brief names (the project output, D128)
    Edit("P14", "j2.py", r'''        if self.stages or self.goal:
            return
        said = [self.request] + [x["answer"] for x in self.intake]''', r'''        if self.stages or self.goal or self.out.get("single"):      # P14: `single` outputs (project work) keep their output
            return
        said = [self.request] + [x["answer"] for x in self.intake]'''),
)

OTHER_EDITS = (
    # ---- P1 in the other modules
    Edit("P1", "j2_artifact_models.py", "import j2_rules\n", "from . import j2_rules\n"),
    Edit("P1", "j2_artifacts.py", "        import j2_schema\n", "        from . import j2_schema\n"),
    Edit("P1", "j2_artifacts.py", "    import j2_map\n", "    from . import j2_map\n", count=3),      # three lazy imports: the third is in groups()
    # j2_agent_models.py has no sibling import; j2_agent_views.py (D143) puts its folder on sys.path and imports three siblings flat
    Edit("P1", "j2_agent_views.py",
         "HERE = os.path.dirname(os.path.abspath(__file__))\nif HERE not in sys.path:\n    sys.path.insert(0, HERE)\n"
         "import j2_agent_models as G      # noqa: E402\nimport j2_artifact_models as AM      # noqa: E402\n"
         "import j2_template_lib as L      # noqa: E402\n",
         "HERE = os.path.dirname(os.path.abspath(__file__))\nfrom . import j2_agent_models as G\n"
         "from . import j2_artifact_models as AM\nfrom . import j2_template_lib as L\n"),
    Edit("P1", "j2_change.py", "import llm\nimport j2_realization as R\n", "from . import llm\nfrom . import j2_realization as R\n"),
    Edit("P1", "j2_map.py", "import j2_artifacts as A\nimport j2_realization as R\n",
         "from . import j2_artifacts as A\nfrom . import j2_realization as R\n"),
    Edit("P1", "j2_story.py", "import j2_artifacts as A\nfrom j2_map import _jsonl, _read",
         "from . import j2_artifacts as A\nfrom .j2_map import _jsonl, _read"),
    Edit("P1", "j2_realization.py", "import llm\n\nHERE =", "from . import llm\n\nHERE ="),
    Edit("P1", "j2_template_lib.py", "import j2_artifact_models as AM\nimport j2_rules\n",
         "from . import j2_artifact_models as AM\nfrom . import j2_rules\n"),
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
    # ---- P12: Windows (D101), nothing else
    Edit("P12", "j2_template_lib.py", "import keyword\nimport os\nimport re\n", "import keyword\nimport os\nfrom sutra_app import oslayer\nimport re\n"),
    Edit("P12", "j2_template_lib.py", "        f.write(text)\n    os.replace(tmp, path)\n", "        f.write(text)\n    oslayer.replace(tmp, path)\n"),
    Edit("P12", "j2_template_lib.py", '''    return os.path.join("templates", rec["artifact"], slug(rec["section"]), f"{slug(rec['template'])}@v{rec['version']}")\n''',
         '''    return "/".join(("templates", rec["artifact"], slug(rec["section"]), f"{slug(rec['template'])}@v{rec['version']}"))     # P12: a path in a record is POSIX on every system\n'''),
    Edit("P12", "j2_template_lib.py", ''' or ".." in rel.split(os.sep):\n''', ''' or ".." in re.split(r"[\\\\/]", rel):          # P12: either separator, on every system\n'''),
    Edit("P12", "j2_check.py", '''    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text, start_new_session=True)\n''',
         '''    # start_new_session is ignored on Windows. The output is decoded as UTF-8 whatever the console code page is.
    decoding = {"encoding": "utf-8", "errors": "replace"} if text else {}
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text, start_new_session=True, **decoding)\n'''),
    Edit("P12", "j2_check.py", '''    for p in (os.getenv("J2_CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",\n''',
         '''    windows = [os.path.join(root, "Google", "Chrome", "Application", "chrome.exe")
               for root in (os.getenv(name) for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "LOCALAPPDATA")) if root]
    for p in (os.getenv("J2_CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", *windows,\n'''),
)

EDITS = J2_EDITS + OTHER_EDITS

PATCH_NOTES = {
    "P1": P1_NOTE,
    "P2": "role files: `J2_DIR` (j2.py) and `AGENTS` (j2_realization.py) are `J2_AGENTS_DIR` or the package copy `agents/j2/`; conditions, `artifacts/types.json` and `templates/` stay package-relative; `J2_RUNS_DIR`, `J2_MEMORY_FILE`, `J2_PLAYBOOK_FILE` and `J2_LIBRARY_DIR` were already environment-driven",
    "P3": "`J2Run.__init__(*, run_dir=None, run_id=None, hooks=None)`: the host names the run folder and id (the first `reset` takes them; `run_id` without `run_dir` is an error; default id = folder name without `j2-`, as before); `self.hooks` defaults to `NullHooks()`",
    "P4": "`user_says` returns False at once when the run holds its lock (J2 took the lock before it looked at the status and then waited, 1.21 s measured, and started a new turn); new `apply_override(cmd)`: the same non-blocking lock around `_override`, for the host (the server checked the key)",
    "P5": "explicit-path variants, the old constants as defaults: `saved_dir(name, runs_dir=None)`, `list_runs(limit=60, runs_dir=None)`, `saved_snapshot_dir(d, name, since=0)` (called by `saved_snapshot`), `load/save/clear_lessons(path=None)`, `load/save/clear_playbooks(path=None)`",
    "P7": "every `llm.ask` is inside a tagged block: `J2Run.call` (function, step, cycle, stage, call_no, builder atom), the chat summary, the template generator and the reviewer through `_ask(...)`; the planner and judge (`Session.ask`, j2_realization.py) name role and purpose and inherit the turn's function; each hook-observed turn runs inside `llm.tagged(function, step, cycle, stage)`",
    "P8": "hook calls (`NullHooks` by default, nothing is built for it): `post` (`message_posted`, not for ASK_REQUESTER), `_ask_user` (`message_posted(m, questions=)` once `paused` is set), `save` (`record_saved`), `_log_call` (`call_finished`; `calls.jsonl` also gains `provider` and `usd`), the turn dispatch (`turn_started`, `turn_finished` through `_dispatch_turn`), `user_says` and both run ends (`run_status`), the crash path (`run_error`); a hook error goes to stderr unless it is fatal (`fatal = True` or a class named RecordRejected)",
    "P9": "`call` appends `system_addendum(fn)` to the system prompt: empty unless the hooks have a node-context file",
    "P10": "`store` and `mark_used` of the template library run inside an exclusive lock on `<library>/.lock` (`oslayer.try_lock`: `flock`, or `msvcrt.locking` on Windows) (waits `LOCK_WAIT_S` = 30 s, then raises `LibraryBusy(RuntimeError)`, which `_route_template` already turns into the generic template); the originals are kept as `_store` and `_mark_used`",
    "P11": "`J2Run.rehydrate(src_dir)` delegates to `rehydrate.py`",
    "P12": "Windows (D101), nothing else: `j2_check.find_chrome` also looks in the Windows install folders of Chrome, `j2_check._chrome` decodes Chrome's output as UTF-8 with replacement, `j2_template_lib` writes its index with `oslayer.replace` (a rename that waits out a reader) and takes its library lock through `oslayer` (P10), records a template's saved path with `/` on every system (`run_tpl_rel`) and splits it on either separator when it checks for `..` (`run_saved_dir`)",
    "P14": "`J2Run._plan_stages` returns early for an output that says `single` (`if self.stages or self.goal or self.out.get(\"single\"):`): named documents in a brief (\"update the PRD in the repo\") do not swap the project output for a PRD stage chain. No other output has `single`, so every other run, prompt and golden is unchanged. The output itself is registered by `sutra_app/engine/capabilities/` (Sutra's own files, not J2's)",
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
            text, found = apply_edits(raw.decode("utf-8"), mine, name=name)
        except UnicodeDecodeError as exc:
            raise VendorError(f"{name} is not UTF-8: {exc}") from None
        for patch, spans in found.items():
            ranges.setdefault(patch, []).extend(f"{name}:{a}-{b}" if a != b else f"{name}:{a}" for a, b in spans)
        add(f"sutra_app/engine/{name}", name, text.encode("utf-8"), raw, sorted({e.patch for e in mine}, key=_pnum))
    unknown = {e.file for e in EDITS} - set(CODE)
    if unknown:
        raise VendorError(f"edits for files that are not vendored: {sorted(unknown)}")
    for name in ROLE_FILES:
        data = src.read(f"agents/j2/{name}")
        add(f"sutra_app/engine/agents/j2/{name}", f"agents/j2/{name}", data, data)
    for name in CONDITIONS:
        data = src.read(f"conditions/{name}")
        add(f"sutra_app/engine/conditions/{name}", f"conditions/{name}", data, data)
    data = src.read("artifacts/types.json")
    add("sutra_app/engine/artifacts/types.json", "artifacts/types.json", data, data)
    for name in GENERIC_TEMPLATES:
        data = src.read(f"templates/{name}")
        add(f"sutra_app/engine/templates/{name}", f"templates/{name}", data, data)
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
    tree = f" (tree of `prototypes/j2`: `{BASELINE_TREE}`)" if commit == BASELINE else ""      # the tree id belongs to the pinned commit only
    out = [
        "# Vendored J2 engine",
        "",
        f"Source: the J2 prototype as it is kept in this repository's own copy `prototypes/j2`, at the sutra commit `{commit}`{tree}, "
        f"extracted with `git archive {commit} prototypes/j2 | tar -x --strip-components=2 -C <empty folder>` (sync 4, D136). That "
        "extraction, given to the script with `--source` and `--commit`, is the only source of every file below, never the working tree. "
        f"History, not a source: the earlier syncs took the J2 prototype at the commits `{PREVIOUS_BASELINES[0]}` and "
        f"`{PREVIOUS_BASELINES[1]}`; the design documents cite the line numbers (`j2.py:n`) of `{DESIGNED_AGAINST}`, and everything "
        "after `j2.py:8313` has moved. Patches are located by anchor text, never by line.",
        "",
        "Copied into `sutra_app/engine/` with the same module names; every change to a J2 file is one of the numbered patches "
        "below and nothing else (decision D13). Prompts stay byte-identical. There is no P6 (the design's table skips it) and no "
        "P13 (retired in sync 4, D140: its code is Sutra's own `engine/runlist.py`). "
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
    out += ["", "Not vendored (engine design 3.2): the older studio (`studio.py`, `server.py`, `ui.html`, `mock_site.py`, "
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
    ap = argparse.ArgumentParser(description="Vendor the J2 engine from an extraction of prototypes/j2 into sutra_app/engine/ (WP E1, sync 4).")
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
