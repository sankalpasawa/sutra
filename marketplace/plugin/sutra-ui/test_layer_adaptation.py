"""Adaptation behind its interface (PRD amendment A1: W1-ADAPT, M5.7, M5.1, M6.3 to M6.5), one section per step.

  A1  adaptation/v1 provides every name its recipe uses, by reference, and passes the contract
  A6  Adaptation starts on the department's deliverable
  A7  the practices in place ride on the line request (J2_ADAPT_MAKE)
  A8  a shape with a confidence: J2B-4 in the covering, J2B-7 in the offer
  A9  organic and default kinds end to end, with stubbed models

The departments here are born the way a person makes them (found, say the words, Root sets up), on a records home of
their own, with no model but the ones a test installs; a test that meets a fault of the interface fails through
conftest.py, so a deliberate one is wrapped in S.expect_refused().
"""
import importlib
import json
import re

import pytest

import layer_schema as S
import layers
import layers.contract as C

WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"
LINE = ["Plan", "Write", "Check", "Publish"]


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


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    return {"ref": C.fixture_department(tmp_path / "departments")}


def v1():
    return importlib.import_module("layers.adaptation.v1")


# ---- A1 · adaptation/v1 by reference ----------------------------------------------------------------------------------
def test_a1_the_module_provides_every_name_its_recipe_uses():
    module = v1()
    used = {"code": set(), "prompt": set(), "draft": set(), "check": set()}
    for s in C._steps(C.recipe_of(module)):
        for kind in used:
            if s.get(kind):
                used[kind].add(s[kind])
    assert {k: len(v) for k, v in used.items()} == {"code": 15, "prompt": 2, "draft": 2, "check": 6}
    for kind, names in used.items():
        assert names <= set(getattr(module, kind.upper())), "%s names the recipe uses that the module leaves to the legacy registry" % kind


@pytest.mark.parametrize("case", [c for c in C.cases() if c[0] in (1, 2, 3, 4, 7)], ids=lambda c: "case %d" % c[0])
def test_a1_the_contract_cases_pass_for_adaptation_v1(case, home):
    _, what, fn = case
    assert fn(v1(), home) == [], what


def test_a1_what_it_holds_by_reference_is_counted_for_the_hand_in(capsys):
    counts = C.by_reference(v1())
    print("adaptation/v1: %(by_reference)d by reference, %(own)d own" % counts)
    assert counts["by_reference"] + counts["own"] == 25


# ---- A2 · Adaptation's words (M2.5) -----------------------------------------------------------------------------------
def test_a2_every_part_of_adaptations_interface_is_served_from_its_words_and_none_is_on_the_fallback(home):
    import layers.prompts as P
    for group, parts in S.PROMPTS["adaptation"].items():
        for part in parts:
            assert P._module(home["ref"], "adaptation", group, part) is v1(), "%s.%s is read from the .md bundle" % (group, part)
    assert C.on_the_md_fallback(v1()) == []
    assert P.faults() == [] and sorted(v1().WORDS) == sorted(v1().LAYOUT) == ["decide", "goal", "make", "sense"]


@pytest.mark.parametrize("case", C.cases(), ids=lambda c: "case %d" % c[0])
def test_a2_the_whole_contract_passes_for_adaptation_v1_with_no_part_on_the_fallback(case, home):
    _, what, fn = case
    assert fn(v1(), home) == [], what


def test_a2_each_part_compiles_to_the_md_part_it_came_from_byte_for_byte(home):
    import layers.prompts as P
    seen = 0
    for group, parts in S.PROMPTS["adaptation"].items():
        for part, spec in parts.items():
            if ("adaptation", group, part) in S.ADDED_PARTS:
                continue
            sample = {n: "<<%s>>" % n for n in spec["inputs"]}
            got = P.prompt(home["ref"], "adaptation", group, part, **sample)
            assert got == P.SLOT.sub(lambda m: sample[m.group(1)], P.md_part("adaptation", group, part)), "%s.%s" % (group, part)
            seen += 1
    assert seen == 6


def test_a2_the_goal_card_is_read_from_the_typed_words(home):
    R = importlib.import_module("engine_runtime")
    does, skills = R._goal_of(home["ref"], "Adaptation")
    assert does == v1().WORDS["goal"]["does"]["text"] == "reads the department's own rows and proposes one rung up, or steps one down"
    assert skills == v1().WORDS["goal"]["skills"]["items"] and len(skills) == 4


def test_a2_the_note_no_run_reads_is_still_a_note_and_the_owners_change_is_a_typed_field(home):
    import layers.prompts as P
    assert S.PROMPTS["adaptation"]["decide"]["note"]["read_by"] is None
    assert P.words(home["ref"], "adaptation", "decide", "note")["text"].startswith("In this version the choice is made by code")
    assert S.validate_field("adaptation", "decide", "note", "text", "Prefer the smaller change.") == []
    assert S.validate_field("adaptation", "decide", "note", "text", "Return ONLY {}") != [], "the answer's shape is the app's"
    assert S.validate_field("adaptation", "goal", "does", "text", "uses {{dept}}") != [], "a marker is the app's"


# ---- A6 · Adaptation starts on the deliverable (M8.2, its part) ---------------------------------------------------------
def _ready(j2, ref):
    """Adaptation asked whether its version trigger is live, the way next_due asks every engine: (input, slot) or None."""
    W, R, _, _, _ = j2
    ctx = R._coord_ctx(ref, W.dept(ref))
    ctx["peek"] = True
    got = R.ready(ctx, "Adaptation", ("version",))
    return (got[0], got[1]) if got and got[1] else None


def _file(j2, ref, art, ok=True):
    """A version of an artifact filed with the verdict given, past the Library's own check of what it holds."""
    W = j2[0]
    return W.VERS.add(W._abase(ref, art), {"file.md": "text of " + art}, [], "Do", {"ok": ok, "notes": []}, W.now(), lock=W._lock(ref))


def _slot(j2, art, v):
    return j2[0]._slot_id("Adaptation", art, v)


def test_a6_the_recipe_starts_adaptation_on_a_post_and_on_a_checked_version_of_the_deliverable():
    start = layers.recipes()["Adaptation"]["start"]
    assert start["on"] == [{"kind": "post"}, {"kind": "version", "of": "$deliverable", "checked": True}] and start["unless"] == []
    assert layers.recipes()["Adaptation"]["reads"] == "Live site", "only the start key changed"


def test_a6_a_website_departments_adaptation_starts_where_it_always_did_on_a_checked_live_site(j2):
    W, R, _, _, _ = j2
    W.create("dref-site", "Site Dept", None, kind="website")
    assert _ready(j2, "dref-site") is None, "no Live site yet: nothing starts it"
    _file(j2, "dref-site", "Live site", ok=False)
    assert _ready(j2, "dref-site") is None, "a version that failed its check is not one that passed"
    _file(j2, "dref-site", "Live site")
    inp, slot = _ready(j2, "dref-site")
    assert slot == _slot(j2, "Live site", 2) and inp["v"] == 2, "the same slot as when the trigger named Live site"
    assert R.slot_of("dref-site", "Adaptation")["on"] == "after Live site v2" and R.slot_of("dref-site", "Adaptation")["of"] == "Live site"
    assert R.start_view(R.engine_def("Adaptation"), W.dept("dref-site"))["on"] == ["a post addressed to it", "a new Live site that passed its check"]


def test_a6_a_default_departments_adaptation_starts_on_result(j2):
    W, R, _, _, _ = j2
    W.create("dref-plain", "Plain Dept", None, kind="default")
    assert _ready(j2, "dref-plain") is None
    _file(j2, "dref-plain", "Live site")                          # not what a default department's work leads to
    assert _ready(j2, "dref-plain") is None
    _file(j2, "dref-plain", "Result")
    inp, slot = _ready(j2, "dref-plain")
    assert slot == _slot(j2, "Result", 1) and inp["v"] == 1 and inp["art"] == "Result"
    assert R.slot_of("dref-plain", "Adaptation") == {"on": "after Result v1", "of": "Result", "checked": True, "v": 1}
    assert R.start_view(R.engine_def("Adaptation"), W.dept("dref-plain"))["on"][-1] == "a new Result that passed its check"
    assert "$" not in " ".join(R.steps_view("dref-plain", "Adaptation")["start"]["on"]), "the screen never shows the token"


def test_a6_a_registered_plans_last_output_is_what_adaptation_starts_on_and_a_department_with_none_waits(j2):
    W, R, _, _, _ = j2
    W.create("dref-lab", "Lab Dept", None, kind="organic")
    _file(j2, "dref-lab", "Live site")
    assert _ready(j2, "dref-lab") is None, "an organic department has no deliverable before its plan is registered"
    assert [t["of"] for t in R.engine_def("Adaptation")["start"]["on"] if t["kind"] == "version"] == ["$deliverable"]
    assert R.start_view(R.engine_def("Adaptation"), W.dept("dref-lab"))["on"][-1] == "a new deliverable that passed its check"
    d = W.dept("dref-lab")
    d["engines"] = ["Do"]
    d["workflows"] = [{"version": 1, "engines": ["Do"], "source": "library", "registered": W.now()}]
    W.save_dept("dref-lab", d)
    _file(j2, "dref-lab", "Result")
    assert _ready(j2, "dref-lab")[1] == _slot(j2, "Result", 1), "Do writes Result, so its department's deliverable is Result"


def test_a6_the_website_scenarios_run_adaptation_on_the_same_slots(j2):
    W, R, J, founding, _ = j2
    root = founding.found_structure("Acme Learning", owner="Sankalp")["root"]
    W.owner_ask(root, WEBSITE)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "publish"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)
    slots = [r["slot"] for r in W.runs(ref) if r.get("engine") == "Adaptation" and str(r.get("slot")).startswith("Adaptation@live-site.")]
    assert slots == [_slot(j2, "Live site", 1)], slots
    assert J.status(ref)["step"] >= 7


def test_a6_a_default_department_that_reached_its_result_has_adaptation_run_on_it(j2, monkeypatch):
    """End to end: a department no template fits makes its line, its last engine files Result, and Adaptation, which used to
    wait for a Live site no default department has, now starts on the Result that passed."""
    W, R, J, _, _ = j2
    ref, _ = _run_scenario(j2, monkeypatch, "default", DOC_WORDS, "Safety Co", DOC, DOC_PLAN)
    assert W.latest(ref, "Result", passed=True), "the plan's last engine filed a Result that passed its check"
    ran = [r for r in W.runs(ref) if r.get("engine") == "Adaptation" and r.get("slot") == _slot(j2, "Result", 1)]
    assert ran and ran[-1]["status"] == "ok", [(r.get("slot"), r.get("status")) for r in W.runs(ref) if r.get("engine") == "Adaptation"]
    steps = [r for r in R.step_rows(ref) if r.get("slot") == _slot(j2, "Result", 1) and "read" in r]
    assert steps and all(r["read"] == [{"art": "Result", "v": 1}] for r in steps), "its rows name the Result that started it, not the Live site its recipe reads"


# ---- A7 · the practices in place (M6.3) -------------------------------------------------------------------------------
FIVE ={"rules", "engines", "artifacts", "required", "taken"}


def _source(j2, kind, payload=None, name="Practice Dept", ref="dref-practices"):
    """adapt_source as the recipe runs it: a department of `kind` and the request Identity posted to Adaptation."""
    W, R, _, _, _ = j2
    W.create(ref, name, None, kind=kind)
    d = W.dept(ref)
    post = {"n": 1, "thread": "x-practices", "src": "Identity", "msg_type": "request",
            "payload": dict({"word": "line", "words": "A guide to the night clinic"}, **(payload or {}))}
    ctx = {"ref": ref, "dept": d, "engine": "Adaptation", "def": R.engine_def("Adaptation"), "post": post, "bag": {}}
    _, step = R.step_def("adapt.source")
    return v1().CODE["adapt_source"](ctx, step, None), ctx


