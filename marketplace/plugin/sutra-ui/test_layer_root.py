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
    # Priority prices the line while the department is born (W1-PRIORITY, M5.3), so the unpriced start is made here: the
    # journal Priority wrote is taken away, and every assertion below is about the rows this test writes
    (W.ddir(ref) / "prices.jsonl").unlink(missing_ok=True)
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


# ---- R4: the registration record ---------------------------------------------------------------------------------------------
def _model(monkeypatch, R, answers):
    """A model that is a function: a step id maps to what the model says. Every other step falls to its draft."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)

    def model(prompt, step):
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"
    monkeypatch.setattr(R, "MODEL", model)


def test_r4_a_website_registration_validates_names_its_deliverable_and_keeps_the_rows(home):
    W, R, J, _ = home
    ref = _born(home)
    d = W.dept(ref)
    reg = d["workflows"][-1]
    assert S.validate("workflow.registration", reg) == [] and S.validate("department", d) == []
    assert S.deliverable(d) == "Live site" and reg["deliverable"] == "Live site"
    event = next(e for e in J.events(ref) if e["action"] == "workflow.validated")["payload"]["checks"]
    assert reg["checks"] == event and all(S.validate("workflow.check", c) == [] for c in reg["checks"])
    assert reg["engines"] == LINE and reg["left_out"] == [] and "fit" not in reg
    assert reg["covers"] == {i["id"]: ["Publish"] for i in d["done_items"]}, "no engine named its covers: the last one holds them all"


def test_r4_a_shaped_registration_names_the_last_output_as_its_deliverable(home):
    W, R, J, _ = home
    ref = _born(home, ORGANIC, "Lab Co")
    d = W.dept(ref)
    reg = d["workflows"][-1]
    assert S.validate("workflow.registration", reg) == [] and reg["source"] == "shaped"
    assert S.deliverable(d) == "Live site" == reg["deliverable"] and reg["engines"] == ["Facts", "Site"]


def test_r4_what_the_plan_left_out_is_what_coordination_then_holds(home, monkeypatch):
    W, R, J, _ = home
    keep = ["Plan", "Write", "Check"]
    _model(monkeypatch, R, {"priority.bargain": lambda prompt: ({"answer": "counter", "why": "room for three today", "keep": keep}
                                                                if "- Publish:" in prompt else {"answer": "accept", "why": "the envelope has room"})})
    ref = _born(home)
    reg = W.dept(ref)["workflows"][-1]
    assert reg["engines"] == keep and reg["left_out"] == ["Publish"] and S.validate("workflow.registration", reg) == []
    assert [r["engine"] for r in R.coordination(ref)["left_out"]] == reg["left_out"]
    assert S.deliverable(W.dept(ref)) == "Build" == reg["deliverable"], "the last engine kept writes the Build"


def test_r4_the_covers_and_the_fit_a_plan_names_are_kept_with_the_record(home):
    W, R, J, _ = home
    ref = _born(home)
    d = W.dept(ref)
    d["done_items"] = [{"id": "D1", "text": "The pages are written", "how": "model", "level": "outcome"},
                       {"id": "D2", "text": "Every page is checked", "how": "code", "level": "target"}]
    W.save_dept(ref, d)
    d = W.dept(ref)
    plan = [{"name": "Plan", "covers": ["D1"], "fit": "plans the pages for a school's algebra course"},
            {"name": "Write", "covers": ["D1"]}, {"name": "Check", "covers": ["D2"]}, {"name": "Publish", "covers": ["D1", "D2"]}]
    R._j2_settle(ref, d, plan, "library", d.get("goal"), "a test")
    reg = W.dept(ref)["workflows"][-1]
    assert reg["version"] == 2 and S.validate("workflow.registration", reg) == []
    assert reg["covers"] == {"D1": ["Plan", "Write", "Publish"], "D2": ["Check", "Publish"]}
    assert reg["fit"] == {"Plan": "plans the pages for a school's algebra course"}


# ---- R3: birth ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", KINDS)
def test_r3_a_new_department_of_each_kind_carries_six_pins_and_validates(home, kind):
    W = home[0]
    d, _ = W.create("r3-" + kind, "Acme " + kind, None, kind=kind)
    stored = W.dept(d["ref"])
    assert stored["layers"] == S.DEFAULT_PINS and len(stored["layers"]) == 6 and stored["schema_version"] == S.SCHEMA_VERSION
    assert d["layers"] == S.DEFAULT_PINS and S.validate("department", stored) == [] and S.validate("root.pins", stored["layers"]) == []
    wf = S.as_workflow(stored["engines"], "library", stored)
    rows = S.validate_workflow(wf, "birth", stored)
    assert rows and failed(rows) == [], rows
    if kind == "organic":
        assert stored["engines"] == [] and rows[-1]["why"] == WS.NO_LINE_AT_BIRTH, "no line: no standard, and the birth row says so"


def test_r3_each_pin_names_an_implementation_the_registry_can_find(home):
    W = home[0]
    d, _ = W.create("r3-pins", "Acme", None)
    assert {layer: impl.split("/")[0] for layer, impl in W.dept("r3-pins")["layers"].items()} == {layer: layer for layer in S.LAYER_NAMES}


def _stub_kind(W, monkeypatch, line=("Plan", "Publish")):
    """A kind whose line reads an artifact nothing writes: Publish reads the Build that only Check files."""
    monkeypatch.setitem(W.KINDS, "stub", dict(W.KINDS["default"], line=list(line), artifacts=["Brief", "Site plan", "Live site"]))


def test_r3_a_stub_kind_whose_line_reads_what_nothing_writes_is_not_made_and_the_failure_names_the_standard(home, monkeypatch):
    W = home[0]
    _stub_kind(W, monkeypatch)
    with pytest.raises(ValueError) as e:
        W.create("r3-stub", "Stub Co", None, kind="stub")
    assert "reads_known" in str(e.value) and "Publish reads Build, which nothing before it writes" in str(e.value)
    assert WS.SAYS["reads_known"] in str(e.value)
    assert W.dept("r3-stub") is None and not (W.ddir("r3-stub") / "dept.json").exists(), "nothing was written"
    assert W.birth_faults("website") == [] and W.birth_faults("organic") == []
    with pytest.raises(ValueError, match="no department kind named nowhere"):
        W.create("r3-nowhere", "Nowhere", None, kind="nowhere")


def test_r3_setup_checks_the_line_before_founding_and_department_is_made_fails_naming_the_standard(home, monkeypatch):
    W, R, J, founding = home
    _stub_kind(W, monkeypatch)
    root = founding.found_structure("Acme", owner="Sankalp")["root"]
    ctx = {"ref": root, "dept": W.dept(root), "bag": {"setup.shape": {"name": "Stub Co", "kind": "stub", "goal": "A stub of a department", "second": ""},
                                                     "setup.read": {"words": "a stub", "conversation": None, "named": None}}}
    seen, real = [], founding.spawn
    monkeypatch.setattr(founding, "spawn", lambda *a, **k: seen.append(a) or {})
    made = R.setup_make(ctx, None, None)
    assert seen == [], "founding was not asked to make anything"
    verdict = R.c_department_is_made(ctx, None, None, made)
    assert verdict["ok"] is False and "reads_known" in verdict["notes"][0] and "Publish reads Build" in verdict["notes"][0]
    assert not [d for d in W.list_depts() if d.get("parent") == root]
    # a kind that meets the standards is made as before
    monkeypatch.setattr(founding, "spawn", real)
    ctx["bag"]["setup.shape"] = {"name": "Acme Website", "kind": "website", "goal": "A site for Acme", "second": ""}
    made = R.setup_make(ctx, None, None)
    assert made["ref"] and R.c_department_is_made(ctx, None, None, made)["ok"]
    assert W.dept(made["ref"])["layers"] == S.DEFAULT_PINS


def test_r3_a_stub_kind_asked_of_root_makes_no_department_and_the_failed_run_names_the_standard(home, monkeypatch):
    W, R, J, founding = home
    _stub_kind(W, monkeypatch)
    _model(monkeypatch, R, {"setup.converse": {"verdict": "clear", "question": ""},
                            "setup.shape": {"name": "Stub Co", "kind": "stub", "goal": "A stub of a department", "purpose": "a stub",
                                            "second": "", "done_items": []}})
    root = founding.found_structure("Acme", owner="Sankalp")["root"]
    W.owner_ask(root, "Set up a stub department for us")
    W.run_until_idle(root, limit=300)
    assert not [d for d in W.list_depts() if d.get("parent") == root], "no department was made"
    text = json.dumps(R.step_rows(root)) + json.dumps(W.runs(root))
    assert "reads_known" in text and "Publish reads Build, which nothing before it writes" in text, text[-1500:]


# ---- R5: grow and born templates ---------------------------------------------------------------------------------------------
def _born_dept(home, kind="website", ref="r5-dept"):
    W = home[0]
    d, _ = W.create(ref, "Acme", None, kind=kind)
    return ref


def test_r5_an_engine_that_reads_what_nothing_files_is_refused_naming_reads_known_and_nothing_is_born(home):
    W, R, J, _ = home
    ref = _born_dept(home)
    before = W.dept(ref)
    shape = {"name": "Launch", "use_case": "launches the site", "does": "launches the site", "reads": "Nothing Files This", "writes": "Launch"}
    with pytest.raises(ValueError) as e:
        W.add_engine(ref, "Launch", shape=shape)
    assert "reads_known" in str(e.value) and "Launch reads Nothing Files This, which nothing before it writes" in str(e.value)
    assert WS.SAYS["reads_known"] in str(e.value)
    after = W.dept(ref)
    assert after["engines"] == before["engines"] and after["artifacts"] == before["artifacts"] and "Launch" not in after["windows"]
    assert not (R.user_templates_dir() / "launch.json").exists() and "Launch" not in R.defs()["engines"], "nothing was born for it"
    # the same engine reading an artifact the line files is added, after it, and born
    out = W.add_engine(ref, "Launch", shape=dict(shape, reads="Pages"))
    assert out["engines"] == LINE + ["Launch"] and (R.user_templates_dir() / "launch.json").exists()
    assert W.dept(ref)["windows"]["Launch"] == 15 and S.validate("department", W.dept(ref)) == []


def test_r5_an_engine_that_writes_what_is_written_is_refused_naming_one_output(home):
    W, R, J, _ = home
    ref = _born_dept(home)
    with pytest.raises(ValueError, match="one_output"):
        W.add_engine(ref, "Second Pages", shape={"name": "Second Pages", "use_case": "writes pages again", "reads": "Brief", "writes": "Pages"})
    assert W.dept(ref)["engines"] == LINE


def test_r5_a_library_engine_joins_where_it_always_did_and_a_function_or_a_repeat_is_refused_as_before(home):
    W, R, J, _ = home
    ref = _born_dept(home)
    assert W.add_engine(ref, "Do")["engines"] == ["Do"] + LINE, "it reads the Brief, so it goes first"
    assert R.coordination(ref)["line"] == ["Do"] + LINE, "and Coordination's line grows at the same place"
    with pytest.raises(ValueError, match="already runs"):
        W.add_engine(ref, "Do")
    with pytest.raises(ValueError, match="is a function, not an engine of the line"):
        W.add_engine(ref, "Priority")
    with pytest.raises(ValueError, match="the Library has no engine named Nowhere"):
        W.add_engine(ref, "Nowhere")


def test_r5_a_fault_the_line_already_had_does_not_stop_a_new_engine_joining(home):
    W, R, J, _ = home
    ref = _born_dept(home)
    d = W.dept(ref)
    d["engines"] = ["Plan", "Write", "Publish"]            # a legacy line: Publish reads the Build nothing before it writes
    W.save_dept(ref, d)
    assert W.grow_faults(W.dept(ref), "Do", R.defs()["engines"]["Do"]) == []
    assert W.add_engine(ref, "Do")["engines"] == ["Do", "Plan", "Write", "Publish"]


def test_r5_a_plan_root_is_registering_is_not_held_to_the_grow_stage_again(home):
    W, R, J, _ = home
    ref = _born_dept(home)
    d = W.dept(ref)
    d["engines"] = ["Plan", "Write", "Publish"]
    W.save_dept(ref, d)
    out = W.add_engine(ref, "Check", registered=True, before="Publish")      # Check's place in a plan that was held whole
    assert out["engines"] == LINE


def _put_and_stamp_engine(home, ref, name, shape):
    """The faithful J5 flow: Adaptation's offer reaches Identity, who puts it to the owner as an ask; the owner stamps it
    (W.decide_ask) and Identity applies the stamp. Returns the ask's id and the board rows said after the stamp."""
    W, R, _, _ = home
    R.post(ref, "Adaptation", "Identity", "propose", {"word": "engine", "engine": name, "offer": {"shape": shape}, "idea": None,
                                                      "why": "the idea asks for it; Priority has room"})
    W.run_until_idle(ref, limit=200)
    ask = next(a for a in W.asks(ref) if a["kind"] == "engine" and a["engine"] == name and a["status"] == "pending")
    seen = len(R.board(ref))
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=200)
    return ask["id"], R.board(ref)[seen:]


