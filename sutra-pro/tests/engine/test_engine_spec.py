"""spec.py (TaskSpec, EngineSettings and how its layers merge) and features.py (engine.md 4.4, section 8, 5;
S1-contracts-01, -03).

The settings tests are written against J2's own variables and defaults (j2.py:63-95, 176, 450-457, 2333, 2460-2848, 3895, 5613;
j2_board.py:30, j2_check.py:24, 137, j2_send.py:76-82, 146, j2_template_lib.py:61), listed one by one below.
"""
import ast
import dataclasses
import hashlib
import json
import os
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from sutra_app.engine import features
from sutra_app.engine.features import FEATURES, STEP_IDS, by_id
from sutra_app.engine.spec import (
    CONNECTORS, DEPT_ID_RE, EDITABLE_FIELDS, ENV_NAMES, LOCKED_FIELDS, RUN_ID_RE, SETTING_KEY_RE, SETTINGS_SCHEMA,
    TASK_SCHEMA, TASK_SETTING_KEYS, EngineSettings, SettingsError, TaskSpec, is_dept_id, is_run_id, read_settings_file,
)

EXAMPLE = json.loads(
    '{"schema":"run-spec/1","run_id":"j2-20261104-100004-7f3a","task_id":"tsk_a1b2c3d4e5f6","dept_id":"web","dept_label":"Web",'
    '"user_text":"A website for my cafe","framing":"","seed_from":null,"upstream":[],"settings":{"J2_BUDGET":"100"},"connector":"auto"}')

# the fields of the orchestrator's RunSpec (orchestrator.md 3.3): every one must exist in TaskSpec
RUN_SPEC_FIELDS = ["run_id", "task_id", "dept_id", "dept_label", "scope_id", "scope_label", "user_text", "framing", "parent_run_id",
                   "seed_from", "upstream", "settings", "connector"]


def task(**changes):
    return TaskSpec.model_validate({**EXAMPLE, **changes})


# ---- ids ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("dept", ["web", "ab", "a" + "b" * 39, "a-b", "a1", "sales-eu", "x9-"])
def test_department_ids_the_rule_accepts(dept):
    assert is_dept_id(dept) and re.fullmatch(DEPT_ID_RE, dept)


@pytest.mark.parametrize("dept", ["", "a", "A", "Web", "1a", "-a", "a_b", "a" * 41, "web\n", " web", "we b", "é", "a.b", "a/b", None, 5])
def test_department_ids_the_rule_refuses(dept):
    assert not is_dept_id(dept)


def test_the_department_rule_is_the_one_in_the_design():
    assert DEPT_ID_RE == r"^[a-z][a-z0-9-]{1,39}$"
    assert re.match(DEPT_ID_RE, "web\n")                      # why every user of the pattern must use fullmatch
    assert not re.fullmatch(DEPT_ID_RE, "web\n")


@pytest.mark.parametrize("run", ["j2-20261104-100004-7f3a", "j2-x", "j2-a_b-C", "j2-" + "a" * 120])
def test_run_ids_the_rule_accepts(run):
    assert is_run_id(run) and re.fullmatch(RUN_ID_RE, run)


@pytest.mark.parametrize("run", ["", "j2-", "J2-1", "x-j2-1", "j2-../x", "j2-a/b", "j2-a b", "j2-é", "j2-1\n", "j2-" + "a" * 121,
                                 "j2", "j2_1", None, 12])
def test_run_ids_the_rule_refuses(run):
    assert not is_run_id(run)


# ---- TaskSpec ---------------------------------------------------------------------------------------------------------

def test_task_spec_accepts_the_orchestrators_task_json():
    t = TaskSpec.model_validate(EXAMPLE)
    assert (t.run_id, t.task_id, t.dept_id, t.dept_label) == ("j2-20261104-100004-7f3a", "tsk_a1b2c3d4e5f6", "web", "Web")
    assert (t.user_text, t.framing, t.seed_from, t.parent_run_id, t.upstream) == ("A website for my cafe", "", None, None, [])
    assert (t.settings, t.connector, t.scope_id, t.scope_label, t.schema_) == ({"J2_BUDGET": "100"}, "auto", None, None, "run-spec/1")


def test_task_spec_ignores_unknown_keys_at_the_top():
    t = TaskSpec.model_validate({**EXAMPLE, "future_field": {"a": 1}, "priority": 3})
    assert not hasattr(t, "future_field") and "future_field" not in t.model_dump()


def test_every_run_spec_field_exists_in_task_spec():
    assert set(RUN_SPEC_FIELDS) <= set(TaskSpec.model_fields)
    assert set(TaskSpec.model_fields) - set(RUN_SPEC_FIELDS) == {"schema_"}


