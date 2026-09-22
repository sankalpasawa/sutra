"""tests/test_gap_and_world.py — where a gap comes from, and how long a boundary is allowed to be.

THE INCIDENT (Aparna's review, then Devansh's own reading, 2026-09-22). The four-fifths adverse
impact rule appeared in 4 of 11 published articles, eleven separate times in "Recruiting Metrics"
across two of its nine sections, while Source of Hire and Offer Acceptance Rate -- topics EVERY
ranking page covers -- were dropped without a word.

It was not random. `prompts/research/winners.md` asked for:

    "Name the Gaps we can own -- sub-topics thin or missing across winners, judged against the
     distinct angle"

A gap was defined as an absence that matched our own angle. Testlify's angle is always some form
of "verify skills properly", so the gap came out compliance-shaped on every article in the niche.
The topic gate then wrote the best gap INTO the angle, and the angle steers every later prompt.

Devansh's fix, and this suite pins it:

  1. THE GAP COMES FROM THE READER, NOT FROM US. The prompt is handed the People Also Ask
     questions -- the only place in the whole run where real people say what they want in their
     own words -- and a gap must point at one. "Judged against the distinct angle" is gone, and
     the prompt says out loud why, so nobody restores it as a tidy-up.
  2. IT IS ALLOWED TO FIND NOTHING. "none" is a real finding: a well-served keyword the article
     must win on quality instead. The old wording implied gaps must exist, so it invented them.
  3. THREE AT MOST, FIFTEEN WORDS AT MOST, PLAIN ENGLISH, ONE DIRECTION. Three gaps pulling three
     ways is how an article argues three things and lands none.
  4. NO PAA IS NOT AN EMPTY BLOCK. It becomes a plain note, because an empty string reads as a
     formatting slip and gets ignored, while "(none captured)" correctly makes a gap HARDER to
     claim.
  5. THE WORLD STATEMENT IS A BOUNDARY, NOT AN ESSAY. Measured on real runs: "about" 75 to 88
     words, "not about" 164 to 200. That block is pasted into every research question, every
     keyword batch and the architect's call -- paid for 20+ times an article. Shorter, NOT vaguer:
     naming the confusable world by name is the entire job.

These are prompt changes, so what is testable is the contract: the token reaches the prompt, the
rules are stated, and the discredited instruction is gone. That is worth pinning precisely because
a prompt has no type checker and a well-meaning edit can undo the whole fix silently.

Run: SEO_AGENT_DATA=$(mktemp -d) bash seo_agent/tests/run_all.sh
"""
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm
from seo_agent.research import _common as _c, winners

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


WINNERS = _c.load_prompt("winners") if hasattr(_c, "load_prompt") else None
if WINNERS is None:
    from seo_agent.tools import _shared as sh
    WINNERS = sh.load_prompt("research/winners")
WORLD = None
try:
    WORLD = sh.load_prompt("research/world")
except Exception:                          # noqa: BLE001
    from seo_agent.tools import _shared as sh
    WORLD = sh.load_prompt("research/world")

low = WINNERS.lower()


# ---- 1. the gap comes from the reader ----------------------------------------------------------
print("a gap comes from the reader, not from our own angle")

ok("the prompt is handed the People Also Ask questions", "{{PAA}}" in WINNERS)
ok("and it says they are what real people ask",
   "people also ask" in low or "actually ask" in low)
ok("the discredited instruction is GONE: gaps are no longer judged against our angle",
   "judged against the distinct angle" not in low, "the old wording is still in the prompt")
ok("and the prompt says WHY, so nobody restores it as a tidy-up",
   "do not judge gaps against our angle" in low)
ok("a gap must name who wants it",
   "wanted because" in low or "who wants it" in low)


# ---- 2. it is allowed to find nothing -----------------------------------------------------------
print("\nfinding no gap is a real answer")

ok("none is explicitly allowed", "none is a perfectly good answer" in low or "often none" in low)
ok("and inventing one to fill the section is forbidden",
   "never invent" in low)


# ---- 3. the limits ------------------------------------------------------------------------------
print("\nthree at most, fifteen words at most, one direction")

ok("at most three", "at most three" in low)
ok("at most fifteen words each", "fifteen words" in low)
ok("plain english is required by name", "plain english" in low)
ok("all of them must point one way",
   "point the same way" in low or "same direction" in low)
ok("and the reason is given, so the rule survives an edit",
   "three directions" in low or "three ways" in low)


# ---- 4. a missing PAA is a note, never an empty block -------------------------------------------
print("\nno PAA becomes a plain note, not an empty block")

seen = {}
_orig_text = llm.text
llm.text = lambda p, **k: seen.setdefault("prompt", p) and "" or ""
try:
    winners.write_up({"https://x.example/a": {"word_count": 900, "headings": ["A"]}},
                     "an angle", "a keyword", {"brand": "Example"}, paa=None)
    empty_prompt = seen.get("prompt", "")
    seen.clear()
    winners.write_up({"https://x.example/a": {"word_count": 900, "headings": ["A"]}},
                     "an angle", "a keyword", {"brand": "Example"},
                     paa=["How do you calculate it?", "  ", "What is a good score?"])
    filled_prompt = seen.get("prompt", "")
finally:
    llm.text = _orig_text

ok("with no PAA the prompt says so in words",
   "none captured" in empty_prompt.lower(), empty_prompt[-400:])
ok("with PAA the questions are really in the prompt",
   "How do you calculate it?" in filled_prompt and "What is a good score?" in filled_prompt)
ok("and a blank question is not passed through as a bullet with nothing after it",
   "\n- \n" not in filled_prompt and "- \n" not in filled_prompt.replace("- How", "x"),
   filled_prompt[filled_prompt.find("- How") - 40:filled_prompt.find("- How") + 120]
   if "- How" in filled_prompt else filled_prompt[-300:])


# ---- 5. the world statement is a boundary, not an essay -----------------------------------------
print("\nthe world statement is a boundary, not an essay")

wlow = (WORLD or "").lower()
ok("about is capped at one sentence", "one sentence" in wlow)
ok("not-about is capped at three named worlds", "at most three" in wlow)
ok("shorter is required, and vaguer is forbidden in the same breath",
   "shorter, not vaguer" in wlow, "the cap could be read as permission to be vague")
ok("the naming example survives, because naming the world by name IS the job",
   "hackathon" in wlow)
ok("and the cost is stated, so the cap is not mistaken for style",
   "twenty times" in wlow or "20+" in wlow)


print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all gap and world checks passed")
