"""Builds view_cases.json, the atom/1 parity cases of tests/library/test_lib_atom_view.py. Run it ONCE, by hand; the tests
never run it and never import J2.

    scripts/py tests/library/fixtures/atom/build_view_cases.py [path/to/J2_Prototype]

Each case holds one J2 stored atom (trimmed to the keys `j2_schema.atom_view` and the importer read; an explicit "count": 1 on an expected item is dropped,
because the library treats 1 as the default and does not echo it), the workflow it
belongs to (name and status), the edges and `ended` flag, and `view`: the dict J2's OWN `atom_view` returned for them.
The real atoms come from J2's saved runs (runs/*/workflows.json, read only); the other cases edit one of them the way
J2's own tests do (a failing result, no result at all, a workflow that was never funded). A copy of j2_schema.py is
imported from a temporary folder, so nothing is written to the J2 checkout. The script checks every case against the
library before it writes the file.
"""
import copy
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))          # tests/library, for factories_atom
sys.dont_write_bytecode = True

from factories_atom import atom_from_j2          # noqa: E402
from sutra_app.library.atom import atom_view    # noqa: E402

J2 = Path(sys.argv[1] if len(sys.argv) > 1 else "~/Desktop/development/J2_Prototype").expanduser()
RUNS = ("j2-20261016-160511", "j2-20261021-141350", "j2-20261022-123744")
KEEP_ATOM = ("id", "goal", "constraints", "context", "how", "expected_output", "attempts", "status", "deed", "board_stale", "board_rechecked")


