"""brand/field_sources.py — builder 11: where this company's audience talks, checked against Reddit.

Port of 9-field-sources/scripts/run_field_sources.py, minus the paid fallback.

Step 1 propose candidate subreddits from the niche and the personas (model; it knows the names).
Step 2 CHECK every one against Reddit and keep only the live ones (code; this is counting).
       The check has THREE answers and never two, because a subreddit with real posts, a community
       nobody posts in, and a community we were not allowed to look at are three different facts:
         keep/drop  Reddit answered and we counted what is there.
         unknown    We could not look. Blocked, login-walled, or no browser on this machine.
       A rate-limited Reddit serves a LOGIN PAGE with HTTP 200, which is why "it answered" is not
       the same as "we read it": research/reddit.py parses the body and only calls it empty when it
       parsed a real, empty listing. There is NO paid fallback: a candidate that cannot be checked
       is marked unverified and said so, never dropped, never raised on.
Step 3 write the reference file (model), then verify every kept name appears and no rejected one does.

HOW THE CHECK REACHES REDDIT. Through research/reddit.py, which goes out through a real browser.
Plain HTTP from an ordinary machine is refused: measured 2026-09-09 on the owner's laptop, this
builder's old request (old.reddit.com HTML with a plain user agent) returned a login page for all
18 candidates, so all 18 were unverified and the file was useless. Six plain-HTTP variations were
tried and every one was a 403 or a login page. A browser gets through; that is the whole fix.

Reads:  brand/persona.md
Writes: brand/_work/field-sources/candidates.json · brand/field-sources.md
"""
import re

from .. import llm
from ..research import reddit
from . import _common as cm

OUTPUT = "field-sources.md"
WORK = "_work/field-sources/"

# --- how a subreddit qualifies -------------------------------------------------------------------
# Vetted by ACTIVITY, never by subscriber count: the free surfaces stopped exposing subscriber
# counts, and a big dormant community is worth less than a small busy one anyway.
MIN_POSTS = 5               # top posts found in the last year
MIN_COMMENTS = 40           # summed across those posts
MAX_KEEP = 10               # subreddits kept in the final list. A longer list is nearly free: the
#                             per-article planner names which subreddits a query goes to, so the list
#                             is a menu, not a workload. Too short is the expensive mistake.
PER_ANGLE = 3               # kept from EACH `covers` angle first
FS_CANDIDATES = 18          # discovered before verification
PROBE_LIMIT = 25            # posts asked for per probe; the thresholds sit well under it
PERSONA_CHARS = 6000
QUERY = "hiring OR interview OR process"
ANGLES = ("the job", "the other side", "the tier below", "the adjacent trade")
# No THROTTLE here any more. Pacing between Reddit requests is decided in ONE place, research/
# reddit.py's MIN_INTERVAL, so the two builders that probe Reddit cannot drift apart or double up.


def fetch(url):
    """The body Reddit returned for one URL, or None when it could not be reached.

    THE network seam for this builder. Tests replace it (tests/test_brand.py and
    tests/test_assets_trends.py both do), which is how no suite ever reaches reddit.com, and
    assets/trends.py calls it directly for its own Reddit reads. It returns text rather than the
    reader's dict because trends.py has been calling it that way since before reddit.py existed.
    """
    got = reddit.fetch(url)
    return got.get("text") or None


def check(sub):
    """One subreddit's activity: {"posts", "comments", "state", "why"}.

    `state` is "ok" (counted), "empty" (Reddit answered, nothing there) or "unknown" (we could
    not look). The verdict is decided HERE and nowhere else; probe() and verify() only read it.

    When a search comes back empty we spend one more request on about.json, because an empty
    listing is also what Reddit returns for a name that does not exist (checked 2026-09-09:
    r/zzzqqxnotarealsub answers 200 with no children, exactly like a real but silent community).
    Telling those apart is the difference between "the model invented this subreddit" and
    "nobody posts there".
    """
    r = reddit.search(sub, QUERY, limit=PROBE_LIMIT, fetch_fn=fetch)
    if r["state"] == "unknown":
        return {"posts": 0, "comments": 0, "state": "unknown", "why": r.get("reason") or ""}
    posts = r["posts"]
    counted = {"posts": len(posts), "comments": sum(int(p.get("num_comments") or 0) for p in posts),
               "state": "ok", "why": ""}
    if r["state"] == "empty":
        was = reddit.exists(sub, fetch_fn=fetch)
        if was == "no":
            return {"posts": 0, "comments": 0, "state": "empty", "why": "there is no subreddit by this name"}
        if was in ("private", "unknown"):
            # The search found nothing AND we could not confirm the community is real. That is two
            # unknowns, not an empty community, so it goes in the unverified pile.
            return {"posts": 0, "comments": 0, "state": "unknown",
                    "why": "the community is private, so its activity cannot be checked" if was == "private"
                           else "the search found nothing and the community could not be confirmed"}
        counted["state"] = "empty"
        counted["why"] = "the community exists but nothing matched in a year"
    return counted


def probe(sub):
    """(posts, comments), or None when Reddit could not be checked.

    Kept as a tuple because assets/trends.py reads it that way. It is a thin read of check(),
    never a second opinion.
    """
    got = check(sub)
    if got["state"] == "unknown":
        return None
    return got["posts"], got["comments"]


def clean_name(name):
    # NOT lstrip("r/"): that strips any leading 'r' or '/' CHARACTER, so "recruiting" came back as
    # "ecruiting" and the four best subreddits were silently rejected as dead.
    n = str(name).strip().strip("/")
    for pre in ("r/", "/r/"):
        if n.lower().startswith(pre):
            n = n[len(pre):]
    return n.strip("/")


