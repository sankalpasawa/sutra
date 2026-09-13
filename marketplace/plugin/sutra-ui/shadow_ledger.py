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


DEFAULT_HOME = "~/.sutra-ui/shadow"


def shadow_home():
    """The shadow home, resolved at CALL time: SUTRA_SHADOW_HOME or the
    default. The one resolver for every Shadow store (ledgers here, the
    mission files, the watch lists) so they can never disagree.

    REFUSES THE DEFAULT HOME UNDER PYTEST. On 2026-09-08..12 whole-directory
    test runs wrote 34 "floor choke fixture" missions and 57 "unwatch fake-*"
    ledger rows into the operator's live home: nineteen test modules pop
    SUTRA_SHADOW_HOME at teardown, so every module that only set it at import
    time (test_shadow_floor_choke, test_shadow_chat_publication) ran against
    the real files once one of those ran first. Same failure class as the
    registry reset (lib/placement_engine.py, 2.264.0) and the same answer:
    while pytest is running a test and the home still resolves to the
    default, raise instead of writing. A deliberate integration test says so
    with SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS=1 (the smoke cycle does).
    """
    home = os.path.expanduser(os.environ.get("SUTRA_SHADOW_HOME") or DEFAULT_HOME)
    if os.environ.get("PYTEST_CURRENT_TEST") \
            and os.environ.get("SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS") != "1" \
            and os.path.realpath(home) == os.path.realpath(
                os.path.expanduser(DEFAULT_HOME)):
        raise RuntimeError(
            "shadow_ledger: refusing to touch the live shadow home %s from a "
            "test (%s). Set SUTRA_SHADOW_HOME to a temp dir (conftest.py does; "
            "a teardown that pops it is re-asserted before the next test), or "
            "declare a deliberate integration test with "
            "SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS=1."
            % (home, os.environ.get("PYTEST_CURRENT_TEST")))
    return home


def _home():
    return shadow_home()


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


def read_latest(kind):
    """EVERY row of one kind, folded to the last writer per id.

    Instructions are supersede-by-id, so a last-N-LINES tail is wrong for
    them: per-chat rows dilute the window until confirmed global rules
    silently age out and old rows become unrevokeable (codex P1
    2026-08-26). Actions/missions keep using the cheap tail.
    """
    path = _path(kind)
    latest = {}
    order = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                rid = row.get("id")
                if not rid:
                    continue
                if rid not in latest:
                    order.append(rid)
                latest[rid] = row
    except OSError:
        return []
    return [latest[r] for r in order]


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
