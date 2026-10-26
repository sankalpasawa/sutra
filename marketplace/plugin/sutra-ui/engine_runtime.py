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
import math
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import layers                      # each layer's bodies and words, behind the interface (PRD A1): _resolve asks its registry
import layers.prompts              # the typed prompt compiler, and the .md reader it falls back on (PRD A1.16)
import layer_schema                # the interface of Root and the five layers (PRD A1)
import owner_words                 # the bargain in the owner's words (PRD M1.7), for Identity's plain-words check (M3.6)
import record                      # the platform product: rows, deployed into the department's own folder
import website_dept as W

RUNGS = ("P", "C0", "C1", "C2")
RUNG_NAME = {"P": "Person", "C0": "Improvised call", "C1": "Checklist", "C2": "Code"}
# a gate's verdict as a function's chat and the board say it: the words of its journey row (functions_view), never the
# verdict's own admit, wait or refuse (PRD M1.7; the owner's ruling on the screen's words)
GATE_SAYS = {"admit": "let through", "wait": "waiting", "refuse": "stopped"}
NATURES = ("transform", "check", "decide", "make")
BELOW = {"C2": "C1", "C1": "C0", "C0": "P"}
ABOVE = {"P": "C0", "C0": "C1", "C1": "C2"}
ACTS = ("request", "agree", "refuse", "propose", "accept-proposal", "reject-proposal", "inform", "failure",
        "not-understood", "cancel")
# each act as the screen says it (PRD M1.7; the owner's ruling: said yes and said no, never accept, refuse or reject):
# what a post does, in a word, as the board and the chat turns print it (22-website.js WB_ACTS says the same words), and
# what a sender may do, as Coordination's who-may-post check says it on its card ('Identity may say no to the owner')
ACT_SAYS = {"request": ("asks", "ask %s"), "agree": ("agrees", "agree with %s"), "refuse": ("says no", "say no to %s"),
            "propose": ("proposes", "propose to %s"), "accept-proposal": ("says yes", "say yes to %s"),
            "reject-proposal": ("says no", "say no to %s"), "inform": ("tells", "tell %s"),
            "failure": ("could not", "tell %s it could not"), "not-understood": ("did not follow", "tell %s it did not follow"),
            "cancel": ("lets go", "let %s go")}
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
    """A definition is data, and data can be wrong. Every fault is named; one fault refuses the whole definition. A
    name is provided by engine_runtime's own registries or by a layer's module (PRD A1.19), and the definitions are held
    to the interface: their edges are the interface's, every handler of a function is a row of what its layer hears,
    and every check a function's step names is one of its layer's or a shared one."""
    faults = []
    seen = {}
    S = layer_schema
    have = {k: layers.names(k) for k in layers.KINDS}
    faults += edge_faults(d.get("edges"))
    for name, e in (d.get("engines") or {}).items():
        if e.get("kind") not in ("work", "function"):
            faults.append("%s: kind is neither work nor function" % name)
        if e.get("kind") == "work" and not (e.get("reads") and e.get("writes")):
            faults.append("%s: a work engine names what it reads and what it writes" % name)
        faults += start_faults(name, e, d.get("engines") or {})
        layer = S.ENGINE_LAYER.get(name) if e.get("kind") == "function" else None
        heard = {(r["act"], r["word"]) for r in S.hears(layer)} if layer else set()
        for h in e.get("on") or []:
            w = h.get("when") or {}
            if layer and (w.get("msg_type"), w.get("word", S.ANY)) not in heard:
                faults.append("%s, %s: the handler hears %s/%s, which is no row of what %s hears" %
                              (name, h.get("name") or "a handler", w.get("msg_type"), w.get("word", S.ANY), name))
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
            elif s["check"] not in CHECK and s["check"] not in have["check"]:
                faults.append("%s: no check named %s ships with the app" % (where, s["check"]))
            elif layer and s["check"] not in S.CHECKS.get(layer, {}) and s["check"] not in S.SHARED_CHECKS:
                faults.append("%s: the check %s is neither %s's nor shared, in the interface" % (where, s["check"], name))
            if s.get("code") and s["code"] not in CODE and s["code"] not in have["code"]:
                faults.append("%s: no function named %s ships with the app" % (where, s["code"]))
            if s.get("prompt"):
                if s["prompt"] not in PROMPT and s["prompt"] not in have["prompt"]:
                    faults.append("%s: no prompt named %s ships with the app" % (where, s["prompt"]))
                if s.get("draft") not in DRAFT and s.get("draft") not in have["draft"]:
                    faults.append("%s: a soft step names a plain draft" % where)
                if not s.get("out"):
                    faults.append("%s: a soft step names the shape of its answer" % where)
            if not s.get("code") and not s.get("prompt"):
                faults.append("%s: the step names neither code nor a prompt" % where)
            if s.get("tools") is not None and (not isinstance(s["tools"], list) or any(t not in W.MODEL_TOOLS for t in s["tools"])):
                faults.append("%s: tools are a list of %s" % (where, ", ".join(W.MODEL_TOOLS)))
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
        # an engine the kind marks required is one of its line (PRD M4.4): no engine is mandatory unless its template says so
        req = k.get("required")
        if req is not None and (not isinstance(req, list) or any(n not in (k.get("line") or []) for n in req)):
            faults.append("kinds, %s: required names engines of its own line" % kind)
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


def edge_faults(edges):
    """The definitions' edges against the interface's (PRD A1.19): for every actor the definitions list, who it may post
    to with each act is what layer_schema.SENDS says, in its order."""
    want, faults = layer_schema.edges(), []
    for actor, acts in (edges or {}).items():
        if actor not in want:
            faults.append("edges, %s: the interface knows no such actor" % actor)
            continue
        for act in sorted(set(acts) | set(want[actor])):
            if (acts or {}).get(act) != want[actor].get(act):
                faults.append("edges, %s: the definitions let it %s to %s, and the interface says %s" %
                              (actor, act, (acts or {}).get(act), want[actor].get(act)))
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


def user_templates_dir():
    """The Library's other half: the engines born in this app's records, under the record home, which an update keeps
    (found live 2026-09-29: a born template written beside the code was gone after the update, and every map read of
    the organisation broke on it)."""
    return W.home() / "_library"


def engine_templates():
    """The Library's engine templates: one file per engine, each with its id, its name and its use case (TPL-1, founder
    2026-09-29: engines come from templates, matched to the use case); the shipped ones beside the code first, then the
    ones born into the record home. A file that is not a template refuses the load, as a bad step does."""
    out = {}
    dirs = [TEMPLATES_DIR]
    try:
        dirs.append(user_templates_dir())
    except Exception:  # noqa: BLE001 -- no record home yet (a load with no home set): the shipped Library alone
        pass
    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                t = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError("the engine template %s is refused: not JSON (%s)" % (p.name, exc))
            if not isinstance(t, dict) or not t.get("id") or not t.get("name") or not t.get("use_case"):
                raise ValueError("the engine template %s is refused: a template names an id, a name and a use case" % p.name)
            if t["name"] in out:
                raise ValueError("the engine template %s is refused: %s is already a template" % (p.name, t["name"]))
            if d != TEMPLATES_DIR:
                _born_fits(p, t)
            out[t["name"]] = t
    return out


_BORN_SEEN = set()                                  # the born templates (file, time) whose fit to the interface was read this run


def _born_fits(p, t):
    """A template born into the record home, read back: if it does not fit the interface's engine.template, that is a row
    (once for the file as it stands), and today's refusals stand as they were (A1.20). Never raises."""
    try:
        key = (str(p), p.stat().st_mtime_ns)
        if key in _BORN_SEEN:
            return
        _BORN_SEEN.add(key)
        import layer_schema as S
        S.report("engine.template", S.validate("engine.template", t), owner="root", never_refuse=True)   # a row; loading never fails on it
    except OSError:
        return


def missing_engines(d):
    """The engines a record names that no template in the Library defines (one born in an older bundle, or a file gone)."""
    have = defs()["engines"]
    return [n for n in (d or {}).get("engines") or [] if n not in have]


def defs():
    """The definitions: the file (the kinds, the edges, Coordination's table), the five functions' engines from their
    layers' recipes (layers/<layer>/v1.json, PRD A1.18), and the Library's engine templates assembled in as engines,
    validated as one."""
    try:
        key = str(user_templates_dir())
    except Exception:  # noqa: BLE001 -- no record home set
        key = "d"
    if key not in _DEFS and "d" in _DEFS:
        _DEFS.clear()                                          # another record home: its own born engines
    if "d" not in _DEFS:
        _DEFS[key] = True
        d = json.loads((Path(__file__).parent / "engine_defs" / "website.json").read_text(encoding="utf-8"))
        import layers                                          # each function's recipe lives with its layer's bodies (A1)
        d["engines"] = dict(layers.recipes(), **(d.get("engines") or {}))
        for name, t in engine_templates().items():
            if name in d["engines"]:
                raise ValueError("the engine template %s is refused: the definitions already hold an engine of that name" % name)
            e = {k: v for k, v in t.items() if k not in ("id", "version")}
            e["from_template"] = t["id"]
            d["engines"][name] = e
        # each function's version 1 is one agent and its files (S-28): a file gone from the bundle refuses the load, as
        # a step with no check does, so no function runs on words that are not there (PRD M2.1)
        faults = validate(d) + bundle_faults()
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


def engine_limit(name):
    """The limit Priority gives an engine, a day, from its template, and the one place its shape is named (PRD M4.1; the
    layer schema binds it): {calls, usd}; a work engine is given work_calls times the calls, since its steps are a call
    each; a function the calls; the money is the same."""
    t = priority_template()
    base = {"calls": int(t.get("calls", W.ENVELOPE["calls"])), "usd": float(t.get("usd", W.ENVELOPE["usd"]))}
    if (engine_def(name) or {}).get("kind") == "work":
        return {"calls": int(t.get("work_calls", 8)) * base["calls"], "usd": base["usd"]}
    return base


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


def _resolve(ctx, kind, name, engine=None):
    """The function that runs `name` of `kind` ('code', 'prompt', 'draft' or 'check') for an engine of this department
    (PRD A1.19, the seam): the one its layer's pinned implementation provides, else the registry literal below, which
    stays the fallback until a body has moved into its layer. `engine` is the engine the step belongs to when that is
    not the one the context runs: a gate, or a rule of another function, is the function's, not the engine it blocks."""
    return layers.resolve(ctx.get("ref"), engine or ctx.get("engine"), kind, name,
                          {"code": CODE, "prompt": PROMPT, "draft": DRAFT, "check": CHECK}[kind], d=ctx.get("dept"))


def _impl(ctx, engine=None):
    """The implementation that ran a step, as the record names it ('identity/v1'): the pin of the layer the engine is;
    None for a work engine, which is no layer's."""
    layer = layers.layer_of(engine or ctx.get("engine"))
    return layers.pins(ctx.get("ref"), ctx.get("dept"))[layer] if layer else None


def card(ctx):
    """Each engine has its own agent. This is who it is: the engine's card, and for a function the brief of the
    Library template the department picked for it."""
    e, d, name = ctx["def"], ctx["dept"], ctx["engine"]
    does, skills = _goal_of(ctx.get("ref"), name, e)
    lines = ["You are the agent of %s, one engine of the department \"%s\"." % (name, d.get("name")),
             "What %s does: it %s." % (name, does),
             "Its skills: %s." % "; ".join(skills)]
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
    W.save_dept(ref, d, by="identity")
    W.system_run(ref, "Identity", "%s set %s's ladder: %s" % (by, engine, ", ".join("%s %d" % kv for kv in sorted(own.items()))))
    return numbers(ref, engine)


# ---- Coordination's table ------------------------------------------------------------------------------------------
#: coordination.json, Coordination's own state, and the one place its shape is named (PRD M4; the layer schema binds it):
#: what is served first and the order inside each (order, functions, line); who may post what to whom (edges); the
#: engines the registered plan left out (left_out, LEFT_OUT_FIELDS); the engines the owner added through J5 (grown); the
#: plan it follows (registered, the workflow's version); one slot for each engine of the line (timetable, SLOT_FIELDS);
#: who wrote it, when and why (by is born or Coordination, never Root).
TABLE_FIELDS = ("order", "functions", "line", "edges", "left_out", "grown", "registered", "timetable", "by", "since", "why")
LEFT_OUT_FIELDS = ("engine", "in_line", "since")
#: one row of Coordination's timetable (PRD M4.3): the engine, what starts it in words ('after <artifact> vN' or 'every
#: <period>'), the trigger behind the words (of and checked, or every_s), its window in minutes, and since when it has held a slot
SLOT_FIELDS = ("engine", "on", "of", "checked", "every_s", "window_min", "since")


def left_out_row(engine, since=None):
    """An engine on the department's record that the registered plan left out: it stays on the record and never runs."""
    return {"engine": engine, "in_line": False, "since": since or W.now()}


def timetable_row(engine, slot, window_min, since=None):
    """One slot of the timetable, from the engine's slot (slot_of) and its window, in SLOT_FIELDS' order."""
    row = {"engine": engine, "on": slot.get("on")}
    row.update({k: slot[k] for k in ("of", "checked", "every_s") if k in slot})
    row.update({"window_min": int(window_min), "since": since or W.now()})
    return row


def _put_table(ref, t, why):
    """Coordination writes its table: the one writer of coordination.json once the department is born."""
    t.update({"since": W.now(), "by": "Coordination", "why": why})
    with W._lock(ref):
        W._write(W.ddir(ref) / "coordination.json", t)
    return t


def born_table(kind="website", line=None):
    """What Coordination is born with: the order of service, the department's line (the engines on its record; the
    kind's line for one born before the record carried it), and who may post what to whom, from the definitions."""
    d = defs()
    t = json.loads(json.dumps(d["coordination"]))
    kinds = d.get("kinds") or {}
    # the engines on the record, an empty line included (a department born with none, the organic kind: Adaptation shapes
    # its line); the kind's line for one born before the record carried it; the defaults' for one born before kinds
    t["line"] = list(line) if line is not None else list((kinds.get(kind) or {}).get("line") or [] if kind in kinds else t["line"])
    t["edges"] = json.loads(json.dumps(d["edges"]))
    return t


def coordination(ref):
    """Coordination's table for this department. It is Coordination's state, kept on the department's record, and it
    is the only copy that is read: a department made before the table was kept reads what Coordination is born with."""
    t = W._read(W.ddir(ref) / "coordination.json", None) if ref else None
    dept = W.dept(ref) or {}
    kind, line = dept.get("kind") or "website", dept.get("engines")
    if not isinstance(t, dict) or table_faults(t, defs()["engines"]):
        born = born_table(kind, line)
        if isinstance(t, dict):
            # a table with a fault (an engine the Library no longer defines) is not read; what a registered plan left out
            # stays out of the born line all the same, so an engine Priority cut never runs (PRD M4.2)
            out = {r.get("engine") for r in (t.get("left_out") if isinstance(t.get("left_out"), list) else []) if isinstance(r, dict)}
            born["line"] = [n for n in born["line"] if n not in out]
        return born
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
    """Coordination's rule on a post: pass or refuse. `item` is (src, dst, act). Its note says the act in the owner's
    words (ACT_SAYS), never the act's id, for the note is the line its card prints."""
    src, dst, act = item
    if may_post(src, dst, act, ctx["ref"]):
        return "admit", _may_note(src, dst, act, "may")
    return "refuse", _may_note(src, dst, act, "may not")


def _may_note(src, dst, act, may):
    """What a sender may or may not post, to whom, as Coordination's card prints it: 'The owner may say no to Identity',
    'Adaptation may not tell the owner'. A post with nobody named says so."""
    who = ["the owner" if x == OWNER else x for x in [src] + list(dst)]
    head = who[0][:1].upper() + who[0][1:]
    if not dst:
        return "%s %s post to nobody" % (head, may)
    return "%s %s %s" % (head, may, ACT_SAYS.get(act, (act, "post " + str(act) + " to %s"))[1] % _names(who[1:]))


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
    if src == "Identity" and OWNER in dst:
        payload = _plainly(ref, payload or {})        # one voice, in plain words (PRD M3.6)
    import layer_schema as S
    S.check_act(src, dst, msg_type, payload or {}, ref)   # the act against the interface (PRD A1.13): a row in warn mode
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
            if th.get("topic") == "line" and (payload or {}).get("word") == "line" and _j2_live(ref):
                _line_conflict(ref, th["id"], "the bargain reached its bound of %s hops" % th["bounds"].get("hops"), bound="hops", src="Coordination")
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
    J = _j2()
    if J:
        J.on_post(ref, row)
    W.signal()                                         # a post is a trigger: its reader looks now
    return row


# ---- one voice, in plain words (PRD M3.6) --------------------------------------------------------------------------
# Only Identity speaks to the owner, and what it says passes this check on its way to the board, from _tell and from
# every other post Identity makes to the owner: no function addressing another, no J2 code, and none of the bargain's
# inside words (grant, counter). The owner's own words are never judged: a word the owner said (in the post, the goal,
# done-when, the rules or the Brief) is theirs to keep. A line that fails is said once more in the owner's words
# (owner_words.plain); one that still fails is replaced by a template, and the post says which.
PLAIN_FAULTS = (("a function addressing another",
                 re.compile(r"^\s*(?:Adaptation|Priority|Coordination|Audit)\s*[,:]|\b(?:dear|hey|hi|hello)\s+(?:Adaptation|Priority|Coordination|Audit)\b|"
                            r"@(?:Adaptation|Priority|Coordination|Audit)\b", re.I)),
                ("a J2 code", re.compile(r"\bJ[12](?:\.[a-h1-9])?\b|\b(?:FI|FA|FP|FC|FAU)\d+(?:\.\d+)?\b|\b(?:S|SM|MK|Q)-\d+\b")),
                ("grant or counter", re.compile(r"\bgrant(?:s|ed|ing)?\b|\bcounter(?:s|ed|ing)?\b|\bcounter-?offers?\b", re.I)))
PLAIN_KEYS = ("done", "objective", "answer", "why")
PLAIN_TEMPLATE = {"answer": "I could not put that in plain words. Ask me again, in other words.",
                  "question": "What should I know before the department starts?",
                  "title": "The plan cannot go on as it is.",
                  "blocked": "The plan cannot go on as it is. Say what to change, or choose a way forward on this card.",
                  "conflict": "Adaptation proposes a plan Priority did not say yes to, and the goal and the rules do not settle it. "
                              "Stamp to run it as proposed, or say no to drop it.",
                  "why": "the reason is on the department's record",
                  "": "The department moved on; what changed is on its record."}
#: the words of an ask its card shows the owner (PRD M3.6, screens S6 and S10), each by the template its kind of line
#: falls back to; the card's own line (text) falls back as the card is: a question, a blocked plan, or a line
CARD_KEYS = {"text": "", "title": "title", "why": "why"}


def _owners_words(ref, payload):
    """Everything the owner said that Identity may say back: the post's words, the goal, done-when, the rules, the Brief."""
    d = W.dept(ref) or {}
    said = [str(payload.get(k) or "") for k in ("words", "boundaries")]
    said += [str(d.get("goal") or ""), str(d.get("done") or "")] + [str(i.get("text") or "") for i in d.get("done_items") or [] if isinstance(i, dict)]
    said += [str(r.get(k) or "") for r in d.get("rules") or [] if isinstance(r, dict) for k in ("line", "from")]
    try:
        said.append(_brief_text(ref) if "Brief" in W.artifacts_of(d) else "")
    except Exception:  # noqa: BLE001 -- the check never fails the post for a record it cannot read
        pass
    return " ".join(said).lower()


def plain_faults(text, owners=""):
    """What a line Identity says to the owner breaks of the plain-words rule (M3.6): [] when it is plain. A word the
    owner said (`owners`, lowercased) is theirs and never a fault."""
    out = []
    for name, rx in PLAIN_FAULTS:
        if any(m.group(0).strip().lower() not in owners for m in rx.finditer(str(text or ""))):
            out.append(name)
    return out


def _plain_one(text, owners, key):
    """One line, checked: (the line, its faults, how it was put right): as it was; said again once in the owner's words;
    or the template for its kind of line."""
    faults = plain_faults(text, owners)
    if not faults:
        return text, [], None
    again = owner_words.plain(text)
    if plain_faults(again, owners):
        return PLAIN_TEMPLATE.get(key, PLAIN_TEMPLATE[""]), faults, "template"
    return again, faults, "said again"


def _plainly(ref, payload):
    """Identity's words to the owner, checked: said again once in the owner's words, then a template (M3.6)."""
    owners, out, fixed = None, dict(payload), []
    for k in PLAIN_KEYS:
        v = out.get(k)
        if not isinstance(v, str) or not v.strip():
            continue
        owners = _owners_words(ref, payload) if owners is None else owners
        out[k], faults, by = _plain_one(v, owners, k)
        if faults:
            fixed.append({"key": k, "faults": faults, "by": by})
    if fixed:
        out["plain"] = fixed
    return out


def plain_card(ref, fields, text_is=""):
    """The words an ask's card shows the owner pass the check Identity's posts pass on their way to the board (M3.6), on
    their way to the ask, so a card never says what the line it stands for may not (found by a verifier 2026-10-23: a
    blocked plan's card said grant and counter while the chat line it stood for was a template). `fields` is the card's
    words by CARD_KEYS ({text, title, why}); `text_is` names what its text is, a 'question', a 'blocked' plan or a
    'conflict' Identity puts to the owner, for its template. The one check for every card: the options ask (_blocked),
    Identity's question (J.asked) and the conflict card (identity_closed). Returns the fields, checked."""
    owners, out = None, dict(fields)
    for k, v in fields.items():
        if not isinstance(v, str) or not v.strip():
            continue
        owners = _owners_words(ref, fields) if owners is None else owners
        out[k] = _plain_one(v, owners, (text_is or "") if k == "text" else CARD_KEYS.get(k, ""))[0]
    return out


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
    if d.get("kind") == "root":
        _reconcile_j1_tells(ref)
    ctx = _coord_ctx(ref, d)
    closed = _ask_rule(ref, "coord.bounds", key="bounds@%s" % W.now(), ctx=ctx)["closed"]
    _ask_rule(ref, "coord.alarm", key="alarm@%s" % W.now(), ctx=ctx)
    return closed


def request(ref, text, about=None, message_id=None, answers=None):
    """The owner's words reach the department as a request to Identity, on the board. On a Root they arrive at the front
    door (the word front), with the department they are about when the person said them from inside one (the chip).
    `answers` names the question of Identity's the words answer, when they came through its answer box (M3.3)."""
    text = " ".join(str(text or "").split())
    if not text:
        raise ValueError("say what the website is for")
    d = W.dept(ref)
    if not d:
        raise ValueError("no department at %s" % ref)
    first = W.artifacts_of(d)[0]              # the Brief; on a Root, a Request
    with W._lock(ref):
        reqs = W.requests(ref)
        rid = str(message_id or ("q-" + uuid.uuid4().hex[:8]))
        prior = next((q for q in reqs if q.get("id") == rid), None)
        if prior:
            return prior, None
        rq = {"id": rid, "text": text, "at": W.now()}
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
              "may_read": [first], "boundaries": "inside the department's goal and rules", "request": rq["id"], "about": ab,
              **({"answers": answers} if answers else {})},
             about=ab)
    return rq, p


def on_stamp(ref, ask, approve):
    """The owner's stamp or refusal, posted in the ask's own thread, so Identity applies it as a step; for an ask with
    options, the option the owner chose (M3.5). An answer to an ask still pending is never dropped: when its thread
    closed before the answer came (a card kept from before the card that waits again had a thread of its own), the
    answer is posted in a thread of its own, which it closes as it would have closed the ask's. None when the ask has no
    thread, or the post did not reach the board."""
    if not ask.get("thread"):
        return None
    chosen = ask.get("chosen") if isinstance(ask.get("chosen"), dict) else None
    act = "accept-proposal" if approve else "reject-proposal"
    pl = dict({"word": ask.get("kind"), "ask": ask["id"]}, **({"option": chosen["id"], "chose": chosen["label"]} if chosen else {}))
    th = _thread(ref, ask["thread"])
    if not th or th["state"] not in CLOSED:
        return post(ref, OWNER, "Identity", act, pl, thread=ask["thread"])
    row = post(ref, OWNER, "Identity", act, pl)
    if row:
        _thread_set(ref, row["thread"], state=_state_after(th, ["Identity"], act), outcome={"by": act, "n": row["n"]})
    return row


# ---- what may start now --------------------------------------------------------------------------------------------
def _run_row(engine, system, slot, status, what, **more):
    """A run as the record keeps it. A run whose line ends with the owner's own words, carried by the post it handled
    ('took the owner's words: ...'), keeps them as `words` too, so a screen shows them as the owner said them and says
    only the rest in its own words (owner_words.kept; PRD M1.7)."""
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
    if not peek and d.get("kind") == "root":
        _reconcile_j1_tells(ref)
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
    if not e or not isinstance(e.get("start"), dict):
        return None                                            # an engine the Library no longer defines: no trigger of its own; the map says so
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
            if e.get("kind") == "work" and (ctx.get("dept") or {}).get("kind") != "root":
                J = _j2()
                hold = J.holding(ctx["ref"]) if J else None
                if hold:                                   # D2: propose, grant, check, register, then run
                    why = why or hold
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
    gctx["peek"] = bool(ctx.get("peek"))
    for gid in ((e or {}).get("start") or {}).get("unless") or []:
        fn, g = step_def(gid)
        rung = rung_of(ref, g)
        answer, why = _resolve(gctx, "code", g["code"], engine=fn)(gctx, g, None)
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
        # the gate's covering is code (M2.4): a start it does not hold for is never let through; the row says it failed
        check = _resolve(gctx, "check", g["check"], engine=fn)(gctx, g, None, {"answer": answer, "why": why})
        if answer == "admit" and not check.get("ok"):
            answer, why = "wait", "; ".join(str(n) for n in check.get("notes") or []) or "its check failed"
        if not ctx.get("peek"):
            _gate_row(ref, slot, fn, g, rung, answer, why, check=check, ctx=gctx)
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
    fn, s = step_def(sid)
    return _resolve(ctx, "code", s["code"], engine=fn)(ctx, s, item)


def _ask_rule(ref, sid, item=None, key=None, ctx=None):
    """Ask one of Coordination's rules, or run in place the step of a handler a function keeps on a fixed trigger (an
    engine is born: Coordination's table, Priority's limit), and write its decision down, once for each thing decided,
    as a row of the function whose step it is."""
    ctx = ctx or _coord_ctx(ref)
    fn, s = step_def(sid)
    got = _resolve(ctx, "code", s["code"], engine=fn)(ctx, s, item)
    out = got if isinstance(got, dict) else {"answer": got[0], "why": got[1]}
    if out.get("answer") or out.get("said"):
        _gate_row(ref, key or sid, fn or "Coordination", s, rung_of(ref, s), out.get("answer") or out.get("said"), out.get("why"), out=out)
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
    _, rule = step_def("coord.busy")
    held = CHECK[rule["check"]](ctx, rule, None, {"answer": busy, "why": why})
    if busy != "admit" or not held.get("ok"):                 # the covering: one run at a time, read again (M2.4)
        return None, None, why if busy != "admit" else "; ".join(held.get("notes") or [])
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
        if first and first["src"] == "Adaptation" and (first.get("payload") or {}).get("word") == "line" and _j2_live(ref):
            which = ((_thread(ref, tid) or {}).get("outcome") or {}).get("which")
            _line_conflict(ref, tid, "the bargain reached its bound (%s)" % which, bound=which, src="Coordination")
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


