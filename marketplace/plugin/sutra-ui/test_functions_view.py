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
      each function's last act is the act and to whom, in the owner's words, never the words a post carried, and so is
      each of the last messages between the five that All five's Between them shows (M1.8)
  F8  every word of the read is the owner's in every state: said yes, asked for less, said no and sent back, never grant,
      counter or refuse (the bargain on the record, a dropped plan, a department Root set up, a running function, and
      every state a real department passes through when Priority says no, Identity asks, the owner says no, Identity
      rules it runs, or Root's check sends a plan back); a rule's tag (go, ask, refuse, always) is the owner's own word
      and stays
  F9  rendered by the panel's own scripts from the real reads of departments Root set up (tests/fixtures/pane_words.js),
      no function's pane, nor the Map, All five or the list, shows grant, counter or refuse at rest or on a hover: the
      older cards under each page (steps, gates, Moves, Control, Stamped by rule, the who-may-post table) included;
      and every tab of each pane, its page, its Chat and its Settings, and the owner's own chat on the department and on
      Root, read in the owner's words when Priority says yes, asks for less and says no, the owner says no, and Root's
      check sends a plan back, served the real /chat, /chat?fn= and /api/dept/ reads; when Identity says no to a request
      and the owner says no to an ask too, and no surface prints an act by its id: Coordination's who-may-post check
      says each act in the board's words ('The owner may say no to Identity'), one table on the server and the screen
  F10 every ask Identity puts to the owner says its answers in the words of its two buttons, Stamp and Say no (the
      conflict, the outside-the-site, the instructions, the engine and the line asks), at rest and on a hover
  F11 on a department on the engine runtime each function's pane agrees with the record: the registry's older cards
      (the department card, the framework, Proposals, Queue, the graph, Recent) are not drawn under the page, so the
      owner is named once and no pane says there are no engines or nothing in the queue while the record holds them;
      and Identity's pane shows what it holds from the record, once: the goal, the done-when and each rule with its tag;
      a record from before Root drafted done-when items keeps its done line, and the pane says that line, once
  F12 Coordination's own state from the record (PRD M4.5): one timetable row per engine of the line, each with its slot
      and where it stands; a waiting engine names what it waits for ('Pages v2 is not filed yet'); who makes and who
      reads each thing, on a website and an organic line; a tie Coordination's AI broke ('Coordination chose Write
      first'); the engines the plan left out; every row stopped where it was on a stopped department; and nothing written;
      before Root's check no timetable at all, so the pane says 'No plan yet' (S7, Empty)
  F13 the engine card's read (PRD M4.7, S17): its place in the timetable, the motor's facts and one row for each of
      the five, the function that holds it saying so; served with the engine route

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
    # the goal reached, then the owner switches the department off on the Map (POST /stop: W.set_stopped only): the cycle
    # still says Goal reached, and every function says stopped, the word the Map, the list, All five and the pane print
    W.set_stopped(REF, True)
    nodes, got = _expect(F)
    assert got["cycle"]["state"] == "done" and got["cycle"]["says"] == "Goal reached" and got["stopped"] is True
    assert {n["word"] for n in nodes.values()} == {"stopped"}, {n["name"]: n["word"] for n in nodes.values()}
    assert F.function(REF, "identity")["node"]["word"] == "stopped"


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
    # a department that lives J2 is born with its functions' limits; each engine is given its own when the plan that
    # names it is registered (PRD M4.1), so the birth run says so
    assert nodes["Priority"]["last"]["what"] == "gave each function its limit", "the record's words, in the owner's"
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


def test_m18_between_them_is_what_each_function_did_never_the_words_it_carried(mods, born, monkeypatch):
    """All five's Between them (round 2, gap 5): the last three messages between the five, newest first, each as the act
    its function did, in the owner's words; the words a message carried (the owner's goal that Identity hands on and
    Adaptation proposes from, Priority's why) are its detail, for the hover, and never the row."""
    W, R, J, F = mods
    ref = born(WEBSITE, "Acme Learning")
    rows = F.functions(ref)["between"]
    assert 1 <= len(rows) <= 3, rows
    posts = [p for p in R.board(ref) if p["src"] in FUNCS and any(x in FUNCS and x != p["src"] for x in p.get("dst") or [])]
    assert [r["n"] for r in rows] == [p["n"] for p in reversed(posts)][:len(rows)], "newest first, between the five only"
    for r in rows:
        assert r["from"] in FUNCS and r["to"] and all(x in FUNCS for x in r["to"]), r
        assert WEBSITE not in r["act"] and "Class 8" not in r["act"], r
        assert r["act"].split()[0] in ("asked", "proposed", "said", "told", "answered", "agreed", "let", "did", "posted"), r
    # the whole bargain, as the rows say it
    acts = [F._did(p) for p in posts]
    assert "asked Adaptation for the plan" in acts and "proposed the plan to Priority" in acts and "said yes to the plan" in acts, acts
    asked = next(p for p in posts if p["src"] == "Identity" and p["dst"] == ["Adaptation"])
    assert WEBSITE in (R._line(asked) or ""), "the owner's words were what Identity's message carried"
    # Priority says no: Adaptation takes the disagreement to Identity, said as the act
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: ({"answer": "reject", "why": "the envelope has no room today"}, 0.01, "model")
                        if step["id"] == "priority.bargain" else (None, 0.0, "offline"))
    ref = born(WEBSITE, "No Room Co")
    rows = F.functions(ref)["between"]
    assert rows[0]["from"] == "Adaptation" and rows[0]["act"] == "told Identity about a disagreement", rows[0]
    assert rows[1]["from"] == "Priority" and rows[1]["act"] == "said no to the plan" and rows[1]["detail"] == "the envelope has no room today", rows[1]
    assert all(WEBSITE not in r["act"] for r in rows)


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
    # the name the owner gave on the sheet is the department's name, and the words after it its goal (round 2, gap 6)
    assert kids[0]["name"] == "Billing", kids[0]["name"]
    asked = " ".join(str(r) for r in W.requests(kids[0]["ref"]))
    assert "Invoices for every customer" in asked and "Set up a department" not in asked, asked
    # a second sheet's department is a second department, never folded into the first under a draft name
    W.owner_ask(root, "Set up a department: Design. Logos and brand pages for every product we sell")
    W.run_until_idle(root, limit=300)
    kids = sorted((d for d in W.list_depts() if d.get("parent") == root), key=lambda d: d["name"])
    assert [k["name"] for k in kids] == ["Billing", "Design"], [k["name"] for k in kids]
    assert all(k["runtime"] == 2 for k in kids)
    said = [str((p.get("payload") or {}).get("done") or "") for p in R.board(root) if p["src"] == "Identity"]
    assert not [x for x in said if "already exists" in x], said


def test_m14_the_shape_prompt_keeps_the_name_the_owner_gave_and_the_covering_holds_it(mods, born, monkeypatch):
    """The AI inside Setup is told the name the owner gave; when it shapes another name all the same, the covering keeps
    the owner's (rules 1 and 6: the owner's own words, and the code's verdict in the covering)."""
    W, R, J, F = mods
    import founding
    prompts = []

    def model(prompt, step):
        if step["id"] != "setup.shape":
            return None, 0.0, "offline"
        prompts.append(prompt)
        return {"name": "Thread & Loom Department", "kind": "organic", "goal": "Invoices for every customer, sent by email",
                "purpose": "Invoices", "second": ""}, 0.01, "model"
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    monkeypatch.setattr(R, "MODEL", model)
    root = founding.found_structure("Thread & Loom", owner="Sankalp")["root"]
    W.owner_ask(root, "Set up a department: Billing. Invoices for every customer, sent by email")
    W.run_until_idle(root, limit=300)
    assert prompts and "THE NAME THE OWNER GAVE: Billing" in prompts[-1], prompts[-1:]
    assert [d["name"] for d in W.list_depts() if d.get("parent") == root] == ["Billing"]


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
# refuse, always) is the owner's own word for a rule (PRD S5: "Tags go, ask, refuse and always"), so neither is scanned;
# on a rendered pane the tag is its badge, which pane_words.js prints as [tag:word].
RULE_TAGS = re.compile(r"\bgo, ask, refuse,? (?:or |and )?always\b|\ba refuse rule\b|\[tag:(?:go|ask|refuse|always)\]")
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


def _client():
    """The app's real routes for a department: the runtime's (website_api) and the registry's (dept_api)."""
    import website_api
    import dept_api
    importlib.reload(website_api)
    importlib.reload(dept_api)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(website_api.router)
    app.include_router(dept_api.router)
    return TestClient(app)


# the registry's reads the older cards under a function's page drew from (20-dept.js), and the Settings tab's template line
DEPT_READS = ("identity", "adaptation", "priority", "coordination", "audit", "functions", "engines")


def _reads(W, ref):
    """The reads a function's pane on its three tabs, the Map, All five and the owner's chat really make, from the real
    routes, by the tail of their path: the runtime's under reads, the registry's under dept."""
    c = _client()
    tails = (["map", "functions", "board", "status", "chat"] + ["functions/" + fn for fn in JOURNEYS] +
             ["steps/" + fn.capitalize() for fn in JOURNEYS] + ["chat?fn=" + fn for fn in JOURNEYS])
    out = {}
    for t in tails:
        got = c.get("/api/native/%s/%s" % (ref, t))
        assert got.status_code == 200, (t, got.status_code)
        out[t] = got.json()
    dept = {}
    for t in DEPT_READS:
        got = c.get("/api/dept/%s/%s" % (ref, t))
        assert got.status_code == 200, (t, got.status_code, got.text[:200])
        dept[t] = got.json()
    return {"name": W.dept(ref)["name"], "reads": out, "dept": dept}


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
        # whose word added an engine is said whole (round 4, gap 2): never a stamp after a yes or a ruling nobody stamped
        assert not re.search(r"(?:yes|ruling)'s stamp", v["rest"] + " " + v["hover"]), (k, "a stamp nobody gave")
    assert "registered the workflow Facts -> Site on Priority's yes" in [r["what"] for r in W.runs(ref)], "the plan's own run line"


# ---- M1.7 (round 3): every tab of a function's pane, the owner's own chat, and every ask say the owner's words ---------
# an act's own id, which the screen never prints (round 4, gaps 1 and 4): the board, the chat turns and Coordination's
# who-may-post check say each act in words (R.ACT_SAYS, 22-website.js WB_ACTS); 'may propose to' is those words
ACT_IDS = re.compile(r"\b(?:accept|reject)-proposal\b|\bnot-understood\b|\bmay (?:request|inform|agree|failure|cancel|refuse) to\b"
                     r"|\bmay not post [a-z-]+ to\b")


def _scan(panes, flow):
    """Every surface rendered (each function's page, Chat and Settings, the Map, All five, the owner's chat and the list):
    something is shown, and nothing at rest or on a hover says grant, counter or refuse, charter or internal system, or
    an act by its id (reject-proposal, accept-proposal, 'may inform to')."""
    for k, v in panes.items():
        assert v["rest"], (flow, k)
        assert not _banned_shown(v["rest"]) and not _banned_shown(v["hover"]), (flow, k, _banned_shown(v["rest"] + " " + v["hover"]))
        text = (v["rest"] + " " + v["hover"]).lower()
        assert "charter" not in text and "internal system" not in text, (flow, k)
        assert not ACT_IDS.search(text), (flow, k, [text[max(0, m.start() - 60):m.end() + 30] for m in ACT_IDS.finditer(text)])
    for fn in JOURNEYS:
        assert {fn, fn + ":chat", fn + ":settings"} <= set(panes), (flow, fn)


def _chat_words(view):
    """What a chat read gives a person to read: each turn's line, and each ask's and answered question's text."""
    return " ".join([str(t.get("line") or "") for t in view.get("turns") or []] +
                    [str(a.get("text") or "") for k in ("asks", "answered") for a in view.get(k) or []])


def _offline(monkeypatch, R, answers):
    """The AI inside answers these steps; every other step falls to its draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: (answers[step["id"]], 0.01, "model") if step["id"] in answers
                        else (None, 0.0, "offline"))


def test_m17_every_tab_of_every_functions_pane_says_the_owners_words(mods, born, monkeypatch, tmp_path):
    """Round 3, gap 1: each function's pane has three tabs, its page, Chat and Settings, and the owner's own chat is
    beside them. Rendered by the panel's own scripts from the real reads (each Chat tab's /chat?fn=, the owner's /chat
    and the registry's /api/dept/ reads too), on departments Root set up where Priority says yes, asks for less, and
    says no; where the owner says no; and where Root's check sends a plan back: no tab shows grant, counter or refuse at
    rest or on a hover. Identity's tells are written in the owner's words where they are composed, so the department's
    chat and Root's say them the same way, and each function's thinking names its steps and verdicts in those words."""
    W, R, J, F = mods
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    c = _client()

    def tells(ref):
        """Identity's words to the owner, on the department's own board and, through Root, on Root's."""
        root = W.dept(ref).get("root")
        mine = _chat_words(c.get("/api/native/%s/chat" % ref).json())
        assert not _banned_shown(mine), _banned_shown(mine)
        if root:
            front = _chat_words(c.get("/api/native/%s/chat" % root).json())
            assert not _banned_shown(front), _banned_shown(front)
            mine += " " + front
        said = " ".join(str((p.get("payload") or {}).get("done") or (p.get("payload") or {}).get("objective") or "")
                        for p in R.board(ref) + (R.board(root) if root else []) if p["src"] == "Identity" and "Owner" in p["dst"])
        assert not _banned_shown(said), ("at the source", _banned_shown(said))
        return mine

    # Priority says yes: the plan is set, and Identity says who said yes in the owner's words
    ref = born(WEBSITE, "Acme Learning")
    panes = _panes(tmp_path, _reads(W, ref))
    _scan(panes, "said yes")
    assert "Priority said yes to it and it passed Root's check" in panes["chat"]["rest"], "the tell, on the owner's chat"
    assert "Priority said yes to it" in tells(ref)
    assert "Send the line Priority said yes to, to Root's check" in panes["adaptation:chat"]["rest"], "Adaptation's thinking"
    assert "Say yes, ask for less, or say no" in panes["priority:chat"]["rest"], "Priority's thinking"
    assert "Gate the effect by rule: let through" in panes["identity:chat"]["rest"], "a gate's verdict in the owner's words"
    assert "Hold the envelope: let through" in panes["priority:chat"]["rest"]
    assert "Who may post to whom" in panes["coordination:settings"]["rest"] and "says no" in panes["coordination:settings"]["rest"]
    assert "How to judge a request: go, ask or stop" in panes["identity:settings"]["rest"], "an instruction file's line"

    # Priority asks for less, Adaptation takes it, and Priority says yes to the shorter line
    _offline(monkeypatch, R, {"priority.bargain": {"answer": "counter", "keep": ["Plan", "Write", "Check"],
                                                   "why": "the envelope has room for three today"}})
    ref = born(WEBSITE, "Less Co")
    assert [e["action"] for e in J.events(ref)].count("proposal.countered") == 1 and "workflow.registered" in [e["action"] for e in J.events(ref)]
    assert W.dept(ref)["workflows"][-1]["engines"] == ["Plan", "Write", "Check"]
    panes = _panes(tmp_path, _reads(W, ref))
    _scan(panes, "asked for less")
    assert "Take Priority's ask for less, or take it to Identity" in panes["adaptation:chat"]["rest"], "Adaptation's thinking"
    assert "the envelope has room for three today asks for less" in panes["priority:chat"]["rest"], "Priority's counter, as an ask for less"
    assert "the envelope has room for three today asks for less" in panes["adaptation:chat"]["rest"]
    assert "Plan -> Write -> Check (from the Library). Priority said yes to it" in tells(ref)

    # Priority says no: Identity puts the plan to the owner, with the ask's answers in the buttons' words
    _offline(monkeypatch, R, {"priority.bargain": {"answer": "reject", "why": "the envelope has no room today"}})
    ref = born(WEBSITE, "No Room Co")
    assert J.status(ref)["state"] == "waiting"
    panes = _panes(tmp_path, _reads(W, ref))
    _scan(panes, "said no")
    assert "Priority said no to the plan: the envelope has no room today" in panes["identity:chat"]["rest"]
    assert "Stamp to run it as proposed, or say no to drop it." in panes["chat"]["rest"]
    assert "Say no" in panes["chat"]["rest"] and "Take Priority's no to Identity" in panes["adaptation:chat"]["rest"]
    tells(ref)
    # the owner says no: the plan is dropped, and Identity says so in the owner's words
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "conflict"]:
        W.decide_ask(ref, a["id"], False)
    W.run_until_idle(ref, limit=300)
    assert J.status(ref)["state"] == "blocked"
    panes = _panes(tmp_path, _reads(W, ref))
    _scan(panes, "the owner said no")
    assert "The plan is dropped because you said no" in panes["chat"]["rest"] and "because you said no" in tells(ref)
    assert "Drop what was turned down" in panes["identity:chat"]["rest"], "Identity's thinking on the owner's no"

    # Root's check sends a plan back once, and Adaptation reshapes it
    real, calls = R._root_check, {"n": 0}

    def check(ref, d, engines, source):
        calls["n"] += 1
        return ["Facts reads Notes, which nothing before it writes"] if calls["n"] == 1 else real(ref, d, engines, source)
    monkeypatch.setattr(R, "_root_check", check)
    _offline(monkeypatch, R, {})
    ref = born(ORGANIC, "Lab Co")
    assert calls["n"] >= 2 and "workflow.blocked" in [e["action"] for e in J.events(ref)]
    panes = _panes(tmp_path, _reads(W, ref))
    _scan(panes, "sent back")
    assert "Root's check sent the plan back (Facts reads Notes, which nothing before it writes)" in panes["chat"]["rest"]
    assert "sent the plan back" in tells(ref)
    monkeypatch.setattr(R, "_root_check", real)

    # round 4, gaps 1 and 4: Identity says no to the owner's request, and the owner says no to an ask; Coordination's
    # who-may-post check says each act in words on its card, never 'Identity may refuse to Owner' or 'reject-proposal'
    _offline(monkeypatch, R, {})
    ref = born(WEBSITE, "Words Co")
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "publish"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)
    W.owner_ask(ref, "Email the new site to every patient")
    W.run_until_idle(ref, limit=300)
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "request"]:
        W.decide_ask(ref, a["id"], False)
    W.run_until_idle(ref, limit=300)
    assert any(p["src"] == "Owner" and p["msg_type"] == "reject-proposal" for p in R.board(ref)), "the owner said no to the ask"
    panes = _panes(tmp_path, _reads(W, ref))
    _scan(panes, "the owner said no to an ask")
    assert "The owner may say no to Identity" in panes["coordination"]["rest"], "the check's note, in the act's words"
    _offline(monkeypatch, R, {"identity.take": {"verdict": "refuse", "why": "it names every patient", "needs": [], "unsure": []}})
    W.owner_ask(ref, "Put every patient's full name on the home page")
    W.run_until_idle(ref, limit=300)
    assert any(p["src"] == "Identity" and p["msg_type"] == "refuse" and "Owner" in p["dst"] for p in R.board(ref)), "Identity said no"
    panes = _panes(tmp_path, _reads(W, ref))
    _scan(panes, "Identity said no to a request")
    assert "Identity may say no to the owner" in panes["coordination"]["rest"], "the check's note, in the act's words"
    notes = [n for r in R.step_rows(ref) if r.get("step") == "coord.edge" for n in (r.get("check") or {}).get("notes") or []]
    assert notes and not any(ACT_IDS.search(n.lower()) or "refuse" in n for n in notes), "at the source, every note in words"