def test_a_task_json_written_the_orchestrators_way_validates(run_dir):
    t = TaskSpec.model_validate_json((run_dir / "task.json").read_text())
    assert (t.run_id, t.dept_id) == (run_dir.name, run_dir.parent.parent.name)


def test_task_spec_defaults():
    t = TaskSpec(run_id="j2-1", task_id="t", dept_id="web", user_text="x")
    assert (t.dept_label, t.scope_id, t.scope_label, t.framing, t.parent_run_id, t.seed_from, t.upstream, t.settings, t.connector,
            t.schema_) == ("", None, None, "", None, None, [], {}, "auto", None)
    assert t.dropped_settings == ()


def test_the_schema_word_is_run_spec_1_or_absent():
    assert TASK_SCHEMA == "run-spec/1"
    assert task(schema="run-spec/1").schema_ == "run-spec/1"
    assert TaskSpec(**{k: v for k, v in EXAMPLE.items() if k != "schema"}).schema_ is None
    assert TaskSpec(schema_="run-spec/1", **{k: v for k, v in EXAMPLE.items() if k != "schema"}).schema_ == "run-spec/1"
    for bad in ("run-spec/2", "", "events/1"):
        with pytest.raises(ValidationError, match="run-spec/1"):
            task(schema=bad)


@pytest.mark.parametrize("field", ["run_id", "task_id", "dept_id", "user_text"])
def test_task_spec_needs_these_fields(field):
    with pytest.raises(ValidationError):
        TaskSpec.model_validate({k: v for k, v in EXAMPLE.items() if k != field})


def test_task_spec_run_id_must_be_a_run_id():
    for bad in ("", "j2-", "../../etc", "j2-../x", "run-1", "j2-" + "a" * 121):
        with pytest.raises(ValidationError, match="run_id"):
            task(run_id=bad)
    assert task(run_id="j2-x_y-1").run_id == "j2-x_y-1"


def test_task_spec_dept_id_must_match_the_rule_without_underscore():
    for bad in ("", "Web", "a", "a_b", "web\n", "a" * 41):
        with pytest.raises(ValidationError, match="dept_id"):
            task(dept_id=bad)
    assert task(dept_id="sales-eu").dept_id == "sales-eu"


def test_task_spec_user_text_is_not_empty_and_kept_as_it_is():
    for bad in ("", "   ", "\n\t"):
        with pytest.raises(ValidationError, match="user_text"):
            task(user_text=bad)
    verbatim = "  Make a site.\n\nIt should feel warm.  \n"
    assert task(user_text=verbatim).user_text == verbatim


def test_task_spec_task_id_is_not_empty():
    with pytest.raises(ValidationError):
        task(task_id="")


@pytest.mark.parametrize("field", ["seed_from", "parent_run_id"])
def test_task_spec_other_run_ids_follow_the_same_rule(field):
    assert task(**{field: "j2-20261103-090000-aaaa"}).model_dump()[field] == "j2-20261103-090000-aaaa"
    assert task(**{field: None}).model_dump()[field] is None
    for bad in ("", "run", "j2-../up", "j2-"):
        with pytest.raises(ValidationError):
            task(**{field: bad})


def test_task_spec_connector_is_one_of_four():
    assert CONNECTORS == ("auto", "claude", "codex", "stub")
    for word in CONNECTORS:
        assert task(connector=word).connector == word
    for bad in ("gemini", "", "Auto", None):
        with pytest.raises(ValidationError):
            task(connector=bad)


def test_task_spec_settings_keep_job_keys_and_report_the_others():
    t = task(settings={"J2_BUDGET": "100", "J2_OUTPUT": "prd", "j2_budget": "5", "PATH": "/x", "J2_": "x", "J2_BUDGET2": "1",
                       "J2_X-Y": "1", "J2_okay": "1", "X_J2_BUDGET": "1"})
    assert t.settings == {"J2_BUDGET": "100", "J2_OUTPUT": "prd"}
    assert t.dropped_settings == ("j2_budget", "PATH", "J2_", "J2_BUDGET2", "J2_X-Y", "J2_okay", "X_J2_BUDGET")
    assert re.fullmatch(SETTING_KEY_RE, "J2_ANYTHING_AT_ALL") and not re.fullmatch(SETTING_KEY_RE, "J2_")


def test_task_spec_settings_need_text_values():
    for bad in ({"J2_BUDGET": 100}, {"J2_FIXES": True}, {"J2_RATES": None}):
        with pytest.raises(ValidationError):
            task(settings=bad)


