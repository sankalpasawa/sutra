"""The pursue scenario (PRD M9, W2-ADAPT F5): a reading that is not done gives a priced round, the round is filed as a correction to
the Brief, the registered line runs again, Audit reads again, and the loop ends in the goal reached or, at the ceiling, in one ask
with options. Run end to end on a website department as a person makes one, with a model that is a function in place of every agent
(Audit's reader says what each reading finds; the other steps fall to their drafts), and the motor run until idle.

  P1  not met, a round, Brief v3, Live site v2, a new reading, goal.reached; only registered engines run (SM-3)
  P2  a run that hits the ceiling ends in an options ask, never in silence (SM-6)
  P3  a reading with an item not met gives one round naming it, priced by Priority, filed as 'Correct this', and the line runs again

THE NEIGHBOURS. The loop is three layers'. Identity hears the reading and asks Adaptation for the next round, then files the round
Priority said yes to (W2-IDENTITY, M8.4 and M9.3); Priority prices the round inside the goal's ceiling (W2-PRIORITY, M9.2);
Adaptation proposes the round (this package). Where a neighbour's handler is in the recipe of the build under test, the real one
runs and nothing stands in for it. Where it is not yet (this branch is cut before they merge), a stand-in does what that handler
posts or calls, no more, and stands down the moment the real handler is there. So the same test is the scenario of this branch
and of the merged build.
"""
import importlib
import json
import re

import pytest

import layer_schema as S
import layers

WEBSITE = "Build a website that teaches algebra to Class 8 students"
LINE = ["Plan", "Write", "Check", "Publish"]
D2_CLAIM = "the doctors page does not name the phone line"
ITEMS = [{"text": "The site is live", "how": "code", "level": "outcome"},
         {"text": "Every page names the phone line", "how": "model", "level": "target"},
         {"text": "A visitor can find the doctors", "how": "person", "level": "outcome"}]


@pytest.fixture
def j2(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    monkeypatch.delenv("J2_ADAPT_MAKE", raising=False)

    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime as R
    import j2_runtime as J
    import functions_view as FV

    for module in (E, W, org2_apply, founding, R, J, FV):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding, FV


def v1():
    return importlib.import_module("layers.adaptation.v1")


# ---- the reader: what Audit says of each Live site, in order ---------------------------------------------------------------
def _reader(monkeypatch, R, verdicts):
    """Audit's reader of the done-when items (audit.items) as a function: the Nth reading it is asked for says what `verdicts[N]`
    says, a list of the ids of the items that are not met (all others are met). Every other agent step falls to its draft, as it
    does offline; the judge reads nothing wrong. Returns the prompts the reader was sent."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    asked = []

    def reader(prompt):
        n = min(len(asked), len(verdicts) - 1)
        asked.append(prompt)
        items = json.loads(prompt.split("THE DONE-WHEN ITEMS:\n", 1)[1].split("\n\nWHAT CODE MEASURED:", 1)[0])
        rows, found = [], []
        for i in items:
            if i["id"] in verdicts[n]:
                rows.append({"id": i["id"], "verdict": "not_met", "claim": D2_CLAIM, "evidence": "doctors.html has no number"})
                found.append({"where": "doctors", "claim": D2_CLAIM, "severity": "high", "item": i["id"]})
            else:
                rows.append({"id": i["id"], "verdict": "met", "claim": "it holds", "evidence": "the work shows it"})
        return {"items": rows, "findings": found}

    def model(prompt, step):
        if step["id"] == "setup.converse":
            return {"verdict": "clear", "question": ""}, 0.01, "model"
        if step["id"] == "setup.shape":
            return {"name": "Acme Learning Department", "kind": "website", "goal": WEBSITE, "done_items": ITEMS}, 0.01, "model"
        if step["id"] == "audit.items":
            return reader(prompt), 0.01, "model"
        if step["id"] == "audit.judge":
            return {"ok": True, "findings": []}, 0.01, "model"
        return None, 0.0, "offline"
    monkeypatch.setattr(R, "MODEL", model)
    return asked


def _born(j2, words=WEBSITE, org="Acme Learning"):
    W, R, J, founding, FV = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    return ref


def _stamp(W, ref, kind=None):
    """The owner's one stamp on what goes out (the first publish): a born rule says ask."""
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == (kind or "publish")]:
        W.decide_ask(ref, a["id"], True)


