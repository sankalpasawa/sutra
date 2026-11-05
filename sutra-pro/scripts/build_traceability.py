#!/usr/bin/env python3
"""The traceability matrix (GAP-TRACE): owner rules, the seven draw.io steps, the 15 chips, the 30 J2 endpoints, every decision and every
work package, each tied to the modules, tests and commits that carry it.

    scripts/py scripts/build_traceability.py            write docs/design/traceability.json and docs/TRACEABILITY.md
    scripts/py scripts/build_traceability.py --check    verify the committed json (exit 1 with the first 20 problems)

Sources: docs/build-plan.json, docs/DECISIONS.md (every `## D<n>` heading), docs/notes/*.md, sutra_app/engine/features.py (FEATURES),
the J2 route table the contract tests compare (sutra_app/engine/api/*.py `ROUTES`, `J2_EXACT` of sutra_ctx.js, tests/contracts), the
golden api shapes, docs/diagram/decisions.json and docs/diagram/gen.py, and `git log --grep '^Merge wp/'`.

The output is deterministic (sorted, no dates). `--check` does NOT compare the committed file with a fresh run: later packages add
files and decisions, and their merges must not fail because of this test. It checks that the file parses, that every path or test
file it names still exists, and that no decision below the highest recorded one lacks a row (a newer decision only prints a notice).
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import glob as globmod
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "traceability/1"
JSON_REL = "docs/design/traceability.json"
MD_REL = "docs/TRACEABILITY.md"
MAX_PROBLEMS = 20
ROOT = Path(__file__).resolve().parent.parent

DECISION_HEAD = re.compile(r"^##\s+D(\d+)\s*[\u2014\u2013-]\s*(.+?)\s*$")
# a decision number that stands alone: not the tail of ORCH-D5, UI-D6 or ENG-D1, not a word like D3.js
DNUM = re.compile(r"(?<![A-Za-z0-9\-])D(\d+)(?![\w\-]|\.\w)")
SUPERSEDES = re.compile(r"supersed\w*\s+(?:the\s+)?D(\d+)")
# a source tag of a decision: S4-fnodes-07, ENG-D3, ORCH-D5, UI-D6, CD12, DL4, FN-9, G03 (the notes and the code cite these, not D-numbers)
SOURCE_TAG = re.compile(r"(?<![\w\-])(?:CD\d+|DL\d+|FN-\d+|G\d{2}|[A-Z][A-Za-z0-9]*-(?:[A-Za-z]+-)?D?\d+)(?![\w\-])")
TEST_PATH = re.compile(r"tests/[\w/.\-]+\.(?:py|mjs|js)\b")


# ---- small helpers -----------------------------------------------------------------------------------------------------------------

def natural(text: str) -> list:
    """Sort key: E2 before E10, CN-9 before ORCH-1."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def ranges(numbers: list[int]) -> str:
    """[1, 2, 3, 5] -> 'D1-D3, D5' (display only)."""
    numbers = sorted(set(numbers))
    out, i = [], 0
    while i < len(numbers):
        j = i
        while j + 1 < len(numbers) and numbers[j + 1] == numbers[j] + 1:
            j += 1
        out.append(f"D{numbers[i]}" if i == j else f"D{numbers[i]}-D{numbers[j]}")
        i = j + 1
    return ", ".join(out)


def d_number(key: str) -> int:
    return int(key[1:])


# ---- parsers (each takes text or a small structure, so tests can feed fixtures) -----------------------------------------------------

def parse_decisions(text: str) -> list[dict]:
    """Every `## D<n> - title` section: id, title, the text of its bullets by label (Decided, Rejected, Diagram, Sources) and its body."""
    found: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        head = DECISION_HEAD.match(line)
        if head:
            current = {"n": int(head.group(1)), "id": f"D{head.group(1)}", "title": head.group(2), "body": []}
            found.append(current)
        elif line.startswith("## "):
            current = None
        elif current is not None:
            current["body"].append(line)
    for item in found:
        body = "\n".join(item["body"])
        item["body"] = body
        for label in ("Sources", "Decided", "Rejected", "Diagram", "Status"):
            match = re.search(rf"^- {label}:\s*(.*)$", body, re.M)
            item[label.lower()] = match.group(1).strip() if match else ""
    return found


def parse_owner_rules(text: str) -> list[dict]:
    """The rows of the table under `## Owner rules`: {rule, source}."""
    rules, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.lower().startswith("## owner rules")
            continue
        if inside and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0] and not set(cells[0]) <= set("-: ") and cells[0] != "Rule":
                rules.append({"rule": cells[0], "source": cells[1]})
    return rules


