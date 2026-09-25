"""chat_archive.py -- which chats are archived, kept in Sutra's own store.

ARCHIVE IS A MARK, NOT A MOVE (founder, 2026-09-25: "Sutra architecture ...
with no changes in the base layers"). The old Archive moved the transcript out
of ~/.claude/projects, so the chat vanished from Claude's own /resume as well as
from this rail. Nothing here touches a transcript: archive state is a small
JSON file beside the app's other state, ~/.sutra-ui/chat-archive.json.

ONLY THE APP ARCHIVES (founder, 2026-09-25: "it should only be driven by the
app and nothing else ... if I start a chat from the terminal, it should show up
in there"). A chat is archived by exactly one thing: an archive mark set
through the app -- the x on a row, the row menu, or an agent working inside the
app through POST /api/sessions/{id}/archive?by=<name>. There is no sweep, no
timer, and nothing watches the terminal: closing a Claude Code window archives
nothing, and a chat started in the terminal simply appears in the rail. The
first cut had a one-time baseline sweep that archived every chat not open in a
terminal at that moment; it archived 34 of the founder's closed chats and was
removed the same day. An old store's `baseline` key is read and ignored.

ONE RULE, NO DAEMON. A chat is archived when its mark is newer than BOTH its
last write and any unarchive of it. So a chat that is written to again -- it
went live, in the terminal or in the panel -- leaves the archive by itself on
the next list read ("if chats are live, they come from archive to become live
automatically").

Two kinds of event:
  marks      one chat archived at `at`, by `by` ("you", or an agent's name)
  unarchived one chat brought back at `ts` (clicking it in Archived)
"""

import json
import os
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()


def _path():
    return Path(os.environ.get("SUTRA_UI_CHAT_ARCHIVE")
                or os.path.expanduser("~/.sutra-ui/chat-archive.json"))


def _empty():
    return {"v": 1, "marks": {}, "unarchived": {}}


def load():
    """The store, or an empty one. An unreadable file must never empty the rail
    or hide a chat: it reads as 'nothing archived'. A `baseline` key left by
    the removed sweep is ignored."""
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty()
    if not isinstance(d, dict):
        return _empty()
    out = _empty()
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
    m = (d.get("marks") or {}).get(sid) or {}
    at = float(m.get("at") or 0) if isinstance(m, dict) else 0.0
    if not at:
        return False, None            # never archived from the app
    if float((d.get("unarchived") or {}).get(sid) or 0) >= at:
        return False, None
    if float(mtime or 0) >= at:
        return False, None            # written to since: it came back by itself
    return True, (m.get("by") or "you")


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
