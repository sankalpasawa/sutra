"""Union + provenance + URL normalisation + canonical collapse + soft-404 detection.

Reads:  urls-wp.json, urls-sitemap.json, urls-archive.json, urls-crawl.json — then the live
        site ONCE per surviving URL (rate-limited, through fetch's cache, resumable via the
        frontier). extract.py later re-parses the same cached HTML offline, fetching nothing.
Writes: _work/reconciled.json:
  { "pages":   { <stored_url>: {sources, aliases, type, title, description, modified,
                                rest_chars, api_page, status, final_url, canonical_declared,
                                canonical_state, match_key} },
    "dropped": {"dead": [...], "soft_404": [...], "collapsed": {alias: target},
                "offsite": [...], "robots": [...], "non_content": [...], "unread": [...]},
    "fan_in":  { <target>: n_aliases },   # anomalies — flagged, NOT collapsed
    "fetch":   {"site_blocked": null|"<why>", "circuit_broken": bool, "page_blocked": n},
    "stats":   {...} }

Rules (each one earned by a measured incident):
- UNION of independent sources; `sources` per URL is kept — the set differences are findings.
- The STORED url is minimally normalised; the MATCH KEY is aggressive (tracking-param blocklist,
  not an allowlist — an allowlist once deleted real permalinks). Two fields, never conflated.
- The CMS's own permalink wins the stored form over later layers'; the rest become aliases.
- canonical_declared is stored verbatim; the RESOLVED state lives in canonical_state. A
  declaration is a hint, never a directive — overwriting it hides that it was wrong.
- Chains (redirects + canonicals) resolve with a hop cap and a visited-set; a loop or a cap
  is UNRESOLVED, surfaced, never guessed.
- Fan-in: a target absorbing > FAN_IN_ALERT aliases is a bug signature (homepage canonical,
  soft-404 template, staging leak) — flagged and NOT collapsed, so no data is destroyed.
- Soft 404s are detected by CONTENT SIGNATURE (identical small bodies across many URLs,
  not-found phrasing), never by status code.
- A single page answering 403 while the homepage still serves is a PAGE fact (recorded);
  403 with the homepage also refusing is a SITE block (the fetch pass stops, loudly).
- max_pages is honoured honestly: URLs beyond it are recorded as `unread`, never dropped silently.
"""
import hashlib
import os
import re
import threading
import urllib.parse as _up
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from .. import store
from . import settings
from .fetch import Blocked, RobotsDisallowed
from .urls import is_non_content, match_key, own_host, store_norm

_NOT_FOUND_RE = re.compile(r"\b(page not found|404|nothing (was )?found|doesn.t exist)\b", re.I)
PREFER = {"wp": 0, "sitemap": 1, "archive": 2, "crawl": 3}


class SiteRefused(Exception):
    """The site blocked the fetch pass before a single page was read. index_site falls back."""


def _load(work, name):
    return store.read_json(os.path.join(work, name)) or {"urls": {}}


def head_canonical(soup):
    """rel=canonical honoured the way a browser does: only from inside a real <head>."""
    for el in soup.find_all("link", rel=True):
        rels = el.get("rel") or []
        rels = [r.lower() for r in (rels if isinstance(rels, list) else str(rels).split())]
        if "canonical" not in rels:
            continue
        if el.find_parent("head") is not None:
            return (el.get("href") or "").strip()
    return ""


def link_header_canonical(headers):
    for part in (headers.get("link", "") or "").split(","):
        if 'rel="canonical"' in part.lower() or "rel=canonical" in part.lower():
            m = re.search(r"<([^>]+)>", part)
            if m:
                return m.group(1).strip()
    return ""


def _union(layers):
    groups = {}                                     # match_key -> record
    for src in ("wp", "sitemap", "archive", "crawl"):
        for raw, meta in (layers[src].get("urls") or {}).items():
            stored = store_norm(raw)
            key = match_key(stored)
            rec = groups.setdefault(key, {
                "url": stored, "url_src": src, "sources": set(), "aliases": set(),
                "type": "", "title": "", "description": "", "modified": "",
                "rest_chars": 0, "api_page": "", "match_key": key,
            })
            rec["sources"].add(src)
            if stored != rec["url"]:
                # keep ONE stored form; prefer the CMS's own permalink over later layers' forms
                if PREFER[src] < PREFER[rec["url_src"]]:
                    rec["aliases"].add(rec["url"])
                    rec["url"], rec["url_src"] = stored, src
                else:
                    rec["aliases"].add(stored)
            meta = meta or {}
            if src == "wp":
                rec.update(type=meta.get("type", ""), title=meta.get("title", ""),
                           description=meta.get("description", ""),
                           modified=meta.get("modified", ""),
                           rest_chars=meta.get("rest_chars", 0),
                           api_page=meta.get("api_page", ""))
            elif src == "sitemap" and not rec["modified"]:
                rec["modified"] = meta.get("lastmod", "")
    return {rec["url"]: rec for rec in groups.values()}


def _fetch_pass(fx, site, pages, say):
    """Make sure every page is in the raw cache (resumable). Returns the fetch verdicts."""
    urls = sorted(pages.keys())
    fx.frontier_add(urls)
    fx.frontier_retry_failed(urls)
    verdict = {"site_blocked": None, "circuit_broken": False, "page_blocked": 0}
    shared = {"fail_streak": 0, "done": 0, "ok": 0, "stop": False}
    guard = threading.Lock()
    root = site["root"] + "/"

    def worker():
        while not shared["stop"]:
            url = fx.frontier_claim()
            if url is None:
                return                         # queue drained
            failed = False
            try:
                r = fx.get(url)
                failed = r.status == 0 or r.status >= 500
                if failed:
                    fx.frontier_fail(url, "fetch failed (HTTP %d)" % r.status)
                else:
                    fx.frontier_done(url)
            except RobotsDisallowed:
                fx.frontier_fail(url, "robots")
            except Blocked as e:
                # page-level 403 or site-wide block? The homepage decides.
                try:
                    site_ok = fx.get(root, force=True).status == 200
                except Exception:
                    site_ok = False
                if not site_ok:
                    with guard:
                        verdict["site_blocked"] = "site-wide block while fetching %s: %s" % (url, str(e)[:160])
                        shared["stop"] = True
                    fx.frontier_fail(url, "blocked (site-wide)")
                    return
                fx.frontier_fail(url, "403 (page-level)")
                with guard:
                    verdict["page_blocked"] += 1
            except Exception as e:             # a worker must never die quietly
                fx.frontier_fail(url, "error: %s" % str(e)[:200])
                failed = True
            with guard:
                # "in a row" across workers: any success clears the streak, so this still means
                # "a WAVE of failures", never an accumulation of scattered bad pages.
                shared["fail_streak"] = shared["fail_streak"] + 1 if failed else 0
                shared["done"] += 1
                if not failed:
                    shared["ok"] += 1
                if shared["done"] % 100 == 0:
                    say("Still reading pages", "%d of %d fetched" % (shared["done"], len(urls)))
                if shared["fail_streak"] >= settings.CIRCUIT_BREAK:
                    verdict["circuit_broken"] = True
                    shared["stop"] = True
                    return

    n_workers = max(1, settings.FETCH_WORKERS)
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        for f in [ex.submit(worker) for _ in range(n_workers)]:
            f.result()
    if verdict["circuit_broken"]:
        say("Stopped reading pages", "%d pages failed in a row — the site is down or throttling us; "
            "what was read so far is kept and the rest is recorded as unread" % settings.CIRCUIT_BREAK)
    if verdict["site_blocked"]:
        say("The site blocked the reading pass", verdict["site_blocked"][:160])
    return verdict