def _said_to_owner(rows):
    return [p["payload"]["done"] for p in rows if p["src"] == "Identity" and "Owner" in p["dst"] and p["msg_type"] == "inform"
            and p["payload"].get("word") == "engine"]


def test_r5_an_engine_the_owner_stamps_and_the_grow_stage_refuses_is_not_added_and_identity_tells_the_owner_why(home):
    W, R, J, _ = home
    ref = _born_dept(home)
    before = W.dept(ref)
    shape = {"name": "Launch", "use_case": "launches the site", "does": "launches the site", "reads": "Nothing Files This", "writes": "Launch"}
    aid, after_stamp = _put_and_stamp_engine(home, ref, "Launch", shape)
    after = W.dept(ref)
    # the line, its artifacts, the windows and the Library are as they were
    assert after["engines"] == before["engines"] and after["artifacts"] == before["artifacts"] and "Launch" not in after["windows"]
    assert not (R.user_templates_dir() / "launch.json").exists() and "Launch" not in R.defs()["engines"]
    # Identity tells the owner, once, in plain words: the standard's own words and what is wrong, never its id
    said = _said_to_owner(after_stamp)
    assert len(said) == 1, said
    assert said[0].startswith("The engine Launch was not added to Acme, and nothing was changed.")
    assert ("would break one: %s (Launch reads Nothing Files This, which nothing before it writes)." % WS.SAYS["reads_known"]) in said[0]
    assert not [sid for sid in WS.STANDARD_CHECKS if sid in said[0]], "no standard's id on the owner's screen"
    assert "Say the idea again, with what it should read" in said[0]
    assert any(t["line"] == said[0] for t in R.chat_view(ref)["turns"]), "and the owner's chat carries it"
    # the ask was stamped, as the owner did, and it does not read as applied: it says it was not, and why
    ask = next(a for a in W.asks(ref) if a["id"] == aid)
    assert ask["status"] == "stamped" and ask["applied"] is False and ask["not_added"] == said[0]
    # the apply step did not fail, and nothing says the engine was added
    runs = [r for r in W.runs(ref) if r["engine"] == "Identity"]
    assert not [r for r in runs if r["status"] == "failed"], runs
    assert not [r for r in runs if "added the engine Launch" in str(r["what"])]
    assert any("did not add the engine Launch" in r["what"] and "reads_known" not in r["what"] for r in runs)


