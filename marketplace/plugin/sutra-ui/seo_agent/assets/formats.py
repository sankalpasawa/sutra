"""assets/formats.py — builder 2, method 2: import a proven format, point it at a subject we own.

Port of `02-asset-engine/2-model-other-niches`. Method 1 finds what earns links INSIDE the niche;
this one imports what earns links outside it. A calculator that pulled links in finance, an index
that pulled them in economics, an award that pulled them in recruitment: the shape travels between
industries even when the subject does not. A format proven elsewhere that nobody in this niche has
built is a fresh link magnet, and it is the gap method 1 cannot fill.

Five steps, A to E, each writing one named file the next one reads:

  A  build the swipe library of formats and pre-screen it against the brand scope   swipe.json
  B  write this company's adaptation of each survivor                               adaptations.json
  C  the real gate: Ownability and Linkability, the two shared tests                filtered.json
  D  score Beatability and Effort on the survivors                                  scored.json
  E  assemble and sort the pool                                                     formats.json

The two rules that shape the whole thing:

FORMAT, NOT TOPIC. Step A judges a bare shape with no subject attached, so its brand-fit tag can
only ever be a rough guess. That is why step A is deliberately generous and step C does the cutting.

ONE VALUE, ONE PLACE. `brand_fit` is decided in exactly one place, step C's Ownability test, which
is the first moment there is a real subject to judge. Step A's tag is carried in the working file
as `prescreen_fit` and never written to an idea row, so the two can never disagree on the sheet.

Free to run. No paid API, no scraping. The model IS the research tool here, which is why this
method is built early while method 1 waits on DataForSEO.

Reads:  assets/scope.md · brand/{brand-voice,features,stats}.md
        prompts/assets/formats-swipe-library.md — the proven-examples table, verbatim
Writes: assets/formats.json — the method 2 pool, a list of `_common.blank_idea` rows
        assets/_work/formats/{swipe.json, format-swipe.md, adaptations.json, filtered.json,
                              scored.json, run-log.md}
"""
import re

from .. import llm
from ..brand import _common as bcm
from ..tools import _shared as sh
from . import _common as cm

OUTPUT = "formats.json"
WORK = "_work/formats/"
METHOD = "model-other-niches"

# Ids sit in a per-method band so a row's origin is readable from its number alone, the same way
# brand_cards reserves 8001+. The three pools are built by three separate builders that never see
# each other's files, so without bands all three would start at a0001 and the merge would be
# handed three different ideas all called a0001.
# The band itself lives in _common.ID_BASE, keyed by both this module's name and the workflow's,
# so there is one table and not four. Kept here only as the offset into THIS method's own pool,
# which starts at 1. (It used to be 2001 here as well, and adding the two together put the ids in
# a band nobody owned: a4001. Found by running it, 2026-09-09.)
ID_BASE = 1

EXTRA_FORMATS = 5           # what source 2 (the model's own knowledge) is asked to add. The original
                            # aims for 3-5 on top of the 19 proven rows.
JUDGE_BATCH = 12            # ideas per Ownability / Linkability call. Small enough that a model does
                            # not start skipping rows, large enough that judging stays consistent
                            # within a batch. Every idea is judged exactly once, in one batch.
SCORE_BATCH = 12

VOICE_CHARS = 4000          # of brand-voice.md; the pillars are what shapes a headline, not the examples
FEATURES_CHARS = 9000       # of features.md; the schema's first sections carry the product truth
STATS_CHARS = 6000          # of stats.md; the numbers we could actually point an asset at

# The original's sort, in its own order: brand fit first, then how strong the idea is on its own,
# then the cheap build wins the tie. Rank proper is the merge's job; this is only so the pool file
# reads best-first on its own.
FIT_ORDER = {"CORE": 0, "TRANSPLANT": 1, "ADJACENT": 2}
EFFORT_ORDER = {"S": 0, "M": 1, "L": 2}

# Banned in an asset's working title. The shape lives in the `format` field and in what_it_would_be;
# repeating it in the name is the trap the original's format-honesty fix was written for
# (2026-07-22): the engine picked a FORMAT first, and 1,143 of 2,213 ideas came out as calculators
# and quizzes when the pages that actually earn links in most niches are plain articles. Checked in
# code rather than trusted to the prompt, and surfaced rather than silently rewritten: a title is
# for a person to fix, and a rewrite here would be this file inventing a value step B owns.
SHAPE_WORDS = ("calculator", "quiz", "generator", "interactive", "dashboard", "tool", "widget",
               "estimator", "configurator", "index")

