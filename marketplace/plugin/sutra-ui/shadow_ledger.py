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
import sys
import time
import uuid

KINDS = ("instructions", "missions", "actions")

#: One row is memory, not storage. A row larger than this is a bug or an
#: exfiltration attempt; either way it is refused, not truncated.
MAX_ROW_BYTES = 8192


DEFAULT_HOME = "~/.sutra-ui/shadow"

#: The plugin version a row was written by, resolved once per process.
#:
#: NOT A NEW RESOLVER. modules_registry.plugin_version() already reads
#: ../.claude-plugin/plugin.json and is what modules_api reports; a second
#: reader of the same file is a second thing that can disagree with the first,
#: which is the failure the shadow_home() docstring above exists to avoid.
#:
#: NO ENV OVERRIDE, deliberately. electron/main.js builds the backend env as
#: {...process.env, ...shellEnv()} -- the user's login shell wins -- so a stale
#: `export SUTRA_UI_VERSION=` in someone's .zshrc would stamp every row in the
#: desktop app with a lie. Making `pid` unforgeable while leaving `build`
#: forgeable by a dotfile would defeat the point of stamping either.
#:
#: Cached because the value is constant within a process. updates.py can
#: replace the bundle under a running process, which makes the cache stale --
#: acceptable, since that process is about to be replaced by the one it staged.
_BUILD = {"id": None}


def build_id():
    """The build that wrote this row. Never raises, never empty.

    Imported lazily: shadow_ledger is imported by every sutra_mcp.py child (one
    per Claude session), and none of them should pay for the registry module to
    append a row.
    """
    if _BUILD["id"] is None:
        try:
            import modules_registry
            _BUILD["id"] = str(modules_registry.plugin_version() or "unknown")
        except Exception:               # noqa: BLE001 -- a provenance stamp is
            _BUILD["id"] = "unknown"    # never a reason to fail the write
    return _BUILD["id"]


def running_under_test():
    """Is this process a test run, whatever runner started it?

    THREE SIGNALS, because there are three ways this repo runs tests and the
    guard below must not depend on which one somebody chose:

      * PYTEST_CURRENT_TEST   pytest, per-test
      * the entry module      `python -m unittest ...` and `python -m pytest`
                              both leave their own __main__ in sys.argv[0]
      * a test file as argv   `python3 test_shadow_x.py`

    NEVER RAISES. A detector that threw would take down the very writes it
    exists to protect.
    """
    try:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return True
        argv = [str(a) for a in (sys.argv or [])]
        if argv:
            entry = os.path.basename(argv[0])
            if entry in ("unittest", "__main__.py", "pytest", "py.test"):
                mod = str(getattr(sys.modules.get("__main__"), "__file__", ""))
                if entry != "__main__.py" or "unittest" in mod \
                        or "pytest" in mod:
                    return True
            if entry.startswith("test_"):
                return True
        return any(os.path.basename(a).startswith("test_") for a in argv[1:])
    except Exception:                    # noqa: BLE001 -- see docstring
        return False


