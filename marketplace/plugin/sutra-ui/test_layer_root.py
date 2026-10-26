"""Root behind its interface (PRD amendment A1, package W1-ROOT; M7.1 to M7.4, M0.7 rework, M1.4 pins).

R1  workflow_schema.py: Root's standards in code, run at birth, proposal, registration, grow and write, against the
    workflow fixtures under schemas/layers/fixtures (a good one for each of the four kinds, a bad one for each standard)
R2  Root's check through the schema
R3  birth     R4  the registration record     R5  grow and born templates     R6  root/v1     R7  ownership

A test that meets a fault of the interface on purpose does so inside S.expect_refused(); any other fault fails the test
through the conftest fixture.
"""
import copy
import importlib
import json
from pathlib import Path

import pytest

import layer_schema as S
import workflow_schema as WS

FIXTURES = S.HERE / "schemas" / "layers" / "fixtures"
KINDS = ("website", "default", "organic", "root")
WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"
LINE = ["Plan", "Write", "Check", "Publish"]


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A records home of the test's own, with no model: the Library's definitions and the born templates are its own."""
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


def failed(rows):
    return [r["check"] for r in rows if not r["passed"]]


# ---- R1: workflow_schema.py ---------------------------------------------------------------------------------------------
def test_r1_the_standard_checks_are_exactly_the_interfaces_standards():
    ids = [s[0] for s in S.WORKFLOW_STANDARDS]
    assert set(WS.STANDARD_CHECKS) == set(ids) and len(WS.STANDARD_CHECKS) == len(ids) == 14
    assert all(callable(fn) for fn in WS.STANDARD_CHECKS.values())
    assert WS.SAYS == {s[0]: s[1] for s in S.WORKFLOW_STANDARDS}, "the says texts are exactly the interface's"


@pytest.mark.parametrize("kind", KINDS)
def test_r1_the_good_workflow_of_each_kind_passes_every_stage(home, kind):
    doc = fixture("workflow.%s.good.json" % kind)
    assert S.validate("workflow", doc["workflow"]) == []
    for stage in S.STAGES:
        rows = WS.run(doc["workflow"], stage, doc["dept"], doc["ctx"])
        assert rows and failed(rows) == [], (kind, stage, rows)
        assert [r["check"] for r in rows] == [s[0] for s in S.WORKFLOW_STANDARDS if s[0] in {r["check"] for r in rows}], "in the interface's order"
        for r in S.validate_workflow(doc["workflow"], stage, doc["dept"], doc["ctx"]):
            assert r["passed"], (kind, stage, r)
            assert S.validate("workflow.check", r) == []


@pytest.mark.parametrize("sid", [s[0] for s in S.WORKFLOW_STANDARDS])
def test_r1_each_bad_workflow_fails_exactly_its_standard(home, monkeypatch, sid):
    doc = fixture("workflow.bad.%s.json" % sid)
    assert doc["standard"] == sid
    if doc.get("without_default_template"):
        import artifacts
        monkeypatch.setattr(artifacts, "default_template", lambda: None)
    rows = WS.run(doc["workflow"], doc["stage"], doc["dept"], doc["ctx"])
    assert failed(rows) == [sid], rows
    assert next(r for r in rows if r["check"] == sid)["why"], "a failure says what is wrong"
    again = S.validate_workflow(doc["workflow"], doc["stage"], doc["dept"], doc["ctx"])
    assert sid in failed(again) and set(failed(again)) <= {sid, "workflow_meets_standards"}


def test_r1_a_passing_row_says_the_standards_own_words(home):
    doc = fixture("workflow.website.good.json")
    says = {s[0]: s[1] for s in S.WORKFLOW_STANDARDS}
    for stage in ("birth", "registration", "grow"):
        for r in WS.run(doc["workflow"], stage, doc["dept"], doc["ctx"]):
            assert r["why"] == says[r["check"]], (stage, r)


def test_r1_only_the_standards_whose_source_and_stage_apply_run(home):
    lib, shaped = fixture("workflow.website.good.json"), fixture("workflow.organic.good.json")
    got = lambda doc, stage: [r["check"] for r in WS.run(doc["workflow"], stage, doc["dept"], doc["ctx"])]
    reg_lib, reg_shaped = got(lib, "registration"), got(shaped, "registration")
    assert "engines_known" in reg_lib and "engines_known" not in reg_shaped
    assert "each_engine_named" in reg_shaped and "each_engine_named" not in reg_lib
    assert "names_new" in reg_shaped and "names_new" not in reg_lib
    assert got(lib, "write") == ["names_an_engine", "engines_known", "line_is_registered"]
    assert got(shaped, "write") == ["names_an_engine", "line_is_registered"]
    assert got(lib, "grow") == ["names_an_engine", "engines_known", "names_unique", "reads_known", "one_output", "check_exists"]
    assert "fits_room" in reg_lib and "fits_room" not in got(lib, "proposal") and "items_covered" in got(lib, "proposal")


def test_r1_a_kind_with_no_line_runs_no_standard_at_birth_and_says_so(home):
    d = {"kind": "organic", "done_items": [{"id": "D1", "text": "x"}]}
    wf = S.as_workflow([], "library", d)
    rows = S.validate_workflow(wf, "birth", d)
    assert [r["check"] for r in rows] == ["workflow_meets_standards"] * 2 and all(r["passed"] for r in rows)
    assert rows[1]["why"] == WS.NO_LINE_AT_BIRTH and "no standard applies" in rows[1]["why"]
    assert S.workflow_faults(wf, "birth", d) == []
    # at any other stage, no engine is a failure of the first standard alone
    assert failed(WS.run(wf, "registration", d)) == ["names_an_engine"] and len(WS.run(wf, "registration", d)) == 1


def test_r1_the_root_kind_reads_the_request_and_a_department_kind_may_not_use_setup(home):
    doc = fixture("workflow.root.good.json")
    assert S.first_input("root") == "Request" and S.first_input("website") == "Brief"
    assert failed(WS.run(doc["workflow"], "birth", doc["dept"])) == []
    elsewhere = dict(copy.deepcopy(doc["workflow"]), kind="default")
    rows = WS.run(elsewhere, "registration", dict(doc["dept"], kind="default"))
    assert "names_unique" in failed(rows) and "first_reads_input" in failed(rows), rows
    # the Request is the root kind's first artifact, so a Setup that read the Brief would fail it
    wrong = copy.deepcopy(doc["workflow"])
    wrong["engines"][0]["reads"] = "Brief"
    assert "first_reads_input" in failed(WS.run(wrong, "registration", doc["dept"]))


def test_r1_the_names_a_function_root_or_the_owner_keeps_are_not_engines(home):
    doc = fixture("workflow.organic.good.json")
    for name in ("Identity", "Root", "owner", "Coordination"):
        wf = copy.deepcopy(doc["workflow"])
        wf["engines"][0]["name"] = name
        wf["covers"] = {"D1": [name], "D2": ["Site"]}
        rows = WS.run(wf, "registration", doc["dept"])
        assert "names_unique" in failed(rows), (name, rows)
        assert set(failed(rows)) <= {"names_unique", "names_new"}, "a function's name is also one the Library has"


def test_r1_items_covered_is_a_warning_at_the_proposal_and_a_failure_at_registration(home):
    bad = fixture("workflow.bad.items_covered.json")
    proposal = WS.run(bad["workflow"], "proposal", bad["dept"], bad["ctx"])
    row = next(r for r in proposal if r["check"] == "items_covered")
    assert row["passed"] and row["why"].startswith("warning: ") and "D6" in row["why"]
    assert failed(proposal) == []
    registration = WS.run(bad["workflow"], "registration", bad["dept"], bad["ctx"])
    assert failed(registration) == ["items_covered"] and "D6 is covered by no engine" in registration[-1 if False else [r["check"] for r in registration].index("items_covered")]["why"]


def test_r1_a_workflow_that_names_no_covers_covers_every_item_with_its_last_engine(home):
    d = {"kind": "organic", "done_items": [{"id": "D1", "text": "a"}, {"id": "D2", "text": "b"}, {"id": "D3", "text": "c"}]}
    wf = S.as_workflow([{"name": "Facts", "reads": "Brief", "writes": "Notes"}, {"name": "Site", "reads": "Notes", "writes": "Live site"}], "shaped", d)
    assert wf["covers_by"] == "default" and wf["covers"] == {"D1": ["Site"], "D2": ["Site"], "D3": ["Site"]}
    assert failed(WS.run(wf, "registration", d)) == []
    bare = {k: v for k, v in wf.items() if k not in ("covers", "covers_by")}
    assert failed(WS.run(bare, "registration", d)) == [], "a workflow with no covers key is read as the default"
    # an item whose covering engines are not in the line is not covered
    wf["covers"]["D3"] = ["Elsewhere"]
    assert failed(WS.run(wf, "registration", d)) == ["items_covered"]


def test_r1_size_has_no_hard_cap_but_more_than_six_says_why(home):
    doc = fixture("workflow.bad.size_in_range.json")
    wf = copy.deepcopy(doc["workflow"])
    assert len(wf["engines"]) == 7 and failed(WS.run(wf, "registration", doc["dept"])) == ["size_in_range"]
    wf["why"] = "the goal is seven pieces of work, each filed by one engine"
    assert failed(WS.run(wf, "registration", doc["dept"])) == []
    assert WS.size_in_range({"engines": []}, None, {})[0] is False


def test_r1_a_level_1_engine_keeps_its_library_name_what_it_reads_and_what_it_writes(home):
    d = {"kind": "organic", "done_items": [{"id": "D1", "text": "a"}]}
    def one(**kw):
        wf = S.as_workflow([{"name": "Do"}], "shaped", d)              # reads Brief and writes Result, as the Library has it
        wf["engines"][0].update(dict({"level": 1}, **kw))
        return wf
    assert failed(WS.run(one(), "registration", d)) == []
    assert failed(WS.run(one(reads="Brief", writes="Result"), "registration", d)) == []
    assert failed(WS.run(one(writes="Elsewhere"), "registration", d)) == ["names_new"]
    assert "names_new" in failed(WS.run(one(name="Nobody Has This", reads="Brief", writes="X"), "registration", d))
    assert failed(WS.run(one(level=2), "registration", d)) == ["names_new"], "level 2 is a new engine: the Library has the name"


def test_r1_fits_room_passes_unpriced_and_reads_a_price_when_there_is_one(home):
    doc = fixture("workflow.organic.good.json")
    row = lambda ctx: next(r for r in WS.run(doc["workflow"], "registration", doc["dept"], ctx) if r["check"] == "fits_room")
    assert row({}) == {"check": "fits_room", "passed": True, "why": "not priced here"}
    inside = {"price": {"answer": "counter", "estimate": {"calls": 10, "usd": 1.0}, "room": {"calls": 30, "usd": 6.0}}}
    assert row(inside)["passed"], "a plan inside the room fits, whatever the row once said"
    over = {"price": {"answer": "counter", "estimate": {"calls": 60, "usd": 1.0}, "room": {"calls": 30, "usd": 6.0}}}
    assert not row(over)["passed"] and "30 calls" in row(over)["why"]
    yes = {"price": {"answer": "accept", "estimate": {"calls": 60, "usd": 1.0}, "room": {"calls": 30, "usd": 6.0}}}
    assert row(yes)["passed"], "Priority said yes: it fit when it priced it"


def test_r1_the_line_may_hold_what_an_earlier_registration_named_what_the_owner_added_and_what_was_left_out(home):
    doc = fixture("workflow.website.good.json")
    d = copy.deepcopy(doc["dept"])
    d["workflows"].append({"version": 2, "engines": ["Plan", "Write"], "source": "library", "registered": "2026-10-27T11:00:00Z"})
    ctx = {"line": LINE + ["Do"], "grown": ["Do"]}
    assert failed(WS.run(doc["workflow"], "write", d, ctx)) == []
    assert failed(WS.run(doc["workflow"], "write", d, {"line": LINE + ["Do"], "grown": []})) == ["line_is_registered"]
    assert failed(WS.run(doc["workflow"], "write", d, {"line": LINE + ["Do"], "grown": [], "left_out": ["Do"]})) == []
    assert WS.run(doc["workflow"], "write", d, {})[-1]["why"] == "Coordination has set no line yet"


def test_r1_a_grown_line_is_held_to_the_same_reads_and_writes(home):
    doc = fixture("workflow.website.good.json")
    d, wf = doc["dept"], copy.deepcopy(doc["workflow"])
    wf["source"] = "shaped"                                  # an engine born for the department is not in the Library yet
    wf["engines"].append({"name": "Launch", "reads": "Nothing Files This", "writes": "Launch", "made_by": "shaped"})
    rows = WS.run(wf, "grow", d, doc["ctx"])
    assert failed(rows) == ["reads_known"]
    assert next(r for r in rows if r["check"] == "reads_known")["why"] == "Launch reads Nothing Files This, which nothing before it writes"
    wf["engines"][-1].update({"reads": "Pages", "writes": "Build"})
    assert failed(WS.run(wf, "grow", d, doc["ctx"])) == ["one_output"]
    # a first engine at the grow stage is held to the first artifact by reads_known itself (first_reads_input does not run)
    first = {"source": "shaped", "kind": "organic", "engines": [{"name": "Lone", "reads": "Nothing", "writes": "Lone"}]}
    assert failed(WS.run(first, "grow", {"kind": "organic"})) == ["reads_known"]
    assert failed(WS.run(first, "registration", {"kind": "organic"})) == ["first_reads_input"], "judged once, by the standard that owns it"


# ---- R2: Root's check through the schema -----------------------------------------------------------------------------------
def _born(home, words=WEBSITE, org="Acme Learning"):
    """A department as a person makes one: found the organisation, say the words, Root sets it up, and it settles."""
    W, _, _, founding = home
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def test_r2_roots_checks_are_the_rows_of_the_workflow_schema_at_registration(home):
    W, R, J, _ = home
    ref = _born(home)
    d = W.dept(ref)
    plan = [{"name": n} for n in LINE]
    rows = R._root_checks(ref, d, plan, "library")
    want = S.validate_workflow(S.as_workflow(plan, "library", d), "registration", d, R._root_ctx(ref, plan))
    assert rows == want and rows[0]["check"] == "workflow_meets_standards"
    assert [r["check"] for r in rows[1:]] == [s[0] for s in S.WORKFLOW_STANDARDS if "registration" in s[3] and "library" in s[2]]
    assert all(S.validate("workflow.check", r) == [] for r in rows) and R._root_check(ref, d, plan, "library") == []


def test_r2_a_failed_row_is_a_fault_in_the_words_of_what_is_wrong_and_the_tests_old_wording_is_gone(home):
    W, R, J, _ = home
    ref = _born(home)
    d = W.dept(ref)
    assert R._root_check(ref, d, [{"name": "Plan"}, {"name": "Nobody Knows"}], "library") == [
        "the Library has no engine named Nobody Knows", "the plan leaves out Check, which this kind of department requires"]
    assert not any(hasattr(R, name) for name in ("LINE_CHECKS", "ROOT_HOLDS", "_root_run")), "the old lists are the schema's now"
    # a shaped line is held to its own shape, by the same standards Adaptation's covering reads
    shaped = [{"name": "Facts", "reads": "Notes", "writes": "Notes"}]
    assert R._root_check(ref, d, shaped, "shaped")[0] == "Facts, the first engine, reads Notes, and the first engine reads Brief"
    assert [n for _, n in R._line_notes(shaped)] == R._line_faults(shaped)
    assert [c for c, _ in R._line_notes(shaped)] == ["first_reads_input"]


def test_r2_a_plan_is_priced_by_the_latest_row_for_it_and_a_ruling_above_priority_stands(home):
    W, R, J, _ = home
    ref = _born(home)
    d = W.dept(ref)
    plan = [{"name": n} for n in LINE]
    fits = lambda: next(r for r in R._root_checks(ref, d, plan, "library") if r["check"] == "fits_room")
    assert fits() == {"check": "fits_room", "passed": True, "why": "not priced here"}
    price = {"at": W.now(), "proposal": "line", "thread": "t-1", "engines": LINE, "estimate": {"calls": 60, "usd": 3.0},
             "room": {"calls": 30, "usd": 6.0}, "answer": "counter", "keep": LINE[:3], "why": "room for three today"}
    W.append_row(ref, "prices.jsonl", price)
    assert not fits()["passed"] and "30 calls" in fits()["why"]
    W.append_row(ref, "prices.jsonl", dict(price, engines=["Elsewhere"], answer="accept"))
    assert not fits()["passed"], "a row for another plan is not this plan's price"
    W.append_row(ref, "prices.jsonl", dict(price, answer="accept"))
    assert fits()["passed"] and fits()["why"] == WS.SAYS["fits_room"]
    # Priority said no, and Identity closed the conflict: the ruling stands above the price
    W.append_row(ref, "prices.jsonl", dict(price, answer="reject"))
    assert not fits()["passed"]
    R.post(ref, "Adaptation", "Identity", "inform", {"word": "conflict", "engines": [{"name": n, "reads": "Brief", "writes": n} for n in LINE], "source": "library", "why": "no room", "for": "t-1"})
    assert fits() == {"check": "fits_room", "passed": True, "why": "not priced here"}


def test_r2_the_third_refusal_goes_to_the_options_ask_naming_the_standard_in_its_words(home):
    # the same path as test_j2's, with the words checked to be the standard's own
    W, R, J, _ = home
    ref = _born(home)
    d = W.dept(ref)
    plan = [{"name": "Plan"}, {"name": "Write"}, {"name": "Publish"}]            # no Check, and Publish has no Build to read
    for _ in range(J.REPAIRS + 1):
        R._j2_settle(ref, d, plan, "library", d.get("goal"), "a test")
    card = next(a for a in W.asks(ref) if a["kind"] == "blocked" and a["status"] == "pending")
    for sid in ("reads_known", "required_kept"):
        assert WS.SAYS[sid] in card["text"] and sid not in card["text"]
    assert "Publish reads Build, which nothing before it writes" in card["why"]
    blocked = [e for e in J.events(ref) if e["action"] == "workflow.blocked"]
    assert len(blocked) == J.REPAIRS + 1 and all(r["check"] in {s[0] for s in S.WORKFLOW_STANDARDS} | {"workflow_meets_standards"}
                                                 for e in blocked for r in e["payload"]["checks"])
