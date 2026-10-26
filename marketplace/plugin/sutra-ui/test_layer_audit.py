"""Audit behind its interface (PRD amendment A1: W1-AUDIT; M8.1 to M8.3, M8.9, M0.3), one section a step.

  U1  audit/v1 provides every name its recipe uses, by reference, and passes the contract
  U2  Audit's words (goal, judge, judge.items) are typed: every part takes the WORDS path, none is on the .md fallback
  U3  the deliverable: every place on Audit's path asks the interface (S.deliverable), one test per kind
  U4  Audit starts on and reads any kind's deliverable; one that is not HTML is read as text
  U5  a reading per done-when item in the S-30 shape; a version not read is a row with read false
  U6  Audit's view: latest and readings

The departments here are born the way test_j2's are (founded, asked for, set up by Root), so what is tested is what a
real department does on its real board; a model is a function (a step id maps to what it says).
"""
import importlib
import json

import pytest

import layer_schema as S
import layers
import layers.contract as C
import layers.prompts as P

WEBSITE = "Build a website that teaches algebra to Class 8 students"
ORGANIC = "Set up a laboratory system to track chemical inventory for our school science team"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_UI_PROPOSALS", str(tmp_path / "proposals"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    monkeypatch.setenv("J1_FLOW_V1", "1")
    monkeypatch.setenv("J2_FLOW_V1", "1")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
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


