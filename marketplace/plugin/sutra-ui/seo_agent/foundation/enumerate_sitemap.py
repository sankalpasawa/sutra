"""Layer 2 — every URL the site's sitemaps declare.

Reads:  robots.txt Sitemap: lines (ALL of them — some sites publish 8), then a platform-aware
        probe list (WordPress core + SEO plugins, Shopify, Webflow, Ghost, Squarespace, HubSpot,
        Wix, Next.js, Drupal, Craft, BigCommerce, Framer, Duda, Magento).
Writes: _work/urls-sitemap.json:
  { "urls": { <loc>: {"lastmod": ..., "sitemap": <which sitemap listed it>} },
    "sitemaps_parsed": [...], "blocked": [...], "not_sitemaps": [...], "all_blocked": bool }

Rules (all measured or spec'd):
- Branch on what the DOCUMENT declares (root element sitemapindex vs urlset), never the filename.
- Follow <loc> literally — NEVER reconstruct child URLs, NEVER same-host-filter children
  (Webflow's children live on a different host).
- Gzip by MAGIC NUMBER, not filename (either can lie).
- Refuse XML that declares entities (billion-laughs) — and HTML pretending to be a sitemap.
- Nested indexes: depth cap + cycle detection INCLUDING through redirects.
- A DECLARED sitemap answering with HTML = BLOCKED, logged loudly. A speculative PROBE answering
  HTML just isn't a sitemap (SPA catch-alls answer 200 to everything) — recorded, not fatal.
- Platforms serve identical sitemaps at several URLs, often via redirects — dedupe on our side.
"""
import gzip
import os
import urllib.parse as _up
import xml.etree.ElementTree as ET

from .. import store
from . import settings
from .fetch import Blocked, RobotsDisallowed

# The probe list — union of where real platforms put sitemaps (checked after robots.txt's own
# Sitemap: lines, in this order).
PROBE_PATHS = [
    "/sitemap.xml",            # near-universal default (Shopify, Webflow, Squarespace, HubSpot,
                               #   Wix, Ghost, Next.js, Drupal, Craft, Framer, Duda, Magento)
    "/sitemap_index.xml",      # WordPress: Yoast + Rank Math
    "/wp-sitemap.xml",         # WordPress core (5.5+)
    "/sitemap-index.xml",      # SEOPress and others
    "/sitemapindex.xml",
    "/sitemap1.xml",           # Blogger-style numbered
    "/sitemap-1.xml",
    "/post-sitemap.xml",       # Yoast children, when the index itself is hidden
    "/page-sitemap.xml",
    "/pages-sitemap.xml",
    "/sitemap/sitemap.xml",
    "/sitemap/index.xml",
    "/sitemap.xml.gz",
    "/xmlsitemap.php",         # BigCommerce
    "/media/sitemap.xml",      # Magento variant
    "/sitemaps.xml",
    "/sitemap.txt",            # the protocol's plain-text form
]

GZIP_MAGIC = b"\x1f\x8b"


def _decode(content):
    """Gzip by magic number (double-encoded and mislabelled files both land here correctly)."""
    if content[:2] == GZIP_MAGIC:
        content = gzip.decompress(content)
    return content


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def classify(content):
    """What IS this document? -> ('index'|'urlset'|'txt'|'html'|'bad', parsed-or-None)"""
    try:
        body = _decode(content or b"")
    except (OSError, EOFError):
        return "bad", None
    head = body[:4096].lstrip()
    if head[:1] != b"<":
        # maybe a plain-text sitemap: lines of URLs
        lines = [ln.strip() for ln in body.decode("utf-8", "ignore").splitlines() if ln.strip()]
        if lines and all(ln.startswith(("http://", "https://")) for ln in lines[:20]):
            return "txt", lines
        return "bad", None
    lowered = head[:2048].lower()
    if b"<!entity" in lowered or (b"<!doctype" in lowered and b"<!doctype html" not in lowered):
        return "bad", None               # entity-declaring XML — refuse (attack surface)
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return ("html", None) if b"<html" in lowered or b"<!doctype html" in lowered else ("bad", None)
    name = _local(root.tag)
    if name == "sitemapindex":
        return "index", root
    if name == "urlset":
        return "urlset", root
    if name == "html":
        return "html", None
    return "bad", None


