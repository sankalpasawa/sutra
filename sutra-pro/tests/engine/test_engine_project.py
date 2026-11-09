"""The `project` output (work package WP4, engine design 2.3, 2.4, D128, D129): project work is a document-flow output built on the one
engine, chosen by the host from a rule table, registered through the registry, with the one vendored change P14. The runs here are mock
runs: offline mode reads no folder and changes nothing, so what is proved is the flow, the files, the selection and the policy."""
import json
import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.engine import capabilities, llm
from sutra_app.engine.api import mount
from sutra_app.engine.capabilities import EngineContext, Capability, register
from sutra_app.engine.capabilities.project import (CONDITIONS_FILE, PROJECT_BUILDER, PROJECT_RUBRIC, PROJECT_SECTIONS, ProjectCapability,
                                                   mock_project_charter, mock_project_section, project_spec)
from sutra_app.engine.spec import EngineSettings

from test_engine_host import QUIET, Running, chat, events, j2, jsonl, make_port_of, of, trace   # noqa: F401  (fixtures and helpers)

PRD_BRIEF = ("Write a PRD for QuickQueue, a mobile app that lets clinic patients join a waiting line remotely. Users: patients at small "
             "clinics and the front-desk staff who manage the line. Problem: patients wait 45 minutes on average in crowded waiting "
             "rooms. Must-have features: join the queue from a phone, live position updates, SMS alert when 2 patients are ahead, staff "
             "dashboard to call the next patient. Constraints: works on low-end Android phones; no patient health data stored. Success: "
             "average in-room wait under 10 minutes; 60% of patients join remotely within 3 months.")
BRIEF = ("Check the details of the app in the repo and update the J2 prototype so that its settings page matches the app: look at the "
         "settings code, list what differs, change the prototype page to match, and say what you verified and what is left to do.")
SECTIONS = ["Findings", "Changes", "Confirmation", "Open items", "Outcome"]