def test_the_seven_task_keys_are_the_ones_the_orchestrator_allows():
    assert TASK_SETTING_KEYS == ("J2_OUTPUT", "J2_BUDGET", "J2_BUDGET_CAP", "J2_FIXES", "J2_MEMORY", "J2_SLIM", "J2_RATES")
    assert all(re.fullmatch(SETTING_KEY_RE, key) for key in TASK_SETTING_KEYS)
    assert all(ENV_NAMES[name] in TASK_SETTING_KEYS for name in ("output", "budget", "budget_cap", "fixes", "memory", "slim", "rates"))
    assert not set(TASK_SETTING_KEYS) & {ENV_NAMES[name] for name in LOCKED_FIELDS}


def test_task_spec_upstream_entries():
    ok = [{"dept_id": "web", "run_id": "j2-20261103-090000-aaaa", "title": "Menu", "files": ["site/v2.html", "prd.md"]},
          {"title": "partial entries are fine", "also": "unknown keys too"}]
    assert task(upstream=ok).upstream == ok
    for bad in ([{"dept_id": "Web"}], [{"run_id": "run-1"}], [{"title": 5}], [{"files": "prd.md"}], [{"files": [1]}], ["just a string"],
                [{"files": None}]):
        with pytest.raises(ValidationError):
            task(upstream=bad)


def test_task_spec_does_not_judge_a_path_that_is_the_hosts_job():
    """`upstream[].files` are checked for `..`, absolute paths and links by the host, which can see the disk."""
    assert task(upstream=[{"files": ["../../other/secret", "/etc/passwd"]}]).upstream[0]["files"][1] == "/etc/passwd"


# ---- EngineSettings: J2's defaults ------------------------------------------------------------------------------------

J2_DEFAULTS = {
    "output": "website",              # j2.py:2333 J2_OUTPUT
    "fixes": 0,                       # :2837 == "1"
    "budget": 100,                    # :66
    "budget_cap": None,               # :67 default 2 x budget
    "max_cycles": 6,                  # :71
    "limit_add": 30,                  # :72
    "bargain_minutes": 15.0,          # :69
    "bargain_calls": 8,               # :70
    "max_turns": 30,                  # :89
    "chat_full_chars": 60000,         # :90
    "delay": 0.0,                     # :95 J2 says 2 outside mock; the router paces now
    "rates": True,                    # :176 != "0"
    "slim": True,                     # :457 != "0"
    "memory": True,                   # :2526 != "0"
    "realization": True,              # :2532 != "0"
    "change": False,                  # :5613 == "1"
    "board": False,                   # j2_board.py:30 == "1"
    "artifact_schema": False,         # :450 == "1"
    "template_library": False,        # j2_template_lib.py:61 == "1"
    "send_mode": "dry-run",           # j2_send.py:76
    "send_cap": 10,                   # j2_send.py:82
    "milestone_emails": False,        # :3895
    "test_email": "",                 # j2_send.py:146
    "test_slack_target": "",
    "tap_min": 44,                    # j2_check.py:24
    "chrome": "",                     # j2_check.py:137
    "force_audit_fail": 0,            # :2839
    "force_audit_note": "",           # :2460
    "force_question": "",             # :2844
    "memory_test_lessons": False,     # :2848 == "1"
    "workspace": "auto",              # D127: Sutra's own, not J2's: the workspace capability
}


def test_engine_settings_default_to_j2s_values():
    assert EngineSettings().model_dump() == J2_DEFAULTS
    assert list(EngineSettings.model_fields) == list(J2_DEFAULTS)
    assert len(J2_DEFAULTS) == 31


def test_the_flags_that_are_on_in_j2_are_on_and_the_others_off():
    s = EngineSettings()
    assert (s.rates, s.slim, s.memory, s.realization) == (True, True, True, True)
    assert (s.change, s.board, s.artifact_schema, s.template_library, s.milestone_emails, s.memory_test_lessons) == (False,) * 6
    assert s.send_mode == "dry-run"                                   # nothing leaves the machine by default


def test_engine_settings_are_closed():
    with pytest.raises(ValidationError):
        EngineSettings(openai_key="x")
    with pytest.raises(ValidationError):
        EngineSettings(budgt=5)


def test_no_setting_is_a_secret():
    """The SMTP login stays in .env, the owner override key on the server: neither is a field (D71, S1-contracts-19)."""
    for name in EngineSettings.model_fields:
        assert not re.search(r"key|token|secret|password|auth|smtp", name, re.I), name


