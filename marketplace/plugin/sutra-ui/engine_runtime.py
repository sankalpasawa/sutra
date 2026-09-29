"""engine_runtime.py -- every unit that runs is an engine: one skeleton in code, steps on rungs inside.

The design is holding/plans/engine-runtime/ (PRD, HLD, LLD). It makes ruled
canon real: no step is fixed as code or as a model (crystallization 5b), and
the five functions are engines too (the five functions, A1).

OFF BY DEFAULT. A department runs here only when its dept.json says
`runtime: 2`; every other department runs on website_dept.py's built path,
unchanged. website_dept.py hands over at six places: the goal, the owner's
words, a stamp, due, run_slot, and the sweep of each tick.

START IS JUST A BUTTON; THE REST IS COORDINATION'S (founder, 2026-09-28).
The skeleton holds no rule of its own. While the department is on, each
tick it asks Coordination one question, "what is next?", and starts what
Coordination names. What is served first, the order of the line, one run at
a time, who is woken by a post, who may post to whom, which gates are asked,
the thread's bounds and the alarm are all Coordination's: its own steps
(coord.*), reading its own table on the department's record
(coordination.json), each decision a row.

THE SKELETON, always code, deciding nothing
    next_due    is the button on? then Coordination's answer (coord.next)
    admit       asks the gates Coordination's table names, in its order; a
                gate that is not on the code rung answers "wait"
    run_engine  the steps of one run, in order; a finished step is not run
                again; the items of a fan-out step run side by side
    run_step    one step on its rung; a miss goes down one rung for that run

THE INSIDE, on a rung
    P   a person: the step files an ask and waits
    C0  the engine's own agent, in one call: goal and inputs in, one closed
        answer out
    C1  the same call, with a checklist learned from earlier runs
    C2  code: a function from the registry, or a table the runtime reads

EVERY STEP HAS A CHECK. A definition with a step that names none is refused
when it is loaded, so nothing a department does rests on a statement alone.

THE BOARD
    Engines never call each other. An engine posts; the post names who it is
    for and wakes only them. A thread is bounded and names the outcome that
    holds when a bound is hit. Acts are FIPA's; thread states are A2A's.
"""
import hashlib
import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import record                      # the platform product: rows, deployed into the department's own folder
import website_dept as W

RUNGS = ("P", "C0", "C1", "C2")
RUNG_NAME = {"P": "Person", "C0": "Improvised call", "C1": "Checklist", "C2": "Code"}
NATURES = ("transform", "check", "decide", "make")
BELOW = {"C2": "C1", "C1": "C0", "C0": "P"}
ABOVE = {"P": "C0", "C0": "C1", "C1": "C2"}
ACTS = ("request", "agree", "refuse", "propose", "accept-proposal", "reject-proposal", "inform", "failure",
        "not-understood", "cancel")
CLOSED = ("completed", "failed", "canceled", "rejected")
FUNCTIONS = ("Identity", "Adaptation", "Priority", "Coordination", "Audit")
WORK = ("Plan", "Write", "Check", "Publish")
OWNER = "Owner"
BOUNDS = {"hops": 4, "seconds": 900, "usd": 0.5}
DEFAULT_OUTCOME = {"request": "failure", "propose": "reject-proposal", "inform": "cancel"}
LADDER = {"runs": 40, "differing": 1, "trial": 20, "misses": 3}
WAITS = (30, 120, 600)                # seconds a soft step waits for the model, in turn; then it asks the owner


class _Mark:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "<%s>" % self.name


NO_RULE, AWAY, INVALID, ASKED = _Mark("no rule"), _Mark("away"), _Mark("invalid"), _Mark("asked")
SKIPPED = "not needed this time"

#: A test may put a callable here: (prompt, step) -> (object or None, usd, how).
MODEL = None
_DEFS = {}
_GATE_SEEN = {}
_SPEND = threading.Lock()


class _Stop(Exception):
    pass


def is_on(ref):
    return (W.dept(ref) or {}).get("runtime") == 2


# ---- definitions ---------------------------------------------------------------------------------------------------
def validate(d):
    """A definition is data, and data can be wrong. Every fault is named; one fault refuses the whole definition."""
    faults = []
    seen = {}
    for name, e in (d.get("engines") or {}).items():
        if e.get("kind") not in ("work", "function"):
            faults.append("%s: kind is neither work nor function" % name)
        if e.get("kind") == "work" and not (e.get("reads") and e.get("writes")):
            faults.append("%s: a work engine names what it reads and what it writes" % name)
        faults += start_faults(name, e, d.get("engines") or {})
        # SHAPE (founder, 2026-09-28): every unit starts with a step by code and ends with a step by code; agents come
        # between. So the input, the output and the least steps of any unit are known before its agent says a word.
        for uname, steps in [("its steps", e.get("steps") or [])] + [(h.get("name") or "a handler", h.get("steps") or []) for h in e.get("on") or []]:
            for which, s in ((("starts", steps[0]), ("ends", steps[-1])) if steps else ()):
                if s.get("prompt") or s.get("born") != "C2" or not s.get("code"):
                    faults.append("%s, %s: a unit %s with a step by code; agents come between" % (name, uname, which))
        groups = [("gate", s) for s in e.get("gates") or []] + [("rule", s) for s in e.get("rules") or []]
        groups += [("step", s) for s in e.get("steps") or []]
        groups += [("step", s) for h in e.get("on") or [] for s in h.get("steps") or []]
        for mode, s in groups:
            sid = s.get("id") or "?"
            where = "%s, %s" % (name, sid)
            if not s.get("id") or not s.get("name"):
                faults.append("%s: a step has an id and a name" % where)
            if seen.get(sid, name) != name:
                faults.append("%s: the id is used by %s too" % (where, seen[sid]))
            seen[sid] = name
            if s.get("nature") not in NATURES:
                faults.append("%s: nature is not one of %s" % (where, ", ".join(NATURES)))
            if s.get("born") not in RUNGS:
                faults.append("%s: born is not a rung" % where)
            if not s.get("check"):
                faults.append("%s: the step names no check" % where)
            elif s["check"] not in CHECK:
                faults.append("%s: no check named %s ships with the app" % (where, s["check"]))
            if s.get("code") and s["code"] not in CODE:
                faults.append("%s: no function named %s ships with the app" % (where, s["code"]))
            if s.get("prompt"):
                if s["prompt"] not in PROMPT:
                    faults.append("%s: no prompt named %s ships with the app" % (where, s["prompt"]))
                if s.get("draft") not in DRAFT:
                    faults.append("%s: a soft step names a plain draft" % where)
                if not s.get("out"):
                    faults.append("%s: a soft step names the shape of its answer" % where)
            if not s.get("code") and not s.get("prompt"):
                faults.append("%s: the step names neither code nor a prompt" % where)
            if mode in ("gate", "rule") and not s.get("code"):
                faults.append("%s: a %s has its rule in code" % (where, mode))
    for src, acts in (d.get("edges") or {}).items():
        for act in acts:
            if act not in ACTS:
                faults.append("edges, %s: %s is not an act" % (src, act))
    faults += table_faults(d.get("coordination"), d.get("engines") or {})
    import artifacts
    faults += artifacts.faults(d)                     # every artifact an engine reads or writes has a template in the Library
    if not d.get("kinds"):
        faults.append("kinds: the definitions name no kind of department")
    import function_templates
    for kind, k in (d.get("kinds") or {}).items():
        for n in k.get("line") or []:
            if ((d.get("engines") or {}).get(n) or {}).get("kind") != "work":
                faults.append("kinds, %s: %s is not a work engine" % (kind, n))
        if not k.get("artifacts") or not k.get("goal") or not k.get("rules"):
            faults.append("kinds, %s: a kind names its artifacts, its goal and its rules" % kind)
        # a kind is a department template (TPL-1): it says which use case it fits and which Library template its five
        # functions run, and that template exists for every function
        if not k.get("use_case"):
            faults.append("kinds, %s: a kind names its use case" % kind)
        ft = k.get("functions_template")
        if not ft or any(not function_templates.get("%s/%s" % (fn, ft)) for fn in function_templates.FUNCTIONS):
            faults.append("kinds, %s: functions_template names a Library template every function has" % kind)
    for name, e in (d.get("engines") or {}).items():
        if e.get("from_template") and not e.get("use_case"):
            faults.append("%s: an engine template names its use case" % name)
    return faults


def start_faults(name, e, engines):
    """Every engine names its start. One that names none, a trigger of no known kind, or a blocker that is no gate, is
    a fault, and one fault refuses the whole definition: this is how every engine comes to start by the same rule."""
    st = e.get("start")
    if not isinstance(st, dict) or not st.get("on"):
        return ["%s: the engine names no start: no trigger makes it run" % name]
    faults = []
    for t in st["on"]:
        kind = (t or {}).get("kind")
        if kind not in ("version", "post", "timer"):
            faults.append("%s, start: %r is not a kind of trigger" % (name, kind))
        elif kind == "version" and not t.get("of"):
            faults.append("%s, start: a version trigger names what it is a version of" % name)
        elif kind == "post" and not e.get("on"):
            faults.append("%s, start: it is triggered by a post and no step of it reads one" % name)
        elif kind == "timer" and not (isinstance(t.get("every_s"), (int, float)) and t["every_s"] > 0):
            faults.append("%s, start: a timer names its period in seconds" % name)
    gates = {g.get("id") for x in engines.values() for g in x.get("gates") or []}
    for gid in st.get("unless") or []:
        if gid not in gates:
            faults.append("%s, start: the blocker %s is no gate of an internal system" % (name, gid))
    return faults


def table_faults(t, engines):
    """Coordination's table is data too: every name in it is an engine that exists, and nothing is served twice."""
    if not isinstance(t, dict):
        return ["coordination: the definitions carry no table for Coordination to be born with"]
    faults = []
    order = t.get("order") or []
    if sorted(order) != sorted(set(order)) or not order or any(k not in ("posts", "line", "functions") for k in order):
        faults.append("coordination, order: it names posts, line and functions, each at most once")
    for key, kind in (("line", "work"), ("functions", "function")):
        names = t.get(key) or []
        if len(names) != len(set(names)):
            faults.append("coordination, %s: a name is there twice" % key)
        for n in names:
            if (engines.get(n) or {}).get("kind") != kind:
                faults.append("coordination, %s: %s is not a %s engine" % (key, n, kind))
    return faults


TEMPLATES_DIR = Path(__file__).parent / "engine-templates"


def engine_templates():
    """The Library's engine templates: one file per engine, each with its id, its name and its use case (TPL-1, founder
    2026-09-29: engines come from templates, matched to the use case). A file that is not a template refuses the load,
    as a bad step does."""
    out = {}
    for p in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("the engine template %s is refused: not JSON (%s)" % (p.name, exc))
        if not isinstance(t, dict) or not t.get("id") or not t.get("name") or not t.get("use_case"):
            raise ValueError("the engine template %s is refused: a template names an id, a name and a use case" % p.name)
        if t["name"] in out:
            raise ValueError("the engine template %s is refused: %s is already a template" % (p.name, t["name"]))
        out[t["name"]] = t
    return out


def defs():
    """The definitions: the file (the functions, the kinds, the edges, Coordination's table) with the Library's engine
    templates assembled in as engines, validated as one."""
    if "d" not in _DEFS:
        d = json.loads((Path(__file__).parent / "engine_defs" / "website.json").read_text(encoding="utf-8"))
        d["engines"] = dict(d.get("engines") or {})
        for name, t in engine_templates().items():
            if name in d["engines"]:
                raise ValueError("the engine template %s is refused: the definitions already hold an engine of that name" % name)
            e = {k: v for k, v in t.items() if k not in ("id", "version")}
            e["from_template"] = t["id"]
            d["engines"][name] = e
        faults = validate(d)
        if faults:
            raise ValueError("the engine definitions are refused: " + "; ".join(faults[:6]))
        _DEFS["d"] = d
    return _DEFS["d"]


def engine_def(name):
    return defs()["engines"].get(name)


def priority_template():
    """The limits a department is born with: Priority's template, in the definitions (founder, 2026-09-28: "some
    default limits which are in the priority templates"). calls and usd a day per engine; work_calls times the calls
    for a work engine, whose steps are a call each."""
    return dict(((engine_def("Priority") or {}).get("template") or {}).get("envelope") or {})


def all_steps(name):
    e = engine_def(name) or {}
    out, seen = [], set()
    for s in (list(e.get("gates") or []) + list(e.get("rules") or []) + list(e.get("steps") or [])
              + [s for h in e.get("on") or [] for s in h["steps"]]):
        if s["id"] not in seen:
            seen.add(s["id"])
            out.append(s)
    return out


def step_def(step_id):
    for name in defs()["engines"]:
        for s in all_steps(name):
            if s["id"] == step_id:
                return name, s
    return None, None


def card(ctx):
    """Each engine has its own agent. This is who it is: the engine's card, and for a function the brief of the
    Library template the department picked for it."""
    e, d, name = ctx["def"], ctx["dept"], ctx["engine"]
    lines = ["You are the agent of %s, one engine of the department \"%s\"." % (name, d.get("name")),
             "What %s does: it %s." % (name, e.get("description") or ""),
             "Its skills: %s." % "; ".join(e.get("skills") or [])]
    # the template this function runs is the pick on the registry, as the Settings tab left it (found 2026-09-29: a
    # later pick reached the screen and never the agent, which read the birth copy on the record)
    try:
        import function_templates
        tid = function_templates.picked(ctx["ref"]).get(name.lower())
    except Exception:  # noqa: BLE001 -- no registry: the birth copy
        tid = (d.get("templates") or {}).get(name.lower())
    if tid:
        try:
            t = function_templates.get(tid) or {}
            if t.get("floor"):
                lines.append("It always: " + " ".join(str(x) for x in t["floor"][:3]))
            if t.get("choices"):
                lines.append("It decides: " + " ".join(str(x) for x in t["choices"][:3]))
        except Exception:  # noqa: BLE001 -- a missing template never stops a step
            pass
    rules = [r for r in d.get("rules") or [] if r.get("line")]
    if rules:
        lines.append("The department's rules, which you follow: " + " ".join("(%s) %s." % (r.get("tag"), str(r["line"]).rstrip("."))
                                                                          for r in rules))
    lines.append("You answer for this engine only, in the exact shape asked, and you state nothing you were not given.")
    return "\n".join(lines) + "\n\n"


# ---- the record's new files ----------------------------------------------------------------------------------------
def _lines(p):
    return record.lines(p)


def _append(ref, name, row):
    """A row onto one of the department's journals, through the core: the runtime files no row by code of its own."""
    return record.append(W.ddir(ref) / name, row, lock=W._lock(ref))


def step_rows(ref):
    return _lines(W.ddir(ref) / "steps.jsonl")


def board(ref):
    return _lines(W.ddir(ref) / "board.jsonl")


def threads(ref):
    return W._read(W.ddir(ref) / "exchanges.json", [])


def ladder(ref):
    return W._read(W.ddir(ref) / "ladder.json", {})


def numbers(ref, engine=None):
    """The ladder's numbers: born from LADDER, the department's own over them, and one engine's own over those (each
    function's Settings tab has its own; founder, 2026-09-28: "each of the five functions has a default settings tab
    which has its own updates")."""
    d = W.dept(ref) or {}
    n = dict(LADDER)
    n.update(d.get("ladder") or {})
    if engine:
        n.update((d.get("ladders") or {}).get(engine) or {})
    return n


def set_numbers(ref, engine, nums, by="the owner"):
    """The owner's own ladder numbers for one engine or function, from its Settings tab; whole numbers, none below zero."""
    d = W.dept(ref)
    if not d:
        raise ValueError("no department here")
    if not engine_def(engine):
        raise ValueError("no such engine")
    own = dict((d.get("ladders") or {}).get(engine) or {})
    for k, v in (nums or {}).items():
        if k not in LADDER:
            raise ValueError("no such number: %s" % k)
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise ValueError("%s must be a whole number" % k)
        if v < 0 or (k in ("runs", "trial") and v < 1):
            raise ValueError("%s is too small" % k)
        own[k] = v
    d.setdefault("ladders", {})[engine] = own
    W.save_dept(ref, d)
    W.system_run(ref, "Identity", "%s set %s's ladder: %s" % (by, engine, ", ".join("%s %d" % kv for kv in sorted(own.items()))))
    return numbers(ref, engine)


# ---- Coordination's table ------------------------------------------------------------------------------------------
def born_table(kind="website", line=None):
    """What Coordination is born with: the order of service, the department's line (the engines on its record; the
    kind's line for one born before the record carried it), and who may post what to whom, from the definitions."""
    d = defs()
    t = json.loads(json.dumps(d["coordination"]))
    t["line"] = list(line or (d.get("kinds") or {}).get(kind, {}).get("line") or t["line"])
    t["edges"] = json.loads(json.dumps(d["edges"]))
    return t


def coordination(ref):
    """Coordination's table for this department. It is Coordination's state, kept on the department's record, and it
    is the only copy that is read: a department made before the table was kept reads what Coordination is born with."""
    t = W._read(W.ddir(ref) / "coordination.json", None) if ref else None
    dept = W.dept(ref) or {}
    kind, line = dept.get("kind") or "website", dept.get("engines")
    if not isinstance(t, dict) or table_faults(t, defs()["engines"]):
        return born_table(kind, line)
    born_edges = born_table(kind, line)["edges"]
    t.setdefault("edges", born_edges)
    if "Root" in born_edges:                         # a department born before Root spoke learns of it: Root carries the owner's words
        t["edges"].setdefault("Root", born_edges["Root"])
    return t


def born(ref):
    """At the department's birth, Coordination writes its table. From then on the order of work is a record."""
    dept = W.dept(ref) or {}
    t = born_table(dept.get("kind") or "website", dept.get("engines"))
    t.update({"since": W.now(), "by": "born"})
    with W._lock(ref):
        W._write(W.ddir(ref) / "coordination.json", t)
    return t


def _sha(obj):
    return "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:24]