def test_r5_the_same_stamp_adds_an_engine_the_line_can_read_and_says_nothing_of_a_refusal(home):
    W, R, J, _ = home
    ref = _born_dept(home)
    shape = {"name": "Launch", "use_case": "launches the site", "does": "launches the site", "reads": "Pages", "writes": "Launch"}
    aid, after_stamp = _put_and_stamp_engine(home, ref, "Launch", shape)
    assert W.dept(ref)["engines"] == LINE + ["Launch"] and not _said_to_owner(after_stamp)
    ask = next(a for a in W.asks(ref) if a["id"] == aid)
    assert ask["status"] == "stamped" and "applied" not in ask and "not_added" not in ask


def test_r5_an_engine_the_line_already_runs_is_told_to_the_owner_in_the_refusals_own_words(home):
    W, R, J, _ = home
    ref = _born_dept(home)
    aid, after_stamp = _put_and_stamp_engine(home, ref, "Plan", {"name": "Plan", "use_case": "plans", "does": "plans"})
    said = _said_to_owner(after_stamp)
    assert said == ["The engine Plan was not added to Acme, and nothing was changed. Acme already runs Plan."], said
    assert W.dept(ref)["engines"] == LINE
    assert next(a for a in W.asks(ref) if a["id"] == aid)["applied"] is False


RAW = ("None", "$.", "^[", "does not match", "fits none of its shapes", "workflow_meets_standards", "\\")


def _plain_to_owner(words):
    """What the owner reads of a refusal holds no placeholder, no schema path or pattern, and no standard's id."""
    assert not [x for x in RAW if x in words], words
    assert not [sid for sid in WS.STANDARD_CHECKS if sid in words], words