def test_a7_a_shaped_source_carries_exactly_the_five_practices_when_make_is_on(j2, monkeypatch):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    out, ctx = _source(j2, "organic")
    assert out["shape"] is True and out["source"] == "shaped"
    assert set(out["practices"]) == FIVE
    assert ctx["post"]["payload"]["practices"] == out["practices"], "the request as Adaptation holds it carries them"
    assert S.validate("act.line_request", ctx["post"]["payload"]) == []
    p = out["practices"]
    assert [r["tag"] for r in p["rules"]] == ["go", "ask"] and all(r["line"] for r in p["rules"])
    assert [e["name"] for e in p["engines"]] == ["Check", "Do", "Plan", "Publish", "Write"], "the shipped work engines, Setup left out"
    assert all(set(e) == {"name", "use_case", "reads", "writes"} for e in p["engines"])
    assert [a["name"] for a in p["artifacts"]] == ["Brief", "Site plan", "Pages", "Build", "Live site", "Result"]
    assert p["required"] == [] and "Do" in p["taken"] and "Identity" in p["taken"]


def test_a7_a_website_reshape_names_check_as_required_with_what_it_refuses(j2, monkeypatch):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    # Root's check sent a website line back: with the make setting on it is shaped, and Check is told to Make
    out, _ = _source(j2, "website", {"faults": ["the plan leaves out D2"]})
    assert out["shape"] is True
    required = out["practices"]["required"]
    assert [r["name"] for r in required] == ["Check"]
    assert "a page with a script" in required[0]["refuses"] and "a link to no page" in required[0]["refuses"]


def test_a7_the_practices_hold_no_done_line_no_other_workflow_and_no_file_text(j2, monkeypatch):
    W, R, _, _, _ = j2
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    # another department's born engine and a version with text in it: neither may reach the practices
    other, _ = W.create("dref-other", "Other Dept", "Track the zebra herd", kind="organic")
    R.born_template("Zebra Count", {"name": "Zebra Count", "use_case": "counts the zebras", "does": "counts the zebras",
                                    "instruction": "Track the zebra herd", "reads": "Brief", "writes": "Zebra Count"}, "dref-other")
    W.add_version("dref-other", "Brief", {"brief.md": "SECRET-FILE-TEXT about the zebra herd"}, [], "owner", {"ok": True, "notes": []})
    R._DEFS.clear()
    out, ctx = _source(j2, "organic", name="Lab Dept")
    blob = json.dumps(out["practices"])
    assert W.dept("dref-practices")["done"] not in blob, "the kind's done line is not read"
    assert "SECRET-FILE-TEXT" not in blob and "Track the zebra herd" not in blob
    assert "Zebra Count" not in [e["name"] for e in out["practices"]["engines"]], "a born engine is never taken"
    assert "Zebra Count" in out["practices"]["taken"], "its name is taken, and that is all that is said of it"
    assert "workflows" not in out["practices"]


def test_a7_nothing_changes_with_the_setting_off_or_for_a_library_line(j2, monkeypatch):
    out, ctx = _source(j2, "organic")                       # off: the shaped source carries no practices
    assert out["shape"] is True and "practices" not in out and "practices" not in ctx["post"]["payload"]
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    out, ctx = _source(j2, "website", name="Site Dept", ref="dref-lib")   # on, but the Library has a line: nothing to make
    assert out["shape"] is False and out["source"] == "library" and "practices" not in out
    assert [e["name"] for e in out["engines"]] == LINE


def test_a7_with_make_on_a_default_departments_first_line_is_made_and_a_registered_one_is_taken(j2, monkeypatch):
    out, _ = _source(j2, "default", name="Plain Dept", ref="dref-plain")
    assert out["shape"] is False and [e["name"] for e in out["engines"]] == ["Do"], "off: the fallback Do, as today"
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    out, _ = _source(j2, "default", name="Plain Two", ref="dref-plain2")
    assert out["shape"] is True and out["source"] == "shaped" and set(out["practices"]) == FIVE
    W = j2[0]
    d = W.dept("dref-plain2")
    d["workflows"] = [{"version": 1, "engines": ["Do"], "source": "library", "registered": W.now()}]
    W.save_dept("dref-plain2", d)
    again, _ = _source_of(j2, "dref-plain2")
    assert again["shape"] is False, "a department with a registered line is not made afresh by its next request"


def _source_of(j2, ref):
    W, R, _, _, _ = j2
    ctx = {"ref": ref, "dept": W.dept(ref), "engine": "Adaptation", "def": R.engine_def("Adaptation"), "bag": {},
           "post": {"n": 1, "thread": "x", "src": "Identity", "msg_type": "request", "payload": {"word": "line", "words": "more"}}}
    _, step = R.step_def("adapt.source")
    return v1().CODE["adapt_source"](ctx, step, None), ctx


def _stub(monkeypatch, R, answers):
    """A model that is a function (test_j2's): a step id maps to what the model says, a dict or a callable taking the prompt;
    every other step falls to its draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    seen = []

    def model(prompt, step):
        if step["id"] not in answers:
            return None, 0.0, "offline"
        seen.append((step["id"], prompt))
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"
    monkeypatch.setattr(R, "MODEL", model)
    return seen


# ---- A4 · the proposal stage ------------------------------------------------------------------------------------------
GOOD = [{"name": "Facts 2", "does": "finds what the goal names, each fact with its source", "reads": "Brief", "writes": "Facts 2", "internet": True},
        {"name": "Site 2", "does": "writes the pages from the facts", "reads": "Facts 2", "writes": "Live site", "internet": False}]


def _line_ctx(j2, source="shaped"):
    W, R, _, _, _ = j2
    W.create("dref-line", "Line Dept", None, kind="organic")
    return {"ref": "dref-line", "dept": W.dept("dref-line"), "bag": {"adapt.source": {"shape": True, "source": source}}}


def test_a4_a_sound_line_says_what_it_always_said_and_the_legacy_check_agrees(j2):
    R = j2[1]
    ctx = _line_ctx(j2)
    for out in ({"engines": GOOD}, {"engines": [dict(GOOD[0], name="Plan")] + GOOD[1:]}, {"engines": []}, {"engines": "none"},
                {"engines": [GOOD[0], dict(GOOD[1], reads="Brief", writes="Facts 2")]}):
        mine, theirs = v1().CHECK["line_is_engines"](ctx, None, None, out), R.c_line_is_engines(ctx, None, None, out)
        assert mine["ok"] == theirs["ok"], out
        # today's wording, each fault now naming the standard it breaks when Root has one for it
        assert [re.sub(r"^[a-z_]+: ", "", n) for n in mine["notes"]] == theirs["notes"], out
    assert v1().CHECK["line_is_engines"](ctx, None, None, {"engines": GOOD}) == \
        {"ok": True, "notes": ["2 engines, each reading what one before it wrote"]}


def test_a4_a_failed_standard_row_fails_the_line_naming_it_and_a_warning_row_passes(j2):
    ctx = _line_ctx(j2)
    got = v1().CHECK["line_is_engines"](ctx, None, None, {"engines": [GOOD[0], dict(GOOD[1], reads="Interviews")]})
    assert got["ok"] is False
    assert got["notes"] == ["reads_known: Site 2 reads Interviews, which nothing before it writes"], "today's wording, naming the standard"
    taken = v1().CHECK["line_is_engines"](ctx, None, None, {"engines": [dict(GOOD[0], name="Plan")] + GOOD[1:]})
    assert taken["notes"] == ["names_new: the Library already has an engine named Plan"]
    # items_covered at the proposal stage is a warning: the line passes, and the notes name no such standard
    d = j2[0].dept(_dept(j2, "organic", ref="dref-three"))
    wf = v1().workflow_of(v1().norm_engines(GOOD), "shaped", d)
    wf["covers"], wf["covers_by"] = {"D1": ["Site 2"]}, "adaptation"
    rows = S.validate_workflow(wf, "proposal", d, {})
    assert next(r for r in rows if r["check"] == "items_covered") == {"check": "items_covered", "passed": True,
                                                                       "why": "warning: D2 is covered by no engine of the plan; D3 is covered by no engine of the plan"}
    assert v1().CHECK["line_is_engines"](ctx, None, None, {"engines": GOOD})["ok"] is True


def test_a4_the_workflow_it_judges_validates_and_carries_what_a_made_engine_adds(j2):
    ctx = _line_ctx(j2)
    engines = [dict(GOOD[0], level=2, confidence=0.9, covers=["D1"]), dict(GOOD[1], level=2, confidence=0.7, doubt="how often?", covers=["D1"])]
    wf = v1().workflow_of(engines, "shaped", ctx["dept"])
    assert S.validate("workflow", wf) == []
    assert [(e["level"], e["confidence"]) for e in wf["engines"]] == [(2, 0.9), (2, 0.7)] and wf["engines"][1]["doubt"] == "how often?"
    assert wf["deliverable"] == "Live site" and set(wf["covers"]) == {"D1"} and wf["covers_by"] == "adaptation"


def test_a4_a_name_or_a_text_that_does_not_fit_the_schema_is_cut_to_fit_before_it_is_judged(j2):
    ctx = _line_ctx(j2)
    long = dict(GOOD[0], name="Facts about the night clinic and all of its rooms and doors", does="x" * 500)
    row = v1().norm_engines([long])[0]
    assert len(row["name"]) == 40 and len(row["does"]) == 200
    got = v1().CHECK["line_is_engines"](ctx, None, None, {"engines": [long, dict(GOOD[1], reads=row["writes"])]})
    assert got["ok"] is True, got


def test_a4_a_shaped_line_whose_second_engine_reads_nothing_filed_fails_naming_reads_known_and_is_shaped_again(j2, monkeypatch):
    """The step fails through the covering, and the existing reshape path runs: the reasons go back to Adaptation, which
    shapes the line again, and the second line registers."""
    W, R, J, founding, FV = j2
    asked = []
    bad = {"engines": [GOOD[0], dict(GOOD[1], reads="Interviews")]}
    lines = iter([bad, {"engines": GOOD}])

    def line(prompt):
        asked.append(prompt)
        return next(lines)
    _stub(monkeypatch, R, {"adapt.line": line, "priority.bargain": {"answer": "accept", "why": "the envelope has room"}})
    root = founding.found_structure("Lab Co", owner="Sankalp")["root"]
    W.owner_ask(root, ORGANIC)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    events = J.events(ref)
    blocked = next(e for e in events if e["action"] == "workflow.blocked")
    assert "reads_known: Site 2 reads Interviews, which nothing before it writes" in " ".join(blocked["payload"]["faults"])
    acts = [e["action"] for e in events]
    assert acts.index("proposal.requested", acts.index("workflow.blocked")) > acts.index("workflow.blocked"), "the reasons go back"
    assert "YOUR LAST LINE WAS REFUSED BY ROOT'S CHECK" in asked[1] and "reads_known" in asked[1]
    assert "workflow.registered" in acts and W.dept(ref)["workflows"][-1]["engines"] == ["Facts 2", "Site 2"]


STANDARD_IDS = re.compile(r"\b(?:%s)\b" % "|".join(i for i, _, _, _ in S.WORKFLOW_STANDARDS))


def test_a4_the_owner_never_reads_a_standards_id_on_a_card_a_tell_or_the_pane(j2, monkeypatch):
    """The notes keep the id of the standard a fault breaks (the done-check reads it); every surface the owner reads says the
    fault in plain words: the blocked card, the line Identity tells, and the Adaptation pane's review."""
    W, R, J, founding, FV = j2
    bad = {"engines": [GOOD[0], dict(GOOD[1], reads="Interviews")]}
    asked = []
    _stub(monkeypatch, R, {"adapt.line": lambda prompt: asked.append(prompt) or bad,
                           "priority.bargain": {"answer": "accept", "why": "the envelope has room"}})
    root = founding.found_structure("Lab Co", owner="Sankalp")["root"]
    W.owner_ask(root, ORGANIC)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    assert len(asked) == 3, "shaped, and shaped again twice, with the reason each time"
    assert "reads_known: Site 2 reads Interviews" in asked[1], "the model is told the standard by its id, as the notes name it"
    assert "reads_known" in " ".join(" ".join(e["payload"].get("faults") or []) for e in J.events(ref) if e["action"] == "workflow.blocked"), "the record keeps it"
    card = next(a for a in W.asks(ref) if a["kind"] == "blocked" and a["status"] == "pending")
    for field in ("text", "title", "why"):
        assert not STANDARD_IDS.search(card[field]), "%s: %s" % (field, card[field])
    assert "Site 2 reads Interviews, which nothing before it writes" in card["text"] and "_known" not in card["text"]
    told = [str(p["payload"].get("done") or p["payload"].get("objective") or "") for p in R.board(ref) if p["src"] == "Identity" and "Owner" in p["dst"]]
    assert not [t for t in told if STANDARD_IDS.search(t)], told
    pane = FV.function(ref, "Adaptation")["j2"]
    assert pane["root_checks"] and not [r["summary"] for r in pane["root_checks"] if STANDARD_IDS.search(r["summary"])], pane["root_checks"]
    assert any("Site 2 reads Interviews" in r["summary"] for r in pane["root_checks"])


