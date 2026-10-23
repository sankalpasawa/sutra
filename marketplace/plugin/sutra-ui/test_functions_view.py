"""test_functions_view.py -- the five functions as one read of the record (functions_view.py; PRD M1.1).

Named claims:
  F1  one fixture per cycle state (assessing, waiting, adapting, bargaining, closing, checking, reshaping, running,
      unread, pursuing, blocked, stopped, done) gives the expected state for all five
  F2  the thread rule: the src of an open thread that wrote its latest post waits on the decider; the decider does not
  F3  a stopped or a done department never shows a function working, whatever runs or waits
  F4  a failed step check is a fault, and so is a start that should have fired (Audit with no run after the version it
      starts on; Coordination idle while two engines are ready); inside the grace window neither is
  F5  the read carries no private key and no path, and it writes nothing
  F6  the route answers for a department on the engine runtime and 404s for any other ref
  F7  the cycle says where the department is in the owner's words, with its eight steps, and needs_you only when it does

Each department is born the way the app makes one (website_dept.create), then its record is set to the state under
test, so what is read is the record a real department keeps.
"""
import importlib
import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

REF = "dref-fv0001"
FUNCS = ["Identity", "Adaptation", "Priority", "Coordination", "Audit"]


@pytest.fixture
def mods(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
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


def _ago(s):
    return (datetime.now(timezone.utc) - timedelta(seconds=s)).astimezone().isoformat(timespec="seconds")


def _cycle(W, state, step, **more):
    row = {"cycle_id": "cycle-test", "step": step, "journey": "J2", "state": state, "open_ask": None, "workflow": [],
           "repairs": 0, "updated_at": W.now()}
    row.update(more)
    W._write(W.ddir(REF) / "j2-state.json", row)


def _ask(W, kind="publish", **more):
    row = {"id": "a-" + kind, "kind": kind, "engine": more.pop("engine", "Publish"), "text": more.pop("text", "Publish: go live for the first time"),
           "status": "pending", "created": W.now()}
    row.update(more)
    W._put_ask(REF, row)
    return row


def _thread(W, R, src, dst, act, word, state="working", tid="x-t1"):
    """A thread on the board whose latest post is src's, as engine_runtime.post writes them."""
    n = len(R.board(REF)) + 1
    R._append(REF, "board.jsonl", {"n": n, "src": src, "dst": [dst], "msg_type": act, "thread": tid, "hop": 1, "about": None,
                                   "payload": {"word": word}, "ack_id": None, "by": None, "at": W.now()})
    ths = [t for t in R.threads(REF) if t["id"] != tid]
    ths.append({"id": tid, "opened_by": src, "with": [dst], "topic": word, "protocol": "propose" if act == "propose" else "inform",
                "decider": dst, "bounds": dict(R.BOUNDS), "default": "cancel", "state": state, "hops": 1, "spent": 0.0,
                "age_s": 0.0, "opened": W.now(), "closed": None, "outcome": None})
    R._save_threads(REF, ths)


def _run(W, engine, status="running", what="Write a page", system=False, **more):
    row = {"id": "r-" + engine.lower() + status, "engine": engine, "system": system, "slot": more.pop("slot", "%s@x.v1" % engine),
           "status": status, "started": more.pop("started", W.now()), "ended": None if status == "running" else W.now(),
           "what": what, "wrote": more.pop("wrote", None), "chain": None, "spend": {"calls": 0, "usd": 0.0}, "retries": 0}
    row.update(more)
    W._put_run(REF, row)
    return row


def _states(F):
    got = F.functions(REF)
    return {n["name"]: n["state"] for n in got["functions"]}, {n["name"]: n for n in got["functions"]}, got


def _expect(F, **want):
    states, nodes, got = _states(F)
    full = {fn: want.get(fn, "quiet") for fn in FUNCS}
    assert states == full, (states, [(n["name"], n["line"], n["waits_on"]) for n in nodes.values()])
    return nodes, got


# ---- F1: one fixture per cycle state --------------------------------------------------------------------------------
def test_f1_assessing_identity_holds_the_turn(mods):
    W, R, J, F = mods
    _cycle(W, "assessing", 1)
    nodes, got = _expect(F, Identity="working")
    assert nodes["Identity"]["line"] == "reading your words"
    assert got["cycle"]["says"] == "Reading your words"


def test_f1_waiting_identity_waits_on_you(mods):
    W, R, J, F = mods
    a = _ask(W, "j2_identity", engine="Identity", text="What evidence will prove this department is done?", missing="done-when")
    _cycle(W, "waiting", 1, open_ask=a["id"])
    nodes, got = _expect(F, Identity="waiting_on_you")
    assert nodes["Identity"]["waits_on"] == "you" and nodes["Identity"]["word"] == "waits on you"
    assert nodes["Identity"]["line"] == "What evidence will prove this department is done?"
    assert got["cycle"]["needs_you"] is True and got["cycle"]["says"] == "Waiting for your answer"


def test_f1_adapting_and_reshaping_are_adaptations_turn(mods):
    W, R, J, F = mods
    _cycle(W, "adapting", 2)
    nodes, _ = _expect(F, Adaptation="working")
    assert nodes["Adaptation"]["line"] == "proposing the work"
    _cycle(W, "reshaping", 5)
    nodes, got = _expect(F, Adaptation="working")
    assert nodes["Adaptation"]["line"] == "reshaping the plan" and got["cycle"]["says"] == "Reshaping the plan"


def test_f1_bargaining_priority_prices_and_adaptation_waits_on_it(mods):
    W, R, J, F = mods
    _cycle(W, "bargaining", 3)
    _thread(W, R, "Adaptation", "Priority", "propose", "line")
    nodes, got = _expect(F, Priority="working", Adaptation="waiting")
    assert nodes["Adaptation"]["waits_on"] == "Priority" and nodes["Adaptation"]["line"] == "waits on Priority"
    assert got["cycle"]["says"] == "Pricing the plan"


def test_f1_closing_identity_settles_and_adaptation_waits_on_it(mods):
    W, R, J, F = mods
    _cycle(W, "closing", 4)
    _thread(W, R, "Adaptation", "Identity", "inform", "conflict", state="submitted")
    nodes, got = _expect(F, Identity="working", Adaptation="waiting")
    assert nodes["Adaptation"]["waits_on"] == "Identity"
    assert got["cycle"]["says"] == "Settling a disagreement"


def test_f1_checking_adaptation_waits_on_root(mods):
    W, R, J, F = mods
    _cycle(W, "checking", 5)
    nodes, got = _expect(F, Adaptation="waiting")
    assert nodes["Adaptation"]["waits_on"] == "Root"
    assert got["cycle"]["says"] == "Root is reviewing the plan"


def test_f1_running_coordination_and_the_running_engine(mods):
    W, R, J, F = mods
    _cycle(W, "running", 6)
    _run(W, "Write")
    nodes, got = _expect(F, Coordination="working")
    assert nodes["Coordination"]["line"] == "Write's turn"
    assert got["cycle"]["running"] == ["Write"] and got["cycle"]["says"] == "Write is working"


def test_f1_running_with_an_ask_waiting_on_you(mods):
    W, R, J, F = mods
    _cycle(W, "running", 6)
    _ask(W, "publish")
    nodes, got = _expect(F, Identity="waiting_on_you")
    assert nodes["Identity"]["line"] == "Publish: go live for the first time"
    assert got["cycle"]["asks"] == 1 and got["cycle"]["needs_you"] is True


def test_f1_pursuing_identity_waits_on_you_while_a_finding_is_asked(mods):
    W, R, J, F = mods
    _cycle(W, "pursuing", 8)
    _ask(W, "finding", engine="Audit", text="Audit found: on Home, the phone line is missing. Stamp to have it put right.")
    nodes, got = _expect(F, Identity="waiting_on_you")
    assert nodes["Identity"]["line"].startswith("Audit found:")
    assert got["cycle"]["says"] == "Working on what Audit found"


def test_f1_unread_says_audit_has_not_read_the_result(mods):
    """M0.3's state: a version Audit's judge did not read leaves the cycle at step 7, never clean; the functions read
    says it in the same words as the department screen (DP_J2_SAYS in 20-dept.js), not as a raw state name."""
    W, R, J, F = mods
    _cycle(W, "unread", 7)
    nodes, got = _expect(F)
    assert got["cycle"]["says"] == "Audit has not read the result" and got["cycle"]["needs_you"] is False
    assert [s["state"] for s in got["cycle"]["steps"] if s["step"] == 7] == ["now"]


def test_f1_blocked_identity_needs_your_words(mods):
    W, R, J, F = mods
    _cycle(W, "blocked", 4)
    nodes, got = _expect(F, Identity="waiting_on_you")
    assert got["cycle"]["says"] == "Stuck: needs your words" and got["cycle"]["needs_you"] is True


def test_f1_stopped_and_done_are_quiet_throughout(mods):
    W, R, J, F = mods
    _cycle(W, "stopped", 6)
    _run(W, "Write")
    _ask(W, "publish")
    _expect(F)
    assert F.functions(REF)["cycle"]["says"] == "Stopped by you"
    _cycle(W, "done", 8)
    nodes, got = _expect(F)
    assert got["cycle"]["says"] == "Goal reached" and got["cycle"]["needs_you"] is False
    assert all(s["state"] in ("done", "skipped") for s in got["cycle"]["steps"])


def test_f1_a_department_with_no_cycle_reads_its_runs_and_asks(mods):
    W, R, J, F = mods
    nodes, got = _expect(F)
    assert got["cycle"]["state"] in ("not_started", "not_ready") and got["cycle"]["says"] == "Not started"
    _run(W, "Audit", what="Judge the pages against the brief", system=True)
    nodes, _ = _expect(F, Audit="working")
    assert nodes["Audit"]["line"] == "Judge the pages against the brief"


# ---- F2: the thread rule ------------------------------------------------------------------------------------------
def test_f2_the_wait_is_on_the_src_of_the_latest_post(mods):
    W, R, J, F = mods
    _cycle(W, "running", 6)
    _thread(W, R, "Coordination", "Priority", "request", "verdict", tid="x-v")
    nodes, _ = _expect(F, Coordination="working")            # the turn is Coordination's: the turn wins over a wait
    _cycle(W, "adapting", 2)
    _thread(W, R, "Adaptation", "Priority", "propose", "line", tid="x-l")
    nodes, _ = _expect(F, Adaptation="working", Coordination="waiting")
    assert nodes["Coordination"]["waits_on"] == "Priority" and nodes["Priority"]["state"] == "quiet", "the decider does not wait"
    # the decider answered: the latest post is Priority's, and on a closed thread nobody waits
    _thread(W, R, "Priority", "Adaptation", "accept-proposal", "line", state="completed", tid="x-l")
    _cycle(W, "running", 6)
    nodes, _ = _expect(F, Coordination="working")
    assert nodes["Priority"]["waits_on"] is None and nodes["Adaptation"]["waits_on"] is None


# ---- F3: stopped and done never show working ---------------------------------------------------------------------
def test_f3_stopped_by_the_record_switch_is_quiet_even_without_a_cycle(mods):
    W, R, J, F = mods
    _run(W, "Identity", system=True, what="Take a request")
    _thread(W, R, "Adaptation", "Priority", "propose", "line")
    d = W.dept(REF)
    d["stopped"] = True
    W.save_dept(REF, d)
    states, nodes, got = _states(F)
    assert set(states.values()) == {"quiet"} and got["cycle"]["state"] == "stopped" and got["stopped"] is True


# ---- F4: faults ---------------------------------------------------------------------------------------------------
def test_f4_a_failed_step_check_is_a_fault(mods):
    W, R, J, F = mods
    R._append(REF, "steps.jsonl", {"id": "s-1", "run": "r-1", "engine": "Identity", "step": "identity.read", "mode": "slot",
                                   "status": "failed", "why": "Read the words: the brief is not text", "started": W.now(), "ended": W.now()})
    nodes, _ = _expect(F, Identity="fault")
    assert nodes["Identity"]["why"] == "Read the words: the brief is not text" and nodes["Identity"]["word"] == "fault"


def test_f4_audit_should_have_fired_after_the_version_it_starts_on(mods):
    W, R, J, F = mods
    W.add_version(REF, "Live site", {"index.html": "<html><body><h1>Home</h1><p>Hello.</p></body></html>"},
                  [{"art": "Build", "v": 1}], "r-pub", {"ok": True, "notes": ["live"]})
    _expect(F)                                               # inside the grace window: not yet a fault
    rows = json.loads((W.ddir(REF) / "artifacts" / "live-site" / "versions.json").read_text())
    rows[-1]["at"] = _ago(F.FIRE_GRACE_S + 60)
    (W.ddir(REF) / "artifacts" / "live-site" / "versions.json").write_text(json.dumps(rows))
    nodes, _ = _expect(F, Audit="fault")
    assert nodes["Audit"]["why"] == "Audit has not read Live site v1"
    _run(W, "Audit", status="ok", system=True, what="read the live site", slot="Audit@live-site.v1")
    _expect(F)                                               # it ran on that version: no fault


def test_f4_coordination_idle_while_two_engines_are_ready(mods, monkeypatch):
    W, R, J, F = mods
    monkeypatch.setattr(F, "_ready_now", lambda ref, d: ["Plan", "Write"])
    rs = W.runs(REF)
    for r in rs:
        r["started"] = _ago(F.FIRE_GRACE_S + 60)
    W._write(W.ddir(REF) / "runs.json", rs)
    nodes, _ = _expect(F, Coordination="fault")
    assert nodes["Coordination"]["why"] == "Plan and Write are ready and nothing has started"
    monkeypatch.setattr(F, "_ready_now", lambda ref, d: ["Plan"])
    _expect(F)


def test_f4_ready_now_asks_by_peek_and_finds_two_engines(mods):
    W, R, J, F = mods
    W.add_version(REF, "Brief", {"brief.md": "# Website\n\nA website for the hospital\n"}, [{"ask": "A website", "at": W.now()}],
                  "owner", {"ok": True, "notes": ["the owner's words"]})
    W.add_version(REF, "Site plan", {"site-plan.json": json.dumps({"pages": [{"slug": "index", "title": "Home"}]})},
                  [{"art": "Brief", "v": 1}], "r-x", {"ok": True, "notes": []})
    before = sorted(os.listdir(W.ddir(REF)))
    ready = F._ready_now(REF, W.dept(REF))
    assert "Plan" in ready and "Write" in ready, ready
    assert sorted(os.listdir(W.ddir(REF))) == before, "a peek writes nothing"


# ---- F5: no private key, no path, no write ----------------------------------------------------------------------
def test_f5_no_private_key_no_path_and_nothing_written(mods):
    W, R, J, F = mods
    _cycle(W, "running", 6)
    _run(W, "Identity", status="ok", system=True, what="read /Users/someone/.sutra-ui/native/dref-fv0001/brief.md")
    J.note(REF, 6, "Identity", "Coordination", "run.completed", "complete", "filed at /Users/someone/secret/x.json", "k1",
           {"private_reasoning": "hidden", "token": "t"})
    home = str(W.ddir(REF))
    snap = {p: os.path.getmtime(os.path.join(home, p)) for p in os.listdir(home)}
    got = F.functions(REF)
    text = json.dumps(got)
    assert "/Users/" not in text and home not in text and ".sutra-ui" not in text
    assert "private_reasoning" not in text and '"token"' not in text
    nodes = {n["name"]: n for n in got["functions"]}
    assert nodes["Identity"]["last"]["what"] == "read brief.md"
    assert {p: os.path.getmtime(os.path.join(home, p)) for p in os.listdir(home)} == snap, "the read wrote nothing"


def test_f5_the_read_never_calls_the_model(mods, monkeypatch):
    W, R, J, F = mods
    called = []
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: called.append(step) or (None, 0.0, "offline"))
    monkeypatch.setattr(W, "model_json", lambda *a, **k: called.append("model_json"))
    W.give_goal(REF, "A website for the hospital")
    _cycle(W, "running", 6)
    F.functions(REF)
    assert called == []


