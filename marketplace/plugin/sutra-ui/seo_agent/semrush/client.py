"""client.py — one client, one credential, one place the Semrush shape gets untangled.

The credential is store.connections()["semrush_key"] (Connections tab, same as every
other provider key in this app), with SEMRUSH_API_KEY as an env override -- env wins
when set. The override exists because this ships in a Mac app launched from the Dock,
where a shell env var never arrives; it matters for anyone who runs sync.py/run_sync.py
from a terminal or launchd job instead. Every call retries the same temporary errors
the same way, and DEMO_MODE turns itself on with no credentials so the dashboard is
demoable end to end without a Semrush account. Every demo row carries "_demo": True.

TWO DIFFERENT WIRE SHAPES, because Semrush itself has two APIs bolted together:
  * the CLASSIC report endpoints (url_organic, domain_organic, backlinks_*) answer
    at GET https://api.semrush.com/ with a `type` query param, and the body is
    semicolon-delimited text, not JSON -- a CSV export format from the product's
    original API, still current. `_report()` parses it.
  * the PROJECTS / Position Tracking endpoints are a REST JSON API under
    https://api.semrush.com/management/v1/ (setup) and
    https://api.semrush.com/reports/v1/ (reading tracked data). `_pt_get`/`_pt_post`
    handle those.

VERIFY BEFORE SPENDING A UNIT ON THIS. The exact export_columns names and the
Position Tracking payload shape below are transcribed from developer.semrush.com as
read during this integration's design (2026-09). Semrush does not version this API
the way a REST API usually is versioned, and one export_columns typo returns an
empty column, not an error. The demo path below never depends on any of this being
exactly right; the first real call should be checked by hand against one known
article before the daily sync is trusted.
"""
import os
import time

import httpx

from .. import store

REPORT_BASE = "https://api.semrush.com/"
PT_MANAGEMENT_BASE = "https://api.semrush.com/management/v1"
PT_REPORTS_BASE = "https://api.semrush.com/reports/v1"
TIMEOUT = 60.0

DEFAULT_DATABASE = "us"           # Semrush's regional database code, not a language code


class NoCredentials(Exception):
    pass


class SemrushError(Exception):
    pass


# ---- credentials ------------------------------------------------------------------------

def _key():
    env = os.environ.get("SEMRUSH_API_KEY", "").strip()
    if env:
        return env
    return (store.connections().get("semrush_key") or "").strip()


def available():
    return bool(_key())


DEMO_MODE = False


def demo_mode():
    """Resolved live, not frozen at import -- a key pasted into Connections mid-session
    takes effect on the next call, same contract as dfs.demo_mode()."""
    return DEMO_MODE or not available()


# ---- retry -----------------------------------------------------------------------------
# Semrush's classic endpoint answers errors IN THE BODY as a line starting "ERROR ",
# with an HTTP 200 -- the same "the transport succeeded, the call did not" trap dfs.py
# guards against. Only network-level and 5xx failures are retried; a real refusal
# (bad key, no units, bad params) is never retried because it will say the same thing
# again.
RETRY_SLEEPS = (5, 15, 40)


def _retry_request(fn):
    attempts = 1 + len(RETRY_SLEEPS)
    for attempt in range(attempts):
        last = attempt + 1 >= attempts
        try:
            r = fn()
            if r.status_code >= 500 and not last:
                time.sleep(RETRY_SLEEPS[attempt])
                continue
            r.raise_for_status()
            return r
        except (httpx.TimeoutException, httpx.TransportError):
            if last:
                raise
            time.sleep(RETRY_SLEEPS[attempt])


# ---- the classic report endpoint (CSV body) --------------------------------------------