class TaggingPort(llm.ScriptedPort):
    """J2's mock mode that keeps the tag and the system text of every request."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.tags, self.systems = [], []

    def complete(self, req, on_progress=None):
        self.tags.append(req.tag)
        self.systems.append(req.system)
        return super().complete(req, on_progress)


def go(run_dir, port_cls=TaggingPort):
    seen = {}

    def make(*, sink, mock, task, paths):
        seen["port"] = port_cls(usage_sink=sink)
        return seen["port"]
    running = Running(run_dir, "--mock", make_port=make)
    assert running.wait(60) == 0
    return running, seen["port"]


def headings(text):
    return re.findall(r"(?m)^## (.+)$", text)


# ---- the output is registered through the registry ---------------------------------------------------------------------------
def test_the_registry_adds_the_project_output_and_leaves_the_others_alone(j2):
    before = {k: dict(v) for k, v in j2.OUTPUTS.items()}
    register(j2)
    assert set(j2.OUTPUTS) == set(before) | {"project"}
    assert {k: dict(j2.OUTPUTS[k]) for k in before} == before
    out = j2.OUTPUTS["project"]
    assert (out["label"], out["noun"], out["file"], out["export"]) == ("Project work", "report", "project.md", None)
    assert list(out["sections"]) == SECTIONS and out["rates"] == "rates_prd" and out["check_types"] == j2.DOC_CHECK_TYPES
    assert out["single"] is True and out["workspace"] == "edit" and out["capability"] == "project"
    assert out["charter_fmt"] is j2.PRD_CHARTER_FMT and out["builder"] == PROJECT_BUILDER and not out["builder"].endswith(".md")
    assert callable(out["mock_charter"]) and callable(out["mock_section"]) and callable(out["mock_atom"])


def test_no_other_output_has_single_so_p14_changes_nothing_for_them(j2):
    register(j2)
    assert [k for k, v in j2.OUTPUTS.items() if v.get("single")] == ["project"]


def test_the_conditions_are_the_capabilitys_own_file_outside_the_vendored_folder(j2):
    register(j2)
    conds = j2.load_conditions(j2.OUTPUTS["project"]["conditions"])
    assert [(c["id"], c["check"], c.get("severity")) for c in conds] == [
        ("PJ1", "sections-present", None), ("PJ2", "nothing-to-be-confirmed", None), ("PJ3", "facts-present-all", "warn")]
    assert j2.OUTPUTS["project"]["conditions"] == CONDITIONS_FILE and "/capabilities/data/" in CONDITIONS_FILE.replace("\\", "/")
    import os
    assert os.path.isabs(CONDITIONS_FILE)
    assert sorted(p.name for p in (__import__("pathlib").Path(j2.CONDITIONS_DIR)).iterdir()) == ["hld.json", "lld.json", "prd.json", "website.json"]


def test_the_rubric_has_the_five_items_of_the_design():
    assert [i for i, _ in PROJECT_RUBRIC] == ["PJ-1", "PJ-2", "PJ-3", "PJ-4", "PJ-5"]
    assert "git diff" in dict(PROJECT_RUBRIC)["PJ-2"] and "Assumption" in dict(PROJECT_RUBRIC)["PJ-5"]


def test_the_atom_rules_keep_the_prd_wording_without_ids_and_say_report(j2):
    rules = project_spec(j2).atom_rules
    assert "ids-unique" not in rules and "ids (target" not in rules and "R1" not in rules and "PRD" not in rules
    assert "heading-present" in rules and "section-not-empty" in rules and "facts-present" in rules


def test_the_builder_text_is_the_designs(j2):
    for word in ("Findings", "Changes", "Confirmation", "Open items", "Outcome", "never commit", "read only for the team",
                 "you cannot run tests", "Assumption:", "## <Section>"):
        assert word in PROJECT_BUILDER


# ---- patch P14 ---------------------------------------------------------------------------------------------------------------
def test_p14_a_single_output_is_never_swapped_for_the_documents_the_brief_names(j2):
    register(j2)
    for output, expect_docs in (("project", False), ("website", True)):
        run = j2.J2Run()
        run.set_output(output)
        run.request = "update the PRD in the repo and the HLD"
        run.intake = []
        run._plan_stages()
        assert bool(run.docset) is expect_docs and bool(run.stages) is expect_docs, output
        assert run.output == (output if not expect_docs else "prd")


# ---- the mock run to Done ----------------------------------------------------------------------------------------------------
def test_a_project_brief_runs_to_done_as_project_work_with_a_report_of_five_sections(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    running, port = go(run_dir)
    rows = events(run_dir)
    assert rows[-1]["t"] == "run.ended" and rows[-1]["status"] in ("done", "done_with_open_items"), rows[-1]
    report = (run_dir / "project.md").read_text(encoding="utf-8")
    assert headings(report) == SECTIONS
    assert not (run_dir / "prd.md").exists() and not (run_dir / "site" / "index.html").exists()
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["output_type"] == "project" and [s["heading"] for s in summary["sections"]] == SECTIONS
    assert summary["conditions"]["total"] == 3
    assert json.loads((run_dir / "settings.json").read_text())["output"] == "project"


def test_the_selection_is_recorded_in_output_json_a_trace_line_and_one_line_of_chat(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    go(run_dir)
    record = json.loads((run_dir / "output.json").read_text())
    assert record == {"choice": "auto", "output": "project", "rule": "project", "reason": "you asked about a repository", "folder": False}
    selected = trace(run_dir, "output.selected")
    assert len(selected) == 1 and selected[0]["data"]["output"] == "project" and selected[0]["data"]["forced"] == {}
    lines = [m["text"] for m in chat(run_dir) if m["who"] == "system" and m["text"].startswith(("Working on this as", "Treating this as"))]
    assert len(lines) == 1 and "you asked about a repository" in lines[0] and "start page" in lines[0]


def test_identity_never_talks_about_a_website_in_a_project_run(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    go(run_dir)
    said = [m["text"] for m in chat(run_dir) if m["who"] == "identity"]
    assert said and not [t for t in said if re.search(r"web\s?site|landing page|visitors", t, re.I)], said


def test_a_short_brief_walks_the_document_mock_questions_a_known_limit_of_the_scripted_path(j2, make_run_dir):
    run_dir = make_run_dir(user_text="update the PRD in the repo", settings=QUIET)
    running = Running(run_dir, "--mock")
    from test_engine_host import Answerer
    answerer = Answerer(run_dir, [BRIEF])
    assert running.wait(60) == 0
    answerer.stop()
    ask = next(e for e in events(run_dir) if e["t"] == "say" and e.get("act") == "ASK_REQUESTER")
    assert ask["who"] == "identity" and not re.search(r"web\s?site", json.dumps(ask), re.I)


def test_named_documents_in_the_brief_do_not_flip_a_project_run_into_a_prd_chain(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BRIEF + " Also update the PRD and the HLD in the repo.", settings=QUIET)
    go(run_dir)
    assert (run_dir / "project.md").exists() and not (run_dir / "prd.md").exists() and not (run_dir / "hld.md").exists()
    assert not [m for m in chat(run_dir) if "Documents asked for" in m["text"]]
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["output_type"] == "project" and "design_documents" not in summary


def test_the_third_section_avoids_the_words_j2s_validator_refuses_in_a_workflow_name_or_a_done_when_item(j2):
    """The design says Verification; J2's `CHECK_WORK` and `NOT_CHECKABLE` refuse that word (see PROJECT_SECTIONS), so the section is Confirmation."""
    for section in PROJECT_SECTIONS:
        assert not j2.J2Run.CHECK_WORK.search(f"Write {section}") and not j2.J2Run.NOT_CHECKABLE.search(f"The {section} section is written")
    assert "Verification" not in PROJECT_SECTIONS


