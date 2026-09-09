"""research/reddit.py — the one place anything in this agent asks Reddit anything.

WHY THIS MODULE EXISTS. Reddit refuses plain HTTP from an ordinary machine. Measured
2026-09-09 on the owner's laptop, six variations, every one a refusal: www.reddit.com
answers 403 Blocked to every user agent we tried, and old.reddit.com answers a LOGIN PAGE
carrying HTTP 200. That second one is the dangerous answer, because a login page with a
success code looks like a successful read of an empty community. brand/field_sources.py
believed it once and dropped all 18 real communities as dead (2026-09-04).

A real browser gets through. So every request here goes out through tools/_browser.py,
which warms the origin once with a real navigation and then runs an in-page fetch(), and
which already owns the two backends (the Sutra desktop shell when the app is running,
Playwright on a developer machine) and the single-worker thread discipline Playwright's
sync API demands. Proved 2026-09-09: live posts from r/recruiting through www.reddit.com's
search.json, top.json and comments.json.

THE THREE-STATE ANSWER. Every call here returns one of exactly three states, and the
distinction is the point of the module:

    "ok"       Reddit answered and there is something in it.
    "empty"    Reddit answered and there is genuinely nothing.
    "unknown"  We could not look. Blocked, login-walled, no browser, timed out, or the
               body was not data at all.

"Nobody talks about this" and "we could not look" are different facts. Collapsing them
makes a company look like it has no community when really we were the ones shut out, so
nothing in this module is allowed to report "empty" unless it parsed a real, empty listing.

WHAT THE CALLS RETURN.

    search(sub, query)  -> {"state", "reason", "url", "posts": [...]}
    top(sub)            -> {"state", "reason", "url", "posts": [...]}
    comments(post_id)   -> {"state", "reason", "url", "comments": [...]}
    exists(sub)         -> "yes" | "no" | "private" | "unknown"

A post:    id · subreddit · title · text · author · score · num_comments · created_utc · url · permalink
A comment: id · author · score · text · permalink

`exists` is here because a subreddit name that does not exist returns an EMPTY listing with
HTTP 200, exactly like a real community nobody posts in (checked 2026-09-09: r/zzzqqxnotarealsub
answers 200 with no children). about.json tells them apart: a real subreddit answers kind "t5",
a name that does not exist is redirected to a subreddit search and so answers a "Listing", and a
private one answers 403 with {"reason": "private"}.

RATE LIMIT. Reddit is being generous right now and a burst would end that, so MIN_INTERVAL
seconds pass between any two requests this process makes. Pacing is decided here and only
here; callers do not add their own sleeps.

Reads:  nothing on disk.
Writes: nothing on disk. It is a reader; the caller decides what to keep.
"""
import json
import os
import re
import threading
import time
import urllib.parse

from ..tools import _browser

HOST = "https://www.reddit.com"     # NOT old.reddit.com: it login-walls even a real browser
                                    # (re-checked 2026-09-09, it redirects to /login/?reason=lor2)
TIMEOUT = 45
MIN_INTERVAL = float(os.environ.get("SEO_AGENT_REDDIT_INTERVAL", "2.0"))   # seconds between requests
DEFAULT_LIMIT = 25
COMMENT_LIMIT = 10
TEXT_CHARS = 4000                   # selftext kept per post; enough to quote from, not a whole essay

# What a logged-out refusal looks like when it arrives as HTML with a 200.
LOGIN_MARKS = ("reason=lor2", "welcome to reddit", 'id="login-form"', "log in to continue",
               "please log in", "/login/?dest")

# The old.reddit search results markup: score and comment count for one result row. Kept because
# old.reddit HTML is still a Reddit surface a caller may hand us, and because reading it as counts
# rather than as a mystery page is what keeps "empty" honest.
_OLD_ROW = re.compile(r'<div class="[^"]*search-result search-result-link.*?'
                      r'<span class="search-score">([\d,]+) point.*?'
                      r'class="search-comments[^"]*"\s*>([\d,]+) comment', re.S)

