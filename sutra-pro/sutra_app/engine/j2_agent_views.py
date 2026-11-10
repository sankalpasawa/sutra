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
from . import j2_agent_models as G
from . import j2_artifact_models as AM
from . import j2_template_lib as L

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


# ---------------------------------------------------------------------------------------------------- step 2: documents
DOC_KINDS = ("prd", "hld", "lld")
_ID_ATTR = re.compile(r'\sid="([^"]+)"')
_CLASS_ATTR = re.compile(r'\sclass="([^"]+)"')


def _decisions(d):
    """The run's template routing decisions (templates.json), oldest first; [] when the run kept none."""
    rec = _read_json(os.path.join(d, "templates.json"), {}) or {}
    return [x for x in (rec.get("decisions") or []) if isinstance(x, dict)]


def _template_for(d, decs, artifact, section, workflow=None):
    """(template, where) the run used for one section: the decision's saved copy in the run, else the library's copy,
    else the generic template; (None, why) when a specialised template is nowhere to be found."""
    mine = [x for x in decs if x.get("artifact") == artifact and x.get("section") == section
            and (workflow is None or x.get("workflow") == workflow)]
    if not mine:
        g = L.generic(artifact, section)
        return (g, "the generic template (no routing decision recorded)") if g else (None, "no template for this section")
    dec = mine[-1]
    if dec.get("kind") == "generic":
        return L.generic(artifact, section), "the generic template (the run's decision)"
    sd = L.run_saved_dir(d, dec)
    if sd:
        got = L.load_dir(sd)
        if got:
            return L.SpecialisedTemplate.model_validate({**got[0], "used_by": (got[1] or {}).get("used_by") or []}), "the run's saved copy"
    t = L.get(f"{dec.get('template')}@{dec.get('version')}", artifact, section)
    if t is not None:
        return t, "the library's copy"
    return None, f"template {dec.get('template')} v{dec.get('version')} is neither saved in the run nor in the library"


def _validate_sections(d, kind, sections, decs):
    """{section: {model, template, valid, errors, from}} for an artifact-schema/1 data file's sections, each against the
    template the run routed it to (the specialised class, then the generic model on its fields), as j2.py did at the time."""
    out = {}
    for name, data in (sections or {}).items():
        gmodel = (AM.SECTION_MODELS.get(kind) or {}).get(name)
        if gmodel is None:
            out[name] = {"model": None, "template": None, "valid": False, "errors": [f"no model for a {kind} section named {name!r}"], "from": None}
            continue
        t, where = _template_for(d, decs, kind, name)
        if t is None:
            obj, errs = G.validate(gmodel, AM.normalise(gmodel, data))
            out[name] = {"model": gmodel.__name__, "template": None, "valid": obj is not None,
                         "errors": errs + [f"checked against the generic model: {where}"], "from": where}
            continue
        got, errs = L.validate(t, data)
        out[name] = {"model": L.class_name(t), "template": f"{t.name} v{t.version}", "valid": not errs, "errors": errs, "from": where}
    return out


def _stamp(rec, kind, validation):
    """The top-level keys the Agent-readable tab reads, added to an artifact-schema/1 data file; every existing key kept."""
    rec["model"] = AM.DOC_MODELS[kind].__name__
    rec["valid"] = bool(validation) and all(v["valid"] for v in validation.values())
    rec["validation"] = validation
    rec["agent_views"] = G.SCHEMA
    return rec


def build_documents(d, decs):
    """prd.json / hld.json / lld.json beside each document: artifact-schema/1 data (the builders' own replies), each
    section validated against its model, and "model" / "valid" added at the top. A document with a .md and no data
    file is reported, not invented."""
    results = []
    for kind in DOC_KINDS:
        md, data = os.path.join(d, f"{kind}.md"), os.path.join(d, f"{kind}.json")
        if not os.path.isfile(md):
            continue
        rec = _read_json(data)
        if not isinstance(rec, dict) or not isinstance(rec.get("sections"), dict):
            results.append(_result(f"document: {kind.upper()}", AM.DOC_MODELS[kind].__name__, f"{kind}.json", False,
                                   "not recorded: the run saved no artifact-schema data for this document"))
            continue
        validation = _validate_sections(d, kind, rec["sections"], decs)
        _write_json(data, _stamp(rec, kind, validation))
        missing = [s for s in AM.SECTION_MODELS[kind] if s not in rec["sections"]]
        results.append(_result(f"document: {kind.upper()}", rec["model"], f"{kind}.json", rec["valid"],
                               ("sections not recorded: " + ", ".join(missing)) if missing else ""))
    return results