# ---- the neighbours that are not on this branch ----------------------------------------------------------------------------
def _heard(R, act, word):
    return R._handler(R.engine_def("Identity"), {"msg_type": act, "payload": {"word": word}}) is not None


class Neighbours:
    """What Identity does with a reading and a round Priority said yes to, and what Priority does at the goal's ceiling, for a
    build whose recipes do not have those handlers yet. Each does only what the real handler posts or calls, and stands down the
    moment the real handler is in the recipe: `identity` and `priority` say which are in play."""

    def __init__(self, j2, monkeypatch, ceiling=None):
        self.W, self.R, self.J, _, _ = j2
        self.identity = not (_heard(self.R, "inform", "reading") and _heard(self.R, "inform", "round"))
        self.priority = ceiling is not None and "round_within_ceiling" not in S.CHECKS["priority"]
        self.asked, self.filed, self.ceiling = set(), set(), ceiling
        if self.identity:
            monkeypatch.setattr(v1(), "hears_round", lambda: True)       # the conflict of a refused round goes to Identity all the same
        if self.priority:
            mod = layers.load("priority/v1")
            real = mod.CODE["priority_post"]
            neighbours = self

            def gate(ctx, step, item):
                pl = ctx["post"]["payload"]
                if pl.get("word") == "round" and int(pl.get("round") or 0) > neighbours.ceiling:
                    neighbours.R.post(ctx["ref"], "Priority", "Adaptation", "reject-proposal",
                                      {"word": "round", "why": "round %d is past the ceiling of %d" % (pl["round"], neighbours.ceiling),
                                       "options": neighbours.options()}, thread=ctx["post"]["thread"])
                    return {"said": "said no to round %s: past the ceiling" % pl.get("round")}
                return real(ctx, step, item)
            monkeypatch.setitem(mod.CODE, "priority_post", gate)

    def options(self):
        W = self.W
        return [W.option("raise", "Add rounds", "up to twice where it started", params={"what": "ceiling", "rounds": self.ceiling * 2}),
                W.option("leave:D2", "Leave D2 out", "D2 is dropped from done-when; nothing more is spent"),
                W.option(W.STOP_OPTION, "Stop here", "the department stops where it is; you can start it again later")]

    def step(self, ref):
        """One thing the stand-in Identity would have done, if there is one: ask for a round on a reading that is not met, or
        file the round Priority said yes to. True when it did something."""
        if not self.identity:
            return False
        W, R = self.W, self.R
        for r in W.rows(ref, "readings.jsonl"):
            not_met = [i["id"] for i in r["items"] if i["verdict"] == "not_met"]
            if r["read"] and not_met and r["id"] not in self.asked:
                self.asked.add(r["id"])
                R.post(ref, "Identity", "Adaptation", "request", {"word": "next", "items": not_met, "reading": r["id"],
                                                                   "findings": [f["id"] for f in r["findings"]]})
                return True
        for row in v1().rounds_of(ref):
            if row["status"] == "granted" and row["round"] not in self.filed:
                self.filed.add(row["round"])
                R._file_brief(ref, W.dept(ref), "Correct this: " + row["correction"], "a round Priority said yes to")
                W.signal()
                return True
        return False


def _pursue(j2, ref, neighbours, limit=12):
    """The motor until idle, and between its turns what the neighbours do on the board: until nothing is left to do."""
    W = j2[0]
    for _ in range(limit):
        W.run_until_idle(ref, limit=300)
        _stamp(W, ref)
        if not neighbours.step(ref):
            W.run_until_idle(ref, limit=300)
            if not neighbours.step(ref):
                return


def _events(J, ref):
    return [e["action"] for e in J.events(ref)]


def _registered_engines(W, ref):
    d = W.dept(ref)
    return set(d["workflows"][-1]["engines"]) | set(j for w in d["workflows"] for j in w["engines"])


def _brief(W, ref):
    cur = W.latest(ref, "Brief")
    return cur["v"], W.read_files(ref, "Brief", cur["v"]).get("brief.md", "")


def _work(W, ref):
    return [r["engine"] for r in W.runs(ref) if not r.get("system")]


def _only_registered_engines_ran(W, R, ref):
    """SM-3: every engine that ran was in a registered line, or is one the owner added (J5)."""
    d = W.dept(ref)
    allowed = {n for w in d["workflows"] for n in w["engines"]} | set(R.coordination(ref).get("grown") or [])
    assert set(_work(W, ref)) <= allowed, (set(_work(W, ref)) - allowed)


