"""test_functions_view.py -- the five functions as one read of the record (functions_view.py; PRD M1.1).

Named claims:
  F1  one fixture per cycle state (assessing, waiting, adapting, bargaining, closing, checking, reshaping, running,
      unread, pursuing, blocked, stopped, done) gives the expected state for all five; a stopped department's word is
      'stopped' on every function, the one word the Map, the list, All five and the pane print (test_website.js)
  F2  the thread rule: the src of an open thread that wrote its latest post waits on the decider; the decider does not
  F3  a stopped or a done department never shows a function working, whatever runs or waits
  F4  a failed step check is a fault, and so is a start that should have fired (Audit with no run after the version it
      starts on; Coordination idle while two engines are ready); inside the grace window neither is
  F5  the read carries no private key and no path, and it writes nothing
  F6  the route answers for a department on the engine runtime and 404s for any other ref
  F7  the cycle says where the department is in the owner's words, with its eight steps, and needs_you only when it does;
      each function's last act is the act and to whom, in the owner's words, never the words a post carried
  F8  every word of the read is the owner's in every state: said yes, asked for less, said no and sent back, never grant,
      counter or refuse (the bargain on the record, a dropped plan, a department Root set up, a running function, and
      every state a real department passes through when Priority says no, Identity asks, the owner says no, Identity
      rules it runs, or Root's check sends a plan back); a rule's tag (go, ask, refuse, always) is the owner's own word
      and stays
  F9  rendered by the panel's own scripts from the real reads of departments Root set up (tests/fixtures/pane_words.js),
      no function's pane, nor the Map, All five or the list, shows grant, counter or refuse at rest or on a hover: the
      older cards under each page (steps, gates, Moves, Control, Stamped by rule, the who-may-post table) included

Each department is born the way the app makes one (website_dept.create), then its record is set to the state under
test, so what is read is the record a real department keeps.
"""
import importlib
import json
import os
import re
import shutil
import subprocess
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
    nodes, got = _expect(F)
    assert got["cycle"]["says"] == "Stopped by you"
    # one word for stopped, on every function, which the Map, the list, All five and the pane all print (round 1, gap 2);
    # a cycle stopped on its own is the department stopped, whatever its switch says
    assert {n["word"] for n in nodes.values()} == {"stopped"} and got["stopped"] is True
    _cycle(W, "done", 8)
    nodes, got = _expect(F)
    assert got["cycle"]["says"] == "Goal reached" and got["cycle"]["needs_you"] is False
    assert all(s["state"] in ("done", "skipped") for s in got["cycle"]["steps"])
    assert {n["word"] for n in nodes.values()} == {"quiet"} and got["stopped"] is False


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


def test_f7_the_last_act_is_what_the_function_did_never_the_words_it_carried(mods):
    """A post names its act and to whom, in the owner's words; the words it carried (the owner's goal, Priority's why)
    are its detail, never the act (round 1, gap 6)."""
    W, R, J, F = mods
    words = "A website for the hospital, with a page for each of the 12 doctors"

    def said(src, dst, act, word, **pl):
        n = len(R.board(REF)) + 1
        R._append(REF, "board.jsonl", {"n": n, "src": src, "dst": [dst], "msg_type": act, "thread": "x-b", "hop": 1, "about": None,
                                       "payload": dict(pl, word=word), "ack_id": None, "by": None, "at": _ago(-n)})
        return {x["name"]: x["last"] for x in F.functions(REF)["functions"]}
    last = said("Identity", "Adaptation", "request", "line", words=words)
    assert last["Identity"] == {"what": "asked Adaptation for the plan", "detail": words, "at": last["Identity"]["at"]}
    last = said("Adaptation", "Priority", "propose", "line", words=words)
    assert last["Adaptation"]["what"] == "proposed the plan to Priority" and last["Adaptation"]["detail"] == words
    assert said("Priority", "Adaptation", "accept-proposal", "line", why="the envelope has room")["Priority"]["what"] == "said yes to the plan"
    assert said("Priority", "Adaptation", "propose", "line", why="keep Plan only")["Priority"]["what"] == "asked Adaptation for less"
    last = said("Priority", "Adaptation", "reject-proposal", "line", why="the envelope has no room today")
    assert last["Priority"] == {"what": "said no to the plan", "detail": "the envelope has no room today", "at": last["Priority"]["at"]}
    assert said("Audit", "Identity", "inform", "finding", claim="Home has no phone line")["Audit"]["what"] == "told Identity what it found"
    assert said("Identity", R.OWNER, "request", "publish", objective="say whether the site may go live")["Identity"]["what"] == "asked you about going live"