def build_design(d, decs):
    """design.json (Design/1, the style guide's data): validated, "model" and "valid" added; the style row reads it."""
    data = os.path.join(d, "design.json")
    if not os.path.isfile(os.path.join(d, "style.json")) and not os.path.isfile(data):
        return []
    rec = _read_json(data)
    if not isinstance(rec, dict) or not isinstance(rec.get("sections"), dict):
        return [_result("style guide", "Design", "design.json", False, "not recorded: the run saved no artifact-schema data for the style guide")]
    validation = _validate_sections(d, "design", rec["sections"], decs)
    _write_json(data, _stamp(rec, "design", validation))
    return [_result("style guide", "Design", "design.json", rec["valid"], "")]


def build_sections(d, decs):
    """site/sections/<id>.json for every website section in sections.json: the builder's own data when website.json
    kept it (J2 keeps the last reply), else the section as the page holds it, marked so; validated as a WebsiteSection."""
    secs = _read_json(os.path.join(d, "sections.json"), {}) or {}
    if not isinstance(secs, dict) or not os.path.isfile(os.path.join(d, "site", "index.html")):
        return []
    saved = {}
    for e in ((_read_json(os.path.join(d, "website.json"), {}) or {}).get("sections") or {}).values():
        if isinstance(e, dict) and e.get("id"):
            saved[str(e["id"])] = e
    results = []
    for sid, e in secs.items():
        if sid == "style" or not isinstance(e, dict):
            continue
        body, head = str(e.get("body") or ""), str(e.get("head") or "")
        if sid in saved:
            data = {k: v for k, v in saved[sid].items() if k in AM.WebsiteSection.model_fields}
            extra = {k: v for k, v in saved[sid].items() if k not in AM.WebsiteSection.model_fields}
            source = {"file": "website.json", "built_by": "j2_agent_views.py", "from": "the builder's reply", **({"also": extra} if extra else {})}
            note = ""
        else:
            ids = _ID_ATTR.findall(body)
            classes = sorted({c for m in _CLASS_ATTR.findall(body) for c in m.split()})
            data = {"id": sid, "anchor": ("#" + ids[0]) if ids else "", "implements": [], "html": body, "head": head,
                    "selectors_used": ["#" + i for i in ids] + ["." + c for c in classes]}
            source = {"file": "sections.json", "built_by": "j2_agent_views.py", "from": "the page (the builder's reply was not kept)",
                      "not_recorded": ["implements", "facts_used"]}
            note = "implements, facts_used not recorded (built from the page)"
        if sid in saved:
            t, where = _template_for(d, decs, "website", "Section", workflow=sid)
            if t is not None:
                got, errs = L.validate(t, data)
                env = {"schema": AM.SCHEMA, "model": L.class_name(t), "template": f"{t.name} v{t.version}", "valid": not errs, "errors": errs,
                       "source": {**source, "checked_against": where}, "data": got if got is not None else data}
            else:
                env = G.envelope(AM.WebsiteSection, AM.normalise(AM.WebsiteSection, data), {**source, "checked_against": where})
        else:
            env = G.envelope(AM.WebsiteSection, data, source)
        env["schema"] = AM.SCHEMA
        out = f"site/sections/{sid}.json"
        _write_json(os.path.join(d, out), env)
        results.append(_result(f"website section {sid}", env.get("model") or "WebsiteSection", out, env["valid"], note))
    return results


# ---------------------------------------------------------------------------------------------------- step 3: records and audits
def _agent(d, name, model, data, source, kind):
    env = G.envelope(model, data, source)
    out = f"agent/{name}.json"
    _write_json(os.path.join(d, out), env)
    return _result(kind, model.__name__, out, env["valid"], "" if env["valid"] else "; ".join(env["errors"][:2]))


