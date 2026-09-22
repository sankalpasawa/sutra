"""tests/test_write_keywords.py — the keywords are settled by the LAST step that rewrites the
article whole, and the secondaries research paid for finally reach it.

The fault, approved for fixing 2026-09-22 (specs/parked-2026-09-22-engine-fixes.md item 9): the
write order after the body is drafted is blend -> wrapper -> coherence -> readable, and blend is
where the keywords were woven in. Three whole-article rewrites then ran, and assemble -- last of
all -- counted what survived. So the keywords were placed, the article was rewritten three more
times, and nothing put back what a later rewrite removed. On top of that, blend is handed only the
primary and its variations, so the SECONDARIES research chose and paid for never reached the body
at all: a heading writer was offered them once, and anything no heading took went to a log nobody
reads.

Entirely offline. The model is a local dispatcher that hands the article back unchanged, and every
prompt it is sent is kept, so the checks read what the model would actually have seen.

What this proves:
  * readable, the last step that rewrites the article whole, is handed all FOUR keyword groups by
    name, including the secondaries nothing has used;
  * that fourth group arrives as PERMISSION -- "only where they fit naturally", never bend a
    sentence, leaving all of them out is a correct answer -- because forcing them in is exactly
    how an article starts reading as SEO filler;
  * blend keeps its own pass on the primary and its variations and is still not handed the
    secondaries, so no phrase is placed by two steps that cannot see each other.
"""
import re
import sys

from seo_agent.tests import _fixture
_fixture.setup()

from seo_agent import llm                                      # noqa: E402
from seo_agent.write import blend, readable                    # noqa: E402

FAILS, PASSES = [], []


def ok(label, cond, extra=""):
    (PASSES if cond else FAILS).append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("   " + str(extra)) if extra and not cond else ""))
    return cond


# ---- the model, stubbed ---------------------------------------------------------------------
# Matched on the literal output keys each prompt asks for, the same rule _fixture.stub_json uses:
# prompts share vocabulary but never share their output shape.
PROMPTS = []

ARTICLE = {
    "h1": "Recruiting Metrics That Change A Decision",
    "intro": "You already report these numbers. This is about the four that move a hiring plan.",
    "quick_answer": "Track time to fill, cost per hire, quality of hire and source of hire.",
    "sections": [
        {"heading": "Time to Fill Formula: When the Clock Starts",
         "prose": "Time to fill counts the days between the approved requisition and the signed offer. "
                  "Teams argue about the start date, and the argument is the whole point: a clock that "
                  "starts at the job advert hides three weeks of approvals. Pick one start and keep it."},
        {"heading": "Cost Per Hire, And What It Leaves Out",
         "prose": "Cost per hire divides everything you spent on hiring by the hires you made. "
                  "It is the number a finance team asks for first, and the one recruiters trust least, "
                  "because it counts agency fees and ignores the time your own panel spent."},
    ],
    "faq": [{"question": "What is a good time to fill?", "answer": "It depends on the role and the market."}],
    "close": "Start with the number your team argues about most.",
    "close_heading": "Where To Take This Next",
}


def json_stub(prompt, system=None, retries=1, **kw):
    PROMPTS.append(prompt)
    if '"ai_overview_on_topic"' in prompt:                      # readable-coverage.md
        return {"table_stakes": [], "ai_overview_on_topic": True,
                "ai_overview_subject": "", "ai_overview": []}
    if '"keywords_skipped"' in prompt:                          # blend.md
        return {"sections": [{"heading": s["heading"], "prose": s["prose"]} for s in ARTICLE["sections"]],
                "edits": [], "keywords_used": [], "keywords_skipped": []}
    if '"sections": [{"heading"' in prompt:                     # readable.md: hand the article back
        return {k: ARTICLE[k] for k in ("h1", "intro", "quick_answer", "sections", "faq", "close")}
    return {}


llm.json_call = json_stub
_fixture.plant_brand_files()


def last_prompt(marker):
    """The most recent prompt the stub was sent that carries this marker. Nothing invented: if the
    call never happened this returns "", and the check that reads it fails rather than passing on
    a default."""
    for p in reversed(PROMPTS):
        if marker in p:
            return p
    return ""


# ══════════════════════════════════════════════════════════════════════════════════════════════
print("\nthe secondaries nothing has used are the ones carried forward")

ok("a secondary no heading took is on the list",
   readable.unused_secondaries({"unplaced": [{"keyword": "offer acceptance rate",
                                              "why": "no section's heading took it"}]})
   == ["offer acceptance rate"])
ok("what a heading DID take is not asked for a second time",
   readable.unused_secondaries({"section_keywords": ["source of hire"],
                                "unplaced": [{"keyword": "offer acceptance rate"}]})
   == ["offer acceptance rate"])