def test_a4_owner_words_say_a_fault_without_its_standards_id_and_leave_everything_else_as_it_was():
    import owner_words
    assert owner_words.plain("reads_known: Site 2 reads Interviews, which nothing before it writes") == \
        "Site 2 reads Interviews, which nothing before it writes"
    assert owner_words.plain("The shaped line did not pass its check: Shape the line the words need: names_new: the Library already has an engine named Plan; "
                             "required_kept: the plan leaves out Check.") == \
        "The shaped line did not pass its check: Shape the line the words need: the Library already has an engine named Plan; the plan leaves out Check."
    for every in S.WORKFLOW_STANDARDS:
        assert not STANDARD_IDS.search(owner_words.plain("%s: x" % every[0]))
    # a word that only looks like one, and a standard named without a colon (the pane's check column), stay as they are
    assert owner_words.plain("reads_known") == "reads_known" and owner_words.plain("Priority said yes to it") == "Priority said yes to it"
    assert owner_words.plain("fits_room_not: x") == "fits_room_not: x"


# ---- A3 · proposals cover the done-when items (M5.1) ------------------------------------------------------------------
ITEMS = [{"id": "D1", "text": "The site is live", "how": "code", "level": "outcome"},
         {"id": "D2", "text": "Every page names the phone line", "how": "model", "level": "target"},
         {"id": "D3", "text": "A visitor can find the doctors", "how": "person", "level": "outcome"}]


def _dept(j2, kind, ref="dref-offer", items=ITEMS, name="Offer Dept", **more):
    W = j2[0]
    W.create(ref, name, "A guide to the night clinic", kind=kind, goal="A guide to the night clinic")
    d = W.dept(ref)
    d["done_items"] = [dict(i) for i in items]
    d.update(more)
    W.save_dept(ref, d)
    return ref


def _offer(j2, monkeypatch, ref, source, got, how="offline draft", live=True, payload=None):
    """adapt_line_offer as the recipe runs it, and what it posted: [(dst, act, payload)] of the new posts."""
    W, R, _, _, _ = j2
    monkeypatch.setattr(R, "_j2_live", lambda r: live)
    before = len(R.board(ref))
    pl = dict({"word": "line", "words": "A guide to the night clinic", "for": "x-req"}, **(payload or {}))
    ctx = {"ref": ref, "dept": W.dept(ref), "engine": "Adaptation", "post": {"n": 1, "thread": "x-req", "src": "Identity", "msg_type": "request", "payload": pl},
           "bag": {"adapt.source": source, "adapt.line": got}, "how": {"adapt.line": how}}
    out = v1().CODE["adapt_line_offer"](ctx, None, None)
    return out, [(p["dst"][0], p["msg_type"], p["payload"]) for p in R.board(ref)[before:]]


def _covers_of(posts):
    return [pl for dst, act, pl in posts if pl.get("word") == "line"][-1]


def test_a3_a_library_line_covers_every_item_with_its_last_engine(j2, monkeypatch):
    ref = _dept(j2, "website")
    src = {"shape": False, "source": "library", "engines": [{"name": n, "does": "", "reads": "Brief", "writes": n, "internet": False} for n in LINE]}
    # a library line reads and writes what the Library says: the offer cares only for the names and the covers
    out, posts = _offer(j2, monkeypatch, ref, src, None, how="code")
    sent = _covers_of(posts)
    assert posts[0][:2] == ("Priority", "propose")
    assert sent["covers"] == {"D1": ["Publish"], "D2": ["Publish"], "D3": ["Publish"]}
    assert [e["covers"] for e in sent["engines"]] == [[], [], [], ["D1", "D2", "D3"]]
    assert S.validate_act("Adaptation", ["Priority"], "propose", sent) == []


def test_a3_the_offline_draft_covers_every_item_with_its_last_engine_and_a_default_dept_with_do(j2, monkeypatch):
    ref = _dept(j2, "organic", ref="dref-draft")
    d = j2[0].dept(ref)
    ctx = {"ref": ref, "dept": d}
    draft = v1().DRAFT["adapt_line_draft"](ctx, None, None)
    assert [(e["name"], e["covers"]) for e in draft["engines"]] == [("Facts", []), ("Site", ["D1", "D2", "D3"])]
    out, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, draft)
    assert set(_covers_of(posts)["covers"]) == {"D1", "D2", "D3"} and "confidence" not in _covers_of(posts)
    ref2 = _dept(j2, "default", ref="dref-do")
    src = {"shape": False, "source": "library", "engines": [{"name": "Do", "does": "", "reads": "Brief", "writes": "Result", "internet": False}]}
    _, posts = _offer(j2, monkeypatch, ref2, src, None, how="code")
    assert _covers_of(posts)["covers"] == {"D1": ["Do"], "D2": ["Do"], "D3": ["Do"]}


def test_a3_the_union_of_covers_is_the_set_of_done_items_in_every_kind_and_every_payload_fits_the_interface(j2, monkeypatch):
    for kind, line in (("website", LINE), ("default", ["Do"]), ("organic", ["Facts 2", "Site 2"])):
        ref = _dept(j2, kind, ref="dref-%s" % kind)
        d = j2[0].dept(ref)
        if kind == "organic":
            got, src = v1().DRAFT["adapt_line_draft"]({"ref": ref, "dept": d}, None, None), {"shape": True, "source": "shaped"}
        else:
            src = {"shape": False, "source": "library", "engines": [{"name": n, "does": "", "reads": "Brief", "writes": n, "internet": False} for n in line]}
            got = None
        _, posts = _offer(j2, monkeypatch, ref, src, got, how="code")
        sent = _covers_of(posts)
        assert set(sent["covers"]) == {i["id"] for i in ITEMS}, kind
        assert S.validate_act("Adaptation", ["Priority"], "propose", sent) == [], kind
        wf = S.as_workflow(sent["engines"], sent["source"], d)
        assert wf["covers_by"] == "adaptation" and S.validate("workflow", wf) == []


def test_a3_covers_a_model_names_are_kept_when_known_and_the_rest_default_to_the_last_engine(j2, monkeypatch):
    ref = _dept(j2, "organic")
    named = {"engines": [dict(GOOD[0], covers=["D1", "D9"]), dict(GOOD[1], covers=["D2", "D3", "D2"])]}
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, named, how="model")
    assert _covers_of(posts)["covers"] == {"D1": ["Facts 2"], "D2": ["Site 2"], "D3": ["Site 2"]}, "D9 is no item; D2 once"
    bare = {"engines": GOOD}
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, bare, how="model")
    assert _covers_of(posts)["covers"] == {"D1": ["Site 2"], "D2": ["Site 2"], "D3": ["Site 2"]}


def test_a3_a_line_that_is_not_made_defaults_every_item_its_model_left_unnamed_to_the_last_engine(j2, monkeypatch):
    """A model that was not asked for covers may still name some: what it names is kept and the rest go to the last engine,
    so Root's check does not refuse the line on every reshape (the setting is off, as it is by default)."""
    ref = _dept(j2, "organic")
    partial = {"engines": [dict(GOOD[0], covers=["D1"]), dict(GOOD[1], covers=["D2"])]}
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, partial, how="model")
    sent = _covers_of(posts)
    assert sent["covers"] == {"D1": ["Facts 2"], "D2": ["Site 2"], "D3": ["Site 2"]}
    assert [e["covers"] for e in sent["engines"]] == [["D1"], ["D2", "D3"]] and S.validate_act("Adaptation", ["Priority"], "propose", sent) == []
    first = {"engines": [dict(GOOD[0], covers=["D2"]), dict(GOOD[1], covers=["D2"])]}
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, first, how="model")
    assert _covers_of(posts)["covers"] == {"D2": ["Facts 2", "Site 2"], "D1": ["Site 2"], "D3": ["Site 2"]}


def test_a3_a_made_line_keeps_exactly_the_covers_its_engines_name(j2, monkeypatch):
    """A made line is held to every item by its own check, so the offer never invents a cover for it."""
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    ref = _dept(j2, "organic")
    partial = {"engines": [_made("Facts 2", "Brief", "Facts 2", ["D1"]), _made("Site 2", "Facts 2", "Live site", ["D2"])]}
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, partial, how="model")
    assert _covers_of(posts)["covers"] == {"D1": ["Facts 2"], "D2": ["Site 2"]}


def test_a3_the_line_goes_to_identity_with_its_covers_when_no_cycle_is_live(j2, monkeypatch):
    ref = _dept(j2, "organic")
    out, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, {"engines": GOOD}, how="model", live=False)
    assert posts[0][:2] == ("Identity", "propose") and set(posts[0][2]["covers"]) == {"D1", "D2", "D3"}


def test_a3_a_department_with_no_done_items_proposes_no_covers(j2, monkeypatch):
    ref = _dept(j2, "organic", items=[])
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, {"engines": GOOD}, how="model")
    assert _covers_of(posts)["covers"] == {} and all(e["covers"] == [] for e in _covers_of(posts)["engines"])


# ---- A8 · shape with a confidence (M6.4) ------------------------------------------------------------------------------
def _made(name, reads, writes, covers, level=2, confidence=0.9, **more):
    return dict({"name": name, "does": "does " + name, "reads": reads, "writes": writes, "covers": covers, "level": level,
                 "confidence": confidence, "internet": False}, **more)


PLAY = [_made("Play rules", "Brief", "Play rules", ["D1"]), _made("Game", "Play rules", "Live site", ["D2", "D3"], confidence=0.7,
                                                              doubt="How often should circles appear?")]


def _verdict_of(j2, monkeypatch, kind, out, how="model", faults=None):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    ref = "dref-check-" + kind
    if not j2[0].dept(ref):
        _dept(j2, kind, ref=ref)
    ctx = {"ref": ref, "dept": j2[0].dept(ref), "bag": {"adapt.source": {"shape": True, "source": "shaped"}}, "how": {"adapt.line": how}}
    return v1().CHECK["line_is_engines"](ctx, {"id": "adapt.line"}, None, out)


def test_a8_a_made_line_that_covers_every_item_with_a_level_and_a_confidence_passes(j2, monkeypatch):
    got = _verdict_of(j2, monkeypatch, "organic", {"engines": PLAY})
    assert got["ok"] is True, got