_URL = re.compile(r"https?://[^\s;,)|]+")
_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")
_EMPHASIS = re.compile(r"[*`]")


def plain(cell):
    """A swipe cell with its markdown emphasis taken off, for anywhere the value is used as a
    value rather than as markdown: inside a prompt, or in an idea's `proof`.

    The table on disk stays verbatim, because the original's step A1 says the rows are carried
    "as-is... nothing rewritten". But the adapt prompt already wraps what it is handed in its own
    bold, so a cell that arrives carrying its own bold gave "****Utility** — cited as..." on the first
    real render (2026-09-09), and a proof row on a screen would show the asterisks as characters.
    """
    return _EMPHASIS.sub("", cell or "").strip()


# ---- step A: the swipe library ------------------------------------------------------------------

def swipe_table():
    """A1 — source 1, the proven-examples table, lifted from disk.

    Mechanical on purpose. The original's own instruction is "carried forward as-is, with its four
    columns intact. Nothing rewritten or summarised". A model asked to recall formats that earn
    links answers differently every run, so two runs of the same company could not be compared.
    The table does not drift. Bold and the source file's "(agent knowledge)" marker come off the
    format name only, which is what the original does; every other cell is left exactly as written.
    """
    text = cm.prompt("formats-swipe-library")
    rows, started = [], False
    for line in text.splitlines():
        m = _TABLE_ROW.match(line.strip())
        if not m:
            if started:
                break               # the first table in the file and nothing else
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) < 4:
            continue
        if cells[0].lower() == "format" or set(cells[0]) <= set("-: "):
            started = True          # the header and its separator
            continue
        started = True
        fmt = re.sub(r"\*+", "", cells[0])
        fmt = re.sub(r"\s*\(agent knowledge\)\s*", " ", fmt, flags=re.I).strip()
        rows.append({"format": fmt, "example": cells[1], "headline_template": cells[2],
                     "why_links": cells[3], "source": "table"})
    if not rows:
        raise RuntimeError("prompts/assets/formats-swipe-library.md has no format table in it. That "
                           "file is the proven half of this method; without it there is nothing to "
                           "adapt but the model's own recollection.")
    return rows


def extra_formats(co, known, say):
    """A2 — source 2, the model's own knowledge, added on top.

    Non-deterministic by design and marked as such in every row (`source: "model"`), so a person
    reading the swipe file can always tell which half is proven and which half is recalled. A
    format whose example the model cannot name is not knowledge, and the prompt tells it to drop
    those; anything that arrives without an example is dropped here too rather than trusted.
    """
    out = llm.json_call(sh.fill(cm.prompt("formats-extra"), brand=co["brand"], n=str(EXTRA_FORMATS),
                                existing="\n".join("- " + f["format"] for f in known)))
    rows = out if isinstance(out, list) else (out or {}).get("formats") or []
    have = {f["format"].strip().lower() for f in known}
    added, refused = [], 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        fmt = str(r.get("format") or "").strip()
        example = str(r.get("example") or "").strip()
        if not fmt or fmt.lower() in have:
            continue
        if not example:
            refused += 1            # "no example you can't name = drop the format", enforced here
            continue
        have.add(fmt.lower())
        added.append({"format": fmt, "example": example,
                      "headline_template": str(r.get("headline_template") or "").strip(),
                      "why_links": str(r.get("why_links") or "").strip(), "source": "model"})
    say("Added formats from the model's own knowledge",
        "%s on top of the %d proven rows%s" % (sh.plural(len(added), "format"), len(known),
                                               "; %d refused for naming no real example" % refused if refused else ""))
    return added


