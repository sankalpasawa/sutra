"""switch_egress.py -- scrub a replay payload on its way out, and leave a
record that it happened.

WHY THE LOG IS NOT OPTIONAL
The founder chose SILENT scrubbing (decision D3): no dialog, no confirmation,
the switch just happens. That is a reasonable UX call and it has one
consequence that has to be paid for somewhere -- nobody is looking at the
moment a secret does or does not leave the machine. A scrubber that silently
misses is indistinguishable from a scrubber that silently worked. So the
compensating control is an append-only record of every switch: what left, how
big it was, which credential SHAPES were caught, and whether the payload was
sent at all.

WHAT IS NEVER WRITTEN
The payload. The redacted values. The matched substrings. A log that recorded
what it caught would be a second plaintext copy of every secret the scrubber
found, sitting in a file that exists precisely because nobody is watching. The
row records shape NAMES and counts -- "one jwt, two openai-key" -- which is
everything an auditor needs to know something was there and nothing they could
use.

ORDER OF OPERATIONS, AND WHY IT IS THIS WAY

    render -> scrub -> re-verify the fence -> send

The fence check runs AFTER scrubbing, not before, because scrubbing is the
last thing that mutates the payload and a boundary verified before the final
mutation is not verified. (Redaction cannot forge a fence marker -- the
placeholder is a fixed string -- but "cannot" is exactly the class of claim
this codebase checks rather than asserts.)

Reads:  nothing.
Writes: one append-only JSONL file, 0600, under ~/.sutra-ui.
"""
import fcntl
import json
import os
import time
import uuid

import replay
import shadow_egress

#: One line per switch attempt. Its own file rather than a row in Shadow's
#: ledger: shadow_ledger.KINDS is a closed set gated on Shadow's own flag
#: (providers.shadow_enabled), and provider switching must be auditable on a
#: machine where Shadow is turned off.
DEFAULT_LOG = "~/.sutra-ui/switch-egress.jsonl"

#: A row is metadata, never content, so it has no business being large. A cap
#: catches a caller who starts putting a payload in one.
MAX_ROW_BYTES = 8192


def log_path():
    return os.path.realpath(os.path.expanduser(
        os.environ.get("SUTRA_UI_SWITCH_EGRESS", DEFAULT_LOG)))


def _open_append(path):
    """0600 enforced with fchmod AFTER open, for the reason json_store spells
    out: O_CREAT's mode is ignored when the file already exists, so a file
    created world-readable by something else would keep those bits."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.fchmod(fd, 0o600)
    except (OSError, AttributeError):
        pass
    return os.fdopen(fd, "a", encoding="utf-8")


def record(row):
    """Append one audit row; returns the stamped row.

    NEVER RAISES on a write failure. An unwritable log must not stop a switch
    the operator asked for -- but it must not be invisible either, so the
    failure is reported in the returned row under "log_error" and the caller
    surfaces it. Silently swallowing it would defeat the whole point of having
    a compensating control.
    """
    row = dict(row if isinstance(row, dict) else {})
    row.setdefault("id", "sw-%s" % uuid.uuid4().hex[:12])
    row.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    line = json.dumps(row, sort_keys=True) + "\n"
    if len(line.encode("utf-8")) > MAX_ROW_BYTES:
        row = {"id": row["id"], "ts": row["ts"],
               "log_error": "row exceeded %d bytes and was not written; a row "
                            "is metadata, never payload" % MAX_ROW_BYTES}
        line = json.dumps(row, sort_keys=True) + "\n"
    try:
        with _open_append(log_path()) as fh:
            # O_APPEND plus flock, matching shadow_ledger: the panel and the
            # MCP child can both be running, and interleaved half-lines would
            # make the file unreadable for exactly the audit it exists for.
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.write(line)
                fh.flush()
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        row["log_error"] = "could not write %s: %s" % (log_path(), exc)
    return row


def scrub_payload(text):
    """(clean, {shape: count}) for one outbound payload.

    Delegates to shadow_egress rather than carrying its own pattern list --
    two credential pattern lists in one codebase drift, and the one that drifts
    is always the one nobody is looking at.
    """
    return shadow_egress.scrub_detail(text or "")


def prepare(plan_result, log=True):
    """Scrub a switch plan's payload and audit it. Returns a NEW result dict.

    On success the returned dict carries `payload` already scrubbed, plus
    `redactions` and `audit`. If scrubbing breaks the data/instruction boundary
    the switch is REFUSED here -- the payload is dropped and the refusal is
    logged with sent=False, because a payload whose fence cannot be trusted is
    worse than no switch.
    """
    if not plan_result or not plan_result.get("switch"):
        return plan_result

    raw = plan_result.get("payload") or ""
    clean, counts = scrub_payload(raw)

    out = dict(plan_result)
    out["payload"] = clean
    out["redactions"] = counts
    out["redaction_count"] = sum(counts.values())
    out["chars"] = len(clean)
    out["chars_before_scrub"] = len(raw)

    # Re-verify AFTER the last mutation. See the module header.
    fence_ok = replay.fence_is_intact(
        {"prompt": clean, "nonce": plan_result.get("nonce")})

    row = _audit_row(out, sent=fence_ok, fence_ok=fence_ok)
    if log:
        row = record(row)
    out["audit"] = row
    if row.get("log_error"):
        out["log_error"] = row["log_error"]

    if not fence_ok:
        return {
            "switch": False,
            "reason": "fence-integrity-failed-after-scrub",
            "detail": ("redaction disturbed the boundary that keeps replayed "
                       "file contents from being read as instructions, so "
                       "nothing was sent."),
            "source": out.get("source"), "target": out.get("target"),
            "audit": row,
        }
    return out


def _audit_row(result, sent, fence_ok):
    """Metadata only. Deliberately does not accept the payload as an argument,
    so a future edit cannot pass it in by accident."""
    budget = result.get("budget") or {}
    return {
        "event": "provider-switch",
        "sutra_id": result.get("sutra_id"),
        "source": result.get("source"),
        "source_session": result.get("source_session"),
        "target": result.get("target"),
        "from_turn": result.get("from_turn"),
        "tier": result.get("tier"),
        "turns": result.get("turns"),
        "user_turns": result.get("user_turns"),
        "chars": result.get("chars"),
        "chars_before_scrub": result.get("chars_before_scrub"),
        # Shape names and counts. Never values -- see the module header.
        "redactions": result.get("redactions") or {},
        "redaction_count": result.get("redaction_count", 0),
        "dropped": {k: v for k, v in (result.get("dropped") or {}).items() if v},
        "window_tokens": budget.get("window_tokens"),
        "window_source": budget.get("window_source"),
        "fence_ok": bool(fence_ok),
        "argv_unsafe": result.get("argv_unsafe"),
        "sent": bool(sent),
    }


def read(limit=50):
    """The most recent rows, newest last. For diagnostics and tests; the panel
    has no reason to render this yet."""
    try:
        with open(log_path(), "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    out = []
    for line in lines[-int(max(limit, 0)):]:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out
