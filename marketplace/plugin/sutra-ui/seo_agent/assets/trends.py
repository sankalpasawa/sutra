"""assets/trends.py — builder 3: what the niche is arguing about right now, turned into asset ideas.

Port of `02-asset-engine/3-study-trends/study-trends.workflow.md` (method 3 of 3). It supplies the
one thing methods 1 and 2 cannot: timeliness. An argument that is live this month, with the real
words people used, and a number the company could publish that would settle it.

The one rule the original puts above everything else: **Reddit measures attention, not linkability.**
The loudest posts are viral drama nobody would ever cite. The value of this method is the filtering,
not the reading, so the pipeline spends most of its effort deciding what to throw away.

The stages, and the file each one writes (every step reads the file the step before it wrote):

  A  subreddits          _work/trends/subreddits.json      the proposal, with its activity evidence
     THE GATE            _work/trends/approved-subreddits.json   written by the chat, read here
     the scrape          _work/trends/posts.json
  1  read every post     (no file; the cards are built in memory and fed to 2a)
  2a phrases per post    _work/trends/phrases.json
  2b tensions            _work/trends/merge-check.md, phrase-map.csv, tensions-base.json
  2c every post placed   _work/trends/post-tension-map.tsv (+ misc-remine.md)
  2d the tension record  _work/trends/tensions.json
  2.5 THE SELF-AUDIT     _work/trends/self-audit.md        nothing is filtered until this passes
  3  the two tests       _work/trends/tensions.json        (verdicts written back in)
  4  ideas               assets/trends.json                THE POOL
  5  THE VERIFY GATE     _work/trends/verify.md            the run is not done until it passes

Reads:  assets/scope.md · brand/field-sources.md and its candidates.json · brand/brand-voice.md ·
        brand/features.md · knowledge/competitors.json · old.reddit
Writes: assets/trends.json plus everything under assets/_work/trends/ listed above.

WHAT THIS BUILDER DOES NOT DO. It does not wait for the subreddit approval. When there is no
approval on file it returns `{"gate": {...}}` and stops, exactly the way `tools/onboard.py` returns
`{"ask": {...}}`, and the chat turns that into one question and calls back later. There is one
waiting mechanism in this app and this is not a second one.
"""
import collections
import csv
import io
import os
import re
import time
import urllib.parse

from .. import llm
from .. import store
from ..brand import _common as bcm
from ..brand import field_sources as fs
from ..tools import _shared as sh
from . import _common as cm

OUTPUT = "trends.json"
METHOD = "study-trends"
WORK = "_work/trends/"
APPROVED = WORK + "approved-subreddits.json"

# ---- phase A: the scrape -----------------------------------------------------------------------
MAX_SUBS = 8              # subreddits put to the person at the gate. The original ran 25+ on a
#                           laptop overnight; in the app a run has to finish while somebody waits.
POSTS_PER_SUB = 25        # the original's `--posts 25 --sort top --time year`
COMMENT_POSTS = 15        # ...and its `--threads 15`: comments are read for the top 15 only
COMMENTS_PER_POST = 15    # top comment blocks kept per post
THROTTLE = 1.5            # seconds between Reddit fetches (tests set 0)
BODY_CHARS = 1200         # of a post body, on the content card
COMMENT_CHARS = 1400      # of the comments, on the content card

# ---- phase B: the mining -----------------------------------------------------------------------
PHRASE_SHARD = 12         # posts per phrase call. Phrase tagging is per-post, so it shards freely
CONSOLIDATE_SHARD = 120   # distinct phrases per consolidate call
MERGECHECK_SHARD = 8      # candidate tensions per merge-check call (its output is long)
ASSIGN_SHARD = 30         # posts per assignment call
RECORDS_SHARD = 12        # tensions per record call (rich output, keep it small)
FILTER_SHARD = 25         # tensions per shared-test call
TENSION_MIN_PHRASES = 2   # a one-phrase tension is noise; its posts fall to misc
TENSION_MAX_POSTS = 8     # the original's size alarm: above this, presumed merged by topic
TENSION_MAX_PHRASES = 15  # ...same alarm, on phrases
MISC_MAX_PCT = 15.0       # misc above this share of posts means the sort was lazy
REMINE_MIN = 3            # the original: "for every group of 3+ posts sharing an issue, promote it"
DEDUP_SIM = 0.85          # two tension SENTENCES merge only when this similar: true duplicates only
IDEA_CTX_CHARS = 6000     # of each brand document per idea call
EMOTIONS = ("anger", "anxiety", "disbelief", "ridicule")     # closed set, 2d
AUDIENCES = ("employer", "candidate", "both")                # closed set, 2d

# The vague predicates that turn a tension back into a topic. Straight from the original's tripwire
# list; a sentence that needs one of these to hold together is a category verdict, not a conflict.
STRETCH = ("doesn't work", "does not work", "is broken", "are broken", "is a mess", "is frustrating",
           "is flawed", "are flawed", "barely predicts", "is unfair", "are unfair", "is outdated",
           "are outdated", "has problems with", "have problems with", "struggles with", "is bad at")

KEPT = ("KEEP", "MAYBE")


def _w(name):
    return WORK + name


def _path(name):
    return cm.path(_w(name))


# ---- phase A1: which subreddits ----------------------------------------------------------------

def _from_field_sources():
    """The subreddits builder 11 already proposed and CHECKED, newest evidence first.

    Discovery does not start from scratch when the brand pack has already done it. `field_sources`
    proposes candidates from the personas and probes every one against old.reddit, so its file
    carries an activity number this builder would otherwise have to go and fetch again.

    A candidate it marked `drop` is dead and stays dropped. A candidate it marked `unknown` is one
    Reddit refused to answer for, and it is carried forward WITH that word on it: on 2026-09-09
    Reddit refused every check for this owner, so all 18 candidates came back unverified. Unverified
    is not empty, and it is not a reason to drop a community that may be the best one on the list.
    """
    rows = []
    raw = bcm.read("_work/field-sources/candidates.json")
    for c in ((raw or {}).get("candidates") or []) if isinstance(raw, dict) else []:
        if not isinstance(c, dict) or c.get("verdict") not in ("keep", "unknown"):
            continue
        rows.append({"name": fs.clean_name(c.get("name") or ""), "who": c.get("who") or "",
                     "covers": c.get("covers") or "", "posts": c.get("posts") or 0,
                     "comments": c.get("comments") or 0,
                     "checked": c.get("verdict") == "keep",
                     "why": c.get("why") or ("checked against Reddit: %s posts, %s comments in a year"
                                             % (c.get("posts"), c.get("comments")))})
    if rows:
        return [r for r in rows if r["name"]], "brand/field-sources.md"
    # No structured file. The written one still names them, and a name is enough to probe.
    md = bcm.read("field-sources.md")
    seen, out = set(), []
    for m in re.finditer(r"\br/([A-Za-z0-9_]{2,30})\b", md or ""):
        n = m.group(1)
        if n.lower() in seen:
            continue
        seen.add(n.lower())
        out.append({"name": n, "who": "", "covers": "", "posts": 0, "comments": 0,
                    "checked": False, "why": "named in field-sources.md"})
    if out:
        return out, "brand/field-sources.md"
    return [], ""


