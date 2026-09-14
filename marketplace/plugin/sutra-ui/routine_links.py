"""routine_links.py -- which chat belongs to which routine.

WHY THIS EXISTS
A routine run IS a chat. `claude -p --output-format json` writes a real
transcript and reports the thread it used, and routines.py has stored that
`session_id` in every run's output since the beginning (routines.py:1073 --
"EVERY HISTORICAL RUN IS ALREADY RESUMABLE"). So the rail was already listing
these conversations; it just had no way to say that a routine produced them,
and they sat among hand-started chats looking identical. Founder, 2026-09-13:
show them as their own section.

THE JOIN IS session_id -> routine, AND IT IS ONE-WAY. A run names its session;
a session does not name its run. So the map is built from the runs tree and
then read by id, never the other way round.

WHERE THE DATA IS
    ~/.sutra-ui/runs/<routine-id>/index.jsonl   one row per run (cheap)
    ~/.sutra-ui/runs/<routine-id>/<stamp>.out   the raw claude JSON (has the id)

The index alone is not enough: `session_id` lives inside the .out blob, so the
map costs one small read per run. Measured on the founder's disk: 1,206 runs in
206 ms cold. That is too much to pay on every rail refresh and nothing like
enough to justify a database, so it is cached and invalidated on the mtime of
the index files -- a new run appends there, which is exactly the event that
makes the map stale.

FAILS SOFT, ALWAYS. A missing runs tree, an unreadable run, a truncated JSON
blob: each yields "no routine for this session", never an error. The rail must
render whatever state the routines are in -- and on this machine a third of the
runs have failed, so half-written outputs are the normal case, not the edge.
"""
import json
import os
from pathlib import Path

#: Where routines.py's runner writes each run. NOT ~/.sutra-ui/routines/runs --
#: that path looks right and does not exist; the runner's plists point here.
RUNS_DIR = Path(os.path.expanduser(
    os.environ.get("SUTRA_UI_RUNS", "~/.sutra-ui/runs")))

#: Cache: {"stamp": <mtime signature>, "map": {session_id: {...}}}
_CACHE = {"stamp": None, "map": {}}


def _stamp(root):
    """A signature that changes when any routine records a new run.

    Built from the index files only -- one stat per routine rather than per
    run. A run appends to its index, so the mtime moves; nothing else needs
    watching."""
    sig = []
    try:
        for d in sorted(root.iterdir()):
            idx = d / "index.jsonl"
            try:
                sig.append((d.name, int(idx.stat().st_mtime), idx.stat().st_size))
            except OSError:
                continue
    except OSError:
        return None
    return tuple(sig)


def _read_runs(routine_dir):
    """Every run in one routine's directory as {session_id: row}.

    The index supplies the run's OUTCOME and time; the .out blob supplies the
    session id. Both are needed and they live in different files, so the index
    is read first (one file) and only its named outputs are opened."""
    out = {}
    idx = routine_dir / "index.jsonl"
    rows = []
    try:
        with open(idx, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue                    # a torn line is one lost run
    except OSError:
        return out

    for row in rows:
        name = row.get("output_file")
        if not name:
            continue
        try:
            with open(routine_dir / name, "r", encoding="utf-8",
                      errors="replace") as fh:
                blob = json.load(fh)
        except (OSError, ValueError):
            continue                            # a failed run may write no JSON
        if not isinstance(blob, dict):
            continue
        sid = blob.get("session_id")
        if not sid:
            continue
        out[sid] = {
            "routine": routine_dir.name,
            "outcome": row.get("outcome"),
            "started_at": row.get("started_at"),
            "duration_s": row.get("duration_s"),
            "trigger": row.get("trigger"),
        }
    return out


def by_session(runs_dir=None, _force=False):
    """{session_id: {routine, outcome, started_at, ...}} for every recorded run.

    Cached on the runs tree's index mtimes, so a rail refresh that changes
    nothing costs one stat per routine instead of a read per run."""
    root = Path(runs_dir) if runs_dir else RUNS_DIR
    stamp = _stamp(root)
    if stamp is None:
        return {}
    if not _force and _CACHE["stamp"] == stamp:
        return _CACHE["map"]
    merged = {}
    try:
        for d in sorted(root.iterdir()):
            if d.is_dir():
                merged.update(_read_runs(d))
    except OSError:
        return _CACHE["map"] if _CACHE["stamp"] else {}
    _CACHE["stamp"], _CACHE["map"] = stamp, merged
    return merged


def summary(runs_dir=None):
    """{routine: {runs, ok, failed}} straight from the indexes.

    Cheap (no .out reads) because it answers a different question: how is each
    routine DOING. The panel shows it beside the routine's chats, because a
    routine that has failed every time it ever ran should not look the same as
    one that works -- daily-leetcode-cp has 38 runs and 0 successes on the
    founder's machine, and nothing in the app said so."""
    root = Path(runs_dir) if runs_dir else RUNS_DIR
    out = {}
    try:
        dirs = sorted(d for d in root.iterdir() if d.is_dir())
    except OSError:
        return out
    for d in dirs:
        runs = ok = failed = 0
        try:
            with open(d / "index.jsonl", "r", encoding="utf-8",
                      errors="replace") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    runs += 1
                    oc = row.get("outcome")
                    if oc in ("ok", "success"):
                        ok += 1
                    elif oc:
                        failed += 1
        except OSError:
            continue
        if runs:
            out[d.name] = {"runs": runs, "ok": ok, "failed": failed}
    return out


def attach(rows, runs_dir=None):
    """Tag each session row with the routine run that produced it, or None.

    Same shape and same soft-failure contract as the department join in app.py:
    a row that belongs to no routine carries `routine: None`, which is a stated
    answer rather than a missing key."""
    try:
        m = by_session(runs_dir)
    except Exception:                                      # noqa: BLE001
        return rows
    if not m:
        for r in rows:
            r.setdefault("routine", None)
        return rows
    for r in rows:
        r["routine"] = m.get(r.get("id")) or None
    return rows
