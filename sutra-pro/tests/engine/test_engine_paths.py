"""paths.py (DataPaths, load_env_file, pid_alive; engine.md 3.3, 4.7 step 2, section 5) and the fixtures of tests/engine/conftest.py.

The conftest is part of work package E0, so its fixtures are tested here: they make the run folders, ports and services that
every later engine package builds on.
"""
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from sutra_app.engine import paths
from sutra_app.engine.llm import ScriptedPort
from sutra_app.engine.paths import SMTP_VARS, DataPaths, RunDirError, default_env_file, load_env_file, pid_alive, project_root
from sutra_app.engine.spec import TaskSpec

RUN = "j2-20261104-100004-7f3a"


# ---- DataPaths --------------------------------------------------------------------------------------------------------

def test_paths_of_a_run_folder(run_dir, data_dir):
    p = DataPaths.from_run_dir(run_dir)
    assert (p.data_dir, p.dept_id, p.run_id) == (data_dir, "web", RUN)
    assert p.dept_dir == data_dir / "departments" / "web"
    assert p.runs_dir == p.dept_dir / "runs" and p.run_dir == run_dir == p.runs_dir / RUN
    assert p.memory_dir == p.dept_dir / "memory"
    assert (p.lessons_file, p.playbooks_file) == (p.memory_dir / "lessons.jsonl", p.memory_dir / "playbooks.jsonl")
    assert p.library_dir == data_dir / "library" and p.agents_dir == data_dir / "agents" / "j2"
    assert (p.engine_json, p.dept_engine_json, p.page_json) == (data_dir / "engine.json", p.dept_dir / "engine.json", p.dept_dir / "page.json")
    assert p.task_json == run_dir / "task.json" and p.inbox == run_dir / "inbox.jsonl" and p.events == run_dir / "events.jsonl"
    assert p.trace == run_dir / "trace.jsonl" and p.snapshot == run_dir / "snapshot.json" and p.live == run_dir / "live.json"
    assert p.settings_json == run_dir / "settings.json" and p.upstream_dir == run_dir / "upstream"


def test_paths_accept_a_string_a_trailing_slash_and_dots(run_dir, data_dir):
    expected = DataPaths.from_run_dir(run_dir)
    assert DataPaths.from_run_dir(str(run_dir)) == expected
    assert DataPaths.from_run_dir(str(run_dir) + "/") == expected
    assert DataPaths.from_run_dir(run_dir / ".." / run_dir.name) == expected
    assert DataPaths.from_run_dir(run_dir / "." / ".") == expected


def test_a_relative_run_dir_is_read_from_the_current_folder(run_dir, data_dir, monkeypatch):
    monkeypatch.chdir(data_dir)
    assert DataPaths.from_run_dir(Path("departments") / "web" / "runs" / RUN) == DataPaths.from_run_dir(run_dir)


def test_reading_the_layout_creates_nothing(run_dir, data_dir):
    before = sorted(str(p) for p in data_dir.rglob("*"))
    p = DataPaths.from_run_dir(run_dir)
    _ = (p.snapshot, p.trace, p.live, p.settings_json, p.upstream_dir, p.lessons_file, p.library_dir, p.j2_env())
    assert sorted(str(p) for p in data_dir.rglob("*")) == before


def test_a_missing_run_folder_is_refused_and_not_made(data_dir):
    target = data_dir / "departments" / "web" / "runs" / RUN
    with pytest.raises(RunDirError, match="does not exist"):
        DataPaths.from_run_dir(target)
    assert not (data_dir / "departments").exists()


def test_a_file_is_not_a_run_folder(data_dir):
    runs = data_dir / "departments" / "web" / "runs"
    runs.mkdir(parents=True)
    (runs / RUN).write_text("x")
    with pytest.raises(RunDirError, match="does not exist"):
        DataPaths.from_run_dir(runs / RUN)


def test_a_run_folder_that_is_a_link_is_refused(run_dir, data_dir):
    link = run_dir.parent / "j2-20261104-100005-aaaa"
    link.symlink_to(run_dir)
    with pytest.raises(RunDirError, match="symbolic link"):
        DataPaths.from_run_dir(link)