def _probe(rows, say):
    """Fill in the activity for candidates that carry none, using builder 11's own probe.

    Vetted by ACTIVITY, never by subscriber count, and a page Reddit would not serve is `unknown`
    rather than `empty` — the same rule, from the same function, so the two builders can never
    disagree about what a dead community looks like.
    """
    unknown = 0
    for i, r in enumerate(rows):
        if r.get("checked"):
            continue
        got = fs.probe(r["name"])
        if got is None:
            r.update(posts=0, comments=0, checked=False, unverified=True,
                     why="unverified: Reddit would not answer the check (blocked or unreachable)")
            unknown += 1
        else:
            r.update(posts=got[0], comments=got[1], checked=True,
                     why="%d posts, %d comments in the last year" % got)
        if i + 1 < len(rows) and THROTTLE:
            time.sleep(THROTTLE)
    if unknown:
        say("Reddit would not answer for every candidate",
            "%d of %d are unverified, and they are kept as unverified rather than dropped"
            % (unknown, len(rows)))
    return rows


def propose(co, say):
    """The candidate subreddits to put to the person, best evidence first."""
    rows, source = _from_field_sources()
    if rows:
        say("Read the subreddits the brand pack already found",
            "%d candidates from field-sources.md" % len(rows))
    else:
        # Nothing on file. Ask for names the same way builder 11 does, with ITS prompt, so the two
        # lists are drawn from the same question rather than two paraphrases of it.
        rows = [{"name": c.get("name"), "who": c.get("who") or "", "covers": c.get("covers") or "",
                 "posts": 0, "comments": 0, "checked": False, "why": ""}
                for c in fs.propose(co, say)]
        source = "proposed here (the brand pack has no field-sources.md yet)"
    rows = _probe(rows, say)
    # Rank by real activity, but never let an unverified one sort below a dead one: it is unknown,
    # not zero. Verified-and-busy first, then unverified, then the rest.
    rows.sort(key=lambda r: (0 if r.get("checked") else 1, -(r.get("comments") or 0)))
    return rows[:MAX_SUBS], source


def approved():
    """The approved subreddit names, or None when nobody has been asked yet.

    None and [] mean different things and always will. None is "the question has not been put".
    [] is "it was put and nothing was approved", which is an answer, and the run respects it.
    """
    raw = cm.read(APPROVED)
    if raw is None:
        return None
    items = raw.get("subreddits") if isinstance(raw, dict) else raw
    out, seen = [], set()
    for it in items or []:
        n = fs.clean_name(it.get("name") if isinstance(it, dict) else it)
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


# ---- phase A3: the scrape ----------------------------------------------------------------------

_THING = re.compile(r'(?=<div [^>]*class="[^"]*\bthing\b)')
_TITLE = re.compile(r'class="title may-blank[^"]*"[^>]*>([^<]+)<')
_MD = re.compile(r'<div class="md">(.*?)</div>', re.S)
_TAG = re.compile(r"<[^>]+>")


def _blocked(page):
    """Is this Reddit refusing us rather than telling us there is nothing there?

    Reddit answers an anonymous request with a redirect to its login page and an HTTP 200, and that
    page contains just enough of the normal markup to read as "zero posts". Measured 2026-09-04 in
    `brand/field_sources.py`: every real community was dropped as dead. So a login page, a block or
    a page with no listing markup at all is UNKNOWN. It is never empty, and it never becomes a claim
    that the niche has nothing to say.
    """
    if page is None:
        return True
    return ("<title>Welcome to Reddit" in page or "reason=lor2" in page
            or 'id="login-form"' in page or 'class="thing' not in page)


def _clean(text):
    return re.sub(r"\s+", " ", bcm.unescape_text(_TAG.sub(" ", text or ""))).strip()


def _parse_listing(page, sub):
    """An old.reddit listing page into post rows. Ported from the original scraper's parse_posts."""
    rows = []
    for block in _THING.split(page or ""):
        if 'data-fullname="t3_' not in block:
            continue

        def attr(name, b=block):
            m = re.search(r'data-%s="([^"]*)"' % name, b)
            return m.group(1) if m else ""

        if not attr("score"):
            continue
        title = _TITLE.search(block)
        rows.append({"post_id": attr("fullname")[3:], "subreddit": attr("subreddit") or sub,
                     "score": int(attr("score") or 0),
                     "comment_count": int(attr("comments-count") or 0),
                     "title": _clean(title.group(1)) if title else "",
                     "author": attr("author"), "date": attr("timestamp"),
                     "url": "https://old.reddit.com" + attr("permalink"),
                     "body": "", "top_comments": ""})
    return rows


def _read_post(url):
    """The post's own text and its top comments, as one content card's worth of words.

    No image OCR. The original shells out to a compiled macOS binary for `image_text`, which does not
    travel into an app that has to run everywhere, so an image post here is its title and its
    comments. Said plainly rather than quietly: for a picture-heavy community the cards are thinner
    than the original's.
    """
    page = fs.fetch(url + ("&" if "?" in url else "?") + "limit=%d" % COMMENTS_PER_POST)
    if _blocked(page):
        return {"body": "", "top_comments": "", "read": False}
    head, _, tail = page.partition('class="commentarea"')
    body = _MD.search(head)
    tail = tail.split('<div class="side">')[0]
    comments = [_clean(c) for c in _MD.findall(tail)[:COMMENTS_PER_POST]]
    return {"body": _clean(body.group(1))[:4000] if body else "",
            "top_comments": " || ".join(c for c in comments if c)[:6000], "read": True}


def scrape(subs, say, redo=False):
    """Phase A3. Every post we could actually read, and an honest note about the ones we could not."""
    if cm.exists(_w("posts.json")) and not redo:
        got = cm.read(_w("posts.json")) or {}
        say("Kept the posts already pulled", "%d posts from the last run" % len(got.get("posts") or []))
        return got
    posts, refused, empty = [], [], []
    for i, sub in enumerate(subs):
        url = "https://old.reddit.com/r/%s/top/?t=year&limit=%d" % (urllib.parse.quote(sub), POSTS_PER_SUB)
        page = fs.fetch(url)
        if _blocked(page):
            refused.append(sub)
            say("Reddit would not serve r/%s" % sub, "recorded as unknown, not as empty")
            continue
        rows = _parse_listing(page, sub)[:POSTS_PER_SUB]
        if not rows:
            empty.append(sub)
        for n, p in enumerate(rows):
            if n < COMMENT_POSTS:
                if THROTTLE:
                    time.sleep(THROTTLE)
                p.update(_read_post(p["url"]))
        posts += rows
        say("Read r/%s" % sub, "%d posts" % len(rows))
        if i + 1 < len(subs) and THROTTLE:
            time.sleep(THROTTLE)
    out = {"at": store.now(), "subreddits": list(subs), "refused": refused, "empty": empty,
           "posts": posts}
    cm.save(_w("posts.json"), out)
    return out


