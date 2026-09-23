"""tests/test_aparna_2026_09_23.py — the six fixes from Aparna's review of "5 types of pre-employment tests".

Her review, in her words, and what each one turned out to be:

  1. "Even when I am explicitly mentioning 1000 words, the churned article doesn't follow it."
     The architect is TOLD a section ceiling and nothing ever counted the sections it returned. A
     1,000-word article planned at 7 sections is 2,100 words before the intro, FAQ and close: the
     overshoot is decided at the plan, not by the writer.

  2. "This should be treated as a types/listicle cluster... introduce all 5 types upfront."
     The listicle format told the architect: "All supporting blocks (definitions, buying guide,
     pros/cons, data) go BELOW the items, never in front." The upfront map she wants was FORBIDDEN
     by the format, which is also why the definition kept landing last.

  3. "Use straightforward headings like '1. Cognitive Ability Tests'."
     No rule anywhere asked for numbered headings.

  3b. And the heading pass was told to BREAK THE TEMPLATE when four headings share a construction,
     so on five test types it varied the fifth by changing what it was ABOUT -- four answered "what
     score passes" and the fifth answered "which roles suit it". Removed outright (owner's call,
     2026-09-23): it did more harm than good on every format, not just listicles.

  4. "Too research-heavy... reads more like a research report than a blog."
     write-body.md capped HOW MANY figures a section may carry and said nothing about how to SAY
     one, so it wrote the card verbatim: "a 2023 meta-analysis found a validity coefficient of
     0.51".

  8. "When I use Edit with AI... the app still starts with the researching phase, which takes ~1
     hour." The chat had no edit tool at all. Its only writing tools were run_research,
     build_blueprint and write_article, so "simplify the content" could only be answered by
     researching a new article from scratch.

Run: SEO_AGENT_DATA=$(mktemp -d) bash seo_agent/tests/run_all.sh
"""
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, registry, store
from seo_agent.tools import _shared as sh

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


LISTICLE = sh.load_prompt("write/formats/listicle")
HEADPASS = sh.load_prompt("write/heading-pass")
BODY = sh.load_prompt("write/write-body")
READABLE = sh.load_prompt("write/readable")


# ---- 8. the chat can edit without researching ---------------------------------------------------
print("the chat can edit an article without researching it again")

names = [t["name"] for t in registry.for_model()]
ok("there is an edit tool at all", "edit_article" in names, names[-5:])
spec = next((t for t in registry.ALL if t["name"] == "edit_article"), {})
desc = (spec.get("description") or "").lower()
ok("it says outright not to research for an edit",
   "do not call run_research" in desc, desc[:160])
ok("it is minutes, not an hour", int(spec.get("est_minutes") or 999) <= 5, spec.get("est_minutes"))
ok("and it takes the instruction in the person's own words",
   "instruction" in ((spec.get("input_schema") or {}).get("properties") or {}))

from seo_agent.tools import edit_article
out = edit_article.run({"chat_id": "c", "run_id": "r"}, instruction="")
ok("an empty instruction is refused, not guessed at", bool(out.get("error")), out)
out = edit_article.run({"chat_id": "c", "run_id": "r"}, instruction="simplify it")
ok("with no article in the Library it says so plainly, and does not start writing one",
   "no finished article" in str(out.get("error", "")).lower(), out)

# It must be the SAME one-call path the Library button uses, not a second implementation.
import inspect
src = inspect.getsource(edit_article)
ok("it calls the Library's own rewrite, rather than reimplementing it",
   "library_edit.propose_article" in src)
ok("and it writes nothing: the person still presses Use this",
   "propose" in src and "library_save" not in src and "library_finish" not in src)


# ---- 1. the length stops being a suggestion ------------------------------------------------------
print("\nthe length is checked at the plan, and cut at the last rewrite")

from seo_agent.write import shape
m = shape.budget_maths({"min": 1000, "max": 1000})
ok("a 1,000-word article has room for 4 sections, not 7",
   m["section_target"] == 4, m)
shape_src = inspect.getsource(shape)
ok("the plan is counted against that ceiling, not just told about it",
   "over_section_ceiling" in shape_src)
