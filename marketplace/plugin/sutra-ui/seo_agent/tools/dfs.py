"""dfs.py — one client, one credential, one place the DataForSEO shape gets untangled.

Every paid call goes through post(), so the login lives in exactly one place and a
credential change is a one-line fix instead of a hunt through five call sites.

The second reason this file exists: DataForSEO buries every answer under
tasks[0].result[0].items, and on an empty, throttled or partial response any of those
three levels can be missing. Unwrapping that at each call site would give five
different KeyErrors halfway through a run, so it happens once, here, in _items().
An odd shape returns an empty list. A real API error (bad login, bad parameters)
still raises, loudly, with the message DataForSEO gave, because pretending a rejected
call returned "no keywords" is how a run quietly produces nonsense.

DEMO_MODE turns itself on when there are no credentials, so the whole app can be
demoed end to end without an account. Every demo row carries "_demo": True, so a
fake number can never be mistaken for a real one downstream.
"""
import hashlib

import httpx

from .. import store

BASE = "https://api.dataforseo.com/v3"
TIMEOUT = 120.0              # their live endpoints genuinely take a minute under load
# The market comes from the company record (knowledge/brand/company.json: location_name and
# language_code). These are only the fallbacks for before that record exists.
DEFAULT_LOCATION_NAME = "United States"
DEFAULT_LANGUAGE = "en"


def market(location_name=None, language_code=None):
    """(location_name, language_code): an explicit choice wins, else the company record, else the
    defaults. Resolved on every call, so a record written mid-session is honoured."""
    rec = store.knowledge("brand/company.json") or {}
    return ((location_name or rec.get("location_name") or DEFAULT_LOCATION_NAME),
            (language_code or rec.get("language_code") or DEFAULT_LANGUAGE))

# Set True to force demo output even when credentials exist. Left False, demo still
# activates on its own whenever credentials are absent, which is the usual case.
DEMO_MODE = False


class NoCredentials(Exception):
    pass


# ---- credentials -----------------------------------------------------------------------

def _auth():
    c = store.connections()
    login = (c.get("dataforseo_login") or "").strip()
    password = (c.get("dataforseo_password") or "").strip()
    return (login, password) if login and password else None


def available():
    """True when a real call can be made. Demo output is not 'available'; callers that
    only want real numbers check this first."""
    return _auth() is not None


def demo_mode():
    """Resolved live, not frozen at import, because the user can paste credentials into
    the Connections tab while the app is running."""
    return DEMO_MODE or _auth() is None


# ---- the one call ----------------------------------------------------------------------

def post(path, payload):
    auth = _auth()
    if auth is None:
        raise NoCredentials(
            "DataForSEO is not connected. Add dataforseo_login and dataforseo_password "
            "in the Connections tab."
        )
    r = httpx.post(BASE + path, auth=auth, json=payload, timeout=TIMEOUT,
                   headers={"content-type": "application/json"})
    r.raise_for_status()
    data = r.json()
    # They answer 200 with the real verdict inside the body, so the HTTP code alone is
    # no proof the call worked. 20000 is their "ok".
    code = data.get("status_code")
    if code is not None and code != 20000:
        raise RuntimeError("DataForSEO refused the call (%s): %s"
                           % (code, data.get("status_message", "no message")))
    return data


def _items(data):
    """tasks[0].result[0].items, where every level is allowed to be missing.

    A missing level means 'nothing found' and returns []. A task that came back with
    its own error code raises, because that is a broken request, not an empty one.
    """
    tasks = (data or {}).get("tasks") or []
    if not tasks:
        return []
    task = tasks[0] or {}
    code = task.get("status_code")
    if code is not None and code != 20000:
        raise RuntimeError("DataForSEO task failed (%s): %s"
                           % (code, task.get("status_message", "no message")))
    result = task.get("result") or []
    if not result:
        return []
    return (result[0] or {}).get("items") or []


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _float(v, default=0.0):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return default


