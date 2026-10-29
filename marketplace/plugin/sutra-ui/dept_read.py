"""dept_read.py -- the cheap read of the departments under a Root (PRD amendment A5, A5.3.1, A5.3.6).

One row for each department, built from three small files (dept.json, j2-state.json, asks.json) and their modification times, and
nothing else: no status call, no functions view, no run journal. `rows` feeds the listing route and the detail screen;
`candidates` feeds the create-or-reuse decision, where the score is a token overlap used to pick eight cards for the model to read and
is never the decision.

The rows are cached by a signature of the files' modification times with a ten-second tick, so a poll costs a few stats."""
import re
import time
from datetime import datetime

import website_dept as W

TICK_S = 10
_CACHE = {}                                         # root_ref or "" -> (checked_at, signature, rows)

_STATE_WORDS = {"stopped": "stopped", "done": "done", "complete": "done", "completed": "done", "waiting": "waiting",
                "blocked": "blocked", "idle": "idle"}
_STOP = frozenset("the a an and or of to for in on with is are be it its this that we you our your at by as from into".split())


def _mtime(p):
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _stamp(ts):
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds") if ts else None


def _signature(root_ref):
    sig = []
    for d in W.list_depts():
        ref = d.get("ref")
        if not ref or d.get("kind") == "root" or not _under(d, root_ref):
            continue
        base = W.ddir(ref)
        sig.append((ref, _mtime(base / "dept.json"), _mtime(base / "j2-state.json"), _mtime(base / "asks.json")))
    return tuple(sig)


def signature(root_ref=None):
    """What changes when any department under `root_ref` changes (the memo key of the Shadow graph)."""
    return _signature(root_ref)


def _under(d, root_ref):
    return not root_ref or root_ref in (d.get("root"), d.get("parent"))


def _row(d):
    ref = d["ref"]
    base = W.ddir(ref)
    st = W._read(base / "j2-state.json", None)
    st = st if isinstance(st, dict) else {}
    pending = [a for a in W.asks(ref) if isinstance(a, dict) and a.get("status") == "pending"]
    blocked = any(a.get("escalated") for a in pending)
    if d.get("stopped"):
        state = "stopped"
    elif blocked:
        state = "blocked"
    elif pending:
        state = "waiting"
    elif not st:
        state = "not_started"
    else:
        state = _STATE_WORDS.get(str(st.get("state") or "").lower(), "working")
    live = d.get("runtime") == 2 and d.get("kind") != "root"
    met = d.get("done_met")
    return {"ref": ref, "name": str(d.get("name") or ref)[:200] or ref, "kind": d.get("kind"), "parent": d.get("parent"),
            "root": d.get("root") or d.get("parent"), "runtime": 2 if d.get("runtime") == 2 else 1,
            "stopped": bool(d.get("stopped")), "state": state, "waiting_on_you": bool(pending), "pending_asks": min(len(pending), 99),
            "working": [str(e)[:40] for e in (st.get("workflow") or []) if isinstance(e, str)][:12] if state == "working" else [],
            "last_activity": _stamp(max(_mtime(base / "dept.json"), _mtime(base / "j2-state.json"), _mtime(base / "asks.json"))),
            "created": d.get("created") if isinstance(d.get("created"), str) and d["created"][:4].isdigit() else None,
            "goal": str(d.get("goal") or "")[:240], "done": str(d.get("done") or "")[:160],
            "done_met": met if isinstance(met, bool) else None,
            "engines": [str(e)[:40] for e in d.get("engines") or []][:32], "artifacts": [str(a)[:40] for a in d.get("artifacts") or []][:32],
            "j2_url": "/j2ui/%s/" % ref if live else None}


def rows(root_ref=None):
    """The departments under `root_ref` (every non-Root department when None), as dept.row dicts, newest activity first."""
    key = root_ref or ""
    sig = _signature(root_ref)
    hit = _CACHE.get(key)
    if hit and hit[1] == sig and time.time() - hit[0] < TICK_S:
        return [dict(r) for r in hit[2]]
    out = [_row(d) for d in W.list_depts() if d.get("ref") and d.get("kind") != "root" and _under(d, root_ref)]
    out.sort(key=lambda r: (r["last_activity"] or "", r["name"]), reverse=True)
    _CACHE[key] = (time.time(), sig, out)
    return [dict(r) for r in out]


def newest(root_ref):
    """When anything under the Root last changed, as seconds (finer than the stamp the rows carry); 0 when it has nothing."""
    return max([max(sig[1:]) for sig in _signature(root_ref)] or [0.0])


def forget():
    """Drop the cache (a test, or a write that must show at once)."""
    _CACHE.clear()


def tokens(text):
    return {t for t in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(t) > 2 and t not in _STOP}


def jaccard(a, b):
    a, b = tokens(a), tokens(b)
    return len(a & b) / len(a | b) if a and b else 0.0


def candidates(root_ref, words, limit=8):
    """Up to `limit` dept.candidate dicts under the Root, best overlap with `words` first. Departments that overlap nothing are
    kept (newest first) to fill the cards: the model judges, the score only orders."""
    want = tokens(words)
    out = []
    for r in rows(root_ref):
        have = tokens("%s %s %s" % (r["name"], r["goal"], r["done"]))
        score = len(want & have) / len(want | have) if want and have else 0.0
        out.append({"ref": r["ref"], "name": r["name"][:80], "kind": r["kind"], "goal": r["goal"], "done": r["done"],
                    "state": r["state"], "stopped": r["stopped"], "blocked": r["state"] == "blocked" or any(
                        a.get("escalated") and a.get("status") == "pending" for a in W.asks(r["ref"])),
                    "last_activity": r["last_activity"], "score": round(score, 4)})
    out.sort(key=lambda c: (c["score"], c["last_activity"] or ""), reverse=True)
    return out[:max(0, int(limit))]
