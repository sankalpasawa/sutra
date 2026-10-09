"""Each task works in its OWN COPY of the project (founder, 2026-10-08, from
Paperclip; option B: "auto-keep when the checks pass").

WHY. Every worker used to run in the founder's own folder -- which, for the
main use of Shadow, is the Sutra repo the app itself runs from. Two tasks at
once edited the same files, a half-done step could break the running app, the
work mixed with the founder's own uncommitted edits, and the checker could
look in a different folder from the one the worker wrote to.

WHAT. When a task's worker is about to start and the project is a git repo:

  1. SNAPSHOT the founder's folder as it is NOW -- `git stash create` takes
     the uncommitted edits without touching the working tree, the index or
     the stash list; untracked files that are not ignored are copied in.
  2. A git WORKTREE of that snapshot under the shadow home (never inside the
     project, never on a synced drive), committed as the task's BASE.
  3. The worker runs there, and the task's checks read there
     (mission["workdir"], which shadow_paths.mission_artifact_root honours).
  4. At the end: a task that FINISHED (its checks passed) is KEPT
     automatically -- its changes since BASE are applied to the founder's
     folder. If they do not apply cleanly (the founder changed the same
     lines), or the task did not finish, the founder decides: Keep or Throw
     away. Keeping and throwing away both remove the copy.

MEASURED 2026-10-08 on the Sutra repo (18.6k files, Windows): snapshot 3.7s,
worktree ~100s, untracked copy 4s. A plain `git apply` fails on files the
founder's checkout has with CRLF endings; `--ignore-whitespace` applies them.

NEVER IN THE WAY. If anything here fails, the task runs in the shared folder
exactly as it always did, and the ledger says why. Off switch: the task-limits
key `task_copies: false`, or SUTRA_SHADOW_TASK_COPIES=0.
"""
import os
import shutil
import subprocess
import threading
import time

import shadow_ledger

#: one copy of untracked files is skipped past this, so a stray build
#: artefact cannot turn a task start into a multi-gigabyte copy
UNTRACKED_FILE_MAX = 20 * 1024 * 1024
UNTRACKED_TOTAL_MAX = 200 * 1024 * 1024
GIT_TIMEOUT_S = 600
_IDENT = ["-c", "user.name=Shadow", "-c", "user.email=shadow@sutra.local",
          "-c", "commit.gpgsign=false"]
#: one keep at a time into the founder's folder
_APPLY_LOCK = threading.Lock()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def enabled():
    if os.environ.get("SUTRA_SHADOW_TASK_COPIES", "").strip() == "0":
        return False
    try:
        import mission_engine
        return mission_engine._read_limits().get("task_copies", True) \
            is not False
    except Exception:                    # noqa: BLE001 -- default on
        return True


def _git(args, cwd, timeout=GIT_TIMEOUT_S, data=None):
    """(code, stdout text, stderr text). Never raises."""
    try:
        p = subprocess.run(["git"] + list(args), cwd=cwd, input=data,
                           capture_output=True, timeout=timeout)
    except Exception as exc:             # noqa: BLE001
        return 1, "", str(exc)
    return (p.returncode, p.stdout.decode("utf-8", "replace").strip(),
            p.stderr.decode("utf-8", "replace").strip())


def toplevel(path):
    """The git repo `path` is inside, or None."""
    if not path or not os.path.isdir(path):
        return None
    code, out, _e = _git(["rev-parse", "--show-toplevel"], path, timeout=30)
    return os.path.realpath(out) if code == 0 and out else None


def copies_dir():
    return os.path.join(os.path.realpath(shadow_ledger.shadow_home()),
                        "worktrees")


def _branch(mid):
    return "shadow/" + str(mid)


def _note(mid, text):
    try:
        shadow_ledger.append("missions", {"mission_id": mid,
                                          "note": "workspace: " + text[:300]})
    except Exception:                    # noqa: BLE001
        pass


