"""chat_store.py -- the chat record that OUTLIVES any one provider session.

A chat here is not a provider session. `claude` keeps its thread in
~/.claude/projects/<cwd>/<id>.jsonl and DeepSeek keeps its own under
~/.gemini/tmp/<project>/chats/session-*.jsonl (session_reader.py:17 and :25),
and neither can load the other's. So the moment the panel lets an operator
switch provider WITHOUT starting over, the durable thing has to be ours: one
`sutra_id` that owns N provider sessions in sequence.

    provider_history = [{provider, native_id, from_turn}, ...]

`from_turn` is what makes it a SEGMENT rather than a fork: turns 0..49 belong
to the first entry, turn 50 onward to the second. Rendering one continuous
thread is then a read of one file, and "which session do I resume" is the last
entry -- not a search.

WHY THE FORMAT IS NOT NEGOTIABLE
Records in this exact shape already exist on the founder's machine, written
2026-09-01 by something outside this checkout (no copy of the repo, no plugin
cache version, and not the .app payload contains the string
"provider_history"). Their shape is therefore treated as the contract and
matched byte-for-byte -- including `_index.json` keyed "<provider>:<native_id>"
-- rather than improved. Inventing a second format would strand them.

TYPED BLOCKS, AND WHY `text` WAS NOT ENOUGH
Those existing records carry messages as {role, text, ts}. A flattened string
cannot express the thing this feature exists to move: a Claude transcript is
93.6% tool_use/tool_result by volume and a DeepSeek transcript is 85%
`thoughts` (measured over 24 and 33 real transcripts respectively). The replay
renderer has to keep tool results distinguishable from prose -- a model that
cannot tell "I ran this" from "I was told this happened" may re-run a mutation
-- and it has to DROP `thoughts` in the DeepSeek->Claude direction. Both are
per-block decisions, so blocks are stored typed:

    {"role": "assistant", "ts": ..., "blocks": [
        {"type": "text",        "text": ...},
        {"type": "thinking",    "text": ...},
        {"type": "tool_use",    "name": ..., "input": {...}, "id": ...},
        {"type": "tool_result", "tool_use_id": ..., "text": ..., "is_error": ...}]}

The legacy {role, text, ts} shape is upgraded ON READ (see `_upgrade_message`)
and the file is NOT rewritten. A read-time upgrade cannot corrupt a record it
misparses, and the two existing chats keep working without a migration step
that has to be correct on the first and only run.

Reads:  ~/.sutra-ui/chats/*.json and _index.json
Writes: the same, atomically via json_store.write_json (0600, tmp+replace).
        Nothing under SUTRA_NATIVE_HOME, nothing in either provider's tree.
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import json_store

#: The four block types the replay renderer knows how to filter. A block whose
#: type is not in here is dropped at write time rather than stored: an unknown
#: type would reach the renderer, which would have to guess whether it is safe
#: to send to another vendor's model, and "guess" is the wrong answer there.
BLOCK_TYPES = ("text", "thinking", "tool_use", "tool_result")

#: Providers that may own a segment -- deliberately the same set as
#: providers.ADAPTERS rather than an import, to keep this module free of the
#: PATH/config probing that providers.py does on every call. Kept in sync by
#: test_chat_store.test_providers_match_adapters.
SEGMENT_PROVIDERS = ("claude", "deepseek")


def store_dir():
    return Path(os.path.expanduser(
        os.environ.get("SUTRA_UI_CHATS", "~/.sutra-ui/chats")))


def _index_path():
    return store_dir() / "_index.json"


def _path(sutra_id):
    return store_dir() / (sutra_id + ".json")


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _mkdir():
    d = store_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def _safe_id(sutra_id):
    """32 lowercase hex and nothing else. `sutra_id` reaches _path() and would
    otherwise be a path-traversal parameter on every read endpoint that takes a
    chat id from the browser."""
    return (isinstance(sutra_id, str) and len(sutra_id) == 32
            and all(c in "0123456789abcdef" for c in sutra_id))


# ------------------------------------------------------------------ blocks --

def block_text(text):
    return {"type": "text", "text": str(text or "")}


def block_thinking(text):
    return {"type": "thinking", "text": str(text or "")}


def block_tool_use(name, inp, tool_id=None):
    return {"type": "tool_use", "name": str(name or ""),
            "input": inp if isinstance(inp, dict) else {},
            "id": tool_id}


def block_tool_result(text, tool_use_id=None, is_error=False):
    return {"type": "tool_result", "text": str(text or ""),
            "tool_use_id": tool_use_id, "is_error": bool(is_error)}


def _clean_blocks(blocks):
    """Keep only well-formed blocks of a known type, in order.

    Silently dropping a malformed block is correct HERE and would be wrong one
    layer up: this is the durable store, and a half-written block that survives
    to disk is a defect every later reader inherits. The caller that produced
    it is in-process and can be fixed; a corrupt record on a founder's disk
    cannot.
    """
    out = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        if b.get("type") not in BLOCK_TYPES:
            continue
        out.append(b)
    return out


# ----------------------------------------------------------------- records --

def _upgrade_message(m):
    """One stored message in the typed shape, whichever shape it was written in.

    Legacy records (the two written 2026-09-01) carry {role, text, ts} with no
    blocks. They become a single text block. A record that already has `blocks`
    passes through with its blocks validated -- so an upgraded read is
    idempotent and a mixed-shape file (legacy turns followed by new ones) is a
    normal case, not a repair case.
    """
    if not isinstance(m, dict):
        return None
    role = m.get("role")
    if role not in ("user", "assistant"):
        return None
    ts = m.get("ts") or ""
    if isinstance(m.get("blocks"), list):
        blocks = _clean_blocks(m["blocks"])
    else:
        # `text` may legitimately be "" -- an empty assistant turn is a real
        # thing (a tool-only turn) and must not vanish, so this does not test
        # truthiness before building the block.
        blocks = [block_text(m.get("text") or "")]
    out = {"role": role, "ts": ts, "blocks": blocks}
    for k in ("provider", "native_id", "turn"):
        if m.get(k) is not None:
            out[k] = m[k]
    return out


def _upgrade(rec):
    """A record from disk, normalised. Missing keys are filled with their empty
    value rather than raising: a record truncated by an older writer must still
    render, and `load` returning None for a chat the operator can see in the
    list would be a worse failure than an empty thread."""
    if not isinstance(rec, dict):
        return None
    msgs = [_upgrade_message(m) for m in (rec.get("messages") or [])]
    hist = [h for h in (rec.get("provider_history") or [])
            if isinstance(h, dict) and h.get("provider") and h.get("native_id")]
    return {
        "sutra_id": rec.get("sutra_id") or "",
        "title": rec.get("title") or "",
        "cwd": rec.get("cwd") or "",
        "branch": rec.get("branch") or "",
        "created": rec.get("created") or "",
        "updated": rec.get("updated") or "",
        "provider_history": hist,
        "messages": [m for m in msgs if m],
    }


def load(sutra_id):
    """One chat, upgraded to the typed shape, or None."""
    if not _safe_id(sutra_id):
        return None
    raw = json_store.read_json(_path(sutra_id), {})
    if not raw:
        return None
    rec = _upgrade(raw)
    return rec if rec and rec["sutra_id"] else None


def save(rec):
    """Persist one chat and refresh its index entries.

    The index is rebuilt from THIS record's provider_history rather than
    appended to, so a segment removed from a record cannot leave a dangling
    "provider:native_id -> sutra_id" row pointing at a session the chat no
    longer claims.
    """
    if not _safe_id(rec.get("sutra_id")):
        raise ValueError("sutra_id must be 32 lowercase hex chars")
    _mkdir()
    rec["updated"] = _now()
    json_store.write_json(_path(rec["sutra_id"]), rec)
    _reindex(rec)
    return rec


def create(cwd="", branch="", title=""):
    """A new empty chat. No provider is chosen here -- a chat exists before it
    has been sent anywhere, and `begin_segment` is what binds it to one."""
    sid = uuid.uuid4().hex
    now = _now()
    return save({
        "sutra_id": sid,
        "title": title or "",
        "cwd": cwd or "",
        "branch": branch or "",
        "created": now,
        "updated": now,
        "provider_history": [],
        "messages": [],
    })


# ---------------------------------------------------------------- segments --

def turn_count(rec):
    """User turns, which is what `from_turn` counts.

    Not len(messages): an assistant reply is not a turn boundary, and counting
    both halves would make every `from_turn` twice the number a reader expects
    when comparing against a rendered thread.
    """
    return sum(1 for m in rec.get("messages") or [] if m.get("role") == "user")


def active_segment(rec):
    """The segment that owns the NEXT turn, or None before the first send."""
    hist = rec.get("provider_history") or []
    return hist[-1] if hist else None


def begin_segment(rec, provider, native_id):
    """Bind the turns from here on to one provider session.

    Idempotent for the same (provider, native_id): re-binding the session that
    is already active is what a browser reconnect looks like, and appending a
    duplicate segment there would split one continuous run into two and make
    the replay renderer believe a switch had happened.
    """
    if provider not in SEGMENT_PROVIDERS:
        raise ValueError("unknown provider %r -- known: %s"
                         % (provider, ", ".join(SEGMENT_PROVIDERS)))
    if not native_id:
        raise ValueError("native_id is required -- a segment with no session "
                         "id cannot be resumed and cannot be replayed from")
    cur = active_segment(rec)
    if cur and cur.get("provider") == provider and cur.get("native_id") == native_id:
        return rec
    rec.setdefault("provider_history", []).append({
        "provider": provider,
        "native_id": native_id,
        "from_turn": turn_count(rec),
    })
    return save(rec)


def segment_of_turn(rec, turn):
    """Which segment owned a given user-turn index. The renderer needs this to
    badge each turn with the provider that actually produced it."""
    found = None
    for h in rec.get("provider_history") or []:
        if h.get("from_turn", 0) <= turn:
            found = h
        else:
            break
    return found


def switched(rec):
    """True once more than one provider has owned part of this chat. The UI
    marker and the replay path both branch on this, so it is computed here
    rather than re-derived in two places that could disagree."""
    provs = [h.get("provider") for h in rec.get("provider_history") or []]
    return len(set(provs)) > 1


# ---------------------------------------------------------------- messages --

def append_turn(rec, role, blocks):
    """Append one message, stamped with the segment that owns it.

    `provider` and `native_id` are copied ONTO the message rather than looked
    up later from provider_history. A message is immutable once written and its
    provenance must survive any later edit to the segment list -- if a segment
    is ever removed or rewritten, the turns it produced must still say who
    produced them.
    """
    if role not in ("user", "assistant"):
        raise ValueError("role must be 'user' or 'assistant'")
    seg = active_segment(rec) or {}
    msg = {
        "role": role,
        "ts": _now(),
        "blocks": _clean_blocks(blocks),
        "turn": turn_count(rec) if role == "user" else max(turn_count(rec) - 1, 0),
    }
    if seg.get("provider"):
        msg["provider"] = seg["provider"]
        msg["native_id"] = seg.get("native_id")
    rec.setdefault("messages", []).append(msg)
    return save(rec)


# ------------------------------------------------------------------ index ---

def _index_key(provider, native_id):
    return "%s:%s" % (provider, native_id)


def _reindex(rec):
    idx = json_store.read_json(_index_path(), {})
    sid = rec["sutra_id"]
    # Drop every row that currently points at this chat, then re-add from the
    # record. Same reason save() rebuilds rather than appends.
    idx = {k: v for k, v in idx.items() if v != sid}
    for h in rec.get("provider_history") or []:
        idx[_index_key(h["provider"], h["native_id"])] = sid
    json_store.write_json(_index_path(), idx)
    return idx


def resolve(provider, native_id):
    """The chat that owns a provider-native session id, or None.

    This is the lookup ws_chat needs on reconnect: the browser hands back a
    native session id, and the panel has to find the Sutra chat it belongs to
    -- which may have started on the OTHER provider.
    """
    if not provider or not native_id:
        return None
    idx = json_store.read_json(_index_path(), {})
    sid = idx.get(_index_key(provider, native_id))
    return sid if _safe_id(sid) else None


def index():
    """The whole reverse map. Read-only view for diagnostics."""
    return json_store.read_json(_index_path(), {})