def _report(report_type, params, columns):
    """One classic-API report call. Returns a list of dicts, one per row.

    `columns` is the export_columns string sent AND the header this parses the
    reply against -- the two must name the same fields in the same order, which is
    why every caller below builds them together rather than passing columns twice.
    """
    key = _key()
    if not key:
        raise NoCredentials("Semrush is not connected. Add semrush_key in the Connections tab.")
    query = dict(params)
    query.update({"key": key, "type": report_type, "export_columns": columns,
                  "export_escape": "1", "export_decode": "1"})
    r = _retry_request(lambda: httpx.get(REPORT_BASE, params=query, timeout=TIMEOUT))
    text = r.text or ""
    if text.startswith("ERROR"):
        raise SemrushError(text.strip()[:300])
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = lines[0].split(";")
    out = []
    for ln in lines[1:]:
        cells = ln.split(";")
        out.append({header[i]: cells[i] if i < len(cells) else "" for i in range(len(header))})
    return out


# ---- the Projects / Position Tracking JSON endpoints -----------------------------------

def _pt_request(method, base, path, params=None, json_body=None):
    key = _key()
    if not key:
        raise NoCredentials("Semrush is not connected. Add semrush_key in the Connections tab.")
    headers = {"Authorization": "Apikey " + key}
    url = base + path

    def call():
        if method == "get":
            return httpx.get(url, params=params or {}, headers=headers, timeout=TIMEOUT)
        if method == "put":
            return httpx.put(url, params=params or {}, json=json_body, headers=headers, timeout=TIMEOUT)
        return httpx.post(url, params=params or {}, json=json_body, headers=headers, timeout=TIMEOUT)

    r = _retry_request(call)
    if not r.content:
        return {}
    try:
        return r.json()
    except ValueError:
        raise SemrushError(("Semrush returned a non-JSON reply: %s" % r.text[:200]))


def _int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _float(v, default=0.0):
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return default


def bare_url(url):
    return (url or "").strip()


# ---- 1. url_organic: what a specific blog URL ranks for, right now --------------------
# Columns per developer.semrush.com/api/v3/analytics/url-reports/ (Ph, Po, Nq, Cp, Kd, Tr):
# keyword, position, search volume, cpc, keyword difficulty, traffic %.

_URL_ORGANIC_COLS = "Ph,Po,Nq,Cp,Kd,Tr"


def url_organic(url, database=DEFAULT_DATABASE, limit=20):
    """Organic keywords ranking THIS url right now, best position first -- display_sort=po_asc
    so a capped limit still gives an exact Top3/Top10/Top20 count (see sync.weekly()'s
    aggregation): with the rows sorted by position, nothing better-ranked is ever left outside
    the cap. Returns [{keyword, position, volume, cpc, difficulty, traffic_share}].

    limit defaults to 20, not Semrush's own cap -- url_organic bills 10 units PER RETURNED ROW
    (not per call), so this number is the main lever on cost. Raise it only with the cost
    math redone (see the integration's cost estimate)."""
    if demo_mode():
        return _demo_url_organic(url, limit)
    rows = _report("url_organic", {"url": bare_url(url), "database": database,
                                    "display_limit": _int(limit, 20),
                                    "display_sort": "po_asc"}, _URL_ORGANIC_COLS)
    out = []
    for row in rows:
        kw = row.get("Ph")
        if not kw:
            continue
        out.append({"keyword": kw, "position": _int(row.get("Po")), "volume": _int(row.get("Nq")),
                    "cpc": _float(row.get("Cp")), "difficulty": _float(row.get("Kd")),
                    "traffic_share": _float(row.get("Tr"))})
    return out


# ---- 2. backlinks for one URL ----------------------------------------------------------
# backlinks_overview accepts target_type=url. Columns: total backlinks, referring domains.

_BACKLINKS_COLS = "total,domains_num"


def backlinks_for_url(url, limit=1):
    """{backlinks, referring_domains} for one blog URL."""
    if demo_mode():
        return _demo_backlinks(url)
    rows = _report("backlinks_overview", {"target": bare_url(url), "target_type": "url"},
                    _BACKLINKS_COLS)
    if not rows:
        return {"backlinks": 0, "referring_domains": 0}
    row = rows[0]
    return {"backlinks": _int(row.get("total")), "referring_domains": _int(row.get("domains_num"))}