@pytest.mark.parametrize("name", ["Launch #1", "Café", "a/b"])
def test_r5_an_engine_whose_name_is_outside_the_names_rule_is_not_added_and_the_owner_reads_what_is_wrong_in_plain_words(home, name):
    """The row a standard does not name (the workflow's own shape) has no words of a standard: it says what is wrong and no
    more, and it is no standard to count in 'break one'. Found by a verifier: 'break one: None ($.engines[4].name: ...)'."""
    W, R, J, _ = home
    ref = _born_dept(home)
    before = W.dept(ref)
    shape = {"name": name, "use_case": "launches the site", "does": "launches the site", "reads": "Pages", "writes": name}
    aid, after_stamp = _put_and_stamp_engine(home, ref, name, shape)
    after = W.dept(ref)
    assert after["engines"] == before["engines"] and after["artifacts"] == before["artifacts"] and name[:40] not in after["windows"]
    assert not list(R.user_templates_dir().glob("*.json")) and name[:40] not in R.defs()["engines"], "nothing was born"
    said = _said_to_owner(after_stamp)
    assert len(said) == 1, said
    _plain_to_owner(said[0])
    assert said[0].startswith("The engine %s was not added to Acme, and nothing was changed." % name)
    assert "its name may only use letters (without accents), digits, spaces and & ' . -" in said[0], said[0]
    assert "would break" not in said[0], "a name that does not fit is no standard broken, and no count says so: " + said[0]
    assert "Say the idea again, under a name that fits, to have it offered again." in said[0]
    ask = next(a for a in W.asks(ref) if a["id"] == aid)
    assert ask["status"] == "stamped" and ask["applied"] is False and ask["not_added"] == said[0]
    assert any(t["line"] == said[0] for t in R.chat_view(ref)["turns"]), "and the owner's chat carries it"


def test_r5_a_standard_and_a_name_that_does_not_fit_are_told_apart_and_only_the_standard_is_counted(home):
    W, R, J, _ = home
    ref = _born_dept(home)
    shape = {"name": "Launch", "use_case": "launches the site", "does": "launches the site", "reads": "Pages #2", "writes": "Launch"}
    _, after_stamp = _put_and_stamp_engine(home, ref, "Launch", shape)
    said = _said_to_owner(after_stamp)
    assert len(said) == 1, said
    _plain_to_owner(said[0])
    assert ("would break one: %s (Launch reads Pages #2, which nothing before it writes). It also does not meet them: "
            "what it reads may only use letters (without accents)" % WS.SAYS["reads_known"]) in said[0], said[0]
    assert "Say the idea again, with what it should read" in said[0]
    assert W.dept(ref)["engines"] == LINE and "Launch" not in R.defs()["engines"]


def test_r5_grow_broken_says_a_name_that_does_not_fit_once_by_its_engine_and_never_a_fault_the_line_already_had(home):
    W, R, J, _ = home
    ref = _born_dept(home)
    shape = {"name": "Launch #1", "reads": "Pages", "writes": "Launch #1"}
    rows = W.grow_broken(W.dept(ref), "Launch #1", None, shape)
    assert [(c, says) for c, says, _ in rows] == [("workflow_meets_standards", None)], rows
    _plain_to_owner(rows[0][2])
    assert rows[0][2].count("its name") == 1 and rows[0][2].count("what it writes") == 1, "the deliverable is its writes, said once: " + rows[0][2]
    # the message add_engine raises says the same plain words
    with pytest.raises(W.GrowRefused) as e:
        W.add_engine(ref, "Launch #1", shape=dict(shape, use_case="launches"))
    _plain_to_owner(str(e.value))
    # a line's own bad name (a record the department schema refuses to save now, so the department is built, not saved) is
    # not the new engine's fault, wherever the new engine goes; its sentence names the engine, never an index
    legacy = dict(W.dept(ref), engines=["Plan", "Write #9", "Publish"])
    assert [r for r in W.grow_broken(legacy, "Do", R.defs()["engines"]["Do"]) if r[0] == "workflow_meets_standards"] == []
    rows = W.grow_broken(legacy, "Launch #1", None, shape)
    assert rows[0][0] == "workflow_meets_standards" and "the name of Write #9" not in rows[0][2] and "its name" in rows[0][2], rows


def _stamp_line(home, ref, engines):
    """The stamped line, as the owner meets it: Adaptation's line reaches Identity, who puts it as one ask; the owner stamps
    it (W.decide_ask). Returns what Identity said to the owner about the line after the stamp."""
    W, R, _, _ = home
    R.post(ref, "Adaptation", "Identity", "propose", {"word": "line", "engines": engines, "words": "gather the facts, then more", "why": "the goal needs it"})
    W.run_until_idle(ref, limit=200)
    ask = next(a for a in W.asks(ref) if a["kind"] == "line" and a["status"] == "pending")
    seen = len(R.board(ref))
    W.decide_ask(ref, ask["id"], True)
    W.run_until_idle(ref, limit=300)
    return [p["payload"]["done"] for p in R.board(ref)[seen:] if p["src"] == "Identity" and "Owner" in p["dst"] and p["msg_type"] == "inform"
            and p["payload"].get("word") == "line"]


def test_r5_a_stamped_line_whose_engine_breaks_a_standard_tells_the_owner_in_the_standards_words_never_its_id(home):
    """identity_apply's line branch adds each engine through add_engine, so a refusal there reaches the owner in the same
    plain sentence as the stamped engine's: no standard id, no doubled name, no 'the line would break' of the raw message."""
    W, R, J, _ = home
    ref = _born_dept(home)
    said = _stamp_line(home, ref, [{"name": "Facts", "does": "gathers facts", "reads": "Brief", "writes": "Notes"},
                                   {"name": "Site2", "does": "builds a second site", "reads": "Notes", "writes": "Pages"}])
    assert len(said) == 1, said
    _plain_to_owner(said[0])
    assert said[0] == ("Added the line Facts; the first starts on your words now. Not added: Site2 (Root holds every line to its "
                       "standards, and this engine would break one: %s (Site2 writes Pages, which is already written))" % WS.SAYS["one_output"]), said[0]
    assert "Site2 is not added" not in said[0] and "the line would break" not in said[0]
    assert W.dept(ref)["engines"] == ["Facts"] + LINE and "Site2" not in R.defs()["engines"]


