"""Output and state files: safe directory chain, JSONL append with de-duplication, history state, purge.

Files 0600, directories 0700, set explicitly (umask not relied on). A symlink at the mailbox dir, output file
or history file is refused with unsafe_path (FR-21).
"""
import errno
import fcntl
import json
import os
import re
import stat
import tempfile
from datetime import date
from pathlib import Path

from errors import PulseError
from policy import MAILBOX_RE


def _unsafe(path) -> PulseError:
    return PulseError("unsafe_path", f"Refused: {path} is a symlink or not a regular path. Nothing was written there.")


def _ensure_dir(p: Path) -> None:
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        try:
            os.mkdir(p, 0o700)
        except FileExistsError:
            st = os.lstat(p)
        else:
            os.chmod(p, 0o700)
            return
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise _unsafe(p)


def mailbox_dir(out_dir, mailbox: str, mock: bool) -> Path:
    """<out_dir>[/_mock]/<mailbox>, created 0700. The configured out_dir itself may be anywhere the user chose."""
    out_dir = Path(out_dir)
    os.makedirs(out_dir, mode=0o700, exist_ok=True)
    d = out_dir
    for part in (["_mock"] if mock else []) + [mailbox]:
        d = d / part
        _ensure_dir(d)
    return d


def check_file(path) -> None:
    """Refuse early if the target path is a symlink or not a regular file."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise _unsafe(path)


def history_path(state_dir, mock: bool) -> Path:
    return Path(state_dir) / ("history.mock.json" if mock else "history.json")


def load_history(state_dir, mock: bool) -> dict:
    """Saved positions by mailbox. Missing or unparsable file gives {} (the caller then does a full list)."""
    p = history_path(state_dir, mock)
    check_file(p)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_history(state_dir, mock: bool, mailbox: str, history_id: str, now) -> None:
    """Replace the state file atomically (temp file in the same dir + os.replace), mode 0600."""
    p = history_path(state_dir, mock)
    data = load_history(state_dir, mock)
    data[mailbox] = {"history_id": str(history_id), "updated": now.isoformat(timespec="seconds")}
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".history-", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        check_file(p)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


_DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})(\.find)?\.jsonl$")


def _is_real_dir(p: Path) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(p).st_mode)  # lstat: a symlink is never a real dir
    except OSError:
        return False


def _mailbox_dirs(out_dir: Path) -> list:
    """Pulse's own layout only: <out>/<name@domain>/ and <out>/_mock/<name@domain>/, real dirs, no symlinks."""
    found = []
    for parent in (out_dir, out_dir / "_mock"):
        if not _is_real_dir(parent):
            continue
        for name in sorted(os.listdir(parent)):
            if MAILBOX_RE.match(name) and _is_real_dir(parent / name):
                found.append(parent / name)
    return found


def purge(out_dir, retention_days: int, today, dry_run: bool) -> list:
    """Delete dated output files older than retention_days (UTC dates). Looks only one level inside Pulse's own
    mailbox dirs (R1-8), never deeper and never elsewhere in out_dir; never follows symlinks; touches only
    YYYY-MM-DD.jsonl and YYYY-MM-DD.find.jsonl; removes mailbox dirs left empty. Returns the files (to be) deleted."""
    out_dir = Path(out_dir)
    if not _is_real_dir(out_dir):
        return []
    victims, touched_dirs = [], set()
    for mb in _mailbox_dirs(out_dir):
        for name in sorted(os.listdir(mb)):
            m = _DATED.match(name)
            if not m:
                continue
            p = mb / name
            try:
                if not stat.S_ISREG(os.lstat(p).st_mode):
                    continue
                d = date.fromisoformat(m.group(1))
            except (OSError, ValueError):
                continue
            if (today - d).days > retention_days:
                victims.append(p)
    if not dry_run:
        for p in victims:
            os.unlink(p)
            touched_dirs.add(p.parent)
        for d in touched_dirs:  # mailbox dirs only, never out_dir or _mock
            try:
                os.rmdir(d)  # only succeeds when empty
            except OSError:
                pass
    return victims


def append_rows(path, rows) -> int:
    """Append rows whose id is not already in the file. Locked, so two runs do not duplicate. Returns count written."""
    try:
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError as e:
        if e.errno in (errno.ELOOP, errno.EISDIR):
            raise _unsafe(path) from None
        raise
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.lseek(fd, 0, os.SEEK_SET)
        chunks = []
        while True:
            b = os.read(fd, 1 << 16)
            if not b:
                break
            chunks.append(b)
        seen = set()
        for line in b"".join(chunks).decode("utf-8", errors="replace").splitlines():
            try:
                seen.add(json.loads(line).get("id"))
            except (ValueError, AttributeError):
                continue
        new = []
        for r in rows:
            if r["id"] not in seen:
                seen.add(r["id"])
                new.append(json.dumps(r, ensure_ascii=False) + "\n")
        if new:
            data = "".join(new).encode("utf-8")
            if os.write(fd, data) != len(data):
                raise OSError("short write")
        return len(new)
    finally:
        os.close(fd)
