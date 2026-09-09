"""brand/type_roles.py — builder 0: what THIS company's page types actually hold, and what to call them.

Port of 0-brand-facts/scripts/classify_types.py. Type NAMES differ per CMS ("successstory" vs
"case-studies"), so no builder may hardcode them. Code summarises each type (count + sample titles
and URLs); the model judges what each type HOLDS, with the criteria in prompts/brand/classify-types.md;
the roles are saved once and every later candidate filter reads them.

The same call also names each type in plain English ("hr-glossary" -> "HR glossary"), because the
Knowledge screen shows the type list to a person and a CMS slug is not a word anybody says. One
call, not two: the type map is decided once, here, by the one step that already has the samples in
front of it. Code fills any name the model left out, so the screen always has something to print.

Reads:  site_index.json rows grouped by `type` (readable bodies only).
Writes: brand/type-roles.json {"stat_types", "story_types", "commercial_types", "editorial_types",
        "display_names": {type: name}, "notes"}
"""
import collections
import re

from .. import llm
from . import _common as cm

OUTPUT = "type-roles.json"
KEYS = ("stat_types", "story_types", "commercial_types", "editorial_types")
SAMPLES = 3                  # titles + URLs shown per type

_SPLIT = re.compile(r"[-_/]+")


def pretty(name):
    """A readable name for a type the model did not name: "test-library" -> "Test library".

    Deliberately dumb. It cannot know that "hr" is said "HR" and "faq" is said "FAQ" — that is
    exactly the judgment the model is asked for. This is the floor under a missing answer, so a
    type never reaches the screen as an empty label.
    """
    words = [w for w in _SPLIT.split(str(name or "").strip()) if w]
    if not words:
        return ""
    first = words[0]
    return " ".join([first[:1].upper() + first[1:]] + [w.lower() for w in words[1:]])


def _by_type(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r.get("type") or "(untyped)"].append(r)
    return by


def _type_table(by):
    lines = []
    for t, grp in sorted(by.items(), key=lambda kv: -len(kv[1])):
        samples = "; ".join('"%s" (%s)' % ((g.get("title") or "")[:60], g["url"][:70]) for g in grp[:SAMPLES])
        lines.append("- %s · %d pages · samples: %s" % (t, len(grp), samples))
    return "\n".join(lines)


def display_names(names, roles=None):
    """{type: plain name} for the types asked about: the model's answer where it gave one, the
    code's fallback where it did not. Callers hand in the types they actually hold, so a screen
    never shows a name for a type the catalogue no longer has."""
    given = (roles or cm.roles()).get("display_names") or {}
    out = {}
    for t in names:
        v = given.get(t)
        out[t] = str(v).strip() if isinstance(v, str) and str(v).strip() else pretty(t)
    return out


def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        r = cm.roles()
        say("Page types already classified", "stat: %s · story: %s" % (r.get("stat_types"), r.get("story_types")))
        return {"files": [OUTPUT], "needs_review": [], "roles": r}
    rows = cm.ok_pages(co.get("language_code"))
    if not rows:
        raise RuntimeError("The site index has no pages with readable text, so page types cannot be classified.")
    by = _by_type(rows)
    table = _type_table(by)
    say("Summarised the page types", "%d readable pages across %d types" % (len(rows), len(by)))
    roles = llm.json_call(cm.fill(cm.prompt("classify-types"), brand=co["brand"],
                                  niche=co.get("niche_definition") or "", types=table))
    if not isinstance(roles, dict):
        raise RuntimeError("The model did not return the page-type roles as an object.")
    for k in KEYS:
        v = roles.get(k)
        roles[k] = [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])
    # Verify, don't trust: every type in the table gets a name whether the model returned one or not.
    roles["display_names"] = display_names(sorted(by), roles)
    roles["notes"] = str(roles.get("notes") or "")
    cm.save(OUTPUT, roles)
    say("Classified the page types",
        "stat: %s · story: %s · commercial: %s · editorial: %s"
        % (roles["stat_types"], roles["story_types"], roles["commercial_types"], roles["editorial_types"]))
    return {"files": [OUTPUT], "needs_review": [], "roles": roles}