ok("and an oversized plan says so, in words, before a line is written",
   "bigger than the length asked for" in shape_src)
ok("it reports rather than truncating, so no evidence is silently dropped",
   "REPORTED, not truncated" in shape_src)

ok("the last rewrite is told the gap in words", "{{OVER_BY}}" in READABLE)
ok("and that the length is not a suggestion", "THE LENGTH IS NOT A SUGGESTION" in READABLE)
ok("it is told what to cut FROM, so it does not cut the answers",
   "Never from a section's answer" in READABLE)


# ---- 2 and 5. the listicle may open with the map -------------------------------------------------
print("\na 'types of' article may finally introduce its types up front")

ok("the ban on anything in front of the items is gone",
   "go **below the items**, never in front" not in LISTICLE,
   "the old blanket rule is still there")
ok("one short section before the items is now allowed",
   "ONE SHORT SECTION BEFORE THE ITEMS" in LISTICLE)
ok("only when the title promises a set, so a tools roundup is unchanged",
   "when the title promises a count or a set" in LISTICLE)
ok("everything else still goes below the items",
   "EVERY OTHER supporting block" in LISTICLE)
ok("and it is a map, not a second article",
   "it is a map, not a summary" in LISTICLE)


# ---- 3. numbered, plain headings ------------------------------------------------------------------
print("\nthe items are numbered and plainly named")

ok("numbering is required when the title promises a count",
   "NUMBER THE ITEMS when the title promises a count" in LISTICLE)
ok("her exact before-and-after is in the prompt, so the rule cannot be misread",
   "1. Cognitive Ability Tests" in LISTICLE and "How\n      Well Cognitive" in LISTICLE
   or "1. Cognitive Ability Tests" in LISTICLE)
ok("the architect is told the items all answer ONE question",
   "THE ITEMS ALL ANSWER THE SAME QUESTION" in LISTICLE)
ok("and that wording may vary while the question may not",
   "Vary the wording; never vary the question" in LISTICLE)


# ---- 3b. the vary-the-headings rule is gone, for every format -------------------------------------
print("\nthe rule that broke real sets is removed, on every format")

ok("BREAK THE TEMPLATE is gone", "BREAK THE TEMPLATE" not in HEADPASS,
   "the rule is still in the heading pass")
# The phrase "reads as generated" survives only inside the note explaining why the rule went, which
# is the point of the note. What must be gone is the INSTRUCTION.
ok("the instruction to vary them is gone",
   "Vary the ones that can carry a different shape" not in HEADPASS,
   "the rule is removed in name but still tells it to vary")
ok("repeated headings are explicitly fine now",
   "REPEATED HEADINGS ARE NOT A FAULT" in HEADPASS)
ok("and the removal records WHY, so it is not restored as a tidy-up",
   "which roles suit it" in HEADPASS)
ok("genuine sloppiness is still fixed",
   "a heading that lies" in HEADPASS)


# ---- 4. the finding leads, the study follows -------------------------------------------------------
print("\nit stops reading like a research report")

ok("the body writer is told the finding goes in the sentence",
   "THE FINDING GOES IN THE SENTENCE" in BODY)
ok("with the before and after spelled out",
   "validity coefficient of 0.51" in BODY and "a third better" in BODY)
ok("and is told never to open with the evidence",
   "NEVER OPEN WITH THE EVIDENCE" in BODY)
ok("the apparatus goes unless the reader would act on the number",
   "DROP THE APPARATUS" in BODY)
ok("the last rewrite carries the same rule, because it can reintroduce the voice",
   "IT MUST NOT READ AS A RESEARCH REPORT" in READABLE)
ok("and it is told not to lose a source tag while doing it",
   "Never remove a tag while doing this" in READABLE)

# The count is deliberately unchanged: her complaint was the voice, not the volume.
ok("the fact budget is NOT cut: the complaint was how facts sound, not how many",
   "AT MOST 3 SOLID STATISTICS" in BODY)


print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all checks passed for Aparna's 2026-09-23 review")