def _gate_row(ref, slot, fn, g, rung, answer, why, out=None, ctx=None, check=None):
    """A decision made on the way to a start, as a row: a blocker's answer, or one of Coordination's rules. Written
    once for each thing decided, however many times it is asked. `check` is the covering's verdict when the caller
    already read it (a failed one held the start: M2.4); else the covering is read here, on `ctx` when given."""
    key0 = str(W.ddir(ref))
    seen = _GATE_SEEN.get(key0)
    if seen is None:
        seen = {(r.get("slot"), r.get("step"), r.get("answer")) for r in step_rows(ref) if r.get("mode") == "gate"}
        _GATE_SEEN[key0] = seen
    key = (slot, g["id"], answer)
    if key in seen:
        return
    seen.add(key)
    where = ctx or {"ref": ref}                           # the department's pins are found from its ref when no context came
    check = check or _resolve(where, "check", g["check"], engine=fn)(ctx, g, None, out or {"answer": answer, "why": why})
    _append(ref, "steps.jsonl", {"id": "s-" + uuid.uuid4().hex[:10], "run": None, "engine": fn, "step": g["id"], "item": None,
                                 "mode": "gate", "slot": slot, "impl": _impl(where, fn), "asked_rung": rung, "rung": rung, "miss": False, "by": "code",
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
    if len(safe) > 120:                                    # a long item is named by its head and its hash (found live 2026-09-30: Errno 63)
        safe = safe[:80] + "-" + _sha(safe)[:16]
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
    J = _j2()
    if J:
        J.on_run(ref, row, "started")
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
                # a kept step keeps how it was answered, as its finished row says: a judge the model read before the app
                # closed is still a reading (M0.3; found 2026-10-23: a department waited at step 7 on a version the model read)
                was = [items[i] for i in kept if kept[i] is not None]
                by = next((r.get("by") for r in reversed(before) if r.get("slot") == slot and r.get("step") == s["id"]
                           and r.get("item") in was and r.get("status") == "ok" and r.get("mode") != "gate" and r.get("by")), None)
                ctx["how"].setdefault(s["id"], by or "kept from before the app closed")

            import threading
            counted, guard = [0], threading.Lock()

            def one(i, s=s, items=items):
                if not (s.get("each") and len(items) > 1):
                    # the working line follows the step (found live 2026-09-29: "reading Brief" for the whole 90 s of a web search)
                    try:
                        W._put_run(ref, dict(row, what=s["name"]))
                    except Exception:  # noqa: BLE001 -- the line never fails the step
                        pass
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
            # a step that may end the run said the words ask for no work of this engine: the run ends ok, files nothing,
            # and the line reads what was filed last (found live 2026-09-29: four web searches in one run, one asked for)
            if s.get("may_end") and isinstance(ctx["bag"][s["id"]], dict) and ctx["bag"][s["id"]].get("run") is False:
                ctx["bag"][s["id"]]["said"] = "not needed: " + str(ctx["bag"][s["id"]].get("why") or "the words ask for none of this")
                break
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
            if ok and filed.get("publish"):
                # a site made by an engine shaped on the fly goes on the host only once its version row is written, so the
                # record and the host never disagree (DeepSeek P1, 2026-09-30); Publish's own step puts a Build there itself
                W._publish_files(ref, filed["files"])
            row.update({"status": "ok" if ok else "failed", "wrote": {"art": e["writes"], "v": out["v"]},
                        "what": "%s from %s, check %s" % (e["writes"], e["reads"], "passed" if ok else "failed")})
            # the last artifact of the kind went out: the person is told in the chat, with the way to it (found live
            # 2026-09-28: after the publish stamp the chat said nothing)
            own = set((W.KINDS.get(ctx["dept"].get("kind") or "website") or {}).get("artifacts") or [])
            # ... and so is what an engine the person added filed (its facts, its list): they asked for it, they hear of it
            if ok and (e["writes"] == W.artifacts_of(ctx["dept"])[-1] or e["writes"] not in own) and ctx["dept"].get("kind") != "root":   # Root's last artifact is a spawn, said by Setup
                try:
                    import artifacts
                    host = (ctx["dept"].get("host") or "").strip()
                    site = (artifacts.get(e["writes"]) or {}).get("kind") == "site"      # a Result is filed; a site goes live
                    _tell(ref, ctx["dept"], {"src": "Root" if ctx["dept"].get("root") else OWNER}, "inform",
                          {"word": "live" if site else "filed",
                           "done": "%s v%d is %s%s." % (e["writes"], out["v"], "live" if site else "filed",
                                                        (" at " + host) if site and host and host != W.HOST_DEFAULT else ""),
                           "link": e["writes"], "v": out["v"], "chain": row.get("chain")})
                except Exception:  # noqa: BLE001 -- telling never fails the version that went out
                    pass
            if not ok and filed["check"].get("broken"):
                _send_back(ref, ctx["dept"], e["writes"], out["v"], filed["check"]["broken"])
        else:
            said = next((ctx["bag"][s["id"]].get("said") for s in reversed(steps)
                         if isinstance(ctx["bag"].get(s["id"]), dict) and ctx["bag"][s["id"]].get("said")), None)
            row.update({"status": "ok", "what": said or what})
            words = str(((p or {}).get("payload") or {}).get("words") or "")
            if words and str(row["what"]).endswith(words):
                row["words"] = words                     # the owner's words the line ends with, as they said them
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
        if name == "Adaptation" and p and (p.get("payload") or {}).get("word") == "line" and p.get("msg_type") == "request":
            _j2_shape_failed(ref, d, p, note)
        if name == "Setup":
            _j1_close(ref, "failed", "I could not set the department up: %s. Say what you want again, or say it differently."
                      % str(note or "a step failed").rstrip("."))
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
    row = W._put_run(ref, row)
    if J:
        J.on_run(ref, row, "ended")
        if name == "Audit" and row.get("status") == "ok" and not p and isinstance(ctx["bag"].get("audit.file"), dict):
            filed = ctx["bag"]["audit.file"]
            if filed.get("read") is False and not filed.get("filed"):
                J.not_read(ref, inp.get("v"), filed.get("why_not_read"))      # never 'clean': the cycle stays at step 7
            else:
                _j2_audit_read(ref, d, inp.get("v"), filed.get("filed"))
        elif name == "Audit" and row.get("status") == "failed" and not p and inp.get("v") is not None:
            # a reading whose covering check failed is no reading (M2.4): the version is not read, nothing is cleared,
            # and the cycle stays at step 7; the failed step is Audit's fault on every screen
            J.not_read(ref, inp.get("v"), "its reading failed its check (%s)" % str(note or "a step failed").rstrip("."))
    return row


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
        out, how = _resolve(ctx, "draft", step["draft"])(ctx, step, item), SKIPPED
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
           "mode": "slot", "slot": ctx["slot"], "impl": _impl(ctx), "asked_rung": asked, "rung": rung, "miss": rung != asked, "by": how,
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
        check = _resolve(ctx, "check", step["check"])(ctx, step, item, out)
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
    # the internet is a given: every agent step may search and fetch (founder, 2026-09-29: "Internet is given ... I don't
    # want to lose all the basic features of agents"); a step's own list narrows it, never widens it
    return W.model_json(prompt, timeout=int(step.get("timeout_s") or W.MODEL_TIMEOUT_S), tools=step.get("tools") or list(W.MODEL_TOOLS))


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
    prompt = card(ctx) + _resolve(ctx, "prompt", step["prompt"])(ctx, step, item)
    if checklist:
        prompt += "\n\nFOLLOW THIS CHECKLIST, learned from this step's earlier runs:\n" + checklist
    usd, calls, fault = 0.0, 0, None
    for _ in (1, 2):
        obj, cost, how = call_model(prompt + ("\n\nYour last answer was not usable: %s. Answer again, in the exact shape asked." % fault
                                              if fault else ""), step)
        usd += float(cost or 0)
        if how == "offline":
            return _resolve(ctx, "draft", step["draft"])(ctx, step, item), 0.0, "offline draft", 0
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
        return _resolve(ctx, "draft", step["draft"])(ctx, step, item)
    return None


def _person(ctx, step, item):
    ref = ctx["ref"]
    key = "%s|%s|%s" % (ctx["slot"], step["id"], item)
    with W._lock(ref):
        a = next((a for a in W.asks(ref) if a.get("kind") == "step" and a.get("key") == key), None)
        if a is None:
            a = W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "step", "engine": ctx["engine"], "slot": ctx["slot"],
                                 "key": key, "step": step["id"], "text": step.get("by_hand") or "%s: by hand" % step["name"],
                                 "status": "pending", "created": W.now()})
            if step.get("by_hand"):
                try:
                    post(ref, "Identity", OWNER, "request", {"word": "step", "objective": step["by_hand"], "output": "a stamp or a refusal",
                                                             "may_read": [], "boundaries": "this one step"})
                except Exception:  # noqa: BLE001 -- the ask is on the record whether or not the chat carries it
                    pass
    if a["status"] == "pending":
        return ASKED, 0.0, a["id"], 0
    if a["status"] == "refused" or not step.get("draft"):
        return INVALID, 0.0, "refused by the owner", 0
    return _resolve(ctx, "draft", step["draft"])(ctx, step, item), 0.0, "stamped by the owner", 0


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
    if step.get("code"):
        try:
            fn = _resolve(ctx, "code", step["code"])
        except KeyError:                                   # a name no registry holds
            fn = None
        if fn is not None:
            return fn(ctx, step, item), 0.0, "code", 0
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
            c2 = _resolve(ctx, "check", step["check"])(ctx, step, item, got)
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
              {"word": "plan", "done": "Planned %d pages: %s. Say which to drop or add." % (len(titles), ", ".join(titles)),
               "chain": W._chain_of(ref, ctx["def"].get("reads") or "Brief", ctx["inp"]["v"])})
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


_ADDRESS = re.compile(r"(?<![\"'=>/\w])(https?://[^\s<>\"']+?)(?=[.,;:!?)\]]*(?:\s|<|$))")


def _link_addresses(html):
    """A bare address in a page's text becomes a link; one already inside a tag or a link is left alone (found live
    2026-09-29: 'Address as read: https://...' as text on every page, for a reader to copy)."""
    out, pos = [], 0
    for m in re.finditer(r"<a\b[^>]*>.*?</a>|<[^>]+>", html, flags=re.I | re.S):
        out.append(_ADDRESS.sub(lambda a: '<a href="%s">%s</a>' % (a.group(1), a.group(1)), html[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_ADDRESS.sub(lambda a: '<a href="%s">%s</a>' % (a.group(1), a.group(1)), html[pos:]))
    return "".join(out)


def write_file(ctx, step, item):
    plan = ctx["bag"]["write.list"]["plan"]
    slugs = ctx["bag"]["write.list"]["pages"]
    files = {}
    for s, page in zip(slugs, ctx["bag"]["write.page"]):
        title = next((p.get("title") for p in plan["pages"] if p["slug"] == s), s)
        files[s + ".html"] = json.dumps({"title": str(page.get("title") or title), "body_html": _link_addresses(str(page["body_html"]))})
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


def _goes_out(e):
    """The artifact an engine writes that goes out into the world, by name: the Library's template counts it after a
    stamp (the Live site); None for one that stays in the record."""
    import artifacts
    w = (e or {}).get("writes")
    return w if w and (artifacts.get(w) or {}).get("counts_after") == "stamp" else None


def _writes_site(e):
    """Whether what the engine writes is a site the app serves (the Library's template says kind site)."""
    import artifacts
    return (artifacts.get((e or {}).get("writes")) or {}).get("kind") == "site"


def _writes_pages(e):
    """Whether what the engine writes is pages, not one text: the Library's template says kind site, pages or build
    (found live 2026-09-30: a line shaped on the fly named Pages, whose template wants html files, and Do filed one text)."""
    import artifacts
    return (artifacts.get((e or {}).get("writes")) or {}).get("kind") in ("site", "pages", "build")


def _web_engine(d):
    """The first engine on the record that reaches the internet, by name; None when none does."""
    for name in d.get("engines") or [x[0] for x in W.engines_of(d)]:
        if any(s.get("tools") for s in all_steps(name)):
            return name
    return None


def identity_wait_engine(ctx, step, item):
    """A blocker on every work engine: while an ask to add an engine the owner's words need is pending, the line waits
    for the stamp, and the owner is told once (found live 2026-09-29: the goal was filed and Plan and Write built a site
    of "to be confirmed" while the engine ask waited; its publish ask came the second the engine filed). A refused ask
    holds nothing: the owner chose."""
    ref, d = ctx["ref"], ctx["dept"]
    pending = [a for a in W.asks(ref) if a.get("kind") == "engine" and a.get("status") == "pending"]
    if not pending or d.get("kind") == "root":
        return "admit", None
    a = pending[0]
    if not a.get("told") and not ctx.get("peek"):
        with W._lock(ref):
            rows = W.asks(ref)
            for x in rows:
                if x.get("id") == a["id"]:
                    x["told"] = W.now()
            W._write(W.ddir(ref) / "asks.json", rows)
        _tell(ref, d, {"src": "Root" if d.get("root") else OWNER}, "inform",
              {"word": "waits", "engine": a.get("engine"),
               "done": "The line waits for your stamp on %s: nothing is built until the engine your words need is in place, or you say no to it."
               % a.get("engine")})
    return "wait", "waits for the stamp on %s" % a.get("engine")


def identity_gate(ctx, step, item):
    """The rule, as built: the first publish asks the owner, and so does every department a Root sets up ("A new
    department is stamped by the owner"); a refused one is skipped, never done."""
    ref, name, slot, inp = ctx["ref"], ctx["engine"], ctx["slot"], ctx["inp"]
    # what goes out into the world asks first: Publish's Live site, and any engine shaped on the fly whose artifact the
    # Library counts after a stamp (the organic line's last engine)
    out_art = "Live site" if name == "Publish" else _goes_out(ctx["def"])
    if out_art:
        if len(W.versions(ref, out_art)) > int(ctx["dept"].get("publish_asks_from") or 0):
            return "admit", None
        # the ask carries the question where the site is served from (founder, 2026-09-28: "more of a question
        # to the user and should be asked to the user"); the answer, or the default on a plain stamp, stays on
        # the record and Publish reads it
        host = ctx["dept"].get("host") or W.HOST_DEFAULT
        kind = "publish"
        objective = ("say whether the site may go live for the first time"
                     + (" under its new goal" if ctx["dept"].get("publish_asks_from") else "")
                     + ", and where it is served from: %s unless you say another" % host)
        text = "%s: go live for the first time, served from %s unless you say where else" % (name, host)
        reads = ctx["def"].get("reads") or "Build"
        may_read, about = [reads], {"art": reads, "v": inp["v"]}
    elif name == "Setup":
        matching = ({"id": "legacy-setup-stamp", "version": 1} if not _j1_enabled() else
                    next((r for r in _effective_rules(ref, ctx["dept"]) if _rule_applies_to_birth(r)), None))
        if matching is None:
            return "admit", None
        words = W.read_files(ref, "Request", inp["v"]).get("request.md", "").strip()
        kind = "setup"
        # one line, not the whole goal back (found live 2026-09-29: a five-line ask, stamped blind)
        head = re.split(r"(?<=[.!?])\s", words.strip(), maxsplit=1)[0]
        head = head if len(head) <= 120 else head[:117].rsplit(" ", 1)[0] + "..."
        objective = "say whether Root may set up a department for this: " + head
        text = "Set up a department for: " + head
        may_read, about = ["Request"], {"art": "Request", "v": inp["v"]}
    else:
        return "admit", None
    with W._lock(ref):
        a = next((x for x in W.asks(ref) if x.get("slot") == slot and x.get("kind") == kind), None)
        if a is None:
            p = post(ref, "Identity", OWNER, "request",
                     {"word": kind, "objective": objective, "output": "a stamp or a refusal", "may_read": may_read,
                      "boundaries": "this one %s" % kind}, about=about)
            ask = {"id": "a-" + uuid.uuid4().hex[:8], "kind": kind, "engine": name, "slot": slot, "text": text,
                   "status": "pending", "created": W.now(), "thread": p["thread"] if p else None}
            if name == "Setup":
                ask["rule"] = {"id": matching.get("id"), "version": matching.get("version")}
                ask["request_v"] = inp["v"]
            W._put_ask(ref, ask)
            return "wait", "waits for the stamp"
    if a["status"] == "pending":
        return "wait", "waits for the stamp"
    if a["status"] == "refused":
        if name == "Setup":
            _j1_close(ref, "refused")
        if not any(r.get("slot") == slot and r.get("status") == "skipped" for r in W.runs(ref)):
            W._put_run(ref, _run_row(name, False, slot, "skipped", "refused by the owner",
                                     chain=W._chain_of(ref, ctx["def"]["reads"], inp["v"])))
        return "refuse", "refused by the owner"
    return "admit", None


def _effective_rules(ref, dept):
    """Local rules followed by rules on the registry ancestors, with stable provenance."""
    rules = [dict(r) for r in dept.get("rules") or []]
    try:
        import placement_engine as E
        domains = E.load_domains()
        cur, seen = ref, set()
        while cur and cur not in seen:
            seen.add(cur)
            for charter in E.charters_for(cur):
                view = E.charter_view(charter) or {}
                for i, rule in enumerate(view.get("rules") or []):
                    if not isinstance(rule, dict):
                        continue
                    inherited = dict(rule)
                    inherited.setdefault("id", "%s:rule:%d" % (charter.get("id"), i + 1))
                    inherited.setdefault("version", view.get("schema") or 1)
                    if not any(r.get("id") == inherited["id"] for r in rules):
                        rules.append(inherited)
            cur = (domains.get(cur) or {}).get("parent_ref")
    except Exception:  # local materialized rules remain authoritative if the registry cannot be read
        pass
    return rules


def _rule_applies_to_birth(rule):
    if rule.get("tag") != "ask":
        return False
    scope = rule.get("applies_to")
    if isinstance(scope, str):
        scope = [scope]
    if isinstance(scope, list):
        return bool({"department_birth", "setup", "*"} & {str(x) for x in scope})
    line = str(rule.get("line") or "")
    return bool(re.search(r"\b(new department|make|create|set up|anything|approval first|approve first)\b", line, re.I))


def priority_envelope(ctx, step, item):
    ref, name, slot = ctx["ref"], ctx["engine"], ctx["slot"]
    calls, usd = W._today_spend(ref, name)
    env = W.limit_of(ctx["dept"], name)
    if calls >= env.get("calls", 0) or usd >= env.get("usd", 0):
        if not any(x.get("kind") == "envelope" and x.get("engine") == name and x["status"] == "pending" for x in W.asks(ref)):
            W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "envelope", "engine": name, "slot": slot,
                             "text": "%s is out of today's envelope" % name, "status": "pending", "created": W.now(), "escalated": True})
        if not ctx.get("peek"):
            # the hold is on the ledger once for its slot, however often the motor asks again (M0.4); a panel read
            # asking the same question writes nothing; Coordination's other waits stay in the status's 'next'
            J = _j2()
            if J:
                J.on_held(ref, name, slot, "%s is out of today's envelope" % name)
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
    # Identity's standard is read on the first words, and on the words that answer its question on it (PRD M3.3): the
    # question they answer is the one the answer box named, or the one open now when they were said in the chat
    J = _j2()
    pl = ctx["post"].get("payload") or {}
    live = bool(J and J.active(ctx["ref"])) and ctx["dept"].get("kind") != "root"
    answers = rule = None
    filled = []
    hurry = bool(JUST_DO_IT.fullmatch(words))
    if live:
        aid = pl.get("answers") or (J.open_question(ctx["ref"]) or {}).get("id")
        q = next((a for a in W.asks(ctx["ref"]) if a["id"] == aid and a.get("kind") == "j2_identity"), None) if aid else None
        if q and q.get("missing") == "rules" and not hurry and (pl.get("answers") == aid or not first):
            # the words answer Identity's question on the rules (PRD M3.4): they are read as a directive, so the rule
            # keeps the tag Identity reads in them and the owner stamps it; recognising them again is not needed
            rule, cue = aid, "directive"
        elif q and (q.get("standard") or (pl.get("answers") == aid and q.get("missing") != "words")):
            # a question Identity's code asked reaches this step from the answer box, the answer on the record already, for
            # Identity to read its standard again and go on, or to fill the defaults 'just do it' asks for (J.answer)
            answers = aid
            # the answer reaches the record before Identity reads its standard again (PRD M3.3): a gap only code can see
            # (no owner, no budget, no done-when) is closed by the owner's words, so neither the reading nor its covering
            # finds it again (found by a verifier 2026-10-23: the owner question came back after every answer, no cap)
            filled = [] if hurry else _standard_fill(ctx["ref"], q.get("missing"), words)
            if filled:
                ctx["dept"] = W.dept(ctx["ref"])
    return {"words": words, "about": about, "later": not first and not rule,
            "assess": bool(live and not rule and (first or (answers and not hurry))),
            "answers": answers, "rule": rule, "hurry": hurry, "filled": filled,
            "facts": {"kind": kind, "leaves_site": bool(LEAVES.search(words)), "first": first,
                      "cue": cue if rule else ("task" if first else cue), "names_work": bool(about)}}


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


def _j1_enabled():
    return os.environ.get("J1_FLOW_V1", "1").strip().lower() not in ("0", "false", "off")


def _j1_record(ref):
    state = W._read(W.ddir(ref) / "j1-state.json", None)
    if isinstance(state, dict):
        return state
    cur = W.latest(ref, "Request")
    if not cur:
        return None
    try:
        row = json.loads(W.read_files(ref, "Request", cur["v"]).get("request.json") or "null")
    except (TypeError, ValueError):
        row = None
    return row if isinstance(row, dict) else None


def _j1_close(ref, status, said=None):
    """The open J1 Request ends without a department (Setup failed, or the owner refused the preview): the next words
    start a new Request, and the owner is told in the chat rather than left with a line that says Sutra is shaping."""
    if not _j1_enabled():
        return
    with W._lock(ref):
        state = W._read(W.ddir(ref) / "j1-state.json", None)
        if not isinstance(state, dict) or state.get("status") in ("completed", "refused", "failed"):
            return
        state.update({"status": status, "outstanding_question": None})
        W._write(W.ddir(ref) / "j1-state.json", state)
    if said:
        try:
            post(ref, "Identity", OWNER, "inform", {"word": "request", "done": said})
        except Exception:  # noqa: BLE001 -- the Request is closed whether or not the word reached the chat
            pass


def _j1_clear(messages):
    user = [m["text"] for m in messages if m.get("actor") == "user"]
    if user and re.fullmatch(r"\s*just do it[.!]?\s*", user[-1], re.I):
        if not " ".join(user[:-1]).strip():
            return False, False
        user, defaults = user[:-1], True
    else:
        defaults = False
    useful = " ".join(user)
    named = bool(re.search(r"\b(department|website|site|app|software|system|service|plan|chart|report|laboratory|game|tool)\b", useful, re.I))
    outcome = bool(re.search(r"\b(for|that|to|so that|which|about)\b", useful, re.I)) or len(useful.split()) >= 10
    return (bool(named) if defaults else bool(named and outcome and len(useful.split()) >= 7)), defaults


JUST_DO_IT = re.compile(r"\s*just do it[.!]?\s*", re.I)
J1_DEFAULTS = ["department name from the organisation", "Priority limits from the selected Library template"]
SECOND = re.compile(r"\b(?:and|plus)\s+(?:also\s+)?(?:an?\s+)?(?:separate|another|second)(?:\s+(?:separate|another|second))*"
                    r"\s+(?:(?:department|team|one)\s+(?:for|to|that|which)\s+)?(.+)$", re.I)
# the Org screen's sheet (19-org2.js o2SendRequest, PRD M1.4): "Set up a department: <name>. <words>". The name is the
# owner's own, so it is the department's name, and the words after it are its goal
SHEET = re.compile(r"^\s*Set up a department:\s*([^.\n]+?)\s*(?:\.\s*(.*))?$", re.S)


def _sheet(words):
    """The name and the words of a sheet's request, or ('', words) for words said any other way."""
    m = SHEET.match(str(words or ""))
    if not m or not m.group(1).strip():
        return "", str(words or "")
    return " ".join(m.group(1).split())[:80], " ".join(str(m.group(2) or "").split())


def _j1_file_words(ref, d, words, note, message_id=None, thread=None):
    """Append one user message to the active J1 Request and file its next version. Whether the words are clear is not
    decided here: Setup's converse step reads the conversation and asks, or hands it on (S-24: no question in code)."""
    prior = _j1_record(ref)
    if not prior or prior.get("status") in ("completed", "refused", "failed"):
        prior = {"id": "j1-" + uuid.uuid4().hex[:12], "messages": [], "status": "collecting",
                 "outstanding_question": None, "defaults_applied": []}
    messages = list(prior.get("messages") or [])
    mid = str(message_id or ("m-" + uuid.uuid4().hex[:12]))
    if not any(m.get("id") == mid for m in messages):
        messages.append({"id": mid, "actor": "user", "text": words, "at": W.now()})
    record = dict(prior, messages=messages, status="collecting", outstanding_question=None, defaults_applied=[],
                  thread=thread or prior.get("thread"))
    body = "\n".join("%s: %s" % (m["actor"].title(), m["text"]) for m in messages) + "\n"
    row = W.add_version(ref, "Request", {"request.md": body, "request.json": json.dumps(record, indent=2)},
                        [{"ask": words, "at": W.now(), "message": mid}], "owner",
                        {"ok": True, "notes": [note]})
    W._write(W.ddir(ref) / "j1-state.json", record)
    return row, record


def _rule_ask(ref, slot, line, tag, words, thread, lead, **more):
    """A rule, restated, as an ask the owner stamps; `more` is kept on the ask (its scope, the question it answers)."""
    text = "%s: %s" % (lead, line)
    W._put_ask(ref, dict({"id": "a-" + uuid.uuid4().hex[:8], "kind": "rule", "engine": "Identity", "slot": slot, "text": text, "tag": tag,
                          "line": line, "words": words, "status": "pending", "created": W.now(), "thread": thread}, **more))
    return text


#: a rule's tag and scope, as Identity restates them to the owner (PRD M3.4)
RULE_SAYS = {"go": "it may do this", "ask": "it asks you first", "refuse": "it never does this", "always": "it always does this"}
SCOPE_SAYS = {"standing": "from now on", "one-time": "this once"}
#: words that say when the department is done: they change its done-when items, never its goal (PRD M3.4)
DONE_CUE = re.compile(r"\b(?:done[- ]when|(?:is|are|counts as|it's) (?:done|finished|complete) (?:when|once|if))\b", re.I)
DONE_LEAD = re.compile(r"^\s*(?:from now on,?\s*)?(?:(?:it|this|the (?:site|website|department|work))\s+(?:is|counts as)\s+"
                       r"(?:done|finished|complete)\s+(?:when|once|if)|(?:it's)\s+(?:done|finished|complete)\s+(?:when|once|if)|done[- ]when)\s*[:,-]?\s*", re.I)


def _rule_answered(ctx, got):
    """The owner answered Identity's question on the rules (PRD M3.4). A rule given as an answer keeps its tag: Identity
    restates it, with its tag and scope, as a rule ask the owner stamps, and nothing is written to the rules before the
    stamp. The stamp writes it and the cycle goes on (identity_apply); a refusal asks the question again."""
    ref, d, p, J = ctx["ref"], ctx["dept"], ctx["post"], _j2()
    words, aid = got["words"], got["rule"]
    J.took(ref, aid, words, at=_words_at(ref, p))
    r = ctx["bag"]["identity.rule"]
    line = " ".join(str(r.get("line") or words).split()).rstrip(".")
    tag = r.get("tag") if r.get("tag") in W.RULE_TAGS else "always"
    scope = r.get("scope") if r.get("scope") in SCOPE_SAYS else "standing"
    if any(str(x.get("line") or "").lower() == line.lower() and x.get("tag") in W.RULE_TAGS for x in d.get("rules") or []):
        _tell(ref, d, p, "inform", {"word": "request", "done": "the department already has this rule"}, thread=p["thread"])
        identity_next(ref)
        return {"said": "the department already has this rule: " + line}
    text = _rule_ask(ref, ctx["slot"], line, tag, words, p["thread"], "A rule, as understood (%s, %s)" % (RULE_SAYS[tag], SCOPE_SAYS[scope]),
                     scope=scope, answers=aid)
    _tell(ref, d, p, "request", {"word": "rule", "objective": text, "output": "a stamp or a refusal", "may_read": [],
                                 "boundaries": "this department, until the owner says otherwise"}, thread=p["thread"])
    return {"said": "restated the owner's answer as a rule, tagged %s, and put it back: %s" % (tag, line)}


def _done_items_said(ctx, r, words):
    """The owner's words say when the department is done (PRD M3.4): a new done-when item, as a done_items ask the owner
    stamps. Its own kind: the goal tag would overwrite the goal, and these words never change it."""
    ref, d, p = ctx["ref"], ctx["dept"], ctx["post"]
    text = DONE_LEAD.sub("", " ".join(str(r.get("line") or words).split())).rstrip(".") or words
    text = text[:1].upper() + text[1:]
    items = W.items_of(d) + [{"text": text, "how": "model", "level": "outcome"}]
    new = W.done_items(items)[-1]
    ask = W.done_items_ask("Done when, as understood: add %s %s, read by an AI. The goal stays as it is" % (new["id"], new["text"]),
                           items, "the owner's words say when the department is done", words=words, thread=p["thread"], slot=ctx["slot"])
    W._put_ask(ref, ask)
    _tell(ref, d, p, "request", {"word": "done_items", "objective": ask["text"], "output": "a stamp or a refusal", "may_read": [],
                                 "boundaries": "this department's done-when, until the owner says otherwise"}, thread=p["thread"])
    return {"said": "restated the owner's words as a done-when item and put them back: %s %s" % (new["id"], new["text"]), "journey": "directive"}


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


def _answers(yes, no, lead=None):
    """How an ask Identity puts to the owner says its two answers, in the words of the ask's two buttons, Stamp and Say
    no (the owner's ruling: said yes and said no, never refuse; PRD M1.7): 'Stamp to <yes>, or say no <no>.', where no
    goes on from 'say no' ('to leave them out', 'and say what to change'). A lead goes first, and the answers follow it
    in lower case. An ask whose text names its answers names them through here, so the text and the buttons agree."""
    said = "%s to %s, or say no %s." % ("stamp" if lead else "Stamp", yes, no)
    return lead + said if lead else said


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


def _norm_q(text):
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).split())


def _standard_question(ctx, out):
    """Identity's question on its standard, put to the owner, or None when the standard is met (PRD M3.3). A reading the
    step did not make (a department not in its cycle) asks nothing. A question Root already asked in J1 and the owner
    answered is not asked again (FI1.2): its point is taken as met."""
    if not isinstance(out, dict) or out.get("enough") is not False or ctx["how"].get("identity.enough") == SKIPPED:
        return None
    question = " ".join(str(out.get("question") or "").split())
    if not question or _norm_q(question) in {_norm_q(q) for q, _ in _j1_said(ctx["dept"])}:
        return None
    J = _j2()
    why = str(out.get("why") or "").strip() or "Identity's standard is not met yet: %s" % ", ".join(out.get("missing") or [])
    card = (J.asked(ctx["ref"], question, list(out.get("missing") or []), why, ctx["post"].get("n")) or {}).get("open_ask")
    # the question as its card keeps it, checked in plain words (M3.6): the line names the card and says the same
    question = next((str(a.get("text") or question) for a in W.asks(ctx["ref"]) if a["id"] == card), question)
    # a thread of its own: the request's thread may have closed on "filed in the Brief", and a post into it would be dropped;
    # the line names its card, and the chat leaves it to the card, which says the question once (M0.6)
    _tell(ctx["ref"], ctx["dept"], ctx["post"], "inform", dict({"word": "question", "done": question}, **({"card": card} if card else {})))
    return question


