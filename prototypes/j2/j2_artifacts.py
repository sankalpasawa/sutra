"""Artifacts of a run, listed from artifacts/types.json (read-only; j2.py's flow does not read the list).

rows(run_dir) scans a run folder against the list: one row per deliverable the run built and per record file it kept.
write(run_dir) saves those rows as artifacts.json at the end of a run; listing(run_dir) reads that file, or scans an older
run that has none. Code only, no model call.
"""
import glob
import hashlib
import json
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TYPES_PATH = os.path.join(HERE, "artifacts", "types.json")
OPEN = {"document": "text", "doc": "text",      # "doc": the form name saved runs recorded before Phase C
         "data": "text", "page": "preview", "image": "image"}      # how the Artifacts tab shows a form
TEXT = {".md": "text/markdown", ".json": "application/json", ".jsonl": "text/plain", ".txt": "text/plain",
        ".html": "text/html", ".png": "image/png"}
MAX_BYTES = 2_000_000


def load_types():
    import j2_types      # its TYPES_PATH: a test may point it at a copy
    with open(j2_types.TYPES_PATH, encoding="utf-8") as f:
        d = json.load(f)
    forms = d.get("forms") or {}
    for t in d["types"]:      # a type made from its form (a new document type) takes the form's workflow
        f = (forms.get(t.get("form")) or {}).get("workflow")
        if t.get("kind") == "type" and f and "workflow" not in t:
            t["workflow"] = {k: v.replace("{name}", t["name"]) for k, v in f.items()}
    return d


def page_types(types=None):
    """The names of the types of the page form (types.json): what the Map and the groups call the site."""
    return {t["name"] for t in (types or load_types())["types"] if t.get("kind") == "type" and t.get("form") == "page"}


def is_page_node(node_id, types=None):
    """A Map work node of a page type ("work:website")."""
    return str(node_id).startswith("work:") and str(node_id)[5:] in page_types(types)


def chosen(d):
    """The types a run chose: its planner's (deliverables.json), its stages (stage-*.json), and the type its records
    name (summary.json output_type, chat.jsonl's first line)."""
    head = {}
    try:
        with open(os.path.join(d, "chat.jsonl"), encoding="utf-8") as f:
            head = json.loads(f.readline() or "{}")
    except (OSError, ValueError):
        pass
    stages = [m.group(1) for f in os.listdir(d) for m in [re.fullmatch(r"stage-(\w+)\.json", f)] if m]
    return {str(x) for x in [*((_read(d, "deliverables.json", {}) or {}).get("deliverables") or []), *stages,
                             (_read(d, "summary.json", {}) or {}).get("output_type"), head.get("output")] if x}