def prepare(mission, base_dir):
    """Make (or reuse) the task's copy. Returns the workspace record, or None
    when the task should run in `base_dir` as before. Never raises."""
    mid = (mission or {}).get("id")
    ws = (mission or {}).get("workspace") or {}
    if ws.get("state") == "active" and ws.get("cwd") \
            and os.path.isdir(ws["cwd"]):
        return ws                         # a restart or a released hold
    if not mid or not enabled():
        return None
    top = toplevel(base_dir)
    if not top:
        return None                       # not a git project: shared folder
    rel = os.path.relpath(os.path.realpath(base_dir), top)
    dest = os.path.join(copies_dir(), mid)
    try:
        os.makedirs(copies_dir(), exist_ok=True)
        if os.path.exists(dest):
            _git(["worktree", "remove", "--force", dest], top)
            shutil.rmtree(dest, ignore_errors=True)
        _git(["worktree", "prune"], top)
        code, snap, _e = _git(["stash", "create"], top)
        if code != 0:
            snap = ""
        code, head, err = _git(["rev-parse", "HEAD"], top)
        if code != 0:
            _note(mid, "no commit to start from (%s)" % err)
            return None
        _git(["branch", "-D", _branch(mid)], top)
        code, _o, err = _git(["worktree", "add", "-b", _branch(mid), dest,
                              snap or head], top)
        if code != 0:
            _note(mid, "could not make the copy (%s)" % err)
            return None
        # untracked, not ignored: the founder's new files are part of "now"
        code, others, _e = _git(["ls-files", "--others", "--exclude-standard",
                                 "-z"], top)
        total, skipped = 0, []
        for f in (others.split("\0") if code == 0 else []):
            src = os.path.join(top, f)
            if not f or not os.path.isfile(src):
                continue
            size = os.path.getsize(src)
            if size > UNTRACKED_FILE_MAX or total + size > UNTRACKED_TOTAL_MAX:
                skipped.append(f)
                continue
            total += size
            dst = os.path.join(dest, f)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        _git(["add", "-A"], dest)
        code, _o, err = _git(_IDENT + ["commit", "-q", "--allow-empty",
                                       "--no-verify", "-m",
                                       "shadow: the task's starting point"],
                             dest)
        if code != 0:
            _note(mid, "could not record the starting point (%s)" % err)
            discard({"repo": top, "path": dest, "branch": _branch(mid)})
            return None
        code, base, _e = _git(["rev-parse", "HEAD"], dest)
        cwd = os.path.normpath(os.path.join(dest, rel))
        os.makedirs(cwd, exist_ok=True)
        rec = {"state": "active", "repo": top, "path": dest, "cwd": cwd,
               "base_dir": os.path.realpath(base_dir),
               "branch": _branch(mid), "base": base, "created_at": _now(),
               "skipped_untracked": skipped[:20]}
        _note(mid, "own copy at %s" % cwd)
        return rec
    except Exception as exc:              # noqa: BLE001 -- see docstring
        _note(mid, "copy failed, using the shared folder (%s)" % exc)
        try:
            discard({"repo": top, "path": dest, "branch": _branch(mid)})
        except Exception:                 # noqa: BLE001
            pass
        return None


def changes(ws):
    """(files, patch bytes): what the task changed since its starting point."""
    if not ws or not ws.get("path") or not os.path.isdir(ws["path"]):
        return [], b""
    _git(["add", "-A"], ws["path"])
    code, names, _e = _git(["diff", "--cached", "--name-only", ws["base"]],
                           ws["path"])
    files = [n for n in names.splitlines() if n.strip()] if code == 0 else []
    if not files:
        return [], b""
    try:
        p = subprocess.run(["git", "diff", "--cached", "--binary", ws["base"]],
                           cwd=ws["path"], capture_output=True,
                           timeout=GIT_TIMEOUT_S)
        return files, p.stdout
    except Exception:                    # noqa: BLE001
        return files, b""


def keep(ws):
    """Apply the task's changes to the founder's folder. Returns
    {"ok", "files", "error"}; on a clash nothing is applied at all."""
    files, patch = changes(ws)
    if not files:
        return {"ok": True, "files": [], "error": ""}
    if not patch:
        return {"ok": False, "files": files, "error": "could not read the changes"}
    flags = ["--binary", "--ignore-whitespace", "--whitespace=nowarn"]
    with _APPLY_LOCK:
        code, _o, err = _git(["apply", "--check"] + flags + ["-"],
                             ws["repo"], data=patch)
        if code != 0:
            return {"ok": False, "files": files, "error": err[:600]}
        code, _o, err = _git(["apply"] + flags + ["-"], ws["repo"], data=patch)
    if code != 0:
        return {"ok": False, "files": files, "error": err[:600]}
    return {"ok": True, "files": files, "error": ""}


