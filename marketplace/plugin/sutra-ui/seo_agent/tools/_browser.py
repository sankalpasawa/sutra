"""_browser.py — fetch through a real browser when a site's bot challenge refuses plain requests.

Not a tool. The crawler calls this when a page answers with a JavaScript challenge
(Vercel "Attack Challenge Mode", Cloudflare "Under Attack", and their kin). Those pages
return 429 or 403 with a marker header and a shell of HTML that only a browser running
JavaScript can get past. Cookies do not carry over to plain requests: the pass is bound
to the browser's own network fingerprint. So every page of such a site has to go through
a browser, and this is the one place that happens.

Measured on testlify.com (Next.js on Vercel, 2026-09-03): one navigation to the homepage
clears the challenge in ~4.6s; after that, in-page `fetch()` calls from that page return
raw bodies (HTML, XML sitemaps, robots.txt) in 0.05–0.35s each, and a burst of six did not
re-arm it. In-page fetch, not page navigation, is the trick: a browser renders XML through
a viewer, but fetch() hands back the bytes.

Two backends, in order:
  1. The Sutra desktop shell. Electron IS Chromium. main.js runs a loopback fetch service
     with a hidden window per origin and hands the backend its address in
     SEO_AGENT_BROWSER_FETCH plus a token in SEO_AGENT_BROWSER_TOKEN. Nothing to install.
  2. Playwright, when importable (a developer machine). One browser per process.
Neither available -> NoBrowser, and the crawler says so plainly instead of pretending the
site is empty.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

TIMEOUT = 60
CHALLENGE_HEADERS = (("x-vercel-mitigated", "challenge"), ("cf-mitigated", "challenge"))
CHALLENGE_BODY = ("cf-chl", "_cf_chl_opt", "challenge-platform", "vercel-challenge", "x-vercel-challenge-token",
                  "Just a moment", "Verifying you are human", "Checking your browser")
SETTLE_TRIES = 10          # in-page fetch retries while the challenge is still clearing
SETTLE_SLEEP = 1.5

# The same fetch the shell runs; kept here so both backends behave identically.
IN_PAGE_FETCH = """async (u) => {
  const r = await fetch(u, {credentials: 'include', redirect: 'follow'});
  const t = await r.text();
  const h = {}; r.headers.forEach((v, k) => { h[k] = v; });
  return {status: r.status, url: r.url, text: t, content_type: r.headers.get('content-type') || '', headers: h};
}"""


class NoBrowser(Exception):
    pass


def challenged(status, headers, body=b""):
    """Is this answer a bot challenge rather than the page? Header markers first, then the
    well-known strings in the body, and only for the two codes challenges use."""
    if status not in (403, 429, 503):
        return False
    h = {str(k).lower(): str(v).lower() for k, v in (headers or {}).items()}
    for k, v in CHALLENGE_HEADERS:
        if v in h.get(k, ""):
            return True
    if isinstance(body, bytes):
        body = body[:6000].decode("utf-8", "ignore")
    body = (body or "")[:6000]
    return any(m.lower() in body.lower() for m in CHALLENGE_BODY)


def available():
    """'shell' | 'playwright' | None"""
    if (os.environ.get("SEO_AGENT_BROWSER_FETCH") or "").strip():
        return "shell"
    try:
        import playwright.sync_api  # noqa: F401
        return "playwright"
    except Exception:
        return None


def fetch(url, timeout=TIMEOUT):
    """{"status", "url", "text", "content_type", "headers"} for one URL, via the browser."""
    kind = available()
    if kind == "shell":
        return _shell_fetch(url, timeout)
    if kind == "playwright":
        return _PW.fetch(url, timeout)
    raise NoBrowser("This site sits behind a bot challenge that only a real browser can pass, and no "
                    "browser is available here. Inside the Sutra app the app's own window does it; "
                    "on a developer machine, `pip install playwright && playwright install chromium`.")


# ---- backend 1: the desktop shell ------------------------------------------------------------

def _shell_fetch(url, timeout):
    base = (os.environ.get("SEO_AGENT_BROWSER_FETCH") or "").rstrip("/")
    token = os.environ.get("SEO_AGENT_BROWSER_TOKEN") or ""
    req = urllib.request.Request(base + "/fetch", data=json.dumps({"url": url, "timeout": int(timeout)}).encode(),
                                 headers={"Content-Type": "application/json", "X-Sutra-Browser": token})
    try:
        with urllib.request.urlopen(req, timeout=timeout + 15) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise NoBrowser("the app's browser fetch refused (%d): %s" % (e.code, e.read()[:200].decode("utf-8", "ignore")))
    except Exception as e:  # noqa: BLE001
        raise NoBrowser("the app's browser fetch did not answer: %s" % str(e)[:120])
    if "status" not in d:
        raise NoBrowser("the app's browser fetch returned no status: %s" % json.dumps(d)[:160])
    return {"status": int(d["status"]), "url": d.get("url") or url, "text": d.get("text") or "",
            "content_type": d.get("content_type") or "", "headers": d.get("headers") or {}}


# ---- backend 2: Playwright ---------------------------------------------------------------------

class _Playwright:
    """One browser for the process, driven from ONE dedicated thread.

    Playwright's sync API is bound to the thread that created it: a page made on thread A
    cannot be used from thread B ("cannot switch to a different thread"). The crawler runs
    six workers, so every browser call is posted to a single worker thread through a queue
    and the caller waits on its result. One page per origin, kept once it has cleared the
    challenge. Measured on the first live run: with a plain lock instead of this, 12 of the
    first 19 pages failed and the read stalled.
    """

    def __init__(self):
        self._q = None
        self._thread = None
        self._start_lock = threading.Lock()

    def _ensure_thread(self):
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                import queue
                self._q = queue.Queue()
                self._thread = threading.Thread(target=self._loop, name="seo-agent:browser", daemon=True)
                self._thread.start()

    def _loop(self):
        from playwright.sync_api import sync_playwright
        pw = browser = None
        pages = {}                      # origin -> page that has cleared the challenge
        while True:
            job = self._q.get()
            if job is None:
                break
            url, timeout, fut = job
            try:
                if browser is None:
                    pw = sync_playwright().start()
                    browser = pw.chromium.launch(headless=True)
                parts = urlsplit(url)
                origin = "%s://%s" % (parts.scheme, parts.netloc)
                page = pages.get(origin)
                if page is None or page.is_closed():
                    ctx = browser.new_context(user_agent=_UA)
                    page = ctx.new_page()
                    page.goto(origin + "/", wait_until="domcontentloaded", timeout=int(timeout * 1000))
                    pages[origin] = page
                last = None
                for _ in range(SETTLE_TRIES):
                    try:
                        r = page.evaluate(IN_PAGE_FETCH, url)
                    except Exception as e:  # noqa: BLE001 -- the page may still be mid-challenge
                        last = {"status": 0, "url": url, "text": "", "content_type": "", "headers": {},
                                "error": str(e)[:160]}
                        time.sleep(SETTLE_SLEEP)
                        continue
                    if not challenged(r.get("status"), r.get("headers"), r.get("text", "")):
                        last = r
                        break
                    last = r
                    time.sleep(SETTLE_SLEEP)
                fut.set_result(last)
            except Exception as e:  # noqa: BLE001
                # a broken browser must not poison every later call: drop it and relaunch next time
                try:
                    if browser is not None:
                        browser.close()
                    if pw is not None:
                        pw.stop()
                except Exception:
                    pass
                pw = browser = None
                pages = {}
                fut.set_exception(NoBrowser("the browser failed on %s: %s" % (url, str(e)[:160])))

    def fetch(self, url, timeout):
        from concurrent.futures import Future
        self._ensure_thread()
        fut = Future()
        self._q.put((url, timeout, fut))
        return fut.result(timeout=timeout + 60)


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
_PW = _Playwright()


def strip_challenge_marker(text):
    """For logs only: the first line of a challenge page, so a note can name what answered."""
    m = re.search(r"<title>([^<]{0,80})</title>", text or "", re.I)
    return m.group(1).strip() if m else ""