def test_p1_not_met_a_round_the_brief_corrected_the_line_run_again_and_the_goal_reached(j2, monkeypatch):
    W, R, J, _, _ = j2
    asked = _reader(monkeypatch, R, [["D2"], []])
    ref = _born(j2)
    neighbours = Neighbours(j2, monkeypatch)
    W.run_until_idle(ref, limit=300)
    _stamp(W, ref)
    W.run_until_idle(ref, limit=300)
    # not met: Audit read Live site v1 and found D2 does not hold
    first = W.rows(ref, "readings.jsonl")[0]
    assert first["v"] == 1 and {i["id"]: i["verdict"] for i in first["items"]} == {"D1": "met", "D2": "not_met", "D3": "met"}
    _pursue(j2, ref, neighbours)
    d = W.dept(ref)
    # a round, named D2 and priced: one proposal to Priority, Priority's answer in its thread, and a price row for it
    [sent] = [p for p in R.board(ref) if p["src"] == "Adaptation" and p["dst"] == ["Priority"] and p["payload"].get("word") == "round"]
    assert sent["payload"]["round"] == 1 and sent["payload"]["covers"] == ["D2"] and "D2" in sent["payload"]["correction"]
    yes = [p for p in R.board(ref) if p["src"] == "Priority" and p["thread"] == sent["thread"] and p["msg_type"] == "accept-proposal"]
    assert yes and yes[0]["payload"]["word"] == "round", "Priority said yes to the round"
    assert [r for r in W.rows(ref, "prices.jsonl") if r.get("thread") == sent["thread"]], "and priced it"
    first_round = v1().rounds_of(ref)[0]                    # Priority granted it; Identity then filed it and Audit read after it, each moving it on
    assert first_round["round"] == 1 and first_round["status"] in v1().RAN
    # the Brief has the correction, as a new version, filed as 'Correct this' with no stamp
    # (the version before it is read from the record, not taken before the round: a build whose Identity files rounds runs the
    # whole loop inside the motor, so there is no moment between the reading and the filing for the test to stand in)
    brief_after, text = _brief(W, ref)
    before = W.read_files(ref, "Brief", brief_after - 1).get("brief.md", "") if brief_after > 1 else ""
    assert brief_after > 1 and "Correct this" not in before, "the correction is a new version of the Brief"
    assert "Correct this" in text and "Every page names the phone line" in text, text
    assert not [a for a in W.asks(ref) if a["kind"] in ("line", "j2_identity", "conflict") and a["status"] == "pending"], "no stamp was asked for a round"
    # the registered line ran again: Live site v2, read again, and every item holds
    assert W.latest(ref, "Live site")["v"] == 2 and {n: _work(W, ref).count(n) for n in LINE} == {n: 2 for n in LINE}
    second = W.rows(ref, "readings.jsonl")[-1]
    assert second["v"] == 2 and second["id"] != first["id"] and {i["verdict"] for i in second["items"]} == {"met"}
    acts = _events(J, ref)
    assert acts.count("goal.reached") == 1 and acts[-1] == "goal.reached" and J.status(ref)["goal_reached"] is True
    # a round never registered a line, and only the engines of the registered line ran (SM-3)
    assert len(d["workflows"]) == 1 and d["workflows"][0]["engines"] == LINE
    _only_registered_engines_ran(W, R, ref)
    assert len(asked) == 2, "Audit read twice: once before the round and once after"


def test_pursue_a_not_met_item_gets_a_priced_round(j2, monkeypatch):
    """A3's row (J2 step 8, the next round): a reading with an item not met gives one round naming it, priced by Priority, filed as
    'Correct this', and the line runs again."""
    W, R, J, _, _ = j2
    _reader(monkeypatch, R, [["D2"], []])
    ref = _born(j2)
    neighbours = Neighbours(j2, monkeypatch)
    _pursue(j2, ref, neighbours)
    rounds = v1().rounds_of(ref)
    assert [(r["round"], r["covers"]) for r in rounds] == [(1, ["D2"])], "one round, and it names D2"
    [priced] = [r for r in W.rows(ref, "prices.jsonl") if r.get("thread") == rounds[0]["thread"]]
    assert priced["answer"] == "accept" and priced["estimate"]["calls"] >= 0, "priced by Priority, in money and room"
    assert rounds[0]["estimate"], "and the round carried the line's observed cost to it"
    assert "Correct this" in _brief(W, ref)[1]
    assert _work(W, ref).count("Plan") == 2, "the line ran again"