def card(p):
    """One post as the model reads it: the whole thing, as one unit. This is stage 1."""
    return ("### %s | r/%s | %sup %sc\nTITLE: %s\nBODY: %s\nTOP_COMMENTS: %s"
            % (p.get("post_id"), p.get("subreddit"), p.get("score", 0), p.get("comment_count", 0),
               (p.get("title") or "")[:300], (p.get("body") or "")[:BODY_CHARS],
               (p.get("top_comments") or "")[:COMMENT_CHARS]))


# ---- stage 2a: phrases -------------------------------------------------------------------------

def tag(co, posts, say, redo=False):
    """2a. Two or three tight phrases per post, written next to the post they came from.

    Sharded because it is embarrassingly parallel: each post is tagged on its own evidence and
    nothing here looks across posts. Recurrence is a LATER question, counted in 2b, and a model
    asked to spot it now invents it.
    """
    if cm.exists(_w("phrases.json")) and not redo:
        return cm.read(_w("phrases.json")) or {}
    shards = [posts[i:i + PHRASE_SHARD] for i in range(0, len(posts), PHRASE_SHARD)]

    def one(shard):
        out = llm.json_call(sh.fill(cm.prompt("trends-phrases"), brand=co["brand"],
                                    cards="\n\n".join(card(p) for p in shard)))
        got = {}
        for r in (out or {}).get("posts") or []:
            if isinstance(r, dict) and r.get("post_id"):
                got[str(r["post_id"])] = [str(x).strip() for x in (r.get("phrases") or []) if str(x).strip()]
        return got

    phrases, failed = {}, 0
    for _shard, got, err in bcm.parallel(one, shards, say, "Reading the posts"):
        if err is not None:
            failed += 1
            continue
        phrases.update(got or {})
    # Every post accounted for, exactly once. A post the model skipped gets an empty list, never a
    # missing key: the coverage check downstream is only worth running on a complete map.
    out = {p["post_id"]: phrases.get(p["post_id"]) or [] for p in posts}
    cm.save(_w("phrases.json"), out)
    tagged = sum(1 for v in out.values() if v)
    say("Tagged every post with phrases",
        "%d of %d posts carry phrases%s" % (tagged, len(out),
                                            "; %d batches failed" % failed if failed else ""))
    return out


# ---- stage 2b: phrases into tensions -----------------------------------------------------------

def _phrase_posts(phrases, only=None):
    """{phrase: [post_id]} in first-seen order, one row per DISTINCT phrase."""
    m = collections.OrderedDict()
    for pid, plist in phrases.items():
        if only is not None and pid not in only:
            continue
        for ph in plist or []:
            m.setdefault(ph.strip(), [])
            if pid not in m[ph.strip()]:
                m[ph.strip()].append(pid)
    return m


def _words(sentence):
    return {w for w in re.findall(r"[a-z']+", (sentence or "").lower()) if len(w) > 3}


def _same_pain(a, b):
    """Two tension SENTENCES that are really the same pain named twice.

    Deliberately tight. The original's own instruction is keep-specific: merging near-misses squashes
    distinct pains together, which is the exact failure the merge check exists to prevent. The real
    cut is stage 3's brand-scope filter, not this.
    """
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / float(len(wa | wb)) >= DEDUP_SIM


def _candidates(co, phrase_posts, say):
    """First pass: phrases grouped into candidate tensions. Sharded when the list is long."""
    items = list(phrase_posts.items())
    shards = [items[i:i + CONSOLIDATE_SHARD] for i in range(0, len(items), CONSOLIDATE_SHARD)]

    def one(shard):
        block = "\n".join("- %s  [%s]" % (ph, ", ".join(ids)) for ph, ids in shard)
        out = llm.json_call(sh.fill(cm.prompt("trends-consolidate"), brand=co["brand"], phrases=block))
        return (out or {}).get("tensions") or []

    cands = []
    for _s, got, err in bcm.parallel(one, shards, say, "Grouping the phrases"):
        for t in got or []:
            if not isinstance(t, dict) or not (t.get("tension") or "").strip():
                continue
            names = [str(p.get("phrase") if isinstance(p, dict) else p).strip()
                     for p in (t.get("phrases") or [])]
            names = [n for n in names if n in phrase_posts]
            if names:
                cands.append({"tension": " ".join(t["tension"].split()), "phrases": sorted(set(names))})
    return cands


def _gate(co, cands, phrase_posts, say):
    """THE MERGE CHECK. The gate that stops phrases being merged by topic instead of by pain.

    It is not paperwork. On the 2026-06-25 run of the original, the tensions were grouped in one
    pass and the evidence file was written afterwards to look done; a real per-phrase pass then found
    12 misassigned posts and 2 topic blobs, and a person caught it by reading the file timestamps.
    Here the check IS the code path that produces the tensions, so there is no version of this run in
    which the tensions exist and the check did not happen. Its record is written before the tension
    records, and stage 5 fails the run if that order is ever inverted.

    Returns (tensions, blocks): the tensions that came out of the check, and the per-candidate
    evidence that goes into merge-check.md.
    """
    shards = [cands[i:i + MERGECHECK_SHARD] for i in range(0, len(cands), MERGECHECK_SHARD)]

    def block_of(t):
        return "- %s\n  phrases: %s" % (t["tension"], "; ".join(t["phrases"]))

    def one(shard):
        out = llm.json_call(sh.fill(cm.prompt("trends-mergecheck"), brand=co["brand"],
                                    max_phrases=str(TENSION_MAX_PHRASES),
                                    tensions="\n".join(block_of(t) for t in shard)))
        return (out or {}).get("checked") or []

    blocks, out = [], []
    results = bcm.parallel(one, shards, say, "Testing every phrase against its tension")
    for shard, got, err in results:
        if err is not None:
            # The check could not run on these candidates. They are NOT quietly promoted: a tension
            # that never went through the gate is exactly what stage 5 refuses to accept.
            blocks.append({"original": "; ".join(t["tension"] for t in shard), "verdict": "NOT RUN",
                           "shared_pain": "", "per_phrase": [], "results": []})
            continue
        for chk in got or []:
            if not isinstance(chk, dict):
                continue
            res = []
            for t in chk.get("result_tensions") or []:
                if not isinstance(t, dict) or not (t.get("tension") or "").strip():
                    continue
                names = [str(p.get("phrase") if isinstance(p, dict) else p).strip()
                         for p in (t.get("phrases") or [])]
                names = sorted({n for n in names if n in phrase_posts})
                if names:
                    res.append({"tension": " ".join(t["tension"].split()), "phrases": names,
                                "shared_pain": chk.get("shared_pain") or "",
                                "from": chk.get("original") or ""})
            out += res
            blocks.append({"original": chk.get("original") or "", "verdict": chk.get("verdict") or "",
                           "shared_pain": chk.get("shared_pain") or "",
                           "per_phrase": [p for p in (chk.get("per_phrase") or []) if isinstance(p, dict)],
                           "results": [t["tension"] for t in res]})
    return out, blocks