#: the defaults 'just do it' fills, for each point of the standard (PRD M3.3): from the kind, and Priority's template
def _standard_defaults(ref, points):
    """'Just do it' ends Identity's questions: each point asked about is filled from the kind's defaults where the record
    has nothing, and each default used is named. The record is the one record; a default written to it is a revision."""
    with W._lock(ref):
        d = W.dept(ref)
        k = W.KINDS.get(d.get("kind") or "website") or {}
        used, changed = [], False
        points = [STANDARD_ALIAS.get(p, p) for p in points or []]
        if "budget" in points:
            _priority_limits(ref)                          # Priority's own write, before the identity is read here
            d = W.dept(ref)
        for pt in [p for p in STANDARD if p in points]:
            if pt == "goal":
                if not str(d.get("goal") or "").strip():
                    d["goal"], changed = k.get("goal", "Work for {name}").format(name=d.get("name")), True
                    used.append("the kind's goal: " + d["goal"])
                else:
                    used.append("the goal as you said it")
            elif pt == "items":
                good = [i for i in d.get("done_items") or [] if isinstance(i, dict) and i.get("how") in W.DONE_HOW]
                if not good:
                    d["done_items"], changed = W.done_items(None, d.get("kind")), True
                    d["done"] = W.done_line(d["done_items"])
                    used.append("D1, the kind's done line: " + d["done"])
                else:
                    if not str(d.get("done") or "").strip():
                        d["done"], changed = W.done_line(good), True      # done stays the items' joined text
                    used.append("the done-when items Root drafted")
            elif pt == "rules":
                tagged = [r for r in d.get("rules") or [] if str(r.get("line") or "").strip() and r.get("tag") in W.RULE_TAGS]
                lines = {str(r["line"]).lower() for r in tagged}
                d["rules"] = tagged + [dict(r) for r in k.get("rules") or [] if str(r["line"]).lower() not in lines]
                changed = True
                used.append("the kind's rules")
            elif pt == "owner":
                if not str(d.get("owner") or "").strip():
                    d["owner"], changed = "the owner", True
                used.append("you, as the owner")
            elif pt == "budget":
                used.append("Priority's limits from its template")
            elif pt == "invented":
                used.append("what nobody gave stays out, to be confirmed")
        if changed:
            W.bump_identity(ref, d)
    return used or ["none were needed: the department starts on what you said"]


def _standard_answered(ctx, got):
    """The owner answered Identity's question on its standard (PRD M3.3). What it says to a gap code reads on the record
    is on the record already (identity_read, _standard_fill), and the answer joins the owner's words in the Brief; the
    standard was read again on both: still not met, and the next question is asked (FI1.1); met, and step 2 starts, and
    the tell names what the answer put on the record. 'Just do it' fills what is missing from the kind's defaults and
    starts step 2, and the tell names them."""
    ref, d, p, J = ctx["ref"], ctx["dept"], ctx["post"], _j2()
    words, aid = got["words"], got["answers"]
    ask = J.took(ref, aid, words, at=_words_at(ref, p)) or {}
    if got.get("hurry"):
        used = _standard_defaults(ref, ask.get("points") or [ask.get("missing")])
        d = W.dept(ref)
        J.assessed(ref, d, key="defaults-" + str(aid))
        _line_request(ref, d, _brief_text(ref).strip() or d.get("goal"), thread=None)
        _tell(ref, d, p, "inform", {"word": "request", "done": "Just doing it. Defaults used: %s. The department starts." % "; ".join(used)},
              thread=p["thread"])
        return {"said": "took 'just do it'; the department starts on the defaults: " + "; ".join(used)}
    row = _file_words(ref, d, "To Identity's question (%s): %s" % (str(ask.get("text") or "").rstrip("?"), words), "the owner's answer")
    question = _standard_question(ctx, ctx["bag"].get("identity.enough"))
    if question:
        return {"said": "took the owner's answer; Identity asks again: " + question, "filed": row["v"]}
    d = W.dept(ref)
    J.assessed(ref, d, key="answered-" + str(aid))
    _line_request(ref, d, _brief_text(ref).strip() or d.get("goal"), thread=None)
    # what the answer put on the record is named, as 'just do it' names its defaults
    taken = ["Taken: %s." % "; ".join(got["filled"])] if got.get("filled") else []
    _tell(ref, d, p, "inform", {"word": "request", "done": " ".join(["Thank you."] + taken + ["The identity is clear now; the department starts."])},
          thread=p["thread"])
    return {"said": "took the owner's answer; the standard is met and the department starts", "filed": row["v"]}


def _words_at(ref, p):
    """Where the owner said the words a post carries, {board, n}: their own post on this board, or, handed on by Root,
    their post at Root's front door. The question card those words answer keeps them, and the chat leaves that turn to
    the card (M0.6). None when no owner's post carries them."""
    pl = p.get("payload") or {}
    if p.get("src") == OWNER:
        return {"board": ref, "n": p["n"]}
    front, th = pl.get("front"), pl.get("front_thread")
    if p.get("src") == "Root" and front and th:
        said = next((q for q in board(front) if q["thread"] == th and q["src"] == OWNER), None)
        if said:
            return {"board": front, "n": said["n"]}
    return None


def identity_file(ctx, step, item):
    ref, d, p = ctx["ref"], ctx["dept"], ctx["post"]
    got = ctx["bag"]["identity.read"]
    words, first = got["words"], got["facts"]["first"]
    J = _j2()
    if J and first:
        # Identity asked what the department is for (thin first words, M0.5): words said in the chat answer it, and are
        # read below as the first words, against the same standard
        J.took_words(ref, words, at=_words_at(ref, p))
    if J and got.get("answers"):
        # the words answer Identity's question on its standard (M3.3): read against it again, then asked again or started
        return _standard_answered(ctx, got)
    if J and got.get("rule"):
        # the words answer Identity's question on the rules (M3.4): a rule ask, its tag and scope restated, for the stamp
        return _rule_answered(ctx, got)
    if J and not first and J.waiting_on_owner(ref):
        # Identity's own question is open (J2.1): these words answer it. They are written to the identity, the standard
        # is read again, and the department starts once it is met
        cur = J.answer(ref, words, at=_words_at(ref, p), go_on=False)
        d = W.dept(ref)
        if cur.get("state") == "waiting":
            return {"said": "took the owner's answer; Identity's next question is asked"}
        J.assessed(ref, d, key="answered")
        brief = W.latest(ref, W.artifacts_of(d)[0])
        text = W.read_files(ref, W.artifacts_of(d)[0], brief["v"]) if brief else {}
        _line_request(ref, d, " ".join(str(v) for v in text.values()).strip() or d.get("goal"), thread=None)
        # what the answer put on the record, or the defaults 'just do it' used, is named, as for Identity's own reading
        # (_standard_answered; found by a verifier 2026-10-26: 'just do it' here said only that the department starts)
        if cur.get("defaults"):
            done = "Just doing it. Defaults used: %s. The department starts." % "; ".join(cur["defaults"])
        else:
            done = " ".join(["Thank you."] + (["Taken: %s." % "; ".join(cur["taken"])] if cur.get("taken") else [])
                            + ["The identity is clear now; the department starts."])
        _tell(ref, d, p, "inform", {"word": "request", "done": done}, thread=p["thread"])
        return {"said": "took the owner's answer on the identity; the department starts"}
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
        if DONE_CUE.search(words):
            # when the department is done is its done-when items, never its goal (M3.4): a done_items ask of its own
            return _done_items_said(ctx, r, words)
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
    first = ctx["bag"]["identity.read"]["facts"]["first"]
    needs = [n for n in (out.get("needs") or []) if isinstance(n, str)]
    # what the person said they are not sure of stays out until they say (found live 2026-09-29: two unsure facts became
    # a page and went live; the question came after): the Brief says so, and the person is asked now
    unsure = [" ".join(str(u).split()) for u in (out.get("unsure") or []) if isinstance(u, str) and str(u).strip()] if d.get("kind") != "root" else []
    filed = words + (("\n\nNot confirmed (the owner is not sure; leave these out until the owner confirms them): " + "; ".join(unsure) + ".") if unsure else "")

    def ask_unsure():
        if unsure:
            _tell(ref, d, p, "inform", {"word": "facts", "holes": len(unsure),
                                        "done": "You said you are not sure of: %s. Say which are right and I will put them in; until then they stay out."
                                        % "; ".join(unsure)})

    # the first words that name nothing to build from get one question, not a site of eight generic pages and twelve
    # holes (found live 2026-09-29: the founder's own "New website" went live on a stamp and then asked for the facts)
    if first and out.get("thin") is True and d.get("kind") != "root":
        J = _j2()
        card = None
        if J and J.active(ref):
            # J2.1: not good enough to start on; Identity asks, and the next words are read against the same standard
            card = (J.questioned(ref, J.THIN, p.get("n")) or {}).get("open_ask")
        # a department is a site only when it is a website, as the question's card says (found by a verifier 2026-10-23:
        # an organic department's card asked what the department is for, and the line beside it what the site is for)
        said = {"word": "question", "done": "Say what the %s is for and about whom or what, and I will start: your words name nothing "
                "to build from yet." % ("site" if d.get("kind") == "website" else "department")}
        if card:
            # the question is a card in the chat (M0.6): the line stays on the record and names its card, and the chat
            # leaves it to the card, which says it once (found by a verifier 2026-10-23: the line, then the card, said it twice)
            said["card"] = card
        _tell(ref, d, p, "inform", said, thread=p["thread"])
        return {"said": "asked the owner what the department is for: the words name nothing to build from"}

    # words the agent reads as a standing rule are put back as a rule, never filed as an ask of the line (found live
    # 2026-09-29: "Nothing goes on the site without a source line under it" was asked for with "Put them on the site as
    # said?" and, stamped, went into the Brief under Asked since; the map's rules never changed and nothing checked it)
    rule = out.get("rule") if isinstance(out.get("rule"), dict) else None
    line = " ".join(str((rule or {}).get("line") or "").split()).rstrip(".")
    if rule and line and str(rule.get("tag")) in ("always", "refuse", "ask") and verdict != "refuse" and not first:
        if any(str(x.get("line") or "").lower() == line.lower() for x in d.get("rules") or []):
            _tell(ref, d, p, "inform", {"word": "request", "done": "the department already has this rule"}, thread=p["thread"])
            return {"said": "the department already has this rule: " + line}
        text = _rule_ask(ref, ctx["slot"], line, str(rule["tag"]), words, p["thread"], "A rule, as understood")
        _tell(ref, d, p, "request", {"word": "rule", "objective": text, "output": "a stamp or a refusal", "may_read": [],
                                     "boundaries": "this department, until the owner says otherwise"}, thread=p["thread"])
        return {"said": "restated the owner's words as a rule and put them back: " + line}

    # the internet is a given (founder, 2026-09-29): words that ask for it are filed like any other, and every agent step
    # can search and open pages; an engine is shaped only from an idea (the new-idea journey), never for reading the web
    if verdict == "go":
        row = _file_words(ref, d, filed, "the owner's goal" if first else "the owner's ask")
        _tell(ref, d, p, "inform", {"word": "request", "done": "filed in the %s" % W.artifacts_of(d)[0], "v": row["v"]}, thread=p["thread"])
        ask_unsure()
        # a department born with no engines (the organic kind): Adaptation shapes the line the words need, and the owner
        # hears the line will be put to them before anything runs (founder, 2026-09-30: "each of the adaptations doesn't
        # do any kind of template. It creates engines on the fly")
        organic = not (d.get("engines") or (W.KINDS.get(d.get("kind") or "website") or {}).get("line"))
        J = _j2()
        live = bool(J and J.active(ref))
        if first and live and not J.waiting_on_owner(ref):
            # J2 step 1: Identity reads the identity against its standard, and asks one question when it is not met (M3.3)
            question = _standard_question(ctx, ctx["bag"].get("identity.enough"))
            if question:
                ask_unsure()
                return {"said": "filed the owner's words and asked, before anything starts: " + question, "filed": row["v"]}
            # J2 steps 1 and 2: the identity is good enough to start on, and Adaptation is asked what the department does
            # next: the Library's line for a kind that has one, a line of its own for one that has none
            J.assessed(ref, d)
            _line_request(ref, d, filed, thread=p["thread"])
            if organic:
                _tell(ref, d, p, "inform", {"word": "line", "done": "Adaptation is shaping the engines your words need; Priority and Root check the line before anything runs."})
        elif not first and live and (J._state(ref) or {}).get("state") == "blocked":
            # the plan is blocked and the owner's new words go (M3.5): step 2 again, with Root's repairs at nought
            _reopen(ref, d, filed)
        elif first and organic and not live:
            post(ref, "Identity", "Adaptation", "request", {"word": "line", "words": filed, "objective": "shape the line the words need",
                                                            "output": "the engines, each with what it does, reads and writes", "may_read": ["Brief"],
                                                            "boundaries": "nothing runs before the owner stamps the line", "for": p["thread"]})
            # a thread of its own: the request's thread closed with "filed in the Brief", and a post into a closed thread is dropped
            _tell(ref, d, p, "inform", {"word": "line", "done": "Adaptation is shaping the engines your words need; you will be asked to stamp the line before anything runs."})
        if unsure:
            return {"said": "took the owner's words, leaving out what they are not sure of, and asked: " + "; ".join(unsure), "filed": row["v"]}
        return {"said": "took the owner's words: " + words, "filed": row["v"]}
    if verdict == "ask":
        # in the person's words: what reaches outside, and what a stamp does (found live 2026-09-28: the person's own
        # address came back as "This reaches outside the site"); an ask that needs something no engine has says what a
        # stamp does here: the department gets an engine for it (found live 2026-09-29: the email wording on a search)
        reach = _reaches(words, why)
        lead = "Your words reach outside the site%s. Put them on the site as said? %s" % (
            (": " + reach) if reach else "", _answers("go ahead", "to leave them out"))
        W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "request", "engine": "Identity", "slot": ctx["slot"],
                         "text": lead + " " + words, "why": why, "words": words, "needs": [], "status": "pending",
                         "created": W.now(), "thread": p["thread"]})
        _tell(ref, d, p, "request", {"word": "request", "objective": lead,
                                     "output": "a stamp or a refusal", "may_read": ["Brief"], "boundaries": words,
                                     "why": why}, thread=p["thread"])
        return {"said": "put the owner's words back to the owner: " + (why or words)}
    _tell(ref, d, p, "refuse", {"word": "request", "why": why or "it breaks a rule"}, thread=p["thread"])
    return {"said": "said no: " + (why or words)}


# ---- the front door: the person speaks with Root (founder, 2026-09-28) ----------------------------------------------
FRONT = [(re.compile(r"^\s*(?:start|set up|create|make|found)\s+(?:a |an |the |another )?(?:new )?[\w -]*?\bdepartment\b", re.I), "setup"),
         (re.compile(r"^\s*(?:stamp|yes|approve|approved|go ahead|ok)\b", re.I), "stamp"),
         (re.compile(r"^\s*(?:refuse|no|reject|rejected)\b", re.I), "refuse"),
         (re.compile(r"^\s*stop\b", re.I), "stop"),
         (re.compile(r"^\s*(?:start|resume)\b", re.I), "start")]


def _children(root_ref):
    return [d for d in W.list_depts() if d.get("parent") == root_ref]


#: the words of a bare yes or no: what the person says beyond them is an answer in words, not a stamp
ASSENT = {"yes", "ok", "okay", "sure", "stamp", "approve", "approved", "go", "ahead", "do", "it", "please", "thanks", "thank",
          "you", "no", "refuse", "reject", "rejected"}


def _stampable(a):
    """An ask a yes or a no in the chat decides: pending and not escalated. Identity's question takes words, never a
    stamp (M0.6), and an ask with options takes one of them (M3.5), so neither is the ask a yes picks (found 2026-10-23:
    'yes, a site for my bakery' failed Root's run; and a bare yes with a blocked plan's card open failed it again)."""
    return a["status"] == "pending" and not a.get("escalated") and a.get("kind") != "j2_identity" and not a.get("options")


def _question_of(dref):
    """Identity's open question on a department, as its cycle keeps it ({id, text, why, missing}), or None."""
    J = _j2()
    return J.open_question(dref) if J else None


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
    # a question of Sutra's is open: the next words answer it, whatever departments this Root already has
    open_q = _j1_enabled() and (_j1_record(ref) or {}).get("status") == "waiting"
    if open_q and wants in ("stamp", "refuse") and not any(
            _stampable(a) for r in [ref] + [c["ref"] for c in kids] for a in W.asks(r)):
        wants = "words"                              # "yes, free" answers Sutra's question when no stamp is waiting
    answering = open_q and wants == "words" and target is None
    if target is None and wants != "setup" and len(kids) == 1 and not answering:
        target = kids[0]
    # Identity's question is open on the department the words are for: a yes, ok or no that says more is the answer, in
    # words (M0.5; the department's Chat box sends here with its chip); a bare yes still looks for an ask to stamp
    if wants in ("stamp", "refuse") and target and _question_of(target["ref"]) and any(
            w not in ASSENT for w in re.findall(r"[a-z0-9']+", words.lower())):
        wants = "words"
    if target is None and wants == "words" and (not kids or answering):
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
        if _j1_enabled():
            # the answer comes from Setup's converse step, in this thread: one question, or that the words are clear
            row, _ = _j1_file_words(ref, d, words, "the owner's ask", (p.get("payload") or {}).get("request"), thread=th)
            return {"said": "filed a request for a department: " + words, "filed": row["v"]}
        row = _file_words(ref, d, words, "the owner's ask")
        post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "filed as a request; a new department is stamped by you, so an ask follows",
                                                "v": row["v"]}, thread=th)
        return {"said": "filed a request for a department: " + words, "filed": row["v"]}
    if wants in ("stamp", "refuse"):
        kids = [target] if target else [c["ref"] for c in _children(ref)]
        for tref in kids + [ref]:
            pend = [x for x in W.asks(tref) if _stampable(x)]
            a = pend[-1] if pend else None             # the latest ask: the one the person just saw
            if a:
                W.decide_ask(tref, a["id"], wants == "stamp")
                dn = (W.dept(tref) or {}).get("name")
                post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "%s: %s" % ("stamped" if wants == "stamp" else "said no", a["text"]),
                                                        "dept": tref, "from": dn}, thread=th, about={"dept": tref, "name": dn})
                return {"said": "%s the ask on %s" % ("stamped" if wants == "stamp" else "said no to", dn)}
        # nothing to stamp, and Identity's question is open: the person hears the question again, and that it takes words
        qref, q = next(((k, q) for k, q in ((k, _question_of(k)) for k in kids) if q), (None, None))
        if q:
            dn = (W.dept(qref) or {}).get("name")
            post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "Nothing is waiting for a stamp. %s asks you: %s Answer it in your own words."
                                                    % (dn, q["text"]), "dept": qref, "from": dn}, thread=th, about={"dept": qref, "name": dn})
            return {"said": "nothing waits for a stamp; %s's question takes words" % dn}
        # nothing to stamp, and a card with ways forward is open (a blocked plan, M3.5): it takes one of its options, so the
        # person hears which card waits and how it is answered, never a fault
        oref, card = next(((k, a) for k in kids + [ref] for a in W.asks(k) if a.get("options") and a["status"] == "pending"), (None, None))
        if card:
            dn = (W.dept(oref) or {}).get("name")
            post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "Nothing is waiting for a stamp. %s asks you to choose: %s Choose one of "
                                                    "the ways forward on its card, or say what to change." % (dn, card.get("title") or card["text"]),
                                                    "dept": oref, "from": dn}, thread=th, about={"dept": oref, "name": dn})
            return {"said": "nothing waits for a stamp; %s's card takes one of its options" % dn}
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


def _on_card(board_ref, p, cards):
    """A post that Identity's question card says (M0.6): the question itself, when the card stands in this chat, or the
    owner's words that answered it, which the card keeps under it. The chat leaves both to the card, so neither is said
    twice; the board keeps them as they were (found by a verifier 2026-10-23: the line, the card, the answer under it
    and the answer again as a turn)."""
    pl = p.get("payload") or {}
    # the owner's choice on an ask with options (M3.5) is said under its card, as 'You chose: ...'
    return pl.get("card") in cards["ids"] or (board_ref, p["n"]) in cards["words"] or bool(pl.get("option") and pl.get("ask") in cards["ids"])


def _cards(rows):
    """What the question cards in a chat carry: the ids of Identity's questions shown as cards (open, or answered with
    words), and where the owner said each answer."""
    ids, words = set(), set()
    for a in rows:
        if a.get("options") and a["status"] in ("pending", "chosen"):
            ids.add(a["id"])                              # an ask with options is a card too (M3.5); its choice is under it
            continue
        if a.get("kind") != "j2_identity" or not (a["status"] == "pending" or (a["status"] == "stamped" and a.get("answered"))):
            continue
        ids.add(a["id"])
        at = a.get("words_at") if isinstance(a.get("words_at"), dict) else {}
        if at.get("board") and at.get("n") is not None:
            words.add((at["board"], at["n"]))
    return {"ids": ids, "words": words}


#: a post as a chat prints it, its shape named once (fn_chat_view, chat_view and a department's own turns each add what
#: they need): who said it to whom and when, in which thread, its topic word, what it said (_line), and whether that line
#: is the owner's own words carried on by a function (quoted: Identity handing the owner's request to Adaptation,
#: Adaptation proposing it to Priority), which a screen shows as the owner said them, never in its own words (PRD M1.7)
TURN = ("n", "src", "dst", "msg_type", "at", "thread", "word", "line", "quoted")


def _quoted(p):
    """True when what a post says (_line) is the owner's own words, which the post carries whole (payload `words`)."""
    pl = p.get("payload") or {}
    return bool(pl.get("words")) and _line(p) == str(pl["words"])


def _post_turn(p, **more):
    """One post as a turn of a chat (TURN), with what the chat adds."""
    pl = p.get("payload") or {}
    turn = {"n": p["n"], "src": p["src"], "dst": p["dst"], "msg_type": p["msg_type"], "at": p["at"], "thread": p["thread"],
            "word": pl.get("word"), "line": _line(p) or str(pl.get("done") or pl.get("words") or ""), "quoted": _quoted(p)}
    turn.update(more)
    return turn