def test_m17_every_ask_says_its_answers_in_the_words_of_its_buttons(mods, born, monkeypatch, tmp_path):
    """Round 3, gap 2: every ask Identity writes says its two answers as its two buttons do, Stamp and Say no, never
    'Refuse to ...'. On a department Root set up, with the first publish stamped, the owner's words that reach outside
    the site and a change to Audit's instructions are each put to the owner: the five's read, Identity's page, the
    owner's chat and All five, at rest and on a hover, say 'or say no', and so do the engine and the line asks."""
    W, R, J, F = mods
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    ref = born(WEBSITE, "Acme Learning")
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "publish"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)
    W.owner_ask(ref, "Email the new site to every patient")
    W.run_until_idle(ref, limit=300)
    out = next(a for a in W.asks(ref) if a["kind"] == "request" and a["status"] == "pending")
    assert "Stamp to go ahead, or say no to leave them out." in out["text"] and out["text"].endswith("Email the new site to every patient")
    ins = R.instructions_ask(ref, "audit", "goal", R._instruction("audit", "goal", ref) + "\nRead every page twice.\n")
    asked = next(p for p in R.board(ref) if p["thread"] == ins["thread"])
    assert asked["payload"]["objective"].endswith("Stamp to use them from the next run, or say no to keep them as they are.")
    for v in [F.functions(ref), F.function(ref, "identity")]:
        assert not _banned(v), _banned(v)
    text = json.dumps(F.functions(ref))
    assert "or say no to" in text, "an ask's words are on the read, said the buttons' way"
    panes = _panes(tmp_path, _reads(W, ref))
    _scan(panes, "asks")
    assert "Stamp to go ahead, or say no to leave them out." in panes["chat"]["rest"], "the ask in the owner's chat"
    assert ">Refuse<" not in json.dumps(panes) and "Say no" in panes["chat"]["rest"], "the buttons say it too"
    # the engine and the line asks say their answers through the same builder (engine_runtime._answers)
    assert R._answers("add it", "to leave the idea parked") == "Stamp to add it, or say no to leave the idea parked."
    assert R._answers("add them and start", "and say what to change") == "Stamp to add them and start, or say no and say what to change."
    import inspect
    for fn in (R.identity_engine, R.identity_line, R.identity_closed, R.instructions_ask):
        assert "_answers(" in inspect.getsource(fn) and "Refuse to" not in inspect.getsource(fn), fn.__name__


