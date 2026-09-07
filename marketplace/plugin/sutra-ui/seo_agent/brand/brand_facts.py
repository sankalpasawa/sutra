"""brand/brand_facts.py — builder 1: the company's real numbers, stories and opinions.

Port of 0-brand-facts (instantiate.py, draft_stats.py, draft_stories.py, run_brand_facts.py).

The one rule: the machine never invents a fact and never clobbers a confirmed one. The three
templates are instantiated once (an existing file is SEED and is never overwritten). Stats and
stories the company's own site already publishes are machine-drafted into the tables, every row
marked ⚠️ with its source URL. The human gate is the edit: a row loses its ⚠️ when a person confirms
it. Once a file carries a confirmed row, new candidates go to brand/_drafts/<name>-new-candidates.md
beside it, never over it. Opinions are interview-only: the machine never drafts one.

Reads:  the catalogue + brand/type-roles.json.
Writes: brand/stats.md · brand/opinions.md · brand/stories.md (+ brand/_drafts/*-new-candidates.md)
"""
import re

from .. import llm
from . import _common as cm

FILES = ["stats.md", "opinions.md", "stories.md"]

# --- candidate selection (which catalogue pages the model reads) ------------------------------
# Defaults chosen on the first company's page-type mix; type-roles.json supersedes them per company.
# A Type absent from a company's CMS simply yields zero candidates: reported, never a crash.
STAT_PAGE_TYPES = ["page", "certifications"]          # where companies publish their own numbers
STAT_TOP_PAGES = 25         # cap on any big generic bucket, by traffic desc (the homepage is always added)
STORY_PAGE_TYPES = ["successstory", "press-release", "podcast"]
BODY_CHAR_CAP = 12000       # chars of page body per prompt (median page ~1.8k words fits whole)

BUCKETS = {"scale": "Product / scale", "results": "Results / proof", "credibility": "Credibility"}
WARN = "⚠️"


# ---- step 1: instantiate ---------------------------------------------------------------------

def instantiate(co):
    """Templates -> brand/. ONLY IF MISSING: an existing file is SEED and is never overwritten."""
    made, kept = [], []
    for name in FILES:
        if cm.exists(name):
            kept.append(name)
            continue
        body = cm.fill(cm.template(name[:-3]), brand=co["brand"], niche=co.get("niche_definition") or "the niche")
        cm.save(name, body)
        made.append(name)
    return made, kept


# ---- the gate, in code ------------------------------------------------------------------------

def human_confirmed(text):
    """True if a human has confirmed anything here: a table row (or ### entry) with no ⚠️ left on it."""
    for line in (text or "").splitlines():
        t = line.strip()
        if (t.startswith("|") and t.count("|") >= 3 and WARN not in t
                and "---" not in t and not t.lower().startswith("| stat")
                and not t.lower().startswith("| <")):
            return True
        if t.startswith("### ") and WARN not in t and not t.startswith("### <"):
            return True
    return False


def already_drafted(text):
    """True once the file carries a ⚠️ candidate row (a table row or a ### entry)."""
    return any(WARN in ln and ln.strip().startswith(("|", "###")) for ln in (text or "").splitlines())


# ---- step 2: draft stats ---------------------------------------------------------------------

def _stat_candidates(co, rows, say):
    home = [r for r in rows if cm.is_home(r["url"], co["domain"])]
    picked = {r["url"]: r for r in home}
    roles = cm.roles()
    if roles:
        types = sorted(set(roles.get("stat_types", [])))
        say("Stat candidate types", "classified for this company: %s" % types)
    else:
        types = STAT_PAGE_TYPES
        say("Stat candidate types", "no type roles on file, so the default type names %s are used" % types)
    for t in types:
        grp = [r for r in rows if r.get("type") == t.strip()]
        if len(grp) > STAT_TOP_PAGES:           # any big generic bucket: cap by traffic
            grp.sort(key=lambda r: r.get("traffic") or 0, reverse=True)
            grp = grp[:STAT_TOP_PAGES]
        for r in grp:
            picked[r["url"]] = r
    return list(picked.values())


def _extract_stats(co, row):
    p = cm.fill(cm.prompt("extract-stats"), brand=co["brand"], niche=co.get("niche_definition") or "",
                url=row["url"], title=row.get("title") or "", body=(row.get("body") or "")[:BODY_CHAR_CAP])
    out = llm.json_call(p)
    if isinstance(out, dict):
        out = out.get("stats") or out.get("items") or [out]
    if not isinstance(out, list):
        return []
    return [dict(s, url=row["url"]) for s in out if isinstance(s, dict) and s.get("value") and s.get("stat")]


