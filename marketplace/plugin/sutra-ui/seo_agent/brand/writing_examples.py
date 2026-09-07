"""brand/writing_examples.py — builder 5: five real articles that embody the voice, pasted in full.

Port of 4-writing-examples/scripts/run_writing_examples.py.

Step 1 classify and select (code): the pool is knowledge/top-pages.json in its own order (traffic
       order, taken as-is), filtered to the classified editorial types, format tagged from URL
       signals, batches picked traffic-first with format diversity.
Step 2 score and annotate (model per article, against brand-voice.md ONLY). Rounds of WE_BATCH
       until KEEP on-voice articles survive, or WE_ROUNDS is spent (the recipe expects several rounds).
Step 3 assemble (code, pure): metadata + What Makes It Great + the FULL VERBATIM body per kept example.

Reads:  knowledge/top-pages.json, the catalogue, brand/type-roles.json, brand/brand-voice.md.
Writes: brand/_work/writing-examples/scored.json · brand/writing-examples.md
"""
import re

from .. import llm
from . import _common as cm

OUTPUT = "writing-examples.md"
WORK = "_work/writing-examples/"

KEEP = 5                    # the recipe's final count
WE_BATCH = 8                # articles scored per round (recipe: pick >=7)
WE_ROUNDS = 4               # scoring rounds before giving up loudly
WE_BODY_CAP = 16000         # chars of one article inside a score prompt
MIN_FORMATS = 3             # the recipe wants >=3 distinct formats

FORMAT_SIGNALS = [
    (re.compile(r"what-|definition|types-of", re.I), "Definitional / pillar"),
    (re.compile(r"top-\d|-questions|\d+-ways", re.I), "Listicle"),
    (re.compile(r"how-to|-process|-steps", re.I), "Step-by-step how-to"),
    (re.compile(r"-vs-|alternatives", re.I), "Comparison"),
]
OTHER_FORMAT = "Thought-leadership / other"
_CTA_CHROME = re.compile(r"\n(Try for free|Book a demo|Sign up for free|View plans)[^\n]*$", re.I)


def tag_format(url):
    return next((k for rx, k in FORMAT_SIGNALS if rx.search(url)), OTHER_FORMAT)


# A writing example is a published ARTICLE. Found live 2026-09-04: with the homepage classified
# under an editorial type, Example 1 was the homepage, its title carried the nav's dot leaders
# ("Hire for proven skills,not ········"), and its keyword was blank. The recipe asks for five real
# published articles, so the pool is filtered here regardless of what type-roles said.
_NOT_ARTICLE = ("/pricing", "/contact", "/about", "/careers", "/login", "/signup", "/sign-up",
                "/demo", "/book-", "/partners", "/integrations", "/customers", "/terms",
                "/privacy", "/security", "/author/", "/tag/", "/category/", "/sitemap")


def _is_article(r, co, strict=True):
    """The homepage, a commercial landing page and a junk-titled page are never examples.
    strict=False keeps the hard exclusions and drops only the length floor."""
    url = (r.get("url") or "").rstrip("/")
    root = "https://" + (co.get("domain") or "").lstrip("www.").rstrip("/")
    if not url or url == root or url == root.replace("https://", "http://"):
        return False                                   # the homepage
    path = url.split("//", 1)[-1].split("/", 1)
    if len(path) < 2 or not path[1]:
        return False                                   # a bare domain or a language root
    low = url.lower()
    if any(seg in low for seg in _NOT_ARTICLE):
        return False
    title = (r.get("title") or "").strip()
    if not title or "\u00b7\u00b7" in title or "····" in title:
        return False                                   # nav furniture scraped as a title
    if not strict:
        return True
    return len((r.get("body") or "").split()) >= 300    # an example has to be long enough to learn from


