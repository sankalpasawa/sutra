"""Builds cases.json, the J2 parity cases of tests/library/test_lib_{artifacts,rules,templates}.py. Run it ONCE, by hand; the
tests never run it and never import J2.

    scripts/py tests/library/fixtures/artifacts/build_artifact_cases.py [path/to/J2_Prototype]

It holds the GOOD payload of each of the 19 sections and 3 documents (a small yoga-studio site, in the shape J2's mock
builders write), and BAD variants for the rules. A copy of j2_artifact_models.py and j2_rules.py is imported from a temporary
folder (nothing is written to the J2 checkout) and answers, for the J2 baseline 33aeeda:
  * `transport_sha` / `reply_sha`: schema_sha of transport_schema(model) and reply_schema(model, {}) for the 19 sections and
    the 3 documents, keyed "<kind>/<section>" and "doc/<kind>";
  * `valid_in_j2`: every good payload validates in J2's own models (the script refuses to write otherwise);
  * `rules`: for every (kind, section) of RULES, the J2 `run_rules` result on the good payload and on each bad variant,
    with the `docs` it was given;
  * `render`: J2's `render_section` text for every renderable section and `style_from_design` for the style guide;
  * `normalise`: one payload of mixed-case enum words and what J2's `normalise` makes of it;
  * `errors`: J2's error lines for a few bad payloads (the library words them the same way, with its own type names).
It also copies J2's committed templates/<artifact>/generic.json (five files) and four stored specialised templates
(spec.json, schema.json, meta.json) next to cases.json, as read-only reference data.
"""
import copy
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
J2 = Path(sys.argv[1] if len(sys.argv) > 1 else "~/Desktop/development/J2_Prototype").expanduser()

PRD = {
    "Problem": {"statement": "Busy people in the neighbourhood cannot find a calm class that fits their week.",
                "assumptions": ["Classes run in the evening"]},
    "Users": {"users": [{"group": "newcomers", "needs": "a gentle first class", "actions": ["book a trial class"]},
                        {"group": "regulars", "needs": "a clear weekly timetable", "actions": []}]},
    "Goals": {"goals": [{"id": "G1", "statement": "Fill the evening classes"},
                        {"id": "G2", "statement": "Make booking take under a minute"}]},
    "Requirements": {"requirements": [
        {"id": "R1", "statement": "Newcomers can book a trial class", "priority": "must", "goals": ["G1"]},
        {"id": "R2", "statement": "Regulars can see the weekly timetable", "priority": "should", "goals": ["G1", "G2"]},
        {"id": "R3", "statement": "The page lists the teachers", "priority": "could", "goals": []}]},
    "Success metrics": {"success_metrics": [
        {"goal": "G1", "metric": "trial bookings per week", "target": "20", "window": "in the first 30 days"},
        {"goal": "G2", "metric": "time to book", "target": "under 60 seconds"}]},
    "Out of scope": {"out_of_scope": ["Online payments", "A member login"]},
}
HLD = {
    "Purpose and scope": {"purpose": "One static page that shows classes and takes trial bookings."},
    "Pages": {"pages": [{"id": "P1", "name": "Home", "purpose": "Shows the classes and the booking form.",
                         "implements": ["R1", "R2"]}]},
    "Components": {"components": [
        {"id": "C1", "name": "Timetable", "responsibility": "Lists the weekly classes", "covers": ["R2"], "page": "P1"},
        {"id": "C2", "name": "Booking form", "responsibility": "Takes a trial booking", "covers": ["R1"], "page": "P1"}]},
    "Data flow": {"data_flows": [{"from": "visitor", "to": "owner's inbox", "data": "name and email",
                                  "trigger": "submitting the booking form"}]},
    "Hosting and deployment": {"hosting": {"kind": "one static file on a static host", "notes": "replace the file"}},
    "Risks": {"risks": [{"risk": "Spam bookings", "mitigation": "a hidden honeypot field"}]},
}
LLD = {
    "Pages and sections": {"sections": [
        {"id": "S1", "anchor": "#classes", "page": "P1", "implements": ["C1"]},
        {"id": "S2", "anchor": "#book", "page": "P1", "implements": ["C2"]}]},
    "Interactive elements": {"elements": [
        {"id": "E1", "section": "S2", "selector": "#book-now", "trigger": "click", "behaviour": "submits the form"}]},
    "Form fields": {"form_fields": [
        {"id": "F1", "form": "#booking", "name": "email", "type": "email", "required": True, "section": "S2",
         "validation": "a valid email"},
        {"id": "F2", "form": "#booking", "name": "class", "type": "select", "required": False}]},
    "File structure": {"files": [{"path": "index.html", "purpose": "the whole page"}]},
    "Responsive and accessibility rules": {"responsive_rules": ["one column under 600px"],
                                           "accessibility_rules": ["every field has a label"]},
}
DESIGN = {"palette": {"primary": "#1f5f8b", "secondary": "#e8f1f5", "accent": "#f2a65a", "background": "#ffffff",
                      "surface": "#f6f8fa", "text": "#1d2733", "muted": "#6b7a89"},
          "fonts": {"heading": "Georgia, serif", "body": "system-ui, sans-serif",
                    "google_fonts_url": "https://fonts.googleapis.com/css2?family=Lora"},
          "spacing": {"unit": "8px", "section": "64px"}, "radius": "12px",
          "buttons": {"primary": "background:#1f5f8b;color:#fff", "secondary": "border:1px solid #1f5f8b"},
          "card": "background:#fff;box-shadow:0 1px 3px #0003", "notes": "calm and warm"}
