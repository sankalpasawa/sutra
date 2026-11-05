"""The run folder, `task.json`, the inbox and the child environment (S1-contracts-03, -09, -11): what the orchestrator writes is what the
engine reads, and the one allowlist of environment names is shared between the launcher and the connectors."""
import json
import os
import stat

import pytest
from sutra_app.connectors import env as connector_env
from sutra_app.connectors.env import PASS_NAMES, child_env
from sutra_app.engine import spec as engine_spec
from sutra_app.engine.host.inbox import InboxTailer
from sutra_app.engine.host.loop import _parse as parse_engine_args
from sutra_app.engine.spec import DEPT_ID_RE, TASK_SCHEMA, TASK_SETTING_KEYS, TaskSpec
from sutra_app.orchestrator import runs
from sutra_app.orchestrator.models import RunSpec, UpstreamRef
from sutra_app.orchestrator.runs import ENGINE_MODULE, EXTRA_PASS_NAMES, ProcessLauncher, child_environment
from sutra_app.ui.boot import URL_ID_PATTERN

from .test_contract_world import clock, db, events, ids, settings, tenv  # noqa: F401  (fixtures used by name)
from orchestrator.test_tasks import ask  # noqa: E402  (after the world: its conftest puts tests/library on sys.path)

SECRETS = {"SUTRA_TOKEN": "tok-0123456789", "ANTHROPIC_API_KEY": "sk-ant-0123456789", "OPENAI_API_KEY": "sk-0123456789",
           "GITHUB_TOKEN": "ghp_0123456789", "CODEX_API_KEY": "cx-0123456789", "AWS_SECRET_ACCESS_KEY": "aws-0123456789",
           "DB_PASSWORD": "pw-0123456789", "CLAUDECODE": "1", "CLAUDE_CODE_OAUTH_TOKEN": "oauth-0123456789"}


def full_environ() -> dict[str, str]:
    base = {name: f"/value/{name}" for name in (*PASS_NAMES, *EXTRA_PASS_NAMES)}
    return {**base, "SUTRA_DATA_DIR": "/data", "SUTRA_MOCK": "1", "J2_BOARD": "1", "J2_SEND_MODE": "live", "HOME": "/Users/x", **SECRETS}


# ---- the allowlist ---------------------------------------------------------------------------------------------------------------

def test_the_launcher_and_the_connectors_share_one_allowlist():
    assert runs.PASS_NAMES is connector_env.PASS_NAMES
    assert EXTRA_PASS_NAMES == ("SHELL", "TERM", "PYTHONPATH")
    assert not set(EXTRA_PASS_NAMES) & set(PASS_NAMES)


def test_the_engine_gets_the_login_directories_so_its_cli_children_find_the_same_login():
    env = child_environment(None, full_environ())
    for name in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "XDG_CONFIG_HOME", "PYTHONPATH", "SHELL", "TERM", "SSL_CERT_FILE", "https_proxy"):
        assert env[name] == f"/value/{name}", name


def test_the_engine_gets_sutra_switches_but_never_the_token_or_a_secret_or_a_j2_flag_from_the_server():
    env = child_environment(None, full_environ())
    assert env["SUTRA_MOCK"] == "1" and env["SUTRA_DATA_DIR"] == "/data"
    assert not set(SECRETS) & set(env)
    assert not [name for name in env if name.startswith("J2_")]


def test_only_the_seven_task_keys_reach_the_engine_environment_and_they_come_from_the_task(tenv):
    task = tenv.new(settings={"J2_OUTPUT": "prd", "J2_BUDGET": "40", "J2_SLIM": "0"})
    spec = tenv.service._run_spec(tenv.db.conn(), tenv.row(task.id), "j2-20261104-100004-7f3a")
    launcher = ProcessLauncher(environ=full_environ())
    env = launcher.environment(spec)
    assert {name: env[name] for name in env if name.startswith("J2_")} == {"J2_OUTPUT": "prd", "J2_BUDGET": "40", "J2_SLIM": "0"}
    assert set(env) - set(PASS_NAMES) - set(EXTRA_PASS_NAMES) == {"SUTRA_DATA_DIR", "SUTRA_MOCK", "J2_OUTPUT", "J2_BUDGET", "J2_SLIM"}
    assert set(spec.settings.model_dump()) <= set(TASK_SETTING_KEYS)


def test_the_cli_children_get_the_allowlist_again_and_no_sutra_or_j2_name():
    engine_env = child_environment({"J2_OUTPUT": "prd"}, full_environ())
    cli_env = child_env("claude", environ=engine_env)
    assert set(cli_env) <= set(PASS_NAMES)
    assert cli_env["CLAUDE_CONFIG_DIR"] == "/value/CLAUDE_CONFIG_DIR" and cli_env["CODEX_HOME"] == "/value/CODEX_HOME"
    assert not [name for name in cli_env if name.startswith(("SUTRA_", "J2_"))]
    assert "PYTHONPATH" not in cli_env and "SHELL" not in cli_env


def test_both_layers_refuse_a_secret_name_whatever_the_value():
    assert "MY_API_KEY" not in child_environment(None, {"MY_API_KEY": "abc", "PATH": "/bin"})
    assert "MY_API_KEY" not in child_environment({"MY_API_KEY": "x"}, {"PATH": "/bin"})
    with pytest.raises(ValueError):
        child_env("codex", {"MY_API_KEY": "abc"})


