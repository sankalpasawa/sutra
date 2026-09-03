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
DEFAULT_LOCATION = 2356      # India
DEFAULT_LANGUAGE = "en"

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

def ranked_keywords(domain, limit=100, location_code=DEFAULT_LOCATION,
                    language_code=DEFAULT_LANGUAGE):
    """What this domain already ranks for. Returns [{keyword, position, volume, url}]."""
    if demo_mode():
        return _demo_ranked(domain, limit)
    payload = [{
        "target": bare_domain(domain),
        "location_code": location_code,
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


def keyword_ideas(seed, limit=100, location_code=DEFAULT_LOCATION,
                  language_code=DEFAULT_LANGUAGE):
    """Keywords related to a seed. Returns [{keyword, volume, difficulty, cpc}]."""
    if demo_mode():
        return _demo_keywords(_seeds(seed), limit, related=True)
    payload = [{
        "keywords": _seeds(seed),
        "location_code": location_code,
        "language_code": language_code,
        "limit": _int(limit, 100),
    }]
    data = post("/dataforseo_labs/google/keyword_ideas/live", payload)
    return [_keyword_row(it) for it in _items(data) if (it or {}).get("keyword")]


def keyword_metrics(keywords, location_code=DEFAULT_LOCATION,
                    language_code=DEFAULT_LANGUAGE):
    """Volume, difficulty and cpc for keywords we already have. Same row shape as
    keyword_ideas, so the two can be mixed in one table."""
    seeds = _seeds(keywords)
    if not seeds:
        return []
    if demo_mode():
        return _demo_keywords(seeds, len(seeds), related=False)
    # Their overview endpoint caps at 700 keywords per call.
    payload = [{
        "keywords": seeds[:700],
        "location_code": location_code,
        "language_code": language_code,
    }]
    data = post("/dataforseo_labs/google/keyword_overview/live", payload)
    return [_keyword_row(it) for it in _items(data) if (it or {}).get("keyword")]


def serp(keyword, depth=10, location_code=DEFAULT_LOCATION,
         language_code=DEFAULT_LANGUAGE):
    """The live first page for one keyword.
    Returns {top_results: [{position, title, url, description}], people_also_ask: [str]}.
    """
    if demo_mode():
        return _demo_serp(keyword, depth)
    payload = [{
        "keyword": keyword,
        "location_code": location_code,
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
