"""sutra_app.oslayer (D101): the few places where Windows and POSIX differ.

Every test here is platform-neutral: it states what the function promises and proves it on whichever system runs it. The Windows leg of
the CI runs this file for real, which is the only proof the Windows branches (msvcrt locks, OpenProcess, job objects, taskkill) get.
"""
import os
import re
import subprocess
import sys
import textwrap
import time

import pytest

from sutra_app import oslayer
from sutra_app.ops import lock


def wait_until(predicate, seconds=15.0, step=0.05):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


# ---------------------------------------------------------------- locks

def test_try_lock_is_exclusive_and_unlock_gives_it_back(tmp_path):
    path = tmp_path / "x.lock"
    first = os.open(path, os.O_RDWR | os.O_CREAT | oslayer.O_BINARY, 0o600)
    second = os.open(path, os.O_RDWR | oslayer.O_BINARY)
    try:
        assert oslayer.try_lock(first) is True
        assert oslayer.try_lock(second) is False, "a second open of the same file does not get the lock"
        oslayer.unlock(first)
        assert oslayer.try_lock(second) is True
        oslayer.unlock(second)
    finally:
        os.close(first)
        os.close(second)


def test_a_lock_dies_with_its_process(tmp_path):
    path = tmp_path / "held.lock"
    code = textwrap.dedent("""
        import os, sys
        from sutra_app import oslayer
        fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT | oslayer.O_BINARY, 0o600)
        assert oslayer.try_lock(fd)
        print("locked", flush=True)
        sys.stdin.readline()
    """)
    child = subprocess.Popen([sys.executable, "-c", code, str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "locked"
        mine = os.open(path, os.O_RDWR | oslayer.O_BINARY)
        try:
            assert oslayer.try_lock(mine) is False, "another process holds it"
            child.stdin.write("\n")
            child.stdin.flush()
            child.wait(timeout=20)
            assert oslayer.try_lock(mine) is True, "the lock went with the process that held it"
        finally:
            os.close(mine)
    finally:
        child.kill()
        child.wait()


def test_the_instance_lock_is_taken_once_and_released(tmp_path):
    first, second = lock.InstanceLock(tmp_path, version="1"), lock.InstanceLock(tmp_path, version="1")
    assert first.acquire() is True
    assert second.acquire() is False
    assert lock.is_locked(tmp_path) is True
    holder = lock.read_holder(tmp_path)
    assert holder is not None and holder.pid == os.getpid()
    first.release()
    assert lock.is_locked(tmp_path) is False
    assert second.acquire() is True
    second.release()


# ---------------------------------------------------------------- processes

def test_pid_alive_knows_this_process_a_finished_child_and_nonsense():
    assert oslayer.pid_alive(os.getpid()) is True
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=30)
    assert oslayer.pid_alive(child.pid) is False
    assert oslayer.pid_alive(0) is False and oslayer.pid_alive(-7) is False


def test_pid_alive_does_not_end_the_process_it_asks_about():
    """On Windows os.kill(pid, 0) would terminate it: the check must only look."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert oslayer.pid_alive(child.pid) is True
        time.sleep(0.2)
        assert child.poll() is None
    finally:
        child.kill()
        child.wait()


GRANDCHILD = textwrap.dedent("""
    import subprocess, sys, time
    grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    print(grandchild.pid, flush=True)
    time.sleep(120)
""")


def start_family():
    child = subprocess.Popen([sys.executable, "-c", GRANDCHILD], stdout=subprocess.PIPE, text=True, **oslayer.popen_group_kwargs())
    return child


def test_a_process_tree_ends_the_child_and_the_grandchild():
    child = start_family()
    tree = oslayer.ProcessTree(child)
    try:
        grandchild = int(child.stdout.readline())
        assert oslayer.pid_alive(child.pid) and oslayer.pid_alive(grandchild)
        tree.send(oslayer.SIGKILL)
        child.wait(timeout=20)
        assert wait_until(lambda: not oslayer.pid_alive(grandchild)), "the grandchild must not outlive the tree"
    finally:
        tree.close()
        child.kill()
        child.wait()


def test_a_process_tree_ends_a_grandchild_that_outlived_its_parent():
    """The no-orphans rule: after the child has gone, whatever it left behind is ended by the same call."""
    child = start_family()
    tree = oslayer.ProcessTree(child)
    try:
        grandchild = int(child.stdout.readline())
        child.kill()
        child.wait(timeout=20)
        assert oslayer.pid_alive(grandchild), "the grandchild is still there when its parent is gone"
        tree.send(oslayer.SIGKILL)
        assert wait_until(lambda: not oslayer.pid_alive(grandchild))
    finally:
        tree.close()


def test_kill_tree_ends_a_process_this_one_did_not_wrap():
    child = start_family()
    try:
        grandchild = int(child.stdout.readline())
        oslayer.kill_tree(child.pid)
        child.wait(timeout=20)
        assert wait_until(lambda: not oslayer.pid_alive(grandchild))
    finally:
        child.kill()
        child.wait()


def test_kill_tree_never_raises_for_a_process_that_is_not_there():
    oslayer.kill_tree(0)
    oslayer.kill_tree(-3)
    child = subprocess.Popen([sys.executable, "-c", "pass"], **oslayer.popen_group_kwargs())
    child.wait(timeout=30)
    oslayer.kill_tree(child.pid)


def test_process_command_names_the_interpreter_of_this_process():
    assert "python" in oslayer.process_command(os.getpid()).lower()
    assert oslayer.process_command(0) == ""


def test_popen_group_kwargs_start_a_new_session_or_a_new_group_without_a_console():
    kwargs = oslayer.popen_group_kwargs()
    if oslayer.IS_WINDOWS:
        assert kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP and kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
    else:
        assert kwargs == {"start_new_session": True}


def test_console_python_is_an_interpreter_that_exists():
    assert os.path.exists(oslayer.console_python())


def test_signal_names_cover_sigkill_on_every_system():
    assert oslayer.signal_name(2) == "SIGINT" and oslayer.signal_name(15) == "SIGTERM"
    assert oslayer.signal_name(oslayer.SIGKILL) == "SIGKILL"
    assert oslayer.signal_name(77) == "SIG77"


# ---------------------------------------------------------------- files

def test_replace_replaces_a_file_and_removes_the_source(tmp_path):
    source, target = tmp_path / "new", tmp_path / "old"
    source.write_text("new", encoding="utf-8")
    target.write_text("old", encoding="utf-8")
    oslayer.replace(source, target)
    assert target.read_text(encoding="utf-8") == "new" and not source.exists()


def test_replace_waits_out_a_refusal_on_windows_and_only_there(tmp_path, monkeypatch):
    source, target = tmp_path / "a", tmp_path / "b"
    source.write_text("1", encoding="utf-8")
    target.write_text("0", encoding="utf-8")
    real, calls = os.replace, {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(13, "in use by another handle")
        real(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    monkeypatch.setattr(oslayer, "IS_WINDOWS", True)
    oslayer.replace(source, target, delay=0)
    assert calls["n"] == 3 and target.read_text(encoding="utf-8") == "1"
    monkeypatch.setattr(oslayer, "IS_WINDOWS", False)
    calls["n"] = 0
    source.write_text("2", encoding="utf-8")
    with pytest.raises(PermissionError):
        oslayer.replace(source, target)
    assert calls["n"] == 1, "off Windows the first refusal is the answer"


def test_replace_gives_up_after_its_attempts_on_windows(tmp_path, monkeypatch):
    source, target = tmp_path / "a", tmp_path / "b"
    source.write_text("1", encoding="utf-8")
    monkeypatch.setattr(os, "replace", lambda src, dst: (_ for _ in ()).throw(PermissionError(13, "always in use")))
    monkeypatch.setattr(oslayer, "IS_WINDOWS", True)
    with pytest.raises(PermissionError):
        oslayer.replace(source, target, attempts=3, delay=0)


# ---------------------------------------------------------------- the console and the user

def test_setup_stdio_is_harmless_whatever_the_streams_are():
    oslayer.setup_stdio()


def test_user_token_is_safe_in_a_file_name():
    assert re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", oslayer.user_token())


def test_the_stop_request_file_round_trip(tmp_path):
    assert lock.stop_requested(tmp_path) is False
    path = lock.request_stop(tmp_path)
    assert path.name == lock.STOP_NAME and lock.stop_requested(tmp_path) is True
    lock.clear_stop(tmp_path)
    assert lock.stop_requested(tmp_path) is False
    lock.clear_stop(tmp_path)                 # clearing nothing is fine