# ---- F6: the route ---------------------------------------------------------------------------------------------------
def test_f6_the_route_answers_for_a_runtime_department_and_404s_otherwise(mods, monkeypatch):
    W, R, J, F = mods
    import website_api
    importlib.reload(website_api)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(website_api.router)
    c = TestClient(app)
    got = c.get("/api/native/%s/functions" % REF)
    assert got.status_code == 200
    body = got.json()
    assert [n["name"] for n in body["functions"]] == FUNCS
    assert set(body["cycle"]) >= {"state", "step", "says", "steps", "needs_you", "ceiling"}
    assert "not_recorded" in body
    assert c.get("/api/native/dref-nothing/functions").status_code == 404
    monkeypatch.setenv("SUTRA_ENGINE_RUNTIME", "1")
    W.create("dref-old0001", "The first build", None)
    assert c.get("/api/native/dref-old0001/functions").status_code == 404, "a department not on the engine runtime"


# ---- F7: the cycle, in words ------------------------------------------------------------------------------------------
def test_f7_the_eight_steps_and_settle_skipped_without_a_conflict(mods):
    W, R, J, F = mods
    _cycle(W, "running", 6)
    got = F.functions(REF)["cycle"]
    assert [s["name"] for s in got["steps"]] == ["Enough to work", "Propose", "Price", "Settle", "Root's review", "Run", "Read", "Next or done"]
    assert [s["state"] for s in got["steps"]] == ["done", "done", "done", "skipped", "done", "now", "next", "next"]
    J.note(REF, 4, "Adaptation", "Identity", "conflict.raised", "waiting", "The bargain did not close.", "c1")
    got = F.functions(REF)["cycle"]
    assert got["steps"][3]["state"] == "done" and got["steps"][3]["last"]["summary"] == "The bargain did not close."
    assert got["needs_you"] is False


