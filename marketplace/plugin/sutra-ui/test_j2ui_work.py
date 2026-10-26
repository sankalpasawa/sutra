"""test_j2ui_work.py -- the page's work content: workflows, lanes, call log (j2ui_work.py; UI port, package j2ui-work).

Named claims (each step of the package adds its own):
  W1  build(ctx) gives exactly the thirteen keys the page reads, each at its empty value when nothing fills it, as JSON; a
      builder that raises empties only its own keys and leaves a reason; the result is the memoised object
  W2  a workflow for each engine of the registered line, in the line's order, W-1 on; none before Root's check registers a plan;
      an engine the plan left out is no workflow; the status is one of the page's six words, read from the engine's state, its
      asks and its latest run; and no string of a workflow is a check's id
  W7  docs, preview and call answer with the prototype's empty shapes (Sutra stores no prompt and no reply); the call log has a row
      for each step that made a model call, none for a department with no model step, and no figure nobody recorded (no tokens,
      no model); a message is linked to its call only when exactly one call of its author brackets its time
  W7c a call made by a slot step of an engine of the line names its atom ('W-1.a2', the id the workflow's atom card has), and the
      page's atom card finds it: it shows the reply and the cost, and does not say 'No AI call yet'; a function's step and an engine
      outside the line have none
  W7b a decision's answer is one bare word in the record (Priority's accept, counter or reject, a gate's admit, wait or refuse); the
      call log says the act in the owner's words (said yes, asked for less, said no; let through, waiting, stopped), whoever made the
      call, never the word, and a code with no act of that kind is replaced by the step's first check note
  W4  a lane for each of the five functions, the validator and each workflow, in that order, with a status in idle, working,
      waiting or blocked; a function waits on you only while the owner holds the turn; the numbers are the record's (Priority's
      calls limit, the runs' retries), never the prototype's constants

The Ctx the page's adapter hands out (j2ui_common) is written by another package. Until it is merged these tests build a stand-in
with the same attributes, filled from a department the way the contract names its sources (standin below): the contract is
the table of attributes, not the implementation. Each department is made the way the app makes one (website_dept.create),
then its record is set to the state under test, so what is read is the record a real department keeps. The other two test
files of this package (test_j2ui_atoms.py, test_j2ui_audit.py) build on the helpers here.
"""
import importlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import j2ui_work as K

PINNED = "f9ceba15192bbd6f62047cb7288d0f291b2fbc4f"          # the J2 prototype commit the page was copied from
REF = "dref-jw0001"
FUNCS = ["Identity", "Adaptation", "Priority", "Coordination", "Audit"]
LINE = ["Plan", "Write", "Check", "Publish"]
BANNED = re.compile(r"GRANT|COUNTER|REFUSE|accept-proposal|reject-proposal", re.I)
ACTS_SAID = {"accept": "said yes", "counter": "asked for less", "reject": "said no", "admit": "let through", "wait": "waiting", "refuse": "stopped"}
BARE = re.compile(r"\b(%s)\b" % "|".join(ACTS_SAID), re.I)          # a decision's own word, bare: Priority's or a gate's answer
CHECK_ID = re.compile(r"^[a-z]+(_[a-z]+)+$")


