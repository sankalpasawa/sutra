"""assets/_common.py — what every asset builder needs, in one place.

Not a builder. The port of layer 02 (`workflows/02-asset-engine/`), whose whole comparability
argument rests on ONE thing: all three idea-finding methods judge an idea with the SAME two named
tests, in the same words. The original says so directly, and it is why the three pools can be
merged and ranked against each other at the end. Three paraphrases could not be.

So the tests live here, once, as `ownability()` and `linkability()`, and every method calls them.
No method writes its own version of either, and no method invents a third test.

Files: knowledge/assets/{scope.md, competitors.json, formats.json, trends.json, ideas.json}
       knowledge/assets/_work/<builder>/…   the per-step working files a person can open
"""
import json
import os
import re

from .. import llm
from .. import store
from ..brand import _common as bcm
from ..tools import _shared as sh

PROMPTS = os.path.join(sh.PROMPTS, "assets")

# The four verdicts the reuse check may return, in the original's own order. First match wins, so
# the order IS the decision tree and must not be re-sorted.
REUSE_VERDICTS = ("already have it", "improve existing", "build from parts", "brand new")

# An idea's life in Sutra. Not in the original, which has no notion of "built": it produced a sheet
# and a human worked it. Here the sheet is live, so a row has to say where it stands.
STATUSES = ("open", "building", "done", "dropped")

# Linkability is scored out of four in the original (2-model-other-niches:257). Below this an idea
# is not worth the trouble, and the original drops it rather than ranking it low.
LINKABILITY_FLOOR = 3
LINKABILITY_OF = 4


# ---- files under knowledge/assets/ -------------------------------------------------------------

def path(name):
    return os.path.join(store.knowledge_dir(), "assets", name)


def exists(name):
    return os.path.exists(path(name))


def read(name, default=None):
    v = store.knowledge("assets/" + name, default)
    if v is None and not name.endswith(".json"):
        return ""
    return v


def save(name, data):
    """Text goes through the same tidy the brand files get: the model writes &gt; when it means >,
    because it has been reading HTML all day (found 2026-09-09 in brand-voice.md)."""
    if isinstance(data, str):
        data = bcm.unescape_text(data)
    return store.save_knowledge("assets/" + name, data)


def strip_fence_safe(text):
    """The brand builders' fence stripper, reused so a model's ```markdown wrapper never ships."""
    return bcm.strip_fence(text)


def prompt(name):
    with open(os.path.join(PROMPTS, name + ".md"), encoding="utf-8") as f:
        return f.read()


# ---- the two shared tests ----------------------------------------------------------------------
# Both are handed the brand scope and, where it exists, the competitor set. An LLM asked "is this
# ours?" without being shown what "ours" means guesses generously: that exact failure fired a
# uniqueness flag on 14 of 18 sections once before. The criteria travel WITH the question, always.

def ownability(ideas, scope, competitors=None, say=None):
    """Can this company credibly own this? One verdict per idea, decided ONCE.

    Returns [{id, verdict: bool, brand_fit: CORE|TRANSPLANT|ADJACENT, transplant_from, why}].

    Never accumulated across batches with `or`. The original warns about the same thing from the
    other direction: a flag merged with OR across passes can only ratchet up, so everything ends
    up flagged. Each idea is judged on the final unit, in one call per batch, and the batch's
    verdicts are taken as given.
    """
    if not ideas:
        return []
    p = sh.fill(prompt("ownability"),
                scope=scope or "(no brand scope on file)",
                competitors=_names(competitors),
                ideas=_numbered(ideas))
    out = llm.json_call(p)
    return _rows(out, ideas, "ownability")


def linkability(ideas, scope, competitors=None, say=None):
    """Would anyone actually cite an asset about this? Scored out of four, one point each:
    a citable number, a journalist would cite it, it is evergreen, the format is proven.

    Returns [{id, score, of, verdict: bool, why}]. `verdict` is score >= LINKABILITY_FLOOR,
    derived in CODE from the score, never asked of the model. The model supplies evidence; the
    keep-or-drop line is ours and is applied identically to all three methods.
    """
    if not ideas:
        return []
    p = sh.fill(prompt("linkability"),
                scope=scope or "(no brand scope on file)",
                competitors=_names(competitors),
                floor=str(LINKABILITY_FLOOR),
                ideas=_numbered(ideas))
    rows = _rows(llm.json_call(p), ideas, "linkability")
    for r in rows:
        r["of"] = LINKABILITY_OF
        if not r.get("judged"):
            r["score"], r["verdict"] = None, None    # unjudged is not zero, and it is not a drop
            continue
        try:
            r["score"] = max(0, min(LINKABILITY_OF, int(r.get("score") or 0)))
        except (TypeError, ValueError):
            r["score"] = 0
        r["verdict"] = r["score"] >= LINKABILITY_FLOOR      # decided here, not by the model
    return rows