def test_r5_a_stamped_line_whose_engine_has_a_name_that_does_not_fit_says_so_in_plain_words(home, monkeypatch):
    """The interface refuses such a line at Adaptation's post in refuse mode, so this is the line branch's own words for
    the form of a name when the post got through (warn mode, or a line asked before): the same plain sentence."""
    monkeypatch.setattr(S, "MODE", "warn")
    W, R, J, _ = home
    ref = _born_dept(home)
    with S.expect_refused("act"):
        said = _stamp_line(home, ref, [{"name": "Facts", "does": "gathers facts", "reads": "Brief", "writes": "Notes"},
                                       {"name": "Site #2", "does": "builds a second site", "reads": "Notes", "writes": "Second"}])
    assert len(said) == 1, said
    _plain_to_owner(said[0])
    assert said[0].startswith("Added the line Facts; the first starts on your words now. Not added: Site #2 (Root holds every line to its standards, "
                              "and this engine does not meet them: its name may only use letters"), said[0]
    assert "would break" not in said[0]
    assert W.dept(ref)["engines"] == ["Facts"] + LINE and "Site #2" not in R.defs()["engines"]


def test_r5_a_stamped_line_in_which_every_engine_is_refused_is_not_told_as_added_and_its_ask_says_it_was_not_applied(home):
    """The line passes the line's own standards (_line_faults reads it against itself) and is refused whole at the grow stage,
    one engine writing what the department already files. Nothing was added, so the owner is not told 'Added the line', the
    line is as it was, and the ask, stamped as the owner made it, is marked not applied with the words on it (as a stamped
    engine's is). Found by a verifier: 'Added the line ; the first starts on your words now.'"""
    W, R, J, _ = home
    ref = _born_dept(home)
    before = W.dept(ref)
    said = _stamp_line(home, ref, [{"name": "Site2", "does": "builds a second site", "reads": "Brief", "writes": "Pages"}])
    assert len(said) == 1, said
    _plain_to_owner(said[0])
    assert "Added the line" not in said[0] and "starts on your words" not in said[0], said[0]
    assert said[0].startswith("The line was not added to Acme, and nothing was changed. Not added: Site2 (Root holds every line to its "
                              "standards, and this engine would break one: %s (" % WS.SAYS["one_output"]), said[0]
    after = W.dept(ref)
    assert after["engines"] == before["engines"] == LINE and after["artifacts"] == before["artifacts"]
    assert "Site2" not in R.defs()["engines"] and not list(R.user_templates_dir().glob("*.json")), "nothing was born"
    ask = next(a for a in W.asks(ref) if a["kind"] == "line")
    assert ask["status"] == "stamped" and ask["applied"] is False and ask["not_added"] == said[0]
    assert any(t["line"] == said[0] for t in R.chat_view(ref)["turns"]), "and the owner's chat carries it"
    runs = [r for r in W.runs(ref) if r["engine"] == "Identity"]
    assert not [r for r in runs if r["status"] == "failed"], runs
    assert not [r for r in runs if "added the line on the owner's stamp" in str(r["what"])], "the run log does not say it was added"
    assert any("did not add the line" in r["what"] for r in runs), runs


def test_r5_a_stamped_line_with_a_fault_of_its_own_is_refused_whole_and_its_ask_says_it_was_not_applied(home, monkeypatch):
    """The line the stamp meets with a fault of its own (a name twice; refuse mode stops it at Adaptation's post, so warn
    mode here) adds nothing, and the ask says so as the line whose engines the department refused does."""
    monkeypatch.setattr(S, "MODE", "warn")
    W, R, J, _ = home
    ref = _born_dept(home)
    with S.expect_refused("act"):
        said = _stamp_line(home, ref, [{"name": "Facts", "does": "gathers facts", "reads": "Brief", "writes": "Notes"},
                                       {"name": "Facts", "does": "gathers more", "reads": "Notes", "writes": "More"}])
    assert len(said) == 1 and said[0].startswith("The line could not be set up: "), said
    _plain_to_owner(said[0])
    assert W.dept(ref)["engines"] == LINE and "Facts" not in R.defs()["engines"]
    ask = next(a for a in W.asks(ref) if a["kind"] == "line")
    assert ask["status"] == "stamped" and ask["applied"] is False and ask["not_added"] == said[0]


def test_r5_a_stamped_line_some_of_whose_engines_are_added_keeps_its_ask_as_applied_and_names_the_rest(home):
    """The half that already held: one engine added, one refused, is an added line with a note of what was not."""
    W, R, J, _ = home
    ref = _born_dept(home)
    said = _stamp_line(home, ref, [{"name": "Facts", "does": "gathers facts", "reads": "Brief", "writes": "Notes"},
                                   {"name": "Site2", "does": "builds a second site", "reads": "Notes", "writes": "Pages"}])
    assert len(said) == 1 and said[0].startswith("Added the line Facts; the first starts on your words now. Not added: Site2"), said
    ask = next(a for a in W.asks(ref) if a["kind"] == "line")
    assert ask["status"] == "stamped" and "applied" not in ask and "not_added" not in ask


def test_r5_the_reasons_count_only_standards_and_a_refusal_that_is_no_standard_keeps_its_own_words(home):
    W, R, J, _ = home
    import engine_runtime
    assert engine_runtime._not_added_reason(ValueError("Acme already runs Plan.")) == "Acme already runs Plan"
    assert engine_runtime._not_added_reason(W.GrowRefused("x", [("one_output", WS.SAYS["one_output"], "Site2 writes Pages, which is already written")])) == (
        "Root holds every line to its standards, and this engine would break one: %s (Site2 writes Pages, which is already written)" % WS.SAYS["one_output"])
    two = [("reads_known", WS.SAYS["reads_known"], "A reads X"), ("one_output", WS.SAYS["one_output"], "B writes Y"),
           ("workflow_meets_standards", None, "its name may only use letters")]
    got = engine_runtime._not_added_reason(W.GrowRefused("x", two))
    assert "would break some:" in got and got.endswith(". It also does not meet them: its name may only use letters"), got


