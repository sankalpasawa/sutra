"""test_shadow_dept.py -- the create-or-reuse decision (PRD A5.3): the choice parsed as dept.choice, the covering DR-1 to DR-8
(a passing and a failing example each), the decision stored on the task and the offline fallback. The model is stubbed
(shadow_dept.CHOOSER); no test calls one."""
import asyncio
import importlib
import json
import re
from pathlib import Path

import pytest

import layer_schema as S

HERE = Path(__file__).resolve().parent
GOAL = "Answer billing questions and keep the invoices filed for every customer"
TASK = "Reply to the invoice dispute from the customer about last month's billing"


@pytest.fixture
def org(tmp_path, monkeypatch):
    """An organisation with its Root and two departments (Billing, Gardening), the stores in a temporary folder."""
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_SHADOW_HOME", str(tmp_path / "shadow"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    import website_dept as W
    import founding
    import placement_engine as E
    import org2_apply
    import engine_runtime
    import dept_read
    import shadow_dept
    mods = (E, W, org2_apply, founding, engine_runtime, dept_read, shadow_dept)
    before = {m: dict(vars(m)) for m in mods}           # the modules as the suites collected them, put back at the end
    for m in mods:
        importlib.reload(m)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    root = founding.found_structure("Acme", owner="Sankalp")["root"]
    kids = {n: founding.spawn(root, n, "default", g)["ref"]
            for n, g in (("Billing", GOAL), ("Gardening", "Plan the garden beds and the watering for the spring season"))}
    dept_read.forget()
    shadow_dept.CHOOSER["fn"] = None
    yield type("Org", (), {"W": W, "founding": founding, "R": engine_runtime, "dr": dept_read, "sd": shadow_dept,
                           "root": root, "kids": kids})
    shadow_dept.CHOOSER["fn"] = None
    monkeypatch.undo()                                  # the real environment back, every module as it was collected
    for m in mods:
        vars(m).update(before[m])


def run(co):
    # a loop of its own: asyncio.run would leave the thread with no current loop for the tests that call get_event_loop
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(co)
    finally:
        loop.close()


def reply(**kw):
    base = {"action": "none", "reason": "no department fits", "confidence": "medium"}
    base.update(kw)
    return json.dumps(base)


def ctx(o, **kw):
    rows = {r["ref"]: r for r in o.dr.rows(o.root)}
    base = {"root_ref": o.root, "org": True, "children": rows, "kinds": {"default": "any goal", "organic": "its own way"},
            "recent": 0, "fallback": None, "birth_ask": False}
    base.update(kw)
    return base


# ---- the source scan ------------------------------------------------------------------------------------------------
def test_the_three_source_files_hold_none_of_the_forbidden_words():
    for name in ("dept_read.py", "shadow_dept.py", "shadow_dept_prompt.py"):
        text = (HERE / name).read_text(encoding="utf-8")
        assert not re.search(r"\b(web|site|page|blog)s?\b", text, re.I), name


# ---- dept.choice, through parse_choice ------------------------------------------------------------------------------
def test_parse_choice_takes_a_valid_choice_bare_fenced_or_among_words(org):
    c = reply(action="use", ref="dref-x")
    assert org.sd.parse_choice(c)["ref"] == "dref-x"
    assert org.sd.parse_choice("```json\n%s\n```" % c)["action"] == "use"
    assert org.sd.parse_choice("Here you go: %s Thanks." % c)["action"] == "use"


def test_parse_choice_refuses_what_does_not_fit_and_never_raises(org):
    with S.expect_refused("dept.choice") as met:
        assert org.sd.parse_choice(reply(action="use")) is None                          # use needs a ref
        assert org.sd.parse_choice(reply(action="create", kind="default")) is None       # create needs a name and a goal
        assert org.sd.parse_choice(reply(extra=1)) is None                               # closed
    assert len(met.rows) == 3
    assert org.sd.parse_choice("no json at all") is None
    assert org.sd.parse_choice("") is None