def parse_notes(text: str, name: str) -> dict:
    """One notes file: its package id (the file name), title, section headings, decisions and test files it cites."""
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")
    sections = [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]
    return {"id": name[:-3] if name.endswith(".md") else name, "title": title, "sections": sections,
            "decisions": sorted({int(m.group(1)) for m in DNUM.finditer(text)}),
            "tags": sorted(set(SOURCE_TAG.findall(text))),
            "tests": sorted(set(TEST_PATH.findall(text))), "lines": len(text.splitlines())}


def parse_plan(plan: dict) -> list[dict]:
    """The work packages of build-plan.json, validated: every entry needs id, title, owns, depends_on, section; ids are unique."""
    packages, seen = [], set()
    entries = plan.get("work_packages") if isinstance(plan, dict) else None
    if not isinstance(entries, list):
        raise ValueError("the plan has no work_packages list")
    for entry in entries:
        if not isinstance(entry, dict) or "id" not in entry:
            raise ValueError(f"a plan entry has no id: {entry!r}")
        missing = [key for key in ("title", "owns", "depends_on", "section") if key not in entry]
        if missing:
            raise ValueError(f"plan entry {entry['id']} lacks {', '.join(missing)}")
        if entry["id"] in seen:
            raise ValueError(f"plan entry {entry['id']} appears twice")
        seen.add(entry["id"])
        packages.append({"id": entry["id"], "title": entry["title"], "section": entry["section"],
                         "owns": list(entry["owns"]), "depends_on": list(entry["depends_on"])})
    return sorted(packages, key=lambda p: natural(p["id"]))


def parse_merge_log(text: str) -> dict[str, list[str]]:
    """`hash|Merge wp/<id>` lines (newest first) -> {id: [short hashes]}."""
    merges: dict[str, list[str]] = {}
    for line in text.splitlines():
        match = re.match(r"^([0-9a-f]{7,40})\|Merge wp/(\S+)\s*$", line)
        if match:
            merges.setdefault(match.group(2), []).append(match.group(1))
    return merges


def load_features(path: Path):
    """FEATURES of sutra_app/engine/features.py, loaded from the file itself (it imports only dataclasses)."""
    name = "_traceability_features"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return list(module.FEATURES)


def parse_chip_labels(gen_text: str) -> list[str]:
    """The labels of the `chips = [(label, sub), ...]` list of docs/diagram/gen.py (read as text, never run)."""
    for node in ast.walk(ast.parse(gen_text)):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "chips" for t in node.targets):
            return [elt.elts[0].value for elt in node.value.elts if isinstance(elt, ast.Tuple)]
    return []


def literal_assign(text: str, name: str):
    """The literal value of a module level `name = ...` (or `name: T = ...`) in `text`, or None."""
    for node in ast.parse(text).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def parse_view_names(views_text: str) -> list[str]:
    """The names in `VIEWS = {fn.__name__: fn for fn in (index, vendor, ...)}` of sutra_app/engine/views.py, in order."""
    for node in ast.walk(ast.parse(views_text)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "VIEWS" for t in targets) and isinstance(node.value, ast.DictComp):
            return [elt.id for elt in node.value.generators[0].iter.elts]
    return []


def parse_j2_exact(js_text: str) -> list[str]:
    """`J2_EXACT` of sutra_ctx.js: the exact J2 paths the page calls (the list the route-table contract test compares)."""
    match = re.search(r"const J2_EXACT = \[(.*?)\];", js_text, re.S)
    return re.findall(r'"([^"]+)"', match.group(1)) if match else []


def golden_owner(key: str, names: list[str]) -> str | None:
    """The view a golden key belongs to: the longest name that is the key or its prefix before an underscore."""
    best = None
    for name in names:
        if key == name or key.startswith(name + "_"):
            if best is None or len(name) > len(best):
                best = name
    return best


# ---- path ownership ----------------------------------------------------------------------------------------------------------------

def owner_of(path: str, packages: list[dict]) -> str | None:
    """The package whose `owns` names `path` exactly, as a folder prefix or by glob (the first in id order)."""
    for package in packages:
        for pattern in package["owns"]:
            if path == pattern or (pattern.endswith("/") and path.startswith(pattern)) or (
                    "*" in pattern and fnmatch.fnmatchcase(path, pattern)):
                return package["id"]
    return None