@pytest.mark.parametrize("what, change, note", [
    ("a missing level", lambda e: e[0].pop("level"), "Play rules names no level, 1 or 2"),
    ("a level outside 1 and 2", lambda e: e[0].update(level=3), "Play rules names no level, 1 or 2"),
    ("a missing confidence", lambda e: e[1].pop("confidence"), "Game names no confidence from 0 to 1"),
    ("a confidence above 1", lambda e: e[1].update(confidence=1.4), "Game names no confidence from 0 to 1"),
    ("a doubt left out below 0.8", lambda e: e[1].pop("doubt"), "Game is not sure (below 0.8) and names no doubt"),
    ("an unknown item", lambda e: e[1].update(covers=["D2", "D3", "D9"]), "Game covers D9, which done-when does not have"),
    ("an item nothing covers", lambda e: e[1].update(covers=["D2"]), "D3 is covered by no engine"),
    ("covers that are no list", lambda e: e[0].update(covers="D1"), "Play rules names the items it covers as a list"),
    ("an engine that covers nothing and feeds nothing", lambda e: e.append(_made("Extra", "Brief", "Extra", [])),
     "Extra covers no item and feeds no engine after it"),
    ("a level 1 off the Library", lambda e: e[0].update(level=1), "Play rules is level 1, and the Library has no engine of that name"),
    # J2B-4 refuses a missing field: the offline draft is filled in (norm_engines), a made engine's guess is not
    ("a missing does", lambda e: e[1].pop("does"), "Game says nothing of what it does"),
    ("an empty does", lambda e: e[1].update(does="  "), "Game says nothing of what it does"),
    ("a missing reads", lambda e: e[1].pop("reads"), "Game names nothing it reads"),
    ("a first engine that leaves its reads out, which would be wired to the Brief", lambda e: e[0].pop("reads"), "Play rules names nothing it reads"),
    ("a reads that is no string", lambda e: e[1].update(reads=["Play rules"]), "Game names nothing it reads"),
    ("a missing writes", lambda e: e[1].pop("writes"), "Game names nothing it writes"),
    ("an empty writes", lambda e: e[0].update(writes=""), "Play rules names nothing it writes"),
    ("a missing internet", lambda e: e[1].pop("internet"), "Game does not say whether it goes to the internet"),
    ("an internet that is no bool", lambda e: e[1].update(internet="yes"), "Game does not say whether it goes to the internet"),
])
def test_a8_what_j2b_4_and_j2b_6_refuse(j2, monkeypatch, what, change, note):
    engines = json.loads(json.dumps(PLAY))
    change(engines)
    got = _verdict_of(j2, monkeypatch, "organic", {"engines": engines})
    assert got["ok"] is False and note in got["notes"], (what, got)


def test_a8_a_shipped_name_is_level_1_on_its_template_and_nowhere_else(j2, monkeypatch):
    write = _made("Plan", "Brief", "Site plan", ["D1"], level=1, confidence=0.9)
    pages = _made("Write", "Site plan", "Pages", ["D2"], level=1)
    rest = _made("Notes", "Pages", "Notes", ["D3"])
    assert _verdict_of(j2, monkeypatch, "organic", {"engines": [write, pages, rest]})["ok"] is True, "level 1 on its template stands"
    off = _verdict_of(j2, monkeypatch, "organic", {"engines": [dict(write, writes="Other"), dict(pages, reads="Other"), rest]})
    assert "Plan is level 1, so it keeps its Library reads (Brief) and writes (Site plan)" in off["notes"]
    low = _verdict_of(j2, monkeypatch, "organic", {"engines": [dict(write, level=2), pages, rest]})
    assert "Plan is an engine of the Library, so it is level 1" in low["notes"]
    legacy = _verdict_of(j2, monkeypatch, "organic", {"engines": [write, pages, rest]}, how="offline draft")
    assert legacy["ok"] is False and "names_new: the Library already has an engine named Plan" in legacy["notes"], "a draft is not made: the old rule"


def test_a8_a_made_engine_that_leaves_a_field_out_is_not_filled_in_but_a_draft_is(j2, monkeypatch):
    """norm_engines keeps its tolerant defaults for the offline draft (reads the Brief, writes its name, goes nowhere)."""
    plan = json.loads(json.dumps(PLAY))
    for e in plan[1:]:
        for key in ("does", "reads", "writes", "internet"):
            e.pop(key)
    got = _verdict_of(j2, monkeypatch, "organic", {"engines": plan})
    assert got["ok"] is False and {"Game says nothing of what it does", "Game names nothing it reads", "Game names nothing it writes",
                                   "Game does not say whether it goes to the internet"} <= set(got["notes"]), got
    row = v1().norm_engines(plan)[1]
    assert (row["does"], row["reads"], row["writes"], row["internet"]) == ("", "Brief", "Game", False), "the draft's defaults stay"


def test_a8_a_level_1_engine_that_leaves_its_reads_out_is_told_once(j2, monkeypatch):
    write = _made("Plan", "Brief", "Site plan", ["D1"], level=1, confidence=0.9)
    pages = _made("Write", "Site plan", "Pages", ["D2"], level=1)
    rest = _made("Notes", "Pages", "Notes", ["D3"])
    gap = dict(write)
    gap.pop("reads")
    got = _verdict_of(j2, monkeypatch, "organic", {"engines": [gap, pages, rest]})
    assert got["ok"] is False and "Plan names nothing it reads" in got["notes"]
    assert not [n for n in got["notes"] if "keeps its Library reads" in n], "a field that is missing is told as missing, once"


def test_a8_a_reshape_keeps_the_engines_the_kind_requires_at_level_1(j2, monkeypatch):
    lib = [_made("Pages", "Brief", "Pages", ["D1", "D2"], confidence=0.9)]
    dropped = _verdict_of(j2, monkeypatch, "website", {"engines": lib})
    assert dropped["ok"] is False and "required_kept: the plan leaves out Check, which this kind of department requires" in dropped["notes"]
    kept = _verdict_of(j2, monkeypatch, "website", {"engines": lib + [_made("Check", "Pages", "Build", ["D3"], level=1)]})
    assert kept["ok"] is True, kept
    changed = _verdict_of(j2, monkeypatch, "website", {"engines": lib + [_made("Check", "Pages", "Build", ["D3"], level=2)]})
    assert "Check is an engine of the Library, so it is level 1" in changed["notes"]


def test_a8_cannot_passes_only_for_an_engine_the_kind_requires_and_known_items(j2, monkeypatch):
    cannot = {"cannot": {"engine": "Check", "items": ["D2"], "why": "the game needs a script and Check refuses a page with one"}}
    assert _verdict_of(j2, monkeypatch, "website", cannot) == {"ok": True, "notes": ["Check cannot serve D2"]}
    other = _verdict_of(j2, monkeypatch, "website", {"cannot": dict(cannot["cannot"], engine="Write")})
    assert other["ok"] is False and "Write is not an engine this kind of department requires" in other["notes"][0]
    assert _verdict_of(j2, monkeypatch, "organic", cannot)["ok"] is False, "a kind that requires nothing has nothing to say cannot of"
    assert _verdict_of(j2, monkeypatch, "website", {"cannot": dict(cannot["cannot"], items=["D9"])})["ok"] is False
    assert _verdict_of(j2, monkeypatch, "website", {"cannot": dict(cannot["cannot"], why="")})["ok"] is False
    assert _verdict_of(j2, monkeypatch, "website", {"cannot": "Check"})["ok"] is False
    assert _verdict_of(j2, monkeypatch, "website", cannot, how="offline draft")["ok"] is False, "only a made answer may say cannot"


def test_a8_the_recipe_lets_a_step_answer_cannot_alone_and_nothing_else_alone(j2):
    R = j2[1]
    step = R.step_def("adapt.line")[1]
    assert step["out"] == {"engines": "list"} and step["or"] == {"cannot": "dict"}
    assert R._fits({"cannot": {"engine": "Check"}}, step) is None
    assert R._fits({"engines": []}, step) is None
    assert R._fits({"cannot": "Check"}, step) == "cannot is not a dict"
    assert R._fits({"why": "x"}, step) == "the answer has no engines"


def test_a8_a_confident_line_goes_to_priority_with_its_confidence_and_no_doubt(j2, monkeypatch):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    ref = _dept(j2, "organic")
    sure = {"engines": [_made("Play rules", "Brief", "Play rules", ["D1"]), _made("Game", "Play rules", "Live site", ["D2", "D3"], confidence=0.85)]}
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, sure, how="model")
    assert [p[:2] for p in posts] == [("Priority", "propose")]
    sent = posts[0][2]
    assert sent["confidence"] == 0.85 and "doubt" not in sent
    assert [(e["level"], e["confidence"]) for e in sent["engines"]] == [(2, 0.9), (2, 0.85)]
    assert S.validate_act("Adaptation", ["Priority"], "propose", sent) == []


def test_a8_a_fairly_sure_line_goes_to_priority_with_the_doubt_in_its_payload_and_nobody_is_asked(j2, monkeypatch):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    monkeypatch.setattr(v1(), "hears_doubt", lambda: True)
    ref = _dept(j2, "organic")
    W = j2[0]
    out, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, {"engines": PLAY}, how="model")
    assert [p[:2] for p in posts] == [("Priority", "propose")], "0.7 is shown, not asked"
    assert posts[0][2]["confidence"] == 0.7 and posts[0][2]["doubt"] == "How often should circles appear?"
    assert [a for a in W.asks(ref) if a["status"] == "pending"] == []


def test_a8_a_line_under_0_6_is_a_doubt_to_identity_and_nothing_goes_to_priority(j2, monkeypatch):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    monkeypatch.setattr(v1(), "hears_doubt", lambda: True)
    ref = _dept(j2, "organic")
    unsure = [_made("Play rules", "Brief", "Play rules", ["D1"]),
              _made("Game", "Play rules", "Live site", ["D2", "D3"], confidence=0.45,
                    doubt="Where should an order go? Unless you say, the form shows the order on the screen and sends nothing.")]
    out, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, {"engines": unsure}, how="model")
    assert [p[:2] for p in posts] == [("Identity", "inform")], "no proposal, so nothing can be registered"
    sent = posts[0][2]
    assert sent["word"] == "doubt" and sent["engine"] == "Game" and sent["confidence"] == 0.45 and sent["cannot"] is None
    assert sent["doubt"] == "Where should an order go?" and sent["fallback"] == "the form shows the order on the screen and sends nothing."
    assert S.validate_act("Adaptation", ["Identity"], "inform", sent) == []
    assert "doubt" in out and not [p for p in j2[1].board(ref) if p["src"] == "Adaptation" and p["dst"] == ["Priority"]]


def test_a8_a_doubt_that_names_no_fallback_is_a_whole_act_with_the_key_left_out(j2, monkeypatch):
    """The second sentence of a doubt is optional ('Unless you say, ...'): a plain question is the common case, and act.doubt
    holds a fallback as text, not as null, so the key is left out and Identity goes on with its default."""
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    monkeypatch.setattr(v1(), "hears_doubt", lambda: True)
    ref = _dept(j2, "organic")
    plain = [_made("Play rules", "Brief", "Play rules", ["D1"]),
             _made("Game", "Play rules", "Live site", ["D2", "D3"], confidence=0.45, doubt="Where should the weekly list go?")]
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, {"engines": plain}, how="model")
    assert [p[:2] for p in posts] == [("Identity", "inform")]
    sent = posts[0][2]
    assert sent["word"] == "doubt" and sent["doubt"] == "Where should the weekly list go?" and "fallback" not in sent
    assert S.validate_act("Adaptation", ["Identity"], "inform", sent) == []