def test_f7_every_node_carries_its_last_act_and_spend(mods):
    W, R, J, F = mods
    got = F.functions(REF)
    nodes = {n["name"]: n for n in got["functions"]}
    assert nodes["Priority"]["last"]["what"] == "gave each engine its limit", "the record's words, in the owner's"
    assert 0 <= nodes["Priority"]["spend"]["share"] <= 1 and nodes["Priority"]["spend"]["calls_limit"] > 0
    assert "what Adaptation did" in got["not_recorded"]


# ---- M1.2: speaks-to and made-by from the record ---------------------------------------------------------------------
WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"


@pytest.fixture
def born(mods, monkeypatch):
    """A department as a person makes one: found the organisation, say the words, Root sets it up (test_j2.py's way)."""
    monkeypatch.setenv("J1_FLOW_V1", "1")
    W, R, J, F = mods
    import founding
    import org2_apply
    import placement_engine as E
    for m in (E, org2_apply, founding):
        importlib.reload(m)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")

    def make(words, org):
        root = founding.found_structure(org, owner="Sankalp")["root"]
        W.owner_ask(root, words)
        W.run_until_idle(root, limit=300)
        child = next(d for d in W.list_depts() if d.get("parent") == root)
        W.run_until_idle(child["ref"], limit=300)
        return child["ref"]
    return make


