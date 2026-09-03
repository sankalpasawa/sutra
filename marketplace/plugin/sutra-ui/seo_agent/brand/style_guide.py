"""brand/style_guide.py — builder 3: the mechanics of how this company's blogs are written.

Port of 2-style-guide/scripts/run_style_guide.py.

Step 1 pick the top editorial blogs (code: the classified editorial types, or the recipe's URL
       signals when no classification exists; traffic order; SG_TOP_BLOGS of them).
Step 2 analyse them in batches (the recipe's three sub-agents), then MERGE IN CODE: yes/no signals
       by majority, list signals by union, free-text signals carried per batch for the filler to weigh.
Step 3 fill the recipe's template, lifted verbatim, and check no [BLOGS]/[STANDARD]/[COMPANY] tag survives.

Reads:  the catalogue + brand/type-roles.json.
Writes: brand/_work/style-guide/{top-blogs.json, analysis.json} · brand/style-guide.md
"""
import collections
import json
import re

from .. import llm
from . import _common as cm

OUTPUT = "style-guide.md"
WORK = "_work/style-guide/"

TOP_BLOGS = 30
BATCHES = 3
SG_BODY_CAP = 9000           # per blog inside a batch prompt

_BLOG_HINT = re.compile(r"what-|how-to|top-\d|-vs-|types-of|-guide|-tips|-questions|-process|definition|steps", re.I)

ENUM_SIGNALS = ["headline_case", "oxford_comma", "quote_style"]                    # majority wins (recipe rule)
LIST_SIGNALS = ["industry_terms", "acronyms", "preferred_words", "avoided_words"]  # union + dedupe
TEXT_SIGNALS = ["brand_naming", "em_dash_usage", "ellipses", "number_style"]       # carried per batch
_TAG = re.compile(r"\[(?:BLOGS|STANDARD|COMPANY)[^\]]*\]")


def pick_blogs(co, say):
    rows = cm.ok_pages(co.get("language_code"))
    roles = cm.roles()
    if roles:
        etypes = set(roles.get("editorial_types", []))
        say("Editorial page types", "classified for this company: %s" % sorted(etypes))
        blogs = [r for r in rows if r.get("type") in etypes]
    else:
        say("Editorial page types", "no type roles on file, so the recipe's URL-signal fallback is used")
        blogs = [r for r in rows if _BLOG_HINT.search(r["url"])]
    tmap = cm.traffic_map()
    blogs.sort(key=lambda r: cm.traffic_of(r, tmap), reverse=True)
    top = [{"url": r["url"], "title": r.get("title") or "", "traffic": str(int(cm.traffic_of(r, tmap))),
            "body": (r.get("body") or "")[:SG_BODY_CAP]} for r in blogs[:TOP_BLOGS]]
    cm.save(WORK + "top-blogs.json", top)
    say("Picked the top blogs", "%d editorial pages, most-read first" % len(top))
    return top


def merge(results):
    """The recipe's merge rule, in code: enum signals by majority, lists by union, text per batch."""
    merged = {}
    for s in ENUM_SIGNALS:
        votes = [str(r.get(s)) for r in results if r.get(s)]
        merged[s] = collections.Counter(votes).most_common(1)[0][0] if votes else ""
    for s in LIST_SIGNALS:
        seen, u = set(), []
        for r in results:
            items = r.get(s) or []
            if isinstance(items, str):
                items = [items]
            for item in items:
                k = str(item).strip().lower()
                if k and k not in seen:
                    seen.add(k)
                    u.append(item)
        merged[s] = u
    for s in TEXT_SIGNALS:
        merged[s] = " | ".join("batch%d: %s" % (i + 1, r.get(s, "")) for i, r in enumerate(results) if r.get(s))
    return merged


def analyze(co, top, say):
    n = max(1, len(top) // BATCHES)
    batches = [top[i:i + n] for i in range(0, len(top), n)][:BATCHES + 1]
    tpl = cm.prompt("analyze-blogs")

    def one(batch):
        block = "\n\n".join("### %s\nURL: %s\n%s" % (b["title"], b["url"], b["body"]) for b in batch)
        return llm.json_call(cm.fill(tpl, brand=co["brand"], blogs=block))

    say("Analysing the blogs", "%d batches, %d at a time" % (len(batches), llm.PARALLEL))
    results = []
    for batch, res, err in cm.parallel(one, batches, say, "Analysing blog batches", every=1):
        if err:
            say("A blog batch could not be analysed", str(err)[:90])
        elif isinstance(res, dict):
            results.append(res)
    if not results:
        raise RuntimeError("No blog batch could be analysed, so there are no observed style signals.")
    merged = merge(results)
    cm.save(WORK + "analysis.json", merged)
    say("Merged the observations", "majority for %s; union for %s" % (", ".join(ENUM_SIGNALS), ", ".join(LIST_SIGNALS)))
    return merged


def fill(co, top, merged, say, redo_notes=""):
    blog_table = "\n".join("| %d | %s | %s | %s |" % (i + 1, b["traffic"], b["title"][:60], b["url"]) for i, b in enumerate(top))
    p = cm.fill(cm.prompt("fill-template"), brand=co["brand"], niche=co.get("niche_definition") or "",
                template=cm.template("style-guide"), analysis=json.dumps(merged, indent=1, ensure_ascii=False),
                blog_table=blog_table,
                redo_notes=("\nREVIEWER FINDINGS to fold in (implement each concretely):\n%s\n" % redo_notes) if redo_notes else "")
    draft = cm.strip_fence(llm.text(p))
    cm.save(OUTPUT, draft)
    leftovers = _TAG.findall(draft)
    say("Filled the style guide", "%d words; %d unresolved template tags" % (cm.words(draft), len(leftovers)))
    return draft, leftovers


def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        say("Kept style-guide.md", "already built; ask for a redo to rebuild it")
        return {"files": [OUTPUT], "needs_review": []}
    top = pick_blogs(co, say)
    if not top:
        raise RuntimeError("No editorial blog pages were found in the site index, so a style guide cannot be observed.")
    merged = analyze(co, top, say)
    draft, leftovers = fill(co, top, merged, say)
    notes = []
    if leftovers:
        notes.append("style-guide.md: %d template tags left unresolved (%s)" % (len(leftovers), ", ".join(sorted(set(leftovers))[:4])))
    n = cm.count_lines(draft, "confirm with marketing")
    if n:
        notes.append("style-guide.md: %d lines to confirm with marketing" % n)
    return {"files": [OUTPUT], "needs_review": notes}