def test_m17_a_runtime_departments_panes_agree_with_its_record(mods, born, tmp_path):
    """Round 3, gaps 3 and 4: on a department on the engine runtime the registry's older cards are not drawn under a
    function's page, so the pane agrees with the record and with the page above it. Served the real /api/dept/ reads,
    Identity's pane names its owner once, as the record does; Adaptation's never says there are no engines while the
    record holds four; the queue is Coordination's timetable, never Priority's (PRD M4.6), and lists the line; and no
    pane carries the registry's Proposals, the template's framework or Recent."""
    W, R, J, F = mods
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    ref = born(WEBSITE, "Acme Learning")
    assert W.dept(ref)["engines"] == ["Plan", "Write", "Check", "Publish"]
    reads = _reads(W, ref)
    assert reads["dept"]["identity"].get("owner") is not None and "engines" in reads["dept"]["engines"], "the registry answered"
    panes = _panes(tmp_path, reads)
    owner = W.map_view(ref)["owner"]
    assert owner and panes["identity"]["rest"].count(owner) == 1, panes["identity"]["rest"].count(owner)
    assert "No owner yet" not in panes["identity"]["rest"]
    for fn in JOURNEYS:
        rest = panes[fn]["rest"]
        assert "No engines yet" not in rest and "Nothing in the queue" not in rest and "Nothing held" not in rest, fn
        assert "Proposals" not in rest and "Always does" not in rest and "Recent" not in rest, fn
        assert "The function" in rest and "Journeys" in rest and "Version 1" in rest, (fn, "the page is the pane")
    # PRD M4.6 (S-05): the queue is Coordination's, never Priority's; its timetable lists the line and why Publish waits
    assert "Queue" not in panes["priority"]["rest"] and "Waits for the stamp" not in panes["priority"]["rest"]
    assert "Timetable" in panes["coordination"]["rest"] and "Publish after a Build that passed" in panes["coordination"]["rest"]
    assert "waits for the stamp" in panes["coordination"]["rest"] and "waits: waits" not in panes["coordination"]["rest"]
    assert "Plan" in panes["adaptation"]["rest"] and "Control" in panes["identity"]["rest"]
    # round 4, gap 5: what Identity holds is on its pane, from the record, once: the goal, the done-when (its items, as
    # Root drafted them) and each rule with its tag as a chip beside it in the pane's word (S5: a refuse rule reads
    # never), as dept.json has them; Identity's page draws them from its own record (M3.7), and nothing draws them twice
    d, idn = W.dept(ref), panes["identity"]["rest"]
    assert d["goal"] and d["goal"] in idn, "the goal"
    done = [i["text"] for i in d.get("done_items") or []] or [d["done"]]
    assert d["done"] and all(t and idn.count(t) == 1 for t in done), ("the done-when, once", [(t, idn.count(t)) for t in done])
    assert d["rules"] and "The department Goal" not in idn, "one set of cards, not a second under the page"
    for r in d["rules"]:
        assert idn.count(r["line"]) == 1 and "%s %s" % ({"refuse": "never"}.get(r["tag"], r["tag"]), r["line"]) in idn, (r, "each rule once, its tag beside it")
    # m1fix, gap 5 residual: a record from before Root drafted done-when items (PRD M3.2) keeps its done line, and
    # Identity's pane says that line, once, never 'No done-when items yet'; the goal and each rule stay once
    d.pop("done_items", None)
    W.save_dept(ref, d)
    idn = _panes(tmp_path, _reads(W, ref))["identity"]["rest"]
    assert d["done"] and idn.count(d["done"]) == 1 and "No done-when items yet" not in idn, ("the done line, once", idn.count(d["done"]))
    assert "Drafted by Root at birth" not in idn and d["goal"] in idn, "the line as the record has it, under the goal"
    assert all(idn.count(r["line"]) == 1 for r in d["rules"]), "each rule still once"


def test_m17_a_record_written_before_reads_in_the_owners_words_on_every_chat(mods):
    """Round 3, gaps 1 and 2, for a department whose record was written before the words were put right at their
    source: the /chat read of a function and the owner's own /chat pass what the functions said, their thinking and
    the asks through owner_words, so an old tell, an old ask and a gate's verdict read in the owner's words; the
    owner's own words stay exactly as they said them, refusal and all."""
    W, R, J, F = mods
    c = _client()

    def said(src, dst, act, payload, tid):
        R._append(REF, "board.jsonl", {"n": len(R.board(REF)) + 1, "src": src, "dst": [dst], "msg_type": act, "thread": tid,
                                       "hop": 1, "about": None, "payload": payload, "ack_id": None, "by": None, "at": W.now()})
    said("Owner", "Identity", "request", {"word": "request", "words": "Do not mind Priority's refusal; ask again"}, "x-o")
    said("Identity", "Owner", "inform", {"word": "line", "done": "The plan is set: Plan -> Write (from the Library). Priority granted it and "
                                                                "it passed Root's check; the first starts now."}, "x-o")
    said("Identity", "Owner", "inform", {"word": "line", "done": "The plan is dropped on your refusal. Say what the department should do."}, "x-o")
    said("Priority", "Adaptation", "propose", {"word": "line", "counter": True, "keep": ["Plan"], "why": "room for one"}, "x-b")
    said("Identity", "Coordination", "refuse", {"word": "verdict", "answer": "refuse"}, "x-g")
    W._put_ask(REF, {"id": "a-old", "kind": "request", "engine": "Identity", "words": "Email every patient, or refuse",
                     "text": "Your words reach outside the site. Put them on the site as said? Stamp to go ahead, Refuse to leave them out. "
                             "Email every patient, or refuse", "status": "pending", "created": W.now()})
    R._append(REF, "steps.jsonl", {"id": "s-g", "engine": "Identity", "step": "identity.gate", "mode": "gate", "answer": "refuse",
                                   "status": "ok", "started": W.now(), "ended": W.now()})
    mine = c.get("/api/native/%s/chat" % REF).json()
    lines = [t["line"] for t in mine["turns"]]
    assert "Do not mind Priority's refusal; ask again" in lines, "the owner's own words, as said"
    assert any("Priority said yes to it and it passed Root's check" in x for x in lines), lines
    assert any(x.startswith("The plan is dropped because you said no") for x in lines), lines
    ask = next(a for a in mine["asks"] if a["id"] == "a-old")
    assert ask["text"] == ("Your words reach outside the site. Put them on the site as said? Stamp to go ahead, or say no to leave them out. "
                           "Email every patient, or refuse"), "the ask's answers said the buttons' way; the owner's words kept"
    ident = c.get("/api/native/%s/chat?fn=identity" % REF).json()["turns"]
    thinks = [t["line"] for t in ident if t["think"]]
    assert "Gate the effect by rule: stopped" in thinks, thinks
    assert "The verdict: stopped" in [t["line"] for t in ident if not t["think"]], "a verdict on the board, in the owner's words"
    pr = c.get("/api/native/%s/chat?fn=priority" % REF).json()["turns"]
    counter = next(t for t in pr if t.get("counter"))
    assert counter["line"] == "room for one" and counter["src"] == "Priority"
    for t in ident + pr:
        if t["src"] != "Owner":
            assert not _banned_shown(t["line"]), t


