"""The needs-you feed contract (PLAN-100 S41, stub).

Now (the module) renders this feed; Shadow is one producer among several.
This stub owns the CONTRACT: schema validation + dedupe + append. Rendering
lands in P4; nothing here draws UI.
"""
import fcntl
import json
import os
import time

import shadow_ledger

REQUIRED = ("item_id", "producer", "kind", "title", "deep_link",
            "dedupe_key", "state")
#: `intervention_id` is the ONE addition the founder-intervention work makes
#: to this contract: a needs-you row can name the typed question waiting on
#: the mission, so opening the card lands on the right form. Optional, so
#: every existing producer and every existing row stays valid, and
#: validate() keeps rejecting anything else.
#: `ts` (2026-09-16): when the row was emitted. emit() stamps it; a row that
#: brings its own keeps it. The relevance rule below needs it for the one
#: time-bound card (a failed task).
OPTIONAL = ("mission_id", "thread_id", "severity", "why_now",
            "primary_action", "secondary_actions", "expires_at",
            "evidence_links", "intervention_id", "ts")
STATES = ("new", "seen", "handled", "expired")

# ── the relevance rule (founder 2026-09-16: "a lot of tasks in my Now, but
# they are not relevant") ────────────────────────────────────────────────
# A card lives only while its task exists and waits on the founder. Before
# this, feed.jsonl only ever grew: nothing set `expired`, no producer set
# `expires_at`, delete never touched the feed, and every state change of a
# task added a row. 23 cards for 14 tasks, 8 of them already deleted.
#
#: mission states in which the task is waiting on the founder, whatever
#: the pause reason
WAITING_STATES = ("brief_confirm", "blocked")
#: pause reasons that wait on the founder. founder_intervened (the founder
#: took over and knows) and autonomy_hold (L0, nothing to decide) are NOT
#: here (codex P2, 2026-09-16). app_restart IS: a relaunch pauses new-chat
#: tasks with a Resume the founder must press (SHADOW-V3 section 7a).
NEEDS_YOU_PAUSES = ("founder_confirm", "floor_confirm", "autonomy_suggest",
                    "autonomy_top_tier", "app_restart")
#: a failed task keeps its card this long from the row's ts, so the founder
#: sees the failure once; the task itself stays in the Focus > Shadow list
#: with its retry (codex P1 fold: hiding failed outright removed a real
#: recovery path). A legacy row without ts expires on first read.
FAILED_GRACE_SECS = 24 * 3600
#: a rescue row (a session hit an error) lives while a task in one of these
#: states still targets that session -- active ownership, not "any mission
#: ever" (codex P2).
OWNING_STATES = ("brief_confirm", "running", "paused", "blocked")

_MISSION_LINK = "sutra://shadow/mission/"
_SESSION_LINK = "sutra://shadow/session/"


def mission_of(item):
    """The mission a row is about: the field, else the deep link, else the
    `stall-<mid>` item id. None for rescue rows and foreign producers."""
    mid = item.get("mission_id")
    if mid:
        return mid
    link = str(item.get("deep_link") or "")
    if link.startswith(_MISSION_LINK):
        return link[len(_MISSION_LINK):] or None
    iid = str(item.get("item_id") or "")
    # the `stall-<mid>` id shape is Shadow's own; another producer's ids
    # mean nothing here (deepseek P2, 2026-09-16)
    if iid.startswith("stall-") and item.get("producer") == "shadow":
        return iid[len("stall-"):] or None
    return None


def session_of(item):
    """The session a rescue row is about, else None."""
    iid = str(item.get("item_id") or "")
    if iid.startswith("rescue-") and item.get("producer") == "shadow":
        return iid[len("rescue-"):] or None
    link = str(item.get("deep_link") or "")
    if link.startswith(_SESSION_LINK):
        return link[len(_SESSION_LINK):] or None
    return None


def relevant(item, store, now=None):
    """Does this row still wait on the founder? Pure: reads the store,
    writes nothing. A row about nothing Shadow owns (another producer, no
    mission, no session) cannot be judged and is kept."""
    if item.get("state") in ("handled", "expired"):
        return False
    if item.get("kind") != "needs_decision":
        return False
    now = time.time() if now is None else now
    sid = session_of(item)
    if sid:
        return any(m.get("target_session") == sid
                   for m in store.list(states=OWNING_STATES))
    mid = mission_of(item)
    if not mid:
        return True
    m = store.load(mid)
    if m is None:
        return False
    state = m.get("state")
    if str(item.get("item_id") or "").startswith("stall-"):
        return state == "running"
    if state in WAITING_STATES:
        return True
    if state == "paused":
        return (m.get("pause_reason") in NEEDS_YOU_PAUSES
                or bool(m.get("pending_say")))
    if state == "failed":
        ts = item.get("ts")
        return isinstance(ts, (int, float)) and (now - ts) < FAILED_GRACE_SECS
    return False