def _own_turns(dref, name, cards=None):
    """A department's own owner-facing turns (ER-10): what its Identity asked or told its owner in threads Root did not
    start, and the owner's own words and stamps there. A post that went to Root's board as well (via Root) is left to
    Root's copy, so the chat never counts it twice; a post a question card says is left to the card."""
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
        if cards and _on_card(dref, p, cards):
            continue
        out.append(_post_turn(p, dept=dref, name=name, own=True, link=pl.get("link"),
                              birth=p["n"] == 1 and p["src"] == OWNER and born_of_root))   # the words Root handed at the birth
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
    # what came of the words said here: the tells of the line on the Brief versions those words made (found live
    # 2026-09-29: "Put the top three first." said to Priority; the plan and the live tells landed only in the department chat)
    chains = {"brief.v%d" % int(p["payload"]["v"]) for p in posts
              if p["thread"] in mine and isinstance(p.get("payload"), dict) and p["payload"].get("word") == "request"
              and str(p["payload"].get("v") or "").isdigit()}
    turns = []
    for p in posts:
        pl = p.get("payload") or {}
        own = p["src"] == name or name in p["dst"] or to_fn(p)
        in_thread = p["thread"] in mine and (p["src"] == OWNER or OWNER in p["dst"])
        of_chain = OWNER in p["dst"] and pl.get("chain") in chains
        if not own and not in_thread and not of_chain:
            continue
        # Priority's counter is a proposal on the board; the chat says it as what it is, an ask for less (PRD M1.7)
        turns.append(_post_turn(p, think=False, counter=bool(pl.get("counter")), _k=(str(p["at"]), p["n"], 0)))
    for r in step_rows(ref):
        if r.get("engine") != name:
            continue
        sname = (step_def(str(r.get("step")))[1] or {}).get("name") or str(r.get("step"))
        if r.get("mode") == "gate":
            line = "%s: %s" % (sname, GATE_SAYS.get(str(r.get("answer")), r.get("answer") or ""))
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
    folded = []
    for t in turns:
        del t["_k"]
        # the same thought twice in a row is one line (found live 2026-09-29: "Gate the effect by rule: admit" three times)
        if t["think"] and folded and folded[-1]["think"] and folded[-1]["line"] == t["line"]:
            folded[-1]["at"] = t["at"]
            continue
        folded.append(t)
    return {"fn": name, "dept": ref, "name": d.get("name"), "turns": folded, "any": bool(folded)}


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
    kids = _children(root) if root else []
    refs = [about] if about else ([root] + [c["ref"] for c in kids] if root else [ref])
    asks, answered, chosen, rows = [], [], [], []
    for r in refs:
        dr = W.dept(r) or {}
        dn = dr.get("name")
        mine = W.asks(r)
        rows += mine
        # an ask with options shows the ones it offers now: no Stop on a department that is stopped (W.offered)
        asks += [dict(a, ref=r, dept=dn, **({"options": W.offered(dr, a)} if a.get("options") else {}))
                 for a in mine if a["status"] == "pending"]
        # Identity's questions the owner answered in words: the card stays in the chat with the answer under it (M0.6)
        answered += [dict(a, ref=r, dept=dn) for a in mine if a.get("kind") == "j2_identity" and a["status"] == "stamped" and a.get("answered")]
        # and an ask with options the owner chose one of: the card goes quiet, with the choice under it (M3.5)
        chosen += [dict(a, ref=r, dept=dn) for a in mine if a.get("options") and a["status"] == "chosen"]
    cards = _cards(rows)
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
            if _on_card(root, p, cards):                 # the question card says it, once
                continue
            turns.append(_post_turn(p, dept=dref, name=ab.get("name") or pl.get("from"), link=pl.get("link"),
                                    offer=pl.get("offer") if isinstance(pl.get("offer"), dict) else None))
        # the person's words at the front door carry the department they reached, as Root's own hand-over says
        # (found live 2026-09-28: a turn that named the department in its words showed no chip)
        for t in turns:
            if t["src"] == OWNER and t.get("word") == "front" and not t.get("dept"):
                later = next((u for u in turns if u["thread"] == t["thread"] and u["n"] > t["n"] and u.get("dept")), None)
                if later:
                    t["dept"], t["name"] = later["dept"], later.get("name")
    if root:
        for c in ([W.dept(about)] if about else kids):
            if c and c.get("ref") and c["ref"] != root:
                turns += _own_turns(c["ref"], c.get("name"), cards)
    elif d:
        turns += _own_turns(ref, d.get("name"), cards)  # a department with no Root: its own chat
    if root and not about:
        # the goal at a department's birth is the person's words said once at the front door; on the whole chat they
        # already stand as the front turn and the setup ask, so the birth copy is not said again (finding 3)
        turns = [t for t in turns if not t.get("birth")]
    turns.sort(key=lambda t: (str(t["at"]), t["n"]))
    return {"root": root, "about": about, "turns": turns, "asks": asks, "answered": answered, "chosen": chosen,
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
        W.add_engine(ref, a.get("engine"), shape=offer.get("shape"), by="the owner's stamp")
        _note_idea(ref, a.get("idea"), {"engine": a.get("engine"), "state": "built"})
        return {"said": "added the engine %s on the owner's stamp; it starts on its own trigger" % a.get("engine")}
    if a.get("kind") == "conflict":
        # J2.3: the owner settled what Identity could not; the plan goes to Root's check and onto the record
        J = _j2()
        if J:
            J._set(ref, step=5, state="checking")
        return _j2_settle(ref, ctx["dept"], [e for e in a.get("engines") or [] if isinstance(e, dict)], a.get("source") or "shaped",
                          a.get("words"), "the owner's stamp")
    if a.get("kind") == "line":
        # the line Adaptation shaped from the words, stamped: each engine born into the Library from Do with its instruction,
        # on the record in order; the first starts on the words now (founder, 2026-09-30: engines on the fly, no template).
        # A line with a fault (a name or slug the Library has, a name twice) is refused whole, never added in part (DeepSeek P2)
        engines = [e for e in (a.get("engines") or []) if isinstance(e, dict) and e.get("name")]
        bad = _line_faults(engines)
        if bad:
            _tell(ref, ctx["dept"], {"src": "Root" if ctx["dept"].get("root") else OWNER}, "inform",
                  {"word": "line", "done": "The line could not be set up: %s. Say the words again and I will shape it afresh." % "; ".join(bad)})
            return {"said": "could not set up the line: " + "; ".join(bad)}
        added, faults = [], []
        for e in engines:
            try:
                does = str(e.get("does") or "").strip()
                W.add_engine(ref, e["name"], shape={"name": e["name"], "use_case": does or e["name"], "does": does,
                                                     "instruction": ("%s\n\nThe goal, in the owner's words: %s" % (does, a.get("words") or "")).strip(),
                                                     "needs": ["internet"] if e.get("internet") else [], "reads": e.get("reads") or "Brief",
                                                     "writes": e.get("writes") or e["name"]}, by="the owner's stamp")
                added.append(e["name"])
            except Exception as exc:  # noqa: BLE001 -- one engine that cannot be born does not lose the rest; the owner hears which
                faults.append("%s (%s)" % (e.get("name"), exc))
        # a thread of its own: the ask's thread closed on the stamp, and a post into a closed thread is dropped
        _tell(ref, ctx["dept"], {"src": "Root" if ctx["dept"].get("root") else OWNER}, "inform",
              {"word": "line", "engines": added,
               "done": "Added the line %s; the first starts on your words now.%s" % (" -> ".join(added), (" Not added: " + "; ".join(faults)) if faults else "")})
        return {"said": "added the line on the owner's stamp: " + " -> ".join(added) + (("; not added: " + "; ".join(faults)) if faults else "")}
    if a.get("kind") == "rung":
        _, s = step_def(a["step"])
        move(ref, s, a["to"], "stamp " + a["id"], evidence=a.get("evidence"), form=a.get("form"))
        post(ref, "Identity", "Adaptation", "inform", {"word": "rung", "step": a["step"], "to": a["to"], "stamped": True})
        return {"said": "moved a step, on the owner's stamp: " + a["text"]}
    if a.get("kind") == "request":
        row = _file_brief(ref, ctx["dept"], a.get("words") or "", "the owner's ask, stamped")
        J = _j2()
        if J and J.active(ref) and (J._state(ref) or {}).get("state") == "blocked":
            # the plan is blocked and the owner stamped the words Identity put back: their go, as a go in the chat is, so
            # step 2 again with Root's repairs at nought, and the plan's card goes quiet with them (M3.5; found by a
            # verifier 2026-10-26: the stamp filed the words and left the plan blocked)
            _reopen(ref, W.dept(ref), a.get("words") or "")
            return {"said": "took the owner's words, stamped; the plan is shaped afresh", "filed": row["v"]}
        return {"said": "took the owner's words, stamped", "filed": row["v"]}
    if a.get("kind") == "rule":
        with W._lock(ref):
            d = W.dept(ref)
            if a.get("tag") == "goal":
                d.setdefault("goals", []).append({"goal": d.get("goal"), "until": W.now()})
                d["goal"] = a["line"]
                d["publish_asks_from"] = len(W.versions(ref, "Live site"))      # the first publish under a new goal asks again
            else:
                kept = list(d.get("rules") or [])
                if a.get("answers"):
                    # it answers Identity's question on the rules: a rule with no tag or no line gives way to it, as before
                    kept = [r for r in kept if str(r.get("line") or "").strip() and r.get("tag") in W.RULE_TAGS]
                d["rules"] = kept + [W.rule_row(a.get("tag") or "always", a["line"], a.get("words"), a.get("scope"))]
            W.bump_identity(ref, d)                      # who the department is changed: a revision, and its copy (M3.1)
        row = _file_brief(ref, d, ("The goal is now: " if a.get("tag") == "goal" else "A rule, from now on: ") + a["line"],
                          "a directive the owner stamped")
        if a.get("answers"):
            _j2_went_on(ref, a["answers"])               # it answered Identity's question on the rules: the cycle goes on (M3.4)
        return {"said": ("took a new goal: " if a.get("tag") == "goal" else "took a rule: ") + a["line"], "filed": row["v"]}
    if a.get("kind") == "blocked":
        return _blocked_chosen(ctx, a, pl)             # PRD M3.5: a way out of a blocked plan, applied by code
    if a.get("kind") == "done_items":
        # PRD M3.4: done-when changes as items, its own kind; the goal stays as it was
        d = W.apply_done_items(ref, a)
        _tell(ref, d, {"src": "Root" if d.get("root") else OWNER}, "inform",
              {"word": "done_items", "done": "Done when is now: %s." % "; ".join("%s %s" % (i["id"], i["text"]) for i in d["done_items"])})
        if a.get("answers"):
            _j2_went_on(ref, a["answers"])
        return {"said": "took the done-when items, stamped: " + "; ".join(i["id"] for i in d["done_items"])}
    if a.get("kind") == "finding":
        row = _file_brief(ref, ctx["dept"], "Correct this: " + str(a.get("found") or a.get("claim") or a["text"]),
                          "a finding the owner stamped")
        return {"said": "sent a finding back to the line", "filed": row["v"]}
    if a.get("kind") == "instructions":
        # PRD M2.2: the owner's own words for one of a function's instruction files, used from the next run on
        return _apply_instructions(ref, ctx["dept"], a)
    return {"said": "took the owner's stamp: " + a["text"]}


def _j2_went_on(ref, aid):
    """An ask that answered Identity's question was stamped (M3.4): the identity is read again, the next thing missing
    is asked, and with nothing missing the department starts (step 2) once its first words are filed. Started already,
    nothing more happens."""
    J = _j2()
    if not J or not J.active(ref) or int((J._state(ref) or {}).get("step") or 1) != 1 or identity_next(ref):
        return
    d = W.dept(ref)
    brief = _brief_text(ref).strip()
    if not brief or any(e.get("action") == "proposal.requested" for e in J.events(ref) if e.get("cycle_id") == J._state(ref).get("cycle_id")):
        return
    J.assessed(ref, d, key="stamped-" + str(aid))
    _line_request(ref, d, brief, thread=None)


def identity_drop(ctx, step, item):
    ref, pl = ctx["ref"], ctx["post"]["payload"]
    a = next((x for x in W.asks(ref) if x["id"] == pl.get("ask")), None)
    if a and a.get("kind") == "conflict":
        J = _j2()
        if J:
            J._set(ref, step=4, state="blocked")
        _blocked(ref, ctx["dept"], {"src": "Root" if ctx["dept"].get("root") else OWNER},
                 "The plan is dropped because you said no. Say what the department should do and I will have it shaped afresh.",
                 "The plan is dropped.", "You, on the plan Identity put to you", "you said no to the plan")
        return {"said": "dropped the plan because the owner said no"}
    if a and a.get("kind") in ("rule", "done_items") and a.get("answers"):
        # the owner said no to the rule that answered Identity's question (M3.4): Identity reads its standard again and
        # asks its question again, never dropped
        identity_next(ref)
    if a and a.get("kind") == "rung":
        _, s = step_def(a["step"])
        e = entry(ref, s)
        e["history"].append({"at": W.now(), "from": e["rung"], "to": e["rung"], "by": "refused by the owner", "evidence": a.get("evidence")})
        e.update({"trial": None, "pending": None})
        _save_entry(ref, e)
        post(ref, "Identity", "Adaptation", "inform", {"word": "rung", "step": a["step"], "to": a["to"], "stamped": False})
    return {"said": "took the owner's no" + (": " + a["text"] if a else "")}


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
        # "to be confirmed"); the owner's reply is a request like any other, and the line puts the facts in.
        # A department with an engine that reaches the internet asks that engine first, once per hole; what it cannot
        # find comes back to the owner (found live 2026-09-29: fees and timings asked of the person)
        lines = _finding_lines(ref, holes, None)
        d = ctx["dept"]
        engine = _web_engine(d)
        looked = set(d.get("looked_up") or [])
        fresh = [f for f in holes if str(f.get("claim")) not in looked]
        count = "%d thing%s" % (len(holes), "" if len(holes) == 1 else "s")
        if engine and fresh:
            text = ("The site says it does not know %s: %s. I have asked %s to look them up; what it cannot find stays to be confirmed."
                    % (count, "; ".join(lines) + (" ..." if len(holes) > len(lines) else ""), engine))
            with W._lock(ref):
                d = W.dept(ref)
                d["looked_up"] = sorted(looked | {str(f.get("claim")) for f in fresh})
                W.save_dept(ref, d, by="identity")
            _file_words(ref, d, "Look up: " + "; ".join(_finding_lines(ref, fresh, None)), "the holes Audit found, for " + engine)
        else:
            text = ("The site says it does not know %s: %s. Tell me here and I will put them in."
                    % (count, "; ".join(lines) + (" ..." if len(holes) > len(lines) else "")))
        _tell(ref, ctx["dept"], {"src": "Root" if ctx["dept"].get("root") else OWNER}, "inform",
              {"word": "facts", "done": text, "holes": len(holes), "about_version": pl.get("about_version")})
        said.append("asked %s for %d fact%s the site lacks" % (engine if engine and fresh else "the owner", len(holes), "" if len(holes) == 1 else "s"))
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
    if pl.get("word") == "line":
        # the department's workflows, proposed together: Priority has room for as many work engines as its template says
        names = [str(e.get("name")) for e in pl.get("engines") or [] if isinstance(e, dict) and e.get("name")]
        limit = int(((engine_def("Priority") or {}).get("template") or {}).get("line") or 6)
        return {"word": "line", "engine": None, "names": names, "limit": limit,
                "facts": {"word": "line", "room": 1 <= len(names) <= limit}}
    eng = pl.get("engine") or "Write"
    calls, _ = W._today_spend(ctx["ref"], eng)
    env = W.limit_of(ctx["dept"], eng)
    return {"word": pl.get("word"), "engine": eng, "facts": {"word": pl.get("word"), "room": calls * 2 < int(env.get("calls") or 0)}}


def priority_post(ctx, step, item):
    pl = ctx["post"]["payload"]
    got = ctx["bag"]["priority.bargain"]
    if pl.get("word") == "line":
        read, answer = ctx["bag"]["priority.read"], got.get("answer")
        names = list(read.get("names") or [])
        why = str(got.get("why") or "").strip()
        if answer == "counter":
            keep = [n for n in names if n in [str(k) for k in got.get("keep") or []]] or names[:int(read.get("limit") or 6)]
            if keep and len(keep) < len(names):
                row = post(ctx["ref"], "Priority", "Adaptation", "propose",
                           {"word": "line", "counter": True, "keep": keep, "why": why or "the envelope has room for %d of them" % len(keep)},
                           thread=ctx["post"]["thread"])
                return {"said": "asked for less on the line: keep " + " -> ".join(keep) if row else "the bargain reached its bound"}
            answer = "reject" if not keep else "accept"
        ok = answer == "accept"
        row = post(ctx["ref"], "Priority", "Adaptation", "accept-proposal" if ok else "reject-proposal",
                   {"word": "line", "why": why or ("the envelope has room" if ok else "the envelope has no room")}, thread=ctx["post"]["thread"])
        return {"said": ("said yes to" if ok else "said no to") + " the line " + " -> ".join(names) if row else "the bargain reached its bound"}
    ok = got.get("answer") == "accept"
    post(ctx["ref"], "Priority", "Adaptation", "accept-proposal" if ok else "reject-proposal",
         {"word": pl.get("word"), "step": pl.get("step"), "to": pl.get("to"), "form": pl.get("form"), "why": got.get("why")},
         thread=ctx["post"]["thread"])
    return {"said": ("said yes to" if ok else "said no to") + " a trial of " + str(pl.get("step"))}


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
    J = _j2()
    if J and J.done(ref):
        return {"said": "the goal is reached; Adaptation proposes nothing more"}
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
    e["history"].append({"at": W.now(), "from": e["rung"], "to": e["rung"], "by": "Priority said no to the trial", "evidence": None})
    e.update({"pending": None, "trial": None})
    _save_entry(ctx["ref"], e)
    return {"said": "dropped a trial of “%s”: Priority said no to it" % s["name"]}


def adapt_heard(ctx, step, item):
    pl = ctx["post"]["payload"]
    return {"said": "heard the ruling on " + str(pl.get("step")) + (": moved" if pl.get("stamped") else ": left as it is")}


def audit_pick(ctx, step, item):
    v = int(ctx["inp"]["v"])
    files = W.read_files(ctx["ref"], "Live site", v)
    # while the department lives its J2 cycle, done-when is read off Audit's reading, so every version is read (M0.3,
    # interim until M8 reads each done-when item); outside a cycle Audit drops in on a sample, as it always has
    sample = _j2_live(ctx["ref"]) or v <= 3 or v % 3 == 0
    return {"sample": sample, "v": v, "pages": sorted(k for k in files if k.endswith(".html"))}


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
        # the page's own sentences, not its navigation or its links (found live 2026-09-29: the nav's "Still To Be
        # Confirmed" read as twelve gaps)
        html = re.sub(r"<(nav|header|footer)\b[^>]*>.*?</\1>", " ", str(files[name]), flags=re.I | re.S)
        html = re.sub(r"<a\b[^>]*>.*?</a>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", html)
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


#: how a judge step was answered, when someone actually read the pages: its agent, its checklist, or a person by hand
READ_BY = ("model", "checklist", "stamped by the owner")


def audit_file(ctx, step, item):
    ref = ctx["ref"]
    mech, judged = ctx["bag"]["audit.mechanical"], ctx["bag"]["audit.judge"]
    faults = mech.get("faults") if "faults" in mech else (mech.get("notes") if not mech.get("ok") else [])
    found = [{"page": None, "claim": n, "severity": "high"} for n in faults or []]
    found += list(mech.get("holes") or [])
    found += [f for f in judged.get("findings") or [] if isinstance(f, dict) and f.get("claim")]
    # 'found nothing' is a reading only when the judge read the version: a judge skipped (not sampled) or answered by
    # its offline draft read nothing, and its empty list is no evidence (M0.3; found 2026-10-23: an offline department
    # reached its goal on a version no one read)
    how = ctx["how"].get("audit.judge")
    read = how in READ_BY
    why_not = None if read else {SKIPPED: "it was not sampled", "offline draft": "no model was there to read it"}.get(
        how, "how it was read is not on the record")
    if not found:
        if not read:
            return {"said": "did not read what went live (%s); nothing is said of it" % why_not, "filed": 0, "read": False,
                    "why_not_read": why_not}
        return {"said": "checked what went live; found nothing", "filed": 0, "read": True}
    high = [f for f in found if str(f.get("severity") or "").lower() == "high"]
    claim = str((high or found)[0]["claim"])
    post(ref, "Audit", "Identity", "inform", {"word": "finding", "claim": claim, "severity": "high" if high else "low",
                                              "findings": found[:12], "about_version": ctx["inp"]["v"]},
         about={"art": "Live site", "v": ctx["inp"]["v"]})
    return {"said": "found %s: %s" % ("something to put right" if high else "something to note", claim), "filed": len(found),
            "read": read, "why_not_read": why_not}


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
    what = "; ".join("%s: %s" % (n, _goal_of(ctx["ref"], n)[0]) for n in ready_now)
    waiting = "; ".join(a["text"] for a in W.asks(ctx["ref"]) if a["status"] == "pending") or "nothing"
    return _prompt("coordination", "tie", "tie", ctx["ref"], ready=", ".join(ready_now), what=what,
                   order=", ".join(ctx["table"]["functions"]), waiting=waiting)


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


def setup_read(ctx, step, item):
    files = W.read_files(ctx["ref"], "Request", ctx["inp"]["v"])
    words = files.get("request.md", "").strip()
    try:
        conversation = json.loads(files.get("request.json") or "null")
    except (TypeError, ValueError):
        conversation = None
    user_words = []
    if isinstance(conversation, dict):
        conversation = dict(conversation, selected_revision=ctx["inp"]["v"])
        # request.md is the readable J1 transcript ("User: ...", "Root: ...").
        # Setup shapes the department from the person's words, not from those
        # presentation labels or Root's clarification questions.
        user_words = [str(m.get("text") or "").strip() for m in conversation.get("messages") or []
                      if isinstance(m, dict) and m.get("actor") == "user"]
        words = " ".join(w for w in user_words if w).strip() or words
    kinds = library_kinds()
    # the departments this Root already has: a new one needs a name none of them has (found live 2026-09-29: Setup shaped
    # the same name as the one that existed, made nothing and said nothing)
    existing = [c.get("name") for c in _children(ctx["ref"]) if c.get("name")]
    # a name the owner gave on the Org sheet is the department's name (round 2, gap 6: Root named it itself, and a second
    # sheet's department took the same draft name and was folded into the first)
    named, _ = _sheet(user_words[0] if user_words else words)
    return {"words": words, "conversation": conversation, "conversing": isinstance(conversation, dict), "named": named,
            "facts": {"asked": bool(words), "kinds": ", ".join(kinds),
                                      "use_cases": "; ".join("%s: %s" % (k, u) for k, u in kinds.items()),
                                      "existing": ", ".join(existing) or "none", "named": named or "none"}}


CONVERSE = ("You are Sutra, the helper of the organisation. The owner wants a department. Ask what you need to know, one question at a "
            "time, until you can confidently create it: what it is for, for whom, and what it must deliver first. Ask only what "
            "the owner has not already said; never ask the same thing twice; one short question, no list. When you could create "
            "the department from what was said, say clear. Three or four questions are plenty: after that, say clear and decide.")


def _converse_examples():
    return [str(q) for q in (engine_def("Setup") or {}).get("clarification_questions") or [] if str(q).strip()]


def _setup_prompt(ctx, part, task=None, **inputs):
    """One part of Root's setup instructions, compiled (A1.16): root/v1's words and layout for root.setup.<part>, the
    interface's answer contract verbatim, and the inputs this code fills. `task` stands in for the default task when the
    Library's Setup template says its own."""
    import layer_schema as S
    ref = ctx.get("ref")
    if task is None:
        return layers.prompt(ref, "root", "setup", part, **inputs)
    P = layers.prompts
    words = P.words(ref, "root", "setup", part)
    words["task"] = str(task)
    return P.compile_layout(layers.impl(ref, "root", ctx.get("dept")).LAYOUT["setup"][part], words,
                            S.PROMPTS["root"]["setup"][part]["returns"], inputs, P.who("root", "setup", part))


def p_setup_converse(ctx, step, item):
    """The converse step's inside (S-24): an instruction, the examples, and the conversation so far. No question lives in
    code. The words are root/v1's (A1.16); the Library's Setup template says its own instruction in their place when it
    sets one."""
    got = ctx["bag"]["setup.read"]
    conversation = got.get("conversation") or {}
    lines = "\n".join("%s: %s" % ("OWNER" if m.get("actor") == "user" else "SUTRA", m.get("text") or "")
                      for m in conversation.get("messages") or [] if isinstance(m, dict))
    return _setup_prompt(ctx, "converse", (engine_def("Setup") or {}).get("converse_instruction") or None,
                         examples=" | ".join(_converse_examples()) or "none", library=got["facts"].get("use_cases") or "",
                         existing=got["facts"].get("existing") or "none", conversation=lines or "OWNER: " + str(got.get("words") or ""))


def d_setup_converse(ctx, step, item):
    """The draft under the AI: with no model, the words are read by a plain test and the examples are asked in turn."""
    conversation = (ctx["bag"].get("setup.read") or {}).get("conversation")
    if not isinstance(conversation, dict):
        return {"verdict": "clear", "question": ""}
    messages = conversation.get("messages") or []
    clear, _ = _j1_clear(messages)
    if clear:
        return {"verdict": "clear", "question": ""}
    examples = _converse_examples() or ["What should this department achieve?"]
    asked = sum(1 for m in messages if m.get("actor") == "root")
    return {"verdict": "ask", "question": examples[min(asked, len(examples) - 1)]}


def c_setup_converse_is_valid(ctx, step, item, out):
    question = " ".join(str(out.get("question") or "").split())
    ok = out.get("verdict") == "clear" or (out.get("verdict") == "ask" and bool(question))
    return _verdict(ok, "one question or clear", "converse must return one question or clear")


def setup_say(ctx, step, item):
    """The converse step's covering: Sutra's question is posted to the owner and the run ends there, or the words are
    handed on to Shape. "Just do it" ends the questions when the owner has said anything to build from, and the defaults
    taken are kept to be said; with nothing said at all, the one thing no default covers is still asked."""
    ref = ctx["ref"]
    got = ctx["bag"].get("setup.read") or {}
    conversation = got.get("conversation")
    if not isinstance(conversation, dict):
        return {"run": True, "said": "the words go on to Shape"}
    out = ctx["bag"].get("setup.converse") or {}
    users = [str(m.get("text") or "") for m in conversation.get("messages") or [] if m.get("actor") == "user"]
    hurry = bool(users) and bool(JUST_DO_IT.fullmatch(users[-1]))
    said = " ".join(users[:-1]).strip() if hurry else " ".join(users).strip()
    ask = out.get("verdict") == "ask"
    question = " ".join(str(out.get("question") or "").split())
    defaults = []
    if hurry and said:
        ask, defaults = False, list(J1_DEFAULTS)
    elif hurry:
        ask, question = True, question or (_converse_examples() or ["What should this department achieve?"])[0]
    with W._lock(ref):
        state = _j1_record(ref)
        if not isinstance(state, dict) or state.get("id") != conversation.get("id"):
            state = dict(conversation)
        newer = sum(1 for m in state.get("messages") or [] if m.get("actor") == "user") > len(users)
        if newer:
            return {"run": False, "why": "the owner said more; the newer words are read next",
                    "said": "left this version: the owner said more, and the newer words are read next"}
        messages = list(state.get("messages") or [])
        if ask:
            if not (messages and messages[-1].get("actor") == "root" and messages[-1].get("text") == question):
                messages.append({"id": "m-" + uuid.uuid4().hex[:12], "actor": "root", "text": question, "at": W.now()})
            state.update({"messages": messages, "status": "waiting", "outstanding_question": question, "defaults_applied": []})
        else:
            state.update({"status": "clear", "outstanding_question": None, "defaults_applied": defaults})
        state.pop("selected_revision", None)
        W._write(W.ddir(ref) / "j1-state.json", state)
    pl = {"word": "question" if ask else "request", "v": ctx["inp"]["v"],
          "done": question if ask else "That is clear. I am shaping the department now."}
    if not post(ref, "Identity", OWNER, "inform", pl, thread=state.get("thread")):
        post(ref, "Identity", OWNER, "inform", pl)          # the front thread closed at its bound: the answer still reaches the chat
    got["conversation"] = dict(state, selected_revision=ctx["inp"]["v"])
    return {"run": not ask, "why": "asked the owner one question" if ask else "", "question": question if ask else "",
            "said": "asked the owner: " + question if ask else "the words are clear; they go on to Shape"}


def p_setup_shape(ctx, step, item):
    """The shape step's inside: the owner's words, the Library's kinds and the departments this Root has, asked for a name,
    a kind, a goal and done-when items. The words are root/v1's (A1.16)."""
    got = ctx["bag"]["setup.read"]
    org = (ctx["dept"].get("org") or {}).get("name") or ctx["dept"].get("name")
    return _setup_prompt(ctx, "shape", org=org, words=got["words"], named=got.get("named") or "none", kinds=got["facts"]["kinds"],
                         use_cases=got["facts"].get("use_cases") or "", existing=got["facts"].get("existing") or "none")


def d_setup_shape(ctx, step, item):
    got = ctx["bag"]["setup.read"]
    org = (ctx["dept"].get("org") or {}).get("name") or ctx["dept"].get("name")
    conversation = got.get("conversation") or {}
    user = [m.get("text", "") for m in conversation.get("messages") or [] if m.get("actor") == "user"]
    useful = " ".join(x for x in user if not JUST_DO_IT.fullmatch(x)).strip() or got["words"]
    named, said = _sheet(useful)
    if named and said:
        useful = said                                   # the sheet's words after its name are the goal
    second = SECOND.search(useful)
    first = useful[:second.start()].strip(" ,;.") if second else useful
    website = bool(re.search(r"\b(website|web site|landing page|blog)\b", first, re.I))
    return _shape_norm({"name": named or "%s %s" % (org.replace(" Root", ""), "Website" if website else "Department"),
                        "kind": "website" if website else "organic", "goal": first or useful, "purpose": first or useful,
                        "second": second.group(1).strip(" .") if second else ""})


def _shape_norm(out):
    """What the code knows and the AI need not say: a kind's route and its template reference follow from the kind (found
    live 2026-10-07: the model answered the reference as {"id": "website", "version": "1"}, the check wanted
    {"id": "department/website", "version": 1}, and no department was ever made)."""
    out = dict(out or {})
    kind = " ".join(str(out.get("kind") or "").split()).lower().split("/")[-1]      # "department/website" names the kind website
    out["kind"] = kind
    out["name"] = " ".join(str(out.get("name") or "").split())[:80]
    out["goal"] = " ".join(str(out.get("goal") or "").split())[:2000]
    out["purpose"] = " ".join(str(out.get("purpose") or out["goal"]).split())[:400]
    out["second"] = " ".join(str(out.get("second") or "").split())[:400]
    organic = kind == "organic"
    out["route"] = "organic" if organic else "template"
    out["template_ref"] = {} if organic else {"id": "department/%s" % kind, "version": 1}
    # Root's done-when items (PRD M3.2): numbered by the code, how and level as the agent said them for the covering to
    # judge; none drafted (offline, or a model that gave none), and the kind's done line is D1
    items = W.done_items(out.get("done_items"), kind)
    out["to_be_confirmed"] = W.to_confirm(items)
    out["done_items"] = [{k: v for k, v in i.items() if k != "confirm"} for i in items]
    return out


def _reconcile_j1_tells(root_ref):
    """Project each persisted birth summary to Root's board exactly once. Setup's own run, the motor's sweep and the
    next-due read all call this; the look at the board and the post are one step under Root's lock, so two of them never
    both find the board empty (found live 2026-10-07: the birth told twice in 2 of 13 foundings)."""
    for child in _children(root_ref):
        if not isinstance(child.get("pending_final_tell"), dict):
            continue
        with W._lock(root_ref):
            fresh = W.dept(child["ref"]) or child
            pending = fresh.get("pending_final_tell")
            if not isinstance(pending, dict) or not pending.get("operation"):
                continue
            operation = pending["operation"]
            if not any((p.get("payload") or {}).get("operation") == operation for p in board(root_ref)):
                try:
                    post(root_ref, "Identity", OWNER, "inform", pending,
                         about={"dept": child["ref"], "name": child["name"]})
                except Exception:  # the durable pending projection is retried by the next sweep
                    continue
            founding_state = dict(fresh.get("founding") or {})
            checkpoints = list(founding_state.get("checkpoints") or [])
            if "final_tell" not in checkpoints:
                checkpoints.append("final_tell")
            founding_state["checkpoints"] = checkpoints
            fresh["founding"] = founding_state
            fresh.pop("pending_final_tell", None)
            W.save_dept(child["ref"], fresh, by="root")


def setup_make(ctx, step, item):
    """Root makes the department: under itself, with its charter, its functions' templates, its record and its goal."""
    shape = _shape_norm(ctx["bag"]["setup.shape"])
    named = (ctx["bag"].get("setup.read") or {}).get("named")
    if named:
        # the owner named the department on the Org sheet: the covering keeps that name, whatever the agent shaped
        shape = dict(shape, name=named)
    bad = W.birth_faults(shape["kind"])
    if bad:
        # the kind's line breaks a standard Root holds every line to (PRD A1.14): founding makes nothing, and the covering
        # fails naming it, so no registry entry is left without a record behind it
        return {"ref": None, "name": shape["name"], "kind": shape["kind"], "goal": shape["goal"], "created": False,
                "refused": "this kind's line breaks Root's standards: " + "; ".join(bad)}
    import founding
    conversation = (ctx["bag"].get("setup.read") or {}).get("conversation") or {}
    live = _j1_record(ctx["ref"]) if conversation else None
    if isinstance(live, dict) and live.get("id") == conversation.get("id"):
        # what the covering wrote after this version was filed (Sutra's last question, the defaults taken) rides along
        conversation = dict(live, selected_revision=conversation.get("selected_revision"))
    offer = ({"label": shape["second"][:80], "words": "Set up another department: " + shape["second"]} if shape.get("second") else None)
    if offer:
        conversation = dict(conversation, suggested_next=offer)     # the child's goal context says what was left for later
    same = next((d for d in _children(ctx["ref"]) if str(d.get("name") or "").lower() == str(shape["name"]).lower()), None)
    if same and (same.get("kind") != shape["kind"] or (same.get("template_ref") or None) != (shape.get("template_ref") or None)):
        base, n = shape["name"], 2
        occupied = {str(d.get("name") or "").lower() for d in _children(ctx["ref"])}
        while ("%s %d" % (base, n)).lower() in occupied:
            n += 1
        shape = dict(shape, name="%s %d" % (base, n))
    made = founding.spawn(ctx["ref"], shape["name"], shape["kind"], shape["goal"], owner=ctx["dept"].get("owner") or "the owner",
                          goal_context=conversation, template_ref=shape.get("template_ref") or None, route=shape.get("route"),
                          done_items=shape.get("done_items"), to_confirm=shape.get("to_be_confirmed"))
    if made.get("existing"):
        # the agent named a department this Root already has: the person is told, and the words go to that department
        # as Root hands words on (found live 2026-09-29: a stamp that ended in silence)
        ref, target, name, words = ctx["ref"], made["ref"], made["name"], shape["goal"]
        post(target, "Root", "Identity", "request", {"word": "request", "words": words, "objective": words, "output": "the Brief's next version",
                                                     "may_read": ["Brief"], "boundaries": "inside the department's goal and rules", "front": ref})
        post(ref, "Identity", OWNER, "inform", {"word": "request", "done": "%s already exists; your words were handed to it" % name,
                                                "dept": target, "from": name}, about={"dept": target, "name": name})
    if not made.get("existing"):
        child = W.dept(made["ref"]) or {}
        engines = child.get("engines") or []
        first = engines[0] if engines else "Adaptation will shape the first engine"
        operation = made["operation_id"]
        line = "%s is set up with %s. First: %s." % (made["name"], ", ".join(engines) if engines else "no born work engines", first)
        # what Root stamped includes the done-when items it drafted, and the birth tell names them (PRD M3.2)
        items = child.get("done_items") or []
        if items:
            line += " Done when: %s." % "; ".join("%s %s%s" % (i["id"], str(i["text"]).rstrip("."),
                                                                " (to confirm)" if any(c.get("item") == i["id"] for c in child.get("to_be_confirmed") or []) else "")
                                                   for i in items)
        defaults = conversation.get("defaults_applied") or []
        if defaults:
            line += " Defaults used: %s." % "; ".join(defaults)
        tell = {"word": "department", "done": line, "dept": made["ref"], "from": made["name"], "operation": operation}
        if offer:
            # J1.5: the first is made, the second is offered: a chip the owner can click, never made unasked
            tell["done"] = line + " You also asked for a second department (%s): say so and I will set it up." % offer["label"]
            tell["offer"] = offer
        child["pending_final_tell"] = tell
        W.save_dept(made["ref"], child, by="root")
        _reconcile_j1_tells(ctx["ref"])
    state = dict(conversation, status="completed", outstanding_question=None, department=made["ref"])
    state.pop("selected_revision", None)
    if offer:
        state["suggested_next"] = offer
    W._write(W.ddir(ctx["ref"]) / "j1-state.json", state)
    return made


def setup_file(ctx, step, item):
    made = ctx["bag"]["setup.make"]
    text = "# %s\n\nref: %s\nkind: %s\ngoal: %s\nset up by Root %s\n" % (made["name"], made["ref"], made["kind"], made["goal"],
                                                                         "now" if made.get("created") else "earlier")
    return {"files": {"department.md": text}, "check": {"ok": True, "notes": ["%s is set up and On" % made["name"]]}}


def c_department_is_shaped(ctx, step, item, out):
    shaped = _shape_norm(out)                             # the route and the template reference are the code's, from the kind
    ok = bool(shaped["name"] and shaped["kind"] in W.KINDS and shaped["kind"] != "root" and shaped["goal"])
    if not ok:
        return _verdict(False, "", "no name, a kind the Library lacks, or no goal")
    # each done-when item Root drafted says how it is checked and what it is (PRD M3.2, MK-2)
    bad = ["%s says how it is checked as %r" % (i["id"], i["how"]) for i in shaped["done_items"] if i["how"] not in W.DONE_HOW]
    bad += ["%s says its level as %r" % (i["id"], i["level"]) for i in shaped["done_items"] if i["level"] not in W.DONE_LEVELS]
    return {"ok": not bad, "notes": bad or ["a name, a kind the Library has, a goal, and %d done-when items, each with how and level"
                                             % len(shaped["done_items"])]}


def c_department_is_made(ctx, step, item, out):
    """The child exists under Root, on the runtime, and its goal reached it: the child's own Identity files the goal when
    the child runs, which is its business, not Root's."""
    if isinstance(out, dict) and out.get("refused"):
        return {"ok": False, "notes": [str(out["refused"])]}
    d = W.dept(out.get("ref")) if isinstance(out, dict) and out.get("ref") else None
    ok = bool(d) and d.get("runtime") == 2 and d.get("parent") == ctx["ref"] and bool(W.requests(out["ref"]))
    return _verdict(ok, "the department exists under Root, on the runtime, and has its goal", "the department was not made under Root")


# ---- an engine from an idea (TPL-1 slice 2, founder 2026-09-29: "the engines are supposed to be created by the five
# functions of the department ... created on the fly, or there is a default one") ---------------------------------------
def engine_from_shape(ref, got, words):
    """The engine Adaptation's agent named for an idea, checked by code and nothing more: a Library pick that exists, is
    a work engine and is not on the record; else a shape (a name, what it does, what it needs, each need one the runtime
    knows), to be born from Do on the stamp with the idea as its instruction; None when the agent named none."""
    d = W.dept(ref) or {}
    have = set(d.get("engines") or [x[0] for x in W.engines_of(d)])
    pick = " ".join(str(got.get("pick") or "").split())
    e = defs()["engines"].get(pick)
    if pick and e and e.get("kind") == "work" and e.get("from_template") and pick not in have and pick != "Setup":
        return {"pick": pick, "use_case": e.get("use_case"), "does": e.get("description")}
    shape = got.get("engine") if isinstance(got.get("engine"), dict) else None
    name = " ".join(str((shape or {}).get("name") or "").split())[:40]
    if not shape or not name or name in have:
        return None
    does = " ".join(str(shape.get("does") or "").split())
    needs = [n for n in (shape.get("needs") or []) if isinstance(n, str) and n in NEEDS]
    return {"shape": {"name": name, "use_case": (does or str(words or ""))[:300], "does": does[:200], "instruction": str(words or "")[:2000],
                      "needs": needs, "reads": "Brief", "writes": name}}


def born_template(name, shape, ref):
    """An engine shaped on the fly, born into the Library from Do: the same three steps (read, do, file) under its own
    ids, its use case and instruction from the idea, what it writes filed under the Default artifact template; made_by
    says which department it was born for and that Adaptation shaped it (PRD M4.1: engines come from Adaptation, never
    from Root). Validated with the rest; refused, it leaves no file."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    if not slug:
        raise ValueError("name the engine")
    user = user_templates_dir()
    user.mkdir(parents=True, exist_ok=True)
    p = user / (slug + ".json")
    if p.exists() or (TEMPLATES_DIR / (slug + ".json")).exists():
        raise ValueError("the Library already has a template at %s" % p.name)
    do = json.loads((TEMPLATES_DIR / "do.json").read_text(encoding="utf-8"))
    t = dict(do)
    does = str(shape.get("does") or shape.get("use_case") or "")
    t.update({"id": "engine/" + slug, "name": name, "version": 1, "use_case": str(shape.get("use_case") or does)[:300],
              "description": does[:200] or ("does what the idea asked: " + name), "instruction": str(shape.get("instruction") or "")[:2000],
              "reads": str(shape.get("reads") or "Brief"), "writes": str(shape.get("writes") or name)[:40],
              "made_by": {"by": "Adaptation", "dept": ref, "at": W.now(), "idea": str(shape.get("instruction") or "")[:300]}})
    t["start"] = {"on": [{"kind": "version", "of": t["reads"]}], "unless": list((do.get("start") or {}).get("unless") or [])}
    t["steps"] = [dict(s, id=slug + "." + s["id"].split(".", 1)[1]) for s in do["steps"]]
    for s in t["steps"]:
        if s.get("only_if"):                                   # a condition on Do's own bag follows the ids
            s["only_if"] = re.sub(r"^do\.", slug + ".", str(s["only_if"]))
    if _writes_pages(t):
        # an engine whose artifact is pages plans them in one small call and writes one page per call, four side by side, as
        # the website kind's Write does; one answer for every page trimmed a growing site (findings 60, 63)
        steps = []
        for s in t["steps"]:
            if s.get("prompt") == "do_make":
                steps.append({"id": slug + ".plan", "name": "Plan the pages", "nature": "make", "born": "C0", "ceiling": "C1",
                              "prompt": "do_pages", "draft": "do_pages_draft", "out": {"pages": "list"}, "check": "pages_are_named"})
                steps.append({"id": slug + ".list", "name": "List the pages", "nature": "transform", "born": "C2",
                              "code": "do_pages_list", "check": "list_has_pages"})
                steps.append({"id": slug + ".page", "name": "Write a page", "nature": "make", "born": "C0", "ceiling": "C1",
                              "each": slug + ".list.pages", "side_by_side": 4, "prompt": "do_page", "draft": "do_page_draft",
                              "out": {"file": "str", "html": "str"}, "check": "page_is_html"})
            else:
                steps.append(s)
        t["steps"] = steps
    # the need step weighs the OWNER'S words against what was filed (finding 38: a search re-run on every Brief version); an
    # engine that reads another engine's filing runs on every new version of it, which is its trigger (found on the Beta
    # 2026-09-30: Launch read Pages v2 and judged the new pages 'not needed', so the site never took them)
    if t["reads"] != "Brief":
        t["steps"] = [s for s in t["steps"] if not s["id"].endswith(".need")]
    needs = [n for n in (shape.get("needs") or []) if isinstance(n, str) and n in NEEDS]
    tools = list(dict.fromkeys(tool for n in needs for tool in NEEDS[n]))
    t["needs"] = needs
    if tools:
        # what the agent said the idea needs, met by the model's own tools: the make step gets them and the time they take
        for s in t["steps"]:
            if s.get("prompt"):
                s["tools"] = tools
                s["timeout_s"] = 600
    import layer_schema as S
    S.check("engine.template", t, ref=ref, owner="root")          # the template as the interface types it, before the file is written (A1.20)
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


# ---- the line changes: each function does its own part (PRD M4.1) -----------------------------------------------------
# Root records a plan; it writes neither Coordination's table nor Priority's limits. When an engine joins the department,
# by a registered plan or by the owner's stamp on an engine an idea asked for (J5), Coordination writes its own table
# and Priority gives the engine its limit, each in its own handler on the fixed trigger "an engine is born", run in
# place on the code rung; each decision is a row of the function whose handler it is (_ask_rule).
def _period(every_s):
    s = int(every_s or 0)
    for unit, n in (("day", 86400), ("h", 3600), ("min", 60)):
        if s >= n and s % n == 0:
            return "%d %s" % (s // n, unit)
    return "%d s" % s


def slot_of(ref, name, rs=None):
    """An engine's slot as Coordination keeps it in its timetable (PRD M4.3), from the engine's own start: 'after
    <artifact> vN', N the version it runs on next (the latest one it has not run on, else the one after the latest), or
    'every <period>'. With the trigger it reads: of, checked, every_s. next_due keeps reading start.on itself."""
    e = engine_def(name) or {}
    trig = next((t for t in (e.get("start") or {}).get("on") or [] if t.get("kind") in ("version", "timer")),
                ((e.get("start") or {}).get("on") or [{}])[0])
    if trig.get("kind") == "version":
        rs = W.runs(ref) if rs is None else rs
        done = {r.get("slot") for r in rs if r.get("status") in ("ok", "failed", "skipped")}
        cur = W.latest(ref, trig["of"], passed=bool(trig.get("checked")))
        v = cur["v"] if cur and W._slot_id(name, trig["of"], cur["v"]) not in done else (cur["v"] + 1 if cur else 1)
        return {"on": "after %s v%d" % (trig["of"], v), "of": trig["of"], "checked": bool(trig.get("checked")), "v": v}
    if trig.get("kind") == "timer":
        return {"on": "every " + _period(trig.get("every_s")), "every_s": trig.get("every_s")}
    return {"on": "on a post to it"}


def _timetable(ref, t):
    """One slot for each engine of the line, from its own start, with its window; an engine that had a slot keeps the
    time it has had one since."""
    d, rs = W.dept(ref) or {}, W.runs(ref)
    was = {r.get("engine"): r for r in t.get("timetable") or [] if isinstance(r, dict)}
    return [timetable_row(name, slot_of(ref, name, rs), (d.get("windows") or {}).get(name) or 30, (was.get(name) or {}).get("since"))
            for name in t.get("line") or []]


def grow_line(ref, name, before=None):
    """Coordination's line, on the record, gains the engine (before another when said, as Research goes before Plan); the
    born copy is written first for a department that had none. Written by Coordination, on the owner's stamp; the engine
    is kept as one the owner added (grown), so a later registration merges it in (PRD M4.2)."""
    t = coordination(ref)
    line = list(t.get("line") or [])
    if name not in line:
        if before in line:
            line.insert(line.index(before), name)
        else:
            line.append(name)
        t["line"] = line
    t["grown"] = list(t.get("grown") or []) + ([name] if name not in (t.get("grown") or []) else [])
    t["left_out"] = [r for r in t.get("left_out") or [] if isinstance(r, dict) and r.get("engine") != name]
    t["timetable"] = _timetable(ref, t)                    # the grown engine gains its slot (PRD M4.3)
    return _put_table(ref, t, "the owner's stamp")


def _check_line(ref, d, t, standing=()):
    """Coordination's line, about to be written, against Root's standards for a write (PRD A1.14, A1.20): the workflow is the
    plan Root registered last (its engines and its source), and the line and the engines the owner added (grown) are what
    it is held against, so a line that names an engine no registered plan holds, which the owner did not add, is not
    written without a word. (The line itself is not the workflow: a standard that counted the workflow's own engines as
    registered would pass every line.) A department with no registered plan is read as the line it is given.

    Registered means named by the plan registered last, or added by the owner (PRD M4.2: the line is what was granted).
    The department's record is not a registration: an engine the plan left out, or Priority cut in a counter, stays on the
    record and is never on the line, so a table that puts it back is one row. Root's own check of a registration reads
    the record as it stands and lets the line a department was born with stand a moment longer (workflow_schema.
    line_is_registered); Coordination, writing the line itself, is held to the plan, so the standard reads a department
    view with no record engines and the last registered plan alone.

    `standing` is what stood on the line before a registration that is not full adds to it: it was held to the plan
    when it was written, so it stays, and only what the call adds must be named by the plan registered last.

    Warn mode leaves one row, the failed standards together, and the write goes through; refuse mode raises
    layer_schema.SchemaFault after the row, and nothing is written."""
    import layer_schema as S
    plans = [w for w in d.get("workflows") or [] if isinstance(w, dict) and w.get("engines")]
    grown = list(t.get("grown") or [])
    ctx = {"line": list(t.get("line") or []), "grown": grown + [n for n in standing if n not in grown]}
    source = plans[-1].get("source") if plans else None
    registered = [str(n) for n in plans[-1]["engines"]] if plans else ctx["line"]
    view = dict(d, engines=[], workflows=plans[-1:])
    rows = S.validate_workflow(S.as_workflow(registered, source if source in S.SOURCES else "library", d), "write", view, ctx)
    failed = [r for r in rows if not r["passed"]]
    failed.sort(key=lambda r: r["check"] == "workflow_meets_standards")      # a standard says it in words; the shape row follows
    S.report("coordination.table", ["%s: %s" % (r["check"], r["why"]) for r in failed], ref=ref, owner="coordination")


def set_line(ref, engines, version=None, full=True):
    """Coordination's line, on the record, after Root registered a plan (PRD M4.2: the line is what was granted). On the
    cycle's first registration, and on any later one that names the whole line (full), the line is the plan in its
    order, and an engine the owner added through J5 (grown) is merged in where it stood. An engine on the department's
    record that the plan left out stays on the record, in_line false, and never runs. A registration that is not full
    adds its engines to the line (none is today: a round of Pursue never registers a line). Written by Coordination,
    with the plan's version, so the table says which registration it follows, and with its timetable: one slot for
    each engine of the line (PRD M4.3). The line is checked as a write before it is put (_check_line): an engine the plan
    registered last does not name, which the owner did not add, is not on a line Coordination writes, though the record
    still holds it."""
    t = coordination(ref)
    d = W.dept(ref) or {}
    old, plan = list(t.get("line") or []), [str(n) for n in engines or [] if n]
    whole = full or not t.get("registered")
    if whole:
        line = list(plan)
        for g in [g for g in t.get("grown") or [] if g not in line and g in (d.get("engines") or [])]:
            after = next((n for n in old[old.index(g) + 1:] if n in line), None) if g in old else None
            if after:
                line.insert(line.index(after), g)
            else:
                line.append(g)
    else:
        line = old + [n for n in plan if n not in old]
    was = {r.get("engine"): r for r in t.get("left_out") or [] if isinstance(r, dict)}
    left = [left_out_row(n, (was.get(n) or {}).get("since")) for n in d.get("engines") or [] if n not in line]
    # the plan's version; a registration that names none keeps the one the table follows, never None (PRD M4.1)
    t.update({"line": line, "left_out": left, "registered": version if version is not None else t.get("registered")})
    t["timetable"] = _timetable(ref, t)                    # one slot for each engine of the line (PRD M4.3)
    _check_line(ref, d, t, standing=() if whole else old)
    return _put_table(ref, t, "the plan Root registered")


#: what the word born carries to the two handlers that keep it (PRD M4.1; the layer schema binds it, and this is the one
#: place its shape is named): a plan Root registered, {engines, version, full}, or an engine the owner stamped, {grow,
#: before}. A born word that names no engine changes nothing.
BORN_FIELDS = ("engines", "version", "full", "grow", "before")


def born_item(ctx, item=None):
    """What an engine born says to the handler that keeps it, in BORN_FIELDS, with why it says nothing when it does not:
    (item, why). Run in place (Root's registration, the owner's stamp: the word is heard by call), it is the item it was
    run with. From the board (_born_on_board) the post only names which record it means, and the handler acts on what
    the record already holds. Empty when it names no engine, so a stray born word writes nothing."""
    if item is None:
        return _born_on_board(ctx)
    if not isinstance(item, dict):
        return {}, "the word born names no engine"
    out = {k: item[k] for k in BORN_FIELDS if k in item and item[k] is not None}
    out["engines"] = [str(n) for n in out.get("engines") or [] if n] if isinstance(out.get("engines"), list) else []
    grow = str(out.pop("grow", None) or "").strip()
    if grow:
        out["grow"] = grow
    return (out, None) if out["engines"] or grow else ({}, "the word born names no engine")


def _born_on_board(ctx):
    """A born word posted on the board (Identity may inform Coordination and Priority) is never a plan of its own: Root's
    check and Priority's price stand in front of the line (PRD M4.1, M4.4). It names the plan Root registered last, by
    its version, and the line is that plan's engines from dept.workflows, the whole line; or an engine stamped onto the
    record (an engine ask the owner stamped, or one the table keeps as grown). A post that names no registered version,
    an older one, a line that is not that plan, a plan without a required engine, or an engine nobody stamped is
    refused, and nothing is written: (item, why)."""
    pl = (ctx.get("post") or {}).get("payload")
    pl = pl if isinstance(pl, dict) else {}
    ref = ctx["ref"]
    d = ctx.get("dept") or W.dept(ref) or {}
    mine = list(d.get("engines") or [])
    grow = str(pl.get("grow") or "").strip()
    if grow:
        stamped = {a.get("engine") for a in W.asks(ref) if a.get("kind") == "engine" and a.get("status") == "stamped"}
        if grow not in mine or (grow not in stamped and grow not in (coordination(ref).get("grown") or [])):
            return {}, "nobody stamped %s onto the department's record" % grow
        return {"engines": [], "grow": grow, "before": pl.get("before") if pl.get("before") in mine else None}, None
    wf = [w for w in d.get("workflows") or [] if isinstance(w, dict)]
    version = pl.get("version")
    if not wf or isinstance(version, bool) or not isinstance(version, int):
        return {}, "the word born names no plan Root registered"
    last = int(wf[-1].get("version") or 0)
    if version != last:
        return {}, "the word born names v%d, and the plan Root registered last is v%d" % (version, last)
    plan = [str(n) for n in wf[-1].get("engines") or [] if n]
    if "engines" in pl and (not isinstance(pl["engines"], list) or [str(n) for n in pl["engines"] if n] != plan):
        return {}, "the line it names is not the plan Root registered (v%d)" % last
    missing = [n for n in required_engines(d) if n not in plan]
    if not plan or missing:
        return {}, ("the plan leaves out %s, which this kind requires" % _names(missing)) if missing else "the plan names no engine"
    return {"engines": plan, "version": last, "full": True}, None


def coord_table(ctx, step, item):
    """Coordination's handler for an engine born: a registered plan sets the line (`item` {engines, version}); an engine
    the owner stamped grows it (`item` {grow, before}). Run in place, or from the board on what the record already
    holds (born_item); a born word that names nothing on the record writes nothing, and neither does one the table
    already follows. Its table is written by Coordination and by nobody else."""
    board_, (item, why), J = item is None, born_item(ctx, item), _j2()
    if not item:
        return {"said": "nothing to do: " + why}
    t = coordination(ctx["ref"])
    if board_ and (item["grow"] in (t.get("line") or []) if item.get("grow") else t.get("registered") == item["version"]):
        return {"said": "nothing to do: the line already holds it: " + " -> ".join(t.get("line") or [])}
    import layer_schema as S
    try:
        if item.get("grow"):
            t = grow_line(ctx["ref"], item["grow"], item.get("before"))
            said = "added %s to the line: %s" % (item["grow"], " -> ".join(t["line"]))
        else:
            t = set_line(ctx["ref"], item.get("engines") or [], item.get("version"), full=item.get("full", True) is not False)
            said = "set the line to the plan: " + " -> ".join(t["line"])
    except S.SchemaFault as exc:        # refuse mode: the table the interface refused is not written, and the line stands as it was
        return {"said": "kept the line it had: " + "; ".join(exc.faults[:3]), "line": list(t.get("line") or [])}
    if J:
        J.on_table(ctx["ref"], t, item.get("grow"))
    return {"said": said, "line": list(t["line"])}


def priority_grant(ctx, step, item):
    """Priority's handler for an engine born: each new engine is given its limit, from Priority's template (a
    work engine work_calls times the calls: engine_limit); one that already holds a limit (the owner's own, or one a
    department off J2 was born with) keeps it. Each is on the ledger, by Priority. `item` is {engines, version}, run in
    place, or from the board on what the record already holds (born_item), where only an engine that holds no limit is
    given one; a born word that names nothing on the record gives nothing. Run in place for the budget Identity's
    question asked about, `item` may carry `within_usd`, the most the owner said the department may spend a day: the
    limits given share what the limits held leave of it, each no more than the template's, so together they never
    exceed it (approvals only tighten; PRD M3.3)."""
    ref, board_ = ctx["ref"], item is None
    within = item.get("within_usd") if isinstance(item, dict) else None
    item, why = born_item(ctx, item)
    names = list(item.get("engines") or ([item["grow"]] if item.get("grow") else []))
    if board_ and names:
        envs0 = (W.dept(ref) or {}).get("envelopes") or {}
        names = [n for n in names if not isinstance(envs0.get(n), dict)]
        why = why or "each engine it names holds its limit"
    if not names:
        return {"said": "nothing to do: " + why if board_ else "no new engine to give a limit"}
    given = []
    with W._lock(ref):
        d = W.dept(ref) or {}
        envs = d.setdefault("envelopes", {})
        new = [n for n in names if not isinstance(envs.get(n), dict)]
        share = None
        if within is not None and new:
            held = sum(float((v or {}).get("usd") or 0) for k, v in envs.items() if isinstance(v, dict) and k not in new)
            share = math.floor(max(0.0, float(within) - held) * 100 / len(new)) / 100.0
        for n in new:
            envs[n] = engine_limit(n)
            if share is not None:
                envs[n]["usd"] = min(float(envs[n]["usd"]), share)
            given.append(n)
        if given:
            W.save_dept(ref, d, by="priority")
    J = _j2()
    if J:
        for n in names:
            J.on_granted(ref, n, envs.get(n), n not in given, item.get("version"))
    kept = [n for n in names if n not in given]
    said = (["gave a limit to " + _names(given) + (" within the %s USD a day the owner said" % _usd(within) if share is not None else "")]
            if given else []) + (
        ["%s %s" % (_names(kept), "keeps the limit it holds" if len(kept) == 1 else "keep the limits they hold")] if kept else [])
    return {"said": "; ".join(said), "given": given, "kept": kept}


def _names(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _usd(x):
    """An amount of US dollars as a person says it: 1, 0.5, 2.75."""
    return ("%.2f" % float(x)).rstrip("0").rstrip(".")


def engine_added(ref, name, before=None):
    """An engine the owner stamped is on the record (J5): Coordination's line gains it and Priority gives it its limit,
    each in its handler for an engine born."""
    _ask_rule(ref, "coord.table", {"grow": name, "before": before}, key="grow@%s@%s" % (name, W.now()))
    _ask_rule(ref, "priority.grant", {"engines": [name]}, key="grant@%s@%s" % (name, W.now()))


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
    offer = engine_from_shape(ref, got, pl.get("words"))
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
        why = str((p.get("payload") or {}).get("why") or "no room in the envelope today").strip().rstrip(".")
        _note_idea(ref, offer.get("idea"), {"engine": offer.get("engine"), "priced": "refused", "why": why})
        # the person floated the idea and waits: a refusal is a turn of the chat, in their words, with what they can do
        # (found live 2026-09-29: the refusal stayed on the board and the ideas row)
        try:
            _tell(ref, ctx["dept"], {"src": "Root" if ctx["dept"].get("root") else OWNER}, "inform",
                  {"word": "idea", "done": "Priority said no to the engine %s: %s. The idea stays parked; raise Priority's limit on its card and say the idea again to have it priced again."
                   % (offer.get("engine"), why[:1].lower() + why[1:])})
        except Exception:  # noqa: BLE001 -- the refusal is on the record whether or not the word reached the person
            pass
        return {"said": "Priority said no to %s: %s; the idea stays parked, and the owner is told" % (offer.get("engine"), why)}
    post(ref, "Adaptation", "Identity", "propose", {"word": "engine", "engine": offer.get("engine"), "offer": offer.get("offer"),
                                                   "idea": offer.get("idea"), "for": offer.get("for"), "why": "the idea asks for it; Priority has room"})
    return {"said": "put the engine %s to Identity for the owner" % offer.get("engine")}


def identity_engine(ctx, step, item):
    """The engine Adaptation proposed, put to the owner as an ask in the owner's words: what it would do, and what a stamp does."""
    ref, p = ctx["ref"], ctx["post"]
    pl = p["payload"]
    offer, name = pl.get("offer") or {}, str(pl.get("engine") or "")
    does = str(offer.get("does") or (offer.get("shape") or {}).get("does") or offer.get("use_case") or "").strip().rstrip(".")
    text = "Add the engine %s to %s?%s %s" % (
        name, ctx["dept"].get("name"), (" What it does: " + does[:1].lower() + does[1:] + ".") if does else "",
        _answers("add it", "to leave the idea parked"))
    W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "engine", "engine": name, "offer": offer, "idea": pl.get("idea"),
                     "text": text, "status": "pending", "created": W.now(), "thread": p["thread"]})
    post(ref, "Identity", OWNER, "request", {"word": "engine", "objective": text, "output": "a stamp or a refusal", "may_read": [],
                                             "boundaries": "this one engine"}, thread=p["thread"])
    return {"said": "put an engine to the owner: " + name}