def candidates(co, say):
    cat = {}
    for r in cm.ok_pages(co.get("language_code")):
        cat[r["url"]] = r
        cat[r["url"].rstrip("/")] = r
    roles = cm.roles()
    etypes = set(roles.get("editorial_types", [])) if roles else set()
    pool = cm.top_pages()                       # top-pages order = traffic order (recipe: as-is)
    if not pool:
        say("No top-pages file", "the pool is the site index ordered by its own traffic column")
        pool = [{"url": r["url"], "traffic": r.get("traffic"), "top_keyword": r.get("top_keyword")}
                for r in sorted(cm.ok_pages(co.get("language_code")), key=lambda r: -(r.get("traffic") or 0))]
    out, seen, dropped = [], set(), 0
    for row in pool:
        r = cat.get(row["url"]) or cat.get(row["url"].rstrip("/"))
        if not r or r["url"] in seen or (etypes and r.get("type") not in etypes):
            continue
        if not _is_article(r, co):
            dropped += 1
            continue
        seen.add(r["url"])
        out.append({"url": r["url"], "traffic": str(row.get("traffic_clean") or row.get("traffic") or ""),
                    "keyword": str(row.get("top_keyword") or r.get("top_keyword") or ""),
                    "format": tag_format(r["url"]), "title": r.get("title") or "", "body": r.get("body") or ""})
    if len(out) < WE_BATCH and dropped:
        # a filter that empties the pool is worse than no filter: fall back to everything but the
        # homepage and the junk-titled pages, and say the standard was relaxed
        out, seen = [], set()
        for row in pool:
            r = cat.get(row["url"]) or cat.get(row["url"].rstrip("/"))
            if not r or r["url"] in seen or (etypes and r.get("type") not in etypes):
                continue
            if not _is_article(r, co, strict=False):
                continue
            seen.add(r["url"])
            out.append({"url": r["url"], "traffic": str(row.get("traffic_clean") or row.get("traffic") or ""),
                        "keyword": str(row.get("top_keyword") or r.get("top_keyword") or ""),
                        "format": tag_format(r["url"]), "title": r.get("title") or "", "body": r.get("body") or ""})
        say("Relaxed the article filter", "too few full-length articles, so shorter pages are allowed in")
    say("Built the pool", "%d editorial candidates (types: %s)%s"
        % (len(out), sorted(etypes) or "URL-signal fallback",
           "; %d pages dropped as not articles" % dropped if dropped else ""))
    return out


def diverse_batch(pool, used, n):
    """Traffic-first with format diversity: round-robin the formats, highest-traffic first (recipe 1.5)."""
    by_fmt = {}
    for c in pool:
        if c["url"] not in used:
            by_fmt.setdefault(c["format"], []).append(c)
    batch = []
    while len(batch) < n and any(by_fmt.values()):
        for fmt in list(by_fmt):
            if by_fmt[fmt] and len(batch) < n:
                batch.append(by_fmt[fmt].pop(0))
    return batch


def score(co, article, voice):
    out = llm.json_call(cm.fill(cm.prompt("score-article"), brand=co["brand"], url=article["url"],
                                keyword=article["keyword"], voice=voice, body=article["body"][:WE_BODY_CAP]))
    out = dict(out) if isinstance(out, dict) else {}
    try:
        out["score"] = float(out.get("score") or 0)
    except (TypeError, ValueError):
        out["score"] = 0.0
    out["verdict"] = "on-voice" if str(out.get("verdict") or "").lower().startswith("on") else "off-voice"
    wm = out.get("what_makes_it_great") or []
    out["what_makes_it_great"] = [str(x) for x in wm] if isinstance(wm, list) else [str(wm)]
    out.update(article)
    return out


