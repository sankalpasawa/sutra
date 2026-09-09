"""tests/test_foundation.py — the site catalogue (index_site) against a fake site.

No network. httpx.MockTransport serves a small fixture site: robots.txt with two declared sitemaps
(one answers HTML and must be reported blocked), a sitemap index with two child urlsets, a
WordPress REST API with one listable type (X-WP-Total 3), pages with hidden elements and h1/h2/h3,
a soft-404 cluster, a redirect alias, a canonical alias, a 429-then-200 page, a robots-disallowed
page, a machine path, and the web archive's CDX index. DataForSEO is stubbed with a fake bulk pull.

Proves the plumbing and the rules: union with provenance, the blocked sitemap flagged, the CMS
body used with heading markers, hidden text gone, the shared footer line de-boilerplated, the soft
404s dropped, the aliases collapsed, the Traffic_clean arithmetic, the report shape, the files
written, and that a second run reuses the first. It does not prove the extractor on real sites.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time

import httpx

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store
from seo_agent.foundation import fetch as fetchmod
from seo_agent.foundation import settings
from seo_agent.tools import dfs, index_site, learn_voice

llm.json_call = _fixture.stub_json
llm.text = _fixture.stub_text

FAILS = []
def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond

# --- no sleeping in tests ---------------------------------------------------------------------------
settings.RATE_RPS = 1000.0
settings.FIREWALL_COOLDOWN = 0
settings.BACKOFF_BASE = 0.001
settings.BACKOFF_MAX = 0.005
settings.ARCHIVE_429_SLEEP = 0
settings.ARCHIVE_MAX_PER_MIN = 1000000

# --- the fixture site ---------------------------------------------------------------------------------
HOST = "fixture.test"
ROOT = "https://" + HOST
FOOTER = "Fixture Co is a registered trademark of Fixture Holdings. All rights reserved worldwide."
MENU = "Home About Pricing Features Team Careers Contact Blog"
CTA = "Book a demo today and see the difference for yourself."   # inside <main> on every page: chrome by repetition
LONG = ("We build skills tests for hiring teams who would rather see work than read claims. "
        "Every test is written by a practitioner, checked by a second one, and scored the same "
        "way for every candidate. The result is a shortlist you can defend to anyone who asks. ")

def page(title, h1, extra="", canonical="", lang="en"):
    # Every page's prose is its own (prefixed with its h1): a line shared by most pages IS chrome
    # by the engine's rule, so shared prose here would be removed, correctly, and prove nothing.
    own = lambda text: "%s: %s" % (h1, text)
    return ("<!doctype html><html lang='%s'><head><title>%s | Fixture Co</title>"
            "<meta name='description' content='%s, described.'>"
            "<meta property='og:site_name' content='Fixture Co'>%s</head><body>"
            "<div class='topbar'>Skip to content</div><div class='menu'>%s</div>"
            "<main><h1>%s</h1><p>%s</p><h2>Details</h2><p>%s</p><h3>More</h3>"
            "<ul><li>One thing about %s</li><li>Two things about %s</li></ul>"
            "<div style='display:none'>HIDDEN-NOTE conditional block</div>"
            "<span hidden>HIDDEN-ATTR</span><p aria-hidden='true'>HIDDEN-ARIA</p>%s<p class='cta'>%s</p></main>"
            "<div class='site-footer'>%s</div>"
            "<script>var x = {\"junk\": \"SCRIPT-JUNK\"}</script></body></html>"
            % (lang, title, title, canonical, MENU, h1, own(LONG * 2), own(LONG), h1, h1, extra, CTA, FOOTER))

def home():
    links = "".join("<li><a href='%s'>%s</a></li>" % (u, u) for u in
                    ["/about", "/pricing", "/features", "/team", "/careers", "/contact",
                     "/blog/post-1/", "/guide/main", "/flaky", "/private/secret", "/archive-only-alive",
                     "mailto:x@y", "#top", "/logo.png", "https://other.example/x"])
    return page("Skills tests for hiring teams", "Hire on evidence", extra="<ul>%s</ul>" % links)

POST_BODY = ("<h2>Why structured interviews win</h2><p>%s</p><h3>What to ask</h3><p>%s</p>"
             "<ul><li>Ask for work</li><li>Score it the same way</li></ul>" % (LONG * 2, LONG))

def post_page(n):
    return ("<!doctype html><html lang='en'><head><title>Post %d | Fixture Co</title></head><body>"
            "<div class='menu'>%s</div><main><h1>Post %d</h1>%s</main>"
            "<div class='site-footer'>%s</div></body></html>" % (n, MENU, n, POST_BODY, FOOTER))

SOFT404 = "<html><head><title>Page not found | Fixture Co</title></head><body><p>Sorry, nothing here.</p></body></html>"

XML = "application/xml"
SITEMAP_INDEX = ("<?xml version='1.0' encoding='UTF-8'?><sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                 "<sitemap><loc>%s/sitemap-pages.xml</loc></sitemap><sitemap><loc>%s/sitemap-posts.xml</loc></sitemap>"
                 "</sitemapindex>" % (ROOT, ROOT))
PAGES_URLS = ["/", "/about", "/pricing", "/features", "/team", "/careers", "/contact", "/guide/main",
              "/guide/alias-canonical", "/flaky", "/blog/redirect-old", "/private/secret",
              "/old/a", "/old/b", "/old/c", "/old/d", "/old/e", "/wp-content/uploads/x.png"]
def urlset(paths):
    return ("<?xml version='1.0' encoding='UTF-8'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
            + "".join("<url><loc>%s%s</loc><lastmod>2026-01-02</lastmod></url>" % (ROOT, p) for p in paths)
            + "</urlset>")
SITEMAP_PAGES = urlset(PAGES_URLS)
# The site as it is AFTER someone publishes and rewrites: /about carries a newer last-changed
# date and /brand-new appears. Nothing else moves. Switched on by MUTATED, for the refresh test.
MUTATED = {"on": False}
REWRITTEN = "Rewritten in September: we now score every submission blind. "
# /about-us is new to the sitemap and is not a new PAGE: it redirects to /about, which the
# catalogue already holds. A refresh must not file it as a second copy of that page.
SITEMAP_PAGES_AFTER = ("<?xml version='1.0' encoding='UTF-8'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                       + "".join("<url><loc>%s%s</loc><lastmod>%s</lastmod></url>"
                                 % (ROOT, p_, "2027-01-01" if p_ == "/about" else "2026-01-02")
                                 for p_ in PAGES_URLS + ["/brand-new", "/about-us"])
                       + "</urlset>")
# A source that FAILS is not a source that said "gone". Both of these switch one source to a
# server error while the rest of the site answers normally.
SITEMAP_FAIL = {"on": False}
WP_FAIL = {"on": False}
SITEMAP_POSTS = urlset(["/blog/post-1", "/blog/post-2", "/blog/post-3"])   # no trailing slash: the CMS form must win

ROBOTS = ("User-agent: *\nDisallow: /private/\n"
          "Sitemap: %s/sitemap_index.xml\nSitemap: %s/blocked-sitemap.xml\n" % (ROOT, ROOT))

WP_TYPES = {"post": {"rest_base": "posts", "rest_namespace": "wp/v2"},
            "page": {"rest_base": "pages"},
            "attachment": {"rest_base": "media"},
            "wp_template": {"rest_base": "templates/(?P<id>[\\d]+)"}}
WP_POSTS = [{"link": "%s/blog/post-%d/" % (ROOT, n), "type": "post",
             "title": {"rendered": "Post %d" % n}, "excerpt": {"rendered": "<p>Excerpt %d</p>" % n},
             "content": {"rendered": POST_BODY}, "modified": "2026-01-0%dT00:00:00" % n} for n in (1, 2, 3)]

CDX_ROWS = [["original"], [ROOT + "/"], ["http://www." + HOST + "/about"], [ROOT + "/archive-only-alive"],
            [ROOT + "/archive-dead"], [ROOT + "/wp-json/wp/v2/posts?per_page=100"], ["https://other.example/x"]]

LOG = []
_lock = threading.Lock()
_flaky = {"hits": 0}

def handler(request):
    url = request.url
    path = url.path
    with _lock:
        LOG.append((request.method, url.host, path))
    H = lambda body, status=200: httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8"})
    if url.host == "web.archive.org":
        if url.params.get("showNumPages") == "true":
            return httpx.Response(200, text="1\n")
        return httpx.Response(200, json=CDX_ROWS)
    if url.host != HOST:
        return H("<html><body>elsewhere</body></html>", 404)
    if request.method == "HEAD":
        status = 404 if path == "/archive-dead" else 200
        return httpx.Response(status, headers={"content-type": "text/html"})
    if path == "/robots.txt":
        return httpx.Response(200, text=ROBOTS, headers={"content-type": "text/plain"})
    if path == "/sitemap_index.xml":
        return httpx.Response(200, text=SITEMAP_INDEX, headers={"content-type": XML})
    if path == "/sitemap-pages.xml":
        if SITEMAP_FAIL["on"]:
            return httpx.Response(500, text="server error")
        return httpx.Response(200, text=SITEMAP_PAGES_AFTER if MUTATED["on"] else SITEMAP_PAGES,
                              headers={"content-type": XML})
    if path == "/sitemap-posts.xml":
        return httpx.Response(200, text=SITEMAP_POSTS, headers={"content-type": XML})
    if path == "/blocked-sitemap.xml":
        return H("<html><body>Checking your browser before accessing the site.</body></html>")
    if path == "/wp-json/wp/v2/types":
        return httpx.Response(200, json=WP_TYPES)
    if path == "/wp-json/wp/v2/posts":
        if WP_FAIL["on"]:
            return httpx.Response(500, text="the content system fell over")
        pg = int(url.params.get("page", "1"))
        if pg > 1:
            return httpx.Response(400, json={"code": "rest_post_invalid_page_number"})
        return httpx.Response(200, json=WP_POSTS, headers={"X-WP-Total": "3", "X-WP-TotalPages": "1"})
    if path == "/wp-json/wp/v2/pages":
        return httpx.Response(401, json={"code": "rest_forbidden"})
    if path == "/":
        return H(home())
    if path == "/about" and MUTATED["on"]:
        return H(page("About", "About", extra="<p>%s</p>" % (REWRITTEN * 6)))
    if path == "/brand-new":
        return H(page("Brand new", "Brand new"))
    if path == "/about-us":
        return httpx.Response(301, headers={"location": ROOT + "/about"})
    if path in ("/about", "/pricing", "/features", "/team", "/careers", "/contact", "/archive-only-alive"):
        return H(page(path.strip("/").title(), path.strip("/").title()))
    if path == "/guide/main":
        return H(page("The guide", "The guide"))
    if path == "/guide/alias-canonical":
        return H(page("The guide, alias", "The guide alias",
                      canonical="<link rel='canonical' href='%s/guide/main'>" % ROOT))
    if path == "/flaky":
        with _lock:
            _flaky["hits"] += 1
            first = _flaky["hits"] == 1
        if first:
            return httpx.Response(429, text="slow down")
        return H(page("Flaky", "Flaky but fine"))
    if path == "/blog/redirect-old":
        return httpx.Response(301, headers={"location": ROOT + "/blog/post-1/"})
    if path in ("/blog/post-1/", "/blog/post-2/", "/blog/post-3/"):
        return H(post_page(int(path[-2])))
    if path in ("/blog/post-1", "/blog/post-2", "/blog/post-3"):
        return httpx.Response(301, headers={"location": ROOT + path + "/"})
    if path.startswith("/old/"):
        return H(SOFT404)
    if path == "/private/secret":
        return H(page("Secret", "Secret"))
    if path == "/wp-content/uploads/x.png":
        return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
    return H("<html><head><title>404</title></head><body>not here</body></html>", 404)

fetchmod.TRANSPORT = httpx.MockTransport(handler)

# --- stub DataForSEO ----------------------------------------------------------------------------------
FAKE_ROWS = [
    {"keyword": "about fixture", "is_another_language": False, "core_keyword": "fixture about",
     "main_intent": "informational", "url": ROOT + "/about", "etv": 100.0, "rank_group": 3, "search_volume": 500},
    {"keyword": "fixture about", "is_another_language": False, "core_keyword": "fixture about",
     "main_intent": "informational", "url": ROOT + "/about", "etv": 60.0, "rank_group": 5, "search_volume": 300},
    {"keyword": "über fixture", "is_another_language": True, "core_keyword": "über fixture",
     "main_intent": "navigational", "url": ROOT + "/about", "etv": 50.0, "rank_group": 2, "search_volume": 90},
    {"keyword": "fixture pricing", "is_another_language": False, "core_keyword": "fixture pricing",
     "main_intent": "commercial", "url": ROOT + "/pricing", "etv": 30.0, "rank_group": 1, "search_volume": 200},
    {"keyword": "missing thing", "is_another_language": False, "core_keyword": "missing thing",
     "main_intent": "informational", "url": ROOT + "/missing-page", "etv": 10.0, "rank_group": 9, "search_volume": 40},
    {"keyword": "fixture login", "is_another_language": False, "core_keyword": "fixture login",
     "main_intent": "navigational", "url": "https://app.fixture.test/login", "etv": 5.0, "rank_group": 1, "search_volume": 10},
]
pulls = {"n": 0}
def fake_bulk(domain, location_name, language_code, limit=1000, max_rows=50000):
    pulls["n"] += 1
    pulls["market"] = (location_name, language_code)
    return {"rows": list(FAKE_ROWS), "total_count": 6, "cost_usd": 0.02}
dfs.available = lambda: True
dfs.demo_mode = lambda: False
dfs.balance = lambda: 12.5
REAL_BULK = dfs.ranked_keywords_bulk        # kept, so the ceiling checks at the foot can drive the
#                                             real client and not this stand-in
dfs.ranked_keywords_bulk = fake_bulk

# --- keep the shared fixture files safe for the suites that run after this one -----------------------
_saved = {name: store.knowledge(name) for name in ("site_index.json", "content-database.jsonl",
                                                    "brand/company.json", "top-pages.json", "catalogue-report.json")}
work = os.path.join(store.knowledge_dir(), "_work")
raw = os.path.join(store.knowledge_dir(), "_raw")
for d in (work, raw):
    shutil.rmtree(d, ignore_errors=True)

events = []
ctx = {"chat_id": "c-test", "run_id": "r-test", "emit": lambda **kw: events.append(kw)}

def site_requests():
    return sum(1 for m, h, p in LOG if h == HOST and p != "/robots.txt")

try:
    print("\nindex_site on the fixture site")
    out = index_site.run(ctx, domain=HOST)
    idx = store.knowledge("site_index.json") or {}
    pages = {p["url"]: p for p in idx.get("pages", [])}
    rec = store.read_json(os.path.join(work, "reconciled.json")) or {}
    report = store.knowledge("catalogue-report.json") or {}
    top = store.knowledge("top-pages.json") or []
    wp = store.read_json(os.path.join(work, "urls-wp.json")) or {}
    sm = store.read_json(os.path.join(work, "urls-sitemap.json")) or {}
    ar = store.read_json(os.path.join(work, "urls-archive.json")) or {}
    cr = store.read_json(os.path.join(work, "urls-crawl.json")) or {}

    print("\nenumeration")
    ok("returns a one-line summary", bool(out.get("summary")) and "\n" not in out["summary"], out.get("summary"))
    ok("the CMS listed its types at runtime and counted posts", (wp.get("types") or {}).get("post", {}).get("total") == 3, wp.get("types"))
    ok("the regex and media types were skipped", not any(t in (wp.get("types") or {}) for t in ("attachment", "wp_template")))
    ok("the unlistable type was skipped, not failed", "page" not in (wp.get("types") or {}) and "page" not in (wp.get("unavailable") or {}))
    ok("the sitemap index led to both child urlsets", len(sm.get("sitemaps_parsed") or []) == 3, sm.get("sitemaps_parsed"))
    ok("the declared HTML-answering sitemap is reported blocked",
       any(b["sitemap"].endswith("/blocked-sitemap.xml") and "HTML" in b["why"] for b in sm.get("blocked") or []), sm.get("blocked"))
    ok("the probes that were not sitemaps are recorded, not blocked",
       any(n["sitemap"].endswith("/sitemap.xml") for n in sm.get("not_sitemaps") or []))
    ok("the archive's own-host rows were kept and the offsite one dropped",
       ROOT + "/archive-only-alive" in (ar.get("urls") or {}) and not any("other.example" in u for u in ar.get("urls") or {}))
    ok("the archive URL already declared was not re-probed", (ar["urls"].get(ROOT + "/about") or {}).get("liveness") == "declared-elsewhere", ar["urls"].get(ROOT + "/about"))
    ok("the dead archive URL was dropped", ROOT + "/archive-dead" in (ar.get("dead") or []))
    ok("the link crawl ran because the other layers were thin", cr.get("skipped") is None and len(cr.get("urls") or {}) > 5, cr.get("skipped"))
    ok("the crawl stayed on the site and skipped robots-disallowed pages",
       ROOT + "/private/secret" not in (cr.get("urls") or {}) and not any("other.example" in u for u in cr.get("urls") or {}))

    print("\nreconcile")
    post1 = ROOT + "/blog/post-1/"
    ok("the CMS permalink won the stored form and the sitemap form is an alias",
       post1 in pages and ROOT + "/blog/post-1" in (rec["pages"].get(post1) or {}).get("aliases", []), (rec["pages"].get(post1) or {}).get("aliases"))
    ok("provenance carries every source that found the page", pages.get(post1, {}).get("source") == "crawl+sitemap+wp", pages.get(post1, {}).get("source"))
    ok("the homepage came from sitemap, archive and crawl", pages.get(ROOT + "/", {}).get("source") == "archive+crawl+sitemap", pages.get(ROOT + "/", {}).get("source"))
    ok("the machine path from the archive was dropped as non-content",
       any("/wp-json/" in u for u in rec["dropped"]["non_content"]) and not any("/wp-json/" in u for u in pages))
    ok("the asset from the sitemap was dropped as non-content", any(u.endswith("x.png") for u in rec["dropped"]["non_content"]))
    ok("the soft-404 cluster was dropped", len(rec["dropped"]["soft_404"]) == 5 and not any("/old/" in u for u in pages), rec["dropped"]["soft_404"])
    ok("the redirect alias collapsed onto its target", rec["dropped"]["collapsed"].get(ROOT + "/blog/redirect-old") == post1, rec["dropped"]["collapsed"])
    ok("the canonical alias collapsed onto its target", rec["dropped"]["collapsed"].get(ROOT + "/guide/alias-canonical") == ROOT + "/guide/main")
    ok("the target kept the alias", ROOT + "/guide/alias-canonical" in rec["pages"][ROOT + "/guide/main"]["aliases"])
    ok("the robots-disallowed page was dropped into its own bucket", ROOT + "/private/secret" in rec["dropped"]["robots"])
    ok("the 429-then-200 page was read after a retry", ROOT + "/flaky" in pages and pages[ROOT + "/flaky"]["body_status"] == "ok", pages.get(ROOT + "/flaky", {}).get("body_status"))
    ok("types: CMS type kept, others inferred from the path", pages[post1]["type"] == "post" and pages[ROOT + "/about"]["type"] == "pages" and pages[ROOT + "/guide/main"]["type"] == "guide",
       (pages[post1]["type"], pages[ROOT + "/about"]["type"], pages[ROOT + "/guide/main"]["type"]))

    print("\nextract")
    body = {u: t for u, t, b in [(r["url"], r["body"], 0) for r in
                                 [json.loads(l) for l in open(os.path.join(store.knowledge_dir(), "content-database.jsonl"), encoding="utf-8") if l.strip()]]}
    about = body.get(ROOT + "/about", "")
    ok("the CMS body was used for posts", pages[post1]["extractor"] == "rest", pages[post1]["extractor"])
    ok("headings are inline markers inside the CMS body", "## Why structured interviews win" in body.get(post1, "") and "### What to ask" in body.get(post1, ""))
    ok("the DOM text was used for non-CMS pages", pages[ROOT + "/about"]["extractor"] == "dom", pages[ROOT + "/about"]["extractor"])
    ok("h1 marker in the DOM text", "# About" in about, about[:200])
    ok("h2/h3 markers in the DOM text (repeated headings on every page are chrome, so check the CMS body too)",
       "## Why structured interviews win" in body.get(post1, "") and "### What to ask" in body.get(post1, ""))
    ok("list items became bullets", "\n- One thing about About" in about, about[:400])
    ok("the repeated h2/h3 lines were removed as chrome (they sit on every page)", "## Details" not in about and "### More" not in about)
    ok("hidden text was removed", not any(t in about for t in ("HIDDEN-NOTE", "HIDDEN-ATTR", "HIDDEN-ARIA", "SCRIPT-JUNK")), about)
    ok("the skip-link was cut", "Skip to content" not in about)
    ok("the shared footer line was de-boilerplated", not any(FOOTER in b for b in body.values()), [u for u, b in body.items() if FOOTER in b])
    ok("the shared menu line was de-boilerplated", not any(MENU in b for b in body.values()))
    ok("the repeated call-to-action inside <main> was de-boilerplated (it survived extraction, repetition removed it)",
       not any(CTA in b for b in body.values()), [u for u, b in body.items() if CTA in b])
    ok("real prose survived", LONG.strip()[:40] in about and pages[ROOT + "/about"]["word_count"] > 100, pages[ROOT + "/about"]["word_count"])
    ok("h1 and title recorded on the row", pages[ROOT + "/about"]["h1"] == "About" and "Fixture Co" in pages[ROOT + "/about"]["title"])
    ok("lang recorded", pages[ROOT + "/about"]["lang"] == "en")

    print("\ntraffic")
    ab = pages.get(ROOT + "/about", {})
    ok("the bulk pull was asked once, for the company's market", pulls["n"] == 1 and pulls.get("market") == ("United States", "en"), pulls)
    ok("Traffic is the raw etv sum", ab.get("traffic") == 210, ab.get("traffic"))
    ok("Traffic_clean drops the foreign row and collapses the core keyword to its max", ab.get("traffic_clean") == 100, ab.get("traffic_clean"))
    ok("top keyword is the best etv", ab.get("top_keyword") == "about fixture" and ab.get("intent") == "informational")
    ok("the keyword list is on the page, best position first", [k["keyword"] for k in ab.get("keywords", [])][:2] == ["über fixture", "about fixture"], ab.get("keywords"))
    ok("top-pages.json is sorted by the cleaned figure", [t["url"] for t in top][:2] == [ROOT + "/about", ROOT + "/pricing"], [t["url"] for t in top])
    ok("top-pages rows carry the contract fields", all(set(t) >= {"url", "traffic", "traffic_clean", "top_keyword", "intent"} for t in top))
    ok("the raw pull is cached for reuse", os.path.exists(os.path.join(work, "traffic-raw.json")))

    print("\ngates and report")
    names = [g["name"] for g in report.get("gates", [])]
    ok("report has the contract shape", all(k in report for k in ("confidence", "gates", "coverage_by_type", "provenance", "withheld", "unknown", "gaps", "traffic")), list(report))
    ok("four named gates with pass and detail", len(names) == 4 and all(set(g) >= {"name", "pass", "detail"} for g in report["gates"]), names)
    g = {x["name"]: x for x in report["gates"]}
    ok("enumeration accounting passes (CMS count matches, every sitemap URL accounted for)", g["enumeration accounting"]["pass"], g["enumeration accounting"]["detail"])
    ok("response integrity passes", g["response integrity"]["pass"], g["response integrity"]["detail"])
    ok("extraction coverage passes", g["extraction coverage"]["pass"], g["extraction coverage"]["detail"])
    ok("the traffic cross-check names the ranking page the catalogue lacks",
       not g["traffic cross-check"]["pass"] and report["gaps"] == [ROOT + "/missing-page"], report["gaps"])
    ok("the failed gate is in the note, not raised", "traffic cross-check" in out.get("note", ""), out.get("note"))
    ok("the blocked sitemap is in the report", any("blocked-sitemap" in b["sitemap"] for b in report["sitemaps"]["blocked"]))
    ok("confidence is full (the CMS counts were verified)", report["confidence"].startswith("full"), report["confidence"])
    ok("coverage by type includes post and pages", "post" in report["coverage_by_type"] and "pages" in report["coverage_by_type"])
    ok("found vs read is reported honestly", report["found_urls"] >= report["read_urls"] == len(rec["pages"]) + len(rec["dropped"]["dead"]) + len(rec["dropped"]["soft_404"]) + len(rec["dropped"]["collapsed"]) + len(rec["dropped"]["offsite"]) + len(rec["dropped"]["robots"]),
       (report["found_urls"], report["read_urls"]))
    ok("the tool result carries coverage and page_count", out.get("page_count") == len(pages) and 0 < out.get("coverage", 0) <= 1)

    print("\nfiles")
    ok("site_index.json light rows have the contract fields",
       all(set(p) >= {"url", "type", "title", "description", "h1", "word_count", "body_chars", "body_status", "traffic", "traffic_clean",
                      "top_keyword", "intent", "keywords", "modified", "lang", "source", "extractor", "text"} for p in pages.values()))
    ok("site_index.json has the header fields", idx.get("domain") == HOST and idx.get("page_count") == len(pages) and idx.get("indexed_at") and idx.get("report"))
    company = store.knowledge("brand/company.json") or {}
    ok("company.json has domain, wordpress_url and brand", company.get("domain") == HOST and company.get("wordpress_url") == ROOT and company.get("brand") == "Fixture Co", company)
    ok("raw cache is content-addressed under knowledge/_raw", any(len(d) == 2 for d in os.listdir(raw)))
    ok("emitted plain-English progress", len(events) > 10 and all(e.get("label") for e in events))

    print("\nlearn_voice can read this index")
    # the brand builders refuse without measured traffic, and the stubbed pull leaves none, so
    # plant a small real-shaped table here the way an import or a live pull would
    _idx_pages = (store.knowledge("site_index.json") or {}).get("pages") or []
    store.save_knowledge("top-pages.json", [
        {"url": p_["url"], "traffic": 500 - i * 10, "traffic_clean": 500 - i * 10,
         "top_keyword": "kw %d" % i} for i, p_ in enumerate(_idx_pages[:14])])
    try:
        lv = learn_voice.run(ctx, sample_pages=4)
        ok("learn_voice runs on the produced index", bool(lv.get("summary")))
    except Exception as e:
        ok("learn_voice runs on the produced index", False, e)

    print("\nresume")
    n0, e0 = site_requests(), len(events)
    out2 = index_site.run(ctx, domain=HOST)
    ok("a second run reuses every stage without touching the site", site_requests() == n0, site_requests() - n0)
    ok("and does not repeat the paid pull", pulls["n"] == 1, pulls["n"])
    ok("and says what it reused", any("Reused" in (e.get("label") or "") for e in events[e0:]))
    ok("and reports the same catalogue", out2.get("page_count") == out.get("page_count"))
    out3 = index_site.run(ctx, domain=HOST, redo=True)
    ok("redo rebuilds the stages from the raw cache, still without re-fetching pages", site_requests() == n0, site_requests() - n0)
    ok("redo keeps the cached traffic pull", pulls["n"] == 1, pulls["n"])
    ok("redo reports the same catalogue", out3.get("page_count") == out.get("page_count"))

    print("\nmax_pages is honoured, and a catalogue that fails its checks STOPS the run")
    for d in (work,):
        shutil.rmtree(d, ignore_errors=True)
    before = store.knowledge("site_index.json") or {}
    stop = ""
    try:
        index_site.run(ctx, domain=HOST, max_pages=5)
        ok("a capped read stops the run instead of saving a sample as the whole site", False)
    except index_site.CatalogueNotTrusted as e:
        stop = str(e)
        ok("a capped read stops the run instead of saving a sample as the whole site", True)
    rep4 = store.knowledge("catalogue-report.json") or {}
    g4 = {x["name"]: x for x in rep4["gates"]}["enumeration accounting"]
    ok("the report is still written, so the person can read what failed", not g4["pass"], g4["detail"])
    ok("and the gate says how many were missed and that a cap did it",
       "never read" in g4["detail"] and "capped the read at 5" in g4["detail"], g4["detail"])
    ok("the refusal is plain English: what failed, what it means, what to do",
       all(bit in stop for bit in ("enumeration accounting", "has NOT been saved", "never read",
                                   "without a page cap", "catalogue-report.json")), stop[:200])
    ok("the catalogue already on file was NOT replaced by the sample",
       (store.knowledge("site_index.json") or {}).get("page_count") == before.get("page_count"),
       (store.knowledge("site_index.json") or {}).get("page_count"))
    ok("the traffic cross-check is a finding, not a stopper, so a missing ranking page never "
       "throws a good catalogue away",
       {x["name"]: x for x in rep4["gates"]}["traffic cross-check"]["stops"] is False)
    out4 = index_site.run(ctx, domain=HOST, max_pages=5, accept_failed_checks=True)
    ok("a person who knows it is short can ask for it anyway", out4.get("page_count") <= 5 and rep4.get("found_urls", 0) > rep4.get("read_urls", 0), (rep4.get("found_urls"), rep4.get("read_urls")))
    ok("the summary says how many were found vs read", "found" in out4.get("summary", "") and "read" in out4.get("summary", ""), out4.get("summary"))

    print("\nthe cap is part of the stage reuse key")
    out5 = index_site.run(ctx, domain=HOST, max_pages=0)
    ok("raising the cap re-runs the settle instead of reusing the capped file",
       out5.get("page_count") > out4.get("page_count"), (out4.get("page_count"), out5.get("page_count")))
    rep5 = store.knowledge("catalogue-report.json") or {}
    g5 = {x["name"]: x for x in rep5["gates"]}["enumeration accounting"]
    ok("and with nothing left unread the gate passes again", g5["pass"], g5["detail"])

    print("\na refresh genuinely re-reads a page that changed")
    # The site moves on: /about is rewritten (and says so with a newer last-changed date) and
    # /brand-new is published. Both halves of the old bug are pinned here — the survey used to
    # read the SAVED sitemap, so it could not see either, and the fetch used to be served from
    # the saved copy, so a "re-read" page came back with its old text.
    from seo_agent.tools import refresh_site as rs
    cdb = os.path.join(store.knowledge_dir(), "content-database.jsonl")
    def db_rows():
        return {json.loads(l)["url"]: json.loads(l)
                for l in open(cdb, encoding="utf-8") if l.strip()}
    NEW_TEXT = REWRITTEN.strip()[:40]
    ok("the page about to change is on file WITHOUT the new text",
       NEW_TEXT not in (db_rows().get(ROOT + "/about", {}).get("body") or ""))
    MUTATED["on"] = True
    n_about = LOG.count(("GET", HOST, "/about"))
    surveyed = rs.survey(ctx, say=lambda *a, **k: None)
    ok("the survey asks the site again, so it sees the page published since the last read",
       ROOT + "/brand-new" in surveyed["new"], surveyed["new"][:5])
    ok("and it sees the one page whose last-changed date moved, and only that one",
       surveyed["changed"] == [ROOT + "/about"], surveyed["changed"])
    ok("a survey reads no pages, only listings", LOG.count(("GET", HOST, "/about")) == n_about)
    out6 = rs.run(ctx, redo_traffic=False)
    ok("the changed page was fetched off the site again, not served from the saved copy",
       LOG.count(("GET", HOST, "/about")) > n_about, LOG.count(("GET", HOST, "/about")) - n_about)
    after = db_rows()
    ok("so the catalogue now holds the page as it is NOW",
       NEW_TEXT in (after.get(ROOT + "/about", {}).get("body") or ""), (after.get(ROOT + "/about") or {}).get("body", "")[:120])
    ok("the number reported as re-read is the number actually read again",
       out6.get("rebuilt") == 1, (out6.get("rebuilt"), out6.get("summary")))
    ok("the page published since the last read was added", ROOT + "/brand-new" in after)
    ok("and the report says what happened in plain English",
       "re-read" in (store.knowledge("catalogue-changes.md") or ""))
    # /about-us is new to the sitemap and is not a new page: it redirects to /about, which we hold.
    ok("an address that is really an existing page is left out, not filed as a second copy",
       out6.get("duplicates") == 1 and ROOT + "/about-us" not in after, (out6.get("duplicates"), ROOT + "/about-us" in after))
    ok("and the person is told it was a duplicate, not told nothing",
       "already in the catalogue" in (store.knowledge("catalogue-changes.md") or ""))

    print("\nan address the last full read judged is not a new page")
    # The site is back to its usual list, which still contains every address reconcile fetched and
    # threw away: five soft 404s, a robots-disallowed page, an image, and two duplicate addresses.
    MUTATED["on"] = False
    dropped7 = (store.read_json(os.path.join(work, "reconciled.json")) or {}).get("dropped") or {}
    junk = (list(dropped7["soft_404"]) + list(dropped7["robots"]) + list(dropped7["non_content"])
            + list(dropped7["collapsed"]))
    s7 = rs.survey(ctx, say=lambda *a, **k: None)
    listed = [u for u in junk if rs._norm(u) in s7["current"]]
    ok("the site really does still list the addresses the last read dropped", len(listed) >= 5, len(listed))
    ok("not one of them is counted as a new page",
       not [u for u in listed if rs._norm(u) in s7["new"]], [u for u in listed if rs._norm(u) in s7["new"]])
    ok("each is reported as already judged instead, with the reason in the person's words",
       all(rs._norm(u) in s7["judged"] for u in listed) and
       any("empty template" in w for w in s7["judged_why"].values()), s7["judged_why"])
    prev7 = rs.run(ctx, preview=True)
    ok("the headline count says so rather than hiding them inside 'new'",
       "already judged" in prev7["summary"] and prev7["judged"] >= 5, prev7["summary"])
    ok("and the preview changed nothing", store.knowledge("catalogue-changes.md") is not None)

    print("\na refresh does not re-add what the last read threw away")
    out7 = rs.run(ctx, redo_traffic=False)
    have7 = {rs._norm(p_["url"]) for p_ in (store.knowledge("site_index.json") or {}).get("pages") or []}
    ok("none of them is in the catalogue afterwards",
       not [u for u in listed if rs._norm(u) in have7], [u for u in listed if rs._norm(u) in have7])
    ok("nothing was added at all this time", out7.get("added") == 0, out7.get("summary"))
    # /brand-new came only from the sitemap, the sitemap answered in full, and it is not listed
    # any more: that is the whole of the evidence "gone" is allowed to rest on.
    ok("a page the site really did stop listing IS removed, so the check still works",
       out7.get("removed") == 1 and ROOT + "/brand-new" not in have7, (out7.get("removed"), out7.get("summary")))

    print("\na source that failed can never delete a page")
    SITEMAP_FAIL["on"] = True
    s8 = rs.survey(ctx, say=lambda *a, **k: None)
    ok("the survey notices the sitemap did not answer", "sitemap" in s8["partial"], s8["partial"])
    ok("so the file that failed gets no vote on the pages it used to list",
       "sitemap-pages" in s8["partial"]["sitemap"], s8["partial"]["sitemap"])
    ok("and NOT ONE page is reported gone, though its listing vanished", s8["gone"] == [], s8["gone"][:5])
    ok("the pages it used to list are left alone instead", len(s8["unjudged"]) >= 5, len(s8["unjudged"]))
    ok("the report names the source that could not answer, so the person can see why",
       "did not answer" in rs.run(ctx, preview=True)["report"])
    # The trap this nearly fell into: the survey writes its own listing, so a failure could become
    # the new baseline and the SECOND check would delete everything the first one protected.
    s8b = rs.survey(ctx, say=lambda *a, **k: None)
    ok("a second check with the same failure still refuses — a failure never becomes the new normal",
       s8b["gone"] == [] and "sitemap" in s8b["partial"], (s8b["gone"][:3], s8b["partial"]))
    ok("because a refresh never writes over what the full read established",
       len((store.read_json(os.path.join(work, "urls-sitemap.json")) or {}).get("urls") or {}) > 15,
       len((store.read_json(os.path.join(work, "urls-sitemap.json")) or {}).get("urls") or {}))
    SITEMAP_FAIL["on"] = False
    WP_FAIL["on"] = True
    s9 = rs.survey(ctx, say=lambda *a, **k: None)
    ok("the same holds for the content system: a broken type is not a deletion",
       "post" in (s9["partial"].get("wp") or ""), s9["partial"])
    ok("and again nothing is judged gone", s9["gone"] == [], s9["gone"][:5])
    WP_FAIL["on"] = False


except Exception as e:
    import traceback
    traceback.print_exc()
    ok("runs", False, e)
finally:
    for name, v in _saved.items():
        if v is not None:
            store.save_knowledge(name, v)
    for d in (work, raw):
        shutil.rmtree(d, ignore_errors=True)
    fetchmod.TRANSPORT = None

print("\nimporting a traffic file someone already paid for")
from seo_agent.foundation import traffic_import
CSV = ("URL,Traffic,Traffic_clean,Top Keyword,Primary Intent,Market\n"
       "https://example.com/a/,4952,3028,gen x,informational,United States/en\n"
       "https://example.com/b/,120,90,hiring test,commercial,United States/en\n"
       "https://example.com/c/,0,0,ranked but quiet,informational,United States/en\n"
       "not-a-url,10,10,junk,,\n"
       "https://example.com/d/,,,,,\n")
rows, dropped, why = traffic_import.parse(CSV)
ok("a traffic export is read", not why and len(rows) == 3, (len(rows), why))
ok("a row that is not a page address is dropped", all(r["url"].startswith("http") for r in rows))
ok("a page that ranks but earns nothing is KEPT, because its keyword is real",
   any(r["url"].endswith("/c/") and r["traffic"] == 0 and r["top_keyword"] for r in rows))
ok("a row with neither a figure nor a keyword is dropped", dropped == 2, dropped)
ok("the rows come back busiest first", [r["url"] for r in rows][0].endswith("/a/"))
bad = traffic_import.parse("something,else\n1,2\n")
ok("a file with no address column is refused, and says which columns it saw",
   bad[2] and "header row is" in bad[2], bad[2])

print("\nthe brand pack refuses to build with no measured traffic")
from seo_agent.brand import _common as bcm
store.save_knowledge("top-pages.json", [])
ok("no traffic on file means no traffic", not bcm.have_traffic())
try:
    bcm.require_traffic("The brand voice builder")
    ok("it refuses", False)
except bcm.NoTraffic as e:
    ok("it refuses, naming the builder and both ways out",
       "brand voice" in str(e) and "DataForSEO" in str(e) and "import" in str(e), str(e)[:120])
store.save_knowledge("top-pages.json", [{"url": "https://example.com/%d/" % i, "traffic": 100 - i,
                                          "traffic_clean": 100 - i} for i in range(12)])
ok("with real rows on file it builds", bcm.have_traffic())
try:
    bcm.require_traffic("The brand voice builder"); ok("and does not raise", True)
except bcm.NoTraffic:
    ok("and does not raise", False)
store.save_knowledge("top-pages.json", {"demo": True, "pages": [{"url": "https://example.com/x/", "traffic": 5}] * 20})
ok("demo figures never count as measured traffic", not bcm.have_traffic())

print("\nthe article extractor rung")
from seo_agent.foundation import extract as _ex
BURIED = ("<html><head><title>t</title></head><body>"
          "<nav>Home Pricing Features Login Signup Blog Contact About Careers Docs Support Partners</nav>"
          "<article><h1>The real cost per hire</h1><p>" + ("The internal share is the one teams forget. " * 12) +
          "</p><h2>What counts</h2><p>" + ("Recruiter time, job ads, agency fees. " * 12) + "</p></article>"
          "<footer>Copyright 2026. Privacy Terms Cookies Sitemap Careers</footer></body></html>")
tb = _ex._trafilatura_body(BURIED)
ok("the article extractor pulls the article out of a page full of navigation", len(tb) > 300, len(tb))
ok("and keeps the headings as markers the rest of the pipeline reads",
   "# The real cost per hire" in tb and "## What counts" in tb, tb[:80])
ok("the navigation and the footer do not come with it",
   "Privacy Terms Cookies" not in tb and "Login Signup" not in tb)
ok("a page it cannot read returns nothing rather than raising", _ex._trafilatura_body("") == "")
ok("and so does junk", _ex._trafilatura_body("<<<not html at all>>>") == "")
_saved_t = _ex._TRAFILATURA
_ex._TRAFILATURA = False
ok("with the package absent the rung is simply skipped", _ex._trafilatura_body(BURIED) == "")
_ex._TRAFILATURA = _saved_t

print("\nthe refresh reads only what changed")
from seo_agent.tools import refresh_site as rs
ok("a sitemap date parses, with or without a timezone",
   rs._parse_lastmod("2026-09-03T18:27:01Z") and rs._parse_lastmod("2026-09-03") and
   rs._parse_lastmod("") is None)
ok("a newer sitemap date than our fetch means the page changed",
   rs._parse_lastmod("2026-09-05") > rs._parse_lastmod("2026-09-04"))

print("\nthe CMS's own list survives a record the site itself cannot render")
# A CMS that cannot render ONE item answers 5xx for the WHOLE 100-item batch that item lands in.
# Without bisection the agent gave up on the type and its other 249 items went with it.
from seo_agent.foundation import enumerate_wp  # noqa: E402

WP_HOST, WP_TOTAL, POISON = "wp.test", 250, 137
ASKED = []                      # (rest_base, per_page, page) of every listing call


def wp_handler(request):
    u = request.url
    if u.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n", headers={"content-type": "text/plain"})
    if u.path == "/wp-json/wp/v2/types":
        return httpx.Response(200, json={"post": {"rest_base": "posts"}, "note": {"rest_base": "notes"}})
    base = u.path.rsplit("/", 1)[-1]
    per, pg = int(u.params.get("per_page", "100")), int(u.params.get("page", "1"))
    ASKED.append((base, per, pg))
    start = (pg - 1) * per                       # 0-based index of this range's first item
    if start >= WP_TOTAL:
        return httpx.Response(400, json={"code": "rest_post_invalid_page_number"})
    items = list(range(start + 1, min(start + per, WP_TOTAL) + 1))
    # posts: ONE poisoned record. notes: every seventh — an endpoint that is simply broken.
    if any((i == POISON) if base == "posts" else (i % 7 == 0) for i in items):
        return httpx.Response(500, text="fatal error rendering this record")
    return httpx.Response(200, headers={"X-WP-Total": str(WP_TOTAL)},
                          json=[{"link": "https://%s/p/%d" % (WP_HOST, i), "type": "post",
                                 "title": {"rendered": "Item %d" % i}, "excerpt": {"rendered": ""},
                                 "content": {"rendered": "<p>body</p>"}, "modified": "2026-01-01"}
                                for i in items])


fetchmod.TRANSPORT = httpx.MockTransport(wp_handler)
_wp_dir = tempfile.mkdtemp(prefix="seo-wp-test-")
_wp_work = os.path.join(_wp_dir, "_work")
_wpfx = fetchmod.Fetcher(_wp_work, os.path.join(_wp_dir, "_raw"))
try:
    doc = enumerate_wp.run(_wpfx, {"root": "https://" + WP_HOST, "host": WP_HOST,
                                   "work": _wp_work, "wordpress_url": ""},
                           lambda *a, **k: None)
finally:
    _wpfx.close()
    fetchmod.TRANSPORT = None
posts = (doc.get("types") or {}).get("post") or {}
ok("the healthy items around the bad record are kept, not lost with it",
   posts.get("collected") == WP_TOTAL - 1, posts)
ok("the item the site cannot render is recorded by position, as a known gap",
   posts.get("unreadable") == [POISON], posts.get("unreadable"))
ok("the accounting still adds up to the site's own count",
   posts.get("collected", 0) + len(posts.get("unreadable") or []) + posts.get("withheld", 0) == WP_TOTAL, posts)
ok("the bad item is the only one missing from the list",
   len(doc["urls"]) == WP_TOTAL - 1 and "https://%s/p/%d" % (WP_HOST, POISON) not in doc["urls"], len(doc["urls"]))
ladder = sorted({per for b, per, _pg in ASKED if b == "posts"}, reverse=True)
ok("it narrowed the range 100 -> 50 -> 25 -> 5 -> 1, each size dividing the last",
   ladder == [100, 50, 25, 5, 1], ladder)
ok("a type where EVERY probe fails is reported unavailable, not filled with invented gaps",
   "note" in (doc.get("unavailable") or {}) and "note" not in (doc.get("types") or {}), doc.get("unavailable"))
ok("and it says the endpoint is failing rather than its records",
   "endpoint is failing" in doc["unavailable"]["note"]["reason"], doc["unavailable"]["note"]["reason"])
shutil.rmtree(_wp_dir, ignore_errors=True)

print("\nthe browser rung: a page whose text only exists once its JavaScript has run")
from seo_agent.foundation import extract as _ex2  # noqa: E402
from seo_agent.tools import _browser as _br  # noqa: E402

SPA_URL, FLAT_URL = "https://spa.test/dashboard", "https://spa.test/plain"
SPA_HTML = ("<!doctype html><html lang='en'><head><title>Dashboard</title></head><body>"
            "<div id='__next'></div><script>window.__NEXT_DATA__=" + ("'padding'" * 400) +
            "</script></body></html>")
RENDERED = ("<!doctype html><html lang='en'><head><title>Dashboard</title></head><body><main>"
            "<h1>Your dashboard</h1><p>%s</p></main></body></html>" % (LONG * 3))


class _FakeFx:
    """Just enough Fetcher for extract: the raw cache, and nothing else."""

    def __init__(self, pages):
        self.pages = pages

    def cached(self, url):
        html = self.pages.get(url)
        if html is None:
            return None
        return fetchmod.FetchResult(url, url, 200, html.encode("utf-8"), "text/html", {}, True)


def _extract_fixture():
    site = {"host": "spa.test", "work": tempfile.mkdtemp(prefix="seo-spa-test-")}
    rec = {"pages": {SPA_URL: {"type": "app", "sources": ["sitemap"]},
                     FLAT_URL: {"type": "page", "sources": ["sitemap"]}}}
    return _FakeFx({SPA_URL: SPA_HTML, FLAT_URL: page("Plain", "Plain")}), site, rec


asked_browser = []
_real_avail, _real_fetch = _br.available, _br.fetch
_br.available = lambda: "shell"
_br.fetch = lambda url, timeout=60: (asked_browser.append(url) or
                                     {"status": 200, "url": url, "text": RENDERED,
                                      "content_type": "text/html", "headers": {}})
try:
    _fx2, _site2, _rec2 = _extract_fixture()
    got = {r["url"]: r for r in _ex2.run(_fx2, _site2, lambda *a, **k: None, _rec2)}
    ok("the JavaScript page was read through the browser", got[SPA_URL]["extractor"] == "browser",
       got[SPA_URL]["extractor"])
    ok("and its text is the text a visitor sees",
       "Your dashboard" in got[SPA_URL]["body"] and got[SPA_URL]["body_status"] == "ok",
       got[SPA_URL]["body"][:120])
    ok("only the empty page went to the browser; a page that already had text never did",
       asked_browser == [SPA_URL], asked_browser)
    ok("no page is left half-judged", not any(r["body_status"] == "spa_candidate" for r in got.values()))
    shutil.rmtree(_site2["work"], ignore_errors=True)

    asked_browser[:] = []
    _br.available = lambda: None
    _fx2, _site2, _rec2 = _extract_fixture()
    got = {r["url"]: r for r in _ex2.run(_fx2, _site2, lambda *a, **k: None, _rec2)}
    ok("with no browser anywhere the page is recorded as unreadable, never as blank text",
       got[SPA_URL]["body_status"] == "failed" and not asked_browser, got[SPA_URL]["body_status"])
    ok("and the page that needed no browser is unaffected", got[FLAT_URL]["body_status"] in ("ok", "stub"))
    shutil.rmtree(_site2["work"], ignore_errors=True)
finally:
    _br.available, _br.fetch = _real_avail, _real_fetch

print("\na page that hangs costs that page, not the whole crawl")
ok("the wall-clock cap and the worker count are the original's numbers",
   (settings.EXTRACT_TIMEOUT, settings.EXTRACT_WORKERS) == (20, 4),
   (settings.EXTRACT_TIMEOUT, settings.EXTRACT_WORKERS))
_pool = _ex2._pool(2)
ok("extraction really runs in separate processes, which is what makes the kill possible",
   _pool is not None and _pool.submit(os.getpid).result(timeout=60) != os.getpid())
if _pool is not None:
    _pool.shutdown(wait=True)
_payloads = [("https://hang.test/%d" % i, {"type": "page", "sources": []},
              page("P%d" % i, "P%d" % i).encode("utf-8"), None) for i in range(6)]
_rows = _ex2._extract_all(_payloads, lambda *a, **k: None)
ok("every page comes back from the pool, once each",
   sorted(r["url"] for r in _rows) == sorted(p_[0] for p_ in _payloads), len(_rows))
_saved_timeout, _real_one = settings.EXTRACT_TIMEOUT, _ex2.extract_one
settings.EXTRACT_TIMEOUT = 1
_ex2.extract_one = lambda *a, **k: time.sleep(60)
try:
    _t0 = time.time()
    _row = _ex2._worker(("https://hang.test/stuck", {"type": "page", "sources": []}, b"<html></html>", None))
    _dt = time.time() - _t0
finally:
    settings.EXTRACT_TIMEOUT, _ex2.extract_one = _saved_timeout, _real_one
ok("a hung extract is KILLED at the cap, not waited out", _dt < 5, "%.1fs" % _dt)
ok("and the page is recorded as unreadable, never as blank text that reads like a real page",
   _row["extractor"] == "timeout" and _row["body_status"] == "failed", _row["extractor"])

# --- the row ceiling is LOUD -----------------------------------------------------------------------
# foundation/settings.py calls TRAFFIC_MAX_ROWS "a loud safety ceiling (never a silent cap)" and
# dfs.ranked_keywords_bulk's docstring says the same. Neither was true: the pull stopped on it and
# came back looking exactly like a pull that had reached the end of the data, so a big site's
# figures were the first 50,000 keywords reported as if they were all of it.
print("\nthe traffic row ceiling says so")
from seo_agent.foundation import traffic as _traffic
_SAID = []


def _say(label, note=""):
    _SAID.append((label, note))


_capped_note = ("stopped at 50000 of 900000 rows: the 50000-row safety ceiling was reached, so the "
                "rest of this domain's keywords are not in the figures")
_saved_bulk = dfs.ranked_keywords_bulk
dfs.ranked_keywords_bulk = lambda domain, location_name, language_code, limit=1000, max_rows=50000: {
    "rows": list(FAKE_ROWS), "total_count": 900000, "cost_usd": 5.0, "capped": _capped_note}
_site = {"host": "ceiling.test", "work": tempfile.mkdtemp(prefix="ceiling-")}
try:
    _r = _traffic.run(_site, _say, [], redo_traffic=True)
    ok("a pull that stops on the ceiling says so, in the run's own words",
       any("ceiling" in l.lower() for l, _n in _SAID)
       and any("not in the figures" in n for _l, n in _SAID), _SAID)
    ok("...and the figures carry it, so a reader of the summary sees it too",
       _r["meta"].get("capped") == _capped_note, _r["meta"].get("capped"))
    # the saved pull is reused on every later run, so the cap has to be as loud the tenth time
    _SAID.clear()
    _traffic.run(_site, _say, [], redo_traffic=False)
    ok("a reused pull that was capped repeats the warning rather than going quiet",
       any("capped" in l.lower() for l, _n in _SAID), _SAID)
finally:
    dfs.ranked_keywords_bulk = _saved_bulk
    shutil.rmtree(_site["work"], ignore_errors=True)

# and the client really does set it, rather than the note being something only the test knows about
_posted = {"n": 0}


_TOTAL = 5000


def _fake_post(path, payload):
    _posted["n"] += 1
    off = payload[0]["offset"]
    n = max(0, min(1000, _TOTAL - off))
    return {"tasks": [{"status_code": 20000, "cost": 0.11,
                       "result": [{"total_count": _TOTAL,
                                   "items": [{"keyword_data": {"keyword": "k%d" % (off + i),
                                                               "keyword_info": {"search_volume": 10}},
                                              "ranked_serp_element": {"serp_item": {"url": "https://x/%d" % i}}}
                                             for i in range(n)]}]}]}


_saved_post, _saved_demo, _saved_bal = dfs.post, dfs.demo_mode, dfs.balance
dfs.post, dfs.demo_mode, dfs.balance = _fake_post, (lambda: False), (lambda: 50.0)
try:
    _out = REAL_BULK("x.test", "United States", "en", limit=1000, max_rows=2000)
    ok("the client stops at the ceiling and hands back the sentence that explains why",
       len(_out["rows"]) == 2000 and "safety ceiling was reached" in (_out.get("capped") or ""),
       (len(_out["rows"]), _out.get("capped")))
    _out2 = REAL_BULK("x.test", "United States", "en", limit=1000, max_rows=50000)
    ok("a pull that reaches the end of the data is NOT reported as capped",
       len(_out2["rows"]) == _TOTAL and not _out2.get("capped"), (len(_out2["rows"]), _out2.get("capped")))
finally:
    dfs.post, dfs.demo_mode, dfs.balance = _saved_post, _saved_demo, _saved_bal

print("\nFake site, stubbed DataForSEO. Proves the rules and the plumbing, not the extractor on real HTML.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