@pytest.mark.parametrize("field, good, bad", [
    ("output", ["website", "prd", "hld", "lld"], ["Website", "docs", "", None, 3]),
    ("fixes", [0, 1], [2, -1, "yes"]),
    ("budget", [1, 100, 100000], [0, -5, 100001, "many", 1.5]),
    ("budget_cap", [None, 1, 100000], [0, 100001, "x"]),
    ("max_cycles", [1, 6, 50], [0, -1]),
    ("limit_add", [0, 30], [-1]),
    ("bargain_minutes", [0, 15, 0.5], [-1, float("nan"), float("inf")]),
    ("bargain_calls", [0, 8], [-1]),
    ("max_turns", [1, 30], [0]),
    ("chat_full_chars", [1, 60000], [0, -1]),
    ("delay", [0, 2.5], [-0.5, float("inf")]),
    ("send_mode", ["dry-run", "mock", "live"], ["Live", "send", "dry_run", ""]),
    ("send_cap", [0, 10], [-1]),
    ("tap_min", [0, 44], [-1]),
    ("force_audit_fail", [0, 99], [-1]),
    ("rates", [True, False], ["maybe", 5]),
])
def test_settings_values_are_checked(field, good, bad):
    for value in good:
        assert getattr(EngineSettings(**{field: value}), field) == value
    for value in bad:
        with pytest.raises(ValidationError):
            EngineSettings(**{field: value})


@pytest.mark.parametrize("field, limit", [("test_email", 320), ("test_slack_target", 200), ("chrome", 1024), ("force_audit_note", 1000),
                                          ("force_question", 1000)])
def test_text_settings_are_bounded(field, limit):
    assert len(getattr(EngineSettings(**{field: "x" * limit}), field)) == limit
    with pytest.raises(ValidationError):
        EngineSettings(**{field: "x" * (limit + 1)})


# ---- locked and editable fields ----------------------------------------------------------------------------------------

def test_the_ten_locked_fields():
    assert LOCKED_FIELDS == ("send_mode", "send_cap", "milestone_emails", "test_email", "test_slack_target", "chrome", "force_audit_fail",
                             "force_audit_note", "force_question", "memory_test_lessons")
    assert set(LOCKED_FIELDS) <= set(EngineSettings.model_fields) and len(set(LOCKED_FIELDS)) == 10


def test_editable_is_everything_else_in_field_order():
    assert EDITABLE_FIELDS == tuple(f for f in EngineSettings.model_fields if f not in LOCKED_FIELDS)
    assert len(EDITABLE_FIELDS) == 21 and not set(EDITABLE_FIELDS) & set(LOCKED_FIELDS)
    assert SETTINGS_SCHEMA == "engine-settings/1"


# ---- to_env ------------------------------------------------------------------------------------------------------------

J2_VARIABLES = {     # engine.md 4.4: the J2 variables that become fields
    "output": "J2_OUTPUT", "fixes": "J2_FIXES", "budget": "J2_BUDGET", "budget_cap": "J2_BUDGET_CAP", "max_cycles": "J2_MAX_CYCLES",
    "limit_add": "J2_LIMIT_ADD", "bargain_minutes": "J2_BARGAIN_MINUTES", "bargain_calls": "J2_BARGAIN_CALLS",
    "max_turns": "J2_MAX_TURNS", "chat_full_chars": "J2_CHAT_FULL_CHARS", "delay": "J2_DELAY", "rates": "J2_RATES",
    "slim": "J2_SLIM", "memory": "J2_MEMORY", "realization": "J2_REALIZATION", "change": "J2_CHANGE", "board": "J2_BOARD",
    "artifact_schema": "J2_ARTIFACT_SCHEMA", "template_library": "J2_TEMPLATE_LIBRARY", "send_mode": "J2_SEND_MODE",
    "send_cap": "J2_SEND_CAP", "milestone_emails": "J2_MILESTONE_EMAILS", "test_email": "J2_TEST_EMAIL",
    "test_slack_target": "J2_TEST_SLACK_TARGET", "tap_min": "J2_TAP_MIN", "chrome": "J2_CHROME",
    "force_audit_fail": "J2_FORCE_AUDIT_FAIL", "force_audit_note": "J2_FORCE_AUDIT_NOTE", "force_question": "J2_FORCE_QUESTION",
    "memory_test_lessons": "J2_MEMORY_TEST_LESSONS", "workspace": "J2_WORKSPACE"}


def test_every_field_has_its_j2_variable():
    assert ENV_NAMES == J2_VARIABLES


NON_DEFAULT = dict(output="prd", fixes=1, budget=250, budget_cap=400, max_cycles=3, limit_add=5, bargain_minutes=2.5, bargain_calls=2,
                   max_turns=9, chat_full_chars=1000, delay=0.5, rates=False, slim=False, memory=False, realization=False, change=True,
                   board=True, artifact_schema=True, template_library=True, send_mode="mock", send_cap=0, milestone_emails=True,
                   test_email="me@example.com", test_slack_target="#tests", tap_min=48, chrome="/opt/chrome", force_audit_fail=2,
                   force_audit_note="forced", force_question="why?", memory_test_lessons=True, workspace="off")