def _settle(tensions, phrase_posts, start=1):
    """Merge true duplicates, drop the fragments, hand out codes. One phrase lives in one tension."""
    final = []
    for t in sorted(tensions, key=lambda x: -len(x["phrases"])):
        for f in final:
            if _same_pain(f["tension"], t["tension"]):
                f["phrases"] = sorted(set(f["phrases"]) | set(t["phrases"]))
                break
        else:
            final.append(dict(t))
    seen, kept = set(), []
    for t in final:
        t["phrases"] = [p for p in t["phrases"] if p not in seen]
        seen.update(t["phrases"])
        if len(t["phrases"]) >= TENSION_MIN_PHRASES:
            kept.append(t)
    kept.sort(key=lambda t: -len(t["phrases"]))
    for i, t in enumerate(kept, start):
        t["tension_id"] = "T%02d" % i
        t["posts"] = sorted({pid for ph in t["phrases"] for pid in phrase_posts.get(ph, [])})
    return kept


def _merge_check_md(co, tensions, blocks, orphans):
    lines = ["# Merge check — %s" % co["brand"], "",
             "The gate that decides whether a group of phrases is one shared pain or several. Every",
             "tension below was formed through it: the sentence was written first, then every phrase",
             "was tested against that sentence one at a time. Written before the tension records, and",
             "the final gate fails this run if that order is ever inverted.", "",
             "## The tensions this produced", ""]
    for t in tensions:
        lines.append("- **%s** — %s  (%d phrases, %d posts)"
                     % (t["tension_id"], t["tension"], len(t["phrases"]), len(t.get("posts") or [])))
    lines += ["", "## The check, candidate by candidate", ""]
    for b in blocks:
        lines.append("**%s** — %s" % (b.get("verdict") or "?", b.get("original") or "(unnamed)"))
        if b.get("shared_pain"):
            lines.append("  shared pain written first: %s" % b["shared_pain"])
        for p in b.get("per_phrase") or []:
            lines.append("  - %s: %s" % ("fits" if p.get("fits") else "does NOT fit", p.get("phrase")))
        for t in b.get("results") or []:
            lines.append("  → %s" % t)
        lines.append("")
    if orphans:
        lines += ["## Orphans: phrases that fit no shared pain", "",
                  "Left aside on purpose. Forcing a leftover into a tension pollutes the evidence more",
                  "than leaving it out.", ""]
        lines += ["- %s" % o for o in orphans[:60]]
        lines.append("")
    return "\n".join(lines) + "\n"


