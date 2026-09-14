#!/usr/bin/env python3
"""Overlap-lock tests for the routine runner.

WHY THIS EXISTS. One routine (observability-synthesis-3h) skipped 279 fires in
a row, 2026-08-07 to 2026-09-14, because a runner older than the try/finally
guard died holding ~/.sutra-ui/runs/<id>/.lock and nothing ever asked whether
the holder was still alive. The lock now carries its holder's pid: a dead pid,
or a pid-less lock older than STALE_AFTER, is cleared and the run re-acquires
under a lock it created itself. A live pid on a fresh lock still skips.

These tests exec the shipped _RUNNER literal (minus its trailing main() call)
so they exercise the code launchd runs, not a re-typed copy.

Run: python3 test_routine_lock.py   (or pytest, from this folder)
"""
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def load_runner():
    src = open(os.path.join(HERE, "routines.py"), encoding="utf-8").read()
    m = re.search(r"_RUNNER = r'''(.*?)'''", src, re.S)
    assert m, "could not locate the _RUNNER literal"
    body = m.group(1).rstrip()
    assert body.endswith("main()"), "runner no longer ends with main() -- update this test"
    body = body[: -len("main()")]
    ns = {"__name__": "routine_runner_under_test"}
    exec(compile(body, "run-routine.py", "exec"), ns)
    return ns


R = load_runner()


def dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def make_lock(tmp, pid=None, age=0):
    lock = os.path.join(tmp, ".lock")
    os.mkdir(lock)
    if pid is not None:
        with open(os.path.join(lock, "pid"), "w") as fh:
            fh.write(str(pid))
    if age:
        t = time.time() - age
        os.utime(lock, (t, t))
    return lock


def test_fresh_acquire_writes_pid_and_release_removes_both():
    with tempfile.TemporaryDirectory() as tmp:
        lock = os.path.join(tmp, ".lock")
        ok, stale = R["acquire_lock"](lock)
        assert ok and stale is None
        assert open(os.path.join(lock, "pid")).read() == str(os.getpid())
        R["release_lock"](lock)
        assert not os.path.exists(lock), "pid file must go before rmdir, or the lock outlives the run"


def test_live_pid_fresh_lock_skips():
    with tempfile.TemporaryDirectory() as tmp:
        lock = make_lock(tmp, pid=os.getpid())
        assert R["acquire_lock"](lock) == (False, None)
        assert os.path.isdir(lock)


def test_dead_pid_is_cleared_and_reacquired():
    with tempfile.TemporaryDirectory() as tmp:
        lock = make_lock(tmp, pid=dead_pid())
        ok, stale = R["acquire_lock"](lock)
        assert ok and "is gone" in stale
        assert open(os.path.join(lock, "pid")).read() == str(os.getpid())


def test_missing_pid_fresh_lock_is_live():
    with tempfile.TemporaryDirectory() as tmp:
        lock = make_lock(tmp)
        assert R["acquire_lock"](lock) == (False, None)


def test_missing_pid_old_lock_is_stale():
    with tempfile.TemporaryDirectory() as tmp:
        lock = make_lock(tmp, age=R["STALE_AFTER"] + 60)
        ok, stale = R["acquire_lock"](lock)
        assert ok and "no holder pid" in stale


def test_bad_pid_values_are_safe():
    with tempfile.TemporaryDirectory() as tmp:
        for bad in ("0", "-1", "garbage"):
            lock = make_lock(tmp, pid=bad)
            assert R["acquire_lock"](lock) == (False, None), bad
            os.utime(lock, (1, 1))
            ok, stale = R["acquire_lock"](lock)
            assert ok and "no holder pid" in stale, bad
            R["release_lock"](lock)


def test_live_pid_but_ancient_lock_is_pid_reuse():
    with tempfile.TemporaryDirectory() as tmp:
        lock = make_lock(tmp, pid=os.getpid(), age=R["STALE_AFTER"] + 60)
        ok, stale = R["acquire_lock"](lock)
        assert ok and "reused" in stale


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok   " + name)
            except AssertionError as e:
                fails += 1
                print("FAIL " + name + ": " + str(e))
    sys.exit(1 if fails else 0)
