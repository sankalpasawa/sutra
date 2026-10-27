"""The artifact form on every write and the measurable website checks (PRD amendment A1: W2-CHECKS; M7.5, M8.6), one section a step.

  G1  a writer a Library engine reads files in the reader's form, and holds to it where it writes (J2B-3)
  G2  Audit's mechanical step finds the page defects a browser is not needed for, one finding for each

The departments in G1 are born the way a person makes them (found, say the words, Root sets up) with J2_ADAPT_MAKE on and a
stub in place of every model; a test that meets a fault of the interface fails through conftest.py, so a deliberate one is
wrapped in S.expect_refused().
"""
import importlib
import json
import re

import pytest

import layer_schema as S
import layers
import layers.contract as C

WEBSITE = "Build a website that teaches algebra to Class 8 students"
ITEMS = [{"text": "The site has a home page and a page of lessons", "how": "model", "level": "target"},
         {"text": "Every page reads clearly for Class 8", "how": "model", "level": "outcome"},
         {"text": "The site is live", "how": "code", "level": "target"}]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    monkeypatch.delenv("J2_ADAPT_MAKE", raising=False)
    return tmp_path


@pytest.fixture
def j2(home):
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
def ref(j2, home):
    """A website department on a records home of its own, with no model, for the tests of one function."""
    W, R, J, founding, FV = j2
    W.create("dref-checks", "Checks Dept", "A site that teaches algebra", kind="website", goal="A site that teaches algebra")
    return "dref-checks"


def audit_v1():
    return importlib.import_module("layers.audit.v1")


# ---- G1 · the form a writer files in (M7.5, J2B-3) -----------------------------------------------------------------------
def page(title="Home", body="<section><h1>Home</h1><p>%s</p></section>" % ("Algebra for Class 8, one step at a time. " * 3)):
    return json.dumps({"title": title, "body_html": body})


def pages_in_form(*slugs):
    """The files of a Pages version in the form Check reads: _plan.json, and each planned page as {title, body_html}."""
    files = {"_plan.json": json.dumps({"pages": [{"slug": s, "title": s.title()} for s in slugs]})}
    files.update({s + ".html": page(s.title()) for s in slugs})
    return files


def test_g1_pages_in_the_form_pass_and_say_what_they_hold():
    import artifacts
    got = artifacts.pages_are_checkable(pages_in_form("index", "lessons"))
    assert got["ok"] is True and got["notes"] == ["the plan names the home page, and every page is a title and a body"]
    assert artifacts.form_check("Pages", pages_in_form("index"))["ok"] is True


@pytest.mark.parametrize("what, files, said", [
    ("no plan at all", {"index.html": page()}, "no plan Check can read"),
    ("a plan that is not JSON", dict(pages_in_form("index"), **{"_plan.json": "pages: index"}), "no plan Check can read"),
    ("a plan that lists no page", dict(pages_in_form("index"), **{"_plan.json": json.dumps({"pages": []})}), "no plan Check can read"),
    ("a plan whose page has no slug", dict(pages_in_form("index"), **{"_plan.json": json.dumps({"pages": [{"title": "Home"}]})}),
     "no plan Check can read"),
    ("a plan with no home page", pages_in_form("lessons"), "does not name the home page"),
    ("a plan that names a page twice", dict(pages_in_form("index"), **{"_plan.json": json.dumps({"pages": [{"slug": "index"}, {"slug": "index"}]})}),
     "names a page twice"),
    ("a planned page that was not written", {k: v for k, v in pages_in_form("index", "lessons").items() if k != "lessons.html"},
     "lessons is planned and was not written"),
    ("a whole HTML page", dict(pages_in_form("index", "lessons"), **{"lessons.html": "<!doctype html><html><body><h1>Lessons</h1></body></html>"}),
     "lessons is a whole HTML page, not a title and a body"),
    ("a page that is not an object", dict(pages_in_form("index"), **{"index.html": json.dumps(["Home"])}), "index is not a page Check can read"),
    ("a page with no body", dict(pages_in_form("index"), **{"index.html": json.dumps({"title": "Home"})}), "index is not a page Check can read"),
    ("a page with a body that is not text", dict(pages_in_form("index"), **{"index.html": json.dumps({"title": "Home", "body_html": ["x"]})}),
     "index is not a page Check can read"),
    ("a body that is a whole page", dict(pages_in_form("index"), **{"index.html": page("Home", "<html><head></head><body><h1>Home</h1></body></html>")}),
     "index holds a whole page, not the inside of main"),
])
def test_g1_a_version_not_in_the_form_fails_and_names_what_is_wrong(what, files, said):
    import artifacts
    got = artifacts.pages_are_checkable(files)
    assert got["ok"] is False, what
    assert any(said in n for n in got["notes"]), (what, got["notes"])


def test_g1_scripts_text_and_links_stay_checks_verdicts_not_the_forms():
    """The form asks only whether Check can read what was filed (J2B-3): a script, almost no text and a link to no page are all in form."""
    import artifacts
    files = dict(pages_in_form("index"), **{"index.html": page("Home", '<p>Hi</p><script>x()</script><a href="nowhere.html">there</a>')})
    assert artifacts.pages_are_checkable(files)["ok"] is True


def test_g1_the_form_is_a_pure_function_over_the_files():
    import artifacts
    files = pages_in_form("index", "lessons")
    before = json.dumps(files, sort_keys=True)
    assert artifacts.pages_are_checkable(files) == artifacts.pages_are_checkable(dict(files))
    assert json.dumps(files, sort_keys=True) == before
    assert artifacts.pages_are_checkable(None)["ok"] is False and artifacts.pages_are_checkable({})["ok"] is False


def test_g1_the_pages_template_names_its_form_and_the_definitions_stay_clean(j2):
    W, R, J, _, _ = j2
    import artifacts
    t = artifacts.get("Pages")
    assert t["form"] == "pages_are_checkable" and t["form"] in artifacts.FORMS and len(t["form"]) <= 60
    assert artifacts.form_of("Pages") == "pages_are_checkable" and artifacts.view("Pages")["form"] == "pages_are_checkable"
    assert [n for n, x in artifacts.templates().items() if x.get("form")] == ["Pages"], "Pages is the one artifact with a form"
    assert artifacts.form_of("Build") is None and artifacts.form_check("Build", {"index.html": "x"}) is None
    assert artifacts.view("Build")["form"] == ""
    assert artifacts.faults(R.defs()) == [] and R.validate(R.defs()) == []


def test_g1_a_form_the_app_does_not_ship_is_a_fault_of_the_definitions_and_a_version_that_does_not_hold(j2, monkeypatch):
    W, R, J, _, _ = j2
    import artifacts
    defs = R.defs()
    t = dict(artifacts.get("Pages"), form="pages_are_pretty")
    monkeypatch.setitem(artifacts.templates(), "Pages", t)
    assert "artifact Pages: no form named pages_are_pretty ships with the app" in artifacts.faults(defs)
    assert "no form named pages_are_pretty" in " ".join(R.validate(defs)), "and the definitions are refused where they load"
    got = artifacts.form_check("Pages", pages_in_form("index"))
    assert got == {"ok": False, "notes": ["no form named pages_are_pretty ships with the app"]}


def test_g1_the_librarys_own_write_files_pages_in_the_form(j2):
    """The form is what the Library's Write files today, so Check reads it: the form changes nothing for the Library's engines."""
    W, R, J, _, _ = j2
    import artifacts
    plan = W._fallback_plan("Checks Dept", "A site that teaches algebra to Class 8 students")
    ctx = {"bag": {"write.list": {"plan": plan, "pages": [p["slug"] for p in plan["pages"]]},
                   "write.page": [{"title": p["title"], "body_html": W._fallback_body(p, plan)} for p in plan["pages"]]}, "how": {}}
    files = R.write_file(ctx, None, None)["files"]
    assert artifacts.pages_are_checkable(files) == {"ok": True, "notes": ["the plan names the home page, and every page is a title and a body"]}


def shape(**more):
    return dict({"name": "Page maker", "use_case": "writes the pages", "does": "writes the pages", "instruction": "write the pages of the site",
                 "needs": [], "reads": "Brief", "writes": "Pages"}, **more)


def born(R, ref, name="Page maker", **more):
    path = R.born_template(name, shape(name=name, **more), ref)
    return json.loads(path.read_text(encoding="utf-8")), path


def test_g1_born_template_takes_the_form_from_the_shape_and_the_template_validates_as_the_interface_types_it(ref, j2):
    W, R, J, _, _ = j2
    t, path = born(R, ref, form="Pages")
    assert t["form"] == "Pages" and S.validate("engine.template", t) == []
    page_step = next(s for s in t["steps"] if s["id"] == "page-maker.page")
    assert page_step["out"] == {"file": "str", "body_html": "str"}, "the page step writes the inside of each page"
    assert R.engine_def("Page maker")["form"] == "Pages", "the definitions carry the form to the step functions"
    assert R.validate(R.defs()) == []


