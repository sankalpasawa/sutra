"""tests/test_readable_cutrounds.py — the author's word limit survives a rewrite that undershoots its own cut.

THE GAP THIS CLOSES. readable.run() is the last step that rewrites the article whole, and it was
told the gap once: "you are N words over, cut that many." One call. Nothing checked whether the
model actually did it, and nothing after this step enforces the number at all -- clean.py and
assemble.py only ever REPORT the final length (reports["clean"], reports["assemble"]["length"]).
A model that tries and comes back 60% of the way there was treated the same as one that landed
exactly: "applied": True, ship it.

This suite proves the bounded extra-round loop added to readable.run():
  * when the first cut still leaves the article over C.WORD_BAND_CEILING_PCT of target, a further
    round runs, told the gap measured off the LAST round's own output;
  * it keeps going, up to C.WORD_BAND_MAX_ROUNDS extra rounds, until the article is back in band;
  * a round that makes no real progress (< C.WORD_BAND_MIN_PROGRESS words cut) ends the loop at
    once, rather than spending a budget on a model that has already said no;
  * an article that lands in band on the FIRST rewrite costs exactly one model call -- the common
    case is not slowed down by a mechanism built for the uncommon one;
  * report["cut_rounds"] says how many extra rounds ran, so a person can see it happened.
"""
import copy
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm
from seo_agent.write import _common as C, readable

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


def say(*_a, **_k):
    pass


def _article(n_words):
    # intro/close/quick_answer left EMPTY on purpose: readable.words() sums every text field, and a
    # non-empty one would add a fixed offset on top of n_words, which is exactly the kind of
    # off-by-a-few arithmetic this suite exists to not have to chase. With them empty, words(article)
    # == n_words exactly, so every expected number below is the number actually asserted.
    return {"h1": "H", "intro": "", "quick_answer": "", "faq": [], "close": "", "close_heading": "Next",
           "sections": [{"heading": "A", "prose": ("word " * n_words).strip()}]}


# Isolate the loop under test: fix_fat/fix_plain/judge_coverage/coverage_report are the readability
# and coverage passes, a different concern from "did it land in the word band", and each one is its
# own model call the real run() makes once at the end regardless of how many cut rounds ran. Stubbed
# to identity/empty so this suite counts only the calls the cut loop itself makes.
_real = {"fix_fat": readable.fix_fat, "fix_plain": readable.fix_plain,
         "judge_coverage": readable.judge_coverage, "coverage_report": readable.coverage_report}
readable.fix_fat = lambda w, say=None: (w, {})
readable.fix_plain = lambda w, rounds=2, say=None: (w, {})
readable.judge_coverage = lambda *a, **k: {}
readable.coverage_report = lambda *a, **k: {}

TARGET = 1000
CEILING = TARGET * C.WORD_BAND_CEILING_PCT      # 1,100


# ======================================================================================
# 1. A rewrite that lands in band on the first try costs exactly one call
# ======================================================================================
print("\nthe common case: landed in band on the first rewrite, no extra cost")

CALLS = []


def stub_lands_first(prompt, system=None, retries=1, **kw):
    CALLS.append(prompt)
    return {"sections": [{"heading": "A", "prose": "word " * 1050}]}       # under CEILING=1,100


real_json = llm.json_call
llm.json_call = stub_lands_first
try:
    CALLS[:] = []
    out = readable.run(_article(2200), {"word_band": {"min": TARGET, "max": TARGET}}, {}, say)
finally:
    llm.json_call = real_json

ok("exactly one model call: no extra round was needed", len(CALLS) == 1, len(CALLS))
ok("cut_rounds is 0", out["report"]["cut_rounds"] == 0, out["report"])
ok("the article is within band", readable.words(out["article"]) <= CEILING, readable.words(out["article"]))


# ======================================================================================
# 2. Overshoots twice, lands on the third call -- two extra rounds, then stops
# ======================================================================================
print("\novershoots twice: two extra rounds run, each told the gap off the LAST round, then it stops")

SEQUENCE = [1800, 1300, 1050]      # first cut: still over; round 1: still over; round 2: in band
SEEN_OVER_BY = []


def stub_needs_two_rounds(prompt, system=None, retries=1, **kw):
    i = len(CALLS)
    CALLS.append(prompt)
    # the over_by line names the gap the model was told -- captured so this test can prove it was
    # measured off the PREVIOUS round's output, not recomputed from the original draft every time
    for line in prompt.splitlines():
        if "words OVER" in line or "within the length" in line:
            SEEN_OVER_BY.append(line.strip())
            break
    n = SEQUENCE[min(i, len(SEQUENCE) - 1)]
    return {"sections": [{"heading": "A", "prose": "word " * n}]}


llm.json_call = stub_needs_two_rounds
try:
    CALLS[:] = []
    SEEN_OVER_BY[:] = []
    out = readable.run(_article(2600), {"word_band": {"min": TARGET, "max": TARGET}}, {}, say)
finally:
    llm.json_call = real_json