def _org_engine_proposal(home, monkeypatch, shape, ref=None):
    """An org.engine proposal for the department, decided yes through proposals.decide with org2_apply as the applier."""
    import org2_apply
    import proposals
    W, R, J, _ = home
    ref = ref or _born_dept(home)
    monkeypatch.setattr(org2_apply.E, "load_domains", lambda: {ref: {"name": "Acme", "status": "live"}})
    rec = proposals.create("org.engine", {"ref": ref, "engine": shape["name"], "shape": shape}, "Add the engine %s" % shape["name"])
    return ref, proposals.decide(rec["id"], True, apply_fn=org2_apply.apply_request)


def test_r5_the_organisation_sheet_path_reports_the_refusal_through_the_proposal_record(home, monkeypatch):
    """org.engine is the other stamp that adds an engine: its caller is proposals.decide, which records a refused apply as
    failed with the reason, never as approved, and the department is as it was. The reason is what the Organisation sheet's
    Approvals show under the failed proposal, so it is in the owner's words: the standard's own, never its id, with no
    doubled name and none of add_engine's own 'the line would break' (found by a verifier: the raw message reached the sheet)."""
    W, R, J, _ = home
    shape = {"name": "Launch", "use_case": "launches the site", "does": "launches the site", "reads": "Nothing Files This", "writes": "Launch"}
    ref, out = _org_engine_proposal(home, monkeypatch, shape)
    error = out["result"]["error"]
    assert out["status"] == "failed"
    assert error == ("Launch was not added to Acme. Root holds every line to its standards, and this engine would break one: %s "
                     "(Launch reads Nothing Files This, which nothing before it writes)." % WS.SAYS["reads_known"]), error
    _plain_to_owner(error)
    assert "is not added to" not in error and "the line would break" not in error, error
    assert W.dept(ref)["engines"] == LINE and "Launch" not in R.defs()["engines"]


def test_r5_the_organisation_sheet_path_says_a_name_that_does_not_fit_in_plain_words_and_a_repeat_as_it_always_did(home, monkeypatch):
    W, R, J, _ = home
    ref, out = _org_engine_proposal(home, monkeypatch, {"name": "Launch #1", "use_case": "launches", "does": "launches", "reads": "Pages", "writes": "Launch"})
    error = out["result"]["error"]
    assert out["status"] == "failed" and error.startswith("Launch #1 was not added to Acme. Root holds every line to its standards, and this engine does not meet them: its name may only use letters"), error
    _plain_to_owner(error)
    assert "would break" not in error and W.dept(ref)["engines"] == LINE
    ref, out = _org_engine_proposal(home, monkeypatch, {"name": "Plan", "use_case": "plans", "does": "plans"}, ref=ref)
    assert out["status"] == "failed" and out["result"]["error"] == "Acme already runs Plan", out["result"]


def test_r5_a_born_template_is_typed_before_its_file_is_written(home, monkeypatch):
    monkeypatch.setattr(S, "MODE", "warn")      # the first half is warn mode (the old refusal stands); the second half sets refuse itself
    W, R, J, _ = home
    ref = _born_dept(home)
    shape = {"name": "Talks List", "use_case": "lists the school's talks", "does": "lists the talks", "instruction": "List the talks.",
             "needs": ["internet"], "reads": "Brief", "writes": "Talks"}
    p = R.born_template("Talks List", shape, ref)
    assert S.validate("engine.template", json.loads(p.read_text(encoding="utf-8"))) == []
    # no use case: the interface catches it before anything is written, and the old refusal stands
    with S.expect_refused("engine.template") as met:
        with pytest.raises(ValueError, match="names its use case"):
            R.born_template("No Use", {"name": "No Use", "use_case": "", "does": "", "instruction": ""}, ref)
    assert met.rows and "use_case" in "; ".join(met.rows[0]["faults"])
    assert not (R.user_templates_dir() / "no-use.json").exists(), "the file was never written"
    # in refuse mode the write is refused with the fault, and still no file
    import pytest as _p
    with _p.MonkeyPatch.context() as m:
        m.setattr(S, "MODE", "refuse")
        with S.expect_refused("engine.template"):
            with pytest.raises(S.SchemaFault):
                R.born_template("Still No Use", {"name": "Still No Use", "use_case": "", "does": "", "instruction": ""}, ref)
    assert not (R.user_templates_dir() / "still-no-use.json").exists()


def test_r5_a_born_template_that_does_not_fit_is_a_row_when_the_library_is_read_and_still_loads(home):
    W, R, J, _ = home
    ref = _born_dept(home)
    R.born_template("Talks List", {"name": "Talks List", "use_case": "lists the talks", "does": "lists", "instruction": "x"}, ref)
    p = R.user_templates_dir() / "talks-list.json"
    t = json.loads(p.read_text(encoding="utf-8"))
    t["made_by"] = {"by": "Root"}                                  # not Adaptation: the interface says only Adaptation shapes an engine
    p.write_text(json.dumps(t), encoding="utf-8")
    with S.expect_refused("engine.template") as met:
        R._DEFS.clear()
        assert "Talks List" in R.defs()["engines"], "today's refusals stand, and this is not one of them"
        R._DEFS.clear()
        R.defs()
    assert len(met.rows) == 1, "once for the file as it stands"


# ---- R6: root/v1: the setup words, typed ---------------------------------------------------------------------------------------
SNAP = S.HERE / "test_fixtures" / "root-prompts.snapshot.json"


def _conversation(*turns):
    return {"id": "c-fixture", "status": "clear",
            "messages": [{"id": "m-%d" % i, "actor": actor, "text": text, "at": "2026-10-27T10:0%d:00+05:30" % i} for i, (actor, text) in enumerate(turns)]}


