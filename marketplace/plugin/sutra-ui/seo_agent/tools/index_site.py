"""index_site.py — catalogue the whole site once, so nothing after this has to guess.

Every later tool asks the same questions: what pages exist, what is each one about, how long is
it, and does it already rank. Answering that per tool would mean crawling the site four times and
getting four slightly different answers. So it happens once, here, and lands in knowledge.

This is the site-catalogue engine (workflows/00-foundation/1-site-catalogue) ported to the agent.
The stages live in seo_agent/foundation/, one module each; this file sequences them:

  1. ENUMERATE from four sources, unioned with provenance — the CMS's own list (WordPress REST,
     types derived at runtime, counts asserted), every sitemap, the web archive (liveness-checked),
     and a link crawl only when the other three are thin.
  2. RECONCILE — drop machine paths, group by match key, fetch every page once through a raw
     cache (polite: per-host rate, cooldowns on firewall pushback), drop dead pages and soft 404s,
     collapse redirect and canonical aliases (never a fan-in suspect), infer types.
  3. EXTRACT offline from the cache — the CMS body when it is a fair share of the page, else the
     visible DOM text with h1/h2/h3 kept inline as #/##/###; then remove site chrome by repetition.
  4. TRAFFIC — one bulk DataForSEO pull, cached so it never repeats by accident, raw and cleaned
     figures per page, joined by match key.
  5. GATES — enumeration accounting, response integrity, extraction coverage, the traffic
     cross-check. A failed gate is REPORTED in the tool's note, never raised.
  6. WRITE — site_index.json, content-database.jsonl, top-pages.json, catalogue-report.json,
     brand/company.json.

The one rule that governs everything: ask the site, never assume the site — and no silent
shortfall. Every list is derived at runtime; every count is checked against an authority the source
itself publishes; anything that cannot be verified is reported as lower confidence, never claimed.

Resume: every stage's output under knowledge/_work/ is its done-marker; a re-run reuses it unless
redo=True. The raw HTML cache is kept even then, and the paid traffic pull only repeats with
redo_traffic=True.

When the site refuses every fetch (a bot wall answering 403/429 to the homepage itself), the index
is built from what the domain ranks for instead: URLs, titles and keywords, no page text. The
summary says so, so the agent can tell the user.
"""
import os
import re
import urllib.parse as _up

from .. import store
from . import _shared as sh
from . import dfs
from ..foundation import settings
from ..foundation import fetch as fetchmod
from ..foundation import (enumerate_archive, enumerate_crawl, enumerate_sitemap, enumerate_wp,
                          extract, gates, reconcile, traffic)
from ..foundation.urls import bare_host, host_of, store_norm

UA = settings.UA             # the browser-like identity, kept here by name for anything that reads it


def _roots(domain):
    """Candidate roots to try, in order. A bare domain gets https first and http as a
    fallback, because a handful of sites still serve plain http and failing the whole
    setup over a scheme is not a real failure."""
    d = (domain or "").strip().rstrip("/")
    if not d:
        raise ValueError("index_site needs a domain, for example example.com")
    if d.startswith(("http://", "https://")):
        return [d]
    return ["https://" + d, "http://" + d]


def _discover(fx, roots, max_pages):
    """Open the homepage and settle the root the site actually serves (scheme and host after its
    own redirects). Raises RuntimeError when every root refuses — that is the "site refuses the
    crawl" signal the fallback keys off."""
    last = None
    for root in roots:
        try:
            r = fx.get(root + "/")
        except fetchmod.Blocked as e:
            last = str(e)[:160]
            continue
        except fetchmod.RobotsDisallowed:
            last = "robots.txt disallows the homepage"
            continue
        if r.status == 200:
            final = r.final_url or root + "/"
            p = _up.urlsplit(final)
            return "%s://%s" % (p.scheme or "https", p.netloc or host_of(root))
        last = ("HTTP %d" % r.status) if r.status else (r.headers.get("_fetch_error") or "no response")
    raise RuntimeError("Could not read %s: %s" % (roots[0], last))


def _stage(site, name, redo, produce, key=None):
    """A stage's output file is its done-marker. Reuse it when it exists for THIS domain AND
    the parameters that shaped it are unchanged.

    Found live 2026-09-04: reuse compared the domain only, so a first run capped at 400 pages
    by the user wrote reconciled.json, and every later uncapped run reused that file. The
    catalogue reported 400 pages of an 11,917-URL site and called it complete, and every brand
    file built from it was thin for the same reason.
    """
    doc = store.read_json(os.path.join(site["work"], name))
    stale = bool(key) and doc is not None and (doc.get("_key") or {}) != key
    if doc and not redo and not stale and doc.get("domain") == site["host"]:
        return doc, True
    out = produce()
    if key and isinstance(out, dict):
        out["_key"] = key
        store.write_json(os.path.join(site["work"], name), out)
    return out, False


# ---- the fallback when the crawl is refused ------------------------------------------------

def _index_from_search(ctx, domain, why, say):
    mode = sh.dfs_mode(dfs)
    rows = dfs.ranked_keywords(domain, limit=200)
    by_url = {}
    for row in rows:
        url = (row.get("url") or "").strip()
        if not url:
            continue
        page = by_url.setdefault(url, {
            "url": url, "title": row.get("title") or url,
            "covers": row.get("description") or "", "body": "",
            "words": 0, "keywords": [], "source": "search",
        })
        page["keywords"].append({"keyword": row.get("keyword"), "position": row.get("position"),
                                 "volume": row.get("volume")})
    pages = list(by_url.values())
    for page in pages:
        page["keywords"].sort(key=lambda r: r.get("position") or 999)
        top = page["keywords"][0]
        page["top_keyword"] = top.get("keyword")
        page["position"] = top.get("position")
        page["keyword_volume"] = top.get("volume")
    if not pages:
        raise RuntimeError("The site refused the crawl (%s) and search data lists no ranking "
                           "pages for %s, so there is nothing to index." % (why[:120], domain))
    note = "%d ranking pages from search data%s" % (
        len(pages), " (demo data, no DataForSEO credentials)" if mode == "demo" else "")
    say("Built the index from search data instead", note)
    store.save_knowledge("site_index.json", {
        "domain": dfs.bare_domain(domain),
        "page_count": len(pages),
        "pages": pages,
        "indexed_at": store.now(),
        "source": "search data",
        "crawl_blocked": why[:300],
    })
    return {
        "summary": "crawl refused; %d ranking pages indexed from search data, no page text" % len(pages),
        "page_count": len(pages),
        "crawl_blocked": True,
        "note": ("The site refused the crawl, so this index comes from what the domain ranks "
                 "for: URLs, titles, keywords and positions, but no page text. Topics and "
                 "research work from it. learn_voice cannot read pages it does not have; "
                 "tell the user, and ask them to allow the crawler or paste a few pages."),
    }


# ---- writing the knowledge files ---------------------------------------------------------------

def _brand_from(rows, root):
    """og:site_name of the homepage, else its <title> before " | " or " - "."""
    home = store_norm(root + "/")
    row = next((r for r in rows if store_norm(r["url"]) == home), None) or (rows[0] if rows else None)
    if not row:
        return ""
    if row.get("og_site_name"):
        return row["og_site_name"].strip()
    title = (row.get("title") or "").strip()
    return re.split(r"\s+[|\-–]\s+", title, maxsplit=1)[0].strip() if title else ""


def _light_row(r):
    return {
        "url": r["url"], "type": r.get("type", ""), "title": r.get("title", ""),
        "description": r.get("description", ""), "h1": r.get("h1", ""),
        "word_count": r.get("word_count", 0), "body_chars": len(r.get("body") or ""),
        "body_status": r.get("body_status", ""),
        "traffic": r.get("traffic", 0), "traffic_clean": r.get("traffic_clean", 0),
        "top_keyword": r.get("top_keyword"), "intent": r.get("intent", ""),
        "keywords": r.get("keywords") or [],
        # the single best keyword flattened, for the older readers (already_ranking, learn_voice)
        "position": ((r.get("keywords") or [{}])[0].get("position") if r.get("keywords") else None),
        "keyword_volume": ((r.get("keywords") or [{}])[0].get("volume") if r.get("keywords") else None),
        "canonical": r.get("canonical", ""),
        "modified": r.get("modified", ""), "lang": r.get("lang", ""), "source": r.get("source", ""),
        "extractor": r.get("extractor", ""),
        "text": (r.get("body") or "")[:settings.BODY_CHARS],
    }


def _write_knowledge(site, rows, tr, report, wp_doc):
    import json
    store.save_knowledge("content-database.jsonl", "".join(
        json.dumps({"url": r["url"], "type": r.get("type", ""), "title": r.get("title", ""),
                    "body": r.get("body", "")}, ensure_ascii=False) + "\n" for r in rows))
    store.save_knowledge("top-pages.json", tr["top_pages"])
    store.save_knowledge("catalogue-report.json", report)
    store.save_knowledge("site_index.json", {
        "domain": site["host"],
        "page_count": len(rows),
        "pages": [_light_row(r) for r in rows],
        "indexed_at": store.now(),
        "confidence": report["confidence"],
        "report": {"confidence": report["confidence"],
                   "gates": [{"name": g["name"], "pass": g["pass"]} for g in report["gates"]],
                   "found_urls": report["found_urls"], "read_urls": report["read_urls"],
                   "traffic": report["traffic"]},
    })
    company = store.knowledge("brand/company.json") or {}
    company["domain"] = site["host"]
    if wp_doc.get("types"):
        company["wordpress_url"] = wp_doc.get("wordpress_url") or site["root"]
    brand = _brand_from(rows, site["root"])
    if brand:
        company["brand"] = brand
    store.save_knowledge("brand/company.json", company)
    return company


# ---- the tool ----------------------------------------------------------------------------------