@pytest.fixture
def mods(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    # the proposals Root's setup files and the registry's reads (dept_api) keep, in this test's own folder
    for var, sub in (("SUTRA_UI_PROPOSALS", "proposals"), ("SUTRA_UI_ROUTINES", "routines"), ("SUTRA_UI_RUNS", "runs")):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(var, str(tmp_path / sub))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    import website_dept as W
    import engine_runtime as R
    import j2_runtime as J
    import functions_view as F
    for m in (W, R, J, F):
        importlib.reload(m)
    W.create(REF, "City Care Hospital Website", None, kind="website")
    return W, R, J, F


# ---- the record, set to the state under test (test_functions_view.py's helpers) --------------------------------------
def ago(s):
    return (datetime.now(timezone.utc) - timedelta(seconds=s)).astimezone().isoformat(timespec="seconds")


def cycle(W, state, step, **more):
    row = {"cycle_id": "cycle-test", "step": step, "journey": "J2", "state": state, "open_ask": None, "workflow": [],
           "repairs": 0, "updated_at": W.now()}
    row.update(more)
    W._write(W.ddir(REF) / "j2-state.json", row)


def ask(W, kind="publish", **more):
    row = {"id": "a-" + kind, "kind": kind, "engine": more.pop("engine", "Publish"), "text": more.pop("text", "Publish: go live for the first time"),
           "status": "pending", "created": W.now()}
    row.update(more)
    W._put_ask(REF, row)
    return row


def run(W, engine, status="ok", what="Write a page", system=False, **more):
    row = {"id": "r-" + engine.lower() + status, "engine": engine, "system": system, "slot": more.pop("slot", "%s@x.v1" % engine),
           "status": status, "started": more.pop("started", W.now()), "ended": None if status == "running" else W.now(),
           "what": what, "wrote": more.pop("wrote", None), "chain": None, "spend": {"calls": 0, "usd": 0.0}, "retries": 0}
    row.update(more)
    W._put_run(REF, row)
    return row


def step_row(R, engine, step, ok=True, notes=None, run_id=None, **more):
    """One row of steps.jsonl, as engine_runtime writes a slot step's."""
    row = {"id": "s-%s-%d" % (step, len(R.step_rows(REF))), "run": run_id, "engine": engine, "step": step, "item": None, "mode": "slot",
           "slot": "%s@x.v1" % engine, "impl": None, "asked_rung": "C2", "rung": "C2", "miss": False, "by": "code", "agent": None,
           "applied": [], "read": [], "facts": None, "usd": 0.0, "calls": 0, "def_version": 1, "started": "2026-10-26T10:00:00+05:30",
           "status": "ok" if ok else "failed", "answer": None, "check": {"ok": ok, "notes": list(notes if notes is not None else [])},
           "trial": None, "ended": "2026-10-26T10:00:01+05:30", "ms": 1000}
    row.update(more)
    R._append(REF, "steps.jsonl", row)
    return row


def post(W, R, src, dst, act, payload, thread="x-t1", hop=1, about=None, at=None):
    n = len(R.board(REF)) + 1
    row = {"n": n, "src": src, "dst": [dst] if isinstance(dst, str) else list(dst), "msg_type": act, "thread": thread, "hop": hop,
           "about": about, "payload": payload, "ack_id": None, "by": None, "at": at or W.now()}
    R._append(REF, "board.jsonl", row)
    return row


def event(J, action, actor, recipient, state, summary, step=1, **more):
    """One event of the cycle's ledger, through the ledger's own writer."""
    return J.note(REF, step, actor, recipient, action, state, summary, "k-%s-%d" % (action, len(J.events(REF))), more.pop("payload", None), **more)


# ---- the stand-in Ctx: the contract's attributes, filled from the record through its public readers ------------------
def standin(mods, ref=REF, planned=True, chat=True):
    """What j2ui_common.get_ctx(ref) will hand out, built the way its contract names its sources (UIPORT-plan section 6.1)."""
    W, R, J, F = mods
    d = W.dept(ref)
    fv = F.functions(ref)
    cur = J._state(ref) or {}
    mv = W.map_view(ref)
    runs, asks = W.runs(ref), W.asks(ref)
    events = [e for e in J.events_after(ref, 0) if cur.get("cycle_id") and e.get("cycle_id") == cur.get("cycle_id")]
    engines = []
    for e in mv["engines"]:
        engines.append({"name": e["name"], "reads": e.get("reads"), "writes": e.get("writes"), "runs_as": e.get("runs_as"),
                        "in_line": e.get("in_line"), "state": e.get("state"), "env": dict(e.get("envelope") or {}),
                        "window_min": e.get("window_min"), "last": e.get("last"), "timetable": e.get("timetable"),
                        "steps_view": R.steps_view(ref, e["name"]), "runs": [r for r in runs if r.get("engine") == e["name"]]})
    # W-k by position in the registered line (map order, in_line true), then the engines the plan left out; none before a plan
    inline = [e for e in engines if e["in_line"]] if planned else []
    for k, e in enumerate(inline + [e for e in engines if e not in inline], 1):
        e["k"] = k
        e["wid"] = "W-%d" % k if planned else None
    arts = []
    for a in W.artifacts_of(d):
        vs = W.versions(ref, a)
        arts.append({"name": a, "slug": W.slug(a), "versions": vs, "latest": vs[-1] if vs else None})
    ctx = types.SimpleNamespace(
        ref=ref, kind="website", d=d, root_ref=d.get("root"), doc=False, stopped=bool(d.get("stopped")), fv=fv, cur=cur,
        state=(fv["cycle"]["state"] if fv else None) or cur.get("state") or "not_started", runs=runs, asks=asks,
        posts=R.board(ref), root_posts=[], steps=R.step_rows(ref), events=events, engines=engines, planned=planned, arts=arts,
        chat=[], msg_of={}, ask_msg={}, ask_opts={}, paused_ask=None, reasons=[], memo={})
    by_name = {e["name"]: e for e in engines}
    ctx.wid = lambda name: (by_name.get(name) or {}).get("wid")
    ctx.fn_id = lambda name: "fn:" + str(name).lower() if name in FUNCS else None
    ctx.who = lambda src: "user" if src == "Owner" else src.lower() if src in FUNCS else ctx.wid(src)
    ctx.dest = ctx.who

    def step_at(iso):
        best = None
        for e in events:
            if str(e.get("occurred_at") or "") <= str(iso or ""):
                best = e.get("step")
        return best
    ctx.step_at = step_at
    if chat:
        fake_chat(ctx)
    return ctx


def fake_chat(ctx):
    """A chat registry as small as the work modules read it: one message for each post of the department's board by the owner or a
    function, ids by position, and msg_of keyed by the board ('b', n) as the contract keys it."""
    for p in ctx.posts:
        who = ctx.who(p["src"])
        if not who:
            continue
        ctx.chat.append({"id": len(ctx.chat) + 1, "t": (p.get("at") or "")[11:19], "who": who, "text": str(p["payload"].get("word") or ""),
                         "step": ctx.step_at(p.get("at"))})
        ctx.msg_of[("b", p["n"])] = len(ctx.chat)
    return ctx.chat


def walk(v):
    """Every string a value holds: the words a person reads (a key such as proposal_id is the page's own name for a field)."""
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from walk(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from walk(x)


@pytest.fixture
def born(mods, monkeypatch):
    """A department as a person makes one: found the organisation, say the words, Root sets it up (test_functions_view.py's way);
    its ctx is the stand-in's, read after the line has run."""
    monkeypatch.setenv("J1_FLOW_V1", "1")
    W, R, J, F = mods
    import founding
    import org2_apply
    import placement_engine as E
    for m in (E, org2_apply, founding):
        importlib.reload(m)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")

    def make(words="Build a website that teaches algebra to Class 8 students", org="Acme Learning"):
        root = founding.found_structure(org, owner="Sankalp")["root"]
        W.owner_ask(root, words)
        W.run_until_idle(root, limit=300)
        child = next(d for d in W.list_depts() if d.get("parent") == root)
        W.run_until_idle(child["ref"], limit=300)
        return child["ref"]
    return make


# ---- the prototype's page, rendered with this package's output (a skip when the prototype or node is not on this machine) --
def proto_file(name):
    """The text of one file of the J2 prototype at the pinned commit, from its git object (never its working tree)."""
    repo = next((p for p in (os.environ.get("J2_PROTOTYPE"), str(Path.home() / "Desktop" / "development" / "J2_Prototype")) if p
                 and (Path(p) / ".git").exists()), None)
    if not repo or not shutil.which("git"):
        pytest.skip("the J2 prototype repo is not on this machine (set J2_PROTOTYPE)")
    got = subprocess.run(["git", "-C", repo, "show", "%s:%s" % (PINNED, name)], capture_output=True, text=True)
    if got.returncode:
        pytest.skip("the prototype's pinned commit %s is not in %s" % (PINNED[:7], repo))
    return got.stdout


DRIVER = r"""
const fs = require("fs"), vm = require("vm");
const [htmlPath, statePath, expr] = process.argv.slice(2);
const noop = () => noop;
const el = () => new Proxy({innerHTML: "", textContent: "", value: "", style: {}, dataset: {}, disabled: false, open: false,
  classList: {toggle: noop, add: noop, remove: noop, contains: () => false}, children: [], scrollHeight: 0},
  {get: (t, k) => k in t ? t[k] : k === "querySelectorAll" ? () => [] : noop, set: (t, k, v) => (t[k] = v, true)});
const els = {};
const ctx = vm.createContext({
  document: {getElementById: id => els[id] || (els[id] = el()), querySelector: () => el(), querySelectorAll: () => [],
             body: el(), addEventListener: noop, createElement: el},
  location: {search: "", href: ""}, localStorage: {getItem: () => null, setItem: noop}, CSS: {escape: x => x},
  fetch: () => Promise.reject(new Error("no network")), setTimeout: noop, setInterval: noop, requestAnimationFrame: noop,
  console, URLSearchParams, Date, JSON, Math, Set, Map, Promise});
const scripts = [...fs.readFileSync(htmlPath, "utf8").matchAll(/<script>([\s\S]*?)<\/script>/g)];
vm.runInContext(scripts[scripts.length - 1][1], ctx);
const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
state.allChat = state.chat;
console.log(JSON.stringify(vm.runInContext("(s) => { CTX = s; return " + expr + "; }", ctx)(state)));
"""


def page_state(got, **more):
    """A state as the page polls it: the keys this package builds, and the few others the panes read, at their empty values."""
    s = {"chat": [], "total": 0, "status": "idle", "thinking": None, "turn": None, "step": 0, "steps": {}, "goal": None, "stamped": False,
         "budget": 960, "spent": 0, "calls": 0, "cycle": 1, "doc": False, "done": False, "outcome": None, "paused": None,
         "versions": 0, "output": "website", "files": [], "docset": [], "docset_files": [], "mock": False}
    s.update(got)
    s.update(more)
    return s


def render(state, expr):
    """The prototype's own page code, run in a stub DOM (its j2_ui_render.js way) on `state`, and `expr` of s evaluated in it:
    the HTML a pane draws. A skip without node or the prototype."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "page.html").write_text(proto_file("j2_ui.html"))
        (t / "state.json").write_text(json.dumps(state))
        (t / "driver.js").write_text(DRIVER)
        got = subprocess.run([node, str(t / "driver.js"), str(t / "page.html"), str(t / "state.json"), expr], capture_output=True,
                             text=True, timeout=60)
    assert got.returncode == 0, got.stderr[-1500:]
    return json.loads(got.stdout)


def shown(html):
    """What a person reads of a pane's HTML."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# ---- W1: the skeleton -----------------------------------------------------------------------------------------------
def test_w1_build_gives_exactly_the_thirteen_keys_at_their_empty_values(mods):
    ctx = standin(mods, planned=False)
    got = K.build(ctx)
    assert sorted(got) == sorted(["workflows", "atoms_v1", "sections", "agents", "lanes", "style", "conflicts", "audits", "conditions",
                                  "rubric", "workable", "call_log", "report"])
    assert list(got) == list(K.KEYS), "in the order the state lists them"
    assert got["workflows"] == [] and got["atoms_v1"] == {} and got["sections"] == [] and got["agents"] == {}
    assert [l["id"] for l in got["lanes"]] == ["identity", "adaptation", "priority", "coordination", "audit", "validator"], "no workflow lane yet"
    assert got["style"] is None and got["report"] is None and got["workable"] is None and got["conditions"] is None
    assert got["conflicts"] == [] and got["audits"] == [] and got["rubric"] == [] and got["call_log"] == []
    assert json.loads(json.dumps(got)) == got, "the page reads it as JSON"
    assert ctx.reasons == [], ctx.reasons


def test_w1_empty_is_a_fresh_shape_each_time():
    a, b = K.empty(), K.empty()
    a["workflows"].append(1)
    a["atoms_v1"]["x"] = 1
    assert b["workflows"] == [] and b["atoms_v1"] == {}, "no list or dict is shared between two reads"


def test_w1_the_second_call_is_the_memoised_object(mods):
    ctx = standin(mods, planned=False)
    first = K.build(ctx)
    assert K.build(ctx) is first and ctx.memo["j2ui_work.build"] is first


def test_w1_a_builder_that_raises_empties_its_own_keys_and_leaves_a_reason(mods, monkeypatch):
    ctx = standin(mods, planned=False)

    def boom(*a, **k):
        raise RuntimeError("the lanes could not be read")
    monkeypatch.setattr(K, "_lanes", boom)
    monkeypatch.setattr(K, "_conflicts", lambda c: [{"id": "C-1"}])
    got = K.build(ctx)
    assert got["lanes"] == [], "the failed group is empty"
    assert got["conflicts"] == [{"id": "C-1"}], "every other group is filled"
    assert any(r.startswith("lanes: RuntimeError") for r in ctx.reasons), ctx.reasons
    assert sorted(got) == sorted(K.KEYS) and json.loads(json.dumps(got)) == got


def test_w1_a_context_with_no_memo_and_no_reasons_still_reads(mods, monkeypatch):
    ctx = standin(mods, planned=False)
    del ctx.memo, ctx.reasons
    monkeypatch.setattr(K, "_lanes", lambda *a: 1 / 0)
    got = K.build(ctx)
    assert sorted(got) == sorted(K.KEYS) and got["lanes"] == []


def test_w1_a_group_never_sets_a_key_that_is_not_one_of_the_thirteen(mods, monkeypatch):
    ctx = standin(mods, planned=False)
    monkeypatch.setattr(K, "_audit", lambda c: {"audits": [], "conditions": None, "rubric": [], "workable": None, "extra": 1})
    assert "extra" not in K.build(ctx)


# ---- W2: a workflow for each engine of the registered line --------------------------------------------------------------
def workflows(mods, **kw):
    ctx = standin(mods, **kw)
    return K.build(ctx)["workflows"], ctx


def test_w2_a_four_engine_line_gets_ids_w1_to_w4_and_each_status(mods):
    W, R, J, F = mods
    run(W, "Plan", status="running", what="Planning the pages")
    ask(W, kind="publish", engine="Write", text="Write: wait for a stamp")
    ask(W, kind="envelope", engine="Check", text="Check is past its limit: raise it?")
    run(W, "Publish", status="ok", what="Live site from Build, check passed", wrote={"art": "Live site", "v": 1})
    wfs, ctx = workflows(mods)
    assert [w["id"] for w in wfs] == ["W-1", "W-2", "W-3", "W-4"]
    assert [w["name"] for w in wfs] == LINE
    assert [w["status"] for w in wfs] == ["running", "held", "unfunded", "done"]
    assert [w["agent"] for w in wfs] == ["W-1 Plan", "W-2 Write", "W-3 Check", "W-4 Publish"]
    assert [w["proposal_id"] for w in wfs] == ["plan", "write", "check", "publish"]


@pytest.mark.parametrize("name,setup,want", [
    ("not run yet", lambda W: None, "registered"),
    ("a run that passed", lambda W: run(W, "Plan", status="ok"), "done"),
    ("a run that failed", lambda W: run(W, "Plan", status="failed", what="Plan could not file the plan"), "failed"),
    ("a run that was skipped", lambda W: run(W, "Plan", status="skipped", what="not needed"), "held"),
    ("a run that was interrupted", lambda W: run(W, "Plan", status="interrupted", what="the app closed"), "held"),
    ("a run that waits on the model", lambda W: run(W, "Plan", status="waiting", what="waits on the model"), "held"),
    ("a run that is running", lambda W: run(W, "Plan", status="running"), "running"),
    ("an ask for the engine", lambda W: ask(W, kind="engine", engine="Plan", text="Plan: add a page?"), "held"),
    ("an envelope ask for the engine", lambda W: ask(W, kind="envelope", engine="Plan", text="raise Plan's limit?"), "unfunded"),
    ("an answered ask", lambda W: ask(W, kind="envelope", engine="Plan", status="stamped"), "registered"),
    ("an ask for another engine", lambda W: ask(W, kind="envelope", engine="Write"), "registered"),
    ("a failed run, then a pending envelope ask", lambda W: (run(W, "Plan", status="failed"), ask(W, kind="envelope", engine="Plan")), "unfunded"),
])
def test_w2_the_status_is_read_from_the_engines_state_asks_and_latest_run(mods, name, setup, want):
    W, R, J, F = mods
    setup(W)
    wfs, ctx = workflows(mods)
    assert wfs[0]["name"] == "Plan" and wfs[0]["status"] == want, (name, wfs[0]["status"])
    assert wfs[0]["status"] in K.STATUSES


def test_w2_a_template_the_library_lacks_is_a_failed_workflow(mods):
    ctx = standin(mods)
    ctx.engines[0]["state"] = "Missing"
    ctx.engines[0]["steps_view"] = None
    got = K.build(ctx)["workflows"][0]
    assert got["status"] == "failed" and got["purpose"] == "Reads Brief and writes Site plan", got["purpose"]
    assert got["completion_check"] == "" and got["last_check"] == ""


def test_w2_the_latest_run_decides_not_the_first(mods):
    W, R, J, F = mods
    run(W, "Plan", status="failed", id="r-plan-1", started=ago(120))
    run(W, "Plan", status="ok", id="r-plan-2", started=ago(60))
    wfs, ctx = workflows(mods)
    assert wfs[0]["status"] == "done"


def test_w2_before_roots_check_registers_a_plan_there_is_no_workflow(mods):
    W, R, J, F = mods
    run(W, "Plan", status="ok")
    wfs, ctx = workflows(mods, planned=False)
    assert wfs == [] and K.build(ctx)["agents"] == {}


def test_w2_an_engine_the_plan_left_out_is_not_a_workflow(mods):
    ctx = standin(mods)
    by = {e["name"]: e for e in ctx.engines}
    by["Write"]["in_line"] = False
    by["Write"]["state"] = "Left out"
    by["Write"]["wid"] = "W-4"
    for k, n in enumerate(["Plan", "Check", "Publish"], 1):
        by[n]["wid"] = "W-%d" % k
    got = K.build(ctx)["workflows"]
    assert [(w["id"], w["name"]) for w in got] == [("W-1", "Plan"), ("W-2", "Check"), ("W-3", "Publish")]
    assert "Write" not in [w["name"] for w in got]


def test_w2_a_workflow_carries_every_key_the_page_reads_in_the_prototypes_order(mods):
    wfs, ctx = workflows(mods)
    assert list(wfs[0]) == ["id", "proposal_id", "name", "covers", "fixes", "purpose", "cost", "estimate", "envelope", "charged",
                            "calls_used", "retries_used", "outputs", "completion_check", "dependencies", "status", "cycle",
                            "section", "revises", "agent", "last_check", "version", "atoms"]
    w = wfs[0]
    assert w["covers"] == [] and w["fixes"] == [] and w["estimate"] is None and w["charged"] is True
    assert w["section"] == "" and w["revises"] == "" and w["cycle"] == 1
    assert w["envelope"]["stop_loss"] == "" and set(w["envelope"]) == {"money_limit", "model_call_limit", "time_limit_minutes",
                                                                      "retry_limit", "stop_loss"}


def test_w2_numbers_are_the_records_own(mods):
    W, R, J, F = mods
    run(W, "Plan", status="ok", spend={"calls": 3, "usd": 0.2}, retries=1)
    run(W, "Plan", status="ok", id="r-plan-again", spend={"calls": 2, "usd": 0.1}, retries=2)
    W.set_envelope(REF, "Plan", calls=17, usd=1.5)
    wfs, ctx = workflows(mods)
    w = wfs[0]
    assert w["cost"] == 5, "model calls summed over all of the engine's runs"
    assert w["retries_used"] == 3
    assert w["calls_used"] == 5, "today's calls against the limit"
    assert w["envelope"]["model_call_limit"] == 17 and w["envelope"]["money_limit"] == 1.5
    assert w["envelope"]["retry_limit"] == len(R.WAITS)
    assert w["envelope"]["time_limit_minutes"] == W.dept(REF)["windows"]["Plan"]


def test_w2_a_window_of_nothing_is_no_time_limit(mods):
    ctx = standin(mods)
    ctx.engines[0]["window_min"] = 0
    assert K.build(ctx)["workflows"][0]["envelope"]["time_limit_minutes"] is None


def test_w2_outputs_dependencies_and_version_follow_what_each_engine_reads_and_writes(mods):
    W, R, J, F = mods
    W.add_version(REF, "Site plan", {"site-plan.json": "{}"}, [{"art": "Brief", "v": 1}], "r-x", {"ok": True, "notes": []})
    W.add_version(REF, "Site plan", {"site-plan.json": "{}"}, [{"art": "Brief", "v": 1}], "r-y", {"ok": True, "notes": []})
    wfs, ctx = workflows(mods)
    by = {w["name"]: w for w in wfs}
    assert by["Plan"]["outputs"] == ["site-plan"] and by["Write"]["outputs"] == ["pages"]
    assert by["Plan"]["dependencies"] == [], "Plan reads the Brief, which no engine of the line writes"
    assert by["Write"]["dependencies"] == ["plan"] and by["Check"]["dependencies"] == ["write"]
    assert by["Publish"]["dependencies"] == ["check"]
    assert by["Plan"]["version"] == 2 and by["Write"]["version"] is None


def test_w2_the_checks_are_sentences_never_ids(mods):
    W, R, J, F = mods
    step_row(R, "Plan", "plan.read", notes=["the brief has words"])
    step_row(R, "Plan", "plan.pages", notes=["6 pages proposed"])
    step_row(R, "Plan", "plan.fit", notes=["the home page is first; every address is its own"])
    step_row(R, "Plan", "plan.file", notes=["files and their verdict are both there"])
    wfs, ctx = workflows(mods)
    plan = wfs[0]
    assert plan["completion_check"] == "File the plan: files and their verdict are both there"
    assert plan["last_check"] == "File the plan: files and their verdict are both there"
    assert wfs[1]["last_check"] == "" and wfs[1]["completion_check"] == "Put the pages together", "not run: the step's name alone"
    for w in wfs:
        assert not [s for s in walk(w) if CHECK_ID.match(s)], [s for s in walk(w) if CHECK_ID.match(s)]


def test_w2_the_purpose_is_the_templates_description_in_the_owners_words(mods):
    wfs, ctx = workflows(mods)
    assert wfs[0]["purpose"] == "reads the brief and every ask in it, and plans the site's pages"
    assert all(w["purpose"] for w in wfs) and not BANNED.search(json.dumps(wfs))


def test_w2_the_cycle_is_the_rounds_number_else_one(mods):
    ctx = standin(mods)
    ctx.cur = dict(ctx.cur or {}, round=3)
    assert K.build(ctx)["workflows"][0]["cycle"] == 3


def test_w2_a_real_departments_line_reads_as_workflows(mods, born):
    W, R, J, F = mods
    ref = born()
    ctx = standin(mods, ref=ref)
    got = K.build(ctx)["workflows"]
    assert [w["id"] for w in got] == ["W-1", "W-2", "W-3", "W-4"] and [w["name"] for w in got] == LINE
    assert [w["status"] for w in got] == ["done", "done", "done", "held"], "the first publish waits for the owner's stamp"
    assert [w["version"] for w in got] == [1, 1, 1, None]
    assert all(w["status"] in K.STATUSES for w in got)
    assert not BANNED.search(json.dumps(got)) and not [s for s in walk(got) if CHECK_ID.match(s)]
    assert json.loads(json.dumps(got)) == got


# ---- W4: lanes ----------------------------------------------------------------------------------------------------------
def lanes(mods, **kw):
    ctx = standin(mods, **kw)
    return K.build(ctx)["lanes"], ctx


def by_id(ls):
    return {l["id"]: l for l in ls}


def test_w4_the_lanes_are_the_five_the_validator_then_each_workflow_in_order(mods):
    ls, ctx = lanes(mods)
    assert [l["id"] for l in ls] == ["identity", "adaptation", "priority", "coordination", "audit", "validator", "W-1", "W-2", "W-3", "W-4"]
    assert [l["name"] for l in ls] == FUNCS + ["Validator", "W-1 Plan", "W-2 Write", "W-3 Check", "W-4 Publish"]
    for l in ls:
        assert list(l)[:6] == ["id", "name", "status", "on", "doing", "last_msg"], list(l)
        assert l["status"] in ("idle", "working", "waiting", "blocked")
    assert [("progress" in l) for l in ls] == [False] * 6 + [True] * 4
    assert by_id(ls)["validator"]["doing"] == "code: checks and registers workflows" and by_id(ls)["validator"]["status"] == "idle"
    assert json.loads(json.dumps(ls)) == ls


def test_w4_before_a_plan_is_registered_there_are_the_five_and_the_validator_only(mods):
    ls, ctx = lanes(mods, planned=False)
    assert [l["id"] for l in ls] == ["identity", "adaptation", "priority", "coordination", "audit", "validator"]


@pytest.mark.parametrize("state,step,working", [("assessing", 1, "identity"), ("adapting", 2, "adaptation"), ("bargaining", 3, "priority"),
                                                  ("running", 6, "coordination"), ("closing", 4, "identity")])
def test_w4_the_function_that_holds_the_turn_is_working(mods, state, step, working):
    W, R, J, F = mods
    cycle(W, state, step)
    ls, ctx = lanes(mods)
    got = by_id(ls)
    assert [i for i in FUNCS if got[i.lower()]["status"] == "working"] == [working.capitalize()], {i: l["status"] for i, l in got.items()}
    assert got[working]["doing"], "and says what it is doing"
    assert all(l["on"] is None for l in ls if l["id"] in [f.lower() for f in FUNCS]), "nothing waits on you"
    assert all(l["status"] in ("idle", "working", "waiting", "blocked") for l in ls)


def test_w4_a_blocked_cycle_waits_on_you_and_a_done_one_waits_on_nobody(mods):
    W, R, J, F = mods
    cycle(W, "blocked", 4)
    ls, ctx = lanes(mods)
    idn = by_id(ls)["identity"]
    assert (idn["status"], idn["on"]) == ("waiting", "you") and "needs your words" in idn["doing"]
    cycle(W, "done", 8)
    ls, ctx = lanes(mods)
    assert {l["status"] for l in ls if l["id"] in [f.lower() for f in FUNCS]} == {"idle"} and all(l["on"] is None for l in ls)


def test_w4_a_function_waits_on_you_only_while_something_waits_on_the_owner(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    ls, ctx = lanes(mods)
    assert [l["id"] for l in ls if l["on"] == "you"] == [], "no ask is pending"
    ask(W, kind="publish", engine="Publish", text="Publish: go live for the first time")
    ls, ctx = lanes(mods)
    waiting = [l["id"] for l in ls if l["on"] == "you"]
    assert waiting == ["identity", "W-4"], waiting
    idn = by_id(ls)["identity"]
    assert idn["status"] == "waiting" and "go live for the first time" in idn["doing"]


def test_w4_a_function_that_waits_on_another_says_which(mods):
    W, R, J, F = mods
    cycle(W, "checking", 5)
    ls, ctx = lanes(mods)
    ada = by_id(ls)["adaptation"]
    assert (ada["status"], ada["on"], ada["doing"]) == ("waiting", "Root", "waits on Root's review"), ada


def test_w4_a_fault_is_blocked(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    ctx = standin(mods)
    node = next(n for n in ctx.fv["functions"] if n["fn"] == "audit")
    node.update(state="fault", why="Audit has not read Live site v1", line="Audit has not read Live site v1")
    audit = by_id(K.build(ctx)["lanes"])["audit"]
    assert (audit["status"], audit["on"]) == ("blocked", None) and audit["doing"].startswith("Audit has not read")


def test_w4_the_numbers_are_the_records_not_the_prototypes(mods):
    W, R, J, F = mods
    run(W, "Write", status="ok", id="r-write-a", spend={"calls": 4, "usd": 0.1}, retries=2)
    W.set_envelope(REF, "Write", calls=17, usd=2.0)
    ls, ctx = lanes(mods)
    p = by_id(ls)["W-2"]["progress"]
    assert p["attempt_limit"] == 17 == W.limit_of(W.dept(REF), "Write")["calls"] != 3, "Priority's calls limit"
    assert p["attempts"] == 4 and p["retries"] == 2 and p["retry_limit"] == len(R.WAITS)
    assert p["write_lock"] is False and p["section"] == ""
    assert by_id(ls)["W-1"]["progress"]["attempt_limit"] == W.limit_of(W.dept(REF), "Plan")["calls"]


def test_w4_a_workflow_lane_by_what_the_engine_is_doing(mods):
    W, R, J, F = mods
    run(W, "Plan", status="running", what="Planning the pages")
    ask(W, kind="engine", engine="Write", text="Write: add a page about parking?")
    ask(W, kind="envelope", engine="Check", text="Check is past its limit")
    run(W, "Publish", status="failed", what="Publish could not copy the build")
    step_row(mods[1], "Publish", "publish.copy", ok=False, notes=["no build to copy"], run_id="r-pub")
    ls, ctx = lanes(mods)
    got = by_id(ls)
    assert (got["W-1"]["status"], got["W-1"]["on"], got["W-1"]["doing"]) == ("working", None, "making Site plan")
    assert (got["W-2"]["status"], got["W-2"]["on"]) == ("waiting", "you") and "add a page about parking" in got["W-2"]["doing"]
    assert (got["W-3"]["status"], got["W-3"]["on"]) == ("waiting", "you"), "an unfunded workflow waits on the owner's yes"
    assert got["W-4"]["status"] == "blocked" and got["W-4"]["doing"] == "failed: Copy the build live: no build to copy"
    assert got["W-4"]["progress"]["last_check"] == "Copy the build live: no build to copy"


def test_w4_a_held_workflow_with_no_ask_is_blocked_and_an_idle_one_says_its_last_run(mods):
    W, R, J, F = mods
    run(W, "Plan", status="interrupted", what="the app closed")
    run(W, "Write", status="ok", what="Pages from Site plan, check passed")
    ls, ctx = lanes(mods)
    got = by_id(ls)
    assert got["W-1"]["status"] == "blocked" and got["W-1"]["doing"] == "held: Plan"
    assert got["W-1"]["progress"]["last_check"] == "not run yet"
    assert (got["W-2"]["status"], got["W-2"]["doing"]) == ("idle", "Pages from Site plan, check passed")
    assert (got["W-3"]["status"], got["W-3"]["doing"]) == ("idle", "")


def test_w4_what_a_lane_says_is_in_the_owners_words(mods):
    W, R, J, F = mods
    run(W, "Plan", status="ok", what="granted the line Plan -> Write; Priority countered")
    ask(W, kind="engine", engine="Write", text="Priority refused the line; take the refusal to Identity")
    ls, ctx = lanes(mods)
    text = json.dumps(ls)
    assert not BANNED.search(text), text
    assert "said yes to the line" in by_id(ls)["W-1"]["doing"] and "said no to the line" in by_id(ls)["W-2"]["doing"]


def test_w4_the_owners_own_words_in_a_line_are_not_rewritten(mods):
    W, R, J, F = mods
    words = "Add a page that says we granted every request"
    run(W, "Plan", status="ok", what="took the owner's words: " + words, words=words)
    ls, ctx = lanes(mods)
    assert by_id(ls)["W-1"]["doing"] == "took the owner's words: " + words


def test_w4_last_msg_is_the_id_of_the_agents_last_message(mods):
    W, R, J, F = mods
    post(W, R, "Owner", "Identity", "request", {"word": "request", "words": "Build a site"}, thread="x-1")
    post(W, R, "Adaptation", "Priority", "propose", {"word": "line"}, thread="x-2")
    post(W, R, "Priority", "Adaptation", "accept-proposal", {"word": "line", "why": "fits"}, thread="x-2", hop=2)
    post(W, R, "Adaptation", "Priority", "propose", {"word": "line"}, thread="x-3")
    ls, ctx = lanes(mods)
    got = by_id(ls)
    assert (got["adaptation"]["last_msg"], got["priority"]["last_msg"]) == (4, 3)
    assert got["identity"]["last_msg"] is None and got["validator"]["last_msg"] is None and got["W-1"]["last_msg"] is None


def test_w4_a_stopped_department_has_no_lane_working(mods):
    W, R, J, F = mods
    run(W, "Plan", status="running")
    W.set_stopped(REF, True)
    ls, ctx = lanes(mods)
    assert "working" not in {l["id"]: l["status"] for l in ls if l["id"] in [f.lower() for f in FUNCS]}.values()


def test_w4_the_prototypes_page_draws_the_lanes(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    run(W, "Plan", status="running", what="Planning the pages")
    ask(W, kind="publish", engine="Publish")
    got = K.build(standin(mods))
    html = render(page_state(got), "renderLanes(s)")
    text = shown(html)
    assert "Agents · live status" in text and "Identity" in text and "Validator" in text and "W-1 Plan" in text
    assert "waiting on you" in text and "working" in text
    assert re.search(r"section\s*· attempts 0/%d · retries 0/%d" % (W.limit_of(W.dept(REF), "Plan")["calls"], len(R.WAITS)), text), text
    assert "last check: not run yet" in text
    assert not re.search(r"undefined|NaN|\bnull\b|\[object", text)


# ---- W7: docs, preview, call and the call log ------------------------------------------------------------------------------
T0, T1, T2, T3 = ("2026-10-26T10:00:0%d+05:30" % n for n in range(4))


def model_step(R, engine="Priority", step="priority.bargain", started=T0, ended=T2, **more):
    return step_row(R, engine, step, notes=more.pop("notes", ["the answer is say yes, ask for less or say no"]), calls=more.pop("calls", 1),
                    started=started, ended=ended, ms=more.pop("ms", 2000), **more)


def test_w7_docs_preview_and_call_answer_with_the_prototypes_empty_shapes(mods):
    ctx = standin(mods)
    empty_doc = {"asked": False, "text": None, "workflows": []}
    assert K.docs(ctx) == {"prd": empty_doc, "hld": empty_doc, "lld": empty_doc}
    d = K.docs(ctx)
    d["prd"]["workflows"].append("x")
    assert K.docs(ctx)["prd"]["workflows"] == [], "a shape of its own each time"
    assert K.preview(ctx, "W-1.a1") == {"anchor": None, "html": None} == K.preview(ctx, "nothing")
    assert K.call(ctx, 1) is None and K.call(ctx, "x") is None


def test_w7_the_prototypes_page_says_no_document_was_asked_for(mods):
    ctx = standin(mods)
    text = shown(render(page_state(K.build(ctx)), "(Object.assign(DOCS, %s), renderDocs())" % json.dumps(K.docs(ctx))))
    assert text.count("Not asked for in this run.") == 3 and "Not written yet" not in text


def test_w7_a_department_with_no_model_step_has_an_empty_call_log(mods, born):
    ref = born()
    ctx = standin(mods, ref=ref)
    assert K.build(ctx)["call_log"] == []
    assert K.build(standin(mods))["call_log"] == []


def test_w7_a_step_that_made_a_call_is_a_row_with_nothing_nobody_recorded(mods):
    W, R, J, F = mods
    cycle(W, "bargaining", 3)
    step_row(R, "Plan", "plan.pages", notes=["6 pages proposed"], calls=2, started=T0, ended=T3, ms=3400, answer="Six pages: Home, About")
    step_row(R, "Plan", "plan.read", notes=["the brief has words"], calls=0, started=T0, ended=T1)          # code: no call
    model_step(R, answer="Priority granted the line")
    ctx = standin(mods)
    got = K.build(ctx)["call_log"]
    assert [c["id"] for c in got] == [1, 2] and [c["fn"] for c in got] == ["W-1", "priority"]
    one = got[0]
    assert list(one) == ["id", "fn", "step", "cycle", "t", "seconds", "model", "tokens", "chars", "inputs", "reply", "reason", "atom"]
    assert one["atom"] == "W-1.a2", "Plan's second slot step: the prototype's calls carry the atom they made"
    assert (one["t"], one["seconds"], one["model"], one["tokens"], one["reason"], one["cycle"]) == ("10:00:03", 3.4, None, None, "", 1)
    assert one["chars"] == {"prompt": 0, "reply": len("Six pages: Home, About")}
    assert one["inputs"] == [["step", "Propose the pages"]] and one["reply"] == {"say": "Six pages: Home, About"}
    two = got[1]
    assert "atom" not in two, "a function's step is no atom's"
    assert two["inputs"] == [["step", "Say yes, ask for less, or say no"]] and two["reply"] == {"say": "Priority said yes to the line"}
    assert all(c["tokens"] is None and c["model"] is None for c in got)
    assert json.loads(json.dumps(got)) == got and not BANNED.search(json.dumps(got))


def test_w7_a_call_with_no_answer_says_what_the_steps_check_noted_or_nothing(mods):
    W, R, J, F = mods
    model_step(R, notes=["the answer is say yes, ask for less or say no"])
    model_step(R, notes=[], started=T1, ended=T2)
    got = K.build(standin(mods))["call_log"]
    assert got[0]["reply"] == {"say": "the answer is say yes, ask for less or say no"} and got[0]["chars"]["reply"] == 0
    assert got[1]["reply"] is None, "the page then says 'No usable reply.'"


def test_w7_a_decisions_bare_answer_is_said_as_the_act_in_the_owners_words_whoever_made_the_call(mods):
    """The record keeps a decision's answer as one word: priority.bargain's accept, counter or reject (a model step, mode slot) and a
    gate's admit, wait or refuse. The page prints a call's reply as it is, so the word would reach the owner as 'counter'."""
    W, R, J, F = mods
    cycle(W, "bargaining", 3)
    for engine, step, mode in (("Priority", "priority.bargain", "slot"), ("Coordination", "coord.edge", "gate"), ("Plan", "plan.pages", "slot")):
        for answer in ACTS_SAID:
            model_step(R, engine=engine, step=step, answer=answer, mode=mode, notes=["it was decided"])
    out = K.build(standin(mods))
    said = [c["reply"]["say"] for c in out["call_log"]]
    assert said == list(ACTS_SAID.values()) * 3
    assert not BARE.search(json.dumps(out)) and not BANNED.search(json.dumps(out)), "no act's own word anywhere in what the page is sent"
    assert not [s for s in walk(out) if s.strip().lower() in ACTS_SAID]
    assert [c["chars"]["reply"] for c in out["call_log"][:6]] == [len(a) for a in ACTS_SAID], "the length is the record's"


def test_w7_the_acts_words_are_the_layers_and_the_runtimes_own(mods):
    """The table is one place: Priority's three are layers/priority's SAID and a gate's three are engine_runtime's GATE_SAYS. A word
    either of them says differently must be said differently here too."""
    import j2ui_atoms
    from layers.priority import v1 as priority
    W, R, J, F = mods
    assert j2ui_atoms.PRIORITY_SAID == dict(priority.SAID)
    assert {a: ACTS_SAID[a] for a in R.GATE_SAYS} == R.GATE_SAYS
    assert dict(j2ui_atoms.PRIORITY_SAID, **R.GATE_SAYS) == ACTS_SAID


def test_w7_a_bare_word_in_any_case_is_still_the_act(mods):
    W, R, J, F = mods
    model_step(R, answer="Counter")
    model_step(R, answer=" REJECT ", started=T1, ended=T2)
    assert [c["reply"]["say"] for c in K.build(standin(mods))["call_log"]] == ["asked for less", "said no"]


def test_w7_a_code_that_is_no_act_gives_way_to_the_steps_first_check_note(mods):
    W, R, J, F = mods
    model_step(R, engine="Identity", step="identity.take", answer="go", notes=["the verdict is go, ask or stop"])
    model_step(R, engine="Identity", step="identity.take", answer="ask", notes=[], started=T1, ended=T2)
    model_step(R, engine="Identity", step="identity.take", answer="accept-proposal", notes=["it was decided"], started=T2, ended=T3)
    model_step(R, engine="Priority", step="priority.bargain", answer="brief_is_text", notes=["it was decided"], started=T0, ended=T1)
    model_step(R, engine="Coordination", step="coord.tie", answer="Plan", notes=["names who goes first"], started=T1, ended=T2)
    out = K.build(standin(mods))["call_log"]
    assert [c["reply"] for c in out] == [{"say": "the verdict is go, ask or stop"}, None, {"say": "it was decided"},
                                         {"say": "it was decided"}, {"say": "Plan"}]
    assert not BARE.search(json.dumps(out)) and not BANNED.search(json.dumps(out))


def one_call_each_slot_step(R, mods):
    """A model call for every slot step of every engine of the line, oldest first; returns {(engine, step id): row}."""
    rows = {}
    for e in standin(mods, chat=False).engines:
        for s in [s for s in (e["steps_view"] or {}).get("steps") or [] if s.get("mode") == "slot"]:
            rows[(e["name"], s["id"])] = step_row(R, e["name"], s["id"], notes=["fine"], calls=1, started=T0, ended=T1, answer="Said it")
    return rows


def test_w7_a_call_names_the_atom_its_step_made_the_same_id_the_workflows_atom_has(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    rows = one_call_each_slot_step(R, mods)
    got = K.build(standin(mods))
    by_step = {(w["name"], a["how"]["steps"]): a["id"] for w in got["workflows"] for a in w["atoms"]}
    assert len(rows) == len(by_step) > 4, "every slot step is an atom, and each made a call"
    said = {c["id"]: c for c in got["call_log"]}
    assert len(said) == len(rows) and all(c.get("atom") for c in said.values())
    asked = {(c["fn"], c["inputs"][0][1]): c["atom"] for c in said.values()}
    assert {a for a in asked.values()} == set(by_step.values()), "each atom has its call, and the id is the one the atom has"
    assert all(a.startswith(w) for (w, _), a in asked.items()), "and the atom is of the workflow that made it"
    ids = [c["atom"] for c in got["call_log"]]
    assert len(ids) == len(set(ids)) and all(re.fullmatch(r"W-\d+\.a\d+", i) for i in ids)


def test_w7_a_step_that_is_no_atom_or_an_engine_outside_the_line_names_none(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    plan = next(e for e in standin(mods).engines if e["name"] == "Plan")
    decisions = [s for s in plan["steps_view"]["steps"] if s.get("mode") != "slot"]
    step_row(R, "Plan", "plan.pages", notes=["fine"], calls=1)
    if decisions:
        step_row(R, "Plan", decisions[0]["id"], notes=["fine"], calls=1, mode=decisions[0]["mode"], started=T1, ended=T2)
    model_step(R, engine="Priority", step="priority.bargain", started=T2, ended=T3)
    step_row(R, "Plan", "not.a.step.of.plan", notes=["fine"], calls=1, started=T2, ended=T3)
    got = K.build(standin(mods))["call_log"]
    assert [c.get("atom") for c in got] == ["W-1.a2"] + [None] * (len(got) - 1), got
    assert K.build(standin(mods, planned=False))["call_log"] and not [c for c in K.build(standin(mods, planned=False))["call_log"] if "atom" in c], \
        "before Root's check registers a plan there is no workflow, so no atom"


def test_w7_the_pages_atom_card_shows_the_call_it_made_and_is_not_told_there_was_none(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    step_row(R, "Plan", "plan.pages", notes=["6 pages proposed"], calls=2, started=T0, ended=T3, ms=3400, answer="Six pages: Home, About")
    got = K.build(standin(mods))
    state = page_state(got, calls=2)
    card = lambda j: shown(render(state, "atomCards(s, Object.assign({}, s.workflows[0], {atoms: [s.workflows[0].atoms[%d]]}))" % j))
    made, other = card(1), card(0)
    assert "Work atom 1 W-1.a2" in made and "No AI call yet" not in made, made
    assert "step: Propose the pages" in made and "Reply received call 1 Six pages: Home, About" in made, made
    assert re.search(r"Cost 1 AI call\(s\) · \d+ characters in and out · 3\.4 s", made), made
    assert "Work atom 1 W-1.a1" in other and other.count("No AI call yet") == 4, "an atom whose step made no call still says so"


def test_w7_the_step_a_call_was_made_in_is_the_cycles_step_at_that_time(mods):
    W, R, J, F = mods
    cycle(W, "bargaining", 3)
    event(J, "proposal.created", "Adaptation", "Priority", "pending", "Proposed", step=2)
    ev_at = J.events(REF)[0]["occurred_at"]
    model_step(R, started=ev_at, ended=ev_at)
    model_step(R, started="2000-01-01T00:00:00+05:30", ended="2000-01-01T00:00:01+05:30")
    got = K.build(standin(mods))["call_log"]
    assert [c["step"] for c in got] == [2, None]


def test_w7_a_message_is_linked_to_the_one_call_of_its_author_that_brackets_its_time(mods):
    W, R, J, F = mods
    model_step(R, started=T0, ended=T2)                                   # Priority's call, 10:00:00 to 10:00:02
    post(W, R, "Priority", "Adaptation", "accept-proposal", {"word": "line", "why": "fits"}, thread="x-1", at=T1)       # inside it
    post(W, R, "Priority", "Adaptation", "accept-proposal", {"word": "line", "why": "fits"}, thread="x-2", at="2026-10-26T10:00:03+05:30")  # a second after
    post(W, R, "Priority", "Adaptation", "accept-proposal", {"word": "line", "why": "fits"}, thread="x-3", at="2026-10-26T10:00:04+05:30")  # too late
    post(W, R, "Adaptation", "Priority", "propose", {"word": "line"}, thread="x-4", at=T1)                              # another author
    post(W, R, "Owner", "Identity", "request", {"word": "request", "words": "Build a site"}, thread="x-5", at=T1)       # the owner's
    ctx = standin(mods)
    K.build(ctx)
    by_post = {ctx.chat[i - 1]["id"]: ctx.chat[i - 1] for i in ctx.msg_of.values()}
    linked = {m["id"]: m.get("calls") for m in ctx.chat}
    assert linked == {1: [1], 2: [1], 3: None, 4: None, 5: None}, linked
    assert "calls" not in by_post[3] and "calls" not in by_post[4] and "calls" not in by_post[5]


def test_w7_two_calls_that_overlap_a_message_link_neither(mods):
    W, R, J, F = mods
    model_step(R, started=T0, ended=T2)
    model_step(R, started=T1, ended=T3)
    post(W, R, "Priority", "Adaptation", "accept-proposal", {"word": "line", "why": "fits"}, thread="x-1", at=T1)
    post(W, R, "Priority", "Adaptation", "accept-proposal", {"word": "line", "why": "fits"}, thread="x-2", at=T0)
    ctx = standin(mods)
    K.build(ctx)
    assert [m.get("calls") for m in ctx.chat] == [None, [1]], "the first matches both calls and is left alone; the second only the first"


def test_w7_a_message_that_has_calls_keeps_them_and_the_link_is_made_once(mods):
    W, R, J, F = mods
    model_step(R)
    post(W, R, "Priority", "Adaptation", "accept-proposal", {"word": "line", "why": "fits"}, thread="x-1", at=T1)
    ctx = standin(mods)
    ctx.chat[0]["calls"] = [99]
    K.build(ctx)
    assert ctx.chat[0]["calls"] == [99]
    ctx2 = standin(mods)
    K.build(ctx2)
    first = list(ctx2.chat[0]["calls"])
    ctx2.memo.clear()
    K.build(ctx2)
    assert ctx2.chat[0]["calls"] == first == [1]


def test_w7_the_dialog_shows_a_linked_messages_cost_and_an_unlinked_one_says_it_was_code(mods):
    W, R, J, F = mods
    model_step(R, started=T0, ended=T2, ms=2000)
    post(W, R, "Priority", "Adaptation", "accept-proposal", {"word": "line", "why": "fits today"}, thread="x-1", at=T1)
    post(W, R, "Adaptation", "Priority", "propose", {"word": "line"}, thread="x-2", at=T1)
    ctx = standin(mods)
    got = K.build(ctx)
    state = page_state(got, chat=ctx.chat, total=len(ctx.chat))
    linked = shown(render(state, "(state = s, openDetail(1), $('dbody').innerHTML)"))
    assert "What it read" in linked and "step Say yes, ask for less, or say no" in linked
    assert re.search(r"AI calls\s+1\s", linked) and re.search(r"time\s+2\.0 s", linked), linked
    assert "not reported by this provider" in linked and "Written by code" not in linked
    unlinked = shown(render(state, "(state = s, openDetail(2), $('dbody').innerHTML)"))
    assert "Written by code, no AI call" in unlinked and re.search(r"AI calls\s+0\s", unlinked) and "instant (code)" in unlinked


def test_w7_a_failure_in_the_log_leaves_every_other_key_filled(mods, monkeypatch):
    W, R, J, F = mods
    model_step(R)
    ctx = standin(mods)
    monkeypatch.setattr(K, "_call_row", lambda *a: 1 / 0)
    got = K.build(ctx)
    assert got["call_log"] == [] and [w["id"] for w in got["workflows"]] == ["W-1", "W-2", "W-3", "W-4"]
    assert [r for r in ctx.reasons if r.startswith("call log: ZeroDivisionError")], ctx.reasons
    assert sorted(got) == sorted(K.KEYS) and json.loads(json.dumps(got)) == got


def test_w7_a_ctx_with_no_step_rows_at_all_still_gives_every_key(mods):
    ctx = standin(mods)
    ctx.steps = None
    got = K.build(ctx)
    assert got["call_log"] == [] and sorted(got) == sorted(K.KEYS) and json.loads(json.dumps(got)) == got
    assert ctx.reasons, "and says why"


def test_w7_a_department_with_thousands_of_rows_builds_in_bounded_time_and_links_the_same(mods, monkeypatch):
    """The page polls every 700 ms and the adapter rebuilds on a change: linking a message to its call must not look at every
    call for every message (5,000 posts, 20,000 step rows and 20,000 ledger events), and a registered plan with nothing on file
    for a function's pane to refine does not read the pane (functions_view.function reads all of those rows whole, for each)."""
    import time
    import functions_view
    panes_read = []
    real = functions_view.function
    monkeypatch.setattr(functions_view, "function", lambda ref, fn: (panes_read.append(fn), real(ref, fn))[1])
    ctx = standin(mods)
    base = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    at = lambda s: (base + timedelta(seconds=s)).isoformat(timespec="seconds")
    steps_per_engine = ("plan.read", "plan.pages", "write.list", "check.build", "publish.copy")
    ctx.steps = [{"id": "s-%d" % i, "run": "r-%d" % (i // 5), "engine": ("Plan", "Plan", "Write", "Check", "Publish")[i % 5], "step": steps_per_engine[i % 5],
                  "mode": "slot", "check": {"ok": True, "notes": ["fine"]}, "calls": 0, "started": at(i), "ended": at(i), "ms": 10,
                  "read": [{"art": "Brief", "v": 1}]} for i in range(20000)]
    for k in range(2500):                                  # Priority's calls: one every 4 seconds, 2 seconds long
        ctx.steps.append({"id": "c-%d" % k, "run": None, "engine": "Priority", "step": "priority.bargain", "mode": "slot", "calls": 1,
                          "check": {"ok": True, "notes": ["fine"]}, "started": at(4 * k), "ended": at(4 * k + 2), "ms": 2000})
    ctx.posts = [{"n": n, "src": "Priority", "dst": ["Adaptation"], "msg_type": "accept-proposal", "thread": "x-%d" % n, "hop": 2,
                  "payload": {"word": "line", "why": "fits"}, "at": at(4 * n + 1)} for n in range(1, 5001)]
    ctx.events = [{"seq": i, "step": 6, "action": "run.completed", "occurred_at": at(i), "payload": {}} for i in range(1, 20001)]
    fake_chat(ctx)
    t = time.time()
    got = K.build(ctx)
    took = time.time() - t
    assert took < 10, "built in %.1f s" % took
    assert len(got["call_log"]) == 2500 and [r["id"] for r in got["call_log"][:3]] == [1, 2, 3]
    linked = [m for m in ctx.chat if m.get("calls")]
    # post n is at 4n+1 and call k (id k+1) runs from 4k to 4k+2, a second's grace after: post n is inside call n, and no other; there
    # is no call 2500, so the last post of the 2,500 calls' span is linked to none
    assert len(linked) == 2499 and all(m["calls"] == [m["id"] + 1] for m in linked), (len(linked), [m["calls"] for m in linked[:5]])
    assert ctx.reasons == [], ctx.reasons
    assert ctx.planned and panes_read == [], "no pane is read when the record holds nothing to refine: %s" % panes_read