def _model(monkeypatch, R, answers):
    """A model that is a function: a step id maps to what the model says (a dict, or a callable taking the prompt).
    Every other step falls to its draft, as it does offline."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)

    def model(prompt, step):
        if step["id"] not in answers:
            return None, 0.0, "offline"
        got = answers[step["id"]]
        return (got(prompt) if callable(got) else got), 0.01, "model"

    monkeypatch.setattr(R, "MODEL", model)


def _born(j2, words=WEBSITE, org="Acme Learning", settle=True):
    W, _, _, founding, _ = j2
    root = founding.found_structure(org, owner="Sankalp")["root"]
    W.owner_ask(root, words)
    W.run_until_idle(root, limit=300)
    child = next(d for d in W.list_depts() if d.get("parent") == root)
    if settle:
        W.run_until_idle(child["ref"], limit=300)
    return child["ref"]


def _default(j2, ref="dref-answers"):
    """A department of the default kind, as test_j2 makes one: one Do engine, its Result the deliverable."""
    W, R, J, _, _ = j2
    d, _ = W.create(ref, "Answers", None, kind="default")
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    W.save_dept(d["ref"], d)
    J.start(d["ref"])
    W.give_goal(d["ref"], "Answer what the science team asks about the lab rota")
    W.run_until_idle(d["ref"], limit=300)
    return d["ref"]


def _stamp_all(W, ref, kind=None):
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and (kind is None or a["kind"] == kind)]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)


def _actions(J, ref):
    return [e["action"] for e in J.events(ref)]


# ---- U1 · audit/v1 by reference ------------------------------------------------------------------------------------
def _audit_module():
    return next(m for m in C.discover() if m.LAYER == "audit")


@pytest.fixture
def contract_ctx(home):
    return {"ref": C.fixture_department(home / "departments")}


def test_u1_audit_v1_passes_the_contract_cases_1_to_4_and_7(contract_ctx):
    m = _audit_module()
    assert C.impl_id(m) == "audit/v1"
    for number, case in ((1, C.case_1), (2, C.case_2), (3, C.case_3), (4, C.case_4), (7, C.case_7)):
        assert case(m, contract_ctx) == [], "contract case %d" % number


def test_u1_every_name_the_recipe_uses_is_provided_by_reference_not_by_the_legacy_registries():
    m = _audit_module()
    recipe = C.recipe_of(m)
    used = {kind: {s[kind] for s in C._steps(recipe) if s.get(kind)} for kind in ("code", "prompt", "draft", "check")}
    mine = C._dicts(m)
    for kind, names in used.items():
        assert names <= set(mine[kind]), "%s: %s are not provided by audit/v1" % (kind, sorted(names - set(mine[kind])))
    counts = C.by_reference(m)
    assert counts["by_reference"] == sum(len(v) for v in used.values()) and counts["own"] == 0


# ---- U3 · the deliverable (M8.1) -----------------------------------------------------------------------------------
LAB_LINE = [{"name": "Gather", "does": "collects the lab inventory facts", "reads": "Brief", "writes": "Notes", "internet": False},
            {"name": "Report", "does": "writes the inventory report", "reads": "Notes", "writes": "Report", "internet": False}]


def _organic(j2, monkeypatch, line=None):
    """An organic department whose line Adaptation shapes: the last engine writes the Report, not the Live site."""
    _, R, _, _, _ = j2
    answers = {"adapt.line": {"engines": line or LAB_LINE}}
    _model(monkeypatch, R, answers)
    return _born(j2, ORGANIC, "Lab Co")


def test_u3_each_kind_names_its_deliverable_website_default_and_the_shaped_last_artifact(j2, monkeypatch):
    W, R, J, _, _ = j2
    web = _born(j2)
    _stamp_all(W, web)                                              # the first publish asks the owner; the Live site goes up
    default = _default(j2)
    organic = _organic(j2, monkeypatch)
    want = {web: "Live site", default: "Result", organic: "Report"}
    assert W.dept(organic)["kind"] == "organic" and W.dept(organic)["workflows"][-1]["engines"] == ["Gather", "Report"]
    for ref, art in want.items():
        assert S.deliverable(W.dept(ref)) == art
        assert R.audit_art({"ref": ref, "inp": {"v": 1}}) == art, "Audit reads what the interface says the plan delivers"
        assert R.audit_art({"ref": ref, "dept": W.dept(ref), "inp": {"v": 1}}) == art
    web_files, default_files = R.audit_files({"ref": web, "inp": {"v": 1}}), R.audit_files({"ref": default, "inp": {"v": 1}})
    assert "index.html" in web_files and list(default_files) == ["result.md"]
    assert R.audit_files({"ref": organic, "inp": {"v": 1}}) == W.read_files(organic, "Report", 1)


def test_u3_a_department_with_no_deliverable_reads_nothing_and_does_not_fail(j2, monkeypatch):
    W, R, J, _, _ = j2
    organic = _born(j2, ORGANIC, "Lab Co", settle=False)           # not yet planned: an organic line is empty
    assert S.deliverable(W.dept(organic)) is None
    ctx = {"ref": organic, "inp": {"v": 1}, "bag": {"audit.pick": {"sample": True}}}
    assert R.audit_files(ctx) == {}
    assert R.audit_pick(ctx, None, None)["pages"] == []
    mech = R.audit_mechanical(ctx, None, None)
    assert mech["ok"] is False and mech["faults"] == ["the deliverable does not trace back to the owner's words"]


def test_u3_the_ledger_cites_the_deliverable_it_read_never_the_live_site_by_default(j2):
    W, R, J, _, _ = j2
    default = _default(j2)
    J.not_read(default, 1, "no model was there to read it")
    unread = [e for e in J.events(default) if e["action"] == "audit.not_read"][-1]
    assert unread["evidence_refs"] == [{"artifact": "Result", "version": 1}]
    assert unread["summary"] == "Audit did not read Result v1: no model was there to read it."
    web = _born(j2)
    J.not_read(web, 2, "it was not sampled")
    unread = [e for e in J.events(web) if e["action"] == "audit.not_read"][-1]
    assert unread["evidence_refs"] == [{"artifact": "Live site", "version": 2}]
    assert unread["summary"] == "Audit did not read Live site v2: it was not sampled."
    # a finding's event cites the artifact the finding says it is about
    R.post(default, "Audit", "Identity", "inform", {"word": "finding", "claim": "x", "severity": "low", "findings": [],
                                                    "about_version": 1, "artifact": "Result"})
    found = [e for e in J.events(default) if e["action"] == "audit.finding_filed"][-1]
    assert found["evidence_refs"] == [{"artifact": "Result", "version": 1}]


def test_u3_no_live_site_literal_is_left_on_audits_path(j2):
    import inspect
    W, R, J, _, _ = j2
    on_path = [R.audit_art, R.audit_files, R.audit_pick, R.audit_mechanical, R.audit_file, R.p_audit_judge, R.d_audit_judge,
               R._j2_audit_read, J.on_post, J.not_read, J.audited, J._deliverable]
    for fn in on_path:
        assert "Live site" not in inspect.getsource(fn), fn.__name__
    assert "Live site" not in inspect.getsource(importlib.import_module("layers.audit.v1"))


# ---- U4 · Audit reads any kind's deliverable (M8.2) -----------------------------------------------------------------
def _audit_rows(R, ref, step=None):
    return [r for r in R.step_rows(ref) if r["engine"] == "Audit" and (step is None or r["step"] == step)]


def test_u4_audit_starts_on_a_checked_version_of_the_deliverable_not_of_an_artifact(j2):
    W, R, J, _, _ = j2
    want = {"on": [{"kind": "version", "of": "$deliverable", "checked": True}], "unless": []}
    assert R.engine_def("Audit")["start"] == want
    assert json.loads((S.HERE / "layers" / "audit" / "v1.json").read_text(encoding="utf-8"))["start"] == want
    assert R.validate(R.defs()) == [], "the definitions are clean with the trigger"
    web = _born(j2)
    assert R.trigger_art(W.dept(web), want["on"][0]) == "Live site"
    assert R.trigger_art(W.dept(web), {"kind": "version", "of": "Pages"}) == "Pages", "a trigger on an artifact is as it was"


def test_u4_the_website_scenario_is_as_it_was_the_same_slot_the_same_words(j2, monkeypatch):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"audit.judge": {"ok": False, "findings": [{"page": "index", "claim": "The fees are invented", "severity": "high"}]}})
    ref = _born(j2)
    _stamp_all(W, ref, kind="publish")
    audit = [r for r in W.runs(ref) if r["engine"] == "Audit"]
    assert [r["slot"] for r in audit] == ["Audit@live-site.v1"] and audit[0]["what"] == "found something to put right: The fees are invented"
    assert all(r["read"] == [{"art": "Live site", "v": 1}] for r in _audit_rows(R, ref))
    found = [e for e in J.events(ref) if e["action"] == "audit.finding_filed"]
    assert [e["evidence_refs"] for e in found] == [[{"artifact": "Live site", "version": 1}]]


def test_u4_a_default_department_reaches_step_7_on_its_result(j2):
    W, R, J, _, _ = j2
    ref = _default(j2)
    assert [r["slot"] for r in W.runs(ref) if r["engine"] == "Audit"] == ["Audit@result.v1"]
    assert all(r["read"] == [{"art": "Result", "v": 1}] for r in _audit_rows(R, ref))
    unread = [e for e in J.events(ref) if e["action"] == "audit.not_read"]
    assert [(e["step"], e["actor"], e["evidence_refs"]) for e in unread] == [(7, "Audit", [{"artifact": "Result", "version": 1}])]
    assert [r["what"] for r in W.runs(ref) if r["engine"] == "Audit"][0].startswith("did not read what went live")
    assert (J.status(ref)["step"], J.status(ref)["state"]) == (7, "unread")
    W.run_until_idle(ref, limit=100)
    assert [r["slot"] for r in W.runs(ref) if r["engine"] == "Audit"] == ["Audit@result.v1"], "once, on that version"


def test_u4_an_organic_shaped_department_reaches_step_7_on_what_its_plan_delivers(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _organic(j2, monkeypatch)
    assert W.dept(ref)["kind"] == "organic"
    assert [r["slot"] for r in W.runs(ref) if r["engine"] == "Audit"] == ["Audit@report.v1"]
    unread = [e for e in J.events(ref) if e["action"] == "audit.not_read"]
    assert [(e["step"], e["evidence_refs"]) for e in unread] == [(7, [{"artifact": "Report", "version": 1}])]
    assert (J.status(ref)["step"], J.status(ref)["state"]) == (7, "unread")


def test_u4_an_organic_department_not_yet_planned_has_nothing_for_audit_to_start_on(j2):
    W, R, J, _, _ = j2
    ref = _born(j2, ORGANIC, "Lab Co", settle=False)
    assert S.deliverable(W.dept(ref)) is None
    ctx = R._coord_ctx(ref, W.dept(ref))
    assert R.ready(ctx, "Audit") is None, "no deliverable: no trigger is live"


def test_u4_root_has_no_deliverable_audit_reads_so_its_scenarios_are_as_they_were(j2, monkeypatch):
    W, R, J, founding, _ = j2
    asked = []
    _model(monkeypatch, R, {"audit.judge": lambda prompt: asked.append(prompt) or {"ok": True, "findings": []}})
    root = founding.found_structure("Acme Learning", owner="Sankalp")["root"]
    W.owner_ask(root, WEBSITE)
    W.run_until_idle(root, limit=300)
    assert W.dept(root)["kind"] == "root" and W.latest(root, "Department"), "Setup filed the department it made"
    assert S.deliverable(W.dept(root)) == "Department", "the interface names one"
    assert not [r for r in W.runs(root) if r["engine"] == "Audit"] and asked == [], "and Audit does not read it"


def test_u4_a_deliverable_that_is_not_html_is_read_as_text_at_most_40000_characters(j2):
    W, R, J, _, _ = j2
    ref = _default(j2)
    big = "word " * 12000                                              # 60,000 characters of text, in a file that is not HTML
    W.add_version(ref, "Result", {"result.md": big, "notes.txt": "A second file."}, [{"art": "Brief", "v": 1}], "r-big",
                  {"ok": True, "notes": ["by hand"]})
    ctx = {"ref": ref, "dept": W.dept(ref), "inp": {"v": 2}, "bag": {}}
    pick = R.audit_pick(ctx, None, None)
    assert pick["pages"] == ["notes.txt", "result.md"], "no HTML page: every file is read, as text"
    ctx["bag"]["audit.pick"] = pick
    pages = json.loads(R.p_audit_judge(ctx, None, None).split("THE PAGES:\n", 1)[1])
    assert [p["page"] for p in pages] == ["notes.txt", "result.md"]
    assert pages[0]["text"] == "A second file."
    assert len(pages[1]["text"]) == R.READ_MAX - len("A second file.") and R.READ_MAX == 40000, "40,000 characters of text in all"
    assert pages[1]["text"].startswith("word word word")
    # an HTML deliverable is read as it was: tags out, whitespace folded, a page at most 1,500 characters
    web = _born(j2)
    _stamp_all(W, web)
    ctx = {"ref": web, "dept": W.dept(web), "inp": {"v": 1}, "bag": {}}
    ctx["bag"]["audit.pick"] = R.audit_pick(ctx, None, None)
    pages = json.loads(R.p_audit_judge(ctx, None, None).split("THE PAGES:\n", 1)[1])
    assert pages and all(p["page"].endswith(".html") and "<" not in p["text"] and len(p["text"]) <= 1500 for p in pages)


def test_u4_the_start_is_said_in_words_by_the_departments_own_deliverable(j2, monkeypatch):
    W, R, J, _, _ = j2
    web, default = _born(j2), _default(j2)
    assert R.steps_view(web, "Audit")["start"]["on"] == ["a new Live site that passed its check"]
    assert R.steps_view(default, "Audit")["start"]["on"] == ["a new Result that passed its check"]
    assert R.start_view(R.engine_def("Audit"))["on"] == ["a new deliverable that passed its check"], "with no department"
    assert R.slot_of(default, "Audit")["on"].startswith("after Result v")


def test_u4_audit_should_have_fired_names_the_artifact_the_plan_delivers(j2):
    from datetime import datetime, timedelta, timezone
    W, R, J, _, FV = j2
    d, _ = W.create("dref-faulty", "Answers", None, kind="default")
    ref = d["ref"]
    W.add_version(ref, "Result", {"result.md": "An answer.\n"}, [{"art": "Brief", "v": 1}], "r-do", {"ok": True, "notes": ["by hand"]})
    audit = lambda: next(n for n in FV.functions(ref)["functions"] if n["name"] == "Audit")      # noqa: E731
    assert audit()["state"] != "fault", "inside the grace window it is not yet a fault"
    p = W.ddir(ref) / "artifacts" / "result" / "versions.json"
    rows = json.loads(p.read_text())
    rows[-1]["at"] = (datetime.now(timezone.utc) - timedelta(seconds=FV.FIRE_GRACE_S + 60)).astimezone().isoformat(timespec="seconds")
    p.write_text(json.dumps(rows))
    assert (audit()["state"], audit()["why"]) == ("fault", "Audit has not read Result v1")


def test_u4_audit_reads_what_it_starts_on_so_the_made_list_and_the_hand_offs_name_audit_as_the_reader_of_the_deliverable(j2, monkeypatch):
    W, R, J, _, FV = j2
    audit = R.engine_def("Audit")
    assert "reads" not in audit and "reads" not in json.loads((S.HERE / "layers" / "audit" / "v1.json").read_text(encoding="utf-8")), \
        "no kind's artifact is named in Audit's recipe: it reads what it starts on, the department's deliverable"
    assert audit["start"]["on"][0]["of"] == R.DELIVERABLE and R.validate(R.defs()) == [], "and the definitions are clean without it"
    web, default, organic = _born(j2), _default(j2), _organic(j2, monkeypatch)
    for ref, art, readers in ((web, "Live site", ["Adaptation", "Audit"]), (default, "Result", ["Audit"]), (organic, "Report", ["Audit"])):
        d = W.dept(ref)
        assert R.reads_art(d, audit) == art and R.steps_view(ref, "Audit")["reads"] == art
        made = {m["art"]: m for m in FV.made(ref, d, [])}
        assert sorted(made[art]["readers"]) == readers, "%s is read by Audit, and the Made list says so" % art
        hand = {h["art"]: h for h in FV._handoffs(ref, d)}
        assert "Audit" in hand[art]["readers"], "and so does the hand-off card"
        assert "read by nobody" not in json.dumps(made), art
    # a work engine's reads are as they were, a function that starts on a post reads nothing, and a department with no
    # deliverable yet, or Root, has Audit read nothing
    assert R.reads_art(W.dept(web), R.engine_def("Write")) == R.engine_def("Write")["reads"]
    assert R.reads_art(W.dept(web), R.engine_def("Identity")) is None and R.reads_art(None, None) is None
    assert R.reads_art({"kind": "root"}, audit) is None and R.reads_art({"kind": "organic", "workflows": []}, audit) is None
    unplanned = _born(j2, ORGANIC, "Second Lab Co", settle=False)
    assert unplanned != organic and S.deliverable(W.dept(unplanned)) is None
    assert R.steps_view(unplanned, "Audit")["reads"] is None
    assert not [a for m in FV.made(unplanned, W.dept(unplanned), []) for a in m["readers"] if a == "Audit"]


def test_u4_no_live_site_literal_is_left_in_audits_recipe_or_in_the_fallbacks_of_its_run_rows(j2):
    import inspect
    W, R, J, _, FV = j2
    assert "Live site" not in (S.HERE / "layers" / "audit" / "v1.json").read_text(encoding="utf-8")
    base = json.loads((S.HERE / "test_fixtures" / "function-engines.base.json").read_text(encoding="utf-8"))
    assert "Live site" not in json.dumps(base["Audit"]) and "reads" not in base["Audit"]
    assert "Live site" not in json.dumps(R.engine_def("Audit"))
    on_path = [R.run_engine, R.run_step, R.steps_view, R.reads_art, R.trigger_art, R._on_version, R.slot_of, R.start_view, R.audit_text,
               R.p_audit_items, FV.made, FV._handoffs]
    for fn in on_path:
        assert "Live site" not in inspect.getsource(fn), fn.__name__


def test_u4_a_run_that_was_not_told_its_artifact_reads_the_departments_deliverable_in_its_rows(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _default(j2)
    seen, real = [], W._put_run
    monkeypatch.setattr(W, "_put_run", lambda r, row: (seen.append(dict(row)), real(r, row))[1])
    R.run_engine(ref, "Audit", {"v": 1}, "Audit@result.v8")                  # a start with no art in its input
    assert seen[0]["what"] == "reading Result", "the run row names the department's deliverable, never the Live site"
    mine = [r for r in _audit_rows(R, ref) if r["slot"] == "Audit@result.v8"]
    assert mine and all(r["read"] == [{"art": "Result", "v": 1}] for r in mine)


# ---- U5 · a reading per done-when item, in the S-30 shape (M8.3, M0.3) ----------------------------------------------
SIX = {"subject", "claim", "evidence", "method", "verdict", "severity"}      # the S-30 fields of a reading's row
JUDGE_OK = {"ok": True, "findings": []}


def _items_of(prompt):
    return json.loads(prompt.split("THE DONE-WHEN ITEMS:\n", 1)[1].split("\n\nWHAT CODE MEASURED:", 1)[0])


def _says(verdict="met", findings=(), **by_id):
    """Audit's reader, a function: every done-when item in the prompt is `verdict`, but the ones `by_id` names."""
    def say(prompt):
        return {"items": [{"id": i["id"], "verdict": by_id.get(i["id"], verdict), "claim": "what is so of %s" % i["id"],
                           "evidence": "what shows it for %s" % i["id"]} for i in _items_of(prompt)], "findings": list(findings)}
    return say


