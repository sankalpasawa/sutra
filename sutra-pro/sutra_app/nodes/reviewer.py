"""The reviewer's job (MAN-11): the prompt, the typed verdict and its checks. Pure except for the one model call that `review` is given."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["VERDICTS", "VERDICT_FILE", "VERDICT_SCHEMA", "MAX_SUMMARY", "MAX_POINTS", "MAX_POINT", "VerdictInvalid", "check_verdict", "prompt_of", "read_reports", "TEMPLATE"]

VERDICT_FILE = "verdict.json"
VERDICTS = ("approve", "changes", "reject")
MAX_SUMMARY, MAX_POINTS, MAX_POINT = 500, 5, 200
TEMPLATE = Path(__file__).resolve().parent / "templates" / "reviewer.md"
VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["verdict", "summary", "needs_work", "points"],
    "properties": {"verdict": {"type": "string", "enum": list(VERDICTS)}, "summary": {"type": "string", "maxLength": MAX_SUMMARY},
                   "needs_work": {"type": "array", "maxItems": 5, "items": {"type": "string", "pattern": "^a[1-5]$"}},
                   "points": {"type": "array", "maxItems": MAX_POINTS, "items": {"type": "string", "maxLength": MAX_POINT}}},
}


class VerdictInvalid(ValueError):
    """The verdict is not the typed object. The reason never quotes the verdict."""


def check_verdict(raw: Any) -> dict[str, Any]:
    """The verdict as the closed object `{v, verdict, summary, needs_work, points}`: only the enum and the refs can affect flow, and the words are plain text that is shown and never read as an
    instruction. Anything else is `VerdictInvalid`."""
    if not isinstance(raw, dict) or not {"verdict", "summary"} <= set(raw) or set(raw) - {"v", "verdict", "summary", "needs_work", "points"}:
        raise VerdictInvalid("the verdict does not have the fields of a verdict")
    if raw["verdict"] not in VERDICTS:
        raise VerdictInvalid("the verdict is not approve, changes or reject")
    summary = raw["summary"]
    if not isinstance(summary, str) or len(summary) > MAX_SUMMARY:
        raise VerdictInvalid("the summary is too long")
    needs, points = raw.get("needs_work", []), raw.get("points", [])
    import re
    if not isinstance(needs, list) or len(needs) > 5 or not all(isinstance(n, str) and re.fullmatch(r"a[1-5]", n) for n in needs):
        raise VerdictInvalid("needs_work names steps that are not steps")
    if not isinstance(points, list) or len(points) > MAX_POINTS or not all(isinstance(p, str) and len(p) <= MAX_POINT for p in points):
        raise VerdictInvalid("the points are too long")
    if raw["verdict"] == "approve" and needs:
        raise VerdictInvalid("an approval asks for no step to be done again")
    return {"v": 1, "verdict": raw["verdict"], "summary": " ".join(summary.split()), "needs_work": list(dict.fromkeys(needs)), "points": [" ".join(p.split()) for p in points]}


def read_reports(run_dir: Path, upstream: list[dict]) -> list[tuple[str, dict]]:
    """`(step title, accepted hand-off)` for each upstream run: the file the SERVER checked and scrubbed (`handoff.accepted.json`), never the node's own `handoff.json`. A run that has none is skipped."""
    out: list[tuple[str, dict]] = []
    base = run_dir.parents[2]
    for entry in upstream[:12]:
        run_id = str(entry.get("run_id", ""))
        found = next(iter(sorted(base.glob(f"*/runs/{run_id}/handoff.accepted.json"))), None) if run_id and "/" not in run_id and ".." not in run_id else None
        try:
            doc = json.loads(found.read_text(encoding="utf-8"))["handoff"] if found is not None and found.is_file() and not found.is_symlink() else None
        except (OSError, ValueError, KeyError, TypeError):
            doc = None
        if isinstance(doc, dict):
            out.append((str(entry.get("title", ""))[:80], doc))
    return out


def prompt_of(request: str, reports: list[tuple[str, dict]]) -> str:
    """The reviewer's prompt: the template with the request and what the steps handed on (summary, claims, file names)."""
    lines = []
    for title, doc in reports:
        lines.append(f"- {title}: {str(doc.get('summary', ''))[:600]}")
        claims = [str(c)[:200] for c in (doc.get("claims") or [])][:10]
        files = [str(f.get("path", ""))[:120] for f in (doc.get("files") or []) if isinstance(f, dict)][:20]
        if claims:
            lines.append("  claims: " + "; ".join(claims))
        if files:
            lines.append("  files: " + ", ".join(files))
    return TEMPLATE.read_text(encoding="utf-8").format(request=request[:2000], reports="\n".join(lines) or "(nothing was handed on)", schema=json.dumps(VERDICT_SCHEMA))