def test_m17_the_owners_words_a_function_carries_on_stay_as_they_said_them(mods, born, tmp_path):
    """Round 4, gap 3: Identity hands the owner's words to Adaptation and Adaptation proposes them to Priority; those
    turns are the owner's words, quoted. Words that carry ', Refuse to' and 'Priority granted' reach every Chat tab, the
    owner's chat, Identity's page (its journeys and Stamped by rule) and All five's hover exactly as the owner said
    them: the record marks the turn quoted and the run's words, and owner_words leaves them alone, while every line a
    function composed itself is still said in the owner's words."""
    W, R, J, F = mods
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    said = WEBSITE + ", Refuse to show fees. Priority granted nothing"
    ref = born(said, "Fee Co")
    c = _client()
    for fn, src in (("identity", "Identity"), ("adaptation", "Adaptation"), ("priority", "Adaptation")):
        turns = c.get("/api/native/%s/chat?fn=%s" % (ref, fn)).json()["turns"]
        carried = [t for t in turns if t["src"] == src and t.get("quoted")]
        assert carried and all(t["line"] == said for t in carried), (fn, [(t["src"], t["line"]) for t in turns if not t["think"]])
    assert any(r.get("words") == said and r["what"].endswith(said) for r in W.runs(ref)), "a run's line that ends with the words keeps them"
    text = json.dumps([F.functions(ref)] + [F.function(ref, fn) for fn in JOURNEYS])
    assert said in text and "or say no to show fees" not in text and "said yes to nothing" not in text
    panes = _panes(tmp_path, _reads(W, ref))
    for k, v in panes.items():
        shown = v["rest"] + " " + v["hover"]
        assert "or say no to show fees" not in shown and "said yes to nothing" not in shown, (k, "the owner's words rewritten")
    for k in ("identity:chat", "adaptation:chat", "priority:chat", "chat", "identity"):
        assert said in panes[k]["rest"], (k, "the owner's words, as said")
    assert said in panes["five"]["hover"], "All five's last act carries the words on its hover"
    # what a function composed itself is still said in the owner's words beside them
    assert "Priority said yes to it and it passed Root's check" in panes["chat"]["rest"]


def test_m17_each_act_says_the_same_words_on_the_board_and_on_coordinations_check(mods):
    """Round 4, gaps 1 and 4: an act is said in words, one table on the server (R.ACT_SAYS) and the same words on the
    board (22-website.js WB_ACTS). Coordination's who-may-post check writes its note in them ('The owner may say no to
    Identity'), and a note a record kept from before, with the act's id in it, reads in them too on the steps card."""
    W, R, J, F = mods
    import owner_words
    assert set(R.ACT_SAYS) == set(R.ACTS)
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "js", "22-website.js")).read()
    body = re.search(r"const WB_ACTS = \{(.*?)\};", src, re.S).group(1)
    assert dict(re.findall(r'"([a-z-]+)":\s*"([^"]+)"', body)) == {a: w for a, (w, _) in R.ACT_SAYS.items()}, "one set of words"
    ctx = {"ref": REF}
    assert R.coord_edge(ctx, None, ("Owner", ["Identity"], "reject-proposal")) == ("admit", "The owner may say no to Identity")
    assert R.coord_edge(ctx, None, ("Identity", ["Owner"], "refuse")) == ("admit", "Identity may say no to the owner")
    assert R.coord_edge(ctx, None, ("Priority", ["Adaptation"], "accept-proposal")) == ("admit", "Priority may say yes to Adaptation")
    assert R.coord_edge(ctx, None, ("Adaptation", ["Owner"], "reject-proposal")) == ("refuse", "Adaptation may not say no to the owner")
    assert R.coord_edge(ctx, None, ("Audit", [], "inform"))[1] == "Audit may not post to nobody"
    for old, said in (("Identity may refuse to Owner", "Identity may say no to the owner"),
                      ("Owner may reject-proposal to Identity", "The owner may say no to Identity"),
                      ("Priority may accept-proposal to Adaptation", "Priority may say yes to Adaptation"),
                      ("Adaptation may inform to Identity", "Adaptation may tell Identity"),
                      ("Identity may request to Owner", "Identity may ask the owner"),
                      ("Audit may not post inform to Identity", "Audit may not tell Identity"),
                      ("Identity may agree to Owner, Adaptation, Coordination", "Identity may agree with the owner, Adaptation and Coordination")):
        assert owner_words.plain(old) == said, old
        assert owner_words.plain(said) == said, "a note in words is left as it is"
    assert owner_words.plain("Identity may not post refuse to nobody") == "Identity may not post to nobody"
    # only a note that names who posts and to whom is read whole: another line that happens to read 'X may <act> to Y'
    # keeps its own words (it is not Coordination's, and plain() reads every line a function composed)
    for line in ("You may request to see the page", "Priority may cancel to save room", "Identity may inform to keep it short",
                 "Adaptation may propose to Priority a smaller plan", "Owner may refuse to Identityless pages"):
        assert owner_words.plain(line) == line, line
    R._append(REF, "steps.jsonl", {"id": "s-old", "engine": "Coordination", "step": "coord.edge", "mode": "gate", "answer": "admit",
                                   "slot": "Owner>Identity:reject-proposal", "status": "ok", "started": W.now(), "ended": W.now(),
                                   "check": {"ok": True, "notes": ["Owner may reject-proposal to Identity"]}})
    view = _client().get("/api/native/%s/steps/Coordination" % REF).json()
    edge = next(s for s in view["steps"] if s["id"] == "coord.edge")
    assert edge["last"]["notes"] == ["The owner may say no to Identity"], edge["last"]