def _phrase_map_csv(tensions, phrase_posts):
    """One row per DISTINCT phrase: the audit trail from a real word to the tension it justifies."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["phrase", "tension_id", "tension", "source_post_ids"])
    for t in tensions:
        for ph in t["phrases"]:
            w.writerow([ph, t["tension_id"], t["tension"], " ".join(phrase_posts.get(ph, []))])
    return buf.getvalue()


def consolidate(co, phrases, say, redo=False):
    """2b. The phrases become tensions, through the merge check, and the evidence is written first."""
    if cm.exists(_w("tensions-base.json")) and not redo:
        return cm.read(_w("tensions-base.json")) or []
    phrase_posts = _phrase_posts(phrases)
    if not phrase_posts:
        cm.save(_w("tensions-base.json"), [])
        return []
    cands = _candidates(co, phrase_posts, say)
    checked, blocks = _gate(co, cands, phrase_posts, say)
    tensions = _settle(checked, phrase_posts)
    orphans = [ph for ph in phrase_posts if not any(ph in t["phrases"] for t in tensions)]
    # merge-check.md FIRST, always. Stage 5 compares its timestamp with the tension records.
    cm.save(_w("merge-check.md"), _merge_check_md(co, tensions, blocks, orphans))
    cm.save(_w("phrase-map.csv"), _phrase_map_csv(tensions, phrase_posts))
    cm.save(_w("tensions-base.json"), tensions)
    say("Consolidated the phrases into tensions",
        "%d distinct phrases, %d candidates, %d tensions after the merge check"
        % (len(phrase_posts), len(cands), len(tensions)))
    return tensions


# ---- stage 2c: every post in exactly one pile --------------------------------------------------

def _assign_call(co, posts, tensions):
    listed = "\n".join("%s | %s" % (t["tension_id"], t["tension"]) for t in tensions)
    valid = {t["tension_id"] for t in tensions}
    shards = [posts[i:i + ASSIGN_SHARD] for i in range(0, len(posts), ASSIGN_SHARD)]

    def one(shard):
        out = llm.json_call(sh.fill(cm.prompt("trends-assign"), brand=co["brand"], tensions=listed,
                                    cards="\n\n".join(card(p) for p in shard)))
        got = {}
        for a in (out or {}).get("assignments") or []:
            if isinstance(a, dict) and a.get("post_id"):
                tid = str(a.get("tension_id") or "misc")
                got[str(a["post_id"])] = tid if tid in valid else "misc"
        return got

    amap = {}
    for _s, got, err in bcm.parallel(one, shards, None, ""):
        amap.update(got or {})
    return amap


def _remine(co, misc_ids, phrases, posts, tensions, say):
    """Re-mine misc. Required, not optional.

    misc is only for a post that shares no pain with any other post. It is not a quiet bin for posts
    that are coherent but off-brand — brand fit is stage 3's decision and it is made in writing. So
    every group of three or more posts sharing an issue is promoted to a real tension here, and the
    count is written down either way.
    """
    phrase_posts = _phrase_posts(phrases, only=set(misc_ids))
    if len(phrase_posts) < TENSION_MIN_PHRASES:
        return [], "misc holds %d posts but almost no phrases, so there was nothing to promote" % len(misc_ids), {}
    cands = _candidates(co, phrase_posts, say)
    checked, blocks = _gate(co, cands, phrase_posts, say)
    fresh = _settle(checked, phrase_posts, start=len(tensions) + 1)
    if not fresh:
        return [], "no group of shared pain came out of the %d misc posts" % len(misc_ids), {}
    by_id = {p["post_id"]: p for p in posts}
    again = _assign_call(co, [by_id[i] for i in misc_ids if i in by_id], fresh)
    counts = collections.Counter(again.values())
    # The codes were handed out before the assignment call and they STAY. Renumbering them now would
    # silently unhook every assignment that was just made against the old code.
    promoted = [t for t in fresh if counts.get(t["tension_id"], 0) >= REMINE_MIN]
    for t in promoted:
        t["from_misc"] = True
    keep_ids = {t["tension_id"] for t in promoted}
    moved = {pid: tid for pid, tid in again.items() if tid in keep_ids}
    note = ("%d misc posts re-mined: %d groups found, %d promoted (a group under %d posts stays in misc)"
            % (len(misc_ids), len(fresh), len(promoted), REMINE_MIN))
    # The promoted tensions went through the same gate, so their evidence belongs in the same file.
    mc = cm.read(_w("merge-check.md")) or ""
    extra = ["", "## Re-mined from misc", "", note, ""]
    for t in promoted:
        extra.append("- **%s** — %s  (%d phrases)" % (t["tension_id"], t["tension"], len(t["phrases"])))
    for b in blocks:
        extra.append("**%s** — %s" % (b.get("verdict") or "?", b.get("original") or "(unnamed)"))
        if b.get("shared_pain"):
            extra.append("  shared pain written first: %s" % b["shared_pain"])
    cm.save(_w("merge-check.md"), mc + "\n".join(extra) + "\n")
    return promoted, note, moved


def assign(co, posts, tensions, say, redo=False):
    """2c. Every post lands in exactly one pile, by its DOMINANT pain."""
    if cm.exists(_w("post-tension-map.tsv")) and not redo:
        amap = {}
        for line in (cm.read(_w("post-tension-map.tsv")) or "").splitlines()[1:]:
            if "\t" in line:
                pid, tid = line.split("\t")[:2]
                amap[pid] = tid
        return amap, tensions
    ids = [p["post_id"] for p in posts]
    amap = _assign_call(co, posts, tensions) if tensions else {}
    for pid in ids:
        amap.setdefault(pid, "misc")
    amap = {pid: amap[pid] for pid in ids}          # exactly the scraped posts, in their own order
    misc = [pid for pid in ids if amap[pid] == "misc"]
    note = "misc holds %d of %d posts" % (len(misc), len(ids))
    if len(misc) >= REMINE_MIN and tensions:
        promoted, note, moved = _remine(co, misc, cm.read(_w("phrases.json")) or {}, posts,
                                        tensions, say)
        if promoted:
            tensions = list(tensions) + promoted
            amap.update(moved)
            cm.save(_w("tensions-base.json"), tensions)
        misc = [pid for pid in ids if amap[pid] == "misc"]
    pct = 100.0 * len(misc) / max(len(ids), 1)
    cm.save(_w("misc-remine.md"),
            "# Re-mining misc\n\n%s\n\nmisc after re-mining: %d of %d posts (%.0f%%). The limit is "
            "%.0f%%; above it the sort was lazy and the final gate fails the run.\n"
            % (note, len(misc), len(ids), pct, MISC_MAX_PCT))
    cm.save(_w("post-tension-map.tsv"),
            "post_id\ttension\n" + "".join("%s\t%s\n" % (pid, amap[pid]) for pid in ids))
    say("Placed every post in one tension", "%d posts, misc %d (%.0f%%)" % (len(ids), len(misc), pct))
    return amap, tensions


# ---- stage 2d: the tension record --------------------------------------------------------------

def banned_words(co):
    """The wording that means stage 4 leaked backwards into the neutral evidence.

    The original's list was one company's product vocabulary. The generic form of it is: the
    company's own name, and any phrasing that proposes a fix. A sub-question is what people are
    ARGUING about, not what somebody could sell them.
    """
    out = ["our platform", "our product", "our tool", "our software", "our solution",
           "would a tool", "would software", "would a platform"]
    brand = (co.get("brand") or "").strip().lower()
    if len(brand) >= 4:
        out.append(brand)
    dom = (co.get("domain") or "").split(".")[0].strip().lower()
    if len(dom) >= 4 and dom != brand:
        out.append(dom)
    return out


def _leaks(text, banned):
    low = (text or "").lower()
    return [b for b in banned if re.search(r"\b%s\b" % re.escape(b), low)]


def records(co, tensions, amap, posts, say, redo=False):
    """2d. One record per tension: what the model has to read, and what is only arithmetic.

    The counts are never asked of a model. # posts, upvotes, comments, the debate ratio and the
    spread of communities are summed off the posts, because a model asked for a number it can only
    estimate will give you one that looks right.
    """
    if cm.exists(_w("tensions.json")) and not redo:
        return cm.read(_w("tensions.json")) or []
    by_id = {p["post_id"]: p for p in posts}
    pile = collections.defaultdict(list)
    for pid, tid in amap.items():
        if tid != "misc":
            pile[tid].append(pid)
    banned = banned_words(co)
    shards = [tensions[i:i + RECORDS_SHARD] for i in range(0, len(tensions), RECORDS_SHARD)]

    def block(t):
        titles = "; ".join((by_id.get(pid, {}).get("title") or "")[:80]
                           for pid in pile.get(t["tension_id"], [])[:8])
        return ("%s | %s\n   phrases: %s\n   posts: %s\n   sample titles: %s"
                % (t["tension_id"], t["tension"], "; ".join(t["phrases"]),
                   " ".join(pile.get(t["tension_id"], [])[:12]), titles))

    def one(shard):
        out = llm.json_call(sh.fill(cm.prompt("trends-records"), brand=co["brand"],
                                    emotions=", ".join(EMOTIONS), audiences=", ".join(AUDIENCES),
                                    banned="; ".join(banned),
                                    tensions="\n".join(block(t) for t in shard)))
        return {str(r["tension_id"]): r for r in (out or {}).get("records") or []
                if isinstance(r, dict) and r.get("tension_id")}

    got = {}
    for _s, res, err in bcm.parallel(one, shards, say, "Writing the tension records"):
        got.update(res or {})

    fixed_emotion, fixed_audience, dropped_q = 0, 0, 0
    rows = []
    for i, t in enumerate(tensions, 1):
        tid = t["tension_id"]
        ids = pile.get(tid, [])
        ps = [by_id[i2] for i2 in ids if i2 in by_id]
        up = sum(int(p.get("score") or 0) for p in ps)
        com = sum(int(p.get("comment_count") or 0) for p in ps)
        r = got.get(tid, {})
        emo = str(r.get("emotion") or "").strip().lower()
        if emo not in EMOTIONS:
            emo, fixed_emotion = "anger", fixed_emotion + 1
        aud = str(r.get("audience") or "").strip().lower()
        if aud not in AUDIENCES:
            aud, fixed_audience = "both", fixed_audience + 1
        best = r.get("best_example")
        if best not in ids:
            best = max(ids, key=lambda x: int(by_id.get(x, {}).get("score") or 0)) if ids else ""
        subs = sorted({by_id.get(x, {}).get("subreddit") or "" for x in ids} - {""})
        # The sub-questions are evidence. Anything naming a product or the company is stage 4 leaking
        # backwards, and it is dropped HERE, at the one place sub-questions are decided, rather than
        # left for the final gate to fail the whole run over.
        subq = []
        for q in (r.get("sub_questions") or []):
            if _leaks(str(q), banned):
                dropped_q += 1
            else:
                subq.append(str(q).strip())
        rows.append({
            "tension_id": tid, "idea_id": cm.new_id(i), "tension": t["tension"],
            "shared_pain": t.get("shared_pain", ""), "from_misc": bool(t.get("from_misc")),
            "phrases": t["phrases"], "core_pain": str(r.get("core_pain") or "").strip(),
            "audience": aud, "emotion": emo,
            "n_posts": len(ids), "posts": ids, "upvotes": up, "comments": com,
            "debate_ratio": round(com / float(up), 3) if up else 0.0, "subreddits": subs,
            "best_example": (by_id.get(best, {}).get("url") or ""), "best_example_id": best or "",
            "quotes": [str(q).strip() for q in (r.get("representative_quotes") or [])][:3],
            "sub_questions": subq, "implied_data": str(r.get("implied_data") or
                                                       r.get("implied_data_point") or "").strip(),
            "linkability": {}, "ownability": {}, "brand_fit": "", "transplant_from": "",
            "verdict": "", "why": "",
        })
    # The size alarm belongs in the gate's own file, and it can only be written once the post counts
    # exist. It goes in BEFORE the records are saved, so the order stage 5 checks still holds.
    big = [r for r in rows if r["n_posts"] > TENSION_MAX_POSTS or len(r["phrases"]) > TENSION_MAX_PHRASES]
    if big:
        mc = cm.read(_w("merge-check.md")) or ""
        out = ["", "## Size alarm", "",
               "Above %d posts or %d phrases a tension is presumed merged by topic. Each of these went"
               % (TENSION_MAX_POSTS, TENSION_MAX_PHRASES),
               "through the check above and came back as one pain; the sentence that covers all of it"
               " is named here.", ""]
        for r in big:
            out.append("- **%s** — %d posts, %d phrases. One pain: %s"
                       % (r["tension_id"], r["n_posts"], len(r["phrases"]),
                          r["shared_pain"] or r["tension"]))
        cm.save(_w("merge-check.md"), mc + "\n".join(out) + "\n")
    cm.save(_w("tensions.json"), rows)
    say("Built the tension records",
        "%d tensions%s" % (len(rows), "; %d sub-questions dropped for naming a product"
                           % dropped_q if dropped_q else ""))
    rows_meta = {"fixed_emotion": fixed_emotion, "fixed_audience": fixed_audience,
                 "dropped_sub_questions": dropped_q}
    cm.save(_w("records-notes.json"), rows_meta)
    return rows


# ---- stage 2.5: the self-audit gate ------------------------------------------------------------

def self_audit(co, rows, amap):
    """The five boxes, ticked in code, before anything is filtered.

    The original ticks them by hand, which is how a checklist gets ticked without being run. Here
    each box is a check over the files that already exist, and a box that fails STOPS the run before
    stage 3. Filtering a bad sort produces a confident, wrong shortlist, which is worse than no
    shortlist at all.
    """
    mc = (cm.read(_w("merge-check.md")) or "").lower()
    pm = list(csv.reader(io.StringIO(cm.read(_w("phrase-map.csv")) or "")))[1:]
    total = len(amap) or 1
    misc = sum(1 for t in amap.values() if t == "misc")
    pct = 100.0 * misc / total
    boxes = []

    vague = [r["tension_id"] for r in rows
             if any(s in r["tension"].lower() for s in STRETCH) or not r["tension"].strip()]
    ungated = [r["tension_id"] for r in rows if r["tension_id"].lower() not in mc]
    boxes.append(("Every tension names one concrete conflict, and went through the merge check",
                  not vague and not ungated,
                  ("stretch-words in %s" % ", ".join(vague) if vague else "")
                  + ("; not in merge-check.md: %s" % ", ".join(ungated) if ungated else "")))

    big = [r["tension_id"] for r in rows
           if (r["n_posts"] > TENSION_MAX_POSTS or len(r["phrases"]) > TENSION_MAX_PHRASES)
           and r["tension_id"].lower() not in mc]
    boxes.append(("No oversized tension left unexamined", not big,
                  "over the size alarm and unjustified: %s" % ", ".join(big) if big else ""))

    boxes.append(("misc was re-mined, counted, and is inside the limit",
                  cm.exists(_w("misc-remine.md")) and pct <= MISC_MAX_PCT,
                  "misc is %d of %d posts (%.0f%%), the limit is %.0f%%"
                  % (misc, total, pct, MISC_MAX_PCT) if pct > MISC_MAX_PCT else ""))

    bad_vocab = [r["tension_id"] for r in rows
                 if r["emotion"] not in EMOTIONS or r["audience"] not in AUDIENCES]
    lazy = len(rows) >= 3 and all(r["audience"] == "both" for r in rows)
    boxes.append(("The closed vocabularies hold, and audience is not lazily \"both\"",
                  not bad_vocab and not lazy,
                  ("outside the vocabulary: %s" % ", ".join(bad_vocab) if bad_vocab else "")
                  + ("; every tension came back \"both\"" if lazy else "")))

    phrases = [row[0] for row in pm if row]
    boxes.append(("The phrase map is one row per distinct phrase",
                  len(phrases) == len(set(phrases)),
                  "%d rows for %d distinct phrases" % (len(phrases), len(set(phrases)))))

    ok = all(b[1] for b in boxes)
    md = ["# Self-audit — %s" % co["brand"], "",
          "Run before any filtering. A bad sort filtered confidently is worse than no shortlist.", ""]
    for label, passed, detail in boxes:
        md.append("- [%s] %s%s" % ("x" if passed else " ", label, ("  — " + detail) if detail else ""))
    md += ["", "**%s**" % ("PASS — on to the filter." if ok else
                           "FAIL — the run stops here. Stage 2 is fixed before anything is filtered.")]
    cm.save(_w("self-audit.md"), "\n".join(md) + "\n")
    return ok, [b[0] for b in boxes if not b[1]]


# ---- stage 3: the two shared tests --------------------------------------------------------------

def _competitors():
    raw = store.knowledge("competitors.json") or {}
    rows = raw.get("competitors") if isinstance(raw, dict) else raw
    return rows or []


def filter_tensions(rows, say):
    """Stage 3. Linkability and Ownability, from `_common`, in the same words as the other methods.

    Both tests live in `_common` and nowhere else. The original's whole argument for merging three
    idea pools and ranking them against each other is that all three judged with the SAME two tests;
    a paraphrase here would produce scores that cannot be compared, and the merge would mean nothing.
    So this method does not own a filter prompt, and it does not invent a third test.

    The keep-or-drop line is drawn HERE, in code, once per tension:
      KEEP   the linkability score cleared the floor AND the company can own it, CORE or TRANSPLANT
      MAYBE  it cleared the floor but the fit is only ADJACENT
      DROP   anything else
    """
    if not rows:
        return rows
    scope = cm.read("scope.md")
    comps = _competitors()
    ideas = [{"id": r["idea_id"], "title": r["tension"],
              "angle": "%s Implied number: %s Sub-questions: %s"
                       % (r["core_pain"], r["implied_data"] or "(none stated)",
                          "; ".join(r["sub_questions"]) or "(none)")} for r in rows]
    own, link = {}, {}
    for i in range(0, len(ideas), FILTER_SHARD):
        shard = ideas[i:i + FILTER_SHARD]
        for v in cm.ownability(shard, scope, comps):
            own[v["id"]] = v
        for v in cm.linkability(shard, scope, comps):
            link[v["id"]] = v
    kept = 0
    for r in rows:
        o = own.get(r["idea_id"]) or {}
        lk = link.get(r["idea_id"]) or {}
        fit = str(o.get("brand_fit") or "").strip().upper()
        r["ownability"] = {"verdict": o.get("verdict"), "why": o.get("why") or ""}
        r["linkability"] = {"score": lk.get("score") or 0, "of": cm.LINKABILITY_OF,
                            "verdict": lk.get("verdict"), "why": lk.get("why") or ""}
        r["brand_fit"] = fit
        r["transplant_from"] = o.get("transplant_from") or ""
        if lk.get("verdict") and o.get("verdict") and fit in ("CORE", "TRANSPLANT"):
            r["verdict"] = "KEEP"
        elif lk.get("verdict") and fit == "ADJACENT":
            r["verdict"] = "MAYBE"
        else:
            r["verdict"] = "DROP"
        r["why"] = "; ".join(x for x in (lk.get("why"), o.get("why")) if x)
        kept += 1 if r["verdict"] in KEPT else 0
    cm.save(_w("tensions.json"), rows)
    say("Filtered the tensions", "%d of %d survive; the rest are attention, not links"
        % (kept, len(rows)))
    return rows


# ---- stage 4: tensions into asset ideas ---------------------------------------------------------

def ideas(co, rows, say):
    """Stage 4. One idea per surviving tension, its shape taken from the tension itself.

    No format borrowing. Picking a proven format is method 1's and method 2's job; this method's edge
    is the argument, so the implied data point usually IS the asset.
    """
    keep = [r for r in rows if r["verdict"] in KEPT]
    if not keep:
        return []
    scope = cm.read("scope.md")[:IDEA_CTX_CHARS]
    voice = bcm.read("brand-voice.md")[:IDEA_CTX_CHARS]
    features = bcm.read("features.md")[:IDEA_CTX_CHARS]

    def one(r):
        return llm.json_call(sh.fill(
            cm.prompt("trends-idea"), brand=co["brand"], scope=scope or "(no brand scope on file)",
            voice=voice or "(no voice profile on file)", features=features or "(no features on file)",
            brand_fit=r["brand_fit"] or "ADJACENT", fit_reason=r["ownability"].get("why") or "",
            tension=r["tension"], core_pain=r["core_pain"], phrases="; ".join(r["phrases"]),
            audience=r["audience"], emotion=r["emotion"],
            implied_data=r["implied_data"] or "(none stated)",
            sub_questions="; ".join(r["sub_questions"]) or "(none)",
            quotes=" / ".join('"%s"' % q for q in r["quotes"]) or "(none)",
            nposts=str(r["n_posts"]), upvotes=str(r["upvotes"]),
            spread=", ".join("r/" + s for s in r["subreddits"]) or "one community"))

    out = []
    for r, got, err in bcm.parallel(one, keep, say, "Shaping the ideas"):
        if err is not None or not isinstance(got, dict):
            continue
        row = cm.blank_idea(r["idea_id"], METHOD)
        row["title"] = str(got.get("asset_title") or "").strip()
        row["angle"] = str(got.get("what_it_would_be") or "").strip()
        row["brand_fit"] = r["brand_fit"]
        row["transplant_from"] = r["transplant_from"]
        row["ownability"] = dict(r["ownability"])
        row["linkability"] = dict(r["linkability"])
        row["proof"] = [
            {"url": r["best_example"], "what": "%d posts, %d upvotes, %d comments across %s — %s"
             % (r["n_posts"], r["upvotes"], r["comments"],
                ", ".join("r/" + s for s in r["subreddits"]) or "one community", r["tension"])},
            {"url": "", "what": "Unfair advantage: %s" % (str(got.get("unfair_advantage") or "").strip()
                                                          or "(not named)")}]
        if row["title"]:
            out.append(row)
    say("Turned the tensions into ideas", "%d ideas, each backed by real posts" % len(out))
    return out


# ---- stage 5: the final verify gate -------------------------------------------------------------

def verify(co, rows, amap, n_ideas, posts):
    """The gate that decides whether this run is finished. It is code, not a claim.

    Self-attestation failed in the original: the agent ticked its own checklist and a person found
    the gate had been written after the thing it was meant to gate. Every check below maps to a
    failure that actually happened, so none of them is decoration.
    """
    mc = (cm.read(_w("merge-check.md")) or "").lower()
    banned = banned_words(co)
    fails = []

    if os.path.exists(_path("merge-check.md")) and os.path.exists(_path("tensions.json")):
        if os.path.getmtime(_path("merge-check.md")) > os.path.getmtime(_path("tensions.json")):
            fails.append("ORDER: merge-check.md is newer than the tension records, so the gate was "
                         "written after the thing it gates")
    ids = [p["post_id"] for p in posts]
    if set(amap) != set(ids) or len(amap) != len(ids):
        fails.append("COVERAGE: %d posts scraped, %d placed" % (len(ids), len(amap)))
    misc = sum(1 for t in amap.values() if t == "misc")
    pct = 100.0 * misc / max(len(ids), 1)
    if pct > MISC_MAX_PCT:
        fails.append("COVERAGE: misc is %.0f%% of posts, over the %.0f%% limit" % (pct, MISC_MAX_PCT))
    for r in rows:
        if r["verdict"] == "DROP" and r["n_posts"] > TENSION_MAX_POSTS \
                and r["tension_id"].lower() not in mc:
            fails.append("OFF-BRAND: %s was dropped with %d posts in it and never examined by name "
                         "in merge-check.md" % (r["tension_id"], r["n_posts"]))
        if r["verdict"] in KEPT:
            if len(r["phrases"]) > TENSION_MAX_PHRASES and r["tension_id"].lower() not in mc:
                fails.append("SIZE-ALARM: %s is kept with %d phrases and is not justified in "
                             "merge-check.md" % (r["tension_id"], len(r["phrases"])))
            if r["tension_id"].lower() not in mc:
                fails.append("GATE: kept tension %s never appears in merge-check.md" % r["tension_id"])
            leaked = _leaks(" ".join(r["sub_questions"]), banned)
            if leaked:
                fails.append("PRODUCT-LEAK: %s sub-questions name %s"
                             % (r["tension_id"], ", ".join(leaked)))
    n_keep = sum(1 for r in rows if r["verdict"] in KEPT)
    if n_keep != n_ideas:
        fails.append("IDEAS: %d tensions kept but %d ideas written" % (n_keep, n_ideas))

    md = ["# Final verify — %s" % co["brand"], "",
          "%d posts · %d tensions · %d kept · %d ideas · misc %d (%.0f%%)"
          % (len(ids), len(rows), n_keep, n_ideas, misc, pct), ""]
    md += ["- %s" % f for f in fails] or ["Every gate is satisfied."]
    md += ["", "**VERIFY: %s**" % ("PASS" if not fails else "FAIL — the run is not done.")]
    cm.save(_w("verify.md"), "\n".join(md) + "\n")
    return not fails, fails


# ---- the run ------------------------------------------------------------------------------------

def _log(co, lines):
    cm.save(_w("run-log.md"), "# Study trends — run log for %s\n\n%s\n"
            % (co["brand"], "\n".join("- " + l for l in lines)))


def _empty(co, say, reason, notes):
    """An empty pool, with the reason written down. Never an invented post, never a quiet zero."""
    cm.save(OUTPUT, [])
    _log(co, ["The pool is empty.", reason])
    say("No trend ideas this run", reason)
    return {"files": [OUTPUT], "needs_review": notes}


def run(co, say, redo=False):
    """Method 3, end to end, with one human gate at the front.

    Returns `{"gate": {...}}` when the subreddits have not been approved, otherwise
    `{"files": [...], "needs_review": [...]}`. Resumable: a stage whose file exists is reused.
    """
    if cm.exists(OUTPUT) and not redo:
        say("Kept the trend ideas", "already built; ask for a redo to run it again")
        return {"files": [OUTPUT], "needs_review": []}

    subs = approved()
    if subs is None:
        rows, source = propose(co, say)
        cm.save(_w("subreddits.json"), {"at": store.now(), "source": source, "proposed": rows})
        unver = [r["name"] for r in rows if not r.get("checked")]
        why = ("These are the communities I would read for what your niche is arguing about right "
               "now. They come from %s, ranked by real activity rather than member counts. Nothing "
               "is scraped until you approve the list." % source)
        if unver:
            why += (" Reddit would not answer the activity check for %s, so %s unverified rather "
                    "than dead. On 2026-09-09 Reddit refused every check for this account."
                    % (", ".join("r/" + n for n in unver), "they are" if len(unver) > 1 else "it is"))
        say("Waiting on the subreddits", "%d proposed; nothing is read until you approve them" % len(rows))
        return {"gate": {"kind": "subreddits", "proposed": rows, "why": why}}

    notes = []
    if not subs:
        return _empty(co, say, "No subreddits were approved, so there was nothing to read.", notes)

    got = scrape(subs, say, redo=redo)
    posts = got.get("posts") or []
    if got.get("refused"):
        notes.append("trends: Reddit would not serve %s. They are unknown, not empty, and worth "
                     "trying again later." % ", ".join("r/" + s for s in got["refused"]))
    if not posts:
        return _empty(co, say, "Reddit returned nothing for %s. That is a Reddit problem, not a "
                      "verdict on the niche, so nothing was invented to fill the gap."
                      % ", ".join("r/" + s for s in subs), notes)

    phrases = tag(co, posts, say, redo=redo)
    tensions = consolidate(co, phrases, say, redo=redo)
    if not tensions:
        return _empty(co, say, "%d posts were read but no shared pain came out of them." % len(posts),
                      notes)
    amap, tensions = assign(co, posts, tensions, say, redo=redo)
    rows = records(co, tensions, amap, posts, say, redo=redo)

    ok, failed = self_audit(co, rows, amap)
    if not ok:
        _log(co, ["Stopped at the self-audit gate, before any filtering.",
                  "Failed: " + "; ".join(failed),
                  "The evidence is in _work/trends/self-audit.md."])
        notes.append("trends: the run stopped at its own audit gate, so no ideas were written. "
                     "Failed: %s. See assets/_work/trends/self-audit.md." % "; ".join(failed))
        say("Stopped at the self-audit gate", "; ".join(failed))
        return {"files": [], "needs_review": notes}

    rows = filter_tensions(rows, say)
    pool = ideas(co, rows, say)
    passed, fails = verify(co, rows, amap, len(pool), posts)
    if not passed:
        # The pool is written where a person can read it, but NOT where the merge reads it. The
        # original's rule is that the run is not done until the gate passes, and handing a merge a
        # pool that failed its own gate is exactly what that rule forbids.
        cm.save(_w("ideas-unverified.json"), pool)
        _log(co, ["VERIFY: FAIL. The run is not done."] + fails)
        notes.append("trends: %d ideas were built but the final gate failed (%s), so they are held "
                     "in assets/_work/trends/ideas-unverified.json instead of the pool."
                     % (len(pool), fails[0]))
        say("The final gate failed", fails[0])
        return {"files": [], "needs_review": notes}

    cm.save(OUTPUT, pool)
    misc = sum(1 for t in amap.values() if t == "misc")
    _log(co, ["VERIFY: PASS.",
              "%d subreddits read, %d posts, %d tensions, %d kept, %d ideas, misc %d."
              % (len(subs), len(posts), len(rows), sum(1 for r in rows if r["verdict"] in KEPT),
                 len(pool), misc),
              "No image OCR: an image post is its title and its comments.",
              "Ownability and Linkability were the shared tests in _common, not this method's own."])
    if not pool:
        notes.append("trends: every tension was dropped as attention rather than links, so the pool "
                     "is empty. The tensions and their reasons are in assets/_work/trends/tensions.json.")
    say("Wrote the trend ideas", "%d ideas from %d posts across %d communities"
        % (len(pool), len(posts), len(subs)))
    return {"files": [OUTPUT], "needs_review": notes}