def assemble(co, kept, pool):
    fmts = sorted({k["format"] for k in kept})
    parts = ["# %s Writing Examples" % co["brand"], "",
             "<!-- Built by the writing-examples builder from the traffic data + the site catalogue;",
             "     voice-scored against brand-voice.md; scores in brand/_work/writing-examples/scored.json.",
             "     Format mix: %s. -->" % ", ".join(fmts), "",
             "Five real, published %s articles that genuinely embody `brand-voice.md` — each pasted" % co["brand"],
             "in full and annotated with why it's exemplary. Show, don't tell: imitate these.", ""]
    if len(fmts) < MIN_FORMATS:
        parts.insert(4, "> ⚑ HUMAN DECISION: only %d formats survived the voice gate (recipe wants ≥%d) — review." % (len(fmts), MIN_FORMATS))
    for i, k in enumerate(kept, 1):
        body = k.get("body") or next((c["body"] for c in pool if c["url"] == k["url"]), "")
        # strip trailing CTA/junk chrome lines (page artifacts, not article text)
        body = _CTA_CHROME.sub("", body)
        parts += ["## Example %d: %s" % (i, k.get("h1") or k.get("title") or ""), "",
                  "**URL**: %s" % k["url"],
                  "**Primary Keyword**: %s" % k["keyword"],
                  "**Format**: %s" % k["format"],
                  "**Voice Score**: %s/10" % (int(k["score"]) if float(k["score"]).is_integer() else k["score"]),
                  "**Word Count**: ~%d words" % len(body.split()), "",
                  "**What Makes It Great**:"]
        parts += ["- %s" % r for r in k.get("what_makes_it_great") or []]
        parts += ["", "**Full Content** (verbatim):", "", "```", body.strip(), "```", ""]
    return "\n".join(parts) + "\n", fmts


def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        say("Kept writing-examples.md", "already built; ask for a redo to rebuild it")
        return {"files": [OUTPUT], "needs_review": []}
    voice = cm.read("brand-voice.md")
    if not voice.strip():
        raise RuntimeError("There is no brand-voice.md yet; it is the only yardstick the articles are scored against.")
    pool = candidates(co, say)
    if not pool:
        raise RuntimeError("No editorial articles were found to pick writing examples from.")
    scored = {}
    if not redo:
        for s in (cm.read(WORK + "scored.json") or []):
            if isinstance(s, dict) and s.get("url"):
                scored[s["url"]] = s
    for rnd in range(1, WE_ROUNDS + 1):
        on_voice = [s for s in scored.values() if s.get("verdict") == "on-voice"]
        if len(on_voice) >= KEEP:
            break
        batch = diverse_batch(pool, set(scored), WE_BATCH)
        if not batch:
            say("The pool is exhausted", "every candidate has been scored")
            break
        say("Round %d: scoring %d articles" % (rnd, len(batch)), "%d on-voice so far" % len(on_voice))
        for art, res, err in cm.parallel(lambda a: score(co, a, voice), batch, say, "Scoring articles", every=4):
            if err:
                say("Could not score an article", "%s: %s" % (art["url"], str(err)[:80]))
            else:
                scored[res["url"]] = res
        cm.save(WORK + "scored.json", [{k: v for k, v in s.items() if k != "body"} for s in scored.values()])
    on_voice = sorted([s for s in scored.values() if s.get("verdict") == "on-voice"], key=lambda s: -float(s.get("score") or 0))
    kept = on_voice[:KEEP]
    notes = []
    if len(kept) < KEEP:
        notes.append("writing-examples.md: only %d on-voice articles after %d rounds; shipped what survived" % (len(kept), WE_ROUNDS))
        say("Fewer than %d on-voice articles" % KEEP, "only %d survived after %d rounds; shipping what survived" % (len(kept), WE_ROUNDS))
    text, fmts = assemble(co, kept, pool)
    cm.save(OUTPUT, text)
    if len(fmts) < MIN_FORMATS:
        notes.append("writing-examples.md: only %d formats survived the voice gate (recipe wants ≥%d)" % (len(fmts), MIN_FORMATS))
    say("Assembled the writing examples", "%d examples across %d formats" % (len(kept), len(fmts)))
    return {"files": [OUTPUT], "needs_review": notes}
