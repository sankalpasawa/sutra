"""The Board story of a run (schema story/1): what each message-board question did, step by step, read from what the
run recorded.

build(run_dir, live=None) is code only, no model call. It reads board.json (board/1), atoms.json (atom/1),
documents.json, artifacts.json, receipts.jsonl, summary.json and the first line of chat.jsonl. Nothing is written and
nothing is guessed: anything the run did not record is None here and shown as "not recorded" on the page. The page
adds the team labels (MAPLABEL in j2_ui.html) from each deliverable's tag, so those labels live in one place.

A run with no board.json gives {"has_board": false, "entries": []}, and the page hides the view.
"""
import json
import os

import j2_artifacts as A
from j2_map import _jsonl, _read      # the same readers the Map uses

SCHEMA = "story/1"
# The steps of one entry, in the order the page lays them out, left to right. The page highlights "change".
STEPS = ("doubt", "ask", "answer", "change", "recheck")


def _tags():
    """deliverable type -> its tag (PRD, HLD, LLD, Site), from artifacts/types.json."""
    return {t["name"]: t["tag"] for t in A.load_types()["types"]}


def _atom_places(rows, docs, atoms, tags):
    """atom id -> {"deliverable", "tag"}: where the run recorded that atom's work. documents.json names each
    document's atoms, and the artifact rows name each deliverable's workflows (that is how a website atom is
    placed). An atom neither records is left out, so the page says "not recorded"."""
    place = {}
    for r in rows:
        for v in atoms:
            if v.get("workflow") in (r.get("workflows") or []):
                place[v["id"]] = {"deliverable": r["type"], "tag": tags.get(r["type"])}
    for kind, d in (docs or {}).items():
        for aid in d.get("atoms") or []:
            place.setdefault(aid, {"deliverable": kind, "tag": tags.get(kind)})
    return place


def _atom(aid, names, place):
    """One atom as the story shows it: its id, the name the run recorded for it, and where it sits."""
    p = place.get(aid) or {}
    return {"atom": aid, "name": names.get(aid), "workflow": str(aid or "").split(".")[0],
            "deliverable": p.get("deliverable"), "tag": p.get("tag")}


def _duplicate_edges(atoms):
    """How many (atom, reason) pairs atoms.json records twice (0 when a run's edges are clean)."""
    n = 0
    for v in atoms:
        for key in ("depends_on", "used_by"):
            pairs = [(e.get("atom"), e.get("why")) for e in v.get(key) or []]
            n += len(pairs) - len(set(pairs))
    return n


def _facts(d, rows, summary, board):
    """A run's own recorded facts, for the compare card: nothing is claimed about another run, only what it wrote."""
    return {"run": os.path.basename(d) if d else None, "status": (summary or {}).get("outcome"),
            "cycles": (summary or {}).get("cycles"),
            "versions": {r["type"]: r.get("version") for r in rows},
            "has_board": bool(board.get("entries")), "questions": len(board.get("entries") or [])}


def build(d, live=None):
    """The story of a run folder: one entry per board question, the numbers under them, and the run's own flags."""
    if not d or not os.path.isdir(d):
        return {"schema": SCHEMA, "run": None, "has_board": False, "entries": [], "numbers": {}, "facts": {},
                "flags": {}, "steps": list(STEPS), "not_recorded": ["the run folder"]}
    board = ((live or {}).get("board") if live else _read(d, "board.json")) or {"entries": []}
    rows = [r for r in A.rows(d) if r["kind"] == "type"]
    atoms = list(((live or {}).get("snapshot") or {}).get("atoms_v1", {}).values()) if live else A._atoms(d)
    docs, summary = _read(d, "documents.json", {}) or {}, _read(d, "summary.json", {}) or {}
    receipts, tags = _jsonl(d, "receipts.jsonl"), _tags()
    head = (_jsonl(d, "chat.jsonl")[:1] or [{}])[0]
    names = {v["id"]: v.get("name") for v in atoms}
    place, nr = _atom_places(rows, docs, atoms, tags), []
    if not os.path.isfile(os.path.join(d, "receipts.jsonl")):
        nr.append("receipts.jsonl (this run recorded no receipts)")
    if not atoms:
        nr.append("atoms.json (no work atoms recorded)")
    entries = []
    for e in board.get("entries") or []:
        up = e.get("artifact_update") or {}
        impact = [{**_atom(x.get("atom"), names, place), "result": x.get("result")} for x in e.get("impact") or []]
        trig = [r for r in receipts if r.get("trigger") == e["id"]]
        entries.append({
            "id": e["id"], "status": e.get("status"), "cycle": e.get("cycle"),
            "doubt": {**_atom(e.get("atom"), names, place), "role": e.get("asked_by_role"),
                      "asked_by": e.get("asked_by")},
            "ask": {**_atom(e.get("to"), names, place), "about": e.get("about"), "question": e.get("question")},
            "answer": {"text": e.get("answer"), "by": e.get("answered_by"), "from": e.get("answered_from"),
                       "updated_own_section": bool(e.get("artifact_update")),
                       "sent_to_identity": e.get("sent_to_identity")},
            "change": {"doc": up.get("doc"), "tag": tags.get(up.get("doc")), "section": up.get("section"),
                       "from_version": up.get("from_version"), "to_version": up.get("to_version")} if up.get("doc")
            else None,
            "recheck": {"atoms": len(impact), "passed": sum(1 for x in impact if x["result"] == "passed"),
                        "failed": sum(1 for x in impact if x["result"] != "passed"), "receipts": len(trig)},
            "impact": impact,
            "reused_by": [{"id": r, **_atom(r, names, place)} if "." in str(r) else
                          {"id": r, "atom": None, "name": None, "workflow": None, "deliverable": None, "tag": None}
                          for r in e.get("used_by") or []]})
    numbers = {"questions": len(entries), "rechecked": sum(x["recheck"]["atoms"] for x in entries),
               "receipts": sum(1 for r in receipts if r.get("trigger")), "duplicate_edges": _duplicate_edges(atoms)}
    return {"schema": SCHEMA, "run": os.path.basename(d), "has_board": bool(board.get("entries")),
            "entries": entries, "numbers": numbers, "facts": _facts(d, rows, summary, board),
            "flags": {"mock": head.get("mock"), "provider": head.get("provider"), "model": head.get("model"),
                      "force_question": head.get("force_question")},
            "steps": list(STEPS), "not_recorded": nr}
