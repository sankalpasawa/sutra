"""J2 as a child of the journey template (PRD amendment A3.7.2): the five functions work toward the identity's goal.

`journeys/J2.json` says what the department goes through, step by step and edge by edge; this file runs the real flow with a
model that is a function and asks the one question of A3.6: did the journey happen the way its definition says?
(`journeys.walk`). It also holds the two edge tests that J2 was missing (the clock and the spend bounds of J2.2, and the
`run.failed` event of J2.7) and the test that keeps the eight sub-journeys equal to the names the ledger stamps. The model is
stubbed everywhere: no test here calls a live one.

The fixture, the model and the helpers are the ones of test_j2.py, copied and not imported, so this file stands alone.
"""
import copy
import importlib
import json

import pytest

import journeys
from journeys import walk

WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"
LINE = ["Plan", "Write", "Check", "Publish"]
RULE = "Every page ends with: Call 108."


@pytest.fixture
def j2(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)

    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime as R
    import j2_runtime as J

    for module in (E, W, org2_apply, founding, R, J):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding


def _model(monkeypatch, R, answers):
    """A model that is a function: a step id maps to what the model says (a dict, or a callable taking the prompt).
    Every other step falls to its draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)

    def model(prompt, step):
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"

    monkeypatch.setattr(R, "MODEL", model)


def _items_met(prompt):
    """Audit's reader (M8.3), a function: it says every done-when item in the prompt is met, with its evidence."""
    items = json.loads(prompt.split("THE DONE-WHEN ITEMS:\n", 1)[1].split("\n\nWHAT CODE MEASURED:", 1)[0])
    return {"items": [{"id": i["id"], "verdict": "met", "claim": "it holds", "evidence": "the work shows it"} for i in items], "findings": []}


def _born(j2, words=WEBSITE, org="Acme Learning", settle=True):
    """A department as a person makes one: found the organisation, say the words, Root sets it up."""
    W, _, _, founding = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    if settle:
        W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _actions(J, ref):
    return [e["action"] for e in J.events(ref)]


def _work(W, ref):
    return [r["engine"] for r in W.runs(ref) if not r.get("system")]


def _stamp_all(W, ref, approve=True, kind=None):
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and (kind is None or a["kind"] == kind)]:
        W.decide_ask(ref, a["id"], approve)
    W.run_until_idle(ref, limit=300)


def _tick(W, ref):
    """One turn of the department's motor: the one thing that is due, run. False when nothing is."""
    name, inp, slot = W.due(ref)
    if not name:
        return False
    W.run_slot(ref, name, inp, slot)
    return True


def _offer(R, ref):
    """The post in which Adaptation offered the line to Priority: the bargain's thread."""
    return next((p for p in R.board(ref) if p["src"] == "Adaptation" and p["msg_type"] == "propose"
                 and (p["payload"] or {}).get("word") == "line"), None)


# ---- the sub-journeys ---------------------------------------------------------------------------------------------------
def test_j2_sub_journeys_equal_the_ledgers_names():
    """The eight sub-journeys J2.a to J2.h are the eight steps one for one, and the names the ledger stamps on its events
    are theirs: a name renamed on one side only, or two steps swapped, fails."""
    import j2_runtime
    J2 = journeys.load()["J2"]
    assert [s["id"] for s in J2["sub"]] == list(j2_runtime.JOURNEY.values())
    assert [s["step"] for s in J2["sub"]] == [str(i + 1) for i in range(len(J2["sub"]))]
    assert list(j2_runtime.JOURNEY) == list(range(1, len(J2["sub"]) + 1))
    assert [s["n"] for s in J2["steps"]] == [str(i + 1) for i in range(len(J2["steps"]))], "the eight steps are 1 to 8"