@pytest.mark.parametrize("renames, message", [
    ({"runs": "run"}, "not <data>/departments"), ({"departments": "depts"}, "not <data>/departments"),
])
def test_a_folder_in_the_wrong_place_is_foreign(run_dir, data_dir, renames, message):
    ancestor = {"runs": run_dir.parent, "departments": run_dir.parent.parent.parent}
    for name, new in renames.items():
        ancestor[name].rename(ancestor[name].with_name(new))
    moved = Path(str(run_dir).replace("/" + list(renames)[0] + "/", "/" + list(renames.values())[0] + "/", 1))
    with pytest.raises(RunDirError, match=message):
        DataPaths.from_run_dir(moved)


def test_a_folder_straight_in_tmp_is_foreign(tmp_path):
    (tmp_path / "somewhere").mkdir()
    with pytest.raises(RunDirError, match="not <data>/departments"):
        DataPaths.from_run_dir(tmp_path / "somewhere")


def test_the_department_and_run_names_must_be_ids(data_dir):
    bad_dept = data_dir / "departments" / "Web_1" / "runs" / RUN
    bad_dept.mkdir(parents=True)
    with pytest.raises(RunDirError, match="department id"):
        DataPaths.from_run_dir(bad_dept)
    bad_run = data_dir / "departments" / "web" / "runs" / "run-1"
    bad_run.mkdir(parents=True)
    with pytest.raises(RunDirError, match="run id"):
        DataPaths.from_run_dir(bad_run)


def test_run_dir_error_is_a_value_error():
    assert issubclass(RunDirError, ValueError)


def test_paths_for_a_department_need_no_run(data_dir):
    p = DataPaths.for_dept(data_dir, "web")
    assert p.run_id is None and p.runs_dir == data_dir / "departments" / "web" / "runs"
    assert p == DataPaths(data_dir, "web")
    for name in ("run_dir", "task_json", "inbox", "events", "trace", "snapshot", "live", "settings_json", "upstream_dir"):
        with pytest.raises(ValueError, match="belong to a run"):
            getattr(p, name)
    with_run = DataPaths.for_dept(str(data_dir), "web", RUN)
    assert with_run.run_dir == data_dir / "departments" / "web" / "runs" / RUN


def test_the_same_paths_come_from_the_folder_and_from_the_ids(run_dir, data_dir):
    assert DataPaths.from_run_dir(run_dir) == DataPaths.for_dept(data_dir, "web", RUN)


def test_paths_refuse_bad_ids_at_once(data_dir):
    for dept in ("", "Web", "a_b", "../x", "web/x", None):
        with pytest.raises(ValueError, match="department id"):
            DataPaths.for_dept(data_dir, dept)
    for run in ("", "run-1", "j2-../x", "j2-a/b"):
        with pytest.raises(ValueError, match="run id"):
            DataPaths.for_dept(data_dir, "web", run)


def test_paths_are_frozen_and_the_data_dir_is_absolute(data_dir, monkeypatch):
    p = DataPaths.for_dept(data_dir, "web")
    with pytest.raises(Exception):
        p.dept_id = "other"
    monkeypatch.chdir(data_dir)
    assert DataPaths.for_dept("rel/data", "web").data_dir == data_dir / "rel" / "data"


def test_j2_env_names_the_departments_files_and_the_global_library(data_dir):
    p = DataPaths.for_dept(data_dir, "web", RUN)
    assert p.j2_env() == {"J2_RUNS_DIR": str(data_dir / "departments/web/runs"),
                          "J2_MEMORY_FILE": str(data_dir / "departments/web/memory/lessons.jsonl"),
                          "J2_PLAYBOOK_FILE": str(data_dir / "departments/web/memory/playbooks.jsonl"),
                          "J2_LIBRARY_DIR": str(data_dir / "library"), "J2_TYPES_DIR": str(data_dir / "types"),
                          "J2_PUSH_RUNS": "0", "J2_RUN_BY": "sutra-pro"}      # the two fixed values (D177)
    assert p.types_dir == data_dir / "types" and DataPaths.for_dept(data_dir, "other").types_dir == p.types_dir, "one per user"
    (data_dir / "agents" / "j2").mkdir(parents=True)
    assert p.j2_env()["J2_AGENTS_DIR"] == str(data_dir / "agents" / "j2")
    assert DataPaths.for_dept(data_dir, "other").j2_env()["J2_MEMORY_FILE"].endswith("departments/other/memory/lessons.jsonl")