def path_problem(root: Path, rel: str) -> str | None:
    """None when `rel` names something that exists under root (a folder when it ends in `/`, at least one match for a glob)."""
    if not isinstance(rel, str) or not rel:
        return f"empty path {rel!r}"
    if rel.startswith("/") or ".." in Path(rel).parts:
        return f"{rel}: not a path inside the repository"
    if any(ch in rel for ch in "*?["):
        return None if globmod.glob(str(root / rel)) else f"{rel}: the pattern matches nothing"
    target = root / rel
    if rel.endswith("/"):
        return None if target.is_dir() else f"{rel}: folder does not exist"
    return None if target.exists() else f"{rel}: file does not exist"


# ---- the curated rows (owner rules and the seven steps are judgment, not parsing; the check proves every path is real) ----------------

FN_MODULES = ["sutra_app/engine/fnodes/layer.py", "sutra_app/engine/fnodes/declare.py", "sutra_app/engine/fnodes/registry.py",
              "sutra_app/engine/fnodes/checks.py", "sutra_app/engine/fnodes/evidence.py", "sutra_app/library/node.py",
              "sutra_app/library/atom.py", "sutra_app/library/functions.py", "sutra_app/orchestrator/atoms.py",
              "sutra_app/orchestrator/nodes.py"]
OWNER_RULE_MAP = [
    ("no relation to the old sutra-ui", [1, 4, 6, 13, 89, 90, 91],
     ["sutra_app/engine/VENDORED.md", "sutra_app/engine/j2.py", "sutra_app/ui/pages/j2_ui.html", "sutra_app/ui/routes.py",
      "scripts/vendor_j2.py", "scripts/port_j2_ui.py"],
     ["tests/engine/test_engine_vendor.py", "tests/engine/test_engine_patches.py", "tests/ui/test_port_edits.py",
      "tests/ui/test_serve.py"]),
    ("ONE global org chart", [26, 42, 43, 44, 67, 68, 70],
     ["sutra_app/library/org_chart.py", "sutra_app/orchestrator/chart.py", "sutra_app/orchestrator/chart_rules.py",
      "sutra_app/orchestrator/agent/planner.py", "sutra_app/orchestrator/graph.py"],
     ["tests/library/test_lib_org_chart.py", "tests/library/test_lib_chart_change.py", "tests/orchestrator/test_chart_store.py",
      "tests/orchestrator/test_chart_rules.py", "tests/orchestrator/test_chat_agent.py"]),
    ("Everything in the J2 prototype", [4, 13, 25, 46, 47, 84, 90, 91],
     ["sutra_app/engine/features.py", "sutra_app/engine/views.py", "sutra_app/engine/j2.py", "sutra_app/engine/api/__init__.py",
      "sutra_app/ui/pages/j2_ui.html", "docs/reference/"],
     ["tests/engine/test_engine_features.py", "tests/engine/test_engine_views.py", "tests/engine/test_engine_prompts.py",
      "tests/engine/test_engine_legacy.py", "tests/contracts/test_contract_route_table.py", "tests/library/test_lib_engine_parity.py"]),
    ("agentic graph node", list(range(49, 67)), FN_MODULES,
     ["tests/engine/test_engine_fn_layer.py", "tests/engine/test_engine_fn_checks.py", "tests/engine/test_engine_fn_declare.py",
      "tests/engine/test_engine_fn_registry.py", "tests/engine/test_engine_fn_mutations.py", "tests/engine/test_engine_fn_golden.py",
      "tests/library/test_lib_node.py", "tests/library/test_lib_atom.py", "tests/library/test_lib_functions.py",
      "tests/contracts/test_contract_fnodes.py", "tests/orchestrator/test_projector_fnodes.py", "tests/orchestrator/test_atoms_usage.py"]),
    ("connector layer", [7, 17] + list(range(27, 39)),
     ["sutra_app/connectors/base.py", "sutra_app/connectors/router.py", "sutra_app/connectors/claude.py", "sutra_app/connectors/codex.py",
      "sutra_app/connectors/stub.py", "sutra_app/connectors/policy.py", "sutra_app/connectors/factory.py",
      "sutra_app/connectors/health.py", "sutra_app/connectors/usage.py", "sutra_app/connectors/orchestrator_port.py",
      "sutra_app/connectors/engine_port.py"],
     ["tests/connectors/test_claude_connector.py", "tests/connectors/test_codex_connector.py", "tests/connectors/test_router_plan.py",
      "tests/connectors/test_router_attempts.py", "tests/connectors/test_stub.py", "tests/connectors/test_policy.py",
      "tests/connectors/test_live.py"]),
    ("Decide autonomously", None,
     ["docs/DECISIONS.md", "docs/DESIGN.md", "docs/diagram/decisions.json", "docs/diagram/gen.py", "docs/design/decision-index.json",
      "scripts/build_traceability.py"],
     ["tests/contracts/test_contract_diagram_strings.py", "tests/test_traceability.py"]),
    ("never push", [1, 89],
     ["scripts/wt.sh", "scripts/gate.sh", "scripts/py", "scripts/plan_tools.py", "docs/BUILD-PLAN.md"],
     ["tests/test_build_plan.py", "tests/test_layout.py"]),
]

