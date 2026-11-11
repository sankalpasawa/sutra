"""Output types defined by data (docs/remove-hardcoding-plan.md, step 1).

load(name) reads one output type from artifacts/types.json and the files its entry points to (the intake prompt, the
charter format, the builder guidance, the plan and atom rules of a document, the necessary conditions), checks them, and
returns the type in the shape j2.output_def gives every run.
A type that fails a check is refused with the reason (ValueError): a run never half-uses it.
"""
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TYPES_PATH = os.path.join(HERE, "artifacts", "types.json")
AGENTS_DIR = os.path.join(HERE, "agents", "j2")
CONDITIONS_DIR = os.path.join(HERE, "conditions")
FORMS = ("page", "document")      # room for "script" and "action": not built yet
NEEDED = ("label", "noun", "form", "conditions", "rubric", "check_types", "done", "intake", "charter_format", "workflow", "cost")
DOC_NEEDED = ("file", "builder", "atom_rules")
EXPORTS = (None, "docx")
TEXTS = {"intake": "intake", "charter_format": "charter_fmt", "atom_rules": "atom_rules"}      # field -> OUTPUTS key


DOCUMENT = "Document"      # generic.json's document-level template, not a section
TEMPLATES_DIR = os.path.join(HERE, "templates")
# Types a run makes (j2_types.create) are local and git-ignored: their entries and their templates; --promote moves one
# into types.json and templates/ for a pull request.
LOCAL_TYPES_PATH = os.path.join(HERE, "artifacts", "types.local.json")
LOCAL_LIBRARY_DIR = os.path.join(HERE, "library", "types")
LOCAL_LIBRARY_REL = "library/types"      # how a local entry's "template" names LOCAL_LIBRARY_DIR
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def template_path(name, path=None):
    """Where a type's template file is: its entry points to it (templates/<name>/generic.json when it doesn't); a type a
    run made (library/types/...) has it in the local library."""
    e = next((t for t in _read_types(path)["types"] if t.get("name") == name), {})
    rel = e.get("template") or f"templates/{name}/generic.json"
    if rel.startswith(LOCAL_LIBRARY_REL + "/"):
        return os.path.join(LOCAL_LIBRARY_DIR, os.path.relpath(rel, LOCAL_LIBRARY_REL))
    return os.path.join(TEMPLATES_DIR, os.path.relpath(rel, "templates"))


_TEMPLATES = {}


def template_file(name):
    """Every template of a type's generic.json, in file order, the document-level one included; () when the type has no
    generic.json. The file is the hand-edited source of the type's sections, fields, rules and rendering: it is read
    again only when it changed, so the entries stay the same objects until then (what is built from them is kept by them)."""
    p = template_path(str(name or ""))
    try:
        st = os.stat(p)
    except OSError:
        return ()
    key = (p, st.st_mtime_ns, st.st_size)
    if key not in _TEMPLATES:
        for k in [k for k in _TEMPLATES if k[0] == p]:
            del _TEMPLATES[k]
        try:
            with open(p, encoding="utf-8") as f:
                _TEMPLATES[key] = tuple(json.load(f)["templates"])
        except (ValueError, KeyError, TypeError) as e:      # a hand edit that broke the file is named, with the file
            raise ValueError(f"{p} is not a readable generic.json ({type(e).__name__}: {e})") from None
    return _TEMPLATES[key]


def template(name):
    """The section templates of a type's template library entry (templates/<name>/generic.json), in document order;
    the document-level template left out. () when the type has no generic.json."""
    return tuple(t for t in template_file(name) if t.get("section") != DOCUMENT)


template.cache_clear = _TEMPLATES.clear      # what a test calls after it points TEMPLATES_DIR at a copy


def section_template(name, section):
    """One section's template, by its exact name (None when the type has no such section)."""
    return next((t for t in template(name) if t.get("section") == section), None)


def document(name):
    """The document-level template of a type (the whole document as one object), or None when its file has none."""
    return next((t for t in template_file(name) if t.get("section") == DOCUMENT), None)