def run(fx, site, say):
    work = site["work"]
    layers = {"wp": _load(work, "urls-wp.json"), "sitemap": _load(work, "urls-sitemap.json"),
              "archive": _load(work, "urls-archive.json"), "crawl": _load(work, "urls-crawl.json")}

    # 1) union with provenance, grouped by the match key ---------------------------------------
    pages = _union(layers)
    non_content = [u for u in pages if is_non_content(u)]
    for u in non_content:
        del pages[u]
    found = len(pages)

    # honour max_pages: keep the CMS's pages first, then sitemap, archive, crawl; record the rest
    unread = []
    cap = int(site.get("max_pages") or 0)
    if cap and len(pages) > cap:
        order = sorted(pages, key=lambda u: (min(PREFER[s] for s in pages[u]["sources"]), u))
        unread = order[cap:]
        for u in unread:
            del pages[u]
        say("Capped the read", "%d pages found, reading the first %d (max_pages)" % (found, cap))

    stats = {"union": found, "found": found, "read": len(pages)}
    for src in layers:
        stats[src] = sum(1 for r in pages.values() if src in r["sources"])
    stats["wp_only"] = sum(1 for r in pages.values() if r["sources"] == {"wp"})
    stats["sitemap_only"] = sum(1 for r in pages.values() if r["sources"] == {"sitemap"})
    stats["archive_only"] = sum(1 for r in pages.values() if r["sources"] == {"archive"})
    say("Combined the four sources", "%d distinct pages (site list %d, sitemaps %d, archive %d, crawl %d)"
        % (len(pages), stats["wp"], stats["sitemap"], stats["archive"], stats["crawl"]))

    # 2) the network pass — every page into the raw cache ----------------------------------------
    say("Reading every page once", "%d pages, %d at a time, at most %.1f requests a second"
        % (len(pages), settings.FETCH_WORKERS, settings.RATE_RPS))
    verdict = _fetch_pass(fx, site, pages, say)

    # 3) offline parse of the cached payloads ----------------------------------------------------
    dropped = {"dead": [], "soft_404": [], "collapsed": {}, "offsite": [], "robots": [],
               "non_content": non_content, "unread": unread}
    body_sig = {}                                   # sha -> [urls] for soft-404 clustering
    states = fx.frontier_states(pages.keys())
    any_read = False
    for url, rec in list(pages.items()):
        st, err = states.get(url, ("", ""))
        r = fx.cached(url)
        if r is None:
            if err == "robots":
                dropped["robots"].append(url)
                del pages[url]
                continue
            # keep the page (it exists) but record it couldn't be read this run; honest status
            rec.update(status=(403 if "403" in err else 0), final_url=url, canonical_declared="",
                       text_words=0, fetch_error=err)
            continue
        rec["status"] = r.status
        rec["final_url"] = r.final_url
        rec["canonical_declared"] = ""
        rec["text_words"] = 0
        if r.status in (404, 410):
            dropped["dead"].append(url)
            del pages[url]
            continue
        if not own_host(r.final_url, site["host"]):
            dropped["offsite"].append(url)
            del pages[url]
            continue
        if r.status == 200 and "html" in (r.content_type or "").lower() and r.content:
            any_read = True
            try:
                soup = BeautifulSoup(r.content, "html.parser")
            except Exception:
                continue
            canon = head_canonical(soup) or link_header_canonical(r.headers)
            if canon:
                rec["canonical_declared"] = store_norm(_up.urljoin(r.final_url, canon))
            text = " ".join(soup.get_text(" ").split())
            rec["text_words"] = len(text.split())
            if not rec["title"]:
                rec["title"] = soup.title.get_text(strip=True) if soup.title else ""
            # Signature EVERY page, not just small ones. Byte-identical bodies are a fact, and
            # what they mean depends only on size (see step 4).
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            body_sig.setdefault(sha, []).append(url)

    if verdict["site_blocked"] and not any_read:
        raise SiteRefused(verdict["site_blocked"])

    # 4) identical bodies: the same text served at many URLs -------------------------------------
    #   small + repeated -> a soft 404 / empty template. Drop them; they are not pages.
    #   large + repeated -> ONE real page reachable at many addresses. Keep ONE, the rest are ALIASES.
    # Measured 2026-07-19: a homepage appeared as 143 separate rows on one site, and 5,878 of
    # 6,363 rows (92%) on another were duplicates. Repetition is evidence at any size.
    for sha, cluster in body_sig.items():
        live = [u for u in cluster if u in pages]
        if len(live) < 2:
            continue
        words = pages[live[0]].get("text_words", 0)
        phrased = any(_NOT_FOUND_RE.search(pages[u].get("title", "")) for u in live)
        if words <= settings.SOFT404_MAX_WORDS and (len(live) >= settings.SOFT404_MIN_CLUSTER or phrased):
            for u in live:                                  # small + repeated = not a page at all
                dropped["soft_404"].append(u)
                del pages[u]
            continue
        if words > settings.SOFT404_MAX_WORDS:
            # the shortest URL with no query string wins (the canonical-looking one); ties alphabetical
            keeper = sorted(live, key=lambda u: (bool(_up.urlsplit(u).query), len(u), u))[0]
            for u in live:
                if u == keeper:
                    continue
                pages[keeper]["aliases"].add(u)
                dropped["collapsed"][u] = keeper
                del pages[u]

    # 5) canonical + redirect collapse (hop cap, loops -> UNRESOLVED, fan-in flagged) ------------
    def next_hop(u):
        rec = pages.get(u)
        if not rec:
            return None
        fin = store_norm(rec.get("final_url") or u)
        if fin != u and match_key(fin) != rec["match_key"] and fin in pages:
            return fin                              # a real redirect to another catalogued page
        canon = rec.get("canonical_declared") or ""
        if canon and match_key(canon) != rec["match_key"] and canon in pages:
            return canon
        return None

    fan_in = {}
    for url in list(pages.keys()):
        if url not in pages:
            continue
        seen, cur = [url], url
        while True:
            nxt = next_hop(cur)
            if nxt is None:
                target = cur
                break
            if nxt in seen or len(seen) > settings.CANONICAL_HOP_CAP:
                target = None                       # loop or cap — UNRESOLVED
                break
            seen.append(nxt)
            cur = nxt
        if target is None:
            pages[url]["canonical_state"] = "unresolved"
        elif target == url:
            pages[url]["canonical_state"] = "self"
        else:
            fan_in[target] = fan_in.get(target, 0) + 1
            pages[url]["canonical_state"] = "alias_of:" + target

    flagged = {t: n for t, n in fan_in.items() if n > settings.FAN_IN_ALERT}
    for url, rec in list(pages.items()):
        st = rec.get("canonical_state", "self")
        if st.startswith("alias_of:"):
            target = st.split(":", 1)[1]
            if target in flagged:
                rec["canonical_state"] = "fan_in_suspect:" + target   # flagged, NOT collapsed
                continue
            tgt = pages.get(target)
            if tgt:
                tgt["aliases"] = set(tgt["aliases"]) | {url} | set(rec["aliases"])
                tgt["sources"] = set(tgt["sources"]) | set(rec["sources"])
                for f in ("type", "title", "description", "modified", "api_page"):
                    if not tgt.get(f):
                        tgt[f] = rec.get(f, "")
                if not tgt.get("rest_chars"):
                    tgt["rest_chars"] = rec.get("rest_chars", 0)
                dropped["collapsed"][url] = target
                del pages[url]

    # 6) type inference for non-CMS pages: majority type per first path segment ------------------
    seg_type = {}
    for url, rec in pages.items():
        if rec.get("type"):
            seg = _up.urlsplit(url).path.strip("/").split("/", 1)[0]
            seg_type.setdefault(seg, {}).setdefault(rec["type"], 0)
            seg_type[seg][rec["type"]] += 1
    for url, rec in pages.items():
        if not rec.get("type"):
            path = _up.urlsplit(url).path.strip("/")
            seg = path.split("/", 1)[0]
            votes = seg_type.get(seg)
            if votes:
                rec["type"] = max(votes, key=votes.get)
            else:
                rec["type"] = seg if seg and "/" in path else "pages"

    for rec in pages.values():                       # json-serialisable
        rec["sources"] = sorted(rec["sources"])
        rec["aliases"] = sorted(rec["aliases"])
        rec.setdefault("canonical_state", "self")
        rec.pop("url_src", None)

    stats.update(final=len(pages), dead=len(dropped["dead"]), soft_404=len(dropped["soft_404"]),
                 collapsed=len(dropped["collapsed"]), offsite=len(dropped["offsite"]),
                 robots=len(dropped["robots"]), non_content=len(non_content), unread=len(unread),
                 fan_in_flagged=len(flagged))
    doc = {"domain": site["host"], "pages": {u: pages[u] for u in sorted(pages)},
           "dropped": dropped, "fan_in": flagged, "fetch": verdict, "stats": stats,
           "capped_at": cap or None}   # the cap this file was actually built under, for the gate
    store.write_json(os.path.join(work, "reconciled.json"), doc)
    say("Settled the page list", "%d real pages; dropped %d gone, %d empty templates, %d duplicate addresses, %d off-site"
        % (stats["final"], stats["dead"], stats["soft_404"], stats["collapsed"], stats["offsite"]))
    return doc
