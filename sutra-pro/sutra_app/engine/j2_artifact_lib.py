"""The content door (J2_ARTIFACT_LIBRARY=1): before a document section's builder runs, the section the source run of
this run's run template wrote for the same template workflow is located and, when its inputs match, served instead
of a model call. Pure logic: nothing here imports j2 or writes a run folder.

The source of a section is the run named by the run template (made_from_run), the workflow named by its row
(made_from) and that run's <kind>.json, templates.json, stage-<kind>.json, summary.json and receipts.jsonl. Nothing
is stored twice: runs travel on Git (founder, 13 Nov).

Doors: reuse (serve the data, 0 model calls, refund), adapt (the builder starts from the data as a draft), build (as
today), unknown (the source run cannot be read: never taken as "there is nothing").
"""
import json
import os
import re

from . import j2_template_lib as L

SCHEMA = "artifact-reuse/1"
DOORS = ("reuse", "adapt", "build", "unknown")


def enabled():
    """J2_ARTIFACT_LIBRARY=1 (default off): the content door. It implies J2_AUTO_REUSE=1 (j2_template_lib.auto_reuse),
    which implies the template library and the run templates, and the template library implies the artifact schema.
    Read per call so tests can switch it."""
    return os.environ.get("J2_ARTIFACT_LIBRARY") == "1"


class SourceUnreadable(Exception):
    """The source run exists in the template's record but cannot be read here (not pulled, a file missing or
    broken). The door is "unknown", never "build because there is nothing"."""


def _fail(what):
    raise SourceUnreadable(what)


def _json(path, what):
    """A JSON file of the source run, or SourceUnreadable naming it."""
    if not os.path.isfile(path):
        _fail(f"{what} is missing ({os.path.basename(path)})")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        _fail(f"{what} cannot be read ({type(e).__name__})")


def stage_audit(run_dir, kind):
    """"pass", "fail" or "not recorded" for one stage of a saved run: its archived audit (stage-<kind>.json, every
    done-when verdict passed), else the run's summary when that stage was its last (status done, every done-when
    item passed)."""
    st = L._read(os.path.join(run_dir, f"stage-{kind}.json"))
    audits = (st or {}).get("audits") or []
    if audits:
        last = audits[-1] or {}
        results = last.get("results") or []
        if last.get("all_pass") is True or (results and all(r.get("pass") for r in results)):
            return "pass"
        return "fail"
    s = L._read(os.path.join(run_dir, "summary.json")) or {}
    if s.get("output_type") == kind and s.get("status") in ("done", "done_with_open_items"):
        dw = s.get("done_when") or []
        if dw and all(x.get("pass") is True for x in dw if isinstance(x, dict)):
            return "pass"
        return "fail" if dw else "not recorded"
    return "not recorded"


def receipts_passed(run_dir, workflow):
    """The texts of the checks that passed on the last attempt of the workflow's atoms, from receipts.jsonl."""
    path = os.path.join(run_dir, "receipts.jsonl")
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if "check" in r and str(r.get("atom") or "").startswith(workflow + "."):
                rows.append(r)
    if not rows:
        return []
    last = max(int(r.get("attempt") or 0) for r in rows)
    return [str(r.get("check") or r.get("type")) for r in rows if int(r.get("attempt") or 0) == last and r.get("pass")]


def source_section(run_tpl_id, key, kind, section, root=None):
    """The section the source run wrote for template workflow `key`: {run, dir, workflow, data, sha, template,
    fingerprint, facts, audit, receipts_passed}. None when the template has no such workflow, the row records no
    source workflow, or the source wrote no such section. SourceUnreadable when the run folder or a file it needs
    cannot be read."""
    rt = L.get_run_template(run_tpl_id)
    if rt is None:
        _fail(f"run template {run_tpl_id!r} cannot be read")
    row = next((w for w in rt.workflows if w.key == key), None)
    if row is None or not row.made_from or not rt.made_from_run:
        return None
    run_dir = os.path.join(L.runs_root(root), rt.made_from_run)
    if not os.path.isdir(run_dir):
        _fail(f"source run {rt.made_from_run} is not in the runs folder")
    decs = (_json(os.path.join(run_dir, "templates.json"), "the source run's routing record") or {}).get("decisions") or []
    mine = [d for d in decs if d.get("workflow") == row.made_from and d.get("artifact") == kind]
    if not mine:
        return None
    d = mine[-1]      # a revision's decision is the one that held
    data = ((_json(os.path.join(run_dir, f"{kind}.json"), "the source run's section data") or {}).get("sections") or {}).get(section)
    if data is None:
        return None
    return {"run": rt.made_from_run, "dir": run_dir, "workflow": row.made_from, "key": key, "data": data,
            "sha": L.sha_of(data), "template": f"{d.get('template')}@{d.get('version')}",
            "fingerprint": d.get("fingerprint"), "facts": d.get("facts"), "action": d.get("action"),
            "audit": stage_audit(run_dir, kind), "receipts_passed": receipts_passed(run_dir, row.made_from)}


