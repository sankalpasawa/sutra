"""field.py — VOICES FROM THE FIELD: what practitioners actually say about this article's subject.

WHERE THIS SITS IN THE RUN. The original runs it as its own station, between the architect and the
writer: `run_article.py` sequences planner -> architect -> field -> writer, and marks field the one
station whose failure does NOT cost the article ("A FIELD FAILURE DOES NOT [stop everything].
write_body treats voices-from-the-field.md as a block that is either there or empty, so the writer is
fine without it. Losing some Reddit quotes must not cost a finished article overnight."). It reads
`architect/structure.json` (the sections and their jobs), which only exists once the architect has
finished, and it writes one file the body writer reads. So in this app it runs after `headings` (the
architect's last step) and before `write_body`, and a failure is reported and stepped over.

WHY IT EXISTS. The article's cards say what is TRUE. This says what people actually argue about, and
one line of that is what stops a section reading like an encyclopedia. On the owner's own
cost-per-hire piece it contributed 1,273 words. It costs no paid API.

THE FIVE STEPS, as the original runs them (run_field.py):
  1. PLAN      the article decides the queries                       (field-plan.md)
  2. SEARCH    titles only, no discussion opened yet
  3. PROBE     read these / requery / stop, up to PROBE_ROUNDS       (field-probe.md)
  4. HARVEST   download the comments of the shortlisted threads only
  5. WRITE     filter everything against the article, write one file (field-write.md)

Step 3 is the point. Searching is cheap and opening discussions is not, so the run looks at titles
before it spends anything and is allowed to stop early. An earlier build of the original scraped 93
discussions on a subject nobody argues about and produced 192 words.

TWO HONESTY RULES, both kept from the original:
  THE COUNTS COME FROM CODE, NEVER FROM THE MODEL. An earlier build let the model write the coverage
  line and it reported 10,200 comments when 85 had been read.
  NOTHING READ MEANS NOTHING WRITTEN. When no discussion was opened, the writing step is not called at
  all, so there is no chance of a briefing about discussions that do not exist. And when fewer than
  MIN_FINDINGS findings survive the filter, the block is dropped entirely rather than handed to the
  writer as one weak finding it might lean on.

REDDIT. Everything that asks Reddit anything goes through `research/reddit.py`, which reads through a
real browser because plain HTTP gets a flat 403 from Reddit on this machine (proved 2026-09-09). This
module never talks to Reddit itself. When that module is not installed, this station reports that
plainly and the article is written without it.
"""
import re

from .. import llm
from . import _common as C

# ---- the knobs, all named, all here (the original's config.py FIELD_* block) -----------------------
PROBE_ROUNDS = 3            # search rounds before giving up
MAX_READ = 12               # threads whose comments are actually downloaded
RESULTS_PER_QUERY = 8       # search results kept per query, titles only
COMMENTS_PER = 12           # top comments kept per thread
COMMENT_CHARS = 700         # chars of one comment shown to the writing step
OP_CHARS = 400              # chars of the original post shown with it
MIN_FINDINGS = 2            # below this the file is dropped, never handed to the writer as one weak point
MAX_HEADING_WORDS = 12      # the prompt's own ceiling on a finding heading, checked in code

# The Reddit module, looked up once. Tests set this directly to a fake, which is also how this station
# was built before research/reddit.py existed.
REDDIT = None


def reddit():
    """The one place anything asks Reddit anything, or None when it is not installed yet."""
    global REDDIT
    if REDDIT is None:
        try:
            from ..research import reddit as _r
            REDDIT = _r
        except Exception:  # noqa: BLE001 — not built yet, or built and broken: either way, no voices
            REDDIT = False
    return REDDIT or None


# ---- the article, as the prompts see it -------------------------------------------------------------

def _sections_block(st):
    return "\n".join("  %d. %s\n     JOB: %s" % (i, s.get("headline") or "", s.get("job") or "(none)")
                     for i, s in enumerate(st.get("sections") or [], 1)) or "  (no sections)"


