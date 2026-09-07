"""Layer 4 — internal-link crawl. LAST RESORT: runs only when the other three layers came back
thin (no CMS, no usable sitemap, little archive history), or when forced.

Reads:  urls-wp.json + urls-sitemap.json + urls-archive.json (to decide whether it is needed),
        then the live site breadth-first through fetch (rate-limited, cached, robots-obeying).
Writes: _work/urls-crawl.json:
  { "skipped": null | "<reason>", "urls": { <url>: {"discovered_from": ...} }, "blocked": null|"<why>" }

Rules:
- BFS stays on the site's own hosts (apex + www) — this layer walks the SITE, unlike sitemap
  children which may live elsewhere and are followed literally there.
- Caps: CRAWL_MAX_PAGES pages (and never more than the run's max_pages), CRAWL_DEPTH_CAP hops.
  State saved every 25 pages -> resumable.
- Only http(s) content pages: skips mailto/tel/fragments, obvious binaries by extension.
"""
import os
import urllib.parse as _up

from bs4 import BeautifulSoup

from .. import store
from . import settings
from .fetch import Blocked, RobotsDisallowed
from .urls import own_host

_SKIP_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".css", ".js",
             ".zip", ".gz", ".mp3", ".mp4", ".webm", ".woff", ".woff2", ".xml", ".json")


def _other_layers_count(work):
    n = set()
    for name in ("urls-wp.json", "urls-sitemap.json", "urls-archive.json"):
        doc = store.read_json(os.path.join(work, name)) or {}
        n |= set((doc.get("urls") or {}).keys())
    return len(n)


def links(base_url, content):
    try:
        soup = BeautifulSoup(content, "html.parser")
    except Exception:
        return []
    out = []
    for a in soup.find_all("a", href=True):
        href = (a["href"] or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        u = _up.urljoin(base_url, href)
        try:
            parts = _up.urlsplit(u)
        except ValueError:
            continue
        if parts.scheme not in ("http", "https"):
            continue
        if parts.path.lower().endswith(_SKIP_EXT):
            continue
        out.append(_up.urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, "")))
    return out


def run(fx, site, say):
    out_path = os.path.join(site["work"], "urls-crawl.json")
    found = _other_layers_count(site["work"])
    if found >= settings.CRAWL_IF_UNDER and not site.get("force_crawl"):
        doc = {"domain": site["host"], "skipped": "other layers found %d URLs" % found, "urls": {}, "blocked": None}
        store.write_json(out_path, doc)
        say("No link crawl needed", "the other sources already found %d pages" % found)
        return doc

    budget = min(settings.CRAWL_MAX_PAGES, int(site.get("max_pages") or settings.CRAWL_MAX_PAGES))
    state_path = out_path + ".state.json"
    st = store.read_json(state_path)
    if st and st.get("domain") == site["host"]:
        queue, seen, urls = st["queue"], set(st["seen"]), st["urls"]
        say("Resuming the link crawl", "%d found so far, %d queued" % (len(urls), len(queue)))
    else:
        queue, seen, urls = [[site["root"] + "/", 0, "(start)"]], set(), {}
        say("Following links from the homepage",
            "the other sources found only %d pages, so the site is walked link by link" % found)

    def save():
        store.write_json(state_path, {"domain": site["host"], "queue": queue, "seen": sorted(seen), "urls": urls})

    blocked, fetched = None, 0
    while queue and len(urls) < budget:
        url, depth, parent = queue.pop(0)
        key = url.rstrip("/")
        if key in seen or depth > settings.CRAWL_DEPTH_CAP:
            continue
        seen.add(key)
        try:
            r = fx.get(url)
        except RobotsDisallowed:
            continue
        except Blocked as e:
            blocked = str(e)[:200]
            save()
            say("The site blocked the link crawl", blocked[:140])
            break
        if r.status != 200 or "html" not in (r.content_type or "").lower():
            continue
        urls[url] = {"discovered_from": parent}
        fetched += 1
        for link in links(r.final_url, r.content):
            if own_host(link, site["host"]) and link.rstrip("/") not in seen:
                queue.append([link, depth + 1, url])
        if fetched % 25 == 0:
            save()
            say("Still following links", "%d pages found, %d waiting" % (len(urls), len(queue)))

    save()
    doc = {"domain": site["host"], "skipped": None, "urls": urls, "blocked": blocked}
    store.write_json(out_path, doc)
    say("Followed the site's links", "%d pages found by crawling" % len(urls))
    return doc