def test_parse_choice_drops_a_null_done_items(org):
    assert org.sd.parse_choice(reply(done_items=None)) is not None


# ---- the covering: DR-1 to DR-8 -------------------------------------------------------------------------------------
def _cover(o, choice, **kw):
    return o.sd.cover(choice, ctx(o, **kw))


def _rules(out):
    return [o["rule"] for o in out["overrides"]]


def test_dr1_no_organisation_means_none(org):
    use = {"action": "use", "ref": org.kids["Billing"], "reason": "r", "confidence": "low"}
    assert _cover(org, use)["final_action"] == "use"
    for bad in ({"root_ref": None}, {"org": False}):
        out = _cover(org, use, **bad)
        assert out["final_action"] == "none" and _rules(out) == ["no_org"]


def test_dr2_a_use_that_is_not_a_child_is_none(org):
    ok = {"action": "use", "ref": org.kids["Billing"], "reason": "r", "confidence": "low"}
    assert "not_a_child" not in _rules(_cover(org, ok))
    out = _cover(org, dict(ok, ref="dref-nowhere"))
    assert out["final_action"] == "none" and _rules(out) == ["not_a_child"]


def test_dr3_a_create_needs_a_kind_of_the_library_a_name_and_a_goal(org):
    ok = {"action": "create", "kind": "default", "name": "Payroll", "goal": "Run the payroll each month", "reason": "r",
          "confidence": "low"}
    assert _cover(org, ok)["final_action"] == "create"
    for bad in (dict(ok, kind="root"), dict(ok, kind="unheard-of"), dict(ok, name="  "), dict(ok, goal=" ")):
        out = _cover(org, bad)
        assert out["final_action"] == "none" and _rules(out) == ["bad_kind"]


def test_dr4_a_create_that_repeats_a_running_department_becomes_a_use_of_it(org):
    ok = {"action": "create", "kind": "default", "name": "Payroll", "goal": "Run the payroll each month", "reason": "r",
          "confidence": "low"}
    assert "duplicate" not in _rules(_cover(org, ok))
    same_name = _cover(org, dict(ok, name="billing"))
    assert (same_name["final_action"], same_name["final_ref"], _rules(same_name)) == ("use", org.kids["Billing"], ["duplicate"])
    near = _cover(org, dict(ok, name="Invoices", goal=GOAL))
    assert (near["final_action"], near["final_ref"]) == ("use", org.kids["Billing"])
    # a stopped department is not a duplicate: it is Off, and a new one may be made
    kids = ctx(org)["children"]
    kids[org.kids["Billing"]] = dict(kids[org.kids["Billing"]], stopped=True)
    assert _cover(org, dict(ok, name="Billing"), children=kids)["final_action"] == "create"


def test_dr5_a_use_of_a_stopped_or_blocked_department_is_held_not_silent(org):
    use = {"action": "use", "ref": org.kids["Billing"], "reason": "r", "confidence": "low"}
    assert _cover(org, use)["held"] is False
    for flag, why in (({"stopped": True}, "stopped"), ({"state": "blocked"}, "blocked")):
        kids = ctx(org)["children"]
        kids[org.kids["Billing"]] = dict(kids[org.kids["Billing"]], **flag)
        out = _cover(org, use, children=kids)
        assert (out["final_action"], out["held"], out["held_reason"], _rules(out)) == ("use", True, why, [why])


def test_dr6_more_than_three_creates_in_ten_minutes_is_none(org):
    ok = {"action": "create", "kind": "default", "name": "Payroll", "goal": "Run the payroll each month", "reason": "r",
          "confidence": "low"}
    assert _cover(org, ok, recent=2)["final_action"] == "create"
    out = _cover(org, ok, recent=3)
    assert out["final_action"] == "none" and _rules(out) == ["rate"]


