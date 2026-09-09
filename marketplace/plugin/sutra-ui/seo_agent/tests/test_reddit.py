"""tests/test_reddit.py — the Reddit reader, and the three-state answer it exists to protect.

The failure this pins was measured on the owner's machine on 2026-09-09: Reddit refuses plain
HTTP from an ordinary client. www.reddit.com answers 403 Blocked to every user agent, and
old.reddit.com answers a LOGIN PAGE carrying HTTP 200. All 18 of the candidate subreddits in the
live install were therefore marked unverified, and the earlier version of that check had already
read the login page as "zero posts" once and dropped every real community as dead (2026-09-04).

So the whole point of research/reddit.py is that it answers in three states and never two:

    ok       Reddit answered and there is something in it
    empty    Reddit answered and there is genuinely nothing
    unknown  we could not look

"Nobody talks about this" and "we could not look" are different facts, and a suite that lets
them blur is the one that ships the bug back. Every check below is about keeping them apart.

NOTHING HERE TOUCHES THE NETWORK. _browser.fetch is replaced with a function that raises, so a
path that forgot its stub fails loudly instead of quietly reading the real reddit.com. Two suites
in this repo once hit real hosts for made-up hostnames and nobody noticed until much later.
"""
import json
import sys
import time

from seo_agent.tests import _fixture
_fixture.setup()

from seo_agent.brand import field_sources as FS  # noqa: E402
from seo_agent.research import reddit as R  # noqa: E402
from seo_agent.tools import _browser  # noqa: E402

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


# ---- the network is sealed off ------------------------------------------------------------------

REACHED = []


def _no_network(url, timeout=None):
    REACHED.append(url)
    raise AssertionError("a test reached the real network: %s" % url)


# fetch_json is NOT replaced: it is one of the things under test, and it reads the module's own
# `fetch`, so sealing that one seals both.
_browser.fetch = _no_network
R.MIN_INTERVAL = 0.0            # the pacing check sets its own value; everything else runs free


# ---- what Reddit actually sends, captured from the live run on 2026-09-09 -----------------------

def _listing(children):
    return json.dumps({"kind": "Listing", "data": {"dist": len(children), "children": children}})


def _post(pid, title, score, ncom, sub="recruiting"):
    return {"kind": "t3", "data": {"id": pid, "title": title, "score": score, "num_comments": ncom,
                                   "subreddit": sub, "selftext": "the body of " + pid,
                                   "author": "someone", "created_utc": 1760050512.0,
                                   "permalink": "/r/%s/comments/%s/t/" % (sub, pid)}}


POSTS = _listing([_post("aaa", "A hiring story", 120, 40), _post("bbb", "An interview story", 90, 30)])
EMPTY = _listing([])
# A name that does not exist: Reddit answers the SEARCH with subreddit rows, kind t5, not posts.
# Measured on r/ExperiencedRecruiter, which returned eight of these named "googlejobs",
# "Accounting", "Oil and Gas Life".
T5_ONLY = _listing([{"kind": "t5", "data": {"id": "2qw2b", "title": "Accounting"}} for _ in range(8)])
LOGIN = ('<!DOCTYPE html><html><head><title>Welcome to Reddit</title></head>'
         '<body><form id="login-form">log in to continue</form></body></html>')
ABOUT_REAL = json.dumps({"kind": "t5", "data": {"display_name": "recruiting", "subscribers": 215605}})
ABOUT_GONE = _listing([{"kind": "t5", "data": {"id": "x"}}])      # about.json redirects to a search
ABOUT_PRIVATE = json.dumps({"reason": "private", "message": "Forbidden", "error": 403})
COMMENTS = json.dumps([
    {"kind": "Listing", "data": {"children": [_post("aaa", "A hiring story", 120, 40)]}},
    {"kind": "Listing", "data": {"children": [
        {"kind": "t1", "data": {"id": "c1", "body": "the quiet one", "score": 12, "author": "a",
                                "permalink": "/r/x/comments/aaa/t/c1/"}},
        {"kind": "t1", "data": {"id": "c2", "body": "the loud one", "score": 400, "author": "b",
                                "permalink": "/r/x/comments/aaa/t/c2/"}},
        {"kind": "t1", "data": {"id": "c3", "body": "[deleted]", "score": 900, "author": "c"}},
        {"kind": "more", "data": {"count": 40}}]}}])