def test_g1_without_a_form_a_born_engine_is_what_it_always_was(ref, j2):
    W, R, J, _, _ = j2
    t, _ = born(R, ref)
    assert "form" not in t and S.validate("engine.template", t) == []
    assert next(s for s in t["steps"] if s["id"] == "page-maker.page")["out"] == {"file": "str", "html": "str"}


@pytest.mark.parametrize("what, more, said", [
    ("a form the Library has none of", {"form": "Result"}, "the Library has no form named Result"),
    ("a form on an engine that writes no pages", {"form": "Pages", "writes": "Facts"}, "so it cannot file in the form of Pages"),
])
def test_g1_a_form_that_cannot_hold_refuses_the_engine_and_leaves_no_file(ref, j2, what, more, said):
    W, R, J, _, _ = j2
    with pytest.raises(ValueError, match=said):
        R.born_template("Page maker", shape(**more), ref)
    assert not (R.user_templates_dir() / "page-maker.json").exists(), what
    assert "Page maker" not in R.defs()["engines"]


def test_g1_a_bad_form_value_is_the_interfaces_to_refuse_before_the_file_is_written(ref, j2, monkeypatch):
    W, R, J, _, _ = j2
    monkeypatch.setattr(S, "MODE", "refuse")
    t = json.loads(json.dumps(born(R, ref, form="Pages")[0]))
    assert S.validate("engine.template", dict(t, form="")) and S.validate("engine.template", dict(t, form="x" * 61))
    with S.expect_refused("engine.template") as met, pytest.raises(S.SchemaFault):
        S.check("engine.template", dict(t, form=7), ref=ref)
    assert met and any("form" in f for f in met)


# a writer's answers, as the stubbed model gives them for a born pages engine (one plan, then a page for each planned file)
PLAN = {"pages": [{"file": "index.html", "title": "Home", "purpose": "the home page"},
                  {"file": "lessons.html", "title": "Lessons", "purpose": "the lessons for Class 8"}]}
BODY = "<section><h1>%s</h1><p>" + "Class 8 algebra, taught one small step at a time with worked examples. " * 3 + '</p><a href="index.html">Home</a></section>'


def do_ctx(R, pages, plan=PLAN, name="page-maker"):
    return {"def": R.engine_def("Page maker"), "ref": "dref-checks", "bag": {name + ".plan": plan, name + ".page": pages}, "how": {}}


def a_page(file, title, body=None):
    return {"file": file, "title": title, "body_html": body or BODY % title}


def test_g1_do_file_files_pages_in_the_form_with_the_plan_and_they_hold(ref, j2):
    W, R, J, _, _ = j2
    import artifacts
    born(R, ref, form="Pages")
    out = R.do_file(do_ctx(R, [a_page("index.html", "Home"), a_page("lessons.html", "Lessons")]), {"id": "page-maker.file"}, None)
    assert sorted(out["files"]) == ["_plan.json", "index.html", "lessons.html"]
    assert json.loads(out["files"]["_plan.json"]) == {"pages": [{"slug": "index", "title": "Home"}, {"slug": "lessons", "title": "Lessons"}]}
    assert json.loads(out["files"]["lessons.html"]) == {"title": "Lessons", "body_html": BODY % "Lessons"}
    assert out["check"]["ok"] is True, out["check"]
    assert artifacts.form_check("Pages", out["files"])["ok"] is True
    assert "2 pages" in out["check"]["notes"]


def test_g1_do_file_takes_a_pages_title_from_the_plan_when_the_agent_gave_none(ref, j2):
    W, R, J, _, _ = j2
    born(R, ref, form="Pages")
    no_title = {"file": "lessons.html", "body_html": BODY % "Lessons"}
    out = R.do_file(do_ctx(R, [a_page("index.html", "Home"), no_title]), {"id": "page-maker.file"}, None)
    assert json.loads(out["files"]["lessons.html"])["title"] == "Lessons" and out["check"]["ok"] is True


def test_g1_whole_html_pages_fail_where_they_are_written(ref, j2):
    W, R, J, _, _ = j2
    born(R, ref, form="Pages")
    whole = "<!doctype html><html><head><title>%s</title></head><body><h1>%s</h1><p>" + "Class 8 algebra, one step at a time. " * 6 + "</p></body></html>"
    pages = [{"file": "index.html", "html": whole % ("Home", "Home")}, {"file": "lessons.html", "html": whole % ("Lessons", "Lessons")}]
    out = R.do_file(do_ctx(R, pages), {"id": "page-maker.file"}, None)
    assert out["check"]["ok"] is False
    assert any("index is a whole HTML page, not a title and a body" in n for n in out["check"]["notes"]), out["check"]
    assert any("lessons is a whole HTML page" in n for n in out["check"]["notes"])
    assert out["files"]["index.html"] == pages[0]["html"], "filed as it came: the form refuses it, the writer does not repair it"
    assert "publish" not in out


def test_g1_a_body_that_is_a_whole_page_fails_where_it_is_written(ref, j2):
    W, R, J, _, _ = j2
    born(R, ref, form="Pages")
    nested = a_page("index.html", "Home", "<html><body>" + BODY % "Home" + "</body></html>")
    out = R.do_file(do_ctx(R, [nested, a_page("lessons.html", "Lessons")]), {"id": "page-maker.file"}, None)
    assert out["check"]["ok"] is False and any("index holds a whole page, not the inside of main" in n for n in out["check"]["notes"])


def test_g1_an_engine_that_planned_pages_and_wrote_text_fails_at_the_form(ref, j2):
    W, R, J, _, _ = j2
    born(R, ref, form="Pages")
    ctx = do_ctx(R, [])
    ctx["bag"]["page-maker.make"] = {"text": "Home page, lessons page. Written by hand."}
    out = R.do_file(ctx, {"id": "page-maker.file"}, None)
    assert out["check"]["ok"] is False and any("no plan Check can read" in n for n in out["check"]["notes"])


def test_g1_with_no_form_do_file_files_whole_pages_exactly_as_it_did(ref, j2):
    """Flag off, or an engine no Library engine reads: nothing changes (the suites' own proof is the gate staying green)."""
    W, R, J, _, _ = j2
    born(R, ref)
    whole = "<!doctype html><html><head><title>Home</title></head><body><h1>Home</h1><p>" + "Class 8 algebra. " * 8 + "</p></body></html>"
    out = R.do_file(do_ctx(R, [{"file": "index.html", "html": whole}]), {"id": "page-maker.file"}, None)
    assert out == {"files": {"index.html": whole}, "check": {"ok": True, "notes": ["1 pages", "every page has a body"]}}


def test_g1_the_page_step_of_a_form_engine_asks_for_the_inside_of_a_page_and_its_check_holds_it(ref, j2):
    W, R, J, _, _ = j2
    born(R, ref, form="Pages")
    ctx = {"def": R.engine_def("Page maker"), "ref": "dref-checks", "dept": W.dept("dref-checks"),
           "bag": {"page-maker.read": {"brief": "Teach algebra to Class 8", "previous": None}, "page-maker.plan": PLAN}}
    step = {"id": "page-maker.page"}
    prompt = R.p_do_page(ctx, step, "index.html")
    assert '{"file": str, "title": str, "body_html": str}' in prompt and "inside of <main> only" in prompt and "no <html>, <head>" in prompt
    assert "THIS PAGE: " + json.dumps(PLAN["pages"][0]) in prompt
    draft = R.d_do_page(ctx, step, "lessons.html")
    assert set(draft) == {"file", "title", "body_html"} and draft["file"] == "lessons.html" and "<html" not in draft["body_html"].lower()
    good = {"file": "index.html", "title": "Home", "body_html": BODY % "Home"}
    assert R.c_page_is_html(ctx, step, "index.html", good)["ok"] is True
    assert R.c_page_is_html(ctx, step, "lessons.html", draft)["ok"] is True, "the offline draft is itself in the form its step checks"
    for what, out in (("a whole page", {"file": "index.html", "html": "<html><body>" + "words " * 30 + "</body></html>"}),
                      ("another page's file", dict(good, file="lessons.html")),
                      ("a body that is a document", dict(good, body_html="<!doctype html><html><body>" + "words " * 30 + "</body></html>")),
                      ("almost no text", dict(good, body_html="<p>Hi</p>"))):
        assert R.c_page_is_html(ctx, step, "index.html", out)["ok"] is False, what
    plain = {"def": {"writes": "Pages"}}
    assert R.c_page_is_html(plain, step, "index.html", {"file": "index.html", "html": "<body>" + "words " * 30 + "</body>"})["ok"] is True


# ---- G1 · _j2_settle births a writer a Library engine reads with the reader's form ---------------------------------------
def made(name, reads, writes, covers, level=2, **more):
    return dict({"name": name, "does": "does " + name, "reads": reads, "writes": writes, "covers": covers, "level": level,
                 "confidence": 0.9, "internet": False}, **more)


MAKER = made("Page maker", "Brief", "Pages", ["D1", "D2"])
CHECK = made("Check", "Pages", "Build", [], level=1)
PUBLISH = made("Publish", "Build", "Live site", ["D3"], level=1)