# ---- the line shaped on the fly (founder, 2026-09-30: "each of the adaptations doesn't do any kind of template. It creates
# engines on the fly. It creates a website, and data is taken from the internet"): a department born with no engines (the
# organic kind) has Adaptation shape its line from the owner's words, Identity puts the whole line to the owner once, and
# the stamp births every engine from Do into the Library; the first starts on the words -----------------------------------
def adapt_line_offer(ctx, step, item):
    ref, pl = ctx["ref"], ctx["post"]["payload"]
    src = ctx["bag"].get("adapt.source") or {"shape": True, "source": "shaped"}
    got = ctx["bag"]["adapt.line"] if src.get("shape") else src
    engines = [{"name": " ".join(str(e["name"]).split())[:40], "does": " ".join(str(e.get("does") or "").split())[:200],
                "reads": " ".join(str(e.get("reads") or "Brief").split())[:40], "writes": " ".join(str(e.get("writes") or e["name"]).split())[:40],
                "internet": bool(e.get("internet"))} for e in got["engines"]]
    if _j2_live(ref):
        # J2 step 3: the proposal goes to Priority, on the board, in a thread of its own with the board's bounds
        post(ref, "Adaptation", "Priority", "propose", {"word": "line", "engines": engines, "source": src.get("source"), "words": pl.get("words"),
                                                       "for": pl.get("for"), "why": "the goal needs these workflows"})
        return {"said": "proposed the line to Priority: " + " -> ".join(e["name"] for e in engines), "engines": engines}
    post(ref, "Adaptation", "Identity", "propose", {"word": "line", "engines": engines, "words": pl.get("words"), "for": pl.get("for"),
                                                   "why": "the goal needs a line and the department was born with none"})
    return {"said": "shaped the line from the words: " + " -> ".join(e["name"] for e in engines), "engines": engines}


def identity_line(ctx, step, item):
    """The line Adaptation shaped, put to the owner as one ask in the owner's words: each engine and what it does."""
    ref, p = ctx["ref"], ctx["post"]
    pl = p["payload"]
    engines = [e for e in (pl.get("engines") or []) if isinstance(e, dict) and e.get("name")]
    names = " -> ".join(e["name"] for e in engines)
    what = "; ".join("%s %s" % (e["name"], str(e.get("does") or "").rstrip(".")) for e in engines)
    text = "Set up the line %s? %s. %s" % (names, what, _answers("add them and start", "and say what to change"))
    W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "line", "engine": "Adaptation", "engines": engines, "words": pl.get("words"),
                     "text": text, "status": "pending", "created": W.now(), "thread": p["thread"]})
    post(ref, "Identity", OWNER, "request", {"word": "line", "objective": text, "output": "a stamp or a refusal", "may_read": ["Brief"],
                                             "boundaries": "these engines, in this order"}, thread=p["thread"])
    return {"said": "put the line to the owner: " + names}


# ---- Do: the default line, one answer filed (TPL-1, founder 2026-09-29: "otherwise ... there is a default one"); an engine
# born from an idea runs these same three steps under its own ids, with its instruction ------------------------------------
# ---- what the department's own engines filed, read by the line (founder, 2026-09-29: "I want the data to be fetched from
# the internet by the department, not that we give it" and "obey the prompts so it builds everything as a user, as a
# product"): nothing is hand-made for one case; an engine the person's idea brought in files under its own name, and Plan
# and Write read the latest of every such artifact with the Brief --------------------------------------------------------
NEEDS = {"internet": ("WebSearch", "WebFetch")}    # what an ask or an idea may need, and the model tools that meet it; closed


def _has_web(d):
    """Every engine reaches the internet: the model's web tools go to every agent step (founder, 2026-09-29: "Internet is
    given"). Kept as a name for the places that once asked."""
    return True


def _context_block(ref):
    """The latest text of every artifact on the record that the kind's own line did not name: what the engines the
    person added have filed (their facts, their lists), for Plan and Write to build from and cite."""
    d = W.dept(ref) or {}
    own = set((W.KINDS.get(d.get("kind") or "website") or {}).get("artifacts") or [])
    out = []
    for a in W.artifacts_of(d):
        if a in own:
            continue
        try:
            cur = W.latest(ref, a)
            files = W.read_files(ref, a, cur["v"]) if cur else {}
        except Exception:  # noqa: BLE001 -- an artifact with no version yet
            files = {}
        text = "\n".join(str(v) for k, v in sorted(files.items()) if str(k).endswith((".md", ".txt", ".json"))).strip()
        if text:
            out.append("%s (v%d):\n%s" % (a, cur["v"], text[:8000]))
    return ("\n\nWHAT THE DEPARTMENT'S OWN ENGINES FILED (build from it; say on the page where each fact came from):\n\n" + "\n\n".join(out)) if out else ""


def _pre(step):
    return str(step["id"]).rsplit(".", 1)[0]


