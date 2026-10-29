"""test_shadow_dept_apply.py -- what the decision does (PRD A5.3.4): a create makes the department once through founding.spawn, a
use or none writes nothing, and a create that an `ask` rule on Root holds is held for the owner (S-18: no stamp is raised; the
owner's yes is confirmed=true on the department route). Link-only: nothing is messaged and no worker is swapped."""
import json

import pytest

from test_shadow_dept import GOAL, TASK, org, reply, run  # noqa: F401  (the fixture)

NEW = dict(action="create", kind="default", name="Payroll", goal="Run the payroll for every employee each month",
           reason="no department does payroll", confidence="high", done_items=["Each payslip is filed"])
ASK_RULE = {"tag": "ask", "line": "A new department needs the owner's yes", "id": "t-ask", "version": 1}


def _spawns(org, monkeypatch):
    calls = []
    real = org.founding.spawn

    def spy(*a, **k):
        calls.append((a, k))
        return real(*a, **k)
    monkeypatch.setattr(org.founding, "spawn", spy)
    return calls


def _ask_rule(org):
    d = org.W.dept(org.root)
    d["rules"] = list(d.get("rules") or []) + [dict(ASK_RULE)]
    org.W.save_dept(org.root, d)


def _children(org):
    return [d for d in org.W.list_depts() if d.get("parent") == org.root]


def test_a_create_calls_founding_spawn_once_and_the_department_exists(org, monkeypatch):
    calls = _spawns(org, monkeypatch)
    org.sd.CHOOSER["fn"] = lambda text: reply(**NEW)
    d = run(org.sd.decide_and_apply(None, words=TASK))
    assert len(calls) == 1
    (args, kw) = calls[0]
    assert args[:4] == (org.root, "Payroll", "default", NEW["goal"]) and kw["done_items"] == ["Each payslip is filed"]
    assert (d["final_action"], d["held"], d["mode"]) == ("create", False, "link")
    assert d["result_ref"] and d["final_ref"] == d["result_ref"] and d["operation_id"]
    made = org.W.dept(d["result_ref"])
    assert made["name"] == "Payroll" and made["parent"] == org.root
    assert made["founding"]["decision"]["final_action"] == "create"
    assert "goal" not in made["founding"]["decision"]["choice"]                      # the long goal is not copied twice


def test_s18_no_ask_rule_means_the_department_is_made_at_once_with_no_stamp(org, monkeypatch):
    assert org.R.birth_ask_applies(org.root) is False
    org.sd.CHOOSER["fn"] = lambda text: reply(**NEW)
    before = list(org.W.asks(org.root))
    d = run(org.sd.decide_and_apply(None, words=TASK))
    assert d["result_ref"] and org.W.asks(org.root) == before


def test_s18_an_ask_rule_holds_the_create_nothing_made_no_ask_raised(org, monkeypatch):
    _ask_rule(org)
    assert org.R.birth_ask_applies(org.root) is True
    calls = _spawns(org, monkeypatch)
    org.sd.CHOOSER["fn"] = lambda text: reply(**NEW)
    n = len(_children(org))
    before = list(org.W.asks(org.root))
    d = run(org.sd.decide_and_apply(None, words=TASK))
    assert (d["final_action"], d["held"], d["held_reason"], d["result_ref"]) == ("create", True, "founder_rule", None)
    assert calls == [] and len(_children(org)) == n and org.W.asks(org.root) == before


def test_a_held_create_says_so_in_the_feed_with_a_plain_title(org):
    import shadow_feed
    _ask_rule(org)
    org.sd.CHOOSER["fn"] = lambda text: reply(**NEW)
    run(org.sd.decide_and_apply(None, words=TASK))
    rows = [json.loads(x) for x in open(shadow_feed._feed_path())]
    assert len(rows) == 1 and rows[0]["kind"] == "info" and "Payroll" in rows[0]["title"] and "yes" in rows[0]["title"]
    assert not shadow_feed.validate(rows[0])


def test_the_owner_approves_a_held_create_and_it_is_made_once(org, monkeypatch):
    _ask_rule(org)
    calls = _spawns(org, monkeypatch)
    org.sd.CHOOSER["fn"] = lambda text: reply(**NEW)
    import mission_engine
    store = mission_engine.MissionStore()
    m = store.create(TASK, mission_engine.default_offer(), target_mode="new")
    held = run(org.sd.decide_and_apply(m))
    assert held["held"] and calls == []
    # the agent is not asked again: the owner said yes to this very choice
    org.sd.CHOOSER["fn"] = lambda text: reply(action="none")
    done = run(org.sd.decide_and_apply(store.load(m["id"]), confirmed=True))
    assert (done["final_action"], done["held"]) == ("create", False) and done["result_ref"]
    assert len(calls) == 1
    got = store.load(m["id"])
    assert got["department_ref"] == done["result_ref"] and got["department_decision"]["held"] is False
    again = run(org.sd.decide_and_apply(store.load(m["id"]), confirmed=True))
    assert again == done and len(calls) == 1                                          # once