def test_m12_website_plan_made_the_site_plan_and_write_reads_it(mods, born):
    W, R, J, F = mods
    ref = born(WEBSITE, "Acme Learning")
    got = F.functions(ref)
    made = {m["art"]: m for m in got["made"]}
    assert made["Site plan"]["by"] == "Plan" and "Write" in made["Site plan"]["readers"]
    assert made["Pages"]["by"] == "Write" and made["Pages"]["readers"] == ["Check"]
    assert made["Brief"]["by"] == "Owner" and made["Brief"]["readers"] == ["Plan"], "the Brief is the owner's own words"
    assert "Audit" in made["Live site"]["readers"], "a function's reads count too"
    pairs = {(p["from"], p["to"]): p["n"] for p in got["speaks"]}
    assert pairs.get(("Owner", "Identity"), 0) >= 1, "the owner spoke to Identity"
    assert any(src == "Identity" and dst == "Owner" for src, dst in pairs), "and Identity back to the owner"
    assert any(src == "Adaptation" and dst == "Priority" for src, dst in pairs), "the bargain is a pair"
    nodes = {n["name"]: n for n in got["functions"]}
    assert any(s["to"] == "Priority" for s in nodes["Adaptation"]["speaks_to"])
    assert not [x for x in got["not_recorded"] if x.startswith("who made")], got["not_recorded"]


