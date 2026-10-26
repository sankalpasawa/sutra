"""test_covering_checks.py -- each function's covering check is code, and it fails loudly (PRD M2.4).

Named claims, one per function and the done check:
  M2.4a  Audit: a finding names where and what. A stubbed finding with no 'where' fails the judge step; the version is
         marked not_read, the Audit node shows a fault, and no goal.reached is written (the done check)
  M2.4b  Priority: yes, less or no, each with its price. An answer that names no price fails the bargain, Priority's node
         shows a fault, and nothing is granted, registered or run
  M2.4c  Identity: a journey is named, and the verdict is go, ask or refuse; an ask or a refusal says why
  M2.4d  Coordination: one run at a time, and a chain stops under twelve. A start the covering does not hold for is never
         let through, even when the rule's own code said admit; the row says the covering failed
  M2.4e  Adaptation: a proposal names its rows; a move with no evidence rows fails
  M2.4f  a failed check never falls back to a draft: the failed row is the model's, and no other row of that step stands

The departments are born the way a person makes them (founded, asked for, set up by Root), on a records home of their
own; no test reaches a model or the network: the model is a function, and every step it does not answer runs offline.
"""
import importlib

import pytest

WEBSITE = "Build a website that teaches algebra to Class 8 students"


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
    import functions_view as F

    for module in (E, W, org2_apply, founding, R, J, F):
        importlib.reload(module)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    return W, R, J, founding, F


