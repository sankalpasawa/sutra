"""brand/type_roles.py — builder 0: what THIS company's page types actually hold.

Port of 0-brand-facts/scripts/classify_types.py. Type NAMES differ per CMS ("successstory" vs
"case-studies"), so no builder may hardcode them. Code summarises each type (count + sample titles
and URLs); the model judges what each type HOLDS, with the criteria in prompts/brand/classify-types.md;
the roles are saved once and every later candidate filter reads them.

Reads:  site_index.json rows grouped by `type` (readable bodies only).
Writes: brand/type-roles.json {"stat_types", "story_types", "commercial_types", "editorial_types", "notes"}
"""
import collections

from .. import llm
from . import _common as cm

OUTPUT = "type-roles.json"
KEYS = ("stat_types", "story_types", "commercial_types", "editorial_types")
SAMPLES = 3                  # titles + URLs shown per type


def _type_table(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r.get("type") or "(untyped)"].append(r)
    lines = []
    for t, grp in sorted(by.items(), key=lambda kv: -len(kv[1])):
        samples = "; ".join('"%s" (%s)' % ((g.get("title") or "")[:60], g["url"][:70]) for g in grp[:SAMPLES])
        lines.append("- %s · %d pages · samples: %s" % (t, len(grp), samples))
    return "\n".join(lines)


def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        r = cm.roles()
        say("Page types already classified", "stat: %s · story: %s" % (r.get("stat_types"), r.get("story_types")))
        return {"files": [OUTPUT], "needs_review": [], "roles": r}
    rows = cm.ok_pages(co.get("language_code"))
    if not rows:
        raise RuntimeError("The site index has no pages with readable text, so page types cannot be classified.")
    table = _type_table(rows)
    say("Summarised the page types", "%d readable pages across %d types" % (len(rows), table.count("\n") + 1))
    roles = llm.json_call(cm.fill(cm.prompt("classify-types"), brand=co["brand"],
                                  niche=co.get("niche_definition") or "", types=table))
    if not isinstance(roles, dict):
        raise RuntimeError("The model did not return the page-type roles as an object.")
    for k in KEYS:
        v = roles.get(k)
        roles[k] = [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])
    roles["notes"] = str(roles.get("notes") or "")
    cm.save(OUTPUT, roles)
    say("Classified the page types",
        "stat: %s · story: %s · commercial: %s · editorial: %s"
        % (roles["stat_types"], roles["story_types"], roles["commercial_types"], roles["editorial_types"]))
    return {"files": [OUTPUT], "needs_review": [], "roles": roles}