def do_read(ctx, step, item):
    art = ctx["def"].get("reads") or "Brief"
    files = W.read_files(ctx["ref"], art, ctx["inp"]["v"])
    text = files.get("brief.md") or "\n".join(str(v) for v in files.values())
    # what is new in the input since its last version (the lines that were not there), so an engine carries a new section
    # through instead of re-doing the old (found on the Beta 2026-09-30: Vetting read Facts v2 and dropped its new food section)
    changed = None
    if int(ctx["inp"]["v"]) > 1:
        try:
            old = W.read_files(ctx["ref"], art, int(ctx["inp"]["v"]) - 1)
            seen = set(l.strip() for v in old.values() for l in str(v).splitlines() if l.strip())
            changed = "\n".join(l for l in text.splitlines() if l.strip() and l.strip() not in seen)[:3000] or None
        except Exception:  # noqa: BLE001 -- no earlier version to read
            changed = None
    # what this engine filed last time, for the need step to weigh the new words against and the make step to build on
    previous, pv, previous_files = None, None, []
    try:
        cur = W.latest(ctx["ref"], ctx["def"].get("writes") or "Result")
        if cur:
            pv = cur["v"]
            old_out = W.read_files(ctx["ref"], ctx["def"]["writes"], pv)
            previous_files = sorted(old_out)
            previous = "\n".join(str(v) for k, v in sorted(old_out.items())).strip() or None
    except Exception:  # noqa: BLE001 -- nothing filed yet
        previous = None
    return {"brief": text, "previous": previous, "previous_v": pv, "previous_files": previous_files, "changed": changed}


def p_do_need(ctx, step, item):
    """Whether the new words ask for this engine's work again, judged by the engine's own agent against what it filed last
    (found live 2026-09-29: 'Put the top three first' and 'Take X out' each paid for a fresh web search)."""
    got = ctx["bag"][_pre(step) + ".read"]
    ins = str(ctx["def"].get("instruction") or ctx["def"].get("use_case") or "").strip()
    reads = ctx["def"].get("reads") or "Brief"
    return ("The engine \"%s\" of the department \"%s\" does this: %s\nIt filed this last time (v%s):\n%s\n\nThe %s now reads:\n%s\n\n"
            "Do the newest words of the %s ask for this engine's work again (new facts to find, a search to repeat, something "
            "to add to what it filed), or only for what the department makes from what it already filed (order, wording, dropping "
            "a line, a rule)? Return ONLY a JSON object: {\"run\": bool, \"why\": \"one line\"}."
            % (ctx["def"].get("name"), ctx["dept"].get("name"), ins[:600], got.get("previous_v"), str(got.get("previous") or "")[:3000],
               reads, str(got.get("brief") or "")[:4000], reads))


def d_do_need(ctx, step, item):
    return {"run": True, "why": "no judgement offline: the engine runs"}


def c_need_is_answer(ctx, step, item, out):
    ok = isinstance(out, dict) and isinstance(out.get("run"), bool) and isinstance(out.get("why"), str)
    return _verdict(ok, "run or not, with why", "no answer")


def p_do_make(ctx, step, item):
    ins = str(ctx["def"].get("instruction") or "").strip()
    got = ctx["bag"][_pre(step) + ".read"]
    reads = ctx["def"].get("reads") or "Brief"
    web = ("You can search the web and open pages. When a page or a subject is named, read it and use what it says, with the "
           "page's URL after each fact; what you could not confirm goes under a line 'Not sure'. ")
    # what was filed last time rides along: a run that runs again adds, or says what it dropped (found live 2026-09-29: each
    # re-run replaced the record; v4 of the site drew on three sources where v1 had four)
    last = ("WHAT YOU FILED LAST TIME (v%s):\n%s\n\nKeep what still holds, add what is new, and list under a line 'Dropped' what you "
            "removed and why; nothing the owner did not ask to drop goes silently.\n\n" % (got.get("previous_v"), str(got.get("previous"))[:6000])
            if got.get("previous") else "")
    last += _new_block(got, reads)
    # an engine whose artifact is a site files pages, not one answer: the Library's template for what it writes says so
    shape = ("Do it as the site's pages, in the owner's own language, nothing invented; where a fact is missing, say so on the page. "
             "Return ONLY a JSON object: {\"files\": {\"index.html\": str, \"<page>.html\": str}}: whole HTML pages, each with a title and a "
             "body, index.html first, every other page linked from it and linking back, each fact with its source as a link."
             if _writes_pages(ctx["def"]) else
             "Do it as one written answer: what was asked for, done as far as words can do it, in the owner's own language, nothing "
             "invented; where a fact is missing, say so. Return ONLY a JSON object: {\"text\": str}.")
    return ("The department \"%s\" was asked for this, in its owner's words (the %s):\n%s\n\n%s%s%s%s"
            % (ctx["dept"].get("name"), reads, got["brief"][:6000],
               ("THIS ENGINE'S INSTRUCTION, FROM THE OWNER'S IDEA: %s\n\n" % ins) if ins else "", last, web, shape))


def d_do_make(ctx, step, item):
    brief = " ".join(str(ctx["bag"][_pre(step) + ".read"]["brief"]).split())
    return {"text": "Noted, to be done by hand: " + brief[:600]}


def _new_block(got, reads):
    """What is new in the input since the engine last ran, as a block of the prompt: the thing that asks for the work now."""
    if got.get("changed") and got.get("previous"):
        return ("NEW IN THE %s SINCE YOUR LAST RUN (this is what asks for your work now; carry every line of it through):\n%s\n\n"
                % (str(reads).upper(), str(got["changed"])[:3000]))
    return ""


# ---- a born engine whose artifact is pages: the pages planned in one small call, then one call per page, as the website
# kind's Write does; every page in one answer trimmed a growing site (found live 2026-09-30, findings 60 and 63) ----------
def p_do_pages(ctx, step, item):
    got = ctx["bag"][_pre(step) + ".read"]
    ins = str(ctx["def"].get("instruction") or "").strip()
    reads = ctx["def"].get("reads") or "Brief"
    kept = ", ".join(got.get("previous_files") or []) or "none yet"
    return ("The department \"%s\" makes the pages of a site from the %s below. Plan the pages as the site should be now: index.html "
            "first, then one entry per page, two to twelve in all, each {\"file\": a lowercase name ending .html, \"title\": str, "
            "\"purpose\": one line}. Keep the pages that still hold from last time (%s), add what the %s now asks for, drop only what "
            "it dropped.\n%sTHE %s:\n%s\n\n%sReturn ONLY a JSON object: {\"pages\": [{\"file\": str, \"title\": str, \"purpose\": str}]}."
            % (ctx["dept"].get("name"), reads, kept, reads, ("THIS ENGINE'S INSTRUCTION: %s\n" % ins) if ins else "",
               str(reads).upper(), got["brief"][:8000], _new_block(got, reads)))


def d_do_pages(ctx, step, item):
    return {"pages": [{"file": "index.html", "title": ctx["dept"].get("name"), "purpose": "the home page"}]}


def do_pages_list(ctx, step, item):
    """The planned pages as their file names, for the page step to run over (an item names a step's row file, so it is a
    name, never the page's whole entry; found live 2026-09-30: Errno 63)."""
    plan = ctx["bag"][_pre(step) + ".plan"]
    return {"pages": [str(p.get("file")) for p in plan.get("pages") or [] if isinstance(p, dict) and p.get("file")], "plan": plan}


def _page_entry(ctx, step, item):
    plan = (ctx["bag"].get(_pre(step) + ".plan") or {}).get("pages") or []
    return next((p for p in plan if isinstance(p, dict) and p.get("file") == item), {"file": str(item or "index.html")})


def p_do_page(ctx, step, item):
    got = ctx["bag"][_pre(step) + ".read"]
    reads = ctx["def"].get("reads") or "Brief"
    plan = ctx["bag"][_pre(step) + ".plan"]["pages"]
    item = _page_entry(ctx, step, item)
    rules = _owner_rules(ctx["dept"])
    return ("Write ONE whole page of this site, in the owner's own language, nothing invented; each fact with its source as a link; "
            "where a fact is missing, say so on the page under 'Not sure'. A complete HTML document (html, head with a title, body), "
            "a nav linking every page of the site by its file name, no script and no external images. You can search the web and "
            "open pages when a fact needs its source.%s\nTHE %s (what the page draws on):\n%s\n\nTHE SITE'S PAGES: %s\nTHIS PAGE: %s\n\n"
            "Return ONLY a JSON object: {\"file\": str, \"html\": str}."
            % (("\nTHE OWNER'S RULES, EACH ONE MET HERE:\n- " + "\n- ".join(rules)) if rules else "", str(reads).upper(),
               got["brief"][:8000], json.dumps(plan), json.dumps(item)))


def d_do_page(ctx, step, item):
    p = _page_entry(ctx, step, item)
    title = str(p.get("title") or ctx["dept"].get("name") or "Page")
    return {"file": str(p.get("file") or "index.html"),
            "html": "<!doctype html><html><head><title>%s</title></head><body><h1>%s</h1><p>%s</p><p>To be written: no agent was there to write this page from the record.</p></body></html>"
                    % (title, title, str(p.get("purpose") or ""))}


def c_pages_are_named(ctx, step, item, out):
    pages = out.get("pages") if isinstance(out, dict) else None
    if not isinstance(pages, list) or not 1 <= len(pages) <= 12:
        return _verdict(False, "", "one to twelve pages")
    files = [str((p or {}).get("file") or "") for p in pages if isinstance(p, dict)]
    notes = []
    if len(files) != len(pages):
        notes.append("a page is not an object")
    if not files or files[0] != "index.html":
        notes.append("the first page is not index.html")
    if any(not re.fullmatch(r"[a-z0-9-]+\.html", f) or len(f) > 60 for f in files):
        notes.append("a file name is not plain lowercase .html of at most 60 characters")
    if len(set(files)) != len(files):
        notes.append("two pages share a file")
    return {"ok": not notes, "notes": notes or ["%d pages, index.html first" % len(files)]}


def c_page_is_html(ctx, step, item, out):
    f, h = (out.get("file"), out.get("html")) if isinstance(out, dict) else (None, None)
    want = item if isinstance(item, str) else ((item or {}).get("file") if isinstance(item, dict) else None)
    ok = (isinstance(f, str) and f.endswith(".html") and (want is None or f == want) and isinstance(h, str) and "<body" in h.lower()
          and len(re.sub(r"<[^>]+>", " ", h).split()) >= 20)
    return _verdict(ok, "a whole page with a body, under its planned name", "not a whole page under its planned name")


def do_file(ctx, step, item):
    """What the engine made, filed under what it writes: files when it answered with files, else one text. The artifact's
    own checks from the Library apply to whoever writes it (found live 2026-09-30: a text filed as Pages and as the Live
    site passed as text, and the site had no page to serve); a site with its home page goes on the host, as Publish puts
    a Build there, the gate having asked the owner before this run."""
    import artifacts
    made = ctx["bag"].get(_pre(step) + ".make") or {}
    pages = ctx["bag"].get(_pre(step) + ".page")
    files = made.get("files") if isinstance(made.get("files"), dict) else None
    if isinstance(pages, list) and pages:
        # a pages engine: one page per call, gathered here
        files = {str(p.get("file")).strip(): str(p.get("html")) for p in pages if isinstance(p, dict) and p.get("file")}
        ok, notes = bool(files), ["%d pages" % len(files)]
    elif files:
        files = {str(k).strip(): str(v) for k, v in files.items() if str(k).strip()}
        ok, notes = True, ["%d files" % len(files)]
    else:
        text = str(made.get("text") or "").strip()
        files, ok, notes = {"result.md": text + "\n"}, len(text) >= 3, ["%d characters" % len(text)]
    own = artifacts.check(ctx["def"].get("writes"), files, default=True)
    if own:
        ok, notes = ok and own["ok"], notes + list(own["notes"])
    out = {"files": files, "check": {"ok": ok, "notes": notes}}
    if ok and _writes_site(ctx["def"]):
        out["publish"] = True                     # on the host after the version row is written (run_engine)
        notes.append("live at the department's site address")
    return out


def c_result_is_text(ctx, step, item, out):
    files = out.get("files") if isinstance(out, dict) else None
    if isinstance(files, dict) and files and all(isinstance(v, str) and v.strip() for v in files.values()):
        return _verdict(True, "%d files, each with text" % len(files), "")
    ok = isinstance(out, dict) and isinstance(out.get("text"), str) and len(out["text"].strip()) >= 3
    return _verdict(ok, "an answer in words", "no answer")


# ---- J2: the five functions work toward the identity's goal (the department page, section J2; S-29) ---------------------
# Adaptation proposes the workflows, Priority grants, refuses or counters, Identity closes what they cannot, Root checks
# and registers, and only then does a workflow run. The lifecycle's record is j2_runtime; it is imported late because it
# imports this module.
def _j2():
    try:
        import j2_runtime
        return j2_runtime
    except Exception:  # noqa: BLE001 -- a department runs without its lifecycle record rather than not at all
        return None


def _j2_live(ref):
    J = _j2()
    return bool(J and J.active(ref))


def _line_request(ref, d, words, thread=None, faults=None):
    """Identity asks Adaptation what the department does next (step 2). With faults, it is Root's refusal going back."""
    return post(ref, "Identity", "Adaptation", "request",
                {"word": "line", "words": words, "objective": "propose the workflows the goal needs",
                 "output": "the engines, each with what it does, reads and writes", "may_read": ["Brief"],
                 "boundaries": "nothing runs before Priority grants it and Root registers it", "for": thread, "faults": list(faults or [])})


def _library_repair(d, lib):
    """The line a kind that requires engines goes back to when Root's check sends a plan back (PRD M4.4): the Library's
    line again, without a name the Library has no engine for, and with each engine the kind requires put in at its
    place on the kind's line. A shaped line is made of names new to the Library, so it can never carry the engine the
    kind requires, and reshaping would be refused for the same fault every time. None for a kind that requires no
    engine, or when the Library itself has no engine the kind requires."""
    req = required_engines(d)
    if not req:
        return None
    work = {n for n, e in defs()["engines"].items() if (e or {}).get("kind") == "work"}
    line = [n for n in lib if n in work]
    kind = list(((defs().get("kinds") or {}).get((d or {}).get("kind") or "website") or {}).get("line") or [])
    for r in req:
        if r in line:
            continue
        if r not in work:
            return None
        after = kind[kind.index(r) + 1:] if r in kind else []
        nxt = next((n for n in line if n in after), None)
        line.insert(line.index(nxt) if nxt else len(line), r)
    return line


def adapt_source(ctx, step, item):
    """Where the proposal comes from (J2.b): the Library's template when the department's kind has one, else Adaptation
    shapes the line itself. A line Root's check refused is shaped again, whatever its first source was, unless the
    kind requires engines: then it is the Library's line again, with the engines the kind requires (_library_repair)."""
    d, pl = ctx["dept"], ctx["post"]["payload"]
    lib = list(d.get("engines") or (W.KINDS.get(d.get("kind") or "website") or {}).get("line") or [])
    repair = _library_repair(d, lib) if pl.get("faults") else None
    if repair:
        lib = repair
    shape = (bool(pl.get("faults")) and not repair) or not lib
    engines = []
    if not shape:
        known = defs()["engines"]
        for n in lib:
            e = known.get(n) or {}
            engines.append({"name": n, "does": str(e.get("description") or e.get("use_case") or ""), "reads": e.get("reads") or "Brief",
                            "writes": e.get("writes") or n, "internet": False})
    took = "takes the Library's line again, with what its kind requires (%s): " % _names(required_engines(d)) if repair else "takes the Library's line: "
    return {"shape": shape, "source": "shaped" if shape else "library", "engines": engines,
            "said": "shapes the line from the goal" if shape else took + " -> ".join(lib)}


def _line_proposal(ref, thread):
    """The line Adaptation last proposed in this thread."""
    mine = [x for x in board(ref) if x["thread"] == thread and x["src"] == "Adaptation" and x["msg_type"] == "propose"
            and (x.get("payload") or {}).get("word") == "line"]
    return (mine[-1].get("payload") or {}) if mine else None


def _line_conflict(ref, thread, why, bound=None, src="Adaptation"):
    """The bargain did not close (a refusal, or its bound): it goes to Identity, never silently to nothing (J2.2)."""
    offer = _line_proposal(ref, thread) or {}
    if any((x.get("payload") or {}).get("word") == "conflict" and (x.get("payload") or {}).get("for") == thread for x in board(ref)):
        return None
    return post(ref, src, "Identity", "inform", {"word": "conflict", "engines": offer.get("engines") or [], "source": offer.get("source"),
                                                 "words": offer.get("words"), "why": why, "bound": bound, "for": thread})


def required_engines(d):
    """The engines the department's kind marks required (PRD M4.4; Q12: the website kind's Check, because it enforces the
    owner's rules). No engine is mandatory unless its template marks it so."""
    k = (defs().get("kinds") or {}).get((d or {}).get("kind") or "website") or {}
    return [str(n) for n in k.get("required") or [] if n]


def _plan_workflow(d, engines, source, why=None):
    """A plan's engines (names, or the dicts a proposal carries) as the workflow schema reads them (A1.14): what the line
    leaves unsaid is what it always meant, an engine the Library lacks reading the kind's first artifact and writing its
    own name, then layer_schema.as_workflow, which looks the Library's own up and inverts each engine's covers. The
    level, the confidence and the doubt of a made engine ride along, which as_workflow does not carry."""
    import layer_schema as S
    first = S.first_input((d or {}).get("kind")) or "Brief"
    lib = defs()["engines"]
    rows = []
    for e in engines or []:
        e = dict(e) if isinstance(e, dict) else {"name": e}
        e["name"] = " ".join(str(e.get("name") or "").split())[:40]
        if e["name"] not in lib:
            e["reads"] = " ".join(str(e.get("reads") or first).split())
            e["writes"] = " ".join(str(e.get("writes") or e["name"]).split())[:40]
        rows.append(e)
    wf = S.as_workflow(rows, source, d)
    for row, e in zip(wf["engines"], rows):
        row.update({k: e[k] for k in ("level", "confidence", "doubt") if e.get(k) is not None})
    if why:
        wf["why"] = str(why)[:600]
    return wf


def _priced(ref, names):
    """Priority's latest price row for this plan (prices.jsonl, once Priority writes them), or None: none written, or the
    plan was settled above Priority (Identity ruled on a conflict over it, or the owner stamped it), which is the one
    way a plan Priority did not say yes to comes to Root."""
    try:
        rows = [r for r in W.rows(ref, "prices.jsonl") if isinstance(r, dict) and set(r.get("engines") or []) == set(names)]
    except (ValueError, OSError):
        return None
    if not rows:
        return None
    if rows[-1].get("answer") != "accept" and any(
            set(n.get("name") if isinstance(n, dict) else n for n in (x.get("payload") or {}).get("engines") or []) == set(names)
            for x in board(ref) if (x.get("payload") or {}).get("word") == "conflict"):
        return None
    return rows[-1]


def _root_ctx(ref, engines):
    """What Root's check reads beside the workflow: Coordination's table (the engines the owner added; the line it holds)
    and Priority's price for this plan, when there is one."""
    t = coordination(ref) if ref else {}
    ctx = {"line": list(t.get("line") or []), "grown": list(t.get("grown") or []),
           "left_out": [r.get("engine") for r in t.get("left_out") or [] if isinstance(r, dict)]}
    price = _priced(ref, [e.get("name") if isinstance(e, dict) else e for e in engines or []]) if ref else None
    if price:
        ctx["price"] = price
    return ctx


def _plan_why(ref, engines):
    """The why the line's proposal gave, when it was long (size_in_range asks one past six engines)."""
    names = [e.get("name") if isinstance(e, dict) else e for e in engines or []]
    for x in reversed(board(ref)):
        pl = x.get("payload") or {}
        if x.get("msg_type") == "propose" and pl.get("word") == "line" and \
                [e.get("name") for e in pl.get("engines") or [] if isinstance(e, dict)] == names:
            return str(pl.get("why") or "")
    return ""


def _root_checks(ref, d, engines, source):
    """Root's standards, as the workflow schema holds them (J2.e, A1.14), one row for each that applied at registration:
    [{check, passed, why}], the schema's own shape row first and then the standards in their order, each a standard's id
    (workflow.check). A Library line is checked for engines the Library has; a shaped line for each engine named once and
    new to the Library, the first reading the kind's first artifact, each reading what one before it wrote and writing
    something new; every line for every done-when item covered, the engines the kind requires kept, a size, a check on
    what each writes, and Priority's price fitting the room. M0.7: the event lists these rows, not a fixed set of names."""
    import layer_schema as S
    wf = _plan_workflow(d, engines, source, why=_plan_why(ref, engines) if ref and len(engines or []) > 6 else None)
    return S.validate_workflow(wf, "registration", d, _root_ctx(ref, engines))


def _root_check(ref, d, engines, source):
    """Root's standards as the fault list its callers use: empty when the workflow meets them, else what each failed row
    says."""
    return [r["why"] for r in _root_checks(ref, d, engines, source) if not r["passed"]]


def _broke(checks):
    """The standards a plan broke, in their own words (WORKFLOW_STANDARDS' says) with what is wrong, for the options ask
    the third refusal leaves: 'each engine writes something not yet written (Site writes Facts, which is already
    written)'. A row that is no standard (the schema's shape, a check put in Root's place) says only what is wrong."""
    import layer_schema as S
    says = {sid: text for sid, text, _, _ in S.WORKFLOW_STANDARDS}
    return "; ".join('"%s" (%s)' % (says[c["check"]], c["why"]) if c.get("check") in says else str(c.get("why"))
                     for c in checks if not c.get("passed"))


#: who said yes to a plan that passes Root's check, as Identity tells the owner it is set: the `by` of _j2_settle, in the
#: owner's words (Priority said yes, Identity ruled, or the owner stamped it; never 'granted')
SETTLED_BY = {"Priority's yes": "Priority said yes to it", "Identity's ruling": "I ruled it runs", "the owner's stamp": "You said yes to it"}


def _j2_settle(ref, d, engines, source, words, by):
    """A granted workflow goes to Root's check. Passed: it is registered on the department's record and its engines may
    run; the owner hears what was made. Refused: the reasons go back to Adaptation, twice at most; then the owner is told."""
    J = _j2()
    who = {"src": "Root" if d.get("root") else OWNER}
    names = [e.get("name") for e in engines]
    faults = _root_check(ref, d, engines, source)
    checks = _root_checks(ref, d, engines, source)
    named = {c["why"] for c in checks if not c["passed"]}
    other = [f for f in faults if f not in named]
    if other:
        # a fault no standard names (a check put in Root's place): the event lists it as the check that ran
        checks.append({"check": "workflow_meets_standards", "passed": False, "why": "; ".join(other)})
    if faults:
        n = J.refused(ref, engines, faults, checks=checks) if J else 1
        if n <= (J.REPAIRS if J else 2):
            _line_request(ref, d, words, faults=faults)
            _tell(ref, d, who, "inform", {"word": "line", "done": "Root's check sent the plan back (%s). Adaptation is reshaping it." % "; ".join(faults)})
            return {"said": "Root's check sent the workflow back to Adaptation: %s" % "; ".join(faults)}
        broke = _broke(checks) or "; ".join(faults)
        _blocked(ref, d, who, "Root's check sent the plan back %d times, and it still does not meet %s. Say what to change and I will have it shaped afresh."
                 % (n, broke), "The plan could not be approved.", "Root, at its review", broke)
        return {"said": "Root's check sent the workflow back %d times; the owner is told" % n}
    added, lost = [], []
    if source == "library":
        added = list(names)
        # an engine the Library's line brought back that is not on the record (a required one, PRD M4.4) is Adaptation's
        # to bring in, as a shaped one is; Root only records the plan (S-10)
        mine = list((W.dept(ref) or {}).get("engines") or [])
        for n in [n for n in names if mine and n not in mine]:
            try:                                           # at its place in the plan: before the next one the record has
                W.add_engine(ref, n, by=by, registered=True, before=next((x for x in names[names.index(n) + 1:] if x in mine), None))
                mine = list((W.dept(ref) or {}).get("engines") or [])
            except Exception as exc:  # noqa: BLE001 -- the owner hears which engine could not be brought in
                added.remove(n)
                lost.append("%s (%s)" % (n, exc))
    else:
        for e in engines:
            try:
                does = str(e.get("does") or "").strip()
                W.add_engine(ref, e["name"], shape={"name": e["name"], "use_case": does or e["name"], "does": does,
                                                     "instruction": ("%s\n\nThe goal, in the owner's words: %s" % (does, words or "")).strip(),
                                                     "needs": ["internet"] if e.get("internet") else [], "reads": e.get("reads") or "Brief",
                                                     "writes": e.get("writes") or e["name"]}, by=by, registered=True)
                added.append(e["name"])
            except Exception as exc:  # noqa: BLE001 -- one engine that cannot be born does not lose the rest; the owner hears which
                lost.append("%s (%s)" % (e.get("name"), exc))
    if not added:
        if J:
            J.refused(ref, engines, lost or ["no engine could be added"], checks=checks)
        _blocked(ref, d, who, "The plan could not be set up: %s." % "; ".join(lost or ["no engine could be added"]),
                 "The plan could not be set up.", "Root, setting up the engines", "; ".join(lost or ["no engine could be added"]))
        return {"said": "no engine of the workflow could be added"}
    if J:
        granted = [e for e in engines if isinstance(e, dict) and e.get("name") in added]
        J.registered(ref, added, source, checks=checks, plan=granted, fit={e["name"]: e["fit"] for e in granted if e.get("fit")})
    _registered(ref, added)
    # Q13: an engine the plan left out needs no stamp, and the message names it (PRD M4.2)
    left = [r.get("engine") for r in coordination(ref).get("left_out") or [] if isinstance(r, dict)]
    _tell(ref, d, who, "inform", {"word": "line", "engines": added,
                                  "done": "The plan is set: %s (%s). %s and it passed Root's check; the first starts now.%s%s"
                                  % (" -> ".join(added), "from the Library" if source == "library" else "shaped for this goal",
                                     SETTLED_BY.get(by, "It was agreed"), (" Not added: " + "; ".join(lost)) if lost else "",
                                     (" Left out of the plan: %s." % _names(left)) if left else "")})
    W.signal()
    return {"said": "registered the workflow %s on %s" % (" -> ".join(added), by)}


def _left_out(d, why):
    """The done-when item a blocked plan may leave out (M3.5): the one its reason names, else the last; none when the
    department has only one item, since done-when is never left empty."""
    items = [i for i in d.get("done_items") or [] if isinstance(i, dict) and i.get("id")]
    if len(items) < 2:
        return None
    named = [i for i in items if re.search(r"\b%s\b" % re.escape(i["id"]), str(why or ""))]
    return (named or items)[-1]


def _blocked(ref, d, who, said, title, by, why):
    """The plan is blocked, and there is always a way out (PRD M3.5, screen S10): the cycle says blocked, and what
    Identity says is an ask with options, the first the one it recommends, each applied by code when the owner chooses
    it: change the plan in my words; leave an item out (a done_items ask, stamped by that choice); stop. The line names
    its card, so the chat says it once, on the card; an older card for the same plan goes quiet."""
    J = _j2()
    if J:
        J._set(ref, state="blocked")
    # what the card says, in plain words before it is made (M3.6): the line that names it says the same
    w = plain_card(ref, {"text": said, "title": title, "why": str(why or "")}, "blocked")
    said, title, why = w["text"], w["title"], w["why"]
    opts = [W.option(W.WORDS_OPTION, "Change the plan in my words", "Adaptation shapes it afresh from what you say; nothing runs before Root's review")]
    item = _left_out(d, why)
    if item:
        opts.append(W.option("leave:" + item["id"], "Leave %s out" % item["id"],
                             "%s is dropped from done-when (%s); nothing more is spent" % (item["id"], str(item["text"]).rstrip("."))))
    opts.append(W.option(W.STOP_OPTION, "Stop here", "the department stops where it is; you can start it again later"))
    for old in W.asks(ref):
        if old.get("kind") == "blocked" and old["status"] == "pending":
            W._put_ask(ref, dict(old, status="replaced", decided=W.now()))
    ask = W.options_ask("blocked", said, opts, title=title, who=by, why=str(why or "").strip(),
                        if_nothing="Nothing runs; the department waits for your words.",
                        cycle_id=((J._state(ref) or {}).get("cycle_id") if J else None))
    ask["thread"] = _card_line(ref, d, who, ask)
    W._put_ask(ref, ask)
    return ask


def _card_line(ref, d, who, ask):
    """What Identity says of a blocked plan's card, on a thread of its own that waits on the owner: the line names the
    card, so the chat says it once, on the card, and the owner's choice is posted in that thread (on_stamp). Returns the
    thread, or None when the line did not reach the board."""
    row = _tell(ref, d, who, "request", {"word": "blocked", "objective": ask["text"], "done": ask["text"], "card": ask["id"],
                                         "output": "one of the options, or your words", "may_read": ["Brief"], "boundaries": "this plan"})
    return row["thread"] if row else None


def _card_waits(ref, d, a):
    """A blocked plan's card the owner answered that must wait open again (M3.5): the words Identity did not take as a
    go, or Stop, leave the plan blocked. The same card, pending again with nothing chosen, on a thread of its own: the
    thread it had closed on the owner's choice, and a choice posted into a closed thread is dropped (found by a verifier
    2026-10-26: after Stop and Start the next choice said 'You chose' and applied nothing, a dead end)."""
    a = dict(a, status="pending", decided=None, by=None, chosen=None)
    a["thread"] = _card_line(ref, d, {"src": "Root" if d.get("root") else OWNER}, a)
    W._put_ask(ref, a)
    return a