def bare_domain(domain):
    """Their target field wants example.com, not https://example.com/pricing."""
    d = (domain or "").strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.split("/")[0].split("?")[0]
    if d.startswith("www."):
        d = d[4:]
    return d


# ---- the four calls --------------------------------------------------------------------

def ranked_keywords(domain, limit=100, location_name=None, language_code=None):
    """What this domain already ranks for. Returns [{keyword, position, volume, url}]."""
    if demo_mode():
        return _demo_ranked(domain, limit)
    location_name, language_code = market(location_name, language_code)
    payload = [{
        "target": bare_domain(domain),
        "location_name": location_name,
        "language_code": language_code,
        "limit": _int(limit, 100),
        "order_by": ["ranked_serp_element.serp_item.rank_group,asc"],
    }]
    data = post("/dataforseo_labs/google/ranked_keywords/live", payload)
    out = []
    for it in _items(data):
        it = it or {}
        kd = it.get("keyword_data") or {}
        serp = (it.get("ranked_serp_element") or {}).get("serp_item") or {}
        kw = kd.get("keyword")
        if not kw:
            continue
        out.append({
            "keyword": kw,
            "position": _int(serp.get("rank_group") or serp.get("rank_absolute")),
            "volume": _int((kd.get("keyword_info") or {}).get("search_volume")),
            "url": serp.get("url") or "",
            # What Google shows for the page. index_site falls back to these when the
            # site itself refuses the crawl, so an index can still be built.
            "title": serp.get("title") or "",
            "description": serp.get("description") or "",
        })
    return out


def keyword_ideas(seed, limit=100, location_name=None, language_code=None):
    """Keywords related to a seed. Returns [{keyword, volume, difficulty, cpc}]."""
    if demo_mode():
        return _demo_keywords(_seeds(seed), limit, related=True)
    location_name, language_code = market(location_name, language_code)
    payload = [{
        "keywords": _seeds(seed),
        "location_name": location_name,
        "language_code": language_code,
        "limit": _int(limit, 100),
    }]
    data = post("/dataforseo_labs/google/keyword_ideas/live", payload)
    return [_keyword_row(it) for it in _items(data) if (it or {}).get("keyword")]


def keyword_metrics(keywords, location_name=None, language_code=None):
    """Volume, difficulty and cpc for keywords we already have. Same row shape as
    keyword_ideas, so the two can be mixed in one table."""
    seeds = _seeds(keywords)
    if not seeds:
        return []
    if demo_mode():
        return _demo_keywords(seeds, len(seeds), related=False)
    location_name, language_code = market(location_name, language_code)
    # Their overview endpoint caps at 700 keywords per call.
    payload = [{
        "keywords": seeds[:700],
        "location_name": location_name,
        "language_code": language_code,
    }]
    data = post("/dataforseo_labs/google/keyword_overview/live", payload)
    return [_keyword_row(it) for it in _items(data) if (it or {}).get("keyword")]


def serp(keyword, depth=10, location_name=None, language_code=None):
    """The live first page for one keyword.
    Returns {top_results: [{position, title, url, description}], people_also_ask: [str]}.
    """
    if demo_mode():
        return _demo_serp(keyword, depth)
    location_name, language_code = market(location_name, language_code)
    payload = [{
        "keyword": keyword,
        "location_name": location_name,
        "language_code": language_code,
        "depth": _int(depth, 10),
    }]
    data = post("/serp/google/organic/live/advanced", payload)
    top, paa = [], []
    for it in _items(data):
        it = it or {}
        kind = it.get("type")
        if kind == "organic" and len(top) < _int(depth, 10):
            top.append({
                "position": _int(it.get("rank_group") or it.get("rank_absolute")),
                "title": it.get("title") or "",
                "url": it.get("url") or "",
                "description": it.get("description") or it.get("snippet") or "",
            })
        elif kind == "people_also_ask":
            # PAA arrives as a block with its questions nested one level down.
            for q in (it.get("items") or []):
                title = (q or {}).get("title")
                if title and title not in paa:
                    paa.append(title)
    return {"top_results": top, "people_also_ask": paa}


