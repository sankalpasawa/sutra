"""Rendering and the small helpers around the artifact models (library design 9.3; J2 `j2_artifact_models.py` 502-631).

Code writes the document, not the agent. Each renderer writes the markdown the existing readers already parse
(parse_hld, parse_lld, md_ids) and the conditions already check (P1-P8 / H1-H6 / L1-L6); the agent sends data and no
agent writes a heading. The functions are J2's, unchanged: `render_section`, `style_from_design`, `normalise`, `errors_of`
and `validate` (which takes the model class explicitly, so it also serves the template classes built at runtime).
"""
import copy
from typing import Any

from .models import FIELD_TYPES, PRIORITIES

__all__ = ["NO_ACTIONS", "render_section", "style_from_design", "normalise", "errors_of", "validate"]

NO_ACTIONS = "have no actions in this version"


def validate(model, data):
    """(object or None, [error lines]) for one section's data, with the full rules. The errors are pydantic's own
    words, so a retry can quote them."""
    try:
        return model.model_validate(data), []
    except Exception as e:
        return None, errors_of(e)


def errors_of(e):
    out = []
    for err in getattr(e, "errors", lambda: [])() or []:
        where = ".".join(str(x) for x in err.get("loc") or ()) or "section"
        out.append(f"{where}: {err.get('msg')}")
    return out or [str(e).splitlines()[0]]


def normalise(model, data: Any):
    """Enum values read case-insensitively and written back in the model's own casing, before validation."""
    if not isinstance(data, dict):
        return data
    d = copy.deepcopy(data)
    enums = {"priority": PRIORITIES, "type": FIELD_TYPES}

    def walk(node):
        if isinstance(node, list):
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for k, v in list(node.items()):
                if k in enums and isinstance(v, str):
                    low = v.strip().lower()
                    node[k] = next((x for x in enums[k] if x.lower() == low), v)
                else:
                    walk(v)
    walk(d)
    return d


# ---------------------------------------------------------------- rendering
def _lines(items, fmt):
    return "\n".join(fmt(i, x) for i, x in enumerate(items, 1))


def _assumptions(data):
    return "".join(f"\nAssumption: {a}" for a in (data.get("assumptions") or []))


def render_section(kind, section, data):
    """The markdown of one section, from its validated data: "## <Section>" and the body, in the shape the readers
    expect. Returns None when nothing here renders that section."""
    d = dict(data or {})
    body = None
    if kind == "prd":
        if section == "Problem":
            body = str(d.get("statement") or "")
        elif section == "Users":
            rows, idle = [], []
            for u in d.get("users") or []:
                acts = ", ".join(u.get("actions") or [])
                rows.append(f"- {u.get('group')}: {u.get('needs') or 'uses the page'}"
                            + (f"; they {acts}." if acts else "."))
                if not (u.get("actions") or []):
                    name = str(u.get("group") or "")
                    idle.append(f"{name[:1].upper() + name[1:]} {NO_ACTIONS}.")
            body = "\n".join(rows) + ("\n\n" + " ".join(idle) if idle else "")
        elif section == "Goals":
            body = _lines(d.get("goals") or [], lambda i, g: f"- **{g['id']}**: {g['statement']}")
        elif section == "Requirements":
            body = _lines(d.get("requirements") or [], lambda i, r: f"{i}. **{r['id']}**: "
                          + str(r["statement"]).rstrip(".") + f" ({r.get('priority', 'must')})."
                          + (f" Serves {', '.join(r.get('goals') or [])}." if r.get("goals") else ""))
        elif section == "Success metrics":
            rows = d.get("success_metrics") or []
            body = ("| Goal | Metric | Target | Window |\n|---|---|---|---|\n"
                    + "\n".join(f"| {m.get('goal')} | {m.get('metric')} | {m.get('target') or 'not set'} | "
                                f"{m.get('window') or 'measurement window not set'} |" for m in rows))
        elif section == "Out of scope":
            body = "\n".join(f"- {x}" for x in d.get("out_of_scope") or [])
    elif kind == "hld":
        if section == "Purpose and scope":
            body = str(d.get("purpose") or "")
        elif section == "Pages":
            body = _lines(d.get("pages") or [], lambda i, p: f"- **{p['id']}** {p['name']}: "
                          + str(p["purpose"]).rstrip(".") + "."
                          + (f" Implements {', '.join(p.get('implements') or [])}." if p.get("implements") else ""))
        elif section == "Components":
            body = _lines(d.get("components") or [], lambda i, c: f"- **{c['id']}** {c['name']}: "
                          + str(c["responsibility"]).rstrip(".") + "."
                          + (f" Covers {', '.join(c.get('covers') or [])}." if c.get("covers") else "")
                          + (f" On {c['page']}." if c.get("page") else ""))
        elif section == "Data flow":
            body = "\n".join(f"- {f.get('from') or f.get('from_')} to {f['to']}: {f['data']}, on {f['trigger']}."
                             for f in d.get("data_flows") or [])
        elif section == "Hosting and deployment":
            h = d.get("hosting") or {}
            body = f"{h.get('kind') or ''}" + (f" {h.get('notes')}" if h.get("notes") else "")
        elif section == "Risks":
            body = "\n".join(f"- {str(r['risk']).rstrip('.')}. Mitigation: {r['mitigation']}"
                             for r in d.get("risks") or [])
    elif kind == "lld":
        if section == "Pages and sections":
            body = _lines(d.get("sections") or [], lambda i, s: f"- **{s['id']}** `{s['anchor']}`"
                          + (f" (page `{s['page']}`)" if s.get("page") else "") + ": shows "
                          + (", ".join(s.get("implements") or []) or "this part of the page") + "."
                          + (f" Implements {', '.join(s.get('implements') or [])}." if s.get("implements") else ""))
        elif section == "Interactive elements":
            body = _lines(d.get("elements") or [], lambda i, e: f"- **{e['id']}** in {e['section']}: `{e['selector']}`"
                          f" trigger {e['trigger']}; behaviour {e['behaviour']}")
        elif section == "Form fields":
            body = _lines(d.get("form_fields") or [],
                          lambda i, f: f"- **{f['id']}** in {f.get('section') or 'S1'}, form `{f['form']}`: field "
                          f"`{f['name']}`, type {f['type']}, required {'yes' if f.get('required') else 'no'}"
                          + (f", validation {f['validation']}" if f.get("validation") else ""))
        elif section == "File structure":
            body = "\n".join(f"- `{x['path']}`: {x['purpose']}" for x in d.get("files") or [])
        elif section == "Responsive and accessibility rules":
            body = "\n".join([f"- {x}" for x in d.get("responsive_rules") or []]
                             + [f"- {x}" for x in d.get("accessibility_rules") or []])
    if body is None:
        return None
    return f"## {section}\n\n{body.strip()}{_assumptions(d)}\n"


def style_from_design(data):
    """The design data as the style guide the rest of the code already uses (style_css, style.json): the same keys
    STYLE_FMT has, so nothing downstream changes."""
    d = dict(data or {})
    fonts = dict(d.get("fonts") or {})
    return {"palette": dict(d.get("palette") or {}),
            "fonts": {"heading": fonts.get("heading"), "body": fonts.get("body"),
                      "google_fonts_url": fonts.get("google_fonts_url")},
            "spacing": dict(d.get("spacing") or {}), "radius": d.get("radius"),
            "buttons": dict(d.get("buttons") or {}), "card": d.get("card"), "notes": d.get("notes") or ""}
