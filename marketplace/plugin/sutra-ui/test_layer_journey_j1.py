"""J1 as a child of the journey template (PRD amendment A3.7.1): found the organisation, be asked until it is clear, and have
the first department made.

`journeys/J1.json` says what a person goes through; this file runs the real flow with a model that is a function and asks the
one question of A3.6: did the journey happen the way its definition says? (`journeys.walk`). It also holds the one edge test
that J1 was missing, the waits of a model that is away (J1.8). The model is stubbed everywhere: no test here calls a live one.

The fixture, the model and the shape are the ones of test_j1.py, copied and not imported, so this file stands alone.
"""
import copy
import importlib
import time

import pytest

import journeys
from journeys import walk

OPENING = "Build me a website"
QUESTION = "What should this department make or achieve, and who is it for?"
ANSWER = "It teaches algebra to Class 8 students so that they practise every week"

LIVE_SHAPE = {"name": "Acme Learning Algebra Website", "kind": "website",
              "goal": "Build a website that teaches algebra to Class 8 students.",
              "purpose": "A live website that teaches algebra to Class 8 students.",
              "route": "template", "template_ref": {"id": "website", "version": "1"}}


@pytest.fixture
def j1(tmp_path, monkeypatch):
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
    """A model that is a function: `answers` maps a step id to what the model says for it (a dict, or a callable taking the
    prompt). Every other step falls to its draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    seen = []

    def model(prompt, step):
        seen.append((step["id"], prompt))
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"

    monkeypatch.setattr(R, "MODEL", model)
    return seen


def _root(j1, name="Acme Learning"):
    W, _, _, founding = j1
    return founding.found_structure(name, owner="Sankalp")["root"]


def _children(W, root):
    return [d for d in W.list_depts() if d.get("parent") == root]


def _root_board(R, root):
    """Root's board as (sender, act, word) in the order it was written."""
    return [(p["src"], p["msg_type"], (p["payload"] or {}).get("word")) for p in R.board(root)]


def _said(R, root, word):
    return [str((p["payload"] or {}).get("done") or "") for p in R.board(root)
            if p["src"] == "Identity" and (p["payload"] or {}).get("word") == word]


def _asks_once_then_clear(monkeypatch, R):
    """The model of the scenario: Root's converse step asks one question the first time and says clear the second; the shape
    step returns a website."""
    asked = {"n": 0}

    def converse(prompt):
        asked["n"] += 1
        if asked["n"] == 1:
            return {"verdict": "ask", "question": QUESTION}
        return {"verdict": "clear", "question": ""}

    return _model(monkeypatch, R, {"setup.converse": converse, "setup.shape": dict(LIVE_SHAPE)})


# ---- the walk -----------------------------------------------------------------------------------------------------------
def test_j1_walk_found_ask_decide_build_tell(j1, monkeypatch):
    """The journey as a person lives it: found the organisation, say vague words, be asked one question, answer it, and
    watch Root decide, build and tell. A question asked twice, a department made before the answer, a stamp at birth or a
    tell that names no first move fails here; so does a step the definition names that the run never took (the walk)."""
    W, R, J, _ = j1
    J1 = journeys.load()["J1"]
    _asks_once_then_clear(monkeypatch, R)
    root = _root(j1)                                                # steps 1 and 2: found; Root is there
    assert W.dept(root)["kind"] == "root"

    W.owner_ask(root, OPENING)                                      # the vague words
    W.run_until_idle(root, limit=200)
    questions = _said(R, root, "question")                          # step 3: Root asks until it is clear
    assert questions == [QUESTION] and questions[0].count("?") == 1
    assert _children(W, root) == [], "nothing is made while the question is open"
    assert not [a for a in W.asks(root) if a["kind"] == "setup"], "the question is Root's, not a stamp for the owner"

    W.owner_ask(root, ANSWER)                                       # step 4: the answer
    W.run_until_idle(root, limit=200)
    [child] = _children(W, root)                                    # steps 5 and 6: Root decides and builds
    assert child["kind"] == "website" and child["template_ref"] == {"id": "department/website", "version": 1}
    five = ["Identity", "Priority", "Coordination", "Adaptation", "Audit"]
    assert {s["name"] for s in W.map_view(child["ref"])["systems"]} == set(five)
    born = W.dept(child["ref"])                                     # step 6: its born rules and its limits, as the record keeps them
    assert [(r["tag"], r["line"]) for r in born["rules"]] == [
        ("go", "Plan, write and check inside the record"), ("ask", "Ask the owner before the first publish"),
        ("refuse", "Never publish a build whose check failed")], "the born rules: one that goes, one that asks, one that refuses"
    assert born["envelopes"] == {f: {"calls": 30, "usd": 6.0} for f in five}, "a limit for each of the five functions, and for no engine yet"
    assert [m["text"] for m in child["initial_goal_context"]["messages"] if m["actor"] == "user"] == [OPENING, ANSWER]
    assert not [a for a in W.asks(root) if a["kind"] == "setup"], "no stamp at birth (S-18)"
    assert _said(R, root, "request") == ["That is clear. I am shaping the department now."]
    told = _said(R, root, "department")                             # step 7: Root tells the owner what it made
    assert len(told) == 1 and "is set up with" in told[0] and "First:" in told[0]
    assert child["name"] in told[0]

    # the board of Root, in the order it was written: the owner's two turns, and Root's words between and after them
    assert _root_board(R, root)[:5] == [("Owner", "request", "front"), ("Identity", "inform", "question"),
                                        ("Owner", "request", "front"), ("Identity", "inform", "request"),
                                        ("Identity", "inform", "department")]

    # the whole flow, against the record only: every act and step the seven steps name happened, in the order they give
    assert walk.follows(J1, walk.trace(W, R, J, root, child["ref"]), walks=["1", "2", "3", "4", "5", "6", "7"]) == []
    assert J1["scenarios"][0]["walks"] == ["1", "2", "3", "4", "5", "6", "7"]


