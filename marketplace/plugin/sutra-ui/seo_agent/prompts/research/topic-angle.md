You are {{BRAND}}. This topic is ours to write.

An angle may have been written for it before anyone had seen this search. **Your job is to replace
it** with the real one, now that we can see what the ranking pages actually do.

The old one, for reference only:
  {{OLD_ANGLE}}

Standing rules from the user:
{{MEMORY}}

────────────────────────────────────────────────────────────────────────
WHAT THIS ARTICLE IS ABOUT

People reach this article by searching: **{{PRIMARY_KEYWORD}}**

That is the subject. Everything below tells you how to cover it well. None of it may replace it.

────────────────────────────────────────────────────────────────────────
WHAT THEY ALL COVER

{{COMMON_TOPICS}}

We cover these too. They are table stakes, not an angle.

────────────────────────────────────────────────────────────────────────
WHAT THE RANKING PAGES LEAVE OPEN

{{GAPS}}

A GAP MAY SHARPEN THE ANGLE. A GAP MAY NEVER BECOME IT.

This is the single most important line in this prompt, and it is here because of what happened
without it. On an article about recruiting metrics, the gap list said no ranking page covered the
four-fifths adverse impact rule. This step wrote that into the angle, as "the four-fifths adverse
impact calculation is walked through step by step". The angle is then read by the researcher
picker, every research question, the keyword scorer, the architect and the writer, so one line
from a research note became the article's purpose: two of its nine sections, eleven mentions, and
two topics every ranking page covered were dropped to make room.

Nobody decided that article was about the four-fifths rule. A note was copied into the wrong box.

So: the angle is about {{PRIMARY_KEYWORD}}. A gap can change HOW we cover that subject. It can
never change WHAT the subject is. If a gap is genuinely a different subject, it belongs in a
different article, and you leave it out of these two lines entirely.

────────────────────────────────────────────────────────────────────────
GOOGLE'S OWN ANSWER

{{AI_OVERVIEW}}

────────────────────────────────────────────────────────────────────────
WRITE THE ANGLE — two lines

Write what OUR READER GETS from our article about {{PRIMARY_KEYWORD}}.

Two lines is all you get. Start from the subject and what a person searching it needs, then let the
gaps sharpen it where they genuinely serve that same subject. Do NOT work through the gap list
covering as much of it as you can fit: that is how the angle becomes a list of other people's
omissions rather than a promise about the thing being searched for.

WRITE IT AS WHAT THE READER GETS, NEVER AS WHAT OTHER PAGES LACK.

The gaps above are how you WORK OUT the angle. They are not how you SAY it. Our reader has never
opened those pages and does not care that they exist. An angle written as a complaint about someone
else's page becomes an article that argues with that page instead of answering the question, and
that is what a reader feels when they land on it.

These words are banned from your two lines:
  instead of · unlike · rather than · whereas · absent from · never · only · fails to · stops at ·
  missing · omits · competitors · other pages · the ranking pages · this page · they

  Weak (a comparison):  "Dates every stat to its real survey year instead of blending 2022-2025
                         data together, and adds the AI figures this page omits entirely."
  Strong (what you get): "Every statistic carries the year it was measured, the sample it came from,
                         and who ran it. The AI-fabricated-resume figures get the same treatment."

Same facts, same gaps, same research. One argues. One delivers.

Let the common topics and Google's own answer shape it too: they tell you what a reader already
expects, so your angle should sit on top of that rather than repeat it.

  - Name concrete things the reader receives. Not a general virtue like "more depth" or "better
    structured".
  - A writer must be able to deliver it by reading and citing public sources. Not new data we would
    collect, not a tool, not original research.

Three tests, all must pass:
  1. Could you have written these two lines without seeing these search results? If yes, it is too
     general. Write it again.
  2. Read your two lines to someone who has never seen a search result page. If they only make sense
     as a comparison with something else, write them again.
  3. Show your two lines to somebody who just searched {{PRIMARY_KEYWORD}}. Would they say "yes,
     that is an article about what I searched for"? If the angle has drifted onto a neighbouring
     subject a gap pointed at, write it again. This test catches the four-fifths failure above,
     and it is the reason it is here.

Return JSON, nothing else:

{"angle": "<two lines>",
 "why_changed": "<one short line: what the old angle missed>"}
