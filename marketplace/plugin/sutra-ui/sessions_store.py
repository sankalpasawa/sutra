"""Sutra's own session identity, so a conversation is not a Claude artifact.

WHAT WAS WRONG

Every part of a Sutra "session" belonged to Claude Code:

    identity      Claude's session uuid, minted by the CLI
    storage       ~/.claude/projects/<encoded-cwd>/<uuid>.jsonl
    listing       scan that directory
    continuation  `claude --resume <uuid>`
    titles        appended into Claude's own JSONL records

Sutra therefore had no sessions of its own. It had a READER over someone
else's. Three consequences, all of them user-visible:

  1. A session did not exist until Claude minted one. Sutra could not open a
     conversation, name it, or attach it to a workspace before a provider ran.
  2. A second provider was invisible by construction. Nothing outside
     ~/.claude/projects can appear in a list built by scanning it.
  3. Claude owned the durable record. If those files move, or the CLI changes
     its layout, Sutra's history goes with them.

WHAT THIS MODULE OWNS

A session is a SUTRA record with an id Sutra mints, before any provider is
involved. What a provider gives back -- Claude's session uuid, or whatever a
future runtime hands out -- is stored as a HANDLE hanging off that record:

    {"id": "s_ab12...", "provider": "claude",
     "handles": {"claude": "<claude-uuid>"}}

Handles are per-provider and plural on purpose. One conversation continued
under a second provider keeps its Sutra identity, its title and its history,
and simply acquires a second handle.

RESUMING, AND WHY THE FALLBACK IS THE POINT

  - handle for the selected provider  -> native resume (`--resume <handle>`).
    Cheapest path, and it keeps the provider's own server-side context.
  - no handle for that provider       -> replay this store's transcript as seed
    context. Slower and lossier, but it is what makes "continue this
    conversation on a different model" mean anything at all.

WHAT THIS MODULE DOES NOT DO

It does not migrate ~/.claude/projects. A bulk import would duplicate history,
race the CLI's own writes, and put Sutra in the business of maintaining a copy
of a format it does not control. Claude's transcripts stay authoritative for
Claude-native sessions and are still browsed through session_reader; this store
ADOPTS one (records its handle) the first time Sutra drives it. Adoption is
additive and reversible: deleting this store loses Sutra's index, not the
conversations.
"""

import errno
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

SCHEMA = 1

#: Sutra ids are prefixed so they can never be confused with a provider's uuid
#: in a log line, a URL, or a --resume argument. A bare uuid in the wrong slot
#: is the kind of bug that only shows up as a provider rejecting a stranger's id.
ID_PREFIX = "s_"

_ENV_DIR = "SUTRA_UI_SESSIONS"
_DEFAULT_DIR = "~/.sutra-ui/sessions"


def store_dir():
    return Path(os.path.expanduser(os.environ.get(_ENV_DIR, _DEFAULT_DIR)))


def _mkdir_private(p):
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass          # a mode we cannot set is not a reason to lose the session
    return p


def _write_private(path, text):
    """Atomic: write a sibling temp file, then rename over the target.

    A half-written meta.json is worse than a missing one -- json.load raises and
    the session disappears from the list. rename(2) within a directory is atomic,
    so a reader sees either the old file or the new one, never a partial.

    A pid-based temp name is NOT enough: the panel is threaded, and two threads
    in ONE process then share a temp path -- the first rename removes it and the
    second os.replace dies with ENOENT, killing that thread mid-write. Observed
    directly (4 threads, 100 appends, 28 survived). mkstemp gives every writer a
    name nobody else holds.
    """
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)          # never leave a stray .tmp behind
        except OSError:
            pass
        raise



#: A crashed writer must not wedge a session forever, so a lock older than this
#: is treated as abandoned and broken. Generous next to the milliseconds an
#: update actually takes -- the cost of breaking a LIVE lock is a lost update,
#: which is the exact bug this exists to prevent.
_LOCK_STALE_S = 30.0
_LOCK_WAIT_S = 5.0