def _shape(obj):
    if isinstance(obj, dict):
        return {k: _shape(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return ["list"]
    return type(obj).__name__


# ---- the ladder ----------------------------------------------------------------------------------------------------
def entry(ref, step, engine=None):
    e = ladder(ref).get(step["id"])
    if e:
        return e
    born = (W.dept(ref) or {}).get("created")
    return {"engine": engine or step_def(step["id"])[0], "step": step["id"], "rung": step["born"], "form": None,
            "since": born, "held": False, "pending": None, "trial": None,
            "history": [{"at": born, "from": None, "to": step["born"], "by": "born", "evidence": None}]}


def rung_of(ref, step):
    return (ladder(ref).get(step["id"]) or {}).get("rung") or step["born"]


def _save_entry(ref, e):
    with W._lock(ref):
        L = ladder(ref)
        L[e["step"]] = e
        W._write(W.ddir(ref) / "ladder.json", L)
    return e


def move(ref, step, to, by, evidence=None, form=None):
    """A rung moves: one row in the step's history, with who moved it and on what numbers."""
    e = entry(ref, step)
    e["history"].append({"at": W.now(), "from": e["rung"], "to": to, "by": by, "evidence": evidence})
    e.update({"rung": to, "form": form if to == "C2" else None, "since": W.now(), "since_row": len(step_rows(ref)),
              "trial": None, "pending": None})
    return _save_entry(ref, e)


def hold(ref, step_id, held=True):
    """The owner pins a step's rung: the keeper neither promotes it nor steps it down."""
    _, s = step_def(step_id)
    if not s:
        raise ValueError("no such step")
    e = entry(ref, s)
    e["held"] = bool(held)
    return _save_entry(ref, e)


def interpret_table(table, facts):
    """The code rung's table form: rules read top to bottom; no rule is an answer too."""
    for rule in (table or {}).get("when") or []:
        ok = True
        for c in rule.get("all") or []:
            v = (facts or {}).get(c.get("field"))
            if "is" in c:
                ok = ok and v == c["is"]
            elif "in" in c:
                ok = ok and v in c["in"]
            elif "under" in c:
                ok = ok and isinstance(v, (int, float)) and not isinstance(v, bool) and v < c["under"]
            else:
                ok = False
        if ok:
            return dict(rule.get("then") or {})
    return NO_RULE


def evidence(ref, step_id, window=None, rows=None, since=0):
    """What a step's rows say, since it last moved. A row a step did not need to run is not evidence of anything.
    `since` is a count of rows, not a time: two rows written in one second are still in order."""
    mine = [r for i, r in enumerate(rows if rows is not None else step_rows(ref))
            if i >= int(since or 0) and r.get("step") == step_id and r.get("mode") != "gate" and r.get("by") != SKIPPED]
    judged = [r for r in mine if r.get("status") in ("ok", "failed")][-(window or 2 * numbers(ref, step_def(step_id)[0])["runs"]):]
    rows = [r for r in judged if r.get("status") == "ok" and r.get("mode") != "mark"]
    by = {}
    for r in rows:
        by.setdefault(r.get("in_sig"), []).append(r.get("out_hash"))
    differing = 0
    for outs in by.values():
        differing += len(outs) - max(outs.count(o) for o in set(outs))
    shapes = [r.get("out_shape") for r in rows]
    drift = len(shapes) - max([shapes.count(s) for s in set(shapes)] or [0])
    passed = sum(1 for r in judged if (r.get("check") or {}).get("ok"))
    return {"runs": len(rows), "differing": differing, "shape_drift": drift,
            "pass": round(passed / len(judged), 3) if judged else None,
            "marked": sum(1 for r in judged if r.get("mode") == "mark"),
            "misses": sum(1 for r in rows[-20:] if r.get("miss")),
            "usd": round(sum(float(r.get("usd") or 0) for r in rows) / len(rows), 4) if rows else 0.0}


def learn_table(ref, step):
    """A candidate table for a decide step: what each set of facts was answered with, where the answers agreed."""
    key = step.get("answer")
    groups = {}
    for r in step_rows(ref):
        if r.get("step") == step["id"] and r.get("status") == "ok" and r.get("facts") is not None and r.get("answer") is not None:
            groups.setdefault(json.dumps(r["facts"], sort_keys=True), []).append(r["answer"])
    when = []
    for facts, answers in sorted(groups.items()):
        if len(answers) >= 2 and len(set(answers)) == 1:
            when.append({"all": [{"field": k, "is": v} for k, v in sorted(json.loads(facts).items())], "then": {key: answers[0]}})
    return {"step": step["id"], "when": when, "else": "no rule"}


def learn_checklist(ref, step):
    """A candidate checklist for a soft step: what its passing runs had in common, in words."""
    rows = [r for r in step_rows(ref) if r.get("step") == step["id"] and r.get("status") in ("ok", "failed") and r.get("mode") != "gate"]
    good, bad = [], []
    for r in rows:
        for n in (r.get("check") or {}).get("notes") or []:
            (good if (r.get("check") or {}).get("ok") else bad).append(str(n))
    lines = ["# Checklist: " + step["name"], "", "Learned from %d runs of this step." % len(rows), "", "Every time:"]
    lines += ["- " + n for n in sorted(set(good))[:12]] or ["- answer in the exact shape the step names"]
    if bad:
        lines += ["", "Never:"] + ["- " + n for n in sorted(set(bad))[:12]]
    return "\n".join(lines) + "\n"


def candidate(ref, step, rung):
    """The latest filed candidate for a rung: a checklist's text, or a table."""
    art = ("Table: " if rung == "C2" else "Checklist: ") + step["id"]
    v = W.latest(ref, art)
    if not v:
        return None
    files = W.read_files(ref, art, v["v"])
    if rung == "C2":
        try:
            return json.loads(files.get("table.json", ""))
        except Exception:  # noqa: BLE001
            return None
    return files.get("checklist.md")


# ---- the board -----------------------------------------------------------------------------------------------------
def may_post(src, dst, msg_type, ref=None):
    """Who may post what to whom: Coordination's table, this department's copy. A post with nobody named is refused."""
    allowed = ((coordination(ref)["edges"] if ref else defs()["edges"]).get(src) or {}).get(msg_type) or []
    return bool(dst) and all(d in allowed for d in dst)


def coord_edge(ctx, step, item):
    """Coordination's rule on a post: pass or refuse. `item` is (src, dst, act)."""
    src, dst, act = item
    if may_post(src, dst, act, ctx["ref"]):
        return "admit", "%s may %s to %s" % (src, act, ", ".join(dst))
    return "refuse", "%s may not post %s to %s" % (src, act, ", ".join(dst) or "nobody")


def _save_threads(ref, ths):
    W._write(W.ddir(ref) / "exchanges.json", ths)


def _state_after(th, dst, msg_type):
    if msg_type == "cancel":
        return "canceled"
    if msg_type == "accept-proposal":
        return "completed"
    if msg_type in ("reject-proposal", "refuse"):
        return "rejected"
    if msg_type == "failure":
        return "failed"
    if msg_type == "request" and OWNER in dst:
        return "input-required"
    if msg_type == "inform" and th["protocol"] == "request":
        return "completed"
    return "working"


def post(ref, src, dst, msg_type, payload=None, thread=None, about=None, by=None, protocol=None, bounds=None, default=None):
    """One post on the department's board. It names who it is for, and wakes only them.
    Returns the post, or None when its thread is closed or was closed just now at its bound."""
    dst = [dst] if isinstance(dst, str) else list(dst or [])
    if msg_type not in ACTS:
        raise ValueError("not an act: %r" % (msg_type,))
    if not dst:
        raise ValueError("a post names who it is for")
    answer, why = _ask_rule(ref, "coord.edge", (src, dst, msg_type), key="%s>%s:%s" % (src, ",".join(dst), msg_type))
    if answer != "admit":
        raise ValueError(why)
    with W._lock(ref):
        ths = threads(ref)
        th = next((t for t in ths if t["id"] == thread), None) if thread else None
        fresh = th is None
        if fresh:
            proto = protocol or ("propose" if msg_type == "propose" else "request" if msg_type == "request" else "inform")
            th = {"id": thread or ("x-" + uuid.uuid4().hex[:8]), "opened_by": src, "with": dst,
                  "topic": (payload or {}).get("word") or msg_type, "protocol": proto, "decider": dst[0],
                  "bounds": dict(bounds or (W.dept(ref) or {}).get("bounds") or BOUNDS),
                  "default": default or DEFAULT_OUTCOME.get(proto, "cancel"),
                  "state": "submitted", "hops": 0, "spent": 0.0, "age_s": 0.0, "opened": W.now(), "closed": None, "outcome": None}
            ths.append(th)
        if th["state"] in CLOSED:
            return None
        between = src != OWNER and OWNER not in dst          # the owner's posts always pass
        if between and th["hops"] >= int(th["bounds"].get("hops") or 0):
            th.update({"state": "canceled", "closed": W.now(), "outcome": {"by": "bound", "which": "hops", "holds": th["default"]}})
            _save_threads(ref, ths)
            return None
        if between:
            th["hops"] += 1
        row = {"n": len(board(ref)) + 1, "src": src, "dst": dst, "msg_type": msg_type, "thread": th["id"], "hop": th["hops"],
               "about": about, "payload": payload or {}, "ack_id": None, "by": by, "at": W.now()}
        if not fresh:
            th["state"] = _state_after(th, dst, msg_type)
        elif OWNER in dst and msg_type == "request":
            th["state"] = "input-required"
        elif OWNER in dst and msg_type == "inform":
            th["state"] = "completed"                  # a statement to the person on a thread of its own: nothing waits on it
        if th["state"] in CLOSED:
            th.update({"closed": W.now(), "outcome": {"by": msg_type, "n": row["n"]}})
        _append(ref, "board.jsonl", row)
        _save_threads(ref, ths)
    W.signal()                                         # a post is a trigger: its reader looks now
    return row


def _thread(ref, tid):
    return next((t for t in threads(ref) if t["id"] == tid), None)


def _thread_set(ref, tid, state=None, spent=0.0, outcome=None):
    with W._lock(ref):
        ths = threads(ref)
        th = next((t for t in ths if t["id"] == tid), None)
        if not th:
            return None
        th["spent"] = round(float(th.get("spent") or 0) + float(spent or 0), 4)
        if state and th["state"] not in CLOSED:
            th["state"] = state
            if state in CLOSED:
                th.update({"closed": W.now(), "outcome": outcome or {"by": "the reader's run"}})
        _save_threads(ref, ths)
        return th


def sweep(ref):
    """Each tick of the system clock: Coordination closes what is past its bound and raises what is past its window.
    A department that is off is left alone: its threads freeze, and their clocks do not run."""
    d = W.dept(ref)
    if not d or d.get("stopped"):
        return []
    ctx = _coord_ctx(ref, d)
    closed = _ask_rule(ref, "coord.bounds", key="bounds@%s" % W.now(), ctx=ctx)["closed"]
    _ask_rule(ref, "coord.alarm", key="alarm@%s" % W.now(), ctx=ctx)
    return closed


def request(ref, text, about=None):
    """The owner's words reach the department as a request to Identity, on the board. On a Root they arrive at the front
    door (the word front), with the department they are about when the person said them from inside one (the chip)."""
    text = " ".join(str(text or "").split())
    if not text:
        raise ValueError("say what the website is for")
    d = W.dept(ref)
    if not d:
        raise ValueError("no department at %s" % ref)
    first = W.artifacts_of(d)[0]              # the Brief; on a Root, a Request
    with W._lock(ref):
        reqs = W.requests(ref)
        rq = {"id": "q-" + uuid.uuid4().hex[:8], "text": text, "at": W.now()}
        reqs.append(rq)
        W._write(W.ddir(ref) / "requests.json", reqs)
    front = d.get("kind") == "root"
    ab = None
    if about and str(about).startswith("fn:"):
        # said in one function's own chat (founder, 2026-09-29): the words still reach Identity, the one door, and
        # carry the function they were said to, so that function's chat shows them and what came of them
        fn = str(about)[3:].strip().lower()
        if fn.title() not in FUNCTIONS:
            raise ValueError("no function named %s" % fn)
        ab = {"fn": fn}
    elif about:
        ad = W.dept(about)
        ab = {"dept": about, "name": (ad or {}).get("name")}
    p = post(ref, OWNER, "Identity", "request",
             {"word": "front" if front else "request", "words": text, "objective": text, "output": "the %s's next version" % first,
              "may_read": [first], "boundaries": "inside the department's goal and rules", "request": rq["id"], "about": ab},
             about=ab)
    return rq, p


def on_stamp(ref, ask, approve):
    """The owner's stamp or refusal, posted in the ask's own thread, so Identity applies it as a step."""
    if not ask.get("thread"):
        return None
    return post(ref, OWNER, "Identity", "accept-proposal" if approve else "reject-proposal",
                {"word": ask.get("kind"), "ask": ask["id"]}, thread=ask["thread"])


# ---- what may start now --------------------------------------------------------------------------------------------
def _run_row(engine, system, slot, status, what, **more):
    row = {"id": "r-" + uuid.uuid4().hex[:10], "engine": engine, "system": system, "slot": slot, "status": status,
           "started": W.now(), "ended": W.now() if status != "running" else None, "what": what, "wrote": None, "chain": None,
           "spend": {"calls": 0, "usd": 0.0}, "retries": 0, "runtime": 2}
    row.update(more)
    return row


def _held_back(ref, slot, rs, peek=False):
    """Why a slot that is due may not start yet, or None. "skip" means it was let rest, and a row says so (a peek writes
    neither the row nor the ask)."""
    mine = [r for r in rs if r.get("slot") == slot]
    if not mine:
        return None
    last = mine[-1]
    if last.get("status") == "waiting":
        waits = [r for r in mine if r.get("status") == "waiting"]
        away = next((a for a in W.asks(ref) if a.get("kind") == "model" and a.get("slot") == slot), None)
        if away and away["status"] == "pending":
            return "waits for the owner: the model is away"
        if away and away["status"] == "refused":
            if not peek:
                W._put_run(ref, _run_row(last["engine"], bool(last.get("system")), slot, "skipped", "the owner let it rest: the model is away"))
            return "skip"
        if len(waits) >= len(WAITS) and not away:
            if not peek:
                W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "model", "engine": last["engine"], "slot": slot,
                                 "text": "The model is away: %s cannot go on. Try again?" % last["engine"], "status": "pending",
                                 "created": W.now(), "escalated": True})
            return "waits for the owner: the model is away"
        if not away and time.time() < float(last.get("retry_at") or 0):
            return "waits for the model"
    if last.get("status") == "asked":
        a = next((a for a in W.asks(ref) if a["id"] == last.get("ask")), None)
        if a and a["status"] == "pending":
            return "waits for the owner"
    return None


def next_due(ref, peek=False):
    """(engine, input, slot), or (None, None, why): what starts now in this department.

    Founder, 2026-09-28: "start is just a button"; every engine "needs a trigger to start", inside or outside, and
    starts "unless it has a blocker"; once started each has "their own internal agency". So nothing here tells an
    engine to run. The skeleton reads whether the button is on, asks every engine whether it is ready by its own
    start (`ready`), and, because a department runs one thing at a time, asks Coordination who goes first.

    peek: a panel read asking the same question. It writes no row and no ask, and never calls the model: Coordination's
    tie is left to the table's order (found live 2026-09-28: the panel stood still for 25 s at a publish, waiting on
    the tie's model call inside a read)."""
    d = W.dept(ref)
    if not d:
        return None, None, "no department"
    if d.get("stopped"):
        return None, None, "stopped"
    ctx = _coord_ctx(ref, d)
    ctx["peek"] = bool(peek)
    name, inp, slot = _run_rule(ctx, "coord.pick")
    if name and not peek:
        _, s = step_def("coord.pick")
        _gate_row(ref, slot, "Coordination", s, rung_of(ref, s), name, "ready by its own start; first by Coordination's table")
    return name, inp, slot


# ---- activation: how every engine starts ---------------------------------------------------------------------------
# One rule for all nine, the five internal systems and the four work engines alike. An engine's definition names its
# start: `on`, the triggers that make it want to run, and `unless`, the blockers that hold it. `ready` is the one piece
# of code that reads a start. No engine has a start of its own in code, so none can differ.
def _on_version(ctx, name, e, trig):
    """Outside trigger: a version of what it reads that it has not run on yet."""
    v = W.latest(ctx["ref"], trig["of"], passed=bool(trig.get("checked")))
    if v:
        slot = W._slot_id(name, trig["of"], v["v"])
        if slot not in ctx["done"]:
            yield v, slot


def _on_post(ctx, name, e, trig):
    """Outside trigger: a post on the board that names this engine, oldest first."""
    for p in board(ctx["ref"]):
        if name not in p["dst"]:
            continue
        slot = "%s@board.n%d" % (name, p["n"])
        if slot in ctx["done"]:
            continue
        if _handler(e, p) is None:
            if not ctx.get("peek"):
                W._put_run(ctx["ref"], _run_row(name, True, slot, "skipped", "no step of %s reads a post of that kind" % name))
            ctx["done"].add(slot)
            continue
        yield {"post": p, "v": p["n"]}, slot


def _on_timer(ctx, name, e, trig):
    """Inside trigger: a time. The system clock is a service; the engine asks it for one start in every period."""
    n = int(ctx.get("now", time.time()) // max(1.0, float(trig["every_s"])))
    slot = "%s@timer.%d" % (name, n)
    if slot not in ctx["done"]:
        yield {"timer": n, "v": n}, slot


TRIGGER = {"version": _on_version, "post": _on_post, "timer": _on_timer}


def ready(ctx, name, kinds=None):
    """The start mechanism, the same for every engine. Returns
         (input, slot, None)  a trigger of its own is live and nothing holds it: it may start
         (None, None, why)    a trigger is live and something holds it
         None                 no trigger of its own is live"""
    e = engine_def(name)
    why = None
    for trig in e["start"]["on"]:
        if kinds and trig["kind"] not in kinds:
            continue
        for inp, slot in TRIGGER[trig["kind"]](ctx, name, e, trig):
            held = _held_back(ctx["ref"], slot, ctx["rs"], ctx.get("peek", False))
            if held == "skip":
                continue
            if held:
                why = why or held
                continue
            answer, reason = blocked(ctx, name, e, inp, slot)
            if answer == "admit":
                return inp, slot, None
            if answer == "wait":
                why = why or reason
    return (None, None, why) if why else None


def blocked(ctx, name, e, inp, slot):
    """The engine's own blockers, in the order its start names them. Each is a gate: a step of an internal system, and
    each answer is a row. The rule in code is the floor: a gate that has gone soft can hold a start, never let one
    through."""
    ref = ctx["ref"]
    gctx = {"ref": ref, "dept": ctx["dept"], "engine": name, "def": e, "slot": slot, "inp": inp, "post": None, "bag": {}, "how": {}}
    for gid in e["start"]["unless"]:
        fn, g = step_def(gid)
        rung = rung_of(ref, g)
        answer, why = CODE[g["code"]](gctx, g, None)
        if rung != "C2" and answer == "admit":
            key = slot + "|" + g["id"]
            v = _verdicts(ref).get(key)
            if v is None and not ctx.get("peek"):
                with W._lock(ref):
                    vs = _verdicts(ref)
                    vs[key] = {"answer": None, "asked": W.now()}
                    W._write(W.ddir(ref) / "verdicts.json", vs)
                _ask_rule(ref, "coord.verdict", (fn, g, name, slot, e.get("reads"), inp["v"]), key=key, ctx=ctx)
            if v is None or v.get("answer") is None:
                return "wait", "%s is judging" % fn
            answer, why = v["answer"], v.get("why")
        if not ctx.get("peek"):
            _gate_row(ref, slot, fn, g, rung, answer, why)
        if answer != "admit":
            return answer, why
    return "admit", None


def admit(ref, d, name, inp, slot):
    """May this engine start on this input? Its own blockers say."""
    return blocked(_coord_ctx(ref, d), name, engine_def(name), inp, slot)


# ---- what engines share: Coordination's rules ----------------------------------------------------------------------
# Each is a step of Coordination (engine_defs/website.json, "rules"), on the code rung, with a check; it reads
# Coordination's table on the department's record; what it decides is a row. Coordination tells no engine to start.
def _coord_ctx(ref, d=None):
    rs = W.runs(ref)
    return {"ref": ref, "dept": d or W.dept(ref), "engine": "Coordination", "def": engine_def("Coordination"), "slot": None,
            "inp": None, "post": None, "bag": {}, "how": {}, "table": coordination(ref), "rs": rs,
            "done": {r["slot"] for r in rs if r.get("slot") and r.get("status") in ("ok", "failed", "skipped")}}


def _run_rule(ctx, sid, item=None):
    _, s = step_def(sid)
    return CODE[s["code"]](ctx, s, item)


def _ask_rule(ref, sid, item=None, key=None, ctx=None):
    """Ask one of Coordination's rules and write its decision down, once for each thing decided."""
    ctx = ctx or _coord_ctx(ref)
    _, s = step_def(sid)
    got = CODE[s["code"]](ctx, s, item)
    out = got if isinstance(got, dict) else {"answer": got[0], "why": got[1]}
    if out.get("answer") or out.get("said"):
        _gate_row(ref, key or sid, "Coordination", s, rung_of(ref, s), out.get("answer") or out.get("said"), out.get("why"), out=out)
    return out if isinstance(got, dict) else (out["answer"], out["why"])


def coord_busy(ctx, step, item):
    """One run at a time in a department."""
    if any(r.get("status") == "running" for r in ctx["rs"]):
        return "wait", "running"
    return "admit", None


def coord_pick(ctx, step, item):
    """When several engines are ready and one may run, who goes first: (engine, input, slot), or (None, None, why).
    Coordination's table says what is served first (posts, the line, internal systems woken by a version) and the
    order inside each. The line is kept in order: while an engine of the line is held, the ones after it wait."""
    t = ctx["table"]
    busy, why = _run_rule(ctx, "coord.busy")
    if busy != "admit":
        return None, None, why
    why, posts = None, len(board(ctx["ref"]))

    def first_post():
        best = None
        for f in t["functions"]:
            got = ready(ctx, f, ("post",))
            if got and got[1] and (best is None or got[0]["post"]["n"] < best[1]["post"]["n"]):
                best = (f, got[0], got[1])
        return best

    for kind in t["order"]:
        got = None
        if kind == "posts":
            got = first_post()
        elif kind == "line":
            for name in t["line"]:
                r = ready(ctx, name, ("version", "timer"))
                if r is None:
                    continue
                if r[1]:
                    got = (name, r[0], r[1])
                else:
                    why = why or r[2]
                break
            if not got and "posts" in t["order"] and len(board(ctx["ref"])) > posts:
                got = first_post()                   # a blocker asked its internal system for a verdict just now
        else:
            ready_now = []
            for f in t["functions"]:
                r = ready(ctx, f, ("version", "timer"))
                if r and r[1]:
                    ready_now.append((f, r))
            if len(ready_now) > 1 and not ctx.get("peek"):
                # several functions woken at once: Coordination's own unit says who goes first (founder, 2026-09-28:
                # "coordination should have an agent as well"); the table's order stands when it says nothing, and
                # a peek never asks it
                pick = _tie(ctx, [f for f, _ in ready_now])
                if pick:
                    ready_now.sort(key=lambda fr: 0 if fr[0] == pick else 1)
            if ready_now:
                f, r = ready_now[0]
                got = (f, r[0], r[1])
        if got:
            return got
    return None, None, why or "nothing due"


def coord_verdict(ctx, step, item):
    """A gate has gone soft: Coordination asks the gate's own internal system for its verdict, on the board.
    `item` is (internal system, gate, engine, slot, what the engine reads, the version)."""
    fn, g, name, slot, reads, v = item
    post(ctx["ref"], "Coordination", fn, "request",
         {"word": "verdict", "gate": g["id"], "engine": name, "slot": slot, "objective": "say whether this may start",
          "output": "admit, wait or refuse", "may_read": [reads], "boundaries": "the department's rules"},
         about={"art": reads, "v": v})
    return {"said": "asked %s whether %s may start" % (fn, name)}


def coord_bounds(ctx, step, item):
    """A thread past its time or its spend is closed, and the outcome it named holds."""
    ref, closed = ctx["ref"], []
    with W._lock(ref):
        ths = threads(ref)
        for th in ths:
            if th["state"] in CLOSED or th["state"] == "input-required":
                continue
            th["age_s"] = round(float(th.get("age_s") or 0) + W.TICK_S, 1)
            which = None
            if th["age_s"] > float(th["bounds"].get("seconds") or 1e12):
                which = "seconds"
            elif float(th.get("spent") or 0) > float(th["bounds"].get("usd") or 1e12):
                which = "usd"
            if which:
                th.update({"state": "canceled", "closed": W.now(), "outcome": {"by": "bound", "which": which, "holds": th["default"]}})
                closed.append(th["id"])
        if ths:
            _save_threads(ref, ths)
    for tid in closed:
        W.system_run(ref, "Coordination", "closed a thread at its bound; what holds: " + str((_thread(ref, tid) or {}).get("default")))
        # the owner's own request, or one Root handed on, that nobody answered in time: Identity is told, and says it
        # back to the person (ER-9; found live 2026-09-28 when a stale clock let a front post die unseen)
        first = next((q for q in board(ref) if q["thread"] == tid), None)
        if first and first["src"] in (OWNER, "Root") and first["msg_type"] == "request":
            fpl = first.get("payload") or {}
            post(ref, "Coordination", "Identity", "inform",
                 {"word": "lost", "for": tid, "from_src": first["src"], "words": str(fpl.get("words") or fpl.get("objective") or ""),
                  "about": fpl.get("about") if isinstance(fpl.get("about"), dict) else None})
    return {"said": "closed a thread at its bound" if closed else "", "closed": closed}


def coord_alarm(ctx, step, item):
    """A run past its window: Coordination tells Identity, and the owner is asked."""
    ref, d, raised = ctx["ref"], ctx["dept"], []
    for r in ctx["rs"]:
        if r.get("status") == "running" and not r.get("alarmed"):
            limit = 60 * int((d.get("windows") or {}).get(r["engine"]) or 30)
            if time.time() - W._ts(r.get("started", "")) > limit:
                r["alarmed"] = True
                W._put_run(ref, r)
                post(ref, "Coordination", "Identity", "inform",
                     {"word": "alarm", "engine": r["engine"], "run": r["id"], "what": "%s has run past its window" % r["engine"]})
                if not any(a.get("kind") == "alarm" and a.get("run") == r["id"] for a in W.asks(ref)):
                    W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "alarm", "engine": r["engine"], "slot": r.get("slot"),
                                     "run": r["id"], "text": "%s has run past its window" % r["engine"], "status": "pending",
                                     "created": W.now(), "escalated": True})
                raised.append(r["id"])
    return {"said": "raised an alarm: a run is past its window" if raised else "", "raised": raised}


