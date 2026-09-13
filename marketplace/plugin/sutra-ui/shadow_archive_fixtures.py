#!/usr/bin/env python3
"""shadow_archive_fixtures.py -- move test debris out of a live Shadow home.

Whole-directory test runs between 2026-09-08 and 2026-09-12 wrote fixture
missions and fixture watch ids into the operator's real ~/.sutra-ui/shadow
(see shadow_ledger.shadow_home for the mechanism and the guard that stops it
recurring). This moves that debris aside. Nothing is deleted: mission files
go to missions/archive/<ts>/, the watch lists are rewritten with a
.bak-<ts> copy beside them, and the append-only ledgers are NOT rewritten
(counts are reported so the reader knows what is in there).

Dry-run by default. `--apply` writes.

    python3 shadow_archive_fixtures.py            # report
    python3 shadow_archive_fixtures.py --apply    # move + rewrite

Criteria are deliberately narrow (codex P2, 2026-09-13): a fixture TARGET
prefix, or the one known fixture objective verbatim. A real mission whose
objective merely mentions fixtures is not touched.
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import shadow_ledger  # noqa: E402

#: session ids only the test fakes mint (each test file names its own)
FIXTURE_TARGET_PREFIXES = ("fake-", "delegate-fake-", "runner-fake-",
                           "say-fake-", "shadow-fake-", "pubfake-",
                           "floor-choke-")
#: exact objectives, lower-cased; test_shadow_floor_choke.py:91
FIXTURE_OBJECTIVES = ("floor choke fixture",)


def is_fixture_sid(sid):
    return str(sid or "").startswith(FIXTURE_TARGET_PREFIXES)


def is_fixture_mission(m):
    if is_fixture_sid(m.get("target_session")):
        return True
    return (m.get("objective") or "").strip().lower() in FIXTURE_OBJECTIVES


def _load_list(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return [str(x) for x in data] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def plan(home):
    """What --apply would do, as data. Pure: reads only."""
    home = os.path.realpath(home)
    mdir = os.path.join(home, "missions")
    missions = []
    if os.path.isdir(mdir):
        for name in sorted(os.listdir(mdir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(mdir, name)
            try:
                with open(path, encoding="utf-8") as handle:
                    m = json.load(handle)
            except (OSError, ValueError):
                continue
            if isinstance(m, dict) and is_fixture_mission(m):
                missions.append({"id": m.get("id") or name[:-5],
                                 "path": path,
                                 "state": m.get("state"),
                                 "target_session": m.get("target_session")})
    lists = {}
    for fname in ("watches.json", "unwatched.json"):
        path = os.path.join(home, fname)
        ids = _load_list(path)
        drop = [s for s in ids if is_fixture_sid(s)]
        if drop:
            lists[fname] = {"path": path, "drop": drop,
                            "keep": [s for s in ids if not is_fixture_sid(s)]}
    ledger = {}
    for kind in shadow_ledger.KINDS:
        path = os.path.join(home, "ledger", kind + ".jsonl")
        n = 0
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    text = " ".join(str(row.get(k) or "")
                                    for k in ("summary", "note", "mission_id"))
                    if any(p in text for p in FIXTURE_TARGET_PREFIXES) \
                            or any(o in text.lower()
                                   for o in FIXTURE_OBJECTIVES):
                        n += 1
        except OSError:
            pass
        ledger[kind] = n
    return {"home": home, "missions": missions, "lists": lists,
            "ledger_fixture_rows": ledger}


def apply(p, ts=None):
    """Execute a plan(). Moves and rewrites; never deletes."""
    ts = ts or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    moved = []
    if p["missions"]:
        adir = os.path.join(p["home"], "missions", "archive", ts)
        os.makedirs(adir, exist_ok=True)
        for m in p["missions"]:
            dest = os.path.join(adir, os.path.basename(m["path"]))
            os.replace(m["path"], dest)
            for side in (".lock", ".tmp"):
                try:
                    os.remove(m["path"] + side)
                except OSError:
                    pass
            moved.append(dest)
            try:
                shadow_ledger.append("missions", {
                    "mission_id": m["id"], "state": m.get("state"),
                    "note": "archived fixture row to %s" % os.path.relpath(
                        dest, p["home"])})
            except Exception:  # noqa: BLE001 -- the move already happened
                pass
    rewritten = []
    for fname, spec in p["lists"].items():
        shutil.copyfile(spec["path"], spec["path"] + ".bak-" + ts)
        with open(spec["path"], "w", encoding="utf-8") as handle:
            json.dump(sorted(spec["keep"]), handle)
        rewritten.append(spec["path"])
    return {"moved": moved, "rewritten": rewritten, "ts": ts}


def _report(p, applied=None):
    out = ["shadow home: %s" % p["home"],
           "fixture missions: %d" % len(p["missions"])]
    for m in p["missions"][:60]:
        out.append("  %s %-13s %s" % (m["id"], m.get("state"),
                                     m.get("target_session")))
    for fname, spec in p["lists"].items():
        out.append("%s: drop %d fixture ids, keep %d"
                   % (fname, len(spec["drop"]), len(spec["keep"])))
    out.append("ledger rows mentioning fixtures (append-only, NOT rewritten): %s"
               % json.dumps(p["ledger_fixture_rows"]))
    if applied is None:
        out.append("dry run. re-run with --apply to move and rewrite.")
    else:
        out.append("moved %d mission files; rewrote %d lists; ts=%s"
                   % (len(applied["moved"]), len(applied["rewritten"]),
                      applied["ts"]))
    return "\n".join(out)


def main(argv):
    do_apply = "--apply" in argv
    p = plan(shadow_ledger.shadow_home())
    applied = apply(p) if do_apply else None
    print(_report(p, applied))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