def _s(x, default=G.NOT_RECORDED):
    return x if isinstance(x, str) and x.strip() else default


def build_records(d, goal, workflows):
    """agent/goal.json (Charter), agent/workflows.json (WorkflowPlan), agent/receipts.json (Receipts), agent/conditions.json
    (Conditions): the run's own records in the agent's shape, the originals untouched."""
    results = []
    if goal:
        data = {"statement": _s(goal.get("statement")), "site_name": goal.get("site_name") if isinstance(goal.get("site_name"), str) else None,
                "audience": _s(goal.get("audience")), "business_type": _s(goal.get("business_type")),
                **{k: [str(x) for x in goal.get(k) or []] for k in ("standards", "rules", "done_when", "core_items", "facts")},
                **{k: list(goal.get(k) or []) for k in ("to_be_confirmed", "dropped_from_brief", "visitor_needs")}}
        results.append(_agent(d, "goal", G.Charter, data, {"file": "goal.json", "built_by": "j2_agent_views.py"}, "charter"))
    if workflows:
        rows = []
        for w in workflows:
            if not isinstance(w, dict):
                continue
            rows.append({"id": str(w.get("id") or ""), "name": str(w.get("name") or ""), "purpose": str(w.get("purpose") or ""),
                         "covers": [x for x in (w.get("covers") or []) if isinstance(x, (int, str))],
                         "fixes": [x for x in (w.get("fixes") or []) if isinstance(x, (int, str))],
                         "outputs": [str(x) for x in (w.get("outputs") or [])], "section": w.get("section") if isinstance(w.get("section"), str) else None,
                         "cycle": w.get("cycle") if isinstance(w.get("cycle"), int) else None,
                         "cost": float(w["cost"]) if isinstance(w.get("cost"), (int, float)) else None,
                         "charged": w.get("charged") if isinstance(w.get("charged"), bool) else None,
                         "calls_used": w.get("calls_used") if isinstance(w.get("calls_used"), int) else None,
                         "retries_used": w.get("retries_used") if isinstance(w.get("retries_used"), int) else None,
                         "dependencies": [str(x) for x in (w.get("dependencies") or [])],
                         "completion_check": w.get("completion_check") if isinstance(w.get("completion_check"), str) else None,
                         "proposal_id": str(w["proposal_id"]) if w.get("proposal_id") is not None else None})
        results.append(_agent(d, "workflows", G.WorkflowPlan, {"workflows": rows}, {"file": "workflows.json", "built_by": "j2_agent_views.py"}, "workflow plan"))
    rp = os.path.join(d, "receipts.jsonl")
    if os.path.isfile(rp):
        items = []
        with open(rp, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(r, dict):
                    continue
                items.append({"atom": _s(r.get("atom")), "check": _s(r.get("check") or r.get("kind")), "attempt": r.get("attempt") if isinstance(r.get("attempt"), int) else None,
                              "passed": r.get("pass") if isinstance(r.get("pass"), bool) else None, "met": r.get("met") if isinstance(r.get("met"), bool) else None,
                              "by": r.get("by") if isinstance(r.get("by"), str) else None, "kind": r.get("kind") if isinstance(r.get("kind"), str) else None,
                              "evidence": str(r.get("evidence") or ""), "expect": r.get("expect", r.get("expected")), "actual": r.get("actual"),
                              "of": r.get("of") if isinstance(r.get("of"), str) else None, "target": r.get("target"), "t": r.get("t") if isinstance(r.get("t"), str) else None})
        results.append(_agent(d, "receipts", G.Receipts, {"items": items}, {"file": "receipts.jsonl", "built_by": "j2_agent_views.py"}, "check results"))
    cond = _read_json(os.path.join(d, "conditions.json"))
    if isinstance(cond, list):
        items = [{"id": str(c.get("id") or ""), "text": str(c.get("text") or ""), "check": c.get("check") if isinstance(c.get("check"), str) else None,
                  "met": bool(c.get("met")), "evidence": str(c.get("evidence") or "")} for c in cond if isinstance(c, dict)]
        results.append(_agent(d, "conditions", G.Conditions, {"items": items}, {"file": "conditions.json", "built_by": "j2_agent_views.py"}, "necessary conditions"))
    return results


def _finding(r):
    return {"id": r.get("id") if isinstance(r.get("id"), str) else None, "item": r.get("item") if isinstance(r.get("item"), (int, str)) else None,
            "criterion": _s(r.get("criterion")), "verdict": _s(r.get("verdict")), "note": str(r.get("note") or ""),
            "severity": _s(r.get("severity")), "confidence": r.get("confidence") if isinstance(r.get("confidence"), (str, int, float)) and not isinstance(r.get("confidence"), bool) else None,
            "passed": bool(r.get("pass")), "evidence": str(r.get("evidence") or r.get("note") or "")}


def build_audits(d, goal):
    """agent/audits/A-1.json, A-2.json, ...: every audit (audits.json, re-checks left out) as a workflow of its own, with the
    goal (the done-when items it judged), the method (what the record shows it used) and the evidence, and every finding."""
    audits = [a for a in (_read_json(os.path.join(d, "audits.json"), []) or []) if isinstance(a, dict) and a.get("kind") != "recheck"]
    done_when = [str(x) for x in (goal or {}).get("done_when") or []]
    results = []
    for i, a in enumerate(audits, 1):
        findings = [_finding(r) for r in (a.get("results") or []) if isinstance(r, dict)]
        rubric = [_finding(r) for r in (a.get("rubric") or []) if isinstance(r, dict)]
        extra = [_finding(r) for r in (a.get("extra_issues") or []) if isinstance(r, dict)]
        mech = a.get("mechanical") if isinstance(a.get("mechanical"), dict) else {}
        conds = [{"id": str(c.get("id") or ""), "text": str(c.get("text") or ""), "check": c.get("check") if isinstance(c.get("check"), str) else None,
                  "met": bool(c.get("met")), "evidence": str(c.get("evidence") or "")} for c in (a.get("conditions") or []) if isinstance(c, dict)]
        lld = a.get("lld") if isinstance(a.get("lld"), dict) else {}
        judged = [f["criterion"] for f in findings if f["criterion"] in done_when] or [f["criterion"] for f in findings]
        goal_s = ("Check the done-when items: " + "; ".join(judged)) if judged else G.NOT_RECORDED
        used = [k for k, on in (("the rubric", bool(rubric)), ("mechanical page checks", bool(mech.get("available"))),
                                ("the necessary conditions", bool(conds)), ("the LLD match", bool(lld)), ("a screenshot", bool(a.get("screenshot")))) if on]
        method = ("Judged each item against the page, using " + ", ".join(used)) if used else G.NOT_RECORDED
        evidence = ([{"kind": "screenshot", "ref": str(a["screenshot"])}] if a.get("screenshot") else []) \
            + ([{"kind": "mechanical", "ref": "audits.json#mechanical", "note": f"{mech.get('bytes', '?')} bytes, {mech.get('forms', '?')} forms"}] if mech.get("available") else []) \
            + ([{"kind": "conditions", "ref": "conditions.json", "note": f"{sum(1 for c in conds if c['met'])} of {len(conds)} met"}] if conds else []) \
            + ([{"kind": "lld", "ref": "lld.md", "note": f"{len(lld.get('matches') or [])} matches, {len(lld.get('mismatches') or [])} mismatches"}] if lld else [])
        data = {"id": f"A-{i}", "cycle": a.get("cycle") if isinstance(a.get("cycle"), int) else 0, "version": a.get("version") if isinstance(a.get("version"), int) else 0,
                "goal": goal_s, "method": method, "findings": findings, "rubric": rubric, "extra_issues": extra,
                "all_pass": a.get("all_pass") if isinstance(a.get("all_pass"), bool) else None, "screenshot": a.get("screenshot") if isinstance(a.get("screenshot"), str) else None,
                "mechanical": mech, "conditions": conds, "lld": lld, "evidence": evidence}
        results.append(_agent(d, f"audits/A-{i}", G.AuditResult, data, {"file": "audits.json", "index": i - 1, "built_by": "j2_agent_views.py"}, f"audit A-{i}"))
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
    decs = _decisions(d)
    results += build_documents(d, decs)
    results += build_design(d, decs)
    results += build_sections(d, decs)
    results += build_records(d, goal, workflows)
    results += build_audits(d, goal)
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
