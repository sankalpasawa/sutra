"""chat_archive.py -- which chats are archived, kept in Sutra's own store.

ARCHIVE IS A MARK, NOT A MOVE (founder, 2026-09-25: "Sutra architecture ...
with no changes in the base layers"). The old Archive moved the transcript out
of ~/.claude/projects, so the chat vanished from Claude's own /resume as well as
from this rail. Nothing here touches a transcript: archive state is a small
JSON file beside the app's other state, ~/.sutra-ui/chat-archive.json.

ONE RULE, NO DAEMON. A chat is archived when the latest archive event that
covers it is newer than BOTH its last write and any unarchive of it. So a chat
that is written to again -- it went live, in the terminal or in the panel --
leaves the archive by itself on the next list read ("if chats are live, they
come from archive to become live automatically"). Nothing archives on a timer.

Three kinds of event:
  baseline   archive everything last touched before `ts` (a one-time sweep;
             chats open in a terminal at that moment are unarchived with it)
  marks      one chat archived at `at`, by `by` ("you", or an agent's name)
  unarchived one chat brought back at `ts` (clicking it in Archived)

Who may archive: the operator (the x on a row, the row menu) and any agent,
through POST /api/sessions/{id}/archive?by=<name>. The row then says who.
"""

import json
import os
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
_CLAUDE_SESSIONS = Path(os.path.expanduser("~/.claude/sessions"))


def _path():
    return Path(os.environ.get("SUTRA_UI_CHAT_ARCHIVE")
                or os.path.expanduser("~/.sutra-ui/chat-archive.json"))


def _empty():
    return {"v": 1, "baseline": 0, "marks": {}, "unarchived": {}}


def load():
    """The store, or an empty one. An unreadable file must never empty the rail
    or hide a chat: it reads as 'nothing archived'."""
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty()
    if not isinstance(d, dict):
        return _empty()
    out = _empty()
    out["baseline"] = float(d.get("baseline") or 0)
    out["marks"] = d.get("marks") if isinstance(d.get("marks"), dict) else {}
    out["unarchived"] = d.get("unarchived") if isinstance(d.get("unarchived"), dict) else {}
    return out


def _save(d):
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


def state(sid, mtime, d=None):
    """(archived, by) for one chat. `mtime` is its last write, in seconds."""
    d = d if d is not None else load()
    base = float(d.get("baseline") or 0)
    m = (d.get("marks") or {}).get(sid) or {}
    at = float(m.get("at") or 0) if isinstance(m, dict) else 0.0
    covered = max(base, at)
    if not covered:
        return False, None
    if float((d.get("unarchived") or {}).get(sid) or 0) >= covered:
        return False, None
    if float(mtime or 0) >= covered:
        return False, None            # written to since: it came back by itself
    return True, (m.get("by") or "you") if at >= base and at else None


def archive(sid, by="you", now=None):
    now = float(now if now is not None else time.time())
    by = (str(by or "you").strip() or "you")[:40]
    with _LOCK:
        d = load()
        d["marks"][sid] = {"at": now, "by": by}
        _save(d)
    return {"archived": True, "by": by, "at": now}


def unarchive(sid, now=None):
    now = float(now if now is not None else time.time())
    with _LOCK:
        d = load()
        d["unarchived"][sid] = now
        _save(d)
    return {"archived": False, "at": now}


def open_in_terminal():
    """Session ids of the Claude Code windows running on this Mac right now.
    Claude writes ~/.claude/sessions/<pid>.json for each; a record whose
    process is gone is stale and ignored."""
    ids = set()
    try:
        files = list(_CLAUDE_SESSIONS.glob("*.json"))
    except OSError:
        return ids
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
            pid = int(rec.get("pid"))
            os.kill(pid, 0)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        sid = rec.get("sessionId")
        if isinstance(sid, str) and sid:
            ids.add(sid)
    return ids


def baseline(keep=None, now=None):
    """Archive every chat last touched before now, except `keep` (default: the
    chats open in a terminal right now). One sweep; later writes bring any chat
    back by the rule above."""
    now = float(now if now is not None else time.time())
    keep = set(open_in_terminal() if keep is None else keep)
    with _LOCK:
        d = load()
        d["baseline"] = now
        for sid in keep:
            d["unarchived"][sid] = now
        _save(d)
    return {"baseline": now, "kept": sorted(keep)}