def test_a8_a_plain_doubt_reaches_the_owner_as_one_question_with_the_departments_own_fallback(j2, monkeypatch):
    import layers.identity.v1 as identity
    W, R, J, _, FV = j2
    plan = {"engines": [_made("Catalogue", "Brief", "Catalogue", ["D1", "D2"], confidence=0.9),
                        _made("Stock page", "Catalogue", "Live site", ["D3"], confidence=0.45, doubt="Where should the weekly list go?")]}
    ref, _ = _run_scenario(j2, monkeypatch, "organic", LAB_WORDS, "Lab Co", LAB, plan)
    doubts = _board_word(R, ref, "doubt", "Adaptation")
    assert len(doubts) == 1 and "fallback" not in doubts[0]["payload"]
    asked = [a for a in W.asks(ref) if a["kind"] == "j2_identity" and a.get("missing") == "plan" and a["status"] == "pending"]
    assert len(asked) == 1 and "Where should the weekly list go?" in asked[0]["text"], "the question reached the owner"
    assert identity.fallback_default(W.dept(ref)) in asked[0]["text"] + ".", "Unless you say, the default"
    assert W.dept(ref).get("workflows") in (None, []), "nothing is registered while the question is open"


def test_a8_a_request_marked_go_on_sends_a_line_under_0_6_to_priority_with_the_doubt_named_and_asks_nothing(j2, monkeypatch):
    """Identity has asked what it can (act.line_request go_on): Adaptation goes on, as for a confidence from 0.6 to under 0.8,
    and never doubts again."""
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    monkeypatch.setattr(v1(), "hears_doubt", lambda: True)
    ref = _dept(j2, "organic")
    unsure = [_made("Play rules", "Brief", "Play rules", ["D1"]),
              _made("Game", "Play rules", "Live site", ["D2", "D3"], confidence=0.45,
                    doubt="Where should an order go? Unless you say, the form shows the order on the screen and sends nothing.")]
    on = {"go_on": True, "doubt": "Where should an order go?", "fallback": "the form shows the order on the screen and sends nothing"}
    out, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, {"engines": unsure}, how="model", payload=on)
    assert [p[:2] for p in posts] == [("Priority", "propose")], "no doubt to Identity, so no second question and no blocked card"
    sent = posts[0][2]
    assert sent["confidence"] == 0.45 and sent["doubt"].startswith("Where should an order go?")
    assert S.validate_act("Adaptation", ["Priority"], "propose", sent) == []
    assert "doubt" not in out and out["said"].startswith("proposed the line to Priority")
    again, more = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, {"engines": unsure}, how="model")
    assert [p[:2] for p in more] == [("Identity", "inform")], "a request that is not marked go_on still doubts"


def test_a9_a_plan_still_under_0_6_after_the_second_answer_goes_to_priority_with_the_doubt_and_is_registered(j2, monkeypatch):
    """J2B-7 end to end: the stub is unsure every time. Identity asks twice; the third time it tells Adaptation to go on, and
    the plan goes to Priority, is checked and registered, with no blocked card and no third question."""
    W, R, J, _, FV = j2
    plan = {"engines": [_made("Catalogue", "Brief", "Catalogue", ["D1", "D2"], confidence=0.9),
                        _made("Stock page", "Catalogue", "Live site", ["D3"], confidence=0.45, doubt="Where should the weekly list go?")]}
    ref, _ = _run_scenario(j2, monkeypatch, "organic", LAB_WORDS, "Lab Co", LAB, plan)
    for said in ("Send it to the science teacher", "Only the lab technician sees it"):
        assert [a for a in W.asks(ref) if a["kind"] == "j2_identity" and a["status"] == "pending"], "a question waits for the owner"
        J.answer(ref, said)
        W.run_until_idle(ref, limit=300)
    asks = [a for a in W.asks(ref) if a["kind"] == "j2_identity" and a.get("missing") == "plan"]
    assert len(asks) == 2 and all(a["status"] != "pending" for a in asks), "two questions, and no third"
    assert len(_board_word(R, ref, "doubt", "Adaptation")) == 3, "the third doubt is the one Identity answers by telling it to go on"
    told = [q for q in _board_word(R, ref, "line", "Identity") if q["payload"].get("go_on")]
    assert len(told) == 1 and told[0]["dst"] == ["Adaptation"], "told once"
    sent = _board_word(R, ref, "line", "Adaptation")[-1]
    assert sent["dst"] == ["Priority"] and sent["payload"]["confidence"] == 0.45 and sent["payload"]["doubt"] == "Where should the weekly list go?"
    acts = [e["action"] for e in J.events(ref)]
    assert "workflow.registered" in acts and J.status(ref)["state"] != "blocked"
    assert not [a for a in W.asks(ref) if a["kind"] == "blocked"], "the owner is not blocked on a plan that was told to go on"
    assert W.dept(ref)["workflows"][-1]["engines"] == ["Catalogue", "Stock page"]


def test_a8_a_request_marked_go_on_changes_nothing_for_a_sure_line(j2, monkeypatch):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    ref = _dept(j2, "organic")
    sure = {"engines": [_made("Play rules", "Brief", "Play rules", ["D1"]), _made("Game", "Play rules", "Live site", ["D2", "D3"], confidence=0.85)]}
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, sure, how="model", payload={"go_on": True})
    assert [p[:2] for p in posts] == [("Priority", "propose")] and "doubt" not in posts[0][2]


def test_a8_until_identity_hears_a_doubt_a_line_under_0_6_is_shown_not_dropped(j2, monkeypatch):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    monkeypatch.setattr(v1(), "hears_doubt", lambda: False)
    ref = _dept(j2, "organic")
    unsure = [_made("Play rules", "Brief", "Play rules", ["D1"]), _made("Game", "Play rules", "Live site", ["D2", "D3"], confidence=0.45, doubt="Where should an order go?")]
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, {"engines": unsure}, how="model")
    assert [p[:2] for p in posts] == [("Priority", "propose")] and posts[0][2]["doubt"] == "Where should an order go?"


def test_a8_cannot_gives_one_conflict_with_three_typed_options(j2, monkeypatch):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    ref = _dept(j2, "website")
    cannot = {"cannot": {"engine": "Check", "items": ["D2"], "why": "the game needs a script and Check refuses a page with one"}}
    out, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, cannot, how="model")
    assert [p[:2] for p in posts] == [("Identity", "inform")], "one conflict, and no proposal"
    sent = posts[0][2]
    assert sent["word"] == "conflict" and sent["engines"] == [] and "Check cannot serve D2" in sent["why"]
    assert [(o["id"], o["kind"]) for o in sent["options"]] == [("root_setup", "root_setup"), ("leave:D2", "leave"), ("stop", "stop")]
    assert sent["options"][0]["params"] == {"words": "A guide to the night clinic"}, "Root sets it up again in the goal's words"
    assert S.validate_act("Adaptation", ["Identity"], "inform", sent) == []
    again, more = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, cannot, how="model")
    assert more == [], "the same request's conflict is posted once"


def test_a8_a_department_with_one_item_cannot_leave_it_out_and_gets_two_options(j2, monkeypatch):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    ref = _dept(j2, "website", items=ITEMS[:1])
    cannot = {"cannot": {"engine": "Check", "items": ["D1"], "why": "the game needs a script"}}
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, cannot, how="model")
    assert [o["kind"] for o in posts[0][2]["options"]] == ["root_setup", "stop"]


def test_a8_offline_keeps_the_draft_with_no_confidence_and_no_question(j2, monkeypatch):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    ref = _dept(j2, "organic")
    d = j2[0].dept(ref)
    draft = v1().DRAFT["adapt_line_draft"]({"ref": ref, "dept": d}, None, None)
    assert all("confidence" not in e and "level" not in e for e in draft["engines"])
    assert _verdict_of(j2, monkeypatch, "organic", draft, how="offline draft")["ok"] is True
    _, posts = _offer(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, draft, how="offline draft")
    assert [p[:2] for p in posts] == [("Priority", "propose")] and "confidence" not in posts[0][2] and "doubt" not in posts[0][2]


def test_a8_a_doubt_is_split_into_the_question_and_what_happens_unless_the_owner_says():
    split = v1().split_doubt
    assert split("When someone pre-orders, where should the order go? Unless you say, the form shows it on the screen.") == \
        ("When someone pre-orders, where should the order go?", "the form shows it on the screen.")
    assert split("Where should it go?") == ("Where should it go?", None)
    assert split("") == ("", None)


def test_a8_the_make_shape_part_is_in_the_interface_with_its_contract_verbatim():
    part = S.PROMPTS["adaptation"]["make"]["shape"]
    assert part["read_by"] == "adapt.line" and set(part["fields"]) == {"task", "guidance"}
    assert part["inputs"] == ("dept", "words", "items", "practices", "rules", "taken", "out", "refused")
    assert part["returns"].startswith('Return ONLY a JSON object: {"engines": [{"name": str, "does": str, "reads": str, "writes": str, "covers": ["D1"], '
                                      '"level": 1 | 2, "confidence": number, "doubt": str, "internet": bool}]}, or {"cannot": {"engine": str')
    assert S.validate_field("adaptation", "make", "shape", "task", "Shape the line.") == []
    assert {"act": "inform", "words": ("doubt",), "to": ("Identity",), "payload": "act.doubt"} in S.SENDS["Adaptation"]


# ---- A1.18 · a layer that does not load runs engine_runtime's own bodies, and never stops a department -----------------
def test_a3_the_fallback_prompt_builder_fills_every_slot_the_part_has_and_says_what_the_layers_does(j2):
    """R.p_adapt_line is the copy a department runs when adaptation/v1 does not load. make.line gained its items slot in
    M5.1, and the copy passed none, so every shaped line raised: 'the app fills no {{items}}'."""
    W, R, _, _, _ = j2
    ref = _dept(j2, "organic", ref="dref-fallback")
    ctx = {"ref": ref, "dept": W.dept(ref), "post": {"payload": {"word": "line", "words": "A guide to the night clinic", "faults": []}}, "bag": {}}
    got = R.p_adapt_line(ctx, None, None)
    for line in ("D1: The site is live", "D2: Every page names the phone line", "D3: A visitor can find the doctors"):
        assert line in got
    assert got == v1().PROMPT["adapt_line"](ctx, None, None), "the copy and the layer's body say the same words"
    ctx["post"]["payload"]["faults"] = ["reads_known: Site 2 reads Interviews"]
    assert R.p_adapt_line(ctx, None, None) == v1().PROMPT["adapt_line"](ctx, None, None) and "REFUSED BY ROOT'S CHECK" in R.p_adapt_line(ctx, None, None)
    bare = _dept(j2, "organic", ref="dref-fallback-bare", items=[])
    ctx = {"ref": bare, "dept": W.dept(bare), "post": {"payload": {"word": "line", "words": "w"}}, "bag": {}}
    assert R.p_adapt_line(ctx, None, None) == v1().PROMPT["adapt_line"](ctx, None, None) and "none" in R.p_adapt_line(ctx, None, None)


def test_a3_a_department_whose_adaptation_layer_does_not_load_still_has_its_line_shaped(j2, monkeypatch):
    """The fallback end to end: with adaptation/v1 unable to load, the prompt that shapes the line is built (it raised) and the
    step runs on engine_runtime's own bodies."""
    import layers
    W, R, J, founding, FV = j2
    real = layers.load
    monkeypatch.setattr(layers, "load", lambda impl_id: None if str(impl_id).startswith("adaptation/") else real(impl_id))
    asked = []
    _stub(monkeypatch, R, {"adapt.line": lambda prompt: asked.append(prompt) or {"engines": GOOD},
                           "priority.bargain": {"answer": "accept", "why": "the envelope has room"}})
    root = founding.found_structure("Lab Co", owner="Sankalp")["root"]
    W.owner_ask(root, ORGANIC)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    assert asked and "WHAT DONE MEANS, ITEM BY ITEM" in asked[0] and "D1: " in asked[0], "the shape step was asked, with the items"
    assert not [r for r in W.runs(ref) if r.get("engine") == "Adaptation" and r.get("status") == "failed" and "items" in str(r.get("what"))]


