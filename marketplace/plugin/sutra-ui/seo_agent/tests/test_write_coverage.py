"""tests/test_write_coverage.py — what the finished draft covered of the topics every ranking page
covers, and why each drop happened.

The fault, approved for fixing 2026-09-22 (specs/parked-2026-09-22-engine-fixes.md item 5): the
Recruiting Metrics article shipped missing two of the six topics every ranking page covers, Source
of Hire and Offer Acceptance Rate, and nobody knew until a reviewer read it. There WAS a coverage
check in write/readable.py; it only wrote a report nobody surfaced.

THIS IS DELIBERATELY NOT A GATE. The owner asked for leeway: nothing is blocked, the run says what
it did, and a person judges. Every check below is about the record being honest and reaching a
screen, never about stopping anything.

Entirely offline: the model is a local dispatcher, and the Library tab is read from artifact files
written exactly as the real producers write them.

What this proves:
  * every expected topic lands in exactly ONE of the two lists, so a topic can no longer fall out
    of the count in silence -- including the one the coverage judge never answered on;
  * a covered topic names the final heading that covers it, and a drop carries a reason in plain
    words, taken from the judge rather than guessed at here;
  * the judge is asked for that reason, and is shown what the architect already recorded it was
    leaving out, so no second AI call was needed;
  * the Edits tab carries the same shape, and an article written before this shipped renders
    nothing rather than an empty box.
"""
import copy
import re
import shutil
import sys

from seo_agent.tests import _fixture
_fixture.setup()

from seo_agent import llm, store, library_tabs as lt           # noqa: E402
from seo_agent.write import readable                           # noqa: E402

FAILS, PASSES = [], []


def ok(label, cond, extra=""):
    (PASSES if cond else FAILS).append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("   " + str(extra)) if extra and not cond else ""))
    return cond


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

STAKES = ["Time to Fill", "Cost Per Hire", "Quality of Hire", "Source of Hire",
          "Offer Acceptance Rate", "Applicants Per Hire"]

ARCHITECT_NOTE = "Left out Source of Hire: no evidence was found for it in the research."

# What the coverage judge hands back. FIVE rows for six expected topics, on purpose: the sixth is
# the case where the judge simply does not answer, which must not be counted either way.
JUDGED = {"table_stakes": [
    {"topic": "Time to Fill", "covered": True,
     "where": "Time to Fill Formula: When the Clock Starts", "why": ""},
    {"topic": "Cost Per Hire", "covered": True,
     "where": "it divides everything you spent by the hires you made", "why": ""},
    {"topic": "Quality of Hire", "covered": True, "where": "Cost Per Hire", "why": ""},
    {"topic": "Source of Hire", "covered": False, "where": "", "why": "no evidence was found for it"},
    {"topic": "Offer Acceptance Rate", "covered": False, "where": "", "why": ""},
], "ai_overview_on_topic": True, "ai_overview_subject": "", "ai_overview": []}


def json_stub(prompt, system=None, retries=1, **kw):
    PROMPTS.append(prompt)
    if '"ai_overview_on_topic"' in prompt:                      # readable-coverage.md
        return copy.deepcopy(JUDGED)
    if '"sections": [{"heading"' in prompt:                     # readable.md: hand the article back
        return {k: ARTICLE[k] for k in ("h1", "intro", "quick_answer", "sections", "faq", "close")}
    return {}


llm.json_call = json_stub
_fixture.plant_brand_files()


def last_prompt(marker):
    for p in reversed(PROMPTS):
        if marker in p:
            return p
    return ""


# ══════════════════════════════════════════════════════════════════════════════════════════════
print("\nevery expected topic lands in exactly one list, with a reason on every drop")

rep = readable.coverage_report(ARTICLE, STAKES, copy.deepcopy(JUDGED))

ok("there is a report", isinstance(rep, dict))
ok("it counts every expected topic the research recorded", rep["expected_total"] == 6)
ok("and every one of them is in exactly one list, so none can fall out in silence",
   len(rep["covered"]) + len(rep["dropped"]) == rep["expected_total"])
ok("the shape is exactly the contract the panel renders",
   set(rep) == {"expected_total", "covered", "dropped"}
   and all(set(r) == {"topic", "section"} for r in rep["covered"])
   and all(set(r) == {"topic", "why"} for r in rep["dropped"]), sorted(rep))

covered = {r["topic"]: r["section"] for r in rep["covered"]}
dropped = {r["topic"]: r["why"] for r in rep["dropped"]}

ok("a covered topic names the final heading that covers it",
   covered.get("Time to Fill") == "Time to Fill Formula: When the Clock Starts", covered)
ok("a heading named in part still resolves to the whole heading",
   covered.get("Quality of Hire") == "Cost Per Hire, And What It Leaves Out", covered)
ok("a 'where' that is a sentence, not a heading, is passed through rather than guessed at",
   covered.get("Cost Per Hire") == "it divides everything you spent by the hires you made", covered)

ok("a dropped topic carries the reason, in plain words",
   dropped.get("Source of Hire") == "no evidence was found for it", dropped)
ok("a drop with no reason on it says so rather than inventing one",
   dropped.get("Offer Acceptance Rate") == "it is not in the article, and no reason was recorded", dropped)