def door(need, rec, source, error=None, has_key=True, goal=None):
    """The content decision for one workflow, from the router's decision rec (its action, template@version and the
    need's fingerprint) and the source section. {door, rule, reason, source: {...}|None}. goal: this run's charter;
    a cross-client section that holds the source business's values is not served as it is (adapt, rule
    cross-facts), so no fact of another client enters this document unchecked."""
    src = None if source is None else {k: source[k] for k in ("run", "workflow", "key", "sha", "template", "fingerprint",
                                                               "audit", "receipts_passed")}
    if error:
        return {"door": "unknown", "rule": "0", "reason": f"the source run cannot be read: {error}; built as today", "source": None}
    if not has_key:
        return {"door": "build", "rule": "none", "reason": "no run template names a source for this workflow", "source": None}
    if source is None:
        return {"door": "build", "rule": "none", "reason": "no source section: the source run wrote none for this workflow", "source": None}
    action = str((rec or {}).get("action") or "")
    routed = f"{(rec or {}).get('template')}@{(rec or {}).get('version')}"
    if source["audit"] != "pass":
        return {"door": "build", "rule": "audit", "reason": f"the source stage's audit is {source['audit']}, so its section is not served", "source": src}
    if source["fingerprint"] and source["fingerprint"] == (need or {}).get("fingerprint") and source["template"] == routed:
        return {"door": "reuse", "rule": "same", "reason": f"the same inputs and the same template as run {source['run']} {source['workflow']}: served, then checked", "source": src}
    if action == "reused":
        foreign = foreign_values(source, goal) if goal is not None else []
        if foreign:
            return {"door": "adapt", "rule": "cross-facts", "source": src,
                    "reason": f"the template fits as it is, but the section of run {source['run']} {source['workflow']} holds "
                              f"{len(foreign)} value(s) of its own business that this charter does not; the builder starts from it as a draft, slotted"}
        return {"door": "reuse", "rule": "cross", "reason": f"the template fits as it is; the section of run {source['run']} {source['workflow']} holds no value of its own business, so it is served for this business and checked (cross-client reuse, 13 Nov)", "source": src}
    if action == "extended":
        return {"door": "adapt", "rule": "near", "reason": f"the template was adapted for these facts; the builder starts from the section of run {source['run']} {source['workflow']} as a draft", "source": src}
    return {"door": "build", "rule": "new", "reason": f"the router {action or 'created'} the template, so nothing is served", "source": src}


MIN_FRAGMENT = 8      # a part of a charter value (split at commas, newlines and " and ") this long counts as the value too


def source_slots(source):
    """[(value, slot)] of the source run's charter, plus the parts of every multi-part value (an address's street,
    a class line's name), so that a fragment of a fact is slotted or caught like the whole fact."""
    slots = list(L.charter_slots(source["dir"]))
    extra = []
    for value, slot in slots:
        for part in re.split(r",|\n|;| and ", value):
            part = part.strip()
            if len(part) >= MIN_FRAGMENT and part.lower() != value.lower():
                extra.append((part, slot))
    return slots + extra


def foreign_values(source, goal):
    """The source business's charter values (and their parts) found in the source section's data that this run's
    charter does not hold: served as they are, they would put another client's facts into this document."""
    mine = json.dumps(goal or {}, ensure_ascii=False).lower()
    text = json.dumps(source["data"], ensure_ascii=False).lower()
    out = []
    for value, _ in source_slots(source):
        v = value.lower()
        if v in text and v not in mine and value not in out:
            out.append(value)
    return out


def draft_text(source):
    """The source section as a draft for a builder's prompt, with every charter value of the source run, and every
    part of one, replaced by a slot (no name or fact of the earlier business reaches a prompt)."""
    return L.with_slots(json.dumps(source["data"], ensure_ascii=False, indent=1), source_slots(source))


def chat_line(d):
    """One system line for the chat."""
    s = d.get("source") or {}
    where = f"run {s.get('run')} {s.get('workflow')}" if s else "the library"
    if d["door"] == "reuse":
        return f"{d['workflow']}: served {d.get('section')} from {where} ({d['rule']} inputs); code runs its checks before it counts."
    if d["door"] == "adapt":
        return f"{d['workflow']}: drafting {d.get('section')} from {where}; the builder starts from it."
    if d["door"] == "unknown":
        return f"{d['workflow']}: {d['reason']}."
    return f"{d['workflow']}: built ({d['reason']})."


def record(decisions, library=None):
    """reuse.json for a run."""
    return {"schema": SCHEMA, "library": library or L.lib_dir(), "runs": L.runs_root(), "decisions": decisions}


def reused_from(run_dir):
    """{workflow id: {run, workflow, key, section}} of the sections a run served (door reuse that held), from its
    reuse.json, for the Artifacts tab."""
    rec = L._read(os.path.join(run_dir, "reuse.json")) or {}
    out = {}
    for d in rec.get("decisions") or []:
        if d.get("door") == "reuse" and d.get("held") and d.get("source"):
            out[d["workflow"]] = {"run": d["source"].get("run"), "workflow": d["source"].get("workflow"),
                                  "key": d.get("key"), "section": d.get("section")}
    return out


def counts(decisions):
    """{door: n} over a run's content decisions, the four doors always present."""
    out = {k: 0 for k in DOORS}
    for d in decisions or []:
        if d.get("door") in out:
            out[d["door"]] += 1
    return out


WORD = re.compile(r"[A-Za-z0-9]+")
