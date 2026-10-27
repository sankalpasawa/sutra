"""Adaptation behind its interface (PRD amendment A1: W1-ADAPT, M5.7, M5.1, M6.3 to M6.5), one section per step.

  A1  adaptation/v1 provides every name its recipe uses, by reference, and passes the contract
  A6  Adaptation starts on the department's deliverable
  A7  the practices in place ride on the line request (J2_ADAPT_MAKE)
  A8  a shape with a confidence: J2B-4 in the covering, J2B-7 in the offer
  A9  organic and default kinds end to end, with stubbed models
  F1  the Library's line fitted to the goal (W2-ADAPT, M5.2): the check, the draft, the notes and the prompts that hold them
  F2  a conflict carries the options Priority sent (M5.4)
  F3  the next round after a reading that is not done: priced, never the same twice, a limit question when none is new (M9.1, M9.4)
  F4  the rounds in the view (M9.6)

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
    assert {k: len(v) for k, v in used.items()} == {"code": 19, "prompt": 4, "draft": 4, "check": 8}
    for kind, names in used.items():
        assert names <= set(getattr(module, kind.upper())), "%s names the recipe uses that the module leaves to the legacy registry" % kind


@pytest.mark.parametrize("case", [c for c in C.cases() if c[0] in (1, 2, 3, 4, 7)], ids=lambda c: "case %d" % c[0])
def test_a1_the_contract_cases_pass_for_adaptation_v1(case, home):
    _, what, fn = case
    assert fn(v1(), home) == [], what


def test_a1_what_it_holds_by_reference_is_counted_for_the_hand_in(capsys):
    counts = C.by_reference(v1())
    print("adaptation/v1: %(by_reference)d by reference, %(own)d own" % counts)
    assert counts["by_reference"] + counts["own"] == 35


# ---- A2 · Adaptation's words (M2.5) -----------------------------------------------------------------------------------
def test_a2_every_part_of_adaptations_interface_is_served_from_its_words_and_none_is_left_without(home):
    import layers.prompts as P
    for group, parts in S.PROMPTS["adaptation"].items():
        for part in parts:
            assert P._module(home["ref"], "adaptation", group, part) is v1(), "%s.%s is served by adaptation/v1's words" % (group, part)
    assert C.parts_without_words(v1()) == []
    assert P.faults() == [] and sorted(v1().WORDS) == sorted(v1().LAYOUT) == ["decide", "goal", "make", "sense"]


@pytest.mark.parametrize("case", C.cases(), ids=lambda c: "case %d" % c[0])
def test_a2_the_whole_contract_passes_for_adaptation_v1_with_no_part_left_without_words(case, home):
    _, what, fn = case
    assert fn(v1(), home) == [], what


def test_a2_each_part_compiles_to_the_retired_files_part_it_came_from_byte_for_byte(home):
    import layers.prompts as P
    from test_function_prompts import retired
    seen = 0
    for group, parts in S.PROMPTS["adaptation"].items():
        for part, spec in parts.items():
            if ("adaptation", group, part) in S.ADDED_PARTS:
                continue
            sample = {n: "<<%s>>" % n for n in spec["inputs"]}
            got = P.prompt(home["ref"], "adaptation", group, part, **sample)
            assert got == P.SLOT.sub(lambda m: sample[m.group(1)], retired("adaptation", group, part)), "%s.%s" % (group, part)
            seen += 1
    assert seen == 6


def test_a2_the_goal_card_is_read_from_the_typed_words(home):
    R = importlib.import_module("engine_runtime")
    does, skills = R._goal_of(home["ref"], "Adaptation")
    assert does == v1().WORDS["goal"]["does"]["text"] == "decides how the department reaches its goal and keeps changing how as it learns: it proposes the workflows the goal needs, from the Library or shaped fresh, and a step's move up or down the ladder"
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


#: what engine_runtime's check of a line (c_line_is_engines, deleted by W3-PROOF X1 with the other copies of bodies a version took over) said
#: for the five outputs below, taken from it on the tree before that commit
LEGACY_LINE_SAYS = [
    {"ok": True, "notes": ["2 engines, each reading what one before it wrote"]},
    {"ok": False, "notes": ["the Library already has an engine named Plan"]},
    {"ok": False, "notes": ["one to six engines"]},
    {"ok": False, "notes": ["one to six engines"]},
    {"ok": False, "notes": ["Site 2 writes Facts 2, which is already written"]},
]


def test_a4_a_sound_line_says_what_it_always_said_and_the_legacy_check_agrees(j2):
    R = j2[1]
    assert not hasattr(R, "c_line_is_engines") and "line_is_engines" not in R.CHECK, "the legacy check is gone; its answers are LEGACY_LINE_SAYS"
    ctx = _line_ctx(j2)
    outs = ({"engines": GOOD}, {"engines": [dict(GOOD[0], name="Plan")] + GOOD[1:]}, {"engines": []}, {"engines": "none"},
            {"engines": [GOOD[0], dict(GOOD[1], reads="Brief", writes="Facts 2")]})
    for out, theirs in zip(outs, LEGACY_LINE_SAYS):
        mine = v1().CHECK["line_is_engines"](ctx, None, None, out)
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


#: what the owner must never read on a card, a tell or the pane: the interface's own path and pattern, or the shape row's id
RAW_SCHEMA = re.compile(r"\$\.|\^\[|workflow_meets_standards|\{0,39\}")

WEB = [dict(GOOD[0], name="Facts (web)", writes="Facts (web)"), dict(GOOD[1], reads="Facts (web)")]


@pytest.mark.parametrize("said, fits", [
    ("Facts (web)", "Facts web"), ("Site: 2", "Site 2"), ("Facts/Notes", "Facts Notes"), ("Facts_web", "Facts web"),
    ("Café notes", "Cafe notes"), ("(web) facts", "web facts"), ("--Facts", "Facts"), ("Facts   about\tit", "Facts about it"),
    ("Q&A of Dr. O'Neil-Smith", "Q&A of Dr. O'Neil-Smith"), ("Facts 2", "Facts 2"), ("", ""), ("***", ""), ("你好", "")])
def test_a4_a_name_is_made_to_fit_the_characters_the_interface_allows_and_a_name_that_fits_is_left_alone(said, fits):
    """The words are the model's and the characters are the interface's: a character NAME_RE refuses becomes a space (an
    accent is dropped), the first character is a letter or a number, and a name that already fits is not touched."""
    assert v1().fit_name(said) == fits
    assert re.search(S.NAME_RE, fits) or fits == ""


def test_a4_whatever_a_model_names_an_engine_it_fits_the_interface_or_is_nothing_and_fitting_twice_changes_nothing():
    """The property the cases above are samples of: a sample of strings from every part of the character range, none of them
    reaching the interface as a name it refuses."""
    import random
    rng = random.Random(7)
    marks = [chr(c) for c in range(32, 0x2fff, 7)] + list("abcXYZ019 &'.-_/:()\u00e9\t\n\u00a0\ufb01")
    for _ in range(500):
        said = "".join(rng.choice(marks) for _ in range(rng.randint(0, 70)))
        fit = v1().fit_name(said)
        assert fit == "" or re.search(S.NAME_RE, fit), repr(said)
        assert v1().fit_name(fit) == fit, repr(said)


def test_a4_norm_engines_fits_the_name_what_it_reads_and_what_it_writes_before_it_cuts(j2):
    row = v1().norm_engines([{"name": "Facts (web)", "does": "x", "reads": "The Brief (owner's)", "internet": True}])[0]
    assert row["name"] == "Facts web" and row["writes"] == "Facts web", "a missing writes is the name as it now is"
    assert row["reads"] == "The Brief owner's"
    long = v1().norm_engines([{"name": "(" + "Facts about the night clinic " * 4}])[0]
    assert len(long["name"]) == 40 and re.search(S.NAME_RE, long["name"]) and long["name"].startswith("Facts")
    for engines in (GOOD, [{"name": n, "reads": "Brief", "writes": n} for n in LINE]):
        assert [r["name"] for r in v1().norm_engines(engines)] == [e["name"] for e in engines], "a name that fits is not changed"


def test_a4_a_name_with_a_character_the_interface_refuses_is_judged_as_the_name_it_will_be_posted_with(j2):
    """Found by a verifier: 'Facts (web)' failed the proposal stage with the interface's path and pattern on the owner's card.
    Now the characters are made to fit before the line is judged, so the line is sound and its notes are as they were."""
    ctx = _line_ctx(j2)
    for said in ("Facts (web)", "Facts: web", "Facts/web", "Facts_web", "Fäcts web"):
        engines = [dict(WEB[0], name=said, writes=said), dict(WEB[1], reads=said)]
        got = v1().CHECK["line_is_engines"](ctx, None, None, {"engines": engines})
        assert got == {"ok": True, "notes": ["2 engines, each reading what one before it wrote"]}, (said, got)
    # two names that differ only in the characters the interface refuses are one name once they fit
    twice = v1().CHECK["line_is_engines"](ctx, None, None, {"engines": [WEB[0], dict(WEB[1], name="Facts web", reads="Facts (web)")]})
    assert twice["ok"] is False and twice["notes"] == ["names_unique: Facts web is named twice"], twice


@pytest.mark.parametrize("engines, note", [
    ([dict(GOOD[0], name="***", writes="***"), GOOD[1]], "engine 1's name may use only letters, numbers, spaces and & ' . - (at most 40 characters)"),
    ([GOOD[0], dict(GOOD[1], reads="***")], "Site 2 names what it reads with only letters, numbers, spaces and & ' . - (at most 40 characters)"),
    ([GOOD[0], dict(GOOD[1], writes="***")], "Site 2 names what it writes with only letters, numbers, spaces and & ' . - (at most 40 characters)")])
def test_a4_what_the_name_pattern_still_refuses_is_said_in_the_owners_words_with_no_path_and_no_pattern(j2, engines, note):
    """A name nothing is left of once its characters are made to fit cannot be judged as a name: the line fails, and the shape
    row (the interface's, which is not one of Root's standards) is said as a sentence, naming no path, no pattern and no id."""
    got = v1().CHECK["line_is_engines"](_line_ctx(j2), None, None, {"engines": engines})
    assert got["ok"] is False and note in got["notes"], got
    assert not RAW_SCHEMA.search(" ".join(got["notes"])), got["notes"]


@pytest.mark.parametrize("covers, note", [
    (["D2", "D3", "D3"], "Game names an item twice"),
    (["D2", "D3", "tomorrow"], "Game names an item in a form done-when does not use"),
    (["D2", "D3"] + ["D%d" % n for n in range(4, 16)], "Game names more than 12 items")])
def test_a4_what_the_shape_row_finds_in_a_made_line_is_said_by_the_engines_name_and_never_by_its_path(j2, monkeypatch, covers, note):
    """The shape row stops at three faults and each is the interface's own (a path, then what is wrong): a note says it by the
    engine's name."""
    engines = json.loads(json.dumps(PLAY))
    engines[1]["covers"] = covers
    got = _verdict_of(j2, monkeypatch, "organic", {"engines": engines})
    assert got["ok"] is False and note in got["notes"], got
    assert not RAW_SCHEMA.search(" ".join(got["notes"])), got["notes"]