# The old.reddit search surface, which is what tests/test_brand.py's stub still feeds this code.
OLD_HIT = ('<div class="search-result search-result-link"><span class="search-score">12 points</span>'
           '<a class="search-comments">%d comments</a></div>')


def stub(answers):
    """A fetch seam that answers from a dict of {url fragment: body}. Records every url."""
    seen = []

    def f(url):
        seen.append(url)
        for frag, body in answers.items():
            if frag in url:
                return body
        return None
    f.seen = seen
    return f


# ---- the three states ----------------------------------------------------------------------------

print("\nthe three-state answer")
r = R.search("recruiting", "hiring", fetch_fn=stub({"search.json": POSTS}))
ok("real results read as ok, with the posts parsed", r["state"] == "ok" and len(r["posts"]) == 2, r)
ok("a post carries its title, score and comment count",
   r["posts"][0]["title"] == "A hiring story" and r["posts"][0]["score"] == 120
   and r["posts"][0]["num_comments"] == 40, r["posts"][0])
ok("and a url that can be opened", r["posts"][0]["url"].startswith("https://www.reddit.com/r/recruiting/comments/"))
r = R.search("quietsub", "hiring", fetch_fn=stub({"search.json": EMPTY}))
ok("a real empty listing reads as empty, not unknown", r["state"] == "empty" and r["posts"] == [], r)
r = R.search("recruiting", "hiring", fetch_fn=stub({"search.json": None}))
ok("no answer at all reads as unknown, never empty", r["state"] == "unknown", r)

print("\na login page is never read as empty")
r = R.search("recruiting", "hiring", fetch_fn=stub({"search.json": LOGIN}))
ok("a login page with HTTP 200 is unknown", r["state"] == "unknown", r)
ok("and says so in plain words", "login page" in r["reason"], r["reason"])
r = R.search("recruiting", "hiring", fetch_fn=stub({"search.json": {"status": 200, "text": LOGIN}}))
ok("the same when the seam hands back a full response dict", r["state"] == "unknown", r)
r = R.search("recruiting", "hiring", fetch_fn=stub({"search.json": {"status": 403, "text": "Blocked"}}))
ok("a 403 block is unknown", r["state"] == "unknown", r)
r = R.comments("aaa", fetch_fn=stub({"comments": LOGIN}))
ok("the comment reader refuses a login page too", r["state"] == "unknown" and r["comments"] == [], r)

print("\na name that does not exist is not eight live posts")
r = R.search("ExperiencedRecruiter", "hiring", fetch_fn=stub({"search.json": T5_ONLY}))
ok("subreddit rows (t5) are not counted as posts", r["state"] == "empty" and r["posts"] == [], r)
ok("and the reason says what came back instead", "not one of them was a post" in r["reason"], r["reason"])
ok("about.json answering a Listing means there is no such name",
   R.exists("ExperiencedRecruiter", fetch_fn=stub({"about.json": ABOUT_GONE})) == "no")
ok("a t5 means it exists", R.exists("recruiting", fetch_fn=stub({"about.json": ABOUT_REAL})) == "yes")
ok("a private community is named as private, not as missing",
   R.exists("CenturyClub", fetch_fn=stub({"about.json": {"status": 403, "text": ABOUT_PRIVATE}})) == "private")
ok("an unreadable about.json is unknown", R.exists("x", fetch_fn=stub({"about.json": LOGIN})) == "unknown")

