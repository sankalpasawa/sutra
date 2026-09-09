"""outbox.py — a plane, or Supabase being down, must not lose work.

WORKSPACE-PLAN.md section 6: the local copy is the truth Sutra reads, and that is only honest if a
change made with no network is still a change. So nothing is ever sent straight to Supabase. Every
local change is written to a queue on disk FIRST, and the queue is drained when the network is
there. A write that never reached Supabase is still on disk after a reboot.

THE QUEUE IS THE DIRECTORY. One file per queued change, named `<seq>-<id>.json`, so the sort order
of the filenames IS the send order and there is no index file that could disagree with the files
beside it. The sequence is `max(what is on disk) + 1`, computed from the directory itself, so a
crash cannot leave a counter file pointing at a number the files do not have.

ORDER IS THE CONTRACT, so a failing item BLOCKS the ones behind it. That is deliberate: two edits
of the same prompt must land in the order they were made, and skipping past a failure to "make
progress" would let the older edit overwrite the newer one. The queue is a queue.

NOTHING IS DROPPED BECAUSE A REQUEST FAILED. There is no maximum attempt count. An item backs off
(1s, 2s, 5s, 15s, 60s, then 5 minutes for ever) and keeps trying, because the alternative is
telling somebody their work went up when it did not. A person can see a stuck item — it carries
its attempt count and its last error, and `status()` reports them.

REPLAYING MUST NOT DOUBLE-APPLY, and it is made safe twice over:
  1. every item has a STABLE id, minted once at enqueue and never regenerated, and a small ledger
     of recently sent ids is written BEFORE the queue file is removed. A crash between the send
     and the delete therefore replays into the ledger and drops the file instead of resending.
  2. the send itself is an UPSERT on the row's own primary key, so even a resend that gets past
     the ledger writes the same values over the same row. It converges; it does not double.

Reads:  workspace/outbox/*.json
Writes: workspace/outbox/*.json, workspace/outbox-sent.json
"""
import os
import re
import threading
import time
import uuid

from .. import store

# How long to wait before retrying a failed send, by attempt number. The last value repeats for
# ever: an outage that lasts an afternoon should be one request every five minutes, not a hot loop,
# and not a give-up.
BACKOFF_SECONDS = (1, 2, 5, 15, 60, 300)

# How many recently-sent ids the crash ledger keeps. It only has to cover the window between a
# successful send and the queue file being removed, which is microseconds; 500 is absurdly
# generous and costs a few KB.
SENT_LEDGER_KEEP = 500

_NAME = re.compile(r"^(\d{12})-([A-Za-z0-9_.-]+)\.json$")
_LOCK = threading.Lock()        # one Sutra process per Mac; this guards the two threads inside it


# ---- where the queue lives -----------------------------------------------------------------------

def dir_():
    return os.path.join(store.data_dir(), "workspace", "outbox")


def _ledger_path():
    return os.path.join(store.data_dir(), "workspace", "outbox-sent.json")


def _files():
    """Every queued item's path, in send order. The filename sort IS the order."""
    d = dir_()
    try:
        names = os.listdir(d)
    except OSError:
        return []
    return [os.path.join(d, n) for n in sorted(names) if _NAME.match(n)]


def _next_seq():
    """max(on disk) + 1, read from the directory rather than a counter file.

    A counter file is a second thing to keep in step with the queue, and a crash between bumping it
    and writing the item would leave them disagreeing. The directory cannot disagree with itself.
    Restarting at 1 once the queue drains is fine: order only ever matters between items that are
    queued at the same time.
    """
    top = 0
    for p in _files():
        m = _NAME.match(os.path.basename(p))
        if m:
            top = max(top, int(m.group(1)))
    return top + 1


# ---- the crash ledger ------------------------------------------------------------------------------

def _ledger():
    return store.read_json(_ledger_path(), []) or []


def _remember(item_id):
    ids = _ledger()
    ids.append(item_id)
    store.write_json(_ledger_path(), ids[-SENT_LEDGER_KEEP:])


# ---- putting something in --------------------------------------------------------------------------