def test_to_env_of_the_defaults_leaves_out_the_empty_values():
    env = EngineSettings().to_env()
    assert set(J2_VARIABLES.values()) - set(env) == {"J2_BUDGET_CAP", "J2_TEST_EMAIL", "J2_TEST_SLACK_TARGET", "J2_CHROME",
                                                     "J2_FORCE_AUDIT_NOTE", "J2_FORCE_QUESTION"}
    assert env == {"J2_OUTPUT": "website", "J2_FIXES": "0", "J2_BUDGET": "100", "J2_MAX_CYCLES": "6", "J2_LIMIT_ADD": "30",
                   "J2_BARGAIN_MINUTES": "15.0", "J2_BARGAIN_CALLS": "8", "J2_MAX_TURNS": "30", "J2_CHAT_FULL_CHARS": "60000",
                   "J2_DELAY": "0.0", "J2_RATES": "1", "J2_SLIM": "1", "J2_MEMORY": "1", "J2_REALIZATION": "1", "J2_CHANGE": "0",
                   "J2_BOARD": "0", "J2_ARTIFACT_SCHEMA": "0", "J2_TEMPLATE_LIBRARY": "0", "J2_SEND_MODE": "dry-run",
                   "J2_SEND_CAP": "10", "J2_MILESTONE_EMAILS": "0", "J2_TAP_MIN": "44", "J2_FORCE_AUDIT_FAIL": "0",
                   "J2_MEMORY_TEST_LESSONS": "0", "J2_WORKSPACE": "auto"}


def test_to_env_for_every_field():
    assert set(NON_DEFAULT) == set(EngineSettings.model_fields)
    env = EngineSettings(**NON_DEFAULT).to_env()
    assert env == {"J2_OUTPUT": "prd", "J2_FIXES": "1", "J2_BUDGET": "250", "J2_BUDGET_CAP": "400", "J2_MAX_CYCLES": "3",
                   "J2_LIMIT_ADD": "5", "J2_BARGAIN_MINUTES": "2.5", "J2_BARGAIN_CALLS": "2", "J2_MAX_TURNS": "9",
                   "J2_CHAT_FULL_CHARS": "1000", "J2_DELAY": "0.5", "J2_RATES": "0", "J2_SLIM": "0", "J2_MEMORY": "0",
                   "J2_REALIZATION": "0", "J2_CHANGE": "1", "J2_BOARD": "1", "J2_ARTIFACT_SCHEMA": "1", "J2_TEMPLATE_LIBRARY": "1",
                   "J2_SEND_MODE": "mock", "J2_SEND_CAP": "0", "J2_MILESTONE_EMAILS": "1", "J2_TEST_EMAIL": "me@example.com",
                   "J2_TEST_SLACK_TARGET": "#tests", "J2_TAP_MIN": "48", "J2_CHROME": "/opt/chrome", "J2_FORCE_AUDIT_FAIL": "2",
                   "J2_FORCE_AUDIT_NOTE": "forced", "J2_FORCE_QUESTION": "why?", "J2_MEMORY_TEST_LESSONS": "1",
                   "J2_WORKSPACE": "off"}


@pytest.mark.parametrize("field", list(EngineSettings.model_fields))
def test_each_field_reaches_the_environment_on_its_own(field):
    base = EngineSettings().to_env()
    changed = EngineSettings(**{field: NON_DEFAULT[field]}).to_env()
    delta = {k: v for k, v in changed.items() if base.get(k) != v}
    assert set(delta) == {ENV_NAMES[field]}


def test_flags_are_one_and_zero_and_zero_is_not_empty():
    env = EngineSettings(rates=False, change=True, send_cap=0, force_audit_fail=0).to_env()
    assert (env["J2_RATES"], env["J2_CHANGE"], env["J2_SEND_CAP"], env["J2_FORCE_AUDIT_FAIL"]) == ("0", "1", "0", "0")


def test_an_empty_text_and_no_budget_cap_leave_their_variables_out():
    env = EngineSettings(chrome="", test_email="", budget_cap=None).to_env()
    assert not {"J2_CHROME", "J2_TEST_EMAIL", "J2_BUDGET_CAP"} & set(env)
    assert EngineSettings(budget_cap=300).to_env()["J2_BUDGET_CAP"] == "300"


def test_to_env_survives_a_round_trip_through_layered():
    for settings in (EngineSettings(), EngineSettings(**NON_DEFAULT), EngineSettings(budget=7, board=True, output="lld")):
        assert EngineSettings.layered(settings.to_env(), None, None, {}) == settings


# ---- layered: order ----------------------------------------------------------------------------------------------------