def _names(competitors):
    if not competitors:
        return "(no competitor set on file yet)"
    out = []
    for c in competitors:
        if isinstance(c, str):
            out.append("- " + c)
        else:
            out.append("- %s%s" % (c.get("domain") or c.get("name") or "",
                                   " (%s)" % c["kind"] if c.get("kind") else ""))
    return "\n".join(out)


def _numbered(ideas):
    """The ideas as the model sees them: a stable id per row, so a returned verdict can never be
    matched back by position. Position matching is how a batch's answers end up on the wrong rows
    when a model returns nine items for ten."""
    out = []
    for i in ideas:
        out.append("### %s\n%s\n%s" % (i.get("id"), i.get("title") or "",
                                       (i.get("angle") or "").strip()))
    return "\n\n".join(out)


def _rows(out, ideas, what):
    """Match returned rows back to ideas BY ID, and account for every idea. An id the model
    invented is dropped; an idea it forgot comes back unjudged rather than silently keeping a
    default, because a default here is a keep-or-drop decision nobody made."""
    got = {}
    rows = out if isinstance(out, list) else (out or {}).get("results") or []
    for r in rows:
        if isinstance(r, dict) and r.get("id"):
            got[str(r["id"])] = r
    result = []
    for i in ideas:
        r = got.get(str(i.get("id")))
        if r is None:
            # A real field, not a phrase in `why`. The formats builder was string-matching
            # "not judged:" to tell a forgotten idea from one that genuinely scored zero, which is
            # a keep-or-drop decision resting on prose nobody promised to keep stable.
            result.append({"id": i.get("id"), "judged": False, "verdict": None,
                           "score": None,
                           "why": "the %s pass returned no row for this idea" % what})
        else:
            r = dict(r)
            r["id"] = i.get("id")
            r["judged"] = True
            result.append(r)
    return result


# ---- the idea row ------------------------------------------------------------------------------

# One band per finder. The three run apart and never see each other's files, so all three would
# otherwise start at a0001 and the merge would receive three different ideas wearing one id. Same
# device brand_cards uses when it reserves 8001+. Raised by the formats builder, 2026-09-09.
# BOTH vocabularies map to the same band. The builders carry a METHOD constant in the original
# workflow's words ("model-other-niches"), while the pool files and this table are named after the
# module. Accepting only one of the two is a trap: the miss returns a base of 0, the ids quietly
# fall outside every band, and the collision it was meant to prevent happens anyway with nothing
# said. Raised by the merge builder, 2026-09-09, which found formats' ids already outside a band.
ID_BASE = {"competitors": 1001, "competitor-study": 1001,
           "formats": 2001, "model-other-niches": 2001,
           "trends": 3001, "study-trends": 3001}


def new_id(n, method=None):
    """a2001.. Stable, sortable, short enough to sit on a button and travel in one field.

    `n` counts from 1 within the method, so the first formats idea is a2001, not a2002. Pass the
    method or the id lands outside every band and the merge cannot tell where it came from.
    """
    if not method:
        return "a%04d" % int(n)
    base = ID_BASE.get(method)
    if base is None:
        # Loud, never a silent 0. A method name this table does not know means the caller has
        # drifted, and the whole point of the bands is that a drift shows up here rather than as
        # two different ideas wearing one id three steps later.
        raise ValueError("No id band for method %r. Known: %s"
                         % (method, ", ".join(sorted(ID_BASE))))
    return "a%04d" % (base + int(n) - 1)


def blank_idea(idea_id, method):
    """Every field an idea carries, so a row is never half a shape. The schema is the original's
    merged sheet (4-merge/README.md) plus `status` and `built`, which are Sutra's own: the sheet
    is live here, so a row has to say where it stands."""
    return {
        "id": idea_id, "title": "", "angle": "", "format": "",
        "method": [method] if isinstance(method, str) else list(method or []),
        "brand_fit": "", "transplant_from": "",
        "ownability": {"verdict": None, "why": ""},
        "linkability": {"score": 0, "of": LINKABILITY_OF, "verdict": None, "why": ""},
        "beatability": None, "effort": "",
        # Does making this need a real build, or can a person do it at a desk? The original added
        # this rule on 2026-07-22 after the engine turned 1,143 of 2,213 ideas into calculators,
        # and its wording is that such an idea is flagged and "never hidden". Without the field the
        # merge drops the flag and the write phase cannot tell a document from a piece of software.
        "tool_escalation": False, "what_it_would_be": "",
        "proof": [], "rank": None,
        "reuse": {"verdict": "", "links": [], "why": ""},
        "status": "open",
        "built": {"library_id": "", "run_id": "", "at": "", "how": ""},
    }


def ideas():
    rows = read("ideas.json") or []
    return rows if isinstance(rows, list) else (rows.get("ideas") or [])


def save_ideas(rows):
    return save("ideas.json", rows)


