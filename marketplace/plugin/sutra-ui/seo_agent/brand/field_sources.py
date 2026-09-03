"""brand/field_sources.py — builder 11: where this company's audience talks, checked against Reddit.

Port of 9-field-sources/scripts/run_field_sources.py, minus the paid fallback.

Step 1 propose candidate subreddits from the niche and the personas (model; it knows the names).
Step 2 CHECK every one against old.reddit and keep only the live ones (code; this is counting).
       A subreddit name that does not exist returns zero results in silence, indistinguishable from
       "nobody discusses this", so the check happens once, here. A rate-limited old.reddit serves a
       LOGIN PAGE with HTTP 200: that is "unknown", never "empty". There is NO paid fallback: a
       candidate that cannot be checked is marked unverified and said so, never dropped, never raised on.
Step 3 write the reference file (model), then verify every kept name appears and no rejected one does.

Reads:  brand/persona.md
Writes: brand/_work/field-sources/candidates.json · brand/field-sources.md
"""
import re
import time
import urllib.parse
import urllib.request

from .. import llm
from . import _common as cm

OUTPUT = "field-sources.md"
WORK = "_work/field-sources/"

# --- how a subreddit qualifies -------------------------------------------------------------------
# Vetted by ACTIVITY, never by subscriber count: old.reddit stopped exposing subscriber counts, and a
# big dormant community is worth less than a small busy one anyway.
MIN_POSTS = 5               # top posts found in the last year
MIN_COMMENTS = 40           # summed across those posts
MAX_KEEP = 10               # subreddits kept in the final list. A longer list is nearly free: the
#                             per-article planner names which subreddits a query goes to, so the list
#                             is a menu, not a workload. Too short is the expensive mistake.
PER_ANGLE = 3               # kept from EACH `covers` angle first
FS_CANDIDATES = 18          # discovered before verification
THROTTLE = 2.0              # seconds between probes (tests set 0)
TIMEOUT = 30
PERSONA_CHARS = 6000
QUERY = "hiring OR interview OR process"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
ANGLES = ("the job", "the other side", "the tier below", "the adjacent trade")

_RESULT = re.compile(r'<div class="[^"]*search-result search-result-link.*?'
                     r'<span class="search-score">([\d,]+) point.*?'
                     r'class="search-comments[^"]*"\s*>([\d,]+) comment', re.S)


class _R308(urllib.request.HTTPRedirectHandler):
    def http_error_308(self, req, fp, code, msg, headers):
        return self.http_error_301(req, fp, 301, msg, headers)


_OPENER = urllib.request.build_opener(_R308)


def fetch(url):
    """The page text, or None when Reddit could not be reached. Tests replace this."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return _OPENER.open(req, timeout=TIMEOUT).read().decode("utf-8", "ignore")
    except Exception:        # noqa: BLE001 - a network failure degrades, never raises
        return None


def probe(sub):
    """(posts, comments) from old.reddit, or None when it is blocking us or unreachable."""
    u = ("https://old.reddit.com/r/%s/search?q=%s&restrict_sr=on&sort=top&t=year"
         % (urllib.parse.quote(sub), urllib.parse.quote(QUERY)))
    page = fetch(u)
    if page is None or "search-result" not in page:
        return None                                   # blocked, private, or genuinely gone: cannot tell
    hits = _RESULT.findall(page)
    return len(hits), sum(int(c.replace(",", "")) for _, c in hits)


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
    for i, c in enumerate(cands):
        got = probe(c["name"])
        if got is None:
            c.update(posts=0, comments=0, checked_via="unreachable", verdict="unknown",
                     why="unverified — Reddit could not be checked (blocked or unreachable); no paid fallback")
            unknown += 1
        else:
            posts, comments = got
            ok = posts >= MIN_POSTS and comments >= MIN_COMMENTS
            c.update(posts=posts, comments=comments, checked_via="free",
                     verdict="keep" if ok else "drop",
                     why="" if ok else "only %d posts / %d comments in a year" % (posts, comments))
        if i + 1 < len(cands) and THROTTLE:
            time.sleep(THROTTLE)
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