def _verdicts(ref):
    return W._read(W.ddir(ref) / "verdicts.json", {})


def _gate_row(ref, slot, fn, g, rung, answer, why, out=None):
    """A decision made on the way to a start, as a row: a blocker's answer, or one of Coordination's rules. Written
    once for each thing decided, however many times it is asked."""
    key0 = str(W.ddir(ref))
    seen = _GATE_SEEN.get(key0)
    if seen is None:
        seen = {(r.get("slot"), r.get("step"), r.get("answer")) for r in step_rows(ref) if r.get("mode") == "gate"}
        _GATE_SEEN[key0] = seen
    key = (slot, g["id"], answer)
    if key in seen:
        return
    seen.add(key)
    check = CHECK[g["check"]](None, g, None, out or {"answer": answer, "why": why})
    _append(ref, "steps.jsonl", {"id": "s-" + uuid.uuid4().hex[:10], "run": None, "engine": fn, "step": g["id"], "item": None,
                                 "mode": "gate", "slot": slot, "asked_rung": rung, "rung": rung, "miss": False, "by": "code",
                                 "in_sig": _sha({"slot": slot}), "out_hash": _sha(answer), "out_shape": "str", "answer": answer,
                                 "check": check, "usd": 0.0, "calls": 0, "ms": 0, "status": "ok" if check.get("ok") else "failed",
                                 "trial": None, "def_version": defs()["def_version"], "started": W.now(), "ended": W.now()})


# ---- a run, step by step -------------------------------------------------------------------------------------------
def _handler(e, p):
    for h in (e or {}).get("on") or []:
        w = h["when"]
        if w.get("msg_type") == p["msg_type"] and ("word" not in w or w["word"] == (p.get("payload") or {}).get("word")):
            return h
    return None


def _out_path(ref, slot, step_id, item):
    safe = re.sub(r"[^A-Za-z0-9_.@-]+", "-", "%s--%s%s" % (slot, step_id, ("--" + str(item)) if item is not None else ""))
    return W.ddir(ref) / "steps" / (safe + ".json")


def _finished(ref, slot, step, item, rows):
    """The checkpoint: a step of this slot that already has a finished row is not run again."""
    if step.get("files"):
        return None                                    # the filing step is code and cheap; it always runs
    p = _out_path(ref, slot, step["id"], item)
    if not p.is_file():
        return None
    if not any(r.get("slot") == slot and r.get("step") == step["id"] and r.get("item") == item and r.get("status") == "ok"
               and r.get("mode") != "gate" for r in rows):
        return None
    got = W._read(p, None)
    return got if isinstance(got, dict) else None


def _at(bag, path):
    sid, _, key = path.rpartition(".")
    return (bag.get(sid) or {}).get(key)


def _cond(bag, expr):
    path, eq, want = expr.partition("=")
    got = _at(bag, path)
    return (str(got) == want) if eq else bool(got)


def _items(ctx, step):
    return list(_at(ctx["bag"], step["each"]) or []) if step.get("each") else [None]


def run_engine(ref, name, inp, slot):
    d = W.dept(ref)
    e = engine_def(name)
    p = inp.get("post") if isinstance(inp, dict) else None
    handler = _handler(e, p) if p else None
    steps = handler["steps"] if handler else list(e.get("steps") or [])
    prior = [r for r in W.runs(ref) if r.get("slot") == slot and r.get("status") in ("interrupted", "waiting", "asked")]
    system = e["kind"] == "function"
    what = handler["name"] if handler else "reading %s" % e.get("reads")
    row = W._put_run(ref, _run_row(name, system, slot, "running", what,
                                   chain=None if system else W._chain_of(ref, e["reads"], inp["v"]),
                                   retries=len([r for r in prior if r["status"] == "interrupted"])))
    if p:
        _thread_set(ref, p["thread"], state="working")
    ctx = {"ref": ref, "dept": d, "engine": name, "def": e, "slot": slot, "inp": inp, "post": p, "run": row["id"], "bag": {}, "how": {},
           "spend": {"calls": 0, "usd": 0.0}}
    status, note, extra = "ok", None, {}
    before = step_rows(ref)
    try:
        for s in steps:
            items = _items(ctx, s)
            kept = {i: _finished(ref, slot, s, it, before) for i, it in enumerate(items)}
            todo = [i for i in kept if kept[i] is None]
            if any(v is not None for v in kept.values()):
                ctx["how"].setdefault(s["id"], "kept from before the app closed")

            import threading
            counted, guard = [0], threading.Lock()

            def one(i, s=s, items=items):
                got1 = run_step(ctx, s, items[i])
                if s.get("each") and len(items) > 1:
                    # how far along: the run row says "page 3 of 8", and the chat's working line reads it (found live
                    # 2026-09-28: one line for three minutes, and nothing said how far Write was)
                    with guard:
                        counted[0] += 1
                        n_done = counted[0]
                    try:
                        W._put_run(ref, dict(row, what="%s %d of %d" % ("page" if "page" in s["name"].lower() else "item", n_done, len(items))))
                    except Exception:  # noqa: BLE001 -- the count never fails the step
                        pass
                return i, got1
            width = max(1, min(int(s.get("side_by_side") or 1), len(todo) or 1))
            if width > 1:
                with ThreadPoolExecutor(max_workers=width, thread_name_prefix="step") as pool:
                    got = list(pool.map(one, todo))
            else:
                got = [one(i) for i in todo]
            bad = None
            for i, (r, out) in got:
                kept[i] = out
                if r["status"] != "ok" and bad is None:
                    bad = r
            if bad is not None:
                status, note = bad["status"], bad.get("why")
                extra = {k: bad[k] for k in ("ask",) if bad.get(k)}
                raise _Stop()
            outs = [kept[i] for i in range(len(items))]
            ctx["bag"][s["id"]] = outs if s.get("each") else outs[0]
    except _Stop:
        pass
    except Exception as exc:  # noqa: BLE001 -- a failed run is a row, never a crash of the motor
        status, note = "failed", "failed: %s" % exc
    row.update({"ended": W.now(), "spend": {"calls": ctx["spend"]["calls"], "usd": round(ctx["spend"]["usd"], 4)}})
    if p:
        _thread_set(ref, p["thread"], spent=ctx["spend"]["usd"])
    if status == "ok":
        filed = next((ctx["bag"][s["id"]] for s in reversed(steps) if s.get("files") and s["id"] in ctx["bag"]), None)
        if not system and filed:
            out = W.add_version(ref, e["writes"], filed["files"], [{"art": e["reads"], "v": inp["v"]}], row["id"], filed["check"])
            ok = bool(filed["check"].get("ok"))
            row.update({"status": "ok" if ok else "failed", "wrote": {"art": e["writes"], "v": out["v"]},
                        "what": "%s from %s, check %s" % (e["writes"], e["reads"], "passed" if ok else "failed")})
            # the last artifact of the kind went out: the person is told in the chat, with the way to it (found live
            # 2026-09-28: after the publish stamp the chat said nothing)
            if ok and e["writes"] == W.artifacts_of(ctx["dept"])[-1] and ctx["dept"].get("kind") != "root":   # Root's last artifact is a spawn, said by Setup
                try:
                    import artifacts
                    host = (ctx["dept"].get("host") or "").strip()
                    site = (artifacts.get(e["writes"]) or {}).get("kind") == "site"      # a Result is filed; a site goes live
                    _tell(ref, ctx["dept"], {"src": "Root" if ctx["dept"].get("root") else OWNER}, "inform",
                          {"word": "live" if site else "filed",
                           "done": "%s v%d is %s%s." % (e["writes"], out["v"], "live" if site else "filed",
                                                        (" at " + host) if site and host and host != W.HOST_DEFAULT else ""),
                           "link": e["writes"], "v": out["v"]})
                except Exception:  # noqa: BLE001 -- telling never fails the version that went out
                    pass
            if not ok and filed["check"].get("broken"):
                _send_back(ref, ctx["dept"], e["writes"], out["v"], filed["check"]["broken"])
        else:
            said = next((ctx["bag"][s["id"]].get("said") for s in reversed(steps)
                         if isinstance(ctx["bag"].get(s["id"]), dict) and ctx["bag"][s["id"]].get("said")), None)
            row.update({"status": "ok", "what": said or what})
        if p:
            th = _thread(ref, p["thread"])
            if th and th["protocol"] == "inform" and th["state"] not in CLOSED:
                _thread_set(ref, p["thread"], state="completed")
    elif status == "waiting":
        n = len([r for r in prior if r["status"] == "waiting"])
        row.update({"status": "waiting", "retry_at": time.time() + WAITS[min(n, len(WAITS) - 1)], "what": note or "waits for the model"})
    elif status == "asked":
        row.update({"status": "asked", "what": note or "waits for the owner"})
        row.update(extra)
    else:
        row.update({"status": "failed", "what": note or "failed"})
        if p:
            _thread_set(ref, p["thread"], state="failed", outcome={"by": "a failed step"})
            # the owner's own request, or one Root handed on, that this run could not carry: the person is told, in
            # the chat, and asked to say it again (found live 2026-09-28: a failed handling was silence)
            if p.get("src") in (OWNER, "Root") and p.get("msg_type") == "request" and ctx["engine"] == "Identity":
                try:
                    pl = p.get("payload") or {}
                    ab = pl.get("about") if isinstance(pl.get("about"), dict) else None
                    _tell(ref, ctx["dept"], p, "inform",
                          {"word": "lost", "for": p["thread"], "why": note or "failed",
                           "done": "I could not act on this: %s. Say it again, or say it differently." % (note or "a step failed")}, about=ab)
                except Exception:  # noqa: BLE001 -- saying it back never fails the row that says why
                    pass
    return W._put_run(ref, row)


def _facts(ctx, step):
    if not step.get("facts"):
        return None
    for v in reversed(list(ctx["bag"].values())):
        if isinstance(v, dict) and isinstance(v.get("facts"), dict):
            return {k: v["facts"].get(k) for k in step["facts"]}
    return None


def _spend(ctx, usd, calls):
    with _SPEND:
        ctx["spend"]["usd"] += float(usd or 0)
        ctx["spend"]["calls"] += int(calls or 0)


def run_step(ctx, step, item):
    """One step, on the rung its record has earned. Returns (row, output)."""
    ref = ctx["ref"]
    asked = rung = rung_of(ref, step)
    t0, started = time.time(), W.now()
    usd, calls, how, out = 0.0, 0, None, None
    stamped = _stamped(ctx, step, item)
    if step.get("only_if") and not _cond(ctx["bag"], step["only_if"]):
        out, how = DRAFT[step["draft"]](ctx, step, item), SKIPPED
    elif stamped is not None:
        out, how, rung = stamped, "stamped by the owner", "P"          # a person answered; the person's answer stands
    else:
        while True:
            out, cost, how, n = RESOLVE[rung](ctx, step, item)
            usd += cost
            calls += n
            if out is AWAY or out is ASKED:
                break
            if out is NO_RULE or out is INVALID:
                rung = (step.get("below") or BELOW).get(rung)
                if rung is None:
                    out, how = INVALID, "no rung below"
                    break
                continue
            break
    _spend(ctx, usd, calls)
    facts = _facts(ctx, step)
    row = {"id": "s-" + uuid.uuid4().hex[:10], "run": ctx["run"], "engine": ctx["engine"], "step": step["id"], "item": item,
           "mode": "slot", "slot": ctx["slot"], "asked_rung": asked, "rung": rung, "miss": rung != asked, "by": how,
           "agent": ctx["engine"] if how in ("model", "checklist") else None,
           "applied": [r["id"] for r in ctx["dept"].get("rules") or [] if r.get("id")] if how in ("model", "checklist") else [],
           "read": [{"post": ctx["post"]["n"]}] if ctx.get("post") else [{"art": ctx["def"].get("reads"), "v": ctx["inp"]["v"]}],
           "facts": facts, "in_sig": _sha(facts if facts is not None else {"step": step["id"], "item": item, "in": ctx["inp"].get("v")}),
           "usd": round(usd, 4), "calls": calls, "def_version": defs()["def_version"], "started": started}

    def end(**more):
        row.update(more)
        row.update({"ended": W.now(), "ms": int((time.time() - t0) * 1000)})
        return _append(ref, "steps.jsonl", row)
    if out is AWAY:
        return end(status="waiting", why="waits for the model"), None
    if out is ASKED:
        return end(status="asked", why="waits for the owner", ask=how), None
    if out is INVALID or not isinstance(out, dict):
        return end(status="failed", why="%s: no answer that fits, on any rung" % step["name"]), None
    with _SPEND:
        ctx["how"][step["id"]] = how
    if how == SKIPPED:
        # a step not needed this time ran its draft only to fill the bag; its check is not a judgement of anything
        # (found live 2026-09-28: a task's long words made "Restate it as a rule" fail its one-line check on a step
        # that was skipped, and the whole request failed unseen)
        check, trial, tcost, tcalls = {"ok": True, "notes": [SKIPPED]}, None, 0.0, 0
    else:
        check = CHECK[step["check"]](ctx, step, item, out)
        trial, tcost, tcalls = _trial(ctx, step, item, out, check, facts)
    _spend(ctx, tcost, tcalls)
    answer = out.get(step["answer"]) if step.get("answer") else None
    hashed = answer if answer is not None else {k: v for k, v in out.items() if k != "files"}
    if not check.get("ok"):
        row["why"] = "%s: %s" % (step["name"], "; ".join(str(n) for n in check.get("notes") or []) or "its check failed")
    elif not step.get("files"):
        W._write(_out_path(ref, ctx["slot"], step["id"], item), out)
    return end(status="ok" if check.get("ok") else "failed", answer=answer, out_hash=_sha(hashed), out_shape=_sha(_shape(hashed)),
               check=check, trial=trial, usd=round(usd + tcost, 4), calls=calls + tcalls), out


# ---- the four resolvers --------------------------------------------------------------------------------------------
def call_model(prompt, step):
    if MODEL is not None:
        return MODEL(prompt, step)
    if os.environ.get("SUTRA_WEBSITE_OFFLINE") == "1":
        return None, 0.0, "offline"
    return W.model_json(prompt, timeout=int(step.get("timeout_s") or W.MODEL_TIMEOUT_S))


def _fits(out, step):
    if not isinstance(out, dict):
        return "the answer is not an object"
    kinds = {"str": str, "list": list, "dict": dict, "bool": bool}
    for k, t in (step.get("out") or {}).items():
        if k not in out:
            return "the answer has no %s" % k
        if isinstance(t, list):
            if out[k] not in t:
                return "%s is not one of %s" % (k, ", ".join(str(x) for x in t))
        elif t in kinds and not isinstance(out[k], kinds[t]):
            return "%s is not a %s" % (k, t)
    return None


def _soft(ctx, step, item, checklist=None):
    """The engine's own agent, in one call. One more call if the answer does not fit; then the rung below."""
    if not step.get("prompt"):
        return NO_RULE, 0.0, "no prompt", 0
    prompt = card(ctx) + PROMPT[step["prompt"]](ctx, step, item)
    if checklist:
        prompt += "\n\nFOLLOW THIS CHECKLIST, learned from this step's earlier runs:\n" + checklist
    usd, calls, fault = 0.0, 0, None
    for _ in (1, 2):
        obj, cost, how = call_model(prompt + ("\n\nYour last answer was not usable: %s. Answer again, in the exact shape asked." % fault
                                              if fault else ""), step)
        usd += float(cost or 0)
        if how == "offline":
            return DRAFT[step["draft"]](ctx, step, item), 0.0, "offline draft", 0
        calls += 1
        if obj is None and (how == "away" or "call failed" in str(how) or "no JSON (exit" in str(how)):
            return AWAY, usd, str(how), calls
        fault = "it held no JSON object" if obj is None else _fits(obj, step)
        if not fault:
            return obj, usd, "checklist" if checklist else "model", calls
    return INVALID, usd, fault, calls


def _stamped(ctx, step, item):
    """What a person already answered for this step of this slot, or None."""
    key = "%s|%s|%s" % (ctx["slot"], step["id"], item)
    a = next((a for a in W.asks(ctx["ref"]) if a.get("kind") == "step" and a.get("key") == key), None)
    if a and a["status"] == "stamped" and step.get("draft"):
        return DRAFT[step["draft"]](ctx, step, item)
    return None


def _person(ctx, step, item):
    ref = ctx["ref"]
    key = "%s|%s|%s" % (ctx["slot"], step["id"], item)
    with W._lock(ref):
        a = next((a for a in W.asks(ref) if a.get("kind") == "step" and a.get("key") == key), None)
        if a is None:
            a = W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "step", "engine": ctx["engine"], "slot": ctx["slot"],
                                 "key": key, "step": step["id"], "text": "%s: by hand" % step["name"], "status": "pending",
                                 "created": W.now()})
    if a["status"] == "pending":
        return ASKED, 0.0, a["id"], 0
    if a["status"] == "refused" or not step.get("draft"):
        return INVALID, 0.0, "refused by the owner", 0
    return DRAFT[step["draft"]](ctx, step, item), 0.0, "stamped by the owner", 0


def _call(ctx, step, item):
    return _soft(ctx, step, item)


def _checklist(ctx, step, item):
    text = candidate(ctx["ref"], step, "C1")
    if not text:
        return NO_RULE, 0.0, "no checklist", 0
    return _soft(ctx, step, item, checklist=text)


def _code(ctx, step, item):
    e = ladder(ctx["ref"]).get(step["id"]) or {}
    if e.get("form") == "table":
        t = candidate(ctx["ref"], step, "C2")
        if not isinstance(t, dict) or t.get("sha") != _sha(t.get("when")):
            return NO_RULE, 0.0, "the table is missing, or was changed by hand", 0
        out = interpret_table(t, _facts(ctx, step) or {})
        return (out, 0.0, "table", 0) if out is not NO_RULE else (NO_RULE, 0.0, "no rule", 0)
    if step.get("code") and step["code"] in CODE:
        return CODE[step["code"]](ctx, step, item), 0.0, "code", 0
    return NO_RULE, 0.0, "the app has no function of that name", 0


RESOLVE = {"P": _person, "C0": _call, "C1": _checklist, "C2": _code}


def _trial(ctx, step, item, out, check, facts):
    """The next rung, run beside the incumbent. Its output is counted, never used."""
    ref = ctx["ref"]
    t = (ladder(ref).get(step["id"]) or {}).get("trial")
    if not t or t.get("state") != "running":
        return None, 0.0, 0
    usd, calls, agrees = 0.0, 0, None
    if t["rung"] == "C2":
        got = interpret_table(candidate(ref, step, "C2"), facts or {})
        agrees = None if got is NO_RULE else (got.get(step["answer"]) == out.get(step["answer"]))
    else:
        text = candidate(ref, step, "C1")
        got, usd, _, calls = _soft(ctx, step, item, checklist=text) if text else (NO_RULE, 0.0, "", 0)
        if isinstance(got, dict):
            c2 = CHECK[step["check"]](ctx, step, item, got)
            same = got.get(step["answer"]) == out.get(step["answer"]) if step.get("answer") else True
            agrees = bool(c2.get("ok")) == bool(check.get("ok")) and same
    with W._lock(ref):
        e = ladder(ref).get(step["id"]) or {}
        t = e.get("trial") or t
        t["runs"] = int(t.get("runs") or 0) + 1
        if agrees is None:
            t["norule"] = int(t.get("norule") or 0) + 1
        elif agrees:
            t["agree"] = int(t.get("agree") or 0) + 1
        e["trial"] = t
        _save_entry(ref, e)
    return {"rung": t["rung"], "agrees": agrees}, usd, calls


