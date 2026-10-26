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


def test_g1_a_bad_form_value_is_the_interfaces_to_refuse_before_the_file_is_written(ref, j2):
    W, R, J, _, _ = j2
    t = json.loads(json.dumps(born(R, ref, form="Pages")[0]))
    with S.expect_refused("engine.template") as met:
        assert S.validate("engine.template", dict(t, form=7)) and S.check("engine.template", dict(t, form=7), ref=ref)
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
