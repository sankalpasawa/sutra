"""expand.py — Step 1 (the TIGHT net) and Step 2 (the free filter).

Ported from 10-dataforseo/scripts/s1_expand.py + s2_filter.py. keyword_suggestions allows ONE seed
per call, so it loops; the pool is deduped by keyword. The old wide net (keyword_ideas) stays
dropped — proven twice to return only off-topic noise. The ranked net (s1b) is not ported: it needs
the asset engine's vetted competitor URLs, which this agent does not have.

Reads: seeds, company. Writes (via the tool): _work/pool.json, _work/shortlist.json.
"""
from ..tools import dfs
from . import _common as _c


def expand(seeds, company, say=None):
    """One keyword_suggestions call per seed → {"pool": [{kw, vol, kd, comp, src}], "cost", "per_seed", "demo"}."""
    loc, lang = company.get("location_name") or "United States", company.get("language_code") or "en"
    pool, per_seed, cost, demo = {}, {}, 0.0, False
    for s in seeds:
        got = dfs.keyword_pool(s, limit=_c.TIGHT_LIMIT, location_name=loc, language_code=lang)
        rows = got.get("rows") or []
        cost += got.get("cost") or 0.0
        demo = demo or bool(got.get("demo"))
        per_seed[s] = len(rows)
        for r in rows:
            if r.get("kw") and r["kw"] not in pool:
                pool[r["kw"]] = r
        if say:
            say("Pulled %s for '%s'" % (_plural(len(rows), "keyword"), s),
                "Phrases that contain the seed, most searched first")
    return {"pool": list(pool.values()), "cost": round(cost, 6), "per_seed": per_seed, "demo": demo}


def filter_pool(pool):
    """Step 2, no API: keep volume >= VOL_FLOOR and (KD unknown or KD <= KD_CEIL), most searched first."""
    short = [v for v in (pool or [])
             if (v.get("vol") or 0) >= _c.VOL_FLOOR
             and (v.get("kd") is None or v["kd"] <= _c.KD_CEIL)]
    short.sort(key=lambda x: -(x.get("vol") or 0))
    return short


def _plural(n, word):
    return "%d %s" % (n, word if n == 1 else word + "s")