def test_a4_a_name_with_a_character_the_interface_refuses_is_proposed_and_registered_as_it_fits(j2, monkeypatch):
    """The finding's probe end to end: an organic department, the make setting off, a model that names 'Facts (web)'. No card
    is blocked; the plan that is registered, and the line Coordination keeps, carry the name as it fits."""
    W, R, J, founding, FV = j2
    asked = []
    _stub(monkeypatch, R, {"adapt.line": lambda prompt: asked.append(prompt) or {"engines": WEB},
                           "priority.bargain": {"answer": "accept", "why": "the envelope has room"}})
    root = founding.found_structure("Lab Co", owner="Sankalp")["root"]
    W.owner_ask(root, ORGANIC)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    assert len(asked) == 1, "shaped once: nothing was sent back"
    acts = [e["action"] for e in J.events(ref)]
    assert "workflow.registered" in acts and "workflow.blocked" not in acts
    assert W.dept(ref)["workflows"][-1]["engines"] == ["Facts web", "Site 2"]
    assert not [a for a in W.asks(ref) if a["kind"] == "blocked"]


def test_a4_a_plan_no_name_can_be_made_of_blocks_with_a_card_that_has_no_path_and_no_pattern(j2, monkeypatch):
    """When nothing is left of a name to judge, the reasons go back twice and then the owner is told: the card, the tell and
    the pane say it in words. The record keeps the check that failed."""
    W, R, J, founding, FV = j2
    bad = {"engines": [dict(GOOD[0], name="***", writes="***"), dict(GOOD[1], reads="***")]}
    asked = []
    _stub(monkeypatch, R, {"adapt.line": lambda prompt: asked.append(prompt) or bad,
                           "priority.bargain": {"answer": "accept", "why": "the envelope has room"}})
    root = founding.found_structure("Lab Co", owner="Sankalp")["root"]
    W.owner_ask(root, ORGANIC)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    assert len(asked) == 3 and "may use only letters, numbers, spaces" in asked[1], "the model is told what a name may use, in words"
    assert not [p for p in asked[1:] if RAW_SCHEMA.search(p)], "nothing of the interface's path or pattern goes back to the model either"
    card = next(a for a in W.asks(ref) if a["kind"] == "blocked" and a["status"] == "pending")
    assert "could not shape a plan that passes its check" in card["text"]
    for field in ("text", "title", "why"):
        assert not RAW_SCHEMA.search(card[field]) and not STANDARD_IDS.search(card[field]), "%s: %s" % (field, card[field])
    told = [str(p["payload"].get("done") or p["payload"].get("objective") or "") for p in R.board(ref) if p["src"] == "Identity" and "Owner" in p["dst"]]
    assert not [t for t in told if RAW_SCHEMA.search(t)], told
    pane = FV.function(ref, "Adaptation")["j2"]
    assert not [r["summary"] for r in pane["root_checks"] if RAW_SCHEMA.search(r["summary"])], pane["root_checks"]


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


# ---- A1.18 · engine_runtime's own copies of the layer's bodies (retired by W3-PROOF X1: see test_layer_retire.py) --------------
def test_a3_the_line_prompt_fills_every_slot_the_part_has_and_says_what_the_layers_does(j2):
    """make.line gained its items slot in M5.1, and a body that passed none raised on every shaped line: 'the app fills no {{items}}'.
    The layer's body fills every slot the part has (engine_runtime's copy of it, the fallback of a layer that does not load, is
    deleted: W3-PROOF X1)."""
    W, R, _, _, _ = j2
    assert not hasattr(R, "p_adapt_line") and "adapt_line" not in R.PROMPT
    ref = _dept(j2, "organic", ref="dref-fallback")
    ctx = {"ref": ref, "dept": W.dept(ref), "post": {"payload": {"word": "line", "words": "A guide to the night clinic", "faults": []}}, "bag": {}}
    got = v1().PROMPT["adapt_line"](ctx, None, None)
    for line in ("D1: The site is live", "D2: Every page names the phone line", "D3: A visitor can find the doctors"):
        assert line in got
    assert "A guide to the night clinic" in got and "REFUSED BY ROOT'S CHECK" not in got
    ctx["post"]["payload"]["faults"] = ["reads_known: Site 2 reads Interviews"]
    assert "REFUSED BY ROOT'S CHECK" in v1().PROMPT["adapt_line"](ctx, None, None)
    bare = _dept(j2, "organic", ref="dref-fallback-bare", items=[])
    ctx = {"ref": bare, "dept": W.dept(bare), "post": {"payload": {"word": "line", "words": "w"}}, "bag": {}}
    assert "none" in v1().PROMPT["adapt_line"](ctx, None, None)


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
    assert [o["id"] for o in card["options"]] == ["root_setup", "leave:D3", "stop"], "the ways out the conflict carries (J2B-7): Identity files them (M5.4)"
    assert [o["kind"] for o in card["options"]] == ["root_setup", "leave", "stop"] and card["options"][0]["params"]["words"]
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


# ---- F1 · fit a Library line to the use case (W2-ADAPT, M5.2) ---------------------------------------------------------
def _fit_ctx(j2, ref="dref-fit", payload=None, kind="website"):
    """The context adapt.fit's check and offer read: a department of `kind` and the source adapt.source took for it."""
    out, ctx = _source(j2, kind, payload, name="Fit Dept", ref=ref)
    ctx["bag"]["adapt.source"] = out
    return ctx


def _fitted(ctx, engines, fit=None):
    return v1().CHECK["line_is_fitted"](ctx, None, None, {"engines": engines, "fit": fit if fit is not None else {}, "why": "x"})


@pytest.mark.parametrize("engines, fit", [
    (LINE, {}),                                                                       # the line whole
    (LINE, {"Plan": "one page only", "Write": "write that one page"}),                # whole, with notes
    (["Plan", "Write", "Check"], {"Write": "no gallery"}),                            # a tail left out
    (["Check"], {"Check": "one page only"}),                                          # 'One page only' keeps Check and leaves the rest
    (["Write", "Check", "Publish"], {}),                                              # in order, and Check is there
])
def test_f1_a_fitted_line_is_an_in_order_subsequence_that_keeps_every_required_engine(j2, engines, fit):
    got = _fitted(_fit_ctx(j2), engines, fit)
    assert got["ok"] is True, got
    assert re.match(r"\d of 4 engines, in the Library's order", got["notes"][0])


@pytest.mark.parametrize("engines, fit, note", [
    (["Plan", "Write", "Check", "Gallery"], {}, "Gallery is not in the kind's line (Plan -> Write -> Check -> Publish)"),
    (["Plan", "Gallery", "Map"], {}, "Gallery and Map are not in the kind's line"),
    (["Write", "Plan", "Check"], {}, "the Library's order is changed: it runs Plan -> Write -> Check -> Publish"),
    (["Check", "Plan"], {}, "the Library's order is changed"),
    (["Plan", "Write", "Publish"], {}, "the line leaves out Check, which this kind of department requires"),
    (["Plan", "Plan", "Write", "Check"], {}, "Plan named more than once"),
    (["Plan", "Write", "Check"], {"Publish": "put it live"}, "fit has a note for Publish, which is no engine of the line"),
    (["Plan", "Write", "Check"], {"Gallery": "no gallery"}, "fit has a note for Gallery, which is no engine of the line"),
    (["Plan", "Write", "Check"], {"Plan": "x" * 301}, "the note for Plan is 301 characters; at most 300"),
    (["Plan", "Write", "Check"], {"Plan": ["not words"]}, "the note for Plan is not words"),
    (["Plan", "Write", "Check"], "no notes", "fit is a note for each engine that needs one, as an object"),
    ([], {}, "the engines to run are named, as a list of names"),
    ("Plan", {}, "the engines to run are named, as a list of names"),
    ([3], {}, "the engines to run are named, as a list of names"),
])
def test_f1_a_fit_that_adds_reorders_drops_a_required_engine_or_notes_wrongly_is_refused_naming_what_is_wrong(j2, engines, fit, note):
    got = _fitted(_fit_ctx(j2), engines, fit)
    assert got["ok"] is False and any(note in n for n in got["notes"]), got


def test_f1_a_note_of_three_hundred_characters_passes_and_the_check_needs_no_department_to_say_no_line(j2):
    assert _fitted(_fit_ctx(j2), LINE, {"Write": "x" * 300})["ok"] is True
    bare = v1().CHECK["line_is_fitted"]({"dept": None, "bag": {}}, None, None, {"engines": LINE, "fit": {}})
    assert bare == {"ok": False, "notes": ["there is no line of the kind's to fit"]}


def test_f1_the_draft_is_the_kinds_line_unchanged_and_a_skipped_step_fits_nothing(j2):
    ctx = _fit_ctx(j2)
    draft = v1().DRAFT["adapt_fit_draft"](ctx, None, None)
    assert draft["engines"] == LINE and draft["fit"] == {} and draft["why"]
    assert v1().CHECK["line_is_fitted"](ctx, None, None, draft)["ok"] is True, "the draft passes the check it stands behind"
    assert S.validate_field("adaptation", "make", "fit", "task", "Fit it.") == []
    shaped = _fit_ctx(j2, ref="dref-fit-shaped", kind="organic")
    assert v1().DRAFT["adapt_fit_draft"](shaped, None, None)["engines"] == [], "a shaped source has no line of the Library's to fit"


def test_f1_the_check_is_held_by_the_interface_and_the_part_is_in_it_with_its_contract_verbatim():
    assert "line_is_fitted" in S.CHECKS["adaptation"] and ("adaptation", "make", "fit") in S.ADDED_PARTS
    part = S.PROMPTS["adaptation"]["make"]["fit"]
    assert part["read_by"] == "adapt.fit" and part["inputs"] == ("dept", "words", "items", "engines", "rules")
    assert part["returns"] == ('Return ONLY a JSON object: {"engines": ["the Library engines to run, in their order"], "fit": '
                               '{"<engine>": "one line: what this engine does differently for this goal"}, "why": "one line"}.')
    assert set(part["fields"]) == {"task", "guidance"}
    step = next(x for x in C._steps(C.recipe_of(v1())) if x["id"] == "adapt.fit")
    assert (step["nature"], step["born"], step["prompt"], step["draft"], step["check"], step["only_if"]) == \
        ("decide", "C0", "adapt_fit", "adapt_fit_draft", "line_is_fitted", "adapt.source.source=library")
    assert step["out"] == {"engines": "list", "fit": "dict", "why": "str"}


def test_f1_the_step_comes_after_the_source_and_before_the_line_it_does_not_replace():
    handler = next(h for h in layers.recipes()["Adaptation"]["on"] if h["name"] == "Shape the line")
    assert [s["id"] for s in handler["steps"]] == ["adapt.hearline", "adapt.source", "adapt.fit", "adapt.line", "adapt.lineoffer"]


def _fit_offer(j2, monkeypatch, ctx, fit, payload=None):
    """adapt_line_offer with adapt.fit's answer in the bag, and what it posted."""
    W, R, _, _, _ = j2
    monkeypatch.setattr(R, "_j2_live", lambda r: True)
    ref, before = ctx["ref"], len(R.board(ctx["ref"]))
    ctx = dict(ctx, post={"n": 1, "thread": "x-req", "src": "Identity", "msg_type": "request",
                          "payload": dict({"word": "line", "words": "A guide to the night clinic", "for": "x-req"}, **(payload or {}))},
               how={"adapt.fit": "model"})
    ctx["bag"] = dict(ctx["bag"], **{"adapt.fit": fit})
    out = v1().CODE["adapt_line_offer"](ctx, None, None)
    return out, [(p["dst"][0], p["msg_type"], p["payload"]) for p in R.board(ref)[before:]]


def test_f1_the_offer_proposes_the_engines_it_kept_with_their_notes_in_fit_and_on_each_row(j2, monkeypatch):
    ctx = _fit_ctx(j2)
    out, posts = _fit_offer(j2, monkeypatch, ctx, {"engines": ["Plan", "Write", "Check"], "fit": {"Write": "one page, no gallery", "Check": "  keep  it\nshort "},
                                                  "why": "one page"})
    sent = _covers_of(posts)
    assert posts[0][:2] == ("Priority", "propose") and [e["name"] for e in sent["engines"]] == ["Plan", "Write", "Check"]
    assert sent["fit"] == {"Write": "one page, no gallery", "Check": "keep it short"}, "notes ride in act.line fit, in plain words"
    assert [e.get("fit") for e in sent["engines"]] == [None, "one page, no gallery", "keep it short"], "and on the row of the engine they are for"
    assert sent["source"] == "library" and "Publish" not in json.dumps(sent["engines"])
    assert S.validate_act("Adaptation", ["Priority"], "propose", sent) == []
    assert out["said"] == "proposed the line to Priority: Plan -> Write -> Check (fitted to the goal, leaving out Publish, 2 notes)"


def test_f1_a_line_with_no_note_and_nothing_left_out_is_proposed_as_it_always_was(j2, monkeypatch):
    ctx = _fit_ctx(j2)
    out, posts = _fit_offer(j2, monkeypatch, ctx, {"engines": LINE, "fit": {}, "why": "nothing to change"})
    sent = _covers_of(posts)
    assert "fit" not in sent and not [e for e in sent["engines"] if "fit" in e] and [e["name"] for e in sent["engines"]] == LINE
    assert out["said"] == "proposed the line to Priority: Plan -> Write -> Check -> Publish"


def test_f1_a_line_root_sent_back_is_taken_whole_and_a_fit_that_is_not_sound_cannot_stop_it(j2, monkeypatch):
    ctx = _fit_ctx(j2, payload={"faults": ["required_kept: the plan leaves out Check"]}, ref="dref-fit-back")
    bad = {"engines": ["Plan", "Gallery"], "fit": {"Gallery": "x" * 400}, "why": "x"}
    assert v1().CHECK["line_is_fitted"](ctx, None, None, bad)["ok"] is True, "the line is taken whole, so nothing is held"
    out, posts = _fit_offer(j2, monkeypatch, ctx, {"engines": ["Check"], "fit": {"Check": "alone"}, "why": "x"}, payload={"faults": ["x"]})
    sent = _covers_of(posts)
    assert [e["name"] for e in sent["engines"]] == LINE and "fit" not in sent, "the repair of a refused line has always been the whole line"


def test_f1_an_offline_department_proposes_and_registers_the_kinds_line_with_no_note(j2):
    W, R, J, _, _ = j2
    ref = _born_site(j2)
    sent = next(p["payload"] for p in R.board(ref) if p["src"] == "Adaptation" and p["dst"] == ["Priority"] and p["payload"].get("word") == "line")
    assert [e["name"] for e in sent["engines"]] == LINE and "fit" not in sent and not [e for e in sent["engines"] if "fit" in e]
    reg = W.dept(ref)["workflows"][-1]
    assert reg["engines"] == LINE and "fit" not in reg and reg["left_out"] == [] and reg["source"] == "library"
    fit_rows = [r for r in R.step_rows(ref) if r.get("step") == "adapt.fit"]
    assert fit_rows and all(r["status"] == "ok" and r["by"] == "offline draft" for r in fit_rows), fit_rows


def _born_site(j2, words=WEBSITE, org="Acme Learning", answers=None, monkeypatch=None, items=None):
    """A website department as a person makes one: found the organisation, say the words, Root sets it up, and the motor
    runs until idle. With `answers` a model that is a function stands in for each step id they name; with `items` done-when
    holds them before the department's own motor first runs."""
    W, R, J, founding, FV = j2
    seen = _stub(monkeypatch, R, answers) if answers is not None else None
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    if items:
        W.put_done_items(ref, items)
    W.run_until_idle(ref, limit=300)
    return (ref, seen) if answers is not None else ref


ONE_PAGE = WEBSITE + ". One page only."
ONE_PLAN = {"site_name": "Algebra, Class 8", "tagline": "One page of algebra", "palette": {"primary": "#0f5e7a", "accent": "#c4956a"},
            "pages": [{"slug": "index", "title": "Algebra", "purpose": "the one page", "sections": ["Algebra"]}]}
ONE_PAGE_BODY = {"title": "Algebra", "body_html": "<section><h1>Algebra for Class 8</h1><p>One page that teaches the first steps of algebra to students of Class 8.</p></section>"}
PLAN_NOTE, WRITE_NOTE = "plan that one page and no other", "write the one page; link to no other"


def test_j1_b4_adaptation_fits_the_templates_line_before_the_first_run(j2, monkeypatch):
    """J1 row B4 (A3): between birth and the first run, adapt.fit may only narrow the template's engines; the engines the kind
    marks required (Check) stay. 'One page only' leaves the last engine out, and Plan and Write are handed their notes."""
    W, R, J, _, _ = j2
    fit = {"engines": ["Plan", "Write", "Check"], "fit": {"Plan": PLAN_NOTE, "Write": WRITE_NOTE}, "why": "one page needs no publish step of its own"}
    ref, seen = _born_site(j2, ONE_PAGE, answers={"adapt.fit": fit, "plan.pages": ONE_PLAN, "write.page": ONE_PAGE_BODY}, monkeypatch=monkeypatch)
    d = W.dept(ref)
    reg = d["workflows"][-1]
    assert reg["engines"] == ["Plan", "Write", "Check"] and set(reg["engines"]) <= set(LINE), "only narrowed, never added to"
    assert [n for n in LINE if n in reg["engines"]] == reg["engines"], "in the template's order"
    assert "Check" in reg["engines"] and reg["left_out"] == ["Publish"] and reg["source"] == "library"
    assert reg["fit"] == {"Plan": PLAN_NOTE, "Write": WRITE_NOTE}, "the registration copies the notes"
    assert S.validate("workflow.registration", reg) == []
    acts = [e["action"] for e in J.events(ref)]
    assert acts.index("workflow.registered") < acts.index("run.started"), "fitted between birth and the first run"
    ran = [r["engine"] for r in W.runs(ref) if not r.get("system")]
    assert ran[:3] == ["Plan", "Write", "Check"] and "Publish" not in ran, ran
    # the prompts of the engines handed a note hold it, once, and Write's holds its own and not Plan's
    plan_prompt = next(p for sid, p in seen if sid == "plan.pages")
    write_prompt = next(p for sid, p in seen if sid == "write.page")
    assert plan_prompt.endswith("\n\nFOR THIS GOAL: " + PLAN_NOTE) and write_prompt.count("FOR THIS GOAL: " + WRITE_NOTE) == 1
    assert PLAN_NOTE not in write_prompt and WRITE_NOTE not in plan_prompt


def test_f1_one_page_only_keeps_check_and_a_fit_naming_an_engine_outside_the_line_is_refused_naming_it(j2):
    ctx = _fit_ctx(j2)
    assert _fitted(ctx, ["Check"], {"Check": "one page only"})["ok"] is True
    got = _fitted(ctx, ["Check"], {"Check": "one page only", "Banner": "a banner"})
    assert got["ok"] is False and got["notes"] == ["fit has a note for Banner, which is no engine of the line"]
    assert _fitted(ctx, ["Plan", "Write"], {})["notes"] == ["the line leaves out Check, which this kind of department requires"]


def test_f1_an_unsound_fit_from_a_model_never_blocks_the_department_it_gets_the_librarys_line(j2, monkeypatch):
    W, R, J, _, _ = j2
    bad = {"engines": ["Plan", "Write", "Gallery"], "fit": {"Gallery": "a photo gallery"}, "why": "x"}
    ref, seen = _born_site(j2, ONE_PAGE, answers={"adapt.fit": bad}, monkeypatch=monkeypatch)
    assert [sid for sid, _ in seen].count("adapt.fit") >= 1
    reg = W.dept(ref)["workflows"][-1]
    assert reg["engines"] == LINE and "fit" not in reg, "the Library's line, whole"
    assert not [a for a in W.asks(ref) if a["kind"] == "blocked" and a["status"] == "pending"], "nobody is asked, nothing is blocked"
    assert [r for r in R.step_rows(ref) if r.get("step") == "adapt.fit" and r["status"] == "failed"], "the refusal is on the record"