# ---- the walk -----------------------------------------------------------------------------------------------------------
def test_j2_walk_from_the_identity_to_the_goal(j2, monkeypatch):
    """The department as a person makes it, left to run: Identity is satisfied, Adaptation proposes the line, Priority
    answers, Root checks and registers, Coordination gives each engine its turn, Audit reads the result and Identity says the
    goal is reached. A step skipped, a goal reached before Audit read, or one reached twice fails here; so does a step the
    definition names that the run never took (the walk)."""
    W, R, J, _ = j2
    J2 = journeys.load()["J2"]
    _model(monkeypatch, R, {"audit.judge": {"ok": True, "findings": []}, "audit.items": _items_met})
    ref = _born(j2)

    # J2.6, the edge out of step 6: the first publish is asked of the owner, once, in the golden lead of the row, and the ask is
    # the act the edge names (Identity requests the owner's publish). The line has run up to it and goes no further without the stamp.
    edge = next(e for e in J2["edges"] if e["id"] == "J2.6")
    (first,) = [a for a in W.asks(ref) if a["status"] == "pending"]
    assert first["kind"] == "publish" and first["text"].startswith("Publish: go live for the first time"), first
    assert first["text"].startswith(edge["outcome"]["golden"]), "the row's golden lead is what the owner reads"
    assert [(p["src"], p["dst"][0], p["msg_type"]) for p in R.board(ref) if (p["payload"] or {}).get("word") == "publish"] == \
        [("Identity", "Owner", "request")], "and it is one request from Identity to the owner"
    assert _work(W, ref) == LINE[:-1] and not W.versions(ref, "Live site"), "nothing goes outside before the stamp"
    _stamp_all(W, ref)                                           # the first publish: a born rule says ask
    assert _work(W, ref) == LINE and len(W.versions(ref, "Live site")) == 1, "and the stamp lets it go, once"

    # the ledger, in order, each event stamped with the sub-journey of its step
    named = {"identity.assessed", "proposal.requested", "proposal.created", "proposal.granted", "workflow.validated",
             "workflow.registered", "timetable.written", "slot.assigned", "run.started", "artifact.filed", "run.completed",
             "audit.finding_filed", "goal.reached"}
    per_engine = [(a, "J2.f") for _ in LINE for a in ("slot.assigned", "run.started", "artifact.filed", "run.completed")]
    assert [(e["action"], e["journey"]) for e in J.events(ref) if e["action"] in named] == \
        [("identity.assessed", "J2.a"), ("proposal.requested", "J2.b"), ("proposal.created", "J2.b"), ("proposal.granted", "J2.c"),
         ("workflow.validated", "J2.e"), ("workflow.registered", "J2.e"), ("timetable.written", "J2.e")] + per_engine + \
        [("audit.finding_filed", "J2.g"), ("goal.reached", "J2.h")]
    assert [e["workflow_ref"] for e in J.events(ref) if e["action"] == "run.started"] == LINE, "each engine of the line, in turn"
    assert all(J.JOURNEY[e["step"]] == e["journey"] for e in J.events(ref)), "an event is stamped with the sub-journey of its step"
    assert {e["journey"] for e in J.events(ref)} <= {s["id"] for s in J2["sub"]}
    reached = [e for e in J.events(ref) if e["action"] == "goal.reached"]
    (reading,) = W.rows(ref, "readings.jsonl")
    assert len(reached) == 1 and reached[0]["actor"] == "Identity" and \
        reached[0]["evidence_refs"] == [{"artifact": "Live site", "version": 1, "reading": reading["id"]}], "Identity says it from the reading, and cites it (M8.4)"
    read = next(e for e in J.events(ref) if e["action"] == "audit.finding_filed")
    assert read["seq"] < reached[0]["seq"], "a goal is never reached unread"
    assert [(s, a) for s, a in [(p["step"], p["status"]) for p in R.step_rows(ref)] if s == "audit.items"] == [("audit.items", "ok")], \
        "Audit's reader read the done-when items item by item"

    # the board holds the acts the steps name, on the department's one board and in this order
    acts = [(p["src"], p["dst"][0], p["msg_type"]) for p in R.board(ref) if (p["payload"] or {}).get("word") == "line"]
    assert acts[:3] == [("Identity", "Adaptation", "request"), ("Adaptation", "Priority", "propose"), ("Priority", "Adaptation", "accept-proposal")]
    # step 7's hand-over: A3.7.2 names Audit's inform/finding, which is the act of a reading with something to put right; this
    # run has nothing to put right, so Audit hands Identity the reading (audit_tell) and files no finding. Both are binds of step 7
    board = [(p["src"], p["dst"][0], p["msg_type"], (p["payload"] or {}).get("word")) for p in R.board(ref)]
    said = [a for a in board if a[0] == "Audit"]
    assert said == [("Audit", "Identity", "inform", "reading")], "Audit tells Identity the reading, once, and files no finding when there is none"
    assert board.index(said[0]) < board.index(("Identity", "Owner", "inform", "goal")), "the goal is said after Identity was handed the reading"
    (post,) = [p for p in R.board(ref) if p["src"] == "Audit"]
    assert post["payload"]["reading"] == reading["id"] and post["payload"]["read"] is True and post["payload"]["findings"] == [], \
        "it is the reading Audit filed, read item by item, with no finding in it"
    st = J.status(ref)
    assert (st["state"], st["step"], st["goal_reached"], st["workflow"]) == ("done", 8, True, LINE)

    # the whole flow, against the record only: every act, step and event the seven steps name happened, in the order they give
    assert J2["scenarios"][0]["walks"] == ["1", "2", "3", "5", "6", "7", "8"]
    assert walk.follows(J2, walk.trace(W, R, J, ref), walks=["1", "2", "3", "5", "6", "7", "8"]) == []


