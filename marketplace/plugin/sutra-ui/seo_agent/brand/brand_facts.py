"""brand/brand_facts.py — builder 1: the company's real numbers and its customer stories.

Port of 0-brand-facts (instantiate.py, draft_stats.py, draft_stories.py, run_brand_facts.py).

The one rule: the machine never invents a fact and never clobbers a confirmed one. The two
templates are instantiated once (an existing file is SEED and is never overwritten). Stats and
stories the company's own site already publishes are machine-drafted into the tables, every row
carrying the DRAFT marker with its source URL. The human gate is the edit: a row loses its marker
when a person confirms it. Once a file carries a confirmed row, new candidates go to
brand/_drafts/<name>-new-candidates.md beside it, never over it.

THE MARKER IS INVISIBLE ON PURPOSE. It used to be a ⚠️ on every drafted row, which meant the owner
opened his own numbers and read a screen of warning symbols about work he had not asked to be
warned about (2026-09-09). The protection it gives is load-bearing all the same: without a way to
tell "the machine wrote this" from "a person confirmed this", a rebuild would clobber the owner's
own edits. So the symbol became `<!--d-->`, an HTML comment at the end of the row: inert, still
there in the editor where a person removes it to confirm, and not a warning at anybody.

Reads:  the catalogue + brand/type-roles.json.
Writes: brand/stats.md · brand/stories.md (+ brand/_drafts/*-new-candidates.md)
"""
import re

from .. import llm
from . import _common as cm

FILES = ["stats.md", "stories.md"]

# --- candidate selection (which catalogue pages the model reads) ------------------------------
# Defaults chosen on the first company's page-type mix; type-roles.json supersedes them per company.
# A Type absent from a company's CMS simply yields zero candidates: reported, never a crash.
STAT_PAGE_TYPES = ["page", "certifications"]          # where companies publish their own numbers
STAT_TOP_PAGES = 25         # cap on any big generic bucket, by traffic desc (the homepage is always added)
STORY_PAGE_TYPES = ["successstory", "press-release", "podcast"]
BODY_CHAR_CAP = 12000       # chars of page body per prompt (median page ~1.8k words fits whole)

BUCKETS = {"scale": "Product / scale", "results": "Results / proof", "credibility": "Credibility"}

# The marker that says "the machine drafted this row and no person has confirmed it".
DRAFT = "<!--d-->"
# What the pack used to write. READ ONLY: recognised so the owner's installed files (35 drafted
# stat rows and 47 stories on 2026-09-09) do not all suddenly read as confirmed, and rewritten to
# DRAFT the first time either file is written. Nothing writes a ⚠️ again.
LEGACY = "⚠️"


# ---- the gate, in code ------------------------------------------------------------------------
# These two files have a SECOND writer: tools/onboard.py puts the setup interview's answers into
# them, inside its own delimited block. Those answers are the owner's own prose, typed into a chat.
# They are not rows anybody confirmed, and the gate below must not read them as such — if it did,
# answering one interview question would make the file look finished and silently cost the owner
# the machine's whole draft of the numbers his site already publishes (caught 2026-09-09). The
# block already avoids tables and ### headings for exactly this reason; masking it here means the
# gate holds even when an answer's own words happen to start with a pipe or a hash.
INTERVIEW_START = "<!-- setup-interview:start -->"
INTERVIEW_END = "<!-- setup-interview:end -->"


def in_interview(text):
    """Which line numbers fall inside the setup-interview block. Empty when there is no block."""
    inside, out = False, set()
    for i, ln in enumerate((text or "").splitlines()):
        t = ln.strip()
        if t.startswith(INTERVIEW_START):
            inside = True
        if inside:
            out.add(i)
        if t.startswith(INTERVIEW_END):
            inside = False
    return out


def is_draft(line):
    """Does this line carry the draft marker, in either the current or the legacy spelling?"""
    return DRAFT in line or LEGACY in line


