"""tests/test_card_filter_stakes.py — the card filter stops throwing away the basics.

THE INCIDENT (Devansh, 2026-09-22, after the demand round shipped: "check if this cutting and shit
was fine actually?"). On the first real run, the filter kept 292 cards of 534 and every number
looked healthy: nothing above the keep threshold was cut, and all 201 hard-data cards survived.

Reading the DROPPED pile instead of counting it found 23 cards answering topics EVERY ranking page
covers, including this one, on an article about interview scorecards:

    dropped, relevance 0: "Definition of interview scorecard as standardized evaluation form"
    table stake #1:       "Definition: what an interview scorecard is"

The cause was this step's own context: title, angle, spine, world, persona -- and nothing about
what readers already expect. So a card serving only the expected ground scored 0 or 1 against OUR
argument and died.

That is the research fix's own bug, one layer down. The researchers had just been sent to collect
exactly this evidence, and the very next step discarded it, which lands the article back at "it
never says what the thing is" -- the complaint the whole round exists to fix.

What this pins:

  1. THE EXPECTED TOPICS REACH THE FILTER AT ALL. They were on the research file the whole time.
  2. A CARD THAT ANSWERS ONE IS PROTECTED, not merely scored higher. Protection is the mechanism
     that already demonstrably works (201 of 201 survived that run) and is audited in the report.
     A score nudge would be invisible and untestable.
  3. IT IS NOT A BLANKET RESCUE. A genuinely off-topic card still dies, and the model is told that
     naming a topic a card does not answer keeps rubbish alive.
  3b. THE CLAIM CARRIES A RECEIPT, checked in code. The first version of this fix trusted whatever
     the model put in `covers_stake`, and this suite caught it: an article with NO measured topics
     still rescued two cards, because the claim was never checked against the list. A model that
     invents a topic name would otherwise keep any card it liked and nothing downstream could
     tell. Same rule the plan tagger already enforces on its own tags.
  4. THE OLD PROTECTIONS ARE UNTOUCHED: hard data, gap and competitor tags, unscored cards.
  5. THE REPORT SAYS HOW MANY SURVIVED THIS WAY -- the number that would have exposed the defect
     on the run that found it.

Run: SEO_AGENT_DATA=$(mktemp -d) bash seo_agent/tests/run_all.sh
"""
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm
from seo_agent.research import score_cards
from seo_agent.tools import _shared as sh

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


STAKES = ["Definition: what an interview scorecard is",
          "How to use or create a scorecard (structured steps)",
          "Pros and cons of using scorecards"]

# The real cards from the run that found this, plus controls.
CARDS = [
    {"id": 1, "tag": "evidence", "gloss": "Definition of interview scorecard as standardized evaluation form"},
    {"id": 2, "tag": "evidence", "gloss": "Workable: building a scorecard requires identifying traits and rating scales"},
    {"id": 3, "tag": "evidence", "gloss": "An entirely unrelated point about office furniture"},
    {"id": 4, "tag": "evidence", "gloss": "Structured interviews predict performance at r=0.51"},
    {"id": 5, "tag": "gap", "gloss": "Nobody shows what a 1 vs a 5 answer sounds like"},
    {"id": 6, "tag": "evidence", "gloss": "A card the judge forgot to score"},
]
REPLY = {"scores": [
    {"id": 1, "relevance": 1, "protected": False, "covers_stake": STAKES[0], "reason": "basics"},
    {"id": 2, "relevance": 0, "protected": False, "covers_stake": STAKES[1], "reason": "how-to"},
    {"id": 3, "relevance": 0, "protected": False, "covers_stake": "", "reason": "off spine"},
    {"id": 4, "relevance": 0, "protected": True, "covers_stake": "", "reason": "hard number"},
    {"id": 5, "relevance": 0, "protected": False, "covers_stake": "", "reason": "off spine"},
]}


def _run(reply=None, stakes=STAKES, cards=None):
    seen = {}
    _orig = llm.json_call

    def fake(p, **k):
        seen["p"] = p
        return reply if reply is not None else REPLY

    llm.json_call = fake
    try:
        kept, rep = score_cards.run(cards or CARDS, "Interview scorecard", "an angle",
                                    {"name": "Hiring manager"},
                                    {"spine": "s", "about": "a", "not_about": "b"},
                                    "Testlify", table_stakes=stakes)
    finally:
        llm.json_call = _orig
    return kept, rep, seen.get("p", "")