def _feed_path():
    d = os.path.join(os.path.realpath(os.path.expanduser(
        os.environ.get("SUTRA_SHADOW_HOME", "~/.sutra-ui/shadow"))))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "feed.jsonl")


def validate(item):
    """Return a list of contract violations (empty = valid)."""
    problems = []
    if not isinstance(item, dict):
        return ["item must be an object"]
    for k in REQUIRED:
        if not item.get(k):
            problems.append("missing required field: %s" % k)
    if item.get("state") and item["state"] not in STATES:
        problems.append("unknown state %r" % (item["state"],))
    unknown = set(item) - set(REQUIRED) - set(OPTIONAL)
    if unknown:
        problems.append("unknown fields: %s" % ", ".join(sorted(unknown)))
    return problems


def _rewrite(decide):
    """Rewrite feed.jsonl in place: `decide(row)` returns the row's new
    state or None to leave it. feed.jsonl is a working set, not a ledger:
    rewrite under the same exclusive lock emit() takes, via temp-file +
    rename so a crash mid-rewrite never truncates the feed. Rows are never
    dropped, only re-stated, so a dedupe_key keeps blocking its re-emit
    (codex P2, 2026-09-16). Returns (rows, changed_count); rows carry the
    new states. (rows, -1) when the file could not be read or written."""
    path = _feed_path()
    rows, changed = [], 0
    try:
        # deepseek fold: the lock lives on a SIDECAR file that is never
        # replaced -- flocking the data file's own fd would let a blocked
        # emit() append to the orphaned inode after os.replace (lost row)
        with open(path + ".lock", "a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                try:
                    with open(path, encoding="utf-8") as handle:
                        for line in handle:
                            try:
                                row = json.loads(line)
                            except ValueError:
                                continue
                            new = decide(row)
                            if new and new != row.get("state"):
                                row["state"] = new
                                changed += 1
                            rows.append(row)
                except OSError:
                    return rows, -1
                if changed:
                    tmp = path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as out:
                        for row in rows:
                            out.write(json.dumps(row) + "\n")
                        out.flush()
                        os.fsync(out.fileno())
                    os.replace(tmp, path)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    except OSError:
        return rows, -1
    return rows, changed


def mark_handled(item_id):
    """Retire ONE item (state -> handled) so the pill stops crying wolf.
    Idempotent. Returns True when a row actually changed."""
    def decide(row):
        if row.get("item_id") == item_id and row.get("state") != "handled":
            return "handled"
        return None
    _rows, changed = _rewrite(decide)
    return changed > 0


def retire(mission_id=None, session_id=None, keep_item_id=None,
           producer=None):
    """Expire every open row about a mission (or a session's rescue rows)
    except `keep_item_id`. Called when a task is deleted (every producer's
    rows: the task is gone), and by the mission emitter with
    producer="shadow" so a task carries ONE Shadow card, the latest
    state's, while another producer's card about it stays (deepseek P2).
    Handled rows stay handled. Returns the number of rows changed."""
    def decide(row):
        if row.get("state") in ("handled", "expired"):
            return None
        if keep_item_id and row.get("item_id") == keep_item_id:
            return None
        if producer and row.get("producer") != producer:
            return None
        if mission_id and mission_of(row) == mission_id:
            return "expired"
        if session_id and session_of(row) == session_id:
            return "expired"
        return None
    _rows, changed = _rewrite(decide)
    return max(changed, 0)


def live_items(store, now=None):
    """The rows Now (and the dot) may show: open rows that still wait on the
    founder per relevant(). Rows that no longer do are persisted as
    `expired` on the way out, under the same lock emit() and mark_handled()
    take, so the feed reflects the rule and a re-read is a pure read.
    `store` is a MissionStore (load + list); tests pass a dict-backed one."""
    now = time.time() if now is None else now
    live = []

    def decide(row):
        if row.get("state") in ("handled", "expired"):
            return None
        if relevant(row, store, now=now):
            live.append(row)
            return None
        return "expired"
    _rewrite(decide)
    return live


def emit(item):
    """Validate + dedupe + append. Returns (accepted, problems)."""
    if isinstance(item, dict) and "ts" not in item:
        item = dict(item, ts=time.time())
    problems = validate(item)
    if problems:
        return False, problems
    path = _feed_path()
    # scan-and-append under ONE lock (codex P2): two producers racing the
    # same dedupe_key must not both pass the scan and double-prompt the
    # founder. The lock lives on the sidecar (deepseek fold): the data file
    # gets replaced by mark_handled(), so its own fd is not a safe lock.
    with open(path + ".lock", "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            with open(path, "a+", encoding="utf-8") as handle:
                handle.seek(0)
                for line in handle:
                    try:
                        if json.loads(line).get("dedupe_key") \
                                == item["dedupe_key"]:
                            return False, ["duplicate dedupe_key"]
                    except ValueError:
                        continue
                handle.write(json.dumps(item) + "\n")
                handle.flush()
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return True, []