def style_guide(path=None):
    """The template a page's first builder fills for the style guide (the page form's "style_guide" in types.json)."""
    return (_read_types(path).get("forms") or {}).get("page", {}).get("style_guide")


def templated(path=None):
    """Every name with a template file, in types.json order: each output type, and before the first type of a form the
    style guide that form names. These are the artifacts the template library knows."""
    d, out = _read_types(path), []
    for t in d["types"]:
        if t.get("kind") != "type":
            continue
        guide = ((d.get("forms") or {}).get(t.get("form")) or {}).get("style_guide")
        for n in ([guide] if guide else []) + [t["name"]]:
            if n not in out and os.path.isfile(template_path(n, path)):
                out.append(n)
    return out


def sections(name):
    """A type's section names, from its template (the source for section names)."""
    return tuple(t["section"] for t in template(name))


def section_of(name, field):
    """The section whose data is `field` (its template's first field: "components" -> "Components")."""
    return next(t["section"] for t in template(name) if t["fields"] and t["fields"][0]["name"] == field)


def cites(name):
    """Cross-document citations, from the template's ref_exists rules whose target is another document:
    {section: (that document's type, its list, the citing field)}, e.g. {"Components": ("prd", "requirements", "covers")}."""
    out = {}
    for t in template(name):
        for r in t.get("rules") or []:
            tgt = str(r.get("target") or "")
            if r.get("rule") == "ref_exists" and tgt and not tgt.startswith("this."):
                doc, rest = tgt.split(".", 1)
                out[t["section"]] = (doc, rest.split("[]")[0], str(r["path"]).split("[].")[-1])
    return out


def section_parts(name, path=None):
    """{section: the rate-card part one section costs at least} (cost.section_parts, else cost.section_part)."""
    cost = _merged(name, path)["cost"]
    return {s: (cost.get("section_parts") or {}).get(s, cost.get("section_part")) for s in sections(name)}


def id_prefixes(name):
    """{list field: id prefix} from the template's ids_sequential rules ("requirements": "R")."""
    return {r["path"]: r["prefix"] for t in template(name) for r in t.get("rules") or [] if r.get("rule") == "ids_sequential"}


def _text(rel):
    """A prompt file, its text exactly (the one newline that ends the file is not part of it)."""
    with open(os.path.join(HERE, rel), encoding="utf-8") as f:
        t = f.read()
    return t[:-1] if t.endswith("\n") else t


_CACHE = {}


def _stamp(p):
    return (p, os.path.getmtime(p), os.path.getsize(p)) if os.path.isfile(p) else (p, None, None)


def _read_local():
    """The types runs made (LOCAL_TYPES_PATH, git-ignored): [] when there are none."""
    if not os.path.isfile(LOCAL_TYPES_PATH):
        return []
    with open(LOCAL_TYPES_PATH, encoding="utf-8") as f:
        return json.load(f).get("types") or []


def _read_types(path=None):
    """types.json with the local types (types.local.json) after its own types, before its records; read again only
    when a file changed (a new type is saved during a run). A local type whose name is already taken is left out, with
    the reason in "refused"."""
    p = path or TYPES_PATH
    key = _stamp(p) + _stamp(LOCAL_TYPES_PATH)
    if key not in _CACHE:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        taken, local, refused = {t.get("name") for t in d["types"]}, [], []
        for t in _read_local():
            if t.get("name") in taken:
                refused.append(f"local type {t.get('name')} refused: {os.path.basename(p)} already has a type of that "
                               f"name (rename it in {os.path.basename(LOCAL_TYPES_PATH)})")
                continue
            taken.add(t.get("name"))
            local.append({**t, "local": True})
        at = next((i for i, t in enumerate(d["types"]) if t.get("kind") != "type"), len(d["types"]))
        d["types"][at:at] = local
        d["refused"] = refused
        for r in refused:
            print(f"j2_types: {r}", file=sys.stderr)
        _CACHE.clear()
        _CACHE[key] = d
    return _CACHE[key]