# ---- the catalogue's calls (index_site) ---------------------------------------------------------

def balance():
    """The account balance in dollars, or None when it cannot be read (no credentials, network,
    odd shape). None means "unknown, proceed": the paid call itself errors loudly if broke."""
    auth = _auth()
    if auth is None:
        return None
    try:
        r = httpx.get(BASE + "/appendix/user_data", auth=auth, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return float(((data.get("tasks") or [{}])[0].get("result") or [{}])[0]["money"]["balance"])
    except Exception:
        return None


def _task(data):
    """(task, first result) with the same error discipline as _items()."""
    tasks = (data or {}).get("tasks") or []
    task = (tasks[0] if tasks else None) or {}
    code = task.get("status_code")
    if code is not None and code != 20000:
        raise RuntimeError("DataForSEO task failed (%s): %s"
                           % (code, task.get("status_message", "no message")))
    result = task.get("result") or []
    return task, ((result[0] if result else None) or {})


def _bulk_row(it):
    it = it or {}
    kd = it.get("keyword_data") or {}
    serp_item = (it.get("ranked_serp_element") or {}).get("serp_item") or {}
    props = kd.get("keyword_properties") or {}
    return {
        "keyword": kd.get("keyword") or "",
        "is_another_language": bool(props.get("is_another_language")),
        "core_keyword": props.get("core_keyword") or "",
        "main_intent": (kd.get("search_intent_info") or {}).get("main_intent") or "",
        "url": serp_item.get("url") or "",
        "etv": _float(serp_item.get("etv"), 0.0),
        "rank_group": _int(serp_item.get("rank_group") or serp_item.get("rank_absolute")),
        "search_volume": _int((kd.get("keyword_info") or {}).get("search_volume")),
    }


def ranked_keywords_bulk(domain, location_name, language_code, limit=1000, max_rows=50000):
    """EVERY keyword the domain ranks for, in one paginated pull ordered by etv desc.

    Returns {"rows": [{keyword, is_another_language, core_keyword, main_intent, url, etv,
    rank_group, search_volume}], "total_count": int, "cost_usd": float}.

    Pagination is driven by the vendor's total_count and offset. Their etv-desc sort is UNSTABLE
    server-side: the same offset can return 28 rows on one call and 676 on the next, so a short
    page is re-asked ONCE and the larger answer wins. total_count also overstates what they will
    serve (the tail is etv~0); the shortfall is the vendor's and is visible in rows vs total_count.
    max_rows is a loud safety ceiling, never a silent cap: the caller sees it in the counts.
    """
    if demo_mode():
        return _demo_ranked_bulk(domain, limit)
    location_name, language_code = market(location_name, language_code)
    limit = max(1, _int(limit, 1000))
    rows, offset, total, cost = [], 0, None, 0.0
    partial = None
    while True:
        task = {"target": bare_domain(domain), "location_name": location_name,
                "language_code": language_code, "limit": limit, "offset": offset,
                "order_by": ["ranked_serp_element.serp_item.etv,desc"]}
        # Every page is paid for. A refusal mid-pull (402: out of balance) must not throw
        # away the pages already bought: measured 2026-09-04, a $0.72 balance bought five
        # pages, the sixth was refused, and the whole pull was discarded. Keep what we have,
        # say it is partial, and let the caller join it.
        if rows:
            bal = balance()
            if bal is not None and bal < BULK_PAGE_FLOOR:
                partial = "stopped at %d of %d rows to keep the balance above $%.2f (it is $%.2f)" % (
                    len(rows), total or 0, BULK_PAGE_FLOOR, bal)
                break
        try:
            t, result = _task(post("/dataforseo_labs/google/ranked_keywords/live", [task]))
        except Exception as e:  # noqa: BLE001 -- 402, a timeout, a 5xx: the rows so far are still paid for
            if not rows:
                raise
            partial = "stopped at %d of %d rows: %s" % (len(rows), total or 0, str(e)[:140])
            break
        cost += float(t.get("cost") or 0)
        if total is None:
            total = _int(result.get("total_count"), 0)
        items = result.get("items") or []
        expected = min(limit, max(0, total - offset))
        if len(items) < expected:
            t2, result2 = _task(post("/dataforseo_labs/google/ranked_keywords/live", [task]))
            cost += float(t2.get("cost") or 0)
            items2 = result2.get("items") or []
            if len(items2) > len(items):
                items = items2
        rows += [_bulk_row(it) for it in items if (it or {}).get("keyword_data")]
        offset += limit
        if offset >= total or not items or offset >= max_rows:
            break
    out = {"rows": rows, "total_count": total or 0, "cost_usd": round(cost, 4)}
    if partial:
        out["partial"] = partial
    return out


# A page of 1,000 ranked rows costs about $0.11 on DataForSEO Labs. Stop paging when the
# balance would not cover another one, so a pull never drives the account negative.
BULK_PAGE_FLOOR = 0.15


def _demo_ranked_bulk(domain, limit):
    d = bare_domain(domain) or "example.com"
    rows = []
    for r in _demo_ranked(d, limit):
        rows.append({"keyword": r["keyword"], "is_another_language": False,
                     "core_keyword": r["keyword"], "main_intent": "informational",
                     "url": r["url"], "etv": round(r["volume"] * 0.1, 1),
                     "rank_group": r["position"], "search_volume": r["volume"], "_demo": True})
    return {"rows": rows, "total_count": len(rows), "cost_usd": 0.0, "_demo": True}


def _keyword_row(it):
    it = it or {}
    info = it.get("keyword_info") or {}
    props = it.get("keyword_properties") or {}
    return {
        "keyword": it.get("keyword") or "",
        "volume": _int(info.get("search_volume")),
        "difficulty": _int(props.get("keyword_difficulty")),
        "cpc": _float(info.get("cpc")),
    }


def _seeds(value):
    """Callers pass a string or a list. Normalise once so the payload builders do not
    each guess."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(v).strip() for v in value if str(v).strip()]


# ---- demo data -------------------------------------------------------------------------
# Stable, not random: the same input gives the same numbers on every run, so a demo can be
# screenshotted twice and match. md5 rather than hash() because hash() is salted per process.

def _spread(text, low, high):
    h = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
    return low + (h % max(1, (high - low + 1)))


_DEMO_MODIFIERS = [
    "{s}", "best {s}", "{s} software", "{s} tools", "{s} for small business",
    "how to {s}", "{s} examples", "{s} pricing", "free {s}", "{s} vs alternatives",
    "{s} template", "{s} checklist", "what is {s}", "{s} guide", "{s} benefits",
]

_DEMO_PATHS = [
    "/", "/pricing", "/blog/getting-started", "/features", "/blog/complete-guide",
    "/integrations", "/blog/comparison", "/about", "/blog/best-practices", "/contact",
    "/customers", "/blog/how-it-works",
]


def _demo_ranked(domain, limit):
    d = bare_domain(domain) or "example.com"
    stem = d.split(".")[0].replace("-", " ")
    rows = []
    for i, path in enumerate(_DEMO_PATHS[:_int(limit, 100)]):
        kw = _DEMO_MODIFIERS[i % len(_DEMO_MODIFIERS)].format(s=stem)
        rows.append({
            "keyword": kw,
            "position": _spread(d + kw, 1, 40),
            "volume": _spread(kw + d, 40, 9000),
            "url": "https://" + d + path,
            "_demo": True,
        })
    return rows


def _demo_keywords(seeds, limit, related):
    rows, seen = [], set()
    for seed in (seeds or ["seo"]):
        variants = ([m.format(s=seed) for m in _DEMO_MODIFIERS] if related else [seed])
        for kw in variants:
            if kw in seen or len(rows) >= _int(limit, 100):
                continue
            seen.add(kw)
            rows.append({
                "keyword": kw,
                "volume": _spread(kw, 30, 12000),
                "difficulty": _spread("d" + kw, 3, 78),
                "cpc": round(_spread("c" + kw, 20, 1400) / 100.0, 2),
                "_demo": True,
            })
    return rows


def _demo_serp(keyword, depth):
    kw = (keyword or "seo").strip()
    hosts = ["hubspot.com", "semrush.com", "ahrefs.com", "moz.com", "backlinko.com",
             "searchenginejournal.com", "wordstream.com", "neilpatel.com",
             "contentmarketinginstitute.com", "zapier.com"]
    top = []
    for i, host in enumerate(hosts[:_int(depth, 10)]):
        top.append({
            "position": i + 1,
            "title": "%s: the %s guide (%s)" % (kw.title(), ["complete", "practical",
                                                            "2026"][i % 3], host.split(".")[0].title()),
            "url": "https://www.%s/blog/%s" % (host, kw.lower().replace(" ", "-")),
            "description": ("Everything about %s, with examples and a checklist you can "
                            "copy." % kw),
            "_demo": True,
        })
    paa = ["What is %s?" % kw,
           "How does %s work?" % kw,
           "Is %s worth it for a small team?" % kw,
           "How much does %s cost?" % kw,
           "What is the best alternative to %s?" % kw]
    return {"top_results": top, "people_also_ask": paa, "_demo": True}


# ---- appended for the write phase: the section-keyword hunt ----------------------------------------

def keyword_suggestions(seed, limit=80, location_name=None, language_code=None):
    """keyword_suggestions, one seed per call: phrases that contain the seed, best volume first.
    Returns [{kw, vol, kd}] (kd is None when DataForSEO gives none). Market from the company record."""
    if not (seed or "").strip():
        return []
    if demo_mode():
        return [{"kw": r["keyword"], "vol": r["volume"], "kd": r["difficulty"]}
                for r in _demo_keywords([seed.strip()], limit, related=True)]
    location_name, language_code = market(location_name, language_code)
    data = post("/dataforseo_labs/google/keyword_suggestions/live", [{
        "keyword": seed.strip(), "location_name": location_name, "language_code": language_code,
        "limit": _int(limit, 80), "order_by": ["keyword_info.search_volume,desc"]}])
    out = []
    for it in _items(data):
        it = it or {}
        ki, kp = it.get("keyword_info") or {}, it.get("keyword_properties") or {}
        if it.get("keyword"):
            kd = kp.get("keyword_difficulty")
            out.append({"kw": it["keyword"], "vol": _int(ki.get("search_volume")),
                        "kd": None if kd is None else _int(kd)})
    return out


# ---- the research engine's calls (ported from 10-dataforseo/scripts: s1_expand, s3_metrics, s4_serp, dfs.balance) ----
# These take location_name / language_code, because that is what the company record carries (the
# original engine's config did the same). Every call returns the parsed rows AND the "cost" field
# DataForSEO puts on the response, so a run can add up what it spent. Demo rows carry "_demo": True.

def _first_result(data):
    """tasks[0].result[0] as a dict, {} when any level is missing. A failed task raises."""
    tasks = (data or {}).get("tasks") or []
    if not tasks:
        return {}
    task = tasks[0] or {}
    code = task.get("status_code")
    if code is not None and code != 20000:
        raise RuntimeError("DataForSEO task failed (%s): %s"
                           % (code, task.get("status_message", "no message")))
    result = task.get("result") or []
    return (result[0] or {}) if result else {}


def _cost(data):
    try:
        return round(float((data or {}).get("cost") or 0.0), 6)
    except (TypeError, ValueError):
        return 0.0


# balance() is defined above (the catalogue's calls) with the same contract the research engine
# needs: dollars, or None when it cannot be read, and None means "unknown, proceed".

def _pool_row(it, src):
    it = it or {}
    ki = it.get("keyword_info") or {}
    kp = it.get("keyword_properties") or {}
    return {"kw": it.get("keyword"), "vol": ki.get("search_volume") or 0,
            "kd": kp.get("keyword_difficulty"), "comp": ki.get("competition_level"), "src": src}


def keyword_pool(seed, limit=200, location_name="United States", language_code="en"):
    """The TIGHT net for the research engine: phrases that contain the seed, ONE seed per call (the
    endpoint allows no more). The same endpoint as keyword_suggestions() above, kept apart because
    this one returns the original engine's pool row shape and the cost of the call.
    Returns {"rows": [{kw, vol, kd, comp, src}], "cost": float}."""
    if demo_mode():
        return {"rows": _demo_suggestions(seed, limit), "cost": 0.0, "demo": True}
    data = post("/dataforseo_labs/google/keyword_suggestions/live", [{
        "keyword": seed, "location_name": location_name, "language_code": language_code,
        "limit": _int(limit, 200), "order_by": ["keyword_info.search_volume,desc"]}])
    rows = [_pool_row(it, "tight") for it in _items(data) if (it or {}).get("keyword")]
    return {"rows": rows, "cost": _cost(data)}


def keyword_overview(keywords, location_name="United States", language_code="en"):
    """Volume + KD + INTENT for a list (their cap is 700 per call).
    Returns {"rows": [{kw, vol, kd, intent}] sorted by volume desc, "cost": float}."""
    kws = _seeds(keywords)[:700]
    if not kws:
        return {"rows": [], "cost": 0.0}
    if demo_mode():
        return {"rows": _demo_overview(kws), "cost": 0.0, "demo": True}
    data = post("/dataforseo_labs/google/keyword_overview/live", [{
        "location_name": location_name, "language_code": language_code, "keywords": kws}])
    rows = []
    for it in _items(data):
        it = it or {}
        ki = it.get("keyword_info") or {}
        kp = it.get("keyword_properties") or {}
        si = it.get("search_intent_info") or {}
        if it.get("keyword"):
            rows.append({"kw": it.get("keyword"), "vol": ki.get("search_volume"),
                         "kd": kp.get("keyword_difficulty"), "intent": si.get("main_intent")})
    rows.sort(key=lambda x: -(x["vol"] or 0))
    return {"rows": rows, "cost": _cost(data)}


def serp_advanced(keyword, depth=20, paa_click_depth=3, ai_overview=True,
                  location_name="United States", language_code="en"):
    """The live Google page for one keyword, with the AI Overview block loaded (without
    load_async_ai_overview it goes missing). Returns {"extract": {...}, "cost": float} where the
    extract is the original engine's 04-serp-extract shape: keyword, features, top_organic[:10],
    featured_snippet, paa, ai_overview{text, cites}, related_searches."""
    if demo_mode():
        return {"extract": _demo_serp_extract(keyword, depth), "cost": 0.0, "demo": True}
    task = {"keyword": keyword, "location_name": location_name, "language_code": language_code,
            "depth": _int(depth, 20)}
    if paa_click_depth:
        task["people_also_ask_click_depth"] = _int(paa_click_depth, 3)
    if ai_overview:
        task["load_async_ai_overview"] = True
    data = post("/serp/google/organic/live/advanced", [task])
    return {"extract": serp_extract(keyword, _items(data)), "cost": _cost(data)}


def serp_extract(keyword, items):
    """Pure code: the structured extract out of the raw SERP items (s4_serp.py, unchanged logic)."""
    from collections import Counter
    items = [i for i in (items or []) if isinstance(i, dict)]
    top = [{"rank": i.get("rank_group"), "domain": i.get("domain"), "title": i.get("title"),
            "url": i.get("url")} for i in items if i.get("type") == "organic"][:10]
    snippet, paa, ai_ov, related = None, [], None, []
    for i in items:
        t = i.get("type")
        if t == "featured_snippet":
            snippet = {"domain": i.get("domain"), "text": i.get("description") or i.get("title")}
        elif t == "people_also_ask":
            paa = [e.get("title") for e in (i.get("items") or []) if isinstance(e, dict) and e.get("title")]
        elif t == "ai_overview":
            txt = " ".join((e.get("text") or "") for e in (i.get("items") or []) if isinstance(e, dict))
            refs = [r.get("domain") for r in (i.get("references") or []) if isinstance(r, dict) and r.get("domain")]
            ai_ov = {"text": txt.strip(), "cites": refs}
        elif t == "related_searches":
            related += [x for x in (i.get("items") or []) if isinstance(x, str)]
    return {"keyword": keyword, "features": dict(Counter(i.get("type") for i in items)),
            "top_organic": top, "featured_snippet": snippet, "paa": paa,
            "ai_overview": ai_ov, "related_searches": related}


# ---- demo data for the research calls (same rules: stable, flagged, never mistaken for real) ----

def _demo_suggestions(seed, limit):
    rows = []
    for i, m in enumerate(_DEMO_MODIFIERS[:_int(limit, 200)]):
        kw = m.format(s=seed)
        rows.append({"kw": kw,
                     # the plain seed always clears the floor/ceiling, so a demo run has a shortlist
                     "vol": 1400 if i == 0 else _spread(kw, 30, 12000),
                     "kd": 22 if i == 0 else _spread("d" + kw, 3, 78),
                     "comp": ["LOW", "MEDIUM", "HIGH"][_spread("c" + kw, 0, 2)],
                     "src": "tight", "_demo": True})
    return rows


def _demo_overview(keywords):
    rows = []
    for i, kw in enumerate(keywords):
        rows.append({"kw": kw, "vol": 1400 if i == 0 else _spread(kw, 30, 12000),
                     "kd": 22 if i == 0 else _spread("d" + kw, 3, 78),
                     "intent": "informational" if i == 0 else
                     ["informational", "commercial", "navigational"][_spread("i" + kw, 0, 2)],
                     "_demo": True})
    rows.sort(key=lambda x: -(x["vol"] or 0))
    return rows


def _demo_serp_extract(keyword, depth):
    kw = (keyword or "seo").strip()
    hosts = ["hubspot.com", "semrush.com", "ahrefs.com", "moz.com", "backlinko.com",
             "searchenginejournal.com", "wordstream.com", "neilpatel.com",
             "contentmarketinginstitute.com", "zapier.com"]
    top = [{"rank": i + 1, "domain": h,
            "title": "%s: the %s guide (%s)" % (kw.title(), ["complete", "practical", "2026"][i % 3], h.split(".")[0].title()),
            "url": "https://www.%s/blog/%s" % (h, kw.lower().replace(" ", "-"))}
           for i, h in enumerate(hosts[:min(10, _int(depth, 10))])]
    paa = ["What is %s?" % kw, "How does %s work?" % kw, "Is %s worth it for a small team?" % kw,
           "How much does %s cost?" % kw, "What is the best alternative to %s?" % kw]
    return {"keyword": kw, "features": {"organic": len(top), "people_also_ask": 1, "ai_overview": 1,
                                        "related_searches": 1, "featured_snippet": 1},
            "top_organic": top,
            "featured_snippet": {"domain": hosts[0], "text": "%s is a way of working that teams adopt to get a measurable result." % kw.capitalize()},
            "paa": paa,
            "ai_overview": {"text": "%s refers to a set of practices. It covers what it is, how it works, "
                                    "what it costs and how to measure it." % kw.capitalize(),
                            "cites": hosts[:3]},
            "related_searches": ["%s examples" % kw, "%s template" % kw, "%s checklist" % kw, "best %s tools" % kw],
            "_demo": True}