def prescreen(co, scope, formats, say):
    """A3 — one light question per bare format: can it plausibly be pointed at anything in scope?

    Deliberately generous. There is no subject yet, so a hard ownability test here would be
    guesswork, and the original says so: "Keep most formats; Step C does the real cutting". The
    transplant check runs before any drop, so a shape whose obvious subject is off-brand gets a
    chance to be re-pointed before it is binned.

    Matched back BY NAME, never by position. A model that returns 22 rows for 24 formats silently
    shifts every answer after the gap onto the wrong format when you zip by index.
    """
    listed = "\n".join("- %s — earns links through %s" % (f["format"], f["why_links"] or "unstated")
                       for f in formats)
    out = llm.json_call(sh.fill(cm.prompt("formats-prescreen"), brand=co["brand"],
                                scope=scope, formats=listed))
    rows = out if isinstance(out, list) else (out or {}).get("screened") or []
    got = {}
    for r in rows:
        if isinstance(r, dict) and r.get("format"):
            got[str(r["format"]).strip().lower()] = r

    kept, dropped = [], []
    for f in formats:
        r = got.get(f["format"].strip().lower())
        if r is None:
            # Unjudged is not a drop. A format the pre-screen forgot has not been rejected by
            # anything, and step C is about to judge its adaptation properly anyway.
            kept.append(dict(f, in_scope_subject="", prescreen_fit="ADJACENT", transplant_from="",
                             prescreen_note="the pre-screen returned no row for this format"))
            continue
        if r.get("keep") is False:
            dropped.append({"format": f["format"],
                            "why": str(r.get("drop_reason") or "no in-scope subject, even after the "
                                       "transplant check").strip()})
            continue
        fit = str(r.get("brand_fit") or "ADJACENT").strip().upper()
        kept.append(dict(f, in_scope_subject=str(r.get("in_scope_subject") or "").strip(),
                         prescreen_fit=fit if fit in FIT_ORDER else "ADJACENT",
                         transplant_from=str(r.get("transplant_from") or "").strip(),
                         prescreen_note=""))
    say("Pre-screened the formats on brand fit",
        "%d kept, %d dropped for having no in-scope subject" % (len(kept), len(dropped)))
    return kept, dropped


def swipe_md(co, kept):
    """A4 — the swipe library as a person reads it. PURE ASSEMBLY.

    Every cell traces to A1/A2 (the four carried format fields) or A3 (subject and rough fit). If a
    value is not one of those, it does not belong in this table, and nothing is decided here.
    """
    lines = ["# Format swipe library — %s" % co["brand"], "",
             "Proven cross-niche link-bait formats, pre-screened to the ones %s can plausibly point at "
             "a subject it owns. Source 1 is the proven-examples table; source 2 is the model's own "
             "knowledge, marked. Built %s." % (co["brand"], bcm.today()), "",
             "Brand fit here is a ROUGH pre-screen on a format with no subject yet. The authoritative "
             "tag is set later, by the Ownability test, once there is a real idea to judge.", "",
             "| Format | Real example(s) | Headline template | Why it earns links | In-scope subject | Brand fit (rough) | Source |",
             "|---|---|---|---|---|---|---|"]
    for f in kept:
        fit = f["prescreen_fit"] + (" (from %s)" % f["transplant_from"] if f.get("transplant_from") else "")
        lines.append("| %s | %s | %s | %s | %s | %s | %s |"
                     % (f["format"], f["example"], f["headline_template"], f["why_links"],
                        f["in_scope_subject"] or "—", fit,
                        "proven table" if f["source"] == "table" else "model knowledge"))
    return "\n".join(lines) + "\n"


def step_a(co, scope, say, redo):
    if cm.exists(WORK + "swipe.json") and not redo:
        data = cm.read(WORK + "swipe.json") or {}
        say("Kept the swipe library", "%s already pre-screened" % sh.plural(len(data.get("kept") or []), "format"))
        return data
    table = swipe_table()
    say("Read the proven-format table", "%s, lifted from disk rather than recalled" % sh.plural(len(table), "format"))
    formats = table + extra_formats(co, table, say)
    kept, dropped = prescreen(co, scope, formats, say)
    data = {"kept": kept, "dropped": dropped, "at": bcm.today()}
    cm.save(WORK + "swipe.json", data)
    cm.save(WORK + "format-swipe.md", swipe_md(co, kept))
    return data


# ---- step B: this company's adaptation of each format -------------------------------------------