# ---- F12 (PRD M4.5): Coordination's timetable, holds, hand-offs and ties, from the record --------------------------------
def _brief_again(W, ref, words="Add a page for the timetable of the algebra classes"):
    """The owner's words filed as the next Brief, as Identity files them: the line has new work at its head."""
    v = W.latest(ref, "Brief")["v"]
    W.add_version(ref, "Brief", {"brief.md": words}, [{"art": "Brief", "v": v}], "owner", {"ok": True, "notes": []})


def test_f12_a_waiting_engine_names_what_it_waits_for_and_the_one_with_the_turn_has_it(mods, born):
    """A waiting row with no reason, a reason that is not the record's ('Pages v2 is not filed yet'), or two engines
    with the turn at once must fail."""
    W, R, J, F = mods
    ref = born(WEBSITE, "Acme Learning")
    c = F.coordination(ref)
    assert set(c) == set(F.COORDINATION_FIELDS) and [r["engine"] for r in c["timetable"]] == ["Plan", "Write", "Check", "Publish"]
    assert all(list(r) == list(F.TIMETABLE_ROW) for r in c["timetable"])
    rows = {r["engine"]: r for r in c["timetable"]}
    assert [rows[n]["state"] for n in ("Plan", "Write", "Check")] == ["ran", "ran", "ran"]
    assert (rows["Publish"]["state"], rows["Publish"]["why"]) == ("waits", "waits for the stamp"), "held by Identity's gate"
    assert rows["Publish"]["starts"] == "after a Build that passed" and rows["Plan"]["starts"] == "after a new Brief"
    assert rows["Plan"]["last"]["wrote"] == "Site plan v1" and rows["Plan"]["window_min"] == 15
    assert c["holds"] == [{"engine": "Publish", "why": "waits for the stamp"}]
    for a in [a for a in W.asks(ref) if a["status"] == "pending"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)
    assert [r["state"] for r in F.coordination(ref)["timetable"]] == ["ran"] * 4 and F.coordination(ref)["holds"] == [], "nothing waiting"
    _brief_again(W, ref)
    c = F.coordination(ref)
    rows = {r["engine"]: r for r in c["timetable"]}
    assert (rows["Plan"]["state"], rows["Plan"]["word"], rows["Plan"]["on"]) == ("turn", "its turn", "after Brief v2")
    assert rows["Plan"]["at"] == W.latest(ref, "Brief")["at"], "its turn since the Brief it runs on was filed"
    assert [(n, rows[n]["why"]) for n in ("Write", "Check", "Publish")] == [
        ("Write", "Site plan v2 is not filed yet"), ("Check", "Pages v2 is not filed yet"), ("Publish", "Build v2 is not filed yet")]
    assert {h["engine"]: h["why"] for h in c["holds"]}["Check"] == "Pages v2 is not filed yet"
    assert [r["state"] for r in c["timetable"]].count("turn") == 1
    # one run at a time: while Plan runs, the rest wait, and the reason says so
    W._put_run(ref, R._run_row("Plan", False, "Plan@brief.v2", "running", "plans the pages"))
    rows = {r["engine"]: r for r in F.coordination(ref)["timetable"]}
    assert rows["Plan"]["state"] == "running" and rows["Plan"]["word"] == "running"
    # the read through the route the pane uses: Coordination's part of its page is this read
    assert F.function(ref, "coordination")["j2"]["timetable"][0]["state"] == "running"
    # a stopped department: every engine stopped where it was
    W.set_stopped(ref, True)
    assert {r["word"] for r in F.coordination(ref)["timetable"]} == {"stopped where it was"}


def test_f12_who_makes_and_who_reads_each_thing_on_a_website_and_an_organic_line(mods, born):
    W, R, J, F = mods
    web = {h["art"]: h for h in F.coordination(born(WEBSITE, "Acme Learning"))["handoffs"]}
    assert [(a, web[a]["says"], web[a]["readers"]) for a in ("Brief", "Site plan", "Pages", "Build")] == [
        ("Brief", "Identity, from your words", ["Plan"]), ("Site plan", "Plan", ["Write"]), ("Pages", "Write", ["Check"]),
        ("Build", "Check", ["Publish"])]
    assert sorted(web["Live site"]["readers"]) == ["Adaptation", "Audit"] and web["Live site"]["says"] is None, "not made yet"
    lab = born(ORGANIC, "Lab Co")
    first, second = W.dept(lab)["engines"]
    org = {h["art"]: h for h in F.coordination(lab)["handoffs"]}
    writes = R.engine_def(first)["writes"]
    assert org["Brief"]["readers"] == [first] and (org[writes]["says"], org[writes]["readers"]) == (first, [second])
    assert [r["engine"] for r in F.coordination(lab)["timetable"]] == [first, second]


def test_f12_a_tie_coordination_broke_and_what_the_plan_left_out_are_on_its_record(mods, born, monkeypatch):
    W, R, J, F = mods
    assert F.coordination(born(WEBSITE, "Acme Learning"))["ties"] == [], "none today"
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: (
        ({"answer": "counter", "why": "room for three today", "keep": ["Plan", "Write", "Check"]} if "- Publish:" in prompt
         else {"answer": "accept", "why": "the envelope has room"}), 0.01, "model") if step["id"] == "priority.bargain" else (None, 0.0, "offline"))
    ref = born(WEBSITE, "Counter Co")
    c = F.coordination(ref)
    assert c["line"] == ["Plan", "Write", "Check"] and [r["engine"] for r in c["left_out"]] == ["Publish"] and c["left_out"][0]["since"]
    assert "Publish" not in [r["engine"] for r in c["timetable"]]
    # a tie, as Coordination's own unit records one (engine_runtime._tie): its step row, and the answer it filed
    slot = "Coordination@tie.7"
    R._append(ref, "steps.jsonl", {"id": "s-tie1", "run": None, "engine": "Coordination", "step": "coord.tie", "mode": "slot",
                                   "slot": slot, "status": "ok", "answer": "Write", "started": W.now(), "ended": W.now()})
    W._write(R._out_path(ref, slot, "coord.tie", None), {"answer": "Write", "why": "the pages wait on it"})
    tie = F.coordination(ref)["ties"][0]
    assert (tie["said"], tie["why"], tie["today"]) == ("Coordination chose Write first", "the pages wait on it", True)
    chain = F.coordination(ref)["chain"]
    assert chain["of"] == "Brief v1" and chain["limit"] == W.CHAIN_LIMIT and 0 < chain["share"] <= 1


