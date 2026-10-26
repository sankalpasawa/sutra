"""test_j2ui_work.py -- the page's work content: workflows, lanes, call log (j2ui_work.py; UI port, package j2ui-work).

Named claims (each step of the package adds its own):
  W1  build(ctx) gives exactly the thirteen keys the page reads, each at its empty value when nothing fills it, as JSON; a
      builder that raises empties only its own keys and leaves a reason; the result is the memoised object
  W2  a workflow for each engine of the registered line, in the line's order, W-1 on; none before Root's check registers a plan;
      an engine the plan left out is no workflow; the status is one of the page's six words, read from the engine's state, its
      asks and its latest run; and no string of a workflow is a check's id

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
import types
from datetime import datetime, timedelta, timezone

import pytest

import j2ui_work as K

REF = "dref-jw0001"
FUNCS = ["Identity", "Adaptation", "Priority", "Coordination", "Audit"]
LINE = ["Plan", "Write", "Check", "Publish"]
BANNED = re.compile(r"GRANT|COUNTER|REFUSE|accept-proposal|reject-proposal", re.I)
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


# ---- W1: the skeleton -----------------------------------------------------------------------------------------------
def test_w1_build_gives_exactly_the_thirteen_keys_at_their_empty_values(mods):
    ctx = standin(mods, planned=False)
    got = K.build(ctx)
    assert sorted(got) == sorted(["workflows", "atoms_v1", "sections", "agents", "lanes", "style", "conflicts", "audits", "conditions",
                                  "rubric", "workable", "call_log", "report"])
    assert list(got) == list(K.KEYS), "in the order the state lists them"
    assert got["workflows"] == [] and got["atoms_v1"] == {} and got["sections"] == [] and got["agents"] == {}
    assert got["lanes"] == []
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
    run(W, "Plan", status="ok", spend={"calls": 3, "usd": 0.2}, retries=1, started=ago(300))
    run(W, "Plan", status="ok", id="r-plan-again", spend={"calls": 2, "usd": 0.1}, retries=2, started=ago(100))
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