def step_b(co, scope, kept, say, redo):
    """One adaptation per surviving format. One, not five.

    The original is blunt about it: "most formats yield exactly one strong idea". Asking for five
    variations per format fills the pool with padding that the step C filter then has to spend its
    judgment on, and a filter fed padding cuts worse.

    The prompt returns its fields in the order the thinking happens: topic, then angle, then the
    name. The angle names what we hold that lets us win, and the title bakes that angle in. Asked
    for the title first, a model guesses a name and then justifies it backwards.
    """
    if cm.exists(WORK + "adaptations.json") and not redo:
        rows = cm.read(WORK + "adaptations.json") or []
        say("Kept the adaptations", "%s already written" % sh.plural(len(rows), "idea"))
        return rows

    voice = bcm.read("brand-voice.md")[:VOICE_CHARS]
    features = bcm.read("features.md")[:FEATURES_CHARS]
    stats = bcm.read("stats.md")[:STATS_CHARS]
    thin = [n for n, v in (("brand-voice.md", voice), ("features.md", features), ("stats.md", stats))
            if not v.strip()]
    if thin:
        # Not fatal, but a person should know: the anti-generic rule in the prompt has less to bite
        # on, so more angles will come back vague and more ideas will die at the Ownability test.
        say("Some brand context is missing", "%s not on file, so the angles have less to hold on to"
            % ", ".join(thin))
    tpl = cm.prompt("formats-adapt")

    def one(f):
        out = llm.json_call(sh.fill(
            tpl, brand=co["brand"], format=f["format"], headline_template=plain(f["headline_template"]),
            why_links=plain(f["why_links"]), example=plain(f["example"]),
            in_scope_subject=f["in_scope_subject"] or "(the pre-screen named none; pick one from the scope)",
            scope=scope, voice=voice or "(no voice file on record)",
            features=features or "(no features file on record)",
            stats=stats or "(no stats file on record)"))
        if not isinstance(out, dict):
            return None
        return {"format": f["format"], "example": f["example"], "why_links": f["why_links"],
                "headline_template": f["headline_template"], "source": f["source"],
                "prescreen_fit": f["prescreen_fit"],      # rough, carried for the audit; never written to a row
                "prescreen_subject": f["in_scope_subject"],
                "our_topic": str(out.get("our_topic") or "").strip(),
                "distinct_angle": str(out.get("distinct_angle") or "").strip(),
                "asset": str(out.get("asset") or "").strip(),
                "tool_escalation": str(out.get("tool_escalation") or "").strip(),
                "headline": str(out.get("headline") or "").strip(),
                "what_it_would_be": str(out.get("what_it_would_be") or "").strip(),
                "source_niche": str(out.get("source_niche") or "").strip()}

    rows, failed = [], 0
    for f, res, err in bcm.parallel(one, kept, say, "Adapting the formats", every=5):
        if err or not res or not res["asset"]:
            failed += 1
            continue
        rows.append(res)
    cm.save(WORK + "adaptations.json", rows)
    say("Wrote one adaptation per format",
        "%s%s" % (sh.plural(len(rows), "idea"), "; %d formats produced nothing" % failed if failed else ""))
    return rows


# ---- step C: the real gate ----------------------------------------------------------------------

def _idea_row(n, a):
    """One adaptation as an idea row. Only the fields this method actually knows are filled.

    `proof` carries the swipe row's real examples, which is this method's evidence: not "someone
    linked to OUR page" but "this shape demonstrably earned links, here, in this other industry".
    `domains` stays None because method 2 counts no linking domains; a 0 there would read as a
    measured zero, and this method has measured nothing.
    """
    # METHOD, not nothing: an id with no band collides with the other two pools at the merge.
    # _common accepts the workflow's name and the module's name for the same band. (2026-09-09)
    row = cm.blank_idea(cm.new_id(n, METHOD), METHOD)
    row["title"] = a["asset"]
    row["angle"] = a["distinct_angle"]
    row["format"] = a["format"]
    example = plain(a["example"])
    urls = _URL.findall(example)
    row["proof"] = [{"url": u, "domains": None, "what": example} for u in urls] or \
                   ([{"url": "", "domains": None, "what": example}] if example else [])
    return row


def _unjudged(r):
    """Did the judge actually return a row for this idea, or did `_common` fill the gap?

    A forgotten idea is not a rejected one, and a default here would be a keep-or-drop decision
    nobody made. So the gap is caught and the idea is kept and flagged for a person instead.

    This used to string-match a phrase in `why`, which put a keep-or-drop decision on prose nobody
    had promised to keep stable. `_common` gained a real `judged` field on 2026-09-09; the old
    phrase is still recognised so a row written by the previous version reads the same way.
    """
    if "judged" in r:
        return not r.get("judged")
    return str(r.get("why") or "").startswith("not judged:")


