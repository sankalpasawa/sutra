"""tests/test_edit_wordlimit.py — a word-count request through chat feedback is not fighting itself.

THE BUG (owner, 2026-10-07): "even when I explicitly ask for a 1,000-word blog, it continues to
generate 1,800+ words despite repeated feedback and prompts to keep it within the requested limit."

The initial-generation half of this was already fixed (seo_agent/write/readable.py's bounded cut
rounds). This suite is the OTHER half: feedback given on an article that already exists goes through
a completely different door, library_edit.propose_article, whose own prompt used to say, unconditionally,
"Keep the article's length in the same range it came in" -- so a person typing "make this 1,000 words"
again and again was losing to an instruction built into the system telling the model the opposite.

What this proves:
  * parse_word_target reads a length request out of plain instruction text, last number wins;
  * with no number in the instruction, propose_article behaves EXACTLY as before (one pass, the
    original "keep the same range" text, zero rounds) -- existing callers (the Library's own
    "AI article" button with no number typed) see no change at all;
  * with a number, propose_article retries -- bounded, progress-guarded, same discipline as
    readable.py's cut-round loop -- each round told the gap measured off the LAST round's output;
  * the heading/citation guards still run on every round, not just the first;
  * the tone fix (candidates described as people a process moves through, never units it discards)
    actually landed in both places prose can originate: the shared writing-rules include (reaches
    the edit path) and write-body.md (first-draft generation).
"""
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import library_edit as le, store
from seo_agent.tools import _shared as sh, edit_article

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


def _article(n_words, heading="What it costs", body_tag="[c1]"):
    return ("# Cost per hire\n\nIntro line [c2].\n\n## %s\n\n%s %s\n"
           % (heading, ("word " * n_words).strip(), body_tag))


# ======================================================================================
# 1. parse_word_target: plain-text number extraction
# ======================================================================================
print("\nparse_word_target reads a length request out of ordinary instruction text")

ok("a bare number", le.parse_word_target("make this 1000 words") == 1000)
ok("a comma'd number", le.parse_word_target("cut it to 1,500 words") == 1500)
ok("hyphenated", le.parse_word_target("I want a 900-word version") == 900)
ok("no number at all is None", le.parse_word_target("make the tone warmer") is None)
ok("the LAST number wins, not the first (the one describing the problem)",
   le.parse_word_target("it's 1,800 words now, make it 1,000 words") == 1000)
ok("a number with no 'words' near it is not mistaken for a length",
   le.parse_word_target("we have 1200 candidates in the pipeline") is None)


# ======================================================================================
# 2. No number in the instruction: propose_article is UNCHANGED from before this fix
# ======================================================================================
print("\nno number in the instruction: behaves exactly as it always did")

AMD = _article(40)
aitem = store.library_save("wl1", "wl1r", "Cost per hire", AMD)
SEEN_PROMPTS = []


def stub_echo(prompt, system=None):
    SEEN_PROMPTS.append(prompt)
    return AMD.replace("word word", "word word, now warmer", 1)


out = le.propose_article(aitem, AMD, "make the tone warmer", model=stub_echo)
ok("exactly one model call: no target means no retry loop at all", len(SEEN_PROMPTS) == 1, len(SEEN_PROMPTS))
ok("length_rounds is 0", out["length_rounds"] == 0, out["length_rounds"])
ok("the prompt carries the ORIGINAL unconditional length text, unchanged",
   "Keep the article's length in the same range it came in" in SEEN_PROMPTS[0], SEEN_PROMPTS[0][-400:])
ok("and does NOT carry a target-words instruction", "THE READER WANTS THIS" not in SEEN_PROMPTS[0])


# ======================================================================================
# 3. A number in the instruction: the length rule flips to an explicit gap
# ======================================================================================
print("\na number in the instruction: the prompt is told the gap, not 'keep it as it is'")

SEEN_PROMPTS[:] = []
BIG = _article(1800)
big_item = store.library_save("wl2", "wl2r", "Cost per hire (long)", BIG)
out = le.propose_article(big_item, BIG, "make this 1000 words", model=stub_echo, target_words=1000)
real_gap = "{:,}".format(len(BIG.split()) - 1000)   # BIG carries a few extra words of heading/intro
ok("the length rule overrides the default, naming the gap",
   "THE READER WANTS THIS SHORTER" in SEEN_PROMPTS[0] and "1,000" in SEEN_PROMPTS[0], SEEN_PROMPTS[0][-500:])
ok("it names the REAL measured gap, not the round number the person typed",
   real_gap in SEEN_PROMPTS[0], (real_gap, SEEN_PROMPTS[0][-500:]))


# ======================================================================================
# 4. The retry loop: overshoots twice, lands on the third, then stops
# ======================================================================================
print("\novershoots twice, lands on the third call, then stops asking for more")

CALLS = []
SEQUENCE = [1800, 1300, 1050]     # first pass: still over; round 1: still over; round 2: in band


def stub_sequence(prompt, system=None):
    i = len(CALLS)
    CALLS.append(prompt)
    n = SEQUENCE[min(i, len(SEQUENCE) - 1)]
    return _article(n)


item3 = store.library_save("wl3", "wl3r", "Cost per hire (converges)", _article(2600))
CALLS[:] = []
out = le.propose_article(item3, _article(2600), "make this 1000 words", model=stub_sequence, target_words=1000)
ok("three calls total: the first pass plus two extra rounds", len(CALLS) == 3, len(CALLS))
ok("length_rounds records exactly two extra rounds", out["length_rounds"] == 2, out["length_rounds"])
ok("the proposed article is within band (<=1,100 words)",
   len(out["proposed"].split()) <= 1100, len(out["proposed"].split()))