WEBSITE = {"id": "S1", "anchor": "#classes", "implements": ["S1"],
           "html": "<section id=\"classes\"><h2>Classes</h2><p>Evening yoga</p></section>",
           "head": "<meta name=\"description\" content=\"Yoga\">", "selectors_used": ["#classes"],
           "facts_used": ["Evening classes"]}

GOOD = {f"prd/{k}": v for k, v in PRD.items()}
GOOD.update({f"hld/{k}": v for k, v in HLD.items()})
GOOD.update({f"lld/{k}": v for k, v in LLD.items()})
GOOD["design/Style guide"] = DESIGN
GOOD["website/Section"] = WEBSITE
DOCS = {
    "prd": {"problem": PRD["Problem"], "users": PRD["Users"]["users"], "goals": PRD["Goals"]["goals"],
            "requirements": PRD["Requirements"]["requirements"],
            "success_metrics": PRD["Success metrics"]["success_metrics"], "out_of_scope": PRD["Out of scope"]["out_of_scope"],
            "assumptions": ["Classes run in the evening"]},
    "hld": {"purpose": HLD["Purpose and scope"]["purpose"], "pages": HLD["Pages"]["pages"],
            "components": HLD["Components"]["components"], "data_flows": HLD["Data flow"]["data_flows"],
            "hosting": HLD["Hosting and deployment"]["hosting"], "risks": HLD["Risks"]["risks"], "assumptions": []},
    "lld": {"sections": LLD["Pages and sections"]["sections"], "elements": LLD["Interactive elements"]["elements"],
            "form_fields": LLD["Form fields"]["form_fields"], "files": LLD["File structure"]["files"],
            "responsive_rules": ["one column under 600px"], "accessibility_rules": ["every field has a label"],
            "assumptions": []},
}
# what the run has recorded so far, for the rules that point at another section or document
CONTEXT = {
    "prd": {"this": DOCS["prd"]},
    "hld": {"this": DOCS["hld"], "prd": DOCS["prd"]},
    "lld": {"this": DOCS["lld"], "hld": DOCS["hld"], "prd": DOCS["prd"]},
    "design": {}, "website": {"lld": DOCS["lld"]},
}


def mutate(base, path, value):
    out = copy.deepcopy(base)
    node = out
    for part in path[:-1]:
        node = node[part]
    if value is ...:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return out


# (kind/section, label, path inside the good payload, new value (... deletes))
BAD = [
    ("prd/Problem", "empty statement", ["statement"], "  "),
    ("prd/Users", "group without actions or needs", ["users", 1, "needs"], ""),
    ("prd/Goals", "first goal id G2", ["goals", 0, "id"], "G2"),
    ("prd/Goals", "duplicate goal id", ["goals", 1, "id"], "G1"),
    ("prd/Requirements", "unknown goal", ["requirements", 0, "goals"], ["G9"]),
    ("prd/Requirements", "priority in capitals", ["requirements", 0, "priority"], "MUST"),
    ("prd/Requirements", "ids out of order", ["requirements", 1, "id"], "R3"),
    ("prd/Success metrics", "metric names a missing goal", ["success_metrics", 0, "goal"], "G7"),
    ("prd/Out of scope", "no lines", ["out_of_scope"], []),
    ("hld/Purpose and scope", "no purpose", ["purpose"], ""),
    ("hld/Pages", "page id P2 first", ["pages", 0, "id"], "P2"),
    ("hld/Components", "covers a missing requirement", ["components", 0, "covers"], ["R9"]),
    ("hld/Components", "page not in this document", ["components", 1, "page"], "P5"),
    ("hld/Components", "no responsibility", ["components", 0, "responsibility"], ""),
    ("hld/Data flow", "flow without a trigger", ["data_flows", 0, "trigger"], ""),
    ("hld/Hosting and deployment", "no hosting kind", ["hosting", "kind"], ""),
    ("hld/Risks", "no mitigation", ["risks", 0, "mitigation"], ""),
    ("lld/Pages and sections", "anchor without #", ["sections", 0, "anchor"], "hero"),
    ("lld/Pages and sections", "implements a missing component", ["sections", 1, "implements"], ["C8"]),
    ("lld/Interactive elements", "element in a missing section", ["elements", 0, "section"], "S9"),
    ("lld/Interactive elements", "no behaviour", ["elements", 0, "behaviour"], ""),
    ("lld/Form fields", "type not allowed", ["form_fields", 0, "type"], "color"),
    ("lld/Form fields", "field in a missing section", ["form_fields", 0, "section"], "S9"),
    ("lld/File structure", "file without a purpose", ["files", 0, "purpose"], ""),
    ("lld/Responsive and accessibility rules", "no rules", ["responsive_rules"], []),
    ("design/Style guide", "palette colour blue", ["palette", "primary"], "blue"),
    ("design/Style guide", "css that closes a rule", ["card"], "a}b"),
    ("design/Style guide", "fonts url elsewhere", ["fonts", "google_fonts_url"], "https://example.com/f.css"),
    ("website/Section", "page tags in the html", ["html"], "<body><section id=\"classes\"></section></body>"),
    ("website/Section", "anchor points at nothing", ["anchor"], "#nowhere"),
    ("website/Section", "implements a missing LLD section", ["implements"], ["S9"]),
]
ERRORS = [  # bad payloads whose error lines J2 words; the library's pydantic type names differ, the paths and meaning do not
    ("prd/Requirements", ["requirements", 0, "priority"], "urgent"),
    ("lld/Form fields", ["form_fields", 0, "required"], "true"),
    ("website/Section", ["html"], ""),
]