def human_confirmed(text):
    """True if a human has confirmed anything here: a table row (or ### entry) with no marker on it.

    The setup interview's block does not count, whatever it contains: see the note above.
    """
    skip = in_interview(text)
    for i, line in enumerate((text or "").splitlines()):
        if i in skip:
            continue
        t = line.strip()
        if (t.startswith("|") and t.count("|") >= 3 and not is_draft(t)
                and "---" not in t and not t.lower().startswith("| stat")
                and not t.lower().startswith("| <")):
            return True
        if t.startswith("### ") and not is_draft(t) and not t.startswith("### <"):
            return True
    return False


def already_drafted(text):
    """True once the file carries a marked candidate row (a table row or a ### entry)."""
    skip = in_interview(text)
    return any(is_draft(ln) and ln.strip().startswith(("|", "###"))
               for i, ln in enumerate((text or "").splitlines()) if i not in skip)


# ---- the one-time migration off the old symbol -------------------------------------------------

def _rule_block(kind):
    """The template's own rule blockquote, read from the template rather than repeated here.

    A migrated file and a freshly instantiated one must say the same thing, and two copies of a
    paragraph drift. The block is the run of `>` lines that opens the template.
    """
    out, started = [], False
    for ln in cm.template(kind).splitlines():
        if ln.startswith(">"):
            started = True
            out.append(ln)
        elif started:
            break
    return out


def _remark(line):
    """One legacy row rewritten with the invisible marker. The row's own text is untouched."""
    out = line.replace(LEGACY + " ", "").replace(" " + LEGACY, "").replace(LEGACY, "").rstrip()
    return out if DRAFT in out else out + DRAFT


def migrate(text, kind):
    """A file full of ⚠️ rewritten once: the rows keep their meaning, the symbol goes.

    Two things change and nothing else. Every drafted row (a table row or a ### entry) trades the
    symbol for DRAFT. Every blockquote run that explains what the symbol meant is replaced, once,
    by the template's current rule block — the whole run, because the sentence wraps across lines
    and dropping only the lines that carry the symbol leaves half a sentence behind.
    """
    if LEGACY not in (text or ""):
        return text
    out, run, placed = [], [], False

    def flush():
        nonlocal placed
        if not run:
            return
        if any(LEGACY in ln for ln in run):
            if not placed:
                out.extend(_rule_block(kind))
                placed = True
        else:
            out.extend(run)
        run.clear()

    keep = in_interview(text)
    for i, ln in enumerate((text or "").splitlines()):
        t = ln.strip()
        if i in keep:               # not the machine's rows, so not the machine's to rewrite
            flush()
            out.append(ln)
            continue
        if t.startswith("|") or t.startswith("###"):
            flush()
            out.append(_remark(ln) if LEGACY in ln else ln)
            continue
        if t.startswith(">"):
            run.append(ln)
            continue
        flush()
        out.append(ln)
    flush()
    # Dropping a whole blockquote leaves the blank lines that surrounded it stacked up. A person
    # reads this file; three blank lines where a paragraph used to be looks like something broke.
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return text.rstrip("\n") + "\n"


def migrate_file(name, say):
    """Rewrite one brand-facts file off the old symbol, if it still carries it. Returns True when
    it did. Called before the drafting decision, so a file the builder then leaves alone (because
    it already carries drafts) still loses its symbols."""
    text = cm.read(name)
    if LEGACY not in (text or ""):
        return False
    cm.save(name, migrate(text, name[:-3]))
    say("Cleared the old warning symbols from %s" % name,
        "the rows still count as drafts; the marker on them is no longer a symbol")
    return True


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
    """The marker sits AFTER the closing pipe, so the row is still three clean cells to anything
    that reads the table by cell."""
    return "| %s | %s | %s — \"%s\" |%s" % (s["stat"], s["value"], s["url"], str(s.get("quote") or "")[:80], DRAFT)