def test_g1_a_writer_a_level_1_engine_reads_is_born_with_the_readers_form_when_the_make_setting_is_on(ref, j2, monkeypatch):
    W, R, J, _, _ = j2
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    assert R._form_for(ref, MAKER, [MAKER, CHECK, PUBLISH]) == "Pages"


def test_g1_with_the_make_setting_off_no_writer_has_a_form(ref, j2, monkeypatch):
    W, R, J, _, _ = j2
    for off in (None, "", "0", "off"):
        monkeypatch.delenv("J2_ADAPT_MAKE", raising=False)
        if off is not None:
            monkeypatch.setenv("J2_ADAPT_MAKE", off)
        assert R._form_for(ref, MAKER, [MAKER, CHECK, PUBLISH]) is None, off


@pytest.mark.parametrize("what, engine, line", [
    ("no level-1 engine reads what it writes", MAKER, [MAKER, made("Site 2", "Pages", "Live site", ["D3"])]),
    ("the engine that reads it is another shaped one", MAKER, [MAKER, made("Checker", "Pages", "Build", ["D3"], level=2)]),
    ("what it writes has no form", made("Facts 2", "Brief", "Facts 2", ["D1"]),
     [made("Facts 2", "Brief", "Facts 2", ["D1"]), made("Check", "Facts 2", "Build", [], level=1)]),
    ("a level-1 engine reads it but is not the Library's", MAKER, [MAKER, made("Reader", "Pages", "Build", [], level=1)]),
    ("it writes nothing", dict(MAKER, writes=""), [MAKER, CHECK]),
])
def test_g1_a_writer_nobody_in_the_library_reads_has_no_form(ref, j2, monkeypatch, what, engine, line):
    W, R, J, _, _ = j2
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    assert R._form_for(ref, engine, line) is None, what


def test_g1_settling_a_shaped_plan_hands_the_form_to_the_engine_born_for_the_writer_and_to_no_other(ref, j2, monkeypatch):
    W, R, J, _, _ = j2
    monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    d = W.dept(ref)
    d["done_items"] = [dict(i, id="D%d" % n) for n, i in enumerate(ITEMS, 1)]
    W.save_dept(ref, d)
    seen, real = {}, W.add_engine

    def spy(r, name, shape=None, **kw):
        seen[name] = dict(shape or {})
        return real(r, name, shape=shape, **kw)
    monkeypatch.setattr(W, "add_engine", spy)
    facts = made("Facts 2", "Brief", "Facts 2", ["D1"])
    pages = made("Page maker", "Facts 2", "Pages", ["D2"])
    R._j2_settle(ref, W.dept(ref), [facts, pages, CHECK, PUBLISH], "shaped", "teach algebra", "Priority's yes")
    assert seen["Page maker"]["form"] == "Pages", "the writer Check reads"
    assert "form" not in seen["Facts 2"], "Facts 2 is read by no Library engine"
    assert "Check" not in seen and "Publish" not in seen, "the Library's own engines are not born"
    born_for = json.loads((R.user_templates_dir() / "page-maker.json").read_text(encoding="utf-8"))
    assert born_for["form"] == "Pages" and "form" not in json.loads((R.user_templates_dir() / "facts-2.json").read_text(encoding="utf-8"))


# ---- G1 · a department end to end: a shaped writer's pages reach Check and Publish in the form --------------------------
LINE = {"engines": [made("Page maker", "Brief", "Pages", ["D1", "D2"]), made("Check", "Pages", "Build", [], level=1),
                    made("Publish", "Build", "Live site", ["D3"], level=1)]}


def stub(monkeypatch, R, answers):
    """A model that is a function: a step id maps to what it says (a dict, or a callable taking the prompt and the step);
    every other step falls to its draft, as it does offline. Returns the calls it met, [(step id, prompt)]."""
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


def the_page_asked_for(prompt):
    return json.loads(re.search(r"THIS PAGE: (\{.*\})", prompt).group(1))


def writes_the_inside(prompt):
    p = the_page_asked_for(prompt)
    return {"file": p["file"], "title": p["title"], "body_html": BODY % p["title"]}


def writes_whole_pages(prompt):
    p = the_page_asked_for(prompt)
    return {"file": p["file"], "html": "<!doctype html><html><head><title>%s</title></head><body>%s</body></html>" % (p["title"], BODY % p["title"])}


def a_department(j2, monkeypatch, writer, make=True, line=LINE):
    """A website department as a person makes one, its line shaped around a writer of Pages that Check reads, with J2_ADAPT_MAKE
    on (or off) and a stub in place of every model; the motor runs until idle and the owner's one stamp on what goes out is given."""
    W, R, J, founding, FV = j2
    if make:
        monkeypatch.setenv("J2_ADAPT_MAKE", "1")
    else:
        monkeypatch.delenv("J2_ADAPT_MAKE", raising=False)
    stub(monkeypatch, R, {"setup.converse": {"verdict": "clear", "question": ""},
                          "setup.shape": {"name": "Algebra Co Department", "kind": "organic", "goal": WEBSITE, "done_items": ITEMS},
                          "adapt.line": line, "priority.bargain": {"answer": "accept", "why": "the envelope has room"},
                          "audit.judge": {"ok": True, "findings": []}, "page-maker.plan": PLAN, "page-maker.page": writer})
    root = founding.found_structure("Algebra Co", owner="Sankalp")["root"]
    W.owner_ask(root, WEBSITE)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "publish"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)
    return ref


def test_g1_with_the_setting_on_a_shaped_writers_pages_in_the_form_pass_check_and_reach_publish(j2, monkeypatch):
    W, R, J, _, _ = j2
    import artifacts
    ref = a_department(j2, monkeypatch, writes_the_inside)
    d = W.dept(ref)
    assert d["workflows"][-1]["engines"] == ["Page maker", "Check", "Publish"] and d["workflows"][-1]["source"] == "shaped"
    assert R.engine_def("Page maker")["form"] == "Pages", "born with the form of the Pages Check reads"
    pages = W.latest(ref, "Pages")
    assert pages and pages["check"]["ok"] is True, pages
    assert artifacts.form_check("Pages", W.read_files(ref, "Pages", pages["v"]))["ok"] is True
    build = W.latest(ref, "Build")
    assert build and build["check"]["ok"] is True, build
    live = W.latest(ref, "Live site")
    assert live and live["check"]["ok"] is True, "the pages reached Publish"
    assert "Lessons" in W.read_files(ref, "Live site", live["v"])["lessons.html"]