def test_dr6_the_window_comes_from_the_created_stamps_so_a_restart_keeps_it(org):
    rows = org.dr.rows(org.root)
    assert org.sd.recent_creates(rows) == 2                                   # the two made by the fixture, just now
    assert org.sd.recent_creates(rows, now=__import__("time").time() + 3600) == 0


def test_dr7_a_create_under_an_ask_rule_is_held_for_the_owner(org):
    ok = {"action": "create", "kind": "default", "name": "Payroll", "goal": "Run the payroll each month", "reason": "r",
          "confidence": "low"}
    assert _cover(org, ok)["held"] is False
    out = _cover(org, ok, birth_ask=True)
    assert (out["final_action"], out["held"], out["held_reason"], _rules(out)) == ("create", True, "founder_rule", ["founder_rule"])


def test_dr8_an_answer_that_is_not_a_choice_is_none_and_says_so(org):
    none = {"action": "none", "reason": "r", "confidence": "low"}
    assert "bad_output" not in _rules(_cover(org, none))
    out = _cover(org, none, fallback="bad_output")
    assert out["final_action"] == "none" and _rules(out) == ["bad_output"]


# ---- decide, with the model stubbed ---------------------------------------------------------------------------------
def test_an_agent_that_chooses_a_department_is_a_use_decided_by_the_agent(org):
    org.sd.CHOOSER["fn"] = lambda text: reply(action="use", ref=org.kids["Billing"], reason="Billing handles invoices")
    d = run(org.sd.decide({"id": "m-0123456789ab", "objective": TASK}))
    assert (d["final_action"], d["final_ref"], d["decided_by"], d["mode"]) == ("use", org.kids["Billing"], "agent", "link")
    assert d["considered"][0] == org.kids["Billing"] and d["candidates_seen"] == 2
    assert d["mission_id"] == "m-0123456789ab" and d["root_ref"] == org.root
    assert S.validate("dept.decision", d) == []


def test_the_question_carries_the_task_the_cards_the_kinds_and_the_rules(org):
    seen = []
    org.sd.CHOOSER["fn"] = lambda text: (seen.append(text), reply())[1]
    run(org.sd.decide({"id": "m-0123456789ab", "objective": TASK}))
    text = seen[0]
    assert TASK in text and "Billing" in text and org.kids["Gardening"] in text and "default: " in text
    assert "THE OWNER'S RULES" in text


def test_an_async_chooser_is_awaited(org):
    async def chooser(text):
        return reply(action="none")
    org.sd.CHOOSER["fn"] = chooser
    assert run(org.sd.decide(None, words=TASK))["decided_by"] == "agent"


def test_no_agent_is_the_offline_fallback_a_use_only_on_a_name_in_the_words(org):
    d = run(org.sd.decide(None, words="please ask Billing about the refund"))
    assert (d["decided_by"], d["final_action"], d["final_ref"], _rules(d)) == ("stub", "use", org.kids["Billing"], ["offline"])
    d = run(org.sd.decide(None, words="something nobody has a department for"))
    assert (d["decided_by"], d["final_action"], _rules(d)) == ("stub", "none", ["offline"])


def test_a_chooser_that_raises_or_times_out_is_offline(org):
    def boom(text):
        raise RuntimeError("no model")
    org.sd.CHOOSER["fn"] = boom
    assert run(org.sd.decide(None, words=TASK))["decided_by"] == "stub"

    async def slow(text):
        await asyncio.sleep(5)
    org.sd.CHOOSER["fn"] = slow
    org.sd.TIMEOUT_S = 0.05
    try:
        assert run(org.sd.decide(None, words=TASK))["decided_by"] == "stub"
    finally:
        org.sd.TIMEOUT_S = 45


def test_an_invalid_answer_is_bad_output_decided_by_code(org):
    org.sd.CHOOSER["fn"] = lambda text: reply(action="use")
    with S.expect_refused("dept.choice"):
        d = run(org.sd.decide(None, words="tidy the garage and sort the tools"))
    assert (d["decided_by"], d["final_action"], _rules(d)) == ("code", "none", ["bad_output"])


