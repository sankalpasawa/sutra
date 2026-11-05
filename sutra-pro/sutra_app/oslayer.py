"""The few places where Windows and POSIX differ, in one module (D101).

Everything else in the app is written once. What cannot be is here, behind names that mean the same thing on both systems:

    try_lock(fd) / unlock(fd)       an exclusive lock on an open file, without waiting          flock / msvcrt.locking
    pid_alive(pid)                  is there a process with this id                            kill(pid, 0) / OpenProcess
    process_command(pid)            its command line (the identity check of a start-up pass)   ps / PowerShell
    popen_group_kwargs()            start a child as the leader of its own process group       new session / new group, no console
    ProcessTree(popen)              end a child and everything it started                      killpg / a job object
    kill_tree(pid)                  the same for a process this one did not start              killpg / taskkill /T /F
    replace(src, dst)               os.replace that waits out a reader on Windows              os.replace / a short retry loop
    O_BINARY                        add to os.open flags that write data: Windows would turn \\n into \\r\\n
    setup_stdio()                   stdout and stderr that never raise on a character the code page lacks
    user_token()                    a short name for the current user, safe in a file name

Not here: the server's own shutdown request (`ops.lock` keeps the stop file) and the browser (`ops.browser`).

POSIX behaviour is what the code did before this module existed: every function below takes the POSIX branch with the same calls.
The Windows branches are proved by `tests/ops/test_oslayer.py`, which the Windows leg of the CI runs for real.
"""
from __future__ import annotations

import contextlib
import functools
import os
import re
import signal
import subprocess
import sys
import time
from typing import Any

__all__ = ["console_python", "IS_WINDOWS", "O_BINARY", "SIGKILL", "try_lock", "unlock", "pid_alive", "process_command", "popen_group_kwargs",
           "hidden_window_kwargs", "ProcessTree", "kill_tree", "replace", "setup_stdio", "user_token", "signal_name"]

IS_WINDOWS = os.name == "nt"
O_BINARY: int = getattr(os, "O_BINARY", 0)          # 0 on POSIX: OR-ing it in changes nothing there
SIGKILL: int = getattr(signal, "SIGKILL", 9)        # Windows has no SIGKILL; 9 is only a name for "end it now"

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)


def console_python() -> str:
    """The interpreter to start a helper with. Windows: the console `python.exe` next to a windowless `pythonw.exe` (or the renamed
    copy of it that the installed app runs as), because a helper's output goes to files and a console-less interpreter has no
    standard streams of its own. Elsewhere: `sys.executable`."""
    if IS_WINDOWS:
        sibling = os.path.join(os.path.dirname(sys.executable), "python.exe")
        if os.path.exists(sibling):
            return sibling
    return sys.executable


# ---- signals by name --------------------------------------------------------------------------------------------------------------

def signal_name(sig: int) -> str:
    """`SIGINT`, `SIGTERM`, `SIGKILL` ... for a signal number, on any system (Windows' `signal.Signals` has no SIGKILL)."""
    try:
        return signal.Signals(sig).name
    except ValueError:
        return "SIGKILL" if sig == 9 else f"SIG{sig}"


# ---- file locks ----------------------------------------------------------------------------------------------------------------------

if IS_WINDOWS:
    import msvcrt

    def try_lock(fd: int) -> bool:
        """Take an exclusive lock on an open file without waiting. False when another handle (this process's too) holds it."""
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)          # byte 0 only: nothing ever reads or writes a lock file
        except OSError:
            return False
        return True

    def unlock(fd: int) -> None:
        with contextlib.suppress(OSError):
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def try_lock(fd: int) -> bool:
        """Take an exclusive lock on an open file without waiting. False when another open file description holds it."""
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def unlock(fd: int) -> None:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)