def _page_with_a_hole(prompt):
    page = json.JSONDecoder().raw_decode(prompt.split("THIS PAGE:\n", 1)[1])[0]
    return {"title": page["title"], "body_html": "<section><h1>%s</h1><p>%s</p><p>Phone: to be confirmed.</p></section>"
            % (page["title"], "What a student needs to know. " * 3)}


def _readings(W, ref):
    rows = W.rows(ref, "readings.jsonl")
    for row in rows:
        assert S.validate_record("audit", "reading", row) == [], row
    return rows


def test_u5_the_step_audit_items_is_in_the_recipe_after_the_mechanical_check_and_the_interface_names_it(j2):
    W, R, J, _, _ = j2
    steps = [s["id"] for s in R.engine_def("Audit")["steps"]]
    assert steps == ["audit.pick", "audit.mechanical", "audit.items", "audit.judge", "audit.file"]
    _, s = R.step_def("audit.items")
    assert s == {"id": "audit.items", "name": "Read each done-when item", "nature": "check", "born": "C0", "ceiling": "C1",
                 "only_if": "audit.pick.sample", "prompt": "audit_items", "draft": "audit_items_draft",
                 "out": {"items": "list", "findings": "list"}, "check": "reading_is_s30"}
    assert "reading_is_s30" in S.CHECKS["audit"] and "reading_is_s30" in S.CONTRACT_SAMPLES
    assert S.PROMPTS["audit"]["judge"]["items"]["read_by"] == "audit.items"
    assert any(r["words"] == ("reading",) and r["to"] == ("Identity",) and r["payload"] == "act.reading" for r in S.SENDS["Audit"])
    assert S.edges()["Audit"] == {"inform": ["Identity"]}
    assert R.validate(R.defs()) == []