# ---- A5 · Adaptation's view -------------------------------------------------------------------------------------------
def _event(action, summary, payload=None, **more):
    return dict({"action": action, "summary": summary, "payload": payload or {}, "occurred_at": "2026-10-27T10:00:00+05:30"}, **more)


ROWS = [{"check": "names_an_engine", "passed": True, "why": "the workflow names its engines"},
        {"check": "items_covered", "passed": False, "why": "D3 is covered by no engine"}]


def _proposed(j2, monkeypatch, ref, source=None, got=None, how="code"):
    """A proposal on the board, and the proposal.created event that names its thread."""
    R = j2[1]
    src = source or {"shape": False, "source": "library", "engines": [{"name": n, "does": "", "reads": "Brief", "writes": n, "internet": False} for n in LINE]}
    _, posts = _offer(j2, monkeypatch, ref, src, got, how=how)
    thread = [p for p in R.board(ref) if p["payload"].get("word") == "line" and p["src"] == "Adaptation"][-1]["thread"]
    return _event("proposal.created", "Proposed the workflow Plan -> Write -> Check -> Publish.",
                  {"source": src["source"], "workflow": [e["name"] for e in posts[0][2]["engines"]], "hop": 1}, proposal_ref=thread)


def test_a5_the_view_is_todays_part_and_the_coverage_of_the_latest_proposal(j2, monkeypatch):
    W, R, J, _, FV = j2
    ref = _dept(j2, "website")
    d = W.dept(ref)
    proposing = [_proposed(j2, monkeypatch, ref)]
    got = v1().view(ref, d, proposing, W.asks(ref))
    assert S.validate_view("adaptation", got) == []
    assert got["proposal"]["workflow"] == LINE and got["proposal"]["source"] == "library"
    assert got["coverage"] == {"items": ["D1", "D2", "D3"], "uncovered": [], "by": "adaptation"}
    assert got["root_checks"] == [] and got["rounds"] == []
    today = FV._j2_body(ref, d, "Adaptation", proposing, W.asks(ref))          # what the pane showed before a layer's view took over (K2)
    assert {k: got[k] for k in ("proposal", "root_checks", "rounds")} == today, "what it showed before is what it shows"
    assert FV._j2_part(ref, d, "Adaptation", proposing, W.asks(ref)) == got, "and the pane is the view"


def test_a5_each_root_review_carries_the_checks_that_ran_in_the_owners_words(j2, monkeypatch):
    W, R, J, _, FV = j2
    ref = _dept(j2, "website")
    d = W.dept(ref)
    events = [_proposed(j2, monkeypatch, ref),
              _event("workflow.blocked", "Root's check refused the workflow: D3 is covered by no engine.", {"workflow": LINE, "faults": ["x"], "checks": ROWS}),
              _event("workflow.validated", "The workflow meets Sutra's standards.", {"workflow": LINE, "checks": [ROWS[0]]})]
    got = v1().view(ref, d, events, W.asks(ref))
    assert S.validate_view("adaptation", got) == []
    blocked, validated = got["root_checks"]
    assert blocked["passed"] is False and validated["passed"] is True
    assert blocked["summary"] == "Root's check sent the plan back: D3 is covered by no engine."
    assert blocked["checks"] == [{"check": "names_an_engine", "says": "the workflow names its engines", "passed": True, "why": "the workflow names its engines"},
                                 {"check": "items_covered", "says": "every done-when item is covered by an engine", "passed": False, "why": "D3 is covered by no engine"}]
    legacy = _event("workflow.validated", "ok", {"checks": [{"check": "names an engine", "passed": True, "why": "the workflow names its engines"}]})
    assert v1().view(ref, d, [legacy], [])["root_checks"][0]["checks"][0]["says"] == "names an engine"
    assert v1().view(ref, d, [_event("workflow.validated", "ok")], [])["root_checks"][0]["checks"] == []


def test_a5_an_item_no_engine_covers_is_named_and_the_view_validates_in_every_state(j2, monkeypatch):
    W, R, J, _, FV = j2
    ref = _dept(j2, "organic")
    d = W.dept(ref)
    # a partial cover is a made line's to name (its own check refuses it); a line that is not made has the rest default to its last engine
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    partial = {"engines": [_made("Facts 2", "Brief", "Facts 2", ["D1"]), _made("Site 2", "Facts 2", "Live site", ["D2"])]}
    prop = _proposed(j2, monkeypatch, ref, {"shape": True, "source": "shaped"}, partial, how="model")
    states = {"proposing": [prop], "reshaping": [prop, _event("workflow.blocked", "Root's check refused the workflow: D3.", {"checks": ROWS})],
              "blocked": [prop] + [_event("workflow.blocked", "Root's check refused the workflow: D3.", {"checks": ROWS})] * 3,
              "registered": [prop, _event("workflow.validated", "The workflow meets Sutra's standards.", {"checks": [ROWS[0]]}),
                             _event("workflow.registered", "Registered it.")]}
    for state, events in states.items():
        got = v1().view(ref, d, events, W.asks(ref))
        assert S.validate_view("adaptation", got) == [], state
        assert got["coverage"] == {"items": ["D1", "D2", "D3"], "uncovered": ["D3"], "by": "adaptation"}, state
    assert len(v1().view(ref, d, states["blocked"], [])["root_checks"]) == 3


def test_a5_a_proposal_that_names_no_covers_reads_as_the_workflow_schema_reads_it_and_no_proposal_has_no_coverage(j2, monkeypatch):
    W, R, J, _, FV = j2
    ref = _dept(j2, "website")
    d = W.dept(ref)
    assert v1().view(ref, d, [], [])["coverage"] is None
    R.post(ref, "Adaptation", "Priority", "propose", {"word": "line", "engines": LINE, "source": "library", "words": "w", "for": "x-1"})
    thread = [p for p in R.board(ref) if p["src"] == "Adaptation"][-1]["thread"]
    old = _event("proposal.created", "Proposed.", {"workflow": LINE, "source": "library"}, proposal_ref=thread)
    assert v1().view(ref, d, [old], [])["coverage"] == {"items": ["D1", "D2", "D3"], "uncovered": [], "by": "default"}


def test_a5_the_view_of_a_born_department_validates_and_reads_through_the_functions_pane(j2):
    W, R, J, founding, FV = j2
    root = founding.found_structure("Acme Learning", owner="Sankalp")["root"]
    W.owner_ask(root, WEBSITE)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    d = W.dept(ref)
    events = FV._events(ref, FV._cycle_state(ref).get("cycle_id"))
    got = v1().view(ref, d, events, W.asks(ref))
    assert S.validate_view("adaptation", got) == []
    assert got["proposal"]["workflow"] == LINE and got["root_checks"][-1]["passed"] is True
    assert got["root_checks"][-1]["checks"], "the checks that ran are listed on the review"
    assert got["coverage"] is not None and got["coverage"]["uncovered"] == []


# ---- A9 · no-template scenarios (M6.5) --------------------------------------------------------------------------------
LAB = [{"text": "Chemicals can be added, found and counted", "how": "model", "level": "outcome"},
       {"text": "Every chemical shows who changed it last", "how": "model", "level": "outcome"},
       {"text": "A stock list for the week is filed", "how": "person", "level": "target"}]
LAB_WORDS = "Set up a laboratory system to track chemical inventory for our school science team"
LAB_PLAN = {"engines": [_made("Catalogue", "Brief", "Catalogue", ["D1", "D2"], confidence=0.9),
                        _made("Stock page", "Catalogue", "Live site", ["D3"], confidence=0.85)]}
DOC_WORDS = "Write the safety handbook for the school science lab, one clear document"
DOC = [{"text": "The handbook covers every room of the lab", "how": "model", "level": "outcome"},
       {"text": "Each rule names who it is for", "how": "model", "level": "outcome"}]
DOC_PLAN = {"engines": [_made("Outline", "Brief", "Outline", ["D1"], confidence=0.9),
                        _made("Handbook", "Outline", "Result", ["D2"], confidence=0.85)]}


def _run_scenario(j2, monkeypatch, kind, words, org, items, plan, answers=None, make=True):
    """A department as a person makes one, with J2_ADAPT_MAKE on (off with make=False) and a stub in place of every model
    Adaptation, Priority, Root and Audit would call; the motor runs until idle, and the owner's one stamp on what goes out
    is given."""
    W, R, J, founding, FV = j2
    if make:
        monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    else:
        monkeypatch.delenv("J2_ADAPT_MAKE", raising=False)
    stubs = {"setup.converse": {"verdict": "clear", "question": ""},
             "setup.shape": {"name": org + " Department", "kind": kind, "goal": words, "done_items": items},
             "adapt.line": plan, "priority.bargain": {"answer": "accept", "why": "the envelope has room"},
             "audit.judge": {"ok": True, "findings": []}}
    if plan is None:
        del stubs["adapt.line"]                         # no agent answers the shape: the offline draft does
    seen = _stub(monkeypatch, R, dict(stubs, **(answers or {})))
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "publish"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)
    return ref, seen


def _deliverable_is_the_departments_own():
    """Whether Audit starts on the department's deliverable (W1-AUDIT, M8.2) and not on the Live site alone."""
    return "$deliverable" in json.dumps(layers.recipes()["Audit"]["start"])


@pytest.mark.parametrize("kind, words, org, items, plan, last", [
    ("organic", LAB_WORDS, "Lab Co", LAB, LAB_PLAN, "Live site"),
    ("default", DOC_WORDS, "Safety Co", DOC, DOC_PLAN, "Result")])
def test_a9_a_department_no_template_fits_shapes_bargains_is_checked_runs_and_is_read(j2, monkeypatch, kind, words, org, items, plan, last):
    W, R, J, _, FV = j2
    ref, seen = _run_scenario(j2, monkeypatch, kind, words, org, items, plan)
    d = W.dept(ref)
    assert d["kind"] == kind and [i["id"] for i in d["done_items"]] == ["D1", "D2", "D3"][:len(items)]
    # shape: the typed part make.shape was sent, with the practices in place and the items
    prompt = next(p for sid, p in seen if sid == "adapt.line")
    assert "THE LIBRARY'S ENGINES" in prompt and "D1: " + items[0]["text"] in prompt and '"cannot": {"engine"' in prompt
    assert "Chemicals" not in prompt or kind == "organic"
    # bargain, Root's check, registration: the cycle's own events, in order, with nothing asked of the owner on the way
    acts = [e["action"] for e in J.events(ref)]
    assert acts[:6] == ["identity.assessed", "proposal.requested", "proposal.created", "proposal.granted", "workflow.validated", "workflow.registered"]
    assert not [a for a in W.asks(ref) if a["kind"] in ("line", "j2_identity", "conflict")]
    names = [e["name"] for e in plan["engines"]]
    assert set(names) <= set(d["engines"]) and d["workflows"][-1]["engines"] == names and d["workflows"][-1]["source"] == "shaped"
    # a covering plan: every item is covered by the engines it names, and the workflow passes the schema
    sent = next(p["payload"] for p in R.board(ref) if p["src"] == "Adaptation" and p["dst"] == ["Priority"] and p["payload"].get("word") == "line")
    assert set(sent["covers"]) == {i["id"] for i in d["done_items"]} and sent["confidence"] == 0.85
    assert S.validate_act("Adaptation", ["Priority"], "propose", sent) == []
    registered = d["workflows"][-1]
    assert S.validate("workflow.registration", registered) == [] and S.validate("workflow", S.as_workflow(sent["engines"], sent["source"], d)) == []
    assert registered["covers"] == sent["covers"] and registered["deliverable"] == last, "Root records what Adaptation said each engine covers"
    assert next(c for c in registered["checks"] if c["check"] == "items_covered")["passed"] is True
    pane = v1().view(ref, d, FV._events(ref, FV._cycle_state(ref).get("cycle_id")), W.asks(ref))
    assert pane["coverage"] == {"items": [i["id"] for i in d["done_items"]], "uncovered": [], "by": "adaptation"}
    assert S.validate_view("adaptation", pane) == []
    # run and read: the plan's engines ran, and the department reached Audit's reading
    ran = [r["engine"] for r in W.runs(ref) if not r.get("system")]
    assert names[0] in ran
    st = J.status(ref)
    if last == "Live site" or _deliverable_is_the_departments_own():
        assert st["step"] >= 7, (st, acts[-6:])
    else:
        assert st["step"] >= 6