def test_f1_a_prompt_with_no_note_is_what_it_always_was(j2):
    W, R, J, _, _ = j2
    ref = _born_site(j2)
    for engine in ("Plan", "Write"):
        assert R._fit_note(ref, engine) == ""
    assert R._context_block(ref) == R._context_block(ref, "Plan") == R._context_block(ref, "Write")


def test_f1_a_note_is_handed_to_the_engine_it_is_for_and_no_other_and_audit_never_reads_it(j2):
    W, R, J, _, _ = j2
    ref = _born_site(j2)
    d = W.dept(ref)
    d["workflows"][-1]["fit"] = {"Write": "  one   page\nonly "}
    W.save_dept(ref, d)
    assert R._fit_note(ref, "Write") == "\n\nFOR THIS GOAL: one page only" and R._fit_note(ref, "Plan") == ""
    assert R._context_block(ref, "Write").endswith("\n\nFOR THIS GOAL: one page only")
    assert "FOR THIS GOAL" not in R._context_block(ref), "Audit's reading of what was filed carries no note"


# ---- F2 · conflicts carry Priority's options (W2-ADAPT, M5.4) ---------------------------------------------------------
def _ways_out(W):
    """The three ways out Priority prices for a no (M5.4): raise the envelope, leave an item out, stop. Built as W.option builds them."""
    raise_ = W.option("raise", "Add 2.00 USD for Plan", "about 2.00 USD more a day, up to twice where it started",
                      params={"what": "envelope", "engine": "Plan", "calls": 30, "usd": 2.0})
    return [raise_, W.option("leave:D1", "Leave D1 out", "D1 is dropped from done-when; nothing more is spent"),
            W.option(W.STOP_OPTION, "Stop here", "the department stops where it is; you can start it again later")]


def _priority_sends_options(monkeypatch, R, options, words=("line",)):
    """Priority as W2-PRIORITY makes it, for a no or an ask for less on a line: the answer carries the ways out it priced."""
    real = R.post

    def post(ref, src, dst, msg_type, payload=None, *a, **kw):
        if src == "Priority" and msg_type in ("reject-proposal", "propose") and (payload or {}).get("word") in words:
            payload = dict(payload, options=options)
        return real(ref, src, dst, msg_type, payload, *a, **kw)
    monkeypatch.setattr(R, "post", post)


def _conflicts(R, ref):
    return [p["payload"] for p in R.board(ref) if p["src"] in ("Adaptation", "Coordination") and p["dst"] == ["Identity"] and p["payload"].get("word") == "conflict"]


def test_f2_a_no_that_carries_options_reaches_identity_with_them(j2, monkeypatch):
    W, R, J, _, _ = j2
    opts = _ways_out(W)
    _priority_sends_options(monkeypatch, R, opts)
    ref, _ = _born_site(j2, answers={"priority.bargain": {"answer": "reject", "why": "no room in the envelope today"}}, monkeypatch=monkeypatch)
    [conflict] = _conflicts(R, ref)
    assert conflict["options"] == opts and [o["kind"] for o in conflict["options"]] == ["raise", "leave", "stop"]
    assert conflict["why"] == "Priority said no to the plan: no room in the envelope today"
    assert S.validate("act.conflict", conflict) == [], "the act fits the interface, three typed options"
    sent = next(p["payload"] for p in R.board(ref) if p["src"] == "Priority" and p["msg_type"] == "reject-proposal")
    assert sent["options"] == opts, "what Priority sent is what Adaptation passed on"


def test_f2_an_ask_for_less_that_cannot_be_taken_reaches_identity_with_the_options_too(j2, monkeypatch):
    W, R, J, _, _ = j2
    opts = _ways_out(W)
    _priority_sends_options(monkeypatch, R, opts)
    # Priority asks to keep Plan -> Write -> Publish: it leaves out Check, which a website requires, so Identity closes it
    counter = {"answer": "counter", "why": "room for three today", "keep": ["Plan", "Write", "Publish"]}
    ref, _ = _born_site(j2, answers={"priority.bargain": counter}, monkeypatch=monkeypatch)
    [conflict] = _conflicts(R, ref)
    assert "leave out Check, which this kind of department requires" in conflict["why"] and conflict["options"] == opts
    assert S.validate("act.conflict", conflict) == []


def _priority_sends_no_options(monkeypatch, R):
    """Priority as it was before it priced ways out: its answers carry none (the real handler of W2-PRIORITY sends them)."""
    real = R.post

    def post(ref, src, dst, msg_type, payload=None, *a, **kw):
        if src == "Priority" and isinstance(payload, dict) and "options" in payload:
            payload = {k: v for k, v in payload.items() if k != "options"}
        return real(ref, src, dst, msg_type, payload, *a, **kw)
    monkeypatch.setattr(R, "post", post)


def test_f2_no_options_from_priority_is_a_conflict_with_none_as_it_always_was(j2, monkeypatch):
    W, R, J, _, _ = j2
    _priority_sends_no_options(monkeypatch, R)
    ref, _ = _born_site(j2, answers={"priority.bargain": {"answer": "reject", "why": "no room in the envelope today"}}, monkeypatch=monkeypatch)
    [conflict] = _conflicts(R, ref)
    assert "options" not in conflict and conflict["why"].startswith("Priority said no to the plan")


def test_f2_only_options_that_fit_the_interface_are_passed_on_and_at_most_three(j2):
    W = j2[0]
    good = _ways_out(W)
    assert v1().options_of({"options": good}) == good
    assert v1().options_of({"options": good + [W.option("words", "Say it in my words", "free")]}) == good, "at most three"
    assert v1().options_of({"options": [{"id": "Not An Id", "label": "x", "cost": "y"}, good[1], "stop", None]}) == [good[1]], "what is not an option is not passed on"
    for nothing in ({}, {"options": []}, {"options": "stop"}, {"options": [{"id": "stop"}]}, None):
        assert v1().options_of(nothing) is None


def test_f2_a_kept_engine_keeps_its_note_when_priority_asks_for_less_and_a_dropped_one_takes_its_note_away(j2, monkeypatch):
    W, R, J, _, _ = j2
    notes = {"Write": "one page, no gallery", "Publish": "put the page live at once"}
    fit = {"engines": LINE, "fit": notes, "why": "one page"}
    counter = {"answer": "counter", "why": "room for three today", "keep": ["Plan", "Write", "Check"]}
    ref, seen = _born_site(j2, ONE_PAGE, answers={"adapt.fit": fit, "priority.bargain": counter}, monkeypatch=monkeypatch)
    again = [p["payload"] for p in R.board(ref) if p["src"] == "Adaptation" and p["dst"] == ["Priority"] and p["payload"].get("word") == "line"]
    assert [[e["name"] for e in pl["engines"]] for pl in again] == [LINE, ["Plan", "Write", "Check"]]
    assert again[0]["fit"] == notes and again[1]["fit"] == {"Write": notes["Write"]}, "the dropped engine's note goes with it"
    assert [e.get("fit") for e in again[1]["engines"]] == [None, notes["Write"], None]
    reg = W.dept(ref)["workflows"][-1]
    assert reg["engines"] == ["Plan", "Write", "Check"] and reg["fit"] == {"Write": notes["Write"]} and reg["left_out"] == ["Publish"]
    assert S.validate("workflow.registration", reg) == []


LIMIT_ITEMS = [{"id": "D1", "text": "Every page checked and live", "how": "code", "level": "outcome"},
               {"id": "D2", "text": "The lessons for each topic are there", "how": "model", "level": "target"}]


def _one_blocked_card(W, ref):
    cards = [a for a in W.asks(ref) if a["status"] == "pending"]
    assert [a["kind"] for a in cards] == ["blocked"], cards
    return cards[0]


def test_f2_a_bargain_that_reaches_its_hop_limit_as_adaptation_takes_an_ask_for_less_reaches_the_owner_once_with_priced_ways(j2, monkeypatch):
    """M5.4 at its limit, through the branch of adapt_line_counter that used to carry options nothing could reach: the post that
    takes Priority's ask for less is the one the bound stops (two hops, and it is the third). The conflict is raised once, with the
    ways Priority prices for a limit, and Identity puts the owner one card that holds them."""
    W, R, J, _, _ = j2
    monkeypatch.setattr(R, "BOUNDS", {"hops": 2, "seconds": 900, "usd": 0.5})
    counter = {"answer": "counter", "why": "room for three today", "keep": ["Plan", "Write", "Check"]}
    ref, _ = _born_site(j2, answers={"priority.bargain": counter}, monkeypatch=monkeypatch, items=LIMIT_ITEMS)
    [conflict] = _conflicts(R, ref)
    assert conflict["bound"] == "hops" and [o["id"] for o in conflict["options"]] == ["leave:D2", "stop"], conflict
    assert S.validate("act.conflict", conflict) == [] and [e["name"] for e in conflict["engines"]] == LINE, "the line the bargain was about"
    card = _one_blocked_card(W, ref)
    assert [(o["id"], o["cost"]) for o in card["options"]] == [(o["id"], o["cost"]) for o in conflict["options"]], "the card has the priced ways"
    assert W.dept(ref).get("workflows") in ([], None) and [r for r in W.runs(ref) if not r.get("system")] == [], "nothing was registered and nothing ran"
    assert len([e for e in J.events(ref) if e["action"] == "conflict.raised"]) == 1


def test_f2_the_conflict_adaptation_files_at_a_bound_carries_the_ways_priority_prices_and_is_filed_once(j2, monkeypatch):
    """The fallback branch of adapt_line_counter (a department the runtime did not raise the conflict for) files the same conflict
    the runtime would: ways priced by Priority, once. Its own ask for less brings none."""
    W, R, J, _, _ = j2
    monkeypatch.setattr(R, "BOUNDS", {"hops": 1, "seconds": 900, "usd": 0.5})
    monkeypatch.setattr(R, "_j2_live", lambda r: False)                    # the runtime raises no conflict where it closes the thread
    ref, _ = _born_site(j2, answers={"priority.bargain": {"answer": "accept", "why": "fits"}}, monkeypatch=monkeypatch, items=LIMIT_ITEMS)
    assert _conflicts(R, ref) == [], "the runtime raised none: the bound closed the thread in silence"
    thread = next(p["thread"] for p in R.board(ref) if p["src"] == "Adaptation" and p["msg_type"] == "propose")
    monkeypatch.setattr(R, "_j2_live", lambda r: True)
    row = v1().line_conflict(ref, thread, "the bargain reached its bound", bound="hops", src="Coordination")
    [conflict] = _conflicts(R, ref)
    assert row and conflict["options"] == R._limit_ways(ref, thread) and [o["id"] for o in conflict["options"]] == ["leave:D2", "stop"]
    assert v1().line_conflict(ref, thread, "the bargain reached its bound", bound="hops", src="Coordination") is None and len(_conflicts(R, ref)) == 1
    own = v1().line_conflict(ref, "x-other", "Priority said no", options=[W.option(W.STOP_OPTION, "Stop here", "it stops")])
    assert own["payload"]["options"][0]["id"] == "stop", "ways given are the ways carried; Priority's limit ways are asked for only when none are given"