def _reopen(ref, d, words, by="your words"):
    """From blocked, the plan is shaped afresh (M3.5): step 2 again, with Root's repairs at nought, and the card that
    asked for a way out goes quiet with the choice the owner made."""
    J = _j2()
    if J:
        J.reopened(ref)
    for a in W.asks(ref):
        if a.get("kind") == "blocked" and a["status"] == "pending":
            way = next((o for o in a.get("options") or [] if o.get("id") == W.WORDS_OPTION), None) or \
                W.option(W.WORDS_OPTION, "Change the plan in my words", "")
            W._put_ask(ref, dict(a, status="chosen", decided=W.now(), by="the owner", chosen=W.chosen(way, words)))
    _line_request(ref, d, _brief_text(ref).strip() or words)
    _tell(ref, d, {"src": "Root" if d.get("root") else OWNER}, "inform",
          {"word": "line", "done": "Adaptation is shaping the plan afresh from %s; Priority and Root check it before anything runs." % by})


def _blocked_chosen(ctx, a, pl):
    """The owner chose a way out of a blocked plan (M3.5), applied here by code: the words option takes the owner's
    words to Identity, which reads them as words said in the chat (its take: go reopens step 2); leave an item out
    writes a done_items ask, stamped by that one click, and reopens step 2; stop stops the department where it is. The
    words and stop leave the plan blocked until something reopens it, so the card waits open again: blocked always
    offers its ways out, before Start and after it."""
    ref, d = ctx["ref"], ctx["dept"]
    chosen = a.get("chosen") or {}
    oid = str(pl.get("option") or chosen.get("id") or "")
    if oid == W.WORDS_OPTION:
        words = str(chosen.get("words") or "").strip()
        # Identity's take reads them against the goal and the rules, as in the chat: a go reopens the plan and the card goes
        # quiet with them (identity_file, _reopen); words that reach outside are an ask, and the plan stays blocked with
        # its card open (found by a verifier 2026-10-23: the box filed the words and reopened step 2 with no take)
        _card_waits(ref, d, a)
        request(ref, words, answers=a["id"])
        return {"said": "took the owner's words for the plan to Identity, to read as said in the chat: " + words}
    if oid.startswith("leave:"):
        iid = oid.split(":", 1)[1]
        items = W.items_of(W.dept(ref))
        gone = next((i for i in items if i["id"] == iid), None)
        if not gone:
            return {"said": "the item %s is no longer in done-when" % iid}
        ask = W.done_items_ask("Leave %s out of done-when: %s. The goal stays as it is" % (iid, str(gone["text"]).rstrip(".")),
                               [i for i in items if i["id"] != iid], "the plan was blocked, and you chose to leave it out",
                               words=chosen.get("label"), answers=a["id"])
        ask.update({"status": "stamped", "decided": W.now(), "by": "the owner"})   # the owner's one click is its stamp
        W._put_ask(ref, ask)
        d = W.apply_done_items(ref, ask)
        _reopen(ref, d, d.get("done") or "", by="the done-when you kept")
        return {"said": "left %s out of done-when on the owner's choice; Adaptation is asked afresh" % iid}
    if oid == W.STOP_OPTION:
        J = _j2()
        if J and J._state(ref):
            J.stop(ref)
        else:
            W.set_stopped(ref, True)
        # the plan is still blocked, so its way out stays open: the card waits again, answerable while the department is
        # stopped and after Start (S10: 'Stopped: the card can still be answered'); the stop is the owner's act, on the
        # ledger and the board (found by a verifier 2026-10-23: Start went back to blocked with no card to answer). While
        # the department is stopped the card does not offer Stop (W.offered)
        _card_waits(ref, W.dept(ref) or d, a)
        return {"said": "stopped the department on the owner's choice; the plan's card stays open"}
    return {"said": "took the owner's choice: %s" % oid}


def _registered(ref, names):
    """Root has recorded the plan (workflow.registered, step 5); Coordination and Priority act on that record, each in its
    handler for an engine born (PRD M4.1): Coordination writes its table, the line and a slot for each engine; Priority gives each engine
    that is new to the department's plans its limit. Root writes neither."""
    wf = (W.dept(ref) or {}).get("workflows") or []
    version = int((wf[-1] if wf else {}).get("version") or 0)
    before = {n for w in wf[:-1] for n in w.get("engines") or []}
    _ask_rule(ref, "coord.table", {"engines": list(names), "version": version, "full": True}, key="table@workflow.v%d" % version)
    _ask_rule(ref, "priority.grant", {"engines": [n for n in names if n not in before], "version": version},
              key="grant@workflow.v%d" % version)


def _j2_shape_failed(ref, d, p, note):
    """Adaptation could not shape a line that passes its own check: the reason goes back to it, twice at most; then the
    owner is told and the cycle is blocked, never left standing at step 2 with nothing said."""
    J = _j2()
    if not J or not J.active(ref):
        return
    why = str(note or "the line did not pass its check").rstrip(".")
    n = J.refused(ref, [], [why])
    who = {"src": "Root" if d.get("root") else OWNER}
    try:
        if n <= J.REPAIRS:
            _line_request(ref, d, (p.get("payload") or {}).get("words"), faults=[why])
            return
        _blocked(ref, d, who, "Adaptation could not shape a plan that passes its check (%s). "
                 "Say what the department should do, in other words, and I will have it shaped afresh." % why,
                 "No plan could be shaped.", "Adaptation, shaping the plan", why)
    except Exception:  # noqa: BLE001 -- the failed run is a row whether or not the word reached the board
        pass


def adapt_line_granted(ctx, step, item):
    """Priority said yes to the line: it goes to Root's check, and from there onto the record (step 5)."""
    ref, p = ctx["ref"], ctx["post"]
    offer = _line_proposal(ref, p["thread"])
    if not offer:
        return {"said": "heard Priority on a line nobody proposed"}
    return _j2_settle(ref, ctx["dept"], offer.get("engines") or [], offer.get("source") or "shaped", offer.get("words"), "Priority's yes")


def adapt_line_refused(ctx, step, item):
    """Priority said no to the line: Adaptation does not drop it in silence; Identity closes the conflict (step 4)."""
    ref, p = ctx["ref"], ctx["post"]
    why = str((p.get("payload") or {}).get("why") or "no room in the envelope").strip().rstrip(".")
    _line_conflict(ref, p["thread"], "Priority said no to the plan: %s" % why)
    return {"said": "Priority said no to the line (%s); the conflict goes to Identity" % why}


def adapt_line_counter(ctx, step, item):
    """Priority asked for less: Adaptation takes that when it leaves a line that still works, and proposes that line
    again in the same thread; what it cannot take goes to Identity. The thread's own bound ends a bargain that will not close."""
    ref, p = ctx["ref"], ctx["post"]
    pl = p.get("payload") or {}
    offer = _line_proposal(ref, p["thread"]) or {}
    keep = [str(k) for k in pl.get("keep") or []]
    engines = [e for e in offer.get("engines") or [] if e.get("name") in keep]
    why = str(pl.get("why") or "the envelope has no room for all of it").strip().rstrip(".")
    # a counter that drops an engine the kind requires is never taken: Identity closes it (PRD M4.4)
    proposed = [e.get("name") for e in offer.get("engines") or []]
    dropped = [n for n in required_engines(ctx["dept"]) if n in proposed and n not in keep]
    if dropped:
        _line_conflict(ref, p["thread"], "Priority asked for less (%s) and the line would leave out %s, which this kind of department requires"
                       % (why, _names(dropped)))
        return {"said": "could not take Priority's ask for less: it leaves out %s, which is required; the conflict goes to Identity" % _names(dropped)}
    if not engines or len(engines) == len(offer.get("engines") or []) or _root_check(ref, ctx["dept"], engines, offer.get("source") or "shaped"):
        _line_conflict(ref, p["thread"], "Priority asked for less (%s) and the line does not work that way" % why)
        return {"said": "could not take Priority's ask for less; the conflict goes to Identity"}
    row = post(ref, "Adaptation", "Priority", "propose", {"word": "line", "engines": engines, "source": offer.get("source"),
                                                         "words": offer.get("words"), "for": offer.get("for"),
                                                         "why": "took Priority's ask for less: " + why}, thread=p["thread"])
    if row is None:
        _line_conflict(ref, p["thread"], "the bargain reached its bound", bound="hops", src="Coordination")
        return {"said": "the bargain reached its bound; it goes to Identity"}
    return {"said": "took Priority's ask for less and proposed again: " + " -> ".join(e["name"] for e in engines)}


def p_identity_close(ctx, step, item):
    d, pl = ctx["dept"], ctx["post"]["payload"]
    rules = "; ".join("%s: %s" % (r.get("tag"), r.get("line")) for r in d.get("rules") or [] if r.get("line"))
    line = " -> ".join(str(e.get("name")) for e in pl.get("engines") or [])
    return _prompt("identity", "goal", "close", ctx["ref"], dept=d.get("name"), goal=pl.get("words") or d.get("goal"), done=d.get("done"),
                   rules=rules or "none", plan=line or "none", against=pl.get("why") or "")


def d_identity_close(ctx, step, item):
    # the draft, when no agent is there to judge: the goal and the rules are not read by code, so the owner is asked
    return {"ruling": "ask", "why": "the goal and the rules do not settle it"}


def c_ruling_is_known(ctx, step, item, out):
    return _verdict(out.get("ruling") in ("run", "drop", "ask"), "the ruling is run, drop or ask", "not a ruling: %r" % (out.get("ruling"),))


def identity_closed(ctx, step, item):
    """Identity's ruling on a bargain that did not close (step 4): run it, drop it, or one ask to the owner (J2.3)."""
    ref, d, pl = ctx["ref"], ctx["dept"], ctx["post"]["payload"]
    got = ctx["bag"]["identity.close"]
    ruling, why = got.get("ruling"), str(got.get("why") or "").strip().rstrip(".")
    engines, J = [e for e in pl.get("engines") or [] if isinstance(e, dict) and e.get("name")], _j2()
    names = " -> ".join(e["name"] for e in engines)
    who = {"src": "Root" if d.get("root") else OWNER}
    if J:
        J.ruled(ref, ruling, why, engines)
    if ruling == "run":
        _tell(ref, d, who, "inform", {"word": "line", "done": "Priority did not say yes to the plan %s; I ruled it runs: %s." % (names, why)})
        return _j2_settle(ref, d, engines, pl.get("source") or "shaped", pl.get("words"), "Identity's ruling")
    if ruling == "drop":
        _blocked(ref, d, who, "The plan %s is dropped: %s. Say what to change, or raise Priority's limit on its card."
                 % (names, why or str(pl.get("why") or "")), "The plan is dropped.", "Identity, settling Priority's no",
                 why or str(pl.get("why") or ""))
        return {"said": "dropped the plan: " + (why or "Priority's no stands")}
    text = ("Adaptation proposes the plan %s. %s. The goal and the rules do not settle it. %s"
            % (names, str(pl.get("why") or "Priority did not say yes to it").rstrip("."), _answers("run it as proposed", "to drop it")))
    # the card quotes Priority's why, which a model may say in the bargain's inside words: it passes the check every card
    # passes (plain_card, M3.6), so the card says what the line it stands for may (found by a verifier 2026-10-26: the
    # Chat's 'Waiting for you' card said grant and counter while its line was plain)
    text = plain_card(ref, {"text": text}, "conflict")["text"]
    if not any(a.get("kind") == "conflict" and a.get("for") == pl.get("for") for a in W.asks(ref)):
        p = post(ref, "Identity", OWNER, "request", {"word": "conflict", "objective": text, "output": "a stamp or a refusal", "may_read": ["Brief"],
                                                     "boundaries": "this one plan"})
        W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "conflict", "engine": "Identity", "engines": engines,
                         "source": pl.get("source") or "shaped", "words": pl.get("words"), "for": pl.get("for"), "text": text,
                         "status": "pending", "created": W.now(), "thread": p["thread"] if p else None})
    return {"said": "could not close the conflict from the goal and the rules; put it to the owner"}


def _j2_audit_read(ref, d, version, filed):
    """Audit's reading closes the loop (step 8): nothing to put right means done-when holds, and Identity says so once."""
    J = _j2()
    if not J or not J.audited(ref, version, filed):
        return
    try:
        _tell(ref, d, {"src": "Root" if d.get("root") else OWNER}, "inform",
              {"word": "goal", "done": "The goal is reached: %s. Audit read Live site v%s and found nothing to put right."
               % (str(d.get("done") or "done").rstrip("."), version), "link": "Live site", "v": version})
    except Exception:  # noqa: BLE001 -- the goal is reached on the record whether or not the word reached the chat
        pass


CODE = {"plan_read": plan_read, "plan_fit": plan_fit, "plan_file": plan_file, "write_list": write_list, "write_file": write_file,
        "do_read": do_read, "do_file": do_file, "adapt_offer": adapt_offer, "adapt_priced": adapt_priced, "identity_engine": identity_engine,
        "adapt_line_offer": adapt_line_offer, "identity_line": identity_line, "do_pages_list": do_pages_list,
        "adapt_source": adapt_source, "adapt_line_granted": adapt_line_granted, "adapt_line_refused": adapt_line_refused,
        "adapt_line_counter": adapt_line_counter, "identity_closed": identity_closed,
        "check_rules_of": check_rules_of,
        "hear": hear, "coord_ready": coord_ready, "coord_record": coord_record,
        "setup_read": setup_read, "setup_say": setup_say, "setup_make": setup_make, "setup_file": setup_file,
        "check_build": check_build, "publish_copy": publish_copy, "identity_gate": identity_gate, "identity_wait_engine": identity_wait_engine,
        "priority_envelope": priority_envelope, "coord_chain": coord_chain, "coord_heard": coord_heard,
        "coord_busy": coord_busy, "coord_pick": coord_pick, "coord_edge": coord_edge, "coord_verdict": coord_verdict,
        "coord_bounds": coord_bounds, "coord_alarm": coord_alarm, "coord_table": coord_table, "priority_grant": priority_grant,
        "identity_read": identity_read, "identity_route": identity_route, "identity_hand": identity_hand, "identity_lost": identity_lost,
        "identity_file": identity_file, "identity_verdict": identity_verdict, "identity_rung": identity_rung,
        "identity_apply": identity_apply, "identity_drop": identity_drop, "identity_finding": identity_finding,
        "identity_alarm": identity_alarm, "identity_idea": identity_idea, "adapt_park": adapt_park,
        "priority_read": priority_read, "priority_post": priority_post,
        "adapt_sense": adapt_sense, "adapt_ladder": adapt_ladder, "adapt_act": adapt_act, "adapt_trial": adapt_trial,
        "adapt_notrial": adapt_notrial, "adapt_heard": adapt_heard, "audit_pick": audit_pick,
        "audit_mechanical": audit_mechanical, "audit_file": audit_file}


# ---- each function's version 1: one agent, its instructions as typed fields (S-28, A1.16) ------------------------------
#: Version 1 of each function is one agent with its instructions inside its covering (PRD M2, rewritten by A1). The words
#: its agent is sent are the layer's WORDS and LAYOUT, compiled by layers/prompts.py from fields the interface types
#: (layer_schema.PROMPTS); the code around them only fills their inputs and checks what comes back. Until a layer holds
#: its words, the bundle's .md files (function-prompts/, which an update of the app replaces) are read through the same
#: split. The bundle sits beside the code and is read-only from here on.
PROMPTS_DIR = Path(__file__).parent / "function-prompts"
#: Each function's files, in its page's order, and in each the parts its steps read, with the inputs the code fills in
#: each, derived from the interface. A file no step reads (Adaptation's decide, whose only part is the note) is the
#: owner's to read, and holds no part.
INSTRUCTIONS = {fn: {group: {part: tuple(spec["inputs"]) for part, spec in parts.items() if "field.note" not in spec["fields"].values()}
                     for group, parts in layer_schema.PROMPTS[fn].items()} for fn in layer_schema.FUNCTION_LAYERS}


# the .md reader and the compiler moved into layers/prompts.py (PRD A1.16); these keep their names for their callers
def _parts(text):
    return layers.prompts.parts_of(text)


def instruction_faults(fn, file, text):
    """What keeps one instruction file from serving its function: layers.prompts.instruction_faults."""
    return layers.prompts.instruction_faults(fn, file, text)


def bundle_faults():
    """Every function's words against the list, at the definitions load: layers.prompts.faults. [] when all serve."""
    return layers.prompts.faults()


def _own(ref, fn, file):
    """Where a department keeps its own copy of one instruction file (PRD M2.2): layers.prompts.own."""
    return layers.prompts.own(ref, fn, file)


def _instruction(fn, file, ref=None):
    """The text of one of a function's instruction files, the department's own copy or the bundle's: layers.prompts.instruction."""
    return layers.prompts.instruction(fn, file, ref)


def _prompt(fn, file, part, ref=None, **slots):
    """One part of one of a function's instructions, its inputs filled: the words its agent is sent (layers.prompts.prompt).
    Each input is filled once, with its value as given, so nothing a value holds is read as a marker; one the code does not
    fill is an error, never a blank."""
    return layers.prompts.prompt(ref, fn, file, part, **slots)


def _goal_of(ref, name, e=None):
    """What an engine does and its skills, as its agent is told them: a function's from its goal words (the owner may
    change them), any other engine's from its definition."""
    e = e if e is not None else (engine_def(name) or {})
    fn = str(name or "").lower()
    if e.get("kind") != "function" or fn not in INSTRUCTIONS:
        return e.get("description") or "", list(e.get("skills") or [])
    return layers.words(ref, fn, "goal", "does")["text"], list(layers.words(ref, fn, "goal", "skills")["items"])


INSTRUCTIONS_MAX = 20000                               # the most one file may hold, in characters
#: What the owner is told of a file no step reads (Adaptation's decide): its words are kept, and no run is sent them.
NOT_READ = "in this version the code makes this choice, so no run reads it yet"


def _read_by_a_run(fn, file):
    """Whether a run is sent any of one instruction file's words: a file that holds no part a step reads (Adaptation's
    decide, whose choice the code makes in this version) is kept as the owner's note, and the owner is told so, never
    that the next run uses it."""
    return bool((INSTRUCTIONS.get(fn) or {}).get(file))


def _waiting_change(ref, fn, file):
    return next((a for a in W.asks(ref) if a.get("kind") == "instructions" and a["status"] == "pending"
                 and a.get("fn") == fn and a.get("file") == file), None)


def instructions_view(ref, fn):
    """A function's instruction files as its Settings shows them: each by name, the line that says what it is for, its
    words as the department reads them now, whether they are the owner's or as shipped, whether a run reads them, and
    a change that waits for the stamp. Names only, never where a file lives."""
    out = []
    for file in INSTRUCTIONS.get(fn) or {}:
        text = _instruction(fn, file, ref)
        shipped = _instruction(fn, file)
        a = _waiting_change(ref, fn, file)
        out.append({"file": file, "lead": _parts(text)[0].split("\n", 1)[0], "text": text, "as_shipped": text == shipped,
                    "read": _read_by_a_run(fn, file), "waits": {"ask": a["id"], "at": a.get("created")} if a else None})
    return out


def instructions_ask(ref, fn, file, text):
    """The owner's change to one of a function's instruction files, filed as an ask (PRD M2.2): Identity puts it to
    the owner and nothing changes until the stamp; on the stamp identity_apply writes the department's own copy. The
    file's covering check runs here, and again at the stamp; one change waits per file."""
    fn, file = str(fn or "").strip().lower(), str(file or "").strip().lower()
    if fn.title() not in FUNCTIONS or fn not in INSTRUCTIONS:
        raise ValueError("no function named %s" % (fn or "nothing"))
    if file not in INSTRUCTIONS[fn]:
        raise ValueError("%s has no instructions named %s" % (fn.title(), file or "nothing"))
    text = str(text if text is not None else "").replace("\r\n", "\n").strip("\n")
    if not text.strip():
        raise ValueError("say what the instructions should be")
    if len(text) > INSTRUCTIONS_MAX:
        raise ValueError("the instructions are too long to keep")
    text += "\n"
    faults = instruction_faults(fn, file, text)
    if faults:
        raise ValueError("these words cannot serve %s: %s" % (fn.title(), "; ".join(faults)))
    d = W.dept(ref)
    if not d:
        raise ValueError("no department at %s" % ref)
    with W._lock(ref):
        if _waiting_change(ref, fn, file):
            raise ValueError("a change to %s's %s already waits for your stamp" % (fn.title(), file))
        if text == _instruction(fn, file, ref):
            raise ValueError("these are the words %s's %s holds now" % (fn.title(), file))
        line = "Change %s's %s instructions to your words" % (fn.title(), file)
        use = (_answers("use them from the next run", "to keep them as they are") if _read_by_a_run(fn, file) else
               _answers("keep them as your note", "to keep them as they are",
                        lead="In this version the code makes this choice, so no run reads these words yet: "))
        p = post(ref, "Identity", OWNER, "request", {"word": "instructions", "objective": line + "? " + use, "output": "a stamp or a refusal",
                                                     "may_read": [], "boundaries": "this one file"})
        return W._put_ask(ref, {"id": "a-" + uuid.uuid4().hex[:8], "kind": "instructions", "engine": fn.title(), "fn": fn, "file": file,
                                "words": text, "text": line, "status": "pending", "created": W.now(), "thread": p["thread"] if p else None})


def _apply_instructions(ref, d, a):
    """The owner's stamp on a change to one instruction file: the department's own copy, written whole, and read by the
    next run. Words that no longer serve the function (the bundle changed under them) are not written, and the owner
    hears why. Words the same as the bundle's take the department's copy away, so a later bundle's words reach it. A
    file no run reads is kept as the owner's note, and the owner is told that, never that the next run uses it."""
    fn, file, text = a.get("fn"), a.get("file"), str(a.get("words") or "")
    who = {"src": "Root" if d.get("root") else OWNER}
    faults = instruction_faults(fn, file, text) if fn in INSTRUCTIONS else ["no function named %s" % fn]
    if faults:
        _tell(ref, d, who, "inform", {"word": "instructions", "done": "Your change to %s's %s was not put in place: %s. Change it again."
                                      % (str(fn).title(), file, "; ".join(faults))})
        return {"said": "could not put the owner's change to %s's %s in place: %s" % (str(fn).title(), file, "; ".join(faults))}
    own = _own(ref, fn, file)
    with W._lock(ref):
        if text == _instruction(fn, file):
            if own.is_file():
                own.unlink()
        else:
            own.parent.mkdir(parents=True, exist_ok=True)
            tmp = own.with_name(own.name + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, own)
    _tell(ref, d, who, "inform", {"word": "instructions", "done": "%s's %s now reads as you changed it%s."
                                  % (str(fn).title(), file, "; the next run uses it" if _read_by_a_run(fn, file)
                                     else ", kept as your note; " + NOT_READ)})
    return {"said": "put the owner's change to %s's %s in place" % (str(fn).title(), file)}


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
            "\n\nBRIEF:\n" + ctx["bag"]["plan.read"]["brief"] + _context_block(ctx["ref"]))


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
            "\n\nTHE BRIEF, AND WHAT WAS ASKED SINCE:\n" + _brief_text(ctx["ref"]) + _context_block(ctx["ref"]) +
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
    # when words are too thin to work from is Identity's completeness, a file of its own (its page lists it); take reads it
    return _prompt("identity", "take", "take", ctx["ref"], goal=d.get("goal"), rules="; ".join(r["line"] for r in d.get("rules") or []),
                   words=got["words"], facts=json.dumps(got["facts"]), completeness=_prompt("identity", "completeness", "thin", ctx["ref"]))


def d_identity_take(ctx, step, item):
    f = ctx["bag"]["identity.read"]["facts"]
    return {"verdict": "ask" if f["leaves_site"] else "go", "why": "it reaches outside the site" if f["leaves_site"] else "inside the goal",
            "needs": [], "unsure": []}


#: Identity's standard (PRD M3.3, MK-1): the five points of its completeness file, each by the word a reading names it;
#: the interface's own tuple (PRD A1.3), so the covering and the schema read one standard
import layer_schema as S  # noqa: E402 -- beside the one name that reads it
STANDARD = S.STANDARD
#: what each point's gap is called, in the owner's words, when code reads it on the record
STANDARD_SAYS = {"goal": "no goal", "items": "no done-when item that says how it is checked", "rules": "a rule with no tag",
                 "owner": "no owner", "budget": "no budget"}
#: the standard as the owner reads it on Identity's pane (PRD M3.7, S5): the five points of MK-1, each by the line its
#: row says and the reading's points it covers
STANDARD_POINTS = (("goal", "The goal names what and for whom", ("goal",)),
                   ("items", "Done-when items, each with how it is checked", ("items",)),
                   ("rules", "Every rule is tagged", ("rules",)),
                   ("owner_budget", "Owner and budget are set", ("owner", "budget")),
                   ("invented", "Nothing invented", ("invented",)))
#: Identity's question for each point of its standard that code reads on the record (PRD M3.3), in the owner's words:
#: one question, for the first point unmet; who owns the department and what it may spend are one question
STANDARD_ASKS = {"goal": "What goal must this department achieve?",
                 "items": "What evidence will prove this department is done?",
                 "rules": "What may this department do, what must it ask you first, and what must it never do?",
                 "owner": "Who owns this department, and what may it spend?",
                 "budget": "Who owns this department, and what may it spend?"}
STANDARD_PAIRS = {"owner": ("owner", "budget"), "budget": ("owner", "budget")}
#: a point by the name a question asked before the standard was one (j2_runtime's own presence check said done-when)
STANDARD_ALIAS = {"done-when": "items"}


def _standard_gaps(d):
    """What code can read of Identity's standard on the record: the points it finds unmet, in the standard's order. The
    goal is there; done-when has items, each saying how it is checked, and its done line, their joined text, is there
    (a record from before the items were drafted keeps its done line alone; one with items and no done line has no
    done-when an older reader can read); every rule is tagged; the owner and the budget are set. Whether the goal names
    what and for whom, and whether anything is invented, is the AI's reading, never code's. The one standard: Identity's
    step, its draft, its covering, its own reading on the record and its pane all read it here (PRD M3.3)."""
    gaps = []
    if not str(d.get("goal") or "").strip():
        gaps.append("goal")
    items = [i for i in d.get("done_items") or [] if isinstance(i, dict)]
    if not str(d.get("done") or "").strip() or any(i.get("how") not in W.DONE_HOW for i in items):
        gaps.append("items")
    rules = d.get("rules") or []
    if not rules or any(not str(r.get("line") or "").strip() or r.get("tag") not in W.RULE_TAGS for r in rules):
        gaps.append("rules")
    if not str(d.get("owner") or "").strip():
        gaps.append("owner")
    if not d.get("envelopes"):
        gaps.append("budget")
    return gaps


def _standard_words(ctx):
    """The owner's words as Identity's standard reads them: what is filed in the Brief, then the words now."""
    words = ctx["bag"]["identity.read"]["words"]
    brief = _brief_text(ctx["ref"]).strip()
    return ("%s\nNOW: %s" % (brief, words)) if brief else words


def _j1_said(d):
    """What Root asked in J1 and what the owner said to each: [(question, answer)]."""
    msgs = [m for m in ((d.get("initial_goal_context") or {}).get("messages") or []) if isinstance(m, dict)]
    out = []
    for i, m in enumerate(msgs):
        if m.get("actor") == "root":
            nxt = next((x for x in msgs[i + 1:] if x.get("actor") == "user"), None)
            if nxt:
                out.append((str(m.get("text") or ""), str(nxt.get("text") or "")))
    return out


def p_identity_enough(ctx, step, item):
    d = ctx["dept"]
    J = _j2()
    cycle = (J._state(ctx["ref"]) or {}).get("cycle_id") if J else None
    asked = _j1_said(d) + [(str(a.get("text") or ""), str(a.get("answered") or "")) for a in W.asks(ctx["ref"])
                           if a.get("kind") == "j2_identity" and a.get("standard") and a.get("cycle_id") == cycle and a.get("answered")]
    items = "; ".join("%s %s (checked by %s, %s)" % (i.get("id"), i.get("text"), i.get("how") or "nothing said", i.get("level") or "no level")
                      for i in d.get("done_items") or [] if isinstance(i, dict)) or str(d.get("done") or "") or "none"
    rules = "; ".join("%s: %s" % (r.get("tag") or "no tag", r.get("line")) for r in d.get("rules") or [] if r.get("line")) or "none"
    budget = "Priority's limits are set for each engine" if d.get("envelopes") else "none"
    confirm = "; ".join("%s: %s" % (c.get("item"), c.get("why")) for c in d.get("to_be_confirmed") or [] if isinstance(c, dict)) or "none"
    return _prompt("identity", "completeness", "enough", ctx["ref"], words=_standard_words(ctx),
                   asked=" | ".join("%s -> %s" % qa for qa in asked) or "nothing", goal=d.get("goal") or "none", items=items,
                   rules=rules, owner=d.get("owner") or "none", budget=budget, confirm=confirm)


def standard_reading(d):
    """Identity's standard as its code reads it on the record (_standard_gaps): the draft under the AI's reading in the
    identity.enough step, and the reading Identity makes by code where the cycle starts and after an answer or a stamp
    (identity_asks). Not met, it asks one question, for the first point unmet."""
    gaps = _standard_gaps(d)
    if not gaps:
        return {"enough": True, "missing": [], "question": "", "why": "read by code: every point is on the record"}
    return {"enough": False, "missing": gaps, "question": STANDARD_ASKS[gaps[0]],
            "why": "Identity's standard is not met yet: the record has %s." % ", ".join(STANDARD_SAYS[g] for g in gaps)}


def d_identity_enough(ctx, step, item):
    """The draft under the AI: the standard as code reads it on the record (standard_reading), with Identity's question
    for the first gap it finds."""
    return standard_reading(ctx["dept"])


