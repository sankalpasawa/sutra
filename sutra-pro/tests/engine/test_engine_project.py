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
from sutra_app.connectors.workdir import WorkFolder
from sutra_app.engine.capabilities import project as project_module
from sutra_app.engine.capabilities.project import (CHECK_TYPES, CONDITIONS_FILE, DATA, PROJECT_BUILDER, PROJECT_INTAKE, PROJECT_RUBRIC, PROJECT_SECTIONS,
                                                   ProjectCapability, mock_project_charter, mock_project_section, project_spec)
from sutra_app.engine.spec import EngineSettings

from test_engine_host import BREW_LAB, QUIET, Running, chat, events, j2, jsonl, make_port_of, of, trace   # noqa: F401  (fixtures and helpers)

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
        self.tags, self.systems, self.users = [], [], []

    def complete(self, req, on_progress=None):
        self.tags.append(req.tag)
        self.systems.append(req.system)
        self.users.append(req.user)
        return super().complete(req, on_progress)


def go(run_dir, port_cls=TaggingPort):
    seen = {}

    def make(*, sink, mock, task, paths):
        seen["port"] = port_cls(usage_sink=sink)
        return seen["port"]
    running = Running(run_dir, "--mock", make_port=make)
    assert running.wait(60) == 0
    return running, seen["port"]


