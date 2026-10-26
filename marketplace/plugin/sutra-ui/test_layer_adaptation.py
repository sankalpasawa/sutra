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


# ---- A7 · the practices in place (M6.3) -------------------------------------------------------------------------------
FIVE = {"rules", "engines", "artifacts", "required", "taken"}


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


# ---- A4 · the proposal stage ------------------------------------------------------------------------------------------
GOOD = [{"name": "Facts 2", "does": "finds what the goal names, each fact with its source", "reads": "Brief", "writes": "Facts 2", "internet": True},
        {"name": "Site 2", "does": "writes the pages from the facts", "reads": "Facts 2", "writes": "Live site", "internet": False}]


class _Standards:
    """Root's standards as W1-ROOT's workflow_schema will run them, for the two the A4 cases need: reads_known fails the
    engine that reads what nothing before it wrote, and items_covered at the proposal stage is only a warning."""

    @staticmethod
    def run(wf, stage, dept=None, ctx=None):
        written, rows = {"Brief"}, []
        for e in wf["engines"]:
            if e["reads"] not in written:
                rows.append({"check": "reads_known", "passed": False, "why": "%s reads %s, which nothing before it wrote" % (e["name"], e["reads"])})
            written.add(e["writes"])
        rows.append({"check": "items_covered", "passed": True, "why": "warning: D3 is covered by no engine"})
        return rows


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
        assert mine == theirs, out
    assert v1().CHECK["line_is_engines"](ctx, None, None, {"engines": GOOD}) == \
        {"ok": True, "notes": ["2 engines, each reading what one before it wrote"]}


def test_a4_a_failed_standard_row_fails_the_line_naming_it_and_a_warning_row_passes(j2, monkeypatch):
    monkeypatch.setattr(S, "_workflow_schema", lambda: _Standards)
    ctx = _line_ctx(j2)
    got = v1().CHECK["line_is_engines"](ctx, None, None, {"engines": [GOOD[0], dict(GOOD[1], reads="Interviews")]})
    assert got["ok"] is False
    assert "Site 2 reads Interviews, which nothing before it writes" in got["notes"], "today's wording is kept"
    assert "reads_known: Site 2 reads Interviews, which nothing before it wrote" in got["notes"]
    assert not any(n.startswith("items_covered") for n in got["notes"]), "a warning row is no fault"
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
    assert legacy["ok"] is False and "the Library already has an engine named Plan" in legacy["notes"], "a draft is not made: the old rule"


def test_a8_a_reshape_keeps_the_engines_the_kind_requires_at_level_1(j2, monkeypatch):
    lib = [_made("Pages", "Brief", "Pages", ["D1", "D2"], confidence=0.9)]
    dropped = _verdict_of(j2, monkeypatch, "website", {"engines": lib})
    assert dropped["ok"] is False and "the plan leaves out Check, which this kind of department requires" in dropped["notes"]
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
    today = FV._j2_part(ref, d, "Adaptation", proposing, W.asks(ref))
    assert {k: got[k] for k in ("proposal", "root_checks", "rounds")} == today, "what it showed before is what it shows"


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
    partial = {"engines": [dict(GOOD[0], covers=["D1"]), dict(GOOD[1], covers=["D2"])]}
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