def run(ctx, domain, max_pages=0, redo=False, redo_traffic=False, force_crawl=False):
    say = sh.reporter(ctx, "index_site")
    roots = _roots(domain)
    # 0 means no cap, which is what the original workflow ships. A cap is a user's explicit
    # "just this many for now", never a silent default that ships a short catalogue as complete.
    max_pages = max(0, int(max_pages or 0))
    work = os.path.join(store.knowledge_dir(), "_work")
    raw = os.path.join(store.knowledge_dir(), "_raw")
    fx = fetchmod.Fetcher(work, raw, on_event=say)
    try:
        try:
            root = _discover(fx, roots, max_pages)
        except RuntimeError as e:
            # The site would not let us in (a 429 or 403 from a bot wall, seen live on
            # testlify.com 2026-09-03). The pages still exist in Google's index, and DataForSEO
            # can list every URL the domain ranks for. That is a real, if thinner, site index:
            # enough for topics and research, not enough to learn the voice. Say so.
            if sh.dfs_mode(dfs) == "off":
                raise
            say("The site refused the crawl", str(e)[:160])
            return _index_from_search(ctx, domain, str(e), say)
        host = bare_host(root)
        say("Opened the site", root)
        site = {"root": root, "host": host, "work": work, "raw": raw, "max_pages": max_pages,
                "force_crawl": force_crawl, "wordpress_url": sh.company().get("wordpress_url") or ""}

        # 1. ENUMERATE
        wp, reused = _stage(site, "urls-wp.json", redo, lambda: enumerate_wp.run(fx, site, say))
        if reused:
            say("Reused the site's own list", "%d pages from the last run" % len(wp.get("urls") or {}))
        sm, reused = _stage(site, "urls-sitemap.json", redo, lambda: enumerate_sitemap.run(fx, site, say))
        if reused:
            say("Reused the sitemap list", "%d pages from the last run" % len(sm.get("urls") or {}))
        ar, reused = _stage(site, "urls-archive.json", redo, lambda: enumerate_archive.run(fx, site, say),
                            key={"liveness_cap": settings.ARCHIVE_LIVENESS_CAP})
        if reused:
            say("Reused the web archive's list", "%d live pages from the last run" % len(ar.get("urls") or {}))
        cr, reused = _stage(site, "urls-crawl.json", redo, lambda: enumerate_crawl.run(fx, site, say))
        if reused and not cr.get("skipped"):
            say("Reused the link crawl", "%d pages from the last run" % len(cr.get("urls") or {}))

        # 2. RECONCILE (fetches every page once)
        try:
            rec, reused = _stage(site, "reconciled.json", redo, lambda: reconcile.run(fx, site, say),
                             key={"max_pages": max_pages})
        except reconcile.SiteRefused as e:
            if sh.dfs_mode(dfs) == "off":
                raise RuntimeError("The site blocked every page fetch: %s" % e)
            say("The site refused the crawl", str(e)[:160])
            return _index_from_search(ctx, domain, str(e), say)
        if reused:
            say("Reused the settled page list", "%d pages from the last run" % len(rec.get("pages") or {}))

        # 3. EXTRACT (offline)
        ex, reused = _stage(site, "extracted.json", redo,   # keyed too: a bigger cap means more pages to read
                            lambda: {"domain": host, "rows": extract.run(fx, site, say, rec)},
                            key={"max_pages": max_pages})
        rows = ex["rows"]
        if reused:
            say("Reused the extracted text", "%d pages from the last run" % len(rows))
        if not rows:
            raise RuntimeError("Found %d URLs at %s and none survived as a readable page."
                               % (rec.get("stats", {}).get("found", 0), root))

        # 4. TRAFFIC
        tr = traffic.run(site, say, rows, redo_traffic=redo_traffic)

        # 5. GATES
        st = rec.get("stats") or {}
        report = gates.run(fx, site, rows, rec, wp, sm, ar, tr, st.get("found", len(rows)), st.get("read", len(rows)))
        failed = [g for g in report["gates"] if not g["pass"]]
        say("Checked the catalogue", ("all %d checks passed" % len(report["gates"])) if not failed else
            "%d of %d checks failed: %s" % (len(failed), len(report["gates"]), "; ".join(g["name"] for g in failed)))

        # 6. WRITE
        company = _write_knowledge(site, rows, tr, report, wp)
        say("Saved the catalogue", "%d pages, %s" % (len(rows), company.get("brand") or host))
    finally:
        fx.close()

    coverage = report["coverage_overall"]
    found, read = report["found_urls"], report["read_urls"]
    summary = "%d pages catalogued for %s (%d URLs found, %d read, %.0f%% with readable text); confidence %s; %s" % (
        len(rows), host, found, read, coverage * 100, report["confidence"].split(":")[0],
        ("all %d checks passed" % len(report["gates"])) if not failed else
        "%d check(s) failed" % len(failed))
    notes = ["%s: %s" % (g["name"], g["detail"]) for g in failed]
    notes += report.get("warnings") or []
    if tr["meta"].get("skipped"):
        notes.append(tr["meta"]["skipped"])
    if tr["meta"].get("demo"):
        notes.append("traffic figures are demo data (no DataForSEO credentials)")
    return {
        "summary": summary,
        "page_count": len(rows),
        "coverage": coverage,
        "confidence": report["confidence"],
        "note": " ".join(n.rstrip(".") + "." for n in notes) if notes else "",
    }