def test_f2_the_two_handlers_are_the_layers_own_now_and_the_runtimes_copies_are_deleted(j2):
    R = j2[1]
    for name in ("adapt_line_refused", "adapt_line_counter"):
        assert not hasattr(v1().CODE[name], "legacy"), "%s is a body of the layer's own" % name
        assert not hasattr(R, name) and name not in R.CODE, "and engine_runtime's copy is gone (W3-PROOF X1): the layer is the one body"


# ---- F3 · propose the next round (W2-ADAPT, M9.1, M9.4) ---------------------------------------------------------------
LINE_COST = {"calls": 8, "usd": 0.36, "basis": "median", "runs": 3,
             "per_engine": {n: {"calls": 2, "usd": 0.09, "basis": "median", "runs": 3} for n in LINE}}
D2_CLAIM = "the doctors page does not name the phone line"
RID = "r-0a1b2c3d"


def _reading_row(W, rid=RID, v=1, not_met=("D2",), claim=D2_CLAIM):
    """What Audit files (audit.reading) when D1 holds, D3 is for the owner to confirm and the items named do not."""
    rows = [{"id": "D1", "subject": "Live site", "claim": "the site is served", "evidence": "the live site passed its check", "method": "code",
             "verdict": "met", "severity": "low"},
            {"id": "D3", "subject": "doctors", "claim": "a visitor can find the doctors", "evidence": "the menu names them", "method": "model",
             "verdict": "met", "severity": "low"}]
    rows += [{"id": i, "subject": "doctors", "claim": claim, "evidence": "doctors.html has no number", "method": "model", "verdict": "not_met",
              "severity": "high"} for i in not_met]
    return {"schema_version": 1, "id": rid, "v": v, "artifact": "Live site", "cycle_id": None, "round": None, "read": True, "why_not_read": None,
            "items": sorted(rows, key=lambda r: r["id"]),
            "findings": [{"id": "F%d" % n, "severity": "high", "claim": claim, "where": "doctors", "item": i, "went_to": "Identity"}
                         for n, i in enumerate(not_met, 1)], "at": W.now()}


def _pursuing(j2, ref="dref-pursue", items=ITEMS):
    """A website department with its line registered, Priority's price for that line on its record, and the reading that found D2
    not met: everything the next round reads, with no run in the way."""
    W, R, J, _, _ = j2
    _dept(j2, "website", ref=ref, items=items, name="Pursue Dept")
    d = W.dept(ref)
    d["engines"] = list(LINE)
    d["workflows"] = [{"version": 1, "engines": LINE, "source": "library", "registered": W.now(), "by": "Root"}]
    W.save_dept(ref, d)
    W.append_row(ref, "prices.jsonl", {"schema_version": 1, "id": "pr-0000fix1", "at": W.now(), "cycle_id": None, "round": None, "proposal": "line",
                                       "engines": LINE, "estimate": LINE_COST, "room": {"calls": 120, "usd": 24.0}, "remaining": {"calls": 112, "usd": 23.64},
                                       "answer": "accept", "keep": [], "why": "fits today", "indices": {"spend_per_run": {}, "checks": {}}})
    W.append_row(ref, "readings.jsonl", _reading_row(W))
    return ref


def _ask_next(R, ref, items=("D2",), reading=RID, findings=("F1",), **more):
    """Identity asks Adaptation for the next round, as W2-IDENTITY will after a reading that is not done (act.next)."""
    return R.post(ref, "Identity", "Adaptation", "request", dict({"word": "next", "items": list(items), "reading": reading, "findings": list(findings)}, **more))


def _round_posts(R, ref):
    return [p for p in R.board(ref) if p["src"] == "Adaptation" and p["dst"] == ["Priority"] and p["msg_type"] == "propose" and p["payload"].get("word") == "round"]


def _rows(W, ref):
    return W.rows(ref, "rounds.jsonl")


def test_f3_a_reading_with_d2_not_met_gives_one_round_naming_d2_with_the_line_cost_priority_observed(j2):
    W, R, J, _, _ = j2
    ref = _pursuing(j2)
    assert _ask_next(R, ref)
    W.run_until_idle(ref, limit=100)
    [sent] = _round_posts(R, ref)
    pl = sent["payload"]
    assert pl["round"] == 1 and pl["covers"] == ["D2"] and pl["fixes"] == ["F1"], pl
    assert "D2" in pl["correction"] and D2_CLAIM in pl["correction"], "it names the item and what Audit found"
    assert pl["estimate"] == LINE_COST, "the estimate is the cost on Priority's latest price row for the line, as it is"
    assert S.validate_act("Adaptation", ["Priority"], "propose", pl) == [] and S.validate("act.round", pl) == []
    first = _rows(W, ref)[0]
    assert (first["round"], first["status"], first["thread"], first["reading"]) == (1, "proposed", sent["thread"], RID)
    assert first["covers"] == ["D2"] and first["estimate"] == LINE_COST and S.validate("adaptation.round", first) == []
    d = W.dept(ref)
    assert len(d["workflows"]) == 1 and d["engines"] == LINE, "a round never registers a line"
    assert not [p for p in R.board(ref) if (p["payload"] or {}).get("word") == "line"], "and proposes none"


def test_f3_priority_saying_yes_moves_the_round_to_granted_and_the_fold_keeps_the_latest_row(j2):
    W, R, J, _, _ = j2
    ref = _pursuing(j2)
    _ask_next(R, ref)
    W.run_until_idle(ref, limit=100)
    rows = _rows(W, ref)
    filed = ["filed"] if v1().hears_round() else []                                   # Identity files a granted round once its recipe hears one (W2-IDENTITY, M9.3)
    assert [r["status"] for r in rows] == ["proposed", "granted"] + filed and rows[0]["thread"] == rows[1]["thread"]
    assert [(r["round"], r["status"]) for r in v1().rounds_of(ref)] == [(1, (filed or ["granted"])[0])], "folded by round, the latest status winning"
    assert [r for r in R.board(ref) if r["src"] == "Priority" and r["msg_type"] == "accept-proposal" and r["payload"].get("word") == "round"]
    told = [p for p in R.board(ref) if p["src"] == "Adaptation" and p["dst"] == ["Identity"] and p["payload"].get("word") == "round"]
    assert bool(told) == v1().hears_round(), "Identity is told to file it once its recipe hears a round, and not before (A1-14)"
    for p in told:
        assert p["payload"]["round"] == 1 and p["payload"]["covers"] == ["D2"] and p["payload"]["estimate"] == LINE_COST
        assert S.validate_act("Adaptation", ["Identity"], "inform", p["payload"]) == []


def _round_in_hand(j2, ref="dref-pursue", **ask):
    """Round 1 proposed and not yet answered: the three steps run as the recipe runs them, with no motor in between, so a test can
    answer it as Priority."""
    W, R, J, _, _ = j2
    ref = _pursuing(j2, ref)
    post = _ask_next(R, ref, **ask)
    ctx = {"ref": ref, "dept": W.dept(ref), "engine": "Adaptation", "post": post, "bag": {}, "how": {}}
    ctx["bag"]["adapt.hearnext"] = v1().CODE["adapt_hearnext"](ctx, None, None)
    ctx["bag"]["adapt.next"] = v1().DRAFT["adapt_next_draft"](ctx, None, None)
    out = v1().CODE["adapt_round"](ctx, None, None)
    return ref, out, _rows(W, ref)[-1]


def _answer(j2, ref, thread, act, payload):
    W, R, _, _, _ = j2
    post = {"n": 99, "thread": thread, "src": "Priority", "msg_type": act, "payload": payload}
    ctx = {"ref": ref, "dept": W.dept(ref), "engine": "Adaptation", "post": post, "bag": {}, "how": {}}
    code = v1().CODE["adapt_round_granted" if act == "accept-proposal" else "adapt_round_refused"]
    return code(ctx, None, None)


def test_f3_priority_saying_no_moves_the_round_to_refused_and_it_becomes_a_conflict_with_the_ways_out_it_sent(j2, monkeypatch):
    W, R, J, _, _ = j2
    monkeypatch.setattr(v1(), "hears_round", lambda: True)
    ref, out, row = _round_in_hand(j2)
    opts = _ways_out(W)
    got = _answer(j2, ref, row["thread"], "reject-proposal", {"word": "round", "why": "round 7 of 6 is past the ceiling", "options": opts})
    assert "the conflict goes to Identity" in got["said"]
    assert [r["status"] for r in _rows(W, ref)] == ["proposed", "refused"]
    [conflict] = _conflicts(R, ref)
    assert conflict["options"] == opts and conflict["round"] == 1 and conflict["for"] == row["thread"] and conflict["engines"] == []
    assert conflict["why"] == "Priority said no to Round 1: round 7 of 6 is past the ceiling", "the round is a name on the card, as on the progress line"
    assert S.validate("act.conflict", conflict) == []
    again = _answer(j2, ref, row["thread"], "reject-proposal", {"word": "round", "why": "again", "options": opts})
    assert len(_conflicts(R, ref)) == 1 and [r["status"] for r in _rows(W, ref)] == ["proposed", "refused"], "a second no is the same no"