class _lock(object):
    """Cross-thread AND cross-process mutex for one session's meta.json.

    WHY. update() is read-modify-write, and bind_handle() rides on it. Without
    this, two providers binding at once lose one another's handle: measured 135
    of 160 handles lost over 20 trials of 8 concurrent binds. A lost handle is
    not cosmetic -- resume silently degrades from native to replay (paying to
    re-send the history) or to fresh (losing it).

    O_CREAT|O_EXCL because it is the one primitive that behaves identically for
    threads and for separate processes; the panel and a scheduled routine are
    both writers and are not in the same process.
    """

    def __init__(self, path):
        self.path = str(path) + ".lock"
        self.fd = None

    def __enter__(self):
        deadline = time.time() + _LOCK_WAIT_S
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                return self
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
                try:
                    if time.time() - os.stat(self.path).st_mtime > _LOCK_STALE_S:
                        os.unlink(self.path)
                        continue
                except OSError:
                    continue          # someone else just released it; retry
                if time.time() > deadline:
                    # Proceeding unlocked beats hanging the UI: the update may
                    # race, but a wedged panel is certain breakage.
                    return self
                time.sleep(0.002)

    def __exit__(self, *exc):
        if self.fd is not None:
            try:
                os.close(self.fd)
                os.unlink(self.path)
            except OSError:
                pass
        return False


def new_id():
    return ID_PREFIX + uuid.uuid4().hex[:20]


def is_sutra_id(sid):
    return isinstance(sid, str) and sid.startswith(ID_PREFIX)


def _dir_for(sid):
    if not is_sutra_id(sid):
        raise ValueError("not a sutra session id: %r" % (sid,))
    if "/" in sid or "\\" in sid or ".." in sid:
        raise ValueError("unsafe session id: %r" % (sid,))
    return store_dir() / sid


def create(title=None, cwd=None, provider=None, sid=None):
    """Mint a session. No provider is contacted; this is the whole point --
    identity exists before, and independently of, any model runtime."""
    sid = sid or new_id()
    d = _mkdir_private(_dir_for(sid))
    now = time.time()
    meta = {
        "schema": SCHEMA,
        "id": sid,
        "title": title or "",
        "cwd": cwd or "",
        "provider": provider or "",
        "handles": {},
        "created_at": now,
        "updated_at": now,
        "turns": 0,
    }
    _write_private(d / "meta.json", json.dumps(meta, indent=2))
    return meta


