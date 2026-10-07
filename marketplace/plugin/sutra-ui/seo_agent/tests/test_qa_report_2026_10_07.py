"""tests/test_qa_report_2026_10_07.py — the six fixes from the QA report on a freshly generated blog.

Her review, as a six-row table (fix / rows affected / impact / effort), and what each became:

  1. "Hard cap: N words... Never deliver over N+5%." Already enforced by code (readable.py's and
     library_edit.py's bounded cut-round loops, prior PRs), not by a prompt line asking nicely --
     tightened the tolerance those loops already check from 10% to the requested 5%, on both.
  2. "Every number must cite the original study or survey, not a blog summarising it. The claim must
     match the source exactly (same population, same question)." New rule in write-body.md,
     beside the existing "name whoever you are attributing to" rule it extends.
  3. "Neutral, respectful tone... Use 'they' for candidates. Screening in = advancing a candidate on
     evidence, never 'removing' people." The candidate-language rule from the prior PR, extended
     with the singular-they and no-sarcasm/no-presumed-guilt lines this report adds by name.
  4. "Audience: recruiters and TA leads only. No advice to candidates." New rule in write-body.md's
     persona section.
  5. "Mention only these Testlify features: <list>. Never name a feature not on the list." Wired to
     the company's own brand/features.md (the same file wrapper.py already reads for the intro/CTA)
     rather than a hand-maintained static list -- a feature the company adds later needs no prompt
     edit, only a features.md rebuild.
  6. "Final step: self-check against rules 1-5 and list any violations before delivering." A
     five-point checklist added to readable.md, the last step that rewrites the article whole,
     immediately before it returns its reply.

Run: SEO_AGENT_DATA=$(mktemp -d) bash seo_agent/tests/run_all.sh
"""
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, library_edit as le
from seo_agent.tools import _shared as sh
from seo_agent.write import _common as C, write_body

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


def say(*_a, **_k):
    pass


WRITE_BODY = open(sh.PROMPTS + "/write/write-body.md", encoding="utf-8").read()
SHARED_RULES = open(sh.PROMPTS + "/_writing_rules.md", encoding="utf-8").read()
READABLE = open(sh.PROMPTS + "/write/readable.md", encoding="utf-8").read()


# ======================================================================================
# 1. The word-count tolerance is 5%, on both enforcement loops, not a prompt line
# ======================================================================================
print("\n1. 'never deliver over N+5%' is the tolerance the EXISTING retry loops check, tightened")

ok("readable.py's cut-round ceiling is 1.05 (was 1.10)", C.WORD_BAND_CEILING_PCT == 1.05, C.WORD_BAND_CEILING_PCT)
ok("library_edit.py's matching ceiling is 1.05 too, not left at the old number",
   le.LENGTH_CEILING_PCT == 1.05, le.LENGTH_CEILING_PCT)
ok("the round budget and progress guard are untouched by the tightening",
   C.WORD_BAND_MAX_ROUNDS == 2 and le.LENGTH_MAX_ROUNDS == 2)


# ======================================================================================
# 2. Cite the original source, not whoever is repeating it; never widen a figure's scope
# ======================================================================================
print("\n2. the original-source rule sits beside the existing attribution rule")

ok("the new rule is in write-body.md", "CREDIT THE ORIGINAL SOURCE" in WRITE_BODY)
ok("it names the exact failure mode: a summary standing in for the study it summarises",
   "not whoever is repeating it" in WRITE_BODY.upper() or "REPEATING IT" in WRITE_BODY)
ok("it also guards against widening a narrow finding into a general claim",
   "NEVER WIDEN WHAT A FIGURE ACTUALLY MEASURED" in WRITE_BODY)
ok("the existing attribution rule it sits beside is untouched",
   "NAME WHOEVER YOU ARE ATTRIBUTING TO" in WRITE_BODY)


# ======================================================================================
# 3. Tone: the prior PR's rule, now with singular they and no sarcasm / no presumed guilt
# ======================================================================================
print("\n3. the tone rule is extended, not replaced -- the original wording still has to survive")

for doc, name in ((WRITE_BODY, "write-body.md"), (SHARED_RULES, "_writing_rules.md (reaches the edit path)")):
    ok("%s still carries the original candidate-language rule" % name,
       "PEOPLE A PROCESS MOVES THROUGH" in doc and "remove any candidates" in doc, name)
    ok("%s adds singular 'they'" % name, "they" in doc.lower() and "whose gender" in doc.lower(), name)
    ok("%s bans sarcasm and presumed-guilt words, by name" % name,
       "cheat" in doc.lower() and "crime" in doc.lower() and "sarcasm" in doc.lower(), name)