def _setup_context(R, words, conversation, named, existing):
    """What setup.read hands the setup prompts, for a fixture, with the Library's own kinds and use cases (library_kinds)."""
    kinds = R.library_kinds()
    return {"ref": "dref-root-fixture", "dept": {"name": "Acme Root", "org": {"name": "Acme"}, "kind": "root"}, "bag": {
        "setup.read": {"words": words, "conversation": conversation, "conversing": isinstance(conversation, dict), "named": named,
                       "facts": {"asked": bool(words), "kinds": ", ".join(kinds), "use_cases": "; ".join("%s: %s" % (k, u) for k, u in kinds.items()),
                                 "existing": existing or "none", "named": named or "none"}}}}


def root_prompts(R):
    """Every setup prompt for the fixtures: a website, an organic department, and two departments asked for in one breath
    with one already made and a name the owner gave."""
    fixtures = {
        "website": _setup_context(R, WEBSITE, _conversation(("user", WEBSITE)), None, ""),
        "organic": _setup_context(R, ORGANIC, _conversation(("user", "A system for the school"), ("root", "Who is it for?"),
                                                            ("user", ORGANIC)), None, "Acme Website"),
        "two departments": _setup_context(R, "Set up a website for the school and a laboratory inventory system for the science team",
                                          _conversation(("user", "Acme Science: a website for the school, and then an inventory system for the lab")),
                                          "Acme Science", "Acme Website, Acme Lab"),
        "no conversation": _setup_context(R, "A site for the school", None, None, ""),
    }
    out = {}
    for name, ctx in fixtures.items():
        out["converse:" + name] = R.p_setup_converse(ctx, None, None)
        out["shape:" + name] = R.p_setup_shape(ctx, None, None)
    return out