def j2_modules():
    tmp = Path(tempfile.mkdtemp(prefix="j2_artifacts_"))
    for name in ("j2_artifact_models.py", "j2_rules.py"):
        shutil.copy(J2 / name, tmp / name)
    sys.path.insert(0, str(tmp))
    sys.dont_write_bytecode = True
    import j2_artifact_models as am          # noqa: E402
    import j2_rules as jr                    # noqa: E402
    return am, jr


def main():
    am, jr = j2_modules()
    cases = {"j2_commit": "33aeeda", "good": GOOD, "docs": DOCS, "context": CONTEXT, "transport_sha": {},
             "reply_sha": {}, "valid_in_j2": {}, "rules": [], "errors": []}
    for kind, sections in am.SECTION_MODELS.items():
        for section, model in sections.items():
            key = f"{kind}/{section}"
            obj, errs = am.validate(model, am.normalise(model, GOOD[key]))
            assert not errs, (key, errs)
            cases["valid_in_j2"][key] = True
            cases["transport_sha"][key] = am.schema_sha(am.transport_schema(model))
            cases["reply_sha"][key] = am.schema_sha(am.reply_schema(model, {}))
    for kind in ("prd", "hld", "lld"):
        model = am.DOC_MODELS[kind]
        obj, errs = am.validate(model, DOCS[kind])
        assert not errs, (kind, errs)
        cases["transport_sha"][f"doc/{kind}"] = am.schema_sha(am.transport_schema(model))
        cases["reply_sha"][f"doc/{kind}"] = am.schema_sha(am.reply_schema(model, {}))
    for (kind, section) in jr.RULES:
        key = f"{kind}/{section}"
        variants = [("good", GOOD[key])] + [(label, mutate(GOOD[key], path, val))
                                            for k, label, path, val in BAD if k == key]
        for label, data in variants:
            for with_docs in (True, False):
                docs = CONTEXT.get(kind, {}) if with_docs else {}
                cases["rules"].append({"kind": kind, "section": section, "label": label, "with_docs": with_docs,
                                       "data": data, "docs": docs, "results": jr.run_rules(kind, section, data, docs)})
    for key, path, val in ERRORS:
        kind, section = key.split("/", 1)
        model = am.SECTION_MODELS[kind][section]
        data = mutate(GOOD[key], path, val)
        _, errs = am.validate(model, am.normalise(model, data))
        cases["errors"].append({"key": key, "data": data, "j2_errors": errs})
    cases["render"] = {}
    for key, data in GOOD.items():
        kind, section = key.split("/", 1)
        text = am.render_section(kind, section, data)
        if text is not None:
            cases["render"][key] = text
    cases["style"] = am.style_from_design(DESIGN)
    mixed = {"requirements": [{"id": "R1", "statement": "x", "priority": " MUST ", "goals": []}],
             "form_fields": [{"type": "Email"}, {"type": "nope"}]}
    cases["normalise"] = {"in": mixed, "out": am.normalise(None, mixed)}
    cases["rule_names"] = {f"{k}/{s}": names for (k, s), names in jr.RULE_NAMES.items()}
    (HERE / "cases.json").write_text(json.dumps(cases, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    # reference data copied from J2 (read only): the committed generic templates and four stored specialised ones
    for artifact in ("prd", "hld", "lld", "design", "website"):
        dst = HERE / "generic" / artifact
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy(J2 / "templates" / artifact / "generic.json", dst / "generic.json")
    for rel in ("prd/requirements/still-point-yoga-requirements/v1", "hld/components/still-point-yoga-components/v1",
                "lld/form-fields/still-point-yoga-form-fields/v1", "website/section/thread-filter/v1"):
        dst = HERE / "library" / rel
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("spec.json", "schema.json", "meta.json"):
            shutil.copy(J2 / "library" / rel / name, dst / name)
    print("wrote", HERE / "cases.json", len(cases["rules"]), "rule cases")


main()