def test_f3_a_round_whose_proposal_the_bound_stopped_is_refused_on_the_record_and_told_to_identity_once(j2, monkeypatch):
    """adapt_round marked the row refused and told nobody when its post came back None (rule 12): Identity hears it once, with the
    ways out, and a bound the runtime already reported is not reported twice."""
    W, R, J, _, _ = j2
    monkeypatch.setattr(v1(), "hears_round", lambda: True)
    real = R.post

    def stopped(ref, src, dst, msg_type, payload=None, *a, **kw):
        return None if (src, dst, (payload or {}).get("word")) == ("Adaptation", "Priority", "round") else real(ref, src, dst, msg_type, payload, *a, **kw)
    monkeypatch.setattr(R, "post", stopped)
    ref, out, row = _round_in_hand(j2)
    assert "could not go to Priority" in out["said"] and [r["status"] for r in _rows(W, ref)] == ["proposed", "refused"]
    [conflict] = _conflicts(R, ref)
    assert (conflict["bound"], conflict["round"], conflict["correction"], conflict["for"], conflict["engines"]) == ("hops", 1, row["correction"], row["thread"], [])
    assert [o["kind"] for o in conflict["options"]] == ["words", "leave", "stop"] and S.validate("act.conflict", conflict) == []
    assert conflict["why"] == "Priority and Adaptation could not settle round 1 between them"
    assert v1().round_bound(ref, row["thread"], "hops") is None and len(_conflicts(R, ref)) == 1, "once, however often the bound is reported"
    assert [r["status"] for r in _rows(W, ref)] == ["proposed", "refused"]
    assert v1().round_bound(ref, "x-nobody", "seconds") is None and v1().round_bound(None, "x", "usd") is None, "a thread that is no round's, and a record that is not there: nothing"


def test_f3_until_identity_hears_a_round_a_round_at_its_bound_stays_on_the_record_and_posts_nothing(j2, monkeypatch):
    W, R, J, _, _ = j2
    monkeypatch.setattr(v1(), "hears_round", lambda: False)
    ref, out, row = _round_in_hand(j2)
    before = len(R.board(ref))
    assert v1().round_bound(ref, row["thread"], "seconds") is None and len(R.board(ref)) == before and [r["status"] for r in _rows(W, ref)] == ["proposed", "refused"]


def test_f3_until_identity_hears_a_round_a_refusal_and_a_grant_stay_on_the_record_and_post_nothing(j2, monkeypatch):
    W, R, J, _, _ = j2
    monkeypatch.setattr(v1(), "hears_round", lambda: False)
    ref, out, row = _round_in_hand(j2)
    before = len(R.board(ref))
    got = _answer(j2, ref, row["thread"], "reject-proposal", {"word": "round", "why": "no room", "options": _ways_out(W)})
    assert "stays on the record" in got["said"] and len(R.board(ref)) == before and [r["status"] for r in _rows(W, ref)] == ["proposed", "refused"]
    ref2, _, row2 = _round_in_hand(j2, ref="dref-pursue-two")
    before = len(R.board(ref2))
    got = _answer(j2, ref2, row2["thread"], "accept-proposal", {"word": "round", "why": "fits today"})
    assert "Identity does not take rounds yet" in got["said"] and len(R.board(ref2)) == before and _rows(W, ref2)[-1]["status"] == "granted"


def test_f3_a_round_nobody_proposed_is_heard_and_nothing_is_written(j2):
    W, R, J, _, _ = j2
    ref = _pursuing(j2)
    assert "nobody proposed" in _answer(j2, ref, "x-nobody", "accept-proposal", {"word": "round"})["said"]
    assert "nobody proposed" in _answer(j2, ref, "x-nobody", "reject-proposal", {"word": "round"})["said"]
    assert _rows(W, ref) == []


def test_f3_the_same_reading_asked_twice_is_one_round(j2):
    W, R, J, _, _ = j2
    ref, out, row = _round_in_hand(j2)
    post = _ask_next(R, ref)
    ctx = {"ref": ref, "dept": W.dept(ref), "engine": "Adaptation", "post": post, "bag": {}, "how": {}}
    ctx["bag"]["adapt.hearnext"] = v1().CODE["adapt_hearnext"](ctx, None, None)
    ctx["bag"]["adapt.next"] = v1().DRAFT["adapt_next_draft"](ctx, None, None)
    again = v1().CODE["adapt_round"](ctx, None, None)
    assert again["said"] == "round 1 is already with Priority for this reading" and len(_round_posts(R, ref)) == 1 and len(_rows(W, ref)) == 1


def test_f3_what_adaptation_hears_is_the_items_that_are_in_done_when_what_audit_found_the_line_and_the_number(j2):
    W, R, J, _, _ = j2
    ref = _pursuing(j2)
    post = {"n": 1, "thread": "x-n", "src": "Identity", "msg_type": "request",
            "payload": {"word": "next", "items": ["D2", "D9", "D2"], "reading": RID, "findings": ["F1", "F8"]}}
    ctx = {"ref": ref, "dept": W.dept(ref), "engine": "Adaptation", "post": post, "bag": {}}
    got = v1().CODE["adapt_hearnext"](ctx, None, None)
    assert [i["id"] for i in got["items"]] == ["D2"], "D9 is not in done-when, and D2 is named once"
    assert got["items"][0]["text"] == "Every page names the phone line" and got["items"][0]["claim"] == D2_CLAIM
    assert [(f["id"], f["item"]) for f in got["findings"]] == [("F1", "D2")] and got["line"] == LINE
    assert got["round"] == 1 and got["last"] is None and got["reading"] == RID
    assert got["facts"] == {"from": "Identity", "act": "request", "word": "next", "items": "D2", "repeat": False}
    assert R.CHECK["facts_are_closed"](ctx, None, None, got)["ok"] is True, "the unit starts with code, and its facts are closed"
    post["payload"]["round"] = 5
    assert v1().CODE["adapt_hearnext"](ctx, None, None)["round"] == 5, "the number Identity gives is kept when it is later than the next"
    post["payload"].update({"items": ["D9"], "reading": "r-ffffffff", "findings": []})
    none = v1().CODE["adapt_hearnext"](ctx, None, None)
    assert none["items"] == [] and none["reading"] == "r-ffffffff" and "no item that done-when has" in none["said"]


