"""Implementation generator (extension, OUTSIDE the stable kernel). From a kernel result (a plan) and the
state it was planned against, produce an IMPLEMENTATION VERSION: a runnable workflow in the sutra-native
user-kit shape, the atoms of its steps, the scaffold of the department that would own it, and a page to
run and watch it. Everything is PROPOSED_ONLY: this module writes no file, calls no runtime, and never
marks anything executed. Deterministic: same plan + same state -> same bytes.

Why it exists (Core Algorithm program, rung L1, 2026-11-10): the kernel answers "what should happen";
the runtime that exists (sutra-native, Sutra Pro) runs workflows and atoms; this module is the bridge
from the first to the second, so the generator is judged by whether its output can run, not by how it reads.
"""
from __future__ import annotations

import html
from kernel.core import canonical, digest

WORKFLOW_SCHEMA = "sutra-native/user-kit-workflow/1"      # the shape of W-start-department.json
REQUIRED_WORKFLOW_FIELDS = ("id", "name", "version", "source", "trigger", "steps", "verify", "enforcement")
REQUIRED_STEP_FIELDS = ("id", "host", "sandbox", "action", "verify")
LOCAL_SANDBOX = "local-model-only"
INVARIANTS = [
    "unknown is neither true nor false; a failed check is not evidence of false",
    "no action without an eligible provider, a scoped grant and available budget",
    "a local receipt is never proof of an external effect",
    "nothing here promotes itself; registration needs an external approval path",
]


def _slug(s: str) -> str:
    out = "".join(ch if ch.isalnum() else "-" for ch in str(s).lower()).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out or "goal"


def _done_when(state, goal: str) -> list:
    """The goal's approved rule, as plain lines: one per alternative (OR), AND inside."""
    rule = state.rules.get(goal)
    if not rule:
        return [f"{goal} is observed TRUE from a verified source"]
    return [" and ".join(f"{c} is TRUE" for c in branch) for branch in rule["branches"]]


def _rules(state, actions: list) -> list:
    rows = []
    for mid in actions:
        m = state.methods.get(mid, {})
        g = m.get("grant")
        if g and g in state.grants:
            rows.append({"tag": "go", "line": f"{mid} may run: grant {g} is held; provider {m.get('provider')}"})
        elif g:
            rows.append({"tag": "ask", "line": f"{mid} needs grant {g} before it runs"})
        else:
            rows.append({"tag": "ask", "line": f"{mid} has no grant declared; ask before it runs"})
    rows.append({"tag": "refuse", "line": "any action kind outside simulate_fact, emit_artifact, compile_candidate"})
    rows.extend({"tag": "always", "line": inv} for inv in INVARIANTS)
    return rows


def _steps(result: dict, state) -> list:
    goal = result["goal"]
    steps = [{"id": "record-intent", "host": "codex", "sandbox": "read-only",
              "action": f"log the goal {goal}, the scope {result['scope']} and the selected plan to the execution record",
              "verify": "an execution row exists for this run"}]
    for mid in result.get("actions", []):
        m = state.methods.get(mid, {})
        cost = ", ".join(f"{k} {v}" for k, v in sorted(m.get("cost", {}).items()))
        reqs = ", ".join(m.get("requires", [])) or "none"
        steps.append({"id": _slug(mid), "host": m.get("provider") or "claude-effector", "sandbox": LOCAL_SANDBOX,
                      "method": mid, "effect": m.get("effect"), "requires": list(m.get("requires", [])),
                      "grant": m.get("grant"), "cost": dict(m.get("cost", {})),
                      "action": f"make {m.get('effect')} true by {mid} (needs {reqs}; grant {m.get('grant')}; cost {cost or 'none'}); "
                                "the owner stamps the ask before any real effect",
                      "verify": f"{m.get('effect')} observed TRUE from an independent source, not from the receipt"})
    steps.append({"id": "show-it", "host": "claude-effector", "sandbox": "read-only",
                  "action": f"show the goal, the plan, the gates and the record; say what waits on a stamp",
                  "verify": f"the page lists {len(result.get('actions', []))} steps and the goal {goal}"})
    return steps