def test_layers_apply_in_order_defaults_file_env_department_task():
    file_, env, dept, task_ = {"budget": 10}, {"J2_BUDGET": "20"}, {"budget": 30}, {"J2_BUDGET": "40"}
    assert EngineSettings.layered(env, file_, dept, task_).budget == 40
    assert EngineSettings.layered(env, file_, dept, {}).budget == 30
    assert EngineSettings.layered(env, file_, None, {}).budget == 20
    assert EngineSettings.layered({}, file_, None, {}).budget == 10
    assert EngineSettings.layered({}, None, None, {}).budget == 100


def test_a_layer_only_overrides_what_it_names():
    s = EngineSettings.layered({"J2_BOARD": "1"}, {"budget": 10, "max_cycles": 2}, {"max_cycles": 9}, {"J2_FIXES": "1"})
    assert (s.budget, s.max_cycles, s.board, s.fixes, s.rates) == (10, 9, True, 1, True)


def test_the_file_layers_use_field_names_and_the_others_j2_names():
    assert EngineSettings.layered({}, {"board": True}, None, {}).board is True
    assert EngineSettings.layered({"J2_BOARD": "1"}, None, None, {}).board is True
    assert EngineSettings.layered({}, None, None, {"J2_BOARD": "1"}).board is True
    assert EngineSettings.layered({"board": "1"}, None, None, {}).board is False       # a field name is not an environment name
    assert EngineSettings.layered({}, None, {"board": True}, {}).board is True
    with pytest.raises(SettingsError):
        EngineSettings.layered({}, {"J2_BOARD": True}, None, {})


def test_a_null_in_a_file_clears_a_cap_set_below_it():
    s = EngineSettings.layered({}, {"budget_cap": 300}, {"budget_cap": None}, {})
    assert s.budget_cap is None
    assert EngineSettings.layered({}, {"budget_cap": 300}, {}, {}).budget_cap == 300


def test_names_that_are_not_settings_are_ignored_in_the_environment_and_the_task():
    env = {"J2_RUNS_DIR": "/x", "J2_MEMORY_FILE": "/y", "J2_SMTP_PASSWORD": "pw", "J2_OVERRIDE_KEY": "k", "PATH": "/bin", "j2_budget": "5",
           "J2_BUDGET_CAPS": "9", "J2_AGENTS_DIR": "/z", "HOME": "/h"}
    assert EngineSettings.layered(env, None, None, {}) == EngineSettings()
    assert EngineSettings.layered({}, None, None, env) == EngineSettings()


def test_an_empty_value_is_not_set():
    s = EngineSettings.layered({"J2_BUDGET": "", "J2_CHROME": "   ", "J2_BOARD": " "}, {"budget": 10}, None, {"J2_MAX_CYCLES": ""})
    assert (s.budget, s.chrome, s.board, s.max_cycles) == (10, "", False, 6)


def test_layered_does_not_touch_its_arguments():
    file_, env, dept, task_ = {"budget": 10}, {"J2_BUDGET": "20"}, {"budget": 30}, {"J2_BUDGET": "40"}
    EngineSettings.layered(env, file_, dept, task_)
    assert (file_, env, dept, task_) == ({"budget": 10}, {"J2_BUDGET": "20"}, {"budget": 30}, {"J2_BUDGET": "40"})


def test_layered_reads_the_real_environment_mapping(clean_env):
    clean_env.setenv("J2_MAX_CYCLES", "4")
    clean_env.setenv("J2_REALIZATION", "0")
    s = EngineSettings.layered(os.environ, None, None, {})
    assert (s.max_cycles, s.realization) == (4, False)


# ---- layered: reading the environment ----------------------------------------------------------------------------------

@pytest.mark.parametrize("word, flag", [("1", True), ("0", False), ("true", True), ("FALSE", False), ("Yes", True), ("no", False),
                                        ("on", True), ("OFF", False), (" 1 ", True), (" off ", False), (1, True), (0, False),
                                        (True, True), (False, False)])
def test_flags_in_the_environment(word, flag):
    assert EngineSettings.layered({"J2_BOARD": word}, None, None, {}).board is flag
    assert EngineSettings.layered({"J2_RATES": word}, None, None, {}).rates is flag          # a flag that is on by default too


@pytest.mark.parametrize("word", ["maybe", "2", "y", "enabled", "-1"])
def test_a_flag_word_that_means_neither_is_an_error_where_j2_read_it_as_off_or_on(word):
    with pytest.raises(SettingsError, match=r"the process environment: J2_BOARD: must be 1 or 0"):
        EngineSettings.layered({"J2_BOARD": word}, None, None, {})


@pytest.mark.parametrize("text, number", [("3", 3), (" 7 ", 7), ("3.0", 3), ("0", 0), (5, 5)])
def test_whole_numbers_in_the_environment(text, number):
    assert EngineSettings.layered({"J2_FORCE_AUDIT_FAIL": text}, None, None, {}).force_audit_fail == number