def test_m12_an_organic_department_with_shaped_engines_needs_no_map(mods, born):
    W, R, J, F = mods
    ref = born(ORGANIC, "Lab Co")
    d = W.dept(ref)
    assert d["kind"] == "organic" and d["engines"], "shaped engines on the record"
    got = F.functions(ref)
    made = {m["art"]: m for m in got["made"]}
    defs = R.defs()["engines"]
    for name in d["engines"]:
        e = defs[name]
        if W.versions(ref, e["writes"]):
            assert made[e["writes"]]["by"] == name, (name, made[e["writes"]])
        readers = [n for n in d["engines"] if defs[n].get("reads") == e["writes"]]
        assert all(r in made[e["writes"]]["readers"] for r in readers), (e["writes"], readers)
    first = d["engines"][0]
    assert first in made[defs[first]["reads"]]["readers"]


def test_m12_a_version_whose_maker_is_not_on_the_record_is_named_not_recorded(mods):
    W, R, J, F = mods
    W.add_version(REF, "Site plan", {"site-plan.json": "{}"}, [{"art": "Brief", "v": 1}], "r-gone", {"ok": True, "notes": []})
    got = F.functions(REF)
    made = {m["art"]: m for m in got["made"]}
    assert made["Site plan"]["by"] is None and "who made Site plan v1" in got["not_recorded"]