_pace_lock = threading.Lock()
_last_call = [0.0]


# ---- the network seam ---------------------------------------------------------------------------

def _pace():
    """Sleep so no two Reddit requests from this process land less than MIN_INTERVAL apart.

    Held across the sleep on purpose: the crawler runs several workers, and a lock released
    before sleeping would let all of them wake together, which is the burst we are avoiding.
    """
    with _pace_lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def fetch(url):
    """One paced request through the browser. Returns {"status", "text", "url", "reason"}.

    Never raises. A caller degrades on a bad answer; it does not crash a four-hour run because
    Reddit hiccuped. Tests replace this function, which is also how no suite ever reaches
    reddit.com.
    """
    _pace()
    try:
        r = _browser.fetch(url, timeout=TIMEOUT)
    except _browser.NoBrowser as e:
        return {"status": 0, "text": "", "url": url, "reason": "no browser here: %s" % str(e)[:200]}
    except Exception as e:          # noqa: BLE001 - a timeout, a dead page, a closed context
        return {"status": 0, "text": "", "url": url, "reason": "the browser failed: %s" % str(e)[:200]}
    return {"status": int(r.get("status") or 0), "text": r.get("text") or "",
            "url": r.get("url") or url, "reason": ""}


def _body(got, url):
    """Normalise whatever the fetch seam handed back into {"status", "text", "reason"}.

    A seam may be replaced with something that returns a plain string body or None instead of the
    full dict: brand/field_sources.py's `fetch` does exactly that, because assets/trends.py has
    been calling it that way since before this module existed.
    """
    if got is None:
        return {"status": 0, "text": "", "url": url, "reason": "Reddit did not answer"}
    if isinstance(got, str):
        return {"status": 200, "text": got, "url": url, "reason": ""}
    return {"status": int(got.get("status") or 0), "text": got.get("text") or "",
            "url": got.get("url") or url, "reason": got.get("reason") or ""}


def _get(url, fetch_fn=None):
    return _body((fetch_fn or fetch)(url), url)


# ---- the urls, built in one place ----------------------------------------------------------------

def _q(s):
    return urllib.parse.quote(str(s or "").strip().strip("/"), safe="")


def search_url(subreddit, query, limit=DEFAULT_LIMIT, sort="top", period="year"):
    return ("%s/r/%s/search.json?q=%s&restrict_sr=on&sort=%s&t=%s&limit=%d"
            % (HOST, _q(subreddit), urllib.parse.quote(query or ""), sort, period, int(limit)))


def top_url(subreddit, limit=DEFAULT_LIMIT, period="year"):
    return "%s/r/%s/top.json?t=%s&limit=%d" % (HOST, _q(subreddit), period, int(limit))


def comments_url(post_id, limit=COMMENT_LIMIT, sort="top"):
    return "%s/comments/%s.json?limit=%d&sort=%s&depth=1" % (HOST, _q(post_id), int(limit), sort)


def about_url(subreddit):
    return "%s/r/%s/about.json" % (HOST, _q(subreddit))


# ---- reading what came back ----------------------------------------------------------------------

def _refused(text):
    low = (text or "")[:8000].lower()
    return any(m in low for m in LOGIN_MARKS)


def _post(d, subreddit=""):
    """One listing child into the post shape every caller in this repo uses."""
    d = d or {}
    permalink = str(d.get("permalink") or "")
    return {"id": str(d.get("id") or ""),
            "subreddit": str(d.get("subreddit") or subreddit or ""),
            "title": str(d.get("title") or ""),
            "text": str(d.get("selftext") or "")[:TEXT_CHARS],
            "author": str(d.get("author") or ""),
            "score": int(d.get("score") or 0),
            "num_comments": int(d.get("num_comments") or 0),
            "created_utc": float(d.get("created_utc") or 0),
            "url": ("https://www.reddit.com" + permalink) if permalink else str(d.get("url") or ""),
            "permalink": permalink}