def test_j2_the_walk_fails_when_a_bind_is_not_what_the_run_did(j2, monkeypatch):
    """The walk is a check and not a rubber stamp: a copy of J2 whose step 6 names an event the ledger never wrote, or whose
    step 5 comes before step 3, fails the walk and says which step and which bind."""
    W, R, J, _ = j2
    _model(monkeypatch, R, {"audit.judge": {"ok": True, "findings": []}, "audit.items": _items_met})
    ref = _born(j2)
    _stamp_all(W, ref)
    record = walk.trace(W, R, J, ref)
    J2 = journeys.load()["J2"]
    assert walk.follows(J2, record, walks=["2", "3", "5", "6"]) == []

    broken = copy.deepcopy(J2)
    for step in broken["steps"]:
        for bind in step.get("binds") or []:
            if bind.get("action") == "run.completed":
                bind["action"] = "run.finished"
    faults = walk.follows(broken, record, walks=["6"])
    assert any(f.startswith("J2 step 6:") and "run.finished" in f for f in faults), faults
    assert walk.follows(J2, record, walks=["5", "3"]) != [], "step 3 happened before step 5, and the journey puts step 3 first"

    # step 7's hand-over is required, not optional: a word that is not the one Audit posted fails the walk and names it
    renamed = copy.deepcopy(J2)
    for step in renamed["steps"]:
        for bind in step["binds"] if step["n"] == "7" else []:
            if bind.get("kind") == "act" and bind.get("word") == "reading":
                bind["word"] = "readings"
    faults = walk.follows(renamed, record, walks=["7"])
    assert any(f.startswith("J2 step 7:") and "readings" in f for f in faults), faults


