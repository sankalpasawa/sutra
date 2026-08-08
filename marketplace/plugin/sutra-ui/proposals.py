"""proposals.py — what the chat agent ASKS for, and what the operator APPROVES.

The chat agent can now reach Sutra's own capabilities through an MCP tool
server (sutra_mcp.py). Reads it may do freely. MUTATIONS it may only PROPOSE.

WHY A PROPOSAL AND NOT A CALL

  Three reasons, and each one alone would be enough:

  1. NOBODY IS BLOCKING. A tool call that waits for a human approval in a
     non-interactive run either hangs the turn or is denied outright. A proposal
     returns instantly -- "PROPOSAL p-abc — awaiting approval in the panel" --
     so the agent finishes its turn and the operator decides afterwards, at
     leisure. Nothing is ever half-applied while someone is asked.

  2. THE PROMPT IS NOT ALWAYS THE OPERATOR. An agent acts on text, and text can
     come from a file, a web page, an issue tracker. "Create a routine that runs
     hourly forever" is a sentence, and a sentence must not be sufficient
     authority to install a scheduled job on someone's Mac.

  3. THE PORT IS UNAUTHENTICATED. Anything reachable over 127.0.0.1:8330 is
     reachable by any process on this machine. A proposal is INERT: writing one
     changes nothing, so the write side of this surface is worth nothing to an
     attacker. Only an approval clicked in the panel applies it.

WHAT A PROPOSAL IS NOT: a queue that drains itself. Nothing here applies on a
timer, on boot, or on the agent's say-so. An unapproved proposal simply expires.
"""
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
#: A proposal nobody acted on is stale, not pending. Anything older than this is
#: reported expired rather than sitting in the panel forever inviting a
#: distracted click days after the conversation that produced it.
TTL_SECONDS = 24 * 60 * 60

#: Every kind the agent may propose. A POSITIVE allow-list: a kind that is not
#: named here cannot be proposed at all, so adding a capability to the MCP
#: server is never enough on its own to make it applicable.
KINDS = (
    "routine.create",
    "routine.update",
    "routine.delete",
    "routine.run",
    # The first kind whose effect leaves this MACHINE. A routine is local; a pull
    # request pushes a branch and publishes to GitHub, where it is visible to
    # other people and cannot be quietly un-done. That makes the proposal gate
    # more necessary here than anywhere else it is already used, not less --
    # reason 2 in the module docstring (the prompt is not always the operator)
    # is the whole argument against a one-click Create PR button.
    "pr.create",
)


def store_dir():
    return Path(os.path.expanduser(
        os.environ.get("SUTRA_UI_PROPOSALS", "~/.sutra-ui/proposals")))


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


def _path(pid):
    return store_dir() / (pid + ".json")


def _write(rec):
    d = _mkdir()
    p = d / (rec["id"] + ".json")
    tmp = Path(str(p) + ".tmp")
    if tmp.exists():
        tmp.unlink()
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, (json.dumps(rec, indent=2) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(str(tmp), str(p))
    return rec


def create(kind, args, summary, session_id=None):
    """Record an intent. Applies NOTHING."""
    if kind not in KINDS:
        raise ValueError("unknown proposal kind %r -- one of: %s"
                         % (kind, ", ".join(KINDS)))
    rec = {
        "schema": SCHEMA,
        # Short and unguessable: it is quoted back to the agent, so it must be
        # readable, and it names a thing an approval acts on, so it must not be
        # predictable by something that can write to this directory.
        "id": "p-" + secrets.token_hex(4),
        "kind": kind,
        "args": args or {},
        # The agent's own one-line description. Shown to the operator VERBATIM
        # and never used to decide anything -- it is a label, not authority.
        "summary": str(summary or "")[:300],
        "session_id": session_id,
        "status": "pending",
        "created_at": _now(),
        "created_ms": int(time.time() * 1000),
        "decided_at": None,
        "result": None,
    }
    return _write(rec)


def get(pid):
    p = _path(pid)
    if not p.is_file():
        raise KeyError(pid)
    return json.loads(p.read_text(encoding="utf-8"))


def _expired(rec):
    return (rec.get("status") == "pending"
            and (time.time() * 1000 - (rec.get("created_ms") or 0)) > TTL_SECONDS * 1000)


def listing(include_decided=True):
    d = store_dir()
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("p-*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if _expired(rec):
            rec = dict(rec, status="expired")
        if not include_decided and rec["status"] != "pending":
            continue
        out.append(rec)
    out.sort(key=lambda r: r.get("created_ms") or 0, reverse=True)
    return out


def pending():
    return [r for r in listing() if r["status"] == "pending"]


def decide(pid, approve, apply_fn=None):
    """Approve or reject. APPLYING IS THE CALLER'S JOB -- this module never
    imports routines.py, so nothing here can mutate anything by itself even if
    it is called by mistake.

    An approval that fails to apply is recorded as `failed`, NOT rolled back to
    pending: the operator already said yes, and re-offering the same click would
    invite them to approve a thing that has already been tried and did not work.
    """
    rec = get(pid)
    if rec["status"] != "pending":
        raise ValueError("proposal %s is already %s" % (pid, rec["status"]))
    if _expired(rec):
        rec["status"] = "expired"
        _write(rec)
        raise ValueError("proposal %s expired before it was decided" % pid)

    rec["decided_at"] = _now()
    if not approve:
        rec["status"] = "rejected"
        return _write(rec)

    if apply_fn is None:
        raise ValueError("nothing was supplied to apply this proposal with")
    try:
        rec["result"] = apply_fn(rec["kind"], rec["args"])
        rec["status"] = "approved"
    except Exception as exc:                      # noqa: BLE001 -- reported, not swallowed
        rec["status"] = "failed"
        rec["result"] = {"error": str(exc)}
    return _write(rec)


def purge(older_than_s=7 * 24 * 60 * 60):
    """Housekeeping only. Never called automatically."""
    n = 0
    for rec in listing():
        if (time.time() * 1000 - (rec.get("created_ms") or 0)) > older_than_s * 1000:
            try:
                _path(rec["id"]).unlink()
                n += 1
            except OSError:
                pass
    return n
