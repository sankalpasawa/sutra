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
import time

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


def get(path):
    """The same call, for the endpoints that only answer to GET (the queue's tasks_ready and
    task_get). Same credential, same 20000 discipline, same one place."""
    auth = _auth()
    if auth is None:
        raise NoCredentials(
            "DataForSEO is not connected. Add dataforseo_login and dataforseo_password "
            "in the Connections tab."
        )
    r = httpx.get(BASE + path, auth=auth, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
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
    max_rows is a loud safety ceiling, never a silent cap: a pull that stops on it comes back with
    a `capped` sentence saying so, which the caller prints and puts in the run's meta.
    """
    if demo_mode():
        return _demo_ranked_bulk(domain, limit)
    location_name, language_code = market(location_name, language_code)
    limit = max(1, _int(limit, 1000))
    rows, offset, total, cost = [], 0, None, 0.0
    partial = capped = None
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
        if offset >= max_rows and offset < (total or 0):
            # THE CEILING SAYS SO NOW (2026-09-10). This branch used to be folded into the break
            # below, so a pull that stopped because it hit max_rows returned exactly like a pull
            # that reached the end of the data: no note, nothing on screen. The docstring here and
            # the comment on foundation/settings.TRAFFIC_MAX_ROWS both promise "a loud safety
            # ceiling, never a silent cap", and neither was true — the site's whole tail was
            # dropped and the run reported a clean finish. The caller prints this sentence.
            capped = ("stopped at %d of %d rows: the %d-row safety ceiling was reached, so the rest "
                      "of this domain's keywords are not in the figures"
                      % (len(rows), total or 0, max_rows))
            break
        if offset >= total or not items:
            break
    out = {"rows": rows, "total_count": total or 0, "cost_usd": round(cost, 4)}
    if partial:
        out["partial"] = partial
    if capped:
        out["capped"] = capped
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


_PAY = {"at": 0.0, "ok": None}


def _can_pay(ttl=300.0):
    """Is there enough balance to be worth calling? Fails OPEN when the check itself errors,
    because the paid calls report their own failures loudly anyway."""
    import time as _t
    now = _t.time()
    if now - _PAY["at"] < ttl and _PAY["ok"] is not None:
        return _PAY["ok"]
    try:
        bal = balance()
        _PAY["ok"] = True if bal is None else bal >= BULK_PAGE_FLOOR
    except Exception:  # noqa: BLE001 — a broken balance check must not block a paid run
        _PAY["ok"] = True
    _PAY["at"] = now
    return _PAY["ok"]


def keyword_pool(seed, limit=200, location_name="United States", language_code="en"):
    """The TIGHT net for the research engine: phrases that contain the seed, ONE seed per call (the
    endpoint allows no more). The same endpoint as keyword_suggestions() above, kept apart because
    this one returns the original engine's pool row shape and the cost of the call.
    Returns {"rows": [{kw, vol, kd, comp, src}], "cost": float}."""
    if demo_mode():
        return {"rows": _demo_suggestions(seed, limit), "cost": 0.0, "demo": True}
    # The same can-pay guard serp_advanced got on 2026-09-04, on the two endpoints it was not put
    # on. Without it the three research calls disagreed: a balance that cannot pay made the SERP
    # step degrade to demo rows and this one crash on a refusal. One rule for all three.
    if not _can_pay():
        return {"rows": _demo_suggestions(seed, limit), "cost": 0.0, "demo": True,
                "skipped": "the DataForSEO balance is too low, so these keywords are demo data"}
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
    if not _can_pay():          # see keyword_pool: one can-pay rule across the three research calls
        return {"rows": _demo_overview(kws), "cost": 0.0, "demo": True,
                "skipped": "the DataForSEO balance is too low, so these numbers are demo data"}
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
    # A run that cannot pay must not fire the calls anyway. Found 2026-09-04: the research
    # conversation issues ~48 searches, and with the balance below zero every one of them would
    # have gone out to be refused. Checked once per process, not per call.
    if not _can_pay():
        return {"extract": _demo_serp_extract(keyword, depth), "cost": 0.0, "demo": True,
                "skipped": "the DataForSEO balance is too low, so these results are demo data"}
    task = {"keyword": keyword, "location_name": location_name, "language_code": language_code,
            "depth": _int(depth, 20)}
    if paa_click_depth:
        task["people_also_ask_click_depth"] = _int(paa_click_depth, 3)
    if ai_overview:
        task["load_async_ai_overview"] = True
    data = post("/serp/google/organic/live/advanced", [task])
    return {"extract": serp_extract(keyword, _items(data)), "cost": _cost(data)}


# ---- the queued SERP batch: many searches, a third of the price ---------------------------------
# TWO WAYS TO BUY A GOOGLE PAGE, AND THEY ARE NOT THE SAME PRICE. Both numbers below are his,
# measured, and written down twice in his own tree (04-write-phase/scripts/verify_sources.py's
# _dfs_batch_serp docstring and write-phase-architecture.md: "searches ~$0.002 live / $0.0006
# queued"). The live endpoint answers inside the reply and costs about three and a third times as
# much. The queue takes every query in one post, makes you wait, and is the right trade whenever
# the answers are all wanted at once and nothing is watching the clock — which is exactly the
# replacement-source hunt, where one article plans hundreds of queries in a single step.
SERP_LIVE_USD = 0.002        # /serp/google/organic/live/advanced, per search
SERP_QUEUED_USD = 0.0006     # task_post + task_get/regular, per search — about a third of live
#
# ...AND THE COLLECTION HAS TWO PRICES TOO. `task_get/advanced` silently costs about double
# `task_get/regular` (his measurement), and the hunt only ever reads organic urls off the result,
# which regular carries. So: post standard, collect REGULAR. Changing that one word here doubles
# the bill for data nobody reads.
BATCH_FETCH = "regular"
BATCH_POST_SIZE = 100        # tasks DataForSEO accepts in one task_post
BATCH_WAIT = 900             # seconds spent POLLING for results before falling back to the endgame
BATCH_POLL_GAP = 15          # seconds between polls of tasks_ready
BATCH_TRIES = 3              # re-poll a slow batch this many times. The tasks are already posted and
#                              PAID FOR, so waiting longer costs nothing at all.
BATCH_DRAIN_ROUNDS = 8       # rounds spent clearing a full ready-list before posting (see below)


def _batch_urls(data, depth):
    """The organic urls off one collected task, best first, or None when the task is NOT DONE.

    None and [] are different answers and the difference is the whole point. A task still in the
    queue answers task_get with a 200 and a top-level 20000, and its "in queue" verdict is one
    level down, on the task. Reading that as an empty result would record "this search found
    nothing" for a search that has not run yet — and a claim with no source is a claim that gets
    its source stripped, so a task read too early costs a real fact.
    """
    tasks = (data or {}).get("tasks") or []
    task = (tasks[0] if tasks else None) or {}
    if task.get("status_code") != 20000:
        return None                                  # in queue, or failed: come back for it
    result = task.get("result") or []
    items = ((result[0] if result else None) or {}).get("items") or []
    return [i.get("url") for i in items
            if isinstance(i, dict) and i.get("type") == "organic" and i.get("url")][:_int(depth, 10)]


def _drain_ready():
    """Clear the ready-list before posting.

    tasks_ready returns AT MOST 1000 entries. A run that dies mid-collection leaves its finished
    tasks on that list for good, and once 1000 have piled up a later run's tasks can never appear
    on it: the new run polls a permanently full list until it gives up. He hit this for real on
    2026-08-02 with 4,387 stale tasks banked. So the shelf is cleared first, and whatever is on it
    is collected whether it is ours or not.
    """
    for _ in range(BATCH_DRAIN_ROUNDS):
        try:
            r = get("/serp/google/organic/tasks_ready")
        except Exception:  # noqa: BLE001 — a drain that cannot run is not a reason to skip the batch
            return
        ids = [x.get("id") for x in ((( r.get("tasks") or [{}])[0] or {}).get("result") or [])
               if isinstance(x, dict) and x.get("id")]
        if not ids:
            return
        for t in ids:
            try:
                get("/serp/google/organic/task_get/%s/%s" % (BATCH_FETCH, t))
            except Exception:  # noqa: BLE001
                pass


def serp_batch(queries, location_name=None, language_code=None, depth=10, say=None):
    """Many organic searches through the STANDARD QUEUE, in one go.

    Returns {"urls": {query: [url]}, "cost": float, "missing": [query], "demo": bool}. A query in
    `missing` never came back; that is a search that did not happen, and the caller must treat it
    as "not searched", never as "nothing found".

    The flow is his, three fixes and all (see _drain_ready for the first):
      2. RESULTS ARE KEPT AS THEY ARRIVE, not at the end. He had one article fetch 945 results and
         report total failure because a wrapper timeout threw away everything already collected.
      3. THE DEADLINE GUARDS POLLING ONLY. Collecting hundreds of finished tasks used to run into
         the same clock as waiting for them, so the collection itself timed out; and an ENDGAME
         asks for whatever is left BY ID, which does not depend on the ready-list at all.
    And the retry above them: DataForSEO's queue can run slower than one BATCH_WAIT window, so a
    poor yield is re-polled rather than accepted. His old loop only retried on a MALFORMED reply, so
    a well-formed "nothing ready yet" read as the final answer — which is how one article had 745
    of 745 queries silently abandoned and 428 claims shipped unverified under a report reading
    "0 cut".
    """
    queries = [str(q).strip() for q in (queries or []) if str(q).strip()]
    queries = list(dict.fromkeys(queries))
    if not queries:
        return {"urls": {}, "cost": 0.0, "missing": [], "demo": False}
    if demo_mode():
        return {"urls": {q: [r["url"] for r in _demo_serp_extract(q, depth)["top_organic"]] for q in queries},
                "cost": 0.0, "missing": [], "demo": True}
    if not _can_pay():
        return {"urls": {}, "cost": 0.0, "missing": list(queries), "demo": True,
                "skipped": "the DataForSEO balance is too low, so no search was bought"}
    location_name, language_code = market(location_name, language_code)
    _drain_ready()

    got, cost, id2q = {}, 0.0, {}
    for i in range(0, len(queries), BATCH_POST_SIZE):
        chunk = queries[i:i + BATCH_POST_SIZE]
        tasks = [{"keyword": q, "location_name": location_name, "language_code": language_code,
                  "depth": _int(depth, 10)} for q in chunk]
        data = post("/serp/google/organic/task_post", tasks)
        cost += _cost(data)
        for t, q in zip((data.get("tasks") or []), chunk):
            if isinstance(t, dict) and t.get("id"):
                id2q[t["id"]] = q

    def collect(tid):
        q = id2q.get(tid)
        if q is None:
            return False
        try:
            data = get("/serp/google/organic/task_get/%s/%s" % (BATCH_FETCH, tid))
        except Exception:  # noqa: BLE001 — a hiccup: try again next round
            return False
        urls = _batch_urls(data, depth)
        if urls is None:                       # still in the queue: NOT an empty result
            return False
        got[q] = urls                          # kept the moment we have it, fix 2
        return True

    for attempt in range(BATCH_TRIES):
        deadline = time.time() + BATCH_WAIT
        while id2q and time.time() < deadline:           # fix 3: the deadline guards POLLING only
            time.sleep(BATCH_POLL_GAP)
            try:
                r = get("/serp/google/organic/tasks_ready")
            except Exception:  # noqa: BLE001
                continue
            ready = [x["id"] for x in (((r.get("tasks") or [{}])[0] or {}).get("result") or [])
                     if isinstance(x, dict) and x.get("id") in id2q]
            for tid in ready:
                if collect(tid):
                    id2q.pop(tid, None)
        for tid in list(id2q):                           # ENDGAME: by id, no ready-list involved
            if collect(tid):
                id2q.pop(tid, None)
        if not id2q:
            break
        if say and attempt < BATCH_TRIES - 1:
            say("Waiting on the search batch",
                "%d of %d searches are not back yet, so it is waiting again (try %d of %d). They are "
                "already paid for, so this costs nothing."
                % (len(id2q), len(queries), attempt + 2, BATCH_TRIES))

    missing = [q for q in queries if q not in got]
    if missing and say:
        say("Part of the search batch never came back",
            "%d of %d searches did not return after %d attempts. Those claims are left UNCHECKED, "
            "not deleted." % (len(missing), len(queries), BATCH_TRIES))
    return {"urls": got, "cost": round(cost, 6), "missing": missing, "demo": False}


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


# ---- the asset engine's calls -------------------------------------------------------------------
# Two named wrappers so assets/competitors.py stops reaching for dfs.post() and the private
# _items() unwrapper. The credential and the shape-untangling stay in this one file, which is the
# whole point of it. Both return the raw items, because the asset engine reads different fields out
# of each row than the research engine does, and the row shaping belongs with the reader.
#
# Neither one has a demo fallback and neither one calls _can_pay(). The asset engine runs its own
# pre-flight (assets/competitors.paid_route) before its first paid call, and a second floor here
# would be the same decision made in two places. Without credentials post() raises NoCredentials,
# which is right: an empty list would read as "this company has no competitors".

def competitors_domain(target, location_name=None, language_code=None, limit=100,
                       exclude_top_domains=True, item_types=("organic",)):
    """Domains that rank for the same keywords as target, most overlap first.

    Returns {"items": [raw rows], "cost": float}. Each row carries domain plus
    metrics.organic.{count, etv}. A candidate GENERATOR, never the answer: the overlap ranking
    puts general-interest sites near the top, so the caller still has to judge the list.
    """
    loc, lang = market(location_name, language_code)
    data = post("/dataforseo_labs/google/competitors_domain/live", [{
        "target": bare_domain(target), "location_name": loc, "language_code": lang,
        "limit": _int(limit, 100), "exclude_top_domains": bool(exclude_top_domains),
        "item_types": list(item_types or ["organic"])}])
    return {"items": _items(data), "cost": _cost(data)}


def domain_pages(target, limit=100, order_by=("page_summary.referring_domains,desc",)):
    """The pages on one domain that earn links, most referring domains first.

    Returns {"items": [raw rows], "cost": float}. The page address is in the row's `page` field on
    this endpoint, not `url`; reading `url` gives an empty column that looks like no data.
    """
    task = {"target": bare_domain(target), "limit": _int(limit, 100)}
    if order_by:
        task["order_by"] = list(order_by)
    data = post("/backlinks/domain_pages/live", [task])
    return {"items": _items(data), "cost": _cost(data)}


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
