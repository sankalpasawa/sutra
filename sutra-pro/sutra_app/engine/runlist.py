"""Run settings' run list and the build journey's stops: `GET /api/runlist` and `GET /api/changes` (J2 sync 4, D140).

J2's own server answers both (`j2_server.run_row`, `run_list` and the inline `/api/changes`); the engine answers them from
`views.runlist` and `views.changes` over one department's runs folder, so the same logic lives here, in a Sutra-owned module,
on J2's readers (`j2.saved_dir`, `j2._read`, `j2._jsonl`). Up to sync 3 the same code was patch P13 inside the vendored `j2.py`
(J2's own repository had neither route then). It moved without a change of logic: the replies are what they were.

Read-only: nothing here writes a file or takes a lock.
"""
import json
import os
import re

from . import j2

__all__ = ["run_row", "run_list", "run_changes"]


def run_row(name, runs_dir=None, live_running=False):
    """One row of Run settings' run list, from the run's own records, or None for a folder that is not a saved run.

    status: summary.json "status" (done and done_with_open_items -> done; stopped, crashed, stuck, out_of_budget -> stopped);
    no summary.json -> stopped (it never finished), except the live run while it runs -> running. title: goal.json
    "site_name", else the first sentence of goal.json "statement", else the run id. output: summary.json "output_type" (the
    type the run ended with), else the chat's meta row "output" (the type it started with). brief: summary.json "brief", else
    the first user message of chat.jsonl. when: from the id."""
    d = j2.saved_dir(name, runs_dir)
    if not d or not os.path.exists(os.path.join(d, "chat.jsonl")):
        return None
    s, g = j2._read(d, "summary.json", {}) or {}, j2._read(d, "goal.json", {}) or {}
    rows = j2._jsonl(d, "chat.jsonl")
    meta = rows[0] if rows and rows[0].get("meta") else {}
    first = next((m for m in rows if m.get("who") == "user"), {})
    st = str(s.get("status") or "")
    status = "running" if live_running else "done" if st.startswith("done") else "stopped"
    stmt = re.split(r"(?<=[.!?])\s", str(g.get("statement") or "").strip())[0]
    title = str(g.get("site_name") or "").strip() or (stmt[:70] + ("…" if len(stmt) > 70 else "")) or name
    m = re.search(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})", name)
    return {"id": name, "title": title, "status": status, "output": s.get("output_type") or meta.get("output") or "",
            "when": f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}" if m else "", "brief": str(s.get("brief") or first.get("text") or "")[:160]}


def run_list(runs_dir=None, live="", live_running=False):
    """GET /api/runlist: every saved run of `runs_dir`, newest first, as `run_row`s; `live` is the live run's id."""
    runs_dir = runs_dir or j2.RUNS_DIR
    names = sorted(os.listdir(runs_dir), reverse=True) if os.path.isdir(runs_dir) else []
    out = [x for x in (run_row(n, runs_dir, bool(live_running) and n == live) for n in names) if x]
    out.sort(key=lambda x: x["when"], reverse=True)
    return {"live": live or "", "runs": out}


def run_changes(d):
    """GET /api/changes, the build journey's stops: one per change request in the run's change.json (`d` is a folder or None)."""
    p = os.path.join(d or "", "change.json")
    try:
        with open(p, encoding="utf-8") as f:
            rows = json.load(f) if d and os.path.isfile(p) else []
    except (OSError, ValueError):
        rows = []
    return {"changes": [{"id": c.get("id"), "request": str(c.get("request") or ""), "cycle": c.get("cycle"),
                         "revise": len(c.get("revise") or []), "new": len(c.get("new") or [])}
                        for c in (rows if isinstance(rows, list) else []) if isinstance(c, dict)]}