def test_f7_on_a_born_department_the_last_act_is_the_functions_own(mods, born):
    W, R, J, F = mods
    ref = born(WEBSITE, "Acme Learning")
    last = {n["name"]: n["last"] for n in F.functions(ref)["functions"]}
    for fn in ("Identity", "Adaptation", "Priority"):
        assert last[fn] and WEBSITE not in last[fn]["what"], (fn, last[fn])
    assert last["Priority"]["what"].startswith("said yes"), last["Priority"]
    assert last["Adaptation"]["what"].split()[0] in ("proposed", "registered"), last["Adaptation"]


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

    def make(words, org, settle=True):
        root = founding.found_structure(org, owner="Sankalp")["root"]
        W.owner_ask(root, words)
        W.run_until_idle(root, limit=300)
        child = next(d for d in W.list_depts() if d.get("parent") == root)
        if settle:
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


# What the screen prints of a read: ids and ledger actions are names it never prints as words, and a rule's tag (go, ask,
# refuse, always) is the owner's own word for a rule (PRD S5: "Tags go, ask, refuse and always"), so neither is scanned.
RULE_TAGS = re.compile(r"\bgo, ask, refuse,? (?:or |and )?always\b|\ba refuse rule\b")
BANNED = ("grant", "counter", "refus", "orders")


def _shown(v):
    def drop(x):
        if isinstance(x, dict):
            return {k: drop(y) for k, y in x.items() if k not in ("id", "action", "tag")}
        return [drop(y) for y in x] if isinstance(x, list) else x
    return RULE_TAGS.sub(" ", json.dumps(drop(v)).lower())


def _banned(v):
    text = _shown(v)
    return [(w, text[max(0, text.index(w) - 60):text.index(w) + 40]) for w in BANNED if w in text]


def test_m17_no_charter_no_internal_system_no_path_and_the_route(mods):
    W, R, J, F = mods
    import website_api
    importlib.reload(website_api)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(website_api.router)
    c = TestClient(app)

    def scan(state):
        for fn in JOURNEYS:
            got = c.get("/api/native/%s/functions/%s" % (REF, fn))
            assert got.status_code == 200, fn
            text = _shown(got.json())
            assert "charter" not in text and "internal system" not in text, (state, fn)
            assert "/users/" not in text and str(W.ddir(REF)).lower() not in text and ".json" not in text, (state, fn)
            assert not _banned(got.json()), (state, fn, _banned(got.json()))
        assert not _banned(c.get("/api/native/%s/functions" % REF).json()), state
    scan("a fresh department")
    # the bargain on the record and the plan dropped: every word the screen prints is still the owner's (gap 1, round 1)
    _cycle(W, "blocked", 4)
    J.note(REF, 3, "Priority", "Adaptation", "proposal.refused", "refused", "Refused.", "r1")
    scan("blocked")
    assert c.get("/api/native/%s/functions/marketing" % REF).status_code == 404
    assert c.get("/api/native/dref-nothing/functions/identity").status_code == 404


