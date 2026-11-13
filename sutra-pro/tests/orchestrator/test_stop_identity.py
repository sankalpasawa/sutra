"""The stop ladder signals only a process it has identified (ORCH-6, D156).

A task re-adopted after the app restarted has a pid this launcher did not spawn, and after a reboot or a crash that number may belong to any
program. The ladder signals a whole process group, so `ProcessLauncher.stop` first reads the command line of such a pid and goes on only when
it is this engine's run of that folder (`-m <module> --run-dir <run folder>`, the identity the start-up pass uses): any other process is
treated as gone, with nothing written to the inbox, nothing signalled and nothing waited for. The engine here is the fake engine process
(`sutra_app.orchestrator.testing.fake_engine`, played by a script); a foreign process is a plain `sleep` or python child, or the same engine
module run for another folder. The launcher's own children are never looked up: their Process handle is the proof.
"""
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from sutra_app.orchestrator.models import RunSpec
from sutra_app.orchestrator.runs import ENGINE_MODULE, ProcessLauncher, is_engine_command
from sutra_app.orchestrator.testing.fake_engine import ev

FAKE_ENGINE = "sutra_app.orchestrator.testing.fake_engine"
SPEC = RunSpec(run_id="j2-20261110-100004-7f3a", task_id="tsk_a1b2c3d4e5f6", dept_id="web", dept_label="Web", user_text="hi")
STARTED = {"emit": ev("run.started", schema="events/1", mock=True, seed="none")}
HOLD = [STARTED, {"hold": True}]                                       # works until the stop line arrives, then writes run.ended stopped and exits 0
STUBBORN = [STARTED, {"ignore_stop": True}, {"hold": True}]            # never honours the stop line: only a signal ends it


def run_folder(tmp_path: Path, name: str = "run") -> Path:
    run = tmp_path / name
    run.mkdir()
    (run / "inbox.jsonl").write_bytes(b"")
    (run / "events.jsonl").write_bytes(b"")
    return run


def script(tmp_path: Path, steps: list) -> Path:
    path = tmp_path / "script.json"
    path.write_text(json.dumps(steps), encoding="utf-8")
    return path


def has_started(run: Path) -> bool:
    return b'"run.started"' in (run / "events.jsonl").read_bytes()


def spawn(argv: list[str], **kwargs) -> subprocess.Popen:
    """A child in a session of its own, as the launcher makes it, reaped the moment it ends (a zombie still answers `kill -0`)."""
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, **kwargs)
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc


def earlier_engine(run: Path, steps_file: Path) -> subprocess.Popen:
    """The engine as an earlier server started it: the launcher's own command line, a session of its own, and no handle on it in the launcher
    that is later asked to stop it."""
    proc = spawn([sys.executable, "-m", FAKE_ENGINE, "--run-dir", str(run)], cwd=run, env={**os.environ, "SUTRA_FAKE_SCRIPT": str(steps_file)})
    deadline = time.monotonic() + 30
    while not has_started(run):
        assert time.monotonic() < deadline and proc.poll() is None, "the fake engine did not start"
        time.sleep(0.02)
    return proc


def end(*procs: subprocess.Popen) -> None:
    for proc in procs:
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait()


# ---- a pid that is not this engine's run -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["sleep", "python", "the engine of another run"])
def test_a_process_that_is_not_this_engines_run_is_left_alone_and_nothing_is_waited_for(tmp_path, caplog, kind):
    run, other = run_folder(tmp_path), run_folder(tmp_path, "other")
    if kind == "sleep":
        foreign = spawn(["sleep", "60"])
    elif kind == "python":
        foreign = spawn([sys.executable, "-c", "import time; time.sleep(60)"])
    else:
        foreign = earlier_engine(other, script(tmp_path, HOLD))               # the engine module, but the folder of ANOTHER run
    try:
        launcher = ProcessLauncher(module=FAKE_ENGINE)
        started = time.monotonic()
        with caplog.at_level(logging.WARNING, logger="sutra_app.orchestrator.runs"):
            asyncio.run(launcher.stop(run, foreign.pid, stop_grace=5, term_grace=5))
        assert time.monotonic() - started < 2.0                              # the two graces (10 s in all) were not waited out
        assert foreign.poll() is None                                        # SIGTERM and SIGKILL both end all three kinds: neither was sent
        assert (run / "inbox.jsonl").read_bytes() == b""                     # no stop line for a process that is not ours
        assert any("not the engine" in record.getMessage() for record in caplog.records)
        if kind == "the engine of another run":
            assert (other / "inbox.jsonl").read_bytes() == b"" and b"run.ended" not in (other / "events.jsonl").read_bytes()
    finally:
        end(foreign)