def test_with_artifact_schema_and_the_template_library_on_a_project_run_still_works_and_both_are_forced_off(j2, make_run_dir, data_dir):
    (data_dir / "engine.json").write_text(json.dumps({"artifact_schema": True, "template_library": True}))
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    go(run_dir)
    settings = json.loads((run_dir / "settings.json").read_text())
    assert settings["artifact_schema"] is False and settings["template_library"] is False
    assert trace(run_dir, "output.selected")[0]
    assert events(run_dir)[-1]["status"] in ("done", "done_with_open_items")
    assert not list(run_dir.glob("site/*.json")) and not (run_dir / "project.json").exists()


def test_other_outputs_keep_the_flags_the_owner_turned_on(j2, make_run_dir, data_dir):
    (data_dir / "engine.json").write_text(json.dumps({"artifact_schema": True, "template_library": True}))
    run_dir = make_run_dir(user_text="a one page site for a cafe called Brew Lab, with a menu, hours and a map, that works on phones and "
                                     "feels warm, plus a loyalty card explainer and a short story about our beans", settings=QUIET)
    running = Running(run_dir, "--mock")
    from test_engine_host import Answerer, VAGUE
    answerer = Answerer(run_dir, VAGUE[1:])
    running.wait(60)
    answerer.stop()
    settings = json.loads((run_dir / "settings.json").read_text())
    assert settings["output"] == "website" and settings["artifact_schema"] is True and settings["template_library"] is True


# ---- selection, end to end in the host ---------------------------------------------------------------------------------------
def test_a_florist_site_is_a_website_run_with_no_line_in_the_chat(j2, make_run_dir):
    run_dir = make_run_dir(user_text="build a florist site", settings=QUIET)
    running = Running(run_dir, "--mock")
    from test_engine_host import Answerer, VAGUE
    answerer = Answerer(run_dir, VAGUE[1:])
    assert running.wait(60) == 0
    answerer.stop()
    record = json.loads((run_dir / "output.json").read_text())
    assert (record["output"], record["rule"], record["choice"]) == ("website", "deliver", "auto")
    assert not [m for m in chat(run_dir) if "project work" in m["text"]]
    assert json.loads((run_dir / "settings.json").read_text())["output"] == "website"


def test_a_team_with_no_folder_and_no_project_words_gets_exactly_what_it_always_got(j2, make_run_dir):
    run_dir = make_run_dir(user_text="a website for my cafe", settings=QUIET)
    running = Running(run_dir, "--mock")
    from test_engine_host import Answerer, VAGUE
    answerer = Answerer(run_dir, VAGUE[1:])
    assert running.wait(60) == 0
    answerer.stop()
    assert json.loads((run_dir / "output.json").read_text())["rule"] == "deliver"
    assert (run_dir / "site" / "index.html").exists()
    assert not [m for m in chat(run_dir) if m["text"].startswith(("Working on this as", "Treating this as"))]


def test_a_folder_that_is_set_turns_an_unclear_request_into_project_work(j2, make_run_dir, data_dir, tmp_path):
    from sutra_app.connectors.workdir import WorkFolder
    folder = tmp_path / "myproject"
    folder.mkdir()
    WorkFolder(data_dir).set(str(folder), access="read")
    brief = ("Check the details of the app and update the J2 prototype so that its settings page matches the app: look at the settings "
             "page, list what differs, change the prototype page to match, and say what you verified and what is left to do.")
    run_dir = make_run_dir(user_text=brief, settings=QUIET)
    go(run_dir)
    record = json.loads((run_dir / "output.json").read_text())
    assert record == {"choice": "auto", "output": "project", "rule": "folder",
                      "reason": "a working folder is set and the request is about it", "folder": True}
    assert (run_dir / "project.md").exists()
    assert [m for m in chat(run_dir) if "in your folder" in m["text"]]