def _batches(rows, size):
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def _listed(rows):
    """Ideas for one of THIS file's own prompts, each headed by its id. The shared tests do their
    own version of this; a scorer answering by position is how a batch's answers land on the wrong
    rows when a model returns nine objects for ten ideas."""
    return "\n\n".join("### %s\n%s\n%s\nFormat: %s"
                       % (r["id"], r["title"], r["angle"], r["format"]) for r in rows)


def step_c(scope, adaptations, say, redo):
    """Ownability and Linkability, the two shared tests, run on ideas that now have real subjects.

    Both come from `_common`, in the same words all three methods use. That sameness is the whole
    reason the three pools can be ranked against each other at the merge; three paraphrases could
    not be. This file writes neither test and invents no third one.

    The competitor set is deliberately NOT passed. The original is explicit: "Whether a competitor
    already has the format is NOT checked here... The in-niche overlap check happens once, at the
    cross-method merge." Method 2 runs no competitor study and no longer borrows method 1's.

    Ownability's CORE / TRANSPLANT / ADJACENT verdict is the AUTHORITATIVE brand fit and the only
    one written to a row. Step A's tag judged a format with no subject; this judges the real idea.
    ADJACENT is the original's "maybe" and survives as the lowest tier, exactly as it does there.
    """
    if cm.exists(WORK + "filtered.json") and not redo:
        data = cm.read(WORK + "filtered.json") or {}
        say("Kept the filtered ideas", "%s already through both tests" % sh.plural(len(data.get("kept") or []), "idea"))
        return data

    rows = [_idea_row(ID_BASE + i, a) for i, a in enumerate(adaptations)]
    by_id = {r["id"]: r for r in rows}
    src = {r["id"]: a for r, a in zip(rows, adaptations)}
    batches = _batches(rows, JUDGE_BATCH)

    own = {}
    for _b, res, err in bcm.parallel(lambda b: cm.ownability(b, scope), batches, say, "Judging ownability", every=1):
        if err:
            say("An ownability batch failed", str(err)[:90])
            continue
        for r in res:
            own[r["id"]] = r
    link = {}
    for _b, res, err in bcm.parallel(lambda b: cm.linkability(b, scope), batches, say, "Judging linkability", every=1):
        if err:
            say("A linkability batch failed", str(err)[:90])
            continue
        for r in res:
            link[r["id"]] = r

    kept, dropped, unjudged = [], [], []
    for row in rows:
        o, l = own.get(row["id"]), link.get(row["id"])
        blind = o is None or l is None or _unjudged(o) or _unjudged(l)
        if o:
            fit = str(o.get("brand_fit") or "").strip().upper()
            row["brand_fit"] = fit if fit in FIT_ORDER else ""
            row["transplant_from"] = str(o.get("transplant_from") or "").strip()
            row["ownability"] = {"verdict": o.get("verdict"), "why": str(o.get("why") or "").strip()}
        if l:
            row["linkability"] = {"score": l.get("score"), "of": l.get("of", cm.LINKABILITY_OF),
                                  "verdict": l.get("verdict"), "why": str(l.get("why") or "").strip(),
                                  "judged": bool(l.get("judged"))}
        if blind:
            # Neither kept on a default nor dropped on one. It goes through, marked, and a person
            # is told which ones and why.
            unjudged.append(row["id"])
            kept.append(row)
            continue
        if o.get("verdict") is True and l.get("verdict") is True:
            kept.append(row)
            continue
        why = []
        if o.get("verdict") is not True:
            why.append("ownability: " + (row["ownability"]["why"] or "this company cannot credibly own it"))
        if l.get("verdict") is not True:
            # An unjudged row reaches here with score None, never 0. The two are not the same and
            # printing one as the other would tell a person an idea scored nothing when in truth
            # nobody looked at it. (_common gained a `judged` field for this, 2026-09-09.)
            sc = row["linkability"].get("score")
            why.append("linkability: %s of %d, needs %d — %s"
                       % ("not scored" if sc is None else sc, row["linkability"]["of"],
                          cm.LINKABILITY_FLOOR,
                          row["linkability"]["why"] or "nobody would cite it"))
        dropped.append({"id": row["id"], "title": row["title"], "format": row["format"],
                        "why": " · ".join(why)})

    data = {"kept": kept, "dropped": dropped, "unjudged": unjudged,
            "adaptation": {r["id"]: src[r["id"]] for r in kept}}
    cm.save(WORK + "filtered.json", data)
    fits = {}
    for r in kept:
        fits[r["brand_fit"] or "untagged"] = fits.get(r["brand_fit"] or "untagged", 0) + 1
    say("Filtered on ownability and linkability",
        "%d kept, %d dropped; %s" % (len(kept), len(dropped),
                                     ", ".join("%d %s" % (v, k) for k, v in sorted(fits.items())) or "nothing survived"))
    return data