def test_g1_whole_html_pages_from_a_writer_with_the_form_stop_at_the_writer_and_check_never_meets_them(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = a_department(j2, monkeypatch, writes_whole_pages)
    assert R.engine_def("Page maker")["form"] == "Pages"
    for art in ("Pages", "Build", "Live site"):
        assert W.versions(ref, art) == [], "%s: nothing was filed, so nothing reached Check or Publish" % art
    rows = [r for r in R.step_rows(ref) if r["engine"] == "Page maker" and r["step"] == "page-maker.page"]
    assert rows and all(r["status"] != "ok" for r in rows), "the page step could not give a page in the form: the writer stopped"
    assert not [r for r in R.step_rows(ref) if r["step"] == "page-maker.file"]
    assert not [r for r in R.step_rows(ref) if r["engine"] in ("Check", "Publish")]


def test_g1_without_the_form_the_same_pages_pass_the_writer_and_fail_later_at_check(j2, monkeypatch):
    """What the form prevents (J2B-3): the artifact's own check asks only that each page is non-empty, so whole HTML pages
    were filed as Pages and Check could not find a plan in them."""
    W, R, J, _, _ = j2
    monkeypatch.setattr(R, "_form_for", lambda *a: None)
    ref = a_department(j2, monkeypatch, writes_whole_pages)
    assert "form" not in R.engine_def("Page maker")
    pages = W.latest(ref, "Pages")
    assert pages and pages["check"]["ok"] is True and "_plan.json" not in W.read_files(ref, "Pages", pages["v"])
    build = W.latest(ref, "Build")
    assert build and build["check"]["ok"] is False and "no home page" in build["check"]["notes"]
    assert W.versions(ref, "Live site") == []


def test_g1_with_the_setting_off_the_department_is_born_as_it_always_was(j2, monkeypatch):
    """No writer has a form, so no engine carries one and a plan the Library gave is untouched (the gate's suites are the rest)."""
    W, R, J, _, _ = j2
    monkeypatch.delenv("J2_ADAPT_MAKE", raising=False)
    monkeypatch.setattr(W, "model_json", lambda *a, **k: (None, 0.0, "offline"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    d, _ = W.create("dref-library", "Library Dept", None, kind="website")
    assert d["engines"] == ["Plan", "Write", "Check", "Publish"] and not [n for n, e in R.defs()["engines"].items() if e.get("form")]
    assert R._form_for("dref-library", MAKER, [MAKER, CHECK, PUBLISH]) is None


# ---- G2 · the mechanical step finds the page defects a browser is not needed for (M8.6) -------------------------------------
HOME = ("<!doctype html><html lang='en'><head><title>Home</title></head><body><header><a href='index.html'>Home</a> "
        "<a href='lessons.html'>Lessons</a></header><main>%s</main></body></html>")
LESSONS = HOME.replace("Home</title>", "Lessons</title>") % "<h1>Lessons</h1><p id='week1'>Week one.</p>"


PLAIN = "<!doctype html><html lang='en'><head><title>Page</title></head><body><main>%s</main></body></html>"


def site(index_main="<h1>Welcome</h1><p>Algebra for Class 8.</p>", **pages):
    """The files of a built site: index.html around `index_main`, a lessons page, and any page by file name."""
    return dict({"index.html": HOME % index_main, "lessons.html": LESSONS}, **pages)


def defects(files):
    return audit_v1().page_defects(files)


def only(files, kind=None):
    got = defects(files)
    assert len(got) == 1, got
    assert set(got[0]) == {"where", "page", "claim", "severity", "kind"} and got[0]["kind"] == "defect"
    return got[0]


def test_g2_a_clean_site_has_no_defect():
    assert defects(site()) == []
    assert defects({}) == [] and defects({"result.md": "# An answer\n\nNo pages here."}) == [], "a deliverable with no page has none"


# one fixture a defect: the finding names where (the page and the element), what is wrong, and how serious
@pytest.mark.parametrize("what, files, where, claim, severity", [
    ("a link to a page the site does not have", site("<h1>Welcome</h1><a href='fees.html'>Our fees</a>"),
     "index.html: the link 'Our fees' (to fees.html)", "the link 'Our fees' goes to a page the site does not have", "medium"),
    ("a link to a page of a folder the site does not have", site("<h1>Welcome</h1><a href='docs/fees.html'>Fees</a>"),
     "index.html: the link 'Fees' (to docs/fees.html)", "the link 'Fees' goes to a page the site does not have", "medium"),
    ("a link to an anchor the page does not have", site("<h1>Welcome</h1><a href='#hours'>Opening hours</a>"),
     "index.html: the link 'Opening hours' (to #hours)", "the link 'Opening hours' goes to a part of the page that is not there", "low"),
    ("a link to an anchor the other page does not have", site("<h1>Welcome</h1><a href='lessons.html#week9'>Week nine</a>"),
     "index.html: the link 'Week nine' (to lessons.html#week9)", "the link 'Week nine' goes to a part of another page that is not there", "low"),
    ("a form with no submit", site("<h1>Welcome</h1><form action='send.php'><input type='text' name='q'></form>"),
     "index.html: the form", "the form has no submit button, so a visitor cannot send it", "medium"),
    ("a form whose only button is not a submit", site("<h1>Welcome</h1><form><input name='q'><button type='button'>Go</button></form>"),
     "index.html: the form", "the form has no submit button, so a visitor cannot send it", "medium"),
    ("an image with no alt", site("<h1>Welcome</h1><img src='img/hero.png'>"),
     "index.html: the image 'hero.png'", "the image 'hero.png' has no alt text for a reader who cannot see it", "medium"),
    ("a page with no h1", site("<h2>Welcome</h2><p>Algebra.</p>"),
     "index.html: the main heading (h1)", "the page has no h1 heading", "medium"),
    ("a page with two h1", site("<h1>Welcome</h1><h1>Also welcome</h1>"),
     "index.html: the main heading (h1)", "the page has more than one h1 heading, and should have one: 'Welcome', 'Also welcome'", "low"),
])
def test_g2_a_fixture_for_each_defect_gives_one_finding_naming_where_and_what(what, files, where, claim, severity):
    got = only(files)
    assert (got["where"], got["claim"], got["severity"]) == (where, claim, severity), what
    assert got["page"] == "index.html" and got["where"].startswith("index.html: "), "the page's own name apart from where: the page and the element"
    assert S.validate("audit.finding", dict(got, id="F1")) == [], what


def test_g2_what_resolves_is_not_a_defect():
    main = ("<h1>Welcome</h1><a href='lessons.html'>Lessons</a> <a href='./lessons.html#week1'>Week one</a> <a href='/index.html'>Home</a> "
            "<a href='/'>Start</a> <a href='#'>Top</a> <a href='#top'>Up</a> <a href='#intro'>Intro</a><p id='intro'>Hello.</p>"
            "<a name='old'></a><a href='#old'>Old</a> <a href='https://example.org/x'>Out</a> <a href='mailto:a@b.in'>Mail</a> "
            "<a href='tel:+911234'>Call</a> <a href='//cdn.example.org/x'>CDN</a> <a href='style.css'>Style</a> <a href='fees.pdf'>Fees</a> "
            "<a href='lessons.html?x=1'>Lessons again</a> <a>No href</a> <a href=''>Empty</a>"
            "<form><input name='q'><button>Send</button></form><form><input type='submit' value='Go'></form>"
            "<form id='f3'><input name='z'></form><button type='submit' form='f3'>Send three</button>"
            "<form><input type='image' src='go.png' alt='Go'></form>"
            "<img src='a.png' alt='A picture of a class'><img src='b.png' alt=''>")
    assert defects(site(main)) == []


def test_g2_a_link_is_read_from_the_page_it_is_on_so_a_folder_resolves_as_a_browser_does():
    files = site(**{"docs/guide.html": PLAIN % "<h1>Guide</h1><a href='../index.html'>Home</a><a href='index.html'>Docs home</a>",
                    "docs/index.html": PLAIN % "<h1>Docs</h1>"})
    assert defects(files) == []
    got = only(dict(files, **{"docs/guide.html": PLAIN % "<h1>Guide</h1><a href='lessons.html'>Lessons</a>"}))
    assert got["where"] == "docs/guide.html: the link 'Lessons' (to docs/lessons.html)", "the target is in where, which the writer reads"
    assert got["claim"] == "the link 'Lessons' goes to a page the site does not have", "and not in the claim, which the owner is quoted"


def test_g2_a_link_to_a_page_whose_name_is_written_with_escapes_resolves():
    assert defects(site("<h1>Welcome</h1><a href='our%20fees.html'>Fees</a>", **{"our fees.html": PLAIN % "<h1>Fees</h1>"})) == []


def test_g2_a_page_the_plan_names_is_a_page_to_link_to():
    files = dict(pages_in_form("index"), **{"index.html": page("Home", "<h1>Home</h1><p>%s</p><a href='lessons.html'>Lessons</a>" % ("word " * 30))})
    assert [d["claim"] for d in defects(files)] == ["the link 'Lessons' goes to a page the site does not have"]
    files["_plan.json"] = json.dumps({"pages": [{"slug": "index"}, {"slug": "lessons"}]})
    assert defects(files) == [], "planned, even before its page is written: the writer's own form says so"


def test_g2_pages_filed_as_a_title_and_a_body_are_read_by_their_body():
    files = dict(pages_in_form("index", "lessons"), **{"lessons.html": page("Lessons", "<h2>Lessons</h2><img src='w.png'>")})
    got = defects(files)
    assert [(d["where"], d["claim"]) for d in got] == [("lessons.html: the image 'w.png'", "the image 'w.png' has no alt text for a reader who cannot see it"),
                                                       ("lessons.html: the main heading (h1)", "the page has no h1 heading")]


def test_g2_each_element_is_a_finding_once_and_one_defect_is_one_finding():
    main = ("<h1>Welcome</h1><a href='fees.html'>Fees</a><a href='fees.html'>Fees</a><img src='a.png'><img src='b.png'><img src='a.png'>"
            "<form><input name='q'></form><form><input name='r'></form>")
    got = defects(site(main))
    assert [d["where"] for d in got] == ["index.html: the link 'Fees' (to fees.html)", "index.html: the first form", "index.html: the second form",
                                         "index.html: the image 'a.png'", "index.html: the image 'b.png'"]
    assert got[2]["claim"] == "the second form has no submit button, so a visitor cannot send it"
    assert len({(d["where"], d["claim"]) for d in got}) == len(got)


def test_g2_a_form_is_named_by_its_own_words_when_it_has_them():
    got = defects(site("<h1>Welcome</h1><form id='visit' action='x'><input name='q'></form><form aria-label='Book a visit'><input name='q'></form>"))
    assert [d["where"] for d in got] == ["index.html: the form 'visit'", "index.html: the form 'Book a visit'"]


def test_g2_the_findings_follow_the_pages_in_name_order_and_each_page_in_its_own_order():
    files = {"b.html": PLAIN % "<h2>B</h2><img src='b.png'>", "a.html": PLAIN % "<h1>A</h1><a href='nowhere.html'>X</a>"}
    got = defects(files)
    assert [d["where"].split(":")[0] for d in got] == ["a.html", "b.html", "b.html"]
    assert [d["claim"] for d in got][1:] == ["the image 'b.png' has no alt text for a reader who cannot see it", "the page has no h1 heading"]


def test_g2_a_page_that_is_not_html_at_all_is_no_fault_of_this_check():
    assert defects({"index.html": "{not json", "about.html": "", "x.html": "<<<>>><a href"}) is not None
    assert defects({"index.html": "\x00\x01"}) is not None


def test_g2_long_words_are_cut_to_the_findings_bounds():
    long = "x" * 400
    got = only(site("<h1>Welcome</h1><a href='%s.html'>%s</a>" % (long, long)))
    assert len(got["where"]) <= 200 and len(got["claim"]) <= 600 and S.validate("audit.finding", dict(got, id="F1")) == []


# ---- G2 · the mechanical step: the record as it always was, and the pages ---------------------------------------------------
def a_website(j2, monkeypatch, write_page=None, judge=None):
    """A website department as a person makes one (founded, asked for, set up by Root), its Live site stamped. `write_page` is
    what the Write step's agent says of a page (a callable of the prompt), `judge` what Audit's judge says of the pages (its
    findings, a list; none by default); Audit's reader says every item is met."""
    W, R, J, founding, FV = j2
    answers = {"audit.items": says("met"), "audit.judge": {"ok": not judge, "findings": judge or []}}
    if write_page:
        answers["write.page"] = write_page
    stub(monkeypatch, R, answers)
    root = founding.found_structure("Acme Learning", owner="Sankalp")["root"]
    W.owner_ask(root, WEBSITE)
    W.run_until_idle(root, limit=300)
    ref = next(d for d in W.list_depts() if d.get("parent") == root)["ref"]
    W.run_until_idle(ref, limit=300)
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "publish"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)
    return ref


def says(verdict):
    """Audit's reader, a function: every done-when item in the prompt is `verdict`."""
    def say(prompt):
        items = json.loads(prompt.split("THE DONE-WHEN ITEMS:\n", 1)[1].split("\n\nWHAT CODE MEASURED:", 1)[0])
        return {"items": [{"id": i["id"], "verdict": verdict, "claim": "what is so of %s" % i["id"], "evidence": "what shows it for %s" % i["id"]}
                          for i in items], "findings": []}
    return say


def the_page(prompt):
    return json.JSONDecoder().raw_decode(prompt.split("THIS PAGE:\n", 1)[1])[0]


def a_page_with(extra):
    """What the Write step's agent says of a page: a heading, text, and `extra` markup (a defect, or none)."""
    def write(prompt):
        p = the_page(prompt)
        return {"title": p["title"], "body_html": "<section><h1>%s</h1><p>%s</p>%s</section>" % (p["title"], "What a student needs to know. " * 3, extra)}
    return write


def mechanical(j2, monkeypatch, ref, files, sample=True):
    """The v1 mechanical step on a department that exists, reading `files` as the deliverable."""
    W, R, J, _, _ = j2
    monkeypatch.setattr(R, "audit_files", lambda ctx: files)
    return audit_v1().CODE["audit_mechanical"]({"ref": ref, "dept": W.dept(ref), "inp": {"v": 1}, "bag": {"audit.pick": {"sample": sample}}}, None, None)


CLEAN_NOTE = ("every version has its run and its check; the trace reaches the owner's words; "
              "the pages' links, forms, images and headings are in order")


def test_g2_audit_mechanical_moved_into_audit_v1_and_the_recipe_still_names_it():
    m = audit_v1()
    assert not hasattr(m.CODE["audit_mechanical"], "legacy"), "a body of the layer's own, no longer a reference to engine_runtime"
    assert not hasattr(m.CHECK["has_a_verdict"], "legacy")
    steps = [s for s in json.loads((S.HERE / "layers" / "audit" / "v1.json").read_text(encoding="utf-8"))["steps"] if s["id"] == "audit.mechanical"]
    assert [(s["code"], s["check"]) for s in steps] == [("audit_mechanical", "has_a_verdict")], "the step id, its code and its covering are as they were"
    assert C.case_3(m) == [] and C.case_4(m) == [] and C.case_7(m) == []


def test_g2_a_clean_site_is_in_order_and_says_the_pages_were_read(j2, monkeypatch):
    ref = a_website(j2, monkeypatch)
    got = mechanical(j2, monkeypatch, ref, site())
    assert got == {"ok": True, "notes": [CLEAN_NOTE], "faults": [], "holes": [], "defects": []}


def test_g2_a_deliverable_that_is_not_html_keeps_the_notes_it_always_had(j2, monkeypatch):
    ref = a_website(j2, monkeypatch)
    got = mechanical(j2, monkeypatch, ref, {"result.md": "An answer."})
    assert got["ok"] is True and got["notes"] == ["every version has its run and its check; the trace reaches the owner's words"]


def test_g2_a_site_not_sampled_is_not_read_for_defects_either(j2, monkeypatch):
    ref = a_website(j2, monkeypatch)
    assert mechanical(j2, monkeypatch, ref, site("<h2>no h1</h2>"), sample=False) == {"ok": True, "notes": ["not sampled"]}


def test_g2_a_defect_that_weighs_medium_fails_the_measure_and_the_notes_say_where_and_what(j2, monkeypatch):
    ref = a_website(j2, monkeypatch)
    got = mechanical(j2, monkeypatch, ref, site("<h1>Welcome</h1><img src='hero.png'><a href='fees.html'>Fees</a>"))
    assert got["ok"] is False and got["faults"] == [] and got["holes"] == []
    assert got["notes"] == ["Home: the link 'Fees' goes to a page the site does not have",
                            "Home: the image 'hero.png' has no alt text for a reader who cannot see it"], "the page by its title (G2 fix)"
    assert [d["where"] for d in got["defects"]] == ["index.html: the link 'Fees' (to fees.html)", "index.html: the image 'hero.png'"], \
        "the finding keeps the page's own name"
    assert [d["severity"] for d in got["defects"]] == ["medium", "medium"]
    assert [d["name"] for d in got["defects"]] == ["Home", "Home"], "and the owner's name for the page, beside its file"


def test_g2_a_defect_that_weighs_low_is_filed_and_noted_but_does_not_fail_the_measure(j2, monkeypatch):
    ref = a_website(j2, monkeypatch)
    got = mechanical(j2, monkeypatch, ref, site("<h1>Welcome</h1><a href='#hours'>Hours</a>"))
    assert got["ok"] is True and [d["severity"] for d in got["defects"]] == ["low"]
    assert got["notes"] == ["noted, Home: the link 'Hours' goes to a part of the page that is not there"]


def test_g2_placeholder_text_is_a_finding_naming_the_page_and_what_it_says(j2, monkeypatch):
    ref = a_website(j2, monkeypatch)
    got = mechanical(j2, monkeypatch, ref, site("<h1>Welcome</h1><p>Opening hours: to be confirmed.</p>"))
    assert got["ok"] is False and got["defects"] == []
    (hole,) = got["holes"]
    assert (hole["page"], hole["kind"], hole["severity"]) == ("index.html", "hole", "high") and "to be confirmed" in hole["claim"]
    assert hole["where"] == "index.html: the text 'to be confirmed'", "where names the page and the words, page stays the page's name"
    assert hole["name"] == "Home", "and the owner's name for the page"
    assert got["notes"] == ["the site says it does not know 1 thing"]
    assert [h["page"] for h in mechanical(j2, monkeypatch, ref, site("<h1>Welcome</h1><p>Lorem ipsum.</p>", **{"lessons.html": LESSONS.replace("Week one.", "TBD")}))["holes"]] \
        == ["index.html", "lessons.html"], "one for each page that says it"


#: what the body engine_runtime held before audit_mechanical moved into the layer said for the four deliverables below (it was deleted by
#: W3-PROOF X1, M2.10, with the other copies of bodies a version took over): taken from it on the tree before that commit
LEGACY_MECHANICAL = [
    {"ok": True, "faults": [], "holes": []},
    {"ok": False, "faults": [], "holes": [{"page": "index.html", "claim": "the page says 'Home Welcome Phone: to be confirmed'",
                                            "severity": "high", "kind": "hole"}]},
    {"ok": True, "faults": [], "holes": []},
    {"ok": False, "faults": ["the deliverable does not trace back to the owner's words"], "holes": []},
]


def test_g2_the_record_is_checked_as_it_always_was(j2, monkeypatch):
    """The part of the body that moved is the legacy body's: same faults, same holes, same notes without the page checks. (The legacy
    body is gone; its answers for these deliverables are LEGACY_MECHANICAL.)"""
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch)
    ctx = {"ref": ref, "dept": W.dept(ref), "inp": {"v": 1}, "bag": {"audit.pick": {"sample": True}}}
    for files, old in zip((site(), site("<h1>Welcome</h1><p>Phone: to be confirmed.</p>"), {"result.md": "An answer."}), LEGACY_MECHANICAL):
        monkeypatch.setattr(R, "audit_files", lambda c, files=files: files)
        new = audit_v1().audit_mechanical(ctx, None, None)
        assert new["faults"] == old["faults"] and new["ok"] == old["ok"]
        assert [{k: v for k, v in h.items() if k not in ("where", "name")} for h in new["holes"]] == old["holes"], \
            "the same holes, each with a where and a name besides"
    organic_less = W.create("dref-nothing", "Nothing", None, kind="organic")[0]["ref"]            # nothing delivered: the trace fault stays a fault
    monkeypatch.setattr(R, "audit_files", lambda c: {})
    bare = {"ref": organic_less, "dept": W.dept(organic_less), "inp": {"v": 1}, "bag": {"audit.pick": {"sample": True}}}
    assert audit_v1().audit_mechanical(bare, None, None)["faults"] == LEGACY_MECHANICAL[3]["faults"] != []
    assert not hasattr(R, "audit_mechanical"), "and the legacy body is not there to drift from it"


def test_g2_the_covering_wants_every_defect_to_name_where_what_and_how_serious(j2):
    W, R, J, _, _ = j2
    good = {"where": "index.html: the form", "claim": "it has no submit button", "severity": "medium"}
    check = audit_v1().CHECK["has_a_verdict"]
    assert check(None, None, None, {"ok": False, "notes": ["x"], "defects": [good]})["ok"] is True
    assert check(None, None, None, {"ok": True, "notes": ["x"]})["ok"] is True, "a step that found no defect and says nothing of them"
    assert check(None, None, None, {"ok": True, "notes": []})["ok"] is False and check(None, None, None, {"notes": ["x"]})["ok"] is False
    for what, bad, said in (("no where", dict(good, where=""), "defect 1 names no where"), ("no what", {k: v for k, v in good.items() if k != "claim"}, "defect 1 names no claim"),
                            ("no weight", dict(good, severity="grave"), "defect 1 has no weight"), ("not a finding", "index.html", "defect 1 has no weight")):
        got = check(None, None, None, {"ok": False, "notes": ["x"], "defects": [good, bad]})
        assert got["ok"] is False and said.replace("defect 1", "defect 2") in got["notes"][0], what


def test_g2_a_defect_reaches_the_reading_as_a_finding_that_names_where_and_what(j2, monkeypatch):
    """Through Audit's real run: a site whose pages carry an image with no alt is read, the measure fails, and the reading files a finding
    for each image, each with the page and the element and what is wrong (the S-30 reading, as the interface types it)."""
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch, a_page_with("<img src='photos/class.png'>"))
    (row, *_) = W.rows(ref, "readings.jsonl")
    assert S.validate_record("audit", "reading", row) == [] and row["read"] is True
    found = [f for f in row["findings"] if "has no alt text" in f["claim"]]
    assert found, row["findings"]
    assert all(S.validate("audit.finding", f) == [] and f["severity"] == "medium" and f["went_to"] == "Identity" for f in found)
    assert {f["where"] for f in found} >= {"index.html: the image 'class.png'"}
    assert all(re.match(r"^[a-z0-9-]+\.html: the image 'class\.png'$", f["where"]) for f in found), "the page and the element, in each"
    code = [r for r in row["items"] if r["method"] == "code"]
    assert code and all(r["verdict"] == "not_met" for r in code), "a measured failure stands over the reader's yes (Q4)"
    assert "the image 'class.png' has no alt text for a reader who cannot see it" in code[0]["claim"]
    assert "goal.reached" not in [e["action"] for e in J.events(ref)]