def test_m17_the_bargain_and_a_dropped_plan_read_in_the_owners_words(mods):
    """The ledger's default summaries (J.on_post), Root's check that did not hold, the owner's no and a blocked cycle:
    the five's read and each function's page carry said yes, asked for less and said no, never grant, counter or refuse;
    Identity's own acts and recipe read the same way."""
    W, R, J, F = mods
    _cycle(W, "blocked", 4)
    J.note(REF, 3, "Priority", "Adaptation", "proposal.granted", "granted", "Granted within the envelope.", "g1")
    J.note(REF, 3, "Priority", "Adaptation", "proposal.countered", "waiting", "Countered.", "c1")
    J.note(REF, 3, "Priority", "Adaptation", "proposal.refused", "refused", "Refused.", "r1")
    J.note(REF, 5, "Root", "Adaptation", "workflow.blocked", "refused", "Root's check refused the workflow: the plan has no Check.", "w1")
    J.note(REF, 1, "User", "Identity", "ask.answered", "complete", "The owner refused it.", "o1")
    _run(W, "Priority", status="ok", system=True, what="granted the line Plan -> Write -> Check -> Publish")
    got = F.functions(REF)
    assert not _banned(got), _banned(got)
    nodes = {n["name"]: n for n in got["functions"]}
    assert nodes["Identity"]["state"] == "waiting_on_you" and nodes["Identity"]["line"] == "the plan was dropped; it needs your words"
    steps = {s["name"]: s for s in got["cycle"]["steps"]}
    assert steps["Price"]["last"]["summary"] == "Said no." and steps["Root's review"]["last"]["summary"].startswith("Root's check sent the plan back")
    for fn in JOURNEYS:
        page = F.function(REF, fn)
        assert not _banned(page), (fn, _banned(page))
    pr = F.function(REF, "priority")
    assert [(b["said"], b["summary"]) for b in pr["j2"]["bargains"]] == [
        ("said yes", "Said yes within the limit."), ("asked for less", "Asked for less."), ("said no", "Said no.")]
    assert {j["id"]: j["status"] for j in pr["journeys"]}["FP2"] == "said no"
    fa1 = {j["id"]: j for j in F.function(REF, "adaptation")["journeys"]}["FA1"]
    assert fa1["status"] == "sent back" and fa1["last"]["summary"].startswith("Root's check sent the plan back")
    idn = F.function(REF, "identity")
    fields = {f["key"]: f["value"] for f in idn["fields"]}
    assert "Says no to you, Adaptation, Coordination" in fields["writes"] and "Take a no" in fields["hears"]
    assert any("Drop what was turned down" == s["name"] for s in idn["recipe"])
    assert {j["id"]: j["last"]["summary"] for j in idn["journeys"] if j["last"]}["FI1"] == "The owner said no."
    # while a function's run goes, its line is the handler's name, which carries the inside word (round 2, gap 2): the
    # Map's box, its hover, the All five card and the list's title read it in the owner's words too
    _cycle(W, "unread", 7)
    for i, (fn, what, said) in enumerate((("Adaptation", "Priority granted the line", "Priority said yes to the line"),
                                          ("Adaptation", "Priority refused the line", "Priority said no to the line"),
                                          ("Adaptation", "Priority countered the line", "Priority asked for less on the line"),
                                          ("Identity", "Take a refusal", "Take a no"), ("Coordination", "Hear a refusal", "Hear a no"))):
        W._write(W.ddir(REF) / "runs.json", [r for r in W.runs(REF) if r.get("status") != "running"])
        _run(W, fn, system=True, what=what, id="r-running-%d" % i)
        got = F.functions(REF)
        node = next(n for n in got["functions"] if n["name"] == fn)
        assert node["state"] == "working" and node["line"] == said, (what, node)
        assert not _banned(got), (what, _banned(got))
        assert not _banned(F.function(REF, fn.lower())["node"]), what


def test_m17_a_born_department_reads_in_the_owners_words(mods, born):
    """What a department's own runs say (granted the line, Priority's grant, the envelope given to each engine) reaches
    the screen in the owner's words too, on a department Root set up."""
    W, R, J, F = mods
    ref = born(WEBSITE, "Acme Learning")
    assert any("grant" in str(r.get("what") or "") for r in W.runs(ref)), "the record's own runs say granted"
    assert not _banned(F.functions(ref)), _banned(F.functions(ref))
    for fn in JOURNEYS:
        page = F.function(ref, fn)
        assert not _banned(page), (fn, _banned(page))


