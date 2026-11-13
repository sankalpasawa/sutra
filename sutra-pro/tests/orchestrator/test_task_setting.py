"""A setting for the team's live run (J2 sync 4: the Simple view's Decide for me switch): `TaskService.send_setting` writes one inbox line,
`{"kind": "setting", "decide_for_me": bool}`, that the engine host reads; the eighth task key `J2_DECIDE_FOR_ME` starts a run with the
switch on. The route, the page's choice and the host are tested in tests/engine."""
import json

import pytest
from pydantic import ValidationError

from orchestrator.test_tasks import ask, tenv  # noqa: F401  (tenv is a fixture)
from sutra_app.engine.host.inbox import InboxTailer
from sutra_app.engine.spec import TASK_SETTING_KEYS
from sutra_app.orchestrator.models import TaskSettings
from sutra_app.orchestrator.runs import ProcessLauncher, inbox_line_count
from sutra_app.orchestrator.testing.fake_engine import ev


def lines(t, task):
    path = t.run_dir(task) / "inbox.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def test_a_setting_is_one_inbox_line_to_the_live_run_and_the_engine_reads_it(tenv):
    task = tenv.started()
    assert tenv.service.send_setting("web", {"decide_for_me": True}) is True
    assert tenv.service.send_setting("web", {"decide_for_me": False}) is True
    rows = lines(tenv, task)
    assert [(r["n"], r["kind"], r["decide_for_me"]) for r in rows] == [(1, "setting", True), (2, "setting", False)]
    assert all(r["at"].endswith("Z") and set(r) == {"n", "kind", "decide_for_me", "at"} for r in rows)
    got = InboxTailer(tenv.run_dir(task) / "inbox.jsonl").read_new()
    assert [(x.n, x.kind, x.decide_for_me) for x in got] == [(1, "setting", True), (2, "setting", False)], "the host reads what the server wrote"


def test_a_team_waiting_for_the_owner_gets_it_too_and_its_state_is_not_touched(tenv):
    task = tenv.started()
    ask(tenv, task)
    assert tenv.status(task) == "waiting_user"
    assert tenv.service.send_setting("web", {"decide_for_me": True}) is True
    assert tenv.status(task) == "waiting_user", "a setting is not an answer: the team still waits for the owner"
    assert tenv.graph.get("web.identity").state == "waiting_on_you" and tenv.row(task).inbox_seq == 0
    question = [m for m in tenv.chats.messages(tenv.graph.get("web").chat_session_id) if m.kind == "question"][0]
    assert question.answered_by is None
    assert "user" not in [m.who for m in tenv.chats.messages(tenv.graph.get("web").chat_session_id)], "and no line of the owner's was made"


def test_the_numbers_go_on_after_an_answer_and_an_answer_after_a_setting(tenv):
    task = tenv.started()
    ask(tenv, task)
    tenv.service.send_setting("web", {"decide_for_me": True})
    tenv.service.deliver_to_department("web", "Sweet Bean")
    tenv.service.send_setting("web", {"decide_for_me": False})
    assert [(r["n"], r["kind"]) for r in lines(tenv, task)] == [(1, "setting"), (2, "user"), (3, "setting")]
    assert inbox_line_count(tenv.run_dir(task)) == 3


def test_no_live_task_means_nothing_is_written_and_false(tenv):
    assert tenv.service.send_setting("web", {"decide_for_me": True}) is False                   # no task at all
    queued = tenv.new()
    assert tenv.status(queued.id) == "queued" and tenv.service.send_setting("web", {"decide_for_me": True}) is False
    assert tenv.service.send_setting("nowhere", {"decide_for_me": True}) is False
    done = tenv.started("sales")
    tenv.write_events(done, ev("run.ended", status="done", outcome="Done."))
    tenv.drain(done)
    assert tenv.status(done) in ("done", "done_with_open_items") and tenv.service.send_setting("sales", {"decide_for_me": True}) is False
    assert not (tenv.run_dir(done) / "inbox.jsonl").read_text(), "an ended run's inbox is left as it was"


def test_only_the_named_teams_live_run_gets_the_line(tenv):
    web, sales = tenv.started("web"), tenv.started("sales")
    assert tenv.service.send_setting("sales", {"decide_for_me": True}) is True
    assert lines(tenv, web) == [] and [r["kind"] for r in lines(tenv, sales)] == ["setting"]