# ---- the spawn command ------------------------------------------------------------------------------------------------------------

def test_the_command_the_launcher_builds_is_one_the_engine_parses():
    assert ENGINE_MODULE == "sutra_app.engine"
    args = parse_engine_args(["--run-dir", "/data/departments/web/runs/j2-20261104-100004-7f3a"])
    assert str(args.run_dir) == "/data/departments/web/runs/j2-20261104-100004-7f3a"


# ---- RunSpec (the writer) and TaskSpec (the reader) -------------------------------------------------------------------------------

def aliases(model) -> set[str]:
    return {info.alias or name for name, info in model.model_fields.items()}


def test_every_run_spec_field_exists_in_the_task_spec():
    assert aliases(RunSpec) <= aliases(TaskSpec)
    assert aliases(TaskSpec) - aliases(RunSpec) == set()               # no field only the reader knows
    assert RunSpec.model_fields["schema_"].default == TASK_SCHEMA == "run-spec/1"


def test_a_run_spec_dump_is_read_back_by_the_task_spec_field_by_field():
    spec = RunSpec(run_id="j2-20261104-100004-7f3a", task_id="tsk_a1b2c3d4e5f6", dept_id="web", dept_label="Web", user_text="Café menu",
                   framing="the owner wants a menu", parent_run_id="j2-20261103-090000-aaaa", seed_from="j2-20261103-090000-aaaa",
                   upstream=[UpstreamRef(dept_id="sales", run_id="j2-20261103-080000-bbbb", title="Quote", files=["quote.md"])],
                   settings={"J2_OUTPUT": "hld", "J2_BUDGET": "75", "J2_BUDGET_CAP": "150", "J2_FIXES": "1", "J2_MEMORY": "0",
                             "J2_SLIM": "1", "J2_RATES": "0"}, connector="stub")
    dump = json.loads(spec.model_dump_json(by_alias=True))
    read = TaskSpec.model_validate(dump)
    assert read.dropped_settings == ()
    for key, value in dump.items():
        name = "schema_" if key == "schema" else key
        assert json.loads(json.dumps(getattr(read, name))) == value, key


def test_the_task_json_the_task_service_writes_is_valid_for_the_engine_and_has_the_agreed_modes(tenv):
    task = tenv.new("web", "Build a landing page", settings={"J2_BUDGET": "30"})
    tenv.run(tenv.service.start_ready())
    run_dir = tenv.run_dir(task.id)
    path = run_dir / "task.json"
    read = TaskSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))
    row = tenv.row(task.id)
    assert (read.run_id, read.task_id, read.dept_id, read.user_text) == (row.run_id, task.id, "web", "Build a landing page")
    assert read.settings == {"J2_BUDGET": "30"} and read.connector in ("auto", "claude", "codex", "stub")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and stat.S_IMODE(os.stat(run_dir).st_mode) == 0o700
    for name in ("inbox.jsonl", "events.jsonl"):
        assert (run_dir / name).read_bytes() == b"" and stat.S_IMODE(os.stat(run_dir / name).st_mode) == 0o600


def test_the_task_spec_ignores_what_a_newer_orchestrator_adds_and_the_run_spec_does_not():
    dump = {"schema": "run-spec/1", "run_id": "j2-20261104-100004-7f3a", "task_id": "tsk_a1b2c3d4e5f6", "dept_id": "web",
            "user_text": "hi", "added_later": 1}
    assert TaskSpec.model_validate(dump).task_id == "tsk_a1b2c3d4e5f6"
    with pytest.raises(ValueError):
        RunSpec.model_validate({**dump, "dept_label": "Web"})


def test_the_task_setting_keys_are_the_run_spec_keys_and_each_one_is_an_engine_setting():
    from sutra_app.orchestrator.models import TaskSettings
    assert tuple(TaskSettings.model_fields) == TASK_SETTING_KEYS
    assert set(TASK_SETTING_KEYS) <= set(engine_spec.ENV_NAMES.values())
    assert not set(TASK_SETTING_KEYS) & {engine_spec.ENV_NAMES[name] for name in engine_spec.LOCKED_FIELDS}


# ---- the inbox --------------------------------------------------------------------------------------------------------------------

def test_the_lines_the_server_appends_to_the_inbox_are_lines_the_engine_reads(tenv):
    task = tenv.started()
    ask(tenv, task)
    assert tenv.service.deliver_to_department("web", "Sweet Bean, in Leeds").delivered == "answer"
    tenv.run(tenv.service.stop(task))
    trace = []
    lines = InboxTailer(tenv.run_dir(task) / "inbox.jsonl", lambda kind, data: trace.append((kind, data))).read_new()
    assert trace == [] and [(line.n, line.kind) for line in lines] == [(1, "user"), (2, "stop")]
    assert lines[0].text == "Sweet Bean, in Leeds"


def test_the_department_rule_is_one_pattern_and_the_url_rule_is_wider(tenv):
    from sutra_app.orchestrator.departments import _DEPT_ID
    assert _DEPT_ID.pattern == DEPT_ID_RE
    import re
    url = re.compile(URL_ID_PATTERN)
    for dept in ("web", "a-b", "ab", "a" * 40):
        assert re.fullmatch(DEPT_ID_RE, dept) and url.fullmatch(dept)