def identity_asks(ref):
    """Identity reads its standard on the record by code (standard_reading) and, when a point is unmet, puts its one
    question to the owner: j2_runtime records the ask (J.asked, its one shape), and Identity says the line on the board,
    which names its card, so the chat says the question once, on the card (M0.6). The cycle calls this where it starts
    and after the owner answers a question this reading asked; the question is Identity's, never the ledger's (rule 14).
    Returns the cycle when a question is open now, None when the standard is met or there is no cycle."""
    J, d = _j2(), W.dept(ref)
    if not J or not d:
        return None
    got = standard_reading(d)
    if got["enough"]:
        return None
    cur = J.asked(ref, got["question"], got["missing"], got["why"], standard=False)
    aid = (cur or {}).get("open_ask")
    if aid:
        try:
            post(ref, "Identity", OWNER, "inform", {"word": "question", "done": got["question"], "card": aid})
        except Exception:  # noqa: BLE001 -- the ask is on the record whether or not the chat carries it
            pass
    return cur


def identity_next(ref):
    """An ask that answered Identity's question was stamped or said no to elsewhere (a rule, done-when items; PRD M3.4):
    Identity reads its standard again by code and asks the next point unmet, one at a time (identity_asks). Returns the
    cycle when a question is open now, None when the standard is met, or a question is open already, or there is no
    cycle to ask in (stopped, or done)."""
    J = _j2()
    if not J:
        return None
    with W._lock(ref):
        cur = J._state(ref)
        if not cur or not cur.get("cycle_id") or cur.get("state") in ("stopped", "done"):
            return None
        if cur.get("open_ask") and any(a["id"] == cur["open_ask"] and a["status"] == "pending" for a in W.asks(ref)):
            return cur
        return identity_asks(ref)


#: the owner's name in an answer to the owner question: 'I am Asha', 'my name is Asha Rao', 'owned by Asha', 'Asha owns it'
OWNER_NAMED = re.compile(r"(?i:\bi am|\bi'm|\bmy name is|\bowned by)\s+([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*)?)|\b([A-Z][\w'.-]*)\s+owns\b")


def _priority_limits(ref, within=None):
    """A department with no budget: Identity asks Priority, and Priority gives each of the five its limit from its
    template, by its own step (priority.grant), on the ledger as Priority's. Identity reads the budget and never writes
    money (rule 2; decision A1-6: one writer for money). `within` is the most the owner said the department may spend a
    day, in US dollars: Priority then gives every engine of the department its limit too (the five and the engines on its
    record, which keep them when the plan that names them is registered), all of them within it. True when Priority
    gave limits."""
    d = W.dept(ref) or {}
    if d.get("envelopes"):
        return False
    names = list(W.SYSTEMS)
    item = {"engines": names}
    if within is not None:
        names += [n for n in d.get("engines") or [] if n not in names]
        item["within_usd"] = float(within)
    got = _ask_rule(ref, "priority.grant", item, key="grant@budget@%s" % W.now())
    return bool((got or {}).get("given"))


#: what an answer says the department may spend: an amount (in figures, or 'a' or 'one' dollar), its money, and how
#: often ('a day', 'a month'); none named is a day, the tightest reading of a limit kept a day
MONEY_SAID = re.compile(r"(?P<pre>\$|\busd\s*|\bus\$\s*|₹|\brs\.?\s*|\binr\s*|€|£)?(?P<n>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?|\ba\b|\bone\b)\s*"
                        r"(?P<unit>dollars?\b|usd\b|bucks?\b|rupees?\b|rs\b|inr\b|euros?\b|pounds?\b)?"
                        r"(?:\s*(?:a|per|each|every|in a|in all a)\s+(?P<per>day|week|month|year)\b|\s*(?P<ly>daily|weekly|monthly|yearly)\b)?", re.I)
PER_DAYS = {"day": 1, "daily": 1, "week": 7, "weekly": 7, "month": 30, "monthly": 30, "year": 365, "yearly": 365}


def _stated_budget(words):
    """What the owner's answer says the department may spend, read by code: {usd: a day, in US dollars, or None for an
    amount in other money, which Priority does not convert; said: the words}, or None when no amount is named."""
    for m in MONEY_SAID.finditer(str(words or "")):
        pre, unit = (m.group("pre") or "").strip().lower(), (m.group("unit") or "").lower()
        if not pre and not unit:
            continue                                   # a bare number is not money
        n = m.group("n").lower()
        if n in ("a", "one") and not unit:
            continue
        amount = 1.0 if n in ("a", "one") else float(n.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", n)
                                                      else n.replace(",", "."))
        per = PER_DAYS.get((m.group("per") or m.group("ly") or "day").lower(), 1)
        dollars = pre in ("$", "usd", "us$") or unit.startswith(("dollar", "usd", "buck"))
        return {"usd": round(amount / per, 4) if dollars else None, "said": " ".join(m.group(0).split())}
    return None


def _standard_fill(ref, point, words):
    """The owner's answer to Identity's question on a point code reads on the record reaches the record (PRD M3.3), through
    the record's own writers, so a gap only code can see is closed by the answer and the same question never comes back:
    no goal, and the words are the goal; no done-when, and they are its next item (W.put_done_items); no owner, and the
    owner is the one who answers, by the name they give; no budget, and Priority gives its limits, by its own step
    (_priority_limits: Priority writes money), within what the words say the department may spend a day, else from its
    template; a limit is the owner's to change on Priority's card. Only the point the question asked about, with its
    pair (who owns it and what it may spend are one question), and only where the record lacks it; a rule goes through
    the rule ask (M3.4), and 'just do it' through the defaults. Returns what was taken, in the owner's words: [] when
    nothing was."""
    point = STANDARD_ALIAS.get(point, point)
    words = " ".join(str(words or "").split())
    taken = []
    if not words or JUST_DO_IT.fullmatch(words):
        return taken
    with W._lock(ref):
        gaps = [g for g in _standard_gaps(W.dept(ref)) if g in STANDARD_PAIRS.get(point, (point,))]
        # what the words say the department may spend reaches Priority as the most its limits may come to (approvals only
        # tighten; found by a verifier 2026-10-26: '1 dollar a day in all' gave 30 USD a day from the template)
        stated = _stated_budget(words) if "budget" in gaps else None
        within = (stated or {}).get("usd")
        limits = "budget" in gaps and _priority_limits(ref, within)    # Priority's own write, before the identity is read here
        d = W.dept(ref)
        if "items" in gaps:
            d = W.put_done_items(ref, W.answered_items(d, words))
            taken.append("done when: " + "; ".join("%s %s" % (i["id"], i["text"]) for i in d["done_items"]))
        changed = False
        if "goal" in gaps:
            d["goal"], changed = words, True
            taken.append("the goal, in your words")
        if "owner" in gaps:
            m = OWNER_NAMED.search(words)
            d["owner"], changed = ((m.group(1) or m.group(2)) if m else "") or "the owner", True
            taken.append("you, as the owner" if d["owner"] == "the owner" else "%s, as the owner" % d["owner"])
        if limits:
            taken.append("Priority's limits within the %s USD a day you said" % _usd(within) if within is not None else
                         "Priority's limits from its template (%s is not in US dollars: change them on Priority's card)"
                         % stated["said"] if stated else "Priority's limits from its template")
        if changed:
            W.bump_identity(ref, d)                        # the one record, and the Org screen's copy of it (M3.1)
    return taken


def c_enough_is_shaped(ctx, step, item, out):
    """Identity's standard, its covering (PRD M3.3): the reading's shape, and the part of the standard code can read.
    Enough is a yes or a no; what is missing is named by the standard's points; a no asks one question in one line; and
    a yes over a gap code finds on the record (no goal, no done-when item saying how it is checked, a rule with no tag,
    no owner, no budget) fails: the measured gap stands."""
    notes = []
    enough, missing = out.get("enough"), out.get("missing")
    if not isinstance(enough, bool):
        notes.append("it does not say whether the identity is enough")
    if not isinstance(missing, list) or any(m not in STANDARD for m in missing):
        notes.append("what is missing is not named by the standard's points: %r" % (missing,))
    q = str(out.get("question") or "")
    if enough is False:
        if not missing:
            notes.append("a no names nothing missing")
        if not q.strip() or "\n" in q.strip() or len(q) > 300:
            notes.append("a no asks no one question in one line")
    elif enough is True:
        if missing:
            notes.append("a yes names something missing")
        gaps = _standard_gaps(ctx["dept"]) if ctx else []
        if gaps:
            notes.append("read as enough, but the record has %s" % ", ".join(STANDARD_SAYS[g] for g in gaps))
    return {"ok": not notes, "notes": notes or ["enough" if enough else "not enough: %s; one question" % ", ".join(missing)]}


def p_identity_gate(ctx, step, item):
    pl = (ctx.get("post") or {}).get("payload") or {}
    return _prompt("identity", "take", "gate", ctx["ref"], rules="; ".join(r["line"] for r in ctx["dept"].get("rules") or []),
                   engine=pl.get("engine"))


def d_identity_gate(ctx, step, item):
    return {"verdict": "admit", "why": "the rules allow it"}


def _offer_lines(pl):
    """An engine offer, in the words Priority's agent judges: which engine, what it does, what it needs, what it costs a
    day (found live 2026-09-29: shown a rung proposal's fields, the agent refused an engine offer as empty). The slots
    of Priority's bargain, part engine."""
    offer = pl.get("offer") if isinstance(pl.get("offer"), dict) else {}
    shape = offer.get("shape") if isinstance(offer.get("shape"), dict) else {}
    name = pl.get("engine") or shape.get("name") or offer.get("pick") or "?"
    does = shape.get("does") or offer.get("does") or offer.get("use_case") or ""
    needs = ", ".join(shape.get("needs") or []) or "nothing beyond the model"
    t = priority_template()
    return {"engine": name, "does": does, "needs": needs, "calls": "%d" % (int(t.get("work_calls", 8)) * int(t.get("calls", 30))),
            "usd": "%.2f" % float(t.get("usd", 6.0))}


def p_priority_bargain(ctx, step, item):
    got, pl = ctx["bag"]["priority.read"], ctx["post"]["payload"]
    room = "yes" if got["facts"]["room"] else "no"
    if pl.get("word") == "line":
        lines = "\n".join("- %s: %s" % (e.get("name"), str(e.get("does") or "")) for e in pl.get("engines") or [] if isinstance(e, dict))
        t = priority_template()
        return _prompt("priority", "bargain", "line", ctx["ref"], source="from the Library" if pl.get("source") == "library" else "shaped for the goal",
                       engines=lines, calls="%d" % (int(t.get("work_calls", 8)) * int(t.get("calls", 30))), usd="%.2f" % float(t.get("usd", 6.0)),
                       room=room, limit=got.get("limit"))
    if pl.get("word") == "engine":
        return _prompt("priority", "bargain", "engine", ctx["ref"], room=room, **_offer_lines(pl))
    return _prompt("priority", "bargain", "cost", ctx["ref"], word=pl.get("word"), step=pl.get("step"), cost=pl.get("cost"), room=room)


def d_priority_bargain(ctx, step, item):
    read = ctx["bag"]["priority.read"]
    if read.get("word") == "line" and not read["facts"]["room"]:
        keep = list(read.get("names") or [])[:int(read.get("limit") or 6)]
        if keep:
            return {"answer": "counter", "why": "the envelope has room for %d workflows" % len(keep), "keep": keep}
        return {"answer": "reject", "why": "the plan names no workflow"}
    room = ctx["bag"]["priority.read"]["facts"]["room"]
    return {"answer": "accept" if room else "reject", "why": "the envelope has room" if room else "the envelope has no room today"}


def p_audit_judge(ctx, step, item):
    ref, v = ctx["ref"], ctx["inp"]["v"]
    files = W.read_files(ref, "Live site", v)
    pages = []
    for name in ctx["bag"]["audit.pick"]["pages"][:12]:
        text = re.sub(r"<[^>]+>", " ", files.get(name, ""))
        pages.append({"page": name, "text": " ".join(text.split())[:1500]})
    # what the department's own engines filed backs a page as the brief does (found live 2026-09-29: facts Source Reader
    # filed with their URLs were asked to be "put right" because the brief did not give them)
    return _prompt("audit", "judge", "judge", ref, brief=_brief_text(ref), filed=_context_block(ref), pages=json.dumps(pages))


def d_audit_judge(ctx, step, item):
    return {"ok": True, "findings": []}


def _words(ctx):
    return ctx["bag"]["identity.read"]["words"]


def p_identity_recognise(ctx, step, item):
    got = ctx["bag"]["identity.read"]
    return _prompt("identity", "take", "recognise", ctx["ref"], goal=ctx["dept"].get("goal"), words=got["words"], facts=json.dumps(got["facts"]))


def d_identity_recognise(ctx, step, item):
    return {"journey": ctx["bag"]["identity.read"]["facts"]["cue"], "why": "read from the words' own cues"}


def _record_lines(ref):
    """What the answer step may read: the record in the kind's own words, and the latest text of what the department filed
    (found live 2026-09-29: 'Which of your changes matters most?' got 'It holds no changes' because the answer saw a
    website's lines and never the Result that held the changes)."""
    d = W.dept(ref) or {}
    arts = list(W.artifacts_of(d))
    out = []
    if "Live site" in arts:
        live = W.latest(ref, "Live site")
        out += ["pages in the plan: " + ", ".join(str(p.get("title")) for p in _pages(ref)) if _pages(ref) else "no plan yet",
                "the site is live, at its version %d" % live["v"] if live else "the site is not live yet"]
    out += ["%s has %d versions" % (a, len(W.versions(ref, a))) for a in arts]
    out += ["waiting for the owner: " + a["text"] for a in W.asks(ref) if a["status"] == "pending"]
    # the latest text the department filed, last artifact first: the work itself, not only its counts
    for a in reversed(arts):
        cur = W.latest(ref, a)
        if not cur:
            continue
        files = W.read_files(ref, a, cur["v"])
        text = "\n".join(str(v) for k, v in sorted(files.items()) if str(k).endswith((".md", ".txt", ".json", ".html"))).strip()
        if text:
            out.append("what was filed last, %s v%d:\n%s" % (a, cur["v"], text[:4000]))
            break
    return out


def p_identity_answer(ctx, step, item):
    return _prompt("identity", "take", "answer", ctx["ref"], question=_words(ctx), record="\n- ".join(_record_lines(ctx["ref"])))


def d_identity_answer(ctx, step, item):
    lines = _record_lines(ctx["ref"])
    return {"answer": "; ".join(lines[:2]), "source": "the department's record", "confidence": "moderate"}


def p_identity_rule(ctx, step, item):
    d = ctx["dept"]
    return _prompt("identity", "take", "rule", ctx["ref"], goal=d.get("goal"), rules="; ".join(r["line"] for r in d.get("rules") or []),
                   words=_words(ctx))


def d_identity_rule(ctx, step, item):
    words = _words(ctx)
    once = bool(re.search(r"\b(just this once|this time only|only this time|for now)\b", words, re.I))
    goal = bool(re.search(r"\b(the (?:site|department|website) is (?:now )?for|the goal is)\b", words, re.I))
    line = re.sub(r"^\s*(from now on|going forward|in future|just this once)[,:]?\s*", "", words, flags=re.I).strip()
    # a rule that asks the owner first is tagged ask, though it says never ('Never publish without asking me', M3.4)
    asks = bool(re.search(r"\b(?:without (?:asking|checking with) (?:me|the owner)|ask(?:ing)? (?:me|the owner) (?:first|before)|"
                          r"check with (?:me|the owner) (?:first|before))\b", line, re.I))
    tag = "goal" if goal else "ask" if asks else "refuse" if re.search(r"\bnever\b", line, re.I) else "always"
    return {"tag": tag, "line": line[:1].upper() + line[1:], "scope": "one-time" if once else "standing"}


def p_identity_weigh(ctx, step, item):
    got = ctx["bag"]["identity.read"]
    return _prompt("identity", "take", "weigh", ctx["ref"], pages=json.dumps([{"slug": p["slug"], "title": p.get("title")} for p in _pages(ctx["ref"])]),
                   words=got["words"])


def d_identity_weigh(ctx, step, item):
    words = _words(ctx)
    what = "format" if re.search(r"\btoo (long|short)\b", words, re.I) else "accuracy" if re.search(r"\b(wrong|incorrect|mistake)\b", words, re.I) \
        else "content"
    return {"about": ctx["bag"]["identity.read"].get("about"), "what": what, "now": words, "future": None}


def p_adapt_shape(ctx, step, item):
    pl, d = ctx["post"]["payload"], ctx["dept"]
    have = set(d.get("engines") or [x[0] for x in W.engines_of(d)])
    lib = "; ".join("%s: %s" % (n, e.get("use_case")) for n, e in defs()["engines"].items()
                    if e.get("kind") == "work" and e.get("from_template") and n not in have and n != "Setup")
    return _prompt("adaptation", "sense", "shape", ctx["ref"], needs=", ".join(NEEDS), goal=d.get("goal"), idea=pl.get("words"),
                   library=lib or "none")


def d_adapt_shape(ctx, step, item):
    words = str(ctx["post"]["payload"].get("words") or "")
    return {"reflected": words, "question": "What would this let a visitor do that they cannot do today?",
            "shapes": ["a page that says it", "a link to where it is already done", "an engine that does it"], "pick": None, "engine": None}


def _out_artifacts():
    """The Library's artifacts that go out into the world (counted after a stamp), for a line's last engine to write under
    the name the app serves: 'Live site: the site as served, at its address'."""
    import artifacts
    return "; ".join("%s: %s" % (t["name"], t.get("use_case") or "") for t in artifacts.templates().values() if t.get("counts_after") == "stamp")


def p_adapt_line(ctx, step, item):
    d, pl = ctx["dept"], ctx["post"]["payload"]
    rules = "; ".join(str(r.get("line")) for r in d.get("rules") or [] if r.get("line"))
    taken = ", ".join(sorted(defs()["engines"]))
    refused = ("\n\n" + _prompt("adaptation", "make", "refused", ctx["ref"], faults="; ".join(str(f) for f in pl["faults"]))) if pl.get("faults") else ""
    return _prompt("adaptation", "make", "line", ctx["ref"], dept=d.get("name"), words=pl.get("words") or d.get("goal"), taken=taken,
                   out=_out_artifacts() or "none", rules=rules or "none", refused=refused)


def d_adapt_line(ctx, step, item):
    # the draft, when no agent is there to judge: two engines, the facts from the internet and the site from the facts.
    # Their names are ones the Library does not have yet: a second department shaped this way takes Facts 2 and Site 2
    # (found 2026-10-07: it took Facts and Site again, its check refused the line, and nothing was said)
    def line(n):
        tag = "" if n == 1 else " %d" % n
        return [{"name": "Facts" + tag, "does": "finds on the internet what the goal names, each fact with its source", "reads": "Brief",
                 "writes": "Facts" + tag, "internet": True},
                {"name": "Site" + tag, "does": "writes the site's pages from the facts, each with its source", "reads": "Facts" + tag,
                 "writes": "Live site", "internet": False}]
    return {"engines": next((line(n) for n in range(1, 50) if not _line_faults(line(n))), line(1))}


PROMPT = {"identity_recognise": p_identity_recognise, "adapt_line": p_adapt_line, "do_pages": p_do_pages, "do_page": p_do_page, "identity_answer": p_identity_answer, "identity_rule": p_identity_rule,
          "identity_weigh": p_identity_weigh, "adapt_shape": p_adapt_shape, "plan_pages": p_plan_pages, "write_page": p_write_page, "identity_take": p_identity_take,
          "identity_gate_soft": p_identity_gate, "priority_bargain": p_priority_bargain, "audit_judge": p_audit_judge,
          "coord_tie": p_coord_tie, "setup_shape": p_setup_shape, "setup_converse": p_setup_converse, "identity_close": p_identity_close, "check_rules": p_check_rules, "do_make": p_do_make, "do_need": p_do_need,
          "identity_enough": p_identity_enough}
DRAFT = {"identity_recognise_draft": d_identity_recognise, "adapt_line_draft": d_adapt_line, "do_pages_draft": d_do_pages, "do_page_draft": d_do_page, "identity_answer_draft": d_identity_answer,
         "coord_tie_draft": d_coord_tie, "setup_shape_draft": d_setup_shape, "setup_converse_draft": d_setup_converse,
         "identity_close_draft": d_identity_close, "check_rules_draft": d_check_rules,
         "identity_rule_draft": d_identity_rule, "identity_weigh_draft": d_identity_weigh, "adapt_shape_draft": d_adapt_shape,
         "plan_pages_draft": d_plan_pages, "write_page_draft": d_write_page, "identity_take_draft": d_identity_take,
         "identity_gate_draft": d_identity_gate, "priority_bargain_draft": d_priority_bargain, "audit_judge_draft": d_audit_judge,
         "do_make_draft": d_do_make, "do_need_draft": d_do_need, "identity_enough_draft": d_identity_enough}


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
    """Identity's take, its covering (M2.4): the verdict is go, ask or refuse, and an ask or a refusal says why, since
    the owner is told it."""
    if out.get("verdict") not in ("go", "ask", "refuse"):
        return _verdict(False, "", "not a verdict: %r" % (out.get("verdict"),))
    return _verdict(out["verdict"] == "go" or str(out.get("why") or "").strip(), "the verdict is one of go, ask, refuse",
                    "the verdict %s does not say why" % out["verdict"])


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
    return _verdict(out.get("answer") in ("accept", "reject", "counter"), "the answer is accept, reject or counter", "not an answer: %r" % (out.get("answer"),))


def c_answer_has_its_price(ctx, step, item, out):
    """Priority's covering (M2.4): yes, less or no, each with its price: the line that says what it costs against the
    room left; an ask for less names what it keeps. An answer without them fails the step; nothing is taken in its place."""
    notes = []
    if out.get("answer") not in ("accept", "reject", "counter"):
        notes.append("not an answer: %r" % (out.get("answer"),))
    if not str(out.get("why") or "").strip():
        notes.append("the answer names no price: nothing says what it costs against the room left")
    if out.get("answer") == "counter" and not [k for k in out.get("keep") or [] if str(k).strip()]:
        notes.append("an ask for less names nothing to keep")
    # the note is said on Priority's card, so it names the answer in the owner's words (said yes, asked for less, said no)
    said = {"accept": "said yes", "reject": "said no", "counter": "asked for less"}.get(out.get("answer"), out.get("answer"))
    return {"ok": not notes, "notes": notes or ["%s, with its price: %s" % (said, str(out["why"]).strip())]}


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


def c_moves_name_their_rows(ctx, step, item, out):
    """Adaptation's covering (M2.4): a proposal names its rows. Each move is of a known kind, on a named step; a move
    down, a trial and a proposal each name the rows it rests on (its evidence, at least one run); an ended trial says why."""
    m = out.get("moves")
    if not isinstance(m, list):
        return _verdict(False, "", "no list of moves")
    notes = []
    for x in m:
        if not isinstance(x, dict) or x.get("kind") not in ("down", "trial", "propose", "end-trial") or not x.get("step"):
            notes.append("a move of no known kind")
        elif x["kind"] == "end-trial":
            if not str(x.get("why") or "").strip():
                notes.append("ending the trial of %s says no why" % x["step"])
        elif not isinstance(x.get("evidence"), dict) or int(x["evidence"].get("runs") or 0) < 1:
            notes.append("the move on %s names no rows it rests on" % x["step"])
    return {"ok": not notes, "notes": notes or ["%d moves, each naming the rows it rests on" % len(m)]}


def c_one_run_at_a_time(ctx, step, item, out):
    """Coordination's covering (M2.4): one run at a time. A start is let through only while no run of the department runs."""
    if out.get("answer") not in ("admit", "wait", "refuse"):
        return _verdict(False, "", "not a gate's answer: %r" % (out.get("answer"),))
    running = [r.get("engine") for r in (ctx or {}).get("rs") or [] if r.get("status") == "running"]
    return _verdict(out["answer"] != "admit" or not running, out.get("why") or "no other run is running",
                    "a start let through while %s runs" % ", ".join(str(n) for n in running[:2]))


def c_chain_under_its_limit(ctx, step, item, out):
    """Coordination's covering (M2.4): a chain stops under its limit. A start is let through only while the runs one
    owner's ask caused are fewer than W.CHAIN_LIMIT."""
    if out.get("answer") not in ("admit", "wait", "refuse"):
        return _verdict(False, "", "not a gate's answer: %r" % (out.get("answer"),))
    chain, n = None, 0
    if ctx and ctx.get("def") and ctx.get("inp"):
        chain = W._chain_of(ctx["ref"], ctx["def"].get("reads"), ctx["inp"].get("v"))
        n = sum(1 for r in W.runs(ctx["ref"]) if chain and r.get("chain") == chain)
    return _verdict(out["answer"] != "admit" or n < W.CHAIN_LIMIT, out.get("why") or "the chain is under its limit",
                    "a start let through on a chain of %d runs, at its limit of %d" % (n, W.CHAIN_LIMIT))


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


def c_findings_name_where_and_what(ctx, step, item, out):
    """Audit's covering (M2.4): a finding names where and what: the page it is on, and its claim. A reading with a
    finding that does not fails the step, and the version is not read; nothing found is never taken in its place."""
    f = out.get("findings")
    if not isinstance(f, list):
        return _verdict(False, "", "no list of findings")
    notes = []
    for i, x in enumerate(f):
        if not isinstance(x, dict) or not str(x.get("claim") or "").strip():
            notes.append("finding %d names no what" % (i + 1))
        elif not str(x.get("page") or x.get("where") or "").strip():
            notes.append("finding %d names no where: %s" % (i + 1, _clip(str(x["claim"]))))
    return {"ok": not notes, "notes": notes or ["%d findings, each naming where and what" % len(f)]}


def _clip(s, n=80):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


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


#: the standards a shaped line is held to as Adaptation shapes it, before the department is known (PRD M0.7, A1.14): the
#: line's own shape. The rest (items covered, the required engines, the room) are the department's, at Root's check.
LINE_STANDARDS = ("each_engine_named", "names_unique", "names_new", "first_reads_input", "reads_known", "one_output")


def _line_notes(engs):
    """_line_faults, each fault with the standard it breaks: [(standard id, note)], in the order the line is read. The
    line is read as a shaped one by the workflow schema's own standards (workflow_schema), with no department behind it,
    so its first artifact is the Brief."""
    import workflow_schema
    wf = _plan_workflow(None, [e if isinstance(e, dict) else {} for e in engs], "shaped")
    return [(r["check"], r["why"]) for r in workflow_schema.run(wf, "proposal", None, {}) if r["check"] in LINE_STANDARDS and not r["passed"]]


def _line_faults(engs):
    """What is wrong with a shaped line, as code sees it: each engine named once and not as the Library names one (by name,
    and by the slug its template file would take, against the shipped and the record home's templates), the first reading
    the Brief, each reading the Brief or what one before it wrote, each writing something not yet written. Empty when the
    line is sound. Shared by the shape step's check and the stamp, so a line refused by one is refused by the other."""
    return [note for _, note in _line_notes(engs)]


def c_line_is_engines(ctx, step, item, out):
    """One to six engines that _line_faults finds nothing wrong with: the shape is the agent's, the check is code."""
    engs = out.get("engines") if isinstance(out, dict) else None
    if not isinstance(engs, list) or not 1 <= len(engs) <= 6:
        return _verdict(False, "", "one to six engines")
    notes = _line_faults(engs)
    return {"ok": not notes, "notes": notes or ["%d engines, each reading what one before it wrote" % len(engs)]}


def c_idea_has_shapes(ctx, step, item, out):
    shapes = [x for x in out.get("shapes") or [] if str(x).strip()]
    ok = bool(str(out.get("reflected") or "").strip()) and 2 <= len(shapes) <= 3
    return _verdict(ok, "reflected back, in %d shapes" % len(shapes), "the idea was not reflected back in two or three shapes")


CHECK = {"line_is_engines": c_line_is_engines, "pages_are_named": c_pages_are_named, "page_is_html": c_page_is_html, "journey_is_known": c_journey_is_known, "answer_names_its_source": c_answer_names_its_source, "result_is_text": c_result_is_text,
         "need_is_answer": c_need_is_answer,
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
         # each function's covering (M2.4): code, and a step that fails one fails; no draft is taken in its place
         "findings_name_where_and_what": c_findings_name_where_and_what, "answer_has_its_price": c_answer_has_its_price,
         "moves_name_their_rows": c_moves_name_their_rows, "one_run_at_a_time": c_one_run_at_a_time,
         "chain_under_its_limit": c_chain_under_its_limit,
         "department_is_shaped": c_department_is_shaped, "department_is_made": c_department_is_made,
         "setup_converse_is_valid": c_setup_converse_is_valid, "ruling_is_known": c_ruling_is_known,
         "enough_is_shaped": c_enough_is_shaped}


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
    does, skills = _goal_of(ref, name, e)                     # a function's own words, as its agent is told them
    view = {"name": name, "kind": e["kind"], "description": does or e.get("description"), "skills": skills,
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
        view["limits"] = []
        for n in [x[0] for x in W.engines_of(d)] + list(W.SYSTEMS):
            env = W.limit_of(d, n)
            calls, usd = W._today_spend(ref, n)
            view["limits"].append({"engine": n, "calls": int(env.get("calls", 0)), "usd": float(env.get("usd", 0.0)),
                                   "used_calls": calls, "used_usd": round(usd, 3)})
    if e["kind"] == "function" and name.lower() in INSTRUCTIONS:
        view["instructions"] = instructions_view(ref, name.lower())      # its version 1 files, for its Settings (S16)
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
    if pl.get("word") == "verdict" and pl.get("answer") in GATE_SAYS and not pl.get("why"):
        return "The verdict: " + GATE_SAYS[pl["answer"]]      # a gate's verdict in the owner's words, never admit or refuse
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
