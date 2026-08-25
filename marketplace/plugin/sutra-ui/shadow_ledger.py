"""Shadow's append-only memory (PLAN-100 S34).

Three JSONL ledgers -- instructions, missions, actions -- under the shadow
home. Append-only by construction: this module exposes no rewrite, and rows
get an id and timestamp stamped at append. This is Shadow's OWN inert
memory: appending a row schedules nothing, installs nothing, changes no app
behavior -- which is why a write tool is admissible in a propose-only MCP
server (the distinction the server's docstring draws).
"""
import fcntl
import json
import os
import time
import uuid

KINDS = ("instructions", "missions", "actions")

#: One row is memory, not storage. A row larger than this is a bug or an
#: exfiltration attempt; either way it is refused, not truncated.
MAX_ROW_BYTES = 8192


def _home():
    return os.path.expanduser(
        os.environ.get("SUTRA_SHADOW_HOME", "~/.sutra-ui/shadow"))


def _path(kind):
    if kind not in KINDS:
        raise ValueError("unknown ledger kind %r" % (kind,))
    home = os.path.realpath(_home())
    d = os.path.join(home, "ledger")
    os.makedirs(d, exist_ok=True)
    path = os.path.realpath(os.path.join(d, kind + ".jsonl"))
    # containment after symlink resolution: an env override or a planted
    # symlink must not walk the append outside the shadow home
    if not path.startswith(home + os.sep):
        raise ValueError("ledger path escapes the shadow home")
    return path


def append(kind, row):
    """Append one row; returns the stamped row. Raises on a non-dict."""
    if not isinstance(row, dict):
        raise ValueError("ledger row must be an object")
    row = dict(row)
    row.setdefault("id", "%s-%s" % (kind[:4], uuid.uuid4().hex[:12]))
    row.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    line = json.dumps(row) + "\n"
    if len(line.encode("utf-8")) > MAX_ROW_BYTES:
        raise ValueError("ledger row exceeds %d bytes" % MAX_ROW_BYTES)
    # O_APPEND + flock: the MCP child and the app can both append; interleaved
    # half-lines would blind read() forever
    with open(_path(kind), "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(line)
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return row


def read(kind, limit=50):
    """Last `limit` rows, oldest first. Malformed lines are skipped, never
    fatal -- a torn write must not blind every later read."""
    try:
        with open(_path(kind), encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return []
    rows = []
    for line in lines[-int(limit):]:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows
