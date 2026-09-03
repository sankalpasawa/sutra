"""Layer 3 — URLs the public web archive remembers, filtered hard, then liveness-checked.

Reads:  the Wayback CDX index for the domain (statuscode:200 + mimetype:text/html only, collapsed
        on urlkey — the raw index is full of junk), plus urls-wp.json / urls-sitemap.json to know
        what this run has already declared.
Writes: _work/urls-archive.json:
  { "urls": { <url>: {"alive": true, "final_url": ..., "liveness": "checked"|"declared-elsewhere"} },
    "dead": [...], "unchecked": [...], "checked": N, "cdx_rows": N, "error": null|"<why>" }

Rules:
- Historical sources tell you what EXISTED; only a live check tells you what EXISTS. An archive-only
  URL joins the union only after a HEAD against the live site says it answers now.
- Rate-limit the archive hard (ARCHIVE_MAX_PER_MIN ceiling; blocks double on repeat offence).
- `page` is the archive's PAGINATION API: a short page NEVER means the end. Ask how many pages
  exist (showNumPages) and read them all. Measured 2026-07-19: stopping on a short page returned
  1,415 of 13,616 rows — 90% of the archive silently missing.
- Keep only the company's own hosts (apex + www). Subdomain apps are not site pages.
- A URL the CMS or sitemap declared THIS run is a current declaration: it is not re-probed
  (9,663 of 11,518 candidates were already declared on one site, hours of probes for nothing).
- The agent caps live probes at ARCHIVE_LIVENESS_CAP. Anything beyond is recorded as UNCHECKED
  and does not join the union — reported, never pretended alive.
- Liveness verdicts persist in sqlite so a killed run resumes, not restarts.
"""
import json
import os
import time
import urllib.parse as _up
from concurrent.futures import ThreadPoolExecutor

import httpx

from .. import store
from . import settings
from .fetch import Blocked, RobotsDisallowed
from .urls import match_key, own_host

CDX = "https://web.archive.org/cdx/search/cdx"


def _declared_elsewhere(work):
    keys = set()
    for name in ("urls-wp.json", "urls-sitemap.json"):
        doc = store.read_json(os.path.join(work, name)) or {}
        for u in (doc.get("urls") or {}):
            keys.add(match_key(u))
    return keys


def _cdx_rows(fx, host, say):
    """EVERY page of the CDX index. The archive is an API here, not a crawl target — its
    published ceiling is the law; we stay far under it."""
    base = {"url": "%s/*" % host, "matchType": "domain",
            "filter": ["statuscode:200", "mimetype:text/html"]}
    r = fx.plain_get(CDX, params=dict(base, showNumPages="true"), timeout=settings.ARCHIVE_TIMEOUT)
    r.raise_for_status()
    n_pages = int((r.text or "").strip() or 1)
    rows = []
    for page in range(n_pages):
        params = dict(base, output="json", collapse="urlkey", fl="original",
                      limit=str(settings.ARCHIVE_PAGE_LIMIT), page=str(page))
        for _attempt in range(4):
            resp = fx.plain_get(CDX, params=params, timeout=settings.ARCHIVE_TIMEOUT)
            if resp.status_code == 429:
                say("The web archive asked us to slow down", "waiting %ds" % settings.ARCHIVE_429_SLEEP)
                time.sleep(settings.ARCHIVE_429_SLEEP)
                continue
            resp.raise_for_status()
            break
        else:
            raise RuntimeError("the web archive kept answering 429")
        data = resp.json() if resp.text.strip() else []
        if data and data[0] == ["original"]:
            data = data[1:]
        rows += [d[0] for d in data if d]
        if page + 1 < n_pages:
            time.sleep(60.0 / settings.ARCHIVE_MAX_PER_MIN)
    return rows, n_pages