def test_g2_a_site_with_nothing_wrong_is_read_and_files_no_defect(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch, a_page_with("<img src='photos/class.png' alt='A class at work'>"))
    (row, *_) = W.rows(ref, "readings.jsonl")
    assert row["read"] is True and row["findings"] == []
    assert [(r["method"], r["verdict"]) for r in row["items"]] == [("code", "met")]
    assert "the pages' links, forms, images and headings are in order" in row["items"][0]["claim"]
    assert "goal.reached" in [e["action"] for e in J.events(ref)]


def test_g2_a_placeholder_reaches_the_reading_as_a_finding_that_names_the_page_and_the_words(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch, a_page_with("<p>Phone: to be confirmed.</p>"))
    (row, *_) = W.rows(ref, "readings.jsonl")
    holes = [f for f in row["findings"] if "to be confirmed" in f["claim"]]
    assert holes and all(S.validate("audit.finding", f) == [] and f["severity"] == "high" for f in holes)
    assert all(re.match(r"^[a-z0-9-]+\.html: the text 'to be confirmed'$", f["where"]) for f in holes), [f["where"] for f in holes]


# ---- G2 · fix round 1: the worst findings stay in the reading, and the words are the owner's -------------------------------------
MANY = "<h1>Welcome</h1>" + "".join("<img src='photo%d.png'>" % n for n in range(14))     # more defects than a reading carries
HIGH = {"page": "index.html", "claim": "states a fee nobody gave", "severity": "high"}
RANK = {"high": 0, "medium": 1, "low": 2}