@pytest.mark.parametrize("text", ["abc", "3.5", "nan", "inf", "1e400", "--3", "0x10"])
def test_a_bad_whole_number_in_the_environment_is_an_error(text):
    with pytest.raises(SettingsError, match="J2_MAX_CYCLES"):
        EngineSettings.layered({"J2_MAX_CYCLES": text}, None, None, {})


def test_numbers_that_are_out_of_range_are_errors_that_name_the_variable_of_the_layer():
    with pytest.raises(SettingsError, match=r"the process environment: J2_BUDGET: "):
        EngineSettings.layered({"J2_BUDGET": "0"}, None, None, {})
    with pytest.raises(SettingsError, match=r"the task's settings: J2_MAX_CYCLES: "):
        EngineSettings.layered({}, None, None, {"J2_MAX_CYCLES": "-2"})


def test_floats_in_the_environment():
    s = EngineSettings.layered({"J2_BARGAIN_MINUTES": "2.5", "J2_DELAY": "1"}, None, None, {})
    assert (s.bargain_minutes, s.delay) == (2.5, 1.0)
    for bad in ("soon", "nan", "inf"):
        with pytest.raises(SettingsError, match="J2_BARGAIN_MINUTES"):
            EngineSettings.layered({"J2_BARGAIN_MINUTES": bad}, None, None, {})


def test_words_in_the_environment_are_folded_like_j2_does():
    s = EngineSettings.layered({"J2_OUTPUT": " PRD ", "J2_SEND_MODE": "Live"}, None, None, {})
    assert (s.output, s.send_mode) == ("prd", "live")
    for var in ("J2_OUTPUT", "J2_SEND_MODE"):
        with pytest.raises(SettingsError, match=var):
            EngineSettings.layered({var: "wiki"}, None, None, {})


def test_fixes_takes_the_flag_words_and_nothing_else():
    assert [EngineSettings.layered({"J2_FIXES": w}, None, None, {}).fixes for w in ("1", "0", "true", "off")] == [1, 0, 1, 0]
    with pytest.raises(SettingsError):
        EngineSettings.layered({"J2_FIXES": "2"}, None, None, {})


def test_text_settings_keep_their_spaces():
    s = EngineSettings.layered({"J2_FORCE_QUESTION": "  why? ", "J2_CHROME": "/Applications/Google Chrome.app"}, None, None, {})
    assert (s.force_question, s.chrome) == ("  why? ", "/Applications/Google Chrome.app")


def test_every_problem_of_a_layer_is_reported_at_once():
    with pytest.raises(SettingsError) as caught:
        EngineSettings.layered({"J2_BOARD": "maybe", "J2_MAX_CYCLES": "abc", "J2_OUTPUT": "wiki"}, None, None, {})
    message = str(caught.value)
    assert all(name in message for name in ("J2_BOARD", "J2_MAX_CYCLES", "J2_OUTPUT"))


# ---- layered: the files ------------------------------------------------------------------------------------------------

def test_an_unknown_field_in_a_file_is_an_error_naming_the_file():
    with pytest.raises(SettingsError, match=r"data/engine\.json: bord"):
        EngineSettings.layered({}, {"bord": True}, None, {})
    with pytest.raises(SettingsError, match=r"the department's engine\.json: send_modes"):
        EngineSettings.layered({}, None, {"send_modes": "live"}, {})


def test_a_bad_value_in_a_file_is_an_error_naming_the_file_and_field():
    with pytest.raises(SettingsError, match=r"data/engine\.json: budget: "):
        EngineSettings.layered({}, {"budget": "lots"}, None, {})
    with pytest.raises(SettingsError, match=r"the department's engine\.json: output: "):
        EngineSettings.layered({}, None, {"output": "wiki"}, {})


def test_a_file_that_is_not_an_object_is_an_error():
    for bad in (["budget"], "budget", 5):
        with pytest.raises(SettingsError, match="must be an object"):
            EngineSettings.layered({}, bad, None, {})


def test_a_file_may_set_a_locked_field_by_hand():
    s = EngineSettings.layered({}, {"send_mode": "mock", "chrome": "/opt/chrome", "force_audit_fail": 2}, None, {})
    assert (s.send_mode, s.chrome, s.force_audit_fail) == ("mock", "/opt/chrome", 2)


def test_settings_error_is_a_value_error():
    assert issubclass(SettingsError, ValueError)


def test_read_settings_file(tmp_path):
    path = tmp_path / "engine.json"
    assert read_settings_file(path) is None
    path.write_text('{"budget": 10, "board": true}')
    assert read_settings_file(path) == {"budget": 10, "board": True}
    assert read_settings_file(str(path)) == {"budget": 10, "board": True}
    path.write_text("{}")
    assert read_settings_file(path) == {}
    for bad in ("", "{not json", "[1, 2]", '"text"', "null", "12"):
        path.write_text(bad)
        with pytest.raises(SettingsError, match="engine.json"):
            read_settings_file(path)


