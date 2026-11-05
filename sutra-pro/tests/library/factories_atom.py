"""Builders for the atom tests (WP L4): drafts, open atoms, tries, closes, abandons, and the importer of J2's atom dicts.

Any library test that needs an atom can import this module (`from factories_atom import opened`): tests/library has no
__init__.py, so pytest puts the folder on sys.path. Nothing here is a fixture and nothing registers a class.

    atom = opened()                                   # an open atom: goal, one file-exists check, node sales.adaptation
    atom = tried(opened(), 2)                         # after two failed tries (attempt 2, still open)
    t = close_with(atom, 0)                           # the close that passes: t.outcome == "closed"
    t = abandon(tried(opened(), 3), "verify failed: file-exists: missing", code="verify_failed")

`atom_from_j2` turns one of J2's stored atom dicts (as `workflows.json` holds them) into a library Atom, so the
`atom_view` parity tests can compare with the view J2's own `j2_schema.atom_view` gave. The fixtures are in
tests/library/fixtures/atom/view_cases.json (built once by build_view_cases.py in that folder).
"""
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sutra_app.library.atom import (
    Atom, AtomDraft, Check, CheckResult, Constraint, ExpectedItem, OutputItem, Transition, Verify, Work, abandon_atom,
    close_atom, default_relevance, open_atom,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "atom"
NODE = "sales.adaptation"
ATOM_ID = "a-3f9a1c2b7d-01"
SHA = "ab" * 32
_ARGS = {
    "file-exists": ["site/index.html"], "grep-count": ["Contact", "site/index.html", "1"], "named-test": ["tests/form.sh"],
    "reply-valid": ["priority", "price"], "answer-recorded": ["m-14"],
}


def work(kind: str = "llm", **over: Any) -> Work:
    return Work(dispatch_kind=kind, agent=over.pop("agent", "Builder"), steps=over.pop("steps", "Create #contact"),
                how_kind=over.pop("how_kind", "AI" if kind == "llm" else "code"), **over)


def check(template: str = "file-exists", args: Sequence[str] | None = None, **over: Any) -> Check:
    """A check with sensible arguments for its template (named-test gets a pin)."""
    if template == "named-test":
        over.setdefault("target_sha256", SHA)
    return Check(template=template, args=list(_ARGS.get(template, []) if args is None else args), **over)


def draft(*checks: Check, goal: str = "Visitors can open the contact form", kind: str = "llm", **over: Any) -> AtomDraft:
    return AtomDraft(goal=goal, work=over.pop("work", work(kind)), verify=Verify(checks=list(checks) or [check()]), **over)


def open_transition(*checks: Check, now: int = 100, id: str = ATOM_ID, node_id: str = NODE, **over: Any) -> Transition:
    """`open_atom` on a draft; keyword arguments left over go to `draft`."""
    ctx = {k: over.pop(k) for k in ("department_id", "workflow_id", "task_id", "session_id", "other_open", "abandoned_ids") if k in over}
    return open_atom(draft(*checks, **over), id=id, node_id=node_id, now=now, **ctx)


def opened(*checks: Check, **over: Any) -> Atom:
    t = open_transition(*checks, **over)
    assert t.outcome == "opened", t.refusal
    return t.atom


def results_for(atom: Atom, *exit_codes: int, evidence: str | None = None, ts: int = 110) -> list[CheckResult]:
    """One CheckResult per check for the atom's NEXT attempt (3 at most: a CheckResult has no attempt 4, and an
    exhausted atom is refused before its results are looked at). One exit code is repeated for every check."""
    codes = list(exit_codes) or [0]
    codes = codes * len(atom.verify.checks) if len(codes) == 1 else codes
    assert len(codes) == len(atom.verify.checks)
    return [CheckResult(attempt=min(atom.attempt + 1, 3), exit_code=code, ts=ts + i,
                        evidence=evidence if evidence is not None else ("present" if code == 0 else "missing"))
            for i, code in enumerate(codes)]


def close_with(atom: Atom, *exit_codes: int, now: int = 120, evidence: str | None = None, **kw: Any) -> Transition:
    return close_atom(atom, results_for(atom, *exit_codes, evidence=evidence, ts=now - 1), now, **kw)


def tried(atom: Atom, failed: int, exit_code: int = 1) -> Atom:
    """The atom after `failed` failed tries: still open, attempt = failed."""
    for _ in range(failed):
        t = close_with(atom, exit_code)
        assert t.outcome == "verify_failed", t.refusal
        atom = t.atom
    return atom


def closed(*checks: Check, tries: int = 0, **over: Any) -> Atom:
    t = close_with(tried(opened(*checks, **over), tries), 0)
    assert t.outcome == "closed", t.refusal
    return t.atom


def abandon(atom: Atom, reason: str = "the run ended", code: str = "run_ended", now: int = 130, **kw: Any) -> Transition:
    return abandon_atom(atom, reason, now, code=code, **kw)


def verify_failed_atom(*checks: Check, **over: Any) -> Atom:
    """An atom the layer ended because its checks failed: three failed tries, then abandoned with code verify_failed."""
    t = abandon(tried(opened(*checks, **over), 3), "verify failed: file-exists: missing", code="verify_failed")
    assert t.outcome == "abandoned", t.refusal
    return t.atom


def refused(goal: str = "done", **over: Any) -> Atom:
    t = open_transition(goal=goal, **over)
    assert t.outcome == "refused"
    return t.atom


def fields(atom: Atom, **changes: Any) -> dict[str, Any]:
    """The atom as the plain dict `Atom.model_validate` takes, with `changes` applied: for building invalid atoms."""
    return {**atom.model_dump(by_alias=False), **changes}


# ---- J2's stored atoms ---------------------------------------------------------------------------------------------

def _j2_args(c: Mapping[str, Any]) -> list[str]:
    target = c.get("target")
    if c.get("type") == "grep-count":      # the plugin's (pattern, file, min); J2 keeps the count in `expect`
        return [str(target), str(c.get("file") or "index.html"), str(max(int(c.get("expect") or 1), 1))]
    items = target if isinstance(target, list) else ([] if target is None else [target])
    return [str(x) for x in items if str(x)]


def atom_from_j2(a: Mapping[str, Any], *, produced: Sequence[Mapping[str, Any]] = (), details: Mapping[str, Any] | None = None,
                 node_id: str = "s-0123456789", ts_open: int = 1_000, ts_closed: int = 1_100) -> Atom:
    """A library Atom from one of J2's stored atom dicts. J2 keeps only the LAST attempt's results, so the importer
    needs `attempts` to equal the results' attempt (the parity cases are single-attempt atoms). `produced` and `details`
    are what J2 derives from `agent_output` (the Atom keeps the derived result, not agent_output): the cases hold them.
    J2's status maps passed -> closed, escalated -> abandoned (verify_failed), failed or none -> open; a result with
    pass None (could not run) becomes exit 127."""
    status, attempts = a.get("status"), int(a.get("attempts") or 0)
    results = list(a.get("results") or [])
    checks = []
    for index, c in enumerate(x for x in a.get("verification") or [] if isinstance(x, Mapping)):
        r = results[index] if index < len(results) else None
        result = [] if r is None else [CheckResult(
            attempt=int(r.get("attempt") or 1), ts=ts_open + 1 + index, evidence=str(r.get("evidence") or ""),
            exit_code=0 if r.get("pass") is True else 127 if r.get("pass") is None else 1)]
        raw = Check(template=c["type"], args=_j2_args(c), text=str(c.get("text") or ""), expect=c.get("expect") if isinstance(c.get("expect"), (bool, int)) else None,
                    relevance_source="default", target_sha256=SHA if c["type"] == "named-test" else None, results=result)
        checks.append(raw.evolve(relevance=default_relevance(raw)))
    how = a.get("how") or {}
    state = {"passed": "closed", "escalated": "abandoned"}.get(status, "open")
    ended = {"closed": {"closed_by": "verify", "ts_closed": ts_closed},
             "abandoned": {"closed_by": "manual-override", "ts_closed": ts_closed, "reason": "escalated: the checks failed",
                           "abandon_code": "verify_failed"},
             "open": {}}[state]
    return Atom(
        id=a["id"], node_id=node_id, workflow_id=str(a["id"]).split(".")[0], state=state, attempt=attempts,
        goal=a.get("goal") or "", constraints=[Constraint(text=c) for c in a.get("constraints") or []],
        context=list(a.get("context") or []),
        work=Work(dispatch_kind="llm" if how.get("kind", "AI") == "AI" else "bash", agent=how.get("agent"),
                  steps=how.get("steps") or "", how_kind=how.get("kind", "AI")),
        expected=[ExpectedItem.model_validate(x) for x in a.get("expected_output") or []], verify=Verify(checks=checks),
        produced=[OutputItem.model_validate(x) for x in produced], notes=(a.get("human_output") or {}).get("text") or "",
        details=dict(details or {}), ts_open=ts_open, **ended)


def load_view_cases() -> list[dict[str, Any]]:
    """The parity cases: {name, source, j2_atom, workflow, edges, ended, view} with `view` = j2_schema.atom_view's output."""
    return json.loads((FIXTURES / "view_cases.json").read_text(encoding="utf-8"))["cases"]
