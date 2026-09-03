"""Search-traffic view — one bulk DataForSEO pull, grouped per page, joined into the catalogue.

Reads:  the company record's market (location_name / language_code) + DataForSEO ranked_keywords
        (PAID) through tools/dfs.py.
Writes: _work/traffic-raw.json — every row, the resume/evidence file. An existing one is REUSED, so
        the paid pull never repeats by accident (only redo_traffic=True re-spends).
Returns: {"per_url": {url: {...}}, "top_pages": [...], "meta": {...}} and fills traffic,
        traffic_clean, top_keyword, intent, keywords on each catalogue row, joined by match key.

Rules (each priced or measured):
- BULK, never per-page: one paginated ranked_keywords pull ($2.50) vs per-page calls ($35.80).
- Pre-flight balance guard: below MIN_CREDITS the pull is skipped and the summary says so. Fail
  OPEN if the balance check itself errors (the paid call errors loudly anyway). Never crash.
- A vendor's aggregate is confidently wrong: pull RAW rows and compute BOTH figures —
  `traffic` (raw etv sum) and `traffic_clean` (drop is_another_language rows, collapse
  near-duplicate keywords onto core_keyword taking each core's MAX etv once). Emitting both
  keeps the distortion visible. Downstream ranks by the CLEANED figure.
- Demo rows (no credentials) are never cached: the moment real credentials arrive, the real pull runs.
"""
import os

from .. import store
from ..tools import _shared as sh
from ..tools import dfs
from . import settings
from .urls import match_key


def group(rows):
    """Per URL: raw sum, cleaned sum, top keyword, intent, and the keyword list."""
    pages = {}
    for it in rows:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        etv = float(it.get("etv") or 0.0)
        p = pages.setdefault(url, {"raw": 0.0, "best_etv": -1.0, "kw": "", "intent": "",
                                   "clean_groups": {}, "keywords": []})
        p["raw"] += etv
        if etv > p["best_etv"]:
            p["best_etv"] = etv
            p["kw"] = it.get("keyword") or ""
            p["intent"] = it.get("main_intent") or ""
        if not it.get("is_another_language"):
            core = it.get("core_keyword") or it.get("keyword") or ""
            g = p["clean_groups"]
            g[core] = max(g.get(core, 0.0), etv)    # each core keyword counted ONCE (max, not sum)
        p["keywords"].append({"keyword": it.get("keyword") or "", "position": it.get("rank_group"),
                              "volume": it.get("search_volume"), "etv": round(etv, 1)})
    out = {}
    for url, p in pages.items():
        kws = sorted(p["keywords"], key=lambda k: (k.get("position") or 999, -(k.get("etv") or 0)))
        out[url] = {"traffic": round(p["raw"]), "traffic_clean": round(sum(p["clean_groups"].values())),
                    "top_keyword": p["kw"], "intent": p["intent"],
                    "keywords": kws[:settings.KEYWORDS_PER_PAGE]}
    return out


def _pull(site, say, market):
    """The paid pull, guarded. Returns (doc, skipped_reason)."""
    location, language = market
    mode = sh.dfs_mode(dfs)
    if mode == "off":
        return None, "DataForSEO is not connected, so search traffic was not added"
    if mode == "live":
        bal = dfs.balance()
        if bal is not None and bal < settings.MIN_CREDITS:
            return None, ("the DataForSEO balance is $%.2f, below the $%.2f floor, so the paid traffic "
                          "pull was skipped; top up and re-run to add traffic" % (bal, settings.MIN_CREDITS))
        say("Pulling search traffic", "one bulk pull for %s (%s / %s)%s"
            % (site["host"], location, language, (", balance $%.2f" % bal) if bal is not None else ""))
    else:
        say("Using demo traffic", "no DataForSEO credentials, so the figures are made up and marked as such")
    res = dfs.ranked_keywords_bulk(site["host"], location, language,
                                   limit=settings.DFS_LIMIT, max_rows=settings.TRAFFIC_MAX_ROWS)
    doc = {"domain": site["host"], "market": "%s/%s" % (location, language),
           "total_count": res.get("total_count", 0), "cost_usd": res.get("cost_usd", 0.0),
           "rows": res.get("rows") or [], "demo": mode == "demo"}
    return doc, None


def run(site, say, rows, redo_traffic=False):
    company = sh.company()
    market = (company.get("location_name") or "United States", company.get("language_code") or "en")
    raw_path = os.path.join(site["work"], "traffic-raw.json")
    doc = store.read_json(raw_path)
    skipped = None
    if doc and doc.get("domain") == site["host"] and not redo_traffic:
        say("Reused the saved traffic pull", "%d rows from %s; the paid pull is never repeated by accident"
            % (len(doc.get("rows") or []), doc.get("market", "")))
    else:
        try:
            doc, skipped = _pull(site, say, market)
        except Exception as e:
            # Traffic is a view on top of the catalogue. Losing it must not lose the catalogue,
            # but the user is told, because a silent skip looks like "this site ranks for nothing".
            doc, skipped = None, "the traffic pull failed: %s" % str(e)[:200]
        if doc and not doc.get("demo"):
            store.write_json(raw_path, doc)
    if skipped:
        say("No search traffic added", skipped)

    per_url = group((doc or {}).get("rows") or []) if doc else {}
    by_key = {match_key(u): v for u, v in per_url.items()}
    hit = 0
    for row in rows:
        m = by_key.get(match_key(row["url"]))
        if m:
            row["traffic"], row["traffic_clean"] = m["traffic"], m["traffic_clean"]
            row["top_keyword"], row["intent"], row["keywords"] = m["top_keyword"], m["intent"], m["keywords"]
            hit += 1
        else:
            row.setdefault("traffic", 0)
            row.setdefault("traffic_clean", 0)
            row.setdefault("top_keyword", None)
            row.setdefault("intent", "")
            row.setdefault("keywords", [])
    market_label = (doc or {}).get("market") or "%s/%s" % market
    top_pages = [{"url": u, "traffic": m["traffic"], "traffic_clean": m["traffic_clean"],
                  "top_keyword": m["top_keyword"], "intent": m["intent"], "market": market_label}
                 for u, m in sorted(per_url.items(), key=lambda kv: -kv[1]["traffic_clean"])]
    if doc:
        say("Joined traffic to the catalogue", "%d of %d pages have search traffic%s"
            % (hit, len(rows), " (demo data)" if doc.get("demo") else ""))
    meta = {"market": market_label, "ranked_pages": len(per_url), "rows": len((doc or {}).get("rows") or []),
            "total_count": (doc or {}).get("total_count", 0), "cost_usd": (doc or {}).get("cost_usd", 0.0),
            "demo": bool((doc or {}).get("demo")), "skipped": skipped, "matched_pages": hit}
    return {"per_url": per_url, "top_pages": top_pages, "meta": meta}
