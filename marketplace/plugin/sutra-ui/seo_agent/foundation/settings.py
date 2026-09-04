"""settings.py — every knob of the catalogue engine, in one place.

Engine knobs (rates, thresholds, timeouts) are method choices, not company facts, so they live
here as named constants and never in the company record. The comments are the original's: each
number was measured on a real site, and the measurement is the reason for the number.

Tests lower the sleeps (RATE_RPS, FIREWALL_COOLDOWN, BACKOFF_MAX, ARCHIVE_*) by assigning to this
module before a run; production never touches them except through the env overrides named here.
"""
import os

# ---- identity --------------------------------------------------------------------------------
# A real browser string, not a bot label. The first live run (testlify.com, 2026-09-03) got a 429
# on the very first request with "(compatible; seo-agent/1.0 ...)": the site's edge refuses
# anything that announces itself as a crawler, before a single page is read. This is the user
# indexing their OWN site, so presenting as the browser they would use to read it is the honest
# thing, and the rate limit below keeps it polite.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA,
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "en-US,en;q=0.9"}

# ---- fetch politeness (the original's Stage 2) ------------------------------------------------
RATE_RPS = float(os.environ.get("SEO_AGENT_RATE_RPS", "1.5"))
                            # token bucket: requests/sec PER HOST (measured: 8 workers dropped 46%
                            # of requests; ~1.3 r/s tripped a firewall on one site — this is the
                            # agent's default, env-tunable when a site asks for slower)
FETCH_WORKERS = 6           # parallel frontier workers. Workers do NOT raise req/s — RATE_RPS still
                            # governs that; they stop one slow page blocking the queue. Serial
                            # measured 1.0 pages/s against a 2.5/s allowance, so the loop, not
                            # politeness, was the cap.
FETCH_CONCURRENCY = max(3, FETCH_WORKERS)   # in-flight cap (semaphore); must not throttle the
                            # workers below their own count, or they queue on each other
FETCH_TIMEOUT = 30          # seconds per request
FETCH_ATTEMPTS = 6          # retries on 429/5xx/timeouts only (full-jitter backoff)
BACKOFF_BASE = 1.0          # full-jitter exponential: sleep uniform(0, min(BACKOFF_MAX, BASE*2^n))
BACKOFF_MAX = 30.0
RETRY_AFTER_CAP = 300       # the longest Retry-After we honour, seconds
FIREWALL_COOLDOWN = 120     # seconds to sit out after a 403/block signal before retrying
BLOCK_HEADER = "cf-mitigated"   # Cloudflare sets this when it challenged/blocked the request
BLOCK_COOLDOWNS = 3         # cooldowns per URL before it is given up as Blocked
SLOWDOWN_CAP = 8.0          # firewall pushback doubles the per-host spacing, up to this many seconds
# A host that has firewalled us this many times IN A ROW is written off for the rest of the run:
# its remaining URLs fail instantly instead of each paying a full cooldown (measured 2026-07-20:
# 262 pages x 8s = 35 wasted minutes on a site that would never answer).
BLOCK_GIVE_UP = 5
CIRCUIT_BREAK = 40          # this many pages failing to fetch IN A ROW = the site is down or
                            # throttling us; stop the fetch pass loudly rather than grind on
ROBOTS_DELAY_CAP = 30       # obey a Crawl-delay, but never slower than this

# ---- enumeration (Stage 3) --------------------------------------------------------------------
WP_PER_PAGE = 100           # WP REST page size (101 -> HTTP 400)
SITEMAP_DEPTH_CAP = 5       # nested sitemap-index recursion cap (with cycle detection)
ARCHIVE_MAX_PER_MIN = 55    # public-archive query ceiling (60/min hard; blocks double on repeat)
ARCHIVE_429_SLEEP = 70      # seconds to sit out when the archive says slow down
ARCHIVE_PAGE_LIMIT = 50000  # CDX rows per index page
ARCHIVE_TIMEOUT = 60        # seconds per CDX call
LIVENESS_ATTEMPTS = 2       # a liveness HEAD asks "does this answer NOW", so the content-fetch
LIVENESS_TIMEOUT = 8        # retry ladder (6 x 30s + backoff) is the wrong shape: it can spend
                            # MINUTES per dead URL proving what one quick probe already showed.
                            # 2 attempts still absorbs a single blip, so a live page is not
                            # mislabelled dead by one hiccup.
LIVENESS_WORKERS = FETCH_CONCURRENCY   # probes run in parallel up to the in-flight cap; the
                            # token bucket still owns the RATE, so this cannot raise req/s
ARCHIVE_LIVENESS_CAP = 5000  # the agent probes at most this many archive-only URLs live; the rest
                            # are recorded as UNCHECKED, never assumed alive
CRAWL_IF_UNDER = 200        # other layers found fewer distinct URLs than this -> crawl kicks in
CRAWL_MAX_PAGES = 5000      # hard page budget for the link crawl
CRAWL_DEPTH_CAP = 6         # hops from the homepage
CANONICAL_HOP_CAP = 5       # rel=canonical chain cap; beyond -> UNRESOLVED, never guessed
FAN_IN_ALERT = 20           # one canonical target absorbing more aliases than this = flagged bug
SOFT404_MIN_CLUSTER = 5     # identical small bodies across at least this many URLs
SOFT404_MAX_WORDS = 150

# ---- extraction (Stage 4) ---------------------------------------------------------------------
EXTRACT_FAIL_CHARS = 250    # below this = failed -> escalate to the next ladder rung
EXTRACT_STUB_CHARS = 400    # 250-400 = genuine stub, recorded as such
FLAG_MEDIAN_FRAC = 0.25     # body < 25% of its type's median -> flagged for review
REST_MIN_SHARE = 0.5        # the CMS-returned body is accepted outright only if it is at least
                            # this share of the LIVE page's text. Below it the CMS field is a
                            # fragment (page-builder sites often expose only the FAQ block) and
                            # the live-HTML text is tried instead — the CMS body still competes,
                            # so it wins whenever the extractors do no better.
DEBOILER_FRAC = 0.75        # a line on >= this fraction of a LANGUAGE's pages is chrome, removed
DEBOILER_MIN_PAGES = 8      # a language group smaller than this has too little repetition signal
BODY_CHARS = 400            # the `text` preview kept on the light row (older code reads it)
KEYWORDS_PER_PAGE = 100     # ranking keywords kept per page on the light row

# ---- traffic (Stage 5) ------------------------------------------------------------------------
DFS_LIMIT = 1000            # ranked_keywords page size (bulk, never per-page: $2.50 vs $35.80)
TRAFFIC_MAX_ROWS = 50000    # loud safety ceiling on the paginated pull (never a silent cap)
MIN_CREDITS = 0.50          # pre-flight balance guard ($). CONTRACTS rule 3: below this, skip the
                            # paid pull and say so; never crash, never ask.

# ---- gates (Stage 6) --------------------------------------------------------------------------
GATE_OVERALL = 0.95         # the catalogue is not trusted below 95% extraction coverage overall
GATE_PER_TYPE = 0.90        # or below 90% for any single page type
