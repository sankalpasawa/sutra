"""The instance lock (GAP-OPS-1, D94): one server per data folder, a pid file the macOS launcher can read, no stale locks."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from sutra_app.ops import lock
from sutra_app.ops.lock import InstanceLock, is_locked, read_holder

REPO = Path(__file__).resolve().parents[2]


def test_acquire_takes_the_lock_and_writes_a_pid_file_the_launcher_can_read(tmp_path):
    held = InstanceLock(tmp_path, version="9.9.9")
    assert held.acquire() is True and held.held
    text = (tmp_path / "app.pid").read_text()
    first, second = text.splitlines()
    assert first == f"{os.getpid()} 0"                                   # the launcher's `read -r pid port` sees a pid and port 0
    assert json.loads(second) == {"pid": os.getpid(), "port": None, "started": json.loads(second)["started"], "version": "9.9.9"}
    held.update(8791)
    assert (tmp_path / "app.pid").read_text().splitlines()[0] == f"{os.getpid()} 8791"
    assert read_holder(tmp_path).port == 8791 and read_holder(tmp_path).url == "http://127.0.0.1:8791/"
    assert (tmp_path / "app.pid").stat().st_mode & 0o777 == 0o600 and (tmp_path / "app.lock").stat().st_mode & 0o777 == 0o600
    held.release()


def test_a_second_lock_on_the_same_folder_is_refused_and_can_see_who_holds_it(tmp_path):
    first = InstanceLock(tmp_path, version="1.0")
    assert first.acquire()
    first.update(8785)
    second = InstanceLock(tmp_path)
    assert second.acquire() is False and not second.held
    holder = second.holder()
    assert (holder.pid, holder.port, holder.version) == (os.getpid(), 8785, "1.0")
    first.release()


def test_release_frees_the_lock_and_removes_the_pid_file(tmp_path):
    first = InstanceLock(tmp_path)
    first.acquire()
    first.release()
    first.release()                                                       # twice is fine
    assert not (tmp_path / "app.pid").exists() and (tmp_path / "app.lock").exists() and not is_locked(tmp_path)
    again = InstanceLock(tmp_path)
    assert again.acquire()
    again.release()


def test_a_pid_file_without_a_lock_is_stale_and_is_replaced(tmp_path):
    (tmp_path / "app.pid").write_text("999999 8780\n")
    assert not is_locked(tmp_path)
    fresh = InstanceLock(tmp_path)
    assert fresh.acquire()
    assert read_holder(tmp_path).pid == os.getpid()
    fresh.release()


def test_release_leaves_a_pid_file_that_the_launcher_rewrote(tmp_path):
    held = InstanceLock(tmp_path)
    held.acquire()
    (tmp_path / "app.pid").write_text("4242 8780\n")                      # the launcher writes its own pid and the port, one line
    assert read_holder(tmp_path).pid == 4242 and read_holder(tmp_path).started is None
    held.release()
    assert (tmp_path / "app.pid").read_text() == "4242 8780\n"


@pytest.mark.parametrize("content", ["", "\n", "abc 8780\n", "-5 8780\n", "0 1\n"])
def test_an_unreadable_pid_file_is_no_holder(tmp_path, content):
    (tmp_path / "app.pid").write_text(content)
    assert read_holder(tmp_path) is None


def test_a_port_out_of_range_is_no_port_and_bad_json_is_ignored(tmp_path):
    (tmp_path / "app.pid").write_text("77 70000\n{not json\n")
    holder = read_holder(tmp_path)
    assert (holder.pid, holder.port, holder.started, holder.version, holder.url) == (77, None, None, None, None)
    for text, port in (("77 65536\n", None), ("77 65535\n", 65535), ("77 0\n", None)):
        (tmp_path / "app.pid").write_text(text)
        assert read_holder(tmp_path).port == port
    (tmp_path / "app.pid").write_text('77 8780\n{"started": true, "version": 5}\n')
    holder = read_holder(tmp_path)
    assert holder.started is None and holder.version is None            # wrong types are dropped, not trusted


def test_holder_waits_for_the_pid_file_of_a_server_that_is_still_starting(tmp_path):
    assert InstanceLock(tmp_path).holder(wait=0) is None
    started = time.monotonic()
    assert InstanceLock(tmp_path).holder(wait=0.2) is None
    assert time.monotonic() - started >= 0.15


def test_update_needs_the_lock_and_the_context_manager_refuses_a_held_folder(tmp_path):
    with pytest.raises(RuntimeError, match="not held"):
        InstanceLock(tmp_path).update(8780)
    with InstanceLock(tmp_path) as held:
        assert held.held
        with pytest.raises(RuntimeError, match="another Sutra Pro"):
            with InstanceLock(tmp_path):
                pass                                                      # pragma: no cover
    assert not is_locked(tmp_path)


def test_is_locked_is_false_for_a_folder_that_never_had_a_lock(tmp_path):
    assert is_locked(tmp_path) is False and is_locked(tmp_path / "missing") is False


def test_another_process_holds_the_lock_and_a_crash_frees_it(tmp_path):
    code = ("import sys, time; from sutra_app.ops.lock import InstanceLock; l = InstanceLock(sys.argv[1]); assert l.acquire(); l.update(8799); "
            "print('held', flush=True); time.sleep(60)")
    child = subprocess.Popen([str(REPO / "scripts" / "py"), "-c", code, str(tmp_path)], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "held"
        assert is_locked(tmp_path) is True
        assert InstanceLock(tmp_path).acquire() is False
        assert read_holder(tmp_path).port == 8799
        os.kill(child.pid, signal.SIGKILL)                                # no clean release: the kernel drops the lock
        child.wait(timeout=10)
        assert is_locked(tmp_path) is False
        fresh = InstanceLock(tmp_path)
        assert fresh.acquire()
        fresh.release()
    finally:
        if child.poll() is None:
            child.kill()
        child.stdout.close()


def test_pid_alive():
    assert lock.pid_alive(os.getpid()) and not lock.pid_alive(0) and not lock.pid_alive(-3)
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    assert not lock.pid_alive(gone.pid)
