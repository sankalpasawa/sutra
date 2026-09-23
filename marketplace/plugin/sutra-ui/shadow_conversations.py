"""A Shadow CONVERSATION is durable, and it is not a mission.

WHY THIS EXISTS (founder, 2026-09-23). Until now the only durable Shadow
identity was the mission id, so the rail -- and therefore everything that
survived a reload -- was rebuilt from `GET /api/shadow/missions` alone. That
made a conversation that produced no task unrepresentable: it lived in the
client's `S.shadowThreads` and nowhere else, so a hard refresh lost it. The
two ideas had been collapsed into one, and the fix is to separate them:

    conversation   minted the instant the founder presses Enter, always,
                   whatever they typed. Holds their prompt and Shadow's
                   replies. Survives a reload. Never implies work.

    mission        created only when Shadow reads actionable work in the
                   prompt. Has its own id, its own lifecycle, its own store.
                   A conversation MAY name one; most do not.

THE ID IS MINTED BY THE CLIENT, deliberately. The transition from New task to
the conversation must be synchronous -- the founder is not to watch a spinner
while a POST decides what their conversation is called -- so the client mints
`shc-<hex>` at the keystroke, renders with it, and tells the server after.
`create` is therefore IDEMPOTENT on that id: a retry, a double-submit or a
replayed request lands on the same record instead of forking a second one.

THE STORE IS THE MISSION STORE'S SHAPE, on purpose. Same home
(shadow_ledger.shadow_home, which is also what refuses to touch the live home
from a test), same file-per-record directory, same atomic lock-and-replace,
same monotonic `seq` so a crashed write cannot leave a torn file and two
writers cannot silently lose each other. Nothing new was invented to store
this; it is the pattern already in use, pointed at a second directory.
"""
import fcntl
import json
import os
import re
import time
import uuid

import shadow_ledger

#: a client-minted id, and the only shape this store will accept. Anchored
#: and bounded: the id becomes a FILENAME, so anything that could climb out
#: of the directory or collide with a mission file is refused at the door.
ID_RE = re.compile(r"^shc-[0-9a-z]{6,40}$")

#: what a listing returns at most. The rail is missions; this list is for
#: rebuilding the conversations a founder can still open, newest first.
LIST_CAP = 200

#: one conversation's transcript, capped so a runaway loop cannot grow a
#: single file without bound. The oldest rows go first -- a conversation's
#: opening line is the one thing worth keeping, so it is pinned.
MAX_MESSAGES = 400

#: one message, capped for the same reason the mission store caps its fields
MAX_TEXT = 8000


def _dir():
    return os.path.join(os.path.realpath(shadow_ledger.shadow_home()),
                        "conversations")


def _path(cid):
    if not ID_RE.match(cid or ""):
        raise ValueError("bad conversation id %r" % (cid,))
    return os.path.join(_dir(), cid + ".json")


def mint():
    """A fresh id, for callers that have no client to mint one."""
    return "shc-" + uuid.uuid4().hex[:16]


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _title(prompt):
    """The conversation's name is the founder's own first line, trimmed --
    never a summary, because a summary of one sentence is that sentence."""
    one = " ".join(str(prompt or "").split())
    return one[:79] + "…" if len(one) > 80 else one


def _clip(text):
    t = str(text if text is not None else "")
    return t[:MAX_TEXT]


def _write(rec):
    """Atomic, locked, seq-guarded -- MissionStore.save's contract."""
    os.makedirs(_dir(), exist_ok=True)
    path = _path(rec["id"])
    with open(path + ".lock", "w") as lk:
        fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
        try:
            disk = _read(rec["id"])
            if disk and disk.get("seq", 0) > rec.get("seq", 0):
                raise ValueError("stale write for %s" % rec["id"])
            rec["seq"] = int(rec.get("seq", 0)) + 1
            rec["updated_at"] = _now()
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(rec, handle, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        finally:
            fcntl.flock(lk.fileno(), fcntl.LOCK_UN)
    return rec


def _read(cid):
    try:
        with open(_path(cid), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def load(cid):
    return _read(cid)


def create(cid, prompt):
    """Open a conversation, or return the one that id already names.

    IDEMPOTENT BY CONTRACT, not by luck. The client mints the id before it
    sends anything, so the same create can legitimately arrive twice -- a
    retry after a dropped socket, a double Enter, a replayed request. The
    second one must be the same conversation, never a fork.
    """
    if not ID_RE.match(cid or ""):
        raise ValueError("bad conversation id %r" % (cid,))
    existing = _read(cid)
    if existing:
        return existing
    rec = {
        "id": cid,
        "title": _title(prompt),
        "created_at": _now(),
        "updated_at": _now(),
        "mission_id": None,
        "messages": [],
        "seq": 0,
    }
    if prompt is not None and str(prompt).strip():
        rec["messages"].append(
            {"who": "founder", "text": _clip(prompt), "ts": _now()})
    return _write(rec)


def append(cid, who, text):
    """Add one turn. `who` is the founder or Shadow -- there is no third
    speaker in this conversation, which is the same rule the pane draws by."""
    if who not in ("founder", "shadow"):
        raise ValueError("who must be founder|shadow")
    rec = _read(cid)
    if not rec:
        raise KeyError(cid)
    rec["messages"].append({"who": who, "text": _clip(text), "ts": _now()})
    if len(rec["messages"]) > MAX_MESSAGES:
        # the opening line is what names the conversation, so it is pinned;
        # the oldest turns after it are what a cap has to give up
        rec["messages"] = rec["messages"][:1] + rec["messages"][-(MAX_MESSAGES - 1):]
    return _write(rec)


def bind_mission(cid, mission_id):
    """Name the mission this conversation opened.

    ONE WAY, AND ONLY ONCE. A conversation that already names a mission keeps
    it: re-binding would let a later, unrelated answer re-point a
    conversation the founder has already read, which is the same class of
    bug as writing a reply into whichever chat happens to be selected.
    """
    rec = _read(cid)
    if not rec:
        raise KeyError(cid)
    if rec.get("mission_id"):
        return rec
    rec["mission_id"] = str(mission_id) if mission_id else None
    return _write(rec)


def list_all():
    """Newest first, capped. Cheap: names come from the records themselves."""
    out = []
    try:
        names = os.listdir(_dir())
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        rec = _read(name[:-5])
        if rec and rec.get("id"):
            out.append(rec)
    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return out[:LIST_CAP]


def delete(cid):
    try:
        os.remove(_path(cid))
        return True
    except OSError:
        return False