# ======================================================================================
# 4. Audience: recruiters and TA leads only, never advice addressed to a candidate
# ======================================================================================
print("\n4. the audience is fixed in the prompt, not left to the auto-built persona alone")

ok("write-body.md states the audience plainly", "RECRUITERS AND TA LEADS" in WRITE_BODY)
ok("and explicitly rules out writing advice addressed to a candidate",
   "advice addressed to\na candidate" in WRITE_BODY or "advice addressed to a\ncandidate" in WRITE_BODY
   or "how to pass this test" in WRITE_BODY, WRITE_BODY[WRITE_BODY.find("RECRUITERS"):][:400])


# ======================================================================================
# 5. Feature allowlist: wired to the company's own features.md, end to end
# ======================================================================================
print("\n5. only a feature on the company's own features.md may be named, proven through a real call")

ok("the prompt points the writer at FILE 3 for the feature list", "FILE 3" in WRITE_BODY)
ok("and refuses anything plausible-sounding that is not on it",
   "does not exist for this article's purposes" in WRITE_BODY)

_fixture.plant_brand_files()      # plants a REAL brand/features.md: "Programmes: cohort-based..."
BP_F, RS_F, CARDS_F = _fixture.write_inputs()
IDX_F = C.card_index(CARDS_F)
CTX_F = C.context(BP_F, RS_F)
st = {"spine": RS_F["spine"], "sections": [
    {"headline": s["h2"], "job": s["job"], "h3s": [], "lead": {"card_ids": s.get("evidence") or []},
     "is_item": False} for s in BP_F["sections"][:1]]}

PROMPTS = []


def capture_text(prompt, system=None, **kw):
    PROMPTS.append(prompt)
    return "## A\n\nOne fact [c1]. Another sentence to give it length."


real_text = llm.text
llm.text = capture_text
try:
    write_body.run(st, IDX_F, CTX_F, say)
finally:
    llm.text = real_text
body_prompt = PROMPTS[0] if PROMPTS else ""
ok("the actual company features.md content reached the section writer's prompt",
   "Programmes: cohort-based, practitioner-led" in body_prompt, body_prompt[:0])
ok("the FILE 3 instruction travelled alongside it, in the same call",
   "WHAT WE BELIEVE" in body_prompt and "Programmes: cohort-based" in body_prompt, body_prompt[:0])

# With no features.md on file at all (an onboarding that has not built one yet), the call must not
# crash and must say so honestly rather than silently passing an empty block.
from seo_agent import store
_saved_features = store.knowledge("brand/features.md")
store.save_knowledge("brand/features.md", "")
PROMPTS[:] = []
llm.text = capture_text
try:
    write_body.run(st, IDX_F, CTX_F, say)
finally:
    llm.text = real_text
ok("with no features file at all, it says so plainly instead of leaving a blank FILE 3",
   "no features file on record" in (PROMPTS[0] if PROMPTS else ""))
if isinstance(_saved_features, str):
    store.save_knowledge("brand/features.md", _saved_features)


# ======================================================================================
# 6. The final self-check: a five-point list, immediately before the reply is returned
# ======================================================================================
print("\n6. readable.md checks itself against rules 1-5 before it answers")

ok("the self-check sits in readable.md, the last whole-article rewrite",
   "BEFORE YOU RETURN ANYTHING, CHECK YOUR OWN REBUILD" in READABLE)
for word in ("LENGTH.", "SOURCES.", "TONE.", "AUDIENCE.", "FEATURES."):
    ok("the checklist covers %s" % word.rstrip("."), word in READABLE)
# Order matters for a reader auditing this file by hand: it must come before the JSON contract, not
# after it, or "before you return anything" would be describing a check already too late to matter.
ok("the self-check appears BEFORE the 'return as JSON' instruction, not after",
   READABLE.find("BEFORE YOU RETURN ANYTHING") < READABLE.find("Return the rebuilt article as JSON"))

print("\nStubbed model and wire. Proves the tightened tolerance reaches both enforcement loops, the "
      "source and audience rules are in the body writer's prompt, the feature allowlist is wired to "
      "the company's own features.md end to end (not a hardcoded list), and the final self-check "
      "runs before readable.py's reply is returned.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all QA-report checks passed")