def a_reading_of(j2, monkeypatch, ref, files, judged=(), slot="Audit@probe.v1"):
    """Audit's filing step (R.audit_file) on a department that exists: the v1 mechanical step's own result over `files`, the
    judge's findings (`judged`), and a reader who says every item is met. Returns what it said and the reading it wrote."""
    W, R, J, _, _ = j2
    mech = mechanical(j2, monkeypatch, ref, files)
    items = json.dumps(W.items_of(W.dept(ref)))
    ctx = {"ref": ref, "dept": W.dept(ref), "inp": {"v": 1}, "slot": slot, "how": {"audit.items": "model"},
           "bag": {"audit.pick": {"sample": True, "pages": []}, "audit.mechanical": mech,
                   "audit.judge": {"ok": not judged, "findings": list(judged)},
                   "audit.items": says("met")("THE DONE-WHEN ITEMS:\n%s\n\nWHAT CODE MEASURED:" % items)}}
    out = R.audit_file(ctx, None, None)
    return out, next(r for r in W.rows(ref, "readings.jsonl") if r["id"] == out["reading"]["id"]), ctx


def test_g2_fix_a_site_with_more_defects_than_a_reading_carries_keeps_the_judges_high_finding(j2, monkeypatch):
    """A reading carries at most twelve findings; the worst are the ones it keeps. Fourteen images with no alt come before the judge's
    one high finding in the order Audit finds them, and the high finding is still the first the reading holds and the first Identity is told."""
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch)
    assert len(defects(site(MANY))) == 14
    out, row, _ = a_reading_of(j2, monkeypatch, ref, site(MANY), [HIGH])
    assert len(row["findings"]) == 12 and [f["id"] for f in row["findings"]] == ["F%d" % n for n in range(1, 13)]
    assert (row["findings"][0]["severity"], row["findings"][0]["claim"]) == ("high", HIGH["claim"])
    assert all(S.validate("audit.finding", f) == [] for f in row["findings"])
    assert out["reading"]["high"] is True and "states a fee nobody gave" in out["said"], "the reading says a high finding exists, and which"
    (post,) = [p for p in R.board(ref) if (p["payload"] or {}).get("word") == "finding" and p["payload"].get("reading") == row["id"]]
    assert post["payload"]["severity"] == "high" and len(post["payload"]["findings"]) == 12
    assert post["payload"]["findings"][0]["claim"] == HIGH["claim"], "Identity is told the high finding, not only the twelve defects before it"
    tell = [p for p in R.board(ref) if (p["payload"] or {}).get("word") == "reading" and p["payload"].get("reading") == row["id"]]
    assert tell and tell[-1]["payload"]["high"] is True


def test_g2_fix_findings_are_ranked_high_then_medium_then_low_and_keep_their_order_within_a_weight(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch)
    judged = [{"page": "index.html", "claim": "the tone is stiff", "severity": "low"}, {"page": "index.html", "claim": "no weight given"},
              {"page": "lessons.html", "claim": "a reader could be harmed", "severity": "critical"}, HIGH]
    files = site("<h1>Welcome</h1><a href='#hours'>Hours</a><img src='a.png'><img src='b.png'><p>Phone: to be confirmed.</p>")
    _, row, _ = a_reading_of(j2, monkeypatch, ref, files, judged)
    assert [(f["severity"], f["claim"][:14]) for f in row["findings"]] == [
        ("high", "the page says "), ("high", "a reader could"), ("high", "states a fee n"),
        ("medium", "the image 'a.p"), ("medium", "the image 'b.p"), ("medium", "no weight give"),
        ("low", "the link 'Hour"), ("low", "the tone is st")], "by weight, and as found within one (critical is high)"
    assert [f["id"] for f in row["findings"]] == ["F%d" % n for n in range(1, 9)]


def test_g2_fix_a_reading_that_finds_few_things_is_as_it_was(j2, monkeypatch):
    """Nothing is cut under twelve and a list of one weight keeps the order it was found in."""
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch)
    _, row, _ = a_reading_of(j2, monkeypatch, ref, site("<h1>Welcome</h1><img src='z.png'><img src='a.png'><img src='m.png'>"))
    assert [f["where"] for f in row["findings"]] == ["index.html: the image 'z.png'", "index.html: the image 'a.png'", "index.html: the image 'm.png'"]


def test_g2_fix_through_a_real_department_the_judges_high_finding_is_in_the_reading_though_every_page_has_defects(j2, monkeypatch):
    """The probe that found the gap: a department whose six pages each carry two images with no alt (twelve defects), and a judge that
    finds one high thing. The reading holds it, says a high finding exists, and Identity was told it."""
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch, a_page_with("<img src='a.png'><img src='b.png'>"), judge=[HIGH])
    rows = W.rows(ref, "readings.jsonl")
    assert rows and all(r["read"] for r in rows)
    for row in rows:
        assert len(row["findings"]) <= 12
        assert HIGH["claim"] in [f["claim"] for f in row["findings"]], [f["claim"][:30] for f in row["findings"]]
        assert row["findings"][0]["severity"] == "high"
    told = [p for p in R.board(ref) if (p["payload"] or {}).get("word") == "reading"]
    assert told and all(p["payload"]["high"] is True for p in told)