def _article(st, ctx):
    return {"title": ctx.get("title") or st.get("h1") or "(none)",
            "angle": ctx.get("angle") or "(none)",
            "spine": st.get("spine") or ctx.get("spine") or "(none)",
            "persona": ctx.get("persona") or "(general professional reader)",
            "sections": _sections_block(st)}


def _sub(name):
    """"r/recruiting", "/r/recruiting" and "recruiting" are the same subreddit.

    NOT lstrip("r/"): that strips any leading 'r' or '/' CHARACTER, so "recruiting" comes back as
    "ecruiting" and the best subreddits are silently rejected as names nobody checked.
    """
    n = str(name or "").strip().strip("/")
    for pre in ("r/", "/r/"):
        if n.lower().startswith(pre):
            n = n[len(pre):]
    return n.strip("/")


def allowed_subreddits():
    """(the checked subreddit names, the file's text). Only names the brand step checked and kept.

    A subreddit that does not exist returns nothing in silence, which is indistinguishable from
    "nobody discusses this". That check happened once, in brand/field_sources.py, and this reads its
    answer rather than guessing again.
    """
    text = C.sh.brand_file("field-sources.md")
    if not text.strip():
        return set(), ""
    subs = set()
    in_table = False
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            in_table = False
            continue
        cell = _sub(s.split("|")[1] if len(s.split("|")) > 1 else "")
        if not cell or cell.lower() in ("subreddit", "---") or set(cell) <= set("-: "):
            in_table = True
            continue
        if in_table and re.fullmatch(r"[A-Za-z0-9_]+", cell):
            subs.add(cell)
    return subs, text


# ---- the Reddit adapter -----------------------------------------------------------------------------
# research/reddit.py answers every call with a three-state verdict: "ok" (it answered and there is
# something), "empty" (it answered and there is genuinely nothing) and "unknown" (we could not look:
# blocked, login-walled, no browser). This module keeps that distinction all the way into the report,
# because "nobody talks about this" and "we were shut out" are different facts, and reading the second
# as the first is exactly the bug that once dropped all 18 of the company's real communities.

def _post(row, where=""):
    """One search result, in the shape the probe and the harvest use. None when it cannot be opened."""
    if not isinstance(row, dict):
        return None
    url = str(row.get("url") or "").strip()
    permalink = str(row.get("permalink") or "")
    if not url and permalink:
        url = "https://www.reddit.com" + permalink
    pid = str(row.get("id") or "")
    if not pid or not url.startswith("http"):
        return None                       # no id means no comment tree, so there is nothing to read
    return {"id": pid, "title": str(row.get("title") or "")[:300], "url": url,
            "where": "r/" + _sub(row.get("subreddit") or where or "?"),
            "score": int(row.get("score") or 0),
            "comments": int(row.get("num_comments") or 0),
            "preview": str(row.get("text") or "")[:OP_CHARS]}


def _comment(row):
    if not isinstance(row, dict):
        return None
    text = str(row.get("text") or row.get("body") or "").strip()
    if not text or text in ("[removed]", "[deleted]"):
        return None
    return {"who": str(row.get("author") or ""), "likes": int(row.get("score") or 0), "text": text}


def _search(mod, sub, query, limit):
    """One search in one subreddit. (posts, state, reason) straight from research/reddit.py."""
    got = mod.search(sub, query, limit=limit) or {}
    return (got.get("posts") or [], str(got.get("state") or "unknown"), str(got.get("reason") or ""))


def _comments(mod, post, limit):
    """The comments on one post. (comments, state, reason). Reddit's comment tree is fetched by the
    post id, never by its url."""
    got = mod.comments(post["id"], limit=limit) or {}
    return (got.get("comments") or [], str(got.get("state") or "unknown"), str(got.get("reason") or ""))


# ---- the step ----------------------------------------------------------------------------------------