def _read(d, name, default=None):
    try:
        with open(os.path.join(d, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _num(path):
    m = re.search(r"(\d+)", os.path.basename(path))
    return int(m.group(1)) if m else 0


def _stat(d, rel):
    p = os.path.join(d, rel)
    with open(p, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    return sha, time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(p)))


def _version(d, t, single):
    """The latest build of a deliverable, from the version files in site/: hld-v3.md, v3.html (a one-document run keeps
    plain names: v3.md)."""
    site = os.path.join(d, "site")
    if not os.path.isdir(site):
        return None
    if t["form"] == "page":
        pat = r"v(\d+)\.html"
    else:
        pat = rf"{t['name']}-v(\d+)\.md" + (r"|v(\d+)\.md" if single else "")
    n = [int(next(g for g in m.groups() if g)) for f in os.listdir(site) for m in [re.fullmatch(pat, f)] if m]
    return max(n) if n else None


def _atoms(d):
    """The atom/1 views of a run: atoms.json, else built from the stored workflows (older runs)."""
    rows = (_read(d, "atoms.json", {}) or {}).get("atoms")
    if rows is None:
        import j2_schema
        rows = j2_schema.run_views(_read(d, "workflows.json", []) or [], ended=True)[0]
    return rows


def _board(d, atoms):
    """What the message board (board/1) changed and re-checked, per deliverable type: {type: {"changed_by": [Q-n],
    "rechecked_after": [Q-n]}}, from board.json only. Empty when the run has no board."""
    entries = (_read(d, "board.json", {}) or {}).get("entries") or []
    wf_of = {v["id"]: v.get("workflow") for v in atoms}
    out = {}
    for e in entries:
        up = e.get("artifact_update") or {}
        if up.get("doc"):
            out.setdefault(up["doc"], {}).setdefault("changed_by", []).append(e["id"])
            # the changed document itself: its own conditions and the owner's checks were re-run
            out[up["doc"]].setdefault("rechecked_after", []).append(e["id"])
        for x in e.get("impact") or []:
            wid = wf_of.get(x.get("atom"))
            if wid:
                out.setdefault(("_wf", wid), {}).setdefault("rechecked_after", []).append(e["id"])
    return out


def rows(d, types=None):
    """[{name, type, kind, form, file, deliverable, workflows, depends_on, version, sha256, time}] for a run folder,
    plus changed_by and rechecked_after when the message board changed or re-checked it."""
    types = types or load_types()
    if not d or not os.path.isdir(d):
        return []
    atoms, docs, out = _atoms(d), _read(d, "documents.json", {}) or {}, []
    board = _board(d, atoms)
    # page types share the page file: a run that chose one shows that one only
    pages, mine = page_types(types), chosen(d)
    for t in types["types"]:
        if t["name"] in pages and t["name"] not in mine and pages & mine:
            continue
        files = [os.path.relpath(p, d) for p in sorted(glob.glob(os.path.join(d, t["file"])), key=_num)] \
            if "*" in t["file"] else [t["file"]] if os.path.isfile(os.path.join(d, t["file"])) else []
        wf = []
        if t["kind"] == "type":
            rx = re.compile(t["workflow"]["refs"])
            wf = sorted({v["workflow"] for v in atoms for o in v.get("output") or []
                         if o.get("verb") == "make" and rx.search(str(o.get("ref") or ""))}, key=_num)
        changed = sorted(set((board.get(t["name"]) or {}).get("changed_by") or []), key=_num)
        rechecked = sorted({q for w in wf for q in (board.get(("_wf", w)) or {}).get("rechecked_after") or []}
                           | set((board.get(t["name"]) or {}).get("rechecked_after") or []), key=_num)
        for rel in files:
            sha, when = _stat(d, rel)
            out.append({"name": t["label"] if len(files) == 1 or t["kind"] == "type" else
                        f"{t['label']} {os.path.splitext(os.path.basename(rel))[0]}",
                        "type": t["name"], "kind": t["kind"], "form": t["form"], "file": rel, "deliverable": t["deliverable"],
                        "workflows": wf, "depends_on": list(t["depends_on"]) if "depends_on" in t else [],
                        "version": _version(d, t, len(docs) <= 1) if t["kind"] == "type" else None,
                        **({"changed_by": changed} if changed else {}),
                        **({"rechecked_after": rechecked} if rechecked else {}),
                        "sha256": sha, "time": when})
    built = {r["type"] for r in out}
    for r in out:      # what it depends on in this run: only the types that were built
        r["depends_on"] = [x for x in r["depends_on"] if x in built]
    return out


def write(d):
    """artifacts.json in the run folder (additive: nothing else is touched)."""
    r = {"schema": "artifacts/1", "rows": rows(d)}
    with open(os.path.join(d, "artifacts.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    return r


def listing(d):
    """What the Artifacts tab shows: the saved artifacts.json when the run has one, else the same rows built by
    scanning the folder. Each row gets its type's label, tag, colour and how to open it."""
    types = load_types()
    by = {t["name"]: t for t in types["types"]}
    saved = _read(d, "artifacts.json") if d else None
    base = saved["rows"] if saved else rows(d, types)
    full = [{**r, "label": by[r["type"]]["label"], "tag": by[r["type"]]["tag"], "color": by[r["type"]]["color"],
             "open": OPEN[r["form"]], "depends_on_labels": [by[x]["label"] for x in r["depends_on"] if x in by],
             "saved": bool(saved)} for r in base if r["type"] in by]
    return {"deliverables": [r for r in full if r["deliverable"]], "records": [r for r in full if not r["deliverable"]]}


def served(d, name):
    """The path of a file named in the run's artifact rows (saved, or found now by the types list), else None. Nothing
    else is ever served."""
    name = str(name or "")
    if not d or ".." in name.split("/") or os.path.isabs(name):
        return None
    ok = {r["file"] for r in (listing(d)["deliverables"] + listing(d)["records"])} | {r["file"].replace(os.sep, "/")
                                                                                     for r in rows(d)}
    if name not in ok:
        ok |= set(tree_files(tree(d)))      # the tree's files: versions, the style guide, exports and the run's other records
    p = os.path.join(d, name)
    return p if name in ok and os.path.isfile(p) and os.path.getsize(p) <= MAX_BYTES else None


# ---------------------------------------------------------------------------------------------------------------- the tree
# The Artifacts tab as a tree (artifacts-tree/1): Plan, Specs (the style guide with them), Deliverable, Proof (the screenshots as
# Verification proof, then the check records, then the run's other files as Run records). Makers, readers and statuses come
# from j2_map.build, the same data the Map draws, so the two always agree; the files come from listing() and the run folder, each
# exactly once. Nothing names a run, a workflow or a stage: only file kinds (types.json) and the map's own fields.
TREE_STATUS = {"filed": "filed", "done_unchecked": "checks did not pass", "fault": "failed", "left_open": "open", "running": "open",
               "waiting": "open", "waiting_on_you": "open", "not_made": "not made", "idle": "filed"}
RECORD_MAKER = {"goal.json": "Client Lead (Identity)", "realization.json": "Adaptation (scored by the confidence judge)",
                "deliverables.json": "Adaptation (scored by the confidence judge)", "audits.json": "Quality Reviewer (Audit)", "receipts.jsonl": "Checker (automatic)",
                "chat.jsonl": "every function (the chat)", "calls.jsonl": "every function (AI calls)"}      # who writes each kind of record
PROOF = ("receipts.jsonl", "audits.json", "conditions.json")
RECORD_NAME = {"calls.jsonl": "AI calls", "outputs.jsonl": "Workflow outputs", "map.json": "Map data", "artifacts.json": "Artifact list",
               "report.json": "Run report (data)", "sections.json": "Sections", "documents.json": "Documents record"}      # files types.json does not list


def _lines(d, f):
    try:
        with open(os.path.join(d, f), encoding="utf-8") as fh:
            return sum(1 for x in fh if x.strip())
    except OSError:
        return 0


def sections_of(d, decks):
    """{deck id: (record file, {section id: entry})}: a document's sections from its stage-<doc>.json, the one box still in work
    from sections.json (as j2_map places them)."""
    out, current = {}, []
    for n in decks:
        k = n["id"].split(":", 1)[1]
        rec = _read(d, f"stage-{k}.json")
        if isinstance(rec, dict) and isinstance(rec.get("sections"), dict):
            out[n["id"]] = (f"stage-{k}.json", rec["sections"])
        else:
            current.append(n)
    cur = _read(d, "sections.json")
    if len(current) == 1 and isinstance(cur, dict) and cur:
        out[current[0]["id"]] = ("sections.json", cur)
    return out


def _code_summary(text, page):
    """What a section holds, in plain words: lines of HTML, CSS rules and lines of JS (a page), else lines of text."""
    text = str(text or "")
    if not page:
        n = sum(1 for x in text.splitlines() if x.strip())
        return f"{n} line{'s' if n != 1 else ''} of text"
    css = " ".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.S | re.I))
    js = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", text, re.S | re.I))
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
    k = lambda n, w: f"{n} {w}{'s' if n != 1 else ''}"
    return ", ".join([k(sum(1 for x in html.splitlines() if x.strip()), "line") + " of HTML", k(css.count("{"), "CSS rule"),
                      k(sum(1 for x in js.splitlines() if x.strip()), "line") + " of JS"])


def code_text(d, deck, section=None):
    """The text a Code or Sections row opens: the full page (site/index.html) or one section's code or text; None if unknown."""
    import j2_map
    if not d or not os.path.isdir(d):
        return None
    if section is None:
        p = os.path.join(d, "site", "index.html")
        return open(p, encoding="utf-8").read() if is_page_node(deck) and os.path.isfile(p) else None
    m = j2_map.build(d)
    src = sections_of(d, [n for n in m["nodes"] if n["id"] == deck]).get(deck)
    e = (src[1] if src else {}).get(section)
    return None if not isinstance(e, dict) else (e.get("head") or "") + (e.get("body") or "")


def _template_data(d, name):
    """{"template", "file"} when a run saved the data an artifact was rendered from (J2_ARTIFACT_SCHEMA=1:
    <kind>.json beside the document), else None. Read only; nothing is guessed."""
    f = f"{name}.json"
    rec = _read(d, f, None)
    if not isinstance(rec, dict) or rec.get("schema") != "artifact-schema/1":
        return None
    return {"template": rec.get("template") or "not recorded", "file": f, "version": rec.get("version")}


def tree(d, m=None):
    import j2_map
    if not d or not os.path.isdir(d):
        return {"schema": "artifacts-tree/1", "groups": []}
    m = m or j2_map.build(d)
    lst, types = listing(d), {t["file"]: t for t in load_types()["types"] if "*" not in t["file"]}
    rowsby = {r["file"]: r for r in lst["deliverables"] + lst["records"]}
    by = {n["id"]: n for n in m["nodes"]}
    made_step = {e["to"]: by[e["from"]] for e in m["edges"] if e["kind"] == "step" and by.get(e["from"], {}).get("kind") == "engine"}
    # who reads what, for the tree's Makers and Readers: the map draws a read from the artifact to the team (the step) that read it,
    # and the team to what it made, so an artifact's reader is the artifact its team made
    made_by_team = {e["from"]: e["to"] for e in m["edges"] if e["kind"] == "step" and by.get(e["from"], {}).get("kind") == "engine"}
    reads = [{**e, "to": made_by_team[e["to"]]} for e in m["edges"] if e["kind"] in ("step", "handoff") and e["from"] != "work:charter"
             and by.get(e["from"], {}).get("kind") == "work" and e["to"] in made_by_team]
    used = set()

    def size(f):
        return os.path.getsize(os.path.join(d, f)) if f and os.path.isfile(os.path.join(d, f)) else None

    def opener(f):
        r = rowsby.get(f)
        if r:
            return r["open"]
        ext = os.path.splitext(f or "")[1]
        return "image" if ext == ".png" else "preview" if ext == ".html" else "text"

    def item(name, f=None, made=None, status="filed", **kw):
        if f and (f in used or not os.path.isfile(os.path.join(d, f))):
            f = None      # each file once; a send has no file of its own (its receipt is under Proof)
        if f:
            used.add(f)
        return {"name": name, "file": f, "made_by": made, "status": status, "size": size(f), "open": opener(f) if f else None, **kw}

    def maker(n):
        st = made_step.get(n["id"])
        return {"persona": st["persona"], "workflows": list(n.get("workflows") or [])} if st else None

    def readers(nid):
        return sorted({w for e in reads if e["from"] == nid for w in e.get("readers") or []}, key=lambda w: int(re.sub(r"\D", "", w) or 0))

    def status(n):
        return n.get("send") or TREE_STATUS.get(n.get("status"), n.get("status") or "filed") if n.get("tag") == "Send" else TREE_STATUS.get(n.get("status"), "filed")

    # 1 Plan
    plan = []
    if "work:charter" in by or os.path.isfile(os.path.join(d, "goal.json")):
        wrote = any(e["kind"] == "speaks_to" and e["to"] == "work:charter" and e["from"] == "fn:identity" for e in m["edges"])
        plan.append(item("Charter", "goal.json", {"function": RECORD_MAKER["goal.json"]} if wrote else None))
    rz = _read(d, "realization.json")
    if rz is not None:
        st = rz.get("stages") or {}
        zone = (((rz.get("plan") or {}).get("certainty_assessment")) or {}).get("zone")
        note = [f"zone {zone}" if zone else "", f"{len(st)} stages: {', '.join(st)}" if st else "",
                f"plan confidence {rz['plan_confidence']}" if rz.get("plan_confidence") is not None else ""]
        kids = [item("Realization plan (text)", "realization.md", {"function": "code"})] if os.path.isfile(os.path.join(d, "realization.md")) else []
        plan.append(item("Realization plan", "realization.json", {"function": RECORD_MAKER["realization.json"]}, note=" · ".join(x for x in note if x), children=kids))
    dv = _read(d, "deliverables.json")
    if isinstance(dv, dict):
        plan.append(item("Deliverables", "deliverables.json", {"function": RECORD_MAKER["deliverables.json"]},
                         note=", ".join(x["type"] for x in deliverable_items(dv))))
    wfs = _read(d, "workflows.json", []) or []
    if os.path.isfile(os.path.join(d, "workflows.json")):
        plan.append(item("Workflows", "workflows.json", {"function": "Validator (code)"}, note=f"{len(wfs)} workflows"))
    # 2 Specs: every decide workflow's file, with its maker and how many workflows read it
    specs = [item(n["label"], n.get("file"), maker(n), status(n), output=n.get("output") if n.get("output") != n["label"] else None, read_by=len(readers(n["id"])), node=n["id"])
             for n in m["nodes"] if n["kind"] == "work" and n.get("tag") == "Spec"]
    specs += [item(n["label"], n.get("file"), maker(n), status(n), node=n["id"], read_by=len(readers(n["id"])))      # the style guide is a guide too
              for n in m["nodes"] if n.get("tag") == "Style"]
    specs += [item(r["name"], f, None, note="no workflow recorded as its maker") for f, r in rowsby.items()
              if r["type"].startswith("workflow_files") and f not in used]
    # 3 Deliverable: each delivered output, with its sections, its versions and exports, and the sends that report it
    deck = [n for n in m["nodes"] if n["kind"] == "work" and n["id"] != "work:charter" and n.get("tag") not in ("Spec", "Style", "Send")]
    sends = [n for n in m["nodes"] if n.get("tag") == "Send"]
    placed_send = set()
    out = []
    secs = sections_of(d, deck)
    wf_name = {w["id"]: w.get("name") or w["id"] for w in wfs if isinstance(w, dict) and w.get("id")}
    persona_of = {}
    for n_ in m["nodes"]:
        if n_["kind"] == "engine":
            for w in n_.get("workflows") or []:
                persona_of.setdefault(w, n_.get("persona"))
    for n in deck:
        kids = []
        t0 = next((x for x in load_types()["types"] if x["kind"] == "type" and f"work:{x['name']}" == n["id"]), None)
        page = bool(t0 and t0["form"] == "page")
        rows_ = []
        for sid, e in (secs.get(n["id"], (None, {}))[1] or {}).items():
            if not isinstance(e, dict):
                continue
            owner = e.get("owner") or sid
            made = sid if sid in wf_name else owner      # the workflow that created it (the section is named by it), else its owner
            text = (e.get("head") or "") + (e.get("body") or "")
            rows_.append({"name": wf_name.get(made) if sid in wf_name else (e.get("workflow") or sid), "file": None, "status": "filed", "size": len(text.encode("utf-8")),
                          "made_by": {"persona": persona_of.get(made), "workflows": [made]}, "open": "code" if page else "codetext",
                          "code": {"deck": n["id"], "section": sid}, "section": sid,
                          **({"rewritten": {"by": owner, "name": wf_name.get(owner, owner)}} if owner != made else {}),
                          "note": _code_summary(text, page)})
        if page and os.path.isfile(os.path.join(d, "site", "index.html")):
            full = {"name": "Full page source", "file": None, "status": "filed", "size": os.path.getsize(os.path.join(d, "site", "index.html")),
                    "made_by": None, "open": "code", "code": {"deck": n["id"]}, "note": "site/index.html, read-only"}
            kids.append(full)
        if rows_:
            kids.append({"name": "Sections", "count": len(rows_), "collapsed": True, "children": rows_})
        t = next((x for x in load_types()["types"] if x["kind"] == "type" and f"work:{x['name']}" == n["id"]), None)
        site = os.path.join(d, "site")
        if t and os.path.isdir(site):
            pat = r"v(\d+)\.html" if t["form"] == "page" else rf"(?:{re.escape(t['name'])}-)?v(\d+)\.md"
            vs = sorted(((int(mm.group(1)), f"site/{f}") for f in os.listdir(site) for mm in [re.fullmatch(pat, f)] if mm))
            if t["form"] != "page" and any(re.fullmatch(rf"{re.escape(t['name'])}-v\d+\.md", f) for f in os.listdir(site)):
                vs = [(k, f) for k, f in vs if os.path.basename(f).startswith(t["name"] + "-")]      # several documents: only this one's
            if vs:
                kids.append({"name": "Versions", "count": len(vs), "collapsed": True,
                             "children": [item(f"v{k}", f, None, "filed") for k, f in vs]})
            base = os.path.splitext(n.get("file") or "")[0]
            for f in sorted(os.listdir(d)):
                if base and f.startswith(os.path.basename(base) + ".") and f != os.path.basename(n.get("file") or "") and f.endswith(".docx"):
                    kids.append(item("Word file", f, {"function": "code (export)"}))
        data = _template_data(d, t["name"])
        if data:
            kids.append(item(f"Template data ({data['template']})", data["file"], {"function": "code (the data the "
                                                                                   "builders sent)"},
                             note=f"rendered from {data['template']}"))
        for s_ in sends:
            if any(e["from"] == n["id"] and e["to"] == s_["id"] for e in reads):
                placed_send.add(s_["id"])
                kids.append(item(s_["label"], None, maker(s_), status(s_), node=s_["id"], note="receipt in Check results"))
        out.append(item(n["label"], n.get("file"), maker(n), status(n), version=n.get("version"), node=n["id"],
                        workflows=len(n.get("workflows") or []), children=kids))
    out += [item(s_["label"], None, maker(s_), status(s_), node=s_["id"], note="receipt in Check results") for s_ in sends if s_["id"] not in placed_send]
    # 4 Proof: the screenshots Audit took while checking (Verification proof), the check records, and every other file the run kept (Run records)
    proof = []
    shots = sorted((f for f, r in rowsby.items() if r["type"] == "screenshots" and f not in used), key=_num)
    if shots:
        proof.append({"name": "Verification proof", "count": len(shots), "collapsed": False, "shots": True,
                      "children": [item(r_["name"], f) for f in shots for r_ in [rowsby[f]]]})
    for f in PROOF:
        if os.path.isfile(os.path.join(d, f)):
            j = _read(d, f)
            n_ = _lines(d, f) if f.endswith(".jsonl") else len(j) if isinstance(j, (list, dict)) else 0
            proof.append(item({"receipts.jsonl": "Check results", "audits.json": "Audits", "conditions.json": "Necessary conditions"}[f], f,
                              {"function": RECORD_MAKER.get(f, "code")}, note=f"{n_} {('entr' + ('y' if n_ == 1 else 'ies')) if f.endswith('.jsonl') else 'item' + ('' if n_ == 1 else 's')}"))
    for f in sorted(os.listdir(d)):
        if re.fullmatch(r"stage-\w+\.json", f):
            proof.append(item(f"Stage record: {f[6:-5]}", f, {"function": "code"}, note=(lambda k: f"{k} audit{'' if k == 1 else 's'}")(len((_read(d, f, {}) or {}).get('audits') or []))))
    rec = []
    for f, r in rowsby.items():
        if f not in used:
            rec.append(item(r["name"], f, {"function": RECORD_MAKER.get(f, "code")}))
    for root, _, files in os.walk(d):
        for x in sorted(files):
            f = os.path.relpath(os.path.join(root, x), d).replace(os.sep, "/")
            if f not in used and not x.startswith("."):
                rec.append(item(types.get(f, {}).get("label") or RECORD_NAME.get(f) or f, f, {"function": RECORD_MAKER.get(f, "code")}))
    if rec:
        proof.append({"name": "Run records", "count": len(rec), "collapsed": True, "children": rec})
    groups = [("plan", "Plan", plan, False), ("specs", "Specs", specs, False), ("deliverables", "Deliverable" if len(out) == 1 else "Deliverables", out, False),
              ("proof", "Proof", proof, False)]
    return {"schema": "artifacts-tree/1", "groups": [{"id": k, "label": lab, "count": len(it), "collapsed": col, "items": it}
                                                       for k, lab, it, col in groups]}


def tree_files(t):
    """Every file the tree shows, once each (for serving and tests)."""
    out = []

    def walk(xs):
        for x in xs:
            if x.get("file"):
                out.append(x["file"])
            walk(x.get("children") or [])
    for g in t.get("groups") or []:
        walk(g["items"])
    return out


# ------------------------------------------------------------------------------------------------------------- the groups
# The Artifacts section as four groups (artifacts-groups/1): Run plan, Guides the makers read, the page's sections ("Website
# sections"), Run records. A guide is one row per output file and a page section one row per section in sections.json (its first workflow, then every workflow
# that rewrote it, as versions). Makers are the Map's (j2_map.build); anything the run did not record is None, never guessed. File
# contents are not included: the page fetches a file (/api/artifact) or a section's code (/api/code) only when it is opened.
CHANGE = re.compile(r"\s*\(change (\d+)\)\s*$")


def _final_checks(w):
    """A workflow's checks by code, the last attempt of each atom only: [{check, pass, evidence}]."""
    out = []
    for a in w.get("atoms") or []:
        rs = [r for r in a.get("results") or [] if isinstance(r, dict)]
        last = max((r.get("attempt") or 1 for r in rs), default=None)
        out += [{"check": r.get("check") or r.get("type") or "", "pass": bool(r.get("pass")), "evidence": str(r.get("evidence") or "")}
                for r in rs if (r.get("attempt") or 1) == last]
    return out


def _method(w):
    """The first sentence of how the workflow's first atom was told to work, else None."""
    steps = str((((w.get("atoms") or [{}])[0] or {}).get("how") or {}).get("steps") or "").strip()
    return (re.split(r"(?<=\.)\s", steps)[0].rstrip(".") + ".") if steps else None


def _parts(text):
    """{html, css, js}: non-blank lines of HTML, CSS rules and non-blank lines of JS in a section's code."""
    css = " ".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.S | re.I))
    js = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", text, re.S | re.I))
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
    n = lambda s: sum(1 for x in s.splitlines() if x.strip())
    return {"html": n(html), "css": css.count("{"), "js": n(js)}


