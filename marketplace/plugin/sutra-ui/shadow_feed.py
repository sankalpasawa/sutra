"""The needs-you feed contract (PLAN-100 S41, stub).

Now (the module) renders this feed; Shadow is one producer among several.
This stub owns the CONTRACT: schema validation + dedupe + append. Rendering
lands in P4; nothing here draws UI.
"""
import fcntl
import json
import os

import shadow_ledger

REQUIRED = ("item_id", "producer", "kind", "title", "deep_link",
            "dedupe_key", "state")
OPTIONAL = ("mission_id", "thread_id", "severity", "why_now",
            "primary_action", "secondary_actions", "expires_at",
            "evidence_links")
STATES = ("new", "seen", "handled", "expired")


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


def mark_handled(item_id):
    """Retire ONE item (state -> handled) so the pill stops crying wolf.
    feed.jsonl is a working set, not a ledger: rewrite-in-place under the
    same exclusive lock emit() takes, via temp-file + rename so a crash
    mid-rewrite never truncates the feed. Idempotent. Returns True when a
    row actually changed."""
    path = _feed_path()
    changed = False
    try:
        # deepseek fold: the lock lives on a SIDECAR file that is never
        # replaced -- flocking the data file's own fd would let a blocked
        # emit() append to the orphaned inode after os.replace (lost row)
        with open(path + ".lock", "a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                rows = []
                try:
                    with open(path, encoding="utf-8") as handle:
                        for line in handle:
                            try:
                                row = json.loads(line)
                            except ValueError:
                                continue
                            if row.get("item_id") == item_id \
                                    and row.get("state") != "handled":
                                row["state"] = "handled"
                                changed = True
                            rows.append(row)
                except OSError:
                    return False
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
        return False
    return changed


def emit(item):
    """Validate + dedupe + append. Returns (accepted, problems)."""
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