def strip_drafts(text, kind):
    """Remove the machine's earlier drafts (and its note) before redrafting, so a redo replaces
    them rather than piling a second copy on top. A confirmed row carries no marker and is
    untouched. Both spellings of the marker are stripped, or a legacy file would keep its old
    rows and gain a second, current copy of every one of them."""
    out, skipping = [], False
    keep = in_interview(text)
    for i, ln in enumerate(text.splitlines()):
        t = ln.strip()
        if i in keep:               # the setup interview's answers are never the machine's to strip
            out.append(ln)
            continue
        if t.startswith("> Machine-drafted"):
            continue
        if kind == "stats" and t.startswith("|") and is_draft(t):
            continue
        if kind == "stories":
            if t.startswith("### ") and is_draft(t):
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
    header survives."""
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
    if human_confirmed(current):            # a confirmed row (the marker removed) is never clobbered
        lines = ["# Stats draft — %s (machine-drafted %s, none of it checked yet)" % (co["brand"], cm.today()),
                 "", "> Read each row. Right -> copy it into `stats.md` and drop the `%s` tag. Wrong or a duplicate -> delete it." % DRAFT,
                 "> Drafted from %d pages of the company's own site; %d unique candidates." % (len(cands), len(rows_)), ""]
        for b, title in BUCKETS.items():
            lines += ["## " + title, "| Stat | Value | Source-note |", "|---|---|---|"]
            lines += [_stat_row(s) for s in by_bucket[b]]
            lines.append("")
        cm.save("_drafts/stats-new-candidates.md", "\n".join(lines))
        say("stats.md carries rows you have checked", "new candidates were written beside it: brand/_drafts/stats-new-candidates.md")
        return "_drafts/stats-new-candidates.md", len(rows_)

    note = ("> Machine-drafted %s from %d pages of the company's own site: %d unique candidates."
            % (cm.today(), len(cands), len(rows_)))
    cm.save("stats.md", _fill_stats_template(current, by_bucket, note))
    say("Drafted the stats", "%d candidate numbers, drafted from the site's own pages" % len(rows_))
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
    return ["### %s%s" % (s.get("title") or "(untitled)", DRAFT),
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
    if human_confirmed(current):            # an approved entry (the marker removed) is never clobbered
        lines = ["# Stories draft — %s (machine-drafted, none of it approved yet)" % co["brand"], "",
                 "> Read each. Good -> copy it into `stories.md` in its format, drop the `%s` tag and sign it. Weak or wrong -> delete." % DRAFT,
                 "> Drafted from %d story-type pages; %d carried a real anecdote." % (len(cands), len(stories)), ""]
        for s in stories:
            lines += _story_block(s)
        cm.save("_drafts/stories-new-candidates.md", "\n".join(lines))
        say("stories.md carries entries you have approved", "new candidates were written beside it: brand/_drafts/stories-new-candidates.md")
        return "_drafts/stories-new-candidates.md", len(stories)

    cm.save("stories.md", _fill_stories_template(current, stories))
    say("Drafted the stories", "%d anecdotes from %d pages" % (len(stories), len(cands)))
    return "stories.md", len(stories)


# ---- the builder ------------------------------------------------------------------------------

def review_notes():
    """What is worth telling a person about, and nothing else.

    It used to count the drafted rows in each file and report "35 rows to confirm". That count is
    already on the row itself, and printed at the owner it read as a list of chores he had not
    asked for (2026-09-09). What survives is the one thing he cannot see from the file: that a
    second file of candidates was written beside a file he had already worked on.
    """
    notes = []
    for extra in ("_drafts/stats-new-candidates.md", "_drafts/stories-new-candidates.md"):
        if cm.exists(extra):
            notes.append("%s: new candidates were written beside a file you have already worked on" % extra)
    return notes


def run(co, say, redo=False):
    made, kept = instantiate(co)
    if made:
        say("Instantiated the brand-facts files", ", ".join(made))
    if kept:
        say("Kept the existing brand-facts files", ", ".join(kept) + " (already exist: SEED, never overwritten)")

    rows = None
    for label, fn, name in (("stats", draft_stats, "stats.md"), ("stories", draft_stories, "stories.md")):
        migrate_file(name, say)         # before the decision below, so a file we then keep is still cleaned
        current = cm.read(name)
        if not redo and (already_drafted(current) or human_confirmed(current)):
            say("Kept the %s" % label, "%s already carries drafted or confirmed rows" % name)
            continue
        if rows is None:
            rows = cm.ok_pages(co.get("language_code"))
        fn(co, rows, say)
    return {"files": list(FILES), "needs_review": review_notes()}