def _wf_row(kind, vs, by, persona, last_audit, file, nodes):
    """One guide or section: its first workflow vs[0], every later version, checks (final attempt), the audit of the items it covers."""
    w0 = by[vs[0]]
    covers = sorted({i for v in vs for i in by[v].get("covers") or [] if isinstance(i, int)})
    res = {r.get("item"): r for r in (last_audit or {}).get("results") or [] if isinstance(r, dict)}
    audit = [{"item": i, "verdict": res[i].get("verdict") or "", "pass": bool(res[i].get("pass")), "note": str(res[i].get("note") or "")}
             for i in covers if i in res]
    checks = [{**c, "workflow": v} for v in vs for c in _final_checks(by[v])]
    versions = []
    for k, v in enumerate(vs):
        m = CHANGE.search(str(by[v].get("name") or ""))
        versions.append({"workflow": v, "cycle": by[v].get("cycle"), "purpose": str(by[v].get("purpose") or ""),
                         "label": "first version" if k == 0 else f"change {m.group(1)}" if m else str(by[v].get("name") or v)})
    return {"id": vs[0], "kind": kind, "name": CHANGE.sub("", str(w0.get("name") or vs[0])).replace("-", " "), "maker": persona.get(vs[0]),
            "file": file, "goal": str(w0.get("purpose") or "") or None, "method": _method(w0), "covers": covers, "audit": audit,
            "screenshot": (last_audit or {}).get("screenshot") if audit else None, "checks": checks, "versions": versions,
            "ok": all(a["pass"] for a in audit) and all(c["pass"] for c in checks if c["workflow"] == vs[-1]), "nodes": nodes}      # the latest version's checks