def _dedupe(found):
    """Same normalised value + similar label keeps the first (the highest-traffic page came first)."""
    seen, rows = set(), []
    for s in found:
        key = (str(s["value"]).strip().lower(), str(s["stat"]).strip().lower()[:30])
        if key in seen:
            continue
        seen.add(key)
        rows.append(s)
    return rows


def _stat_row(s):
    return "| %s | %s | %s %s — \"%s\" |" % (s["stat"], s["value"], WARN, s["url"], str(s.get("quote") or "")[:80])


def strip_drafts(text, kind):
    """Remove the machine's earlier ⚠️ drafts (and its note) before redrafting, so a redo replaces
    them rather than piling a second copy on top. Confirmed rows carry no ⚠️ and are untouched."""
    out, skipping = [], False
    for ln in text.splitlines():
        t = ln.strip()
        if t.startswith("> Machine-drafted"):
            continue
        if kind == "stats" and t.startswith("|") and WARN in t:
            continue
        if kind == "stories":
            if t.startswith("### " + WARN):
                skipping = True
                continue
            if skipping and (t.startswith("### ") or t.startswith("## ")):
                skipping = False
            if skipping:
                continue
        out.append(ln)
    return "\n".join(out) + "\n"


def _fill_stats_template(text, by_bucket, note):
    """Insert the drafted rows into the instantiated template's own three tables, so the rule
    header (which tells the human what ⚠️ means) survives."""
    text = strip_drafts(text, "stats")
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        out.append(ln)
        if i == 0 and ln.startswith("# "):
            out += ["", note]
        for b, title in BUCKETS.items():
            if ln.strip() == "## " + title and i + 2 < len(lines) and lines[i + 2].strip().startswith("|---"):
                out += [lines[i + 1], lines[i + 2]]
                out += [_stat_row(s) for s in by_bucket.get(b, [])]
                i += 2
                break
        i += 1
    return "\n".join(out) + "\n"


def draft_stats(co, rows, say):
    cands = _stat_candidates(co, rows, say)
    if not cands:
        say("No stat candidate pages", "the catalogue has no page of a stat-carrying type; the draft was skipped")
        return None, 0
    say("Reading pages for the company's own numbers", "%d candidate pages, %d at a time" % (len(cands), llm.PARALLEL))
    found = []
    for row, res, err in cm.parallel(lambda r: _extract_stats(co, r), cands, say, "Reading stat pages"):
        if err:
            say("Could not read a page for stats", "%s: %s" % (row["url"], str(err)[:90]))
        else:
            found.extend(res)
    rows_ = _dedupe(found)
    by_bucket = {"scale": [], "results": [], "credibility": []}
    for s in rows_:
        b = s.get("bucket") if s.get("bucket") in by_bucket else "scale"
        by_bucket[b].append(s)

    current = cm.read("stats.md")
    if human_confirmed(current):            # a confirmed row (⚠️ removed) is never clobbered
        lines = ["# Stats draft — %s (machine-drafted %s — EVERY row %s unconfirmed)" % (co["brand"], cm.today(), WARN),
                 "", "> Review each row. Confirmed -> copy into `stats.md` and drop the %s. Wrong/duplicate -> delete." % WARN,
                 "> Drafted from %d pages of the company's own site; %d unique candidates." % (len(cands), len(rows_)), ""]
        for b, title in BUCKETS.items():
            lines += ["## " + title, "| Stat | Value | Source-note |", "|---|---|---|"]
            lines += [_stat_row(s) for s in by_bucket[b]]
            lines.append("")
        cm.save("_drafts/stats-new-candidates.md", "\n".join(lines))
        say("stats.md carries confirmed rows", "new candidates were written beside it: brand/_drafts/stats-new-candidates.md")
        return "_drafts/stats-new-candidates.md", len(rows_)

    note = ("> Machine-drafted %s from %d pages of the company's own site: %d unique candidates. EVERY row marked %s "
            "is unconfirmed. Confirm it (drop the %s, add \"confirmed by\"), or delete it."
            % (cm.today(), len(cands), len(rows_), WARN, WARN))
    cm.save("stats.md", _fill_stats_template(current, by_bucket, note))
    say("Drafted the stats", "%d candidate numbers, every one marked %s until you confirm it" % (len(rows_), WARN))
    return "stats.md", len(rows_)


# ---- step 3: draft stories -------------------------------------------------------------------

def _story_candidates(rows, say):
    roles = cm.roles()
    if roles:
        types = set(roles.get("story_types", []))
        say("Story candidate types", "classified for this company: %s" % sorted(types))
    else:
        types = set(STORY_PAGE_TYPES)
        say("Story candidate types", "no type roles on file, so the default type names %s are used" % sorted(types))
    return [r for r in rows if r.get("type") in types]


