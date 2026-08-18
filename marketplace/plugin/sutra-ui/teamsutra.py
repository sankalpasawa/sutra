"""teamsutra.py — durable task state for the Teamsutra feature.

WHAT A TASK IS. A record of one piece of work someone asked for from inside the
panel — usually via the Ask Sutra selection chat. It is DURABLE: unlike a
proposal (24h TTL, purged at 7 days, "an unapproved proposal simply expires"),
a filed task must survive nobody clicking. That is why this is not a
proposals.py kind: proposals stay the approval gate, this module is only the
task's memory. Neither module grows a second job.

WHY CREATION IS INERT. proposals.py grounds the security of the unauthenticated
127.0.0.1 port on every reachable write being inert. A task that an unattended
worker will later act on is NOT inert — so the agent-reachable write files at
status="draft", which no worker may claim. Only an operator moves draft ->
queued. One enum value instead of a parallel approval subsystem.

SHAPE. Copied from routines.py, the store whose SCHEMA is actually CHECKED on
load (a mismatch refuses rather than half-interprets). One JSON file per record
at ~/.sutra-ui/teamsutra/t-<8hex>.json (env override SUTRA_UI_TEAMSUTRA), dir
0700, records 0600, every write atomic via composio_store._write_json.

ORDERING. Strictly by the validated created_ms field, oldest first, id as the
tie-break. NEVER glob order: t-<8hex> names are random, so directory order is
not age order. A corrupt record is surfaced as status="corrupt" in listings and
skipped by claim ordering — one bad file must never halt the sweep.
"""
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import composio_store as cx

SCHEMA = 1
ID_RE = re.compile(r"^t-[0-9a-f]{8}$")

#: Full lifecycle. draft is the agent-filed inert state; only queued is
#: claimable; the two rightmost states are terminal.
STATUSES = ("draft", "queued", "claimed", "needs_review", "blocked", "failed", "done", "dropped")

#: The one transition an agent-reachable surface may perform is CREATING a
#: draft. Everything else is operator- or runner-driven, checked in set_status.
ALLOWED_TRANSITIONS = {
    "draft": ("queued", "dropped"),
    "queued": ("claimed", "draft", "dropped"),
    "claimed": ("needs_review", "blocked", "failed", "queued", "dropped"),
    "needs_review": ("done", "queued", "dropped"),
    "blocked": ("queued", "dropped"),
    "failed": ("queued", "dropped"),
    "done": (),
    "dropped": (),
}

TITLE_MAX = 200
BODY_MAX = 100_000
SELECTION_MAX = 4_000
MAX_ATTEMPTS_DEFAULT = 3


def store_dir():
    return Path(os.path.expanduser(os.environ.get("SUTRA_UI_TEAMSUTRA", "~/.sutra-ui/teamsutra")))


def _mkdir_private(p):
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    return p


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _new_id():
    return "t-" + secrets.token_hex(4)


def _path(tid):
    return store_dir() / (tid + ".json")


def validate_new(body):
    """Refuse everything refusable while the operator (or agent) is still
    present to be told. Returns the full record; raises ValueError with a
    plain-English reason otherwise."""
    if not isinstance(body, dict):
        raise ValueError("a task is a JSON object")
    title = (body.get("title") or "").strip()
    if not title or len(title) > TITLE_MAX:
        raise ValueError("title is required, 1-%d characters — it is the only "
                         "thing that makes a queue scannable" % TITLE_MAX)
    text = (body.get("body") or "").strip()
    if not text or len(text) > BODY_MAX:
        raise ValueError("body is required, 1-%d characters" % BODY_MAX)
    kind = body.get("kind") or "bug"
    if kind not in ("bug", "task", "question"):
        raise ValueError("kind must be bug, task or question, not %r" % kind)

    src = body.get("source") or {}
    if not isinstance(src, dict):
        raise ValueError("source must be an object")
    sel = (src.get("selection") or "")[:SELECTION_MAX]
    # A department may be null and MUST be null rather than guessed: a wrong
    # address is the failure the placement layer exists to remove.
    source = {
        "selection": sel,
        "screen": src.get("screen") or None,
        "domain_ref": src.get("domain_ref") or None,
        "domain_path": src.get("domain_path") or None,
        "domain_name": src.get("domain_name") or None,
        "charter_id": src.get("charter_id") or None,
        "session_id": src.get("session_id") or None,
    }

    verify = (body.get("verify") or "").strip()
    if verify in ("works", "passes", "done", "no errors", "it runs"):
        raise ValueError("verify %r proves nothing — give a runnable command, "
                         "or leave it empty" % verify)

    now = now_iso()
    return {
        "schema": SCHEMA,
        "id": _new_id(),
        "title": title,
        "body": text,
        "kind": kind,
        "status": "draft",
        "source": source,
        "verify": verify,
        "diff": None,                 # the worker's output: a unified diff, or None
        "blocked_reason": None,
        "last_error": None,
        "attempts": 0,
        "max_attempts": int(body.get("max_attempts") or MAX_ATTEMPTS_DEFAULT),
        "runs": [],
        "proposal_id": None,
        "created_at": now,
        "updated_at": now,
        "created_ms": int(time.time() * 1000),
    }