def deliverable_items(dv):
    """The types the planner chose, in build order, each with its why (deliverables.json)."""
    return [{"type": str(x.get("type") if isinstance(x, dict) else x), "why": str((x.get("why") if isinstance(x, dict) else "") or "")}
            for x in ((dv or {}).get("plan") or {}).get("deliverables") or []]


def groups(d, m=None):
    """{"schema": "artifacts-groups/1", "site": {...}, "groups": [{id, label, rows}]} for a run folder (five empty groups when there is none)."""
    import j2_map
    empty = [{"id": k, "label": lab, "rows": []} for k, lab in (("plan", "Run plan"), ("guides", "Guides the makers read"),
                                                                ("site", "Page sections"), ("documents", "Documents"), ("records", "Run records"))]
    if not d or not os.path.isdir(d):
        return {"schema": "artifacts-groups/1", "documents": {}, "site": None, "groups": empty}
    m = m or j2_map.build(d)
    t = {g["id"]: g for g in tree(d, m)["groups"]}
    plan_items = {x["name"]: x for x in t["plan"]["items"]}
    fn = lambda x: ((x or {}).get("made_by") or {}).get("function")
    node_ids = {n["id"] for n in m["nodes"]}
    persona = {}
    for n in m["nodes"]:
        if n["kind"] == "engine" and n.get("persona"):
            for w in n.get("workflows") or []:
                persona.setdefault(w, n["persona"])
    wfs = [w for w in _read(d, "workflows.json", []) or [] if isinstance(w, dict) and w.get("id")]
    by = {w["id"]: w for w in wfs}
    audits = [a for a in _read(d, "audits.json", []) or [] if isinstance(a, dict)]
    last = audits[-1] if audits else None
    has = lambda f: os.path.isfile(os.path.join(d, f))
    # 1 Run plan
    plan = []
    g = _read(d, "goal.json")
    if isinstance(g, dict):
        plan.append({"id": "charter", "kind": "charter", "name": "Charter", "file": "goal.json", "maker": fn(plan_items.get("Charter")),
                     "audience": g.get("audience") or None, "done_when": [str(x) for x in g.get("done_when") or []], "nodes": ["work:charter"]})
    rz = _read(d, "realization.json")
    if isinstance(rz, dict):
        plan.append({"id": "realization", "kind": "realization", "name": "Realization plan", "file": "realization.json",
                     "maker": fn(plan_items.get("Realization plan")), "text": "realization.md" if has("realization.md") else None,
                     "zone": (((rz.get("plan") or {}).get("certainty_assessment")) or {}).get("zone"), "confidence": rz.get("plan_confidence"),
                     "stages": list(rz.get("stages") or {}), "nodes": []})
    dv = _read(d, "deliverables.json")
    if isinstance(dv, dict):
        plan.append({"id": "deliverables", "kind": "deliverables", "name": "Deliverables", "file": "deliverables.json",
                     "maker": fn(plan_items.get("Deliverables")), "items": deliverable_items(dv), "nodes": []})
    if has("workflows.json"):
        cyc = {}
        for w in wfs:
            c = cyc.setdefault(w.get("cycle"), {"cycle": w.get("cycle"), "n": 0, "changes": set(), "fixes": []})
            c["n"] += 1
            mm = CHANGE.search(str(w.get("name") or ""))
            if mm:
                c["changes"].add(int(mm.group(1)))
            c["fixes"] += [str(x) for x in w.get("fixes") or []]
        cycles = [{**c, "changes": sorted(c["changes"])} for _, c in sorted(cyc.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))]
        plan.append({"id": "workflows", "kind": "workflows", "name": "Workflows", "file": "workflows.json", "maker": fn(plan_items.get("Workflows")),
                     "count": len(wfs), "cycles": cycles, "nodes": []})
    # 2 Guides: the workflows that write a document, one row per output file
    secs = _read(d, "sections.json")
    secs = secs if isinstance(secs, dict) else {}
    out_of = lambda w: str((w.get("outputs") or [""])[0] or "")
    files, delivered = {}, {t["file"] for t in load_types()["types"] if t["deliverable"]}      # a PRD, HLD or LLD is a deliverable (Documents), not a guide
    for w in sorted(wfs, key=lambda w: _num(w["id"])):
        o = out_of(w)
        if o.endswith(".md") and o not in delivered and w["id"] not in secs:
            files.setdefault(o, []).append(w["id"])
    guides = []
    for o, vs in files.items():
        rel = f"artifacts/{o}" if has(f"artifacts/{o}") else o if has(o) else None
        row = _wf_row("guide", vs, by, persona, last, rel, [f"work:{v}" for v in vs if f"work:{v}" in node_ids])
        base = os.path.splitext(rel or o)[0]
        olds = sorted(((int(mm.group(1)), f) for f in _all_files(d)
                       for mm in [re.fullmatch(re.escape(base) + r"\.v(\d+)\.md", f)] if mm))
        match = len(olds) == len(vs) - 1      # one saved copy per later version: v1 is the first workflow's, and so on
        row["docs"] = [{"label": f"v{k}", "file": f, "workflow": vs[i] if match else None} for i, (k, f) in enumerate(olds)] + \
                      ([{"label": "current", "file": rel, "workflow": vs[-1]}] if rel else [])
        guides.append(row)
    # 3 the page's sections: one row per section (sections.json), its versions the workflows recorded on it; then the style guide
    site = []
    web = next((n for n in m["nodes"] if is_page_node(n["id"]) and (n.get("status") != "not_made" or has("site/index.html"))), None)      # a document run keeps an unmade page node
    if web:
        for sid in sorted((k for k in secs if k in by), key=_num):
            e = secs[sid] if isinstance(secs[sid], dict) else {}
            vs = [sid] + sorted((w["id"] for w in wfs if w.get("section") == sid and w["id"] != sid), key=_num)
            if len(vs) == 1 and e.get("owner") in by and e["owner"] != sid:
                vs.append(e["owner"])      # an older run records only the current owner
            p = _parts((e.get("head") or "") + (e.get("body") or ""))
            kind = "script" if p["js"] and not p["html"] and not p["css"] else "section"
            row = _wf_row(kind, vs, by, persona, last, "site/index.html" if has("site/index.html") else None, [])
            names = {str(by[v].get("name") or "") for v in vs}
            row.update({"section": sid, "deck": web["id"], "owner": e.get("owner") or sid, "parts": p,
                        "reused_by": [{"id": w["id"], "name": str(w.get("name") or "")} for w in wfs
                                      if w["id"] not in vs and names & {str(x) for x in w.get("dependencies") or []}] if kind == "script" else []})
            site.append(row)
        st = next((x for x in t["specs"]["items"] if x.get("node") == "work:style"), None)
        if st or has("style.json"):
            mb = (st or {}).get("made_by") or {}
            site.append({"id": "style", "kind": "style", "name": "Style guide", "file": "style.json" if has("style.json") else None,
                         "maker": mb.get("persona"), "made_in": mb.get("workflows") or [], "read_by": (st or {}).get("read_by"),
                         "section": "style" if "style" in secs else None, "deck": web["id"], "nodes": ["work:style"] if "work:style" in node_ids else []})
    # 4 Run records: the check receipts, the audits, the necessary conditions and the screenshots
    rec = []
    if has("receipts.jsonl"):
        rs = []
        with open(os.path.join(d, "receipts.jsonl"), encoding="utf-8") as fh:
            for x in fh:
                try:
                    rs.append(json.loads(x))
                except ValueError:
                    pass
        ok = sum(1 for r in rs if isinstance(r, dict) and (r.get("pass") is True or r.get("met") is True))
        rec.append({"id": "receipts", "kind": "receipts", "name": "Check results", "file": "receipts.jsonl", "maker": RECORD_MAKER["receipts.jsonl"],
                    "count": len(rs), "passed": ok, "failed": len(rs) - ok, "nodes": []})
    if audits:
        rec.append({"id": "audits", "kind": "audits", "name": "Audits", "file": "audits.json", "maker": RECORD_MAKER["audits.json"], "nodes": [],
                    "audits": [{"cycle": a.get("cycle"), "version": a.get("version"), "screenshot": a.get("screenshot"),
                                "passed": sum(1 for r in a.get("results") or [] if isinstance(r, dict) and r.get("pass")),
                                "total": len(a.get("results") or [])} for a in audits]})
    for i, a_ in enumerate(audits, 1):      # agent-views/1: every audit as a workflow of its own, beside the chart row
        f_ = f"agent/audits/A-{i}.json"
        rs_ = [r for r in a_.get("results") or [] if isinstance(r, dict)]
        rec.append({"id": f"A-{i}", "kind": "audit", "name": f"Audit A-{i}", "file": f_ if has(f_) else None, "maker": RECORD_MAKER["audits.json"], "nodes": [],
                    "cycle": a_.get("cycle"), "version": a_.get("version"), "passed": sum(1 for r in rs_ if r.get("pass")), "total": len(rs_),
                    "all_pass": a_.get("all_pass") if isinstance(a_.get("all_pass"), bool) else None, "screenshot": a_.get("screenshot")})
    cond = _read(d, "conditions.json")
    if isinstance(cond, list):
        rec.append({"id": "conditions", "kind": "conditions", "name": "Necessary conditions", "file": "conditions.json", "maker": "code", "nodes": [],
                    "items": [{"id": str(c.get("id") or ""), "text": str(c.get("text") or ""), "met": bool(c.get("met"))} for c in cond if isinstance(c, dict)]})
    shots = sorted((f for f in _all_files(d) if re.fullmatch(r"site/shots/[^/]+\.png", f)), key=_num)
    if shots:
        aud = {}
        for a in audits:
            aud.setdefault(a.get("screenshot"), a)      # the first audit that took it
        rec.append({"id": "shots", "kind": "shots", "name": "Audit screenshots", "file": None, "maker": RECORD_MAKER["audits.json"], "nodes": [],
                    "shots": [{"file": f, "version": (aud.get(f) or {}).get("version"),
                               "passed": sum(1 for r in (aud.get(f) or {}).get("results") or [] if isinstance(r, dict) and r.get("pass")) if f in aud else None,
                               "total": len((aud.get(f) or {}).get("results") or []) if f in aud else None} for f in shots]})
    # the documents (PRD, HLD, LLD) are in Documents, not here: each one's sections with their own heading, so a Map link can land on the heading,
    # and its three views
    doc_types = [t for t in load_types()["types"] if t["deliverable"] and t["form"] == "document"]
    decks = [n for n in m["nodes"] if n["id"] in {f"work:{t['name']}" for t in doc_types} and n.get("status") != "not_made"]
    documents = {t["name"]: {"sections": {}, "file": t["file"], "kind": "document"} for t in doc_types if has(t["file"])}
    for deck, (_, ss) in sections_of(d, decks).items():
        for sid, e in (ss or {}).items():
            hit = re.search(r"^#{1,6}\s+(.+?)\s*$", ((e.get("head") or "") + "\n" + (e.get("body") or "")) if isinstance(e, dict) else "", re.M)
            if hit:
                documents.setdefault(deck.split(":", 1)[1], {"sections": {}, "file": None, "kind": "document"})["sections"][sid] = hit.group(1)
    # 5 Documents: the PRD, HLD and LLD as rows too (agent-views/1), so each has the three tabs; the agent view is the
    # artifact-schema data beside the document (prd.json), the human view the markdown, the versions the saved copies in site/
    docs = []
    for name, info in documents.items():
        if not info.get("file") or not has(info["file"]):
            continue
        st = next((x for x in t["specs"]["items"] if x.get("node") == f"work:{name}"), None)
        mb = (st or {}).get("made_by") or {}
        olds = sorted(((int(mm.group(1)), f) for f in _all_files(d) for mm in [re.fullmatch(rf"site/{name}-v(\d+)\.md", f)] if mm))
        # the row's own file is the latest saved copy when it is the current document byte for byte, else none, and its version list holds
        # the copies only: the page routes a Map link by the node's file (prd.md), and the PRD's must keep landing on the Documents view;
        # the human view reads doc_file (the current document), so the text shown is always the current one
        same = olds and _same_file(d, olds[-1][1], info["file"])
        tag = next((t.get("tag") for t in doc_types if t["name"] == name), None) or name.upper()      # PRD, HLD, LLD, or a new type's label
        docs.append({"id": name, "kind": "document", "name": tag, "file": olds[-1][1] if same else None, "doc_file": info["file"], "maker": mb.get("persona"),
                     "made_in": mb.get("workflows") or [], "sections": info["sections"], "nodes": [],      # no Map node: a PRD / HLD / LLD link keeps landing on the Documents view
                     "versions": [{"workflow": None, "cycle": None, "purpose": "", "label": f"v{k}"} for k, _ in olds]
                                 + [{"workflow": None, "cycle": None, "purpose": "", "label": "current"}],
                     "docs": [{"label": f"v{k}", "file": f, "workflow": None} for k, f in olds]})      # the saved copies only: naming prd.md here would catch its Map link
        docs[-1]["ok"] = (agent_view(d, docs[-1]) or {}).get("valid") is True      # the row's mark: the document's data file validates (agent-views/1)
    for x in plan + guides + site + docs + rec + list(documents.values()):
        x["views"] = views(d, x)
    return {"schema": "artifacts-groups/1", "documents": documents,
            "site": {"version": (web or {}).get("version"), "audit": {"version": last.get("version"), "passed": sum(1 for r in last.get("results") or [] if isinstance(r, dict) and r.get("pass")),
                                                                     "total": len(last.get("results") or [])} if last else None} if web else None,
            "groups": [{**e, "rows": r, **({"label": f"{web['label']} sections"} if e["id"] == "site" and web else {})}
                       for e, r in zip(empty, (plan, guides, site, docs, rec))]}


