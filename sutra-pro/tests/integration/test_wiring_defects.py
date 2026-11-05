"""Wiring defects found by the coverage critic (work package GAP-W1, docs/design/gaps.md G01 to G04).

G01  the host builds the function-node layer through its own factory call (no `SUTRA_HOOKS` override), a swallowed hook error
     is no longer silent, and a `stop` line or SIGTERM abandons every open atom before `run.ended`.
G02  a wheel built offline carries `library/specs/function_specs.json`.
G03  `default_env_file()` is `<project>/.env` in a checkout and `<data dir>/.env` in an installed app (both copies of it).
G04  the Sutra read tools open the database the app writes: one constant, and a real MCP server reads a chart row from a
     database made by `Database.migrate()` and the real chart store.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from sutra_app import config as app_config
from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.connectors.tools import profiles
from sutra_app.engine import paths as engine_paths
from sutra_app.engine.events import EventWriter
from sutra_app.engine.fnodes.layer import FunctionNodeHooks, factory
from sutra_app.engine.host import loop
from sutra_app.engine.spec import TaskSpec
from sutra_app.orchestrator.chart import ChartStore
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.db import Database
from sutra_app.orchestrator.graph import GraphStore

REPO = Path(__file__).resolve().parents[2]


def _load_recorder():
    spec = importlib.util.spec_from_file_location("record_fn_golden_gapw1", REPO / "scripts" / "record_fn_golden.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rec = _load_recorder()


# ---- G01a: the host and the layer agree on the name of the TaskSpec --------------------------------------------------------
@pytest.fixture
def run_dir(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    return folder


def _task() -> TaskSpec:
    return TaskSpec(schema="run-spec/1", run_id=rec.RUN_ID, task_id=rec.TASK_ID, dept_id=rec.DEPT, dept_label="Web", user_text="hi")


def _bare_host(run_dir):
    """A `Host` with just what `_make_hooks` reads: the run folder, the writer and the task."""
    host = loop.Host(loop._parse(["--run-dir", str(run_dir)]), None)
    host.paths = SimpleNamespace(run_dir=run_dir)
    host.writer = EventWriter(run_dir)
    host.task = _task()
    return host


def test_the_layer_factory_takes_the_task_spec_as_spec_and_as_its_alias_task(run_dir):
    writer = EventWriter(run_dir)
    by_spec = factory(writer, lambda: None, spec=_task(), environ={})
    by_task = factory(writer, lambda: None, task=_task(), environ={})
    for hooks in (by_spec, by_task):
        assert isinstance(hooks, FunctionNodeHooks)
        assert (hooks.run_id, hooks.dept_id) == (rec.RUN_ID, rec.DEPT)


def test_the_layer_factory_refuses_spec_and_task_together(run_dir):
    with pytest.raises(TypeError, match="spec"):
        factory(EventWriter(run_dir), lambda: None, task=_task(), spec=_task(), environ={})


def test_the_host_builds_the_function_node_layer_through_its_own_factory_call(run_dir, monkeypatch):
    monkeypatch.delenv("SUTRA_HOOKS", raising=False)
    monkeypatch.delenv("SUTRA_NODES", raising=False)
    host = _bare_host(run_dir)
    hooks = host._make_hooks(lambda: None)
    assert isinstance(hooks, FunctionNodeHooks)
    assert host._function_nodes_off is None
    assert not (run_dir / "trace.jsonl").exists(), "no publish.error: the factory call itself did not fail"


def test_a_factory_that_fails_leaves_the_reason_for_the_chat_and_a_trace_line(run_dir, monkeypatch):
    monkeypatch.setenv("SUTRA_HOOKS", "no_such_module_gapw1:factory")
    host = _bare_host(run_dir)
    hooks = host._make_hooks(lambda: None)
    assert not isinstance(hooks, FunctionNodeHooks)
    assert "no_such_module_gapw1" in host._function_nodes_off
    trace = [json.loads(x) for x in (run_dir / "trace.jsonl").read_text().splitlines()]
    assert [t["type"] for t in trace] == ["publish.error"] and trace[0]["data"]["where"] == "hooks"


def _system_texts(run):
    return [m["text"] for m in run["chat"] if m.get("who") == "system"]


def test_a_run_without_the_layer_says_so_in_the_chat_unless_nodes_are_off(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "DEFAULT_HOOKS", "no_such_module_gapw1:factory")
    broken = rec.run_scenario(tmp_path / "broken", "default")
    lines = [t for t in _system_texts(broken) if t.startswith("function nodes are off: ")]
    assert len(lines) == 1 and "no_such_module_gapw1" in lines[0]
    assert [t["data"]["where"] for t in broken["trace"] if t["type"] == "publish.error"] == ["hooks"]
    assert broken["code"] == 0
    off = rec.run_scenario(tmp_path / "off", "off")
    assert not [t for t in _system_texts(off) if "function nodes are off" in t]
    assert not [t for t in off["trace"] if t["type"] == "publish.error"]


# ---- G01b: a stop or SIGTERM abandons the open atoms before run.ended ---------------------------------------------------
def _atoms(run):
    last = {}
    for e in rec.function_atom_events(run["events"]):
        last[e["atom"]["id"]] = e["atom"]
    return last


def test_a_stop_line_abandons_the_open_manual_atom_before_run_ended(tmp_path):
    run = rec.run_scenario(tmp_path, "default", stop_on_question=True)
    atoms = _atoms(run)
    assert run["code"] == 0 and run["events"][-1]["t"] == "run.ended" and run["events"][-1]["status"] == "stopped"
    manual = [a for a in atoms.values() if a["work_kind"] == "manual"]
    assert [a["status"] for a in manual] == ["abandoned"]
    assert [a["id"] for a in atoms.values() if a["status"] == "open"] == []
    assert "run ended: stopped" in json.dumps(manual[0]), "the reason names the stop"
    abandoned_at = [i for i, e in enumerate(run["events"]) if e["t"] == "atom" and e["atom"]["status"] == "abandoned"]
    assert abandoned_at and max(abandoned_at) < len(run["events"]) - 1


def test_sigterm_abandons_the_open_atoms_too_and_exits_143(tmp_path, monkeypatch):
    made = []
    original = loop.Host.__init__

    def spy(self, *a, **k):
        original(self, *a, **k)
        made.append(self)

    def terminate_on_first_question(run, answers, stop, stop_run=False):
        while not stop.is_set():
            rows = [json.loads(x) for x in (run / "events.jsonl").read_text().splitlines() if x.strip()]
            if any(e["t"] == "say" and e.get("act") == "ASK_REQUESTER" for e in rows):
                made[0].request_termination()
                return
            stop.wait(0.005)

    monkeypatch.setattr(loop.Host, "__init__", spy)
    monkeypatch.setattr(rec, "_answer", terminate_on_first_question)
    run = rec.run_scenario(tmp_path, "default")
    atoms = _atoms(run)
    assert run["code"] == loop.EXIT_TERM == 143
    assert run["events"][-1]["t"] == "run.ended" and run["events"][-1]["status"] == "stopped"
    assert [a["status"] for a in atoms.values() if a["work_kind"] == "manual"] == ["abandoned"]
    assert [a["id"] for a in atoms.values() if a["status"] == "open"] == []


def test_a_stop_with_the_plain_hooks_has_no_atoms_to_abandon_and_is_no_error(tmp_path):
    run = rec.run_scenario(tmp_path, "off", stop_on_question=True)
    assert run["code"] == 0 and run["events"][-1]["status"] == "stopped"
    assert not [t for t in run["trace"] if t["type"] == "publish.error"]


# ---- G03: .env beside the data folder for an installed app ---------------------------------------------------------------
@pytest.fixture(params=["config", "engine_paths"])
def env_module(request):
    return app_config if request.param == "config" else engine_paths


def test_a_checkout_keeps_its_env_file_at_the_project_root(env_module, tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    monkeypatch.setattr(env_module, "project_root", lambda: tmp_path)
    assert env_module.default_env_file({}) == tmp_path / ".env"
    assert env_module.default_env_file({"SUTRA_DATA_DIR": str(tmp_path / "elsewhere")}) == tmp_path / ".env"


def test_an_installed_app_looks_beside_its_data_folder(env_module, tmp_path, monkeypatch):
    site = tmp_path / "site-packages"
    site.mkdir()
    monkeypatch.setattr(env_module, "project_root", lambda: site)
    data = tmp_path / "data"
    assert env_module.default_env_file({"SUTRA_DATA_DIR": str(data)}) == data / ".env"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert env_module.default_env_file({}) == tmp_path / "home" / ".sutra-pro" / ".env"


def test_the_env_file_variable_wins_everywhere(env_module, tmp_path, monkeypatch):
    monkeypatch.setattr(env_module, "project_root", lambda: tmp_path / "site-packages")
    named = tmp_path / "mine.env"
    assert env_module.default_env_file({"SUTRA_ENV_FILE": str(named), "SUTRA_DATA_DIR": str(tmp_path / "d")}) == named


def test_settings_load_the_override_key_from_the_data_folder_env_of_an_installed_app(tmp_path, monkeypatch):
    site = tmp_path / "site-packages"
    site.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    (data / ".env").write_text("J2_OVERRIDE_KEY=from-the-data-folder-0123456789\n")
    monkeypatch.setattr(app_config, "project_root", lambda: site)
    monkeypatch.delenv("SUTRA_ENV_FILE", raising=False)
    monkeypatch.delenv("J2_OVERRIDE_KEY", raising=False)
    settings = app_config.Settings.load({"SUTRA_DATA_DIR": str(data)})
    assert settings.env_file == data / ".env"
    assert settings.override_key.get_secret_value() == "from-the-data-folder-0123456789"


# ---- G04: the Sutra tools open the database the app writes -------------------------------------------------------------
def test_one_constant_names_the_database_file():
    assert app_config.DB_FILENAME == "db.sqlite3"
    settings = app_config.Settings.load({}, data_dir=Path("/x/data"), token="t" * 20, env_file=Path("/x/none.env"))
    assert settings.db_path == Path("/x/data") / app_config.DB_FILENAME


@pytest.fixture
def migrated(tmp_path):
    settings = app_config.Settings.load({}, data_dir=tmp_path / "data", token="t" * 20, env_file=tmp_path / "none.env")
    db = Database(settings.db_path, lambda events: None)
    db.migrate()
    store = ChartStore(db, graph=GraphStore(db), chats=ChatStore(db), data_dir=settings.data_dir)
    assert store.bootstrap() is True
    db.close()
    return settings


@pytest.mark.parametrize("who", ["profiles", "claude", "codex"])
def test_the_mcp_server_started_with_the_entry_of_each_builder_reads_the_root_chart(migrated, tmp_path, who):
    cfg = ConnectorConfig(data_dir=migrated.data_dir, work_root=tmp_path / "work", python=sys.executable)
    entry = {"profiles": lambda: profiles.mcp_servers(cfg, ("sutra",)),
             "claude": lambda: ClaudeConnector(cfg).mcp_servers(("sutra",)),
             "codex": lambda: CodexConnector(cfg).mcp_servers(("sutra",))}[who]()["sutra"]
    assert entry["env"]["SUTRA_DB_RO"] == str(migrated.db_path)
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"), **entry["env"]}
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "sutra_chart_read", "arguments": {}}}
    proc = subprocess.run([entry["command"], *entry["args"]], input=json.dumps(request) + "\n", capture_output=True, text=True,
                          timeout=60, env=env, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.splitlines()[0])["result"]
    body = json.loads(result["content"][0]["text"])
    assert result["isError"] is False, body
    assert body["root"]["kind"] == "root" and body["revision"] == 1


# ---- G02: the wheel carries the function specs ---------------------------------------------------------------------------
def test_a_built_wheel_carries_the_function_specs(tmp_path):
    uv = shutil.which("uv")
    if uv is None:
        print("skipped: uv is not on PATH, so no wheel can be built here")
        pytest.skip("uv is not on PATH")
    src = tmp_path / "src"
    src.mkdir()
    for name in ("pyproject.toml", "README.md"):
        if (REPO / name).is_file():
            shutil.copy(REPO / name, src)
    shutil.copytree(REPO / "sutra_app", src / "sutra_app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    proc = subprocess.run([uv, "build", "--wheel", "--offline", "--out-dir", str(tmp_path / "dist"), str(src)], capture_output=True,
                          text=True, timeout=180, cwd=tmp_path)
    if proc.returncode != 0:
        reason = (proc.stderr.strip().splitlines() or ["uv build failed"])[-1]
        print(f"skipped: uv could not build a wheel offline here ({reason})")
        pytest.skip(f"uv could not build a wheel offline: {reason}")
    wheels = sorted((tmp_path / "dist").glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        data = json.loads(wheel.read("sutra_app/library/specs/function_specs.json"))
    assert data, "the specs file is not empty"
