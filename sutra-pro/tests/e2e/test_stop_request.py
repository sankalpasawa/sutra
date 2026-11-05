"""A stop request (D101): the file `app.stop` and the `sutra-pro stop` command end a REAL server, on every system.

On Windows a server with no console cannot be signalled, so `sutra-pro stop` writes `<data>/app.stop` and the server, which polls
for it, shuts down the way a SIGTERM would. The file works everywhere, so this test drives it on every system; the command is driven
too, through whichever way the system it runs on takes (SIGTERM on POSIX, the file on Windows).

The desktop app (D107) ends its server a third way: it holds the write end of the server's standard input, and `--exit-when-stdin-closes`
makes the server stop when that pipe closes, so a killed app cannot leave a server running.
"""
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

import pytest
from harness import REPO

from sutra_app import oslayer
from sutra_app.ops import lock

STOP_WITHIN_S = 30


class Running:
    def __init__(self, data_dir, *, args=(), stdin=None) -> None:
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("SUTRA_", "J2_", "STUDIO_"))}
        self.env.update({"SUTRA_DATA_DIR": str(data_dir), "SUTRA_ENV_FILE": str(data_dir.parent / "none.env"), "PYTHONUTF8": "1"})
        self.data_dir = data_dir
        self.lines: list[str] = []
        self.proc = subprocess.Popen([sys.executable, "-m", "sutra_app", "--offline", "--no-browser", "--port", "0", *args], cwd=str(REPO),
                                     env=self.env, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                     **oslayer.popen_group_kwargs())
        threading.Thread(target=self._read, daemon=True).start()
        self.base = self._wait_for_url()

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.append(line.rstrip())

    def _wait_for_url(self) -> str:
        end = time.time() + 90
        while time.time() < end:
            for line in self.lines:
                found = re.search(r"running at (http://127\.0\.0\.1:\d+)/", line)
                if found:
                    return found.group(1)
            if self.proc.poll() is not None:
                pytest.fail("the server exited early:\n" + "\n".join(self.lines))
            time.sleep(0.05)
        pytest.fail("the server did not announce its address:\n" + "\n".join(self.lines))

    def health(self) -> bool:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(self.base + "/api/health", timeout=20) as response:
            return response.status == 200

    def finish(self) -> None:
        if self.proc.poll() is None:
            oslayer.kill_tree(self.proc.pid)
            self.proc.wait(timeout=20)


@pytest.fixture
def running(tmp_path):
    box = Running(tmp_path / "data")
    yield box
    box.finish()


def test_the_stop_file_ends_a_real_server_cleanly(running):
    assert running.health()
    holder = lock.read_holder(running.data_dir)
    # on Windows the pid of the process we started is a venv launcher: the server is its child, and the pid file names the server
    assert holder is not None and (oslayer.IS_WINDOWS or holder.pid == running.proc.pid) and lock.is_locked(running.data_dir)
    lock.request_stop(running.data_dir)
    assert running.proc.wait(timeout=STOP_WITHIN_S) == 0, "\n".join(running.lines)
    assert not lock.is_locked(running.data_dir), "the instance lock went with the server"
    assert not lock.stop_requested(running.data_dir), "the server answered the request and removed it"
    assert not (running.data_dir / lock.PID_NAME).exists(), "the pid file is removed by the server that wrote it"


def test_a_stop_request_left_by_a_crash_does_not_stop_the_next_server(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    lock.request_stop(data)
    box = Running(data)
    try:
        time.sleep(1.5)                                  # three polls of the stop file
        assert box.proc.poll() is None, "a stale app.stop must be cleared at start, not obeyed"
        assert box.health()
    finally:
        box.finish()


def test_the_stop_command_ends_a_real_server(running):
    done = subprocess.run([sys.executable, "-m", "sutra_app", "stop", "--data-dir", str(running.data_dir), "--wait", "30"], cwd=str(REPO),
                          env=running.env, capture_output=True, text=True, encoding="utf-8", timeout=90)
    assert done.returncode == 0, done.stdout + done.stderr
    assert running.proc.wait(timeout=STOP_WITHIN_S) is not None
    assert not lock.is_locked(running.data_dir)


def test_closing_standard_input_ends_a_server_that_was_asked_to_watch_it(tmp_path):
    box = Running(tmp_path / "data", args=("--exit-when-stdin-closes",), stdin=subprocess.PIPE)
    try:
        assert box.health()
        assert box.proc.poll() is None, "an open input keeps the server running"
        box.proc.stdin.close()                           # what the desktop app's death does: the write end of the pipe goes away
        assert box.proc.wait(timeout=STOP_WITHIN_S) == 0, "\n".join(box.lines)
        assert not lock.is_locked(box.data_dir), "the instance lock went with the server"
        assert not (box.data_dir / lock.PID_NAME).exists(), "the pid file is removed by the server that wrote it"
    finally:
        box.finish()


def test_a_server_that_was_not_asked_to_watch_standard_input_ignores_its_closing(tmp_path):
    box = Running(tmp_path / "data", stdin=subprocess.PIPE)
    try:
        assert box.health()
        box.proc.stdin.close()
        time.sleep(2.5)                                  # the watcher, had it been asked for, answers within a second
        assert box.proc.poll() is None and box.health(), "the flag, not a pipe, is what makes a server follow its starter"
    finally:
        box.finish()