def enqueue(kind, table, pk, key, row=None, op="upsert", actor="", item_id=None):
    """Queue one change and return its item. Never talks to the network.

    `item_id` is the stable id the whole idempotence story rests on. It is minted here, once, and
    written into the file; a retry re-sends the SAME id rather than minting a new one, which is
    what lets the ledger recognise a replay. A caller may pass its own id when it already has a
    natural one (a run id, say) — same rule: mint it once, never regenerate it.
    """
    if op not in ("upsert", "delete"):
        raise ValueError("op is upsert or delete, not %r" % op)
    # Refused at the door as well as at the send. The trigger owns the log (WORKSPACE-PLAN.md
    # section 3), and a client write to it would leave the log and the tables disagreeing for ever.
    if table == "changes":
        raise ValueError("a client never writes the changes log; the trigger does")
    item = {"id": item_id or ("q-" + uuid.uuid4().hex),
            "kind": kind, "table": table, "pk": pk or "", "key": str(key),
            "op": op, "row": row if row is not None else {},
            "actor": actor or "", "queued_at": store.now(),
            "attempts": 0, "next_try_at": 0.0, "last_error": ""}
    with _LOCK:
        seq = _next_seq()
        path = os.path.join(dir_(), "%012d-%s.json" % (seq, item["id"]))
        store.write_json(path, item)        # temp file in the same dir, then rename. Never half an item.
    return item


def pending():
    """Every queued item, in send order."""
    out = []
    for p in _files():
        it = store.read_json(p)
        if it:
            it["_path"] = p
            out.append(it)
    return out


def count():
    return len(_files())


# ---- getting it out ---------------------------------------------------------------------------------

def _send(client, item):
    """One item onto Supabase. The row goes to its own table; the LOG is written by the trigger.

    Never a write to `changes`. That is the entire argument for having a trigger at all
    (WORKSPACE-PLAN.md section 3): a client that wrote both the row and the log entry, and died
    between them, would leave a change nobody ever heard about.
    """
    if item["table"] == "changes":
        raise ValueError("a client never writes the changes log; the trigger does")
    if item["op"] == "delete":
        if not item.get("pk"):
            raise ValueError("cannot delete from %s without a primary key column" % item["table"])
        client.delete(item["table"], {item["pk"]: item["key"]})
        return
    row = dict(item.get("row") or {})
    # An EMPTY pk means the database fills it (company.workspace_id defaults to
    # current_workspace_id(), and that default is what makes a second company row impossible).
    # Stamping the queue's key into it would send a made-up value into a uuid column.
    if item.get("pk"):
        row.setdefault(item["pk"], item["key"])
    client.upsert(item["table"], [row])


def drain(client, now=None, limit=None):
    """Send what is due, in order, until something fails or the queue is empty.

    Returns {"sent", "left", "blocked", "why"}. `blocked` is true when an item failed and the rest
    of the queue is waiting behind it, which is the state the UI shows as "waiting for the network".
    """
    now = time.time() if now is None else now
    sent, blocked, why = 0, False, ""
    ledger = set(_ledger())
    for item in pending()[:limit or 10 ** 9]:
        if float(item.get("next_try_at") or 0) > now:
            blocked = True                      # backing off. The queue waits; it does not reorder.
            why = item.get("last_error") or "waiting to retry"
            break
        if item["id"] in ledger:
            # Sent already, and the process died before the file was removed. Drop the file; do NOT
            # send it again. This is the crash window the ledger exists for.
            _drop(item["_path"])
            continue
        try:
            _send(client, item)
        except Exception as e:                  # noqa: BLE001 — every failure is the same failure here
            item["attempts"] = int(item.get("attempts") or 0) + 1
            item["last_error"] = str(e)[:300]
            item["next_try_at"] = now + BACKOFF_SECONDS[min(item["attempts"] - 1,
                                                            len(BACKOFF_SECONDS) - 1)]
            path = item.pop("_path")
            store.write_json(path, item)
            blocked, why = True, item["last_error"]
            break
        _remember(item["id"])                   # ledger FIRST, then the file. Never the other way.
        ledger.add(item["id"])
        _drop(item["_path"])
        sent += 1
    return {"sent": sent, "left": count(), "blocked": blocked, "why": why}


def _drop(path):
    try:
        os.remove(path)
    except OSError:
        pass


def status():
    """What the Connections tab shows: how much is waiting, and why the head of the queue is stuck."""
    items = pending()
    head = items[0] if items else None
    return {"queued": len(items),
            "oldest_at": head.get("queued_at") if head else None,
            "attempts": int(head.get("attempts") or 0) if head else 0,
            "last_error": (head.get("last_error") or "") if head else ""}


def clear():
    """Empty the queue and the ledger. For tests and for a workspace being left, nothing else."""
    for p in _files():
        _drop(p)
    _drop(_ledger_path())