def run(fx, site, say):
    host, root = site["host"], site["root"]
    out_path = os.path.join(site["work"], "urls-archive.json")
    try:
        raw, n_pages = _cdx_rows(fx, host, say)
    except (httpx.HTTPError, ValueError, RuntimeError) as e:
        # The archive being down must not end the index; it is one of four sources.
        doc = {"domain": host, "urls": {}, "dead": [], "unchecked": [], "checked": 0, "cdx_rows": 0,
               "error": "web archive unavailable: %s" % str(e)[:160]}
        store.write_json(out_path, doc)
        say("Could not reach the web archive", str(e)[:140])
        return doc
    say("Asked the web archive", "%d remembered pages across %d index page(s)" % (len(raw), n_pages))

    scheme = _up.urlsplit(root).scheme or "https"
    served_host = _up.urlsplit(root).netloc or host     # the host the site actually serves (www or apex)
    candidates = set()
    for u in raw:
        try:
            parts = _up.urlsplit(u)
        except ValueError:
            continue
        if parts.scheme not in ("http", "https") or not own_host(u, host):
            continue
        candidates.add(_up.urlunsplit((scheme, served_host, parts.path, parts.query, "")))

    declared = _declared_elsewhere(site["work"])
    known = {u: {"alive": bool(a), "status": s, "final_url": f} for u, a, s, f in
             fx.db("SELECT url, alive, status, final_url FROM archive_liveness", fetch="all")}
    todo = sorted(u for u in candidates if u not in known and match_key(u) not in declared)
    probe_now, unchecked = todo[:settings.ARCHIVE_LIVENESS_CAP], todo[settings.ARCHIVE_LIVENESS_CAP:]

    def record(u, alive, status, final_url):
        fx.db("INSERT OR REPLACE INTO archive_liveness(url, alive, status, final_url) VALUES(?,?,?,?)",
              (u, int(alive), status, final_url))

    def probe(u):
        """One liveness probe. Records its own verdict, so a failure here can never take down the
        sweep (one bad URL must never end the job)."""
        try:
            r = fx.head(u)
            if r.status_code == 405:                      # HEAD not allowed — ask properly
                r2 = fx.get(u)
                record(u, r2.status == 200, r2.status, r2.final_url)
                return
            record(u, r.status_code == 200, r.status_code, str(r.url))
        except RobotsDisallowed:
            record(u, False, -1, "")
        except Blocked as e:
            record(u, False, -3, str(e)[:200])
        except Exception as e:                            # FetchFailed, httpx errors
            record(u, False, -2, str(e)[:200])

    if probe_now:
        say("Checking which remembered pages still exist",
            "%d to check live%s" % (len(probe_now),
                                    (", %d more left unchecked (cap %d)" % (len(unchecked), settings.ARCHIVE_LIVENESS_CAP))
                                    if unchecked else ""))
        with ThreadPoolExecutor(max_workers=settings.LIVENESS_WORKERS) as ex:
            for i, _ in enumerate(ex.map(probe, probe_now), 1):
                if i % 100 == 0:
                    say("Still checking remembered pages", "%d of %d" % (i, len(probe_now)))

    known = {u: {"alive": bool(a), "status": s, "final_url": f} for u, a, s, f in
             fx.db("SELECT url, alive, status, final_url FROM archive_liveness", fetch="all")}
    urls, dead, assumed = {}, [], 0
    unchecked_set = set(unchecked)
    for u in sorted(candidates):
        if match_key(u) in declared:
            # Deliberately NOT liveness-checked: another layer declared it this run. It stays in
            # the archive set so provenance (and the archive-only set difference) remains exact.
            urls[u] = {"alive": True, "final_url": "", "liveness": "declared-elsewhere"}
            assumed += 1
            continue
        if u in unchecked_set:
            continue
        k = known.get(u)
        if k and k["alive"]:
            urls[u] = {"alive": True, "final_url": k["final_url"], "liveness": "checked"}
        else:
            dead.append(u)
    doc = {"domain": host, "urls": urls, "dead": dead, "unchecked": unchecked,
           "checked": len(candidates) - len(unchecked), "cdx_rows": len(raw),
           "liveness_skipped_declared": assumed, "error": None}
    store.write_json(out_path, doc)
    say("The web archive's view", "%d still live (%d already known from the site, %d verified), %d gone%s"
        % (len(urls), assumed, len(urls) - assumed, len(dead),
           (", %d not checked" % len(unchecked)) if unchecked else ""))
    return doc
