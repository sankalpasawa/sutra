"""python3 j2_agent_views.py build <run_dir> | --all [--runs DIR]: the agent-readable JSON of every artifact of a saved run.

Each artifact of a run folder gets a Pydantic-validated JSON where j2_artifacts.agent_view() looks for it, so the
Artifacts pane's Agent-readable tab shows its model, its schema and the real "valid" mark:
  guides       artifacts/<name>.md        -> artifacts/<name>.json            (j2_agent_models.Guide and its kinds)
  documents    prd.md / hld.md / lld.md   -> prd.json / hld.json / lld.json   (artifact-schema/1 data, "model" and "valid" added)
  style guide  style.json                 -> design.json                      (artifact-schema/1 Design, "model" and "valid" added)
  sections     site/index.html            -> site/sections/<id>.json          (artifact-schema/1 WebsiteSection)
  records      goal.json, workflows.json, receipts.jsonl, conditions.json -> agent/<name>.json
  audits       audits.json                -> agent/audits/A-1.json, A-2.json, ...
Data a run did not save is written as "not recorded"; nothing is guessed, and "valid" is always the result of the
validation that just ran. Files the run keeps are read, never rewritten, except the artifact-schema JSONs, which only
gain top-level keys. Nothing here reads .env, calls.jsonl or any secret.
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import j2_agent_models as G      # noqa: E402

RUNS_DIR = os.environ.get("J2_RUNS_DIR") or os.path.join(HERE, "runs")
DELIVERED_MD = ("prd.md", "hld.md", "lld.md", "report.md")      # documents and the report are not guides


def _read_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _read_text(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _write_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _rel(d, p):
    return os.path.relpath(p, d).replace(os.sep, "/")


def _result(kind, model, path, valid, note=""):
    return {"kind": kind, "model": model, "path": path, "valid": valid, "note": note}


# ---------------------------------------------------------------------------------------------------- step 1: guides
_HEAD = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")


def parse_guide(text):
    """(title, purpose, sections) of a markdown guide: the first level-1 heading is the title (else the first heading of
    any level); the prose before the first heading is the purpose; every heading opens a section with its paragraphs
    and bullet points. Fenced code is kept as text."""
    title, purpose_lines, sections, cur, fence = None, [], [], None, False
    for raw in text.split("\n"):
        line = raw.rstrip()
        if line.startswith("```"):
            fence = not fence
        m = None if fence else _HEAD.match(line)
        if m:
            level, heading = len(m.group(1)), m.group(2).strip()
            if title is None and level == 1:
                title = heading
                continue
            cur = {"heading": heading, "level": level, "text": [], "points": []}
            sections.append(cur)
            continue
        b = None if fence else _BULLET.match(line)
        if cur is None:
            if line.strip():
                purpose_lines.append(line.strip())
        elif b:
            cur["points"].append(b.group(1).strip())
        else:
            cur["text"].append(line)
    if title is None:
        title = sections[0]["heading"] if sections else G.NOT_RECORDED
    out = [{"heading": s["heading"], "level": s["level"], "points": s["points"],
            "text": re.sub(r"\n{3,}", "\n\n", "\n".join(s["text"]).strip())} for s in sections]
    return title, (" ".join(purpose_lines).strip() or G.NOT_RECORDED), out


def guide_files(d, workflows):
    """Every guide a planning workflow wrote: artifacts/**/*.md, and a workflow's .md output at the run's root that is
    not a document or the report. [(relative file, workflow id or None)]."""
    out, seen = [], set()
    by_out = {}
    for w in workflows:
        for o in w.get("outputs") or []:
            by_out.setdefault(str(o), w.get("id"))
    for p in sorted(glob.glob(os.path.join(d, "artifacts", "**", "*.md"), recursive=True)):
        rel = _rel(d, p)
        if rel not in seen:
            seen.add(rel)
            out.append((rel, by_out.get(rel) or by_out.get(os.path.basename(rel))))
    for o, wid in by_out.items():
        if o.endswith(".md") and os.path.basename(o) not in DELIVERED_MD and "/" not in o and o not in seen \
                and os.path.isfile(os.path.join(d, o)):
            seen.add(o)
            out.append((o, wid))
    return out


def build_guides(d, workflows, facts):
    results = []
    for rel, wid in guide_files(d, workflows):
        text = _read_text(os.path.join(d, rel))
        if text is None:
            continue
        title, purpose, sections = parse_guide(text)
        cls = G.guide_model_for(rel)
        data = {"kind": cls.model_fields["kind"].default, "title": title, "purpose": purpose, "audience": G.NOT_RECORDED,
                "sections": sections, "facts_used": [f for f in facts if f and f in text], "source_file": rel,
                "written_by": wid or G.NOT_RECORDED, "words": len(text.split())}
        env = G.envelope(cls, data, {"file": rel, "built_by": "j2_agent_views.py", "from": "the guide's markdown"})
        out = os.path.splitext(rel)[0] + ".json"
        _write_json(os.path.join(d, out), env)
        results.append(_result("guide: " + data["kind"], cls.__name__, out, env["valid"],
                               "written_by not recorded" if not wid else ""))
    return results


# ---------------------------------------------------------------------------------------------------- the run
def build(d, quiet=False):
    """Every agent-readable JSON of one run folder; [{kind, model, path, valid, note}]."""
    d = os.path.abspath(d)
    if not os.path.isdir(d):
        raise SystemExit(f"no such run folder: {d}")
    workflows = _read_json(os.path.join(d, "workflows.json"), []) or []
    goal = _read_json(os.path.join(d, "goal.json"), {}) or {}
    facts = [str(x) for x in (goal.get("facts") or []) if isinstance(x, str)]
    results = []
    results += build_guides(d, workflows, facts)
    if not quiet:
        print_table(d, results)
    return results


def print_table(d, results):
    print(f"{os.path.basename(d)}: {len(results)} agent-readable JSON(s), {sum(1 for r in results if r['valid'])} valid")
    for r in results:
        print(f"  {r['kind']:<28} {r['model']:<16} {r['path']:<44} {'valid' if r['valid'] else 'INVALID'}{('  ' + r['note']) if r['note'] else ''}")


def main(argv):
    if "--all" in argv:
        runs = argv[argv.index("--runs") + 1] if "--runs" in argv else RUNS_DIR
        names = sorted(n for n in os.listdir(runs) if os.path.isfile(os.path.join(runs, n, "workflows.json"))) if os.path.isdir(runs) else []
        total = []
        for n in names:
            total += build(os.path.join(runs, n), quiet="--quiet" in argv)
        print(f"{len(names)} run(s): {len(total)} JSON(s), {sum(1 for r in total if r['valid'])} valid")
        return 0
    if len(argv) >= 2 and argv[0] == "build":
        build(argv[1], quiet="--quiet" in argv)
        return 0
    print(__doc__.strip().split("\n")[0])
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
