"""What changed in the owner's working folder while a run worked (D135): seen by the engine host with git, never by an agent.

    watch = FolderWatch.start(grant)      before the first message starts the work: the baseline, or None when there is nothing to read
    watch.finish(edit_now)                after the work, or its stop: {"files": [{path, status}], "more": n}, or None

The owner reads the list in the team's chat ("Files changed in your folder during this run"), so it has to be what git says and not what a builder wrote
in its report: a report that names a file nobody touched, or leaves out one that changed, is told apart from the folder by this list, which no agent
writes. The host compares `git status --porcelain` before and after; a file that was already changed before the run and changed again is told apart by a
fingerprint of its content (a status alone would be the same on both sides).

Nothing is said, and nothing is an error, when there is nothing to read: no folder, a folder that is not a git work tree (looked for BEFORE git runs:
on a Mac without the developer tools the `git` stub opens an installer dialog), git missing, slow or refusing the folder (a timeout, "dubious
ownership"), a status of more than MAX_ENTRIES entries, or an owner who allowed no change at either end (nothing could have changed).

The folder is only read: `git --no-optional-locks status` takes no lock and refreshes no index, `core.fsmonitor` is switched off (it is a command
the repository's own configuration names), no `GIT_*` variable of this process reaches it and no prompt can open.
"""
import hashlib
import os
import shutil
import stat
import subprocess
import sys
from typing import Optional

from sutra_app import oslayer

__all__ = ["FolderWatch", "snapshot", "changes_between", "status_word", "git_executable", "GIT_START_TIMEOUT_S", "GIT_END_TIMEOUT_S", "MAX_ENTRIES",
           "LISTED_MAX", "STATUS_WORDS"]

GIT_START_TIMEOUT_S = 10.0       # the baseline is taken before the first message: a slow repository delays the start, never more than this
GIT_END_TIMEOUT_S = 6.0          # the run is over (or being stopped): the list must not hold the end up
MAX_ENTRIES = 5000               # a status longer than this is not a change list anyone reads: nothing is said
HASH_FILE_MAX = 2_000_000        # a changed file up to this size is fingerprinted by its content; a bigger one by its size and time
HASH_TOTAL_MAX = 64_000_000      # content hashed in one snapshot, at most
LISTED_MAX = 100                 # files named in `deliverable.json`; the rest are counted
STATUS_WORDS = ("new", "modified", "deleted", "reverted")


