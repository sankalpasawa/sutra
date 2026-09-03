"""fetch.py — polite, resumable HTTP for the site being catalogued. Everything else depends on this.

Reads:  settings (rate, identity). The target site's robots.txt governs what we touch.
Writes: knowledge/_raw/<sha[:2]>/<sha>.<ext>   (content-addressed raw payload cache, atomic)
        knowledge/_work/catalogue.sqlite       (pages: url -> sha/status/final_url; frontier: resume)

The rules, all measured on real sites:
- ONE token bucket PER HOST owns the request rate. Concurrency never raises the rate: 8 workers
  once dropped 46% of requests, and ~1.3 r/s tripped a firewall. One hostile host must only ever
  slow ITSELF, never the run (a shared bucket once dragged 24 sites to 8s/page).
- Retries on timeouts / transport errors / 429 / 5xx ONLY, full-jitter backoff, honouring
  Retry-After. A 403 or a cf-mitigated header = FIREWALL BLOCK: sit out a long cooldown,
  permanently slow the bucket, retry a little, then raise Blocked. Never silence.
- Cache the raw payload, not the HTTP transaction: fetch once, re-parse offline forever. A cached
  URL is served with ZERO network calls, so an extractor change never refetches a page.
- The frontier hands out work under one lock, so a killed run resumes exactly where it stopped
  and two workers can never claim the same URL.

Tests point TRANSPORT at an httpx.MockTransport before building a Fetcher; nothing else changes.
"""
import hashlib
import json
import os
import random
import re
import sqlite3
import threading
import time
import urllib.parse as _up

import httpx

from ..tools import _browser

from .. import store
from . import settings
from .urls import host_of

TRANSPORT = None          # tests set an httpx.MockTransport here; production leaves it None


class Blocked(Exception):
    """The site's firewall is refusing us (403 / cf-mitigated) and the cooldowns didn't clear it.
    Loud by design — a block must be reported, never read as 'page empty'."""


class RobotsDisallowed(Exception):
    """robots.txt forbids this URL. We do not fetch it."""


class FetchFailed(Exception):
    """Retries exhausted. .status is the last HTTP status the server answered with, or 0 when no
    answer ever reached us (timeout, DNS, connection reset). The distinction is load-bearing:
    a server that answered 500 is the site's own data; our dead network is not."""

    def __init__(self, msg, status=0, resp=None):
        super().__init__(msg)
        self.status = status
        self.resp = resp


class FetchResult:
    __slots__ = ("url", "final_url", "status", "content", "content_type", "headers", "from_cache")

    def __init__(self, url, final_url, status, content, content_type, headers, from_cache):
        self.url, self.final_url, self.status = url, final_url, status
        self.content, self.content_type = content, content_type
        self.headers, self.from_cache = headers, from_cache

    @property
    def text(self):
        return self.content.decode("utf-8", "ignore") if self.content else ""


# Headers worth keeping for cached responses (stored lowercase). X-WP-Total lets the WP layer
# assert coverage OFFLINE from cache; Link carries rel=canonical; Content-Length feeds gate 2.
KEPT_HEADERS = ("x-wp-total", "x-wp-totalpages", "link", "content-length", "content-encoding")


# ---- robots.txt, the minimal honest reader ---------------------------------------------------

class Robots:
    """The `*` group of a robots.txt: Allow/Disallow with `*` and `$`, longest match wins, an
    Allow wins a tie. Plus Crawl-delay and every Sitemap: line (some sites publish 8)."""

    def __init__(self, text=""):
        self.sitemaps, self.rules, self.crawl_delay = [], [], None
        groups, cur, saw_agent = [], None, False
        for raw in (text or "").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, _, value = line.partition(":")
            field, value = field.strip().lower(), value.strip()
            if field == "sitemap":
                if value:
                    self.sitemaps.append(value)
                continue
            if field == "user-agent":
                if cur is None or not saw_agent:
                    cur = {"agents": [], "rules": [], "delay": None}
                    groups.append(cur)
                    saw_agent = True
                cur["agents"].append(value.lower())
                continue
            if cur is None:
                continue
            saw_agent = False
            if field in ("allow", "disallow"):
                cur["rules"].append((field == "allow", value))
            elif field == "crawl-delay":
                try:
                    cur["delay"] = float(value)
                except ValueError:
                    pass
        for g in groups:
            if "*" in g["agents"]:
                self.rules = [(a, p) for a, p in g["rules"] if p or a]
                self.crawl_delay = g["delay"]
                break

    @staticmethod
    def _rx(pattern):
        rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern.rstrip("$"))
        return re.compile("^" + rx + ("$" if pattern.endswith("$") else ""))

    def can_fetch(self, url):
        try:
            parts = _up.urlsplit(url)
        except ValueError:
            return True
        path = (parts.path or "/") + (("?" + parts.query) if parts.query else "")
        best = None                        # (length, allow)
        for allow, pat in self.rules:
            if not pat:
                continue                   # "Disallow:" with nothing = allow everything
            if self._rx(pat).match(path):
                cand = (len(pat), allow)
                if best is None or cand[0] > best[0] or (cand[0] == best[0] and allow):
                    best = cand
        return True if best is None else best[1]