# Decisions whose packages neither notes nor code name by D-number or source tag, curated by hand from the package titles. They count as
# implemented; a decision that is a process rule or a recorded non-decision (D87, D91, D93, D96) stays "documented only".
DECISION_PACKAGES = {
    8: ["CN-2", "CN-5", "UI-0"], 10: ["ORCH-2", "UI-3"], 12: ["GAP-OPS-1", "ORCH-8"], 26: ["E0", "E3"], 30: ["CN-6"],
    39: ["L1", "L5", "L7"], 40: ["L1", "L8"], 50: ["L4", "L5", "L6"], 69: ["ORCH-7"], 90: ["E1", "E2", "E5", "L7", "L8", "UI-2"],
}

# step n -> (draw.io step, modules, tests that exist now, the gap the coverage critic named)
STEPS = [
    ("1 Chat agent reads the chart; does the requirement fit the org",
     ["sutra_app/orchestrator/agent/agent.py", "sutra_app/orchestrator/agent/prompts.py", "sutra_app/orchestrator/chart.py"],
     ["tests/orchestrator/test_chat_agent.py", "tests/orchestrator/test_agent_demo.py", "tests/integration/test_offline_demo.py",
      "tests/e2e/test_scenario_new_team.py"],
     "run end to end by tests/e2e (GAP-E2E); a real model reading the digest is the live smoke (GAP-LIVE, run on the owner's say-so)"),
    ("2 For a new department or workflow the agent references the models library",
     ["sutra_app/orchestrator/agent/planner.py", "sutra_app/library/registry.py", "sutra_app/library/wire.py"],
     ["tests/orchestrator/test_chat_agent.py", "tests/library/test_lib_registry.py", "tests/library/test_lib_transport.py",
      "tests/e2e/test_scenario_new_team.py"],
     "prompt content is tested in the e2e scenario; a model that reads the schema is the live smoke (GAP-LIVE)"),
    ("3 claude cli + python models build structured workflows and a visual graph",
     ["sutra_app/connectors/router.py", "sutra_app/connectors/claude.py", "sutra_app/connectors/orchestrator_port.py",
      "sutra_app/library/workflow.py", "sutra_app/orchestrator/tasks.py", "sutra_app/orchestrator/graph.py"],
     ["tests/connectors/test_orchestrator_port.py", "tests/connectors/test_claude_connector.py", "tests/connectors/test_router_json.py",
      "tests/library/test_lib_workflow.py", "tests/orchestrator/test_scripted_conversation.py", "tests/e2e/test_scenario_fake_cli.py"],
     "run through the real router over the fake claude and codex (GAP-E2E); the real CLIs are the live smoke (GAP-LIVE)"),
    ("4 The graph is visible",
     ["sutra_app/orchestrator/api/graph.py", "sutra_app/orchestrator/graph.py", "sutra_app/ui/static/js/graph_render.js"],
     ["tests/orchestrator/test_api_graph.py", "tests/orchestrator/test_graph_store.py", "tests/ui/test_view_graph.py",
      "tests/ui/js/graph_render.test.js", "tests/ui/js/graph_layout.test.js", "tests/e2e/test_scenario_new_team.py",
      "tests/e2e/test_browser_real_app.py"],
     "the browser walk against the real app runs with SUTRA_BROWSER=1 (GAP-E2E-UI)"),
    ("5 Each node is linked to its chat session",
     ["sutra_app/orchestrator/nodes.py", "sutra_app/orchestrator/chats.py", "sutra_app/ui/static/js/fnode_view.js"],
     ["tests/orchestrator/test_graph_store.py", "tests/orchestrator/test_chat_store.py", "tests/ui/test_view_panel.py",
      "tests/ui/js/fnode_view.test.js", "tests/e2e/test_scenario_new_team.py"],
     "the e2e scenario resolves every node's chat session from the real graph (GAP-E2E)"),
    ("6 The graph updates dynamically from agent interaction",
     ["sutra_app/engine/host/publisher.py", "sutra_app/orchestrator/projector.py", "sutra_app/orchestrator/events.py",
      "sutra_app/orchestrator/api/events.py", "sutra_app/ui/static/js/sutra_events.js"],
     ["tests/orchestrator/test_projector.py", "tests/orchestrator/test_projector_fnodes.py", "tests/orchestrator/test_events_sse.py",
      "tests/ui/js/events.test.js", "tests/integration/test_offline_demo.py", "tests/e2e/test_scenario_new_team.py",
      "tests/e2e/test_scenario_restart_stop.py", "tests/e2e/test_browser_resync.py"],
     "the live chain, engine to browser, is run by GAP-E2E and GAP-E2E-UI"),
    ("7 Each department and division is linked to its chat",
     ["sutra_app/orchestrator/departments.py", "sutra_app/orchestrator/chats.py", "sutra_app/ui/static/js/chat_view.js"],
     ["tests/orchestrator/test_departments.py", "tests/orchestrator/test_chat_store.py", "tests/ui/test_view_panel.py",
      "tests/ui/js/chat_view.test.js", "tests/e2e/test_scenario_new_team.py"],
     "as step 5"),
]


