"""tests/test_research_demand.py — the researchers finally see what readers want, and must ask about it.

THE INCIDENT (Aparna's review, 2026-09-22). "Why did it not even start with what are the different
types of skills assessments?" The architect's own prompt already demanded exactly that, in capitals:

    AT LEAST 3 OR 4 OF THE EXPECTED TOPICS SHOULD BE SECTIONS IN THEIR OWN RIGHT
    THE BASICS COME FIRST. If the article defines its own subject anywhere ("what a skills
    assessment is"), that section is placed before anything that assumes the definition.

It could not obey, because it had nothing to obey with. The chain, traced end to end:

  research measures what every ranking page covers, what people ask Google, and Google's own
  answer -> NONE of it is passed to the research conversation, which is handed five lines: title,
  angle, spine, about, not-about -> so the twelve questions are shaped by our angle alone -> nobody
  asks about the basics -> no evidence comes back for them -> no cluster forms -> no box exists ->
  the architect cannot build the section however loudly it is told to.

On Recruiting Metrics the result was measurable: of the six topics every ranking page covered,
Source of Hire and Offer Acceptance Rate were missing from the published article entirely.

Two halves, and the second is the one that matters:

  1. THE BRIEF NOW CARRIES THE DEMAND. Table stakes, the People Also Ask questions and the AI
     Overview go in beside the spine, so even a free question is asked by somebody who can see what
     readers expect.
  2. THE FIRST QUESTIONS ARE SET, NOT REQUESTED. RESERVED_TURNS of each researcher's turns are
     taken from the expected topics and the model is simply NOT ASKED on those turns, so it cannot
     decline. Asking nicely was tried: the architect prompt shouts in capitals and is ignored.
     Half the conversation stays free, which is where the interesting questions always came from.

The costs are pinned too, because "add more context" is how a prompt quietly doubles: the brief
stays small, and a run with no demand measured is unchanged from before.

Run: SEO_AGENT_DATA=$(mktemp -d) bash seo_agent/tests/run_all.sh
"""
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm
from seo_agent.research import curate

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


STAKES = ["Time to Fill", "Cost per Hire", "Source of Hire", "Quality of Hire",
          "Offer Acceptance Rate", "Time to Hire"]
CTX = {"spine": "what this argues", "about": "recruiting measurement", "not_about": "payroll",
       "table_stakes": STAKES,
       "paa": ["How do you calculate time to fill?", "What is a good offer acceptance rate?"],
       "ai_overview": "Google answers it with a list of six metrics."}


# ---- 1. the brief carries the demand -----------------------------------------------------------
print("the research brief carries what readers already want")

brief = curate._article_block("Recruiting Metrics", "an angle", CTX)
ok("what every ranking page covers is in it", "Source of Hire" in brief)
ok("what people ask Google is in it", "How do you calculate time to fill?" in brief)
ok("Google's own answer is in it", "six metrics" in brief)
ok("and it says WHY they matter, so they are not read as decoration",
   "leaves before reaching anything" in brief, brief[:300])

bare = curate._article_block("A topic", "an angle", {"spine": "s"})
ok("a run with nothing measured is unchanged: no empty headings, no blank bullets",
   "WHAT EVERY PAGE" not in bare and "  - " not in bare, bare)
ok("and the brief stays small: the conversation is capped at 2,500 words and this must not eat it",
   len(brief.split()) < 400, len(brief.split()))


# ---- 2. the first questions are SET, not asked for ---------------------------------------------
print("\nthe expected topics are put to the researchers, not suggested")

seeds = curate._seed_questions(STAKES, 3)
ok("every researcher gets the same reserved share",
   [len(x) for x in seeds] == [curate.RESERVED_TURNS] * 3, [len(x) for x in seeds])
flat = [q for row in seeds for q in row]
ok("all six expected topics are covered between them",
   all(any(t in q for q in flat) for t in STAKES), flat)
ok("they are dealt round-robin, so one topic is not answered by one mind",
   seeds[0][0] != seeds[1][0] and "Time to Fill" in seeds[0][0] and "Cost per Hire" in seeds[1][0],
   seeds)
ok("a heading becomes a real question, because a bare heading makes a poor web search",
   all(q.strip().endswith("?") for q in flat), flat)

already = curate._seed_questions(["Is a skills test legally defensible?"], 1)
ok("a topic that is already a question is left alone",
   already[0] == ["Is a skills test legally defensible?"], already)
ok("no expected topics means no reserved turns, and the conversation is entirely free",
   curate._seed_questions([], 3) == [[], [], []])
ok("blank entries never become a question about nothing",
   curate._seed_questions(["  ", "", "Real topic"], 1)[0] ==
   ["What does a reader need to know about Real topic, for this article?"],
   curate._seed_questions(["  ", "", "Real topic"], 1))

ok("half the conversation stays free for the questions worth having",
   curate.RESERVED_TURNS * 2 <= curate.TURNS,
   "reserved %d of %d turns" % (curate.RESERVED_TURNS, curate.TURNS))


# ---- 3. a reserved turn never reaches the model -------------------------------------------------
print("\na reserved turn is never put to the model, so it cannot be declined")

asked = []
_orig_text = llm.text
llm.text = lambda p, **k: (asked.append(p), "Some invented question?")[1]
try:
    q1 = curate._ask("topic", brief, {"role": "the sceptic", "focus": "proof"}, [])
finally:
    llm.text = _orig_text
ok("an ordinary turn does go to the model", len(asked) == 1 and q1)

# The loop's own rule, in the one line that matters: a seed wins over the model for that turn.
seeds_for_one = ["What does a reader need to know about Source of Hire, for this article?"]
turns_so_far = []
chosen = seeds_for_one[len(turns_so_far)] if len(turns_so_far) < len(seeds_for_one) else ""
ok("with a seed left, the seed is the question", chosen == seeds_for_one[0])
turns_so_far = [{"question": "x", "answer": "y"}]
chosen = seeds_for_one[len(turns_so_far)] if len(turns_so_far) < len(seeds_for_one) else ""
ok("once the seeds run out, the researcher is free again", chosen == "")


# ---- 4. the free questions can see the demand too -----------------------------------------------
print("\neven a free question is asked by somebody who can see what readers expect")

from seo_agent.tools import _shared as sh
p = sh.load_prompt("research/ask-question")
low = p.lower()
ok("the question prompt tells them to read what every ranking page covers",
   "every ranking page already covers" in low)
ok("and not to repeat a question already put to them as a set one",
   "do not repeat those" in low)


print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all research-demand checks passed")
