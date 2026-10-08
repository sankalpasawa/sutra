"""tests/test_writing_rules_2026_10_08.py — the remaining gaps from the "SEO Writer: Writing Rules" doc.

Checked every line of that document against what prior PRs had already shipped (the +/-5% band, cite
the original source, never compare different questions, audience restriction, no invented features,
tone/screening language, sentence variety, no keyword-stuffing, the Testlify link in the close, table
headers, title/body agreement -- all already covered). What was left, six items:

  1. "Target 1,000 words when none is given." allocate_words.DEFAULT_WORDS and shape.budget_maths's
     matching inline fallback were both 1500/2500 -- legacy numbers from before the length became a
     question asked of the person every time. Brought both down to 1,000, and proved the fallback
     actually reaches target_words(), not just the constant sitting unused.
  2. Tone: "lazy" and "dishonest" join "cheat" and "crime" on the no-presumed-guilt list, in both
     write-body.md and _writing_rules.md (the copy the edit path reaches).
  3. "The name you write is the name the tag points to." A sentence can name the right KIND of
     source (rule from the prior PR) while still citing the wrong ORGANIZATION's card because two
     cards reported similar numbers. New rule in write-body.md closes that specific gap.
  4. The intro's agitate-beat figure and the TL;DR's one allowed number must be the SAME figure, not
     two independently-chosen ones each getting the "repeat it once" exception. wrapper.md now says
     so explicitly.
  5. blend.md's "reference to something not there" rule covered backward references ("as we saw
     above") only. Extended to forward promises ("the example below shows X") -- the twin failure
     mode, and the document's own example ("as the next section explains") is a forward one.
  6. readable.md's five-point self-check gets a sixth: STRUCTURE -- title/body agreement, promised
     content actually delivered, and table headers surviving the rebuild. The underlying rules all
     already exist elsewhere in the pipeline; this is the point where the LAST whole-article step
     checks itself against them, same as it already does for length, sources, tone, audience and
     features.

Run: SEO_AGENT_DATA=$(mktemp -d) bash seo_agent/tests/run_all.sh
"""
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent.tools import _shared as sh
from seo_agent.write import _common as C, allocate_words, shape

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


WRITE_BODY = open(sh.PROMPTS + "/write/write-body.md", encoding="utf-8").read()
SHARED_RULES = open(sh.PROMPTS + "/_writing_rules.md", encoding="utf-8").read()
WRAPPER = open(sh.PROMPTS + "/write/wrapper.md", encoding="utf-8").read()
BLEND = open(sh.PROMPTS + "/write/blend.md", encoding="utf-8").read()
READABLE = open(sh.PROMPTS + "/write/readable.md", encoding="utf-8").read()


# ======================================================================================
# 1. No-band fallback is 1,000 words, proved through target_words() and budget_maths(), not just
#    the constants
# ======================================================================================
print("\n1. 'target 1,000 words when none is given' reaches the real functions, not just the constant")

ok("allocate_words.DEFAULT_WORDS is 1,000", allocate_words.DEFAULT_WORDS == 1000, allocate_words.DEFAULT_WORDS)
ok("target_words() with no plan at all falls back to 1,000", allocate_words.target_words(None) == 1000)
ok("target_words() with an empty word_band falls back to 1,000",
   allocate_words.target_words({"word_band": {}}) == 1000)
ok("target_words() with a real band still uses the person's own midpoint, not the fallback",
   allocate_words.target_words({"word_band": {"min": 800, "max": 1200}}) == 1000)
m = shape.budget_maths({})
ok("shape.budget_maths's inline fallback matches: 1000 x 0.9 = 900", m["budget"] == 900, m)


# ======================================================================================
# 2. Tone: "lazy" and "dishonest" join the no-presumed-guilt list, in both prompt copies
# ======================================================================================
print("\n2. 'lazy' and 'dishonest' are banned alongside 'cheat' and 'crime', in both prompt copies")