def test_f12_before_roots_check_there_is_no_timetable_and_the_pane_says_no_plan_yet(mods, born, tmp_path):
    """S7, Empty: a website whose plan nobody registered yet, its born table holding the kind's line, read as a
    timetable of four waiting engines ('waits: Brief v1 is not filed yet') must fail; the pane says 'No plan yet'."""
    W, R, J, F = mods
    ref = born(WEBSITE, "Acme Learning", settle=False)
    t = W._read(W.ddir(ref) / "coordination.json", None)
    assert (t["by"], t.get("registered"), t["line"]) == ("born", None, ["Plan", "Write", "Check", "Publish"]), "the born table holds the line"
    c = F.coordination(ref)
    assert (c["timetable"], c["holds"], c["left_out"]) == ([], [], []) and set(c) == set(F.COORDINATION_FIELDS)
    assert F.function(ref, "coordination")["j2"]["timetable"] == []
    assert F.engine_card(ref, "Plan")["head"]["word"] == "no plan yet"
    if shutil.which("node") is not None:
        rest = _panes(tmp_path, _reads(W, ref))["coordination"]["rest"]
        assert "No plan yet" in rest and "is not filed yet" not in rest, rest[:600]
    # Root registers the plan: Coordination's timetable is its line again
    W.run_until_idle(ref, limit=300)
    assert W.dept(ref)["workflows"] and [r["engine"] for r in F.coordination(ref)["timetable"]] == ["Plan", "Write", "Check", "Publish"]


def test_f12_the_coordination_read_writes_nothing_and_never_calls_the_model(mods, born, monkeypatch):
    W, R, J, F = mods
    ref = born(WEBSITE, "Acme Learning")
    _brief_again(W, ref)
    called = []
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: called.append(step) or (None, 0.0, "offline"))
    home = str(W.ddir(ref))
    snap = {p: os.path.getmtime(os.path.join(home, p)) for p in os.listdir(home)}
    F.coordination(ref)
    F.function(ref, "coordination")
    assert {p: os.path.getmtime(os.path.join(home, p)) for p in os.listdir(home)} == snap and called == []


# ---- F13 (PRD M4.7): the engine card, the motor folded in and the five beside it --------------------------------------
def test_f13_the_engine_card_names_its_slot_and_what_each_of_the_five_is_doing(mods, born, monkeypatch):
    """A card whose holder is not the function that holds it (Identity's stamp, Priority's limit), a motor that says each
    slot ran once when one ran twice, or a card for a department not on the runtime must fail."""
    W, R, J, F = mods
    ref = born(WEBSITE, "Acme Learning")
    card = F.engine_card(ref, "Publish")
    assert set(card) == set(F.ENGINE_CARD_FIELDS) and [r["fn"] for r in card["five"]] == FUNCS
    assert all(list(r) == list(F.ENGINE_FIVE_ROW) for r in card["five"])
    assert (card["head"]["state"], card["head"]["why"]) == ("waits", "waits for the stamp")
    assert card["motor"] == {"slot": "after Build v1", "starts": "after a Build that passed", "once": True, "says": "ran once per slot",
                             "window_min": 10, "today": 0.0}
    five = {r["fn"]: r for r in card["five"]}
    assert (five["Identity"]["state"], five["Identity"]["says"]) == ("warn", "holds it until you stamp the first publish")
    assert (five["Coordination"]["state"], five["Coordination"]["says"]) == ("wait", "keeps its slot while Identity holds it")
    assert five["Adaptation"]["says"] == "proposed it in the plan Root registered" and five["Priority"]["state"] == "ok"
    assert five["Audit"]["says"] == "will read the Live site it leads to"
    write = {r["fn"]: r for r in F.engine_card(ref, "Write")["five"]}
    assert (write["Coordination"]["says"], write["Identity"]["says"]) == ("gave it its slot; it ran", "lets it start: no rule holds it")
    # held by budget: Priority's row is block
    W._put_run(ref, R._run_row("Write", False, None, "ok", "wrote a page", spend={"calls": 3, "usd": 0.1}))
    W.set_envelope(ref, "Write", calls=2)
    assert {r["fn"]: r for r in F.engine_card(ref, "Write")["five"]}["Priority"]["state"] == "block"
    # a slot that ran twice: the motor says so
    run = next(r for r in W.runs(ref) if r["engine"] == "Plan" and r.get("slot"))
    W._put_run(ref, dict(run, id="r-twice"))
    assert F.engine_card(ref, "Plan")["motor"]["says"] == "a slot ran twice"
    # the route the card reads: the engine read carries it on the runtime
    import website_api
    importlib.reload(website_api)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(website_api.router)
    got = TestClient(app).get("/api/native/%s/engine/Write" % ref).json()
    assert got["card"]["engine"] == "Write" and got["card"]["motor"]["slot"]
    assert F.engine_card(REF, "Write") is None or W.dept(REF).get("runtime") == 2
    old, _ = W.create("dref-old01", "Old", None, kind="website")
    if W.dept(old["ref"]).get("runtime") != 2:
        assert F.engine_card(old["ref"], "Write") is None