def _write(rec):
    _mkdir_private(store_dir())
    cx._write_json(_path(rec["id"]), rec)


def create(body):
    rec = validate_new(body)
    _write(rec)
    return rec


def load(tid):
    """Load one record. Refuses a schema mismatch rather than half-interpreting
    it — the reader that guesses is the reader that corrupts."""
    if not ID_RE.match(tid or ""):
        raise ValueError("not a task id: %r" % tid)
    p = _path(tid)
    if not p.exists():
        raise FileNotFoundError(tid)
    rec = cx._read_json(p, {})
    if not rec:
        # The file exists but did not parse as a dict — that is corruption,
        # and the caller (listing) surfaces it as such rather than "missing".
        raise ValueError("task %s exists but does not parse as a record" % tid)
    if rec.get("schema") != SCHEMA:
        raise ValueError("task %s has schema %r; this build understands %d. "
                         "Refusing to half-interpret it." % (tid, rec.get("schema"), SCHEMA))
    return rec


def listing():
    """Every record, oldest first by created_ms (id tie-break). A file that
    does not parse or fails the schema check appears as status='corrupt' with
    its filename — visible, never silently dropped, never fatal."""
    d = store_dir()
    out = []
    if not d.is_dir():
        return out
    for p in d.glob("t-*.json"):
        tid = p.stem
        try:
            out.append(load(tid))
        except Exception as e:
            out.append({"schema": SCHEMA, "id": tid, "status": "corrupt",
                        "title": "(unreadable: %s)" % e, "created_ms": 0,
                        "created_at": None, "updated_at": None})
    out.sort(key=lambda r: (r.get("created_ms") or 0, r.get("id") or ""))
    return out


def claimable():
    """The queue as the worker sees it: queued only, oldest first, corrupt
    records excluded (they are already visible in listing())."""
    return [r for r in listing() if r.get("status") == "queued"]


def set_status(tid, new, **fields):
    """One guarded transition. Raises on anything ALLOWED_TRANSITIONS forbids,
    so an illegal move is a loud error rather than a quiet corruption."""
    rec = load(tid)
    cur = rec["status"]
    if new not in STATUSES:
        raise ValueError("unknown status %r" % new)
    if new not in ALLOWED_TRANSITIONS.get(cur, ()):
        raise ValueError("a task cannot go %s -> %s" % (cur, new))
    rec["status"] = new
    for k in ("diff", "blocked_reason", "last_error", "proposal_id"):
        if k in fields:
            rec[k] = fields[k]
    if new == "claimed":
        rec["attempts"] = int(rec.get("attempts") or 0) + 1
    if fields.get("run_row"):
        rec["runs"] = (rec.get("runs") or [])[-19:] + [fields["run_row"]]
    rec["updated_at"] = now_iso()
    _write(rec)
    return rec


def drop(tid):
    return set_status(tid, "dropped")


#: task.apply provenance — the ONLY keys record_apply_result may write.
#: pr_url/pr_state/applied_at land on success; apply_error on failure. Nothing
#: here can move status: a failed apply stays at needs_review by design, so the
#: transition table above ships byte-identical (APPLY-DESIGN v1.1 D-A1).
APPLY_RESULT_FIELDS = ("pr_url", "pr_state", "applied_at", "apply_error")


def record_apply_result(tid, **extra):
    """Allowlisted field update with NO transition. The apply failure path must
    persist provenance without weakening the guarded store, so anything outside
    APPLY_RESULT_FIELDS is refused — id/status/attempts are unreachable here."""
    bad = sorted(set(extra) - set(APPLY_RESULT_FIELDS))
    if bad:
        raise ValueError("record_apply_result refuses non-allowlisted fields: %s"
                         % ", ".join(bad))
    rec = load(tid)
    rec.update(extra)
    rec["updated_at"] = now_iso()
    _write(rec)
    return rec