def test_r6_the_root_prompts_render_as_the_inline_builders_did(home):
    """The snapshot was written from p_setup_converse and p_setup_shape before their words moved into root/v1; a words
    migration passes it unchanged, and it changes only in a commit of its own ('snapshot: <reason>')."""
    W, R, J, _ = home
    got = root_prompts(R)
    if __import__("os").environ.get("ROOT_PROMPTS_SNAPSHOT") == "write":
        SNAP.write_text(json.dumps(got, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    want = json.loads(SNAP.read_text(encoding="utf-8"))
    assert sorted(got) == sorted(want) and len(want) == 8
    for k in sorted(want):
        assert got[k] == want[k], "%s renders as it did before the move" % k


# ---- R7: ownership -----------------------------------------------------------------------------------------------------------
def test_r7_roots_saves_are_roots_and_change_only_keys_it_owns_or_hand_the_rest_to_their_layer(home, monkeypatch):
    W, R, J, founding = home
    calls, real = [], W.save_dept

    def spy(ref, d, by=None):
        before = W._read(W.ddir(ref) / "dept.json", None) or {}
        calls.append((by, {k for k in d if k not in before or before[k] != d[k]} - {"schema_version"}))
        return real(ref, d, by=by)
    monkeypatch.setattr(W, "save_dept", spy)
    ref = _born(home)
    W.add_engine(ref, "Do")
    root = [keys for by, keys in calls if by == "root"]
    assert root and all(S.owner_of_key(k) in (None, "root") for keys in root for k in keys), "Root's saves change Root's keys only"
    assert {"workflows"} in root, "the registration is saved as Root's"
    assert {"engines", "artifacts"} in root, "so is the engine Root records"
    assert any(by == "root" and "pending_final_tell" in keys for by, keys in calls), "so is the birth tell Setup keeps"
    assert any(by == "root" and "founding" in keys for by, keys in calls), "and the checkpoint that follows it"
    assert ("identity", {"windows"}) in [(by, keys) for by, keys in calls], "the engine's window is Identity's, saved as such"
    births = [by for by, keys in calls if "layers" in keys]
    assert len(births) == 2 and set(births) == {None}, "the organisation's Root and the department are born, handing each layer its first values"


def test_r7_no_ownership_row_is_met_through_a_birth_a_registration_and_a_grown_line(home):
    W, R, J, founding = home
    seen = len(S.REFUSED["rows"])
    ref = _born(home)
    W.add_engine(ref, "Do")
    organic = _born(home, ORGANIC, "Lab Co")
    W.add_engine(organic, "Do")
    rows = S.REFUSED["rows"][seen:]
    assert not [r for r in rows if any("Root wrote" in f or "is Root's" in f for f in r.get("faults") or [])], rows
    assert not rows, "nothing at all was refused"


def test_r6_root_v1_holds_the_setup_words_typed_and_provides_every_setup_step_by_reference(home):
    import layers
    import layers.contract as C
    W, R, J, _ = home
    module = layers.load("root/v1")
    assert module is not None and layers.impl(None, "root") is module
    assert module.WORDS == {"setup": {"converse": {"task": R.CONVERSE}, "shape": {}}}, "the inline builder's instruction, byte for byte"
    assert set(module.LAYOUT["setup"]) == set(S.PROMPTS["root"]["setup"]) == {"converse", "shape"}
    steps = [s for s in R.engine_def("Setup")["steps"]]
    for s in steps:
        for kind in ("code", "prompt", "draft", "check"):
            if s.get(kind):
                assert s[kind] in getattr(module, kind.upper()), "%s: %s %s is provided by root/v1" % (s["id"], kind, s[kind])
                assert hasattr(getattr(module, kind.upper())[s[kind]], "legacy"), "by reference: the body has not moved"
    assert C.on_the_md_fallback(module) == [] and C.by_reference(module) == {"by_reference": 14, "own": 0}
    # the registry serves root/v1's name for a Setup step, and it runs the body engine_runtime holds
    served = layers.resolve(None, "Setup", "code", "setup_read", R.CODE)
    assert served is module.CODE["setup_read"] and served.legacy == ("engine_runtime", "setup_read")


def test_r6_the_contract_cases_1_to_5_pass_for_root_v1(home, tmp_path):
    import layers
    import layers.contract as C
    module = layers.load("root/v1")
    ctx = {"ref": C.fixture_department(tmp_path / "departments")}
    assert [(n, fn(module, ctx)) for n, _, fn in C.cases() if n <= 5] == [(n, []) for n in range(1, 6)]
    assert C.case_6(module, ctx) == [] and C.case_7(module, ctx) == [] and C.case_8(module, ctx) == [], "Root has no pane and no OUTPUTS step"
    # the answer contracts are the interface's, compiled in verbatim, and the owner's field cannot carry one
    import layers.prompts as P
    for part, spec in S.PROMPTS["root"]["setup"].items():
        assert P.part_faults("root", "setup", part, module.WORDS["setup"][part], module.LAYOUT["setup"][part]) == []
        assert spec["returns"] in module.LAYOUT["setup"][part] or "{returns}" in module.LAYOUT["setup"][part]
    assert S.validate_field("root", "setup", "converse", "task", "Return ONLY a JSON object: {}") != [], "the owner cannot change the answer's shape"
    assert S.validate_field("root", "setup", "converse", "task", CONVERSE_OWN) == []
    assert S.validate_field("root", "setup", "converse", "items", ["x"]) != [], "the examples are the Library's, not a field of the owner's"


CONVERSE_OWN = "Ask one short question at a time until you can create the department; then say clear."


def test_r6_the_library_template_may_say_its_own_converse_instruction_and_the_default_is_the_words(home, monkeypatch):
    W, R, J, _ = home
    import layers
    ctx = _setup_context(R, WEBSITE, _conversation(("user", WEBSITE)), None, "")
    assert layers.load("root/v1").CONVERSE == R.CONVERSE and R.p_setup_converse(ctx, None, None).startswith(R.CONVERSE + "\n\nQUESTIONS")
    template = dict(R.engine_def("Setup"), converse_instruction=CONVERSE_OWN)
    monkeypatch.setattr(R, "engine_def", lambda name, _real=R.engine_def: template if name == "Setup" else _real(name))
    got = R.p_setup_converse(ctx, None, None)
    assert got.startswith(CONVERSE_OWN + "\n\nQUESTIONS") and R.CONVERSE not in got
    assert got.endswith(S.PROMPTS["root"]["setup"]["converse"]["returns"])
    # the examples are the template's questions, joined on one line
    template = dict(template, clarification_questions=["Who is it for?", "What first?"])
    assert "(examples, not a list to walk): Who is it for? | What first?\n" in R.p_setup_converse(ctx, None, None)


def test_r6_a_marker_the_code_gives_no_value_is_an_error_never_a_blank(home):
    import layers
    with pytest.raises(ValueError, match="no \\{\\{existing\\}\\}|fills no|existing"):
        layers.prompt(None, "root", "setup", "shape", org="Acme", words="w", named="none", kinds="website", use_cases="u")


def test_r6_standards_are_the_interfaces_ids_and_words_for_the_screen_to_list(home):
    import layers
    got = layers.call(None, "root", "standards")
    assert [r["id"] for r in got] == [s[0] for s in S.WORKFLOW_STANDARDS] and [r["says"] for r in got] == [s[1] for s in S.WORKFLOW_STANDARDS]
    assert all(set(r) == {"id", "says", "sources", "stages"} and set(r["stages"]) <= set(S.STAGES) for r in got)
    assert json.loads(json.dumps(got)) == got, "it goes out as JSON"


def _snapshot(W, *refs):
    """Everything a department keeps in its folder, as bytes by file name: what 'changes nothing else' is measured on."""
    out = {}
    for ref in refs:
        for p in sorted(W.ddir(ref).rglob("*")):
            if p.is_file():
                out[(ref, str(p.relative_to(W.ddir(ref))))] = p.read_bytes()
    return out


def test_r6_a_root_setup_option_posts_one_request_on_the_root_department_and_changes_nothing_else(home):
    import layers
    W, R, J, _ = home
    ref = _born(home)
    root = W.dept(ref)["root"]
    ask = W.options_ask("blocked", "An engine the kind requires cannot serve D2.", [
        W.option("root_setup", "Set the department up again, done its own way", "Root sets it up again from your words"),
        W.option("stop", "Stop here", "the department stops where it is")], title="The plan could not be shaped.", who="Adaptation", why="D2")
    option = dict(ask["options"][0], params={"words": "A site that teaches algebra to Class 8 students."})
    assert S.validate("option.words", option["params"]) == [] and S.OPTION_KINDS["root_setup"]["layer"] == "root"
    before, requests = _snapshot(W, ref), [p for p in R.board(root) if p["src"] == "Owner" and p["msg_type"] == "request"]
    out = layers.call(ref, "root", "apply_option", ref, ask, option)
    after = _snapshot(W, ref)
    assert after == before, "nothing of the department changes: its record, its asks, its board, its runs"
    posted = [p for p in R.board(root) if p["src"] == "Owner" and p["msg_type"] == "request"]
    assert len(posted) == len(requests) + 1 and posted[-1]["dst"] == ["Identity"]
    assert posted[-1]["payload"]["words"] == out["text"] == "A site that teaches algebra to Class 8 students, done its own way"
    assert posted[-1]["payload"]["about"] == {"dept": ref, "name": W.dept(ref)["name"]} and posted[-1]["payload"]["word"] == "front"
    assert [r["text"] for r in W.requests(root)][-1] == out["text"] and out["root"] == root
    # the words may come from the card the owner answered; without any, nothing is posted
    kept = len(R.board(root))
    out = layers.call(ref, "root", "apply_option", ref, dict(ask, chosen={"id": "root_setup", "words": "Another way"}), {"id": "root_setup"})
    assert out["text"] == "Another way, done its own way"
    with pytest.raises(ValueError, match="say what the department is for"):
        layers.call(ref, "root", "apply_option", ref, ask, {"id": "root_setup"})
    assert len(R.board(root)) == kept + 1
    with pytest.raises(ValueError, match="no department"):
        layers.call("dref-nowhere", "root", "apply_option", "dref-nowhere", ask, option)