# ---- the registry: code steps --------------------------------------------------------------------------------------
def _brief_text(ref):
    cur = W.latest(ref, "Brief")
    return W.read_files(ref, "Brief", cur["v"]).get("brief.md", "") if cur else ""


def plan_read(ctx, step, item):
    return {"brief": W.read_files(ctx["ref"], "Brief", ctx["inp"]["v"]).get("brief.md", "")}


def plan_fit(ctx, step, item):
    plan = dict(ctx["bag"]["plan.pages"])
    pages = [dict(p) for p in plan.get("pages") or [] if isinstance(p, dict)]
    for p in pages:
        p["slug"] = W.slug(str(p.get("slug") or p.get("title") or "page")) or "page"
        p.setdefault("title", p["slug"].title())
    if not pages or pages[0]["slug"] != "index":
        pages = [p for p in pages if p["slug"] != "index"]
        pages.insert(0, {"slug": "index", "title": "Home", "purpose": "the front door", "sections": ["Welcome"]})
    for s, t, purpose in W._asked_pages(ctx["bag"]["plan.read"]["brief"]):
        if s not in {p["slug"] for p in pages}:
            pages.append({"slug": s, "title": t, "purpose": purpose, "sections": [t]})
    seen, out = set(), []
    for p in pages:
        if p["slug"] not in seen:
            seen.add(p["slug"])
            out.append(p)
    plan["pages"] = out
    plan.setdefault("site_name", ctx["dept"]["name"])
    return plan


def plan_file(ctx, step, item):
    plan = ctx["bag"]["plan.fit"]
    n = len(plan["pages"])
    _tell_plan(ctx, plan)
    return {"files": {"site-plan.json": json.dumps(plan, indent=1)},
            "check": {"ok": n >= 2, "notes": ["%d pages" % n, str(ctx["how"].get("plan.pages") or "")]}}


def _tell_plan(ctx, plan):
    """The pages Plan chose, said to the person whenever they change, so a page the person never named is theirs to
    keep or drop (found live 2026-09-28: three pages the goal never asked for)."""
    try:
        ref = ctx["ref"]
        titles = [str(p.get("title") or p.get("slug")) for p in plan["pages"]]
        cur = W.latest(ref, "Site plan")
        if cur:
            before = json.loads(W.read_files(ref, "Site plan", cur["v"]).get("site-plan.json", "{}")).get("pages") or []
            if [str(p.get("title") or p.get("slug")) for p in before] == titles:
                return
        _tell(ref, ctx["dept"], {"src": "Root" if ctx["dept"].get("root") else OWNER}, "inform",
              {"word": "plan", "done": "Planned %d pages: %s. Say which to drop or add." % (len(titles), ", ".join(titles))})
    except Exception:  # noqa: BLE001 -- the plan is filed whether or not the word reached the person
        pass


def _owner_rules(d):
    """The rules the person stamped, as lines: the ones the line is held to (a kind's born rules are process, not pages)."""
    return [str(r["line"]) for r in d.get("rules") or [] if r.get("line") and str(r.get("id") or "").startswith("u-")]


def check_rules_of(ctx, step, item):
    """The person's own rules and every page as text: what the next step holds the site to (finding 12)."""
    rules = _owner_rules(ctx["dept"])
    src = W.read_files(ctx["ref"], "Pages", ctx["inp"]["v"])
    pages = []
    for name in sorted(src):
        if not name.endswith(".html"):
            continue
        try:
            data = json.loads(src[name])
        except Exception:  # noqa: BLE001
            data = {"title": name[:-5], "body_html": str(src[name])}
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(data.get("body_html") or ""))).strip()
        pages.append({"slug": name[:-5], "title": str(data.get("title") or name[:-5]), "text": text[:1500]})
    return {"rules": rules, "any": bool(rules and pages), "pages": pages}


SEND_BACK = "Correct this: the rule is broken"


def _send_back(ref, d, art, v, broken):
    """A build that breaks a stamped rule goes back to the line with the finding, twice at most, and the person is told
    each time (finding 12: two versions broke a stamped rule and nothing said so)."""
    try:
        lines = ["'%s' on %s" % (b.get("rule"), ", ".join(b.get("pages") or [])) for b in broken]
        cur = W.latest(ref, "Brief")
        tries = W.read_files(ref, "Brief", cur["v"]).get("brief.md", "").count(SEND_BACK) if cur else 0
        src = {"src": "Root" if d.get("root") else OWNER}
        if tries >= 2:
            _tell(ref, d, src, "inform", {"word": "broken", "done": "%s v%d breaks your rule %s, and two rewrites did not mend it. Say the rule another way, or drop it."
                                          % (art, v, "; ".join(lines))})
            return
        _file_words(ref, d, "%s %s" % (SEND_BACK, "; ".join(lines)), "the check's finding")
        _tell(ref, d, src, "inform", {"word": "broken", "done": "%s v%d breaks your rule %s. Sent back to be rewritten." % (art, v, "; ".join(lines))})
    except Exception:  # noqa: BLE001 -- the failed version is filed either way
        pass


def write_list(ctx, step, item):
    plan = json.loads(W.read_files(ctx["ref"], "Site plan", ctx["inp"]["v"]).get("site-plan.json", "{}"))
    return {"plan": plan, "pages": [p["slug"] for p in plan.get("pages") or []]}


def write_file(ctx, step, item):
    plan = ctx["bag"]["write.list"]["plan"]
    slugs = ctx["bag"]["write.list"]["pages"]
    files = {}
    for s, page in zip(slugs, ctx["bag"]["write.page"]):
        title = next((p.get("title") for p in plan["pages"] if p["slug"] == s), s)
        files[s + ".html"] = json.dumps({"title": str(page.get("title") or title), "body_html": str(page["body_html"])})
    files["_plan.json"] = json.dumps(plan)
    return {"files": files, "check": {"ok": bool(slugs), "notes": ["%d pages" % len(slugs), str(ctx["how"].get("write.page") or "")]}}


def check_build(ctx, step, item):
    files, check, _ = W.engine_check(ctx["ref"], ctx["dept"], ctx["inp"])
    held = ctx["bag"].get("check.rules")
    broken = [b for b in ((held.get("broken") if isinstance(held, dict) else None) or []) if isinstance(b, dict) and b.get("rule")]
    if broken:
        # a rule the person stamped is a check the line runs: a build that breaks it is filed failed and never goes live
        check = dict(check, ok=False, broken=broken,
                     notes=list(check.get("notes") or []) + ["breaks the rule '%s' on %s" % (b["rule"], ", ".join(b.get("pages") or [])) for b in broken])
    return {"files": files, "check": check}


def publish_copy(ctx, step, item):
    files, check, _ = W.engine_publish(ctx["ref"], ctx["dept"], ctx["inp"])
    return {"files": files, "check": check}


def identity_gate(ctx, step, item):
    """The rule, as built: the first publish asks the owner, and so does every department a Root sets up ("A new
    department is stamped by the owner"); a refused one is skipped, never done."""
    ref, name, slot, inp = ctx["ref"], ctx["engine"], ctx["slot"], ctx["inp"]
    if name == "Publish":
        if len(W.versions(ref, "Live site")) > int(ctx["dept"].get("publish_asks_from") or 0):
            return "admit", None
        # the ask carries the question where the site is served from (founder, 2026-09-28: "more of a question
        # to the user and should be asked to the user"); the answer, or the default on a plain stamp, stays on
        # the record and Publish reads it
        host = ctx["dept"].get("host") or W.HOST_DEFAULT
        kind = "publish"
        objective = ("say whether the site may go live for the first time"
                     + (" under its new goal" if ctx["dept"].get("publish_asks_from") else "")
                     + ", and where it is served from: %s unless you say another" % host)
        text = "Publish: go live for the first time, served from %s unless you say where else" % host
        may_read, about = ["Build"], {"art": "Build", "v": inp["v"]}
    elif name == "Setup":
        words = W.read_files(ref, "Request", inp["v"]).get("request.md", "").strip()
        kind = "setup"
        objective = "say whether Root may set up this department: " + words[:300]
        text = "Set up a department: " + words[:200]
        may_read, about = ["Request"], {"art": "Request", "v": inp["v"]}
    else:
        return "admit", None
    with W._lock(ref):
        a = next((x for x in W.asks(ref) if x.get("slot") == slot and x.get("kind") == kind), None)
        if a is None:
            p = post(ref, "Identity", OWNER, "request",
                     {"word": kind, "objective": objective, "output": "a stamp or a refusal", "may_read": may_read,
                      "boundaries": "this one %s" % kind}, about=about)
            W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": kind, "engine": name, "slot": slot, "text": text,
                             "status": "pending", "created": W.now(), "thread": p["thread"] if p else None})
            return "wait", "waits for the stamp"
    if a["status"] == "pending":
        return "wait", "waits for the stamp"
    if a["status"] == "refused":
        if not any(r.get("slot") == slot and r.get("status") == "skipped" for r in W.runs(ref)):
            W._put_run(ref, _run_row(name, False, slot, "skipped", "refused by the owner",
                                     chain=W._chain_of(ref, ctx["def"]["reads"], inp["v"])))
        return "refuse", "refused by the owner"
    return "admit", None


def priority_envelope(ctx, step, item):
    ref, name, slot = ctx["ref"], ctx["engine"], ctx["slot"]
    calls, usd = W._today_spend(ref, name)
    env = (ctx["dept"].get("envelopes") or {}).get(name) or W.ENVELOPE
    if calls >= env.get("calls", 0) or usd >= env.get("usd", 0):
        if not any(x.get("kind") == "envelope" and x.get("engine") == name and x["status"] == "pending" for x in W.asks(ref)):
            W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "envelope", "engine": name, "slot": slot,
                             "text": "%s is out of today's envelope" % name, "status": "pending", "created": W.now(), "escalated": True})
        return "wait", "%s is out of its envelope" % name
    return "admit", None


def coord_chain(ctx, step, item):
    ref = ctx["ref"]
    chain = W._chain_of(ref, ctx["def"]["reads"], ctx["inp"]["v"])
    if chain and sum(1 for r in W.runs(ref) if r.get("chain") == chain) >= W.CHAIN_LIMIT:
        return "wait", "the chain from %s hit its limit" % chain
    return "admit", None


def coord_heard(ctx, step, item):
    return {"said": "heard Identity's verdict: " + str((ctx["post"]["payload"] or {}).get("answer"))}


LEAVES = re.compile(r"\b(e-?mail|sms|text message|whatsapp|post (?:it )?to|tweet|send (?:it |this )?to|payment|charge|invoice|domain|dns|"
                    r"hosting|another site|social media)\b", re.I)
KINDS = ("goal", "add-page", "remove", "style", "change", "other")
#: Canon's five journeys (holding/website/native/products/cos/design-journeys.html). Identity recognises one of them.
JOURNEYS = ("task", "query", "directive", "feedback", "new-idea")
PHONE = re.compile(r"(?<![\w.])\+?\d[\d -]{6,}\d(?![\w.])")
ADDRESS = re.compile(r"\b(?:road|street|lane|avenue|nagar|marg|colony|sector|block|floor|\d{6})\b", re.I)


def _reaches(words, why=""):
    """What in the person's words reaches outside the site, named for them: an email, a phone number, an address, a
    payment; or the judge's own reason when it said one."""
    found = []
    if re.search(r"\b(?:e-?mail|@)", words, re.I) or "@" in words:
        found.append("an email address")
    if PHONE.search(words):
        found.append("a phone number")
    if ADDRESS.search(words):
        found.append("an address")
    if re.search(r"\b(?:payment|charge|invoice|pay)\b", words, re.I):
        found.append("a payment")
    if found:
        return ", ".join(found) + ", so people will write, call or come"
    w = str(why or "").strip().rstrip(".")
    return "" if not w or w.lower() in ("it reaches outside the site", "reaches outside the site") else w


def _answers_facts(ref, words):
    """True when the department's last word to the person was its facts question and these words carry no rule cue: the
    person is answering, and an answer is the facts, never a rule (found live 2026-09-28: the hours came back as a rule
    to stamp)."""
    if re.search(CUES[0][1], words, re.I):
        return False
    for p in reversed(board(ref)):
        if p["src"] == "Identity" and OWNER in p["dst"]:
            return (p.get("payload") or {}).get("word") == "facts"
    return False


CUES = (("directive", r"\b(from now on|always|never|every time|going forward|in future|stop (?:doing|using|saying)|just this once)\b"),
        ("new-idea", r"\b(what if|could we|can we have|i want a new|explore|how about|imagine if)\b"),
        ("feedback", r"\b(wrong|too (?:long|short|much|many|little)|missed|should have|i don'?t like|not what i|is off|mistake|incorrect)\b"),
        ("query", r"(\?\s*$|^\s*(?:what|how many|how much|which|when|where|who|why|is|are|does|did|tell me|show me)\b)"))


def _pages(ref):
    v = W.latest(ref, "Site plan")
    try:
        return json.loads(W.read_files(ref, "Site plan", v["v"]).get("site-plan.json", "{}")).get("pages") or [] if v else []
    except Exception:  # noqa: BLE001
        return []


def _named_page(ref, words):
    low = words.lower()
    for p in _pages(ref):
        for name in (str(p.get("title") or ""), str(p.get("slug") or "").replace("-", " ")):
            if len(name) > 2 and name.lower() != "home" and re.search(r"\b%s\b" % re.escape(name.lower()), low):
                return p["slug"]
    return "index" if re.search(r"\bhome ?page\b", low) and _pages(ref) else None


def identity_read(ctx, step, item):
    words = str((ctx["post"].get("payload") or {}).get("words") or "")
    first = not W.versions(ctx["ref"], W.artifacts_of(ctx["dept"])[0])
    if first:
        kind = "goal"
    elif re.search(r"\b(add|create|include|new)\b.{0,60}\b(page|section)\b", words, re.I):
        kind = "add-page"
    elif re.search(r"\b(remove|delete|drop|take (?:down|out))\b", words, re.I):
        kind = "remove"
    elif re.search(r"\b(colou?rs?|styles?|fonts?|look|design|theme|layout)\b", words, re.I):
        kind = "style"
    elif re.search(r"\b(change|update|fix|correct|rewrite|edit|replace|shorten)\b", words, re.I):
        kind = "change"
    else:
        kind = "other"
    cue = next((j for j, rx in CUES if re.search(rx, words, re.I)), "task")
    about = _named_page(ctx["ref"], words)
    return {"words": words, "about": about, "later": not first,
            "facts": {"kind": kind, "leaves_site": bool(LEAVES.search(words)), "first": first,
                      "cue": "task" if first else cue, "names_work": bool(about)}}


def _file_brief(ref, d, words, note):
    cur = W.latest(ref, "Brief")
    if not cur:
        return W.add_version(ref, "Brief", {"brief.md": "# " + d["name"] + "\n\n" + words + "\n"},
                             [{"ask": words, "at": W.now()}], "owner", {"ok": True, "notes": [note]})
    base = W.read_files(ref, "Brief", cur["v"]).get("brief.md", "")
    body = base.rstrip() + ("\n\n## Asked since\n" if "## Asked since" not in base else "\n") + "- " + words + "\n"
    return W.add_version(ref, "Brief", {"brief.md": body}, [{"art": "Brief", "v": cur["v"]}, {"ask": words, "at": W.now()}],
                         "owner", {"ok": True, "notes": [note]})


def _file_words(ref, d, words, note):
    """The owner's words, filed as the department's first artifact: the Brief's next version; on a Root, a new Request,
    which its engine Setup reads."""
    if d.get("kind") == "root":
        return W.add_version(ref, "Request", {"request.md": words + "\n"}, [{"ask": words, "at": W.now()}], "owner",
                             {"ok": True, "notes": [note]})
    return _file_brief(ref, d, words, note)


def _rule_ask(ref, slot, line, tag, words, thread, lead):
    text = "%s: %s" % (lead, line)
    W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "rule", "engine": "Identity", "slot": slot, "text": text, "tag": tag,
                     "line": line, "words": words, "status": "pending", "created": W.now(), "thread": thread})
    return text


def _mark(ref, about, words):
    """The owner's word on a piece of work counts against the step that made it: the strongest check there is."""
    made = [r for r in step_rows(ref) if r.get("step") == "write.page" and r.get("status") == "ok" and r.get("mode") == "slot"
            and (about is None or r.get("item") == about)]
    src = made[-1] if made else {"engine": "Write", "slot": None, "item": about, "rung": "C0", "in_sig": None}
    return _append(ref, "steps.jsonl", {"id": "s-" + uuid.uuid4().hex[:10], "run": None, "engine": src["engine"], "step": "write.page",
                                        "item": src.get("item"), "mode": "mark", "slot": src.get("slot"), "asked_rung": src.get("rung"),
                                        "rung": src.get("rung"), "miss": False, "by": "the owner", "in_sig": src.get("in_sig"),
                                        "check": {"ok": False, "notes": ["the owner: " + words]}, "usd": 0.0, "calls": 0, "ms": 0,
                                        "status": "failed", "trial": None, "def_version": defs()["def_version"],
                                        "started": W.now(), "ended": W.now()})


def _tell(ref, d, p, msg_type, payload, thread=None, about=None):
    """What Identity says to the owner. On the department's own board as always; and when the words came through Root
    (the front door), the same is said on Root's board too, about this department, so the one chat carries it. The
    department's own copy is marked via Root then, so the chat never counts it twice."""
    root = d.get("root")
    relay = p.get("src") == "Root" and root and W.dept(root)
    own = dict(payload)
    if relay:
        own["via"] = "Root"
    row = post(ref, "Identity", OWNER, msg_type, own, thread=thread, about=about)
    if relay:
        pl = dict(payload)
        pl.update({"dept": ref, "from": d.get("name")})
        try:
            post(root, "Identity", OWNER, msg_type, pl, about={"dept": ref, "name": d.get("name")})
        except ValueError:                       # Root's own table refuses nothing Identity says to the owner; a fault is a row here, not a crash
            pass
    return row


def tell_switch(ref, d, stopped):
    """Stop and Start are the person's own acts on the department: a turn of the chat, on Root's too, so a person who
    comes back reads what they did (found live 2026-09-28: the chat said nothing of a stop and still said 'is working')."""
    try:
        _tell(ref, d, {"src": "Root" if d.get("root") else OWNER}, "inform",
              {"word": "stopped" if stopped else "started",
               "done": "Stopped by you: every engine stops where it is." if stopped else "Started by you: every engine looks to its own triggers."})
    except Exception:  # noqa: BLE001 -- the switch never fails for a word
        pass


def identity_lost(ctx, step, item):
    """A request of the owner's, or one Root handed on, that Coordination closed at its bound before anyone answered:
    Identity says so to the person and asks for the words again (ER-9)."""
    ref, d, p = ctx["ref"], ctx["dept"], ctx["post"]
    pl = p.get("payload") or {}
    words = str(pl.get("words") or "")
    ab = pl.get("about") if isinstance(pl.get("about"), dict) else None
    if not ab and d.get("kind") == "root":               # no chip: the department the words named, as the route would have read it
        target = _named(_children(ref), words)
        if target:
            ab = {"dept": target["ref"], "name": target["name"]}
    _tell(ref, d, {"src": pl.get("from_src")}, "inform",
          {"word": "lost", "done": "I could not act on this in time: %s Say it again." % words, "for": pl.get("for")}, about=ab)
    return {"said": "said back a request lost at its bound: " + words[:80]}


FRONT_WAIT_S = 60


def front_state(ref):
    """The owner's requests on this board that nobody answered: waiting (open past FRONT_WAIT_S) and lost (closed at a
    bound, not yet said back). What the department's status and Health read (ER-9)."""
    ths = {t["id"]: t for t in threads(ref)}
    by_thread, said_back = {}, set()
    for q in board(ref):
        by_thread.setdefault(q["thread"], []).append(q)
        if (q.get("payload") or {}).get("for") and OWNER in q["dst"]:   # said back to the person, not merely told to Identity
            said_back.add(q["payload"]["for"])
    waiting, lost = [], []
    for tid, posts in by_thread.items():
        first = posts[0]
        if first["src"] not in (OWNER, "Root") or first["msg_type"] != "request":   # the owner's own, or handed on by Root
            continue
        answered = any(q["src"] not in (OWNER, "Root") for q in posts[1:])
        words = str((first.get("payload") or {}).get("words") or "")
        state = (ths.get(tid) or {}).get("state")
        if state in ("canceled", "failed") and not answered and tid not in said_back:
            lost.append({"words": words, "at": first["at"]})
        elif not answered and state not in CLOSED and time.time() - W._ts(first["at"]) > FRONT_WAIT_S:
            waiting.append({"words": words, "since": first["at"]})
    return {"waiting": waiting, "lost": lost}