def test_a_pid_that_is_gone_is_still_nothing_to_do(tmp_path):
    run = run_folder(tmp_path)
    gone = spawn(["sleep", "0"])
    gone.wait(timeout=10)
    launcher = ProcessLauncher(module=FAKE_ENGINE)
    started = time.monotonic()
    asyncio.run(launcher.stop(run, gone.pid, stop_grace=5, term_grace=5))
    assert time.monotonic() - started < 2.0 and (run / "inbox.jsonl").read_bytes() == b""


# ---- an engine under a recorded pid is still stopped -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("steps, how", [(HOLD, "the stop line"), (STUBBORN, "SIGTERM")])
def test_an_engine_the_launcher_spawned_is_stopped_by_the_ladder_without_a_look_at_its_command(tmp_path, steps, how):
    run = run_folder(tmp_path)
    looked: list[int] = []
    launcher = ProcessLauncher(module=FAKE_ENGINE, extra_env={"SUTRA_FAKE_SCRIPT": str(script(tmp_path, steps))})
    launcher.command_of = lambda pid: looked.append(pid) or ""               # its Process handle is the proof: `ps` is never asked about it

    async def go() -> int:
        pid = await launcher.start(SPEC, run)
        for _ in range(1500):                                                # the child needs a moment to import and write its first line
            if has_started(run):
                break
            await asyncio.sleep(0.02)
        assert has_started(run) and launcher.alive(pid)
        await launcher.stop(run, pid, stop_grace=10 if how == "the stop line" else 0.5, term_grace=5)
        return pid

    pid = asyncio.run(go())
    assert not launcher.alive(pid) and looked == []
    assert launcher.exit_code(pid) == (0 if how == "the stop line" else -signal.SIGTERM)
    assert json.loads((run / "inbox.jsonl").read_text().splitlines()[0])["kind"] == "stop"
    assert (b'"stopped"' in (run / "events.jsonl").read_bytes()) is (how == "the stop line")       # an engine that heard the line said so itself


@pytest.mark.parametrize("steps, how", [(HOLD, "the stop line"), (STUBBORN, "SIGTERM")])
def test_an_engine_an_earlier_server_started_is_stopped_by_the_ladder(tmp_path, steps, how):
    run = run_folder(tmp_path)
    engine = earlier_engine(run, script(tmp_path, steps))
    try:
        launcher = ProcessLauncher(module=FAKE_ENGINE)                       # a server that has just started: no handle on the pid
        started = time.monotonic()
        asyncio.run(launcher.stop(run, engine.pid, stop_grace=10 if how == "the stop line" else 0.5, term_grace=5))
        assert engine.wait(timeout=10) == (0 if how == "the stop line" else -signal.SIGTERM)
        assert time.monotonic() - started < 5.0                              # the ladder stopped at the rung that worked
        assert json.loads((run / "inbox.jsonl").read_text().splitlines()[0])["kind"] == "stop"
        assert (b'"stopped"' in (run / "events.jsonl").read_bytes()) is (how == "the stop line")
    finally:
        end(engine)


# ---- the identity itself ---------------------------------------------------------------------------------------------------------------

def test_the_identity_is_the_engine_module_and_the_run_folder(tmp_path):
    run = tmp_path / "run"
    command = f"/usr/bin/python3 -m {ENGINE_MODULE} --run-dir {run}"
    assert is_engine_command(command, ENGINE_MODULE, run)
    assert not is_engine_command(command, ENGINE_MODULE, tmp_path / "other")            # the engine, but the folder of another run
    assert not is_engine_command(command, FAKE_ENGINE, run)                             # another module
    assert not is_engine_command("sleep 60", ENGINE_MODULE, run) and not is_engine_command("", ENGINE_MODULE, run)


def test_a_windows_command_line_shows_a_folder_with_a_space_in_quotes_and_is_the_same_identity():
    run = Path(r"D:\Sutra Data\departments\web\runs\r1")
    command = rf'"C:\Python311\python.exe" -X utf8 -m {ENGINE_MODULE} --run-dir "{run}"'
    assert is_engine_command(command, ENGINE_MODULE, run)
    assert not is_engine_command(command, ENGINE_MODULE, Path(r"D:\Sutra Data\departments\web\runs\r2"))
