#!/usr/bin/env python3
"""Audit of the old app's seed templates against Sutra Pro's seeds (work package ABS-11; absorb design inventory row 34).

    scripts/py scripts/audit_old_templates.py --old <old sutra-ui folder> [--dry-run | --apply] [--data-dir D]

Reads `function-templates/<function>/<name>.json`, `artifact-templates/*.json` and `engine-templates/*.json` of the old folder AS DATA (nothing there is
ever written) and compares them with what Sutra Pro ships:

  function templates   Pro's five function specs (`sutra_app/library/specs/function_specs.json`): a function Pro has is "covered"; the old use-case
                       variants (`identity/money-movement`, ...) have no Pro equivalent: Pro has one spec per function
  artifact templates   Pro's artifact types (`sutra_app/engine/artifacts/types.json`), by name
  engine templates     Pro's J2 template folders (`sutra_app/engine/templates/<artifact>/`), by name

It prints which old seeds Pro already has and which it lacks. Dry run by default. `--apply` copies each LACKING seed that passes the shape check
(an object with id, name and version) to `<data-dir>/library/old-templates/<kind>/<file>`, verbatim, and prints every warning of the check. Sutra Pro
does not read that folder yet: the copies are kept so a use-case template can be offered to a team later; the audit says so. Exit 0; 1 on a bad argument.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent.parent
PRO_SPECS = HERE / "sutra_app" / "library" / "specs" / "function_specs.json"
PRO_TYPES = HERE / "sutra_app" / "engine" / "artifacts" / "types.json"
PRO_TEMPLATES = HERE / "sutra_app" / "engine" / "templates"
KINDS = ("function-templates", "artifact-templates", "engine-templates")


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def norm(name: str) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def read_old(old: Path) -> dict[str, list[dict]]:
    """`{kind: [{file, rel, doc, name, function}]}` in a stable order. An unreadable file is listed with doc None."""
    found: dict[str, list[dict]] = {k: [] for k in KINDS}
    for kind in KINDS:
        base = old / kind
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.json")):
            doc = _json(path)
            rel = path.relative_to(base).as_posix()
            function = rel.split("/")[0] if kind == "function-templates" and "/" in rel else ""
            name = doc.get("name") if isinstance(doc, dict) and isinstance(doc.get("name"), str) else path.stem
            found[kind].append({"file": path, "rel": rel, "doc": doc, "name": name, "function": function})
    return found


def pro_seeds(root: Path = HERE) -> dict[str, set[str]]:
    specs = _json(root / "sutra_app" / "library" / "specs" / "function_specs.json") or {}
    types = _json(root / "sutra_app" / "engine" / "artifacts" / "types.json") or {}
    templates = root / "sutra_app" / "engine" / "templates"
    listed = types.get("types", []) if isinstance(types, dict) else []
    names = {norm(k) for k in listed if isinstance(k, str)} | {norm(v.get("name", "")) for v in (listed.values() if isinstance(listed, dict) else listed)
                                                                 if isinstance(v, dict)}
    engine = {norm(p.stem) for p in templates.rglob("*.json")} | {norm(p.name) for p in templates.iterdir() if p.is_dir()} if templates.is_dir() else set()
    return {"function-templates": {norm(k) for k in (specs.get("specs", {}) if isinstance(specs, dict) else {})}, "artifact-templates": names,
            "engine-templates": engine}


def covered(kind: str, item: dict, pro: dict[str, set[str]]) -> bool:
    if kind == "function-templates":
        return False if item["rel"].split("/")[-1].removesuffix(".json") != "default" else norm(item["function"]) in pro[kind]
    return norm(item["name"]) in pro[kind] or norm(item["file"].stem) in pro[kind]


def warnings_of(item: dict) -> list[str]:
    doc = item["doc"]
    if not isinstance(doc, dict):
        return [f"{item['rel']}: not a JSON object"]
    return [f"{item['rel']}: missing {key}" for key in ("id", "name", "version") if key not in doc]


def audit(old: Path, pro: dict[str, set[str]] | None = None) -> dict[str, dict[str, list[dict]]]:
    pro = pro if pro is not None else pro_seeds()
    out: dict[str, dict[str, list[dict]]] = {}
    for kind, items in read_old(old).items():
        out[kind] = {"has": [i for i in items if covered(kind, i, pro)], "lacks": [i for i in items if not covered(kind, i, pro)]}
    return out


def apply(result: dict[str, dict[str, list[dict]]], data_dir: Path) -> tuple[list[str], list[str]]:
    """Copy each lacking seed that passes the shape check; -> (copied relative names, warnings). The old files are only read."""
    copied: list[str] = []
    problems: list[str] = []
    for kind, groups in result.items():
        for item in groups["lacks"]:
            bad = warnings_of(item)
            if bad:
                problems += bad
                continue
            dest = data_dir / "library" / "old-templates" / kind / item["rel"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(item["file"].read_bytes())
            copied.append(f"{kind}/{item['rel']}")
    return copied, problems


def report(result: dict[str, dict[str, list[dict]]]) -> str:
    lines: list[str] = []
    for kind, groups in result.items():
        total = len(groups["has"]) + len(groups["lacks"])
        lines.append(f"{kind}: {total} old, {len(groups['has'])} covered by Sutra Pro, {len(groups['lacks'])} lacking")
        for item in groups["has"]:
            lines.append(f"  has     {item['rel']}")
        for item in groups["lacks"]:
            lines.append(f"  lacks   {item['rel']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="audit_old_templates", description=__doc__.split("\n\n")[0])
    parser.add_argument("--old", required=True, type=Path, help="the old app's sutra-ui folder (read only)")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".sutra-pro", help="where --apply copies the lacking seeds")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the audit and change nothing (the default)")
    mode.add_argument("--apply", action="store_true", help="copy the lacking seeds that pass the shape check")
    args = parser.parse_args(argv)
    if not args.old.is_dir():
        print(f"audit: {args.old} is not a folder", file=sys.stderr)
        return 1
    result = audit(args.old)
    print(report(result))
    if args.apply:
        copied, problems = apply(result, args.data_dir)
        print(f"copied {len(copied)} seed(s) to {args.data_dir / 'library' / 'old-templates'}")
        for line in problems:
            print(f"warning: {line}")
        print("Sutra Pro does not read these copies yet; they are kept for offering a use-case template to a team later.")
    else:
        print("dry run: nothing was written (use --apply to copy the lacking seeds)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