def test_u5_audit_v1_provides_the_new_names_and_the_contract_still_passes(contract_ctx):
    m = _audit_module()
    assert set(m.PROMPT) == {"audit_judge", "audit_items"} and set(m.DRAFT) == {"audit_judge_draft", "audit_items_draft"}
    assert "reading_is_s30" in m.CHECK
    for case in (C.case_1, C.case_2, C.case_3, C.case_4, C.case_6, C.case_7, C.case_8):
        assert case(m, contract_ctx) == [], case.__name__


def test_u5_the_prompt_carries_the_brief_the_deliverable_the_items_and_what_code_measured(j2):
    W, R, J, _, _ = j2
    ref = _default(j2)
    d = W.dept(ref)
    ctx = {"ref": ref, "dept": d, "inp": {"v": 1}, "bag": {"audit.mechanical": {"ok": True, "notes": ["every version has its run and its check"], "holes": []}}}
    prompt = R.p_audit_items(ctx, None, None)
    returns = S.PROMPTS["audit"]["judge"]["items"]["returns"]
    assert returns in prompt and prompt.count("Return ONLY") == 1, "the answer's shape is the interface's, verbatim"
    assert "THE BRIEF:\n" in prompt and "THE DELIVERABLE:\n--- result.md ---\n" in prompt
    assert _items_of(prompt) == [{"id": "D1", "text": d["done_items"][0]["text"], "how": "model", "level": "outcome"}]
    assert json.loads(prompt.split("WHAT CODE MEASURED:\n", 1)[1]) == {"ok": True, "notes": ["every version has its run and its check"], "holes": []}
    # an item that rests on a fact nobody gave carries why
    d["to_be_confirmed"] = [{"item": "D1", "why": "the rota is not given"}]
    W.save_dept(ref, d)
    ctx["dept"] = W.dept(ref)
    assert _items_of(R.p_audit_items(ctx, None, None))[0]["confirm"] == "the rota is not given"
    # a deliverable that is not HTML is the text of its files, at most READ_MAX characters in all
    W.add_version(ref, "Result", {"result.md": "word " * 12000}, [{"art": "Brief", "v": 1}], "r-big", {"ok": True, "notes": ["by hand"]})
    ctx["inp"] = {"v": 2}
    text = R.p_audit_items(ctx, None, None).split("THE DELIVERABLE:\n", 1)[1].split("\n\nTHE DONE-WHEN ITEMS:", 1)[0]
    assert text.startswith("--- result.md ---\nword word") and len(text) == R.READ_MAX


def test_u5_a_stub_judge_says_met_on_an_item_that_failed_mechanically_and_the_reading_records_not_met_with_both_rows(j2, monkeypatch):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"write.page": _page_with_a_hole, "audit.items": _says("met"), "audit.judge": JUDGE_OK})
    ref = _born(j2)
    _stamp_all(W, ref, kind="publish")
    (row,) = _readings(W, ref)
    assert (row["artifact"], row["v"], row["read"], row["why_not_read"]) == ("Live site", 1, True, None)
    assert [(r["id"], r["method"], r["verdict"]) for r in row["items"]] == [("D1", "code", "not_met"), ("D1", "model", "met")], \
        "a measured failure stands over the reader's yes, and both rows are kept (Q4)"
    assert all(SIX <= set(r) for r in row["items"]) and row["items"][0]["severity"] == "high"
    assert R.audit_verdicts(row["items"]) == {"D1": "not_met"}
    assert "goal.reached" not in _actions(J, ref) and J.status(ref)["state"] == "pursuing"
    assert row["cycle_id"] == J.status(ref)["cycle_id"] and row["findings"] and all(f["went_to"] == "Identity" for f in row["findings"])
    assert [f["id"] for f in row["findings"]] == ["F%d" % n for n in range(1, len(row["findings"]) + 1)]


# when code and the reader disagree about an item, both rows are kept and the worse verdict stands (decision A1-16)
CODE_ITEM = [{"id": "D1", "text": "The site is true to the brief", "how": "code", "level": "outcome"}]


@pytest.mark.parametrize("code_ok, reader, rows, stands", [
    (True, "met", [("code", "met")], "met"),
    (True, "not_met", [("code", "met"), ("model", "not_met")], "not_met"),           # the record is whole; the reader read the work
    (True, "to_confirm", [("code", "met"), ("model", "to_confirm")], "to_confirm"),
    (False, "met", [("code", "not_met"), ("model", "met")], "not_met"),              # Q4: a measured failure over the reader's yes
    (False, "to_confirm", [("code", "not_met"), ("model", "to_confirm")], "not_met"),
    (False, "not_met", [("code", "not_met")], "not_met"),
])
def test_u5_when_code_and_the_reader_disagree_both_rows_are_kept_and_the_worse_verdict_stands(j2, code_ok, reader, rows, stands):
    W, R, J, _, _ = j2
    mech = {"ok": code_ok, "notes": ["the record holds"] if code_ok else ["the site says it does not know 1 thing"]}
    said = _says(reader)("THE DONE-WHEN ITEMS:\n%s\n\nWHAT CODE MEASURED:" % json.dumps(CODE_ITEM))
    got = R.audit_rows(CODE_ITEM, mech, said, True)
    assert [(r["method"], r["verdict"]) for r in got] == rows and all(SIX <= set(r) for r in got)
    assert R.audit_verdicts(got) == {"D1": stands}
    assert R.audit_verdicts(list(reversed(got))) == {"D1": stands}, "the order of the rows decides nothing"
    assert all(S.validate("audit.reading_item", r) == [] for r in got)