def _looks_like_sitemap(loc):
    """Does this <loc> point at a nested SITEMAP rather than a content page? Judge by the target,
    not the wrapper tag. (Real case: a site wraps its sitemap INDEX in <urlset>/<url> instead of
    <sitemapindex>/<sitemap>, so a spec-literal parse mistakes 12 child sitemaps for 12 pages.)"""
    path = _up.urlsplit(loc).path.lower()
    return path.endswith(".xml") or path.endswith(".xml.gz")


def _locs(root, child_name):
    """<loc> values under <sitemap>/<url> children, taken literally, plus lastmod."""
    out = []
    for el in root:
        if _local(el.tag) != child_name:
            continue
        loc, lastmod = None, ""
        for sub in el:
            if _local(sub.tag) == "loc":
                loc = (sub.text or "").strip()
            elif _local(sub.tag) == "lastmod":
                lastmod = (sub.text or "").strip()
        if loc:
            out.append((loc, lastmod))
    return out


def run(fx, site, say):
    root = site["root"]
    declared = fx.sitemaps_from_robots(root)
    say("Read robots.txt", "%d sitemap(s) declared" % len(declared) if declared else "no sitemap declared")

    urls, parsed_ok, blocked, not_sitemaps = {}, [], [], []
    seen = set()                          # cycle detection: requested AND final URLs

    def walk(sm_url, depth, is_declared):
        key = sm_url.rstrip("/")
        if key in seen:
            return
        seen.add(key)
        if depth > settings.SITEMAP_DEPTH_CAP:
            blocked.append({"sitemap": sm_url, "why": "nested deeper than %d levels — not descended"
                            % settings.SITEMAP_DEPTH_CAP})
            return
        try:
            r = fx.get(sm_url)
        except RobotsDisallowed:
            blocked.append({"sitemap": sm_url, "why": "robots disallows it"})
            return
        except Blocked as e:
            blocked.append({"sitemap": sm_url, "why": "firewall: %s" % str(e)[:120]})
            return
        seen.add((r.final_url or sm_url).rstrip("/"))          # cycles THROUGH redirects
        if r.status != 200:
            (blocked if is_declared else not_sitemaps).append(
                {"sitemap": sm_url, "why": "HTTP %d" % r.status})
            return
        kind, payload = classify(r.content)
        if kind == "index":
            children = _locs(payload, "sitemap")
            parsed_ok.append(sm_url)
            for loc, _ in children:
                walk(loc, depth + 1, is_declared=True)   # declared BY the index — must exist
        elif kind == "urlset":
            entries = _locs(payload, "url")
            parsed_ok.append(sm_url)
            for loc, lastmod in entries:
                if _looks_like_sitemap(loc):
                    walk(loc, depth + 1, is_declared=True)   # a <url> that is really a sitemap
                elif loc not in urls:
                    urls[loc] = {"lastmod": lastmod, "sitemap": sm_url}
        elif kind == "txt":
            parsed_ok.append(sm_url)
            for loc in payload:
                if loc not in urls:
                    urls[loc] = {"lastmod": "", "sitemap": sm_url}
        elif kind == "html":
            if is_declared:
                blocked.append({"sitemap": sm_url,
                                "why": "HTML where XML was expected — challenge/anti-bot page"})
                say("A declared sitemap was blocked",
                    "%s answered a web page instead of a sitemap" % sm_url)
            else:
                not_sitemaps.append({"sitemap": sm_url, "why": "HTML (SPA catch-all, not a sitemap)"})
        else:
            (blocked if is_declared else not_sitemaps).append(
                {"sitemap": sm_url, "why": "unparseable / entity-declaring XML"})

    for sm in declared:
        walk(sm, 0, is_declared=True)
    for path in PROBE_PATHS:
        walk(root + path, 0, is_declared=False)

    all_blocked = bool(not urls and blocked)
    doc = {"domain": site["host"], "urls": urls, "sitemaps_parsed": parsed_ok,
           "blocked": blocked, "not_sitemaps": not_sitemaps, "all_blocked": all_blocked}
    store.write_json(os.path.join(site["work"], "urls-sitemap.json"), doc)
    if all_blocked:
        say("Every sitemap was refused", "%d sitemap(s) blocked — this is not an empty layer, it is being refused"
            % len(blocked))
    else:
        say("Read the sitemaps", "%d pages from %d sitemap file(s)%s"
            % (len(urls), len(parsed_ok), (", %d blocked" % len(blocked)) if blocked else ""))
    return doc
