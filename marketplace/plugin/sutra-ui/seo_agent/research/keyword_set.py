"""keyword_set.py — Blueprint step 8b: the consolidated KEYWORD SET the write phase checks against.

Ported from 13-research-structure/scripts/keyword_set.py. PURE CODE: the research already holds the
exact fields, so this flattens them. Deduped, order kept, and the primary never appears again in
another list. {primary, variations, secondaries, in_body}, all plain strings.
"""


def _kw(x):
    if isinstance(x, dict):
        return str(x.get("keyword") or "").strip()
    return str(x or "").strip()


def run(keywords):
    keywords = keywords or {}
    ks = {
        "primary": _kw(keywords.get("primary")),
        "variations": [k for k in (_kw(v) for v in (keywords.get("variations") or [])) if k],
        "secondaries": [k for k in (_kw(v) for v in (keywords.get("secondary") or [])) if k],
        "in_body": [k for k in (_kw(v) for v in (keywords.get("in_body") or [])) if k],
    }
    seen = {ks["primary"].lower()} if ks["primary"] else set()
    for key in ("variations", "secondaries", "in_body"):
        out = []
        for k in ks[key]:
            if k.lower() not in seen:
                seen.add(k.lower())
                out.append(k)
        ks[key] = out
    return ks