def next_open(rows=None):
    """The idea the chip offers: highest ranked, still open. None when the sheet is empty or done.

    Rank ascending, because rank 1 is best. An unranked row sorts last rather than first: a row
    with no rank has not been through the merge, and offering it would jump the queue.
    """
    rows = rows if rows is not None else ideas()
    open_rows = [r for r in rows if r.get("status") == "open"]
    if not open_rows:
        return None
    return sorted(open_rows, key=lambda r: (r.get("rank") is None, r.get("rank") or 0,
                                            r.get("id") or ""))[0]


def by_id(idea_id, rows=None):
    for r in (rows if rows is not None else ideas()):
        if str(r.get("id")) == str(idea_id):
            return r
    return None


def mark_built(idea_id, library_id, run_id):
    """Tick one idea, from PROVENANCE only.

    The owner's decision, 2026-09-09: an idea is ticked when a run that started FROM it saves to
    the Library, and never any other way. An article somebody typed himself ticks nothing, and
    nothing is ever matched by meaning. Matching added a whole class of wrong answers to save a
    rare piece of bookkeeping, and a wrong tick silently removes an idea from the queue where
    nobody would ever find it.
    """
    rows = ideas()
    row = by_id(idea_id, rows)
    if not row:
        return None
    row["status"] = "done"
    row["built"] = {"library_id": library_id or "", "run_id": run_id or "",
                    "at": store.now(), "how": "from_idea"}
    save_ideas(rows)
    return row


def counts(rows=None):
    rows = rows if rows is not None else ideas()
    out = {s: 0 for s in STATUSES}
    for r in rows:
        s = r.get("status") or "open"
        out[s] = out.get(s, 0) + 1
    return out


# ---- the two human gates -----------------------------------------------------------------------
# A builder proposes a list and stops. loop.py asks. The answer lands here, in a file the builder
# checks on its next run, so the approval survives a crash, a quit and a week off.

GATE_FILES = {"competitors": "_work/competitors/approved.json",
              "trends": "_work/trends/approved-subreddits.json",
              "subreddits": "_work/trends/approved-subreddits.json"}


def gate_path(kind):
    return GATE_FILES.get(kind or "", "")


def gate_approved(kind):
    """The approved list, or None when the gate has not been answered. None and [] are different:
    None means nobody was asked, [] means a person looked and kept nothing."""
    name = gate_path(kind)
    if not name or not exists(name):
        return None
    v = read(name)
    return v if isinstance(v, list) else (v or {}).get("approved")


def save_gate(kind, approved):
    name = gate_path(kind)
    if not name:
        raise ValueError("No gate file is defined for %r" % (kind,))
    return save(name, list(approved or []))


def parse_gate_answer(kind, text, proposed):
    """What the person actually approved.

    Three shapes, because a person answering in a chat box will use all three: they accept the
    list as proposed, they paste their own list, or they accept it with edits. A rewritten list
    WINS over the proposal, always. Taking the proposal anyway when somebody clearly typed
    something else would make the gate decorative, which is worse than having no gate at all.
    """
    text = (text or "").strip()
    proposed = list(proposed or [])
    if not text or text.lower() in ("use this list", "yes", "ok", "agreed", "looks right", "approve"):
        return proposed

    # Anything that looks like a list of its own replaces the proposal. One per line or comma
    # separated; a leading bullet or number is stripped, because people type lists that way.
    items = []
    for raw in re.split(r"[\n,]+", text):
        v = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", raw).strip().strip("\"'")
        if v:
            items.append(v)
    if not items:
        return proposed

    by_key = {}
    for p in proposed:
        k = (p.get("domain") or p.get("name") or "") if isinstance(p, dict) else str(p)
        by_key[k.lower().lstrip("r/").strip()] = p
    out = []
    for v in items:
        hit = by_key.get(v.lower().lstrip("r/").strip())
        # a name the proposal already carried keeps its evidence; a new one is taken at face value
        out.append(hit if hit is not None else ({"domain": v} if "." in v else {"name": v}))
    return out


# What each method is CALLED on screen. The builders name themselves after the original's folders
# ("model-other-niches"), which is right in a file path and wrong in a sentence a person reads.
# One table, used by anything that writes a line for the screen. (2026-09-09: the imported sheet's
# summary reached the tab reading "1892 ideas from competitor-study, model-other-niches".)
METHOD_NAMES = {
    "competitors": "the competitor study", "competitor-study": "the competitor study",
    "formats": "other industries", "model-other-niches": "other industries",
    "trends": "what your audience argues about", "study-trends": "what your audience argues about",
    "imported": "a sheet you loaded",
}


def method_name(m):
    return METHOD_NAMES.get(m, m)


def method_list(names):
    """"a, b and c" — an Oxford-free list a person reads, never a comma-joined slug dump."""
    out = [method_name(n) for n in (names or [])]
    if len(out) <= 1:
        return out[0] if out else ""
    return ", ".join(out[:-1]) + " and " + out[-1]