def test_u5_a_measure_that_found_the_record_whole_does_not_overrule_a_reader_who_says_not_met(j2, monkeypatch):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"audit.items": _says("not_met"), "audit.judge": JUDGE_OK})
    ref = _born(j2)
    _stamp_all(W, ref, kind="publish")                              # a website's D1 is by code, and its record holds
    (row,) = _readings(W, ref)
    assert [(r["id"], r["method"], r["verdict"]) for r in row["items"]] == [("D1", "code", "met"), ("D1", "model", "not_met")], \
        "both rows are kept"
    assert R.audit_verdicts(row["items"]) == {"D1": "not_met"}, "a reader's no stands over a measure that only found the record whole"
    assert [(f["severity"], f["item"]) for f in row["findings"]] == [("high", "D1")] and "does not hold" in row["findings"][0]["claim"]
    assert "goal.reached" not in _actions(J, ref) and J.status(ref)["state"] == "pursuing" and J.status(ref)["goal_reached"] is not True
    latest = _view(j2, ref)["latest"]
    assert [(i["id"], i["verdict"], i["method"]) for i in latest["items"]] == [("D1", "not_met", "model")], "the pane shows the row that stands"


def test_u5_a_measure_that_found_the_record_whole_does_not_overrule_a_reader_in_doubt(j2, monkeypatch):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"audit.items": _says("to_confirm"), "audit.judge": JUDGE_OK})
    ref = _born(j2)
    _stamp_all(W, ref, kind="publish")
    (row,) = _readings(W, ref)
    assert [(r["id"], r["method"], r["verdict"]) for r in row["items"]] == [("D1", "code", "met"), ("D1", "model", "to_confirm")]
    assert R.audit_verdicts(row["items"]) == {"D1": "to_confirm"}
    assert [(f["severity"], f["item"]) for f in row["findings"]] == [("medium", "D1")]
    assert not [a for a in W.asks(ref) if a["kind"] == "finding"], "a doubt is noted, never a stamp to ask"
    (q,) = [a for a in W.asks(ref) if a["kind"] == "j2_identity" and a["status"] == "pending"]
    assert (q["missing"], q["points"]) == ("fact", ["D1"]), "Identity weighs the doubt (M8.5): one question to the owner, who has the fact"
    assert "goal.reached" not in _actions(J, ref) and J.status(ref)["state"] == "waiting"
    assert [(i["verdict"], i["method"]) for i in _view(j2, ref)["latest"]["items"]] == [("to_confirm", "model")]


def test_u5_when_code_and_the_reader_agree_one_row_is_kept_and_every_item_met_reaches_the_goal(j2, monkeypatch):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"audit.items": _says("met"), "audit.judge": JUDGE_OK})
    ref = _born(j2)
    _stamp_all(W, ref)
    (row,) = _readings(W, ref)
    assert [(r["id"], r["method"], r["verdict"]) for r in row["items"]] == [("D1", "code", "met")] and row["findings"] == []
    assert all(SIX <= set(r) for r in row["items"])
    assert _actions(J, ref)[-2:] == ["audit.finding_filed", "goal.reached"] and J.status(ref)["goal_reached"] is True


def test_u5_offline_there_is_no_goal_and_one_row_with_read_false(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    _stamp_all(W, ref)
    (row,) = _readings(W, ref)
    assert (row["read"], row["why_not_read"], row["items"], row["findings"]) == (False, "no model was there to read it", [], [])
    assert (row["artifact"], row["v"]) == ("Live site", 1)
    assert "goal.reached" not in _actions(J, ref) and J.status(ref)["state"] == "unread"
    W.run_until_idle(ref, limit=100)
    assert len(_readings(W, ref)) == 1, "a version is read once, however long the motor runs"


def test_u5_a_version_not_sampled_is_a_row_with_read_false_and_why(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _born(j2)
    _stamp_all(W, ref)
    _model(monkeypatch, R, {"audit.items": _says("met"), "audit.judge": JUDGE_OK})
    monkeypatch.setitem(layers.load("audit/v1").CODE, "audit_pick", lambda ctx, step, item: {"sample": False, "v": int(ctx["inp"]["v"]), "pages": []})
    row = R.run_engine(ref, "Audit", {"v": 4}, "Audit@live-site.v4")
    assert row["status"] == "ok" and "not sampled" in row["what"]
    last = _readings(W, ref)[-1]
    assert (last["v"], last["read"], last["why_not_read"], last["items"]) == (4, False, "it was not sampled", [])
    assert "goal.reached" not in _actions(J, ref)


def test_u5_a_reading_that_fails_its_check_is_a_row_with_read_false_too(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _default(j2)
    bad = lambda prompt: {"items": [{"id": "D1", "verdict": "met", "claim": "it holds", "evidence": ""}], "findings": []}     # noqa: E731
    _model(monkeypatch, R, {"audit.items": bad, "audit.judge": JUDGE_OK})
    row = R.run_engine(ref, "Audit", {"v": 1, "art": "Result"}, "Audit@result.v9")
    assert row["status"] == "failed"
    assert [(r["step"], r["status"]) for r in R.step_rows(ref) if r["step"] == "audit.items"][-1] == ("audit.items", "failed")
    last = _readings(W, ref)[-1]
    assert (last["artifact"], last["read"], last["items"]) == ("Result", False, [])
    assert last["why_not_read"].startswith("its reading failed its check") and "D1: no evidence" in last["why_not_read"]
    assert "goal.reached" not in _actions(J, ref)


def test_u5_a_replayed_filing_writes_its_reading_once(j2, monkeypatch):
    W, R, J, _, _ = j2
    ref = _default(j2)
    ctx = {"ref": ref, "dept": W.dept(ref), "inp": {"v": 1}, "slot": "Audit@result.v7", "how": {"audit.items": "model"},
           "bag": {"audit.pick": {"sample": True, "pages": ["result.md"]}, "audit.mechanical": {"ok": True, "notes": ["fine"]},
                   "audit.judge": JUDGE_OK, "audit.items": _says("met")("THE DONE-WHEN ITEMS:\n%s\n\nWHAT CODE MEASURED:" % json.dumps(W.items_of(W.dept(ref))))}}
    before = len(W.rows(ref, "readings.jsonl"))
    first, second = R.audit_file(ctx, None, None), R.audit_file(ctx, None, None)
    assert len(W.rows(ref, "readings.jsonl")) == before + 1 and first["reading"]["id"] == second["reading"]["id"]


def test_u5_a_reader_that_says_not_met_leaves_the_owner_a_next_move_and_no_goal(j2, monkeypatch):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"audit.items": _says("not_met"), "audit.judge": JUDGE_OK})
    ref = _default(j2)
    (row,) = _readings(W, ref)
    assert [(r["id"], r["method"], r["verdict"], r["severity"]) for r in row["items"]] == [("D1", "model", "not_met", "high")]
    (f,) = row["findings"]
    assert (f["severity"], f["item"], f["where"]) == ("high", "D1", "Result") and "does not hold" in f["claim"]
    assert [a["kind"] for a in W.asks(ref) if a["status"] == "pending"] == ["finding"], "the existing finding ask is the next move"
    assert "goal.reached" not in _actions(J, ref) and J.status(ref)["state"] == "pursuing"


def test_u5_a_reader_in_doubt_blocks_done_and_is_noted_not_put_to_the_owner(j2, monkeypatch):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"audit.items": _says("to_confirm"), "audit.judge": JUDGE_OK})
    ref = _default(j2)
    (row,) = _readings(W, ref)
    assert [(r["verdict"], r["severity"]) for r in row["items"]] == [("to_confirm", "medium")]
    assert [(f["severity"], f["item"]) for f in row["findings"]] == [("medium", "D1")]
    assert not [a for a in W.asks(ref) if a["kind"] == "finding"], "a doubt is noted, never a stamp to ask"
    assert "goal.reached" not in _actions(J, ref)