def identity_file(ctx, step, item):
    ref, d, p = ctx["ref"], ctx["dept"], ctx["post"]
    got = ctx["bag"]["identity.read"]
    words, first = got["words"], got["facts"]["first"]
    journey = "task" if first else ctx["bag"]["identity.recognise"].get("journey")
    if not first and journey == "directive" and _answers_facts(ref, words):
        journey = "task"                                 # an answer to the department's own question is the facts (finding 16)
    if journey == "query":
        a = ctx["bag"]["identity.answer"]
        _tell(ref, d, p, "inform", {"word": "answer", "answer": a["answer"], "source": a["source"],
                                    "confidence": a["confidence"], "done": a["answer"]}, thread=p["thread"])
        return {"said": "answered the owner: " + str(a["answer"])[:160], "journey": journey}
    if journey == "directive":
        r = ctx["bag"]["identity.rule"]
        if r.get("scope") == "one-time":
            row = _file_words(ref, d, words, "the owner's directive, for this once")
            _tell(ref, d, p, "inform", {"word": "request", "done": "applied this once; not kept as a rule", "v": row["v"]}, thread=p["thread"])
            return {"said": "applied the owner's words once: " + words, "journey": journey, "filed": row["v"]}
        clash = [x["line"] for x in d.get("rules") or [] if x.get("line") and str(x["line"]).lower() == str(r["line"]).lower()]
        if clash:
            _tell(ref, d, p, "inform", {"word": "request", "done": "the department already has this rule"}, thread=p["thread"])
            return {"said": "the department already has this rule: " + r["line"], "journey": journey}
        text = _rule_ask(ref, ctx["slot"], r["line"], r["tag"], words, p["thread"], "A new goal, as understood" if r["tag"] == "goal"
                         else "A rule, as understood")
        _tell(ref, d, p, "request", {"word": "rule", "objective": text, "output": "a stamp or a refusal", "may_read": [],
                                     "boundaries": "this department, until the owner says otherwise"}, thread=p["thread"])
        return {"said": "restated the owner's words and put them back: " + r["line"], "journey": journey}
    if journey == "feedback":
        w = ctx["bag"]["identity.weigh"]
        about = w.get("about") or got.get("about")
        _mark(ref, about, words)
        title = next((str(x.get("title")) for x in _pages(ref) if x.get("slug") == about), None)
        row = _file_words(ref, d, "Correct this%s: %s" % (" on " + title if title else "", w["now"]), "the owner's feedback")
        _tell(ref, d, p, "inform", {"word": "request", "done": "sent a correction to the line", "v": row["v"]}, thread=p["thread"])
        if w.get("future"):
            t = _tell(ref, d, p, "request", {"word": "rule", "objective": "Carry this forward: " + str(w["future"]),
                                             "output": "a stamp, or a refusal to keep it to this once", "may_read": [],
                                             "boundaries": "work like this, from now on"})
            _rule_ask(ref, ctx["slot"], str(w["future"]), "always", words, t["thread"] if t else None, "Carry this forward")
        return {"said": "took the owner's feedback%s: %s" % (" on " + title if title else "", w["now"]), "journey": journey, "filed": row["v"]}
    if journey == "new-idea":
        post(ref, "Identity", "Adaptation", "request", {"word": "idea", "words": words, "objective": "shape this idea and park it",
                                                        "output": "the idea reflected back, in two or three shapes",
                                                        "may_read": ["Brief", "Site plan"], "boundaries": "nothing is built before the owner commits",
                                                        "for": p["thread"]})
        return {"said": "passed an idea to Adaptation: " + words, "journey": journey}
    out = ctx["bag"]["identity.take"]
    verdict, why = out.get("verdict"), str(out.get("why") or "")
    if verdict == "go":
        row = _file_words(ref, d, words, "the owner's goal" if ctx["bag"]["identity.read"]["facts"]["first"] else "the owner's ask")
        _tell(ref, d, p, "inform", {"word": "request", "done": "filed in the %s" % W.artifacts_of(d)[0], "v": row["v"]}, thread=p["thread"])
        return {"said": "took the owner's words: " + words, "filed": row["v"]}
    if verdict == "ask":
        # in the person's words: what reaches outside, and what a stamp does (found live 2026-09-28: the person's own
        # address came back as "This reaches outside the site")
        reach = _reaches(words, why)
        lead = "Your words reach outside the site%s. Put them on the site as said? Stamp to go ahead, Refuse to leave them out." % (
            (": " + reach) if reach else "")
        W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "request", "engine": "Identity", "slot": ctx["slot"],
                         "text": lead + " " + words, "why": why, "words": words, "status": "pending",
                         "created": W.now(), "thread": p["thread"]})
        _tell(ref, d, p, "request", {"word": "request", "objective": lead,
                                     "output": "a stamp or a refusal", "may_read": ["Brief"], "boundaries": words,
                                     "why": why}, thread=p["thread"])
        return {"said": "put the owner's words back to the owner: " + (why or words)}
    _tell(ref, d, p, "refuse", {"word": "request", "why": why or "it breaks a rule"}, thread=p["thread"])
    return {"said": "refused: " + (why or words)}


# ---- the front door: the person speaks with Root (founder, 2026-09-28) ----------------------------------------------
FRONT = [(re.compile(r"^\s*(?:start|set up|create|make|found)\s+(?:a |an |the |another )?(?:new )?[\w -]*?\bdepartment\b", re.I), "setup"),
         (re.compile(r"^\s*(?:stamp|yes|approve|approved|go ahead|ok)\b", re.I), "stamp"),
         (re.compile(r"^\s*(?:refuse|no|reject|rejected)\b", re.I), "refuse"),
         (re.compile(r"^\s*stop\b", re.I), "stop"),
         (re.compile(r"^\s*(?:start|resume)\b", re.I), "start")]


def _children(root_ref):
    return [d for d in W.list_depts() if d.get("parent") == root_ref]


def _named(children, words):
    low = words.lower()
    for c in children:
        if c["name"].lower() in low:
            return c
    for c in children:                              # "meadow clinic" for "Meadow Clinic Website"
        stem = c["name"].lower().replace(" website", "").strip()
        if stem and re.search(r"\b%s\b" % re.escape(stem), low):
            return c
    return None


def identity_route(ctx, step, item):
    """Who the words are for, by code: the chip (the department the person stood in), a name in the words, the only
    child; and what they want: a department set up, a stamp, a refusal, Stop, Start, or words for a department."""
    ref, p = ctx["ref"], ctx["post"]
    pl = p.get("payload") or {}
    words = str(pl.get("words") or "")
    about = ((pl.get("about") or {}) if isinstance(pl.get("about"), dict) else {}).get("dept")
    kids = _children(ref)
    wants = next((w for rx, w in FRONT if rx.search(words)), "words")
    target = next((c for c in kids if c["ref"] == about), None) if about else None
    if target is None:
        target = _named(kids, words)
    if target is None and wants != "setup" and len(kids) == 1:
        target = kids[0]
    if target is None and wants == "words" and not kids:
        wants = "setup"                              # a Root with no department yet: the first words are for one
    said = words
    if target and wants == "words":
        for rx in (r"^\s*(?:on|to|for|in)\s+%s\s*[,:]\s*(.+)$", r"^\s*%s\s*[,:]\s*(.+)$"):
            m = re.match(rx % re.escape(target["name"]), words, re.I)
            if m:
                said = m.group(1).strip()
                break
    return {"wants": wants, "target": target["ref"] if target else None, "name": target["name"] if target else None, "words": said,
            "facts": {"wants": wants, "targeted": bool(target), "children": str(len(kids))}}


def identity_hand(ctx, step, item):
    """Root does what the words want: files a department request (its engine Setup asks, then makes); stamps or refuses the
    ask waiting; stops or starts a department; or hands the words to the department's Identity as a post from Root, and
    tells the owner where they went. Every answer to the owner carries the department it is about."""
    ref, d, p = ctx["ref"], ctx["dept"], ctx["post"]
    r = ctx["bag"]["identity.route"]
    wants, target, name, words, th = r["wants"], r["target"], r["name"], r["words"], p["thread"]
    ab = {"dept": target, "name": name} if target else None
    if wants == "setup":
        row = _file_words(ref, d, words, "the owner's ask")
        post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "filed as a request; a new department is stamped by you, so an ask follows",
                                                "v": row["v"]}, thread=th)
        return {"said": "filed a request for a department: " + words, "filed": row["v"]}
    if wants in ("stamp", "refuse"):
        for tref in ([target] if target else [c["ref"] for c in _children(ref)]) + [ref]:
            pend = [x for x in W.asks(tref) if x["status"] == "pending" and not x.get("escalated")]
            a = pend[-1] if pend else None             # the latest ask: the one the person just saw
            if a:
                W.decide_ask(tref, a["id"], wants == "stamp")
                dn = (W.dept(tref) or {}).get("name")
                post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "%s: %s" % ("stamped" if wants == "stamp" else "refused", a["text"]),
                                                        "dept": tref, "from": dn}, thread=th, about={"dept": tref, "name": dn})
                return {"said": "%s the ask on %s" % ("stamped" if wants == "stamp" else "refused", dn)}
        post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "nothing is waiting for a stamp"}, thread=th)
        return {"said": "nothing waits for a stamp"}
    if wants in ("stop", "start"):
        if not target:
            post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "Say which department: " + (", ".join(c["name"] for c in _children(ref)) or "none yet")}, thread=th)
            return {"said": "asked which department"}
        W.set_stopped(target, wants == "stop")
        post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "%s is %s" % (name, "Off" if wants == "stop" else "On"), "dept": target, "from": name},
             thread=th, about=ab)
        return {"said": "%s %s" % ("stopped" if wants == "stop" else "started", name)}
    if not target:
        kids = _children(ref)
        post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "Say which department: " + ", ".join(c["name"] for c in kids) +
                                                ". For a new one, say: start a department for ..."}, thread=th)
        return {"said": "asked which department"}
    post(target, "Root", "Identity", "request", {"word": "request", "words": words, "objective": words, "output": "the Brief's next version",
                                                 "may_read": ["Brief"], "boundaries": "inside the department's goal and rules", "front": ref, "front_thread": th})
    post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "handed to %s" % name, "dept": target, "from": name}, thread=th, about=ab)
    return {"said": "handed to %s: %s" % (name, words)}


def _own_turns(dref, name):
    """A department's own owner-facing turns (ER-10): what its Identity asked or told its owner in threads Root did not
    start, and the owner's own words and stamps there. A post that went to Root's board as well (via Root) is left to
    Root's copy, so the chat never counts it twice."""
    ths = {t["id"]: t for t in threads(dref)}
    born_of_root = bool((W.dept(dref) or {}).get("root"))
    out = []
    for p in board(dref):
        if p["src"] != OWNER and OWNER not in p["dst"]:
            continue
        pl = p.get("payload") or {}
        # what Identity said in a thread Root opened went to Root's board too; the person's own stamp or refusal in
        # such a thread lives here alone, so it shows (found live 2026-09-28: a stamp inside the department left no turn)
        if pl.get("via") == "Root" or ((ths.get(p["thread"]) or {}).get("opened_by") == "Root" and p["src"] != OWNER):
            continue
        out.append({"n": p["n"], "src": p["src"], "dst": p["dst"], "msg_type": p["msg_type"], "at": p["at"], "thread": p["thread"],
                    "word": pl.get("word"), "line": _line(p) or str(pl.get("done") or pl.get("words") or ""),
                    "dept": dref, "name": name, "own": True, "link": pl.get("link"),
                    "birth": p["n"] == 1 and p["src"] == OWNER and born_of_root})   # the words Root handed at the birth
    return out


def fn_chat_view(ref, fn):
    """One function's chat, which exists from the department's birth and is never started: what the function said and
    was told on the board, the person's words said to it (about fn) and every owner-facing turn of those threads, and
    its thinking, its own step rows, as quiet lines between, all in time order (founder, 2026-09-29: a click on a
    function's Chat "should not start a new chat. It should just show the existing chat there"; SIM-3 c: each
    function's thinking in its own chat)."""
    name = str(fn or "").strip().title()
    if name not in FUNCTIONS:
        raise ValueError("no function named %s" % fn)
    d = W.dept(ref) or {}
    posts = board(ref)

    def to_fn(p):
        ab = p.get("about") if isinstance(p.get("about"), dict) else {}
        pl = p.get("payload") or {}
        pab = pl.get("about") if isinstance(pl.get("about"), dict) else {}
        return (ab.get("fn") or pab.get("fn") or "").lower() == name.lower()

    mine = {p["thread"] for p in posts if to_fn(p)}
    turns = []
    for p in posts:
        pl = p.get("payload") or {}
        own = p["src"] == name or name in p["dst"] or to_fn(p)
        in_thread = p["thread"] in mine and (p["src"] == OWNER or OWNER in p["dst"])
        if not own and not in_thread:
            continue
        turns.append({"n": p["n"], "src": p["src"], "dst": p["dst"], "msg_type": p["msg_type"], "at": p["at"], "thread": p["thread"],
                      "word": pl.get("word"), "line": _line(p) or str(pl.get("done") or pl.get("words") or ""), "think": False,
                      "_k": (str(p["at"]), p["n"], 0)})
    for r in step_rows(ref):
        if r.get("engine") != name:
            continue
        sname = (step_def(str(r.get("step")))[1] or {}).get("name") or str(r.get("step"))
        if r.get("mode") == "gate":
            line = "%s: %s" % (sname, r.get("answer") or "")
        else:
            line = "%s, %s" % (sname, RUNG_NAME.get(str(r.get("rung")), str(r.get("rung") or "")).lower())
        at = r.get("ended") or r.get("started") or r.get("at") or ""
        # within one second the clock cannot tell; a row that read post n comes after post n (found live 2026-09-29:
        # Identity's reading of the words stood above the words)
        read = next((x.get("post") for x in (r.get("read") or []) if isinstance(x, dict) and x.get("post")), None)
        # a row that read no post (a gate on the way to a start) follows whatever was said in its second
        turns.append({"n": None, "src": name, "dst": [], "msg_type": "step", "at": at, "thread": r.get("run"), "word": r.get("step"),
                      "line": line, "think": True, "_k": (str(at), read if read is not None else 10 ** 9, 1)})
    turns.sort(key=lambda t: t["_k"])
    for t in turns:
        del t["_k"]
    return {"fn": name, "dept": ref, "name": d.get("name"), "turns": turns, "any": bool(turns)}


def chat_view(ref, about=None):
    """The one chat: the owner's turns and what Identity said back, read from Root's board, each with the department it
    is about, and each department's own asks and answers beside them (ER-10), in time order; the asks waiting, with the
    department they belong to; the departments under Root. For a department, the same chat scoped to it."""
    d = W.dept(ref) or {}
    root = ref if d.get("kind") == "root" else d.get("root")
    if root and not W.dept(root):
        root = None
    if root and d.get("kind") != "root" and not about:
        about = ref
    turns = []
    if root:
        for p in board(root):
            if p["src"] != OWNER and OWNER not in p["dst"]:
                continue
            pl = p.get("payload") or {}
            ab = p.get("about") if isinstance(p.get("about"), dict) else {}
            dref = ab.get("dept") or pl.get("dept") or ((pl.get("about") or {}) if isinstance(pl.get("about"), dict) else {}).get("dept")
            if about and dref != about:
                continue
            turns.append({"n": p["n"], "src": p["src"], "dst": p["dst"], "msg_type": p["msg_type"], "at": p["at"], "thread": p["thread"],
                          "word": pl.get("word"), "line": _line(p) or str(pl.get("done") or pl.get("words") or ""),
                          "dept": dref, "name": ab.get("name") or pl.get("from"), "link": pl.get("link")})
        # the person's words at the front door carry the department they reached, as Root's own hand-over says
        # (found live 2026-09-28: a turn that named the department in its words showed no chip)
        for t in turns:
            if t["src"] == OWNER and t.get("word") == "front" and not t.get("dept"):
                later = next((u for u in turns if u["thread"] == t["thread"] and u["n"] > t["n"] and u.get("dept")), None)
                if later:
                    t["dept"], t["name"] = later["dept"], later.get("name")
    kids = _children(root) if root else []
    if root:
        for c in ([W.dept(about)] if about else kids):
            if c and c.get("ref") and c["ref"] != root:
                turns += _own_turns(c["ref"], c.get("name"))
    elif d:
        turns += _own_turns(ref, d.get("name"))         # a department with no Root: its own chat
    if root and not about:
        # the goal at a department's birth is the person's words said once at the front door; on the whole chat they
        # already stand as the front turn and the setup ask, so the birth copy is not said again (finding 3)
        turns = [t for t in turns if not t.get("birth")]
    turns.sort(key=lambda t: (str(t["at"]), t["n"]))
    refs = [about] if about else ([root] + [c["ref"] for c in kids] if root else [ref])
    asks = []
    for r in refs:
        dn = (W.dept(r) or {}).get("name")
        asks += [dict(a, ref=r, dept=dn) for a in W.asks(r) if a["status"] == "pending"]
    return {"root": root, "about": about, "turns": turns, "asks": asks,
            "departments": [{"ref": c["ref"], "name": c["name"], "stopped": bool(c.get("stopped"))} for c in kids]}


def identity_verdict(ctx, step, item):
    ref, pl = ctx["ref"], ctx["post"]["payload"]
    got = ctx["bag"]["identity.judge"]
    answer = got.get("verdict") if got.get("verdict") in ("admit", "wait", "refuse") else "wait"
    with W._lock(ref):
        vs = _verdicts(ref)
        vs["%s|%s" % (pl.get("slot"), pl.get("gate"))] = {"answer": answer, "why": got.get("why"), "at": W.now()}
        W._write(W.ddir(ref) / "verdicts.json", vs)
    post(ref, "Identity", "Coordination", "agree" if answer == "admit" else "refuse", {"word": "verdict", "answer": answer},
         thread=ctx["post"]["thread"])
    return {"said": "gave its verdict on %s: %s" % (pl.get("engine"), answer), "verdict": answer}


def identity_rung(ctx, step, item):
    ref, p = ctx["ref"], ctx["post"]
    pl = p["payload"]
    _, s = step_def(pl["step"])
    text = "Move “%s” from %s to %s" % (s["name"], RUNG_NAME[pl["from"]].lower(), RUNG_NAME[pl["to"]].lower())
    W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "rung", "engine": pl.get("engine"), "slot": ctx["slot"],
                     "step": pl["step"], "from": pl["from"], "to": pl["to"], "form": pl.get("form"), "evidence": pl.get("evidence"),
                     "trial": pl.get("trial"), "text": text, "status": "pending", "created": W.now(), "thread": p["thread"]})
    post(ref, "Identity", OWNER, "request", {"word": "rung", "objective": text, "output": "a stamp or a refusal", "may_read": [],
                                             "boundaries": "this one step", "evidence": pl.get("evidence")}, thread=p["thread"])
    return {"said": "put a move to the owner: " + text}


def identity_apply(ctx, step, item):
    ref, pl = ctx["ref"], ctx["post"]["payload"]
    a = next((x for x in W.asks(ref) if x["id"] == pl.get("ask")), None)
    if not a:
        return {"said": "took a stamp"}
    if a.get("kind") == "engine":
        # TPL-1 slice 2: the engine Adaptation offered, priced by Priority, now stamped: on the record, in the line, and
        # a shaped one born into the Library; it starts on its own trigger like every other engine
        offer = a.get("offer") or {}
        W.add_engine(ref, a.get("engine"), shape=offer.get("shape"), by="the owner")
        _note_idea(ref, a.get("idea"), {"engine": a.get("engine"), "state": "built"})
        return {"said": "added the engine %s on the owner's stamp; it starts on its own trigger" % a.get("engine")}
    if a.get("kind") == "rung":
        _, s = step_def(a["step"])
        move(ref, s, a["to"], "stamp " + a["id"], evidence=a.get("evidence"), form=a.get("form"))
        post(ref, "Identity", "Adaptation", "inform", {"word": "rung", "step": a["step"], "to": a["to"], "stamped": True})
        return {"said": "moved a step, on the owner's stamp: " + a["text"]}
    if a.get("kind") == "request":
        row = _file_brief(ref, ctx["dept"], a.get("words") or "", "the owner's ask, stamped")
        return {"said": "took the owner's words, stamped", "filed": row["v"]}
    if a.get("kind") == "rule":
        with W._lock(ref):
            d = W.dept(ref)
            if a.get("tag") == "goal":
                d.setdefault("goals", []).append({"goal": d.get("goal"), "until": W.now()})
                d["goal"] = a["line"]
                d["publish_asks_from"] = len(W.versions(ref, "Live site"))      # the first publish under a new goal asks again
            else:
                d["rules"] = list(d.get("rules") or []) + [{"id": "u-" + uuid.uuid4().hex[:6], "tag": a.get("tag") or "always",
                                                            "line": a["line"], "since": W.now(), "from": a.get("words")}]
            W.save_dept(ref, d)
        row = _file_brief(ref, d, ("The goal is now: " if a.get("tag") == "goal" else "A rule, from now on: ") + a["line"],
                          "a directive the owner stamped")
        return {"said": ("took a new goal: " if a.get("tag") == "goal" else "took a rule: ") + a["line"], "filed": row["v"]}
    if a.get("kind") == "finding":
        row = _file_brief(ref, ctx["dept"], "Correct this: " + str(a.get("found") or a.get("claim") or a["text"]),
                          "a finding the owner stamped")
        return {"said": "sent a finding back to the line", "filed": row["v"]}
    return {"said": "took the owner's stamp: " + a["text"]}