def _extract_story(co, row):
    p = cm.fill(cm.prompt("extract-stories"), brand=co["brand"], niche=co.get("niche_definition") or "",
                url=row["url"], title=row.get("title") or "", body=(row.get("body") or "")[:BODY_CHAR_CAP])
    out = llm.json_call(p)
    if isinstance(out, dict) and out.get("story") and not out.get("none"):
        return dict(out, url=row["url"])
    return None


def _story_block(s):
    return ["### %s %s" % (WARN, s.get("title") or "(untitled)"),
            str(s.get("story") or ""),
            "- Point it makes: %s" % (s.get("point") or ""),
            "- Number (if any): %s" % (s.get("number") or ""),
            "- Source: %s  (machine draft — needs approval)" % s["url"], ""]


def _fill_stories_template(text, stories):
    text = strip_drafts(text, "stories")
    lines = text.splitlines()
    blocks = []
    for s in stories:
        blocks += _story_block(s)
    if not blocks:
        blocks = ["*(none yet)*"]
    out, placed = [], False
    for i, ln in enumerate(lines):
        if not placed and ln.strip() == "*(none yet)*" and any(l.strip() == "## Stories" for l in lines[:i]):
            out += blocks
            placed = True
            continue
        if not placed and ln.startswith("## The interview"):
            out += blocks
            placed = True
        out.append(ln)
    if not placed:
        out += [""] + blocks
    return "\n".join(out) + "\n"


def draft_stories(co, rows, say):
    cands = _story_candidates(rows, say)
    if not cands:
        say("No story candidate pages", "the catalogue has no page of a story-carrying type; the draft was skipped")
        return None, 0
    say("Reading the company's own success stories", "%d candidate pages, %d at a time" % (len(cands), llm.PARALLEL))
    stories = []
    for row, res, err in cm.parallel(lambda r: _extract_story(co, r), cands, say, "Reading story pages"):
        if err:
            say("Could not read a page for stories", "%s: %s" % (row["url"], str(err)[:90]))
        elif res:
            stories.append(res)

    current = cm.read("stories.md")
    if human_confirmed(current):            # an approved entry (⚠️ removed) is never clobbered
        lines = ["# Stories draft — %s (machine-drafted — EVERY entry %s unconfirmed)" % (co["brand"], WARN), "",
                 "> Review each. Approved -> copy into `stories.md` in its format and sign it. Weak/wrong -> delete.",
                 "> Drafted from %d story-type pages; %d carried a real anecdote." % (len(cands), len(stories)), ""]
        for s in stories:
            lines += _story_block(s)
        cm.save("_drafts/stories-new-candidates.md", "\n".join(lines))
        say("stories.md carries approved entries", "new candidates were written beside it: brand/_drafts/stories-new-candidates.md")
        return "_drafts/stories-new-candidates.md", len(stories)

    cm.save("stories.md", _fill_stories_template(current, stories))
    say("Drafted the stories", "%d anecdotes from %d pages, every one marked %s until you approve it"
        % (len(stories), len(cands), WARN))
    return "stories.md", len(stories)


# ---- the builder ------------------------------------------------------------------------------

def _opinions_unanswered(text):
    m = re.search(r"## Opinions\s*\n(.*?)(?:\n## |\Z)", text or "", re.S)
    return bool(m) and m.group(1).strip() in ("", "*(none yet)*")


def review_notes():
    notes = []
    n = cm.count_lines(cm.read("stats.md"), WARN)
    if n:
        notes.append("stats.md: %d %s rows to confirm" % (n, WARN))
    n = cm.count_lines(cm.read("stories.md"), "### " + WARN)
    if n:
        notes.append("stories.md: %d %s entries to approve" % (n, WARN))
    if _opinions_unanswered(cm.read("opinions.md")):
        notes.append("opinions.md: the interview is unanswered (human-only, the machine never drafts an opinion)")
    for extra in ("_drafts/stats-new-candidates.md", "_drafts/stories-new-candidates.md"):
        if cm.exists(extra):
            notes.append("%s: new candidates beside a confirmed file" % extra)
    return notes


def run(co, say, redo=False):
    made, kept = instantiate(co)
    if made:
        say("Instantiated the brand-facts files", ", ".join(made))
    if kept:
        say("Kept the existing brand-facts files", ", ".join(kept) + " (already exist: SEED, never overwritten)")

    rows = None
    for label, fn, name in (("stats", draft_stats, "stats.md"), ("stories", draft_stories, "stories.md")):
        current = cm.read(name)
        if not redo and (already_drafted(current) or human_confirmed(current)):
            say("Kept the %s" % label, "%s already carries drafted or confirmed rows" % name)
            continue
        if rows is None:
            rows = cm.ok_pages(co.get("language_code"))
        fn(co, rows, say)
    return {"files": list(FILES), "needs_review": review_notes()}