# ---- 3. Position Tracking: the scheduled, campaign-based rollup by landing page -------
# Keyword-first: a campaign tracks a KEYWORD LIST, and Semrush determines which URL on
# the domain ranks for each one. The "organic landing pages" report rolls that up by
# URL. See the module docstring: verify this shape against your own account before
# trusting the daily numbers.

def pt_create_campaign(domain, name, database=DEFAULT_DATABASE):
    if demo_mode():
        return {"project_id": "demo-project", "_demo": True}
    return _pt_request("post", PT_MANAGEMENT_BASE, "/projects",
                        json_body={"domain": bare_url(domain), "name": name})


def pt_enable_tracking(project_id, database=DEFAULT_DATABASE, device="desktop"):
    if demo_mode():
        return {"ok": True, "_demo": True}
    return _pt_request("post", PT_MANAGEMENT_BASE,
                        "/projects/%s/tracking/enable" % project_id,
                        json_body={"database": database, "device": device})


def pt_set_keywords(project_id, keywords):
    """The keyword LIST for the campaign. Additive on Semrush's side per their docs;
    callers should pass the full desired set, not a delta, since this module does not
    track what was sent last time."""
    if demo_mode():
        return {"ok": True, "count": len(keywords), "_demo": True}
    return _pt_request("put", PT_MANAGEMENT_BASE, "/projects/%s/keywords" % project_id,
                        json_body={"keywords": list(keywords)})


def pt_landing_pages(project_id, date=None):
    """One row per landing page the campaign's tracked keywords resolve to.

    Returns [{url, keywords_count, average_position, top3, top10, top20,
    estimated_traffic, visibility}]. `date` is YYYY-MM-DD; None means latest.
    """
    if demo_mode():
        return _demo_landing_pages(project_id)
    params = {}
    if date:
        params["date"] = date
    data = _pt_request("get", PT_REPORTS_BASE, "/projects/%s/tracking/landing_pages" % project_id,
                        params=params)
    rows = data.get("data") if isinstance(data, dict) else data
    out = []
    for row in rows or []:
        row = row or {}
        out.append({
            "url": row.get("url") or row.get("landing_page") or "",
            "keywords_count": _int(row.get("keywords_count") or row.get("kw_count")),
            "average_position": _float(row.get("avg_position") or row.get("position")),
            "top3": _int(row.get("top3")), "top10": _int(row.get("top10")),
            "top20": _int(row.get("top20")),
            "estimated_traffic": _int(row.get("traffic") or row.get("estimated_traffic")),
            "visibility": _float(row.get("visibility")),
        })
    return out


# ---- demo data --------------------------------------------------------------------------
# Stable, not random: md5 of the input, so a demo run is reproducible and screenshots match.

import hashlib


def _spread(text, low, high):
    h = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
    return low + (h % max(1, (high - low + 1)))


_DEMO_MODIFIERS = ["{s}", "best {s}", "{s} guide", "{s} examples", "how to {s}",
                   "{s} vs alternatives", "{s} checklist", "{s} pricing"]


def _demo_url_organic(url, limit):
    stem = (url or "blog").rstrip("/").rsplit("/", 1)[-1].replace("-", " ") or "seo"
    rows = []
    for i, m in enumerate(_DEMO_MODIFIERS[:_int(limit, 100)]):
        kw = m.format(s=stem)
        rows.append({"keyword": kw, "position": _spread(url + kw, 1, 45),
                    "volume": _spread(kw + url, 20, 4000), "cpc": 0.0,
                    "difficulty": float(_spread("d" + kw, 10, 80)),
                    "traffic_share": round(_spread("t" + kw, 1, 900) / 100.0, 2), "_demo": True})
    return rows


def _demo_backlinks(url):
    return {"backlinks": _spread(url, 0, 40), "referring_domains": _spread("d" + url, 0, 15),
            "_demo": True}


def _demo_landing_pages(project_id):
    return [{"url": "https://testlify.com/blog/demo-post", "keywords_count": 6,
             "average_position": 14.2, "top3": 1, "top10": 2, "top20": 4,
             "estimated_traffic": 320, "visibility": 0.42, "_demo": True}]