def identity_drop(ctx, step, item):
    ref, pl = ctx["ref"], ctx["post"]["payload"]
    a = next((x for x in W.asks(ref) if x["id"] == pl.get("ask")), None)
    if a and a.get("kind") == "rung":
        _, s = step_def(a["step"])
        e = entry(ref, s)
        e["history"].append({"at": W.now(), "from": e["rung"], "to": e["rung"], "by": "refused by the owner", "evidence": a.get("evidence")})
        e.update({"trial": None, "pending": None})
        _save_entry(ref, e)
        post(ref, "Identity", "Adaptation", "inform", {"word": "rung", "step": a["step"], "to": a["to"], "stamped": False})
    return {"said": "took the owner's refusal" + (": " + a["text"] if a else "")}


def _finding_lines(ref, findings, claim):
    """What Audit found, in the owner's words: every finding a reader could be misled by, each with the page it is on."""
    high = [f for f in findings or [] if isinstance(f, dict) and f.get("claim") and str(f.get("severity") or "").lower() == "high"]
    titles = {str(p.get("slug")): str(p.get("title")) for p in _pages(ref) if p.get("title")}
    out = []
    for f in (high or [{"page": None, "claim": claim}])[:4]:
        slug = str(f.get("page") or "").rsplit(".", 1)[0]
        where = titles.get(slug) or ("Home" if slug == "index" else None)
        out.append(("on %s, " % where if where else "") + str(f["claim"]).strip().rstrip("."))
    return out


def identity_finding(ctx, step, item):
    ref, pl = ctx["ref"], ctx["post"]["payload"]
    finds = [f for f in pl.get("findings") or [] if isinstance(f, dict) and f.get("claim")]
    holes = [f for f in finds if f.get("kind") == "hole"]
    rest = [f for f in finds if f.get("kind") != "hole"]
    said = []
    if holes:
        # the facts only the owner knows: a question in the chat, not a stamp (found live 2026-09-28: a site of
        # "to be confirmed"); the owner's reply is a request like any other, and the line puts the facts in
        lines = _finding_lines(ref, holes, None)
        text = ("The site says it does not know %d thing%s: %s. Tell me here and I will put them in."
                % (len(holes), "" if len(holes) == 1 else "s", "; ".join(lines) + (" ..." if len(holes) > len(lines) else "")))
        _tell(ref, ctx["dept"], {"src": "Root" if ctx["dept"].get("root") else OWNER}, "inform",
              {"word": "facts", "done": text, "holes": len(holes), "about_version": pl.get("about_version")})
        said.append("asked the owner for %d fact%s the site lacks" % (len(holes), "" if len(holes) == 1 else "s"))
    high = [f for f in rest if str(f.get("severity") or "").lower() == "high"]
    if high:
        claim = str(high[0]["claim"])
        found = "; ".join(_finding_lines(ref, rest, claim))
        text = "Audit found: %s. Stamp to have it put right." % found
        p = post(ref, "Identity", OWNER, "request", {"word": "finding", "objective": text,
                                                     "output": "a stamp or a refusal", "may_read": ["Live site"],
                                                     "boundaries": claim, "claim": claim})
        W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "finding", "engine": "Audit", "slot": ctx["slot"],
                         "text": text, "claim": claim, "found": found, "findings": rest,
                         "status": "pending", "created": W.now(), "thread": p["thread"] if p else None})
        said.append("put a finding to the owner: " + found)
    elif rest:
        said.append("noted a finding: " + str(rest[0]["claim"]))
    return {"said": "; ".join(said) or "noted a finding: " + str(pl.get("claim"))}


def identity_idea(ctx, step, item):
    pl = ctx["post"]["payload"]
    said = "parked an idea: %s" % pl.get("reflected")
    if pl.get("for"):
        post(ctx["ref"], "Identity", OWNER, "inform", {"word": "idea", "done": said, "shapes": pl.get("shapes"), "idea": pl.get("idea")},
             thread=pl["for"])
    return {"said": "told the owner where the idea went: " + str(pl.get("reflected"))}


def ideas(ref):
    return W._read(W.ddir(ref) / "ideas.json", [])


def adapt_park(ctx, step, item):
    """Canon's new-idea journey: never built before the owner commits, and never lost."""
    ref, pl, got = ctx["ref"], ctx["post"]["payload"], ctx["bag"]["adapt.shape"]
    row = {"id": "i-" + uuid.uuid4().hex[:6], "words": pl.get("words"), "reflected": got["reflected"], "question": got.get("question"),
           "shapes": [str(x) for x in got["shapes"]][:3], "state": "parked", "at": W.now()}
    with W._lock(ref):
        rows = ideas(ref)
        rows.append(row)
        W._write(W.ddir(ref) / "ideas.json", rows)
    post(ref, "Adaptation", "Identity", "inform", {"word": "idea", "idea": row["id"], "reflected": row["reflected"],
                                                   "shapes": row["shapes"], "for": pl.get("for")}, thread=ctx["post"]["thread"])
    return {"said": "parked an idea, in %d shapes: %s" % (len(row["shapes"]), row["reflected"]), "idea": row["id"]}


def identity_alarm(ctx, step, item):
    return {"said": "heard an alarm: " + str((ctx["post"]["payload"] or {}).get("what"))}


def priority_read(ctx, step, item):
    pl = ctx["post"]["payload"]
    eng = pl.get("engine") or "Write"
    calls, _ = W._today_spend(ctx["ref"], eng)
    env = (ctx["dept"].get("envelopes") or {}).get(eng) or W.ENVELOPE
    return {"word": pl.get("word"), "engine": eng, "facts": {"word": pl.get("word"), "room": calls * 2 < int(env.get("calls") or 0)}}


def priority_post(ctx, step, item):
    pl = ctx["post"]["payload"]
    got = ctx["bag"]["priority.bargain"]
    ok = got.get("answer") == "accept"
    post(ctx["ref"], "Priority", "Adaptation", "accept-proposal" if ok else "reject-proposal",
         {"word": pl.get("word"), "step": pl.get("step"), "to": pl.get("to"), "form": pl.get("form"), "why": got.get("why")},
         thread=ctx["post"]["thread"])
    return {"said": ("granted" if ok else "refused") + " a trial of " + str(pl.get("step"))}


def adapt_sense(ctx, step, item):
    ref = ctx["ref"]
    rows, L = step_rows(ref), ladder(ref)
    out = {}
    for name in defs()["engines"]:
        for s in all_steps(name):
            ev = evidence(ref, s["id"], rows=rows, since=(L.get(s["id"]) or {}).get("since_row"))
            if ev["runs"]:
                out[s["id"]] = ev
    return {"steps": out}


def adapt_ladder(ctx, step, item):
    ref = ctx["ref"]
    moves = []
    for sid, ev in sorted(ctx["bag"]["adapt.sense"]["steps"].items()):
        eng, s = step_def(sid)
        if not s or not s.get("prompt"):
            continue                                   # a step with no softer form has nowhere to move
        n = numbers(ref, eng)                          # the engine's own numbers, from its Settings
        e = entry(ref, s, eng)
        if e.get("held") or e.get("pending"):
            continue
        rung, t = e["rung"], e.get("trial")
        strict = s.get("stringency") == "high"
        if RUNGS.index(rung) > RUNGS.index(s["born"]) and (ev["differing"] > n["differing"] or ev["misses"] >= n["misses"]):
            moves.append({"kind": "down", "step": sid, "engine": eng, "from": rung, "to": BELOW[rung], "evidence": ev,
                          "why": "its answers began to differ" if ev["differing"] > n["differing"] else "it met inputs it had no rule for"})
            continue
        if t and t.get("state") == "running":
            if int(t.get("runs") or 0) >= n["trial"]:
                against = int(t["runs"]) - int(t.get("agree") or 0) - int(t.get("norule") or 0)
                if against <= (0 if strict else 1) and int(t.get("agree") or 0) >= 1:
                    moves.append({"kind": "propose", "step": sid, "engine": eng, "from": rung, "to": t["rung"], "form": t.get("form"),
                                  "evidence": ev, "trial": {k: t.get(k) for k in ("runs", "agree", "norule")}})
                else:
                    moves.append({"kind": "end-trial", "step": sid, "engine": eng, "why": "the trial disagreed"})
            continue
        up = ABOVE.get(rung)
        top = s.get("ceiling") or "C2"
        if not up or RUNGS.index(up) > RUNGS.index(top) or (up == "C2" and not s.get("facts")):
            continue
        if ev["runs"] >= n["runs"] * (2 if strict else 1) and ev["differing"] <= n["differing"] and (ev["pass"] or 0) >= 0.95:
            moves.append({"kind": "trial", "step": sid, "engine": eng, "from": rung, "to": up, "evidence": ev})
    return {"moves": moves}


def adapt_act(ctx, step, item):
    ref, said = ctx["ref"], []
    for m in ctx["bag"]["adapt.ladder"]["moves"]:
        eng, s = step_def(m["step"])
        e = entry(ref, s, eng)
        if m["kind"] == "down":
            move(ref, s, m["to"], "evidence: " + m["why"], evidence=m["evidence"])
            said.append("stepped “%s” down: %s" % (s["name"], m["why"]))
        elif m["kind"] == "end-trial":
            e["history"].append({"at": W.now(), "from": e["rung"], "to": e["rung"], "by": m["why"], "evidence": None})
            e["trial"] = None
            _save_entry(ref, e)
            said.append("ended a trial of “%s”" % s["name"])
        elif m["kind"] == "trial" and m["to"] == "C2":
            t = learn_table(ref, s)
            if not t["when"]:
                continue
            t["sha"] = _sha(t["when"])
            W.add_version(ref, "Table: " + s["id"], {"table.json": json.dumps(t, indent=1)}, [{"rows": m["evidence"]["runs"]}],
                          ctx["run"], {"ok": True, "notes": ["%d rules" % len(t["when"])]})
            e["trial"] = {"rung": "C2", "form": "table", "runs": 0, "agree": 0, "norule": 0, "state": "running", "started": W.now()}
            _save_entry(ref, e)
            said.append("began a trial of “%s” as code" % s["name"])
        elif m["kind"] == "trial":
            W.add_version(ref, "Checklist: " + s["id"], {"checklist.md": learn_checklist(ref, s)}, [{"rows": m["evidence"]["runs"]}],
                          ctx["run"], {"ok": True, "notes": ["from %d runs" % m["evidence"]["runs"]]})
            p = post(ref, "Adaptation", "Priority", "propose",
                     {"word": "trial", "step": s["id"], "engine": eng, "to": "C1", "form": None,
                      "cost": "one more call a run, for %d runs" % numbers(ref, eng)["trial"], "evidence": m["evidence"]})
            e["pending"] = "a trial, with Priority"
            _save_entry(ref, e)
            if p:
                said.append("asked Priority for a trial of “%s” by checklist" % s["name"])
        elif m["kind"] == "propose":
            p = post(ref, "Adaptation", "Identity", "propose",
                     {"word": "rung", "step": s["id"], "engine": eng, "from": m["from"], "to": m["to"], "form": m.get("form"),
                      "evidence": m["evidence"], "trial": m["trial"]})
            e["pending"] = "a move, with the owner"
            if e.get("trial"):
                e["trial"]["state"] = "done"
            _save_entry(ref, e)
            if p:
                said.append("proposed “%s” one rung up" % s["name"])
    return {"said": "; ".join(said) if said else "read the rows; nothing to move", "moves": len(ctx["bag"]["adapt.ladder"]["moves"])}


def adapt_trial(ctx, step, item):
    pl = ctx["post"]["payload"]
    eng, s = step_def(pl["step"])
    e = entry(ctx["ref"], s, eng)
    e.update({"pending": None, "trial": {"rung": pl.get("to") or "C1", "form": pl.get("form"), "runs": 0, "agree": 0, "norule": 0,
                                         "state": "running", "started": W.now()}})
    _save_entry(ctx["ref"], e)
    return {"said": "began a trial of “%s” by checklist" % s["name"]}


def adapt_notrial(ctx, step, item):
    pl = ctx["post"]["payload"]
    eng, s = step_def(pl["step"])
    e = entry(ctx["ref"], s, eng)
    e["history"].append({"at": W.now(), "from": e["rung"], "to": e["rung"], "by": "Priority refused the trial", "evidence": None})
    e.update({"pending": None, "trial": None})
    _save_entry(ctx["ref"], e)
    return {"said": "dropped a trial of “%s”: Priority refused it" % s["name"]}


def adapt_heard(ctx, step, item):
    pl = ctx["post"]["payload"]
    return {"said": "heard the ruling on " + str(pl.get("step")) + (": moved" if pl.get("stamped") else ": left as it is")}


def audit_pick(ctx, step, item):
    v = int(ctx["inp"]["v"])
    files = W.read_files(ctx["ref"], "Live site", v)
    return {"sample": v <= 3 or v % 3 == 0, "v": v, "pages": sorted(k for k in files if k.endswith(".html"))}


def audit_mechanical(ctx, step, item):
    ref = ctx["ref"]
    if not ctx["bag"]["audit.pick"]["sample"]:
        return {"ok": True, "notes": ["not sampled"]}
    notes = []
    for a in W.artifacts_of(W.dept(ref))[1:]:
        for v in W.versions(ref, a):
            if not v.get("run") or "check" not in v:
                notes.append("%s has a version with no run or no check" % a)
    if not any(c.get("kind") == "ask" for c in W.trace(ref, "Live site", ctx["inp"]["v"])):
        notes.append("the live site does not trace back to the owner's words")
    # a page that says "to be confirmed" published what nobody knew (found live 2026-09-28: twelve such places on
    # four pages); Audit names each hole, Identity asks the owner for the facts instead of a stamp
    holes = placeholders(W.read_files(ref, "Live site", ctx["inp"]["v"]))
    said = notes + (["the site says it does not know %d thing%s" % (len(holes), "" if len(holes) == 1 else "s")] if holes else [])
    return {"ok": not said, "notes": said or ["every version has its run and its check; the trace reaches the owner's words"],
            "faults": notes, "holes": holes}


PLACEHOLDER = re.compile(r"to be confirmed|to be announced|\bTBD\b|\bTBA\b|lorem ipsum|\[insert[^\]]*\]|coming soon|will be added here", re.I)


def placeholders(files):
    """Where a site admits it does not know: each placeholder phrase with the words before it, one finding per hole."""
    out = []
    for name in sorted(files):
        if not name.endswith(".html"):
            continue
        text = re.sub(r"<[^>]+>", " ", str(files[name]))
        for m in PLACEHOLDER.finditer(text):
            before = text[max(0, m.start() - 60):m.start()]              # the sentence the phrase sits in, not a cut word
            cut = max(before.rfind(". "), before.rfind("! "), before.rfind("? "), before.rfind("\n"))
            if cut >= 0:
                before = before[cut + 1:]
            elif m.start() > 60 and " " in before:
                before = before[before.find(" ") + 1:]                  # a window that opened mid-word starts at the next word
            around = re.sub(r"\s+", " ", before + m.group(0)).strip()
            out.append({"page": name, "claim": "the page says '%s'" % around[-90:], "severity": "high", "kind": "hole"})
    return out


def audit_file(ctx, step, item):
    ref = ctx["ref"]
    mech, judged = ctx["bag"]["audit.mechanical"], ctx["bag"]["audit.judge"]
    faults = mech.get("faults") if "faults" in mech else (mech.get("notes") if not mech.get("ok") else [])
    found = [{"page": None, "claim": n, "severity": "high"} for n in faults or []]
    found += list(mech.get("holes") or [])
    found += [f for f in judged.get("findings") or [] if isinstance(f, dict) and f.get("claim")]
    if not found:
        return {"said": "checked what went live; found nothing", "filed": 0}
    high = [f for f in found if str(f.get("severity") or "").lower() == "high"]
    claim = str((high or found)[0]["claim"])
    post(ref, "Audit", "Identity", "inform", {"word": "finding", "claim": claim, "severity": "high" if high else "low",
                                              "findings": found[:12], "about_version": ctx["inp"]["v"]},
         about={"art": "Live site", "v": ctx["inp"]["v"]})
    return {"said": "found %s: %s" % ("something to put right" if high else "something to note", claim), "filed": len(found)}


# ---- the rulings of 2026-09-28: every unit starts and ends with code; Coordination's own agent; Root spawns ---------
def hear(ctx, step, item):
    """A unit that hears a post starts with code: who asked, with what act, in which word. Closed facts."""
    p = ctx.get("post") or {}
    pl = p.get("payload") or {}
    return {"facts": {"from": str(p.get("src") or ""), "act": str(p.get("msg_type") or ""),
                      "word": pl.get("word") if isinstance(pl.get("word"), str) else None}}


def coord_ready(ctx, step, item):
    names = list(ctx.get("ready") or [])
    return {"ready": names, "facts": {"ready": ", ".join(names), "several": len(names) > 1}}


def coord_record(ctx, step, item):
    tie = ctx["bag"].get("coord.tie") or {}
    return {"said": "%s goes first: %s" % (tie.get("answer"), tie.get("why") or "by the table")}


def p_coord_tie(ctx, step, item):
    ready_now = ctx["bag"]["coord.ready"]["ready"]
    what = "; ".join("%s: %s" % (n, (engine_def(n) or {}).get("description") or "") for n in ready_now)
    waiting = "; ".join(a["text"] for a in W.asks(ctx["ref"]) if a["status"] == "pending") or "nothing"
    return ("Several functions of the department are ready at once, and one runs at a time. Say who goes first.\n"
            "READY NOW: %s\nWHAT EACH DOES: %s\nCOORDINATION'S TABLE, THE USUAL ORDER: %s\nWAITING FOR THE OWNER: %s\n\n"
            "Return ONLY a JSON object: {\"answer\": \"one of the ready names\", \"why\": \"one line\"}."
            % (", ".join(ready_now), what, ", ".join(ctx["table"]["functions"]), waiting))


def d_coord_tie(ctx, step, item):
    ready_now = ctx["bag"]["coord.ready"]["ready"]
    first = next((n for n in ctx["table"]["functions"] if n in ready_now), ready_now[0] if ready_now else None)
    return {"answer": first, "why": "by Coordination's table"}


def _tie(ctx, ready_now):
    """Coordination's own unit, when several functions are ready at once: list who is ready (code), say who goes first
    (its agent, until the step hardens to the table), record the pick (code). The name, or None to keep the table's
    order. Each step is a row, so the owner sees Coordination's agent at work."""
    steps = list((engine_def("Coordination") or {}).get("steps") or [])
    if not steps or not ready_now:
        return None
    n = len(board(ctx["ref"]))
    ctx2 = dict(ctx)
    ctx2.update({"slot": "Coordination@tie.%d" % n, "run": None, "inp": {"v": n}, "post": None, "bag": {}, "how": {},
                 "spend": {"calls": 0, "usd": 0.0}, "ready": list(ready_now)})
    for s in steps:
        row, out = run_step(ctx2, s, None)
        if row.get("status") != "ok" or not isinstance(out, dict):
            return None
        ctx2["bag"][s["id"]] = out
    pick = (ctx2["bag"].get("coord.tie") or {}).get("answer")
    return pick if pick in ready_now else None


def library_kinds():
    """The Library's department kinds a Root may set up, each with the use case it fits: name: use case."""
    return {k: str(v.get("use_case") or "") for k, v in W.KINDS.items() if k != "root"}


def kind_for(words):
    """The kind whose use case fits the words, by their plainest cue; default when none does (TPL-1: "if they match the
    use case, then great. Otherwise ... there is a default one")."""
    low = " ".join(str(words or "").lower().split())
    if any(w in low for w in ("website", "web site", "site ", "web page", "webpage", "landing page", "homepage", "home page")) or low.endswith("site"):
        return "website" if "website" in W.KINDS else "default"
    return "default" if "default" in W.KINDS else "website"


def setup_read(ctx, step, item):
    words = W.read_files(ctx["ref"], "Request", ctx["inp"]["v"]).get("request.md", "").strip()
    kinds = library_kinds()
    return {"words": words, "facts": {"asked": bool(words), "kinds": ", ".join(kinds),
                                      "use_cases": "; ".join("%s: %s" % (k, u) for k, u in kinds.items())}}


def p_setup_shape(ctx, step, item):
    got = ctx["bag"]["setup.read"]
    org = (ctx["dept"].get("org") or {}).get("name") or ctx["dept"].get("name")
    return ("The owner of %s asks Root for a department. Shape it: a short name (the organisation's name and what it is, like "
            "\"%s Website\"), its kind from the Library (the kind whose use case fits the words; default when none does), and its "
            "goal in one or two sentences in the owner's own words.\n"
            "THE OWNER'S WORDS: %s\nKINDS IN THE LIBRARY: %s\nEACH KIND'S USE CASE: %s\n\n"
            "Return ONLY a JSON object: {\"name\": str, \"kind\": str, \"goal\": str}."
            % (org, org, got["words"], got["facts"]["kinds"], got["facts"].get("use_cases") or ""))


def d_setup_shape(ctx, step, item):
    got = ctx["bag"]["setup.read"]
    org = (ctx["dept"].get("org") or {}).get("name") or ctx["dept"].get("name")
    kind = kind_for(got["words"])
    return {"name": "%s %s" % (org, "Website" if kind == "website" else "Department"), "kind": kind, "goal": got["words"]}