# ---- J2.2: the bounds -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bound", ["seconds", "usd"])
def test_j2_2_the_clock_and_the_spend_bounds_also_go_to_identity(j2, monkeypatch, bound):
    """J2.2: a bargain that runs past its clock or its spend is closed by Coordination and sent to Identity as a conflict,
    which cannot settle it and asks the owner once; the work is held. A bargain closed in silence, or one whose bound is
    misnamed, fails. (The hop bound is test_j2.py's.)"""
    W, R, J, _ = j2
    if bound == "seconds":
        monkeypatch.setattr(R, "BOUNDS", {"hops": 4, "seconds": 1, "usd": 0.5})
        words, org = WEBSITE, "Acme Learning"
    else:
        # a model that charges 0.01 a call, a bound of a hundredth of that, and a counter, so that the thread is still open
        # (Priority answered, Adaptation has not) when the spend is read
        monkeypatch.setattr(R, "BOUNDS", {"hops": 4, "seconds": 900, "usd": 0.0001})
        three = {"engines": [{"name": "Facts", "does": "finds the facts", "reads": "Brief", "writes": "Facts", "internet": True},
                             {"name": "Notes", "does": "sorts the facts", "reads": "Facts", "writes": "Notes", "internet": False},
                             {"name": "Summary", "does": "writes the summary", "reads": "Notes", "writes": "Summary", "internet": False}]}

        def priority(prompt):
            if "- Summary:" in prompt:
                return {"answer": "counter", "why": "room for two today", "keep": ["Facts", "Notes"]}
            return {"answer": "accept", "why": "the envelope has room"}

        _model(monkeypatch, R, {"adapt.line": three, "priority.bargain": priority})
        words, org = ORGANIC, "Lab Co"
    ref = _born(j2, words, org, settle=False)

    def open_bargain():
        offer = _offer(R, ref)
        return R._thread(ref, offer["thread"]) if offer else None

    # the department's own turns, one at a time, until the bargain is open and (for the spend) has cost something
    for _ in range(80):
        th = open_bargain()
        if th and th["state"] not in R.CLOSED and (bound == "seconds" or th["spent"] > th["bounds"]["usd"]):
            break
        assert _tick(W, ref), "the department ran out of turns before the bargain was open"
    th = open_bargain()
    assert th["state"] not in R.CLOSED and th["bounds"][bound] == R.BOUNDS[bound]
    assert "conflict.raised" not in _actions(J, ref), "nothing is sent to Identity before a bound is reached"

    R.sweep(ref)                                                 # the system clock's tick: Coordination reads the bounds
    th = open_bargain()
    assert th["state"] == "canceled" and th["outcome"]["by"] == "bound" and th["outcome"]["which"] == bound
    W.run_until_idle(ref, limit=100)

    raised = [e for e in J.events(ref) if e["action"] == "conflict.raised"]
    assert len(raised) == 1, "one conflict, however many turns follow"
    assert (raised[0]["actor"], raised[0]["recipient"], raised[0]["step"]) == ("Coordination", "Identity", 4)
    assert raised[0]["payload"]["bound"] == bound and raised[0]["proposal_ref"] == th["id"]
    assert [a["kind"] for a in W.asks(ref) if a["status"] == "pending"] == ["conflict"], "Identity could not settle it: the owner is asked once"
    assert _work(W, ref) == [], "the line is held while the conflict is open"
    assert _actions(J, ref)[-2:] == ["identity.ruled", "ask.created"] and J.status(ref)["step"] == 4


# ---- J2.7: a failed run ------------------------------------------------------------------------------------------------
def test_j2_7_a_failed_run_is_one_run_failed_event_on_the_ledger(j2, monkeypatch):
    """J2.7: a build that breaks a rule the owner stamped is filed failed and sent back to be rewritten, twice at most, and
    the owner is told; each failed build is one run.failed event on the ledger (with the reason, the run and the engine) and
    a run that passed never is. A failure the ledger does not see, or one it sees twice, fails."""
    W, R, J, _ = j2
    holds = {"broken": True}

    def check_rules(prompt):
        return {"broken": [{"rule": RULE, "pages": ["about"], "why": "no 108"}] if holds["broken"] else []}

    _model(monkeypatch, R, {"audit.judge": {"ok": True, "findings": []}, "audit.items": _items_met, "check.rules": check_rules})
    ref = _born(j2, settle=False)
    # the owner states the rule before the line has run, and stamps it: Check holds every build to it from the first
    W.owner_ask(ref, "From now on, every page ends with: Call 108.")
    for _ in range(60):
        if [a for a in W.asks(ref) if a["kind"] == "rule" and a["status"] == "pending"] or not _tick(W, ref):
            break
    _stamp_all(W, ref, kind="rule")
    assert [r["line"] for r in W.dept(ref)["rules"]][-1] == RULE and J.status(ref)["step"] == 6

    failed_builds = [v for v in W.versions(ref, "Build") if not v["check"]["ok"]]
    assert len(failed_builds) == 3, "the build, and the two rewrites it was sent back for"
    said = [t["line"] for t in R.chat_view(ref)["turns"] if t["word"] == "broken"]
    assert len(said) == 3 and all(s.endswith("Sent back to be rewritten.") for s in said[:2])
    assert "two rewrites did not mend it. Say the rule another way, or drop it." in said[2]
    assert W.read_files(ref, "Brief", W.latest(ref, "Brief")["v"])["brief.md"].count(R.SEND_BACK) == 2

    failed = [e for e in J.events(ref) if e["action"] == "run.failed"]
    assert len(failed) == len(failed_builds) == 3, "one event for each failed build"
    assert {e["run_ref"] for e in failed} == {r["id"] for r in W.runs(ref) if r["status"] == "failed"}, "and for nothing else that failed"
    assert len({e["run_ref"] for e in failed}) == 3, "each run once"
    for e in failed:
        assert (e["actor"], e["recipient"], e["step"], e["journey"], e["workflow_ref"]) == ("Check", "Coordination", 6, "J2.f", "Check")
        assert e["state"] == "failed" and e["reason_codes"] == ["check.failed"] and "check failed" in e["summary"]

    # the rule is met at last: the line goes on to its end, and not one more run.failed is written, for it or for the rest
    holds["broken"] = False
    W.owner_ask(ref, "Add a page on visiting hours.")
    W.run_until_idle(ref, limit=300)
    passed = [e for e in J.events(ref) if e["action"] == "run.completed"]
    assert len(failed) == 3 and len([e for e in J.events(ref) if e["action"] == "run.failed"]) == 3
    assert not {e["run_ref"] for e in passed} & {e["run_ref"] for e in failed}, "a run that passed is never a failed one"
    assert [e["workflow_ref"] for e in passed][-1] == "Check" and len(passed) > len(LINE) - 1
    assert [v["check"]["ok"] for v in W.versions(ref, "Build")] == [False, False, False, True]
    W.run_until_idle(ref, limit=100)
    assert len([e for e in J.events(ref) if e["action"] == "run.failed"]) == 3, "more turns of the motor add nothing"