def shadow_home():
    """The shadow home, resolved at CALL time: SUTRA_SHADOW_HOME or the
    default. The one resolver for every Shadow store (ledgers here, the
    mission files, the watch lists) so they can never disagree.

    REFUSES THE DEFAULT HOME UNDER ANY TEST RUNNER. On 2026-09-08..12 whole-directory
    test runs wrote 34 "floor choke fixture" missions and 57 "unwatch fake-*"
    ledger rows into the operator's live home: nineteen test modules pop
    SUTRA_SHADOW_HOME at teardown, so every module that only set it at import
    time (test_shadow_floor_choke, test_shadow_chat_publication) ran against
    the real files once one of those ran first. Same failure class as the
    registry reset (lib/placement_engine.py, 2.264.0) and the same answer:
    while pytest is running a test and the home still resolves to the
    default, raise instead of writing. A deliberate integration test says so
    with SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS=1 (the smoke cycle does).

    ...AND UNDER `unittest`, WHICH IT DID NOT (founder, 2026-09-21). The
    guard keyed on PYTEST_CURRENT_TEST alone, so it fired for `pytest` and
    was INERT for `python3 -m unittest`. Measured: fourteen fixture missions
    -- "ten greatest riders", "ten riders", "x" -- written into the live home
    across four unittest runs, every one of them left `paused` with
    `pause_reason: founder_confirm`, so they piled up in the founder's
    WAITING ON YOU list as tasks they had never started.

    That is the SAME failure this guard was written for, arriving through the
    one runner it did not watch. `running_under_test()` now asks the question
    the guard always meant to ask -- "is this a test process?" -- rather than
    "is this pytest?".
    """
    home = os.path.expanduser(os.environ.get("SUTRA_SHADOW_HOME") or DEFAULT_HOME)
    if running_under_test() \
            and os.environ.get("SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS") != "1" \
            and os.path.realpath(home) == os.path.realpath(
                os.path.expanduser(DEFAULT_HOME)):
        raise RuntimeError(
            "shadow_ledger: refusing to touch the live shadow home %s from a "
            "test (%s). Set SUTRA_SHADOW_HOME to a temp dir (conftest.py does; "
            "a teardown that pops it is re-asserted before the next test), or "
            "declare a deliberate integration test with "
            "SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS=1."
            % (home, os.environ.get("PYTEST_CURRENT_TEST") or "unittest"))
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
    """Append one row; returns the stamped row. Raises on a non-dict.

    EVERY ROW NAMES THE PROCESS AND BUILD THAT WROTE IT (founder,
    2026-09-16). A row recorded WHAT happened and never WHO wrote it, and this
    home has many writers: the app, and one sutra_mcp.py child per Claude
    session. When five app boots drove one mission concurrently, the only way
    to establish which process wrote which row was to reconstruct it by hand
    from transcript timestamps. This is that, recorded at the source.

    ASSIGNED, NOT setdefault, and the difference is the whole point:
      * app.py's instruction confirm/revoke re-appends `dict(rows[-1])`, so a
        setdefault would carry the ORIGINAL capture's pid onto a write made
        by a different process minutes or days later;
      * sutra_mcp.py exposes append to a worker with a caller-supplied row, so
        a setdefault would let a delegate forge its own provenance.
    A stamp that can be inherited or supplied is not provenance.
    """
    if not isinstance(row, dict):
        raise ValueError("ledger row must be an object")
    row = dict(row)
    row.setdefault("id", "%s-%s" % (kind[:4], uuid.uuid4().hex[:12]))
    row.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    # THE CALLER'S ROW IS WHAT THE LIMIT IS ABOUT -- measured before the stamp
    # goes on. MAX_ROW_BYTES says "one row is memory, not storage", which is a
    # statement about what a caller may hand us; charging the caller for ~40
    # bytes of our own bookkeeping would quietly move that bar and could fail
    # a lifecycle write (most call sites do not wrap append in try/except).
    line = json.dumps(row) + "\n"
    if len(line.encode("utf-8")) > MAX_ROW_BYTES:
        raise ValueError("ledger row exceeds %d bytes" % MAX_ROW_BYTES)
    row["pid"] = os.getpid()
    row["build"] = build_id()
    line = json.dumps(row) + "\n"
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


def read_for_mission(kind, mission_id, limit=50):
    """Last `limit` rows OF ONE MISSION, oldest first.

    THE LEAK THIS CLOSES (founder, 2026-09-21). `read("actions", 10)` returns
    the last ten rows written by ANY mission, and `shadow_session.
    standing_context` put them in the boot context of EVERY task chat. So a
    Europe trip mission booted holding the MotoGP mission's judge verdicts,
    its criteria and the artifacts they named -- and the task chat, which
    writes the worker's brief, duly wrote about them. Observed verbatim on
    the founder's install: "The one real signal about this founder in the
    workspace is MotoGP - two artifacts from this week".

    THE LEDGER IS GLOBAL BY DESIGN and that is correct: it is one audit log
    for the whole of Shadow. What was wrong was READING it unscoped and
    calling the result context. A row carries `mission_id`, so the scope was
    always available -- nothing asked for it.

    ROWS WITH NO mission_id ARE NOT THIS MISSION'S. A boot row, a spawn with
    no mission attached, a global housekeeping row: none of them is about the
    work, and admitting them "because they are not another mission's" is how
    a scope boundary erodes. Only an exact id match counts.

    SCANS A BOUNDED TAIL. A mission's own rows are recent by construction, so
    reading the last SCAN_TAIL rows and filtering is enough without turning
    every boot into a full-file scan.
    """
    mission_id = str(mission_id or "").strip()
    if not mission_id:
        return []
    rows = read(kind, SCAN_TAIL)
    mine = [r for r in rows
            if str((r or {}).get("mission_id") or "") == mission_id]
    return mine[-int(limit):] if limit else mine


#: How far back read_for_mission looks before filtering. Generous enough that
#: a mission's own rows survive interleaving with other missions', bounded so
#: a boot never reads an unbounded file.
SCAN_TAIL = 500


def read(kind, limit=50):
    """Last `limit` rows, oldest first. Malformed lines are skipped, never
    fatal -- a torn write must not blind every later read.

    UNSCOPED, AND CALLERS MUST KNOW THAT. This returns rows from every
    mission. For anything that becomes CONTEXT for one mission, use
    `read_for_mission` -- see the leak note there.
    """
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