def setup_make(ctx, step, item):
    """Root makes the department: under itself, with its charter, its functions' templates, its record and its goal."""
    shape = ctx["bag"]["setup.shape"]
    import founding
    return founding.spawn(ctx["ref"], shape["name"], shape["kind"], shape["goal"], owner=ctx["dept"].get("owner") or "the owner")


def setup_file(ctx, step, item):
    made = ctx["bag"]["setup.make"]
    text = "# %s\n\nref: %s\nkind: %s\ngoal: %s\nset up by Root %s\n" % (made["name"], made["ref"], made["kind"], made["goal"],
                                                                         "now" if made.get("created") else "earlier")
    return {"files": {"department.md": text}, "check": {"ok": True, "notes": ["%s is set up and On" % made["name"]]}}


def c_department_is_shaped(ctx, step, item, out):
    ok = (isinstance(out.get("name"), str) and out["name"].strip() and out.get("kind") in W.KINDS and out.get("kind") != "root"
          and isinstance(out.get("goal"), str) and out["goal"].strip())
    return _verdict(ok, "a name, a kind the Library has, and a goal", "no name, a kind the Library lacks, or no goal")


def c_department_is_made(ctx, step, item, out):
    """The child exists under Root, on the runtime, and its goal reached it: the child's own Identity files the goal when
    the child runs, which is its business, not Root's."""
    d = W.dept(out.get("ref")) if isinstance(out, dict) and out.get("ref") else None
    ok = bool(d) and d.get("runtime") == 2 and d.get("parent") == ctx["ref"] and bool(W.requests(out["ref"]))
    return _verdict(ok, "the department exists under Root, on the runtime, and has its goal", "the department was not made under Root")


# ---- an engine from an idea (TPL-1 slice 2, founder 2026-09-29: "the engines are supposed to be created by the five
# functions of the department ... created on the fly, or there is a default one") ---------------------------------------
_STOP = set("what if the a an and or of to for in on with my our we it its this that could would should be is are was do does "
            "have has each every when then also just there here from into as by at one department site".split())


def _content(words):
    return {w for w in re.findall(r"[a-z0-9]+", str(words or "").lower()) if len(w) >= 4 and w not in _STOP}


def engine_for_idea(ref, words, hint=None):
    """Which engine an idea asks for: the Library engine template whose use case shares the most words with the idea
    (two at least) and is not on the record yet, as a pick; else a shape from the idea (its name from the model's hint,
    or the idea's first words), to be born from Do on the stamp; None when the idea holds no words an engine could do."""
    d = W.dept(ref) or {}
    have = set(d.get("engines") or [x[0] for x in W.engines_of(d)])
    hint = hint if isinstance(hint, dict) else {}
    idea = _content(words) | _content(hint.get("does"))
    if not idea:
        return None
    best, score = None, 0
    for name, e in defs()["engines"].items():
        if e.get("kind") != "work" or not e.get("from_template") or name in have or name == "Setup":
            continue
        s = len(idea & _content(e.get("use_case")))
        if s > score:
            best, score = name, s
    if best and score >= 2:
        e = defs()["engines"][best]
        return {"pick": best, "use_case": e.get("use_case"), "does": e.get("description")}
    name = " ".join(str(hint.get("name") or "").split())
    if not name:
        name = " ".join(w.title() for w in [w for w in re.findall(r"[a-z0-9]+", str(words or "").lower()) if w in idea][:2]) or "Helper"
    does = str(hint.get("does") or words or "")
    return {"shape": {"name": name[:40], "use_case": does[:300], "does": does[:200], "instruction": str(words or "")[:2000],
                      "reads": "Brief", "writes": name[:40]}}


def born_template(name, shape, ref):
    """An engine shaped on the fly, born into the Library from Do: the same three steps (read, do, file) under its own
    ids, its use case and instruction from the idea, what it writes filed under the Default artifact template; made_by
    says which department's owner stamped it. Validated with the rest; refused, it leaves no file."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    if not slug:
        raise ValueError("name the engine")
    p = TEMPLATES_DIR / (slug + ".json")
    if p.exists():
        raise ValueError("the Library already has a template at %s" % p.name)
    do = json.loads((TEMPLATES_DIR / "do.json").read_text(encoding="utf-8"))
    t = dict(do)
    does = str(shape.get("does") or shape.get("use_case") or "")
    t.update({"id": "engine/" + slug, "name": name, "version": 1, "use_case": str(shape.get("use_case") or does)[:300],
              "description": does[:200] or ("does what the idea asked: " + name), "instruction": str(shape.get("instruction") or "")[:2000],
              "reads": str(shape.get("reads") or "Brief"), "writes": str(shape.get("writes") or name)[:40],
              "made_by": {"dept": ref, "at": W.now(), "idea": str(shape.get("instruction") or "")[:300]}})
    t["start"] = {"on": [{"kind": "version", "of": t["reads"]}], "unless": list((do.get("start") or {}).get("unless") or [])}
    t["steps"] = [dict(s, id=slug + "." + s["id"].split(".", 1)[1]) for s in do["steps"]]
    if not t["use_case"]:
        raise ValueError("an engine names its use case")
    p.write_text(json.dumps(t, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    _DEFS.clear()
    try:
        defs()
    except ValueError:
        p.unlink()
        _DEFS.clear()
        raise
    return p


def grow_line(ref, name):
    """Coordination's line, on the record, gains the engine; the born copy is written first for a department that had none."""
    t = coordination(ref)
    if name not in (t.get("line") or []):
        t["line"] = list(t.get("line") or []) + [name]
    t.update({"since": W.now(), "by": "stamp"})
    with W._lock(ref):
        W._write(W.ddir(ref) / "coordination.json", t)
    return t


def _note_idea(ref, idea_id, note):
    if not idea_id:
        return
    with W._lock(ref):
        rows = ideas(ref)
        for r in rows:
            if r.get("id") == idea_id:
                r.update(note)
        W._write(W.ddir(ref) / "ideas.json", rows)


def adapt_offer(ctx, step, item):
    """After an idea is parked, Adaptation offers the engine it asks for, if any: to Priority first, which prices it against
    the envelope; Identity puts it to the owner once Priority answers (adapt.priced). Nothing is added without the stamp."""
    ref, pl, got = ctx["ref"], ctx["post"]["payload"], ctx["bag"]["adapt.shape"]
    offer = engine_for_idea(ref, pl.get("words"), got.get("engine"))
    if not offer:
        return {"said": "the idea asks for no engine", "offer": None}
    name = offer.get("pick") or offer["shape"]["name"]
    # a thread of its own, as every proposal of Adaptation's: the idea's thread closed when the idea was parked
    post(ref, "Adaptation", "Priority", "propose", {"word": "engine", "engine": name, "offer": offer, "idea": ctx["bag"]["adapt.park"].get("idea"),
                                                   "for": pl.get("for"), "why": "the idea asks for it"})
    return {"said": "offered an engine to Priority: %s%s" % (name, " (from the Library)" if offer.get("pick") else " (shaped from the idea)"),
            "offer": offer}


def adapt_priced(ctx, step, item):
    """Priority priced the engine: with room, Adaptation proposes it to Identity, who asks the owner; without, the idea
    stays parked, and says so."""
    ref, p = ctx["ref"], ctx["post"]
    mine = [x for x in board(ref) if x["thread"] == p["thread"] and x["src"] == "Adaptation" and x["msg_type"] == "propose"
            and (x.get("payload") or {}).get("word") == "engine"]
    if not mine:
        return {"said": "heard Priority on an engine nobody offered"}
    offer = mine[-1]["payload"]
    if p["msg_type"] != "accept-proposal":
        _note_idea(ref, offer.get("idea"), {"engine": offer.get("engine"), "priced": "refused", "why": (p.get("payload") or {}).get("why")})
        return {"said": "Priority has no room for %s; the idea stays parked" % offer.get("engine")}
    post(ref, "Adaptation", "Identity", "propose", {"word": "engine", "engine": offer.get("engine"), "offer": offer.get("offer"),
                                                   "idea": offer.get("idea"), "for": offer.get("for"), "why": "the idea asks for it; Priority has room"})
    return {"said": "put the engine %s to Identity for the owner" % offer.get("engine")}


def identity_engine(ctx, step, item):
    """The engine Adaptation proposed, put to the owner as an ask in the owner's words: what it would do, and what a stamp does."""
    ref, p = ctx["ref"], ctx["post"]
    pl = p["payload"]
    offer, name = pl.get("offer") or {}, str(pl.get("engine") or "")
    does = str(offer.get("does") or (offer.get("shape") or {}).get("does") or offer.get("use_case") or "").strip().rstrip(".")
    text = "Add the engine %s to %s?%s Stamp to add it, Refuse to leave the idea parked." % (
        name, ctx["dept"].get("name"), (" What it does: " + does[:1].lower() + does[1:] + ".") if does else "")
    W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "engine", "engine": name, "offer": offer, "idea": pl.get("idea"),
                     "text": text, "status": "pending", "created": W.now(), "thread": p["thread"]})
    post(ref, "Identity", OWNER, "request", {"word": "engine", "objective": text, "output": "a stamp or a refusal", "may_read": [],
                                             "boundaries": "this one engine"}, thread=p["thread"])
    return {"said": "put an engine to the owner: " + name}


# ---- Do: the default line, one answer filed (TPL-1, founder 2026-09-29: "otherwise ... there is a default one"); an engine
# born from an idea runs these same three steps under its own ids, with its instruction ------------------------------------
def _pre(step):
    return str(step["id"]).rsplit(".", 1)[0]


def do_read(ctx, step, item):
    art = ctx["def"].get("reads") or "Brief"
    files = W.read_files(ctx["ref"], art, ctx["inp"]["v"])
    return {"brief": files.get("brief.md") or "\n".join(str(v) for v in files.values())}


def p_do_make(ctx, step, item):
    ins = str(ctx["def"].get("instruction") or "").strip()
    return ("The department \"%s\" was asked for this, in its owner's words (the Brief):\n%s\n\n%sDo it as one written answer: what was "
            "asked for, done as far as words can do it, in the owner's own language, nothing invented; where a fact is missing, say "
            "so. Return ONLY a JSON object: {\"text\": str}."
            % (ctx["dept"].get("name"), ctx["bag"][_pre(step) + ".read"]["brief"][:6000],
               ("THIS ENGINE'S INSTRUCTION, FROM THE OWNER'S IDEA: %s\n\n" % ins) if ins else ""))


def d_do_make(ctx, step, item):
    brief = " ".join(str(ctx["bag"][_pre(step) + ".read"]["brief"]).split())
    return {"text": "Noted, to be done by hand: " + brief[:600]}


def do_file(ctx, step, item):
    text = str(ctx["bag"][_pre(step) + ".make"].get("text") or "").strip()
    return {"files": {"result.md": text + "\n"}, "check": {"ok": len(text) >= 3, "notes": ["%d characters" % len(text)]}}


def c_result_is_text(ctx, step, item, out):
    ok = isinstance(out, dict) and isinstance(out.get("text"), str) and len(out["text"].strip()) >= 3
    return _verdict(ok, "an answer in words", "no answer")


CODE = {"plan_read": plan_read, "plan_fit": plan_fit, "plan_file": plan_file, "write_list": write_list, "write_file": write_file,
        "do_read": do_read, "do_file": do_file, "adapt_offer": adapt_offer, "adapt_priced": adapt_priced, "identity_engine": identity_engine,
        "check_rules_of": check_rules_of,
        "hear": hear, "coord_ready": coord_ready, "coord_record": coord_record,
        "setup_read": setup_read, "setup_make": setup_make, "setup_file": setup_file,
        "check_build": check_build, "publish_copy": publish_copy, "identity_gate": identity_gate,
        "priority_envelope": priority_envelope, "coord_chain": coord_chain, "coord_heard": coord_heard,
        "coord_busy": coord_busy, "coord_pick": coord_pick, "coord_edge": coord_edge, "coord_verdict": coord_verdict,
        "coord_bounds": coord_bounds, "coord_alarm": coord_alarm,
        "identity_read": identity_read, "identity_route": identity_route, "identity_hand": identity_hand, "identity_lost": identity_lost,
        "identity_file": identity_file, "identity_verdict": identity_verdict, "identity_rung": identity_rung,
        "identity_apply": identity_apply, "identity_drop": identity_drop, "identity_finding": identity_finding,
        "identity_alarm": identity_alarm, "identity_idea": identity_idea, "adapt_park": adapt_park,
        "priority_read": priority_read, "priority_post": priority_post,
        "adapt_sense": adapt_sense, "adapt_ladder": adapt_ladder, "adapt_act": adapt_act, "adapt_trial": adapt_trial,
        "adapt_notrial": adapt_notrial, "adapt_heard": adapt_heard, "audit_pick": audit_pick,
        "audit_mechanical": audit_mechanical, "audit_file": audit_file}


# ---- the registry: prompts and drafts ------------------------------------------------------------------------------
#: What the first walk on the runtime found (2026-09-28): Audit caught the writer stating hours nobody gave, twice. The
#: rule is said once, to the planner and to the writer, and the writer reads the brief itself, corrections included.
NOTHING_INVENTED = ("State no fact nobody gave you: no phone number, address, opening hours, date, price, count, name, award "
                    "or claim of history, and no promise of what is offered or when. Where a reader needs such a fact and "
                    "none was given, say in plain words that it is to be confirmed, or leave it out. A line in the brief "
                    "that begins 'Correct this' names something that must no longer be said anywhere on the site. ")


def p_plan_pages(ctx, step, item):
    return ("Read the brief and every ask in it, and plan the site. Return ONLY a JSON object, no prose: {\"site_name\": str, "
            "\"tagline\": str, \"palette\": {\"primary\": \"#hex\", \"accent\": \"#hex\"}, \"pages\": [{\"slug\": \"lowercase-hyphen\", "
            "\"title\": str, \"purpose\": str, \"sections\": [str]}]}. The first page's slug is index. Include every page "
            "the brief or an ask names. Six to ten pages. " + NOTHING_INVENTED +
            "\n\nBRIEF:\n" + ctx["bag"]["plan.read"]["brief"])


def d_plan_pages(ctx, step, item):
    return W._fallback_plan(ctx["dept"]["name"], ctx["bag"]["plan.read"]["brief"])


def _page_of(ctx, item):
    plan = ctx["bag"]["write.list"]["plan"]
    return plan, next(p for p in plan["pages"] if p["slug"] == item)


def p_write_page(ctx, step, item):
    plan, page = _page_of(ctx, item)
    site = {"site_name": plan.get("site_name"), "tagline": plan.get("tagline"),
            "pages": [{"slug": p["slug"], "title": p.get("title")} for p in plan["pages"]]}
    rules = _owner_rules(ctx["dept"])
    return ("Write the body of ONE page of this site. Return ONLY a JSON object, no prose: {\"title\": str, \"body_html\": str}. "
            "body_html is the inside of <main> only: semantic HTML (section, h1, h2, p, ul, a), no <html>, <head>, <script> or "
            "<style>, no external images or links. Link to other pages as '<slug>.html' and only to slugs of this site. "
            + NOTHING_INVENTED +
            (("\n\nTHE OWNER'S RULES, EACH ONE MET HERE:\n- " + "\n- ".join(rules)) if rules else "") +
            "\n\nTHE BRIEF, AND WHAT WAS ASKED SINCE:\n" + _brief_text(ctx["ref"]) +
            "\n\nTHE SITE:\n" + json.dumps(site) + "\n\nTHIS PAGE:\n" + json.dumps(page))


def d_write_page(ctx, step, item):
    plan, page = _page_of(ctx, item)
    return {"title": page.get("title") or item, "body_html": W._fallback_body(page, plan)}


def p_check_rules(ctx, step, item):
    got = ctx["bag"]["check.rules_of"]
    return ("Hold every page of this site to the owner's rules. A rule about every page is broken on each page that does not meet it; "
            "read the page's text as a visitor would.\nTHE RULES:\n- " + "\n- ".join(got["rules"]) +
            "\n\nTHE PAGES (slug, title, text):\n" + json.dumps(got["pages"]) +
            "\n\nReturn ONLY a JSON object, no prose: {\"broken\": [{\"rule\": str, \"pages\": [slug], \"why\": \"one line\"}]}; "
            "a rule every page meets is not listed; broken is [] when every rule holds.")


EVERY_PAGE = re.compile(r"\bevery page\b.*?(?:end(?:s)? with|carr(?:y|ies)|show(?:s)?|include(?:s)?|ha(?:s|ve)|say(?:s)?|name(?:s)?)\s*:?\s*(.+?)\.?\s*$", re.I)


def d_check_rules(ctx, step, item):
    """Code's own reading of a rule about every page: the words after the colon must be on each page. The draft when
    the model is away, and the floor under its answer."""
    got = ctx["bag"]["check.rules_of"]
    broken = []
    for rule in got["rules"]:
        m = EVERY_PAGE.search(rule)
        if not m:
            continue
        want = m.group(1).strip().strip("'\"").lower()
        bad = [p["slug"] for p in got["pages"] if want and want not in p["text"].lower()]
        if bad:
            broken.append({"rule": rule, "pages": bad, "why": "the page does not carry '%s'" % want})
    return {"broken": broken}


def p_identity_take(ctx, step, item):
    d, got = ctx["dept"], ctx["bag"]["identity.read"]
    return ("Judge one request from the owner.\nTHE GOAL: %s\nTHE RULES: %s\nTHE REQUEST: %s\nREAD BY CODE: %s\n\n"
            "Return ONLY a JSON object, no prose: {\"verdict\": \"go\" | \"ask\" | \"refuse\", \"why\": \"one line\"}. "
            "go: it is inside the goal and stays inside the site. ask: it would reach outside the site, or the goal does not "
            "cover it. refuse: it breaks a rule."
            % (d.get("goal"), "; ".join(r["line"] for r in d.get("rules") or []), got["words"], json.dumps(got["facts"])))


def d_identity_take(ctx, step, item):
    f = ctx["bag"]["identity.read"]["facts"]
    return {"verdict": "ask" if f["leaves_site"] else "go", "why": "it reaches outside the site" if f["leaves_site"] else "inside the goal"}


def p_identity_gate(ctx, step, item):
    pl = (ctx.get("post") or {}).get("payload") or {}
    return ("An engine asks whether it may start.\nTHE RULES: %s\nTHE ENGINE: %s\n\nReturn ONLY a JSON object: "
            "{\"verdict\": \"admit\" | \"wait\" | \"refuse\", \"why\": \"one line\"}."
            % ("; ".join(r["line"] for r in ctx["dept"].get("rules") or []), pl.get("engine")))


def d_identity_gate(ctx, step, item):
    return {"verdict": "admit", "why": "the rules allow it"}


def p_priority_bargain(ctx, step, item):
    got, pl = ctx["bag"]["priority.read"], ctx["post"]["payload"]
    return ("Adaptation proposes something that costs.\nTHE PROPOSAL: %s, for the step %s\nWHAT IT COSTS: %s\n"
            "ROOM IN THE ENVELOPE TODAY: %s\n\nReturn ONLY a JSON object: {\"answer\": \"accept\" | \"reject\", \"why\": \"one line\"}."
            % (pl.get("word"), pl.get("step"), pl.get("cost"), "yes" if got["facts"]["room"] else "no"))


def d_priority_bargain(ctx, step, item):
    room = ctx["bag"]["priority.read"]["facts"]["room"]
    return {"answer": "accept" if room else "reject", "why": "the envelope has room" if room else "the envelope has no room today"}


def p_audit_judge(ctx, step, item):
    ref, v = ctx["ref"], ctx["inp"]["v"]
    files = W.read_files(ref, "Live site", v)
    pages = []
    for name in ctx["bag"]["audit.pick"]["pages"][:12]:
        text = re.sub(r"<[^>]+>", " ", files.get(name, ""))
        pages.append({"page": name, "text": " ".join(text.split())[:1500]})
    return ("Check what the department made against what it was asked. Read the brief, then the pages. Find any statement of fact "
            "on a page that the brief does not give: a phone number, an address, a date, a count, a name, a claim of history. "
            "Return ONLY a JSON object: {\"ok\": bool, \"findings\": [{\"page\": str, \"claim\": str, \"severity\": \"high\" | "
            "\"low\"}]}. high: a reader could be harmed or misled by it. At most eight findings.\n\n"
            "THE BRIEF:\n%s\n\nTHE PAGES:\n%s" % (_brief_text(ref), json.dumps(pages)))


def d_audit_judge(ctx, step, item):
    return {"ok": True, "findings": []}


def _words(ctx):
    return ctx["bag"]["identity.read"]["words"]


def p_identity_recognise(ctx, step, item):
    got = ctx["bag"]["identity.read"]
    return ("Recognise what kind of words the owner has given. There are five kinds, and only five:\n"
            "task: \"do X for me\". query: \"tell me Y\". directive: \"from now on, do Z\", a standing change to how the "
            "department works or to its goal. feedback: \"that was wrong\", about work already made. new-idea: \"I want a new "
            "capability\", something the department cannot do today.\n"
            "THE GOAL: %s\nTHE WORDS: %s\nREAD BY CODE: %s\n\n"
            "Return ONLY a JSON object: {\"journey\": \"task\" | \"query\" | \"directive\" | \"feedback\" | \"new-idea\", "
            "\"why\": \"one line\"}." % (ctx["dept"].get("goal"), got["words"], json.dumps(got["facts"])))


def d_identity_recognise(ctx, step, item):
    return {"journey": ctx["bag"]["identity.read"]["facts"]["cue"], "why": "read from the words' own cues"}


def _record_lines(ref):
    live = W.latest(ref, "Live site")
    out = ["pages in the plan: " + ", ".join(str(p.get("title")) for p in _pages(ref)) if _pages(ref) else "no plan yet",
           "the site is live, at its version %d" % live["v"] if live else "the site is not live yet"]
    out += ["%s has %d versions" % (a, len(W.versions(ref, a))) for a in W.artifacts_of(W.dept(ref))]
    out += ["waiting for the owner: " + a["text"] for a in W.asks(ref) if a["status"] == "pending"]
    return out


def p_identity_answer(ctx, step, item):
    return ("Answer the owner's question from the record below, and from nothing else. If the record does not hold the answer, say "
            "so.\nTHE QUESTION: %s\nTHE RECORD:\n- %s\n\nReturn ONLY a JSON object: {\"answer\": str, \"source\": \"which line "
            "of the record\", \"confidence\": \"high\" | \"moderate\" | \"low\" | \"unknown\"}."
            % (_words(ctx), "\n- ".join(_record_lines(ctx["ref"]))))


def d_identity_answer(ctx, step, item):
    lines = _record_lines(ctx["ref"])
    return {"answer": "; ".join(lines[:2]), "source": "the department's record", "confidence": "moderate"}


def p_identity_rule(ctx, step, item):
    d = ctx["dept"]
    return ("The owner has given a directive. Restate it as one rule, in one line, in plain words.\nTHE GOAL: %s\n"
            "THE RULES TODAY: %s\nTHE DIRECTIVE: %s\n\nReturn ONLY a JSON object: {\"tag\": \"always\" | \"ask\" | \"refuse\" | "
            "\"goal\", \"line\": str, \"scope\": \"standing\" | \"one-time\"}. tag goal: the directive changes what the "
            "department is for. scope one-time: the owner means this once."
            % (d.get("goal"), "; ".join(r["line"] for r in d.get("rules") or []), _words(ctx)))


def d_identity_rule(ctx, step, item):
    words = _words(ctx)
    once = bool(re.search(r"\b(just this once|this time only|only this time|for now)\b", words, re.I))
    goal = bool(re.search(r"\b(the (?:site|department|website) is (?:now )?for|the goal is)\b", words, re.I))
    line = re.sub(r"^\s*(from now on|going forward|in future|just this once)[,:]?\s*", "", words, flags=re.I).strip()
    tag = "goal" if goal else "refuse" if re.search(r"\bnever\b", line, re.I) else "always"
    return {"tag": tag, "line": line[:1].upper() + line[1:], "scope": "one-time" if once else "standing"}


def p_identity_weigh(ctx, step, item):
    got = ctx["bag"]["identity.read"]
    return ("The owner has given feedback on work the department made. Read what it changes.\nTHE PAGES: %s\nTHE FEEDBACK: %s\n\n"
            "Return ONLY a JSON object: {\"about\": \"the page's slug, or null\", \"what\": \"format\" | \"content\" | "
            "\"tone\" | \"scope\" | \"accuracy\", \"now\": \"the correction to make now, one line\", \"future\": \"a rule to "
            "carry forward to work like this, one line, or null\"}."
            % (json.dumps([{"slug": p["slug"], "title": p.get("title")} for p in _pages(ctx["ref"])]), got["words"]))


def d_identity_weigh(ctx, step, item):
    words = _words(ctx)
    what = "format" if re.search(r"\btoo (long|short)\b", words, re.I) else "accuracy" if re.search(r"\b(wrong|incorrect|mistake)\b", words, re.I) \
        else "content"
    return {"about": ctx["bag"]["identity.read"].get("about"), "what": what, "now": words, "future": None}


def p_adapt_shape(ctx, step, item):
    pl = ctx["post"]["payload"]
    return ("The owner floats an idea the department cannot do today. Do not plan a build. Reflect the idea back in sharper words, "
            "name the question underneath it, and give two or three shapes it could take, smallest first. If the idea is something "
            "the department could do each time on its own, name that engine: one or two words, and what it does in one line; else null."
            "\nTHE GOAL: %s\nTHE IDEA: %s\n\nReturn ONLY a JSON object: {\"reflected\": str, \"question\": str, \"shapes\": [str, str, str], "
            "\"engine\": {\"name\": str, \"does\": str} or null}."
            % (ctx["dept"].get("goal"), pl.get("words")))


def d_adapt_shape(ctx, step, item):
    words = str(ctx["post"]["payload"].get("words") or "")
    return {"reflected": words, "question": "What would this let a visitor do that they cannot do today?",
            "shapes": ["a page that says it", "a link to where it is already done", "an engine that does it"], "engine": None}


PROMPT = {"identity_recognise": p_identity_recognise, "identity_answer": p_identity_answer, "identity_rule": p_identity_rule,
          "identity_weigh": p_identity_weigh, "adapt_shape": p_adapt_shape, "plan_pages": p_plan_pages, "write_page": p_write_page, "identity_take": p_identity_take,
          "identity_gate_soft": p_identity_gate, "priority_bargain": p_priority_bargain, "audit_judge": p_audit_judge,
          "coord_tie": p_coord_tie, "setup_shape": p_setup_shape, "check_rules": p_check_rules, "do_make": p_do_make}
DRAFT = {"identity_recognise_draft": d_identity_recognise, "identity_answer_draft": d_identity_answer,
         "coord_tie_draft": d_coord_tie, "setup_shape_draft": d_setup_shape, "check_rules_draft": d_check_rules,
         "identity_rule_draft": d_identity_rule, "identity_weigh_draft": d_identity_weigh, "adapt_shape_draft": d_adapt_shape,
         "plan_pages_draft": d_plan_pages, "write_page_draft": d_write_page, "identity_take_draft": d_identity_take,
         "identity_gate_draft": d_identity_gate, "priority_bargain_draft": d_priority_bargain, "audit_judge_draft": d_audit_judge,
         "do_make_draft": d_do_make}


# ---- the registry: checks. Every step names one; each is code, and each says what it looked at. ---------------------
def _verdict(ok, yes, no):
    return {"ok": bool(ok), "notes": [yes if ok else no]}


def c_brief_is_text(ctx, step, item, out):
    return _verdict(len(str(out.get("brief") or "").strip()) > 0, "the brief has words", "the brief is empty")


def c_plan_has_pages(ctx, step, item, out):
    n = len([p for p in out.get("pages") or [] if isinstance(p, dict)])
    return _verdict(n >= 1, "%d pages proposed" % n, "no page was proposed")


def c_plan_is_fit(ctx, step, item, out):
    slugs = [p.get("slug") for p in out.get("pages") or []]
    notes = []
    if not slugs or slugs[0] != "index":
        notes.append("the first page is not the home page")
    if len(set(slugs)) != len(slugs):
        notes.append("two pages share an address")
    if any(not s or not re.fullmatch(r"[a-z0-9-]+", str(s)) for s in slugs):
        notes.append("a page's address is not plain lowercase")
    return {"ok": not notes, "notes": notes or ["the home page is first; every address is its own"]}


def c_filed_has_files(ctx, step, item, out):
    ok = isinstance(out.get("files"), dict) and bool(out["files"]) and isinstance(out.get("check"), dict) and "ok" in out["check"]
    return _verdict(ok, "files and their verdict are both there", "the step filed no files, or no verdict")


def c_list_has_pages(ctx, step, item, out):
    n = len(out.get("pages") or [])
    return _verdict(n >= 1 and isinstance(out.get("plan"), dict), "%d pages to write" % n, "the plan names no page")


def c_rules_are_listed(ctx, step, item, out):
    ok = isinstance(out.get("rules"), list) and isinstance(out.get("pages"), list)
    return _verdict(ok, "%d rules of the owner's, %d pages" % (len(out.get("rules") or []), len(out.get("pages") or [])),
                    "no list of rules and pages")


def c_broken_is_listed(ctx, step, item, out):
    broken = out.get("broken")
    ok = isinstance(broken, list) and all(isinstance(b, dict) and b.get("rule") and isinstance(b.get("pages"), list) for b in broken)
    return _verdict(ok, "every rule holds" if ok and not broken else "%d rules broken, each with its pages" % len(broken or []),
                    "no verdict on the rules, or a broken rule without its pages")


def c_page_has_body(ctx, step, item, out):
    body = str(out.get("body_html") or "")
    notes = []
    if len(re.sub(r"<[^>]+>", "", body).strip()) < 40:
        notes.append("almost no text")
    if re.search(r"<\s*script", body, re.I):
        notes.append("carries a script")
    if not str(out.get("title") or "").strip():
        notes.append("has no title")
    return {"ok": not notes, "notes": notes or ["has a title and a body; carries no script"]}


def c_verdict_is_known(ctx, step, item, out):
    return _verdict(out.get("verdict") in ("go", "ask", "refuse"), "the verdict is one of go, ask, refuse",
                    "not a verdict: %r" % (out.get("verdict"),))


def c_gate_verdict_is_known(ctx, step, item, out):
    return _verdict(out.get("verdict") in ("admit", "wait", "refuse"), "the verdict is one of admit, wait, refuse",
                    "not a verdict: %r" % (out.get("verdict"),))


def c_gate_answer_is_known(ctx, step, item, out):
    return _verdict(out.get("answer") in ("admit", "wait", "refuse"), out.get("why") or "the gate let it through",
                    "not a gate's answer: %r" % (out.get("answer"),))


def c_names_who_goes_first(ctx, step, item, out):
    return _verdict(out.get("answer") in defs()["engines"], "it names an engine of this department",
                    "it names no engine: %r" % (out.get("answer"),))


def c_answer_is_known(ctx, step, item, out):
    return _verdict(out.get("answer") in ("accept", "reject"), "the answer is accept or reject", "not an answer: %r" % (out.get("answer"),))


def c_facts_are_closed(ctx, step, item, out):
    f = out.get("facts")
    ok = isinstance(f, dict) and bool(f) and all(isinstance(v, (str, bool)) or v is None for v in f.values())
    if ok and "kind" in f:
        ok = f["kind"] in KINDS
    return _verdict(ok, "every fact is one of a closed set", "a fact is open, or missing")


def c_said_what_it_did(ctx, step, item, out):
    return _verdict(len(str(out.get("said") or "").strip()) > 0, "it says what it did", "it did not say what it did")


def c_counted_the_rows(ctx, step, item, out):
    s = out.get("steps")
    ok = isinstance(s, dict) and all(isinstance(v, dict) and "runs" in v and "differing" in v for v in s.values())
    return _verdict(ok, "%d steps counted" % len(s or {}), "a step has no count")


def c_moves_are_known(ctx, step, item, out):
    m = out.get("moves")
    ok = isinstance(m, list) and all(x.get("kind") in ("down", "trial", "propose", "end-trial") and x.get("step") for x in m)
    return _verdict(ok, "%d moves, each of a known kind" % len(m or []), "a move of no known kind")


def c_picked_a_sample(ctx, step, item, out):
    ok = isinstance(out.get("sample"), bool) and isinstance(out.get("pages"), list)
    return _verdict(ok, "it says whether it sampled, and which pages", "it does not say whether it sampled")


def c_has_a_verdict(ctx, step, item, out):
    ok = isinstance(out.get("ok"), bool) and isinstance(out.get("notes"), list) and bool(out["notes"])
    return _verdict(ok, "; ".join(str(n) for n in out.get("notes") or []), "it gave no verdict")


def c_findings_are_rows(ctx, step, item, out):
    f = out.get("findings")
    ok = isinstance(f, list) and all(isinstance(x, dict) and x.get("claim") for x in f)
    return _verdict(ok, "%d findings, each with its claim" % len(f or []), "a finding with no claim")


def c_journey_is_known(ctx, step, item, out):
    return _verdict(out.get("journey") in JOURNEYS, "the words are one of canon's five journeys: %s" % out.get("journey"),
                    "not a journey: %r" % (out.get("journey"),))


def c_answer_names_its_source(ctx, step, item, out):
    notes = []
    if not str(out.get("answer") or "").strip():
        notes.append("no answer")
    if not str(out.get("source") or "").strip():
        notes.append("the answer names no source")
    if out.get("confidence") not in ("high", "moderate", "low", "unknown"):
        notes.append("the answer does not say how sure it is")
    return {"ok": not notes, "notes": notes or ["an answer, its source, and how sure it is"]}


def c_rule_is_tagged(ctx, step, item, out):
    notes = []
    if out.get("tag") not in ("always", "ask", "refuse", "goal"):
        notes.append("the rule's tag is not one of always, ask, refuse, goal")
    if out.get("scope") not in ("standing", "one-time"):
        notes.append("the rule does not say whether it stands or is for this once")
    if not 3 < len(str(out.get("line") or "").strip()) <= 240 or "\n" in str(out.get("line") or ""):
        notes.append("the rule is not one line")
    return {"ok": not notes, "notes": notes or ["one line, tagged, with its scope"]}


def c_feedback_says_what_changes(ctx, step, item, out):
    notes = []
    if out.get("what") not in ("format", "content", "tone", "scope", "accuracy"):
        notes.append("it does not say what kind of change this is")
    if not str(out.get("now") or "").strip():
        notes.append("it names no correction to make now")
    if out.get("about") and ctx is not None and out["about"] not in {p["slug"] for p in _pages(ctx["ref"])}:
        notes.append("it names a page the site does not have: %s" % out["about"])
    return {"ok": not notes, "notes": notes or ["what changes now, and what kind of change it is"]}


def c_idea_has_shapes(ctx, step, item, out):
    shapes = [x for x in out.get("shapes") or [] if str(x).strip()]
    ok = bool(str(out.get("reflected") or "").strip()) and 2 <= len(shapes) <= 3
    return _verdict(ok, "reflected back, in %d shapes" % len(shapes), "the idea was not reflected back in two or three shapes")


CHECK = {"journey_is_known": c_journey_is_known, "answer_names_its_source": c_answer_names_its_source, "result_is_text": c_result_is_text,
         "rule_is_tagged": c_rule_is_tagged, "feedback_says_what_changes": c_feedback_says_what_changes,
         "idea_has_shapes": c_idea_has_shapes, "brief_is_text": c_brief_is_text, "plan_has_pages": c_plan_has_pages, "plan_is_fit": c_plan_is_fit,
         "filed_has_files": c_filed_has_files, "list_has_pages": c_list_has_pages, "page_has_body": c_page_has_body,
         "rules_are_listed": c_rules_are_listed, "broken_is_listed": c_broken_is_listed,
         "verdict_is_known": c_verdict_is_known, "gate_verdict_is_known": c_gate_verdict_is_known,
         "gate_answer_is_known": c_gate_answer_is_known, "answer_is_known": c_answer_is_known,
         "names_who_goes_first": c_names_who_goes_first,
         "facts_are_closed": c_facts_are_closed, "said_what_it_did": c_said_what_it_did, "counted_the_rows": c_counted_the_rows,
         "moves_are_known": c_moves_are_known, "picked_a_sample": c_picked_a_sample, "has_a_verdict": c_has_a_verdict,
         "findings_are_rows": c_findings_are_rows,
         "department_is_shaped": c_department_is_shaped, "department_is_made": c_department_is_made}


# ---- what the screens read -----------------------------------------------------------------------------------------
def steps_view(ref, name):
    """An engine as the owner sees it: its steps in order, each with the rung it runs on, its check and what its rows say."""
    e = engine_def(name)
    if not e:
        return None
    rows = step_rows(ref)
    L = ladder(ref)
    gates = {g["id"] for g in e.get("gates") or []}
    rules = {s["id"] for s in e.get("rules") or []}
    under = {s["id"]: h["name"] for h in e.get("on") or [] for s in h["steps"]}
    under.update({sid: SHARED for sid in rules})
    out = []
    for s in all_steps(name):
        en = L.get(s["id"]) or entry(ref, s, name)
        mine = [r for r in rows if r.get("step") == s["id"]]
        last = mine[-1] if mine else None
        decides = s["id"] in gates or s["id"] in rules          # a decision on the way to a start, not a run of work
        out.append({"id": s["id"], "name": s["name"], "nature": s["nature"],
                    "mode": "gate" if s["id"] in gates else "rule" if s["id"] in rules else "slot",
                    "under": under.get(s["id"]),
                    "rung": en["rung"], "rung_name": RUNG_NAME[en["rung"]], "form": en.get("form"), "born": s["born"],
                    "ceiling": s.get("ceiling") or ("C2" if s.get("prompt") else s["born"]), "soft": bool(s.get("prompt")),
                    "held": bool(en.get("held")), "pending": en.get("pending"), "trial": en.get("trial"),
                    "each": bool(s.get("each")), "side_by_side": int(s.get("side_by_side") or 1), "check": s["check"],
                    "ran": bool(mine),
                    "last": last and {"at": last.get("ended") or last.get("started"), "status": last.get("status"),
                                      "rung": last.get("rung"), "miss": bool(last.get("miss")), "by": last.get("by"),
                                      "item": last.get("item"), "ok": (last.get("check") or {}).get("ok"),
                                      "notes": (last.get("check") or {}).get("notes")},
                    "evidence": (_decided(mine) if decides else evidence(ref, s["id"], rows=rows, since=en.get("since_row")))
                    if mine else None,
                    "history": en.get("history") or []})
    view = {"name": name, "kind": e["kind"], "description": e.get("description"), "skills": e.get("skills") or [],
            "reads": e.get("reads"), "writes": e.get("writes"), "steps": out,
            "hears": ([SHARED] if rules else []) + [h["name"] for h in e.get("on") or []],
            "start": start_view(e), "numbers": numbers(ref, name)}
    if name == "Coordination":
        t = coordination(ref)
        view["table"] = {"first": [FIRST[k] for k in t["order"]], "line": list(t["line"]),
                         "may_post": [{"from": src, "act": act, "to": list(dst)} for src, acts in sorted(t["edges"].items())
                                      for act, dst in sorted(acts.items())]}
    if name == "Priority":
        # the limits, engine by engine: born from Priority's template, set by the owner on this card
        d = W.dept(ref) or {}
        envs = d.get("envelopes") or {}
        view["limits"] = []
        for n in [x[0] for x in W.engines_of(d)] + list(W.SYSTEMS):
            env = envs.get(n) or W.ENVELOPE
            calls, usd = W._today_spend(ref, n)
            view["limits"].append({"engine": n, "calls": int(env.get("calls", 0)), "usd": float(env.get("usd", 0.0)),
                                   "used_calls": calls, "used_usd": round(usd, 3)})
    return view


SHARED = "What engines share"
#: Words the screen shows. The users' word for the five is function; "internal system" is the word inside and is
#: never put in anything a screen reads (founder, 2026-09-28).
FIRST = {"posts": "A post waiting for its reader", "line": "The line, in its order", "functions": "A function woken by new work"}


def start_view(e):
    """An engine's start, in words: what makes it run, and what holds it."""
    on = []
    for t in (e.get("start") or {}).get("on") or []:
        if t["kind"] == "version":
            on.append("a new %s%s" % (t["of"], " that passed its check" if t.get("checked") else ""))
        elif t["kind"] == "post":
            on.append("a post addressed to it")
        else:
            on.append("the clock, in every period it names")
    unless = [(step_def(g)[0], (step_def(g)[1] or {}).get("name")) for g in (e.get("start") or {}).get("unless") or []]
    return {"on": on, "unless": [{"by": fn, "name": nm} for fn, nm in unless]}


def _decided(mine):
    """What the rows of a gate or a rule say: how many decisions, and how many passed their check."""
    ok = sum(1 for r in mine if (r.get("check") or {}).get("ok"))
    return {"runs": len(mine), "differing": 0, "shape_drift": 0, "pass": round(ok / len(mine), 3), "marked": 0, "misses": 0, "usd": 0.0}


def _line(p):
    """What a post said, in words. A post that carries only an id or a topic said nothing more than its act, and the
    screen shows the act: an id or a bare topic word is never printed as if it were speech."""
    pl = p.get("payload") or {}
    for k in ("words", "objective", "claim", "done", "reflected", "line", "what", "why", "cost", "answer"):
        if pl.get(k):
            # the person's own words are shown whole; a function's line is cut short (found live 2026-09-28: a
            # four-sentence request lost its last sentence on the screen)
            return str(pl[k]) if k in ("words", "done", "answer") else str(pl[k])[:220]
    if pl.get("step") and pl.get("to"):
        name = (step_def(str(pl["step"]))[1] or {}).get("name")
        if name:
            return "%s, to %s" % (name, RUNG_NAME.get(str(pl["to"]), str(pl["to"])))
    return ""


def board_view(ref):
    """The department's one board, newest thread first, every post in it."""
    posts = board(ref)
    out = []
    for th in reversed(threads(ref)):
        mine = [p for p in posts if p["thread"] == th["id"]]
        out.append({"id": th["id"], "topic": th["topic"], "protocol": th["protocol"], "state": th["state"], "decider": th["decider"],
                    "opened": th["opened"], "closed": th.get("closed"), "outcome": th.get("outcome"), "bounds": th["bounds"],
                    "hops": th["hops"], "default": th["default"],
                    "posts": [{"n": p["n"], "src": p["src"], "dst": p["dst"], "msg_type": p["msg_type"], "at": p["at"],
                               "word": (p.get("payload") or {}).get("word"), "line": _line(p)} for p in mine]})
    return {"threads": out[:60], "any": bool(posts)}