def findings(md):
    """The real findings in the written file: every '## ' heading that is not the negative section."""
    return [h for h in re.findall(r"^## (.+)$", md or "", re.M) if "did not show up" not in h.lower()]


def block(md):
    """The writer's FILE 2 block, or "" when this file has nothing worth showing it.

    A FILE THAT FOUND NOTHING MUST NOT APPEAR AT ALL. When fewer than two findings survived the
    filter, field-write.md writes a two-line "nothing useful came back, ignore this file" instead of a
    report. Wrapping that in the rules block would hand the writer a page of instructions about a file
    with nothing in it, and invite it to lean on something that was never there. So the whole block is
    dropped and the writer never learns the step ran.
    """
    body = (md or "").strip()
    if not body or len(findings(body)) < MIN_FINDINGS:
        return ""
    return "\n\n" + C.prompt("field-block", field_file=body).strip() + "\n"


def _nothing(note, say, **extra):
    say("No voices from the field", note)
    report = {"note": note, "queries": [], "results": 0, "read": 0, "comments": 0, "blocked": 0,
              "findings": 0, "rounds": 0, "coverage": "", "words": 0, "log": []}
    report.update(extra)
    return {"markdown": "", "block": "", "report": report}


def run(st, ctx=None, say=lambda *a: None):
    """Read where practitioners argue, and write one briefing the body writer can use.

    Returns {"markdown", "block", "report"}. Never raises: this station is allowed to find nothing,
    and an article is not worth losing over a forum being down.
    """
    ctx = ctx or {}
    a = _article(st, ctx)
    mod = reddit()
    if mod is None:
        return _nothing("the Reddit reader (research/reddit.py) is not installed, so nowhere was read", say)
    allowed, sources_text = allowed_subreddits()
    if not allowed:
        return _nothing("no checked subreddit list on file, so nothing was searched. Build the brand "
                        "pack's field-sources.md first", say)

    say("Looking for what practitioners say in public",
        "%s checked, in %s" % (C.sh.plural(len(allowed), "subreddit"), ", ".join(sorted(allowed))[:160]))

    # ---- Step 1: PLAN ------------------------------------------------------------------------------
    try:
        plan = llm.json_call(C.prompt("field-plan", field_sources=sources_text or "(none)", **a)) or {}
    except Exception as e:  # noqa: BLE001
        return _nothing("the search planner failed (%s), so nothing was searched" % type(e).__name__, say)
    log, seen, pool, shortlist, probes = [], set(), {}, [], []

    def _queries(d):
        out = []
        for item in ((d.get("reddit") or {}).get("queries") or []):
            q = str((item or {}).get("q") or "").strip()
            if not q:
                continue
            # The model writes "r/recruiting" as often as "recruiting". Normalise BEFORE the check, or
            # the guard silently drops every subreddit it was given.
            named = [_sub(s) for s in (item.get("subreddits") or [])]
            subs = [s for s in named if s in allowed]
            dropped = [s for s in named if s not in allowed]
            if dropped:
                log.append('dropped unchecked subreddit(s) %s on query "%s"' % (dropped, q))
            # A query aimed only at rooms nobody checked is not thrown away: it is sent to the busiest
            # checked rooms instead. The guard still holds, because every name here comes from the
            # checked list; all that changes is that a good query survives a bad room.
            out.append({"q": q, "subreddits": subs or sorted(allowed)[:3],
                        "serves": str(item.get("serves") or "")})
        return out

    live = _queries(plan)
    if not live:
        return _nothing("the planner returned no searchable query, so nothing was searched", say)
    say("Planned %s" % C.sh.plural(len(live), "search"),
        " | ".join('"%s" in %s' % (q["q"], ", ".join("r/" + s for s in q["subreddits"])) for q in live)[:400])

    # ---- Steps 2 and 3: search titles, probe, maybe requery ----------------------------------------
    blocked = 0                 # searches Reddit would not let us make. NOT the same as "found nothing".
    for rnd in range(1, PROBE_ROUNDS + 1):
        found = []
        for item in live:
            for sub in item["subreddits"]:
                try:
                    rows, state, reason = _search(mod, sub, item["q"], RESULTS_PER_QUERY)
                except Exception as e:  # noqa: BLE001 — one dead search never stops the station
                    rows, state, reason = [], "unknown", "%s: %s" % (type(e).__name__, str(e)[:80])
                if state == "unknown":
                    blocked += 1
                    log.append('could not search "%s" in r/%s: %s' % (item["q"], sub, reason))
                    say('Could not search "%s" in r/%s' % (item["q"], sub),
                        reason or "Reddit would not answer, so this is unknown, not empty")
                    continue
                new = 0
                for row in rows[:RESULTS_PER_QUERY]:
                    p = _post(row, sub)
                    if not p or p["url"] in seen:
                        continue
                    seen.add(p["url"])
                    p["query"], p["serves"] = item["q"], item["serves"]
                    found.append(p)
                    new += 1
                say('Searched "%s" in r/%s' % (item["q"], sub),
                    "%d result(s), %d new" % (len(rows), new))
        for p in found:
            pool[len(pool)] = p
        if not found and rnd > 1:
            say("Nothing new came back", "round %d of %d" % (rnd, PROBE_ROUNDS))
            break
        block_txt = "\n".join(
            '  [%d] %s | %dc %dpts | %s' % (i, p["where"][:26], p["comments"], p["score"], p["title"][:96])
            for i, p in pool.items() if i not in shortlist)
        already = ("Already shortlisted for reading: %d discussion(s)." % len(shortlist)
                   if shortlist else "Nothing shortlisted yet.")
        last = ("THIS IS THE LAST ROUND. `requery` will not be run again, so choose `read` or `stop`."
                if rnd == PROBE_ROUNDS else "")
        try:
            pr = llm.json_call(C.prompt("field-probe", round=rnd, max_rounds=PROBE_ROUNDS, already=already,
                                        results=block_txt or "(nothing)", last_round=last, **a)) or {}
        except Exception as e:  # noqa: BLE001
            log.append("probe failed in round %d: %s" % (rnd, str(e)[:90]))
            break
        probes.append(pr)
        d = pr.get("reddit") or {}
        act = str(d.get("action") or "stop").lower()
        say("Round %d: %s" % (rnd, act.upper()), str(d.get("why") or "")[:140])
        if act == "read":
            ids = [int(i) for i in (d.get("read") or []) if str(i).isdigit() and int(i) in pool]
            shortlist += [i for i in ids if i not in shortlist]
            say("Shortlisted %s to read" % C.sh.plural(len(ids), "discussion"),
                "; ".join(pool[i]["title"][:60] for i in ids)[:200])
            break
        if act == "requery" and rnd < PROBE_ROUNDS:
            live = _queries(pr)
            if not live:
                break
            continue
        break

    shortlist = sorted(shortlist, key=lambda i: -pool[i]["comments"])[:MAX_READ]
    if not shortlist:
        # THE TWO ANSWERS MUST NOT READ THE SAME. Reddit shutting us out is not the same finding as
        # Reddit answering and having nothing, and the note says which one this was.
        why = ("%d of the searches could not be made at all (Reddit would not answer), so this is "
               "unknown, not empty" % blocked if blocked else
               "nothing worth reading came back: %d result(s) looked at across %d search round(s), "
               "and none of them was a discussion about this subject" % (len(pool), max(1, len(probes))))
        return _nothing(why, say, results=len(pool), rounds=len(probes), blocked=blocked, log=log)

    # ---- Step 4: HARVEST ---------------------------------------------------------------------------
    say("Reading %s" % C.sh.plural(len(shortlist), "discussion"), "the comments, not just the titles")
    bundle = []
    for i in shortlist:
        p = pool[i]
        try:
            raw, state, reason = _comments(mod, p, COMMENTS_PER * 4)
        except Exception as e:  # noqa: BLE001
            raw, state, reason = [], "unknown", "%s: %s" % (type(e).__name__, str(e)[:80])
        if state == "unknown":
            blocked += 1
            log.append("could not read %s: %s" % (p["url"], reason))
            say("Could not read a discussion", "%s (%s)" % (p["title"][:60], reason[:70]))
            continue
        cs = [c for c in (_comment(r) for r in raw) if c and len(c["text"]) > 25]
        cs.sort(key=lambda c: -c["likes"])
        cs = cs[:COMMENTS_PER]
        if not cs:
            continue
        bundle.append({"where": p["where"], "title": p["title"], "query": p["query"],
                       "engagement": "%dpts %dc" % (p["score"], p["comments"]),
                       "op": p.get("preview") or "", "comments": cs})
        say("Read: %s" % p["title"][:60], "%s in %s" % (C.sh.plural(len(cs), "comment"), p["where"]))

    if not bundle:
        return _nothing("the shortlisted discussions could not be opened, so nothing was read", say,
                        results=len(pool), rounds=len(probes), read=len(shortlist), blocked=blocked, log=log)

    # THE COUNTS COME FROM CODE, NEVER FROM THE MODEL.
    n_c = sum(len(b["comments"]) for b in bundle)
    coverage = ("%d discussion(s) read and %d comments, all on Reddit. %d results were looked at "
                "across %d search round(s)." % (len(bundle), n_c, len(pool), max(1, len(probes)))
                + (" %d request(s) Reddit would not answer, so those are unknown rather than empty."
                   % blocked if blocked else ""))
    say("Coverage", coverage)

    # ---- Step 5: WRITE -----------------------------------------------------------------------------
    blocks = []
    for b in bundle:
        lines = ['### %s  (%s · %s · found by: "%s")' % (b["title"], b["where"], b["engagement"], b["query"])]
        if b["op"]:
            lines.append("  OP: " + b["op"])
        for c in b["comments"]:
            lines.append("  (%d) %s" % (c["likes"], c["text"][:COMMENT_CHARS]))
        blocks.append("\n".join(lines))
    try:
        md = llm.text(C.prompt("field-write", coverage=coverage, bundle="\n\n".join(blocks), **a)) or ""
    except Exception as e:  # noqa: BLE001
        return _nothing("the writing step failed (%s), so no file was produced" % type(e).__name__, say,
                        results=len(pool), rounds=len(probes), read=len(bundle), comments=n_c,
                        blocked=blocked, log=log)
    md = re.sub(r"^```[a-z]*\n|\n```$", "", md.strip())
    # The prompt bans em dashes and the model uses them anyway. Ask once, then enforce in code.
    n_dash = md.count("—")
    md = re.sub(r"\s*—\s*", ", ", md)

    heads = findings(md)
    over = [h for h in heads if len(h.split()) > MAX_HEADING_WORDS]
    if over:
        log.append("%d heading(s) over %d words" % (len(over), MAX_HEADING_WORDS))
    blk = block(md)
    note = ("%d finding(s) from %s and %s. %s"
            % (len(heads), C.sh.plural(len(bundle), "discussion"), C.sh.plural(n_c, "comment"),
               "The writer gets them." if blk else
               "Fewer than %d, so the writer is not shown the file at all." % MIN_FINDINGS))
    say("Voices from the field: %s" % C.sh.plural(len(heads), "finding"),
        "%d words%s" % (len(md.split()), ", %d em dash(es) replaced" % n_dash if n_dash else ""))
    return {"markdown": md, "block": blk,
            "report": {"note": note, "queries": [q["q"] for q in live], "results": len(pool),
                       "rounds": len(probes), "read": len(bundle), "comments": n_c, "blocked": blocked,
                       "findings": len(heads), "coverage": coverage, "words": len(md.split()),
                       "em_dashes_replaced": n_dash, "log": log}}