ok("an older run whose record is plain strings still reads",
   readable.unused_secondaries({"unplaced": ["source of hire"]}) == ["source of hire"])
ok("blanks and repeats are dropped, so the prompt never shows an empty phrase",
   readable.unused_secondaries({"unplaced": [{"keyword": "a"}, {"keyword": " "}, {"keyword": "a"},
                                             {"keyword": "b"}]}) == ["a", "b"])
ok("a run with no such record asks for nothing at all", readable.unused_secondaries({}) == [])


# ---- what the last rewrite actually sees ------------------------------------------------------
print("\nthe last rewrite is handed four labelled groups, and the fourth as permission")

KS = {"primary": "recruiting metrics", "variations": ["recruitment metrics", "hiring metrics"],
      "section_keywords": ["time to fill", "cost per hire"],
      "unplaced": [{"keyword": "offer acceptance rate", "why": "no section's heading took it"},
                   {"keyword": "source of hire", "why": "no section's heading took it"}]}
ST = {"keywords": KS, "coverage_note": "Left nothing out.", "word_budget": {"target": 2000}}
PLAN = {"table_stakes": ["Time to Fill"], "ai_overview": "Recruiting metrics measure hiring performance.",
        "format_archetype": "", "word_band": {"min": 2000, "max": 2000}}

out = readable.run(readable.C.deep(ARTICLE), PLAN, ST, lambda *a: None)
rw = last_prompt("YOU CUT FACTS, NOT WORDS.")

ok("the rewrite call was made", bool(rw))
for label in ("Main keyword:", "Other forms of it:", "Already used in headings:",
              "Chosen but not used anywhere yet:"):
    ok('the prompt names the group "%s"' % label.rstrip(":"), label in rw)
ok("the two unused secondaries are in it, by name",
   "offer acceptance rate" in rw and "source of hire" in rw)
ok("the primary and its variations are still named",
   "recruiting metrics" in rw and "hiring metrics" in rw)
ok("the heading keywords are named too", "time to fill" in rw and "cost per hire" in rw)
ok("no {{TOKEN}} reached the model unfilled", not re.findall(r"\{\{[A-Z_]+\}\}", rw),
   sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", rw))))

# Read with the line breaks flattened, so re-wrapping a paragraph in the prompt never fails a
# check for the wrong reason.
flat = " ".join(rw.split())
ok("the rule on them is permission, not a quota", "WORK THESE IN ONLY WHERE THEY FIT NATURALLY." in flat)
ok("and a sentence is never bent to hold one", "NEVER BEND A SENTENCE TO HOLD A PHRASE." in flat)
ok("leaving every one of them out is allowed, in so many words", "is a correct answer" in flat)
ok("the main keyword is not placed a second time here", "Do not add more of it." in flat)
ok("the rewrite still applied", out["report"]["applied"] is True)

noleft = readable.run(readable.C.deep(ARTICLE), PLAN,
                      dict(ST, keywords=dict(KS, unplaced=[])), lambda *a: None)
ok("a run whose headings took every secondary still finishes", noleft["report"]["applied"] is True)
ok("and says so in words, never as an empty line",
   "(none — every one of them is already in a heading)" in last_prompt("YOU CUT FACTS, NOT WORDS."))


# ---- blend keeps its own pass, and is still not handed the secondaries -------------------------
print("\nblend keeps the primary and its variations, so no phrase is placed twice")

BODY = {"sections": [{"headline": s["heading"], "prose": s["prose"]} for s in ARTICLE["sections"]]}
INPUTS = {"group_a": {"keyword_set": dict(KS, secondaries=["offer acceptance rate", "source of hire"]),
                      "word_band": {"min": 2000, "max": 2000}}}
CTX = {"title": "Recruiting metrics", "angle": "The four that change a decision"}
blend.run(BODY, {"sections": [], "keywords": KS, "spine": "One spine"}, INPUTS, CTX, lambda *a: None)
bp = last_prompt("You are the editor.")

ok("blend was called", bool(bp))
ok("blend still gets the primary", "recruiting metrics" in bp)
ok("and its variations", "hiring metrics" in bp)
ok("but NOT the secondaries: placing one is a rewrite, and this step is three rewrites too early",
   "offer acceptance rate" not in bp and "source of hire" not in bp)
ok("it still counts what landed, in code rather than from the model's own report",
   blend.kw_counts(BODY["sections"], ["cost per hire"])["cost per hire"] == 1)

print("\n%d checks, %d failed" % (len(PASSES) + len(FAILS), len(FAILS)))
if FAILS:
    print("FAILED: " + ", ".join(FAILS))
    sys.exit(1)
print("the keywords are settled by the last step that rewrites the article whole")