def discard(ws):
    """Remove the copy and its branch. Never raises."""
    if not ws:
        return False
    repo, path = ws.get("repo"), ws.get("path")
    if repo and path:
        _git(["worktree", "remove", "--force", path], repo)
    if path and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    if repo:
        _git(["worktree", "prune"], repo)
        if ws.get("branch"):
            _git(["branch", "-D", ws["branch"]], repo)
    return True


def note_for_worker(ws):
    """The line the worker reads first, so an absolute path in the task never
    sends it back into the founder's folder."""
    if not ws or ws.get("state") != "active":
        return ""
    return ("[Where you work] This task has its own copy of the project at "
            "%s. Make every change there -- never in %s, which is the "
            "founder's own folder. Paths in the task that point at the "
            "founder's folder mean the same file in your copy.]\n\n"
            % (ws["cwd"], ws.get("base_dir") or ws.get("repo")))


# ------------------------------------------------------- the task's end ---
def _update(mid, fn):
    """load -> fn(m) -> save, retried on a concurrent write."""
    import mission_engine
    store = mission_engine.MissionStore()
    for _ in range(5):
        m = store.load(mid)
        if m is None:
            return None
        fn(m)
        try:
            store.save(m)
            return m
        except ValueError:
            continue
    return None


def finish(mid):
    """Called once a task has ended. FINISHED (done): kept automatically,
    unless it clashes. Otherwise: nothing changed -> the copy goes; something
    changed -> the founder decides. Never raises; returns the record."""
    import mission_engine
    try:
        m = mission_engine.MissionStore().load(mid)
    except Exception:                    # noqa: BLE001
        return None
    ws = (m or {}).get("workspace") or {}
    if not m or ws.get("state") != "active" \
            or m.get("state") not in mission_engine.TERMINAL:
        return ws or None
    files, _p = changes(ws)
    if not files:
        discard(ws)
        out = dict(ws, state="empty", files=[], ended_at=_now())
    elif m["state"] == "done":
        got = keep(ws)
        if got["ok"]:
            discard(ws)
            out = dict(ws, state="kept", files=got["files"], ended_at=_now(),
                       kept_by="auto")
        else:
            out = dict(ws, state="clash", files=got["files"],
                       error=got["error"], ended_at=_now())
    else:
        out = dict(ws, state="pending", files=files, ended_at=_now())
    _update(mid, lambda mm: mm.__setitem__("workspace", out))
    _note(mid, "%s (%d file%s)" % (out["state"], len(out.get("files") or []),
                                   "" if len(out.get("files") or []) == 1
                                   else "s"))
    return out


def decide(mid, action):
    """The founder's Keep / Throw away on a pending or clashing copy.
    Returns the new record; raises ValueError when there is nothing to
    decide."""
    import mission_engine
    m = mission_engine.MissionStore().load(mid)
    ws = (m or {}).get("workspace") or {}
    if ws.get("state") not in ("pending", "clash"):
        raise ValueError("there is no copy waiting for you on this task")
    if action == "discard":
        discard(ws)
        out = dict(ws, state="discarded", decided_at=_now())
    elif action == "keep":
        got = keep(ws)
        if got["ok"]:
            discard(ws)
            out = dict(ws, state="kept", files=got["files"],
                       decided_at=_now(), kept_by="founder")
        else:
            out = dict(ws, state="clash", files=got["files"],
                       error=got["error"], decided_at=_now())
    else:
        raise ValueError("keep or discard")
    _update(mid, lambda mm: mm.__setitem__("workspace", out))
    _note(mid, "founder: %s -> %s" % (action, out["state"]))
    return out


def sweep():
    """Boot: a task that ended while the app was down still gets its end."""
    import mission_engine
    done = []
    try:
        for m in mission_engine.MissionStore().list(
                states=mission_engine.TERMINAL):
            if ((m.get("workspace") or {}).get("state")) == "active":
                finish(m["id"])
                done.append(m["id"])
    except Exception:                    # noqa: BLE001
        pass
    return done