ok("a topic the judge never answered on is reported as dropped, not quietly counted as covered",
   dropped.get("Applicants Per Hire") == "the coverage check never answered on this one", dropped)

ok("no expected topics means no report at all",
   readable.coverage_report(ARTICLE, [], copy.deepcopy(JUDGED)) is None)
ok("a coverage call that did not answer means no report either",
   readable.coverage_report(ARTICLE, STAKES, None) is None)


# ---- through the step, end to end --------------------------------------------------------------
print("\nit is a NOTE, not a gate: the run says it and carries on")

SAY = []
ST = {"keywords": {"primary": "recruiting metrics", "variations": [], "section_keywords": []},
      "coverage_note": ARCHITECT_NOTE, "word_budget": {"target": 2000}}
PLAN = {"table_stakes": STAKES, "ai_overview": "Recruiting metrics measure hiring performance.",
        "format_archetype": "", "word_band": {"min": 2000, "max": 2000}}

out = readable.run(readable.C.deep(ARTICLE), PLAN, ST, lambda *a: SAY.append(a))

ok("the report rides on the readable step's own report, which is what write-report.json carries",
   isinstance(out["report"].get("coverage_report"), dict), sorted(out["report"]))
ok("the step still applied its rewrite; nothing was blocked", out["report"]["applied"] is True)
ok("three of the six were dropped and not one of them stopped anything",
   out["report"]["coverage_report"]["expected_total"] == 6
   and len(out["report"]["coverage_report"]["dropped"]) == 3,
   out["report"]["coverage_report"])
ok("and it is said out loud, once, at the end of the draft",
   sum(1 for label, _n in SAY if label.startswith("Expected topics:")) == 1, [s[0] for s in SAY])
ok("the line names what was dropped and why",
   any("Source of Hire — no evidence was found for it" in str(n) for _l, n in SAY), SAY)

cp = last_prompt("does this article genuinely cover this")
ok("the coverage judge is asked for a reason on every drop",
   "SAY WHY, IN ONE SHORT PLAIN SENTENCE" in cp)
ok("and is shown what the architect already recorded it was leaving out, so no second call is needed",
   ARCHITECT_NOTE in cp)
ok("no {{TOKEN}} reached the coverage judge unfilled", not re.findall(r"\{\{[A-Z_]+\}\}", cp),
   sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", cp))))


# ---- and it reaches a screen ---------------------------------------------------------------------
print("\nthe Edits tab carries the same shape, and an old article renders nothing")

MADE, ITEMS = [], []


def run_with(report):
    c = store.new_chat("coverage tab test")
    r = store.new_run(c, "recruiting metrics")
    MADE.append(c)
    item = store.library_start(c, r, "req")
    ITEMS.append(item)
    store.save_artifact(c, r, "draft.md", "# Recruiting metrics\n\nbody\n")
    store.save_artifact(c, r, "write-report.json", report)
    return lt.edits(store.library_get(item))


COV = {"expected_total": 6,
       "covered": [{"topic": "Time to Fill", "section": "Time to Fill Formula: When the Clock Starts"}],
       "dropped": [{"topic": "Source of Hire", "why": "no evidence was found"}]}

ed = run_with({"steps": {"readable": {"applied": True, "coverage_report": COV}}, "length": {"words": 2180}})
ok("the Edits tab has a coverage row", isinstance(ed.get("coverage"), dict), ed)
ok("carrying the same three fields, unchanged", ed["coverage"] == COV, ed["coverage"])

ed_top = run_with({"coverage_report": COV, "steps": {"readable": {}}})
ok("a report written at the top level of write-report.json is found too", ed_top["coverage"] == COV)

ed_old = run_with({"steps": {"readable": {"applied": True}}, "length": {"words": 2180}})
ok("an article written before this shipped renders nothing, not an empty box",
   ed_old is not None and ed_old["coverage"] is None, ed_old)
ok("and the rest of its Edits tab is unaffected", ed_old["passes"] == ["Rewrote it to be read"])

ed_junk = run_with({"steps": {"readable": {"coverage_report": {
    "expected_total": 2,
    "covered": [{"topic": "", "section": "x"}, {"topic": "Time to Fill", "section": "A heading"}],
    "dropped": "not a list"}}}})
ok("a row with no topic is dropped rather than drawn as a blank line",
   ed_junk["coverage"]["covered"] == [{"topic": "Time to Fill", "section": "A heading"}],
   ed_junk["coverage"])
ok("and a malformed list is empty, never a crash", ed_junk["coverage"]["dropped"] == [])
ok("a coverage report with no expected topics is no row at all",
   run_with({"steps": {"readable": {"coverage_report": {"expected_total": 0, "covered": [], "dropped": []}}}})
   ["coverage"] is None)


# ---- clean up ---------------------------------------------------------------------------------
for i in ITEMS:
    store.library_delete(i)
for ch in MADE:
    shutil.rmtree(store.chat_dir(ch), ignore_errors=True)

print("\n%d checks, %d failed" % (len(PASSES) + len(FAILS), len(FAILS)))
if FAILS:
    print("FAILED: " + ", ".join(FAILS))
    sys.exit(1)
print("what the draft covered, and why each drop happened, is on the record")