def j2_schema():
    tmp = Path(tempfile.mkdtemp(prefix="j2_schema_"))
    shutil.copy(J2 / "j2_schema.py", tmp / "j2_schema.py")
    spec = importlib.util.spec_from_file_location("j2_schema_copy", tmp / "j2_schema.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trim(atom):
    """The keys J2's atom_view and the importer read; long document text in agent_output is cut to the first section name."""
    out = {k: copy.deepcopy(atom[k]) for k in KEEP_ATOM if k in atom}
    for item in out.get("expected_output") or []:      # an explicit count of 1 is the default: the library does not echo it
        if item.get("count") == 1:
            del item["count"]
    out["verification"] = [{k: c[k] for k in ("text", "type", "target", "expect", "file", "item") if k in c} for c in atom.get("verification") or []]
    out["results"] = [{k: r[k] for k in ("check", "type", "target", "pass", "evidence", "attempt") if k in r} for r in atom.get("results") or []]
    if atom.get("human_output"):
        out["human_output"] = {"text": atom["human_output"].get("text")}
    ag = atom.get("agent_output") or {}
    if ag:
        out["agent_output"] = {k: copy.deepcopy(ag[k]) for k in ("anchor", "files", "section", "ids", "selectors", "kind", "file", "attempt") if k in ag}
        out["agent_output"]["section_names"] = [(ag.get("section_names") or [None])[0]]
    return out


def real_atoms():
    for run in RUNS:
        for wf in json.loads((J2 / "runs" / run / "workflows.json").read_text(encoding="utf-8")):
            for atom in wf.get("atoms") or []:
                yield run, wf, atom


def adaptable(S, atom, wf_status, ended=False):
    """The library case for this atom, or None when the importer cannot hold it (a bound, or a second attempt)."""
    try:
        view = S.atom_view(atom, {"name": "wf", "status": wf_status}, [], ended)
        lib = atom_from_j2(atom, produced=view["output"], details=view["details"])
        return view if atom_view(lib, {"name": "wf", "status": wf_status}, [], ended).wire() == view else None
    except Exception:
        return None


def pick(S, predicate):
    for run, wf, raw in real_atoms():
        atom = trim(raw)
        if atom.get("attempts") == 1 and atom.get("status") == "passed" and predicate(atom) and adaptable(S, atom, "done"):
            return run, wf, atom
    raise SystemExit("no real atom matches; the saved runs changed?")


def case(S, name, source, wf, atom, *, status="done", edges=(), ended=False):
    workflow = {"name": wf.get("name") if isinstance(wf, dict) else wf, "status": status}
    return {"name": name, "source": source, "j2_atom": atom, "workflow": workflow, "edges": list(edges), "ended": ended,
            "view": S.atom_view(atom, workflow, list(edges), ended)}


def main():
    S = j2_schema()
    cases = []
    run, wf, site = pick(S, lambda a: (a.get("agent_output") or {}).get("anchor") and not any(c["type"] == "behavior-steps" for c in a["verification"]))
    cases.append(case(S, "website_section_closed", f"{run} {site['id']}", wf, site))
    run2, wf2, doc = pick(S, lambda a: (a.get("agent_output") or {}).get("kind") == "doc")
    cases.append(case(S, "document_section_closed", f"{run2} {doc['id']}", wf2, doc))
    run3, wf3, calc = pick(S, lambda a: any(c["type"] == "behavior-steps" for c in a["verification"]))
    cases.append(case(S, "behaviour_steps_closed", f"{run3} {calc['id']}", wf3, calc))

    failed = copy.deepcopy(site)
    failed.update(status="failed", attempts=1)
    failed["results"][0].update({"pass": False, "evidence": "'#hero' found 0 time(s) in index.html, expected 1"})
    cases.append(case(S, "failed_try_workflow_failed", f"{run} {site['id']} with a failing result", wf, failed, status="failed"))
    cases.append(case(S, "failed_try_workflow_running", f"{run} {site['id']} with a failing result", wf, failed, status="running"))
    escalated = copy.deepcopy(failed)
    escalated["status"] = "escalated"
    cases.append(case(S, "escalated", f"{run} {site['id']} escalated", wf, escalated, status="done"))

    unbuilt = trim(next(raw for _, _, raw in real_atoms() if raw is not None and raw.get("id") == site["id"]))
    for key in ("results", "attempts", "status", "agent_output", "human_output"):
        unbuilt.pop(key, None)
    unbuilt["results"] = []
    cases.append(case(S, "never_checked_open", f"{run} {site['id']} before any check", wf, unbuilt, status="registered"))
    cases.append(case(S, "never_built_run_ended", f"{run} {site['id']} before any check", wf, unbuilt, status="held", ended=True))
    cases.append(case(S, "never_funded", f"{run} {site['id']} before any check", wf, unbuilt, status="unfunded"))
    cases.append(case(S, "done_workflow_run_ended", f"{run} {site['id']} before any check", wf, unbuilt, status="done", ended=True))

    linked = copy.deepcopy(site)
    linked.update(board_stale="Q-3", board_rechecked="Q-4")
    edges = [{"atom": "W-2.a1", "why": "its section, anchor and selectors were listed in this builder's prompt"},
             {"atom": "W-3.a1", "why": "LLD slice hero"},
             {"atom": "W-2.a1", "why": "its section, anchor and selectors were listed in this builder's prompt"}]
    cases.append(case(S, "edges_and_board_marks", f"{run} {site['id']} with edges and board marks", wf, linked, edges=edges))

    deed = {"id": "W-9.a1", "goal": "Send the milestone email about prd.md", "how": {"kind": "code", "agent": "code", "steps": ""},
            "constraints": ["only to the target in J2_TEST_EMAIL", "built by code, no model"], "context": ["prd.md"],
            "expected_output": [{"text": "The milestone email reaches the configured test target", "kind": "send", "target": "send_email", "met": True}],
            "verification": [{"text": "The milestone email was sent to the configured test target", "type": "deed-send", "target": "send_email",
                              "expect": True, "item": 1}],
            "results": [{"check": "The milestone email was sent to the configured test target", "type": "deed-send", "target": "send_email",
                         "pass": True, "evidence": "sent in mock mode", "attempt": 1}],
            "attempts": 1, "status": "passed", "human_output": {"text": "The email was sent in test mode to the mock recorder only."},
            "deed": {"channel": "email", "mode": "mock", "sent": True}}
    cases.append(case(S, "send_deed_closed", "crafted after j2.py send_deed (a deed atom)", {"name": "Send the milestone email"}, deed))

    (HERE / "view_cases.json").write_text(json.dumps({"j2_commit": "33aeeda", "cases": cases}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases")


if __name__ == "__main__":
    main()