def test_u5_a_yes_about_an_item_that_rests_on_a_fact_nobody_gave_is_a_doubt(j2, monkeypatch):
    W, R, J, _, _ = j2
    d, _ = W.create("dref-unsure", "Unsure", None, kind="default")
    d["to_be_confirmed"] = [{"item": "D1", "why": "the rota is not given"}]
    W.save_dept(d["ref"], d)
    rows = R.audit_rows(W.items_of(W.dept(d["ref"])), {"ok": True, "notes": []}, _says("met")(
        "THE DONE-WHEN ITEMS:\n%s\n\nWHAT CODE MEASURED:" % json.dumps(W.items_of(W.dept(d["ref"])))), True)
    assert [(r["verdict"], r["claim"]) for r in rows] == [("to_confirm", "it waits on a fact nobody has given: the rota is not given")]


def test_u5_a_reading_that_names_no_evidence_or_misses_an_item_fails_its_check(j2):
    W, R, J, _, _ = j2
    ref = _default(j2)
    d = W.dept(ref)
    d["done_items"] = d["done_items"] + [{"id": "D2", "text": "The rota is current", "how": "model", "level": "outcome"}]
    W.save_dept(ref, d)
    ctx = {"ref": ref, "dept": W.dept(ref)}
    check = R.CHECK["reading_is_s30"]
    row = lambda i, **k: dict({"id": i, "verdict": "met", "claim": "it holds", "evidence": "the work shows it"}, **k)      # noqa: E731
    assert check(ctx, None, None, {"items": [row("D1"), row("D2")], "findings": []})["ok"]
    assert check(ctx, None, None, {"items": [], "findings": [], "read": False})["ok"], "a reader that read nothing claims no item"
    assert check(ctx, None, None, {"items": [row("D1"), row("D2")], "findings": [{"where": "result.md", "claim": "x", "severity": "low"}]})["ok"]
    got = check(ctx, None, None, {"items": [row("D1")], "findings": []})
    assert not got["ok"] and got["notes"] == ["D2 is not read"]
    got = check(ctx, None, None, {"items": [row("D1"), row("D2", evidence=" ")], "findings": []})
    assert not got["ok"] and got["notes"] == ["D2: no evidence"]
    got = check(ctx, None, None, {"items": [row("D1"), row("D2", verdict="fine"), row("D2")], "findings": []})
    assert got["notes"] == ["D2: the verdict is not one of met, not met or to confirm", "D2 is read twice"]
    got = check(ctx, None, None, {"items": [row("D1"), row("D2")], "findings": [{"claim": "no where"}]})
    assert not got["ok"] and "names no where" in got["notes"][0]
    assert not check(ctx, None, None, {"items": "none", "findings": []})["ok"]
    assert not check(ctx, None, None, {"items": [{"verdict": "met"}], "findings": []})["ok"]


def test_u5_low_findings_do_not_block_done_but_a_high_one_does(j2, monkeypatch):
    W, R, J, _, _ = j2
    low = {"where": "result.md", "claim": "the tone is stiff", "severity": "low", "item": None}
    _model(monkeypatch, R, {"audit.items": _says("met", findings=[low]), "audit.judge": JUDGE_OK})
    ref = _default(j2)
    (row,) = _readings(W, ref)
    assert [f["severity"] for f in row["findings"]] == ["low"] and row["read"] is True
    acts = _actions(J, ref)
    assert acts.count("audit.finding_filed") == 1 and acts[-1] == "goal.reached", "the one reading, noted, then done"
    high = dict(low, severity="high", claim="the fees are invented")
    _model(monkeypatch, R, {"audit.items": _says("met", findings=[high]), "audit.judge": JUDGE_OK})
    ref2 = _default(j2, "dref-answers2")
    assert "goal.reached" not in _actions(J, ref2) and J.status(ref2)["state"] == "pursuing"


def _goal_says(R, ref):
    """What Identity told the owner when the goal was reached: the one post of the word goal."""
    (post,) = [p for p in R.board(ref) if p["src"] == "Identity" and R.OWNER in p["dst"] and (p["payload"] or {}).get("word") == "goal"]
    return post["payload"]["done"]


def test_u5_identity_says_audit_found_nothing_only_when_it_filed_nothing(j2, monkeypatch):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"audit.items": _says("met"), "audit.judge": JUDGE_OK})
    ref = _default(j2)
    said = _goal_says(R, ref)
    assert said.startswith("The goal is reached: ") and said.endswith("Audit read Result v1 and found nothing to put right.")
    assert _view(j2, ref)["latest"]["findings"] == [] and _view(j2, ref)["readings"][-1]["summary"] == "read Result v1: every done-when item holds"


@pytest.mark.parametrize("severity", ["low", "medium"])
def test_u5_a_reading_that_noted_something_that_does_not_block_is_not_told_as_found_nothing(j2, monkeypatch, severity):
    W, R, J, _, _ = j2
    noted = {"where": "result.md", "claim": "the tone is stiff", "severity": severity, "item": None}
    _model(monkeypatch, R, {"audit.items": _says("met", findings=[noted]), "audit.judge": JUDGE_OK})
    ref = _default(j2)
    assert _actions(J, ref)[-1] == "goal.reached" and not [a for a in W.asks(ref) if a["status"] == "pending"], "it does not block, and asks nothing"
    said = _goal_says(R, ref)
    assert said.endswith("Audit read Result v1 and noted something that does not block."), said
    assert "nothing to put right" not in said and not any(ch.isdigit() for ch in said.replace("v1", "")), "and no count is given"
    # the owner can see it: the pane lists the findings of the reading it shows
    got = _view(j2, ref)
    (f,) = got["latest"]["findings"]
    assert (f["severity"], f["claim"], f["where"], f["item"], f["went_to"]) == (severity, "the tone is stiff", "result.md", None, "Identity")
    assert got["readings"][-1]["summary"] == "read Result v1: every done-when item holds, and something is noted"
    assert got["findings"] == [], "and the asks the owner stamps are as they were: this one needs no stamp"