def running_systems(run_dir):
    """The system text of every call the run made (calls.jsonl)."""
    return [json.loads(line)["system"] for line in (run_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def headings(text):
    return re.findall(r"(?m)^## (.+)$", text)


# ---- the output is registered through the registry ---------------------------------------------------------------------------
def test_the_registry_adds_the_project_type_and_leaves_the_others_alone(j2):
    before = {n: j2.output_def(n) for n in j2.j2_types.names() if n != "project"}
    register(j2)
    names = j2.j2_types.names()
    assert names.count("project") == 1 and [n for n in names if n != "project"] == list(before)
    assert {n: j2.output_def(n) for n in before} == before
    out = j2.output_def("project")
    assert (out["label"], out["noun"], out["file"], out["export"]) == ("Project work", "report", "project.md", None)
    assert list(out["sections"]) == SECTIONS and out["rates"] == "rates_prd" and out["check_types"] == tuple(CHECK_TYPES)
    assert out["single"] is True and out["workspace"] == "edit" and out["deliver"] is True
    assert out["charter_fmt"] == (DATA / "project.charter.txt").read_text(encoding="utf-8")[:-1]
    assert out["intake"] == PROJECT_INTAKE and out["builder"] == PROJECT_BUILDER
    assert callable(out["mock_charter"]) and callable(out["mock_section"]) and callable(out["mock_atom"])
    assert out["mock_charter"] is mock_project_charter, "the capability's own mock, not the document form's"


def test_the_project_type_is_no_planners_choice_and_no_template_librarys_artifact(j2):
    register(j2)
    entry = next(e for e in j2.j2_types.entries() if e.get("name") == "project")
    assert entry["deliverable"] is False and entry["host"] == "project" and "project" not in j2.j2_types.templated()
    assert json.loads(json.dumps(entry)) == entry, "no callable in an entry that a route may dump"
    for kind in j2.j2_types.names():
        assert j2.j2_types.info(kind)["name"] == kind


def test_no_other_output_has_single_so_p14_changes_nothing_for_them(j2):
    register(j2)
    assert [k for k in j2.j2_types.names() if j2.output_def(k).get("single")] == ["project"]


def test_the_conditions_are_the_capabilitys_own_file_outside_the_vendored_folder(j2):
    register(j2)
    conds = j2.load_conditions(j2.output_def("project")["conditions"])
    assert [(c["id"], c["check"], c.get("severity")) for c in conds] == [
        ("PJ1", "sections-present", None), ("PJ2", "nothing-to-be-confirmed", None), ("PJ3", "facts-present-all", "warn")]
    assert j2.output_def("project")["conditions"] == CONDITIONS_FILE and "/capabilities/data/" in CONDITIONS_FILE.replace("\\", "/")
    import os
    assert os.path.isabs(CONDITIONS_FILE)
    assert "project.json" not in sorted(p.name for p in (__import__("pathlib").Path(j2.j2_types.CONDITIONS_DIR)).iterdir())


def test_the_rubric_has_the_five_items_of_the_design():
    assert [i for i, _ in PROJECT_RUBRIC] == ["PJ-1", "PJ-2", "PJ-3", "PJ-4", "PJ-5"]
    assert "git diff" in dict(PROJECT_RUBRIC)["PJ-2"] and "Assumption" in dict(PROJECT_RUBRIC)["PJ-5"]


def test_the_atom_rules_keep_the_prd_wording_without_ids_and_say_report(j2):
    rules = project_module._data("project.atom_rules.md")
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


def test_the_third_section_avoids_the_words_j2s_validator_refuses_in_a_done_when_item(j2):
    """The design says Verification; J2's `NOT_CHECKABLE` refuses that word in a done-when item (see PROJECT_SECTIONS), so the section is Confirmation."""
    for section in PROJECT_SECTIONS:
        assert not j2.J2Run.NOT_CHECKABLE.search(f"The {section} section is written")
    assert "Verification" not in PROJECT_SECTIONS


def test_with_artifact_schema_and_the_template_library_on_a_project_run_still_works_and_both_are_forced_off(j2, make_run_dir, data_dir):
    (data_dir / "engine.json").write_text(json.dumps({"artifact_schema": True, "template_library": True}))
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    go(run_dir)
    settings = json.loads((run_dir / "settings.json").read_text())
    assert settings["artifact_schema"] is False and settings["template_library"] is False
    assert trace(run_dir, "output.selected")[0]
    assert events(run_dir)[-1]["status"] in ("done", "done_with_open_items")
    assert not list(run_dir.glob("site/*.json")), "no artifact-schema section files: that machinery is off for a project run"
    assert not (run_dir / "project.json").exists(), "J2 sync 5 treats every document type alike: no artifact-schema data, so no project.json guide"


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
    assert settings["output"] == "auto" and settings["artifact_schema"] is True and settings["template_library"] is True


# ---- selection, end to end in the host ---------------------------------------------------------------------------------------
def test_a_florist_site_is_left_to_the_planner_with_no_line_in_the_chat(j2, make_run_dir):
    run_dir = make_run_dir(user_text="build a florist site", settings=QUIET)
    running = Running(run_dir, "--mock")
    from test_engine_host import Answerer, VAGUE
    answerer = Answerer(run_dir, VAGUE[1:])
    assert running.wait(60) == 0
    answerer.stop()
    record = json.loads((run_dir / "output.json").read_text())
    assert (record["output"], record["rule"], record["choice"], record["reason"]) == (None, "planner", "auto", "the team's planner chooses")
    assert not [m for m in chat(run_dir) if "project work" in m["text"]]
    assert json.loads((run_dir / "settings.json").read_text())["output"] == "auto"
    assert trace(run_dir, "output.selected")[0]["data"]["output"] is None


def test_a_team_with_no_folder_and_no_project_words_gets_a_page_the_planner_chose(j2, make_run_dir):
    run_dir = make_run_dir(user_text="a website for my cafe", settings=QUIET)
    running = Running(run_dir, "--mock")
    from test_engine_host import Answerer, VAGUE
    answerer = Answerer(run_dir, VAGUE[1:])
    assert running.wait(60) == 0
    answerer.stop()
    assert json.loads((run_dir / "output.json").read_text())["rule"] == "planner"
    assert (run_dir / "site" / "index.html").exists(), "J2's planner chose the page type"
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
def test_builders_of_a_project_run_may_edit_audit_looks_at_git_and_helpers_get_no_folder(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    _, port = go(run_dir)
    tags = port.tags
    builders = [t for t in tags if t.function.startswith("W-") and t.purpose == "agent_turn"]
    assert builders and {t.workspace for t in builders} == {"edit"}
    assert {t.workspace for t in tags if t.function == "audit" and t.purpose in ("agent_turn", "plan", "judge")} == {"inspect"}      # D135: reads files and git, changes nothing
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


def test_a_run_the_planner_chose_has_no_project_text_in_any_prompt(j2, make_run_dir):
    run_dir = make_run_dir(user_text="build a florist site for Petal and Stem in Jaipur with bouquets, same-day delivery, wedding flowers, "
                                     "a contact form and opening hours, warm and simple, working well on phones", settings=QUIET)
    running = Running(run_dir, "--mock", make_port=make_port_of(TaggingPort))
    from test_engine_host import Answerer, VAGUE
    answerer = Answerer(run_dir, VAGUE[1:])
    running.wait(60)
    answerer.stop()
    assert json.loads((run_dir / "output.json").read_text())["output"] is None
    assert not [s for s in running_systems(run_dir) if "## Project work" in s]


# ---- honest capability text (D135): what the owner allowed reaches the charter and the team's own words ---------------------------------------------
UPDATE_BRIEF = ("Check the details of the app in the repo and update README.md so that its first section matches the app: add the line "
                "'checked by the team' at the end of README.md, list what you changed, and say what you verified and what is left to do.")
LOOK_BRIEF = ("Look at the folder of the app in the repo and list its top-level files, say what each one is for, and report which of them the "
              "settings page reads, naming each file and saying what you could not check and what is left to look at.")
READ_ONLY = re.compile(r"read[- ]only", re.I)


@pytest.fixture(autouse=True)
def unbound_mock_policy():
    """The scripted Identity asks the store the host bound for the run; a unit test that calls the mock directly starts from none."""
    project_module.bind_data_dir(None)
    yield
    project_module.bind_data_dir(None)


def choose_folder(data_dir, tmp_path, access):
    folder = tmp_path / "myproject"
    folder.mkdir(exist_ok=True)
    WorkFolder(data_dir).set(str(folder), access=access)
    return folder


def charter_of(run_dir):
    return json.loads((run_dir / "goal.json").read_text(encoding="utf-8"))


def limits_of(goal):
    return " | ".join([*goal["constraints"], *goal["rules"]])


def test_the_charter_of_an_update_brief_has_no_read_only_limit_when_the_owner_allowed_changes(j2, make_run_dir, data_dir, tmp_path):
    choose_folder(data_dir, tmp_path, "edit")
    run_dir = make_run_dir(user_text=UPDATE_BRIEF, settings=QUIET)
    go(run_dir)
    goal = charter_of(run_dir)
    assert not READ_ONLY.search(limits_of(goal)), limits_of(goal)
    assert "Do not change any file" not in limits_of(goal) and "no code or files in the folder are changed" not in limits_of(goal)
    changes = next(item for item in goal["done_when"] if "Changes section" in item)
    assert "README.md" in changes and "lists each change made" in changes          # the files to change are named
    assert goal["features"] and any("update readme.md" in f.lower() for f in goal["features"])


def test_the_charter_of_an_update_brief_says_read_only_plainly_when_the_owner_chose_read_only(j2, make_run_dir, data_dir, tmp_path):
    choose_folder(data_dir, tmp_path, "read")
    run_dir = make_run_dir(user_text=UPDATE_BRIEF, settings=QUIET)
    go(run_dir)
    goal = charter_of(run_dir)
    assert READ_ONLY.search(limits_of(goal)) and "Settings, under Working folder" in limits_of(goal)
    assert "Do not change any file in the working folder" in goal["rules"]
    changes = next(item for item in goal["done_when"] if "Changes section" in item)
    assert "cannot be made" in changes and "exact edits file by file" in changes and "how to allow changes" in changes


def test_with_no_folder_an_update_brief_is_not_told_the_folder_is_read_only(j2, make_run_dir):
    run_dir = make_run_dir(user_text=UPDATE_BRIEF, settings=QUIET)
    go(run_dir)
    assert not READ_ONLY.search(limits_of(charter_of(run_dir)))


@pytest.mark.parametrize("access", ["edit", "read"])
def test_a_brief_that_only_looks_stays_a_report_whatever_the_owner_allowed(j2, make_run_dir, data_dir, tmp_path, access):
    choose_folder(data_dir, tmp_path, access)
    run_dir = make_run_dir(user_text=LOOK_BRIEF, settings=QUIET)
    go(run_dir)
    goal = charter_of(run_dir)
    changes = next(item for item in goal["done_when"] if "Changes section" in item)
    assert "says no change was asked" in changes and not READ_ONLY.search(limits_of(goal)), limits_of(goal)
    assert "The request asks for no change" in limits_of(goal)


def test_the_scripted_identity_reads_the_access_the_host_bound_and_a_direct_call_can_say_it(data_dir, tmp_path):
    assert not READ_ONLY.search(limits_of(mock_project_charter(UPDATE_BRIEF)))                       # nothing bound: no folder, no claim
    choose_folder(data_dir, tmp_path, "read")
    project_module.bind_data_dir(data_dir)
    assert READ_ONLY.search(limits_of(mock_project_charter(UPDATE_BRIEF)))
    assert not READ_ONLY.search(limits_of(mock_project_charter(UPDATE_BRIEF, access="edit")))        # an explicit access wins over the store
    WorkFolder(data_dir).set_access("edit")
    assert not READ_ONLY.search(limits_of(mock_project_charter(UPDATE_BRIEF)))                       # read again on every call: a change applies at once


def test_every_call_of_a_project_run_that_has_a_folder_says_what_the_team_may_do(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    _, port = go(run_dir)
    asked = [t for t in port.tags if t.workspace != "none"]
    assert asked and {t.team_workspace for t in asked} == {"edit"}
    assert {t.team_workspace for t in port.tags if t.workspace == "none"} == {"none"}                 # a helper call has no folder and says nothing of a team
    assert {f for t in asked for f in [t.function] if f in ("identity", "adaptation", "priority", "coordination", "audit")} == {
        "identity", "adaptation", "priority", "coordination", "audit"}


def test_a_website_run_never_says_anything_about_a_team(j2, make_run_dir):
    run_dir = make_run_dir(user_text="build a florist site for Petal and Stem in Jaipur with bouquets, same-day delivery, wedding flowers, "
                                     "a contact form and opening hours, warm and simple, working well on phones", settings=QUIET)
    running = Running(run_dir, "--mock", make_port=make_port_of(TaggingPort))
    from test_engine_host import Answerer, VAGUE
    answerer = Answerer(run_dir, VAGUE[1:])
    running.wait(60)
    answerer.stop()
    assert {t.team_workspace for t in running.host.port.tags} == {"none"}


def test_the_intake_says_what_the_brief_means_and_when_read_only_may_be_written():
    for words in ("update, implement, fix, change or add something", "the goal includes making that change in the folder",
                  "names the files to change", "only asks to look, list, check or report stays a report",
                  "Your own tools only read because you plan; that is not a limit of the run, so never put it in the charter",
                  "\"Folder is read-only\" in constraints or rules only when that text says the owner chose read only",
                  "gives the exact edits file by file, and says how to allow changes (Settings, under Working folder)"):
        assert words in PROJECT_INTAKE, words
    assert "the owner" in PROJECT_INTAKE and PROJECT_INTAKE.startswith("J2.a for project work in the owner's working folder.")


def test_the_intake_reaches_identity_after_j2s_own_prompt_in_a_project_run(j2, make_run_dir):
    run_dir = make_run_dir(user_text=UPDATE_BRIEF, settings=QUIET)
    _, port = go(run_dir)
    intake = [u for t, u in zip(port.tags, port.users) if t.function == "identity" and "REQUESTER'S BRIEF" in u]
    assert intake and all(PROJECT_INTAKE in u for u in intake)
    assert all(u.index("REQUESTER'S BRIEF") < u.index(PROJECT_INTAKE) for u in intake)                 # J2's brief and answers first, the output's rules after them
    assert not [u for t, u in zip(port.tags, port.users) if t.function != "identity" and PROJECT_INTAKE in u]


def test_a_builder_is_told_not_to_fence_its_whole_reply_and_to_fence_blocks_with_tildes():
    """A live run: the builder wrapped its reply in a code fence and put an edit in a second one; the first closing fence ended the section, and the exact edit
    the owner needed was lost."""
    for words in ("never inside a code fence of its own", "fenced with three tildes (~~~), never three backticks", "so it cannot end the section early"):
        assert words in PROJECT_BUILDER, words


def test_audit_is_told_to_check_every_claimed_change_against_the_folder_with_git_diff():
    text = project_module.ADDENDA["audit"]
    for words in ("git diff", "git status", "the report claims that the folder does not show has not been made", "You cannot edit anything"):
        assert words in text
    assert "never describe a change instead of making it" in PROJECT_BUILDER and "how to allow changes" in PROJECT_BUILDER


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


def test_the_start_pages_output_command_accepts_auto_and_a_type_of_the_data_and_pins_nothing_else(api, fake_services):
    for kind, expect in (("auto", "auto"), ("project", "project"), ("prd", "prd"), ("pdf", None), ("", None)):
        got = api.post("/api/output?dept=web", json={"type": kind}, headers={"X-Sutra-Token": "fake-token-fake-token-0123"})
        assert got.status_code == 200 and got.json() == {"ok": True, "output": expect}, (kind, got.text)


# ---- the report in Artifacts (J2 sync 4, D146): a row of the Documents group made by the capability, with J2's own three tabs ------------
def register_run(fake_services, run_dir, dept="web"):
    """The run folder the host made, as a run of the department for the engine's routes."""
    ref = SimpleNamespace(run_id=run_dir.name, task_id="tsk_" + "0" * 12, dept_id=dept, dir=f"departments/{dept}/runs/{run_dir.name}", status="done")
    fake_services.runs.append(ref)
    return ref


def documents_of(api, ref):
    body = api.get(f"/api/artifacts/groups?dept=web&run={ref.run_id}").json()
    return body, next(g for g in body["groups"] if g["id"] == "documents")["rows"]


def test_a_project_runs_report_is_a_row_of_the_documents_group_with_the_summary_agent_and_human_tabs(j2, make_run_dir, api, fake_services):
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    go(run_dir)
    ref = register_run(fake_services, run_dir)
    body, rows = documents_of(api, ref)
    assert [r["id"] for r in rows] == ["project"], "J2 lists project.md itself; the capability's row is the fallback and is never a second one (D164)"
    row = rows[0]
    assert (row["kind"], row["name"], row["file"], row["doc_file"], row["nodes"], row["ok"]) == \
        ("document", "Project work report", "project.md", "project.md", [], True), "a report is not a Map node: nothing links to it"
    assert row["views"] == {"summary": True,
                            "agent": {"format": "text", "file": "project.md", "schema": None, "model": None, "valid": None},
                            "human": {"format": "markdown", "file": "project.md"}}, "no artifact-schema data: the agent tab reads the markdown"
    assert body["documents"] == {"project": {"sections": {}, "file": "project.md", "kind": "document"}}
    for name, start in (("project.md", "# The project"),):
        got = api.get(f"/api/artifact?dept=web&run={ref.run_id}&name={name}")
        assert got.status_code == 200 and got.text.lstrip().startswith(start), f"{name} is served: the tree lists every file of a run folder"
    page = api.get(f"/view?dept=web&run={ref.run_id}&name=project.md")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html") and "<h2>Findings</h2>" in page.text
    assert "sandbox" in page.headers["content-security-policy"], "a generated page is sandboxed like every html the engine serves (D83)"
    assert api.get(f"/doc/project?dept=web&run={ref.run_id}").text == page.text, "/doc/<name> is the same file as a page"


def test_a_website_run_and_a_prd_run_made_by_the_host_get_no_extra_row(j2, make_run_dir, api, fake_services):
    site = make_run_dir(run_id="j2-20261104-100001-aaaa", user_text=BREW_LAB, settings=QUIET)
    go(site)
    prd = make_run_dir(run_id="j2-20261104-100002-bbbb", user_text=PRD_BRIEF, settings={**QUIET, "J2_OUTPUT": "prd"})
    go(prd)
    for run_dir, expect in ((site, []), (prd, ["prd"])):
        ref = register_run(fake_services, run_dir)
        body, rows = documents_of(api, ref)
        assert [r["id"] for r in rows] == expect and set(body["documents"]) == set(expect), run_dir.name
    assert "project" not in {r["id"] for r in documents_of(api, SimpleNamespace(run_id=prd.name))[1]}


def test_a_capability_that_registers_a_second_output_with_a_report_file_is_listed_with_no_code_of_its_own(j2, make_run_dir, api, fake_services):
    """The registry's hook is the whole mechanism: a test capability adds an output with a `file`, and its run shows the row."""
    from sutra_app.engine.capabilities import OutputSpec
    thing = OutputSpec(name="thing", label="Thing", noun="note", sections=("One",), conditions="x.json", rubric=(("T-1", "t"),),
                       check_types=("heading-present",), builder="b", file="thing.md", done="Done")

    class Adds(Capability):
        name = "adds"

        def outputs(self):
            return {"thing": thing}
    capabilities.register(j2, [Adds()])
    try:
        run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
        go(run_dir)
        (run_dir / "thing.md").write_text("# Thing\n\nDone.\n", encoding="utf-8")
        chat_file = run_dir / "chat.jsonl"
        lines = chat_file.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        chat_file.write_text("\n".join([json.dumps({**first, "output": "thing"}), *lines[1:]]) + "\n", encoding="utf-8")
        ref = register_run(fake_services, run_dir)
        from sutra_app.engine import views
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(capabilities, "CAPABILITIES", (*capabilities.CAPABILITIES, Adds()))
            _, rows = documents_of(api, ref)
        assert "thing" in {r["id"] for r in rows}
        row = next(r for r in rows if r["id"] == "thing")
        assert (row["name"], row["file"]) == ("Thing note", "thing.md") and row["views"]["human"] == {"format": "markdown", "file": "thing.md"}
    finally:
        capabilities.SPECS.pop("thing", None)
        j2.j2_types.HOST.pop("thing", None)
        j2.j2_types._CACHE.clear()


# ---- J2 sync 5: the project run keeps its prompts and makes no planner call (D164, D165) ----------------------------------------------------
def test_a_project_run_makes_no_planner_call_and_its_prompts_carry_the_capabilitys_own_texts(j2, make_run_dir):
    run_dir = make_run_dir(user_text=BRIEF, settings=QUIET)
    go(run_dir)
    assert not (run_dir / "deliverables.json").exists(), "P14: a host-pinned project run is free of J2's deliverables planner (D129)"
    calls = [json.loads(line) for line in (run_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [c["fn"] for c in calls].count("adaptation") >= 1
    systems = {c["fn"]: c["system"] for c in calls}
    charter = (DATA / "project.charter.txt").read_text(encoding="utf-8")[:-1]
    identity = [c for c in calls if c["fn"] == "identity"]
    assert any(PROJECT_INTAKE in c["prompt"] for c in identity), "the intake text is in Identity's prompt"
    assert any(charter in c["system"] for c in identity), "the charter format is in Identity's reply format"
    builders = [c["system"] for c in calls if c["fn"].startswith("W-")]
    assert builders and all(PROJECT_BUILDER in s for s in builders)
    assert project_module.PROJECT_PLAN in systems["adaptation"], "the plan guidance moved into Adaptation's addendum"
    assert "## Project work" in systems["audit"]


def test_the_atom_rules_and_the_charter_still_equal_the_vendored_prd_texts_with_the_four_edits(j2):
    """The drift guard that `_atom_rules` was: fails loudly when J2's text under the project's copy moves (deviation 1: the prd type's files)."""
    from pathlib import Path
    templates = Path(j2.j2_types.HERE) / "templates" / "prd"
    edits = ((' ids (target: the id prefix, "R" for requirement ids R1, R2, ...),', ""),
             (' ids-unique (target: an id prefix, "R" for R1, R2, ...; expect true);', ""),
             ("in the PRD when", "in the report when"), ("on the PRD after", "on the report after"))
    rules = (templates / "atom_rules.md").read_text(encoding="utf-8")
    rules = rules[:-1] if rules.endswith("\n") else rules
    for old, new in edits:
        assert old in rules, old
        rules = rules.replace(old, new)
    assert project_module._data("project.atom_rules.md") == rules
    charter = (templates / "charter.txt").read_text(encoding="utf-8")
    assert project_module._data("project.charter.txt") == (charter[:-1] if charter.endswith("\n") else charter)


def test_the_template_file_equals_what_j2_writes_for_a_new_type_of_the_five_sections(j2):
    assert json.loads((DATA / "project.generic.json").read_text(encoding="utf-8")) == \
        j2.j2_types.template_for("project", "Project work", list(PROJECT_SECTIONS))