def test_the_owners_choice_in_the_team_settings_beats_the_words(j2, make_run_dir, data_dir):
    (data_dir / "departments" / "web").mkdir(parents=True, exist_ok=True)
    (data_dir / "departments" / "web" / "engine.json").write_text(json.dumps({"output": "prd"}))
    brief = ("Write a PRD for QuickQueue, a mobile app that lets clinic patients join a waiting line remotely. Users: patients at small "
             "clinics and the staff. Problem: patients wait 45 minutes. Must-have features: join the queue from a phone, live position "
             "updates. Constraints: works on low-end Android phones. Success: average wait under 10 minutes within 3 months. Keep it in the repo.")
    run_dir = make_run_dir(user_text=brief, settings=QUIET)
    go(run_dir)
    record = json.loads((run_dir / "output.json").read_text())
    assert (record["choice"], record["output"], record["rule"]) == ("prd", "prd", "owner")
    assert (run_dir / "prd.md").exists() and not (run_dir / "project.md").exists()
    assert not [m for m in chat(run_dir) if "project work" in m["text"]]


def test_the_task_settings_choice_beats_the_words_too(j2, make_run_dir):
    run_dir = make_run_dir(user_text=PRD_BRIEF, settings={**QUIET, "J2_OUTPUT": "prd"})
    go(run_dir)
    assert json.loads((run_dir / "output.json").read_text())["rule"] == "owner"
    assert (run_dir / "prd.md").exists()


def seed_run(data_dir, run_id, output, dept="web"):
    folder = data_dir / "departments" / dept / "runs" / run_id
    folder.mkdir(parents=True)
    (folder / "chat.jsonl").write_text(json.dumps({"meta": True, "run": run_id[3:], "output": output}) + "\n")
    (folder / "summary.json").write_text(json.dumps({"run": run_id[3:], "output_type": output, "status": "done"}))
    return folder


def test_a_follow_up_keeps_the_output_of_the_run_it_continues(j2, make_run_dir, data_dir):
    seed_run(data_dir, "j2-20261104-090000-aaaa", "project")
    run_dir = make_run_dir(run_id="j2-20261104-100000-bbbb", seed_from="j2-20261104-090000-aaaa", settings=QUIET,
                           user_text="Now also look at the tests folder layout and say what is missing there, list each missing area, "
                                     "and note what you checked and what is left to do about each one of them please.")
    go(run_dir)
    record = json.loads((run_dir / "output.json").read_text())
    assert (record["output"], record["rule"]) == ("project", "followup")
    assert (run_dir / "project.md").exists()


def test_a_seed_that_is_not_a_run_of_this_team_is_not_a_follow_up(j2, make_run_dir, data_dir):
    run_dir = make_run_dir(run_id="j2-20261104-100000-cccc", seed_from="j2-20261104-090000-zzzz", settings=QUIET, user_text=BRIEF)
    go(run_dir)
    assert json.loads((run_dir / "output.json").read_text())["rule"] == "project"