GAME = [{"text": "The game has a name", "how": "model", "level": "outcome"},
        {"text": "A round lasts thirty seconds", "how": "code", "level": "target"},
        {"text": "No script errors on any page", "how": "code", "level": "outcome"}]
GAME_WORDS = "Build a browser game where you tap circles for thirty seconds"


def _board_word(R, ref, word, src=None):
    return [p for p in R.board(ref) if (p["payload"] or {}).get("word") == word and (src is None or p["src"] == src)]


def test_a9_a_stub_cannot_on_a_website_game_gives_one_conflict_with_three_typed_options_and_registers_nothing(j2, monkeypatch):
    """Root's check sends a website line back; with the make setting on it is made, not taken again, and Check, which the kind
    requires, cannot pass a game's script: one conflict goes to Identity with the ways out, and nothing is registered."""
    W, R, J, _, FV = j2
    real, calls = R._root_check, {"n": 0}

    def check(ref, d, engines, source):
        calls["n"] += 1
        return ["the plan does not cover D3"] if calls["n"] == 1 else real(ref, d, engines, source)
    monkeypatch.setattr(R, "_root_check", check)
    cannot = {"cannot": {"engine": "Check", "items": ["D3"], "why": "the game needs a script and Check refuses any page with one"}}
    ref, seen = _run_scenario(j2, monkeypatch, "website", GAME_WORDS, "Game Co", GAME, cannot)
    prompt = next(p for sid, p in seen if sid == "adapt.line")
    assert "THIS KIND OF DEPARTMENT REQUIRES THESE ENGINES" in prompt and "- Check:" in prompt and "a page with a script" in prompt
    conflicts = _board_word(R, ref, "conflict", "Adaptation")
    assert len(conflicts) == 1, "one conflict, not one for each try"
    sent = conflicts[0]["payload"]
    assert [(o["id"], o["kind"]) for o in sent["options"]] == [("root_setup", "root_setup"), ("leave:D3", "leave"), ("stop", "stop")]
    assert S.validate_act("Adaptation", ["Identity"], "inform", sent) == []
    assert "workflow.registered" not in [e["action"] for e in J.events(ref)] and W.dept(ref).get("workflows") in (None, [])


def test_a3_a_model_that_names_some_covers_with_the_setting_off_still_has_its_line_registered(j2, monkeypatch):
    """With J2_ADAPT_MAKE off (today's default), a stub that names covers for two of three items used to leave D3 uncovered,
    and Root's check refused the line on every reshape: 'D3 is covered by no engine of the plan'."""
    W, R, J, _, FV = j2
    plan = {"engines": [dict(GOOD[0], covers=["D1"]), dict(GOOD[1], covers=["D2"])]}
    ref, _ = _run_scenario(j2, monkeypatch, "organic", LAB_WORDS, "Lab Co", LAB, plan, make=False)
    acts = [e["action"] for e in J.events(ref)]
    assert "workflow.registered" in acts and "workflow.blocked" not in acts, acts
    registered = W.dept(ref)["workflows"][-1]
    assert registered["engines"] == ["Facts 2", "Site 2"] and registered["covers"] == {"D1": ["Facts 2"], "D2": ["Site 2"], "D3": ["Site 2"]}
    assert next(c for c in registered["checks"] if c["check"] == "items_covered")["passed"] is True


def _cannot_game(j2, monkeypatch, items=GAME):
    """A website game whose first line Root's check sends back, and a stub Make that answers cannot for D3 each time it is asked."""
    W, R, J, _, FV = j2
    real, calls = R._root_check, {"n": 0}

    def check(ref, d, engines, source):
        calls["n"] += 1
        return ["the plan does not cover D3"] if calls["n"] == 1 else real(ref, d, engines, source)
    monkeypatch.setattr(R, "_root_check", check)
    cannot = {"cannot": {"engine": "Check", "items": ["D3"], "why": "the game needs a script and Check refuses any page with one"}}
    return _run_scenario(j2, monkeypatch, "website", GAME_WORDS, "Game Co", items, cannot)[0]


def test_a9_a_cannot_reaches_the_owner_as_one_card_that_says_it_in_plain_words_with_ways_out_and_no_plan_to_stamp(j2, monkeypatch):
    """What the owner sees: not 'Adaptation proposes the plan . ... Stamp to run it as proposed' over a plan that is empty, whose
    stamp sent Root a plan that names no engine and brought the same card back."""
    W, R, J, _, FV = j2
    ref = _cannot_game(j2, monkeypatch)
    assert [a for a in W.asks(ref) if a["kind"] == "conflict"] == [], "no card offers a plan to stamp when there is none"
    cards = [a for a in W.asks(ref) if a["kind"] == "blocked" and a["status"] == "pending"]
    assert len(cards) == 1
    card = cards[0]
    assert card["text"].startswith("Check cannot serve D3: the game needs a script and Check refuses any page with one.")
    assert "Say what the department should do" in card["text"] and "the plan ." not in card["text"]
    assert not re.search(r"run it as proposed|Stamp|stamp|drop it", card["text"]), card["text"]
    assert not STANDARD_IDS.search(card["text"] + card["title"] + card["why"])
    assert [o["id"] for o in card["options"]] == ["words", "leave:D3", "stop"], "the ways out a blocked plan always has"
    assert J.status(ref)["state"] == "blocked"
    told = [str(p["payload"].get("done") or "") for p in R.board(ref) if p["src"] == "Identity" and "Owner" in p["dst"]]
    assert not [t for t in told if "the plan ." in t or "run it as proposed" in t], told
    events = J.events(ref)
    assert "workflow.registered" not in [e["action"] for e in events]
    assert not [e for e in events if "names no engine" in str(e.get("summary"))], "no empty plan ever reached Root's check"
    assert [e["action"] for e in events if e["action"] == "identity.ruled"], "the ledger says Identity put it to the owner"


def test_a9_choosing_a_way_out_of_a_cannot_applies_it_and_does_not_bring_the_same_card_back(j2, monkeypatch):
    W, R, J, _, FV = j2
    ref = _cannot_game(j2, monkeypatch)
    card = next(a for a in W.asks(ref) if a["kind"] == "blocked" and a["status"] == "pending")
    before = len([q for q in R.board(ref) if q["src"] == "Identity" and q["dst"] == ["Adaptation"] and q["msg_type"] == "request"])
    W.choose_option(ref, card["id"], "leave:D3")
    W.run_until_idle(ref, limit=300)
    assert [i["id"] for i in W.dept(ref)["done_items"]] == ["D1", "D2"], "D3 is left out of done-when on the owner's choice"
    asked = [q for q in R.board(ref) if q["src"] == "Identity" and q["dst"] == ["Adaptation"] and q["msg_type"] == "request"]
    assert len(asked) > before, "Adaptation is asked afresh"
    assert not [a for a in W.asks(ref) if a["kind"] == "conflict"]
    assert not [e for e in J.events(ref) if "names no engine" in str(e.get("summary"))]
    assert next(a for a in W.asks(ref) if a["id"] == card["id"])["status"] == "chosen"


def test_a9_a_stub_at_0_7_shows_the_doubt_and_asks_nothing_and_the_department_goes_on(j2, monkeypatch):
    W, R, J, _, FV = j2
    plan = {"engines": [_made("Catalogue", "Brief", "Catalogue", ["D1", "D2"], confidence=0.9),
                        _made("Stock page", "Catalogue", "Live site", ["D3"], confidence=0.7, doubt="Should the list show names or only counts?")]}
    ref, _ = _run_scenario(j2, monkeypatch, "organic", LAB_WORDS, "Lab Co", LAB, plan)
    sent = _board_word(R, ref, "line", "Adaptation")[0]["payload"]
    assert sent["confidence"] == 0.7 and sent["doubt"] == "Should the list show names or only counts?"
    assert not _board_word(R, ref, "doubt") and not [a for a in W.asks(ref) if a["kind"] in ("j2_identity", "conflict")]
    assert [e["action"] for e in J.events(ref)][:6][-1] == "workflow.registered"


def test_a9_a_stub_at_0_45_is_one_doubt_to_identity_and_nothing_is_registered(j2, monkeypatch):
    if not v1().hears_doubt():
        pytest.skip("Identity's recipe has no handler for a doubt yet (W1-IDENTITY, M3.9): until it has, a doubt is shown, not asked")
    W, R, J, _, FV = j2
    plan = {"engines": [_made("Catalogue", "Brief", "Catalogue", ["D1", "D2"], confidence=0.9),
                        _made("Stock page", "Catalogue", "Live site", ["D3"], confidence=0.45,
                              doubt="Where should the weekly list go? Unless you say, it is filed and sent nowhere.")]}
    ref, _ = _run_scenario(j2, monkeypatch, "organic", LAB_WORDS, "Lab Co", LAB, plan)
    doubts = _board_word(R, ref, "doubt", "Adaptation")
    assert len(doubts) == 1 and doubts[0]["dst"] == ["Identity"] and doubts[0]["payload"]["confidence"] == 0.45
    assert not [p for p in R.board(ref) if p["src"] == "Adaptation" and p["dst"] == ["Priority"]], "nothing is proposed"
    assert W.dept(ref).get("workflows") in (None, []) and "workflow.registered" not in [e["action"] for e in J.events(ref)]


def test_a9_offline_with_the_setting_on_keeps_the_draft_and_asks_nothing(j2, monkeypatch):
    W, R, J, founding, FV = j2
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    root = founding.found_structure("Lab Co", owner="Sankalp")["root"]
    W.owner_ask(root, LAB_WORDS)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    created = next(e for e in J.events(ref) if e["action"] == "proposal.created")
    assert created["payload"]["workflow"] == ["Facts", "Site"]
    sent = _board_word(R, ref, "line", "Adaptation")[0]["payload"]
    assert "confidence" not in sent and "doubt" not in sent and sent["covers"] == {"D1": ["Site"]}
    assert not _board_word(R, ref, "doubt")


def test_a9_with_the_setting_on_and_no_agent_to_shape_a_default_department_keeps_do(j2, monkeypatch):
    """J2B-9: the offline draft keeps a default department's Do. It used to be the site draft (Facts -> Site, writing Live
    site), and Identity asked a document department whether the site may go live."""
    W, R, J, _, FV = j2
    ref, seen = _run_scenario(j2, monkeypatch, "default", DOC_WORDS, "Safety Co", DOC, None)
    assert not [sid for sid, _ in seen if sid == "adapt.line"], "no agent was asked: the draft answered"
    d = W.dept(ref)
    assert d["kind"] == "default" and d["workflows"][-1]["engines"] == ["Do"] and d["workflows"][-1]["source"] == "library"
    assert "Facts" not in d["engines"] and "Site" not in d["engines"]
    assert d["workflows"][-1]["covers"] == {"D1": ["Do"], "D2": ["Do"]} and d["workflows"][-1]["deliverable"] == "Result"
    sent = _board_word(R, ref, "line", "Adaptation")[0]["payload"]
    assert sent["source"] == "library" and "confidence" not in sent and "doubt" not in sent
    assert S.validate_act("Adaptation", ["Priority"], "propose", sent) == []
    assert not [a for a in W.asks(ref) if "go live" in str(a.get("text"))], "a document is not a site"
    assert "workflow.blocked" not in [e["action"] for e in J.events(ref)]