def _ui(impl: dict) -> str:
    e = html.escape
    wf = impl["workflow"]
    rows = "".join(f"<tr><td>{e(s['id'])}</td><td>{e(s['host'])}</td><td>{e(s['sandbox'])}</td><td>{e(s['action'])}</td><td>{e(s['verify'])}</td></tr>" for s in wf["steps"])
    gates = "".join(f"<li><b>{e(r['tag'])}</b> {e(r['line'])}</li>" for r in impl["scaffold"]["rules"])
    done = "".join(f"<li>{e(d)}</li>" for d in impl["scaffold"]["done_when"])
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{e(impl['scaffold']['title'])}</title><style>body{{font:14px/1.5 -apple-system,Arial,sans-serif;margin:0;padding:24px;color:#15202b;background:#fff}}"
            "table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{border:1px solid #d7dde3;padding:5px 7px;text-align:left;vertical-align:top}"
            "th{background:#f3f6f8;font-size:11px;text-transform:uppercase;color:#5b6773}.banner{background:#fdf3ec;border-left:4px solid #9a4a1e;padding:8px 12px;margin:0 0 16px}"
            "h1{font-size:20px;margin:0 0 6px}h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#5b6773;margin:18px 0 6px}code{background:#f3f6f8;padding:0 4px}</style></head><body>"
            f"<h1>{e(impl['scaffold']['title'])}</h1><div class=\"banner\"><b>{e(impl['status'])}.</b> Generated from a local plan; nothing here has run. "
            f"Workflow <code>{e(wf['id'])}</code>, {len(wf['steps'])} steps, kernel status <code>{e(impl['plan']['status'])}</code>.</div>"
            f"<h2>Goal</h2><p>{e(impl['scaffold']['purpose'])}</p><h2>Done when</h2><ul>{done}</ul>"
            f"<h2>Steps</h2><table><tr><th>Step</th><th>Host</th><th>Sandbox</th><th>Action</th><th>Verify</th></tr>{rows}</table>"
            f"<h2>Gates and rules</h2><ul>{gates}</ul>"
            f"<h2>Record</h2><p>Plan cost {e(canonical(impl['plan']['cost']))}; trace root <code>{e(impl['plan']['trace_root_sha256'] or '')}</code>; "
            f"implementation sha256 <code>{e(impl['implementation_sha256'])}</code>.</p></body></html>")


def to_implementation(result: dict, state) -> dict:
    """result: a Kernel.resolve() record (or a recorded case outcome); state: the State it was planned against."""
    goal = result["goal"]
    scope = result.get("scope", state.scope)
    slug = _slug(goal)
    actions = list(result.get("actions", []))
    workflow = {
        "schema": WORKFLOW_SCHEMA,
        "id": f"W-{slug}",
        "name": f"Make {goal} true for {scope}",
        "version": "0.1.0-proposed",
        "created": "generated; the deploy step stamps the date",
        "source": f"Core Algorithm plan for {goal}, trace root {result.get('trace_root_sha256')}",
        "deploy": "PROPOSED_ONLY: review, then cp to ~/.sutra-native/user-kit/workflows/ under the owner's stamp",
        "trigger": {"kind": "intent", "utterance_patterns": [f"(make|complete) {slug.replace('-', ' ')}"], "input": f"the standing goal {goal} in scope {scope}"},
        "steps": _steps(result, state),
        "verify": f"{goal} observed TRUE from an independent source; every step's receipt present; budget not exceeded "
                  f"(plan cost {canonical(result.get('cost'))} within {canonical(state.budget)})",
        "enforcement": {"current": "PROPOSED_ONLY: generated from a local plan; nothing executed; every real effect is an ask the owner stamps",
                        "planned": "the daemon runs the steps as asks; independent verification closes each"},
    }
    scaffold = {
        "title": f"Department for {goal}",
        "scope": scope,
        "purpose": f"keep {goal} true for {scope}, by approved rules, with verified evidence",
        "done_when": _done_when(state, goal),
        "rules": _rules(state, actions),
        "functions": {"identity": "the goal and the done lines above", "adaptation": "needs from new rules and facts (the kernel's REFINE and QUERY)",
                      "priority": f"preference {list(state.preference)} over budget {dict(state.budget)}",
                      "coordination": f"{len(actions)} method steps in order, providers {sorted({state.methods.get(a, {}).get('provider') for a in actions} - {None})}",
                      "audit": "hash-chained trace; independent verifier; local receipts never count as external proof"},
    }
    atoms = [{"id": f"A{i}", "workflow": workflow["id"], "name": s.get("method", s["id"]), "owner": "proposed-department", "status": "open",
              "goal": {"text": goal}, "constraints": [f"grant {s.get('grant')}", f"cost {canonical(s.get('cost', {}))}", "LOCAL_REFERENCE_ONLY"],
              "context": {"scope": scope, "requires": s.get("requires", [])}, "work": {"method": s.get("method"), "host": s["host"]},
              "verify": {"check": s["verify"], "met": False, "evidence": None}}
             for i, s in enumerate(workflow["steps"], 1) if s.get("method")]
    impl = {"schema": "core-algorithm/implementation/1", "status": "PROPOSED_ONLY",
            "plan": {"goal": goal, "scope": scope, "status": result.get("status"), "actions": actions, "cost": result.get("cost"),
                     "trace_root_sha256": result.get("trace_root_sha256")},
            "workflow": workflow, "atoms": atoms, "scaffold": scaffold,
            "claim": "generated from a local plan; not executed; not registered; a runnable shape, not a run"}
    impl["implementation_sha256"] = digest({k: v for k, v in impl.items() if k != "ui"})
    impl["ui"] = _ui(impl)
    impl["ui_sha256"] = digest(impl["ui"])
    return impl


def validate_workflow(wf: dict) -> list:
    """Return the list of problems (empty when the workflow has the user-kit shape and is proposal-only)."""
    problems = [f"missing {f}" for f in REQUIRED_WORKFLOW_FIELDS if f not in wf]
    for i, s in enumerate(wf.get("steps", [])):
        problems += [f"step {i} missing {f}" for f in REQUIRED_STEP_FIELDS if f not in s]
        if s.get("method") and s.get("sandbox") != LOCAL_SANDBOX:
            problems.append(f"step {i} is a method step without the local sandbox")
    if "PROPOSED_ONLY" not in str(wf.get("enforcement", {}).get("current", "")):
        problems.append("enforcement.current is not PROPOSED_ONLY")
    return problems