# ---- FEATURES ---------------------------------------------------------------------------------------------------------

CHIPS = ["Workflow builder agents", "Code validator", "Confidence judge", "Budget and rate card", "Memory", "Message board",
         "Document chain", "Site build and checks", "Sends and deeds", "Run views", "Template library", "Charter change",
         "Artifact schemas", "Story and agent views", "Plan and priorities"]


def test_the_table_has_eight_steps_fifteen_chips_and_one_row_of_extras():
    assert [f.id for f in FEATURES if f.kind == "step"] == list(STEP_IDS) == ["J2.a", "J2.b", "J2.c", "J2.d", "J2.e", "J2.f", "J2.g", "J2.h"]
    assert [f.chip for f in FEATURES if f.kind == "chip"] == CHIPS
    assert [f.kind for f in FEATURES if f.kind not in ("step", "chip")] == ["extra"]
    assert len(FEATURES) == 24
    assert FEATURES[-1].chip.startswith("Also: run report and reviewer, owner override, test switches, docx export, redaction, saved runs")


def test_feature_ids_are_unique_and_found_by_id():
    ids = [f.id for f in FEATURES]
    assert len(set(ids)) == len(ids)
    assert by_id()["J2.f"].chip == "J2.f Coordination schedules, builders run"
    assert set(by_id()) == set(ids)


def test_the_flags_of_a_feature_are_real_settings():
    for feature in FEATURES:
        assert set(feature.flags) <= set(EngineSettings.model_fields), feature.id
    assert by_id()["judge"].flags == ("realization", "change")
    assert by_id()["extras"].flags == ("force_audit_fail", "force_audit_note", "force_question")


def test_files_are_relative_and_symbols_live_in_the_features_files():
    for feature in FEATURES:
        assert feature.files and len(set(feature.files)) == len(feature.files), feature.id
        for file in feature.files:
            assert file and not file.startswith("/") and ".." not in Path(file).parts, (feature.id, file)
        for file, name in feature.symbols:
            assert file in feature.files and file.endswith(".py") and name.isidentifier(), (feature.id, file, name)
        assert len(set(feature.symbols)) == len(feature.symbols)


def test_files_of_later_packages_are_listed_apart():
    later = [(f.id, f.later) for f in FEATURES if f.later]
    assert later == [("extras", (("api/reply.py", "redact"),))]
    assert not set(dict(later)["extras"]) & {(file, name) for file, name in by_id()["extras"].symbols}
    assert all(file not in by_id()["extras"].files for file, _ in by_id()["extras"].later)


def test_the_loop_steps_name_the_methods_the_design_names():
    names = {f.id: {name for _, name in f.symbols} for f in FEATURES}
    assert names["J2.a"] == {"_identity_intake", "CHARTER_FMT"}
    assert names["J2.e"] == {"_agree", "_register", "atom_missing"}
    assert names["J2.h"] == {"_identity_audit", "workable", "_identity_limit"}
    assert "builder.md" in " ".join(by_id()["builders"].files) and "agents/j2/audit.md" in by_id()["J2.g"].files


def test_the_table_is_the_design_as_it_was_written():
    """Section 8 of engine.md, transcribed. Change a row on purpose and this digest changes with it (and so must the design);
    `test_every_symbol_and_file_of_the_table_exists_in_j2` below checks the names against J2 itself."""
    blob = json.dumps([dataclasses.asdict(f) for f in FEATURES], sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == "b7d8eab5100022ec08503149bc42fa2cfa977c7fbb35b17c50b42c48a0091e7d"


J2_CHECKOUT = os.environ.get("SUTRA_J2_CHECKOUT")


@pytest.mark.skipif(not J2_CHECKOUT, reason="set SUTRA_J2_CHECKOUT to a J2 checkout to check FEATURES against J2's own files")
def test_every_symbol_and_file_of_the_table_exists_in_j2():
    root = Path(J2_CHECKOUT)
    where = {"seed/library/": "library/"}          # the engine seeds data/library from J2's library/
    for feature in FEATURES:
        for file in feature.files:
            assert (root / where.get(file, file)).exists(), (feature.id, file)
        defined = {}
        for file, name in feature.symbols:
            if file not in defined:
                tree = ast.parse((root / file).read_text(encoding="utf-8"))
                found = set()
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        found.add(node.name)
                    elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                        for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                            if isinstance(target, ast.Name):
                                found.add(target.id)
                defined[file] = found
            assert name in defined[file], (feature.id, file, name)