for doc, name in ((WRITE_BODY, "write-body.md"), (SHARED_RULES, "_writing_rules.md (reaches the edit path)")):
    ok("%s bans 'lazy'" % name, "lazy" in doc.lower(), name)
    ok("%s bans 'dishonest'" % name, "dishonest" in doc.lower(), name)
    ok("%s still bans the original 'cheat' / 'crime' pair" % name,
       "cheat" in doc.lower() and "crime" in doc.lower(), name)
    ok("%s frames this as 'guilt OR a character flaw', not guilt alone" % name,
       "character flaw" in doc.lower(), name)


# ======================================================================================
# 3. The name in the sentence must be the name the tag's own card actually points to
# ======================================================================================
print("\n3. a named source must be the organization the cited card actually comes from")

ok("the rule is in write-body.md", "THE NAME YOU WRITE IS THE NAME THE TAG POINTS TO" in WRITE_BODY)
ok("it names the exact failure mode: a different org's card wearing this name because the finding "
   "looks similar", "wearing" in WRITE_BODY and "similar" in WRITE_BODY)
ok("it sits beside the existing 'credit the original source' rule, not replacing it",
   "CREDIT THE ORIGINAL SOURCE" in WRITE_BODY)


# ======================================================================================
# 4. The intro's hook figure and the TL;DR's one allowed number must be the same figure
# ======================================================================================
print("\n4. the TL;DR's one allowed number must be the SAME figure the intro already used")

ok("wrapper.md's TL;DR rule is in wrapper.md", "At most ONE number across the whole block" in WRAPPER)
ok("it now says that number must be the same one the intro's agitate beat already used",
   "THE SAME\n  figure the intro" in WRAPPER or "THE SAME figure the intro" in WRAPPER
   or ("SAME" in WRAPPER and "agitate beat already used" in WRAPPER))
ok("it explains why: one figure gets this repeated treatment on purpose, a second one would be the "
   "redundancy the rest of the prompt works against", "redundancy" in WRAPPER)


# ======================================================================================
# 5. blend.md's "reference to something not there" rule now covers forward promises too
# ======================================================================================
print("\n5. blend.md's dangling-reference rule covers promises to come, not just references back")

ok("the original backward-reference rule survives", '"as we saw above"' in BLEND)
ok("it now explicitly runs both ways", "THIS RUNS BOTH WAYS" in BLEND)
ok("it names the forward failure mode by its own example: a promised section that never arrives",
   "the example below\n   shows" in BLEND or "the example below shows" in BLEND)
ok("and tells the editor what to do about it: fix the promise or cut it",
   "fix the promise or cut it" in BLEND)


# ======================================================================================
# 6. readable.md's self-check gains a sixth point: STRUCTURE
# ======================================================================================
print("\n6. readable.md's final self-check is now six points, not five -- STRUCTURE added")

ok("the self-check still opens the same way", "BEFORE YOU RETURN ANYTHING, CHECK YOUR OWN REBUILD" in READABLE)
for word in ("LENGTH.", "SOURCES.", "TONE.", "AUDIENCE.", "FEATURES.", "STRUCTURE."):
    ok("the checklist covers %s" % word.rstrip("."), word in READABLE)
ok("the closing line now says six, not five",
   "one of these six" in READABLE and "one of these five" not in READABLE)
ok("STRUCTURE covers the headline promise", "headline promises" in READABLE)
ok("STRUCTURE covers table headers surviving the rebuild", "column headers" in READABLE)
ok("STRUCTURE covers forward references actually arriving",
   '"below" or "next"' in READABLE or "below\" or \"next\"" in READABLE)
ok("STRUCTURE still comes before the JSON-return instruction, same ordering rule as before",
   READABLE.find("BEFORE YOU RETURN ANYTHING") < READABLE.find("Return the rebuilt article as JSON"))


print("\nProves the no-band word-count fallback is 1,000 end to end (constant and both functions that "
      "read it), the tone ban now covers 'lazy' and 'dishonest', a cited name must match its tag's "
      "actual source, the intro and TL;DR share one anchor figure instead of two, blend.md's dangling-"
      "reference check runs forward as well as backward, and readable.md's self-check is six points.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all writing-rules checks passed")
