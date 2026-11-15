"""A run template named by the request (J2 sync 6, D182): the host calls `J2Run.set_run_template` before the first line of the chat, says so in one
`system` line when it was not used, and never refuses a start for it. A follow-up ignores both task keys. Runs are the vendored J2 in mock mode;
the seed library's run template `thread-boutique-website` (made by a mock run, so eligible offline) is the one used."""
import json

import pytest

from test_engine_host import BREW_LAB, QUIET, Running, chat, events, j2, jsonl, trace   # noqa: F401  (fixtures and helpers)

TEMPLATE = "thread-boutique-website"


def started(make_run_dir, data_dir, settings=None, engine=None, text=BREW_LAB, **fields):
    if engine is not None:
        (data_dir / "engine.json").write_text(json.dumps(engine))
    run_dir = make_run_dir(user_text=text, settings={**QUIET, **(settings or {})}, **fields)
    running = Running(run_dir, "--mock")
    assert running.wait(60) == 0
    return run_dir, running


def system_lines(run_dir):
    return [m["text"] for m in chat(run_dir) if m.get("who") == "system"]


def requested(run_dir):
    rows = trace(run_dir, "run_template.requested")
    return rows[0]["data"] if rows else None


def test_a_request_with_the_template_starts_the_run_from_it_whole(j2, make_run_dir, data_dir):
    run_dir, running = started(make_run_dir, data_dir, {"J2_RUN_TEMPLATE": TEMPLATE, "J2_RUN_TEMPLATE_WORKFLOWS": "all"}, engine={"run_templates": True})
    assert requested(run_dir) == {"id": TEMPLATE, "workflows": "all", "taken": True, "why": None}
    record = json.loads((run_dir / "templates.json").read_text())
    assert record["run_template"]["id"] == TEMPLATE and len(record["run_template"]["selected"]) == record["run_template"]["of"] == 5
    assert not [line for line in system_lines(run_dir) if "was not used" in line]
    assert events(run_dir)[-1]["status"] in ("done", "done_with_open_items")
    assert any("Using run template" in line for line in system_lines(run_dir)), "J2's own line says it"


def test_a_request_with_selected_workflows_takes_only_those_and_what_they_need(j2, make_run_dir, data_dir):
    run_dir, _ = started(make_run_dir, data_dir, {"J2_RUN_TEMPLATE": TEMPLATE, "J2_RUN_TEMPLATE_WORKFLOWS": "W-1"}, engine={"run_templates": True})
    record = json.loads((run_dir / "templates.json").read_text())["run_template"]
    assert requested(run_dir)["taken"] is True and 1 <= len(record["selected"]) <= record["of"]
    assert record["selected"] != [] and len(record["selected"]) < record["of"], "not the whole template"


def test_a_template_with_the_flag_off_is_not_used_says_why_in_the_chat_and_the_run_starts_from_scratch(j2, make_run_dir, data_dir):
    run_dir, running = started(make_run_dir, data_dir, {"J2_RUN_TEMPLATE": TEMPLATE, "J2_RUN_TEMPLATE_WORKFLOWS": "all"})
    assert f"The run template {TEMPLATE} was not used: run templates are switched off in this team's settings; the team starts from scratch." in system_lines(run_dir)
    assert requested(run_dir)["taken"] is False and "switched off" in requested(run_dir)["why"]
    assert running.host.run.run_tpl is None
    assert events(run_dir)[-1]["status"] in ("done", "done_with_open_items"), "never a refused start"
    assert "run_template" not in json.loads((run_dir / "templates.json").read_text()) if (run_dir / "templates.json").exists() else True


def test_an_unknown_id_is_a_system_line_and_a_trace_line_not_a_failed_start(j2, make_run_dir, data_dir):
    run_dir, _ = started(make_run_dir, data_dir, {"J2_RUN_TEMPLATE": "no-such-template"}, engine={"run_templates": True})
    assert "The run template no-such-template was not used: the library has no run template with that id; the team starts from scratch." in system_lines(run_dir)
    assert requested(run_dir)["taken"] is False
    assert events(run_dir)[-1]["status"] in ("done", "done_with_open_items")


@pytest.mark.parametrize("settings, why", [({"J2_RUN_TEMPLATE": "Bad Id"}, "it is not a run template id"),
                                           ({"J2_RUN_TEMPLATE": TEMPLATE, "J2_RUN_TEMPLATE_WORKFLOWS": "a b"}, "the list of workflows is not valid")])
def test_a_bad_shape_is_refused_by_the_host_too_the_task_file_is_only_read(j2, make_run_dir, data_dir, settings, why):
    run_dir, _ = started(make_run_dir, data_dir, settings, engine={"run_templates": True})
    assert why in requested(run_dir)["why"] and requested(run_dir)["taken"] is False
    assert [line for line in system_lines(run_dir) if "was not used" in line and why in line]


def test_the_reuse_flags_that_imply_run_templates_count(j2, make_run_dir, data_dir):
    run_dir, _ = started(make_run_dir, data_dir, {"J2_RUN_TEMPLATE": TEMPLATE}, engine={"auto_reuse": True})
    assert requested(run_dir)["taken"] is True, "auto_reuse implies run_templates (effective(), D178)"


def test_a_project_run_never_takes_a_run_template_even_when_one_is_named(j2, make_run_dir, data_dir):
    chain = {"run_templates": True, "auto_reuse": True, "artifact_library": True}
    run_dir, running = started(make_run_dir, data_dir, {"J2_RUN_TEMPLATE": TEMPLATE}, engine=chain,
                               text=("Check the details of the app in the repo and update the J2 prototype so that its settings page matches the app: look at "
                                     "the settings code, list what differs, change the prototype page to match, and say what you verified and what is left to do."))
    assert running.host.selection.output == "project"
    assert requested(run_dir)["taken"] is False and "switched off" in requested(run_dir)["why"]
    assert not (run_dir / "templates.json").exists() or "run_template" not in json.loads((run_dir / "templates.json").read_text())


def test_no_key_means_no_line_no_trace_and_the_run_is_what_it_was(j2, make_run_dir, data_dir):
    run_dir, _ = started(make_run_dir, data_dir, engine={"run_templates": True})
    assert requested(run_dir) is None and not [line for line in system_lines(run_dir) if "run template" in line.lower()]


def test_a_follow_up_ignores_both_keys(j2, make_run_dir, data_dir):
    first, _ = started(make_run_dir, data_dir, engine={"run_templates": True}, text=BREW_LAB)
    second = make_run_dir(run_id="j2-20261104-100005-7f3b", user_text="Add a section for visiting hours", seed_from=first.name,
                          settings={**QUIET, "J2_RUN_TEMPLATE": TEMPLATE, "J2_RUN_TEMPLATE_WORKFLOWS": "all"})
    running = Running(second, "--mock")
    assert running.wait(60) == 0
    assert requested(second) is None and running.host.run.run_tpl is None
    assert not [line for line in system_lines(second) if "run template" in line.lower()]