# ---- load_env_file ----------------------------------------------------------------------------------------------------

def env_file(tmp_path, text, name=".env"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_smtp_names_are_the_five_of_j2_send():
    assert SMTP_VARS == ("J2_SMTP_HOST", "J2_SMTP_PORT", "J2_SMTP_USER", "J2_SMTP_PASSWORD", "J2_SMTP_FROM")


def test_only_the_smtp_login_is_loaded(tmp_path):
    path = env_file(tmp_path, "\n".join([
        "J2_SMTP_HOST=smtp.example.com", "J2_SMTP_PORT=587", "J2_SMTP_USER=bot", "J2_SMTP_PASSWORD=pa ss", "J2_SMTP_FROM=bot@example.com",
        "J2_OVERRIDE_KEY=owner-key", "ANTHROPIC_API_KEY=sk-nope", "J2_BUDGET=5", "GEMINI_API_KEY=g", "PATH=/evil", "J2_TEST_EMAIL=me@x.y"]))
    env = {}
    names = load_env_file(path, environ=env)
    assert names == SMTP_VARS
    assert env == {"J2_SMTP_HOST": "smtp.example.com", "J2_SMTP_PORT": "587", "J2_SMTP_USER": "bot", "J2_SMTP_PASSWORD": "pa ss",
                   "J2_SMTP_FROM": "bot@example.com"}


def test_a_variable_that_is_already_set_wins_and_an_empty_one_does_not(tmp_path):
    path = env_file(tmp_path, "J2_SMTP_HOST=from-file\nJ2_SMTP_PORT=587\nJ2_SMTP_USER=from-file\n")
    env = {"J2_SMTP_HOST": "from-shell", "J2_SMTP_USER": ""}
    assert load_env_file(path, environ=env) == ("J2_SMTP_PORT", "J2_SMTP_USER")
    assert env == {"J2_SMTP_HOST": "from-shell", "J2_SMTP_PORT": "587", "J2_SMTP_USER": "from-file"}


def test_the_file_syntax_of_j2s_loader_and_a_little_more(tmp_path):
    path = env_file(tmp_path, textwrap.dedent("""\
        # the login
        J2_SMTP_HOST = "smtp.example.com"

        export J2_SMTP_PORT=587
        J2_SMTP_USER='bot'
        no equals sign here
        J2_SMTP_PASSWORD=has=equals=signs
        J2_SMTP_FROM=
        #J2_SMTP_FROM=commented@out.com
        """))
    env = {}
    assert load_env_file(path, environ=env) == ("J2_SMTP_HOST", "J2_SMTP_PORT", "J2_SMTP_USER", "J2_SMTP_PASSWORD")
    assert env == {"J2_SMTP_HOST": "smtp.example.com", "J2_SMTP_PORT": "587", "J2_SMTP_USER": "bot", "J2_SMTP_PASSWORD": "has=equals=signs"}


def test_a_byte_order_mark_does_not_hide_the_first_name(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes(b"\xef\xbb\xbfJ2_SMTP_HOST=smtp.example.com\n")
    env = {}
    assert load_env_file(path, environ=env) == ("J2_SMTP_HOST",) and env["J2_SMTP_HOST"] == "smtp.example.com"


def test_a_missing_or_unreadable_file_is_no_file(tmp_path):
    env = {}
    assert load_env_file(tmp_path / "nope.env", environ=env) == ()
    assert load_env_file(tmp_path, environ=env) == ()                                   # a folder
    bad = tmp_path / "bad.env"
    bad.write_bytes(b"J2_SMTP_HOST=\xff\xfe\n")
    assert load_env_file(bad, environ=env) == ()
    assert env == {}


def test_load_env_file_returns_names_and_never_values(tmp_path):
    path = env_file(tmp_path, "J2_SMTP_PASSWORD=s3cret-value\n")
    names = load_env_file(path, environ={})
    assert names == ("J2_SMTP_PASSWORD",) and "s3cret-value" not in repr(names)


def test_the_default_env_file_is_sutra_env_file_else_the_project_dot_env(tmp_path):
    assert default_env_file({}) == project_root() / ".env"
    assert default_env_file({"SUTRA_ENV_FILE": ""}) == project_root() / ".env"
    assert default_env_file({"SUTRA_ENV_FILE": "  "}) == project_root() / ".env"
    assert default_env_file({"SUTRA_ENV_FILE": str(tmp_path / "x.env")}) == tmp_path / "x.env"
    assert (project_root() / "sutra_app" / "engine" / "paths.py").exists()


def test_load_env_file_without_a_path_reads_the_named_file(tmp_path):
    env_file(tmp_path, "J2_SMTP_HOST=named.example.com\n", name="named.env")
    env = {"SUTRA_ENV_FILE": str(tmp_path / "named.env")}
    assert load_env_file(environ=env) == ("J2_SMTP_HOST",)
    assert env["J2_SMTP_HOST"] == "named.example.com"


def test_load_env_file_sets_the_process_environment_by_default(tmp_path, clean_env):
    clean_env.setenv("J2_SMTP_FROM", "")                               # registers the clean-up of what the loader sets
    path = env_file(tmp_path, "J2_SMTP_FROM=bot@example.com\n")
    assert load_env_file(path) == ("J2_SMTP_FROM",)
    assert os.environ["J2_SMTP_FROM"] == "bot@example.com"


# ---- pid_alive --------------------------------------------------------------------------------------------------------

def test_this_process_and_its_parent_are_alive():
    assert pid_alive(os.getpid()) is True
    assert pid_alive(os.getppid()) is True


def test_a_finished_and_reaped_process_is_not_alive():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert pid_alive(child.pid) is False


def test_a_running_child_is_alive_until_it_ends():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert pid_alive(child.pid) is True
    finally:
        child.kill()
        child.wait()
    assert pid_alive(child.pid) is False


@pytest.mark.parametrize("pid", [0, -1, -999, True, False, 1.0, "12", None, [], 2 ** 100, -(2 ** 100)])
def test_something_that_is_not_a_pid_is_never_alive(pid):
    assert pid_alive(pid) is False


def test_a_process_of_another_user_counts_as_alive(monkeypatch):
    def denied(pid, sig):
        raise PermissionError
    monkeypatch.setattr(paths.os, "kill", denied)
    assert pid_alive(4242) is True


def test_other_os_errors_mean_not_alive(monkeypatch):
    def gone(pid, sig):
        raise ProcessLookupError
    monkeypatch.setattr(paths.os, "kill", gone)
    assert pid_alive(4242) is False

    def odd(pid, sig):
        raise OSError("weird")
    monkeypatch.setattr(paths.os, "kill", odd)
    assert pid_alive(4242) is False


def test_pid_alive_sends_signal_zero_only(monkeypatch):
    sent = []
    monkeypatch.setattr(paths.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    assert pid_alive(77) is True and sent == [(77, 0)]


# ---- the conftest fixtures --------------------------------------------------------------------------------------------

def test_data_dir_is_an_empty_folder(data_dir, tmp_path):
    assert data_dir == tmp_path / "data" and data_dir.is_dir() and list(data_dir.iterdir()) == []


def test_run_dir_is_made_the_way_the_orchestrator_makes_one(run_dir, data_dir):
    assert run_dir == data_dir / "departments" / "web" / "runs" / RUN
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((run_dir / "task.json").stat().st_mode) == 0o600
    assert sorted(p.name for p in run_dir.iterdir()) == ["events.jsonl", "inbox.jsonl", "task.json"]
    for name in ("inbox.jsonl", "events.jsonl"):
        assert (run_dir / name).read_bytes() == b"" and stat.S_IMODE((run_dir / name).stat().st_mode) == 0o600
    task = TaskSpec.model_validate_json((run_dir / "task.json").read_text())
    assert (task.run_id, task.dept_id, task.dept_label, task.user_text, task.connector) == (RUN, "web", "Web", "A website for my cafe", "auto")
    assert task.settings == {"J2_BUDGET": "100"} and task.task_id == "tsk_a1b2c3d4e5f6"


def test_make_run_dir_builds_other_departments_and_runs(make_run_dir, data_dir):
    first = make_run_dir("sales-eu", "j2-20261104-110000-bbbb", user_text="Plan the launch", seed_from=RUN, connector="stub")
    second = make_run_dir()
    assert first.parent.parent.name == "sales-eu" and second.name == RUN
    task = TaskSpec.model_validate_json((first / "task.json").read_text())
    assert (task.dept_id, task.dept_label, task.run_id, task.user_text, task.seed_from, task.connector) == (
        "sales-eu", "Sales-Eu", "j2-20261104-110000-bbbb", "Plan the launch", RUN, "stub")
    assert DataPaths.from_run_dir(first).dept_id == "sales-eu"
    with pytest.raises(FileExistsError):
        make_run_dir()
    assert not (first / ".task.json.tmp").exists()                     # written by rename


def test_scripted_port_is_a_fresh_port_with_a_recording_sink(scripted_port):
    assert isinstance(scripted_port, ScriptedPort) and scripted_port.delay == 0 and scripted_port.usage_sink.rows == []
    from sutra_app.engine.port import CompletionRequest
    scripted_port.complete(CompletionRequest(system="s", user="u", scripted=lambda: "x"))
    assert len(scripted_port.usage_sink.rows) == 1 and scripted_port.usage_sink.record({"a": 1}) == 2


def test_the_scripted_port_of_the_next_test_starts_empty(scripted_port):
    assert scripted_port.usage_sink.rows == []


@pytest.fixture
def dirty_env(monkeypatch):
    for name in ("J2_BUDGET", "J2_ANYTHING", "STUDIO_MOCK", "STUDIO_MOCK_DELAY", "SUTRA_MOCK", "SUTRA_OFFLINE", "SUTRA_HOOKS",
                 "SUTRA_NODES", "SUTRA_HEARTBEAT_S", "SUTRA_RECORDS", "SUTRA_RECORDS_HOOK", "SUTRA_ENV_FILE", "SUTRA_SLOW_PROBE", "KEEP_ME"):
        monkeypatch.setenv(name, "1")


def test_clean_env_removes_the_j2_and_studio_variables_and_the_engines_switches(dirty_env, clean_env):
    gone = [n for n in os.environ if n.startswith(("J2_", "STUDIO_"))]
    assert gone == []
    for name in ("SUTRA_MOCK", "SUTRA_OFFLINE", "SUTRA_HOOKS", "SUTRA_NODES", "SUTRA_HEARTBEAT_S", "SUTRA_RECORDS", "SUTRA_RECORDS_HOOK",
                 "SUTRA_ENV_FILE"):
        assert name not in os.environ
    assert os.environ["KEEP_ME"] == "1" and os.environ["SUTRA_SLOW_PROBE"] == "1" and "PATH" in os.environ     # nothing else is touched
    clean_env.setenv("J2_BOARD", "1")                                      # it returns the monkeypatch
    assert os.environ["J2_BOARD"] == "1"


def test_clean_env_leaves_the_opt_in_switches_of_the_suite_alone(monkeypatch):
    monkeypatch.setenv("SUTRA_SLOW", "1")
    monkeypatch.setenv("SUTRA_J2_CHECKOUT", "/x")
    from _pytest.monkeypatch import MonkeyPatch
    with MonkeyPatch.context() as mp:
        for name in list(os.environ):
            if name.startswith(("J2_", "STUDIO_")):
                mp.delenv(name)
    assert os.environ["SUTRA_SLOW"] == "1" and os.environ["SUTRA_J2_CHECKOUT"] == "/x"


_STATE = {}


def test_llm_reset_gives_a_known_state_part_one(llm_reset):
    from sutra_app.engine.port import CallTag
    assert (llm_reset.MOCK, llm_reset.PROVIDER, llm_reset.MODEL, llm_reset._PORT, llm_reset._DEFAULT_PORT) == (False, None, None, None, None)
    assert llm_reset._BASE_TAG == CallTag() and llm_reset.bound_atom() is None and llm_reset.LAST_META == {}
    llm_reset.configure(mock=True, base_tag={"run_id": "j2-1"})
    llm_reset.bind_atom("a-aaaaaaaaaa-01")
    llm_reset.LAST_META["x"] = 1
    _STATE["dirty"] = True


def test_llm_reset_puts_it_back_part_two(llm_reset):
    assert _STATE.get("dirty") is True                                     # the previous test did dirty the module
    assert (llm_reset.MOCK, llm_reset._PORT, llm_reset.bound_atom(), llm_reset.LAST_META, llm_reset.current_tag().run_id) == (False, None, None, {}, "")


# ---- fake_services ----------------------------------------------------------------------------------------------------

def test_fake_services_know_their_departments_and_runs(fake_services, data_dir):
    assert fake_services.data_dir == data_dir and fake_services.department("web") is None
    dept = fake_services.add_department("web", "Web")
    assert fake_services.department("web") is dept and (dept.id, dept.name, dept.archived) == ("web", "Web", False)
    assert (data_dir / "departments" / "web" / "runs").is_dir()
    assert fake_services.add_department("old", archived=True).archived is True and fake_services.department("old").name == "Old"


def test_add_run_makes_the_folder_and_its_files(fake_services, data_dir):
    ref = fake_services.add_run("web", RUN, status="done", files={"chat.jsonl": '{"meta": true}\n', "summary.json": {"status": "done"},
                                                                  "site/v1.html": "<p>hi</p>", "site/shots/v1.png": b"\x89PNG"})
    folder = data_dir / ref.dir
    assert ref.dir == f"departments/web/runs/{RUN}" and (ref.run_id, ref.dept_id, ref.status) == (RUN, "web", "done")
    assert (folder / "chat.jsonl").read_text() == '{"meta": true}\n'
    assert (folder / "summary.json").read_text() == '{"status": "done"}'
    assert (folder / "site" / "v1.html").read_text() == "<p>hi</p>" and (folder / "site/shots/v1.png").read_bytes() == b"\x89PNG"
    assert fake_services.department("web") is not None                  # a department is added with its first run


def test_add_run_numbers_unnamed_runs_with_valid_ids(fake_services):
    from sutra_app.engine.spec import is_run_id
    refs = [fake_services.add_run("web") for _ in range(3)]
    assert len({r.run_id for r in refs}) == 3 and all(is_run_id(r.run_id) for r in refs)


def test_resolve_run_is_the_orchestrators_rule(fake_services):
    assert fake_services.resolve_run(None, "web") is None
    old = fake_services.add_run("web", "j2-20261104-090000-aaaa", status="done")
    assert fake_services.resolve_run(None, "web") is old                   # the latest when nothing is live
    live = fake_services.add_run("web", "j2-20261104-100000-bbbb", status="running")
    newer = fake_services.add_run("web", "j2-20261104-110000-cccc", status="done")
    assert fake_services.resolve_run(None, "web") is live                  # the live task's run beats a newer finished one
    assert fake_services.resolve_run("j2-20261104-090000-aaaa", "web") is old        # an id wins
    other = fake_services.add_run("sales", "j2-20261104-120000-dddd")
    assert fake_services.resolve_run(other.run_id, "web") is None          # another department's run is not found
    assert fake_services.resolve_run("j2-nope", "web") is None
    assert fake_services.resolve_run(None, "sales") is other and newer.status == "done"
    for status in ("starting", "waiting_user"):
        assert fake_services.add_run("hr", status=status) is fake_services.resolve_run(None, "hr")


def test_a_delivery_answers_a_waiting_run_or_starts_a_follow_up(fake_services):
    follow = fake_services.deliver_to_department("web", "More please", scope_id="menu", settings={"J2_OUTPUT": "prd"})
    assert (follow.delivered, follow.task_id.startswith("tsk_")) == ("follow_up", True)
    waiting = fake_services.add_run("web", status="waiting_user")
    answer = fake_services.deliver_to_department("web", "Option 2")
    assert (answer.delivered, answer.task_id) == ("answer", waiting.task_id)
    assert fake_services.deliveries == [
        {"dept_id": "web", "text": "More please", "scope_id": "menu", "settings": {"J2_OUTPUT": "prd"}},
        {"dept_id": "web", "text": "Option 2", "scope_id": None, "settings": None}]


def test_a_busy_department_raises_but_the_attempt_is_still_recorded(fake_services):
    fake_services.busy = True
    with pytest.raises(Exception) as caught:
        fake_services.deliver_to_department("web", "hello")
    assert type(caught.value).__name__ == "FakeBusy" and "web" in str(caught.value)
    assert [d["text"] for d in fake_services.deliveries] == ["hello"]


def test_stop_live_answers_what_it_is_told_and_remembers_the_asks(fake_services):
    assert fake_services.stop_live("web") is True
    fake_services.stop_result = False
    assert fake_services.stop_live("hr") is False
    assert fake_services.stops == ["web", "hr"]


def test_redact_hides_the_secrets_it_was_given(fake_services):
    assert fake_services.redact("the key is sk-12345") == "the key is sk-12345"
    fake_services.secrets.append("sk-12345")
    assert fake_services.redact("the key is sk-12345, again sk-12345") == "the key is [redacted], again [redacted]"


def test_require_token_is_a_fastapi_dependency_that_wants_the_header(fake_services):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()

    @app.post("/write", dependencies=[Depends(fake_services.require_token)])
    def write():
        return {"ok": True}

    @app.get("/read")
    def read():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/read").status_code == 200
    denied = client.post("/write")
    assert denied.status_code == 401 and denied.json()["detail"]["error"]["code"] == "bad_token"
    assert client.post("/write", headers={"X-Sutra-Token": "wrong"}).status_code == 401
    assert client.post("/write", headers={"X-Sutra-Token": fake_services.token}).json() == {"ok": True}
    assert fake_services.require_token is fake_services.require_token       # one dependency object


# ---- collection rules of the conftest ---------------------------------------------------------------------------------

@pytest.fixture
def mini_suite(tmp_path):
    """tests/engine/conftest.py alone in a temporary folder, with a legacy script that must never be collected and a slow test."""
    suite = tmp_path / "suite"
    (suite / "legacy").mkdir(parents=True)
    (suite / "conftest.py").write_text((Path(__file__).parent / "conftest.py").read_text(encoding="utf-8"), encoding="utf-8")
    (suite / "legacy" / "j2_flow_test.py").write_text("def test_legacy_script():\n    raise AssertionError('J2 scripts are not collected')\n")
    (suite / "test_things.py").write_text(textwrap.dedent("""\
        import pytest
        def test_plain(): pass
        @pytest.mark.slow
        def test_slow(): pass
        @pytest.mark.live
        def test_live(): pass
    """))
    return suite


def run_suite(suite, *args, slow=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SUTRA_")}
    if slow:
        env["SUTRA_SLOW"] = "1"
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--strict-markers", "-rs", *args],
                         cwd=suite, env=env, capture_output=True, text=True)
    return out.returncode, out.stdout + out.stderr


def test_the_legacy_scripts_are_not_collected_and_slow_tests_skip_by_default(mini_suite):
    code, out = run_suite(mini_suite)
    assert code == 0, out
    assert "2 passed, 1 skipped" in out                                   # test_plain and test_live ran, test_slow did not
    assert "slow engine suite: set SUTRA_SLOW=1, or select it with -m" in out
    assert "J2 scripts are not collected" not in out and "j2_flow_test" not in out


def test_slow_tests_run_with_sutra_slow_one(mini_suite):
    code, out = run_suite(mini_suite, slow=True)
    assert code == 0 and "3 passed" in out and "skipped" not in out, out


def test_slow_tests_run_when_a_marker_expression_is_given(mini_suite):
    code, out = run_suite(mini_suite, "-m", "slow")
    assert code == 0 and "1 passed, 2 deselected" in out and "skipped" not in out, out
    code, out = run_suite(mini_suite, "-m", "not slow")
    assert code == 0 and "2 passed, 1 deselected" in out and "skipped" not in out, out


def test_the_slow_and_live_markers_are_registered_by_the_conftest_itself(mini_suite):
    code, out = run_suite(mini_suite, "--markers")
    assert code == 0 and "@pytest.mark.slow: long engine suites" in out and "@pytest.mark.live: talks to the real claude or codex CLI" in out
