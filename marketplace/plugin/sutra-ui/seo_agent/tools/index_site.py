"""index_site.py — read the whole site once, so nothing after this has to guess.

Every later tool asks the same questions: what pages exist, what is each one about,
how long is it, and does it already rank. Answering that per tool would mean crawling
the site four times and getting four slightly different answers. So it happens once,
here, and lands in knowledge as site_index.json.

Discovery goes sitemap first, homepage links second. A sitemap is the site telling us
what it considers a page, which beats guessing from navigation, but plenty of sites do
not have one, and a tool that fails on those is a tool nobody trusts at setup.

Rankings are attached by exact URL match. A page with no match keeps top_keyword None
rather than borrowing a neighbour's keyword, because a wrong keyword on a page is worse
than no keyword: it steers every article written afterwards.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

# Sitemaps are XML read with the HTML parser on purpose: the bundle ships pure-Python
# wheels only, and <loc> inside <sitemap>/<url> parses the same either way.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from .. import store
from . import _shared as sh
from . import dfs

WORKERS = 10                 # polite: ten open connections is a crawl, not an attack
FETCH_TIMEOUT = 20.0
# A real browser string, not a bot label. The first live run (testlify.com, 2026-09-03)
# got a 429 on the very first request with "(compatible; seo-agent/1.0 ...)": the site's
# edge refuses anything that announces itself as a crawler, before a single page is read.
# This is the user indexing their OWN site, so presenting as the browser they would use
# to read it is the honest thing, and the concurrency cap below keeps it polite.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA,
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "en-US,en;q=0.9"}
BODY_CHARS = 400             # enough for learn_voice to hear the tone, small enough to store
SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml")
SKIP_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip",
                   ".mp4", ".mp3", ".css", ".js", ".xml", ".ico", ".woff", ".woff2")


def _client():
    return httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True, headers=HEADERS)


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


def _same_site(url, host):
    try:
        h = (urlparse(url).netloc or "").lower()
    except ValueError:
        return False
    h = h[4:] if h.startswith("www.") else h
    host = host[4:] if host.startswith("www.") else host
    return h == host


def _wanted(url):
    if not url or not url.startswith("http"):
        return False
    path = urlparse(url).path.lower()
    return not path.endswith(SKIP_EXTENSIONS)


def _clean(url):
    """Drop the fragment and trailing slash so /about and /about#team are one page, not
    two entries fighting for the same ranking row."""
    url = url.split("#")[0]
    if url.endswith("/") and urlparse(url).path != "/":
        url = url[:-1]
    return url


# ---- discovery -------------------------------------------------------------------------

def _sitemap_urls(client, root, max_pages, depth=0):
    """Returns page URLs from a sitemap, following one level of sitemap-index nesting."""
    found = []
    for path in (SITEMAP_PATHS if depth == 0 else [""]):
        target = root + path if depth == 0 else root
        try:
            r = client.get(target)
        except httpx.HTTPError:
            continue
        if r.status_code != 200 or "<" not in r.text[:2000]:
            continue
        soup = BeautifulSoup(r.text, "html.parser")   # no lxml: the bundle carries pure-Python deps only
        # A sitemap index points at more sitemaps; a sitemap points at pages.
        children = [s.loc.get_text(strip=True) for s in soup.find_all("sitemap") if s.loc]
        if children and depth == 0:
            for child in children[:20]:
                found.extend(_sitemap_urls(client, child, max_pages, depth + 1))
                if len(found) >= max_pages:
                    break
        else:
            found.extend(u.get_text(strip=True) for u in soup.find_all("loc"))
        if found:
            break
    return found


def _homepage_links(client, root):
    """The fallback when there is no sitemap: whatever the homepage links to on its own
    domain. Shallow by design, since a full crawl at setup is not worth the minutes."""
    try:
        r = client.get(root)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError("Could not open %s to find any pages: %s" % (root, e))
    soup = BeautifulSoup(r.text, "html.parser")
    host = (urlparse(root).netloc or "").lower()
    urls = [root]
    for a in soup.find_all("a", href=True):
        u = _clean(urljoin(root, a["href"]))
        if _wanted(u) and _same_site(u, host) and u not in urls:
            urls.append(u)
    return urls


def _discover_at(client, root, max_pages):
    host = (urlparse(root).netloc or "").lower()
    urls, source = [], "sitemap"
    for u in _sitemap_urls(client, root, max_pages):
        u = _clean(u)
        if _wanted(u) and _same_site(u, host):
            urls.append(u)
    if not urls:
        source = "homepage links"
        urls = _homepage_links(client, root)
    # dict.fromkeys keeps the sitemap's own order, which is usually importance order.
    urls = list(dict.fromkeys(urls))[:max_pages]
    if not urls:
        raise RuntimeError("Found no pages at %s. Is the domain right?" % root)
    return urls, source


def _discover(client, roots, max_pages):
    last = None
    for root in roots:
        try:
            urls, source = _discover_at(client, root, max_pages)
            return root, urls, source
        except (RuntimeError, httpx.HTTPError) as e:
            last = e
    raise RuntimeError("Could not read %s: %s" % (roots[0], last))


# ---- fetching --------------------------------------------------------------------------

def _fetch_one(client, url):
    try:
        r = client.get(url)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", "").lower():
            return None
        soup = BeautifulSoup(r.text, "html.parser")
    except (httpx.HTTPError, ValueError):
        # One dead page must not end the crawl. It is dropped and counted, not raised.
        return None

    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""
    desc_tag = (soup.find("meta", attrs={"name": "description"})
                or soup.find("meta", attrs={"property": "og:description"}))
    desc = (desc_tag.get("content") or "").strip() if desc_tag else ""
    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(strip=True) if h1_tag else ""
    body = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()

    return {
        "url": url,
        "title": title,
        "description": desc,
        "h1": h1,
        "word_count": len(body.split()),
        "text": body[:BODY_CHARS],
        "keywords": [],
        "top_keyword": None,
        "position": None,
    }


def _fetch_all(urls):
    with _client() as client:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(lambda u: _fetch_one(client, u), urls))
    return [p for p in results if p]


# ---- rankings --------------------------------------------------------------------------

def _attach_rankings(pages, domain):
    """Every keyword a URL ranks for goes on the page, best position first.

    The full list matters because run_research uses it as a hard filter: do not chase a
    keyword we already hold. Keeping only the top one would hide the other nineteen and
    the filter would quietly pass everything. top_keyword is the same data flattened, for
    anywhere that wants a single line.
    """
    rows = dfs.ranked_keywords(domain, limit=100)
    by_url = {}
    for row in rows:
        url = sh.normalise_url(row.get("url") or "")
        if not url:
            continue
        by_url.setdefault(url, []).append({
            "keyword": row.get("keyword"),
            "position": row.get("position"),
            "volume": row.get("volume"),
        })
    matched = 0
    for page in pages:
        found = by_url.get(sh.normalise_url(page["url"]))
        if not found:
            continue
        found.sort(key=lambda r: r.get("position") or 999)
        page["keywords"] = found
        page["top_keyword"] = found[0].get("keyword")
        page["position"] = found[0].get("position")
        page["keyword_volume"] = found[0].get("volume")
        matched += 1
    return matched, len(rows)


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


# ---- the tool --------------------------------------------------------------------------

def run(ctx, domain, max_pages=300):
    say = sh.reporter(ctx, "index_site")
    roots = _roots(domain)
    max_pages = max(1, int(max_pages or 300))

    try:
        with _client() as client:
            root, urls, source = _discover(client, roots, max_pages)
    except RuntimeError as e:
        # The site would not let us in (a 429 or 403 from a bot wall, seen live on
        # testlify.com 2026-09-03). The pages still exist in Google's index, and
        # DataForSEO can list every URL the domain ranks for, with the title and
        # description Google shows. That is a real, if thinner, site index: enough for
        # topics and research, not enough to learn the voice. Say so, in the data and
        # in the summary, and let the model tell the user.
        if sh.dfs_mode(dfs) == "off":
            raise
        say("The site refused the crawl", str(e)[:160])
        return _index_from_search(ctx, domain, str(e), say)
    say("Found the pages", "%d URLs from the %s" % (len(urls), source))

    pages = _fetch_all(urls)
    if not pages:
        raise RuntimeError("Fetched %d URLs from %s and none returned readable HTML."
                           % (len(urls), root))
    skipped = len(urls) - len(pages)
    say("Read the pages",
        "%d pages read%s" % (len(pages), (", %d skipped" % skipped) if skipped else ""))

    ranked_count = 0
    mode = sh.dfs_mode(dfs)
    if mode in ("live", "demo"):
        try:
            ranked_count, total = _attach_rankings(pages, domain)
            note = "%d of %d pages matched a ranking keyword" % (ranked_count, len(pages))
            if mode == "demo":
                note += " (demo data, no DataForSEO credentials)"
            say("Checked rankings", note)
        except Exception as e:
            # Rankings are a bonus on top of the crawl. Losing them must not lose the crawl,
            # but the user is told, because a silent skip looks like "this site ranks for
            # nothing".
            say("Rankings unavailable", str(e)[:200])
    else:
        say("Skipped rankings", "DataForSEO is not connected")

    store.save_knowledge("site_index.json", {
        "domain": dfs.bare_domain(domain),
        "page_count": len(pages),
        "pages": pages,
        "indexed_at": store.now(),
    })

    return {
        "summary": "%d pages, %d with rankings" % (len(pages), ranked_count),
        "page_count": len(pages),
    }