# ---- step 1 -------------------------------------------------------------------------------------

def propose(co, say):
    persona = cm.read("persona.md")[:PERSONA_CHARS]
    r = llm.json_call(cm.fill(cm.prompt("propose-subreddits"), brand=co["brand"], niche=co.get("niche_definition") or "",
                              persona=persona or "(no persona file)", n=FS_CANDIDATES))
    cands = [c for c in ((r or {}).get("subreddits") or []) if isinstance(c, dict) and str(c.get("name") or "").strip()] if isinstance(r, dict) else []
    seen, uniq = set(), []
    for c in cands:
        c["name"] = clean_name(c["name"])
        if c["name"].lower() in seen or not c["name"]:
            continue
        seen.add(c["name"].lower())
        uniq.append(c)
    say("Proposed candidate subreddits", "%d names across the four angles" % len(uniq))
    return uniq


# ---- step 2 -------------------------------------------------------------------------------------

def verify(cands, say):
    unknown = 0
    for c in cands:
        got = check(c["name"])
        if got["state"] == "unknown":
            # A REFUSAL IS NOT AN EMPTY COMMUNITY. Reddit answers a logged-out or rate-limited
            # request with a login page carrying HTTP 200, and on 2026-09-04 this builder read
            # that page as "zero posts" and dropped every real community. Unknown, and said so.
            why = "unverified — Reddit could not be checked; no paid fallback"
            if got["why"]:
                why += " (%s)" % got["why"]
            c.update(posts=0, comments=0, checked_via="unreachable", verdict="unknown", why=why)
            unknown += 1
        else:
            posts, comments = got["posts"], got["comments"]
            ok = posts >= MIN_POSTS and comments >= MIN_COMMENTS
            c.update(posts=posts, comments=comments, checked_via="free",
                     verdict="keep" if ok else "drop",
                     why="" if ok else (got["why"] or "only %d posts / %d comments in a year" % (posts, comments)))
    # RANK WITHIN EACH ANGLE, NOT ACROSS ALL OF THEM. Raw comment volume favours big general communities
    # over small exact ones. So take the best few from each `covers` group first, then fill by volume.
    keep = sorted([c for c in cands if c["verdict"] == "keep"], key=lambda c: -c["comments"])
    per_group, chosen = {}, []
    for c in keep:                                     # pass 1: guarantee every angle is represented
        g = c.get("covers") or "?"
        if per_group.get(g, 0) < PER_ANGLE and len(chosen) < MAX_KEEP:
            per_group[g] = per_group.get(g, 0) + 1
            chosen.append(c)
    for c in keep:                                     # pass 2: fill what is left by activity
        if len(chosen) >= MAX_KEEP:
            break
        if c not in chosen:
            chosen.append(c)
    for c in keep:
        if c not in chosen:
            c["verdict"], c["why"] = "drop", "outside the top %d once every angle was covered" % MAX_KEEP
    cm.save(WORK + "candidates.json", {"candidates": cands})
    n_keep = sum(1 for c in cands if c["verdict"] == "keep")
    say("Checked every subreddit against Reddit", "kept %d of %d%s" % (n_keep, len(cands),
        ("; %d could not be checked and are marked unverified" % unknown) if unknown else ""))
    if not n_keep and not unknown:
        say("Nothing survived the check", "either the proposals were wrong or every community is quiet")
    return cands, unknown


# ---- step 3 -------------------------------------------------------------------------------------

def _block(rows):
    return "\n".join("  %s — %s — covers %s — %d posts, %d comments%s"
                     % (c["name"], c.get("who", ""), c.get("covers", "?"), c.get("posts", 0), c.get("comments", 0),
                        (" — " + c["why"]) if c.get("why") else "") for c in rows) or "  (none)"


def write(co, cands, say):
    kept = [c for c in cands if c["verdict"] == "keep"]
    unverified = [c for c in cands if c["verdict"] == "unknown"]
    rej = [c for c in cands if c["verdict"] == "drop"]
    md = cm.strip_fence(llm.text(cm.fill(cm.prompt("write-field-sources"), brand=co["brand"],
                                          niche=co.get("niche_definition") or "",
                                          sources=cm.template("field-sources-sources"),
                                          kept=_block(kept), unverified=_block(unverified), rejected=_block(rej),
                                          today=cm.today())))
    cm.save(OUTPUT, md)
    # VERIFY, DON'T TRUST: every kept subreddit must appear, and no rejected one may sit in the table.
    missing = [c["name"] for c in kept if c["name"] not in md]
    leaked = [c["name"] for c in rej if re.search(r"\|\s*(?:r/)?%s\s*\|" % re.escape(c["name"]), md)]
    say("Wrote field-sources.md", "%d words, %d verified subreddits, %d unverified" % (cm.words(md), len(kept), len(unverified)))
    notes = []
    if missing:
        notes.append("field-sources.md: kept but missing from the file: %s" % ", ".join(missing))
    if leaked:
        notes.append("field-sources.md: rejected but listed in the table: %s" % ", ".join(leaked))
    return notes


def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        say("Kept field-sources.md", "already built; ask for a redo to rebuild it")
        return {"files": [OUTPUT], "needs_review": []}
    cands = propose(co, say)
    if not cands:
        raise RuntimeError("The model proposed no subreddits to check.")
    cands, unknown = verify(cands, say)
    notes = write(co, cands, say)
    if unknown:
        notes.append("field-sources.md: %d subreddits are unverified (Reddit could not be checked); confirm them by hand" % unknown)
    return {"files": [OUTPUT], "needs_review": notes}