CODE_ITEM = [{"id": "D1", "text": "Every page is checked and live", "how": "code", "level": "target"}]
ALT = "the image 'a.png' has no alt text for a reader who cannot see it"


def code_row(j2, mech):
    """The row audit_rows gives a done-when item that code measures, for a measure that said `mech`."""
    W, R, J, _, _ = j2
    said = {"items": [{"id": "D1", "verdict": "met", "claim": "what is so of D1", "evidence": "what shows it"}], "findings": []}
    (row,) = [r for r in R.audit_rows(CODE_ITEM, mech, said, True) if r["method"] == "code"]
    assert S.validate("audit.reading_item", row) == []
    return row


@pytest.mark.parametrize("what, mech, claim, verdict", [
    ("the record and the pages are in order",
     {"ok": True, "notes": ["every version has its run and its check; the trace reaches the owner's words"], "faults": [], "holes": [], "defects": []},
     "the record holds: every version has its run and its check; the trace reaches the owner's words", "met"),
    ("a low defect is noted and the record holds",
     {"ok": True, "notes": ["noted, Home: the link 'Hours' goes to a part of the page that is not there"], "faults": [], "holes": [], "defects": []},
     "the record holds: noted, Home: the link 'Hours' goes to a part of the page that is not there", "met"),
    ("only a page defect fails: the pages need work, and the record is not said to fail",
     {"ok": False, "notes": ["About: " + ALT, "Contact: " + ALT], "faults": [], "holes": [], "defects": [{"page": "about.html"}, {"page": "contact.html"}]},
     "the pages need work: About: %s; Contact: %s" % (ALT, ALT), "not_met"),
    ("a page that says it does not know is a page that needs work",
     {"ok": False, "notes": ["the site says it does not know 2 things"], "faults": [], "holes": [{"page": "index.html"}, {"page": "about.html"}]},
     "the pages need work: the site says it does not know 2 things", "not_met"),
    ("only a fault of the record fails: the record does not hold",
     {"ok": False, "notes": ["Plan has a version with no run or no check"], "faults": ["Plan has a version with no run or no check"], "holes": [], "defects": []},
     "the record does not hold: Plan has a version with no run or no check", "not_met"),
    ("both fail: each is named by what it is",
     {"ok": False, "notes": ["the live site does not trace back to the owner's words", "Home: " + ALT],
      "faults": ["the live site does not trace back to the owner's words"], "holes": [], "defects": [{"page": "index.html"}]},
     "the record does not hold: the live site does not trace back to the owner's words; the pages need work: Home: %s" % ALT, "not_met"),
    ("a result that does not say which notes are the record's keeps the words it always had",
     {"ok": False, "notes": ["the site says it does not know 1 thing"]},
     "the record does not hold: the site says it does not know 1 thing", "not_met"),
])
def test_g2_fix_the_measures_row_is_worded_by_what_failed(j2, what, mech, claim, verdict):
    row = code_row(j2, mech)
    assert (row["claim"], row["verdict"]) == (claim, verdict), what
    assert row["evidence"] == "; ".join(mech["notes"]), "the evidence is the notes, as it was"


def test_g2_fix_a_measure_with_nothing_to_say_still_gets_a_claim(j2):
    assert code_row(j2, {"ok": True, "notes": []})["claim"].startswith("the record holds")
    assert code_row(j2, {"ok": False, "notes": []})["claim"].startswith("the record does not hold")


def test_g2_fix_a_long_set_of_notes_is_cut_to_the_claims_bound(j2):
    notes = ["About: " + ALT.replace("a.png", "x%d.png" % n) for n in range(30)]
    row = code_row(j2, {"ok": False, "notes": notes, "faults": [], "holes": [], "defects": [{}] * 30})
    assert len(row["claim"]) <= 600 and row["claim"].startswith("the pages need work: About: ") and len(row["evidence"]) <= 1000


def test_g2_fix_the_notes_name_a_page_by_its_title_and_never_by_its_file(j2, monkeypatch):
    """The site plan names its pages (index is Home, about is About), as Identity's questions to the owner name them; a page the plan does
    not name is called by the title it carries, and one that carries none by its file name read as words."""
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch)
    assert {p["slug"]: p["title"] for p in R._pages(ref)}["about"] == "About"
    img = "<h1>%s</h1><img src='a.png'>"
    files = {"index.html": HOME % (img % "Welcome"), "about.html": PLAIN % (img % "About us"), "lessons.html": LESSONS,
             "our-fees.html": "<html><head><title>What we charge</title></head><body>%s</body></html>" % (img % "Fees"),
             "docs/guide.html": json.dumps({"title": "A guide", "body_html": img % "Guide"})}
    got = mechanical(j2, monkeypatch, ref, files)
    assert got["ok"] is False and got["faults"] == []
    assert got["notes"] == ["About: " + ALT, "A guide: " + ALT, "Home: " + ALT, "What we charge: " + ALT], got["notes"]
    assert [d["page"] for d in got["defects"]] == ["about.html", "docs/guide.html", "index.html", "our-fees.html"], \
        "the findings keep the page's own name: it is what Identity maps to a title, and what a link names"
    assert got["defects"][0]["where"] == "about.html: the image 'a.png'"
    assert [d["name"] for d in got["defects"]] == ["About", "A guide", "Home", "What we charge"], "each finding says its page as the notes do"
    bare = {"index.html": HOME % "<h1>Welcome</h1>", "lessons.html": LESSONS, "price_list.html": PLAIN.replace("<title>Page</title>", "") % (img % "Prices")}
    assert mechanical(j2, monkeypatch, ref, bare)["notes"] == ["price list: " + ALT]
    many = dict(files, **{"page%d.html" % n: PLAIN % (img % n) for n in range(3)})
    assert mechanical(j2, monkeypatch, ref, many)["notes"][-1] == "more is wrong on the pages"


def test_g2_fix_a_low_defect_is_noted_by_its_pages_title(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch)
    got = mechanical(j2, monkeypatch, ref, site("<h1>Welcome</h1><a href='#hours'>Hours</a>"))
    assert got["ok"] is True
    assert got["notes"] == ["noted, Home: the link 'Hours' goes to a part of the page that is not there"]


def test_g2_fix_a_department_with_no_site_plan_names_its_pages_by_what_they_carry(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = W.create("dref-noplan", "No plan", None, kind="organic")[0]["ref"]
    assert R._pages(ref) == []
    files = {"index.html": HOME % "<h1>Welcome</h1><img src='a.png'>", "contact-us.html": PLAIN.replace("<title>Page", "<title>") % "<h1>Contact</h1><img src='a.png'>"}
    monkeypatch.setattr(R, "audit_files", lambda ctx: files)
    ctx = {"ref": ref, "dept": W.dept(ref), "inp": {"v": 1}, "bag": {"audit.pick": {"sample": True}}}
    got = audit_v1().audit_mechanical(ctx, None, None)
    assert [n for n in got["notes"] if ALT in n] == ["contact us: " + ALT, "Home: " + ALT]


def test_g2_fix_the_ask_Identity_files_for_a_page_defect_names_the_pages_and_what_needs_work(j2, monkeypatch):
    """The probe that found the gap: Identity is not yet heard by a next round (as at the commit it was found on), so the item that code
    measures as not met goes to the owner as a finding to stamp, and it quotes the measure's claim. A missing alt text is not a record
    that does not hold, and the pages are named as the owner knows them."""
    W, R, J, _, _ = j2
    monkeypatch.setattr(importlib.import_module("layers.identity.v1"), "next_is_heard", lambda: False)
    ref = a_website(j2, monkeypatch, a_page_with("<img src='a.png'><img src='b.png'>"))
    asks = [a for a in W.asks(ref) if a["kind"] == "finding" and a["status"] == "pending"]
    assert asks, [(a["kind"], a["status"]) for a in W.asks(ref)]
    text = asks[0]["text"]
    assert text.startswith("Audit found: D1 ") and "the pages need work: About: the image 'a.png' has no alt text" in text, text
    assert "the record does not hold" not in text and ".html" not in text, text
    assert text.endswith("Stamp to have it put right.")


# ---- G2 · fix round 2: no file and no path reaches the owner, and a page is named by its title -----------------------------------
LINK_CLAIM = "the link 'Read more' goes to a page the site does not have"


@pytest.mark.parametrize("what, files, target, claim", [
    ("a page of the site's root", site("<h1>Welcome</h1><a href='fees.html'>Fees</a>"), "fees.html",
     "the link 'Fees' goes to a page the site does not have"),
    ("a page of a folder", site("<h1>Welcome</h1><a href='docs/fees.html'>Fees</a>"), "docs/fees.html",
     "the link 'Fees' goes to a page the site does not have"),
    ("a page by its path from the root", site("<h1>Welcome</h1><a href='/docs/fees.html'>Fees</a>"), "docs/fees.html",
     "the link 'Fees' goes to a page the site does not have"),
    ("a link with no words on it", site("<h1>Welcome</h1><a href='fees.html'><img src='f.png' alt='Fees'></a>"), "fees.html",
     "a link goes to a page the site does not have"),
    ("an anchor of this page", site("<h1>Welcome</h1><a href='#week9'>Fees</a>"), "#week9",
     "the link 'Fees' goes to a part of the page that is not there"),
    ("an anchor of another page", site("<h1>Welcome</h1><a href='lessons.html#week9'>Fees</a>"), "lessons.html#week9",
     "the link 'Fees' goes to a part of another page that is not there"),
])
def test_g2_fix2_a_link_defect_names_its_target_in_where_and_never_in_the_claim(what, files, target, claim):
    """The claim is quoted to the owner (the code row, the ask, the Audit tab): it names no file, no path and no anchor. The writer who puts
    the link right reads `where`, and that holds the target."""
    got = only(files)
    assert got["claim"] == claim, what
    assert not re.search(r"\.html?\b|/|#", got["claim"]) and target not in got["claim"], (what, got["claim"])
    assert got["where"].endswith("(to %s)" % target) and got["where"].startswith("index.html: "), (what, got["where"])
    assert S.validate("audit.finding", dict(got, id="F1")) == [], what


def test_g2_fix2_two_links_of_one_name_to_two_missing_pages_are_two_findings(j2, monkeypatch):
    """The claim no longer tells them apart, so where does: one finding for each element, in the step and in the reading Audit files."""
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch)
    files = site("<h1>Welcome</h1><a href='a.html'>Read more</a><a href='b.html'>Read more</a><a href='a.html'>Read more</a>")
    assert [(d["where"], d["claim"]) for d in defects(files)] == [("index.html: the link 'Read more' (to a.html)", LINK_CLAIM),
                                                                  ("index.html: the link 'Read more' (to b.html)", LINK_CLAIM)]
    out, row, _ = a_reading_of(j2, monkeypatch, ref, files)
    assert [(f["where"], f["claim"]) for f in row["findings"]] == [("index.html: the link 'Read more' (to a.html)", LINK_CLAIM),
                                                                   ("index.html: the link 'Read more' (to b.html)", LINK_CLAIM)], \
        "the reading keeps both, as it kept two claims that differed by their targets before"
    assert out["filed"] == 2