def _model(monkeypatch, R, answers):
    """test_j2.py's model that is a function: a step id maps to what the AI inside says; every other step falls to its
    draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)

    def model(prompt, step):
        if step["id"] not in answers:
            return None, 0.0, "offline"
        return answers[step["id"]], 0.01, "model"
    monkeypatch.setattr(R, "MODEL", model)


def _stepped(W, J, F, ref, bad, limit=300):
    """Run the department one start at a time, as the motor does, and read the five and each function's page after
    every start, so every state the real flow passes through is read, not only where it comes to rest."""
    for _ in range(limit):
        for v in [F.functions(ref)] + [F.function(ref, fn) for fn in JOURNEYS]:
            if _banned(v):
                bad.append((J.status(ref).get("state"), v.get("fn") or "five", _banned(v)))
        if not W.run_until_idle(ref, limit=1):
            return


def test_m17_the_real_flow_reads_in_the_owners_words_in_every_state_it_passes(mods, born, monkeypatch):
    """Round 2, gap 4: the record's own lines reach the screen in the owner's words in the states a real department
    passes through, not only on the happy path. Priority's AI says no, Identity's draft puts the plan to the owner (the
    ask's text is Identity's line, at rest on All five and its pane), the owner says no (Identity's tell is its last
    act's detail); and Root's check sends a plan back once, so Adaptation reshapes it (FA1's row and the Propose pill)."""
    W, R, J, F = mods
    _model(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "the envelope has no room today"}})
    ref, bad = born(WEBSITE, "Acme Learning", settle=False), []
    _stepped(W, J, F, ref, bad)
    got = F.functions(ref)
    idn = next(n for n in got["functions"] if n["name"] == "Identity")
    assert J.status(ref)["state"] == "waiting" and idn["state"] == "waiting_on_you", (J.status(ref), idn)
    assert "Priority said no to the plan: the envelope has no room today" in idn["line"], idn["line"]
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "conflict"]:
        W.decide_ask(ref, a["id"], False)
    _stepped(W, J, F, ref, bad)
    assert J.status(ref)["state"] == "blocked"
    last = next(n for n in F.functions(ref)["functions"] if n["name"] == "Identity")["last"]
    assert last and "said no" in " ".join(filter(None, [last["what"], last["detail"]])), last
    # Identity rules the plan runs: its tell says Priority did not say yes, never that it did not grant
    _model(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "the envelope has no room today"},
                            "identity.close": {"ruling": "run", "why": "the goal cannot be met without a site"}})
    ruled = born(WEBSITE, "Run Co", settle=False)
    _stepped(W, J, F, ruled, bad)
    assert "workflow.registered" in [e["action"] for e in J.events(ruled)]
    assert not bad, bad[:3]

    real, calls = R._root_check, {"n": 0}

    def check(ref, d, engines, source):
        calls["n"] += 1
        return ["Facts reads Notes, which nothing before it writes"] if calls["n"] == 1 else real(ref, d, engines, source)
    monkeypatch.setattr(R, "_root_check", check)
    _model(monkeypatch, R, {})
    ref, seen = born(ORGANIC, "Lab Co", settle=False), []
    states = []
    for _ in range(300):
        states.append(J.status(ref).get("state"))
        for v in [F.functions(ref)] + [F.function(ref, fn) for fn in JOURNEYS]:
            if _banned(v):
                seen.append((states[-1], v.get("fn") or "five", _banned(v)))
        if not W.run_until_idle(ref, limit=1):
            break
    assert calls["n"] >= 2 and "adapting" in states, states
    assert not seen, seen[:3]


# ---- M1.7 (round 2, gap 1): the older cards under each function's page say the owner's words too -----------------------
PANE_DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "fixtures", "pane_words.js")