def test_a9_with_the_setting_on_and_no_agent_to_shape_a_website_reshape_gets_the_librarys_line_with_its_check(j2, monkeypatch):
    """A website Root sends back once, the setting on and no agent to shape it: the Library repair it has with the setting off
    (the line again, with the Check its kind requires). The Facts -> Site draft has no Check, so required_kept failed and the
    department ended blocked."""
    W, R, J, _, FV = j2
    real, calls = R._root_check, {"n": 0}

    def check(ref, d, engines, source):
        calls["n"] += 1
        return ["the plan does not cover D3"] if calls["n"] == 1 else real(ref, d, engines, source)
    monkeypatch.setattr(R, "_root_check", check)
    ref, _ = _run_scenario(j2, monkeypatch, "website", GAME_WORDS, "Game Co", GAME, None)
    acts = [e["action"] for e in J.events(ref)]
    assert acts.count("workflow.blocked") == 1 and "workflow.registered" in acts, acts
    registered = W.dept(ref)["workflows"][-1]
    assert registered["engines"] == LINE and registered["source"] == "library"
    assert not [a for a in W.asks(ref) if a["kind"] == "blocked"] and J.status(ref)["state"] != "blocked"


def test_a9_the_librarys_draft_is_judged_as_the_librarys_line_and_only_when_it_is_the_draft(j2, monkeypatch):
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    ref = _dept(j2, "default", ref="dref-do-draft")
    ctx = {"ref": ref, "dept": j2[0].dept(ref), "post": {"payload": {"word": "line", "words": "x"}}}
    draft = v1().DRAFT["adapt_line_draft"](ctx, None, None)
    assert draft["source"] == "library" and [e["name"] for e in draft["engines"]] == ["Do"]
    judged = dict(ctx, bag={"adapt.source": {"shape": True, "source": "shaped"}}, how={"adapt.line": "offline draft"})
    assert v1().CHECK["line_is_engines"](judged, None, None, draft)["ok"] is True, v1().CHECK["line_is_engines"](judged, None, None, draft)
    # an agent that says its line is the Library's is not believed: Do is an engine the Library already has
    claimed = dict(judged, how={"adapt.line": "model"})
    assert v1().CHECK["line_is_engines"](claimed, None, None, draft)["ok"] is False
    # with the setting off, or for a kind with no Library line, the draft is the two engines it has always been
    monkeypatch.delenv("J2_ADAPT_MAKE")
    assert [e["name"] for e in v1().DRAFT["adapt_line_draft"](ctx, None, None)["engines"]] == ["Facts", "Site"]
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    organic = _dept(j2, "organic", ref="dref-organic-draft")
    assert [e["name"] for e in v1().DRAFT["adapt_line_draft"]({"ref": organic, "dept": j2[0].dept(organic)}, None, None)["engines"]] == ["Facts", "Site"]
    # a default department's line Root sent back needs no Check, so the draft is again the two engines
    sent_back = dict(ctx, post={"payload": {"word": "line", "words": "x", "faults": ["the plan does not cover D2"]}})
    assert [e["name"] for e in v1().DRAFT["adapt_line_draft"](sent_back, None, None)["engines"]] == ["Facts", "Site"]
    assert "practices" not in sent_back["post"]["payload"], "asking what the setting's absence would take sets nothing on the request"


def test_a9_a_made_website_reshape_keeps_the_librarys_own_check_and_publish_and_registers_them_with_the_plan(j2, monkeypatch):
    """Level 1 takes the Library's engine as it is (J2B-3). A website department has them on its record from birth, and
    Root, which records the plan and never makes an engine (S-10), takes them as the plan names them: it adds nothing
    for them, and does not lose them."""
    W, R, J, _, FV = j2
    real, calls = R._root_check, {"n": 0}

    def check(ref, d, engines, source):
        calls["n"] += 1
        return ["the plan does not cover D3"] if calls["n"] == 1 else real(ref, d, engines, source)
    monkeypatch.setattr(R, "_root_check", check)
    plan = {"engines": [_made("Play rules", "Brief", "Play rules", ["D1"]), _made("Game page", "Play rules", "Pages", ["D2"]),
                        _made("Check", "Pages", "Build", [], level=1), _made("Publish", "Build", "Live site", ["D3"], level=1)]}
    ref, _ = _run_scenario(j2, monkeypatch, "website", GAME_WORDS, "Game Co", GAME, plan)
    registered = W.dept(ref)["workflows"][-1]
    assert registered["engines"] == ["Play rules", "Game page", "Check", "Publish"], registered
    assert registered["source"] == "shaped" and registered["covers"] == {"D1": ["Play rules"], "D2": ["Game page"], "D3": ["Publish"]}
    assert all(c["passed"] for c in registered["checks"]) and any(c["check"] == "required_kept" for c in registered["checks"])
    assert not [x for x in R.board(ref) if "Not added" in str((x["payload"] or {}).get("done") or "")]
    assert R.coordination(ref)["line"] == registered["engines"]


# ---- A1 · Adaptation's two records, typed as their writers write them (A1.9, A1.20) -----------------------------------
def test_a1_an_idea_parked_and_then_noted_is_a_typed_record_whoever_writes_it(j2):
    W, R, _, _, _ = j2
    ref = _dept(j2, "organic", ref="dref-ideas")
    shaped = {"reflected": "the site in Hindi too", "question": None, "shapes": ["a second language", "a Hindi page", "a link", "a fourth"],
              "pick": None, "engine": None}
    ctx = {"ref": ref, "dept": W.dept(ref), "post": {"thread": "x-idea", "payload": {"words": "a page in Hindi", "for": None}},
           "bag": {"adapt.shape": shaped}}
    R.adapt_park(ctx, None, None)
    R.adapt_park(dict(ctx, bag={"adapt.shape": dict(shaped, question="Which pages first?")}, post={"thread": "x-idea-2", "payload": {"words": None}}), None, None)
    first, second = R.ideas(ref)
    assert first["shapes"] == shaped["shapes"][:3] and first["state"] == "parked" and first["question"] is None
    R._note_idea(ref, first["id"], {"engine": "Do", "state": "built"})                                  # the engine the owner stamped
    R._note_idea(ref, second["id"], {"engine": "Web Facts", "priced": "refused", "why": "no room for another engine today"})
    for row in R.ideas(ref):
        assert S.validate_record("adaptation", "idea", row) == [], row
    assert [(r["engine"], r["state"]) for r in R.ideas(ref)] == [("Do", "built"), ("Web Facts", "parked")]


def test_a1_a_ladder_entry_is_a_typed_record_at_every_point_a_step_moves(j2):
    W, R, _, _, _ = j2
    ref = _dept(j2, "organic", ref="dref-ladder")
    engine, step = R.step_def("adapt.line")
    R.hold(ref, step["id"])                                                                                # a born entry, pinned
    R.hold(ref, step["id"], held=False)
    R.move(ref, step, "C1", "stamp a-1", evidence={"runs": 12, "differing": 0, "misses": 0, "pass": 1.0})   # a move up, with its numbers
    R.move(ref, step, "C0", "evidence: its answers began to differ", evidence=None)                        # and one down
    ctx = {"ref": ref, "post": {"payload": {"step": step["id"], "to": "C1", "form": None}}}
    R.adapt_trial(ctx, None, None)                                                                          # a trial, running
    assert R.ladder(ref)[step["id"]]["trial"]["state"] == "running"
    R.adapt_notrial(ctx, None, None)                                                                        # and Priority's no to it
    e = R.entry(ref, step)
    e["trial"] = {"rung": "C2", "form": "table", "runs": 4, "agree": 4, "norule": 0, "state": "done", "started": W.now()}
    e["pending"] = "a move, with the owner"
    R._save_entry(ref, e)
    _, other = R.step_def("adapt.source")
    R.hold(ref, other["id"])
    assert set(R.ladder(ref)) == {step["id"], other["id"]}
    for entry in R.ladder(ref).values():
        assert S.validate_record("adaptation", "ladder", entry) == [], entry
    assert [h["by"] for h in R.ladder(ref)[step["id"]]["history"]][:2] == ["born", "stamp a-1"]


def test_a1_a_record_that_does_not_fit_is_a_row_in_warn_mode_where_the_idea_or_the_entry_is_written(j2, monkeypatch):
    monkeypatch.setattr(S, "MODE", "warn")
    W, R, _, _, _ = j2
    ref = _dept(j2, "organic", ref="dref-bad-records")
    engine, step = R.step_def("adapt.line")
    e = R.entry(ref, step)
    with S.expect_refused("adaptation.ladder") as met:
        R._save_entry(ref, dict(e, rung="C9", held="yes"))
    assert sorted(met) == ["$.held: is not true or false", "$.rung: is not one of P, C0, C1, C2"]
    assert R.ladder(ref)[step["id"]]["rung"] == "C9", "warn mode: the write lands"
    ctx = {"ref": ref, "dept": W.dept(ref), "post": {"thread": "x-idea", "payload": {"words": "w"}},
           "bag": {"adapt.shape": {"reflected": "r" * 8001, "question": 7, "shapes": ["a", "b"]}}}
    with S.expect_refused("adaptation.idea") as met:
        R.adapt_park(ctx, None, None)
    assert len(met) == 2 and any(f.startswith("$.question") for f in met) and any(f.startswith("$.reflected") for f in met), met


def test_a1_a_record_that_does_not_fit_is_refused_in_refuse_mode_and_nothing_is_written(j2, monkeypatch):
    monkeypatch.setattr(S, "MODE", "refuse")
    W, R, _, _, _ = j2
    ref = _dept(j2, "organic", ref="dref-refused-records")
    engine, step = R.step_def("adapt.line")
    e = R.entry(ref, step)
    with S.expect_refused("adaptation.ladder"):
        with pytest.raises(S.SchemaFault):
            R._save_entry(ref, dict(e, rung="C9"))
    assert step["id"] not in R.ladder(ref)
    R._save_entry(ref, e)
    assert R.ladder(ref)[step["id"]]["rung"] == e["rung"], "an entry that fits is written"
    ctx = {"ref": ref, "dept": W.dept(ref), "post": {"thread": "x-idea", "payload": {"words": "w"}},
           "bag": {"adapt.shape": {"reflected": "r", "question": 7, "shapes": ["a", "b"]}}}
    with S.expect_refused("adaptation.idea"):
        with pytest.raises(S.SchemaFault):
            R.adapt_park(ctx, None, None)
    assert R.ideas(ref) == []


def test_a1_the_two_records_are_no_longer_open_and_the_rungs_are_the_runtimes():
    R = importlib.import_module("engine_runtime")
    assert S.RUNGS == R.RUNGS
    for name in ("adaptation.idea", "adaptation.ladder"):
        assert S.DEFS[name]["properties"] and S.DEFS[name]["required"], "%s is typed" % name
    assert S.validate_record("adaptation", "idea", "a page in Hindi") and S.validate_record("adaptation", "ladder", ["C0"])
    assert S.validate_record("adaptation", "ladder", {"engine": "Write", "step": "write.page", "rung": "C0", "held": False, "history": [],
                                                      "something_a_later_writer_adds": 1}) == [], "an unknown key passes and is kept"