# ---- the eighth task key -------------------------------------------------------------------------------------------------------
def test_the_task_key_is_a_zero_or_a_one_and_nothing_else():
    assert TASK_SETTING_KEYS[7] == "J2_DECIDE_FOR_ME" and tuple(TaskSettings.model_fields) == TASK_SETTING_KEYS
    assert TaskSettings(J2_DECIDE_FOR_ME="1").model_dump() == {"J2_DECIDE_FOR_ME": "1"}
    assert TaskSettings(J2_DECIDE_FOR_ME="0").model_dump() == {"J2_DECIDE_FOR_ME": "0"} and TaskSettings().model_dump() == {}
    for bad in ("yes", "true", "2", "", 1, True):
        with pytest.raises(ValidationError):
            TaskSettings(J2_DECIDE_FOR_ME=bad)


def test_a_first_message_with_the_key_starts_a_run_that_has_it_in_its_task_and_its_environment(tenv):
    result = tenv.service.deliver_to_department("web", "Build a landing page", settings={"J2_DECIDE_FOR_ME": "1", "J2_OUTPUT": "prd"})
    assert result.delivered == "follow_up"
    task = result.task_id

    async def go():
        await tenv.service.start_ready()
    tenv.run(go())
    spec = json.loads((tenv.run_dir(task) / "task.json").read_text())
    assert spec["settings"] == {"J2_OUTPUT": "prd", "J2_DECIDE_FOR_ME": "1"}
    from sutra_app.orchestrator.models import RunSpec
    env = ProcessLauncher(environ={}).environment(RunSpec.model_validate(spec))
    assert env["J2_DECIDE_FOR_ME"] == "1" and env["J2_OUTPUT"] == "prd", "the engine process is started with the switch on"


def test_a_key_the_task_does_not_know_is_still_refused(tenv):
    with pytest.raises(Exception):
        tenv.service.deliver_to_department("web", "Build", settings={"J2_SEND_MODE": "live"})


# ---- J2 sync 6 (D182): the two task-only run template keys ---------------------------------------------------------------------------

def test_the_run_template_keys_take_an_id_and_a_workflow_list_and_nothing_else():
    ok = TaskSettings(J2_RUN_TEMPLATE="thread-boutique-website", J2_RUN_TEMPLATE_WORKFLOWS="all")
    assert ok.model_dump() == {"J2_RUN_TEMPLATE": "thread-boutique-website", "J2_RUN_TEMPLATE_WORKFLOWS": "all"}
    assert TaskSettings(J2_RUN_TEMPLATE_WORKFLOWS="w1,w2").model_dump() == {"J2_RUN_TEMPLATE_WORKFLOWS": "w1,w2"}
    for bad in ("Upper", "has space", "../x", "a_b", "", "x" * 81, 5, True):
        with pytest.raises(ValidationError):
            TaskSettings(J2_RUN_TEMPLATE=bad)
    for bad in ("a b", "w1;w2", "x" * 21, ",".join(f"k{i}" for i in range(41)), "x," * 300, 7, True):
        with pytest.raises(ValidationError):
            TaskSettings(J2_RUN_TEMPLATE_WORKFLOWS=bad)


def test_the_run_template_keys_cannot_widen_into_the_settings_that_switch_the_reuse_flags():
    for key in ("J2_RUN_TEMPLATES", "J2_AUTO_REUSE", "J2_ARTIFACT_LIBRARY", "J2_REVIEWER", "J2_REVIEWER_WAIT", "J2_PUSH_RUNS", "J2_RUN_BY"):
        with pytest.raises(ValidationError):
            TaskSettings.model_validate({key: "1"})


def test_a_first_message_with_a_run_template_has_both_keys_in_its_task_and_a_bad_one_is_refused_with_422(tenv):
    from sutra_app.orchestrator.errors import AppError
    result = tenv.service.deliver_to_department("web", "a website for a boutique", settings={
        "J2_RUN_TEMPLATE": "thread-boutique-website", "J2_RUN_TEMPLATE_WORKFLOWS": "w1,w2"})
    assert result.delivered == "follow_up"
    row = tenv.row(result.task_id)
    assert row.settings == {"J2_RUN_TEMPLATE": "thread-boutique-website", "J2_RUN_TEMPLATE_WORKFLOWS": "w1,w2"}
    for bad in ({"J2_RUN_TEMPLATE": "Not An Id"}, {"J2_RUN_TEMPLATE": "x", "J2_RUN_TEMPLATE_WORKFLOWS": "a b"}):
        with pytest.raises(AppError) as refused:
            tenv.service.deliver_to_department("sales", "a website for a boutique", settings=bad)
        assert refused.value.code == "validation"