def test_no_root_is_dr1(org):
    org.sd.CHOOSER["fn"] = lambda text: reply(action="use", ref=org.kids["Billing"])
    d = run(org.sd.decide(None, words=TASK, root_ref="no-such-root"))
    assert (d["final_action"], d["root_ref"], _rules(d)) == ("none", None, ["no_org"])


# ---- which Root -------------------------------------------------------------------------------------------------------
def test_the_single_root_is_the_root(org):
    assert org.sd.pick_root() == org.root


def test_with_several_roots_the_shadow_setting_then_the_newest_activity(org, monkeypatch):
    import providers
    second = org.founding.found_structure("Beta", owner="Sankalp")["root"]
    org.founding.spawn(second, "Ledger", "default", "Keep the books for Beta in order every month")
    org.dr.forget()
    assert org.sd.pick_root() == second                                              # the newest activity
    monkeypatch.setattr(providers, "_raw_settings", lambda: {"shadow.dept_root": org.root})
    assert org.sd.pick_root() == org.root


def test_no_root_at_all_picks_none(org, monkeypatch):
    monkeypatch.setattr(org.W, "list_depts", lambda: [])
    assert org.sd.pick_root() is None


# ---- record -----------------------------------------------------------------------------------------------------------
def _task(org):
    import mission_engine
    store = mission_engine.MissionStore()
    return store, store.create(TASK, mission_engine.default_offer(), target_mode="new")


def test_record_stores_the_decision_and_the_ref_on_the_task_and_one_ledger_row(org):
    import shadow_ledger
    store, m = _task(org)
    org.sd.CHOOSER["fn"] = lambda text: reply(action="use", ref=org.kids["Billing"], reason="Billing handles invoices")
    d = run(org.sd.decide_and_apply(m))
    got = store.load(m["id"])
    assert got["department_decision"] == d and got["department_ref"] == org.kids["Billing"]
    rows = [r for r in shadow_ledger.read("actions", 50) if r.get("kind") == "department"]
    assert len(rows) == 1 and rows[0]["final_ref"] == org.kids["Billing"] and rows[0]["mission_id"] == m["id"]


def test_a_task_has_one_decision_asking_again_returns_it(org):
    store, m = _task(org)
    calls = []
    org.sd.CHOOSER["fn"] = lambda text: (calls.append(1), reply())[1]
    first = run(org.sd.decide_and_apply(m))
    again = run(org.sd.decide_and_apply(store.load(m["id"])))
    assert again == first and len(calls) == 1


def test_a_preview_stores_nothing(org):
    store, m = _task(org)
    org.sd.CHOOSER["fn"] = lambda text: reply()
    run(org.sd.decide_and_apply(m, apply_it=False))
    assert "department_decision" not in store.load(m["id"])


def test_record_is_refused_before_anything_is_written_when_the_decision_does_not_fit(org):
    store, m = _task(org)
    org.sd.CHOOSER["fn"] = lambda text: reply()
    d = run(org.sd.decide(m))
    with S.expect_refused("dept.decision"):
        with pytest.raises(S.SchemaFault):
            org.sd.record(dict(d, final_action="use"))                               # use with no ref
    assert "department_decision" not in store.load(m["id"])


# ---- the task chat ----------------------------------------------------------------------------------------------------
def test_the_task_chat_asks_the_question_in_one_turn_and_returns_the_text(org):
    import shadow_task_chat as T
    chat = T.TaskChat("m-0123456789ab")
    seen = []

    async def turn(prompt, timeout, images=None):
        seen.append((prompt, timeout))
        return reply()
    chat._turn = turn
    facts = org.sd.PROMPT.render({"words": TASK, "candidates": org.dr.candidates(org.root, TASK), "kinds": {"default": "x"},
                                  "rules": []})
    assert run(chat.dept_choice(facts)) == reply()
    assert seen[0][0].startswith("Pick the department for this task") and TASK in seen[0][0] and seen[0][1] == 45