# ------------------------------------------------------------------------------------------------------------- the views
# Every row of groups() and every document carries views (artifact-views/1), the three tabs of the Artifacts pane:
#   {"summary": true,
#    "agent": {"format": "json"|"code"|"text", "file", "schema", "model", "valid"} or None,      what an agent reads
#    "human": {"format": "list"|"markdown"|"table"|"page"|"style"|"chart"|"shots", "file"} or None}      what a person reads
# A view the run did not save is None; the page then says "Not saved for this artifact yet." Every file named here is a file of
# the run folder, so served() serves it.

def _same_file(d, a, b):
    try:
        with open(os.path.join(d, a), "rb") as fa, open(os.path.join(d, b), "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def _ok(d, f):
    p = os.path.join(d, f) if d and f else ""
    return bool(p) and os.path.isfile(p) and os.path.getsize(p) <= MAX_BYTES


def agent_view(d, row):
    """THE ONE PLACE a saved Pydantic JSON is picked up for a row's Agent-readable tab.

    Looked for, in this order:
      1. a Pydantic JSON beside the row's file, same name, .json:  artifacts/copy.md -> artifacts/copy.json,  prd.md -> prd.json.
         A website section has no file of its own: its JSON is site/sections/<section id>.json (W-5 -> site/sections/W-5.json).
      2. the row's own file when it is JSON already (goal.json, realization.json, workflows.json, audits.json, ...).
      3. a website section (or the style guide's section): its code in the page (format "code", shown from /api/code).
      4. any other file, as raw text (a guide's .md, receipts.jsonl).
    The JSON may carry "schema", "model" (else "template") and "valid": the pane shows them above the JSON when present.
    To pick up a JSON saved elsewhere, add its path to `cands` below; nothing else (j2_ui.html included) needs to change."""
    f, sec = row.get("file"), row.get("section")
    stem = os.path.splitext(f)[0] if f and not (sec and row.get("deck")) else None
    cands = [f"{stem}.json"] if stem and not f.endswith(".json") else []
    if row.get("kind") == "document":
        cands.insert(0, f"{row.get('id')}.json")      # the document's data file (prd.json), whichever copy of the markdown the row shows
    if stem and row.get("kind") in ("charter", "realization", "workflows", "receipts", "conditions"):
        cands.insert(0, f"agent/{os.path.basename(stem)}.json")      # agent-views/1: the record in the agent's shape, the original untouched
    if row.get("kind") == "style":
        cands.insert(0, "design.json")      # the style guide's own data (Design/1), when the run saved it
    if sec and row.get("deck"):
        cands.append(f"site/sections/{sec}.json")
    if f and f.endswith(".json"):
        cands.append(f)
    for c in cands:
        if _ok(d, c):
            rec = _read(d, c)
            if rec is None:
                continue      # not JSON: not the agent's form
            meta = rec if isinstance(rec, dict) and isinstance(rec.get("schema"), str) else {}      # only a JSON that names its schema says its model
            valid = meta.get("valid")
            return {"format": "json", "file": c, "schema": meta.get("schema"),
                    "model": meta.get("model") or meta.get("template") or None, "valid": valid if isinstance(valid, bool) else None}
    if sec and row.get("deck") and _ok(d, "site/index.html"):
        return {"format": "code", "file": "site/index.html", "schema": None, "model": None, "valid": None}
    if f and _ok(d, f):
        return {"format": "text", "file": f, "schema": None, "model": None, "valid": None}
    return None


HUMAN = {"charter": "list", "deliverables": "list", "realization": "markdown", "workflows": "table", "guide": "markdown", "document": "markdown", "section": "page",
         "script": "page", "style": "style", "receipts": "table", "audits": "chart", "audit": "list", "conditions": "list", "shots": "shots"}


def human_view(d, row):
    """What a person reads: the rendered view the pane drew before the tabs, from the file it was drawn from; None when nothing was saved."""
    k = row.get("kind")
    f = {"realization": row.get("text"), "shots": ((row.get("shots") or [{}])[0]).get("file"), "document": row.get("doc_file") or row.get("file")}.get(k, row.get("file"))      # a Documents row reads doc_file; a documents entry (no doc_file) its own file
    return {"format": HUMAN[k], "file": f} if k in HUMAN and _ok(d, f) else None


def views(d, row):
    return {"summary": True, "agent": agent_view(d, row), "human": human_view(d, row)}


def _all_files(d):
    """Every file in a run folder, relative, with forward slashes."""
    return sorted(os.path.relpath(os.path.join(r, x), d).replace(os.sep, "/") for r, _, fs in os.walk(d) for x in fs if not x.startswith("."))