ok("headings survived every round", "## What it costs" in out["proposed"])
ok("the citation tag survived every round", "[c1]" in out["proposed"] and "[c2]" in out["proposed"])


# ======================================================================================
# 5. Still over after every round allowed: stops at the round cap, does not loop forever
# ======================================================================================
print("\nstill over after every round it is allowed: stops on the round budget")

CALLS[:] = []


def stub_never_lands(prompt, system=None):
    CALLS.append(prompt)
    n = max(1400, 2600 - 300 * len(CALLS))     # real progress every time, never enough
    return _article(n)


item4 = store.library_save("wl4", "wl4r", "Cost per hire (never lands)", _article(2600))
out = le.propose_article(item4, _article(2600), "make this 1000 words", model=stub_never_lands, target_words=1000)
ok("tried the first pass plus every extra round it is allowed, no more",
   len(CALLS) == 1 + le.LENGTH_MAX_ROUNDS, len(CALLS))
ok("length_rounds is capped at LENGTH_MAX_ROUNDS", out["length_rounds"] == le.LENGTH_MAX_ROUNDS, out["length_rounds"])


# ======================================================================================
# 6. No real progress on a round: treated as the model declining, loop stops early
# ======================================================================================
print("\nno real progress: treated as the model declining further, not retried for nothing")

CALLS[:] = []


def stub_stalls(prompt, system=None):
    CALLS.append(prompt)
    return _article(1300)      # identical every time: zero progress after the first cut


item5 = store.library_save("wl5", "wl5r", "Cost per hire (stalls)", _article(2600))
out = le.propose_article(item5, _article(2600), "make this 1000 words", model=stub_stalls, target_words=1000)
ok("one extra round ran, found no progress, and stopped rather than spending the full budget",
   len(CALLS) == 2, len(CALLS))
ok("length_rounds reflects the one round that actually ran", out["length_rounds"] == 1, out["length_rounds"])


# ======================================================================================
# 7. Guards still fire mid-loop, not just on the first pass
# ======================================================================================
print("\na heading drift on an extra round is still caught, not just on the first pass")


def stub_drifts_on_round_two(prompt, system=None):
    if len(CALLS) == 0:
        CALLS.append(prompt)
        return _article(1800)                                    # pass 1: fine, still over
    CALLS.append(prompt)
    return _article(1000, heading="A different heading entirely")  # round 1: drifts a heading


CALLS[:] = []
item6 = store.library_save("wl6", "wl6r", "Cost per hire (drifts)", _article(2600))
out = le.propose_article(item6, _article(2600), "make this 1000 words", model=stub_drifts_on_round_two,
                         target_words=1000)
ok("a round that breaks a guard is dropped; the last GOOD text is kept, not a half-broken one",
   "## What it costs" in out["proposed"], out["proposed"][:120])
ok("a round that never applied (its own guard refused it) is not counted as a round that ran",
   out["length_rounds"] == 0, out["length_rounds"])


# ======================================================================================
# 8. edit_article.run() wires the chat instruction's number through end to end
# ======================================================================================
print("\nedit_article.run() parses the chat instruction and passes the number through")

ctx = {"chat_id": "wlc", "run_id": "wlr", "step_id": "edit", "emit": lambda **kw: None}
item7 = store.library_save("wl7", "wl7r", "Cost per hire (chat)", _article(2600))
CALLS[:] = []
real_propose = le.propose_article


def spy_propose(item_id, draft, instruction, model=None, target_words=None):
    CALLS.append(target_words)
    return real_propose(item_id, draft, instruction, model=stub_echo, target_words=target_words)


le.propose_article = spy_propose
try:
    result = edit_article.run(ctx, instruction="make this 1000 words", item_id=item7)
finally:
    le.propose_article = real_propose
ok("the parsed target reached propose_article", CALLS == [1000], CALLS)
ok("the tool's own return carries the target and the round count",
   result.get("target_words") == 1000 and "length_rounds" in result, result)


# ======================================================================================
# 9. The tone fix actually landed where prose originates and where it gets edited
# ======================================================================================
print("\nthe candidate-language rule landed in both the shared edit-path rules and write-body.md")

shared_rules = open(sh.PROMPTS + "/_writing_rules.md", encoding="utf-8").read()
write_body = open(sh.PROMPTS + "/write/write-body.md", encoding="utf-8").read()
MARK = "PEOPLE A PROCESS MOVES THROUGH"
ok("the shared writing-rules include (reaches write/edit-article.md) carries the rule", MARK in shared_rules)
ok("write-body.md (first-draft origin) carries the same rule", MARK in write_body)
ok("the exact complaint's own wording is named as the thing NOT to write",
   "remove any candidates" in shared_rules and "remove any candidates" in write_body)
ok("edit-article.md actually includes the shared rules block",
   "{{WRITING_RULES}}" in open(sh.PROMPTS + "/write/edit-article.md", encoding="utf-8").read())

print("\nStubbed model. Proves a word-count request given as chat feedback on an EXISTING article "
      "now gets the same bounded, verified retry the initial-generation fix already had, and that "
      "the candidate-language tone fix reaches both where prose is written and where it is edited.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all edit-wordlimit and tone checks passed")
