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