def read(sid):
    try:
        with open(_dir_for(sid) / "meta.json", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def update(sid, **fields):
    """Merge fields into the record. `handles` merges rather than replaces, so
    binding a second provider never drops the first one's handle."""
    path = _dir_for(sid) / "meta.json"
    bump = fields.pop("_bump_turns", False)
    with _lock(path):
        meta = read(sid)
        if meta is None:
            return None
        handles = fields.pop("handles", None)
        # Incremented INSIDE the lock. Doing read()+update(turns=n+1) from the
        # caller spans two locked sections and loses updates exactly as the
        # handle race did -- measured 25 of 100 appends counted.
        if bump:
            meta["turns"] = int(meta.get("turns") or 0) + 1
        meta.update(fields)
        if handles:
            meta.setdefault("handles", {}).update(handles)
        meta["updated_at"] = time.time()
        _write_private(path, json.dumps(meta, indent=2))
    return meta


def bind_handle(sid, provider, handle):
    """Record what a provider called this conversation.

    Called when a runtime reports its own session id. Idempotent, and it never
    clobbers a DIFFERENT provider's handle -- that is what makes one Sutra
    session able to span providers.
    """
    if not provider or not handle:
        return read(sid)
    return update(sid, handles={provider: handle})


def handle_for(sid, provider):
    meta = read(sid)
    if not meta:
        return None
    return (meta.get("handles") or {}).get(provider) or None


def find_by_handle(provider, handle):
    """The Sutra session that already owns this provider handle, or None.

    THE STORE HEALS ITSELF. Identity is supposed to travel on the wire: the
    socket announces a sutra_session id and the client hands it back on the next
    message. When that round trip is broken -- as it was, because nothing in the
    client ever read the frame -- every reopen minted a NEW record and one
    conversation shattered into a record per pane.

    Reopening always carries the PROVIDER's id (that is what --resume needs), so
    the provider handle is a second, independent way to recognise a conversation
    Sutra has already seen. Looking it up here means a forgetful or older client
    cannot fragment the store; the wire round trip becomes an optimisation
    rather than the only thing holding identity together.

    A linear scan over meta.json files, like listing(). At the size this store
    reaches -- one record per conversation -- an index would be a second thing to
    keep correct for no measurable gain.
    """
    if not provider or not handle:
        return None
    for meta in listing(limit=10000):
        if (meta.get("handles") or {}).get(provider) == handle:
            return meta
    return None


def resume_plan(sid, provider, native_ok=True):
    """How to continue this session under `provider`, without deciding for the
    caller. Returns ('native', handle) | ('replay', sid) | ('fresh', sid).

    Separated from the doing so it is testable without a runtime, and so the UI
    can TELL the operator which one is about to happen -- "continuing on a new
    model, replaying N turns" is information they should have before it costs
    them tokens, not after.
    """
    meta = read(sid)
    if meta is None:
        return ("fresh", sid)
    h = (meta.get("handles") or {}).get(provider)
    # A handle is not enough: the provider must also be ABLE to resume from it.
    # Holding an id proves the thread existed, not that this CLI can continue
    # it -- some take a conversation only as replayed context. Saying "native"
    # for one of those would hand it an id it has no flag to accept.
    if h and native_ok:
        return ("native", h)
    if meta.get("turns"):
        return ("replay", sid)
    return ("fresh", sid)


def append_turn(sid, role, text, provider=None, meta_extra=None):
    """Append one provider-neutral turn to this session's own transcript.

    O_APPEND with a single write() call: concurrent appenders (the panel and a
    scheduled routine can both be live) interleave whole lines rather than
    corrupting each other. Kept small and boring -- this file is the thing that
    makes cross-provider continuation possible, so it must not depend on any
    provider's record shape.
    """
    d = _mkdir_private(_dir_for(sid))
    row = {"schema": SCHEMA, "ts": time.time(), "role": role,
           "text": text or "", "provider": provider or ""}
    if meta_extra:
        row.update(meta_extra)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    fd = os.open(str(d / "transcript.jsonl"),
                 os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    update(sid, _bump_turns=True)
    return row


def transcript(sid, limit=None):
    """Turns, oldest first. Unparseable lines are SKIPPED, not fatal: a torn
    final line (power loss mid-append) must not make the whole history
    unreadable."""
    p = _dir_for(sid) / "transcript.jsonl"
    out = []
    try:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out[-limit:] if limit else out


def listing(limit=200):
    """Sessions, newest first. A directory whose meta.json is missing or corrupt
    is skipped rather than raising -- one bad record must not empty the list."""
    d = store_dir()
    out = []
    try:
        names = os.listdir(d)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
        return []
    for name in names:
        if not is_sutra_id(name):
            continue
        m = read(name)
        if m:
            out.append(m)
    out.sort(key=lambda r: r.get("updated_at") or 0, reverse=True)
    return out[:limit]


def delete(sid):
    """Remove Sutra's record. The provider's own transcript is NOT touched --
    this store never had the right to delete Claude's files, and a user removing
    a Sutra session is not asking for that."""
    import shutil
    d = _dir_for(sid)
    if not d.exists():
        return False
    shutil.rmtree(d)
    return True
