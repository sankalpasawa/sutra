"""Settings across sections (S1-contracts-03): the seven task keys the orchestrator validates, the two `engine.json` layers the engine
host reads, the Settings routes that edit them, and the dangerous switches that stay out of every web path."""
import json
import os
import re
import stat

import pytest

from sutra_app.engine.paths import DataPaths
from sutra_app.engine.spec import (
    EDITABLE_FIELDS, ENV_NAMES, LOCKED_FIELDS, TASK_SETTING_KEYS, EngineSettings, SettingsError, read_settings_file,
)
from sutra_app.orchestrator.departments import ENGINE_OWNED
from sutra_app.orchestrator.errors import AppError
from sutra_app.orchestrator.models import TaskSettings

from .test_contract_world import World, clock, db, events, ids, settings, tenv, world  # noqa: F401  (fixtures used by name)

PATH = "/api/engine/settings"
GOOD = {"J2_OUTPUT": "lld", "J2_BUDGET": "55", "J2_BUDGET_CAP": "99", "J2_FIXES": "1", "J2_MEMORY": "0", "J2_SLIM": "0", "J2_RATES": "0"}
FIELD_OF = {env: name for name, env in ENV_NAMES.items()}


# ---- the task keys: orchestrator (writer) against engine (reader) -----------------------------------------------------------------

def test_the_seven_keys_are_the_same_list_on_both_sides():
    assert tuple(TaskSettings.model_fields) == TASK_SETTING_KEYS
    assert len(TASK_SETTING_KEYS) == 7
    assert [FIELD_OF[key] for key in TASK_SETTING_KEYS] == ["output", "budget", "budget_cap", "fixes", "memory", "slim", "rates"]


def test_what_the_orchestrator_accepts_the_engine_reads_as_the_same_values():
    task = TaskSettings.model_validate(GOOD).model_dump()
    assert task == GOOD
    effective = EngineSettings.layered({}, None, None, task)
    assert (effective.output, effective.budget, effective.budget_cap, effective.fixes) == ("lld", 55, 99, 1)
    assert (effective.memory, effective.slim, effective.rates) == (False, False, False)


@pytest.mark.parametrize("key, value, ok", [
    ("J2_BUDGET", "1", True), ("J2_BUDGET", "100000", True), ("J2_BUDGET", "0", False), ("J2_BUDGET", "100001", False),
    ("J2_BUDGET", "12.5", False), ("J2_BUDGET", "-3", False), ("J2_BUDGET_CAP", "1", True), ("J2_BUDGET_CAP", "100000", True),
    ("J2_BUDGET_CAP", "0", False), ("J2_BUDGET_CAP", "100001", False), ("J2_OUTPUT", "prd", True), ("J2_OUTPUT", "deck", False),
    ("J2_FIXES", "1", True), ("J2_FIXES", "2", False), ("J2_RATES", "0", True), ("J2_RATES", "2", False)])
def test_both_sides_draw_the_line_at_the_same_value(key, value, ok):
    def writer() -> bool:
        try:
            TaskSettings.model_validate({key: value})
            return True
        except ValueError:
            return False

    def reader() -> bool:
        try:
            EngineSettings.layered({}, None, None, {key: value})
            return True
        except SettingsError:
            return False
    assert writer() is ok
    assert reader() is ok


def test_the_task_service_refuses_every_locked_switch_and_every_unknown_key_with_422(tenv):
    for name in LOCKED_FIELDS:
        with pytest.raises(AppError) as refused:
            tenv.new(settings={ENV_NAMES[name]: "1"})
        assert refused.value.code == "validation", name
    for key in ("J2_BOARD", "J2_CHANGE", "J2_RUNS_DIR", "SUTRA_TOKEN", "PATH"):
        with pytest.raises(AppError):
            tenv.new(settings={key: "1"})
    assert tenv.new(settings=GOOD).id


def test_a_locked_switch_cannot_come_in_by_the_say_route_either(world):
    """`POST /api/say` carries no settings from the page; `POST /api/output` carries the output word only."""
    r = world.client.post("/api/say", params={"dept": "web"}, json={"text": "hi", "settings": {"J2_SEND_MODE": "live"}}, headers=world.auth)
    assert r.status_code == 200
    task = world.t.service.store.latest_in(world.t.db.conn(), "web")
    assert task.settings == {}
    assert world.client.post("/api/output", params={"dept": "web"}, json={"type": "prd"}, headers=world.auth).status_code in (200, 409)


