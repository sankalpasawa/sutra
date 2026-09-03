"""tests/test_browser.py — reading a site that answers every plain request with a bot challenge.

The failure this pins happened on the first live run (2026-09-03): testlify.com moved to
Next.js on Vercel with Attack Challenge Mode, and robots.txt, the sitemap and every page
answered 429 with a JavaScript challenge. Cookies from a browser did not help a plain
client; only a browser passes. So the crawler must (1) recognise a challenge instead of
retrying it as a rate limit, (2) switch that host to the browser for the rest of the run,
(3) cache what the browser fetched like any other page, and (4) say plainly when there is
no browser rather than reporting an empty site.

The "browser" here is a fake of the desktop shell's fetch service: a loopback HTTP server
that answers POST /fetch the way main.js does. No real browser, no network.
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from seo_agent.tests import _fixture
_fixture.setup()

import httpx  # noqa: E402

from seo_agent.foundation import fetch as F  # noqa: E402
from seo_agent.tools import _browser  # noqa: E402

FAILS = []
def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond

# ---- a fake shell fetch service -------------------------------------------------------------
CALLS = []
PAGES = {"https://walled.example/robots.txt": ("text/plain", "User-agent: *\nAllow: /\nSitemap: https://walled.example/sitemap.xml\n"),
         "https://walled.example/sitemap.xml": ("application/xml", "<urlset><url><loc>https://walled.example/a</loc></url></urlset>"),
         "https://walled.example/a": ("text/html", "<html><body><main><h1>Page A</h1><p>" + "real words " * 60 + "</p></main></body></html>")}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        CALLS.append((self.path, self.headers.get("x-sutra-browser"), body.get("url")))
        if self.headers.get("x-sutra-browser") != "tok":
            self.send_response(403); self.end_headers(); self.wfile.write(b'{"error":"bad token"}'); return
        ct, text = PAGES.get(body.get("url"), ("text/html", ""))
        out = {"status": 200 if text else 404, "url": body.get("url"), "text": text, "content_type": ct, "headers": {"content-type": ct}}
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(out).encode())

srv = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["SEO_AGENT_BROWSER_FETCH"] = "http://127.0.0.1:%d" % srv.server_address[1]
os.environ["SEO_AGENT_BROWSER_TOKEN"] = "tok"

print("\nrecognising a challenge")
ok("a Vercel challenge is recognised by its header", _browser.challenged(429, {"x-vercel-mitigated": "challenge"}, b"<html>"))
ok("a Cloudflare challenge is recognised by its body", _browser.challenged(403, {}, b"<html><title>Just a moment...</title>cf-chl"))
ok("a plain 429 rate limit is NOT a challenge", not _browser.challenged(429, {"retry-after": "5"}, b"slow down"))
ok("a 200 is never a challenge whatever the body says", not _browser.challenged(200, {}, b"Just a moment"))
ok("the shell backend is reported when its env is set", _browser.available() == "shell")

print("\nthe client")
r = _browser.fetch("https://walled.example/sitemap.xml")
ok("fetches through the shell service", r["status"] == 200 and "<loc>" in r["text"])
ok("the token travels on the call", CALLS and CALLS[-1][1] == "tok")
os.environ["SEO_AGENT_BROWSER_TOKEN"] = "wrong"
try:
    _browser.fetch("https://walled.example/a"); ok("a refused token raises NoBrowser", False)
except _browser.NoBrowser as e:
    ok("a refused token raises NoBrowser, with the shell's reason", "403" in str(e))
os.environ["SEO_AGENT_BROWSER_TOKEN"] = "tok"

print("\nthe fetcher switches a challenged host to the browser")
plain_hits = []
def transport(req):
    plain_hits.append(str(req.url))
    if req.url.host == "walled.example":
        return httpx.Response(429, headers={"x-vercel-mitigated": "challenge", "content-type": "text/html"},
                              content=b"<html data-astro-cid-4wdtffzm><title>Verifying</title></html>")
    return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html><body>open site</body></html>")
F.TRANSPORT = httpx.MockTransport(transport)
import tempfile
work = tempfile.mkdtemp(prefix="seo-browser-test-")
events = []
fx = F.Fetcher(os.path.join(work, "_work"), os.path.join(work, "_raw"), on_event=lambda l, n="": events.append((l, n)))
r1 = fx.get("https://walled.example/a", obey_robots=False)
ok("the first page came back through the browser, status 200", r1.status == 200, r1.status)
ok("with the real body", b"Page A" in (r1.body if hasattr(r1, "body") else getattr(r1, "content", b"")) or "Page A" in str(r1.__dict__))
ok("and only ONE plain request was spent on the challenge", plain_hits.count("https://walled.example/a") == 1, plain_hits)
ok("the switch was said out loud, naming the host", any("bot challenge" in l for l, n in events) and any("walled.example" in n for l, n in events), events)
n_plain = len(plain_hits)
r2 = fx.get("https://walled.example/sitemap.xml", obey_robots=False)
ok("the next page on that host skipped plain HTTP entirely", len(plain_hits) == n_plain, plain_hits)
ok("and came through the browser", r2.status == 200 and CALLS[-1][2] == "https://walled.example/sitemap.xml")
r3 = fx.get("https://walled.example/a", obey_robots=False)
ok("a re-read is served from the cache, not the browser", CALLS[-1][2] != "https://walled.example/a" or fx.stats["cache"] >= 1)
h = fx.head("https://walled.example/a", obey_robots=False)
ok("a liveness probe on a challenged host goes through the browser and reads as alive", h.status_code == 200 and CALLS[-1][2] == "https://walled.example/a")
r4 = fx.get("https://open.example/x", obey_robots=False)
ok("an unchallenged host still goes plain", r4.status == 200 and "https://open.example/x" in plain_hits)

print("\nthe write phase's source check and the research page reader use the same fallback")
from seo_agent.write import _common as WC  # noqa: E402
from seo_agent.research import web as RW  # noqa: E402
real_get = httpx.get
def fake_get(url, **kw):
    plain_hits.append(url)
    if "walled.example" in url:
        return httpx.Response(429, headers={"x-vercel-mitigated": "challenge", "content-type": "text/html"},
                              content=b"<html><title>Verifying</title></html>", request=httpx.Request("GET", url))
    return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html><body>" + b"open words " * 80 + b"</body></html>",
                          request=httpx.Request("GET", url))
httpx.get = fake_get
try:
    txt = WC._fetch_once("https://walled.example/a")     # the fixture stubs WC.fetch's network; test the real reader
    ok("the source check reads a walled page through the browser", "real words" in txt and not txt.startswith("__ERR__"), txt[:80])
    ok("and remembers the host", "walled.example" in WC._BROWSER_HOSTS)
    n_plain = len(plain_hits)
    WC._fetch_once("https://walled.example/a")
    ok("the second read on that host spends no plain request", len(plain_hits) == n_plain)
    ok("an open host still reads plain in the source check", not WC._fetch_once("https://open.example/y").startswith("__ERR__"))
    page = RW.fetch("https://walled.example/a")
    ok("the research page reader reads a walled page through the browser", page["word_count"] > 50 and "Page A" in page["headings"], page)
    ok("and remembers the host too", "walled.example" in RW._BROWSER_HOSTS)
finally:
    httpx.get = real_get

print("\nno browser at all")
del os.environ["SEO_AGENT_BROWSER_FETCH"]
import importlib
real_avail = _browser.available
_browser.available = lambda: None
fx2 = F.Fetcher(os.path.join(work, "_work2"), os.path.join(work, "_raw2"))
try:
    fx2.get("https://walled.example/b", obey_robots=False); ok("raises Blocked when nothing can pass the challenge", False)
except F.Blocked as e:
    ok("raises Blocked when nothing can pass the challenge, naming the challenge", "bot challenge" in str(e) and "Sutra app" in str(e), str(e))
_browser.available = real_avail
F.TRANSPORT = None
srv.shutdown()

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), FAILS)); sys.exit(1)
print("all browser-fetch checks passed")