def test_p2_a_run_that_hits_the_ceiling_ends_in_an_options_ask_and_not_in_silence(j2, monkeypatch):
    W, R, J, _, _ = j2
    monkeypatch.setattr(S, "ROUNDS_DEFAULT", 1)                         # the goal's ceiling: one round (Priority's default is six)
    _reader(monkeypatch, R, [["D2"]])                                   # and D2 is never put right
    ref = _born(j2)
    neighbours = Neighbours(j2, monkeypatch, ceiling=1)
    _pursue(j2, ref, neighbours, limit=16)
    ceiling = ((W.dept(ref).get("ceiling") or {}).get("rounds")) or neighbours.ceiling
    rows = v1().rounds_of(ref)
    assert [r["round"] for r in rows] == list(range(1, ceiling + 2)), "one round past the ceiling was proposed, and no more"
    assert len(rows[:-1]) == ceiling and all(r["status"] in v1().RAN for r in rows[:-1]) and rows[-1]["status"] == "refused", "the last was not funded"
    acts = _events(J, ref)
    assert "goal.reached" not in acts and J.status(ref)["goal_reached"] is False, "it did not finish"
    # the end is a conflict to Identity with the ways out Priority priced, and Identity's one ask with options
    conflicts = [p["payload"] for p in R.board(ref) if p["src"] == "Adaptation" and p["dst"] == ["Identity"] and p["payload"].get("word") == "conflict"]
    assert len(conflicts) == 1 and conflicts[0]["round"] == rows[-1]["round"] and 1 <= len(conflicts[0]["options"]) <= 3
    assert S.validate("act.conflict", conflicts[0]) == []
    asks = [a for a in W.asks(ref) if a["status"] == "pending" and a.get("options")]
    assert asks, "SM-6: an end that is not done has a pending ask with options"
    for a in asks:
        assert 1 <= len(a["options"]) <= 3 and all(o["kind"] in S.OPTION_KINDS for o in a["options"]), a["options"]
        assert not re.search(r"\b(grant|counter|refus)", " ".join(str(a.get(k) or "") for k in ("text", "title", "why")), re.I), "the owner's words"
    _only_registered_engines_ran(W, R, ref)


def test_p3_the_same_item_not_met_twice_gets_a_different_correction_and_two_rounds_reach_the_goal(j2, monkeypatch):
    """The acceptance of M9: a department with a failing item reaches done in two or more rounds."""
    W, R, J, _, _ = j2
    _reader(monkeypatch, R, [["D2"], ["D2"], []])
    ref = _born(j2)
    neighbours = Neighbours(j2, monkeypatch)
    _pursue(j2, ref, neighbours)
    rows = v1().rounds_of(ref)
    assert [(r["round"], r["covers"]) for r in rows] == [(1, ["D2"]), (2, ["D2"])] and all(r["status"] in v1().RAN for r in rows)
    one, two = rows[0]["correction"], rows[1]["correction"]
    assert v1().words_of(one) != v1().words_of(two) and two.startswith("Try another way, attempt 2."), (one, two)
    text = _brief(W, ref)[1]
    assert text.count("Correct this") == 2 and "Try another way" in text, text
    assert W.latest(ref, "Live site")["v"] == 3 and _work(W, ref).count("Publish") == 3
    acts = _events(J, ref)
    assert acts.count("goal.reached") == 1 and acts[-1] == "goal.reached"
    _only_registered_engines_ran(W, R, ref)


def test_p4_nobody_asks_for_a_round_unless_a_reading_found_an_item_not_met(j2, monkeypatch):
    W, R, J, _, _ = j2
    _reader(monkeypatch, R, [[]])                                       # every item holds the first time
    ref = _born(j2)
    neighbours = Neighbours(j2, monkeypatch)
    _pursue(j2, ref, neighbours)
    assert v1().rounds_of(ref) == [] and not [p for p in R.board(ref) if p["payload"].get("word") in ("next", "round")]
    assert _events(J, ref).count("goal.reached") == 1 and W.latest(ref, "Live site")["v"] == 1