print("\ncomments, because the argument matters and not only the headline")
r = R.comments("aaa", fetch_fn=stub({"comments": COMMENTS}))
ok("the comment tree is read", r["state"] == "ok" and len(r["comments"]) == 2, r)
ok("loudest first", [c["id"] for c in r["comments"]] == ["c2", "c1"], r["comments"])
ok("a deleted comment is left out", all(c["text"] != "[deleted]" for c in r["comments"]))
ok("a 'more' stub is not mistaken for a comment", all(c["id"] in ("c1", "c2") for c in r["comments"]))
r = R.comments("bbb", fetch_fn=stub({"comments": json.dumps([
    {"kind": "Listing", "data": {"children": []}}, {"kind": "Listing", "data": {"children": []}}])}))
ok("a post with no comments is empty, not unknown", r["state"] == "empty", r)

print("\nthe old.reddit results surface still counts")
r = R.search("recruiting", "hiring", fetch_fn=stub({"search.json": "<html>" + "".join(OLD_HIT % 20 for _ in range(6)) + "</html>"}))
ok("old-style results HTML is read as posts", r["state"] == "ok" and len(r["posts"]) == 6, r["state"])
ok("with its comment counts", sum(p["num_comments"] for p in r["posts"]) == 120, r["posts"][:1])

print("\na malformed reply does not crash a run")
BAD = ["", "   ", "{", '{"data": {"children": "not a list"}}', "[]", "[1, 2]", "null", "12",
       '{"kind": "Listing"}', '{"error": 500, "reason": "server"}', "<html><body>nothing here</body></html>",
       '{"data": {"children": [{"kind": "t3"}]}}', '{"data": {"children": [null]}}']
crashed = []
for body in BAD:
    for call in (lambda b: R.search("s", "q", fetch_fn=stub({"search.json": b})),
                 lambda b: R.top("s", fetch_fn=stub({"top.json": b})),
                 lambda b: R.comments("p", fetch_fn=stub({"comments": b}))):
        try:
            got = call(body)
            if got["state"] not in ("ok", "empty", "unknown"):
                crashed.append((body[:20], got["state"]))
        except Exception as e:      # noqa: BLE001 - that is the whole point of the check
            crashed.append((body[:20], repr(e)[:60]))
ok("thirteen malformed bodies across three calls, no exception and always one of the three states",
   not crashed, crashed)
r = R.search("s", "q", fetch_fn=stub({"search.json": '{"data": {"children": [{"kind": "t3", "data": {}}]}}'}))
ok("a post with no fields at all still parses into the post shape",
   r["state"] == "ok" and r["posts"][0]["title"] == "" and r["posts"][0]["score"] == 0, r)


def _boom(url):
    raise RuntimeError("the browser died")


try:
    r = R.search("s", "q", fetch_fn=_boom)
    ok("a seam that raises is not caught here", False, r)
except RuntimeError:
    ok("a seam that raises surfaces to its caller, so a bug is not swallowed as 'empty'", True)
real_browser_fetch = _browser.fetch
_browser.fetch = lambda url, timeout=None: (_ for _ in ()).throw(_browser.NoBrowser("no browser here"))
r = R.search("s", "q")
ok("no browser on the machine reads as unknown, never empty", r["state"] == "unknown", r)
ok("and the reason names the missing browser", "no browser" in r["reason"].lower(), r["reason"])
_browser.fetch = real_browser_fetch

print("\nthe rate limiter actually delays")
R.MIN_INTERVAL = 0.25
R._last_call[0] = 0.0
_browser.fetch = lambda url, timeout=None: {"status": 200, "text": EMPTY, "url": url, "headers": {}}
t0 = time.monotonic()
for _ in range(3):
    R.fetch("https://www.reddit.com/r/x/top.json")