# ---- 1. the expected topics reach the filter ----------------------------------------------------
print("the expected topics reach the filter at all")

kept, rep, prompt = _run()
ids = sorted(c["id"] for c in kept)
ok("the table stakes are really in the prompt", STAKES[0] in prompt, prompt[:200])
ok("and they are introduced as what readers expect, not as more of our argument",
   "already covers" in prompt.lower())
ok("the prompt asks for the topic a card answers, by name",
   "covers_stake" in prompt)
ok("every token was filled", "{{" not in prompt, prompt[:160])


# ---- 2. the card that died on the real run now survives -----------------------------------------
print("\nthe cards that died on the real run now survive")

ok("the DEFINITION card survives, though it scored 1 against our own argument", 1 in ids, ids)
ok("the how-to card survives, though it scored 0", 2 in ids, ids)
ok("the report says how many were kept this way, so the number is visible next time",
   rep.get("kept_for_expected_topic") == 2, rep.get("kept_for_expected_topic"))
ok("and it records which topics it was working from",
   rep.get("expected_topics_seen") == STAKES, rep.get("expected_topics_seen"))


# ---- 3. it is not a blanket rescue --------------------------------------------------------------
print("\nit is not a blanket rescue: rubbish still dies")

ok("a genuinely off-topic card is still dropped", 3 not in ids, ids)
dropped_ids = [d["id"] for d in rep.get("dropped") or []]
ok("and it is on the record as dropped, with its reason", 3 in dropped_ids, dropped_ids)
ok("the prompt warns that a false claim here keeps rubbish alive",
   "keeps rubbish alive" in prompt.lower())

blank = {"scores": [dict(r, covers_stake="") for r in REPLY["scores"]]}
kept_b, rep_b, _p = _run(reply=blank)
ok("with no card claiming a topic, the old behaviour is exactly unchanged",
   sorted(c["id"] for c in kept_b) == [4, 5, 6], sorted(c["id"] for c in kept_b))

kept_n, rep_n, prompt_n = _run(stakes=[])
ok("an article with no measured expected topics says so rather than showing an empty list",
   "none measured" in prompt_n.lower(), prompt_n[:200])
ok("and nothing is rescued in that case, however the model answers",
   rep_n.get("kept_for_expected_topic") == 0, rep_n.get("kept_for_expected_topic"))

# The receipt rule on its own: a claim is only worth something when the topic really exists.
invented = {"scores": [dict(REPLY["scores"][0], covers_stake="A topic nobody measured"),
                       REPLY["scores"][2]]}
kept_i, rep_i, _p2 = _run(reply=invented, cards=[CARDS[0], CARDS[2]])
ok("a topic the model invented rescues nothing",
   1 not in [c["id"] for c in kept_i], [c["id"] for c in kept_i])
reworded = {"scores": [dict(REPLY["scores"][0], covers_stake="what an interview scorecard is"),
                       REPLY["scores"][2]]}
kept_r, _rr, _p3 = _run(reply=reworded, cards=[CARDS[0], CARDS[2]])
ok("but a real topic shortened the way a model reasonably would still counts",
   1 in [c["id"] for c in kept_r], [c["id"] for c in kept_r])


# ---- 4. the old protections are untouched -------------------------------------------------------
print("\nthe protections that already worked are untouched")

ok("a hard number still survives a zero score", 4 in ids, ids)
ok("a gap-tagged card still survives", 5 in ids, ids)
ok("an unscored card is still kept rather than silently dropped", 6 in ids, ids)
ok("and the unscored one is counted, not hidden", rep.get("unscored_count") == 1, rep.get("unscored_count"))


# ---- 5. a filter that cannot run still aborts ---------------------------------------------------
print("\nfail-closed is unchanged: a broken scorer still aborts the step")

_orig = llm.json_call


def _boom(*_a, **_k):
    raise RuntimeError("the scorer died")


llm.json_call = _boom
try:
    score_cards.run(CARDS, "t", "a", {}, {"spine": "s"}, "b", table_stakes=STAKES)
    aborted = False
except Exception:                          # noqa: BLE001
    aborted = True
finally:
    llm.json_call = _orig
ok("a crashed scorer aborts rather than defaulting every card to keep", aborted)


print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all card-filter expected-topic checks passed")
