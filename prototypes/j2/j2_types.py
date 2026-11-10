"""Output types defined by data (docs/remove-hardcoding-plan.md, step 1).

load(name) reads one output type from artifacts/types.json and the files its entry points to (the intake prompt, the
charter format, the builder guidance, the necessary conditions), checks them, and returns the type in the shape of an
entry of j2.OUTPUTS. j2.py uses it instead of OUTPUTS only when J2_GENERIC=1, and only for the website so far.
A type that fails a check is refused with the reason (ValueError): a run never half-uses it.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TYPES_PATH = os.path.join(HERE, "artifacts", "types.json")
AGENTS_DIR = os.path.join(HERE, "agents", "j2")
CONDITIONS_DIR = os.path.join(HERE, "conditions")
FORMS = ("page", "doc")
NEEDED = ("label", "noun", "form", "conditions", "rubric", "check_types", "done", "intake", "charter_format", "workflow", "cost")


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
    bad = [k for k in NEEDED if entry.get(k) in (None, "", [])]
    if bad:
        raise ValueError(f"{name}: missing {', '.join(bad)}")
    if entry["form"] not in FORMS:
        raise ValueError(f"{name}: unknown form {entry['form']!r}")
    builder = entry["workflow"].get("builder")
    files = {"builder": os.path.join(AGENTS_DIR, builder or ""), "conditions": os.path.join(CONDITIONS_DIR, entry["conditions"]),
             "intake": os.path.join(HERE, entry["intake"]), "charter_format": os.path.join(HERE, entry["charter_format"])}
    missing = [k for k, p in files.items() if not os.path.isfile(p)]
    if missing:
        raise ValueError(f"{name}: file not found for {', '.join(missing)}")
    if any(not (isinstance(r, dict) and r.get("id") and r.get("text")) for r in entry["rubric"]):
        raise ValueError(f"{name}: every rubric item needs an id and a text")
    out = {"label": entry["label"], "noun": entry["noun"], "sections": tuple(entry["workflow"].get("sections") or ()),
           "conditions": entry["conditions"], "rubric": tuple((r["id"], r["text"]) for r in entry["rubric"]),
           "rates": entry["cost"]["card"], "check_types": tuple(entry["check_types"]), "builder": builder,
           "export": None, "done": entry["done"], "intake": _text(entry["intake"]), "charter_fmt": _text(entry["charter_format"])}
    if entry.get("export") or entry.get("plan"):      # ponytail: the website has neither; step 2 (PRD/HLD/LLD) wires export and plan
        raise ValueError(f"{name}: export and plan are not read from data yet")
    if entry["form"] == "doc":      # a page's file is the page form's own (site/index.html); OUTPUTS names a document's
        out["file"] = entry["file"]
    if entry["form"] == "page":      # the parts a page needs first, in order (J2Run.SITE_ESSENTIALS): its minimum cost
        out["essentials"] = tuple(p for p, n in entry["cost"]["parts"].items() for _ in range(n))
    return out
