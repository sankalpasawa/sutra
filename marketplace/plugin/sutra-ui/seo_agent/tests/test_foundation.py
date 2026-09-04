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
import threading

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
        return httpx.Response(200, text=SITEMAP_PAGES, headers={"content-type": XML})
    if path == "/sitemap-posts.xml":
        return httpx.Response(200, text=SITEMAP_POSTS, headers={"content-type": XML})
    if path == "/blocked-sitemap.xml":
        return H("<html><body>Checking your browser before accessing the site.</body></html>")
    if path == "/wp-json/wp/v2/types":
        return httpx.Response(200, json=WP_TYPES)
    if path == "/wp-json/wp/v2/posts":
        pg = int(url.params.get("page", "1"))
        if pg > 1:
            return httpx.Response(400, json={"code": "rest_post_invalid_page_number"})
        return httpx.Response(200, json=WP_POSTS, headers={"X-WP-Total": "3", "X-WP-TotalPages": "1"})
    if path == "/wp-json/wp/v2/pages":
        return httpx.Response(401, json={"code": "rest_forbidden"})
    if path == "/":
        return H(home())
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

    print("\nmax_pages is honoured")
    for d in (work,):
        shutil.rmtree(d, ignore_errors=True)
    out4 = index_site.run(ctx, domain=HOST, max_pages=5)
    rep4 = store.knowledge("catalogue-report.json") or {}
    ok("only max_pages are read and the rest are recorded", out4.get("page_count") <= 5 and rep4.get("found_urls", 0) > rep4.get("read_urls", 0), (rep4.get("found_urls"), rep4.get("read_urls")))
    g4 = {x["name"]: x for x in rep4["gates"]}["enumeration accounting"]
    # the original fails the run rather than ship a short catalogue; here the gate fails and says so
    ok("a capped read FAILS the accounting gate, so a sample never reads as the whole site", not g4["pass"], g4["detail"])
    ok("and the gate says how many were missed and that a cap did it",
       "never read" in g4["detail"] and "capped the read at 5" in g4["detail"], g4["detail"])
    ok("the summary says how many were found vs read", "found" in out4.get("summary", "") and "read" in out4.get("summary", ""), out4.get("summary"))

    print("\nthe cap is part of the stage reuse key")
    out5 = index_site.run(ctx, domain=HOST, max_pages=0)
    ok("raising the cap re-runs the settle instead of reusing the capped file",
       out5.get("page_count") > out4.get("page_count"), (out4.get("page_count"), out5.get("page_count")))
    rep5 = store.knowledge("catalogue-report.json") or {}
    g5 = {x["name"]: x for x in rep5["gates"]}["enumeration accounting"]
    ok("and with nothing left unread the gate passes again", g5["pass"], g5["detail"])

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

print("\nFake site, stubbed DataForSEO. Proves the rules and the plumbing, not the extractor on real HTML.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