def test_g2_fix2_the_reader_and_the_judge_who_find_one_thing_on_a_page_are_still_one_finding(j2, monkeypatch):
    """The dedupe that tells two links apart is for page defects only: two sources saying the same words of one page stay one finding."""
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch)
    said = {"page": "index.html", "claim": "states a fee nobody gave", "severity": "medium"}
    _, row, _ = a_reading_of(j2, monkeypatch, ref, site(), [said, dict(said, where="somewhere else")])
    assert [f["claim"] for f in row["findings"]] == ["states a fee nobody gave"]


def test_g2_fix2_holes_and_defects_are_named_by_the_owners_name_for_the_page(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch)
    files = {"index.html": HOME % "<h1>Welcome</h1><p>Phone: to be confirmed.</p><img src='a.png'>",
             "about.html": PLAIN % "<h1>About us</h1><p>Opening hours: to be confirmed.</p><a href='gone.html'>Gone</a>",
             "our-fees.html": "<html><head><title>What we charge</title></head><body><h1>Fees</h1><p>TBD</p></body></html>",
             "price_list.html": PLAIN.replace("<title>Page</title>", "") % "<h1>Prices</h1><form><input name='q'></form>", "lessons.html": LESSONS}
    got = mechanical(j2, monkeypatch, ref, files)
    assert {h["page"]: h["name"] for h in got["holes"]} == {"index.html": "Home", "about.html": "About", "our-fees.html": "What we charge"}
    assert {d["page"]: d["name"] for d in got["defects"]} == {"index.html": "Home", "about.html": "About", "price_list.html": "price list"}
    assert all(h["page"].endswith(".html") and h["where"].startswith(h["page"] + ": ") for h in got["holes"] + got["defects"]), \
        "the file stays in page and where, for the writer and for Identity"
    assert not [n for n in got["notes"] if ".html" in n or "/" in n], got["notes"]
    assert all(S.validate("audit.finding", dict(f, id="F1")) == [] for f in got["holes"] + got["defects"])


def test_g2_fix2_the_post_to_identity_and_the_audit_tab_name_every_page_by_its_title(j2, monkeypatch):
    """The probe that found the gap, through a real department: a page with an image with no alt, a bad link and a placeholder. Audit's
    post carries the title beside each finding's file, and the Audit tab (j2ui_audit._finding_rows) shows the title, never the file,
    in its note, and no file or path in the words of the finding."""
    import j2ui_audit
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch)
    files = {"index.html": HOME % "<h1>Welcome</h1><img src='a.png'><a href='gone.html'>Gone</a><a href='docs/lost.html#top2'>Lost</a>"
                                  "<p>Phone: to be confirmed.</p>",
             "about.html": PLAIN % "<h1>About us</h1><img src='b.png'><a href='#nope'>Up</a>",
             "our-fees.html": "<html><head><title>What we charge</title></head><body><h1>Fees</h1><a href='lessons.html#week9'>Week</a></body></html>",
             "lessons.html": LESSONS}
    _, row, _ = a_reading_of(j2, monkeypatch, ref, files)
    (post,) = [p for p in R.board(ref) if (p["payload"] or {}).get("word") == "finding" and p["payload"].get("reading") == row["id"]]
    mine = [f for f in post["payload"]["findings"] if f.get("kind") in ("defect", "hole")]
    assert {f["page"]: f["name"] for f in mine} == {"index.html": "Home", "about.html": "About", "our-fees.html": "What we charge"}
    assert {f["kind"] for f in mine} == {"defect", "hole"} and len(mine) >= 7
    rows = j2ui_audit._finding_rows(post)
    assert len(rows) == len(post["payload"]["findings"]) and {r["note"] for r in rows} == {"Home", "About", "What we charge"}, [r["note"] for r in rows]
    for r in rows:
        assert not re.search(r"\.html?\b|/", r["criterion"] + " " + r["note"]), r
    links = [r["criterion"] for r in rows if "link" in r["criterion"]]
    assert sorted(links) == sorted(["the link 'Gone' goes to a page the site does not have", "the link 'Lost' goes to a page the site does not have",
                                    "the link 'Up' goes to a part of the page that is not there",
                                    "the link 'Week' goes to a part of another page that is not there"]), links
    assert {f["where"] for f in mine if "link" in f["claim"]} >= {"index.html: the link 'Gone' (to gone.html)",
                                                                  "index.html: the link 'Lost' (to docs/lost.html)",
                                                                  "our-fees.html: the link 'Week' (to lessons.html#week9)"}, "the writer still has the target"


def test_g2_fix2_the_measures_row_for_a_bad_link_names_the_pages_and_no_file(j2, monkeypatch):
    """The code row is what Identity quotes to the owner and the Audit tab lists as the criterion. Through the mechanical step on a site
    whose pages go to a page it does not have, to a part of one it has not, and to a part of its own page that is not there."""
    W, R, J, _, _ = j2
    ref = a_website(j2, monkeypatch)
    mech = mechanical(j2, monkeypatch, ref, site("<h1>Welcome</h1><a href='docs/fees.html'>Fees</a><a href='lessons.html#week9'>Week nine</a>"
                                                  "<a href='#hours'>Hours</a>"))
    claim = R.audit_code_claim(mech)
    assert claim == ("the pages need work: Home: the link 'Fees' goes to a page the site does not have; "
                     "noted, Home: the link 'Week nine' goes to a part of another page that is not there; "
                     "noted, Home: the link 'Hours' goes to a part of the page that is not there"), claim
    assert not re.search(r"\.html?\b|/|#", claim + " ".join(mech["notes"]))


def test_g2_fix2_the_ask_Identity_files_for_a_form_and_a_link_names_the_pages_and_no_file(j2, monkeypatch):
    """The earlier probe held for an image: a form, and the links the measure only notes, are quoted in the same words with no file in
    them. (A link to a page the site lacks never reaches Audit through a real department: Check refuses that build first.)"""
    W, R, J, _, _ = j2
    monkeypatch.setattr(importlib.import_module("layers.identity.v1"), "next_is_heard", lambda: False)
    ref = a_website(j2, monkeypatch, a_page_with("<form><input name='q'></form><a href='#nope'>Up</a><a href='contact.html#hours'>Hours</a>"))
    asks = [a for a in W.asks(ref) if a["kind"] == "finding" and a["status"] == "pending"]
    assert asks, [(a["kind"], a["status"]) for a in W.asks(ref)]
    text = asks[0]["text"]
    assert "the pages need work: About: the form has no submit button, so a visitor cannot send it" in text, text
    assert "noted, About: the link 'Up' goes to a part of the page that is not there" in text, text
    assert "noted, About: the link 'Hours' goes to a part of another page that is not there" in text, text
    assert "the record does not hold" not in text and not re.search(r"\.html?\b|#", text), text
    assert text.endswith("Stamp to have it put right.")