# ---- step D: score ------------------------------------------------------------------------------

def step_d(co, kept, say, redo):
    """Beatability 1-3 and Effort S/M/L, on the same scales method 1 uses.

    Matched back by id. An idea the scorer skipped keeps its blank score rather than a middle
    guess, because a made-up 2 is indistinguishable from a judged 2 once it is on the sheet.
    """
    if cm.exists(WORK + "scored.json") and not redo:
        rows = cm.read(WORK + "scored.json") or []
        say("Kept the scores", "%s already scored" % sh.plural(len(rows), "idea"))
        return rows
    if not kept:
        cm.save(WORK + "scored.json", [])
        return []

    tpl = cm.prompt("formats-score")

    def one(batch):
        out = llm.json_call(sh.fill(tpl, brand=co["brand"], ideas=_listed(batch)))
        return out if isinstance(out, list) else (out or {}).get("scores") or []

    got = {}
    for _b, res, err in bcm.parallel(one, _batches(kept, SCORE_BATCH), say, "Scoring", every=1):
        if err:
            say("A scoring batch failed", str(err)[:90])
            continue
        for r in res or []:
            if isinstance(r, dict) and r.get("id"):
                got[str(r["id"])] = r

    missing = 0
    for row in kept:
        r = got.get(row["id"])
        if not r:
            missing += 1
            continue
        try:
            b = int(r.get("beatability"))
            row["beatability"] = b if 1 <= b <= 3 else None
        except (TypeError, ValueError):
            row["beatability"] = None
        e = str(r.get("effort") or "").strip().upper()[:1]
        row["effort"] = e if e in EFFORT_ORDER else ""
    cm.save(WORK + "scored.json", kept)
    say("Scored beatability and effort",
        "%s%s" % (sh.plural(len(kept) - missing, "idea"), "; %d came back unscored" % missing if missing else ""))
    return kept


# ---- step E: assemble ---------------------------------------------------------------------------

def evidence(row):
    """How many real examples prove this format earns links. Crude on purpose: it is a sort key,
    not a measurement, and it is never written to the row as if it were one."""
    what = (row.get("proof") or [{}])[0].get("what") or ""
    return max(len(re.split(r"[;,]| and ", what)) if what.strip() else 0, 1)


def sort_key(row):
    return (FIT_ORDER.get(row.get("brand_fit"), 3),
            -(evidence(row) * (row.get("beatability") or 0)),
            EFFORT_ORDER.get(row.get("effort"), 1),
            row.get("id") or "")


def run_log(co, swipe, filtered):
    """Every cut this method made, in one file a person can audit. PURE ASSEMBLY, written fresh from
    the two working files each run, so a resumed run never doubles the log."""
    lines = ["# Method 2 run log — %s" % co["brand"], "",
             "Every format and idea this method dropped, with the reason. Built %s." % bcm.today(), ""]
    drops = swipe.get("dropped") or []
    lines += ["## Formats dropped at the pre-screen (%d)" % len(drops), "",
              "No subject inside the brand scope, even after the transplant check.", ""]
    lines += ["- **%s** — %s" % (d["format"], d["why"]) for d in drops] or ["*(none)*"]
    idrops = filtered.get("dropped") or []
    lines += ["", "## Ideas dropped at the gate (%d)" % len(idrops), "",
              "Failed Ownability or Linkability against the brand scope. Most ideas that die, die "
              "here, and that is the filter working.", ""]
    lines += ["- **%s** (%s) — %s" % (d["title"] or d["id"], d["format"], d["why"]) for d in idrops] or ["*(none)*"]
    unj = filtered.get("unjudged") or []
    if unj:
        lines += ["", "## Kept but not judged (%d)" % len(unj), "",
                  "The model returned no verdict for these. They were neither kept nor dropped on a "
                  "default: they are on the sheet, unjudged, for a person to look at.", "",
                  "- " + ", ".join(unj)]
    return "\n".join(lines) + "\n"