def _children(payload):
    """The children of a Reddit listing, or None when this is not a listing at all."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    kids = data.get("children")
    return kids if isinstance(kids, list) else None


def _error_reason(payload, status):
    """The reason Reddit gave for refusing, when it refused in JSON."""
    if isinstance(payload, dict) and (payload.get("error") or payload.get("reason")):
        return "Reddit refused: %s (%s)" % (payload.get("reason") or payload.get("message") or "error",
                                            payload.get("error") or status)
    return ""


def parse_listing(body, status=200, subreddit=""):
    """A response body into {"state", "posts", "reason"}. The one place the verdict is decided.

    The order matters. JSON first, because that is what the live path asks for. Old-style HTML
    second, because a caller may hand us an old.reddit page and counting its results is better
    than calling it a mystery. Anything else is UNKNOWN, and that catch-all is what stops a
    login page from ever being read as an empty community.
    """
    text = body or ""
    if not text.strip():
        return {"state": "unknown", "posts": [], "reason": "Reddit sent an empty body"}
    payload = None
    try:
        payload = json.loads(text)
    except Exception:               # noqa: BLE001 - HTML, a truncated body, a challenge page
        payload = None

    if payload is not None:
        kids = _children(payload)
        if kids is not None:
            # ONLY kind "t3" IS A POST. Ask any listing endpoint for a subreddit that does not
            # exist and Reddit quietly answers with SUBREDDIT results, kind "t5", instead:
            # r/ExperiencedRecruiter's search.json and top.json both returned 8 t5 rows named
            # "googlejobs", "Accounting", "Oil and Gas Life" (measured 2026-09-09). Counted
            # blindly, a name nobody uses would score as eight live posts.
            posts = [_post(k.get("data"), subreddit) for k in kids
                     if isinstance(k, dict) and k.get("kind") == "t3"]
            if posts:
                return {"state": "ok", "posts": posts, "reason": ""}
            if kids:
                return {"state": "empty", "posts": [],
                        "reason": "Reddit answered with %d results and not one of them was a post" % len(kids)}
            return {"state": "empty", "posts": [], "reason": "Reddit answered with no results"}
        why = _error_reason(payload, status)
        return {"state": "unknown", "posts": [], "reason": why or "Reddit sent JSON that is not a listing"}

    if _refused(text):
        return {"state": "unknown", "posts": [],
                "reason": "Reddit served a login page (HTTP %s), so this could not be checked" % status}

    rows = _OLD_ROW.findall(text)
    if rows:
        posts = [{"id": "", "subreddit": subreddit, "title": "", "text": "", "author": "",
                  "score": int(s.replace(",", "")), "num_comments": int(c.replace(",", "")),
                  "created_utc": 0.0, "url": "", "permalink": ""} for s, c in rows]
        return {"state": "ok", "posts": posts, "reason": ""}
    if "search-result-link" in text or 'class="thing' in text:
        return {"state": "empty", "posts": [], "reason": "an old.reddit results page with no results"}
    if status >= 400:
        return {"state": "unknown", "posts": [], "reason": "Reddit answered HTTP %s" % status}
    return {"state": "unknown", "posts": [],
            "reason": "Reddit answered with a page, not data (HTTP %s), so this could not be checked" % status}


def parse_comments(body, status=200):
    """A comments-endpoint body into {"state", "comments", "reason"}.

    That endpoint answers with a LIST of two listings: [the post, the comment tree]. Anything
    else that parses as JSON is not the comments endpoint, and is unknown rather than empty.
    """
    text = body or ""
    if not text.strip():
        return {"state": "unknown", "comments": [], "reason": "Reddit sent an empty body"}
    try:
        payload = json.loads(text)
    except Exception:               # noqa: BLE001
        if _refused(text):
            return {"state": "unknown", "comments": [],
                    "reason": "Reddit served a login page (HTTP %s), so this could not be read" % status}
        return {"state": "unknown", "comments": [],
                "reason": "Reddit answered with a page, not data (HTTP %s)" % status}
    if isinstance(payload, dict):
        return {"state": "unknown", "comments": [],
                "reason": _error_reason(payload, status) or "Reddit sent JSON that is not a comment tree"}
    if not isinstance(payload, list) or len(payload) < 2:
        return {"state": "unknown", "comments": [], "reason": "Reddit sent JSON that is not a comment tree"}
    kids = _children(payload[1])
    if kids is None:
        return {"state": "unknown", "comments": [], "reason": "the comment tree had no children list"}
    out = []
    for k in kids:
        if not isinstance(k, dict) or k.get("kind") != "t1":     # t1 is a comment; "more" is a stub
            continue
        d = k.get("data") or {}
        text_ = str(d.get("body") or "").strip()
        if not text_ or text_ in ("[deleted]", "[removed]"):
            continue
        out.append({"id": str(d.get("id") or ""), "author": str(d.get("author") or ""),
                    "score": int(d.get("score") or 0), "text": text_[:TEXT_CHARS],
                    "permalink": str(d.get("permalink") or "")})
    out.sort(key=lambda c: -c["score"])
    if out:
        return {"state": "ok", "comments": out, "reason": ""}
    return {"state": "empty", "comments": [], "reason": "the post has no readable comments"}


# ---- the calls ------------------------------------------------------------------------------------

def search(subreddit, query, limit=DEFAULT_LIMIT, sort="top", period="year", fetch_fn=None):
    """Top posts in one subreddit matching a query. {"state", "posts", "reason", "url"}."""
    url = search_url(subreddit, query, limit, sort, period)
    got = _get(url, fetch_fn)
    r = parse_listing(got["text"], got["status"], subreddit)
    if r["state"] == "unknown" and got["reason"]:
        r["reason"] = got["reason"]
    r["url"] = url
    return r


def top(subreddit, limit=DEFAULT_LIMIT, period="year", fetch_fn=None):
    """The subreddit's top posts over a period. {"state", "posts", "reason", "url"}."""
    url = top_url(subreddit, limit, period)
    got = _get(url, fetch_fn)
    r = parse_listing(got["text"], got["status"], subreddit)
    if r["state"] == "unknown" and got["reason"]:
        r["reason"] = got["reason"]
    r["url"] = url
    return r