spent = time.monotonic() - t0
ok("three paced requests take at least two intervals", spent >= 0.5, "%.3fs" % spent)
ok("and not wildly more than that", spent < 2.0, "%.3fs" % spent)
t0 = time.monotonic()
R.MIN_INTERVAL = 0.0
R.fetch("https://www.reddit.com/r/x/top.json")
ok("MIN_INTERVAL 0 does not sleep, so a suite is not slowed by it", time.monotonic() - t0 < 0.1)
_browser.fetch = _no_network

print("\nbuilder 11 keeps the same three answers")
FS.fetch = stub({"search.json": POSTS})
ok("a live subreddit is counted", FS.check("recruiting")["state"] == "ok")
ok("probe hands back the tuple assets/trends.py reads", FS.probe("recruiting") == (2, 70), FS.probe("recruiting"))
FS.fetch = stub({"search.json": LOGIN})
got = FS.check("recruiting")
ok("a login page is unknown for the builder too", got["state"] == "unknown" and got["posts"] == 0, got)
ok("probe returns None so the builder marks it unverified rather than dead", FS.probe("recruiting") is None)
FS.fetch = stub({"search.json": EMPTY, "about.json": ABOUT_REAL})
got = FS.check("quietsub")
ok("a real but silent community is empty, and says which it is",
   got["state"] == "empty" and "nothing matched" in got["why"], got)
ok("and probe reports zero rather than None, because we did look", FS.probe("quietsub") == (0, 0))
FS.fetch = stub({"search.json": EMPTY, "about.json": ABOUT_GONE})
got = FS.check("madeupsub")
ok("a name the model invented is named as such, not called quiet",
   got["state"] == "empty" and "no subreddit by this name" in got["why"], got)
FS.fetch = stub({"search.json": EMPTY, "about.json": {"status": 403, "text": ABOUT_PRIVATE}})
got = FS.check("CenturyClub")
ok("a private community cannot be checked, so it is unknown", got["state"] == "unknown" and "private" in got["why"], got)

print("\nverify() writes the three answers through to the candidate rows")
said = []
cands = [{"name": "recruiting", "covers": "the job"}, {"name": "walledsub", "covers": "the job"},
         {"name": "quietsub", "covers": "the other side"}]


def _mixed(url):
    if "walledsub" in url:
        return LOGIN
    if "quietsub" in url:
        return ABOUT_REAL if "about.json" in url else EMPTY
    return POSTS


FS.fetch = _mixed
FS.MIN_POSTS, FS.MIN_COMMENTS = 2, 60
rows, unknown = FS.verify(cands, lambda l, n="": said.append((l, n)))
by = {c["name"]: c for c in rows}
ok("the live one is kept", by["recruiting"]["verdict"] == "keep", by["recruiting"])
ok("the walled one is unknown and is NOT dropped", by["walledsub"]["verdict"] == "unknown" and unknown == 1, by["walledsub"])
ok("its row says we could not check, and why", "could not be checked" in by["walledsub"]["why"]
   and "login page" in by["walledsub"]["why"], by["walledsub"]["why"])
ok("the quiet one is dropped on the numbers, not on a refusal", by["quietsub"]["verdict"] == "drop", by["quietsub"])
ok("the count of unverified names is said out loud", any("could not be checked" in n for l, n in said), said)

print("\nthe browser's json entry point")
_browser.fetch = lambda url, timeout=None: {"status": 200, "text": LOGIN, "url": url, "headers": {}}
ok("a login page parses to data=None, so no caller can read it as an empty result",
   _browser.fetch_json("https://www.reddit.com/x.json")["data"] is None)
_browser.fetch = lambda url, timeout=None: {"status": 200, "text": POSTS, "url": url, "headers": {}}
got = _browser.fetch_json("https://www.reddit.com/x.json")
ok("real json comes back parsed", isinstance(got["data"], dict) and got["data"]["kind"] == "Listing")
_browser.fetch = _no_network

ok("no check in this suite reached the real network", not REACHED, REACHED)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), FAILS))
    sys.exit(1)
print("all reddit checks passed")
