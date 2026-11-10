"""Output types defined by data (docs/remove-hardcoding-plan.md, step 1).

load(name) reads one output type from artifacts/types.json and the files its entry points to (the intake prompt, the
charter format, the builder guidance, the plan and atom rules of a document, the necessary conditions), checks them, and
returns the type in the shape of an entry of j2.OUTPUTS. j2.py uses it instead of OUTPUTS only when J2_GENERIC=1 (j2.output_def).
A type that fails a check is refused with the reason (ValueError): a run never half-uses it.
"""
import json
import os
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
TYPES_PATH = os.path.join(HERE, "artifacts", "types.json")
AGENTS_DIR = os.path.join(HERE, "agents", "j2")
CONDITIONS_DIR = os.path.join(HERE, "conditions")
FORMS = ("page", "doc")
NEEDED = ("label", "noun", "form", "conditions", "rubric", "check_types", "done", "intake", "charter_format", "workflow", "cost")
DOC_NEEDED = ("file", "builder", "plan", "atom_rules")
EXPORTS = (None, "docx")
TEXTS = {"intake": "intake", "charter_format": "charter_fmt", "plan": "plan", "atom_rules": "atom_rules"}      # field -> OUTPUTS key


DOCUMENT = "Document"      # generic.json's document-level template, not a section


@lru_cache(maxsize=None)
def template(name):
    """The section templates of a type's template library entry (templates/<name>/generic.json), in document order;
    the document-level template left out. () when the type has no generic.json."""
    p = os.path.join(HERE, "templates", name, "generic.json")
    if not os.path.isfile(p):
        return ()
    with open(p, encoding="utf-8") as f:
        return tuple(t for t in json.load(f)["templates"] if t.get("section") != DOCUMENT)


def sections(name):
    """A type's section names, from its template (the source for section names under J2_GENERIC=1)."""
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


def enabled():
    return os.getenv("J2_GENERIC") == "1"


def _text(rel):
    """A prompt file, its text exactly (the one newline that ends the file is not part of it)."""
    with open(os.path.join(HERE, rel), encoding="utf-8") as f:
        t = f.read()
    return t[:-1] if t.endswith("\n") else t


def load(name, path=TYPES_PATH):
    with open(path, encoding="utf-8") as f:
        entry = next((t for t in json.load(f)["types"] if t.get("name") == name and t.get("kind") == "type"), None)
    if entry is None:
        raise ValueError(f"{name}: no such output type in {os.path.basename(path)}")
    doc = entry.get("form") == "doc"
    bad = [k for k in NEEDED + (DOC_NEEDED if doc else ()) if entry.get(k) in (None, "", [])]
    if bad:
        raise ValueError(f"{name}: missing {', '.join(bad)}")
    if entry["form"] not in FORMS:
        raise ValueError(f"{name}: unknown form {entry['form']!r}")
    if entry.get("export") not in EXPORTS:
        raise ValueError(f"{name}: unknown export {entry['export']!r}")
    # a page's builder is a role file in agents/j2 (workflow.builder); a document's is its own text ("builder")
    files = {"conditions": os.path.join(CONDITIONS_DIR, entry["conditions"]),
             "builder": os.path.join(HERE, entry["builder"]) if entry.get("builder") else os.path.join(AGENTS_DIR, entry["workflow"].get("builder") or ""),
             **{k: os.path.join(HERE, entry[k]) for k in TEXTS if entry.get(k)}}
    missing = [k for k, p in files.items() if not os.path.isfile(p)]
    if missing:
        raise ValueError(f"{name}: file not found for {', '.join(missing)}")
    if any(not (isinstance(r, dict) and r.get("id") and r.get("text")) for r in entry["rubric"]):
        raise ValueError(f"{name}: every rubric item needs an id and a text")
    out = {"label": entry.get("output_label") or entry["label"], "noun": entry["noun"],
           "sections": sections(name) if doc else (), "conditions": entry["conditions"],
           "rubric": tuple((r["id"], r["text"]) for r in entry["rubric"]), "rates": entry["cost"]["card"],
           "check_types": tuple(entry["check_types"]),
           "builder": _text(entry["builder"]) if entry.get("builder") else entry["workflow"]["builder"],
           "export": entry.get("export"), "done": entry["done"]}
    out.update({key: _text(entry[k]) for k, key in TEXTS.items() if entry.get(k)})
    if doc:      # a page's file is the page form's own (site/index.html); a document names its own
        out["file"] = entry["file"]
    else:      # the parts a page needs first, in order (J2Run.SITE_ESSENTIALS): its minimum cost
        out["essentials"] = tuple(p for p, n in entry["cost"]["parts"].items() for _ in range(n))
    if entry.get("mock"):      # migration only: names of the mock functions in j2.py, which j2 resolves (j2.output_def)
        out["mock"] = dict(entry["mock"])
    return out