def comments(post_id, limit=COMMENT_LIMIT, sort="top", fetch_fn=None):
    """The top comments on one post, best score first. {"state", "comments", "reason", "url"}.

    Voices from the field needs the argument people had, not only the headline, which is why
    this exists at all.
    """
    url = comments_url(post_id, limit, sort)
    got = _get(url, fetch_fn)
    r = parse_comments(got["text"], got["status"])
    if r["state"] == "unknown" and got["reason"]:
        r["reason"] = got["reason"]
    r["url"] = url
    return r


def exists(subreddit, fetch_fn=None):
    """"yes" | "no" | "private" | "unknown" — is there a subreddit by this name?

    Only worth spending a request on when a search came back EMPTY, because that is the one
    moment where a wrong name and a quiet community look identical.
    """
    got = _get(about_url(subreddit), fetch_fn)
    try:
        payload = json.loads(got["text"] or "")
    except Exception:               # noqa: BLE001
        return "unknown"
    if not isinstance(payload, dict):
        return "unknown"
    if payload.get("kind") == "t5":
        return "yes"
    if payload.get("kind") == "Listing":
        # about.json for a real subreddit is always a t5. A name that does not exist gets
        # redirected to a SUBREDDIT SEARCH, so the answer is a Listing: empty for a name nothing
        # resembles, and full of t5 near-misses otherwise. Both mean the same thing, and reading
        # the second as "unknown" left r/ExperiencedRecruiter unexplained (2026-09-09).
        return "no"
    reason = str(payload.get("reason") or "").lower()
    if reason in ("private", "gold_only", "quarantined"):
        return "private"
    if reason in ("banned", "deleted"):
        return "no"
    return "unknown"