def refused(path=None):
    """Why each refused local type was left out ([] when none)."""
    return list(_read_types(path)["refused"])


def entries(path=None):
    """Every entry of types.json, output types and records, in file order."""
    return list(_read_types(path)["types"])


def names(path=None):
    """Every output type's name, in file order."""
    return [t["name"] for t in _read_types(path)["types"] if t.get("kind") == "type"]


def _merged(name, path=None):
    """A type's entry with its form's defaults filled in ({name}, {label}, {noun} and {sections} from the type)."""
    d = _read_types(path)
    entry = next((t for t in d["types"] if t.get("name") == name and t.get("kind") == "type"), None)
    if entry is None:
        raise ValueError(f"{name}: no such output type in {os.path.basename(path or TYPES_PATH)}")
    form = (d.get("forms") or {}).get(entry.get("form"))
    if entry.get("form") not in FORMS or not isinstance(form, dict):
        raise ValueError(f"{name}: unknown form {entry.get('form')!r}")
    noun = entry.get("noun") or entry.get("label") or name
    label = str(entry.get("label") or name)
    rule = practice_rule(entry, form)
    fill = lambda v: (v.replace("{name}", name).replace("{label}", label).replace("{lower}", label.lower())
                      .replace("{noun}", noun).replace("{sections}", ", ".join(sections(name)))
                      .replace("{practice}", rule) if isinstance(v, str) else v)
    out = {**{k: fill(v) for k, v in form.items() if k not in ("workflow", "cost")}, **entry, "noun": noun}
    out["workflow"] = {**{k: fill(v) for k, v in (form.get("workflow") or {}).items()}, **(entry.get("workflow") or {})}
    out["cost"] = {**(form.get("cost") or {}), **(entry.get("cost") or {})}
    out["_fill"] = fill
    return out


def practice_rule(entry, form):
    """What a type's prompts add at "{practice}" (the builder's Assumption rule, the no-invented-facts condition and
    rubric item): its form's practice_rule when the type's data says "recommended_practice": true (a policy, guide,
    plan or SOP), else "" (a strict type: its prompts unchanged)."""
    return form.get("practice_rule") or "" if entry.get("recommended_practice") is True else ""


def named(text, path=None, alone=False):
    """The document types a text names by their own words (each type's triggers, or a group's pattern for all its
    members), in types.json order, and then the page types it names: by their own triggers, else (none of those) the
    page types that take the site words (also_when: site-words). The pages only when a document is named too, unless
    alone. Offline only: the planner's answer in mock runs."""
    d, text = _read_types(path), str(text or "")
    hit = lambda t: (any(re.search(x, text, re.I) for x in t.get("triggers") or [])
                     or any(re.search((d.get("groups") or {}).get(g, {}).get("pattern", "$^"), text, re.I) for g in t.get("groups") or []))
    ts = [t for t in d["types"] if t.get("kind") == "type"]
    docs = [t["name"] for t in ts if t.get("form") == "document" and hit(t)]
    pages = [t["name"] for t in ts if t.get("form") == "page" and hit(t)] or \
            [t["name"] for t in ts if t.get("also_when") == "site-words" and re.search(d.get("site_words") or "$^", text, re.I)]
    return docs + pages if docs or alone else []


def page_type(path=None):
    """The first page type in types.json (the mock planner's answer for a brief that names no type)."""
    return next(x["name"] for x in _read_types(path)["types"] if x.get("kind") == "type" and x.get("form") == "page")


def default(path=None):
    """The type chosen before the first message: J2_OUTPUT, else None (not chosen yet: the planner chooses)."""
    t = str(os.getenv("J2_OUTPUT") or "").strip().lower()
    return t if t in names(path) else None


def form(name, path=None):
    """A form's own entry in types.json ("page", "document")."""
    return _read_types(path)["forms"][name]