ok("three calls total: the first rewrite plus two extra cut rounds", len(CALLS) == 3, len(CALLS))
ok("cut_rounds records exactly two extra rounds", out["report"]["cut_rounds"] == 2, out["report"])
ok("it stopped the moment it landed in band, not after burning the full round budget",
   readable.words(out["article"]) <= CEILING, readable.words(out["article"]))
# Each call's own over_by names the gap in the article GOING INTO that call, so the sequence is the
# trail of a shrinking draft: 2,600 (the original) -> 1,800 (round 1's input) -> 1,300 (round 2's
# input) -> 1,050 (lands, loop stops with no fourth call needed).
ok("the first call is told the gap off the ORIGINAL 2,600-word draft",
   "1,600" in SEEN_OVER_BY[0], SEEN_OVER_BY)
ok("the second call is told a SMALLER gap, measured off round 1's own 1,800-word output "
   "-- not the original draft repeated",
   "1,600" not in SEEN_OVER_BY[1] and "800" in SEEN_OVER_BY[1], SEEN_OVER_BY)
ok("the third call's gap is smaller again, off round 2's 1,300-word output",
   "800" not in SEEN_OVER_BY[2] and "300" in SEEN_OVER_BY[2], SEEN_OVER_BY)


# ======================================================================================
# 3. Still over after every round it is allowed: stops at the ceiling, cut_rounds caps out
# ======================================================================================
print("\nstill over after every round it is allowed: the loop ends on the round budget, not forever")


def stub_never_lands(prompt, system=None, retries=1, **kw):
    CALLS.append(prompt)
    # cuts a real, meaningful amount every time, but never enough to clear the ceiling
    n = max(1400, 2600 - 300 * len(CALLS))
    return {"sections": [{"heading": "A", "prose": "word " * n}]}


llm.json_call = stub_never_lands
try:
    CALLS[:] = []
    out = readable.run(_article(2600), {"word_band": {"min": TARGET, "max": TARGET}}, {}, say)
finally:
    llm.json_call = real_json

ok("it tried the first rewrite plus every extra round it is allowed, no more",
   len(CALLS) == 1 + C.WORD_BAND_MAX_ROUNDS, len(CALLS))
ok("cut_rounds is capped at WORD_BAND_MAX_ROUNDS", out["report"]["cut_rounds"] == C.WORD_BAND_MAX_ROUNDS, out["report"])


# ======================================================================================
# 4. No progress: the model declines to cut further, and the loop takes that as the answer
# ======================================================================================
print("\nno real progress on a round: treated as the model declining, not retried into a billing loop")


def stub_stalls(prompt, system=None, retries=1, **kw):
    CALLS.append(prompt)
    # first cut gets partway there; the extra round returns the SAME length: no progress at all
    return {"sections": [{"heading": "A", "prose": "word " * 1300}]}


llm.json_call = stub_stalls
try:
    CALLS[:] = []
    out = readable.run(_article(2600), {"word_band": {"min": TARGET, "max": TARGET}}, {}, say)
finally:
    llm.json_call = real_json

ok("one extra round ran (saw it had not landed), then a second attempt made no progress and stopped "
   "rather than spending the full round budget for nothing",
   len(CALLS) == 2, len(CALLS))
ok("cut_rounds reflects the one round that actually ran before the stall was caught",
   out["report"]["cut_rounds"] == 1, out["report"])


# ======================================================================================
# 5. An empty reply on an extra round ends the loop, keeping the best article found so far
# ======================================================================================
print("\nan empty reply on an extra round ends the loop, keeping what the last good round produced")


def stub_goes_empty(prompt, system=None, retries=1, **kw):
    CALLS.append(prompt)
    if len(CALLS) == 1:
        return {"sections": [{"heading": "A", "prose": "word " * 1800}]}   # still over; a round is tried
    return {}                                                               # the extra round answers nothing


llm.json_call = stub_goes_empty
try:
    CALLS[:] = []
    out = readable.run(_article(2600), {"word_band": {"min": TARGET, "max": TARGET}}, {}, say)
finally:
    llm.json_call = real_json

ok("the empty extra round still counted as an attempt", out["report"]["cut_rounds"] == 1, out["report"])
ok("the article is the last round that DID answer (1,800 words), not thrown away",
   readable.words(out["article"]) == 1800, readable.words(out["article"]))
ok("and it is still over the ceiling, honestly -- an empty reply ends the loop, it does not pretend "
   "to have landed", readable.words(out["article"]) > CEILING, readable.words(out["article"]))


# ---- tidy up --------------------------------------------------------------------------------------
readable.fix_fat, readable.fix_plain = _real["fix_fat"], _real["fix_plain"]
readable.judge_coverage, readable.coverage_report = _real["judge_coverage"], _real["coverage_report"]

print("\nStubbed model. Proves the author's word limit is enforced with a bounded, self-stopping "
      "retry -- free on the common path, capped and progress-guarded on the uncommon one.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all readable cut-round checks passed")