def _reads(W, ref):
    """The reads a function's pane, the Map and All five really make, from the real routes, by the tail of their path."""
    import website_api
    importlib.reload(website_api)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(website_api.router)
    c = TestClient(app)
    tails = ["map", "functions", "board", "status"] + ["functions/" + fn for fn in JOURNEYS] + ["steps/" + fn.capitalize() for fn in JOURNEYS]
    out = {}
    for t in tails:
        got = c.get("/api/native/%s/%s" % (ref, t))
        assert got.status_code == 200, (t, got.status_code)
        out[t] = got.json()
    return {"name": W.dept(ref)["name"], "reads": out}


def _panes(tmp_path, reads):
    """What a person sees on each function's pane, the Map, All five and the list, rendered by the panel's own scripts
    from those reads (tests/fixtures/pane_words.js): the text at rest, and the hovers apart."""
    src = tmp_path / ("reads-%d.json" % len(list(tmp_path.glob("reads-*.json"))))
    src.write_text(json.dumps(reads))
    p = subprocess.run(["node", PANE_DRIVER, str(src)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def _banned_shown(text):
    text = RULE_TAGS.sub(" ", text.lower())
    return [text[max(0, text.index(w) - 60):text.index(w) + 40] for w in BANNED if w in text]


def test_m17_every_card_on_a_functions_pane_says_the_owners_words(mods, born, monkeypatch, tmp_path):
    """The function's page sits on top of the older cards (its steps, gates and Moves, Identity's Control and Stamped by
    rule, Priority's limits, Coordination's who-may-post table): those cards print the steps, map and status reads, whose
    names and run lines are the record's inside words (a handler's name, a step's name, a function's goal, a run's line).
    Rendered from the real reads of departments Root set up, the bargain on the record and Priority saying no, no pane,
    nor the Map, All five or the list, shows grant, counter or refuse, at rest or on a hover."""
    W, R, J, F = mods
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    ref = born(WEBSITE, "Acme Learning")
    panes = _panes(tmp_path, _reads(W, ref))
    for k, v in panes.items():
        assert v["rest"], k
        assert not _banned_shown(v["rest"]) and not _banned_shown(v["hover"]), (k, _banned_shown(v["rest"] + " " + v["hover"]))
    assert "Runs within your rules" in panes["identity"]["rest"], "Identity's Control, in the owner's words"
    assert "Gates" in panes["identity"]["rest"] and "Stamped by rule" in panes["identity"]["rest"], "the older cards are there"
    assert "Say yes, ask for less, or say no" in panes["priority"]["rest"], "Priority's bargain step"
    assert "says no" in panes["coordination"]["rest"], "the who-may-post table's act words"
    assert "Priority said yes to the line" in panes["adaptation"]["rest"], "Adaptation's handler, as it hears Priority"
    # Priority says no, and Identity puts the plan to the owner: the conflict ask is at rest on Identity's line
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: ({"answer": "reject", "why": "the envelope has no room today"}, 0.01, "model")
                        if step["id"] == "priority.bargain" else (None, 0.0, "offline"))
    ref = born(WEBSITE, "No Room Co")
    assert J.status(ref)["state"] == "waiting"
    panes = _panes(tmp_path, _reads(W, ref))
    for k, v in panes.items():
        assert not _banned_shown(v["rest"]) and not _banned_shown(v["hover"]), (k, _banned_shown(v["rest"] + " " + v["hover"]))
    assert "Priority said no to the plan" in panes["five"]["rest"], "the ask at rest on All five"
    # an organic department: Adaptation shapes its engines and Identity adds each on Priority's yes (Stamped by rule)
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: (None, 0.0, "offline"))
    ref = born(ORGANIC, "Lab Co")
    assert W.dept(ref)["engines"]
    panes = _panes(tmp_path, _reads(W, ref))
    for k, v in panes.items():
        assert not _banned_shown(v["rest"]) and not _banned_shown(v["hover"]), (k, _banned_shown(v["rest"] + " " + v["hover"]))