def form_check_types(name, path=None):
    """Every check type a form's outputs run: the form's own, then each of its types' own, in file order, once each."""
    d = _read_types(path)
    lists = [form(name, path).get("check_types") or []] + [t.get("check_types") or [] for t in d["types"]
                                                         if t.get("kind") == "type" and t.get("form") == name]
    return tuple(dict.fromkeys(x for xs in lists for x in xs))


def expect_kinds(path=None):
    """{expected-output kind: the check type that verifies it} (types.json "expect_kinds")."""
    return dict(_read_types(path)["expect_kinds"])


def info(name, path=None):
    """What the views and messages need of a type: its form, label, file, preview and ready message."""
    e = _merged(name, path)
    return {"name": name, "form": e["form"], "label": e.get("label"), "noun": e["noun"], "file": e.get("file"),
            "preview": e.get("preview"), "ready": e.get("ready")}


def recorded(d, path=None):
    """The document types a run folder names that types.json and the local store no longer have (a local type deleted
    after the run): {name: entry}, with the label and file the run recorded, so the run still opens. The label is
    artifacts.json's row name (written when the run ends), else the planner's new type (deliverables.json), else
    the name in words; the file is documents.json's, else artifacts.json's, else <name>.md. Nothing new is recorded:
    runs already record both, so old runs open the same way."""
    if not d or not os.path.isdir(d):
        return {}

    def rd(n):
        try:
            with open(os.path.join(d, n), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None
    docs, known, out = rd("documents.json"), set(names(path)), {}
    if not isinstance(docs, dict) or not set(docs) - known:
        return {}
    arts = {r.get("type"): r for r in (rd("artifacts.json") or {}).get("rows") or [] if isinstance(r, dict) and r.get("kind") == "type"}
    new = {x.get("type"): x.get("new") or {} for x in ((rd("deliverables.json") or {}).get("plan") or {}).get("deliverables") or []
           if isinstance(x, dict) and isinstance(x.get("new"), dict)}
    for k, v in docs.items():
        if k in known or not NAME_RE.match(str(k)) or not isinstance(v, dict):
            continue
        a, n = arts.get(k) or {}, new.get(k) or {}
        label = str(a.get("name") or n.get("label") or k.replace("_", " ").capitalize())
        file = next((f for f in (v.get("file"), a.get("file"), n.get("file")) if isinstance(f, str) and re.fullmatch(r"[\w.-]+\.md", f)), f"{k}.md")
        out[k] = {"name": k, "kind": "type", "label": label, "tag": label, "color": "--other", "form": "document", "file": file,
                  "deliverable": True, "triggers": [], "groups": [], "depends_on": [], "recorded": True}
    return out


def load(name, path=None):
    entry = _merged(name, path)
    fill = entry.pop("_fill")
    doc = entry["form"] == "document"
    bad = [k for k in NEEDED + (DOC_NEEDED if doc else ()) if entry.get(k) in (None, "", [])]
    if bad:
        raise ValueError(f"{name}: missing {', '.join(bad)}")
    if entry.get("export") not in EXPORTS:
        raise ValueError(f"{name}: unknown export {entry['export']!r}")
    # a page's builder is a role file in agents/j2 (workflow.builder); a document's is its own text ("builder")
    files = {"conditions": os.path.join(CONDITIONS_DIR, entry["conditions"]),
             "builder": os.path.join(HERE if doc else AGENTS_DIR, entry.get("builder") or ""),
             **{k: os.path.join(HERE, entry[k]) for k in TEXTS if entry.get(k)}}
    missing = [k for k, p in files.items() if not os.path.isfile(p)]
    if missing:
        raise ValueError(f"{name}: file not found for {', '.join(missing)}")
    if any(not (isinstance(r, dict) and r.get("id") and r.get("text")) for r in entry["rubric"]):
        raise ValueError(f"{name}: every rubric item needs an id and a text")
    out = {"label": entry.get("output_label") or entry["label"], "noun": entry["noun"],
           "sections": sections(name) if doc else (), "conditions": entry["conditions"],
           "rubric": tuple((r["id"], r["text"].replace("{practice}", fill("{practice}"))) for r in entry["rubric"]),
           "rates": entry["cost"]["card"], "recommended_practice": entry.get("recommended_practice") is True,
           "practice": fill("{practice}"),
           "check_types": tuple(entry["check_types"]),
           "builder": fill(_text(entry["builder"])) if doc else entry["builder"],
           "export": entry.get("export"), "done": entry["done"]}
    out.update({key: fill(_text(entry[k])) for k, key in TEXTS.items() if entry.get(k)})
    # a done-when item's words -> the rate-card part it needs at least (cost.item_parts; first match wins)
    out["item_parts"] = tuple((x["part"], x["words"]) for x in entry["cost"].get("item_parts") or ())
    if doc:      # a page's file is the page form's own (site/index.html); a document names its own
        out["file"] = entry["file"]
    else:      # the parts a page needs first, in order: its minimum cost (J2Run._stage_cost)
        out["essentials"] = tuple(p for p, n in entry["cost"]["parts"].items() for _ in range(n))
    if entry.get("mock"):      # migration only: names of the mock functions in j2.py, which j2 resolves (j2.output_def)
        out["mock"] = dict(entry["mock"])
    return out


def template_for(name, label, secs):
    """A new document type's template library entry (templates/<name>/generic.json), complete enough to build each
    section's model and checks from: one generic template per section, its text required and its assumptions optional,
    the rule that the text is written, and the lines the data is rendered as. It is the type's source from then on: a
    person may edit its fields, rules and render lines."""
    return {"schema": "template-library/1", "artifact": name, "kind": "generic", "version": 1,
            "from": "made by J2 for a new document type (j2_types.create); hand-edit it like any generic.json",
            "templates": [{"name": f"{label} · {x}", "artifact": name, "section": x, "version": 1, "kind": "generic",
                           "description": f"The generic {label} {x} section", "conditions": ["C1"],
                           "fields": [{"name": "text", "type": "string", "required": True, "nullable": False,
                                       "description": f"the {x} section, in the charter's own facts"},
                                      {"name": "assumptions", "type": "list[string]", "required": False, "nullable": False,
                                       "description": "facts you had to assume, each one line"}],
                           "objects": [], "rules": [{"rule": "not_empty", "path": "text", "name": "the section is written",
                                                     "from": "C1"}],
                           "render": [{"text": "{text}"},
                                      {"each": "assumptions", "line": "Assumption: {_}", "after_body": True}]} for x in secs]}


def create_problems(name, label, secs, file, path=None, practice=False):
    """What a proposed new type lacks ([] when it can be made): a name, a form (document), a section, a file name,
    and recommended_practice true or false when given."""
    out = []
    if not NAME_RE.match(str(name or "")):
        out.append(f"name {name!r} must be lower case letters, digits and _ (2 to 41 characters)")
    elif name in names(path) or name in {t.get("name") for t in _read_local()}:
        out.append(f"type {name} already exists")
    if not str(label or "").strip():
        out.append("it needs a label")
    if not isinstance(secs, list) or not [x for x in secs if str(x or "").strip()]:
        out.append("it needs at least one section")
    elif len(set(map(str, secs))) != len(secs) or any(not str(x).strip() or x == DOCUMENT for x in secs):
        out.append("its sections must be unique, named, and not 'Document'")
    if not re.fullmatch(r"[a-z0-9_-]+\.md", str(file or "")):
        out.append(f"file {file!r} must be a .md file name")
    if practice is not None and not isinstance(practice, bool):
        out.append(f"recommended_practice {practice!r} must be true or false")
    return out


def _write_local(types):
    os.makedirs(os.path.dirname(LOCAL_TYPES_PATH), exist_ok=True)
    with open(LOCAL_TYPES_PATH, "w", encoding="utf-8") as f:
        f.write('{\n  "types": [\n' + ",\n".join("    " + json.dumps(t, ensure_ascii=False) for t in types) + "\n  ]\n}\n")


def _write_template(p, tpl):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(tpl, f, indent=1, ensure_ascii=False)
        f.write("\n")


def create(name, label, secs, file=None, path=None, practice=None):
    """Save a new document type, locally: its entry in types.local.json (the document form fills the rest) and its
    template in the local library (library/types/<name>/generic.json), so the next run reuses it; --promote moves it
    into types.json. practice: the type's recommended_practice (kept only when true). ValueError with the reasons
    when it can't be made."""
    file = file or f"{name}.md"
    bad = create_problems(name, label, secs, file, path, practice)
    if bad:
        raise ValueError(f"new type {name}: " + "; ".join(bad))
    entry = {"name": name, "kind": "type", "label": str(label).strip(), "tag": str(label).strip(), "color": "--other",
             "form": "document", "template": f"{LOCAL_LIBRARY_REL}/{name}/generic.json", "file": file, "deliverable": True,
             "triggers": [], "groups": [], "depends_on": [], "made_by": "adaptation",
             **({"recommended_practice": True} if practice else {})}
    local, d = _read_local(), os.path.join(LOCAL_LIBRARY_DIR, name)
    _write_template(os.path.join(d, "generic.json"), template_for(name, entry["label"], [str(x).strip() for x in secs]))
    _write_local(local + [entry])
    template.cache_clear()
    import j2_template_lib      # here, not at the top: the template library reads this module
    bad = j2_template_lib.generic_problems([name])
    if bad:      # a template that doesn't check is never left behind: the type is taken back
        _write_local(local)
        shutil.rmtree(d, ignore_errors=True)
        template.cache_clear()
        raise ValueError(f"new type {name}: its template is not valid: " + "; ".join(bad))
    return entry


def promote(name, path=None):
    """Move a local type into types.json (before the first record, one line, as create() wrote it) and its template
    into templates/<name>/generic.json, and out of the local store: the change a pull request carries."""
    local = _read_local()
    entry = next((t for t in local if t.get("name") == name), None)
    if entry is None:
        raise ValueError(f"{name}: no local type of that name in {os.path.basename(LOCAL_TYPES_PATH)}")
    p = path or TYPES_PATH
    import j2_template_lib      # here, not at the top: the template library reads this module
    bad = j2_template_lib.generic_problems([name])      # checked while still local: a bad one is never promoted
    if bad:
        raise ValueError(f"{name}: its template is not valid: " + "; ".join(bad))
    text = open(p, encoding="utf-8").read()
    if name in {t.get("name") for t in json.loads(text)["types"]}:
        raise ValueError(f"{name}: {os.path.basename(p)} already has a type of that name")
    src = os.path.join(LOCAL_LIBRARY_DIR, name, "generic.json")
    with open(src, encoding="utf-8") as f:
        tpl = json.load(f)
    entry = {**entry, "template": f"templates/{name}/generic.json"}
    first_record = text.index('    {\n      "name": "screenshots"')
    text = text[:first_record] + "    " + json.dumps(entry, ensure_ascii=False) + ",\n" + text[first_record:]
    json.loads(text)
    _write_template(os.path.join(TEMPLATES_DIR, name, "generic.json"), tpl)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    _write_local([t for t in local if t.get("name") != name])
    shutil.rmtree(os.path.dirname(src), ignore_errors=True)
    template.cache_clear()
    return entry


if __name__ == "__main__":      # python3 j2_types.py --promote <name>
    if len(sys.argv) != 3 or sys.argv[1] != "--promote":
        sys.exit("usage: python3 j2_types.py --promote <name>")
    try:
        e = promote(sys.argv[2])
    except ValueError as err:
        sys.exit(str(err))
    print(f"promoted {e['name']}: artifacts/types.json and templates/{e['name']}/generic.json (commit them for a PR)")