def test_u5_a_department_with_no_done_when_items_is_not_read_against_anything(j2, monkeypatch):
    W, R, J, _, _ = j2
    d, _ = W.create("dref-noitems", "Answers", None, kind="default")
    d["done_items"], d["done"] = [], ""
    W.save_dept(d["ref"], d)
    _model(monkeypatch, R, {"audit.items": lambda prompt: {"items": [], "findings": []}, "audit.judge": JUDGE_OK})
    W.add_version(d["ref"], "Result", {"result.md": "An answer.\n"}, [{"art": "Brief", "v": 1}], "r-do", {"ok": True, "notes": ["by hand"]})
    ctx = {"ref": d["ref"], "dept": W.dept(d["ref"]), "inp": {"v": 1}, "slot": "Audit@result.v1", "how": {"audit.items": "model"},
           "bag": {"audit.pick": {"sample": True, "pages": []}, "audit.mechanical": {"ok": True, "notes": ["fine"]}, "audit.judge": JUDGE_OK,
                   "audit.items": {"items": [], "findings": []}}}
    out = R.audit_file(ctx, None, None)
    assert out["read"] is False and out["why_not_read"] == "the department has no done-when items to read it against"


def test_u5_audit_tells_identity_a_reading_only_once_its_recipe_hears_one(j2, monkeypatch):
    """Identity's recipe hears a reading since W2-IDENTITY (Hear a reading, M8.4): Audit tells it each one. A recipe with no
    handler for one is told nothing (A1-14), so no merge order leaves an act unheard."""
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"audit.items": _says("met"), "audit.judge": JUDGE_OK})
    ref = _default(j2)
    (row,) = _readings(W, ref)
    told = [p for p in R.board(ref) if (p["payload"] or {}).get("word") == "reading"]
    assert len(told) == 1, "Identity has the handler: the reading was posted"
    post = told[0]
    assert (post["src"], post["dst"], post["msg_type"]) == ("Audit", ["Identity"], "inform")
    pl = post["payload"]
    assert S.validate("act.reading", pl) == []
    assert (pl["reading"], pl["artifact"], pl["v"], pl["read"], pl["met"], pl["not_met"], pl["to_confirm"], pl["high"]) == \
        (row["id"], "Result", 1, True, ["D1"], [], [], False)
    real = R._handler
    monkeypatch.setattr(R, "_handler", lambda e, p: None if (p.get("payload") or {}).get("word") == "reading" else real(e, p))
    assert R.audit_tell(ref, row) is None, "a recipe that does not hear a reading is told nothing"


def test_u5_done_is_read_from_a_reading_never_from_no_findings(j2, monkeypatch):
    """J.audited only records (M8.4): whatever the reading, it never writes goal.reached; a clean reading of a version read item
    by item is one line of the ledger. The goal is reached only by Identity, from the reading (test_layer_identity J2): the
    reading cited, every item met."""
    W, R, J, _, _ = j2
    ref = _default(j2)
    assert J.active(ref)
    held = [None, {}, {"read": False, "met": [], "not_met": [], "to_confirm": [], "high": False},
            {"read": True, "met": [], "not_met": [], "to_confirm": [], "high": False},                  # read, and no item met
            {"read": True, "met": ["D1"], "not_met": ["D2"], "to_confirm": [], "high": False},
            {"read": True, "met": ["D1"], "not_met": [], "to_confirm": ["D2"], "high": False},
            {"read": True, "met": ["D1", "D2"], "not_met": [], "to_confirm": [], "high": True}]
    for reading in held:
        assert J.audited(ref, 1, 0, reading=reading) is False, reading
    assert "goal.reached" not in _actions(J, ref) and J.status(ref)["state"] != "done" and "audit.finding_filed" not in _actions(J, ref)
    assert J.audited(ref, 1, 0, reading={"read": True, "met": ["D1", "D2"], "not_met": [], "to_confirm": [], "high": False}) is False
    acts = _actions(J, ref)
    assert acts[-1] == "audit.finding_filed" and "goal.reached" not in acts and J.status(ref)["goal_reached"] is False, "it records, and rules nothing"
    assert J.audited(ref, 1, 0, reading={"read": True, "met": ["D1", "D2"], "not_met": [], "to_confirm": [], "high": False}) is False
    assert _actions(J, ref).count("audit.finding_filed") == 1, "once for the version"


# ---- U6 · Audit's view: latest and readings -------------------------------------------------------------------------
def _view(j2, ref):
    W, R, J, _, FV = j2
    got = _audit_module().view(ref, W.dept(ref), J.events(ref), W.asks(ref))
    assert S.validate_view("audit", got) == [], S.validate_view("audit", got)
    assert S.validate("view.audit", got) == []
    return got


def test_u6_the_view_validates_empty_and_says_no_reading_yet(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    got = _view(j2, ref)
    assert got["latest"] is None and got["readings"] == [] and got["spot_checks"] == [] and set(got) == {"readings", "findings", "spot_checks", "latest"}


def test_u6_a_version_not_read_is_a_reading_with_its_reason_and_no_latest(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    _stamp_all(W, ref)
    got = _view(j2, ref)
    (entry,) = got["readings"]
    assert (entry["artifact"], entry["v"], entry["read"], entry["why_not_read"], entry["verdicts"]) == \
        ("Live site", 1, False, "no model was there to read it", {})
    assert entry["summary"] == "did not read Live site v1: no model was there to read it" and entry["at"]
    assert got["latest"] is None, "no version has been read, so nothing is the latest reading"


def test_u6_a_reading_lists_each_item_with_the_row_whose_verdict_stands(j2, monkeypatch):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"write.page": _page_with_a_hole, "audit.items": _says("met"), "audit.judge": JUDGE_OK})
    ref = _born(j2)
    _stamp_all(W, ref, kind="publish")
    got = _view(j2, ref)
    (entry,) = got["readings"]
    assert (entry["read"], entry["why_not_read"], entry["verdicts"]) == (True, None, {"D1": "not_met"})
    assert entry["summary"] == "read Live site v1: D1 not met"
    latest = got["latest"]
    assert (latest["artifact"], latest["v"]) == ("Live site", 1) and latest["at"]
    (item,) = latest["items"]
    assert set(item) == {"id", "verdict", "method", "evidence", "claim"}
    assert (item["id"], item["verdict"], item["method"]) == ("D1", "not_met", "code"), "the measured failure stands over the reader's yes"
    assert "does not know" in item["claim"]
    assert got["findings"] == [], "a hole is a question in the chat, not a finding ask: the pane lists asks as it did"


def test_u6_when_the_reader_is_the_one_who_says_no_its_row_is_the_one_shown(j2, monkeypatch):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"audit.items": _says("not_met"), "audit.judge": JUDGE_OK})
    ref = _default(j2)
    got = _view(j2, ref)
    (item,) = got["latest"]["items"]
    assert (item["id"], item["verdict"], item["method"]) == ("D1", "not_met", "model") and got["latest"]["artifact"] == "Result"