# ---- M1.4: the Org sheet's words reach Root, and the department is born on the runtime ----------------------------------
def test_m14_the_sheets_words_set_up_a_runtime_department_with_its_five_functions(mods, born, monkeypatch):
    """What the Org sheet sends under an organisation with a Root (19-org2.js o2SendRequest): Root's front door reads
    it as a set-up, and the department it makes is on the engine runtime, with the five functions' read."""
    W, R, J, F = mods
    import founding
    root = founding.found_structure("Thread & Loom", owner="Sankalp")["root"]
    W.owner_ask(root, "Set up a department: Billing. Invoices for every customer, sent by email")
    W.run_until_idle(root, limit=300)
    kids = [d for d in W.list_depts() if d.get("parent") == root]
    assert len(kids) == 1 and kids[0]["runtime"] == 2, kids
    got = F.functions(kids[0]["ref"])
    assert [n["name"] for n in got["functions"]] == FUNCS


# ---- M1.7: each function as its site page holds it ------------------------------------------------------------------
JOURNEYS = {"identity": ["FI1", "FI2", "FI3", "FI4"], "adaptation": ["FA1", "FA2", "FA3", "FA4", "FA5"], "priority": ["FP1", "FP2"],
            "coordination": ["FC1", "FC2"], "audit": ["FAU1"]}


def test_m17_every_function_has_its_page_fields_recipe_journeys_and_version_one(mods):
    W, R, J, F = mods
    for fn, ids in JOURNEYS.items():
        p = F.function(REF, fn)
        assert p["name"] == fn.capitalize() and p["line"] and p["v1"] and p["holds"] and p["hands_to"]
        assert [f["key"] for f in p["fields"]] == ["goal", "done", "hears", "writes", "checks", "envelope", "settings"]
        done = next(f for f in p["fields"] if f["key"] == "done")
        assert done["placeholder"] is True and done["value"] is None, "a placeholder the screen shows as 'not set yet'"
        assert p["template"]["name"], fn
        assert p["recipe"] and all(s["by"] in ("code", "AI", "person") and s["rung"] in ("P", "C0", "C1", "C2") for s in p["recipe"])
        assert [j["id"] for j in p["journeys"]] == ids
        assert all(j["status"] for j in p["journeys"]) and p["node"]["name"] == fn.capitalize()
    later = {j["id"]: j["status"] for j in F.function(REF, "adaptation")["journeys"]}
    assert later["FA4"] == "later" and later["FA5"] == "later" and later["FA2"] == "not built yet" and later["FA1"] == "not run yet"
    with pytest.raises(ValueError):
        F.function(REF, "marketing")


