"""orphan.py — Blueprint step 7: any high-demand keyword no H2 covers.

Ported from 13-research-structure/scripts/orphan.py. Against the research's EXISTING metrics (no
new API calls): keywords at or over HIGH_VOL with KD under the ceiling, top ORPHAN_POOL by volume,
judged by meaning against the H2 labels. A safety net for content-first.
"""
from .. import llm
from . import _common as _c


def run(sections, metrics_rows):
    hot = [r for r in (metrics_rows or []) if (r.get("vol") or 0) >= _c.HIGH_VOL
           and r.get("kd") is not None and r["kd"] < _c.KD_CEIL]
    hot.sort(key=lambda x: -(x.get("vol") or 0))
    hot = hot[:_c.ORPHAN_POOL]
    if not hot or not sections:
        return []
    secs = "\n".join("- %s" % s["h2"] for s in sections)
    kws = "\n".join("%s | %s" % (r["kw"], r["vol"]) for r in hot)
    allowed = {r["kw"].strip().lower(): r for r in hot}
    try:
        got = llm.json_call(_c.prompt("orphan", sections=secs, keywords=kws))
        raw = (got.get("orphans") if isinstance(got, dict) else got) or []
    except Exception:  # noqa: BLE001 — no orphan list is a warning, not a failure
        return []
    out = []
    for o in raw:
        kw = (o.get("keyword") if isinstance(o, dict) else o) or ""
        row = allowed.get(str(kw).strip().lower())
        if row:                                            # only keywords from the measured pool, with its numbers
            out.append({"keyword": row["kw"], "volume": row.get("vol")})
    return out