# ---- the token bucket — the ONE owner of a host's request rate --------------------------------

class _Bucket:
    def __init__(self, rps):
        self.delay = 1.0 / max(rps, 0.05)
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.monotonic()
            wake = max(now, self._next)
            self._next = wake + self.delay
        time.sleep(max(0.0, wake - time.monotonic()))

    def slower(self):
        """Firewall pushback: permanently double the spacing (capped). Delay only ever grows."""
        with self._lock:
            self.delay = min(settings.SLOWDOWN_CAP, self.delay * 2)
        return self.delay


def _raw_path(raw_dir, sha, content_type):
    ext = ".html"
    ct = (content_type or "").lower()
    if "xml" in ct:
        ext = ".xml"
    elif "json" in ct:
        ext = ".json"
    elif "html" not in ct and ct:
        ext = ".bin"
    return os.path.join(raw_dir, sha[:2], sha + ext)


def _write_bytes(path, data):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")     # SAME dir -> the rename is atomic
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


class Fetcher:
    """One per run. `get` serves from the cache with zero network calls when it can."""

    def __init__(self, work_dir, raw_dir, on_event=None):
        self.work_dir, self.raw_dir = work_dir, raw_dir
        os.makedirs(work_dir, exist_ok=True)
        os.makedirs(raw_dir, exist_ok=True)
        self.say = on_event or (lambda label, note="": None)
        self.client = httpx.Client(headers=dict(settings.HEADERS), timeout=settings.FETCH_TIMEOUT,
                                   follow_redirects=True, transport=TRANSPORT)
        self.stats = {"network": 0, "cache": 0, "retries": 0, "cooldowns": 0, "fetch_failed": 0}
        self._buckets, self._buckets_lock = {}, threading.Lock()
        self._robots, self._robots_lock = {}, threading.Lock()
        self._dead, self._dead_lock = {}, threading.Lock()
        self._browser_hosts = set()       # hosts whose bot challenge sent us through a real browser
        self._sem = threading.BoundedSemaphore(settings.FETCH_CONCURRENCY)
        self._db_lock = threading.RLock()
        self._db = sqlite3.connect(os.path.join(work_dir, "catalogue.sqlite"), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        # WAL's documented companion. FULL fsyncs on EVERY commit and the frontier commits ~3x per
        # page behind one lock — measured 2026-07-19 as the real ceiling once fetching went
        # parallel. NORMAL cannot corrupt the DB in WAL mode; a power cut may lose the last few
        # transactions, which here means a few pages revert to 'pending' and are re-fetched.
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS pages(
            url TEXT PRIMARY KEY, sha TEXT, status INTEGER, content_type TEXT,
            final_url TEXT, fetched_at REAL, kept_headers TEXT DEFAULT '')""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS frontier(
            url TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, claimed_at REAL, error TEXT)""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS archive_liveness(
            url TEXT PRIMARY KEY, alive INTEGER, status INTEGER, final_url TEXT)""")
        self._db.commit()

    def close(self):
        try:
            self.client.close()
        finally:
            with self._db_lock:
                self._db.close()

    # ---- sqlite plumbing, shared with the stages that persist their own resume state ---------
    def db(self, sql, params=(), fetch="none"):
        with self._db_lock:
            cur = self._db.execute(sql, params)
            out = cur.fetchall() if fetch == "all" else (cur.fetchone() if fetch == "one" else None)
            self._db.commit()
            return out

    def dbmany(self, sql, rows):
        with self._db_lock:
            self._db.executemany(sql, rows)
            self._db.commit()

    # ---- per-host state -------------------------------------------------------------------------
    def _bucket(self, url):
        host = host_of(url)
        with self._buckets_lock:
            b = self._buckets.get(host)
            if b is None:
                b = self._buckets[host] = _Bucket(settings.RATE_RPS)
            return b

    def _note_block(self, host):
        with self._dead_lock:
            self._dead[host] = self._dead.get(host, 0) + 1
            return self._dead[host]

    def _note_success(self, host):
        with self._dead_lock:
            self._dead.pop(host, None)

    def host_given_up(self, url):
        with self._dead_lock:
            return self._dead.get(host_of(url), 0) >= settings.BLOCK_GIVE_UP

    def robots_for(self, url):
        """robots.txt for the URL's host, fetched once, Crawl-delay obeyed (capped)."""
        parts = _up.urlsplit(url)
        host = (parts.netloc or "").lower()
        with self._robots_lock:
            if host in self._robots:
                return self._robots[host]
        robots_url = "%s://%s/robots.txt" % (parts.scheme or "https", host)
        try:
            self._bucket(url).wait()
            r = self.client.get(robots_url)
            self.stats["network"] += 1
            rp = Robots(r.text) if r.status_code == 200 else Robots("")
        except httpx.HTTPError:
            rp = Robots("")          # unreachable robots = allow (standard); the fetch itself will tell
        b = self._bucket(url)
        if rp.crawl_delay and rp.crawl_delay > b.delay:
            b.delay = float(min(rp.crawl_delay, settings.ROBOTS_DELAY_CAP))
        with self._robots_lock:
            self._robots[host] = rp
        return rp

    def sitemaps_from_robots(self, root):
        return list(self.robots_for(root.rstrip("/") + "/").sitemaps)

    # ---- the cache ------------------------------------------------------------------------------
    def cached(self, url):
        row = self.db("SELECT sha, status, content_type, final_url, kept_headers FROM pages WHERE url=?",
                      (url,), fetch="one")
        if not row:
            return None
        sha, status, ctype, final_url, kept = row
        path = _raw_path(self.raw_dir, sha, ctype) if sha else None
        if sha and not os.path.exists(path):
            return None                      # cache row without payload — treat as uncached
        content = open(path, "rb").read() if sha else b""
        headers = json.loads(kept) if kept else {}
        return FetchResult(url, final_url or url, status, content, ctype, headers, True)

    def cached_meta(self, url):
        """(sha, status, content_type, kept_headers) for the integrity gate, or None."""
        row = self.db("SELECT sha, status, content_type, kept_headers FROM pages WHERE url=?",
                      (url,), fetch="one")
        return row

    def raw_path(self, sha, content_type):
        return _raw_path(self.raw_dir, sha, content_type)

    def _store(self, url, resp):
        body = resp.content or b""
        ctype = resp.headers.get("content-type", "")
        sha = ""
        if body:
            sha = hashlib.sha256(body).hexdigest()
            _write_bytes(_raw_path(self.raw_dir, sha, ctype), body)
        kept = json.dumps({k: resp.headers[k] for k in KEPT_HEADERS if k in resp.headers})
        self.db("INSERT OR REPLACE INTO pages(url, sha, status, content_type, final_url, fetched_at, kept_headers) "
                "VALUES(?,?,?,?,?,?,?)",
                (url, sha, resp.status_code, ctype, str(resp.url), time.time(), kept))

    # ---- one rate-limited round trip, with the retry ladder -------------------------------------
    def _is_block(self, resp):
        return resp.status_code == 403 or settings.BLOCK_HEADER in resp.headers

    def network(self, url, method="GET", attempts=None, timeout=None):
        """Retries timeouts / transport errors / 429 / 5xx with full-jitter backoff, honouring
        Retry-After. Block handling (403/cf-mitigated) lives in get(). Raises FetchFailed when the
        ladder is exhausted, carrying the last answered status (0 = never reached the server)."""
        attempts = attempts or settings.FETCH_ATTEMPTS
        last_resp, last_err = None, ""
        for n in range(attempts):
            self._bucket(url).wait()
            try:
                kw = {"timeout": timeout} if timeout else {}
                resp = self.client.request(method, url, **kw)
            except httpx.HTTPError as e:
                last_err = "%s: %s" % (type(e).__name__, str(e)[:120])
            else:
                self.stats["network"] += 1
                if _browser.challenged(resp.status_code, resp.headers, resp.content):
                    return resp            # a bot challenge: retrying plain HTTP cannot pass it; get() decides
                if resp.status_code == 429 or resp.status_code >= 500:
                    retry_after = (resp.headers.get("retry-after") or "").strip()
                    if retry_after.isdigit():
                        time.sleep(min(int(retry_after), settings.RETRY_AFTER_CAP))
                    self.stats["retries"] += 1
                    # Keep the response: if the retries exhaust, the caller must be able to tell
                    # "the server ANSWERED 500" from "we never reached the server".
                    last_resp, last_err = resp, "HTTP %d (retryable)" % resp.status_code
                else:
                    return resp
            if n + 1 < attempts:
                time.sleep(random.uniform(0.0, min(settings.BACKOFF_MAX, settings.BACKOFF_BASE * (2 ** n))))
        raise FetchFailed(last_err or "no response", last_resp.status_code if last_resp is not None else 0,
                          last_resp)

    def get(self, url, force=False, obey_robots=True, attempts=None):
        """Fetch a URL through the cache. Returns FetchResult.

        - cached & not force -> served from disk, ZERO network calls
        - force -> unconditional refetch, replaces the cache
        - 403/cf-mitigated -> cooldown + slower bucket, few retries, then raises Blocked
        - retries exhausted -> a FetchResult with status 0 (no answer) or the answered 5xx,
          NOT cached, so a later run retries. One bad URL must never end a whole-site run.
        """
        hit = None if force else self.cached(url)
        if hit:
            self.stats["cache"] += 1
            return hit
        if obey_robots and not self.robots_for(url).can_fetch(url):
            raise RobotsDisallowed(url)
        if self.host_given_up(url):
            raise Blocked("%s — abandoned after %d blocks in a row" % (host_of(url), settings.BLOCK_GIVE_UP))

        with self._sem:
            cooldowns = 0
            while True:
                if host_of(url) in self._browser_hosts:
                    resp = self._browser_get(url)
                    break
                try:
                    resp = self.network(url, attempts=attempts)
                except FetchFailed as e:
                    self.stats["fetch_failed"] += 1
                    return FetchResult(url, url, e.status, b"", "", {"_fetch_error": str(e)[:200]}, False)
                if _browser.challenged(resp.status_code, resp.headers, resp.content):
                    # The site runs a JavaScript bot challenge. Cooldowns cannot clear it and
                    # neither can cookies; only a real browser can. Switch this host to the
                    # browser for the rest of the run, and say so once.
                    if _browser.available():
                        self._browser_hosts.add(host_of(url))
                        self.say("The site runs a bot challenge",
                                 "%s answered every plain request with HTTP %d. Reading it through a real "
                                 "browser from here on (%s)." % (host_of(url), resp.status_code, _browser.available()))
                        resp = self._browser_get(url)
                        break
                    raise Blocked("%s runs a bot challenge (HTTP %d, %s) and no browser is available to pass "
                                  "it. Inside the Sutra app this works through the app's own window."
                                  % (host_of(url), resp.status_code, _browser.strip_challenge_marker(
                                      resp.content[:6000].decode("utf-8", "ignore")) or "challenge page"))
                if self._is_block(resp):
                    cooldowns += 1
                    self.stats["cooldowns"] += 1
                    if cooldowns > settings.BLOCK_COOLDOWNS:
                        n = self._note_block(host_of(url))
                        if n >= settings.BLOCK_GIVE_UP:
                            self.say("Gave up on %s" % host_of(url),
                                     "it blocked %d requests in a row; its remaining pages are recorded as unread" % n)
                        raise Blocked("%s — still blocked after %d cooldowns (HTTP %d, %s=%s)"
                                      % (url, cooldowns - 1, resp.status_code, settings.BLOCK_HEADER,
                                         resp.headers.get(settings.BLOCK_HEADER, "-")))
                    delay = self._bucket(url).slower()
                    self.say("The site's firewall pushed back",
                             "waiting %ds before trying %s again, and slowing to one request every %.1fs"
                             % (settings.FIREWALL_COOLDOWN, url, delay))
                    self._sem.release()               # do NOT hold a slot while sleeping —
                    try:                              # it starves every other worker
                        time.sleep(settings.FIREWALL_COOLDOWN)
                    finally:
                        self._sem.acquire()
                    continue
                break

        self._note_success(host_of(url))
        self._store(url, resp)
        # Lowercase keys, like the cached form, so a stage reads x-wp-total the same way whether
        # the page came from the wire or the disk.
        return FetchResult(url, str(resp.url), resp.status_code, resp.content,
                           resp.headers.get("content-type", ""),
                           {k.lower(): v for k, v in resp.headers.items()}, False)

    def _browser_get(self, url):
        """One page through the browser, returned as an httpx.Response so the cache and every
        caller see the same shape as a plain fetch. The bucket still paces it."""
        self._bucket(url).wait()
        try:
            r = _browser.fetch(url)
        except _browser.NoBrowser as e:
            raise Blocked(str(e))
        self.stats["network"] += 1
        headers = {str(k).lower(): str(v) for k, v in (r.get("headers") or {}).items()}
        if r.get("content_type"):
            headers["content-type"] = r["content_type"]
        headers["x-sutra-fetched-via"] = "browser"
        body = (r.get("text") or "").encode("utf-8")
        resp = httpx.Response(int(r.get("status") or 0), headers=headers, content=body,
                              request=httpx.Request("GET", r.get("url") or url))
        return resp

    def head(self, url, obey_robots=True):
        """Liveness probe (archive layer). No cache — a HEAD answers 'does it exist NOW'.

        Deliberately NOT on the content-fetch retry ladder: a probe only asks whether the URL
        answers right now, and a URL that needs six retries across minutes is not a live page.
        Measured 2026-07-19: the full ladder dragged archive liveness to 0.42 req/s."""
        if obey_robots and not self.robots_for(url).can_fetch(url):
            raise RobotsDisallowed(url)
        with self._sem:
            if host_of(url) in self._browser_hosts:
                # A challenged host answers HEAD with the challenge too, so "gone" would be a lie
                # (measured: 300 of 300 archived pages read as gone on the first live run). Ask the
                # browser instead; a GET's status is the liveness answer.
                return self._browser_get(url)
            resp = self.network(url, method="HEAD", attempts=settings.LIVENESS_ATTEMPTS,
                                timeout=settings.LIVENESS_TIMEOUT)
            if _browser.challenged(resp.status_code, resp.headers, resp.content) and _browser.available():
                self._browser_hosts.add(host_of(url))
                return self._browser_get(url)
            return resp

    def plain_get(self, url, params=None, timeout=None):
        """A GET outside the site's token bucket, for APIs with their own published ceiling
        (the web archive). No cache, no retries; the caller owns the pacing."""
        r = self.client.get(url, params=params, timeout=timeout or settings.FETCH_TIMEOUT)
        self.stats["network"] += 1
        return r

    # ---- the frontier: resumable work-queue with an atomic claim --------------------------------
    def frontier_add(self, urls):
        self.dbmany("INSERT OR IGNORE INTO frontier(url) VALUES(?)", [(u,) for u in urls])

    def frontier_retry_failed(self, urls):
        """A failed fetch is not cached, so a re-run may try it again. Resets only THIS run's URLs."""
        self.dbmany("UPDATE frontier SET state='pending', error=NULL WHERE url=? AND state='failed'",
                    [(u,) for u in urls])

    def frontier_reset(self, urls):
        self.dbmany("UPDATE frontier SET state='pending', error=NULL, attempts=0 WHERE url=?",
                    [(u,) for u in urls])

    def frontier_claim(self, urls_filter=None, stale_after=900):
        """Atomically claim one pending URL (or reclaim one stuck in_progress > stale_after seconds).
        Returns the URL or None when the frontier is drained. The claim happens under the db lock,
        so two workers can never take the same URL."""
        now = time.time()
        with self._db_lock:                 # select + update under ONE lock = an atomic claim,
            row = self._db.execute(         # without needing sqlite's RETURNING (3.35+)
                "SELECT url FROM frontier WHERE state='pending' "
                "OR (state='in_progress' AND claimed_at < ?) LIMIT 1", (now - stale_after,)).fetchone()
            if not row:
                return None
            self._db.execute("UPDATE frontier SET state='in_progress', claimed_at=?, attempts=attempts+1 "
                             "WHERE url=?", (now, row[0]))
            self._db.commit()
            return row[0]

    def frontier_done(self, url):
        self.db("UPDATE frontier SET state='done', error=NULL WHERE url=?", (url,))

    def frontier_fail(self, url, error):
        self.db("UPDATE frontier SET state='failed', error=? WHERE url=?", (str(error)[:500], url))

    def frontier_states(self, urls):
        """{url: (state, error)} for the given URLs."""
        out = {}
        rows = self.db("SELECT url, state, error FROM frontier", fetch="all")
        want = set(urls)
        for u, s, e in rows:
            if u in want:
                out[u] = (s, e or "")
        return out