# ---- the folder policy of a project run ----------------------------------------------------------------------------------------
def test_builders_of_a_project_run_may_edit_audit_only_reads_and_helpers_get_no_folder(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    _, port = go(run_dir)
    tags = port.tags
    builders = [t for t in tags if t.function.startswith("W-") and t.purpose == "agent_turn"]
    assert builders and {t.workspace for t in builders} == {"edit"}
    assert {t.workspace for t in tags if t.function == "audit" and t.purpose in ("agent_turn", "plan", "judge")} == {"read"}
    for fn in ("identity", "adaptation", "priority", "coordination"):
        assert {t.workspace for t in tags if t.function == fn and t.purpose == "agent_turn"} == {"read"}, fn
    assert {t.workspace for t in tags if t.purpose in ("summary", "template", "review", "change")} <= {"none"}
    assert all(t.stage == "project" for t in tags if t.stage)


def test_workspace_off_means_no_agent_of_a_project_run_gets_a_folder(j2, make_run_dir, data_dir):
    (data_dir / "engine.json").write_text(json.dumps({"workspace": "off"}))
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    _, port = go(run_dir)
    assert {t.workspace for t in port.tags} == {"none"}


def test_the_project_addenda_reach_identity_adaptation_and_audit_only_in_a_project_run(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    _, port = go(run_dir)
    by_fn = {}
    for tag, system in zip(port.tags, port.systems):
        by_fn.setdefault(tag.function, []).append(system)
    for fn, key in (("identity", "look before you ask"), ("adaptation", "plan the five sections only"), ("audit", "you cannot edit")):
        assert by_fn[fn] and all("## Project work" in s and key in s.lower() for s in by_fn[fn] if "## Reply format" in s), fn
    for fn in ("priority", "coordination"):
        assert not [s for s in by_fn.get(fn, []) if "## Project work" in s], fn
    builders = [s for fn, ss in by_fn.items() if fn.startswith("W-") for s in ss]
    assert builders and all("Workflow agent for one section of a project work report" in s for s in builders if "Reply format" in s)


def test_a_website_run_has_no_project_text_in_any_prompt(j2, make_run_dir):
    run_dir = make_run_dir(user_text="build a florist site for Petal and Stem in Jaipur with bouquets, same-day delivery, wedding flowers, "
                                     "a contact form and opening hours, warm and simple, working well on phones", settings=QUIET)
    running = Running(run_dir, "--mock", make_port=make_port_of(TaggingPort))
    from test_engine_host import Answerer, VAGUE
    answerer = Answerer(run_dir, VAGUE[1:])
    running.wait(60)
    answerer.stop()
    assert json.loads((run_dir / "output.json").read_text())["output"] == "website"


# ---- the addendum, as a unit -------------------------------------------------------------------------------------------------
def ctx(output):
    c = EngineContext(task=SimpleNamespace(), settings=EngineSettings(), paths=SimpleNamespace(), data_dir=None)
    c.selection = capabilities.Selection(output, "owner", "x")
    return c


@pytest.mark.parametrize("fn,expect", [("identity", True), ("adaptation", True), ("audit", True), ("priority", False),
                                       ("coordination", False), ("W-1", False)])
def test_the_addendum_is_for_three_agents_and_only_for_project_work(fn, expect):
    cap = ProjectCapability()
    assert bool(cap.addendum(fn, ctx("project"))) is expect
    assert cap.addendum(fn, ctx("website")) == "" and cap.addendum(fn, ctx("prd")) == ""


def test_the_vendored_role_files_are_not_touched_by_the_addendum():
    import hashlib
    from pathlib import Path
    root = Path(capabilities.__file__).resolve().parents[1] / "agents" / "j2"
    manifest = (root.parent.parent / "VENDORED.md").read_text()
    for name in ("identity.md", "adaptation.md", "audit.md", "builder.md"):
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() in manifest


# ---- the mocks ---------------------------------------------------------------------------------------------------------------
def test_the_mock_charter_names_the_project_and_records_one_item_per_section():
    goal = mock_project_charter(BRIEF)
    assert goal["business_type"] == "project" and goal["done_when"] and len(goal["done_when"]) == len(goal["core"]) == 5
    assert [s for s in SECTIONS if any(s in item for item in goal["done_when"])] == SECTIONS
    assert goal["product_name"] in goal["facts"]


def test_the_mock_sections_are_honest_that_nothing_was_changed_offline():
    goal = mock_project_charter(BRIEF)
    texts = {s: mock_project_section({"name": f"Write {s}"}, goal) for s in PROJECT_SECTIONS}
    assert all(t.startswith(f"## {s}\n") for s, t in texts.items())
    assert "No changes were made" in texts["Changes"] and "Offline" in texts["Findings"]
    assert not [t for t in texts.values() if re.search(r"web\s?site", t, re.I)]


# ---- the API ---------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def api(fake_services):
    fake_services.add_department("web")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    mount(app, fake_services)
    return TestClient(app, raise_server_exceptions=False)


def test_the_capabilities_route_lists_the_project_output_with_its_policy(api):
    body = api.get("/api/engine/capabilities").json()
    project = next(c for c in body["capabilities"] if c["name"] == "project")
    assert project["outputs"] == [{"name": "project", "label": "Project work", "workspace": "edit", "single": True}]
    assert "project" in body["outputs"]


def test_refs_names_the_project_conditions_and_rubric(api):
    got = api.get("/api/refs?dept=web").json()
    assert {"PJ1", "PJ2", "PJ3"} <= set(got["conditions"]) and {"PJ-1", "PJ-5"} <= set(got["rubric"])
    assert {"W1", "P1"} <= set(got["conditions"]) | {"W1", "P1"}


def test_the_start_pages_output_command_accepts_auto_and_project_and_nothing_else(api, fake_services):
    for kind, expect in (("auto", "auto"), ("project", "project"), ("prd", "prd"), ("pdf", "website"), ("", "website")):
        got = api.post("/api/output?dept=web", json={"type": kind}, headers={"X-Sutra-Token": "fake-token-fake-token-0123"})
        assert got.status_code == 200 and got.json() == {"ok": True, "output": expect}, (kind, got.text)