# ---- the Windows API, only where there is one ---------------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _kernel32() -> Any:
    """kernel32 with the argument and result types set. Without them ctypes passes a 64-bit handle as a 32-bit int."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.GetExitCodeProcess.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.TerminateJobObject.restype = wintypes.BOOL
    return k32


def _pid_alive_windows(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes
    process_query_limited_information, still_active, error_access_denied = 0x1000, 259, 5
    if pid > 0xFFFFFFFF:
        return False                                                  # not a DWORD, so not a process id
    k32 = _kernel32()
    handle = k32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return ctypes.get_last_error() == error_access_denied        # it exists, it is only not ours to look at
    try:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == still_active
    finally:
        k32.CloseHandle(handle)


def pid_alive(pid: int) -> bool:
    """Is there a process with this id? Never signals it: on Windows `os.kill(pid, 0)` would END the process, so it is not used there."""
    if pid <= 0:
        return False
    if IS_WINDOWS:
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def hidden_window_kwargs() -> dict[str, Any]:
    """`subprocess` arguments that keep a console window from flashing up when a helper runs (Windows only; empty elsewhere)."""
    return {"creationflags": _CREATE_NO_WINDOW} if IS_WINDOWS else {}


def process_command(pid: int) -> str:
    """The command line of a process, or "" when there is none or it cannot be read (the identity check of a start-up pass)."""
    if pid < 1:
        return ""
    if IS_WINDOWS:
        script = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"
        argv, timeout = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], 20
    else:
        argv, timeout = ["ps", "-p", str(pid), "-o", "command="], 5
    try:
        done = subprocess.run(argv, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, **hidden_window_kwargs())
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.decode("utf-8", "replace").strip() if done.returncode == 0 else ""


# ---- process groups and trees ---------------------------------------------------------------------------------------------------

def popen_group_kwargs() -> dict[str, Any]:
    """`Popen` arguments that make the child the leader of its own process group, so one signal reaches it and what it starts.
    POSIX: a new session. Windows: a new process group and no console window of its own."""
    if IS_WINDOWS:
        return {"creationflags": _CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW}
    return {"start_new_session": True}


def kill_tree(pid: int) -> None:
    """End a process and everything it started, forcefully, for a process this one did not start (a `ProcessTree` does the same
    for a child it did). Never raises."""
    if pid < 1:
        return
    if IS_WINDOWS:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], capture_output=True, timeout=20,
                           stdin=subprocess.DEVNULL, **hidden_window_kwargs())
        return
    with contextlib.suppress(OSError):
        os.killpg(os.getpgid(pid), SIGKILL)


class ProcessTree:
    """Everything one started child starts, so that it can be ended together: `send(SIGINT | SIGTERM | SIGKILL)`.

    POSIX: the child was started with `popen_group_kwargs()`, a session leader, so its pid is the id of its process group and the
    signal goes to the group. Windows: the child is put into a job object right after it is created, and the job holds every
    process it starts from then on; ending the job ends them all, even those whose parent is already gone. SIGINT is a
    Ctrl+Break to the child's group (it only arrives when the child has a console, which a hidden one does not),
    SIGTERM is TerminateProcess on the child, SIGKILL is TerminateJobObject on the whole tree."""

    def __init__(self, popen: subprocess.Popen) -> None:
        self._popen = popen
        self._job: Any = _make_job(popen) if IS_WINDOWS else None

    def send(self, sig: int) -> None:
        if not IS_WINDOWS:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(self._popen.pid, sig)
            return
        if sig == signal.SIGINT:
            with contextlib.suppress(OSError, ValueError):
                self._popen.send_signal(signal.CTRL_BREAK_EVENT)         # type: ignore[attr-defined]
        elif sig == signal.SIGTERM:
            with contextlib.suppress(OSError):
                self._popen.terminate()
        else:
            self._kill_everything()

    def _kill_everything(self) -> None:
        if self._job is not None:
            _kernel32().TerminateJobObject(self._job, 1)
        else:
            kill_tree(self._popen.pid)
        with contextlib.suppress(OSError):
            self._popen.kill()

    def close(self) -> None:
        """Let go of the job object. Whatever is still in it ends now (the job kills its processes when its last handle closes)."""
        job, self._job = self._job, None
        if job is not None:
            _kernel32().CloseHandle(job)


def _make_job(popen: subprocess.Popen) -> Any:
    """A job object that ends its processes when closed, holding `popen`; None when Windows refuses (the tree is then ended with taskkill)."""
    import ctypes
    k32 = _kernel32()
    job_object_extended_limit_information, kill_on_job_close = 9, 0x2000

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                              "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32), ("SchedulingClass", ctypes.c_uint32)]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    job = k32.CreateJobObjectW(None, None)
    if not job:
        return None
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = kill_on_job_close
    if not k32.SetInformationJobObject(job, job_object_extended_limit_information, ctypes.byref(limits), ctypes.sizeof(limits)):
        k32.CloseHandle(job)
        return None
    if not k32.AssignProcessToJobObject(job, int(popen._handle)):             # type: ignore[attr-defined]
        k32.CloseHandle(job)
        return None
    return job


# ---- files ---------------------------------------------------------------------------------------------------------------------------

def replace(src: str | os.PathLike[str], dst: str | os.PathLike[str], *, attempts: int = 40, delay: float = 0.025) -> None:
    """`os.replace`. Windows refuses to replace a file that another handle has open (a reader polling it), so there a
    PermissionError is waited out for about a second before it is allowed to propagate. POSIX: exactly `os.replace`."""
    if not IS_WINDOWS:
        os.replace(src, dst)
        return
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


# ---- the console and the user ----------------------------------------------------------------------------------------------------

def setup_stdio() -> None:
    """On Windows, make stdout and stderr UTF-8 with replacement: a console or a pipe is in a legacy code page by default, and a
    message with an arrow in it would raise UnicodeEncodeError. A stream that is None (no console) is left alone."""
    if not IS_WINDOWS:
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8", errors="replace")


def user_token() -> str:
    """The numeric user id on POSIX, the sanitized account name on Windows: something short that is safe in a file name."""
    getuid = getattr(os, "getuid", None)
    if getuid is not None:
        return str(getuid())
    import getpass
    return re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser() or "user")[:40] or "user"