def git_executable() -> Optional[str]:
    """The `git` to run, or None. On a Mac, Apple's stub in /usr/bin opens an installer dialog when the developer tools are missing, so it is only
    used once `xcode-select -p` says they are there."""
    exe = shutil.which("git")
    if exe is None:
        return None
    if sys.platform == "darwin" and os.path.realpath(exe) == "/usr/bin/git":
        try:
            done = subprocess.run(["xcode-select", "-p"], capture_output=True, timeout=5, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return None
        if done.returncode != 0:
            return None
    return exe


def _has_dot_git(folder: str) -> bool:
    """Is there a `.git` (folder or file: a worktree) at the folder or above it? Looked at before git is run."""
    here = os.path.realpath(folder)
    while True:
        if os.path.lexists(os.path.join(here, ".git")):
            return True
        up = os.path.dirname(here)
        if up == here:
            return False
        here = up


def _git(exe: str, folder: str, args: list, timeout: float) -> Optional[bytes]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C", "LANG": "C"})
    argv = [exe, "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.quotepath=off", "-C", folder, *args]
    try:
        done = subprocess.run(argv, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, env=env, **oslayer.hidden_window_kwargs())
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _fingerprint(root: str, rel: str, spent: list) -> str:
    """What a changed path holds now, as a short string: a link's target, the SHA-1 of a file's content (up to HASH_FILE_MAX, within HASH_TOTAL_MAX),
    else its size and time. A path that is not there is `gone`."""
    full = os.path.join(root, *rel.split("/"))
    try:
        if os.path.islink(full):
            return "link:" + os.readlink(full)
        info = os.stat(full)
    except OSError:
        return "gone"
    if not stat.S_ISREG(info.st_mode):
        return f"other:{info.st_mtime_ns}"
    if info.st_size <= HASH_FILE_MAX and spent[0] + info.st_size <= HASH_TOTAL_MAX:
        try:
            digest = hashlib.sha1()
            with open(full, "rb") as handle:
                for block in iter(lambda: handle.read(65536), b""):
                    digest.update(block)
            spent[0] += info.st_size
            return "sha1:" + digest.hexdigest()
        except OSError:
            pass
    return f"stat:{info.st_size}:{info.st_mtime_ns}"


def snapshot(exe: str, folder: str, timeout: float) -> Optional[dict]:
    """`{path relative to the folder: (status code, fingerprint)}` for every path `git status` reports below the folder, or None when git cannot say
    (not a work tree, a timeout, a refusal, more than MAX_ENTRIES paths). Untracked files are listed one by one; renames are not detected, so a
    rename is a deleted path and a new one."""
    top = _git(exe, folder, ["rev-parse", "--is-inside-work-tree", "--show-prefix"], timeout)
    if top is None:
        return None
    lines = top.decode("utf-8", "replace").split("\n")
    if lines[0].strip() != "true":
        return None
    prefix = lines[1].strip() if len(lines) > 1 else ""
    out = _git(exe, folder, ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames", "--", "."], timeout)
    if out is None:
        return None
    root, spent, found = os.path.realpath(folder), [0], {}
    for raw in out.split(b"\0"):
        if len(raw) < 4:
            continue
        if len(found) >= MAX_ENTRIES:
            return None
        code, path = raw[:2].decode("ascii", "replace"), raw[3:].decode("utf-8", "replace")
        rel = path[len(prefix):] if prefix and path.startswith(prefix) else path
        found[rel] = (code, _fingerprint(root, rel, spent))
    return found


def status_word(code: str) -> str:
    """The word for a two-letter porcelain code: deleted when either side says D, new for an untracked or added path, else modified."""
    if "D" in code:
        return "deleted"
    if code == "??" or "A" in code:
        return "new"
    return "modified"


def changes_between(before: dict, after: dict) -> list:
    """`[{path, status}]`, sorted by path, for every path whose entry is not the same in both snapshots. A path that was in the same state before the run
    (changed, or untracked) and holds other content now is `modified`; a path that is no longer listed was either an untracked file that is gone
    (`deleted`) or a changed file that is back to the committed content (`reverted`)."""
    rows = []
    for path in sorted(set(before) | set(after)):
        was, now = before.get(path), after.get(path)
        if was == now:
            continue
        if now is None:
            status = "deleted" if was is not None and was[0] == "??" else "reverted"
        elif was is not None and was[0] == now[0]:
            status = "modified"
        else:
            status = status_word(now[0])
        rows.append({"path": path, "status": status})
    return rows


class FolderWatch:
    """The baseline of one run. `start` returns None when there is nothing to read; `finish` is called once, after the work."""

    def __init__(self, folder: str, exe: str, before: dict, edit_at_start: bool) -> None:
        self.folder, self.exe, self.before, self.edit_at_start = folder, exe, before, edit_at_start

    @classmethod
    def start(cls, grant) -> Optional["FolderWatch"]:
        """`grant` is what `WorkFolder.grant()` gives (the folder with the owner's access), or None when no folder is set."""
        if not grant:
            return None
        folder = str(grant)
        if not _has_dot_git(folder):
            return None
        exe = git_executable()
        if exe is None:
            return None
        before = snapshot(exe, folder, GIT_START_TIMEOUT_S)
        if before is None:
            return None
        return cls(folder, exe, before, bool(getattr(grant, "edit", False)))

    def finish(self, edit_now: bool) -> Optional[dict]:
        """`{"files": [{path, status}], "more": n}` (at most LISTED_MAX files named), or None: the owner allowed no change at either end, or git cannot say
        now. An empty list is a true answer: git looked and nothing changed."""
        if not (self.edit_at_start or edit_now):
            return None
        after = snapshot(self.exe, self.folder, GIT_END_TIMEOUT_S)
        if after is None:
            return None
        rows = changes_between(self.before, after)
        return {"files": rows[:LISTED_MAX], "more": max(0, len(rows) - LISTED_MAX)}