def test_m17_each_journey_shows_its_live_status_and_last_move_from_the_record(mods):
    W, R, J, F = mods
    _cycle(W, "running", 6)
    J.note(REF, 1, "Identity", "Adaptation", "identity.assessed", "complete", "The identity is good enough to start on.", "a1")
    J.note(REF, 4, "Adaptation", "Identity", "conflict.raised", "waiting", "The bargain did not close.", "c1")
    J.note(REF, 2, "Adaptation", "Priority", "proposal.created", "pending", "Proposed the workflow Plan -> Write.", "p1")
    J.note(REF, 3, "Priority", "Adaptation", "proposal.countered", "waiting", "Keep Plan only: the room is one engine.", "k1")
    J.note(REF, 6, "Priority", "Write", "envelope.held", "held", "Write is past its envelope.", "h1")
    J.note(REF, 6, "Coordination", "Write", "slot.assigned", "assigned", "Write has the next turn.", "s1")
    J.note(REF, 7, "Audit", "Identity", "audit.finding_filed", "recorded", "Audit read Live site v1 and found nothing to put right.", "f1")
    _thread(W, R, "Owner", "Identity", "request", "request", tid="x-o")
    R._append(REF, "board.jsonl", {"n": 99, "src": "Coordination", "dst": ["Identity"], "msg_type": "inform", "thread": "x-l", "hop": 0,
                                   "about": None, "payload": {"word": "lost", "words": "a page for the doctors"}, "at": W.now()})
    R._append(REF, "steps.jsonl", {"id": "s-g", "engine": "Identity", "step": "identity.gate", "mode": "gate", "answer": "admit",
                                   "status": "ok", "started": W.now(), "ended": W.now()})
    want = {"identity": {"FI1": "done", "FI2": "heard", "FI3": "let through", "FI4": "waiting"},
            "adaptation": {"FA1": "waiting"}, "priority": {"FP1": "held", "FP2": "waiting"},
            "coordination": {"FC1": "running", "FC2": "told Identity"}, "audit": {"FAU1": "done"}}
    for fn, rows in want.items():
        got = {j["id"]: j for j in F.function(REF, fn)["journeys"]}
        for jid, status in rows.items():
            assert got[jid]["status"] == status, (fn, jid, got[jid])
            assert got[jid]["last"] and got[jid]["last"]["summary"] and got[jid]["last"]["at"], (fn, jid)
    fp2 = {j["id"]: j for j in F.function(REF, "priority")["journeys"]}["FP2"]
    assert fp2["last"]["summary"] == "Keep Plan only: the room is one engine."
    j2 = F.function(REF, "priority")["j2"]
    assert [b["said"] for b in j2["bargains"]] == ["asked for less"], "the owner's words: said yes, asked for less, said no"


def test_m17_no_charter_no_internal_system_no_path_and_the_route(mods):
    W, R, J, F = mods
    import website_api
    importlib.reload(website_api)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(website_api.router)
    c = TestClient(app)
    for fn in JOURNEYS:
        got = c.get("/api/native/%s/functions/%s" % (REF, fn))
        assert got.status_code == 200, fn
        shown = json.loads(json.dumps(got.json()))
        def drop_ids(v):                                    # ids are names the screen never prints as words
            if isinstance(v, dict):
                return {k: drop_ids(x) for k, x in v.items() if k not in ("id", "action")}
            return [drop_ids(x) for x in v] if isinstance(v, list) else v
        text = json.dumps(drop_ids(shown)).lower()
        assert "charter" not in text and "internal system" not in text, fn
        assert "/users/" not in text and str(W.ddir(REF)).lower() not in text and ".json" not in text, fn
        for word in ("granted", "countered", "orders"):
            assert word not in text, (fn, word)
    assert c.get("/api/native/%s/functions/marketing" % REF).status_code == 404
    assert c.get("/api/native/dref-nothing/functions/identity").status_code == 404