def _model(monkeypatch, R, answers):
    """A model that is a function: a step id maps to what the model says; every other step runs its offline draft."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)

    def model(prompt, step):
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"

    monkeypatch.setattr(R, "MODEL", model)


def _born(j2, words=WEBSITE, org="Acme Learning"):
    W, _, _, founding, _ = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _actions(J, ref):
    return [e["action"] for e in J.events(ref)]


def _node(F, ref, fn):
    return next(n for n in F.functions(ref)["functions"] if n["name"] == fn)


# ---- M2.4a: Audit, the done check ------------------------------------------------------------------------------------
def test_m2_4a_an_audit_finding_with_no_where_fails_the_step_and_no_goal_is_reached(j2, monkeypatch):
    """A finding with no 'where' read as a reading (the goal then reached, or 'found nothing' said) must fail."""
    W, R, J, _, F = j2
    _model(monkeypatch, R, {"audit.judge": {"ok": False, "findings": [{"claim": "The fees are invented", "severity": "high"}]}})
    ref = _born(j2)
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "publish"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)

    judged = [r for r in R.step_rows(ref) if r["step"] == "audit.judge"]
    assert [r["status"] for r in judged] == ["failed"]
    assert "names no where" in judged[0]["why"] and judged[0]["by"] == "model"          # M2.4f: the model's, no draft after it
    audit = [r for r in W.runs(ref) if r["engine"] == "Audit"]
    assert audit and audit[-1]["status"] == "failed"
    acts = _actions(J, ref)
    assert "goal.reached" not in acts and "audit.finding_filed" not in acts
    unread = [e for e in J.events(ref) if e["action"] == "audit.not_read"]
    assert len(unread) == 1 and unread[0]["evidence_refs"] == [{"artifact": "Live site", "version": 1}]
    assert "failed its check" in unread[0]["summary"] and "names no where" in unread[0]["summary"]
    st = J.status(ref)
    assert (st["state"], st["step"], st["goal_reached"]) == ("unread", 7, False)
    node = _node(F, ref, "Audit")
    assert node["state"] == "fault" and node["word"] == "fault" and "names no where" in node["why"]
    assert not [a for a in W.asks(ref) if a["kind"] == "finding"]                       # nothing was put to the owner
    W.run_until_idle(ref, limit=100)
    assert "goal.reached" not in _actions(J, ref)


def test_m2_4a_a_finding_that_names_its_page_is_a_reading(j2):
    _, R, _, _, _ = j2
    _, s = R.step_def("audit.judge")
    check = R.CHECK[s["check"]]
    assert check(None, s, None, {"ok": False, "findings": [{"page": "index.html", "claim": "The fees are invented"}]})["ok"]
    assert check(None, s, None, {"ok": True, "findings": []})["ok"]
    assert not check(None, s, None, {"ok": False, "findings": [{"page": "index.html", "claim": " "}]})["ok"]
    assert not check(None, s, None, {"ok": False, "findings": "none"})["ok"]


# ---- M2.4b: Priority -------------------------------------------------------------------------------------------------
def test_m2_4b_a_bargain_that_names_no_price_fails_and_nothing_is_granted(j2, monkeypatch):
    W, R, J, _, F = j2
    _model(monkeypatch, R, {"priority.bargain": {"answer": "accept", "why": ""}})
    ref = _born(j2)
    bargained = [r for r in R.step_rows(ref) if r["step"] == "priority.bargain"]
    assert bargained and bargained[-1]["status"] == "failed" and "names no price" in bargained[-1]["why"]
    acts = _actions(J, ref)
    assert "proposal.granted" not in acts and "workflow.registered" not in acts
    assert not [r for r in W.runs(ref) if not r.get("system")]                           # nothing ran
    node = _node(F, ref, "Priority")
    assert node["state"] == "fault" and "names no price" in node["why"]


def test_m2_4b_an_ask_for_less_names_what_it_keeps(j2):
    _, R, _, _, _ = j2
    _, s = R.step_def("priority.bargain")
    check = R.CHECK[s["check"]]
    assert check(None, s, None, {"answer": "counter", "why": "room for two today", "keep": ["Plan", "Write"]})["ok"]
    got = check(None, s, None, {"answer": "counter", "why": "room for two today", "keep": []})
    assert not got["ok"] and got["notes"] == ["an ask for less names nothing to keep"]
    assert not check(None, s, None, {"answer": "maybe", "why": "unsure"})["ok"]


# ---- M2.4c: Identity -------------------------------------------------------------------------------------------------
def test_m2_4c_identitys_journey_is_named_and_its_verdict_says_why(j2):
    _, R, _, _, _ = j2
    _, take = R.step_def("identity.take")
    _, recognise = R.step_def("identity.recognise")
    assert R.CHECK[take["check"]](None, take, None, {"verdict": "go", "why": ""})["ok"]
    assert R.CHECK[take["check"]](None, take, None, {"verdict": "ask", "why": "it sends an email"})["ok"]
    got = R.CHECK[take["check"]](None, take, None, {"verdict": "refuse", "why": " "})
    assert not got["ok"] and got["notes"] == ["the verdict refuse does not say why"]
    assert not R.CHECK[take["check"]](None, take, None, {"verdict": "maybe"})["ok"]
    assert not R.CHECK[recognise["check"]](None, recognise, None, {"journey": "chat"})["ok"]


# ---- M2.4d: Coordination ---------------------------------------------------------------------------------------------
def _plain_dept(W, ref="dref-cover"):
    """A website department with its Brief v1 filed and nothing run on it yet."""
    W.create(ref, "Cover Website", None)
    W.add_version(ref, "Brief", {"brief.md": "# Cover Website\n\nA website for the cover band.\n"},
                  [{"ask": "a website for the cover band", "at": W.now()}], "owner", {"ok": True, "notes": ["the owner's goal"]})
    return ref


def test_m2_4d_one_run_at_a_time_is_the_covering_of_coordinations_rule(j2):
    W, R, _, _, _ = j2
    _, busy = R.step_def("coord.busy")
    check = R.CHECK[busy["check"]]
    assert check({"rs": []}, busy, None, {"answer": "admit"})["ok"]
    got = check({"rs": [{"engine": "Write", "status": "running"}]}, busy, None, {"answer": "admit"})
    assert not got["ok"] and got["notes"] == ["a start let through while Write runs"]
    assert check({"rs": [{"engine": "Write", "status": "running"}]}, busy, None, {"answer": "wait", "why": "running"})["ok"]


def test_m2_4d_a_chain_at_its_limit_is_never_let_through_even_when_its_rule_says_admit(j2, monkeypatch):
    """A gate whose own code says admit on a chain at its limit, let through because the covering's verdict was only
    written down, must fail."""
    W, R, J, _, F = j2
    monkeypatch.setenv("J2_FLOW_V1", "0")
    ref = _plain_dept(W)
    brief = W.latest(ref, "Brief")
    assert R._j2() and not J.active(ref)
    for i in range(W.CHAIN_LIMIT):
        W._put_run(ref, R._run_row("Plan", False, "Plan@old.%d" % i, "ok", "an earlier run", chain="brief.v%d" % brief["v"]))
    wrong = lambda ctx, step, item: ("admit", None)                                          # the rule went wrong
    monkeypatch.setitem(R.CODE, "coord_chain", wrong)
    import layers
    monkeypatch.setitem(layers.impl(ref, "coordination").CODE, "coord_chain", wrong)         # the gate resolves through its layer (A1)
    ctx = R._coord_ctx(ref)
    slot = W._slot_id("Plan", "Brief", brief["v"])
    answer, why = R.blocked(ctx, "Plan", R.engine_def("Plan"), {"v": brief["v"]}, slot)
    assert answer == "wait" and "at its limit of 12" in why
    rows = [r for r in R.step_rows(ref) if r["step"] == "coord.chain" and r["slot"] == slot]
    assert [(r["answer"], r["status"]) for r in rows] == [("wait", "failed")]
    assert "at its limit" in "; ".join(rows[0]["check"]["notes"])
    assert _node(F, ref, "Coordination")["state"] == "fault"


def test_m2_4d_under_its_limit_the_chain_lets_the_start_through(j2, monkeypatch):
    W, R, _, _, _ = j2
    monkeypatch.setenv("J2_FLOW_V1", "0")
    ref = _plain_dept(W, "dref-cover2")
    brief = W.latest(ref, "Brief")
    ctx = R._coord_ctx(ref)
    gctx = {"ref": ref, "def": R.engine_def("Plan"), "inp": {"v": brief["v"]}}
    _, chain = R.step_def("coord.chain")
    assert R.CHECK[chain["check"]](gctx, chain, None, {"answer": "admit"})["ok"]
    assert R.CHECK[chain["check"]](None, chain, None, {"answer": "admit"})["ok"]           # no run to read: nothing to hold
    assert R.CODE["coord_chain"]({"ref": ref, "def": R.engine_def("Plan"), "inp": {"v": brief["v"]}}, chain, None) == ("admit", None)
    assert ctx["table"]


# ---- M2.4e: Adaptation -----------------------------------------------------------------------------------------------
def test_m2_4e_a_proposal_names_its_rows(j2):
    _, R, _, _, _ = j2
    _, ladder = R.step_def("adapt.ladder")
    check = R.CHECK[ladder["check"]]
    ev = {"runs": 40, "differing": 0, "pass": 1.0, "misses": 0}
    assert check(None, ladder, None, {"moves": []})["ok"]
    assert check(None, ladder, None, {"moves": [{"kind": "trial", "step": "write.page", "evidence": ev},
                                                 {"kind": "end-trial", "step": "plan.pages", "why": "the trial disagreed"}]})["ok"]
    got = check(None, ladder, None, {"moves": [{"kind": "propose", "step": "write.page", "evidence": {"runs": 0}}]})
    assert not got["ok"] and got["notes"] == ["the move on write.page names no rows it rests on"]
    assert not check(None, ladder, None, {"moves": [{"kind": "end-trial", "step": "plan.pages"}]})["ok"]
    assert not check(None, ladder, None, {"moves": [{"kind": "jump", "step": "plan.pages", "evidence": ev}]})["ok"]


def test_m2_4_every_function_step_names_a_covering_that_ships(j2):
    """The definitions name the coverings this milestone adds, on the steps their pages name, and load clean."""
    _, R, _, _, _ = j2
    want = {"audit.judge": "findings_name_where_and_what", "priority.bargain": "answer_has_its_price",
            "adapt.ladder": "moves_name_their_rows", "coord.busy": "one_run_at_a_time", "coord.chain": "chain_under_its_limit",
            "identity.take": "verdict_is_known", "identity.recognise": "journey_is_known"}
    for sid, check in want.items():
        assert R.step_def(sid)[1]["check"] == check, sid
        assert check in R.CHECK
    assert R.validate(R.defs()) == []