def test_the_owner_declines_by_doing_nothing_and_nothing_is_made(org, monkeypatch):
    _ask_rule(org)
    calls = _spawns(org, monkeypatch)
    org.sd.CHOOSER["fn"] = lambda text: reply(**NEW)
    import mission_engine
    store = mission_engine.MissionStore()
    m = store.create(TASK, mission_engine.default_offer(), target_mode="new")
    run(org.sd.decide_and_apply(m))
    run(org.sd.decide_and_apply(store.load(m["id"])))                                 # asked again, no yes: the held decision stands
    assert calls == [] and store.load(m["id"])["department_decision"]["held"] is True


def test_a_use_posts_nothing_and_writes_no_department_file(org):
    ref = org.kids["Billing"]
    snap = {p: p.stat().st_mtime_ns for p in (org.W.ddir(ref)).rglob("*") if p.is_file()}
    n = len(_children(org))
    org.sd.CHOOSER["fn"] = lambda text: reply(action="use", ref=ref, reason="Billing handles invoices")
    d = run(org.sd.decide_and_apply(None, words=TASK))
    assert (d["final_action"], d["final_ref"], d["result_ref"], d["held"]) == ("use", ref, None, False)
    assert snap == {p: p.stat().st_mtime_ns for p in (org.W.ddir(ref)).rglob("*") if p.is_file()}
    assert len(_children(org)) == n


def test_dr5_a_use_of_a_stopped_department_is_held_and_never_started(org):
    import shadow_feed
    ref = org.kids["Billing"]
    d = org.W.dept(ref)
    d["stopped"] = True
    org.W.save_dept(ref, d)
    org.dr.forget()
    org.sd.CHOOSER["fn"] = lambda text: reply(action="use", ref=ref, reason="Billing handles invoices")
    out = run(org.sd.decide_and_apply(None, words=TASK))
    assert (out["final_action"], out["held"], out["held_reason"]) == ("use", True, "stopped")
    assert org.W.dept(ref)["stopped"] is True                                           # still Off: Shadow does not start it
    rows = [json.loads(x) for x in open(shadow_feed._feed_path())]
    assert rows[0]["title"] == "Billing is Off. Use it anyway, or create another?" and rows[0]["department"] == ref


def test_dr4_spawn_finding_the_department_already_there_rewrites_the_record_as_a_use(org, monkeypatch):
    same = dict(NEW, name="Gardening", goal="Something else entirely about taxes and nothing else at all")
    org.sd.CHOOSER["fn"] = lambda text: reply(**same)
    # the covering lets it through (no stopped child hides it); spawn is authoritative and finds the name
    d = run(org.sd.decide(None, words=TASK))
    assert d["final_action"] == "use" and [o["rule"] for o in d["overrides"]] == ["duplicate"]   # DR-4 got there first
    forced = dict(d, final_action="create", final_ref=None, overrides=[], held=False, held_reason=None)
    out = org.sd.apply(forced, words=TASK)
    assert (out["final_action"], out["final_ref"], out["result_ref"]) == ("use", org.kids["Gardening"], None)
    assert [o["rule"] for o in out["overrides"]] == ["duplicate"]


def test_a_spawn_that_refuses_is_none_with_the_reason_and_never_raises(org, monkeypatch):
    def refuse(*a, **k):
        raise ValueError("an incompatible department already has the name Payroll")
    monkeypatch.setattr(org.founding, "spawn", refuse)
    org.sd.CHOOSER["fn"] = lambda text: reply(**NEW)
    d = run(org.sd.decide_and_apply(None, words=TASK))
    assert d["final_action"] == "none" and d["overrides"][-1]["rule"] == "duplicate"


def test_dr6_three_creates_in_the_window_and_the_next_is_none(org):
    # the fixture made two (Billing, Gardening) just now: one more fits, the one after it does not
    org.sd.CHOOSER["fn"] = lambda text: reply(**dict(NEW, name="Dept A", goal="Unrelated work number one zz"))
    assert run(org.sd.decide_and_apply(None, words=TASK))["final_action"] == "create"
    org.sd.CHOOSER["fn"] = lambda text: reply(**dict(NEW, name="Dept B", goal="Different thing altogether qq"))
    d = run(org.sd.decide_and_apply(None, words=TASK))
    assert d["final_action"] == "none" and "rate" in [o["rule"] for o in d["overrides"]]