# ---- J1.8: the waits ----------------------------------------------------------------------------------------------------
class _Clock:
    """The runtime's `time` module with a clock the test moves: only time() is its own, so a wait is read exactly."""

    def __init__(self):
        self.now = time.time()

    def time(self):
        return self.now

    def __getattr__(self, name):
        return getattr(time, name)


def test_j1_8_the_waits_are_30_120_and_600_seconds(j1, monkeypatch):
    """J1.8: a soft step with the model away waits 30, then 120, then 600 seconds, and only then asks the owner; the
    Request is kept as it was said. A wait that is zero, one that is the same each time, or an ask before the third wait
    fails. (test_j1 sets the waits to zero to run quickly; this is the one test of the real ones.)"""
    W, R, J, _ = j1
    assert R.WAITS == (30, 120, 600)
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: (None, 0.0, "away"))
    clock = _Clock()
    monkeypatch.setattr(R, "time", clock)
    root = _root(j1)
    words = "Build a website that teaches algebra to Class 8 students"
    W.owner_ask(root, words)

    def asks_of_the_model():
        return [a for a in W.asks(root) if a["kind"] == "model"]

    started = []
    for wait in R.WAITS:
        started.append(clock.now)
        W.run_until_idle(root, limit=200)
        waiting = [r for r in W.runs(root) if r["engine"] == "Setup" and r["status"] == "waiting"]
        assert len(waiting) == len(started)
        assert waiting[-1]["retry_at"] - started[-1] == wait, "this wait is %s seconds" % wait
        if len(started) < len(R.WAITS):
            assert asks_of_the_model() == [], "the owner is asked only after the last wait"
            W.run_until_idle(root, limit=200)
            assert len([r for r in W.runs(root) if r["engine"] == "Setup" and r["status"] == "waiting"]) == len(started), \
                "before the wait is over nothing is tried again"
        clock.now += wait                                           # the wait is over: the next turn tries the model again

    W.run_until_idle(root, limit=200)                               # the third wait is over: the owner is asked
    assert [r["retry_at"] - s for r, s in zip([r for r in W.runs(root) if r["engine"] == "Setup" and r["status"] == "waiting"], started)] \
        == [30, 120, 600]
    assert len(asks_of_the_model()) == 1 and asks_of_the_model()[0]["status"] == "pending"
    assert "Try again?" in asks_of_the_model()[0]["text"]
    W.run_until_idle(root, limit=200)
    assert len(asks_of_the_model()) == 1, "one ask, however long it stays open"
    # the Request is kept as it was said; nothing was decided while the model was away
    state = W._read(W.ddir(root) / "j1-state.json", {})
    assert state["status"] == "collecting" and [m["text"] for m in state["messages"]] == [words]
    assert _children(W, root) == []


def test_j1_the_walk_fails_when_a_bind_is_not_what_the_run_did(j1, monkeypatch):
    """The walk is a check and not a rubber stamp: a copy of J1 whose step 3 names a step the run never took, or whose step 5
    names a sender that did not speak, fails the walk and says which step and which bind."""
    W, R, J, _ = j1
    _asks_once_then_clear(monkeypatch, R)
    root = _root(j1)
    W.owner_ask(root, OPENING)
    W.run_until_idle(root, limit=200)
    W.owner_ask(root, ANSWER)
    W.run_until_idle(root, limit=200)
    [child] = _children(W, root)
    record = walk.trace(W, R, J, root, child["ref"])
    J1 = journeys.load()["J1"]
    assert walk.follows(J1, record, walks=["3", "5"]) == []

    broken = copy.deepcopy(J1)
    for step in broken["steps"]:
        for bind in step.get("binds") or []:
            if bind.get("id") == "setup.say":
                bind["id"] = "setup.sayy"
            if step["n"] == "5" and bind.get("kind") == "act":
                bind["src"] = "Audit"
    faults = walk.follows(broken, record, walks=["3", "5"])
    assert any(f.startswith("J1 step 3:") and "setup.sayy" in f for f in faults), faults
    assert any(f.startswith("J1 step 5:") and "Audit" in f for f in faults), faults
    assert not [f for f in faults if "step 1" in f or "step 2" in f]