# ---- building the document ---------------------------------------------------------------------------------------------------------

def git_merges(root: Path) -> dict[str, list[str]]:
    try:
        out = subprocess.run(["git", "-C", str(root), "log", "--merges", "--format=%h|%s", "--grep=^Merge wp/"], capture_output=True,
                             text=True, timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse_merge_log(out)


SELF_FILES = {"tests/test_traceability.py"}      # this package's own tests quote decision numbers as fixtures: not evidence


def code_refs(root: Path) -> dict[str, set[str]]:
    """{'D12' or a source tag: files of sutra_app/ and tests/ that cite it}."""
    refs: dict[str, set[str]] = {}
    for top in ("sutra_app", "tests"):
        for path in sorted((root / top).rglob("*")):
            if path.suffix not in (".py", ".js", ".mjs", ".html") or "__pycache__" in path.parts or not path.is_file():
                continue
            try:
                text = read(path)
            except (OSError, UnicodeDecodeError):
                continue
            rel = path.relative_to(root).as_posix()
            if rel in SELF_FILES:
                continue
            for token in {f"D{m.group(1)}" for m in DNUM.finditer(text)} | set(SOURCE_TAG.findall(text)):
                refs.setdefault(token, set()).add(rel)
    return refs


def build_document(root: Path, merges: dict[str, list[str]] | None = None) -> dict:
    plan = parse_plan(json.loads(read(root / "docs" / "build-plan.json")))
    plan_ids = [p["id"] for p in plan]
    decisions_text = read(root / "docs" / "DECISIONS.md")
    decisions = parse_decisions(decisions_text)
    rules = parse_owner_rules(decisions_text)
    notes = {}
    for path in sorted((root / "docs" / "notes").glob("*.md")):
        notes[path.stem] = parse_notes(read(path), path.name)
    merges = git_merges(root) if merges is None else merges
    refs = code_refs(root)
    id_pattern = re.compile(r"(?<![A-Za-z0-9\-])(" + "|".join(re.escape(i) for i in sorted(plan_ids, key=len, reverse=True)) +
                            r")(?![A-Za-z0-9\-])")
    all_d = [d["n"] for d in decisions]

    # (f) packages
    packages = []
    for p in plan:
        note = notes.get(p["id"])
        commits = merges.get(p["id"], [])
        packages.append({
            "id": p["id"], "title": p["title"], "section": p["section"], "depends_on": sorted(p["depends_on"], key=natural),
            "owns": sorted(p["owns"]), "notes": f"docs/notes/{p['id']}.md", "notes_lines": note["lines"] if note else 0,
            "decisions_cited": [f"D{n}" for n in note["decisions"]] if note else [],
            "merge_commits": commits, "status": "merged" if commits else "pending"})

    # (a) owner rules
    owner_rows = []
    for rule in rules:
        entry = next((e for e in OWNER_RULE_MAP if e[0].lower() in rule["rule"].lower()), None)
        ids = (all_d if entry and entry[1] is None else entry[1] if entry else [])
        owner_rows.append({"rule": rule["rule"], "source": rule["source"],
                           "decisions": [f"D{n}" for n in sorted(set(ids)) if n in all_d],
                           "modules": list(entry[2]) if entry else [], "tests": list(entry[3]) if entry else []})

    # (b) steps
    step_rows = [{"step": text, "modules": mods, "tests": tests, "later_tests": f"tests/e2e/test_step{i}_*",
                  "gap": gap} for i, (text, mods, tests, gap) in enumerate(STEPS, start=1)]

    # (c) chips
    features = [f for f in load_features(root / "sutra_app" / "engine" / "features.py") if f.kind == "chip"]
    labels = parse_chip_labels(read(root / "docs" / "diagram" / "gen.py"))
    chip_rows = []
    for i, feature in enumerate(features):
        chip_rows.append({"id": feature.id, "chip": feature.chip, "diagram_label": labels[i] if i < len(labels) else "",
                          "modules": sorted(f"sutra_app/engine/{f}" for f in feature.files), "flags": sorted(feature.flags),
                          "tests": ["tests/engine/test_engine_features.py"]})

    # (d) endpoints
    api_dir = root / "sutra_app" / "engine" / "api"
    get_routes, post_routes = {}, {}
    for path in sorted(api_dir.glob("*.py")):
        routes = literal_assign(read(path), "ROUTES")
        if routes and path.name == "commands.py":
            post_routes.update({name: (route, path.name) for route, name in routes})
        elif routes:
            get_routes.update({name: (route, path.name) for route, name in routes})
    names = parse_view_names(read(root / "sutra_app" / "engine" / "views.py"))
    golden = json.loads(read(root / "tests" / "engine" / "golden" / "api_shapes.json"))
    golden_keys: dict[str, list[str]] = {}
    for kind in ("get", "post"):
        keys = set(golden.get(kind, {}).get("live", {}) if kind == "get" else golden.get(kind, {}))
        for key in sorted(keys):
            owner = golden_owner(key, names)
            if owner:
                golden_keys.setdefault(owner, []).append(key)
    exact = set(parse_j2_exact(read(root / "sutra_app" / "ui" / "static" / "js" / "sutra_ctx.js")))
    endpoint_rows, number = [], 0
    for name in names:
        variants = [("GET", "/site/{key}?run=", "saved"), ("GET", "/site/{key}", "live")] if name == "site" else [None]
        for variant in variants:
            number += 1
            if name in post_routes:
                method, route, adapter = "POST", post_routes[name][0], f"sutra_app/engine/api/{post_routes[name][1]}"
            elif name in get_routes:
                method, route, adapter = "GET", get_routes[name][0], f"sutra_app/engine/api/{get_routes[name][1]}"
            else:
                method = "GET"
                route = {"index": "/", "vendor": "/vendor/d3.min.js"}.get(name, "")
                adapter = "sutra_app/ui/routes.py"
            if variant:
                route = variant[1]
            endpoint_rows.append({
                "n": number, "name": name + (f" ({variant[2]})" if variant else ""), "method": method, "path": route,
                "handler": "sutra_app/engine/views.py", "adapter": adapter,
                "in_ui_list": route in exact or route.split("?")[0] in exact,
                "golden_keys": golden_keys.get(name, []),
                "tests": ["tests/engine/test_engine_views.py", "tests/engine/golden/api_shapes.json",
                          "tests/engine/test_engine_api_scope.py", "tests/contracts/test_contract_route_table.py"]})

    # (e) decisions
    superseded: dict[int, list[int]] = {}
    for d in decisions:
        for m in SUPERSEDES.finditer(d["body"]):
            superseded.setdefault(int(m.group(1)), []).append(d["n"])
    decision_rows = []
    for d in decisions:
        tokens = {d["id"]} | set(SOURCE_TAG.findall(d["sources"]))
        in_notes = sorted((pid for pid, n in notes.items() if pid in plan_ids and (
            d["n"] in n["decisions"] or tokens & set(n["tags"]))), key=natural)
        cited_in = {f for token in tokens for f in refs.get(token, ())}
        in_code = sorted({owner_of(f, plan) for f in cited_in if owner_of(f, plan)}, key=natural)
        in_body = sorted(set(id_pattern.findall(d["body"])), key=natural)
        curated = [i for i in DECISION_PACKAGES.get(d["n"], []) if i in plan_ids]
        touched = sorted(set(in_notes) | set(in_code) | set(in_body) | set(curated), key=natural)
        rejected = bool(re.search(r"\b(rejected|vetoed|withdrawn)\b", d["status"] + " " + d["title"], re.I))
        status = "rejected" if rejected else "implemented" if (in_notes or in_code or curated) else "documented only"
        decision_rows.append({"id": d["id"], "title": d["title"], "packages": touched, "status": status,
                              "superseded_by": [f"D{n}" for n in sorted(superseded.get(d["n"], []))],
                              "diagram": d["diagram"][:160]})

    return {
        "schema": SCHEMA,
        "counts": {"decisions": len(decision_rows), "packages": len(packages), "endpoints": len(endpoint_rows), "chips": len(chip_rows),
                   "steps": len(step_rows), "owner_rules": len(owner_rows)},
        "max_decision": max(all_d) if all_d else 0,
        "owner_rules": owner_rows, "steps": step_rows, "chips": chip_rows, "endpoints": endpoint_rows,
        "decisions": decision_rows, "packages": packages}


# ---- the markdown ------------------------------------------------------------------------------------------------------------------

def cell(value) -> str:
    text = ", ".join(value) if isinstance(value, list) else str(value)
    return (text or "-").replace("|", "\\|").replace("\n", " ")


def code_list(items: list[str]) -> str:
    return "<br>".join(f"`{i}`" for i in items) if items else "-"


def render_markdown(doc: dict) -> str:
    out = ["# Traceability matrix", "",
           "_Generated by `scripts/build_traceability.py` from `docs/build-plan.json`, `docs/DECISIONS.md`, `docs/notes/*.md`, "
           "`sutra_app/engine/features.py`, the engine route table, `docs/diagram/` and `git log`. Do not edit by hand; run "
           "`scripts/py scripts/build_traceability.py` to refresh it. The machine copy is `docs/design/traceability.json`; "
           "`--check` verifies that every path named there still exists and that no decision lacks a row._", ""]
    c = doc["counts"]
    out += [f"{c['owner_rules']} owner rules, {c['steps']} draw.io steps, {c['chips']} chips, {c['endpoints']} J2 endpoints, "
            f"{c['decisions']} decisions (D1 to D{doc['max_decision']}), {c['packages']} work packages.", ""]

    out += ["## A. Owner rules", "", "| Rule | Source | Decisions | Modules | Tests |", "|---|---|---|---|---|"]
    for r in doc["owner_rules"]:
        out.append(f"| {cell(r['rule'])} | {cell(r['source'])} | {ranges([d_number(x) for x in r['decisions']]) or '-'} | "
                   f"{code_list(r['modules'])} | {code_list(r['tests'])} |")

    out += ["", "## B. The seven draw.io steps", "", "| Step | Modules | Tests today | Later tests | Gap |", "|---|---|---|---|---|"]
    for r in doc["steps"]:
        out.append(f"| {cell(r['step'])} | {code_list(r['modules'])} | {code_list(r['tests'])} | `{r['later_tests']}` | {cell(r['gap'])} |")

    out += ["", "## C. The 15 chips of the runtime strip", "", "| Chip | Diagram label | Modules (under `sutra_app/engine/`) | Flags |", "|---|---|---|---|"]
    for r in doc["chips"]:
        mods = [m.replace("sutra_app/engine/", "", 1) for m in r["modules"]]
        out.append(f"| {cell(r['id'] + ': ' + r['chip'])} | {cell(r['diagram_label'])} | {code_list(mods)} | {cell(r['flags'])} |")

    out += ["", "## D. The 30 J2 endpoints", "",
            "| # | View | Method and path | Handler | Served by | Golden keys | In the page's list |", "|---|---|---|---|---|---|---|"]
    for r in doc["endpoints"]:
        out.append(f"| {r['n']} | {cell(r['name'])} | {r['method']} `{r['path']}` | `{r['handler']}` | `{r['adapter']}` | "
                   f"{cell(r['golden_keys'])} | {'yes' if r['in_ui_list'] else 'no'} |")
    out += ["", "Golden tests of every row: " + ", ".join(f"`{t}`" for t in doc["endpoints"][0]["tests"]) + ".", ""]

    out += ["## E. Decisions", "", "| Decision | Title | Packages | Status |", "|---|---|---|---|"]
    for r in doc["decisions"]:
        status = r["status"] + (f" (superseded by {', '.join(r['superseded_by'])})" if r["superseded_by"] else "")
        out.append(f"| {r['id']} | {cell(r['title'])} | {cell(r['packages'])} | {status} |")

    out += ["", "## F. Work packages", "", "| Package | Section | Owns | Notes | Merge commit |", "|---|---|---|---|---|"]
    for r in doc["packages"]:
        commits = ", ".join(r["merge_commits"]) if r["merge_commits"] else "pending"
        out.append(f"| {r['id']} | {r['section']} | {code_list(r['owns'])} | `{r['notes']}` | {commits} |")
    return "\n".join(out) + "\n"


def dump_json(doc: dict) -> str:
    return json.dumps(doc, indent=1, sort_keys=False, ensure_ascii=False) + "\n"


# ---- --check -----------------------------------------------------------------------------------------------------------------------

def check(root: Path) -> tuple[list[str], list[str]]:
    """(problems, notices) of the committed traceability.json against the repository at `root`."""
    problems: list[str] = []
    notices: list[str] = []
    target = root / JSON_REL
    if not target.is_file():
        return [f"{JSON_REL}: file does not exist (run scripts/build_traceability.py)"], notices
    try:
        doc = json.loads(read(target))
    except ValueError as exc:
        return [f"{JSON_REL}: does not parse: {exc}"], notices
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        return [f"{JSON_REL}: schema is not {SCHEMA}"], notices
    sections = ("owner_rules", "steps", "chips", "endpoints", "decisions", "packages")
    for key in sections:
        if not isinstance(doc.get(key), list) or not doc[key]:
            problems.append(f"{JSON_REL}: section {key} is missing or empty")
    if problems:
        return problems, notices

    def look(label: str, rel: str) -> None:
        issue = path_problem(root, rel)
        if issue:
            problems.append(f"{label}: {issue}")

    for row in doc["owner_rules"]:
        if not row.get("modules") or not row.get("tests"):
            problems.append(f"owner rule {row.get('rule', '?')!r}: no module or no test is named")
        for rel in row.get("modules", []) + row.get("tests", []):
            look(f"owner rule {row.get('rule', '?')[:30]!r}", rel)
    for row in doc["steps"]:
        for rel in row.get("modules", []) + row.get("tests", []):
            look(f"step {row.get('step', '?')[:12]!r}", rel)
    for row in doc["chips"]:
        for rel in row.get("modules", []) + row.get("tests", []):
            look(f"chip {row.get('id', '?')}", rel)
    for row in doc["endpoints"]:
        for rel in [row.get("handler"), row.get("adapter")] + row.get("tests", []):
            look(f"endpoint {row.get('n', '?')} {row.get('name', '?')}", rel)
    package_ids = {row.get("id") for row in doc["packages"]}
    for row in doc["packages"]:
        label = f"package {row.get('id', '?')}"
        if row.get("status") == "merged":
            look(label, row.get("notes", ""))
            for rel in row.get("owns", []):
                look(label, rel)
            if not row.get("merge_commits"):
                problems.append(f"{label}: merged but no merge commit is recorded")
    recorded = set()
    for row in doc["decisions"]:
        recorded.add(row.get("id"))
        for pid in row.get("packages", []):
            if pid not in package_ids:
                problems.append(f"decision {row.get('id')}: names the unknown package {pid}")
    present = {d["id"]: d["n"] for d in parse_decisions(read(root / "docs" / "DECISIONS.md"))}
    recorded_max = max((d_number(i) for i in recorded if isinstance(i, str) and re.fullmatch(r"D\d+", i)), default=0)
    for did, n in sorted(present.items(), key=lambda kv: kv[1]):
        if did not in recorded:
            if n <= recorded_max:
                problems.append(f"{did}: has a heading in docs/DECISIONS.md but no row in {JSON_REL}")
            else:
                notices.append(f"{did}: newer than the last recorded decision (D{recorded_max}); refresh with scripts/build_traceability.py")
    for did in sorted(recorded - set(present), key=natural):
        problems.append(f"{did}: has a row in {JSON_REL} but no heading in docs/DECISIONS.md")
    return problems, notices


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="verify the committed traceability.json (exit 1 on problems)")
    ap.add_argument("--root", default=str(ROOT), help="repository root (default: the checkout holding this script)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if args.check:
        problems, notices = check(root)
        for line in notices:
            print(f"notice: {line}", file=sys.stderr)
        for line in problems[:MAX_PROBLEMS]:
            print(f"problem: {line}")
        if len(problems) > MAX_PROBLEMS:
            print(f"... and {len(problems) - MAX_PROBLEMS} more")
        if problems:
            print(f"traceability check: {len(problems)} problem(s); fix the paths or run scripts/py scripts/build_traceability.py")
            return 1
        print("traceability check: ok")
        return 0
    doc = build_document(root)
    (root / JSON_REL).write_text(dump_json(doc), encoding="utf-8")
    (root / MD_REL).write_text(render_markdown(doc), encoding="utf-8")
    print(f"wrote {JSON_REL} and {MD_REL}: " + ", ".join(f"{v} {k}" for k, v in doc["counts"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