def test_f3_the_numbers_of_the_rounds_follow_each_other_and_start_again_with_a_cycle(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _pursuing(j2)
    base = {"schema_version": 1, "at": W.now(), "correction": "x", "covers": ["D2"], "status": "granted"}
    W.append_row(ref, "rounds.jsonl", dict(base, round=1, cycle_id="c-one"))
    W.append_row(ref, "rounds.jsonl", dict(base, round=2, cycle_id="c-one"))
    monkeypatch.setattr(v1(), "cycle_of", lambda r: "c-one")
    assert v1().next_number(ref, {}) == 3 and [r["round"] for r in v1().rounds_of(ref)] == [1, 2]
    monkeypatch.setattr(v1(), "cycle_of", lambda r: "c-two")
    assert v1().next_number(ref, {}) == 1 and v1().rounds_of(ref) == [], "the goal changed: a new cycle's first round is round 1"
    assert v1().next_number(ref, {"round": 99}) == 99 and v1().next_number(ref, {"round": 120}) == 1 and v1().next_number(ref, {"round": True}) == 1, \
        "a number outside 1 to 99 is not one Identity gave"


def test_f3_a_round_priority_would_not_pay_for_keeps_its_number_and_is_proposed_again_as_the_same_round(j2, monkeypatch):
    """M9.1, M9.2 (found by a verifier 2026-10-27): the number counted the refused round as used, so asking again after the owner added
    room was round 3 against a ceiling of 2, refused again. The fold by (cycle, round) already lets the latest row win."""
    W, R, J, _, _ = j2
    ref = _pursuing(j2)
    base = {"schema_version": 1, "at": W.now(), "correction": "x", "covers": ["D2"], "cycle_id": "c-one"}
    monkeypatch.setattr(v1(), "cycle_of", lambda r: "c-one")
    W.append_row(ref, "rounds.jsonl", dict(base, round=1, status="granted"))
    W.append_row(ref, "rounds.jsonl", dict(base, round=2, status="refused", thread="x-two"))
    assert v1().next_number(ref, {}) == 2, "round 2 never ran: it is still the next round"
    assert v1().next_number(ref, {"round": 2}) == 2 and v1().next_number(ref, {"round": 4}) == 4, "the number Identity gives is kept when later"
    W.append_row(ref, "rounds.jsonl", dict(base, round=2, status="proposed", thread="x-two-again"))
    assert v1().next_number(ref, {}) == 3, "proposed again, it is used"
    assert [(r["round"], r["status"]) for r in v1().rounds_of(ref)] == [(1, "granted"), (2, "proposed")], "one row for the round, the latest"
    W.append_row(ref, "rounds.jsonl", dict(base, round=2, status="refused", thread="x-two-again"))
    assert v1().next_number(ref, {}) == 2, "and refused again, it is the next round again"


@pytest.mark.parametrize("text, says", [
    ("Put the phone line on the doctors page", "already failed in round 1"),                      # the one that failed, as it was
    ("put the phone line on the doctors page.", "already failed in round 1"),                     # in lower case and with a full stop
    ("  PUT   the phone line, on the doctors page!! ", "already failed in round 1"),            # and with other spaces and marks
    ("Put the phone line on the doctors page and the contact page", None),
    ("Add the phone line to the footer of every page", None),
    ("", "a round says what to correct"), ("   ", "a round says what to correct"), (None, "a round says what to correct"),
    (7, "a round says what to correct")])
def test_f3_a_correction_equal_in_its_words_to_the_one_that_failed_is_refused_and_a_new_one_passes(text, says):
    ctx = {"bag": {"adapt.hearnext": {"items": [{"id": "D2"}], "last": {"round": 1, "correction": "Put the phone line on the doctors page"}}}}
    got = v1().CHECK["round_is_new"](ctx, None, None, {"correction": text, "fixes": [], "covers": ["D2"], "why": "x"})
    assert got["ok"] is (says is None), got
    if says:
        assert says in got["notes"][0]
    else:
        assert got["notes"] == ["a correction that is new for D2"]


def test_f3_with_nothing_that_failed_any_correction_with_words_is_new_and_the_check_needs_no_department():
    for ctx in (None, {}, {"bag": {}}, {"bag": {"adapt.hearnext": {"items": [], "last": None}}}):
        assert v1().CHECK["round_is_new"](ctx, None, None, {"correction": "Put right D2"})["ok"] is True
    assert v1().CHECK["round_is_new"](None, None, None, "not an object")["ok"] is False


def _granted_round(W, ref, correction, n=1, covers=("D2",), cycle=None):
    W.append_row(ref, "rounds.jsonl", {"schema_version": 1, "round": n, "at": W.now(), "cycle_id": cycle, "correction": correction, "fixes": ["F1"],
                                       "covers": list(covers), "estimate": LINE_COST, "status": "granted", "thread": "x-r%d" % n, "reading": RID})


FIRST_TRY = "Put the phone line on the doctors page"


def test_f3_the_same_failure_twice_gives_a_different_correction_and_the_agent_is_told_the_last_approach_failed(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _pursuing(j2)
    _granted_round(W, ref, FIRST_TRY)                                            # round 1 ran, and the next reading finds D2 not met again
    W.append_row(ref, "readings.jsonl", _reading_row(W, rid="r-1b2c3d4e", v=2))
    different = "Add the phone line to the footer of every page, the doctors page included"
    seen = _stub(monkeypatch, R, {"adapt.next": {"correction": different, "fixes": ["F1"], "covers": ["D2"], "why": "the first fix did not hold"}})
    _ask_next(R, ref, reading="r-1b2c3d4e")
    W.run_until_idle(ref, limit=100)
    [sent] = _round_posts(R, ref)
    assert sent["payload"]["round"] == 2 and sent["payload"]["correction"] == different
    prompt = next(p for sid, p in seen if sid == "adapt.next")
    assert "THE LAST ROUND: the last approach failed: " + FIRST_TRY in prompt and "D2: Every page names the phone line" in prompt
    assert [(r["round"], r["status"]) for r in v1().rounds_of(ref)] == [(1, "granted"), (2, "filed" if v1().hears_round() else "granted")]


def test_f3_offline_the_draft_is_a_numbered_other_try_so_it_is_never_the_approach_that_failed(j2):
    W, R, J, _, _ = j2
    ref = _pursuing(j2)

    def draft():
        post = {"n": 1, "thread": "x-d", "src": "Identity", "msg_type": "request", "payload": {"word": "next", "items": ["D2"], "reading": RID, "findings": ["F1"]}}
        ctx = {"ref": ref, "dept": W.dept(ref), "engine": "Adaptation", "post": post, "bag": {}}
        ctx["bag"]["adapt.hearnext"] = v1().CODE["adapt_hearnext"](ctx, None, None)
        out = v1().DRAFT["adapt_next_draft"](ctx, None, None)
        assert v1().CHECK["round_is_new"](ctx, None, None, out)["ok"] is True, "the draft passes the check it stands behind"
        return out["correction"]
    first = draft()
    assert first == "Put right D2: Every page names the phone line. Audit found: " + D2_CLAIM
    _granted_round(W, ref, first, n=1)
    second = draft()
    assert second.startswith("Try another way, attempt 2.") and words_differ(second, first)
    _granted_round(W, ref, second, n=2)
    third = draft()
    assert third.startswith("Try another way, attempt 3.") and words_differ(third, second) and words_differ(third, first)


def words_differ(a, b):
    return v1().words_of(a) != v1().words_of(b)


def test_f3_a_round_that_priority_would_not_pay_for_did_not_fail_so_its_correction_may_be_said_again(j2):
    W, R, J, _, _ = j2
    ref = _pursuing(j2)
    W.append_row(ref, "rounds.jsonl", {"schema_version": 1, "round": 1, "at": W.now(), "cycle_id": None, "correction": FIRST_TRY, "fixes": [], "covers": ["D2"],
                                       "status": "refused", "thread": "x-r1"})
    assert v1().failed_round(ref, ["D2"]) is None
    _granted_round(W, ref, "Another", n=2)
    assert v1().failed_round(ref, ["D2"])["correction"] == "Another" and v1().failed_round(ref, ["D3"]) is None, "only for the same items"


def test_f3_a_model_that_says_the_failed_correction_again_ends_in_one_question_to_identity_with_three_ways_out(j2, monkeypatch):
    """The covering refuses the repeat and the step fails; the department does not go quiet: Identity is put one conflict with the
    owner's own words, leaving the item out, and stopping as the ways out (M9.4's limit question)."""
    W, R, J, _, _ = j2
    monkeypatch.setattr(v1(), "hears_round", lambda: True)
    ref = _pursuing(j2)
    _granted_round(W, ref, FIRST_TRY)
    _stub(monkeypatch, R, {"adapt.next": {"correction": FIRST_TRY.lower() + ".", "fixes": ["F1"], "covers": ["D2"], "why": "again"}})
    _ask_next(R, ref)
    W.run_until_idle(ref, limit=100)
    assert _round_posts(R, ref) == [], "no second round for the approach that failed"
    failed = [r for r in R.step_rows(ref) if r.get("step") == "adapt.next" and r["status"] == "failed"]
    assert failed and "already failed in round 1" in failed[0]["why"]
    [conflict] = _conflicts(R, ref)
    assert [o["id"] for o in conflict["options"]] == ["words", "leave:D2", "stop"] and [o["kind"] for o in conflict["options"]] == ["words", "leave", "stop"]
    assert conflict["round"] == 2 and "Adaptation has no new way to put D2 right" in conflict["why"] and "already failed in round 1" in conflict["why"]
    assert conflict["why"] == "Adaptation has no new way to put D2 right: its only idea is the approach that already failed in round 1", \
        "the owner reads the reason, not the step's name nor the covering's note"
    assert "Say what to correct" not in conflict["why"] and "correction" not in conflict, "no step's name in it; no correction, for none was proposed"
    assert S.validate("act.conflict", conflict) == [] and conflict["engines"] == []
    assert [(r["round"], r["status"]) for r in v1().rounds_of(ref)] == [(1, "granted")], "nothing was written for a round that was not proposed"


def test_f3_the_reason_there_is_no_new_round_is_said_in_the_owners_words_whatever_the_run_noted(j2):
    W, R, J, _, _ = j2
    ref = _pursuing(j2)
    repeat = "Say what to correct: %s1 (Put the phone line on the doctors page); a round says something new" % v1().REPEATS
    assert v1().next_reason(ref, ["D2"], repeat) == "nothing it could say was new", "no round failed yet, so none is repeated"
    _granted_round(W, ref, FIRST_TRY)
    assert v1().next_reason(ref, ["D2"], repeat) == "its only idea is the approach that already failed in round 1"
    for note in ("Say what to correct: no answer that fits, on any rung", "failed: boom", "", None):
        assert v1().next_reason(ref, ["D2"], note) == "nothing it could say was new", note
    assert v1().next_reason(ref, ["D3"], repeat) == "nothing it could say was new", "the round that failed was for another item"


def test_f3_one_item_left_in_done_when_cannot_be_left_out_so_the_limit_question_has_two_ways_out(j2, monkeypatch):
    W, R, J, _, _ = j2
    monkeypatch.setattr(v1(), "hears_round", lambda: True)
    ref = _pursuing(j2, items=[dict(ITEMS[1], id="D1")])
    assert [o["kind"] for o in v1().next_options(W.dept(ref), ["D1"])] == ["words", "stop"]
    three = _pursuing(j2, "dref-pursue-three")
    assert [o["kind"] for o in v1().next_options(W.dept(three), ["D2"])] == ["words", "leave", "stop"]
    assert [o["kind"] for o in v1().next_options(W.dept(three), ["D9"])] == ["words", "stop"], "an item that is not there is not left out"


def test_f3_until_identity_hears_a_round_a_failed_next_posts_nothing(j2, monkeypatch):
    W, R, J, _, _ = j2
    monkeypatch.setattr(v1(), "hears_round", lambda: False)
    ref = _pursuing(j2)
    post = _ask_next(R, ref)
    before = len(R.board(ref))
    assert v1().next_failed(ref, W.dept(ref), post, "a step failed") is None and len(R.board(ref)) == before


def test_f3_a_round_is_asked_by_identity_alone_and_the_edges_are_the_boards(j2):
    W, R, J, _, _ = j2
    ref = _pursuing(j2)
    assert _ask_next(R, ref)
    assert R.may_post("Identity", ["Adaptation"], "request", ref) and R.may_post("Adaptation", ["Priority"], "propose", ref)
    assert R.may_post("Adaptation", ["Identity"], "inform", ref) and not R.may_post("Adaptation", ["Owner"], "inform", ref), "only Identity speaks to the owner"
    assert S.validate_act("Identity", ["Adaptation"], "request", {"word": "next", "items": []}), "act.next needs at least one item"


def test_f3_the_interface_hears_and_sends_the_round_and_the_recipe_has_the_handlers_for_it():
    hears = {(r["act"], r["word"]): r for r in S.hears("adaptation")}
    for pair, handler in ((("request", "next"), "Propose the next round"), (("accept-proposal", "round"), "Priority said yes to the round"),
                          (("reject-proposal", "round"), "Priority said no to the round")):
        assert hears[pair]["handler"] == handler and hears[pair]["via"] == "board"
    assert hears[("request", "next")]["from"] == ("Identity",) and hears[("request", "next")]["payload"] == "act.next"
    assert hears[("accept-proposal", "round")]["from"] == hears[("reject-proposal", "round")]["from"] == ("Priority",)
    sends = {(r["act"], r["words"]): r for r in S.SENDS["Adaptation"]}
    assert sends[("propose", ("round",))]["to"] == ("Priority",) and sends[("inform", ("round",))]["to"] == ("Identity",)
    assert {r["payload"] for r in S.SENDS["Adaptation"] if r["words"] == ("round",)} == {"act.round"}
    assert any(r["act"] == "request" and r["words"] == ("next",) and r["to"] == ("Adaptation",) for r in S.SENDS["Identity"])
    part = S.PROMPTS["adaptation"]["decide"]["next"]
    assert part["read_by"] == "adapt.next" and part["inputs"] == ("dept", "items", "findings", "line", "last") and set(part["fields"]) == {"task", "guidance"}
    assert part["returns"] == 'Return ONLY a JSON object: {"correction": "one line: what to correct", "fixes": ["F1"], "covers": ["D2"], "why": "one line"}.'
    assert ("adaptation", "decide", "next") in S.ADDED_PARTS and "round_is_new" in S.CHECKS["adaptation"]
    handler = next(h for h in layers.recipes()["Adaptation"]["on"] if h["name"] == "Propose the next round")
    assert [(s["id"], s["born"], s["nature"]) for s in handler["steps"]] == [("adapt.hearnext", "C2", "transform"), ("adapt.next", "C0", "decide"),
                                                                           ("adapt.round", "C2", "transform")]
    nxt = handler["steps"][1]
    assert (nxt["prompt"], nxt["draft"], nxt["check"]) == ("adapt_next", "adapt_next_draft", "round_is_new")
    assert nxt["out"] == {"correction": "str", "fixes": "list", "covers": "list", "why": "str"}


# ---- F4 · the rounds in the view (W2-ADAPT, M9.6) --------------------------------------------------------------------
def _pane(j2, ref):
    W, R, J, _, FV = j2
    return v1().view(ref, W.dept(ref), [], W.asks(ref))


def test_f4_the_view_validates_in_a_two_round_fixture_and_a_round_is_one_row_the_latest_status_winning(j2):
    W, R, J, _, FV = j2
    ref = _pursuing(j2)
    base = {"schema_version": 1, "cycle_id": None, "fixes": ["F1"], "covers": ["D2"], "estimate": LINE_COST, "reading": RID}
    W.append_row(ref, "rounds.jsonl", dict(base, round=1, at="2026-10-26T10:00:00+05:30", correction=FIRST_TRY, status="proposed", thread="x-r1"))
    W.append_row(ref, "rounds.jsonl", dict(base, round=1, at="2026-10-26T10:01:00+05:30", correction=FIRST_TRY, status="granted", thread="x-r1"))
    W.append_row(ref, "rounds.jsonl", dict(base, round=2, at="2026-10-26T10:30:00+05:30", correction="Add the phone line to every footer", status="proposed",
                                           thread="x-r2", reading="r-1b2c3d4e"))
    pane = _pane(j2, ref)
    assert S.validate_view("adaptation", pane) == [], S.validate_view("adaptation", pane)
    assert [(r["round"], r["status"], r["said"]) for r in pane["rounds"]] == [(1, "granted", "Priority said yes"), (2, "proposed", "asked Priority")]
    assert pane["round"] == pane["rounds"][-1] and pane["round"]["correction"] == "Add the phone line to every footer"
    assert pane["rounds"][0]["at"] == "2026-10-26T10:01:00+05:30" and pane["rounds"][0]["estimate"] == LINE_COST and pane["rounds"][0]["covers"] == ["D2"]
    # what the pane is read from is the journal as written: three rows, two rounds
    assert len(_rows(W, ref)) == 3 and len(pane["rounds"]) == 2
    for r in pane["rounds"]:
        assert S.validate("view.adaptation.round", r) == []


def test_f4_a_department_with_no_round_has_none_and_still_validates(j2):
    W, R, J, _, FV = j2
    ref = _pursuing(j2)
    pane = _pane(j2, ref)
    assert pane["round"] is None and pane["rounds"] == [] and S.validate_view("adaptation", pane) == []


def test_f4_each_status_has_the_owners_words_and_never_the_bargains_inside_ones(j2):
    for status, says in (("proposed", "asked Priority"), ("granted", "Priority said yes"), ("refused", "Priority said no"),
                         ("filed", "filed in the Brief"), ("read", "read by Audit")):
        assert v1().ROUND_SAID[status] == says
    assert set(v1().ROUND_SAID) == {"proposed", "granted", "refused", "filed", "read"} == set(S.DEFS["adaptation.round"]["properties"]["status"]["enum"])
    assert not re.search(r"grant|counter|refus", " ".join(v1().ROUND_SAID.values()), re.I)


#: what the pane says of a round a limit of its thread closed (rule 12), by the limit: Priority never answered it, so it did not say no
BOUND_SAID = {"seconds": "Priority did not answer in time", "usd": "Pricing it cost more than it may", "hops": "Priority and Adaptation could not settle it"}


def _propose_again(j2, ref):
    """The same reading asked for the round again, as the steps run it (no motor): a new row, proposed, on a thread of its own."""
    W, R, J, _, _ = j2
    post = _ask_next(R, ref, round=1)
    ctx = {"ref": ref, "dept": W.dept(ref), "engine": "Adaptation", "post": post, "bag": {}, "how": {}}
    ctx["bag"]["adapt.hearnext"] = v1().CODE["adapt_hearnext"](ctx, None, None)
    ctx["bag"]["adapt.next"] = v1().DRAFT["adapt_next_draft"](ctx, None, None)
    return v1().CODE["adapt_round"](ctx, None, None)


@pytest.mark.parametrize("bound", sorted(BOUND_SAID))
def test_f4_a_round_a_limit_closed_says_priority_did_not_answer_it_and_not_that_priority_said_no(j2, monkeypatch, bound):
    """Found by a verifier 2026-10-27: round_bound marked a round whose thread hit its time, spend or hop limit refused, and the
    pane read 'Priority said no' for a round Priority never answered (at the hop limit it may have said yes, the answer dropped).
    The row keeps which limit closed it, and the owner's words say that."""
    W, R, J, _, _ = j2
    monkeypatch.setattr(v1(), "hears_round", lambda: True)
    ref, out, row = _round_in_hand(j2)
    assert v1().round_bound(ref, row["thread"], bound) is not None
    stopped = _rows(W, ref)[-1]
    assert (stopped["status"], stopped["bound"], stopped["thread"]) == ("refused", bound, row["thread"]) and S.validate("adaptation.round", stopped) == []
    pane = _pane(j2, ref)
    assert S.validate_view("adaptation", pane) == []
    [shown] = pane["rounds"]
    assert (shown["round"], shown["status"], shown["said"]) == (1, "refused", BOUND_SAID[bound]) and pane["round"] == shown
    assert S.validate("view.adaptation.round", shown) == [] and len(shown["said"]) <= 60
    assert not re.search(r"said no|grant|counter|refus|\bbound\b|\bhops\b|\busd\b|\bseconds\b", shown["said"], re.I), shown["said"]


def test_f4_a_round_priority_really_said_no_to_keeps_saying_so_and_the_cause_of_an_earlier_try_does_not_outlive_it(j2, monkeypatch):
    W, R, J, _, _ = j2
    monkeypatch.setattr(v1(), "hears_round", lambda: True)
    ref, out, row = _round_in_hand(j2)
    # a real no from Priority: no limit on the row
    _answer(j2, ref, row["thread"], "reject-proposal", {"word": "round", "why": "no room", "options": _ways_out(W)})
    [said_no] = _pane(j2, ref)["rounds"]
    assert (said_no["status"], said_no["said"]) == ("refused", "Priority said no") and not _rows(W, ref)[-1].get("bound")
    # the round is asked for again, the limit of its new thread closes it: now it was never answered
    assert "proposed round 1" in _propose_again(j2, ref)["said"]
    again = _rows(W, ref)[-1]
    assert (again["status"], again["bound"]) == ("proposed", None) and again["thread"] != row["thread"]
    assert v1().round_bound(ref, again["thread"], "seconds") is not None
    assert [(r["round"], r["status"], r["said"]) for r in _pane(j2, ref)["rounds"]] == [(1, "refused", BOUND_SAID["seconds"])]
    # asked a third time, the limit of the second try is not carried to the third: when Priority really says no this time, it says no
    assert "proposed round 1" in _propose_again(j2, ref)["said"]
    third = _rows(W, ref)[-1]
    assert (third["status"], third["bound"]) == ("proposed", None)
    assert [(r["status"], r["said"]) for r in _pane(j2, ref)["rounds"]] == [("proposed", "asked Priority")]
    _answer(j2, ref, third["thread"], "reject-proposal", {"word": "round", "why": "still no room", "options": _ways_out(W)})
    assert [(r["status"], r["said"]) for r in _pane(j2, ref)["rounds"]] == [("refused", "Priority said no")]


def test_f4_a_round_a_limit_closed_and_asked_again_that_priority_then_says_yes_to_says_yes(j2, monkeypatch):
    W, R, J, _, _ = j2
    monkeypatch.setattr(v1(), "hears_round", lambda: True)
    ref, out, row = _round_in_hand(j2)
    v1().round_bound(ref, row["thread"], "hops")
    _propose_again(j2, ref)
    again = _rows(W, ref)[-1]
    _answer(j2, ref, again["thread"], "accept-proposal", {"word": "round", "why": "it fits"})
    assert [(r["status"], r["said"]) for r in _pane(j2, ref)["rounds"]] == [("granted", "Priority said yes")]


def test_f4_a_limit_the_view_has_no_words_for_still_says_the_round_was_not_settled_and_the_bound_words_are_the_owners(j2):
    assert set(v1().BOUND_ROUND_SAID) == set(v1().BOUND_SAYS) == set(BOUND_SAID) and dict(v1().BOUND_ROUND_SAID) == BOUND_SAID
    assert v1().round_said({"status": "refused", "bound": "weather"}) == "Priority and Adaptation could not settle it"
    assert v1().round_said({"status": "refused", "bound": None}) == "Priority said no" and v1().round_said({"status": "refused"}) == "Priority said no"
    assert v1().round_said({"status": "granted", "bound": "seconds"}) == "Priority said yes", "a limit means something only on a refused round"
    assert not re.search(r"grant|counter|refus|said no", " ".join(v1().BOUND_ROUND_SAID.values()), re.I)


def test_f4_only_the_rounds_of_the_cycle_the_department_is_in_are_shown(j2, monkeypatch):
    W, R, J, _, FV = j2
    ref = _pursuing(j2)
    _granted_round(W, ref, "old way", n=1, cycle="c-one")
    _granted_round(W, ref, "old way two", n=2, cycle="c-one")
    _granted_round(W, ref, "new way", n=1, cycle="c-two")
    monkeypatch.setattr(v1(), "cycle_of", lambda r: "c-two")
    pane = _pane(j2, ref)
    assert [(r["round"], r["correction"]) for r in pane["rounds"]] == [(1, "new way")] and pane["round"]["correction"] == "new way"
    monkeypatch.setattr(v1(), "cycle_of", lambda r: "c-one")
    assert [r["round"] for r in _pane(j2, ref)["rounds"]] == [1, 2]
    assert S.validate_view("adaptation", _pane(j2, ref)) == []


def test_f4_the_pane_a_function_page_reads_carries_the_rounds_through_the_layer(j2):
    W, R, J, _, FV = j2
    ref = _pursuing(j2)
    _granted_round(W, ref, FIRST_TRY)
    pane = FV.function(ref, "Adaptation")["j2"]
    assert [(r["round"], r["status"]) for r in pane["rounds"]] == [(1, "granted")] and pane["round"]["said"] == "Priority said yes"
    assert "j2_faults" not in pane, "the layer's view passed the interface, so the page did not fall back"


def test_f4_a_round_row_written_by_a_later_writer_with_a_status_the_pane_does_not_know_is_not_shown(j2):
    W, R, J, _, FV = j2
    ref = _pursuing(j2)
    path = W.ddir(ref) / "rounds.jsonl"
    path.write_text(json.dumps({"round": 1, "correction": "x", "covers": ["D2"], "status": "archived", "cycle_id": None}) + "\n", encoding="utf-8")
    pane = _pane(j2, ref)
    assert pane["rounds"] == [] and S.validate_view("adaptation", pane) == []