def test_u6_a_done_reading_shows_every_item_met(j2, monkeypatch):
    W, R, J, _, _ = j2
    _model(monkeypatch, R, {"audit.items": _says("met"), "audit.judge": JUDGE_OK})
    ref = _born(j2)
    _stamp_all(W, ref)
    got = _view(j2, ref)
    assert [(i["id"], i["verdict"]) for i in got["latest"]["items"]] == [("D1", "met")]
    (entry,) = got["readings"]
    assert entry["summary"] == "read Live site v1: every done-when item holds" and entry["verdicts"] == {"D1": "met"}
    assert J.status(ref)["goal_reached"] is True


def test_u6_only_the_last_six_readings_are_listed_newest_last_and_a_reading_from_before_the_journal_is_kept(j2):
    W, R, J, _, _ = j2
    ref = _default(j2)
    before = _view(j2, ref)["readings"]
    for n in range(2, 10):
        row = {"schema_version": 1, "id": "r-%08x" % n, "v": n, "artifact": "Result", "cycle_id": None, "round": None, "read": True,
               "why_not_read": None, "findings": [], "at": W.now(),
               "items": [{"id": "D1", "subject": "x", "claim": "c", "evidence": "e", "method": "model", "verdict": "met", "severity": "low"}]}
        W.append_row(ref, "readings.jsonl", row)
    got = _view(j2, ref)
    assert [e["v"] for e in got["readings"]] == [4, 5, 6, 7, 8, 9] and got["latest"]["v"] == 9
    assert before and "v" in before[0], "the version the department read has its row"


def test_u6_the_pane_still_lists_the_ledgers_readings_for_a_department_with_no_journal(j2):
    W, R, J, _, _ = j2
    ref = _born(j2)
    J.note(ref, 7, "Audit", "Identity", "audit.finding_filed", "recorded", "Audit read Live site v1 and found nothing to put right.", "old-1")
    got = _view(j2, ref)
    assert [e["summary"] for e in got["readings"]] == ["Audit read Live site v1 and found nothing to put right."]
    assert got["latest"] is None


def test_u6_the_contract_passes_for_audit_v1_with_no_part_of_it_on_the_md_fallback_beyond_the_unmoved_words(contract_ctx):
    m = _audit_module()
    for number, case in enumerate((C.case_1, C.case_2, C.case_3, C.case_4, C.case_5, C.case_6, C.case_7, C.case_8), 1):
        assert case(m, contract_ctx) == [], "contract case %d" % number
    counts = C.by_reference(m)
    assert counts == {"by_reference": 12, "own": 0}, "every name audit/v1 provides is by reference"


# ---- U2 · Audit's words (M2.5) --------------------------------------------------------------------------------------
def test_u2_every_part_of_audit_takes_the_words_path_and_none_is_on_the_md_fallback(contract_ctx):
    m = _audit_module()
    parts = [(g, p) for g, ps in S.PROMPTS["audit"].items() for p in ps]
    assert parts == [("goal", "does"), ("goal", "skills"), ("judge", "judge"), ("judge", "items")]
    for group, part in parts:
        assert P._module(None, "audit", group, part) is m, "%s.%s is served from audit/v1's WORDS" % (group, part)
    assert C.on_the_md_fallback(m) == [] and C.case_5(m, contract_ctx) == []
    assert set(m.WORDS) == set(m.LAYOUT) == {"goal", "judge"}


def test_u2_the_words_compile_to_the_bundles_part_byte_for_byte_and_the_prompts_hold_the_returns(j2):
    W, R, J, _, _ = j2
    for group, part in (("goal", "does"), ("goal", "skills"), ("judge", "judge"), ("judge", "items")):
        spec = S.PROMPTS["audit"][group][part]
        sample = {n: "<<%s>>" % n for n in spec["inputs"]}
        want = P.SLOT.sub(lambda mm: sample[mm.group(1)], P.md_part("audit", group, part))
        assert P.prompt(None, "audit", group, part, **sample) == want, (group, part)
        assert spec["returns"] is None or spec["returns"] in P.prompt(None, "audit", group, part, **sample)
    # and what a run sends is those words: the judge's prompt as it was, the reader's as the interface says
    ref = _default(j2)
    ctx = {"ref": ref, "dept": W.dept(ref), "inp": {"v": 1}, "bag": {"audit.mechanical": {"ok": True, "notes": ["fine"], "holes": []}}}
    ctx["bag"]["audit.pick"] = R.audit_pick(ctx, None, None)
    assert R.p_audit_items(ctx, None, None).startswith("Read the work against what was asked, one done-when item at a time.")
    assert R.p_audit_judge(ctx, None, None).startswith("Check what the department made against what it was asked.")


def test_u2_a_layout_the_app_cannot_fill_refuses_the_definitions_load_and_names_audits_part(j2, monkeypatch):
    W, R, J, _, _ = j2
    m = layers.load("audit/v1")
    monkeypatch.setitem(m.LAYOUT["judge"], "items", m.LAYOUT["judge"]["items"].replace("{{measured}}", "{{measured}} {{findings}}"))
    R._DEFS.clear()
    with pytest.raises(ValueError) as got:
        R.defs()
    assert "Audit's judge instructions, items: the layout holds {{findings}} and the app fills no such input" in str(got.value)
    monkeypatch.undo()
    R._DEFS.clear()
    assert R.validate(R.defs()) == []


def test_u2_the_owners_value_for_the_new_part_is_checked_as_a_field_of_it():
    assert S.validate_field("audit", "judge", "items", "task", "Read it, item by item.") == []
    assert S.validate_field("audit", "judge", "items", "guidance", "At most four findings.") == []
    assert S.validate_field("audit", "judge", "items", "task", "Say {{items}} first.")                  # only the app writes a marker
    assert S.validate_field("audit", "judge", "items", "task", "Return ONLY a JSON object: {}.")        # the answer's shape is the app's
    assert S.validate_field("audit", "judge", "items", "returns", "x"), "the answer contract is not a field"


def test_u6_the_fixtures_the_screens_draw_from_validate_and_have_the_keys_the_live_pane_has(j2):
    doc = json.loads((S.HERE / "schemas" / "layers" / "fixtures" / "view.audit.v1.json").read_text(encoding="utf-8"))
    states = doc["view.audit"]
    assert list(states) == ["empty", "reading", "not_read", "done"]
    for name, fixture in states.items():
        assert S.validate("view.audit", fixture) == [], name
        assert set(fixture) == {"readings", "findings", "spot_checks", "latest"}, name
    live = _view(j2, _born(j2))
    assert set(live) == set(states["empty"]) and live == states["empty"]
    # the words on a screen: names, never counts, no codes of the machine, nothing the screen rules forbid
    text = json.dumps(states).lower()
    for word in ("charter", "internal system", "grant", "counter", "refuse"):
        assert word not in text, word
    assert states["reading"]["readings"][0]["verdicts"] == {"D1": "met", "D2": "not_met", "D3": "to_confirm"}
    assert [i["verdict"] for i in states["reading"]["latest"]["items"]] == ["met", "not_met", "to_confirm"]
    assert states["not_read"]["latest"] is None and states["not_read"]["readings"][0]["read"] is False