def step_e(co, rows, swipe, filtered, say):
    """Assemble the pool and sort it. No new thinking: every field on every row was decided by an
    earlier step, and this one only arranges them."""
    rows = sorted(rows, key=sort_key)
    cm.save(OUTPUT, rows)
    cm.save(WORK + "run-log.md", run_log(co, swipe, filtered))
    return rows


# ---- review notes -------------------------------------------------------------------------------

def review_notes(rows, filtered, adaptations):
    """What a person has to look at. Each one is something code found and code cannot fix."""
    notes = []
    unj = filtered.get("unjudged") or []
    if unj:
        notes.append("formats.json: %d ideas are on the sheet with no verdict, because the judge "
                     "returned no row for them (%s). They were not dropped on a default; read them."
                     % (len(unj), ", ".join(unj[:6])))

    shape = [r for r in rows if any(w in (r["title"] or "").lower() for w in SHAPE_WORDS)]
    if shape:
        notes.append("formats.json: %d titles still name the shape (%s). The format belongs in the "
                     "format field, not the title; picking the shape first is what turned a whole "
                     "pool into calculators once before." % (len(shape), "; ".join(r["title"] for r in shape[:3])))

    # The schema has nowhere to record that an idea needs a real build, so the honest flag the
    # original insists on ("never hidden") is surfaced here and kept in adaptations.json.
    keep_ids = {r["id"] for r in rows}
    needs_build = [a for i, a in (filtered.get("adaptation") or {}).items()
                   if i in keep_ids and a.get("tool_escalation")]
    if needs_build:
        notes.append("formats.json: %d of these cannot be written from desk research — they need a "
                     "real build or data nobody holds yet (%s). The reason per idea is in "
                     "_work/formats/adaptations.json under tool_escalation."
                     % (len(needs_build), "; ".join("%s: %s" % (a["asset"][:40], a["tool_escalation"])
                                                    for a in needs_build[:3])))

    unscored = [r["id"] for r in rows if r.get("beatability") is None or not r.get("effort")]
    if unscored:
        notes.append("formats.json: %d ideas carry no beatability or effort (%s), so they sort last "
                     "rather than being guessed at." % (len(unscored), ", ".join(unscored[:6])))

    # The original's own expectation, kept as a sanity line rather than a rule: "roughly 8-20
    # surviving ideas, not 50". Far outside that and something upstream is wrong, usually a scope
    # that rules nothing out, so every idea passes ownability.
    if adaptations and len(rows) > 30:
        notes.append("formats.json: %d ideas survived, well above the 8 to 20 this method usually "
                     "produces. That normally means scope.md rules too little out, so the "
                     "ownability test approves nearly everything." % len(rows))
    if adaptations and len(rows) < 5:
        notes.append("formats.json: only %d ideas survived the gate out of %d adaptations. Worth "
                     "reading the run log before trusting the pool."
                     % (len(rows), len(adaptations)))
    return notes


# ---- the builder --------------------------------------------------------------------------------

def run(co, say, redo=False):
    if cm.exists(OUTPUT) and not redo:
        say("Kept the format ideas", "already built; ask for a redo to rebuild them")
        return {"files": [OUTPUT], "needs_review": []}

    scope = cm.read("scope.md")
    if not (scope or "").strip():
        raise RuntimeError("There is no assets/scope.md yet. Every method judges against the brand "
                           "scope, and without it this one would import formats and point them at "
                           "whatever it felt like.")

    swipe = step_a(co, scope, say, redo)
    adaptations = step_b(co, scope, swipe.get("kept") or [], say, redo)
    filtered = step_c(scope, adaptations, say, redo)
    rows = step_d(co, filtered.get("kept") or [], say, redo)
    rows = step_e(co, rows, swipe, filtered, say)

    say("Wrote the format ideas",
        "%s from %s of proven format; the merge ranks them against the other methods"
        % (sh.plural(len(rows), "idea"), sh.plural(len(swipe.get("kept") or []), "shape")))
    return {"files": [OUTPUT], "needs_review": review_notes(rows, filtered, adaptations)}