# ---- the files: Settings routes (engine) against the host's layering ---------------------------------------------------------------

def test_the_route_lists_the_fields_the_engine_module_says_are_editable_and_locked(world):
    body = world.client.get(PATH).json()
    assert body["schema"] == "engine-settings/1"
    assert body["editable"] == list(EDITABLE_FIELDS) and body["locked"] == list(LOCKED_FIELDS)
    assert set(body["editable"]) | set(body["locked"]) == set(EngineSettings.model_fields)
    assert body["defaults"] == EngineSettings().model_dump() and body["effective"] == body["defaults"]


def test_a_locked_or_unknown_field_is_refused_and_nothing_is_written(world):
    for field in (LOCKED_FIELDS[0], "send_mode", "no_such_field"):
        r = world.client.put(PATH, json={"set": {field: "live"}}, headers=world.auth)
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation", field
    assert not (world.t.settings.data_dir / "engine.json").exists()


def test_what_the_route_writes_is_what_the_host_reads_and_the_layers_stack_in_order(world):
    data = world.t.settings.data_dir
    assert world.client.put(PATH, json={"set": {"budget": 40, "board": True, "slim": False}}, headers=world.auth).status_code == 200
    assert world.client.put(PATH, params={"dept": "web"}, json={"set": {"budget": 60, "fixes": 1}}, headers=world.auth).status_code == 200
    paths = DataPaths.for_dept(data, "web")
    assert paths.engine_json == data / "engine.json" and paths.dept_engine_json == data / "departments" / "web" / "engine.json"
    for path in (paths.engine_json, paths.dept_engine_json):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert json.loads(paths.engine_json.read_text()) == {"board": True, "budget": 40, "slim": False}
    host = EngineSettings.layered({}, read_settings_file(paths.engine_json), read_settings_file(paths.dept_engine_json), {})
    assert (host.budget, host.board, host.slim, host.fixes) == (60, True, False, 1)            # the department beats the global file
    shown = world.client.get(PATH, params={"dept": "web"}).json()
    assert shown["effective"] == host.model_dump()                                             # the Settings page shows what the host will use
    task = EngineSettings.layered({}, read_settings_file(paths.engine_json), read_settings_file(paths.dept_engine_json), {"J2_BUDGET": "5"})
    assert task.budget == 5                                                                    # the task beats both files
    other = world.client.get(PATH, params={"dept": "sales"}).json()
    assert other["effective"]["budget"] == 40 and other["department"] == {}


def test_a_run_started_after_the_change_reads_it_and_one_started_before_does_not(world):
    """`task.json` carries only the seven keys; the files are read by the host at its start, so the change reaches the NEXT run only."""
    first = world.t.new("web", "first")
    world.t.run(world.t.service.start_ready())
    assert json.loads((world.t.run_dir(first.id) / "task.json").read_text())["settings"] == {}
    assert world.client.put(PATH, params={"dept": "web"}, json={"set": {"max_cycles": 3}}, headers=world.auth).status_code == 200
    assert "max_cycles" not in json.loads((world.t.run_dir(first.id) / "task.json").read_text())
    assert not (world.t.run_dir(first.id) / "settings.json").exists()                          # nothing but the engine writes it
    paths = DataPaths.for_dept(world.t.settings.data_dir, "web", world.t.row(first.id).run_id)
    assert EngineSettings.layered({}, None, read_settings_file(paths.dept_engine_json), {}).max_cycles == 3


def test_the_folders_the_engine_keeps_in_a_department_are_the_ones_the_sweep_leaves_alone(world):
    paths = DataPaths.for_dept(world.t.settings.data_dir, "web")
    assert {paths.dept_engine_json.name, paths.page_json.name, paths.memory_dir.name} == set(ENGINE_OWNED)


def test_no_secret_is_a_setting_and_no_locked_field_is_a_task_key():
    assert not [name for name in EngineSettings.model_fields if re.search(r"KEY|TOKEN|SECRET|PASSWORD", name, re.I)]
    assert not {ENV_NAMES[name] for name in LOCKED_FIELDS} & set(TASK_SETTING_KEYS)