def test_j2_7_after_the_goal_a_failed_run_is_not_yet_a_run_failed_event(j2, monkeypatch):
    """J2.7 after the goal is reached (BL-4b). The ledger writes a run only while the cycle is active (`j2_runtime.on_run`), and
    a cycle that reached its goal is done. A build that breaks a rule stamped after that is still filed failed, sent back
    twice and then asked about: that is the line's own record and it holds. But the ledger holds fewer `run.failed` events
    than the department had failed runs: the sends-back of a done cycle are not on it, and the one that is, is there only
    because the options ask moved the cycle out of done. This states the gap and does not endorse it: when the ledger
    records the failed runs of a done cycle, the last assertion fails, and J2.7 is bound to a test that asserts all three."""
    W, R, J, _ = j2
    holds = {"broken": False}

    def check_rules(prompt):
        return {"broken": [{"rule": RULE, "pages": ["about"], "why": "no 108"}] if holds["broken"] else []}

    _model(monkeypatch, R, {"audit.judge": {"ok": True, "findings": []}, "audit.items": _items_met, "check.rules": check_rules})
    ref = _born(j2)
    _stamp_all(W, ref)                                           # the first publish: the goal is reached, the cycle is done
    assert J.status(ref)["state"] == "done" and [e["action"] for e in J.events(ref)][-1] == "goal.reached"
    assert [r for r in W.runs(ref) if r["status"] == "failed"] == [] and [e for e in J.events(ref) if e["action"] == "run.failed"] == []

    # the owner states a rule after the goal and stamps it: the department builds again, and the build breaks the rule
    holds["broken"] = True
    W.owner_ask(ref, "From now on, every page ends with: Call 108.")
    W.run_until_idle(ref, limit=300)
    _stamp_all(W, ref, kind="rule")
    assert [r["line"] for r in W.dept(ref)["rules"]][-1] == RULE

    # what the line keeps holds after the goal as it does before it: three failed builds, sent back twice, then the owner is asked
    failed_runs = [r for r in W.runs(ref) if not r.get("system") and r["status"] == "failed"]
    assert [v["check"]["ok"] for v in W.versions(ref, "Build")][-3:] == [False, False, False] and len(failed_runs) == 3
    said = [t["line"] for t in R.chat_view(ref)["turns"] if t["word"] == "broken"]
    assert len(said) == 3 and all(s.endswith("Sent back to be rewritten.") for s in said[:2])
    assert "two rewrites did not mend it. Say the rule another way, or drop it." in said[2]
    assert [a["kind"] for a in W.asks(ref) if a["status"] == "pending"] == ["blocked"], "one ask, with the ways out"
    assert len([e for e in J.events(ref) if e["action"] == "goal.reached"]) == 1, "the goal was reached once, and a failed build does not undo it"

    # what the ledger keeps does not: a run.failed event is a failed run, but not every failed run is one (BL-4b)
    on_ledger = [e for e in J.events(ref) if e["action"] == "run.failed"]
    assert {e["run_ref"] for e in on_ledger} <= {r["id"] for r in failed_runs}, "an event is never written for a run that did not fail"
    assert len(on_ledger) < len(failed_runs), "BL-4b: the ledger misses the failed runs of a cycle that is done"
